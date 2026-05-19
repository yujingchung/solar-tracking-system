# ============================================================
# build_pi_deploy.ps1
# 重建 4 個樹莓派部署資料夾
#
# 產出：
#   raspberry-pi/deploy/solar_tracking/實驗組1/  (ANFIS, system_id=1)
#   raspberry-pi/deploy/solar_tracking/實驗組2/  (ANFIS, system_id=2)
#   raspberry-pi/deploy/solar_tracking/對照組1/  (Traditional, system_id=3)
#   raspberry-pi/deploy/solar_tracking/對照組2/  (Traditional, system_id=4)
#
# 每個資料夾內含：
#   - 主控程式 (.py，已自動把 system_id 改為對應值)
#   - config.json
#   - requirements.txt
#   - solar_tracking.service (systemd)
#   - start.sh
#   - README.md (詳細部署步驟)
#   - models/  (僅 ANFIS：含 .keras + scaler + config)
#
# 使用：
#   cd D:\宇靖\solar-tracking-dashboard
#   .\build_pi_deploy.ps1
# ============================================================

$ErrorActionPreference = 'Stop'
Set-Location 'D:\宇靖\solar-tracking-dashboard'
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8

$ApiUrl       = 'https://solar-dashboard.tail7c1eb9.ts.net/api'   # Tailscale Funnel public
$ApiUrlLocal  = 'http://192.168.0.124:8000/api'                    # 同網內備用

# 用絕對路徑，因為 [System.IO.File]::WriteAllText 使用 .NET process 的 CWD
# 而不是 PowerShell 的 $PWD（兩者可能不同步，造成 system32 找不到路徑的怪事）
$ProjectRoot  = (Resolve-Path .).Path
$DeployRoot   = Join-Path $ProjectRoot 'raspberry-pi\deploy\solar_tracking'
$SrcCtrlAnfis = Join-Path $ProjectRoot 'raspberry-pi\src\controllers\anfis_controller.py'
$SrcCtrlTrad  = Join-Path $ProjectRoot 'raspberry-pi\src\controllers\traditional_controller.py'
$ModelDir     = Join-Path $ProjectRoot 'algorithms\runs\run05_ds02_20260506_含照度'

# Pi 設定矩陣
$Pis = @(
    @{ Name='實驗組1'; Type='anfis';       SystemId=1; DeviceId='raspberry_pi_exp_1';  Title='實驗組 I｜ANFIS 智慧追日' },
    @{ Name='實驗組2'; Type='anfis';       SystemId=2; DeviceId='raspberry_pi_exp_2';  Title='實驗組 II｜ANFIS 智慧追日' },
    @{ Name='對照組1'; Type='traditional'; SystemId=3; DeviceId='raspberry_pi_ctrl_1'; Title='對照組 I｜差分感測追日' },
    @{ Name='對照組2'; Type='traditional'; SystemId=4; DeviceId='raspberry_pi_ctrl_2'; Title='對照組 II｜差分感測追日' }
)

Write-Host "═══════════════════════════════════════════════" -ForegroundColor Cyan
Write-Host "  建置 4 個樹莓派部署資料夾" -ForegroundColor Cyan
Write-Host "═══════════════════════════════════════════════" -ForegroundColor Cyan
Write-Host "  Source ANFIS    : $SrcCtrlAnfis"
Write-Host "  Source Traditional: $SrcCtrlTrad"
Write-Host "  Model directory : $ModelDir"
Write-Host "  Deploy target   : $DeployRoot\<pi-name>\"
Write-Host ""

# Sanity check
if (-not (Test-Path $SrcCtrlAnfis)) { Write-Host "✗ 找不到 $SrcCtrlAnfis" -ForegroundColor Red; exit 1 }
if (-not (Test-Path $SrcCtrlTrad))  { Write-Host "✗ 找不到 $SrcCtrlTrad"  -ForegroundColor Red; exit 1 }
if (-not (Test-Path $ModelDir))     { Write-Host "⚠ 找不到 $ModelDir，ANFIS pi 將沒有 model 檔" -ForegroundColor Yellow }

foreach ($pi in $Pis) {
    $name = $pi.Name
    $type = $pi.Type
    $sid  = $pi.SystemId
    $did  = $pi.DeviceId

    Write-Host ""
    Write-Host "── 處理 $name (system_id=$sid, type=$type) ──" -ForegroundColor Green

    $piDir = Join-Path $DeployRoot $name

    # 1. Clean & recreate
    if (Test-Path $piDir) {
        cmd /c "rmdir /s /q `"$piDir`"" 2>$null
    }
    New-Item -ItemType Directory -Force -Path $piDir | Out-Null

    # 2. Copy controller + customize system_id
    if ($type -eq 'anfis') {
        $src = $SrcCtrlAnfis
        $dst = Join-Path $piDir 'anfis_controller.py'
    } else {
        $src = $SrcCtrlTrad
        $dst = Join-Path $piDir 'traditional_controller.py'
    }
    $content = Get-Content $src -Raw -Encoding UTF8
    # 替換 system_id (Python dict 格式：'system_id': N,)
    $content = $content -replace "'system_id':\s*\d+,", "'system_id': $sid,"
    # 替換 api_url 為公開 URL
    $content = $content -replace "'api_url':\s*'http://localhost:8000/api'", "'api_url': '$ApiUrl'"
    [System.IO.File]::WriteAllText($dst, $content, [System.Text.UTF8Encoding]::new($false))
    Write-Host "  ✓ controller: $(Split-Path $dst -Leaf)"

    # 3. config.json (informational, 也可給未來改為動態載入用)
    $cfg = [PSCustomObject]@{
        system_id   = $sid
        device_id   = $did
        type        = $type
        api_url     = $ApiUrl
        api_url_lan = $ApiUrlLocal
        title       = $pi.Title
        location    = @{
            site      = '先鋒金土地公廟'
            latitude  = 25.10
            longitude = 121.43
            timezone  = 'Asia/Taipei'
        }
        notes = '此 config.json 為記錄用。實際生效設定在 controller .py 的 CONFIG dict 內。'
    } | ConvertTo-Json -Depth 5
    [System.IO.File]::WriteAllText((Join-Path $piDir 'config.json'), $cfg, [System.Text.UTF8Encoding]::new($false))
    Write-Host "  ✓ config.json"

    # 4. requirements.txt
    if ($type -eq 'anfis') {
        $req = @'
# 實驗組 (ANFIS 追日) Python 套件
# 安裝指令：pip3 install -r requirements.txt

gpiozero          # Raspberry Pi GPIO / MCP3008 ADC
RPi.GPIO          # gpiozero 底層驅動
smbus2            # INA3221 I2C 通訊
spidev            # MCP3008 SPI
numpy             # 數值計算
requests          # Django API 上傳
tensorflow        # ANFIS 模型推論 (用 tflite-runtime 替代會更輕)
joblib            # scaler 載入
# minimalmodbus   # MPPT RS485（確認協定後取消註解）
'@
    } else {
        $req = @'
# 對照組 (差分感測追日) Python 套件
# 安裝指令：pip3 install -r requirements.txt

gpiozero          # Raspberry Pi GPIO / MCP3008 ADC
RPi.GPIO          # gpiozero 底層驅動
smbus2            # INA3221 I2C 通訊
spidev            # MCP3008 SPI
requests          # Django API 上傳
# minimalmodbus   # MPPT RS485（確認協定後取消註解）
'@
    }
    [System.IO.File]::WriteAllText((Join-Path $piDir 'requirements.txt'), $req, [System.Text.UTF8Encoding]::new($false))
    Write-Host "  ✓ requirements.txt"

    # 5. systemd service
    $ctrlFile = if ($type -eq 'anfis') { 'anfis_controller.py' } else { 'traditional_controller.py' }
    $svc = @"
[Unit]
Description=Solar Tracking Controller ($name, system_id=$sid)
After=network.target
Wants=network-online.target

[Service]
Type=simple
User=pi
WorkingDirectory=/home/pi/solar_tracking/$name
ExecStart=/usr/bin/python3 /home/pi/solar_tracking/$name/$ctrlFile
Restart=on-failure
RestartSec=30
StandardOutput=append:/home/pi/solar_tracking/$name/service.log
StandardError=append:/home/pi/solar_tracking/$name/service.log

[Install]
WantedBy=multi-user.target
"@
    [System.IO.File]::WriteAllText((Join-Path $piDir 'solar_tracking.service'), $svc, [System.Text.UTF8Encoding]::new($false))
    Write-Host "  ✓ solar_tracking.service"

    # 6. start.sh
    $start = @"
#!/bin/bash
# $name 啟動腳本（手動測試用）
# 用法：bash start.sh

cd "`$(dirname "`$0")"
echo "=== $($pi.Title) 啟動 ==="
echo "工作目錄：`$(pwd)"
echo "Python  ：`$(which python3)"
echo "system_id：$sid"
echo ""

"@
    if ($type -eq 'anfis') {
        $start += @"
# ANFIS：確認模型檔案存在
if [ ! -f "models/anfis_with_illumination.keras" ]; then
    echo "[警告] 缺 models/anfis_with_illumination.keras"
    echo "       缺少模型時控制器會 fallback 到模擬預測（不可正式部署）"
fi

python3 $ctrlFile
"@
    } else {
        $start += @"
python3 $ctrlFile
"@
    }
    [System.IO.File]::WriteAllText((Join-Path $piDir 'start.sh'), $start, [System.Text.UTF8Encoding]::new($false))
    Write-Host "  ✓ start.sh"

    # 7. 複製 ANFIS 模型
    if ($type -eq 'anfis') {
        $modelsDir = Join-Path $piDir 'models'
        New-Item -ItemType Directory -Force -Path $modelsDir | Out-Null
        $modelFiles = @(
            'best_anfis.keras',
            'anfis_with_illumination.keras',
            'scaler_X_with_illumination.save',
            'model_config_with_illumination.json'
        )
        $copied = 0
        foreach ($mf in $modelFiles) {
            $srcM = Join-Path $ModelDir $mf
            if (Test-Path $srcM) {
                Copy-Item -Force $srcM (Join-Path $modelsDir $mf)
                $copied++
            }
        }
        Write-Host "  ✓ models/ ($copied 個檔案)"
    }

    # 8. README.md
    $readme = if ($type -eq 'anfis') {
        @"
# $($pi.Title) — system_id=$sid

樹莓派部署資料夾，**整個複製到 Pi 的 /home/pi/solar_tracking/$name/**。

---

## 一、初次部署步驟

### 1. 把整個資料夾 SCP 到樹莓派

從 Windows PowerShell（在本機跑）：
``````
scp -r .\raspberry-pi\deploy\solar_tracking\$name pi@<Pi-IP>:/home/pi/solar_tracking/
``````

或用 SFTP 工具（FileZilla、WinSCP）拖過去。

### 2. SSH 進 Pi 確認檔案到位

``````bash
ssh pi@<Pi-IP>
cd /home/pi/solar_tracking/$name
ls -la
``````

應該看到：`$ctrlFile`、`config.json`、`requirements.txt`、`solar_tracking.service`、`start.sh`、`models/`、`README.md`

### 3. 安裝 Python 套件

``````bash
pip3 install -r requirements.txt
``````

TensorFlow 在 Pi 4/5 上裝起來可能要 10-20 分鐘。如果太重，之後可以改用 `tflite-runtime`（需重訓模型為 .tflite）。

### 4. 確認硬體接線

打開 `$ctrlFile`，找到 `CONFIG = {` 區塊，依現場接線**至少確認**：

| 參數 | 說明 |
|------|------|
| `'system_id': $sid` | 已預設為 $sid（不要改）|
| `'api_url'` | 已預設為 Tailscale public URL，網內可改 `$ApiUrlLocal` |
| `'simulation_mode'` | 測試時設 `True`，正式部署改 `False` |
| `'mcp3008'` 通道 | 確認 LDR 東/西/南/北接 CH0/CH1/CH2/CH3 |
| `'ldr_calibration'` | **必填**：各 LDR 校正係數（無校正時建議用相對值） |

### 5. 手動測試

``````bash
cd /home/pi/solar_tracking/$name
bash start.sh
``````

預期：
- 看到 ANFIS 模型載入成功訊息
- LDR 讀值印出
- 預測角度印出
- 上傳到 Django API 成功

按 Ctrl+C 中斷。

### 6. 設定 systemd 開機自動啟動

``````bash
sudo cp solar_tracking.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable solar_tracking
sudo systemctl start solar_tracking
``````

### 7. 確認服務在跑

``````bash
sudo systemctl status solar_tracking
tail -f /home/pi/solar_tracking/$name/service.log
``````

---

## 二、日常維運

### 重啟服務
``````bash
sudo systemctl restart solar_tracking
``````

### 看最近 log
``````bash
tail -100 /home/pi/solar_tracking/$name/service.log
``````

### 暫停服務（保留設定）
``````bash
sudo systemctl stop solar_tracking
``````

### 完全移除
``````bash
sudo systemctl stop solar_tracking
sudo systemctl disable solar_tracking
sudo rm /etc/systemd/system/solar_tracking.service
``````

---

## 三、更新部署（之後從 Windows push）

當你改了控制器邏輯後從 Windows 重新跑 `build_pi_deploy.ps1`，再：

``````
# 在 Windows
scp -r .\raspberry-pi\deploy\solar_tracking\$name pi@<Pi-IP>:/home/pi/solar_tracking/

# 在 Pi
sudo systemctl restart solar_tracking
``````

---

## 四、注意事項與 TODO

- **ANFIS 模型**：用 V2 (run05) 訓練版本，含照度。R²=0.844, RMSE=32.43W
- **推桿 GPIO**：`_drive_ew()` / `_drive_ns()` 內的 GPIO BCM pin 編號要依實際接線填入（目前是 placeholder）
- **霍爾感測器**：行程→角度對照表要實測後填入，否則無法精確閉迴路
- **INA3221**：CH1 = 兩支推桿合計、CH2 = 樹莓派；要在 `CONFIG['ina3221']` 確認
- **MPPT RS485**：協定還沒解開，目前 voltage/current 上傳是從 INA3221 或 LDR ADC 估算
- **照度單位**：LDR 校正後輸出 W/m²，跟訓練時的 illumination 欄位一致
- **api_url**：預設指 Tailscale Funnel（外網可達）。若 Pi 跟 server 在同 WiFi，可改 LAN 內網 IP 加快速度

## 五、檔案清單

| 檔案 | 用途 |
|------|------|
| ``$ctrlFile`` | 主控程式（包含 CONFIG + 所有邏輯）|
| ``config.json`` | 參數記錄（informational，目前控制器沒讀）|
| ``requirements.txt`` | Python 套件清單 |
| ``solar_tracking.service`` | systemd 服務定義 |
| ``start.sh`` | 手動測試啟動腳本 |
| ``models/`` | ANFIS 模型 + scaler + config |
| ``README.md`` | 本文件 |
"@
    } else {
        @"
# $($pi.Title) — system_id=$sid

樹莓派部署資料夾，**整個複製到 Pi 的 /home/pi/solar_tracking/$name/**。

對照組不使用 ANFIS，採用「**差分感測追日**」演算法：比較東/西、南/北 LDR 差值，超過閾值就驅動推桿往光較強的方向。

---

## 一、初次部署步驟

### 1. 把整個資料夾 SCP 到樹莓派

從 Windows PowerShell（在本機跑）：
``````
scp -r .\raspberry-pi\deploy\solar_tracking\$name pi@<Pi-IP>:/home/pi/solar_tracking/
``````

### 2. SSH 進 Pi 確認檔案到位

``````bash
ssh pi@<Pi-IP>
cd /home/pi/solar_tracking/$name
ls -la
``````

### 3. 安裝 Python 套件

``````bash
pip3 install -r requirements.txt
``````

對照組不用 TensorFlow，安裝快很多。

### 4. 確認硬體接線

打開 `$ctrlFile`，找到 `CONFIG = {` 區塊，**至少確認**：

| 參數 | 說明 |
|------|------|
| `'system_id': $sid` | 已預設為 $sid（不要改）|
| `'api_url'` | 已預設為 Tailscale public URL |
| `'simulation_mode'` | 測試時 `True`，正式部署 `False` |
| `'threshold': 50` | LDR ADC 差值門檻（超過才移動），可調 |
| `'mcp3008'` 通道 | 確認 LDR 東/西/南/北接 CH0/CH1/CH2/CH3 |
| `'interval_seconds': 600` | 每 10 分鐘檢查一次 |

### 5. 手動測試

``````bash
cd /home/pi/solar_tracking/$name
bash start.sh
``````

預期：
- LDR 讀值印出
- 差值計算 + 移動決策印出
- 上傳到 Django API 成功

### 6. 設定 systemd 開機自動啟動

``````bash
sudo cp solar_tracking.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable solar_tracking
sudo systemctl start solar_tracking
``````

### 7. 確認服務在跑

``````bash
sudo systemctl status solar_tracking
tail -f /home/pi/solar_tracking/$name/service.log
``````

---

## 二、日常維運

### 重啟服務
``````bash
sudo systemctl restart solar_tracking
``````

### 看最近 log
``````bash
tail -100 /home/pi/solar_tracking/$name/service.log
``````

---

## 三、跟實驗組的差異

| 項目 | 對照組（本資料夾） | 實驗組 |
|------|-----------------|--------|
| 演算法 | 差分感測（LDR 差值）| ANFIS 預測 |
| 依賴 | gpiozero, smbus2, requests | + tensorflow, joblib |
| 模型檔 | 無 | models/*.keras |
| CPU 負載 | 低 | 中（TF 推論）|
| 安裝時間 | ~5 分鐘 | ~20 分鐘 |
| 角度更新邏輯 | LDR 差值 > threshold 就動 | 預測增益 > worthiness 才動 |

---

## 四、注意事項與 TODO

- **GPIO 接線**：`_drive_ew()` / `_drive_ns()` 內的 BCM pin 編號要依實際接線
- **霍爾感測器**：行程→角度對照表要實測後填入
- **INA3221**：CH1 = 兩支推桿合計、CH2 = 樹莓派
- **MPPT RS485**：協定未解，目前 voltage/current 從 INA3221 估算

## 五、檔案清單

| 檔案 | 用途 |
|------|------|
| ``$ctrlFile`` | 主控程式（包含 CONFIG + 所有邏輯）|
| ``config.json`` | 參數記錄（informational）|
| ``requirements.txt`` | Python 套件清單 |
| ``solar_tracking.service`` | systemd 服務定義 |
| ``start.sh`` | 手動測試啟動腳本 |
| ``README.md`` | 本文件 |
"@
    }
    [System.IO.File]::WriteAllText((Join-Path $piDir 'README.md'), $readme, [System.Text.UTF8Encoding]::new($false))
    Write-Host "  ✓ README.md"
}

# ────────────────────────────────────────────────────────────
# 總結
# ────────────────────────────────────────────────────────────
Write-Host ""
Write-Host "═══════════════════════════════════════════════" -ForegroundColor Cyan
Write-Host "  完成。4 個資料夾結構：" -ForegroundColor Cyan
Write-Host "═══════════════════════════════════════════════" -ForegroundColor Cyan
foreach ($pi in $Pis) {
    $piDir = Join-Path $DeployRoot $pi.Name
    $files = (Get-ChildItem -Recurse -File $piDir).Count
    $size  = "{0:N1}" -f ((Get-ChildItem -Recurse -File $piDir | Measure-Object Length -Sum).Sum / 1KB)
    Write-Host "  $($pi.Name) → $files 個檔案，${size} KB"
}

Write-Host ""
Write-Host "下一步：" -ForegroundColor Yellow
Write-Host "  1. cd raspberry-pi\deploy\solar_tracking\實驗組1\"
Write-Host "  2. 開 README.md 跟著步驟做"
Write-Host "  3. scp -r 整個資料夾上 Pi"
Write-Host "  4. ssh 進去後按 README 安裝 + 設定"
