# 2026-07-14 追日系統上線進度總整理

**日期**:2026-07-14
**主軸**:4 個追日系統(2 ANFIS + 2 傳統差動)完整上線 + Dashboard 整理
**產出**:3 台 Pi 部署完成、Dashboard frontend 全面對齊、發現 INA3221 register bug 修補

---

## Slide 1 — 4 系統總覽表(現場左→右順序)

**場域實體位置(左 → 右)**

| 順序 | 1 | 2 | 3 | 4 |
|:---:|:---:|:---:|:---:|:---:|
| **系統簡稱** | ANFIS 2 | Traditional 2 | ANFIS 1 | Traditional 1 |
| **Dashboard 標籤** | 實驗組 II | 對照組 II | 實驗組 I | 對照組 I |
| **system_id** | **2** | **7** | **4** | **6** |
| **Pi hostname** | raspberrypi-1 | raspberrypi-v3 | raspberrypi-v4 | raspberrypi-v2 |
| **VPN IP (Tailscale)** | 100.66.182.46 | 100.126.13.120 | 100.79.66.68 | 100.117.40.76 |
| **Pi user** | `rte` | `raspberrypi` | `raspberrypi` | `raspberrypi` |
| **Controller** | anfis_controller.py | traditional_controller.py | anfis_controller.py | traditional_controller.py |
| **部署狀態** | ✅ 已上線 | ✅ 已上線 | ✅ 已上線(硬體異常)| ⏸ 未部署(VPN 未裝)|
| **VPN 狀態** | ● 連線 | ● 連線 | ● 連線 | ✗ 未接 |
| **主要缺口** | INA3221 chip / LDR 沒接 | RS485 線色 / LDR 沒接 | 🔴 GPIO LOW 仍 35W / Hall 5V | 整台待部署 |

**Dashboard 訪問**:`https://solar-dashboard.tail7c1eb9.ts.net/dashboard/`

---

## Slide 2 — raspberrypi-1(ANFIS 2 / 實驗組 II)

### 今日進度與問題

- ✅ 同步最新 anfis_controller.py(EPEVER SOC + battery + INA3221 register + 夜間邏輯 fix)
- ✅ Restart 後啟動流程正常
- ✅ MPPT V/I/P、電池 V/I/P/SOC 全部真實讀取
- ✅ ANFIS 推論與上傳持續運作
- ✅ Hall 位置回授啟用中
- ⚠️ INA3221 I2C timeout 持續(0x40 chip 故障)→ 影響 INA3221 CH1/CH2 資料
- ⚠️ LDR 硬體未接 → `simulate_ldr = True`

### 功能上線狀況

| 元件 | 狀態 | 備註 |
|---|:---:|---|
| ANFIS 推論 | 🟢 真實 | 9 維特徵 |
| MPPT PV V/I/P | 🟢 真實 | EPEVER RS485 0x3100 |
| 電池 V/I/P/SOC | 🟢 真實 | 0x3104-0x311A |
| LDR 4 方位 | 🟡 模擬 | 硬體未接,`simulate_ldr=True` |
| 推桿 GPIO | 🟢 真實 | 開/閉迴路都可 |
| Hall 位置回授 | 🟢 啟用 | 6/20 現場實測正確 |
| INA3221 電力監測 | 🔴 失敗 | I2C 0x40 timeout |
| API 上傳 | 🟢 成功 | Tailscale URL 正常 |
| 夜間停動 | 🟢 修好 | 只記錄不移動 |

---

## Slide 3 — raspberrypi-v3(Traditional 2 / 對照組 II)

### 今日進度與問題

- ✅ 首次部署 traditional_controller.py 到 `~/solar_tracking/traditional_2/`
- ✅ Systemd service 建立並自動啟動
- 🔧 lgpio 編譯失敗 → 安裝 `swig + python3-dev + liblgpio-dev` 後成功
- 🔴 **舊 process 資料污染**:一支從 6/12 起就在跑的 `traditional_controller.py`(pid 1765)用 old `system_id=4`,持續灌 traditional 格式資料進 v4 的 dashboard → `systemctl restart` 強制殺舊 process 才生效
- 🔴 **INA3221 register off-by-1 bug**:所有 SHUNT/BUS 位址錯 1,讀 shunt 卻得 bus voltage → 修正 `_REG_SHUNT/_REG_BUS`
- 🔴 **非太陽時間 skip 整個 cycle bug**:過 19:00 完全不記錄資料 → 改成「只跳過推桿動作,LDR/MPPT 照讀照傳」
- ⚠️ MPPT NoResponse(RS485 線色需現場修正:藍/白藍/棕 to Pin 4/5/8)
- ⚠️ LDR 硬體未接,MCP3008 讀浮空 pin 噪聲(~1)

### 功能上線狀況

| 元件 | 狀態 | 備註 |
|---|:---:|---|
| Traditional 差動邏輯 | 🟢 真實 | 東西/南北 LDR 差判斷 |
| MPPT PV V/I/P | 🔴 NoResponse | 現場修 RS485 線色 |
| 電池 V/I/P/SOC | 🔴 NoResponse | 同上 |
| LDR 4 方位 | ⚠️ 未接 | MCP3008 讀噪聲,決策不可靠 |
| 推桿 GPIO | 🟢 真實 | INA3221 顯示動作時 447-487mA ✓ |
| INA3221 CH1(推桿)| 🟢 真實 | Register fix 後 24V 正確 |
| INA3221 CH2(Pi)| 🟢 真實 | 同上 |
| API 上傳 | 🟢 成功 | |
| 夜間停動 | 🟢 修好 | 只記錄不移動 |

---

## Slide 4 — raspberrypi-v4(ANFIS 1 / 實驗組 I)

### 今日進度與問題

- ✅ 首次部署 anfis_controller.py + 建 systemd + venv(TF + sklearn 等 5-10 min 安裝)
- ✅ ANFIS 模型載入 + LDR 4 方位讀取(v4 有實體 LDR + calibration)
- ✅ EPEVER MPPT/電池 SOC 全部真實讀取
- 🔧 Hall 感測器需 5V 供電,若接 Pi 5V 會讓 Pi 沒電 → 關 `hall.enabled = False` 退回開迴路時間驅動
- 🔴 **系統名稱對應 bug**:Dashboard frontend 寫死 id=1/2/3/4,實際 DB 是 id=4/2/6/7,造成 v4 資料被誤標成「對照組 II」→ 修 SYSTEMS/SYS_MAP/HTML element ids/pill button data-sys/CSV download 連結
- 🔴 **非太陽時間仍跑格網掃描 + 移動 bug**:sun_time 檢查放在 grid search 後,晚上每 10 分鐘動 15° 才回歸,浪費電磨損推桿 → sun_time 檢查移到迴圈開頭
- 🔴 **INA3221 register off-by-1 bug**:與 v3 相同 → 修正
- 🔴 **硬體異常:GPIO 全 LOW 仍有 1.47A / 35W 持續消耗**
  - 已排除 code / GPIO 邏輯問題(手動測試 GPIO 全 LOW 電流不變)
  - 硬體嫌疑:H 橋 MOSFET 短路 / 24V bus 上有未知負載 / motor 線圈損壞
  - 已 stop + disable service,防止 controller 再命令推桿
  - **待現場處理**:關 24V 電源、摸 H 橋是否過燙、拔推桿線觀察電流變化

### 功能上線狀況

| 元件 | 狀態 | 備註 |
|---|:---:|---|
| ANFIS 推論 | 🟢 真實 | |
| MPPT PV V/I/P | 🟢 真實 | |
| 電池 V/I/P/SOC | 🟢 真實 | Batt V ~13.24V |
| LDR 4 方位 | 🟢 真實 | 有 channel_calibration.json |
| 推桿 GPIO | 🟢 真實 | 但硬體有異常 |
| Hall 位置回授 | 🔴 關閉 | 5V 供電問題,退回開迴路 |
| INA3221 CH1(推桿)| 🟡 讀值正確但異常 | 24V 對,但電流 1.47A idle ← 🚨 |
| INA3221 CH2(Pi)| 🟢 真實 | 24V bus / ~0.128A |
| API 上傳 | 🟢 成功 | |
| 夜間停動 | 🟢 修好 | |
| **Service 狀態** | 🔴 已 stop + disable | 硬體異常,等現場處理 |

---

## Slide 5 — Dashboard 全面修補 + 明日現場工作

### Dashboard(所有系統影響)

**Frontend 5 個 bug 全修**:
1. `SYSTEMS/SYS_MAP/CLR_MAP/TYP_MAP`:1/2/3/4 → **4/2/6/7**
2. 總覽 4 個 header 卡片 HTML element ids:`ov-s1/2/3/4-*` → `ov-s4/2/6/7-*`
3. 即時監控 pill button data-sys 屬性
4. `live-sys-panel-*` 容器 id + `liveSelect()` 用 id 匹配 panel
5. CSV download 連結 + 預設 liveSelect(4)

**單位修正**:推桿電流 `mA` → `A`(dashboard 資料實際是 A)

**Backend 加欄位**:PowerRecord + serializer + views.py CSV export 全部含 `battery_voltage/current/power/SOC`

### 明日現場工作優先序

| 優先 | 系統 | 工作 | 預估時間 |
|:---:|---|---|---|
| 🔴 P0 | v4 | **關 24V 電源,查明 35W 漏電源**(H 橋 / motor / 未知負載)| 30-60 min |
| 🔴 P0 | v3 | **修 RS485 線色**(藍 Pin4=B、白藍 Pin5=A、棕 Pin8=GND)| 5 min |
| 🟡 P1 | v4 | 修 Hall 5V 供電(不能吃 Pi 5V)| 20 min |
| 🟡 P1 | raspberrypi-1 | 檢查 INA3221 chip / 換掉 | 15 min |
| 🟢 P2 | 全部 | 接 LDR 硬體(v3 / raspberrypi-1)| 30 min |
| 🟢 P2 | Traditional 1 | 部署到 raspberrypi-v2(需先接 VPN)| 60 min |

### 今日重大 bug 全收錄(list)

1. **系統 id 混亂**:frontend 寫死 1-4,實際 DB 是 4/2/6/7 → dashboard 標籤全錯位
2. **INA3221 register off-by-1**:所有 controller 讀電壓/電流全錯(bus 讀成 shunt / shunt 讀成 bus)
3. **非太陽時間仍動推桿**:sun_time 檢查放在 grid search 後,晚上每 10 分鐘無用移動
4. **v3 舊 process 資料污染**:6/12 舊 code 一直在跑,持續灌錯 system_id=4
5. **v4 GPIO LOW 仍 35W**:硬體漏電(尚待現場診斷)
6. **dashboard 電流單位標 mA 但實際 A**

### 里程碑

**今天前**:1 台 Pi(raspberrypi-1)有真實資料,dashboard 標籤混亂
**今天後**:3 台 Pi 上線、資料流乾淨、dashboard frontend 完全對齊 backend、EPEVER 電池 SOC 全上線、controller 兩支(anfis + traditional)資料 schema 一致

**下一步**:排除 v4 35W 漏電 + v3 RS485 → 3 系統完整運作,可開始累積實驗資料
