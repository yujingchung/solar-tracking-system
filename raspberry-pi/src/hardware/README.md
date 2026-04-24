# hardware/

預計放置與硬體直接互動的底層驅動模組，從 `controllers/` 抽出可重用的部分。

## 預計內容

- `actuator_driver.py` — 雙軸推桿（方位角推桿 206mm、傾角推桿 406mm）GPIO 控制，從 `test_actuator.py` 重構出來
- `ina3221_monitor.py` — INA3221 雙通道電源監控（CH1 推桿、CH2 樹莓派供電）
- `hall_sensor.py` — 霍爾感測器（用於推桿位置回授）

## 現狀

尚未建立，`controllers/anfis_controller.py` 與 `controllers/traditional_controller.py` 目前直接使用 `RPi.GPIO`，待抽出。
