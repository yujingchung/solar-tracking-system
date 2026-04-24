# raspberry-pi/src/algorithms/

樹莓派上的**執行期演算法模組**（輕量化、可直接被控制器 import）。與頂層 `algorithms/` 的差別：

| | 頂層 `algorithms/` | 本資料夾 `raspberry-pi/src/algorithms/` |
|---|---|---|
| 目的 | 離線訓練、研究、視覺化 | 實機即時決策 |
| 依賴 | TensorFlow / Keras / matplotlib | 輕量（numpy, json） |
| 執行環境 | 開發機 / GPU 伺服器 | Raspberry Pi |

## 預計內容

- `anfis/` — 載入離線訓練好的 ANFIS 規則庫，推論用的輕量版
- `traditional/` — 傳統光感測器差值追日邏輯，從 `controllers/traditional_controller.py` 抽出

## 現狀

目前演算法邏輯仍寫在 `controllers/anfis_controller.py` 與 `controllers/traditional_controller.py` 內部，尚未抽成獨立模組。
