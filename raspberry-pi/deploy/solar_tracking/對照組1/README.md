# 對照組 I｜差分感測追日 — system_id=3

樹莓派部署資料夾，**整個複製到 Pi 的 /home/pi/solar_tracking/對照組1/**。

對照組不使用 ANFIS，採用「**差分感測追日**」演算法：比較東/西、南/北 LDR 差值，超過閾值就驅動推桿往光較強的方向。

---

## 一、初次部署步驟

### 1. 把整個資料夾 SCP 到樹莓派

從 Windows PowerShell（在本機跑）：
```
scp -r .\raspberry-pi\deploy\solar_tracking\對照組1 pi@<Pi-IP>:/home/pi/solar_tracking/
```

### 2. SSH 進 Pi 確認檔案到位

```bash
ssh pi@<Pi-IP>
cd /home/pi/solar_tracking/對照組1
ls -la
```

### 3. 安裝 Python 套件

```bash
pip3 install -r requirements.txt
```

對照組不用 TensorFlow，安裝快很多。

### 4. 確認硬體接線

打開 $ctrlFile，找到 CONFIG = { 區塊，**至少確認**：

| 參數 | 說明 |
|------|------|
| 'system_id': 3 | 已預設為 3（不要改）|
| 'api_url' | 已預設為 Tailscale public URL |
| 'simulation_mode' | 測試時 True，正式部署 False |
| 'threshold': 50 | LDR ADC 差值門檻（超過才移動），可調 |
| 'mcp3008' 通道 | 確認 LDR 東/西/南/北接 CH0/CH1/CH2/CH3 |
| 'interval_seconds': 600 | 每 10 分鐘檢查一次 |

### 5. 手動測試

```bash
cd /home/pi/solar_tracking/對照組1
bash start.sh
```

預期：
- LDR 讀值印出
- 差值計算 + 移動決策印出
- 上傳到 Django API 成功

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
tail -f /home/pi/solar_tracking/對照組1/service.log
```

---

## 二、日常維運

### 重啟服務
```bash
sudo systemctl restart solar_tracking
```

### 看最近 log
```bash
tail -100 /home/pi/solar_tracking/對照組1/service.log
```

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

- **GPIO 接線**：_drive_ew() / _drive_ns() 內的 BCM pin 編號要依實際接線
- **霍爾感測器**：行程→角度對照表要實測後填入
- **INA3221**：CH1 = 兩支推桿合計、CH2 = 樹莓派
- **MPPT RS485**：協定未解，目前 voltage/current 從 INA3221 估算

## 五、檔案清單

| 檔案 | 用途 |
|------|------|
| `traditional_controller.py` | 主控程式（包含 CONFIG + 所有邏輯）|
| `config.json` | 參數記錄（informational）|
| `requirements.txt` | Python 套件清單 |
| `solar_tracking.service` | systemd 服務定義 |
| `start.sh` | 手動測試啟動腳本 |
| `README.md` | 本文件 |