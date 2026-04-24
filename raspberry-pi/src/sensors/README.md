# sensors/

預計放置感測器讀取模組。

## 預計內容

- `light_sensor.py` — 四方位光感測器（東/西/南/北 光照強度）讀取，對應 GPIO 2/3/4/17
- `environmental.py` — 溫度、濕度感測
- `power_meter.py` — 太陽能板輸出電壓、電流讀取

## 現狀

感測器邏輯目前分散在 `controllers/traditional_controller.py` 中的 `_read_light_sensors()` 等方法，待抽出為獨立模組。
