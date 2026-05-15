# ============================================================
# register_task_scheduler.ps1
# Register solar_weekly_run.ps1 to Windows Task Scheduler
# Schedule: every Monday 02:00
#
# Usage (must run PowerShell as Administrator):
#   cd D:\宇靖\solar-tracking-dashboard
#   .\register_task_scheduler.ps1
#
# Unregister:
#   Unregister-ScheduledTask -TaskName 'SolarWeeklyMaintenance' -Confirm:$false
# ============================================================

$TaskName    = 'SolarWeeklyMaintenance'
# Use $PSScriptRoot to avoid hardcoding Chinese path (encoding issues)
$ProjectRoot = if ($PSScriptRoot) { (Get-Item $PSScriptRoot).FullName } else { (Get-Item (Split-Path -Parent $MyInvocation.MyCommand.Path)).FullName }
$ScriptPath  = Join-Path $ProjectRoot 'solar_weekly_run.ps1'
$WorkingDir  = $ProjectRoot

Write-Host "Project root resolved to: $ProjectRoot" -ForegroundColor Cyan
Write-Host "Will register script:     $ScriptPath" -ForegroundColor Cyan

# Verify script exists
if (-not (Test-Path $ScriptPath)) {
    Write-Host "ERROR: cannot find $ScriptPath" -ForegroundColor Red
    exit 1
}

# 1. Action: run powershell with bypass exec policy
$Action = New-ScheduledTaskAction `
    -Execute 'powershell.exe' `
    -Argument "-ExecutionPolicy Bypass -NoProfile -File `"$ScriptPath`"" `
    -WorkingDirectory $WorkingDir

# 2. Trigger: weekly Monday 02:00
$Trigger = New-ScheduledTaskTrigger -Weekly -DaysOfWeek Monday -At '02:00'

# 3. Settings
$Settings = New-ScheduledTaskSettingsSet `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -StartWhenAvailable `
    -ExecutionTimeLimit (New-TimeSpan -Hours 2) `
    -RestartCount 3 `
    -RestartInterval (New-TimeSpan -Minutes 10)

# 4. Principal: run as current user with highest privileges
$Principal = New-ScheduledTaskPrincipal `
    -UserId $env:USERNAME `
    -LogonType S4U `
    -RunLevel Highest

# 5. Register (overwrite if exists)
try {
    if (Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue) {
        Write-Host "Existing $TaskName found, removing first..." -ForegroundColor Yellow
        Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false
    }
    Register-ScheduledTask `
        -TaskName $TaskName `
        -Description 'Solar tracking system weekly maintenance: docker check + token check + z3a_collect + reload' `
        -Action $Action `
        -Trigger $Trigger `
        -Settings $Settings `
        -Principal $Principal | Out-Null
    Write-Host "OK: registered task: $TaskName" -ForegroundColor Green
    Write-Host ''
    Write-Host 'Task details:' -ForegroundColor Cyan
    Get-ScheduledTask -TaskName $TaskName | Get-ScheduledTaskInfo | Format-List NextRunTime, LastRunTime, LastTaskResult
    Write-Host 'Manual test run:' -ForegroundColor Cyan
    Write-Host "  Start-ScheduledTask -TaskName '$TaskName'"
    Write-Host 'View history:' -ForegroundColor Cyan
    Write-Host "  Get-ScheduledTask -TaskName '$TaskName' | Get-ScheduledTaskInfo"
    Write-Host 'Unregister:' -ForegroundColor Cyan
    Write-Host "  Unregister-ScheduledTask -TaskName '$TaskName' -Confirm:`$false"
} catch {
    Write-Host "FAILED: $($_.Exception.Message)" -ForegroundColor Red
    Write-Host 'Possible causes:' -ForegroundColor Yellow
    Write-Host '  1. PowerShell not running as Administrator'
    Write-Host '  2. UAC blocking'
    Write-Host '  3. User account missing batch logon right'
    exit 1
}
