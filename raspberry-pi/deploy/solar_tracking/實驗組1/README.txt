=====================================
  太陽能追日系統 — 實驗組 I｜ANFIS 智慧追日｜system_id=1
=====================================

【部署步驟】

1. 將整個 實驗組1/ 資料夾複製到樹莓派：
   放置路徑：/home/pi/solar_tracking/實驗組1/

2. 安裝 Python 套件：
   pip3 install -r requirements.txt

3. （僅實驗組）將模型檔案放入 models/ 資料夾：
   請見 models/README.txt 的說明

4. 填寫硬體設定（首次部署必做）：
   打開 anfis_controller.py，找到 CONFIG 區塊，確認以下設定：
     - api_url       → Django 伺服器的 IP/網址（預設 localhost:8000）
     - simulation_mode → 測試時 True，正式部署改 False
     - ldr_calibration → （僅實驗組）填入四顆 LDR 的實際校正係數

5. 手動測試執行：
   cd /home/pi/solar_tracking/實驗組1/
   bash start.sh

6. 設定開機自動啟動（systemd）：
   sudo cp solar_tracking.service /etc/systemd/system/
   sudo systemctl daemon-reload
   sudo systemctl enable solar_tracking
   sudo systemctl start solar_tracking

【查看執行狀態】
   sudo systemctl status solar_tracking
   tail -f /home/pi/solar_tracking/實驗組1/service.log

【停止服務】
   sudo systemctl stop solar_tracking

【注意事項】
   - simulation_mode=False 時感測器斷線會直接報錯，不會靜默繼續
   - 推桿 GPIO 驅動（_drive_ew/_drive_ns）尚有 TODO 待填入接線資訊
   - 實驗組的霍爾感測器行程-角度對照表需完成後才能閉迴路控制
   - INA3221 功率讀取尚未實作（見 anfis_controller.py TODO）

