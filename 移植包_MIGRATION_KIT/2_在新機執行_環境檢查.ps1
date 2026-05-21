# =====================================================================
#  2_在新機執行_環境檢查.ps1
#  在「新機」執行：檢查前置軟體、環境變數、專案檔案是否就緒
#  用法： powershell -ExecutionPolicy Bypass -File .\2_在新機執行_環境檢查.ps1
#  （唯讀檢查，不會改動任何東西）
# =====================================================================

$OutputEncoding = [System.Text.Encoding]::UTF8

$ScriptDir   = Split-Path -Parent $MyInvocation.MyCommand.Path
$ProjectRoot = Split-Path -Parent $ScriptDir

$pass = 0; $warn = 0

function Check-Cmd($name, $cmd) {
    $exists = Get-Command $cmd -ErrorAction SilentlyContinue
    if ($exists) {
        try { $v = & $cmd --version 2>&1 | Select-Object -First 1 } catch { $v = '' }
        Write-Host ("[OK]   {0,-20} {1}" -f $name, $v) -ForegroundColor Green
        $script:pass++
    } else {
        Write-Host ("[缺]   {0,-20} 找不到，請安裝" -f $name) -ForegroundColor Yellow
        $script:warn++
    }
}

function Check-File($desc, $path) {
    if (Test-Path $path) {
        Write-Host ("[OK]   {0,-20} {1}" -f $desc, $path) -ForegroundColor Green
        $script:pass++
    } else {
        Write-Host ("[缺]   {0,-20} 找不到： {1}" -f $desc, $path) -ForegroundColor Yellow
        $script:warn++
    }
}

Write-Host "==================================================" -ForegroundColor Cyan
Write-Host " 新機環境檢查　專案根目錄： $ProjectRoot" -ForegroundColor Cyan
Write-Host "==================================================" -ForegroundColor Cyan

Write-Host "`n--- 前置軟體 ---"
Check-Cmd 'Docker'         'docker'
Check-Cmd 'docker-compose' 'docker-compose'
Check-Cmd 'Git'            'git'
Check-Cmd 'Python'         'python'
Check-Cmd 'pip'            'pip'

Write-Host "`n--- 環境變數 ---"
if ($env:PYTHONUTF8 -eq '1') {
    Write-Host "[OK]   PYTHONUTF8          = 1" -ForegroundColor Green; $pass++
} else {
    Write-Host "[缺]   PYTHONUTF8          未設為 1（會導致 Z3A 簡體字靜默失敗！）" -ForegroundColor Yellow
    Write-Host "       設定 → 系統 → 進階 → 環境變數 → 新增 PYTHONUTF8=1，再重開終端機" -ForegroundColor Yellow
    $warn++
}

Write-Host "`n--- 必要檔案（git 以外） ---"
Check-File '.env.dev'              (Join-Path $ProjectRoot '.env.dev')
Check-File '主資料集 CSV'           (Join-Path $ProjectRoot 'data')
Check-File 'solar_angle_data.db'   (Join-Path $ProjectRoot 'solar_angle_data.db')
Check-File 'docker-compose-dev.yml'(Join-Path $ProjectRoot 'docker-compose-dev.yml')

# 進一步確認 data 內真的有非備份的主 CSV
$mainCsv = Get-ChildItem (Join-Path $ProjectRoot 'data') -Filter '*processed.csv' -File -ErrorAction SilentlyContinue |
           Where-Object { $_.Name -notlike '*.bak.*' }
if ($mainCsv) {
    Write-Host ("[OK]   主資料集檔名         {0}" -f $mainCsv[0].Name) -ForegroundColor Green; $pass++
} else {
    Write-Host "[缺]   data\ 內找不到主資料集 CSV（非 .bak）" -ForegroundColor Yellow; $warn++
}

# .env.dev 內 Z3A_CSV_PATH 是否還指向舊機路徑
$envFile = Join-Path $ProjectRoot '.env.dev'
if (Test-Path $envFile) {
    $line = Select-String -Path $envFile -Pattern '^Z3A_CSV_PATH=' -ErrorAction SilentlyContinue
    if ($line) {
        Write-Host "`n--- 提醒 ---"
        Write-Host ("       .env.dev 目前 {0}" -f $line.Line) -ForegroundColor DarkYellow
        Write-Host "       請確認此路徑是【新機】的 CSV 完整路徑，不是舊機的！" -ForegroundColor DarkYellow
    }
}

Write-Host "`n=================================================="
if ($warn -eq 0) {
    Write-Host " 全部通過（$pass 項）。可以進行步驟 7 啟動 Docker。" -ForegroundColor Green
} else {
    Write-Host " 通過 $pass 項，待處理 $warn 項（見上面黃字）。" -ForegroundColor Yellow
}
Write-Host "=================================================="
