# =====================================================================
#  1_在舊機執行_打包.ps1
#  在「舊機」執行：把 git 以外的必要檔案打包成一個資料夾，方便搬到新機
#  用法： powershell -ExecutionPolicy Bypass -File .\1_在舊機執行_打包.ps1
# =====================================================================

$ErrorActionPreference = 'Stop'
$OutputEncoding = [System.Text.Encoding]::UTF8

# 專案根目錄 = 本腳本所在資料夾的上一層
$ScriptDir   = Split-Path -Parent $MyInvocation.MyCommand.Path
$ProjectRoot = Split-Path -Parent $ScriptDir

# 輸出檔包位置（桌面）
$Stamp   = Get-Date -Format 'yyyyMMdd'
$OutDir  = Join-Path ([Environment]::GetFolderPath('Desktop')) "solar_migration_包_$Stamp"

Write-Host "==================================================" -ForegroundColor Cyan
Write-Host " 太陽能專案 移植打包" -ForegroundColor Cyan
Write-Host " 專案根目錄： $ProjectRoot"
Write-Host " 輸出檔包：   $OutDir"
Write-Host "==================================================" -ForegroundColor Cyan

New-Item -ItemType Directory -Force -Path $OutDir | Out-Null
New-Item -ItemType Directory -Force -Path (Join-Path $OutDir 'data') | Out-Null

# ---- 1) .env.dev（機密設定） ----
$envSrc = Join-Path $ProjectRoot '.env.dev'
if (Test-Path $envSrc) {
    Copy-Item $envSrc (Join-Path $OutDir '.env.dev') -Force
    Write-Host "[OK] .env.dev 已複製" -ForegroundColor Green
} else {
    Write-Host "[警告] 找不到 .env.dev！" -ForegroundColor Yellow
}

# ---- 2) 主資料集 CSV（排除 .bak 備份） ----
$csv = Get-ChildItem (Join-Path $ProjectRoot 'data') -Filter '*processed.csv' -File |
       Where-Object { $_.Name -notlike '*.bak.*' } |
       Select-Object -First 1
if ($csv) {
    Copy-Item $csv.FullName (Join-Path $OutDir "data\$($csv.Name)") -Force
    $sizeMB = [math]::Round($csv.Length / 1MB, 1)
    Write-Host "[OK] 主資料集已複製： $($csv.Name) ($sizeMB MB)" -ForegroundColor Green
} else {
    Write-Host "[警告] 找不到主資料集 CSV！" -ForegroundColor Yellow
}

# ---- 3) solar_angle_data.db ----
$db = Join-Path $ProjectRoot 'solar_angle_data.db'
if (Test-Path $db) {
    Copy-Item $db (Join-Path $OutDir 'solar_angle_data.db') -Force
    Write-Host "[OK] solar_angle_data.db 已複製" -ForegroundColor Green
} else {
    Write-Host "[略過] 找不到 solar_angle_data.db（可能不需要）" -ForegroundColor DarkGray
}

# ---- 4) MySQL mysqldump（容器需在執行中） ----
$dumpPath = Join-Path $OutDir 'solar_db_dump.sql'
$running = (docker ps --filter "name=solar_db" --format "{{.Names}}" 2>$null)
if ($running -match 'solar_db') {
    Write-Host "[..] 正在 mysqldump solar_db ..." -ForegroundColor Cyan
    docker exec solar_db sh -c 'exec mysqldump -uroot -p"$MYSQL_ROOT_PASSWORD" --databases $MYSQL_DATABASE' |
        Out-File -FilePath $dumpPath -Encoding utf8
    if ((Test-Path $dumpPath) -and ((Get-Item $dumpPath).Length -gt 0)) {
        Write-Host "[OK] MySQL 已匯出： solar_db_dump.sql" -ForegroundColor Green
    } else {
        Write-Host "[警告] mysqldump 似乎沒產出內容，請檢查容器" -ForegroundColor Yellow
    }
} else {
    Write-Host "[略過] solar_db 容器未執行，未匯出 MySQL" -ForegroundColor Yellow
    Write-Host "       若需要即時資料，請先 docker-compose up -d 再重跑本腳本，" -ForegroundColor Yellow
    Write-Host "       或改用整夾複製 mysql\ 資料夾的方式。" -ForegroundColor Yellow
}

Write-Host "==================================================" -ForegroundColor Cyan
Write-Host " 打包完成！" -ForegroundColor Green
Write-Host " 請把這個資料夾搬到新機： $OutDir" -ForegroundColor Green
Write-Host "==================================================" -ForegroundColor Cyan
explorer $OutDir
