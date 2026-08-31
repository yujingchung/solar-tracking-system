# 太陽能追日系統 (Solar Tracking System)

基於 ANFIS 演算法的智慧雙軸太陽能追日系統——碩士論文研究專案。
**實驗場域**：先鋒 金土地公廟（25.10°N, 121.43°E）｜ **研究者**：鐘宇靖 ｜ 指導教授：陳玉彬 教授

---

## 專案概述

設計實驗組（ANFIS 智慧追日）與對照組（傳統 LDR 差值追日）的雙組別實驗，比較兩種追日策略的發電效益；另以 24 片固定角度面板（傾角 10°/15°/20°/30° × 方位角 160°/180°/200°，每組合 A/B 兩片）＋ 2 片備用，作為 ANFIS 模型的訓練資料來源與對照基準。

### 四套追日系統（2026-09 現況：全數上線）

| 組別 | 追日方式 | system_id | Pi 主機名 | Tailscale IP | SSH 帳號 | 程式資料夾 | 上傳間隔 |
|------|----------|-----------|-----------|--------------|----------|------------|----------|
| 實驗組 I | ANFIS | 4 | raspberrypi-v4 | 100.79.66.68 | raspberrypi | `anfis_1` | 10 分鐘 |
| 實驗組 II | ANFIS | 2 | raspberrypi-1 | 100.66.182.46 | rte | `anfis_2` | 5 分鐘 |
| 對照組 I | LDR 差值 | 6 | raspberrypi | 100.96.31.110 | raspberrypi | `traditional_1` | 10 分鐘 |
| 對照組 II | LDR 差值 | 7 | raspberrypi-v3 | 100.126.13.120 | raspberrypi | `traditional_2` | 5 分鐘 |

---

## 系統架構

```
┌──────────────────────────────────────────────────────────────┐
│  樹莓派（×4 台，systemd 服務 solar_tracking.service）        │
│  ├─ MCP3008 SPI：4 方位光敏電阻（東/西/南/北，ADC 0-1023）  │
│  ├─ INA3221 I2C（0x40）：推桿電力＋Pi 電力（通道對應見下）  │
│  ├─ LX08A USB-RS232：MW PV-ML24-40 MPPT（9600 bps, fc03）  │
│  ├─ H 橋繼電器 ×8（GPIO 驅動 24V 雙軸推桿）                │
│  └─ 霍爾位置回授（54.19 pulse/mm；homing 歸零＋EMI gating）│
└────────────────┬─────────────────────────────────────────────┘
                 │ REST（Tailscale VPN）
┌────────────────▼─────────────────────────────────────────────┐
│  Django 後端（Docker：solar_db / solar_backend / tailscale） │
│  ├─ REST API：/api/power-records/ 等                        │
│  ├─ 固定面板 CSV API（49 MB pandas 記憶體載入＋mtime 快取） │
│  └─ Z3A IoT 雲端 API 代理（token 機制見 Z3A_TOKEN_SOP.md）  │
└────────────────┬─────────────────────────────────────────────┘
                 │ Tailscale Funnel HTTPS
┌────────────────▼─────────────────────────────────────────────┐
│  儀表板（backend/static/dashboard.html，單一檔案，7 頁籤）   │
│  總覽｜固定面板研究｜CSV 進階分析｜即時監控｜發電比較｜      │
│  Z3A 採集｜下載中心                                          │
└──────────────────────────────────────────────────────────────┘
```

### 硬體重點（2026-08/09 更新）

- **MPPT**：2026-08-21 全數由 EPEVER Tracer-AN（20 A，RS485/115200/fc04）換裝為**明緯 PV-ML24-40**（40 A，RS232 RJ12/9600/fc03，SRNE ML2440 貼牌），解除晴天正午 ≈296 W 削頂。RJ12 ⑤⑥ 為電源腳**絕不可接**（會與 Pi USB 5V 倒灌造成掉電）。
- **霍爾回授**：全系統具 homing 歸零（開機首次移動前＋每晚回歸前全收歸零）與 EMI gating（僅計數當前驅動軸），行程-角度換算依論文表 4.1 三點分段線性。
- **INA3221 通道對應（各台不同，維修必讀）**：

| 系統 | I2C bus | 推桿 | 樹莓派 | 備註 |
|------|---------|------|--------|------|
| 實驗組 I | 1（硬體） | CH3 | CH2 | CH1 通道燒毀停用 |
| 實驗組 II | 3（軟體 I2C，GPIO20/21） | CH1 | CH3 | GPIO2/3 損壞，dtoverlay i2c-gpio |
| 對照組 I | 1（硬體） | CH1 | CH2 | 標準接法 |
| 對照組 II | 1（硬體） | CH1 | CH2 | 標準接法 |

---

## 目錄結構

```
solar-tracking-dashboard/
├── backend/                      # Django 後端（Docker）
│   ├── dashboard/                # models / views / fixed_panel_api / z3a_api
│   └── static/dashboard.html     # 儀表板前端（單一檔案）＋ theme.css
├── data/                         # 主資料集 CSV（49 MB）
├── algorithms/                   # ANFIS 訓練管線
│   ├── solar_anfis_model_v2.py   # 模型主程式
│   ├── train_pipeline.py         # 一鍵訓練（datasets/ 與 runs/ 管理）
│   ├── datapreprocessor/         # SimpleSolarPreprocessor
│   ├── coordinate_conversion/    # (β,φ) ⇄ (γ,ζ) 轉換
│   └── flowcharts/               # 控制流程圖 PDF
├── fixed_data_process_visualization/  # 固定面板五步前處理管線（Tkinter GUI）
├── raspberry-pi/
│   ├── config/                   # 各系統 config
│   ├── src/controllers/          # anfis_controller / traditional_controller
│   └── deploy/                   # 各現場機台程式快照
├── docs/                         # 設計知識庫、手冊
├── z3a_collect.py                # Z3A 雲端抓取＋CSV 合併
├── solar_weekly_run.ps1          # 週運維（Task Scheduler 每週一 02:00）
└── docker-compose-dev.yml
```

---

## 快速開始

```bash
# 於專案根目錄（Windows 主機）
docker-compose -f docker-compose-dev.yml up -d
# 儀表板：http://localhost:8000/dashboard/
# 公網：https://solar-dashboard.tail7c1eb9.ts.net/dashboard/
```

注意：開啟 Fiddler 的 HTTPS 解密會破壞 Tailscale 容器 TLS，啟動前請先關閉；改動 `.env.dev` 後需 `up -d --force-recreate backend` 才會重讀。

---

## 樹莓派部署

```bash
# 1. 複製對應資料夾到 Pi（見上方四系統表）
# 2. 建立 venv 並安裝套件（實驗組需 TensorFlow/sklearn）
# 3.（僅實驗組）放入模型檔：anfis_with_illumination.keras、scaler、config
# 4. 確認 CONFIG：system_id、MPPT baud=9600、INA 通道對應（見上表）
# 5. 手動測試：python3 <controller>.py
# 6. systemd 自啟：sudo systemctl enable --now solar_tracking.service
```

任何手動測試腳本要操作 GPIO 或 /dev/ttyUSB0 前，先 `sudo systemctl stop solar_tracking.service`，測完再 start。

---

## ANFIS 訓練管線

```bash
cd algorithms/
python train_pipeline.py                              # 完整（前處理＋訓練）
python train_pipeline.py --skip-preprocess --dataset ds02_20260506_含照度
```

模型：Gaussian MF（7 MFs/輸入，9 維特徵：時間/日期/角度 sin-cos ＋照度）→ Dense 128→64→32→16→1。儲存採 `.keras`（h5py 對中文路徑不相容）。評估含排名導向指標（Top-1 選擇率、次佳落差）。

---

## API 端點（節錄）

| Endpoint | 用途 |
|----------|------|
| `GET/POST /api/power-records/` | 追日系統即時紀錄 |
| `GET /api/fixed-panels/kpi-summary/` | 固定面板研究 KPI（支援季節參數） |
| `POST /api/fixed-panels/reload/` | 清快取重讀 CSV |
| `GET /api/z3a/history/` | Z3A 雲端歷史查詢 |

---

## 例行維運

- **每週一 02:00**：Windows Task Scheduler 跑 `solar_weekly_run.ps1`（健檢→token→抓取→reload），log 於 `logs/`。
- **Z3A token**：約 78 天以 Fiddler 手動更新一次，SOP 見 `Z3A_TOKEN_SOP.md`。
- **照度資料**：MongoDB Atlas 匯出後以 `merge_illumination_csv.py` 合併（處理假 UTC 時區）。
- 完整硬體說明見《太陽能案場硬體系統架構手冊》；軟體操作見《使用手冊 v2.4》。

---

## 版本紀錄

| 日期 | 內容 |
|------|------|
| 2026-09-06 | 40A MPPT（ML2440/RS232/9600）全面換裝與程式支援；霍爾 homing＋EMI gating；實II 軟體 I2C bus3；各台 INA 通道重對應；儀表板發電比較新增 β/φ 欄；backend 電池/SOC 欄位；四系統全數上線 |
| 2026-06-26 | Z3A token 機制簡化（token2 直用，~78 天一次） |
| 2026-05-15 | 儀表板 7 頁籤重寫；KPI API；週運維自動化 |
| 2026-03 | 初版：雙組別追日＋固定面板資料管線 |

---

## 授權

學術研究用途。
