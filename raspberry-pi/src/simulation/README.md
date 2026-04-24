# simulation/

模擬模式（`simulation_mode: true`）下的虛擬硬體與環境模型，用於在沒有實際推桿、感測器時仍能測試控制邏輯。

## 預計內容

- `virtual_actuator.py` — 虛擬推桿回應（模擬霍爾脈衝、到位時間）
- `virtual_sensors.py` — 用 pvlib 計算理論光照並加上雜訊
- `weather_scenarios.py` — 預設天候情境（晴/陰/多雲轉晴等）

## 現狀

目前 `controllers/` 內的對照組/實驗組程式各自內嵌了簡單的模擬邏輯（`HARDWARE_AVAILABLE = False` 時走模擬路徑），未來可抽到這裡統一管理。
