# CLAUDE.md — 太陽能追日系統專案說明

> 給 AI 助理（Claude）的專案導覽。每次開新對話前請先讀這份文件。

---

## 1. 專案定位

**研究題目**：基於 ANFIS 演算法的智慧太陽能追日系統  
**場域**：先鋒（金土地公廟）太陽能實驗場  
**研究者**：鐘宇靖  
**論文**：`碩士論文計劃書_鐘宇靖_final.docx`

實驗設計：
- **對照組**：傳統光感測器差值追日（`raspberry-pi/src/controllers/traditional_controller.py`）
- **實驗組**：ANFIS 智慧追日（`raspberry-pi/src/controllers/anfis_controller.py`）
- **資料源**：28 片固定角度面板（傾角 10°/15°/20°/30° × 方位角 160°/180°/200°）＋ 4 片追日面板

---

## 2. 資料夾結構

```
solar-tracking-dashboard/
├── backend/                        # Django 後端（Docker 容器內）
│   ├── dashboard/
│   │   ├── models.py               # SystemGroup, PowerRecord
│   │   ├── views.py                # REST API viewsets
│   │   ├── fixed_panel_api.py      # 固定面板歷史 CSV 查詢 API
│   │   ├── z3a_api.py              # Z3A IoT 雲端 API 代理
│   │   └── urls.py                 # 所有路由
│   ├── static/dashboard.html       # 單頁前端儀表板（全部邏輯在這一個檔案）
│   ├── pmp_solar_dashboard/
│   │   └── settings.py             # Django 設定（含 Z3A 環境變數）
│   ├── requirements.txt
│   └── Dockerfile
├── data/
│   └── combined_solar_data_20250301_20260406_processed.csv  # 主要資料檔（49 MB）
├── algorithms/
│   ├── solar_anfis_model_v2.py     # ANFIS 訓練主程式
│   ├── coordinate_conversion/      # (β,φ) ⇄ (γ,ζ) 座標轉換工具
│   │   ├── tiptilt_to_azalt.py     # (γ,ζ) → (β,φ) 轉換 + 生成對照表
│   │   ├── azalt_to_tiptilt.py     # (β,φ) → (γ,ζ) 反向轉換
│   │   └── visualization.py        # 雙座標系對照圖（需先產生 CSV）
│   └── flowcharts/                 # 實驗組/對照組流程圖 PDF
├── fixed_data_process_visualization/  # 固定面板資料處理六步管線
│   ├── solar_data_pipeline.py      # Tkinter GUI 入口
│   ├── convert name1.py            # ① 重命名
│   ├── power calculation2.py       # ② 計算 P=V×I
│   ├── power summary3.py           # ③ 日發電量匯總
│   ├── data preprocessing4.py      # ④ 加太陽角度（pvlib）
│   ├── combine data 5.py           # ⑤ 多時段合併
│   ├── fixed_panel_data_visualization.py  # ⑥ 互動式圖表
│   └── 使用手冊.md
├── raspberry-pi/
│   ├── config/                     # 樹莓派設定檔
│   │   ├── system_config.json      # 控制器完整配置（硬體、演算法、位置）
│   │   ├── config.json             # 資料採集器預設設定
│   │   ├── config_mountain_control.json    # 山上對照組（system_id=6）
│   │   ├── config_mountain_experiment.json # 山上實驗組（system_id=7）
│   │   └── config_simulation.json          # 模擬測試（system_id=5）
│   └── src/
│       ├── main_controller.py      # 控制器進入點（--mode both/anfis/traditional）
│       ├── controllers/            # ANFIS / 傳統兩組控制邏輯
│       ├── raspberry_pi_data_collector.py  # 上傳資料到 Django API
│       ├── test_actuator.py        # 雙軸推桿手動控制測試（需 GPIO + INA3221）
│       └── test_uploader.py        # 推桿控制 + API 上傳整合測試
├── tailscale-config/
│   └── serve.json                  # Tailscale Funnel 設定（443 → backend:8000）
├── scripts/
│   ├── test_api.py                 # Django REST API 端點測試（localhost:8000）
│   └── start_solar_tracking.bat    # Windows 選單式啟動器
├── z3a_collect.py                  # Z3A 歷史資料抓取＋合併 CSV 腳本（獨立執行）
├── check_z3a.py                    # Z3A API 除錯腳本（測試所有裝置）
├── solar_angle_data.db             # SQLite，由 data preprocessing4.py 產生
├── docker-compose-dev.yml          # Docker 服務定義
├── .env.dev                        # 環境變數（含密碼/Token，不進 git）
├── README.md
├── ARCHITECTURE.md                 # 詳細架構說明（含資料流圖）
└── 碩士論文計劃書_鐘宇靖_final.docx
```

---

## 3. Docker 服務

**啟動指令**（必須在專案根目錄執行，且 compose 檔案名稱不是預設值）：
```bash
cd D:\宇靖\solar-tracking-dashboard
docker-compose -f docker-compose-dev.yml up -d
docker-compose -f docker-compose-dev.yml down
docker-compose -f docker-compose-dev.yml build   # 重建 backend image
```

**三個容器**：

| 容器 | Image | 說明 |
|------|-------|------|
| `solar_db` | mysql:8.0 | MySQL 資料庫，資料存在 `./mysql/` |
| `solar_backend` | 自建（`./backend/Dockerfile`） | Django 5.0，port 8000 |
| `solar_tailscale` | tailscale/tailscale:latest | Funnel 隧道，公開 HTTPS |

**存取方式**：
- 本機：`http://localhost:8000/dashboard/`
- 外網：`https://solar-dashboard.tail7c1eb9.ts.net/dashboard/`

### Dockerfile 重要事項
pip install 全部需要加 `--trusted-host` 參數，否則在有 SSL 攔截的環境下會失敗：
```dockerfile
RUN pip install -r requirements.txt --no-cache-dir \
    --trusted-host pypi.org \
    --trusted-host pypi.python.org \
    --trusted-host files.pythonhosted.org
```

### Tailscale 注意事項
Tailscale 容器若需要重新連線（docker-compose down 後再 up），必須確認本機沒有 **Fiddler** 在執行。Fiddler 的 HTTPS Decrypt 功能會攔截容器的 TLS 連線，導致容器無法連到 `controlplane.tailscale.com`，錯誤訊息為 `x509: certificate signed by unknown authority (CN=DO_NOT_TRUST_FiddlerRoot)`。

---

## 4. 儀表板頁面（dashboard.html）

位置：`backend/static/dashboard.html`（單一大檔案，約 1500 行）

**頁籤結構**：
1. **系統總覽** — 對照組/實驗組即時功率、發電量
2. **功率曲線** — 各系統時間序列圖
3. **固定面板** — 歷史 CSV 資料查詢，依傾角/方位角篩選
4. **Z3A 採集** — 從 Z3A 雲端 API 即時查詢各面板電壓/電流/功率（★ 新增）

---

## 5. 後端 API 端點

Base URL：`/api/`

### 固定面板 API（讀取 CSV 檔案）
| 端點 | 說明 |
|------|------|
| `GET /api/fixed-panels/status/` | CSV 載入狀態與欄位清單 |
| `GET /api/fixed-panels/summary/` | 所有面板總發電量摘要 |
| `GET /api/fixed-panels/power-curve/` | 單日功率曲線（需 `?date=YYYY-MM-DD`） |
| `GET /api/fixed-panels/monthly/` | 月發電量 |
| `GET /api/fixed-panels/daily/` | 日發電量 |
| `GET /api/fixed-panels/panel-list/` | 所有面板 ID 清單 |
| `GET /api/fixed-panels/day-curve/` | 逐分鐘曲線 |
| `GET /api/fixed-panels/panel-trend/` | 面板長期趨勢 |
| `GET /api/fixed-panels/raw-csv/` | 匯出原始 CSV |

### Z3A IoT API（代理至七雲物聯雲端）
| 端點 | 說明 |
|------|------|
| `GET /api/z3a/devices/` | 列出所有綁定裝置 |
| `GET /api/z3a/history/` | 取得單一裝置歷史數據（需 `?device_id=&start=&end=&measured_fun=`） |
| `GET /api/z3a/status/` | Token / 連線狀態診斷 |
| `POST /api/z3a/refresh/` | 手動重新取得 Token |

**measured_fun 對應**：
- `1` = 電壓（dcv_value ÷ 1,000,000 → V）
- `5` = 電流（dca_value ÷ 1,000,000,000 → A；搭配分流器修正係數）
- `4` = dcma_value（目前恆為 0，無用）

### 即時資料 API（樹莓派上傳用）
| 端點 | 說明 |
|------|------|
| `GET/POST /api/systems/` | SystemGroup CRUD |
| `GET/POST /api/power-records/` | PowerRecord CRUD |
| `GET /api/realtime-data/` | 最新即時資料 |

---

## 6. Z3A 面板對照表

共 27 個 DeviceId（1 個待確認）：

| DeviceId | panel_id | 傾角 | 方位角 | 備註 |
|----------|----------|------|--------|------|
| Z3A0412097 | Panel_20_180_A | 20° | 180° | R1-4 |
| Z3A0412118 | Panel_20_180_B | 20° | 180° | R1-3 |
| Z3A0412115 | Panel_30_180_A | 30° | 180° | R1-2 |
| Z3A0412106 | Panel_30_180_B | 30° | 180° | R1-1 |
| Z3A0412107 | Panel_30_160_A | 30° | 160° | L1-8 |
| Z3A0512127 | Panel_30_160_B | 30° | 160° | L1-7 |
| Z3A0512134 | Panel_20_160_A | 20° | 160° | L1-6 |
| Z3A0412116 | Panel_20_160_B | 20° | 160° | L1-5 |
| Z3A0412095 | Panel_20_200_A | 20° | 200° | L1-4 |
| Z3A0512128 | Panel_20_200_B | 20° | 200° | L1-3 |
| Z3A0512135 | Panel_30_200_A | 30° | 200° | L1-2 |
| Z3A0412112 | Panel_30_200_B | 30° | 200° | L1-1 |
| Z3A0512125 | Panel_10_180_A | 10° | 180° | R2-4 ⚠ DeviceId 疑似與 L2-4 重複 |
| Z3A0412122 | Panel_10_180_B | 10° | 180° | R2-3 |
| Z3A0412099 | Panel_15_180_A | 15° | 180° | R2-2 |
| Z3A0412108 | Panel_15_180_B | 15° | 180° | R2-1 |
| Z3A0512132 | Panel_10_160_A | 10° | 160° | L2-8 |
| Z3A0512129 | Panel_10_160_B | 10° | 160° | L2-7 |
| Z3A0412098 | Panel_15_160_A | 15° | 160° | L2-6 |
| Z3A0412113 | Panel_15_160_B | 15° | 160° | L2-5 |
| （待確認） | Panel_15_200_A | 15° | 200° | L2-4 ⚠ DeviceId 未知 |
| Z3A0412105 | Panel_15_200_B | 15° | 200° | L2-3 |
| Z3A0512126 | Panel_10_200_A | 10° | 200° | L2-2 |
| Z3A0412120 | Panel_10_200_B | 10° | 200° | L2-1 |
| Z3A0412111 | Tracking_2_25_上 | 25° | — | 追日A上（實驗組） |
| Z3A0512124 | Tracking_2_25_下 | 25° | — | 追日A下（實驗組） |
| Z3A0412103 | Tracking_1_20_上 | 20° | — | 追日B上（對照組） |
| Z3A0312076 | Tracking_1_20_下 | 20° | — | 追日B下（對照組） |

---

## 7. 主要資料檔

**`data/combined_solar_data_20250301_20260406_processed.csv`**
- 時間範圍：2025-03-01 ～ 2026-04-06
- 欄位（共 20 欄）：`timestamp`, `tilt_angle`, `azimuth_angle`, `panel_id`, `voltage_V`, `current_A`, `power_W`, `daily_energy_Wh`, `solar_zenith`, `solar_azimuth`, `solar_elevation`, `theoretical_poa`, `airmass`, `dni`, `dhi`, `ghi`, `is_tracking`, `tracking_system`, `tracking_position`, `id`
- 時區：Asia/Taipei（UTC+8）
- 取樣頻率：10 分鐘

---

## 8. z3a_collect.py（歷史資料補抓腳本）

用於將 Z3A 雲端歷史資料合併進 CSV 檔案，格式與現有 CSV 完全一致。

```bash
# 抓最近 7 天（預設）
python z3a_collect.py

# 指定日期範圍
python z3a_collect.py --start 2026-04-07 --end 2026-05-03

# 指定天數
python z3a_collect.py --days 30
```

⚠ 執行前需先設定環境變數 `Z3A_TOKEN`，或讓 `.env.dev` 中的 Token 生效。  
⚠ Token 過期時間：2026-05-09（`exp: 1778646040`），過期後需重新取得。

---

## 9. 待解決事項

| 問題 | 說明 | 優先度 |
|------|------|--------|
| L2-4 DeviceId 待確認 | `Z3A0512125` 疑似同時對應 R2-4 和 L2-4，`Panel_15_200_A` 目前無法抓資料 | 高 |
| Z3A 歷史資料補抓 | 2026-04-07 至今的資料尚未合併進 CSV | 中 |
| Z3A Token 過期 | 2026-05-09 到期，需在 App 重新登入取得新 Token 並更新 `.env.dev` 和 `z3a_collect.py` | 中 |
| 電流單位換算確認 | dca_value ÷ 1e9 算出的 A 值是否需乘以分流器修正係數（20A/75mV），需對照實測值確認 | 低 |

---

## 10. 常用指令

```bash
# Docker 操作（必須在專案根目錄）
docker-compose -f docker-compose-dev.yml up -d          # 啟動全部服務
docker-compose -f docker-compose-dev.yml down           # 停止全部服務
docker-compose -f docker-compose-dev.yml build          # 重建 backend image
docker-compose -f docker-compose-dev.yml up -d --build  # 重建並啟動

# 查看 log
docker logs solar_backend --tail 50
docker logs solar_tailscale --tail 50

# 進入容器除錯
docker exec -it solar_backend bash

# Z3A API 除錯
python check_z3a.py

# 歷史資料補抓
python z3a_collect.py --start 2026-04-07 --end 2026-05-03

# 固定面板資料處理 GUI
python fixed_data_process_visualization/solar_data_pipeline.py

# 樹莓派控制器（在樹莓派上執行）
python raspberry-pi/src/main_controller.py --mode both
```

---

## 11. 環境變數（.env.dev 重要欄位）

| 變數 | 說明 |
|------|------|
| `Z3A_BASE_URL` | 七雲物聯 API 根 URL（`https://server.qiyunwulian.com:12341`） |
| `Z3A_PHONE` | 七雲物聯帳號手機號（用於自動重新登入） |
| `Z3A_PASSWORD` | 七雲物聯帳號密碼 |
| `Z3A_TOKEN` | Bearer Token，過期時間 2026-05-09 |
| `TS_AUTHKEY` | Tailscale Auth Key（Reusable + No Expiry + tag:container） |
| `SQL_ROOT_PASSWORD` | MySQL root 密碼 |
| `SQL_USER` / `SQL_PASSWORD` | MySQL 應用程式帳號 |
| `DJANGO_ALLOWED_HOSTS` | 含 `solar-dashboard.tail7c1eb9.ts.net` |
| `CSRF_TRUSTED_ORIGINS` | 含 `https://solar-dashboard.tail7c1eb9.ts.net` |

---

## 12. 已知設計決策與限制

- **dashboard.html 是單一大檔案**：所有前端 HTML/CSS/JS 都在這一個檔案，沒有 React/Vue，方便 Django static file 直接 serve。
- **固定面板資料用 CSV 而非 DB**：資料量大（49 MB），Django 啟動時一次性載入記憶體，查詢走 pandas。
- **Z3A 的 `requests` 套件用 lazy import**：避免套件未安裝時整個 Django crash，透過 `_REQUESTS_OK` flag，缺套件時各端點回傳 503。
- **Tailscale 用 Docker 容器而非 Windows 原生**：方便跨機器部署，但需注意 SSL 攔截工具（如 Fiddler）開著時會導致 Tailscale 容器無法連線。
