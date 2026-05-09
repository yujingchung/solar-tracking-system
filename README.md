# 太陽能追日系統 (Solar Tracking System)

基於 ANFIS 演算法的智慧雙軸太陽能追日系統——碩士論文研究專案。
**實驗場域**：新北市 ｜ **研究者**：鐘宇靖

---

## 專案概述

設計實驗組（ANFIS 智慧追日）與對照組（傳統 LDR 差值追日）的雙組別實驗，比較兩種追日策略的發電效益。

| 組別 | 追日方式 | System ID | 控制程式 |
|------|----------|-----------|----------|
| 實驗組 I & II | ANFIS 智慧追日 | 1, 2 | `anfis_controller.py` |
| 對照組 I & II | 傳統 LDR 差值追日 | 3, 4 | `traditional_controller.py` |

另有 28 片固定角度參考面板（傾角 10°/15°/20°/30° × 方位角 160°/180°/200°）作為對照基準。

---

## 系統架構

```
┌─────────────────────────────────────────────────────────┐
│  樹莓派（×4 台）                                         │
│  ├─ MCP3008 SPI：4 方向光敏電阻（東/西/南/北）          │
│  ├─ INA3221 I2C（0x40）：推桿電力(CH1)＋Pi電力(CH2)   │
│  ├─ RS485→USB：MPPT 控制器（太陽能板 V/I）             │
│  └─ 雙軸線性推桿（霍爾感測器閉迴路回授）               │
└────────────────┬────────────────────────────────────────┘
                 │ HTTPS（Tailscale Funnel）
┌────────────────▼────────────────────────────────────────┐
│  Django 後端（Docker）                                   │
│  ├─ REST API：/api/power-records/                       │
│  ├─ 固定面板 CSV API（49 MB，pandas 記憶體載入）        │
│  └─ Z3A IoT 雲端 API 代理                              │
└────────────────┬────────────────────────────────────────┘
                 │
┌────────────────▼────────────────────────────────────────┐
│  儀表板前端（dashboard.html，單一檔案）                  │
│  ├─ 系統總覽：各組即時功率                              │
│  ├─ 功率曲線：各系統時序圖表                           │
│  ├─ 固定式面板發電分析：CSV 查詢 ＋ 照度疊加圖        │
│  └─ Z3A 採集：IoT 雲端即時 V/I/P                      │
└─────────────────────────────────────────────────────────┘
```

---

## 目錄結構

```
solar-tracking-dashboard/
├── backend/
│   ├── dashboard/
│   │   ├── models.py             # SystemGroup, PowerRecord
│   │   ├── views.py              # REST API viewsets
│   │   ├── serializers.py        # RealTimeDataSerializer
│   │   ├── fixed_panel_api.py    # 固定面板 CSV 查詢 API
│   │   └── z3a_api.py            # Z3A IoT 雲端 API 代理
│   ├── static/dashboard.html     # 單一檔案前端（~1500 行）
│   └── requirements.txt
├── data/
│   └── combined_solar_data_20250301_20260406_processed.csv  # 49 MB 主資料集
├── algorithms/
│   ├── solar_anfis_model_v2.py   # ANFIS 模型（存 .keras 格式）
│   ├── train_pipeline.py         # 一鍵訓練啟動器
│   ├── datasets/                 # 預處理資料集（dsXX_YYYYMMDD_desc/）
│   ├── runs/                     # 訓練輸出（runXX_dsXX_desc/）
│   ├── datapreprocessor/
│   │   └── data preprocessor.py # SimpleSolarPreprocessor
│   └── coordinate_conversion/   # (β,φ) ⇄ (γ,ζ) 座標轉換工具
├── fixed_data_process_visualization/  # 固定面板資料六步驟處理管線
│   ├── solar_data_pipeline.py    # Tkinter GUI 入口
│   └── 使用手冊.md
├── raspberry-pi/
│   ├── src/controllers/
│   │   ├── anfis_controller.py        # 實驗組控制器
│   │   └── traditional_controller.py  # 對照組控制器
│   └── deploy/solar_tracking/         # 可直接部署的四個資料夾
│       ├── 實驗組1/   (system_id=1)
│       ├── 實驗組2/   (system_id=2)
│       ├── 對照組1/   (system_id=3)
│       └── 對照組2/   (system_id=4)
├── algorithms/flowcharts/        # 實驗/對照組流程圖 PDF
├── z3a_collect.py                # Z3A 歷史資料抓取 ＋ CSV 合併
├── docker-compose-dev.yml
└── .env.dev                      # 金鑰/Token — 不進版控
```

---

## 快速開始

### Docker（從專案根目錄執行）

```bash
docker-compose -f docker-compose-dev.yml up -d        # 啟動
docker-compose -f docker-compose-dev.yml down          # 停止
docker-compose -f docker-compose-dev.yml up -d --build # 重新建構
```

| 網址 | 說明 |
|------|------|
| `http://localhost:8000/dashboard/` | 本機儀表板 |
| `https://solar-dashboard.tail7c1eb9.ts.net/dashboard/` | 公開網址（Tailscale） |

> ⚠️ 啟動 Docker 前請關閉 **Fiddler**——其 HTTPS 解密會導致 Tailscale 容器 TLS 驗證失敗。

### 除錯指令

```bash
docker logs solar_backend --tail 50
docker exec -it solar_backend bash
```

---

## 樹莓派部署

四台 Pi 各自運行一個控制器，程式位於 `raspberry-pi/deploy/solar_tracking/`。

### 每台 Pi 硬體配置

| 硬體 | 功能 |
|------|------|
| MCP3008（SPI） | 四方向光敏電阻：CH0=東, CH1=西, CH2=南, CH3=北 |
| INA3221（I2C 0x40） | CH1=推桿電力（雙軸合計）, CH2=Pi 本身電力 |
| RS485→USB | MPPT 控制器：太陽能板電壓/電流 |
| 雙軸線性推桿 | 霍爾感測器回授，閉迴路定位 |

### 部署步驟

```bash
# 1. 複製資料夾到 Pi
scp -r 實驗組1/ pi@<PI_IP>:/home/pi/solar_tracking/

# 2. 安裝套件
pip3 install -r requirements.txt

# 3.（僅實驗組）將模型檔案放入 models/ 資料夾
#    anfis_with_illumination.keras
#    scaler_X_with_illumination.save
#    model_config_with_illumination.json

# 4. 硬體就緒後將 CONFIG 中 simulation_mode 改為 False

# 5. 手動測試
bash start.sh

# 6. 設定開機自動啟動
sudo cp solar_tracking.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable solar_tracking
sudo systemctl start solar_tracking
```

### 座標系統

- **Tip-tilt**：γ 南北（±30°，+北/−南），ζ 東西（±30°，+東/−西）
- **傾角方位角**：β（傾角 0–41.4°），φ（方位角 0–360°）
- 轉換函式：`tiptilt_to_azalt(γ, ζ) → (β, φ)`，定義於 `anfis_controller.py`

---

## ANFIS 訓練管線

```bash
cd algorithms/
python train_pipeline.py                                   # 完整管線
python train_pipeline.py --skip-preprocess                 # 僅訓練（使用最新資料集）
python train_pipeline.py --skip-preprocess --dataset ds02_20260506_含照度
```

### 模型規格

- **輸入特徵（9 維）**：`hour_sin/cos`、`day_sin/cos`、`tilt_sin/cos`、`azimuth_sin/cos`、`illumination`
- **網路架構**：高斯隸屬函數層（7 MF/輸入）→ Dense(128→64→32→16→1) ＋ BatchNorm ＋ Dropout
- **儲存格式**：`.keras`（h5py 在含中文字元的 Windows 路徑下會崩潰，不用 `.h5`）
- **輸出目錄**：`algorithms/runs/runXX_dsXX_desc/`

### 目前訓練結果（run04，ds02，含照度）

| 指標 | 數值 |
|------|------|
| R²（整體） | 0.844 |
| RMSE | 32.43 W |
| MAE | 20.98 W |

各角度區間 R² 均為負值 → 模型學到時間→功率的映射，尚未學會角度差異。
**下一步**：加入 `theoretical_poa`、`solar_elevation` 特徵改善角度鑑別能力。

---

## API 端點

**Base URL**：`/api/`

| 端點 | 方法 | 說明 |
|------|------|------|
| `/api/power-records/` | GET/POST | PowerRecord CRUD — Pi 上傳目標 |
| `/api/realtime-data/` | GET | 各系統最新資料 |
| `/api/systems/` | GET/POST | SystemGroup CRUD |
| `/api/fixed-panels/day-curve/` | GET | 固定面板每分鐘曲線 |
| `/api/fixed-panels/panel-trend/` | GET | 長期面板趨勢 |
| `/api/z3a/history/` | GET | Z3A 裝置歷史資料 |
| `/api/z3a/devices/` | GET | Z3A 裝置清單 |

**POST `/api/power-records/` 必填欄位**：`system_id`、`voltage`、`current`

---

## 主資料集

`data/combined_solar_data_20250301_20260406_processed.csv`（49 MB）
- **時間範圍**：2025-03-01 至 2026-04-06 ｜**間隔**：10 分鐘 ｜**時區**：Asia/Taipei
- **主要欄位**：`timestamp`、`tilt_angle`、`azimuth_angle`、`panel_id`、`voltage_V`、`current_A`、`power_W`、`solar_elevation`、`theoretical_poa`、`ghi`、`illumination`

---

## 待辦事項

| 項目 | 優先度 |
|------|--------|
| 確認 MPPT 通訊協定（Modbus RTU 或自訂）→ 實作 `read_mppt_power()` | 高 |
| 確認 GPIO 接線 → 實作 `_drive_ew()` / `_drive_ns()` | 高 |
| 建立霍爾感測器行程-角度對照表 → 實作 `_move_to_tiptilt()` | 高 |
| 四顆 LDR 個別校正係數測量 | 高 |
| 改善 ANFIS 角度鑑別能力（加入 `theoretical_poa` 等特徵） | 中 |
| Z3A Token 於 2026-05-09 到期，需重新登入更新 `.env.dev` | 中 |

---

## 版本紀錄

| 版本 | 日期 | 說明 |
|------|------|------|
| v0.4 | 2026-05 | 重寫 Pi 控制器、建立四組部署資料夾、加入 INA3221/MPPT、修正 API payload、CLAUDE.md 英文化 |
| v0.3 | 2026-05 | ANFIS 訓練管線、照度資料整合、固定面板六步驟處理管線、Z3A 資料收集 |
| v0.2 | 2025-09 | 主控制器架構、統一設定系統 |
| v0.1 | 2025-03 | Django 後端初版、基本儀表板 |

---

## 授權

MIT License
