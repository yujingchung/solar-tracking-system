# algorithms/ — 演算法研究與訓練

本資料夾集中存放 ANFIS 研究相關的所有離線訓練程式、座標轉換工具與演算法流程圖。
部署到樹莓派的「執行期控制器」位於 `raspberry-pi/src/controllers/`，會載入本資料夾訓練出的模型。

## 結構

```
algorithms/
├── solar_anfis_model_v2.py       # ANFIS 模型訓練主程式（TF/GPU，756 行）
├── coordinate_conversion/        # 座標系轉換工具（β,φ ⇄ γ,ζ）
│   ├── tiptilt_to_azalt.py
│   ├── visualization.py
│   └── README.md
└── flowcharts/                   # 演算法流程圖
    ├── 實驗組流程圖.pdf
    └── 對照組流程圖.pdf
```

## 資料流

```
data/combined_solar_data_*.csv          (12 組固定面板實測資料)
           │ (β, φ, power, illum, solar_zenith, solar_azimuth)
           ▼
   coordinate_conversion/tiptilt_to_azalt.py
           │ 把 (β, φ) 轉成 (γ, ζ)
           ▼
   solar_anfis_model_v2.py                (訓練 ANFIS)
           │
           ▼
   訓練好的模型 / 規則庫
           │
           ▼
   raspberry-pi/src/controllers/anfis_controller.py
           (實機部署、比較實驗)
```

## 檔案說明

### `solar_anfis_model_v2.py`
最新版 ANFIS 訓練腳本。包含：
- GPU / TensorFlow 動態記憶體配置與混合精度選項
- 從處理後 CSV 讀取訓練資料
- 模糊化、規則庫建構、模型訓練、評估

**對應的輸入資料**：`data/combined_solar_data_20250301_20260406_processed.csv`
**對應的 SQLite**：`solar_angle_data.db`（由 `fixed_data_process_visualization/data preprocessing4.py` 產生）

### `coordinate_conversion/`
見該資料夾內的 README。把固定式面板 (β 傾角, φ 方位角) 與追日系統 (γ 南北向傾角, ζ 東西向傾角) 兩個座標系統透過法向量串聯旋轉公式對應起來。

### `flowcharts/`
- `實驗組流程圖.pdf`：ANFIS 版追日控制邏輯流程
- `對照組流程圖.pdf`：傳統光感測器追日邏輯流程
