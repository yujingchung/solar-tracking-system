# ============================================================
# solar_weekly_run.ps1
# Solar tracking system weekly maintenance
# Triggered by Windows Task Scheduler every Monday 02:00
#
# Steps:
#   1. Verify solar_backend Docker container is running
#   2. Run z3a_check_token.py to check token expiry
#   3. If token valid, run z3a_collect.py --pipeline --days 7
#   4. POST to backend reload endpoint
#   5. List recent backup files
#   6. Save full log to logs\solar_YYYY-MM-DD.log
#
# Manual run (test):
#   cd D:\宇靖\solar-tracking-dashboard
#   .\solar_weekly_run.ps1
# ============================================================

$ErrorActionPreference = 'Continue'
# Use $PSScriptRoot to avoid hardcoding Chinese path which has encoding issues
$ProjectRoot = if ($PSScriptRoot) { $PSScriptRoot } else { Split-Path -Parent $MyInvocation.MyCommand.Path }
Set-Location $ProjectRoot

# CRITICAL: Force Python to use UTF-8 for I/O
# Windows default is CP950 (Traditional Chinese), which cannot encode
# simplified Chinese characters like 时 in Z3A cloud CSV column names.
# Without this, step 4 (pvlib) silently fails to write any data.
$env:PYTHONIOENCODING = 'utf-8'
$env:PYTHONUTF8       = '1'
# Also switch console codepage to UTF-8 (65001) for safe output
try { chcp 65001 | Out-Null } catch { }
# CRITICAL: Tell PowerShell to DECODE child process stdout as UTF-8,
# otherwise PS reads Python's UTF-8 bytes as CP950 and produces mojibake.
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$OutputEncoding           = [System.Text.Encoding]::UTF8

# Ensure logs/ directory exists
$LogDir = Join-Path $ProjectRoot 'logs'
if (-not (Test-Path $LogDir)) { New-Item -ItemType Directory -Path $LogDir | Out-Null }

# Today's log file
$Today    = Get-Date -Format 'yyyy-MM-dd'
$LogFile  = Join-Path $LogDir "solar_weekly_$Today.log"

# Log helper
function Write-Log {
    param([string]$Message, [string]$Level = 'INFO')
    $line = "[$((Get-Date).ToString('yyyy-MM-dd HH:mm:ss'))] [$Level] $Message"
    Write-Host $line
    Add-Content -Path $LogFile -Value $line -Encoding UTF8
}

Write-Log "============================================================"
Write-Log "Weekly maintenance started"
Write-Log "============================================================"

# Variables for final report
$BackendStatus = '?'
$TokenStatus   = '?'
$CollectResult = '?'
$ReloadStatus  = '?'
$ShouldCollect = $false
$BackupFiles   = @()


# ------------------------------------------------------------
# Stage 1: Backend health check
# ------------------------------------------------------------
Write-Log ''
Write-Log '-- Stage 1: Backend health check --'

try {
    $dockerStatus = & docker ps --filter "name=solar_backend" --format "{{.Status}}" 2>&1
    if (-not $dockerStatus) {
        Write-Log 'solar_backend not running, attempting to start...' 'WARN'
        & docker-compose -f docker-compose-dev.yml up -d backend 2>&1 | ForEach-Object { Write-Log $_ }
        Start-Sleep -Seconds 10
        $dockerStatus = & docker ps --filter "name=solar_backend" --format "{{.Status}}" 2>&1
    }
    if ($dockerStatus -match '^Up') {
        Write-Log "OK Docker container running: $dockerStatus"
        try {
            $resp = Invoke-WebRequest -Uri 'http://localhost:8000/api/fixed-panels/status/' -UseBasicParsing -TimeoutSec 10
            if ($resp.StatusCode -eq 200) {
                Write-Log 'OK Django API 200'
                $BackendStatus = "OK ($dockerStatus)"
            } else {
                Write-Log "WARN Django returned $($resp.StatusCode)" 'WARN'
                $BackendStatus = "WARN Django returned $($resp.StatusCode)"
            }
        } catch {
            Write-Log "WARN Django API no response: $($_.Exception.Message)" 'WARN'
            $BackendStatus = "WARN Django API no response"
        }
    } else {
        Write-Log "FAIL Docker container start failed" 'ERROR'
        $BackendStatus = "FAIL Container not running"
    }
} catch {
    Write-Log "FAIL Stage 1 exception: $($_.Exception.Message)" 'ERROR'
    $BackendStatus = "FAIL Cannot check (docker command error)"
}


# ------------------------------------------------------------
# Stage 2: Token status check
# ------------------------------------------------------------
Write-Log ''
Write-Log '-- Stage 2: Token status check --'

try {
    $tokenOutput = & python -X utf8 z3a_check_token.py 2>&1
    $tokenOutput | ForEach-Object { Write-Log $_ }

    # Find access token line and parse days remaining
    # Only parse the FIRST "剩 N.N 天" or "剩 N.N hours" found in output.
    # z3a_check_token.py emits "  狀態：✓ 有效 — 剩 9.3 天" for the access token first,
    # so we exit on first match.
    $daysLeft = $null
    foreach ($line in $tokenOutput) {
        $s = "$line"
        # Specifically require the "剩" keyword followed by a number
        if ($s -match '剩\s+(\d+(?:\.\d+)?)\s*天') {
            try { $daysLeft = [double]$Matches[1] } catch { }
            break
        }
        if ($s -match '剩\s+(\d+(?:\.\d+)?)\s*小時') {
            try { $daysLeft = [double]$Matches[1] / 24.0 } catch { }
            break
        }
        if ($s -match '已過期' -or $s -match 'expired') {
            $daysLeft = -1
            break
        }
        # English fallback (in case z3a_check_token.py is rewritten)
        if ($s -match '(\d+(?:\.\d+)?)\s+days\s+left') {
            try { $daysLeft = [double]$Matches[1] } catch { }
            break
        }
    }

    if ($null -eq $daysLeft) {
        Write-Log "WARN Cannot parse token status" 'WARN'
        $TokenStatus = 'WARN Cannot parse output'
        $ShouldCollect = $true
    } elseif ($daysLeft -lt 0) {
        $TokenStatus = "FAIL Token expired"
        $ShouldCollect = $false
    } elseif ($daysLeft -lt 1) {
        $TokenStatus = "URGENT expires in $([Math]::Round($daysLeft * 24, 1)) hours"
        $ShouldCollect = $true
    } elseif ($daysLeft -lt 3) {
        $TokenStatus = "URGENT $([Math]::Round($daysLeft, 1)) days left, update NOW"
        $ShouldCollect = $true
    } elseif ($daysLeft -lt 7) {
        $TokenStatus = "WARN $([Math]::Round($daysLeft, 1)) days left, update this week"
        $ShouldCollect = $true
    } else {
        $TokenStatus = "OK ($([Math]::Round($daysLeft, 1)) days left)"
        $ShouldCollect = $true
    }
    Write-Log "Token status: $TokenStatus, ShouldCollect=$ShouldCollect"

} catch {
    Write-Log "FAIL Stage 2 exception: $($_.Exception.Message)" 'ERROR'
    $TokenStatus = "FAIL Check failed"
    $ShouldCollect = $true
}


# ------------------------------------------------------------
# Stage 3: Z3A data collection (conditional)
# ------------------------------------------------------------
Write-Log ''
Write-Log '-- Stage 3: Z3A data collection --'

if (-not $ShouldCollect) {
    Write-Log 'Skip collection: token expired'
    $CollectResult = 'Skipped (token expired, update first)'
    $ReloadStatus  = 'N/A: collection not run'
} else {
    try {
        Write-Log 'Running: python -X utf8 z3a_collect.py --pipeline --days 7'
        $collectOutput = & python -X utf8 z3a_collect.py --pipeline --days 7 2>&1
        $collectOutput | ForEach-Object { Write-Log $_ }
        $exitCode = $LASTEXITCODE

        if ($exitCode -eq 0) {
            # Parse new rows and total rows from output (pipeline mode emits both)
            $newRows   = $null
            $totalRows = $null
            foreach ($line in $collectOutput) {
                $s = "$line"
                # pipeline merge result: "新資料（pipeline 輸出）：N 筆"
                if ($null -eq $newRows -and $s -match '新資料.*?[：:]\s*([\d,]+)\s*筆') {
                    $newRows = $Matches[1]
                }
                # Total in CSV after merge: "（共 N 筆）" or "共 N 筆"
                if ($null -eq $totalRows -and $s -match '共\s*([\d,]+)\s*筆') {
                    $totalRows = $Matches[1]
                }
            }
            if ($null -eq $newRows) { $newRows = '?' }
            if ($null -eq $totalRows) { $totalRows = '?' }

            # Convert to int for warning check
            $newRowsInt = 0
            try { $newRowsInt = [int]($newRows -replace ',', '') } catch { $newRowsInt = -1 }

            if ($newRowsInt -eq 0) {
                $CollectResult = "WARN exit=0 but 0 new rows merged (pipeline step 4 may have failed silently); total=$totalRows"
                Write-Log "WARN Collection: $CollectResult" 'WARN'
            } else {
                $CollectResult = "OK new=$newRows total=$totalRows"
                Write-Log "OK Collection complete: $CollectResult"
            }

            # Stage 3.5: notify backend reload
            Write-Log '-- Stage 3.5: notify backend reload --'
            try {
                $reloadResp = Invoke-RestMethod -Uri 'http://localhost:8000/api/fixed-panels/reload/' -Method POST -TimeoutSec 30
                if ($reloadResp.success -eq $true) {
                    $ReloadStatus = "OK reloaded ($($reloadResp.df_rows) rows, range $($reloadResp.date_range.start) ~ $($reloadResp.date_range.end))"
                } else {
                    $ReloadStatus = "WARN reload API returned success=false"
                }
                Write-Log "OK Reload: $ReloadStatus"
            } catch {
                Write-Log "WARN Reload failed: $($_.Exception.Message)" 'WARN'
                $ReloadStatus = 'WARN failed (backend will mtime auto-reload next start)'
            }
        } else {
            Write-Log "FAIL z3a_collect.py exit code $exitCode" 'ERROR'
            $CollectResult = "FAIL exit code $exitCode"
            $ReloadStatus = 'N/A: collection failed'
        }
    } catch {
        Write-Log "FAIL Stage 3 exception: $($_.Exception.Message)" 'ERROR'
        $CollectResult = "FAIL exception: $($_.Exception.Message)"
        $ReloadStatus = 'N/A: collection exception'
    }
}


# ------------------------------------------------------------
# Stage 4: List recent backup files
# ------------------------------------------------------------
Write-Log ''
Write-Log '-- Stage 4: List recent backup files --'

try {
    $BackupFiles = Get-ChildItem -Path (Join-Path $ProjectRoot 'data\*.bak.*.csv') -ErrorAction SilentlyContinue |
                   Sort-Object LastWriteTime -Descending |
                   Select-Object -First 3
    foreach ($f in $BackupFiles) {
        $sizeMb = [Math]::Round($f.Length / 1MB, 1)
        Write-Log ("  $($f.Name) ({0} MB, $($f.LastWriteTime.ToString('MM/dd HH:mm')))" -f $sizeMb)
    }
} catch {
    Write-Log "WARN Cannot list backup files: $($_.Exception.Message)" 'WARN'
}


# ------------------------------------------------------------
# Final report
# ------------------------------------------------------------
$ReportPath = Join-Path $LogDir 'latest_report.txt'

$reportLines = @()
$reportLines += '============================================'
$reportLines += "[$Today] Solar maintenance report"
$reportLines += '============================================'
$reportLines += ''
$reportLines += "Backend health : $BackendStatus"
$reportLines += "Token status   : $TokenStatus"
$reportLines += "Data collection: $CollectResult"
$reportLines += "Cache reload   : $ReloadStatus"
$reportLines += ''
$reportLines += 'Recent backups:'
if ($BackupFiles) {
    foreach ($f in $BackupFiles) {
        $sizeMb = [Math]::Round($f.Length / 1MB, 1)
        $reportLines += "  - $($f.Name) ($sizeMb MB, $($f.LastWriteTime.ToString('MM/dd HH:mm')))"
    }
} else {
    $reportLines += '  (none)'
}
$reportLines += ''
$reportLines += "Full log: $LogFile"
$reportLines += '============================================'

$report = $reportLines -join "`r`n"

Write-Log ''
Write-Log '============================================================'
$reportLines | ForEach-Object { Write-Log $_ }
Write-Log '============================================================'
Set-Content -Path $ReportPath -Value $report -Encoding UTF8

Write-Host ''
Write-Host "Full log:    $LogFile"
Write-Host "Last report: $ReportPath"
