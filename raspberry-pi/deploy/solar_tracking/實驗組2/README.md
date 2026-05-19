# 實驗組 II｜ANFIS 智慧追日 — system_id=2

樹莓派部署資料夾，**整個複製到 Pi 的 /home/pi/solar_tracking/實驗組2/**。

---

## 一、初次部署步驟

### 1. 把整個資料夾 SCP 到樹莓派

從 Windows PowerShell（在本機跑）：
```
scp -r .\raspberry-pi\deploy\solar_tracking\實驗組2 pi@<Pi-IP>:/home/pi/solar_tracking/
```

或用 SFTP 工具（FileZilla、WinSCP）拖過去。

### 2. SSH 進 Pi 確認檔案到位

```bash
ssh pi@<Pi-IP>
cd /home/pi/solar_tracking/實驗組2
ls -la
```

應該看到：$ctrlFile、config.json、equirements.txt、solar_tracking.service、start.sh、models/、README.md

### 3. 安裝 Python 套件

```bash
pip3 install -r requirements.txt
```

TensorFlow 在 Pi 4/5 上裝起來可能要 10-20 分鐘。如果太重，之後可以改用 	flite-runtime（需重訓模型為 .tflite）。

### 4. 確認硬體接線

打開 $ctrlFile，找到 CONFIG = { 區塊，依現場接線**至少確認**：

| 參數 | 說明 |
|------|------|
| 'system_id': 2 | 已預設為 2（不要改）|
| 'api_url' | 已預設為 Tailscale public URL，網內可改 $ApiUrlLocal |
| 'simulation_mode' | 測試時設 True，正式部署改 False |
| 'mcp3008' 通道 | 確認 LDR 東/西/南/北接 CH0/CH1/CH2/CH3 |
| 'ldr_calibration' | **必填**：各 LDR 校正係數（無校正時建議用相對值） |

### 5. 手動測試

```bash
cd /home/pi/solar_tracking/實驗組2
bash start.sh
```

預期：
- 看到 ANFIS 模型載入成功訊息
- LDR 讀值印出
- 預測角度印出
- 上傳到 Django API 成功

按 Ctrl+C 中斷。

### 6. 設定 systemd 開機自動啟動

```bash
sudo cp solar_tracking.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable solar_tracking
sudo systemctl start solar_tracking
```

### 7. 確認服務在跑

```bash
sudo systemctl status solar_tracking
tail -f /home/pi/solar_tracking/實驗組2/service.log
```

---

## 二、日常維運

### 重啟服務
```bash
sudo systemctl restart solar_tracking
```

### 看最近 log
```bash
tail -100 /home/pi/solar_tracking/實驗組2/service.log
```

### 暫停服務（保留設定）
```bash
sudo systemctl stop solar_tracking
```

### 完全移除
```bash
sudo systemctl stop solar_tracking
sudo systemctl disable solar_tracking
sudo rm /etc/systemd/system/solar_tracking.service
```

---

## 三、更新部署（之後從 Windows push）

當你改了控制器邏輯後從 Windows 重新跑 uild_pi_deploy.ps1，再：

```
# 在 Windows
scp -r .\raspberry-pi\deploy\solar_tracking\實驗組2 pi@<Pi-IP>:/home/pi/solar_tracking/

# 在 Pi
sudo systemctl restart solar_tracking
```

---

## 四、注意事項與 TODO

- **ANFIS 模型**：用 V2 (run05) 訓練版本，含照度。R²=0.844, RMSE=32.43W
- **推桿 GPIO**：_drive_ew() / _drive_ns() 內的 GPIO BCM pin 編號要依實際接線填入（目前是 placeholder）
- **霍爾感測器**：行程→角度對照表要實測後填入，否則無法精確閉迴路
- **INA3221**：CH1 = 兩支推桿合計、CH2 = 樹莓派；要在 CONFIG['ina3221'] 確認
- **MPPT RS485**：協定還沒解開，目前 voltage/current 上傳是從 INA3221 或 LDR ADC 估算
- **照度單位**：LDR 校正後輸出 W/m²，跟訓練時的 illumination 欄位一致
- **api_url**：預設指 Tailscale Funnel（外網可達）。若 Pi 跟 server 在同 WiFi，可改 LAN 內網 IP 加快速度

## 五、檔案清單

| 檔案 | 用途 |
|------|------|
| `anfis_controller.py` | 主控程式（包含 CONFIG + 所有邏輯）|
| `config.json` | 參數記錄（informational，目前控制器沒讀）|
| `requirements.txt` | Python 套件清單 |
| `solar_tracking.service` | systemd 服務定義 |
| `start.sh` | 手動測試啟動腳本 |
| `models/` | ANFIS 模型 + scaler + config |
| `README.md` | 本文件 |