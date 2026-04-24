# 系統架構說明 (ARCHITECTURE)

> 本文件說明 solar-tracking-dashboard 整個系統的資料流、各模組的職責、以及「固定角度案場資料 → ANFIS 訓練 → 實機部署」的完整路徑。論文與口試呈現可以此為藍圖。

---

## 1. 系統定位

**研究題目**：太陽能追日系統演算法優化（以 ANFIS 為核心）

**實驗設計**：
- **對照組（Control）**：傳統光感測器差值追日（`controllers/traditional_controller.py`）
- **實驗組（Experiment）**：ANFIS 智慧追日（`controllers/anfis_controller.py`）
- **額外資料源**：12 組固定角度太陽能板（方位角 160°/180°/200° × 傾角 10°/15°/20°/30°），作為 ANFIS 訓練樣本與 benchmark

**量測指標**：發電量、推桿耗能、追日誤差、轉動次數。

---

## 2. 整體資料流

```
                         ┌──────────────────────────┐
                         │ 12 組固定角度面板          │
                         │ (β, φ) × 24 片板子         │
                         │ 採集：V, I, 每分鐘         │
                         └────────────┬─────────────┘
                                      │ 原始 CSV
                                      ▼
      ╔═══════════════════════════════════════════════════╗
      ║  fixed_data_process_visualization/ (6 步管線)     ║
      ║  ─────────────────────────────────────────────    ║
      ║  ① convert name1.py        重命名 → (β, φ).csv   ║
      ║  ② power calculation2.py   P = V × I              ║
      ║  ③ power summary3.py       日發電量匯總            ║
      ║  ④ data preprocessing4.py  加太陽角度 (pvlib)     ║
      ║  ⑤ combine data 5.py       多時段合併              ║
      ║  ⑥ fixed_panel_data_visualization.py  互動式圖表  ║
      ╚═══════════════════╤═══════════════════════════════╝
                          │
                          ▼
              ┌───────────────────────────┐
              │ data/combined_..._.csv    │  (49 MB, 2025-03 ~ 2026-04)
              │ solar_angle_data.db       │  (SQLite 12 MB)
              │                           │
              │ 欄位: timestamp, tilt,    │
              │ azimuth, power_W,         │
              │ solar_zenith/azimuth,     │
              │ theoretical_poa, V, I     │
              └────────────┬──────────────┘
                           │
                           ▼
      ╔════════════════════════════════════════════╗
      ║ algorithms/coordinate_conversion/          ║
      ║ tiptilt_to_azalt.py                        ║
      ║  (β, φ) ⇄ (γ, ζ) 法向量轉換                ║
      ║   x = sin(ζ)                               ║
      ║   y = sin(γ)·cos(ζ)                        ║
      ║   z = cos(γ)·cos(ζ)                        ║
      ║   β = arccos(z),  φ = atan2(x, y)          ║
      ╚═══════════════════╤════════════════════════╝
                          │ 以追日系統語言 (γ, ζ) 表達的資料
                          ▼
      ╔════════════════════════════════════════════╗
      ║ algorithms/solar_anfis_model_v2.py         ║
      ║  (TensorFlow / GPU / FP16 option)          ║
      ║  ─────────────────────────────────────     ║
      ║  輸入：太陽位置、光照、γ、ζ                 ║
      ║  輸出：預測發電量 / 最佳角度決策            ║
      ╚═══════════════════╤════════════════════════╝
                          │ 訓練好的規則庫 / 權重
                          ▼
      ╔════════════════════════════════════════════╗
      ║ raspberry-pi/src/controllers/              ║
      ║  ├── anfis_controller.py                   ║
      ║  │   (實驗組：載入模型並做即時決策)        ║
      ║  └── traditional_controller.py             ║
      ║      (對照組：光感測器差值法)              ║
      ╚═══════════════════╤════════════════════════╝
                          │ HTTP POST
                          ▼
      ╔════════════════════════════════════════════╗
      ║ backend/ (Django + DRF + MySQL)            ║
      ║  API: /api/realtime-data/                  ║
      ║  Model: SystemGroup, PowerRecord           ║
      ║  Dashboard: /dashboard/ (登入後)           ║
      ╚════════════════════════════════════════════╝
```

---

## 3. 模組職責

### 3.1 資料層

| 資料夾 / 檔案 | 角色 |
|--------------|------|
| `data/combined_solar_data_20250301_20260406_processed.csv` | 已處理完畢的 12 組固定面板資料總合（49MB） |
| `solar_angle_data.db` | SQLite 資料庫，由 `data preprocessing4.py` 產生，含太陽角度欄位 |
| `mysql/` | Docker MySQL 持久化目錄，儲存實機運行的 PowerRecord |

### 3.2 資料處理管線（離線）

`fixed_data_process_visualization/`：專門處理固定角度面板的 6 步管線。獨立、可單獨執行，透過 `solar_data_pipeline.py` 提供 Tkinter GUI。

### 3.3 演算法層（離線研究）

`algorithms/`：
- `solar_anfis_model_v2.py` — 最新 ANFIS 訓練程式（原 `solar_anfis_model(new).py`）
- `coordinate_conversion/` — (β, φ) ⇄ (γ, ζ) 座標轉換工具 + 視覺化
- `flowcharts/` — 實驗組、對照組流程圖 PDF

### 3.4 控制層（線上、樹莓派）

`raspberry-pi/src/`：
- `main_controller.py` — 命令列進入點（`--mode both/anfis/traditional`）
- `controllers/` — 兩組控制邏輯實作
- `utils/config_manager.py` — 讀取 `raspberry-pi/config/system_config.json`
- `raspberry_pi_data_collector.py` — 上傳資料到 Django API
- 其他空目錄（`hardware/`, `sensors/`, `simulation/`, `algorithms/`）是為日後重構預留的骨架，內含 README 說明預期用途

### 3.5 網站層

`backend/`（Django 5.0 + DRF）：
- `dashboard/models.py` — `SystemGroup`（對照組 / 實驗組）、`PowerRecord`（發電、推桿、樹莓派電源）
- `dashboard/views.py` — REST API viewsets
- `static/dashboard.html` — 單頁前端儀表板，含 CSV 匯出、日期過濾、分頁
- 部署：`docker-compose-dev.yml` 拉起 `solar_db`（MySQL）+ `solar_backend`

### 3.6 測試與啟動

| 檔案 | 角色 |
|------|------|
| `test_actuator.py` | 雙軸推桿手動操作測試（含 INA3221 雙通道功率監控） |
| `test_uploader.py` | 推桿操作 + Django API 上傳整合測試 |
| `scripts/test_api.py` / `test_system_5.py` | Django API 端點測試 |
| `scripts/start_solar_tracking.bat` | Windows 選單式啟動器 |

---

## 4. 設定檔

統一存放在 `raspberry-pi/config/`：

| 檔案 | 用途 | 格式 | 讀取者 |
|------|------|------|--------|
| `system_config.json` | 控制器完整配置（硬體、系統、演算法、位置） | 巢狀 | `utils/config_manager.py` |
| `config.json` | 資料採集器用（預設） | 扁平 | `raspberry_pi_data_collector.py` |
| `config_mountain_control.json` | 山上對照組 (system_id=6) | 扁平 | 同上 |
| `config_mountain_experiment.json` | 山上實驗組 (system_id=7) | 扁平 | 同上 |
| `config_simulation.json` | 模擬測試 (system_id=5) | 扁平 | 同上 |

## 5. 常用開發命令

```bash
# 啟動後端 (MySQL + Django)
docker-compose -f docker-compose-dev.yml up -d

# 訪問儀表板
# → http://192.168.0.100:8000/dashboard/

# 樹莓派上啟動控制器
python raspberry-pi/src/main_controller.py --mode both       # 對比模式
python raspberry-pi/src/main_controller.py --mode anfis      # 實驗組
python raspberry-pi/src/main_controller.py --mode traditional # 對照組

# 固定面板資料處理（Tkinter GUI）
python fixed_data_process_visualization/solar_data_pipeline.py

# 產生座標對照表
python algorithms/coordinate_conversion/tiptilt_to_azalt.py

# 可視化座標對應
python algorithms/coordinate_conversion/visualization.py tiptilt_conversion_step1.csv

# 訓練 ANFIS
python algorithms/solar_anfis_model_v2.py
```

---

## 6. 命名與座標系約定

| 符號 | 系統 | 範圍 | 物理意義 |
|------|------|------|---------|
| β | 固定式 | 0 ~ 45° | 面板與水平面夾角（傾角） |
| φ | 固定式 | 0 ~ 360° | 方位角（以正北為 0°，順時針） |
| γ | 追日式 | -30 ~ +30° | 南北向傾角（+北傾、-南傾） |
| ζ | 追日式 | -35 ~ +35° | 東西向傾角（+東傾、-西傾） |

轉換關係：見 `algorithms/coordinate_conversion/README.md`。

實驗常用配置：
- A: β=10°, φ=160°（東南傾）
- B: β=10°, φ=180°（正南傾）
- C: β=20°, φ=180°（正南傾，較陡）
- D: β=30°, φ=200°（西南傾）

---

## 7. 本次整理紀錄（2026-04-21）

| 動作 | 說明 |
|------|------|
| 移動 | `Tiptilt to azalt.py`、`visualization.py` → `algorithms/coordinate_conversion/` |
| 刪除 | 根目錄 `實驗組程式.py`、`對照組程式.py`（與 `src/controllers/` 內容完全一致） |
| 合併 | `raspberry-pi/src/config/` 併入 `raspberry-pi/config/`，更新 `config_manager.py` 路徑 |
| 搬移 | `solar_anfis_model(new).py` → `algorithms/solar_anfis_model_v2.py`（去除括號） |
| 搬移 | 實驗組/對照組流程圖 PDF → `algorithms/flowcharts/` |
| 刪除 | `backend/dashboard/models_backup.py`（git history 保留） |
| 補 README | `raspberry-pi/src/{hardware,sensors,simulation,algorithms}` 空資料夾 |
| 新增 | 本文件 `ARCHITECTURE.md` |

---

## 8. 下一步建議

1. **把 `tiptilt_to_azalt.py` 嵌入資料預處理管線** — 在 `data preprocessing4.py` 產出 CSV 時順便加上 `gamma_equiv` / `zeta_equiv` 欄位，讓 ANFIS 訓練能直接使用追日系統語言。
2. **為 ANFIS 訓練寫獨立的 training script** — 從 `solar_anfis_model_v2.py` 抽出一支 `train.py`，把資料載入、特徵工程、模型存檔分離，方便比較不同超參數。
3. **把 `fixed_data_process_visualization/` 檔名正規化** — 目前檔名有空格與 `1/2/3/4/5` 尾數，如改為 `01_convert_name.py`、`02_power_calc.py` 會比較好 import。（尚未做，避免影響 `solar_data_pipeline.py` 的既有 subprocess 呼叫）
4. **寫一份訓練/部署 SOP 放在 `docs/`** — 從採集資料到部署 ANFIS 上線的完整手冊。
