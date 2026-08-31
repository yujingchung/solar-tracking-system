# Session Handoff — 4 Pi 系統上線狀態總覽

> **給下一個 session 接手用**。7/15 修 rpi-1 + 部署改造 3 台;8/07 新部署 Traditional 1 完成 → 4 系統全部上線。
> 若下輪要動 Pi 上的 controller,先讀完 §7「Pi 端部署陷阱」。

## 0. 一分鐘總覽(2026-08-07 底)

| 系統 | Pi | sys_id | 上線 | MPPT | 硬體 | 主缺口 |
|---|---|:---:|:---:|:---:|:---:|---|
| **實驗組 II** ANFIS 2 | rpi-1 (rte@100.66.182.46) | 2 | 🟢 | 🟢 | ⚠️ INA3221 chip 壞 | INA3221 換 chip |
| **對照組 II** Trad 2 | v3 (100.126.13.120) | 7 | 🟢 | 🔴 NoResponse | 🟢 | RS485 線色現場修 |
| **實驗組 I** ANFIS 1 | v4 (100.79.66.68) | 4 | 🟡 | 🟢 | 🔴 33W 漏電 | H 橋 / motor 診斷 |
| **對照組 I** Trad 1 | raspberrypi (100.96.31.110) | 6 | 🟢 | 🟢 | 🟢 | 全對(4 台裡最健康) |

**共通問題(下次現場一次修)**:所有 3 個有 LDR 的 Pi(rpi-1、v3、Trad 1)的 4 方位 raw ADC 全 saturate 在 ~1000+。**現場換 10kΩ → 2.2kΩ 分壓電阻**才能有 gradient 讓差動/微調生效。

## 0.1 本輪(2026-08-07)新增

- **Traditional 1(對照組 I,sys_id=6)首次部署** 到 `raspberrypi@100.96.31.110`
  - 部署目錄:`~/solar_tracking/traditional_1/` + 獨立 `.venv/`
  - Systemd service:`solar_tracking.service`(15:03 上線)
  - D 槽 traditional_controller.py 的 default `system_id=6` 剛好對,**不用 sed**
  - 首筆 log:`PV=34.46V/0.01A/1.6W Batt=14.61V SOC=100%` MPPT 通、LDR 有值、上傳成功
- **Pin 對應驗證**(axis_verify.py 現場測試):
  - Traditional 1 pin 標籤 = 實體(和 rpi-1 相反,不用對調)
  - NS extend = 南、EW extend = 西
  - 已存 memory `actuator_pin_mapping_traditional_1.md`
- **INA3221 baseline**:CH1 idle 4mA / 0.1W → **無漏電**,對比 v4 的 1.4A/33W 明顯健康
- 目前 4 台完整上線(v4 硬體有問題但仍在跑)

## 0.2 本次還沒完成的事

- v3 MPPT RS485 硬體修復(現場)
- v4 33W 漏電硬體診斷(現場)
- 3 台 Pi LDR 分壓電阻換小顆(現場)
- rpi-1 INA3221 chip 換掉(現場)
- CONFIG 分離到 `local_config.json`(避免每次 scp 蓋掉 system_id,長期軟體改善)

---

---

## 1. 4 個系統對應表(從左至右 = 現場實體位置)

| 順序 | 1 | 2 | 3 | 4 |
|:---:|:---:|:---:|:---:|:---:|
| **系統簡稱** | ANFIS 2 | Traditional 2 | ANFIS 1 | Traditional 1 |
| **Dashboard 標籤** | 實驗組 II | 對照組 II | 實驗組 I | 對照組 I |
| **DB `system_id`** | **2** | **7** | **4** | **6** |
| **Pi hostname** | raspberrypi-1 | raspberrypi-v3 | raspberrypi-v4 | raspberrypi (預設名) |
| **VPN IP (Tailscale)** | 100.66.182.46 | 100.126.13.120 | 100.79.66.68 | **100.96.31.110** ⚠️ 2026-07-15 新上線,取代舊 100.117.40.76(v2 hostname,Apr 17 offline 殘留) |
| **Pi user** | `rte` | `raspberrypi` | `raspberrypi` | `raspberrypi`(待確認) |
| **Pi 端工作目錄** | `~/solar_tracking/anfis_2/` | `~/solar_tracking/traditional_2/` | `~/solar_tracking/anfis_1/` | 待建立 `~/solar_tracking/traditional_1/` |
| **Controller** | `anfis_controller.py` | `traditional_controller.py` | `anfis_controller.py` | `traditional_controller.py` |
| **Systemd service** | `solar_tracking.service` | `solar_tracking.service` | `solar_tracking.service` | 待建立 |
| **部署狀態** | 🟢 剛救回來 | 🟢 上線中 | 🟡 硬體漏電但在跑 | 🟢 **2026-08-07 上線,4 台裡最健康** |

**Dashboard URL**: `https://solar-dashboard.tail7c1eb9.ts.net/dashboard/`

**SSH 快捷**(Windows PowerShell):
```powershell
ssh rte@100.66.182.46           # rpi-1
ssh raspberrypi@100.126.13.120  # v3
ssh raspberrypi@100.79.66.68    # v4
ssh raspberrypi@100.96.31.110   # Traditional 1(2026-07-15 新上線)
```

---

## 2. 各系統當前部署細節(2026-07-15 晚上)

### 2.1 raspberrypi-1(ANFIS 2 / sys_id=2)

**Service**:`solar_tracking.service`(單一 service,不叫 `solar-*.service`)
**Systemd unit 檔**:`/etc/systemd/system/solar_tracking.service`
**Log 檔**:`~/solar_tracking/anfis_2/anfis_controller.log` + `service.log`
**channel_calibration.json**:🔴 **不存在**(ldr_module fallback 用 ratio=1.0)

**元件狀態**:
| 元件 | 狀態 | 備註 |
|---|:---:|---|
| ANFIS 推論 | 🟢 真實 | 9 維特徵(含 illumination) |
| MPPT PV V/I/P | 🟢 32V/0A(SOC=100 電池滿停充,是正常物理反應) | EPEVER RS485 baud=115200 slave=1 |
| 電池 V/I/P/SOC | 🟢 14.46V/0A/100% | 0x3104-0x311A |
| LDR 4 方位 | 🟢 讀真值(**今天 sed 過 True→False**) | raw ADC ~1000 全 saturate |
| 推桿 GPIO | 🟢 有動 | NS=[17,27,22,23] EW=[5,6,13,19] |
| Hall 位置回授 | ⚠️ 一直超時 | pin 24/25 NS, 16/26 EW,可能感測器線斷 |
| INA3221 CH1 推桿 | 🔴 I2C timeout | chip 0x40 硬體壞,record 上是 null |
| INA3221 CH2 Pi | 🔴 I2C timeout | 同上 |
| API 上傳 | 🟢 每 10 分鐘 | 資料進 DB 正常 |
| 夜間停動 | 🟢 修好 | 19:00 後只記錄不移動 |

**今日重大 bug**:`~/solar_tracking/anfis_2/anfis_controller.py` 第 104 行 `'simulate_ldr': True` → 用亂數上傳(range 300-800)。已 sed 改成 `False`,現在讀真硬體。

**今天發生的 incident**:15:41 sed + restart 後過一陣子 Pi 整台掛掉(kernel hang,Tailscale 顯示 idle 但 ping/SSH 全 timeout)。半小時後救回來(可能 watchdog 或 kernel oom-recover)。原因未知,懷疑 INA3221 timeout 反覆終於把 I2C bus 死鎖到 kernel。

---

### 2.2 raspberrypi-v3(Traditional 2 / sys_id=7)

**Service**:`solar_tracking.service`
**Log 檔**:`~/solar_tracking/traditional_2/traditional_controller.log`
**channel_calibration.json**:不存在(traditional 沒用 ldr_module,不影響)

**元件狀態**:
| 元件 | 狀態 | 備註 |
|---|:---:|---|
| Traditional 差動邏輯 | 🟢 有跑 | 東西/南北 LDR 差判斷 |
| MPPT PV V/I/P | 🔴 全 0 | `NoResponse` at 115200/9600/19200,slave 1/2/3 都測過 → **RS485 硬體層問題** |
| 電池 V/I/P/SOC | 🔴 全 0 或 null | 同 MPPT |
| LDR 4 方位 | 🟢 讀真值 raw ~1010 全 saturate | 決策每次都「保持」,ew_diff 只 ±3-6 |
| 推桿 GPIO | 🟢 有動時 447-487mA | INA3221 CH1 idle 3.6mA 正常 |
| INA3221 CH1 推桿 | 🟢 24V/3.6mA idle | 和 v4 的 1.4A 對比 = v4 硬體真有問題 |
| INA3221 CH2 Pi | 🟢 23.96V/115mA | 正常 |
| API 上傳 | 🟢 每 10 分鐘 | |
| 4 方位分別讀值上傳 | 🟢 **今日補上** | D 槽 traditional_controller.py 加了 light_east/west/south/north 4 個 payload |
| 夜間停動 | 🟢 修好 | |

**今日 bug 陷阱**:
- `scp` 覆蓋掉了先前手動改的 `system_id: 6`(D 槽 default 是 6)→ 資料短暫上到「對照組 I」sys_id=6。已 sed 改回 7。
- 「非太陽時間 skip 整個 cycle」bug 已修:過 19:00 現在會**只跳過推桿動作,LDR/MPPT 照讀照傳**。

---

### 2.3.1 raspberrypi(Traditional 1 / sys_id=6)🟢 **2026-08-07 新上線,最健康的一台**

**Service**:`solar_tracking.service`(2026-08-07 15:03 首次上線)
**Log 檔**:`~/solar_tracking/traditional_1/traditional_controller.log`
**channel_calibration.json**:不存在(traditional 沒用 ldr_module,不影響)

**元件狀態**:
| 元件 | 狀態 | 備註 |
|---|:---:|---|
| Traditional 差動邏輯 | 🟢 | LDR 差值 < threshold 每次「保持」(saturate 問題) |
| **MPPT PV V/I/P** | 🟢 **34.46V/0.01A/1.6W** | RS485 通!比 v3 好 |
| 電池 V/I/P/SOC | 🟢 14.61V/SOC=100% | |
| LDR 4 方位 | 🟢 東=1006 西=1007 南=1006 北=1014 | raw saturate,同 v3/rpi-1 |
| 推桿 GPIO | 🟢 兩軸都能動(2026-08-07 現場實測) | pin 標籤=實體,不像 rpi-1 反 |
| INA3221 CH1 推桿 | 🟢 idle 4mA/0.1W | **無漏電**(和 v4 的 1.4A/33W 天差地遠) |
| INA3221 CH2 Pi | 🟢 23.91V/135mA | |
| API 上傳 | 🟢 | |
| 4 方位分別讀值 | 🟢 有 | D 槽 traditional_controller.py 補過 |
| 夜間停動 | 🟢 修好 | |

**Pin 對應**(2026-08-07 axis_verify.py 實測):
- NS(pin 17/27/22/23)= 實體 NS, extend = **南**(往南倒)
- EW(pin 5/6/13/19)= 實體 EW, extend = **西**(往西轉)
- **和 rpi-1 相反** — 這台 pin 標籤和實體一致,不用對調

---

### 2.3.2 raspberrypi-v4(ANFIS 1 / sys_id=4)🟡 硬體漏電但持續運作

**Service**:`solar_tracking.service`(**運行中!** 不是先前以為的 stop+disable)
**Log 檔**:`~/solar_tracking/anfis_1/anfis_controller.log`
**channel_calibration.json**:🟢 存在,ratio 正常 ~1.0(0.99-1.02)

**元件狀態**:
| 元件 | 狀態 | 備註 |
|---|:---:|---|
| ANFIS 推論 | 🟢 真實 | |
| MPPT PV V/I/P | 🟢 33V/0A | SOC=100 停充,正常 |
| 電池 V/I/P/SOC | 🟢 14.3V/0A/100% | |
| LDR 4 方位 | 🟢 真實讀值 | channel_calibration.json 正確 |
| 推桿 GPIO | 🟢 有動 | 但 hall 讀不到 → 開迴路運轉 |
| Hall 位置回授 | 🔴 **關閉** | 5V 供電問題,若接 Pi 5V 會讓 Pi 斷電 |
| INA3221 CH1 推桿 | 🟡 **1.4A idle / 33W 持續漏電** 🔴 | 已排除 code 問題,是硬體(H 橋 or motor 短路 or 24V bus 上有未知負載) |
| INA3221 CH2 Pi | 🟢 24V/128mA | 正常 |
| API 上傳 | 🟢 | |

**Root cause 待現場診斷步驟**:
1. 關 24V 電源 → 摸 H 橋(BTS7960)散熱片是否燙 → 燙 = MOSFET 短路
2. 拔推桿 motor 接頭 → 開回 24V → INA3221 CH1 若掉到 ~0 = 問題在 motor 線圈短路
3. 若電流還在 = 問題在 24V bus 上有其他負載

**User 選 A(讓 service 繼續跑收資料)** — 接受每天 0.8 度電漏電 + 推桿磨損代價,等下次現場修硬體。

---

## 3. 今日 D 槽檔案改動(2026-07-15)

### 3.1 `raspberry-pi/src/controllers/anfis_controller.py`
- **修 payload 上傳的 light_north/east/west/south 改成 raw ADC**(反除 slope):
  ```python
  'light_north': round(ldr_cal.get('north', 0.0) / CONFIG['ldr_calibration']['north']['slope'], 1),
  'light_east':  round(ldr_cal.get('east',  0.0) / CONFIG['ldr_calibration']['east']['slope'],  1),
  'light_west':  round(ldr_cal.get('west',  0.0) / CONFIG['ldr_calibration']['west']['slope'],  1),
  'light_south': round(ldr_cal.get('south', 0.0) / CONFIG['ldr_calibration']['south']['slope'], 1),
  ```
- ANFIS 決策內部仍用 `ldr_cal`(post-slope),行為不變。

### 3.2 `raspberry-pi/src/controllers/traditional_controller.py`
- **補上 4 方位 raw 讀值 payload**(先前只有 light_intensity):
  ```python
  'light_intensity':  values['illumination'],
  'light_east':       values['east'],
  'light_west':       values['west'],
  'light_south':      values['south'],
  'light_north':      values['north'],
  ```
- Traditional 讀 LDR 沒經 ldr_module,`values['east']` 就是 raw ADC。

### 3.3 `backend/static/dashboard.html`
- 「四方位光照 (lux)」→ **「四方位光照 (raw ADC 0-1023)」+ hover tooltip 提示過曝**
- 總覽表「光照(lux)」→「照度(raw)」
- **總照 = 4 方位 raw 平均**(不再顯示 slope 後的 illumination):
  ```javascript
  const vals = [lN, lE, lW, lS].filter(v => v != null);
  const avg = vals.length === 4 ? vals.reduce((a,b)=>a+b,0) / 4 : bl;
  setEl(`s${p}-lt`, fmt(avg, 0));
  ```

**Backend 重啟**(改完 dashboard.html 要 restart 才生效):
```powershell
docker-compose -f docker-compose-dev.yml restart backend
```

---

## 4. 今日發現的重大 bug 總表

| # | Bug | 系統 | Root Cause | 狀態 |
|---|---|---|---|---|
| 1 | Dashboard system_id 混亂 | frontend | 寫死 1/2/3/4,實際 DB 是 4/2/6/7 | ✅ 已修 |
| 2 | INA3221 register off-by-1 | 全 anfis + traditional | shunt/bus reg 位址錯 1 | ✅ 已修 |
| 3 | 非太陽時間仍動推桿 | anfis controller | sun_time 檢查放在 grid search 後 | ✅ 已修 |
| 4 | v3 舊 process 資料污染 | v3 | 6/12 舊 code 一直在跑,灌錯 sys_id=4 | ✅ systemctl restart 清掉 |
| 5 | v4 GPIO LOW 仍 33W | v4 硬體 | H 橋短路 or 24V bus 未知負載 | 🔴 待現場診斷 |
| 6 | Dashboard 電流單位標 mA 但實際 A | frontend | 單位錯 | ✅ 已修 |
| 7 | **rpi-1 simulate_ldr=True** | rpi-1 code | 上傳 random 亂數當 LDR 值(range 300-800) | ✅ sed 改 False |
| 8 | scp 覆蓋 system_id 導致資料上錯位置 | v3 部署 | D 槽 default 6,v3 應該 7,scp 後回到 6 | ⚠️ **每次 scp 後都要 sed 一次!長期方案是分 CONFIG 到 local file** |
| 9 | traditional payload 4 方位讀值 null | traditional controller | code 沒填 light_east/west/south/north | ✅ D 槽已補 |
| 10 | ANFIS payload 4 方位是 raw × slope 顯示 > 1023 | anfis controller | slope 1.15 讓值超 1023 | ✅ 今日反除 slope |

---

## 5. 待辦(task list state)

| # | 內容 | 狀態 | Owner |
|---|---|:---:|---|
| 1 | 加讀 EPEVER SOC | ✅ | done |
| 2 | 同步 traditional_controller 加 EPEVER + battery + SOC | ✅ | done |
| 3 | v3 加 simulate_ldr 分項旗標 | ⏸ | 之後 |
| 4 | ~~Dashboard 隱藏未部署的對照組 I(sys_id=6)~~ | 🗑️ | 已刪除,現在對照組 I 已部署(2026-08-07)|
| 5 | 修 dashboard.html system_id 對應表 | ✅ | done |
| 6 | 診斷 INA3221 電壓讀值 2V | ✅ | done |
| 7 | 修 INA3221 register 位址 off-by-1 | ✅ | done |
| 8 | 修「非太陽時間仍動推桿」 | ✅ | done |
| 9 | 🔴 **v4 硬體 33W 漏電** | 🔴 | **下次現場 P0** |
| 10 | 現場測試 3 系統 LDR + MPPT | ✅ | done |
| 11 | 補 traditional light_east/west/south/north payload | ✅ | done |
| 12 | LDR raw 全 saturate ~1000:換小分壓電阻 | 🔴 | **下次現場 P0**,推薦 2.2kΩ |
| 13 | Pi 端部署 CONFIG 分離到 local_config.json | ⏸ | **長期改善**,避免 scp 覆蓋 system_id |
| 14 | rpi-1 simulate_ldr=True bug | ✅ | done |
| 15 | **Traditional 1 (100.96.31.110) 部署 controller** | ✅ | done 2026-08-07 |
| 16 | Traditional 1 pin 對應驗證(axis_verify.py 實測) | ✅ | 標籤=實體,extend=南/西 |
| 17 | Dashboard 顯示改成 raw ADC + 總照 = 4 方位平均 | ✅ | done(anfis_controller 反除 slope 上傳)|

---

## 6. 明日現場工作優先序

| 優先 | 系統 | 工作 | 預估時間 |
|:---:|---|---|---|
| 🔴 P0 | v4 | 關 24V 電源,查明 33W 漏電源(H 橋 / motor / 未知負載) | 30-60 min |
| 🔴 P0 | v3 | 修 RS485 線色(藍 Pin4=B、白藍 Pin5=A、棕 Pin8=GND),或換整個 RS485 adapter | 5-30 min |
| 🔴 P0 | 全部 3 台 | 換 LDR 分壓電阻 10kΩ → 2.2kΩ 讓亮光下 raw 落 600-900 有 gradient | 30 min |
| 🟡 P1 | rpi-1 | 檢查 INA3221 chip / 換掉(避免 I2C timeout deadlock 讓 Pi 掛) | 15 min |
| 🟡 P1 | v4 | 修 Hall 5V 供電(不能吃 Pi 5V,需獨立電源) | 20 min |
| ✅ | ~~Traditional 1 部署~~ | 已於 2026-08-07 上線,IP 100.96.31.110 hostname `raspberrypi` | done |

---

## 7. Pi 端部署陷阱(⚠️ 下輪必讀)

### 7.1 CONFIG 寫死在 .py 檔頭部
每支 controller 的 CONFIG dict 在 .py 檔第 44-232 行左右,包含 `system_id`、`simulate_*`、`hall.enabled` 等 per-Pi 設定。**沒有外部 config file 讀取**。

D 槽的 `config/*.json` 只給舊的 `raspberry_pi_data_collector.py` 用,新 controller 不讀。

### 7.2 scp 覆蓋 = 蓋掉 per-Pi 設定 ⚠️
每次 `scp anfis_controller.py raspberrypi@x.x.x.x:...` 都會**蓋掉先前手動改的 system_id、hall.enabled、simulate_ldr 等**。

D 槽 default 值:
- `anfis_controller.py`: `system_id=7`, `simulate_ldr=None`, `hall.enabled=True`
- `traditional_controller.py`: `system_id=6`, `simulate_ldr=None`

**scp 之後必跑的 sed 3 支 Pi 對應命令**:

**rpi-1 (ANFIS 2)**:
```bash
sed -i "s/'system_id': 7,/'system_id': 2,/" ~/solar_tracking/anfis_2/anfis_controller.py
sed -i "s/'simulate_ldr':      None,/'simulate_ldr':      False,/" ~/solar_tracking/anfis_2/anfis_controller.py
sudo systemctl restart solar_tracking.service
```

**v3 (Traditional 2)**:
```bash
sed -i "s/'system_id': 6,/'system_id': 7,/" ~/solar_tracking/traditional_2/traditional_controller.py
sudo systemctl restart solar_tracking.service
```

**v4 (ANFIS 1)**:
```bash
sed -i "s/'system_id': 7,/'system_id': 4,/" ~/solar_tracking/anfis_1/anfis_controller.py
sed -i "s/'simulate_ldr':      None,/'simulate_ldr':      False,/" ~/solar_tracking/anfis_1/anfis_controller.py
sed -i "s/'simulate_mppt':     None,/'simulate_mppt':     False,/" ~/solar_tracking/anfis_1/anfis_controller.py
sed -i "s/'simulate_actuator': None,/'simulate_actuator': False,/" ~/solar_tracking/anfis_1/anfis_controller.py
python3 -c "
p = '/home/raspberrypi/solar_tracking/anfis_1/anfis_controller.py'
t = open(p).read().replace(\"'enabled':       True,   # False\", \"'enabled':       False,  # False\")
open(p,'w').write(t)
"
sudo systemctl restart solar_tracking.service
```

### 7.3 systemctl restart vs start ⚠️
Python **不 hot-reload**。scp 完 .py 之後,一定要 `systemctl restart <service>`(**不是 `start`**)。舊 process 記憶體內是舊 code,disk 改了不會生效。(見 memory 記錄 `feedback_scp_python_reload.md`)

### 7.4 INA3221 register 已修 off-by-1
- 舊值錯:`_REG_SHUNT = {1: 0x02, 2: 0x04, 3: 0x06}`
- 新正確:`_REG_SHUNT = {1: 0x01, 2: 0x03, 3: 0x05}`
- `_REG_BUS = {1: 0x02, 2: 0x04, 3: 0x06}`

如果現場獨立驗證 INA3221 電流讀值,**要用新 register 位址**,不然拿到的是 bus voltage 當 shunt voltage 值(v4 的 190V 誤讀就是這個)。

**正確 INA3221 讀值 python one-liner**(給 debug 用):
```python
import smbus2
b = smbus2.SMBus(1)
def r(reg):
    d = b.read_i2c_block_data(0x40, reg, 2)
    v = (d[0] << 8) | d[1]
    return v - 65536 if v >= 32768 else v
# 注意這裡的公式:bus 直接除 1000,不再乘 8;shunt 保持不變
for ch, (sr, br) in [(1,(0x01,0x02)), (2,(0x03,0x04))]:
    shunt_mv = r(sr) * 40 / 1000 / 8   # shunt mV
    bus_v    = r(br) / 1000            # bus V(不是 × 8 / 1000!)
    i_a      = shunt_mv / 100          # shunt_mV / 100 = A(0.1Ω)
    print(f'CH{ch}: V={bus_v:.2f}V I={i_a:.3f}A P={bus_v*i_a:.1f}W')
```

---

## 8. 診斷 API cheat sheet

**從 Windows PowerShell 打 dashboard API**:
```powershell
# 系統最新資料
curl.exe "https://solar-dashboard.tail7c1eb9.ts.net/api/power-records/?system=2&ordering=-timestamp&page_size=3"
# 換 system=2/7/4/6 分別看實 II/對 II/實 I/對 I

# 4 系統最新 timestamp 一起看
foreach ($sid in 2, 7, 4, 6) {
  curl.exe -s "https://solar-dashboard.tail7c1eb9.ts.net/api/power-records/?system=$sid&ordering=-timestamp&page_size=1" | ConvertFrom-Json | ForEach-Object { "$sid : $($_.results[0].timestamp)" }
}
```

**判斷網路狀況**:
```powershell
# 3 台 ping
foreach ($ip in "100.66.182.46", "100.126.13.120", "100.79.66.68") {
    Write-Host "$ip : $(Test-Connection $ip -Count 1 -Quiet)"
}

# Tailscale peer 狀態
tailscale status | Select-String "raspberrypi"
```

**辨別 Pi 死機 vs WiFi outage**:
- 3 台都 ping 不通 → WiFi 場域 outage(WiFi 有獨立小 PV + 電池,memory 有記)
- 只 1 台不通,其他通 → 單機掛
- Tailscale 顯示 "idle" tx 有增長 rx = 0 → **kernel hang**,只能物理 power cycle
- Tailscale 顯示 "active" 但沒資料 → 網路通但 controller 有事

---

## 9. 需要記得的物理常識

### 9.1 為何白天 MPPT 讀值 `PV=32V I=0A P=0W`?
**電池滿了(SOC=100)MPPT 主動停充**。這是 EPEVER 的 float / equalize 模式正確反應,**不是 bug**。要看到有功率就得等**電池被下游負載耗掉**(場域主控制室吃電 ~98W)才會重新充電。

### 9.2 為何 LDR raw 全 saturate ~1000?
現有 10kΩ 分壓電阻在亮光下讓 LDR 分壓輸出 saturate 到接近 VCC。**現場換 2.2kΩ 讓亮光下讀值落在 600-900** 才有 gradient。差動控制 / ANFIS 微調都需要 gradient 才能作用。

### 9.3 為何 rpi-1 沒 `channel_calibration.json`,v4 有?
v4 是 6/17 部署,那時跑過校正腳本產生 JSON(ratio ~1.0 正常)。rpi-1 是 6/5 部署後沒跑校正,ldr_module fallback 用 ratio=1.0(等於沒校正,對決策無影響)。

### 9.4 場域電源架構(2 個獨立系統)
- **主系統**:大電池,下游控制室持續耗 ~98W,大電池是 3 支 tracking Pi 的電源
- **WiFi 系統**:獨立小 PV + 小電池,沒有 SOC 監控,天氣不好會斷網 → **3 台 Pi 同時失聯 = WiFi 斷,不是 Pi 掛**

### 9.5 raspberrypi-1 推桿 pin 對應(容易搞錯)
2026-06-20 現場實測結果,`dual_actuator_upload.py` 檔名跟 pin 對應**反了**:
- NS(南北 / 傾角 γ):pin 17=brown_high, 27=blue_high, 22=brown_low, 23=blue_low
- EW(東西 / 方位 ζ):pin 5=brown_high, 6=blue_high, 13=brown_low, 19=blue_low
- Extend = brown_high + blue_low HIGH(4-pin H 橋控制)

---

## 10. 今日發生的小事件回顧(如果下輪遇到類似狀況)

### 10.1 15:41 rpi-1 突然掛掉
時間點:sed 改 simulate_ldr True→False + `systemctl restart solar_tracking.service` 後幾分鐘。
症狀:SSH `Connection reset` → 之後全 timeout。Tailscale 顯示 idle,tx 有增加 rx = 0。
恢復:等 ~30 min 後 Pi 自己回來(watchdog 或 kernel recovery)。
**猜測原因**:INA3221 chip 硬體壞,I2C timeout 反覆最終把整個 I2C bus 死鎖到 kernel level。**下次 rpi-1 掛,先懷疑 INA3221**。

### 10.2 v3 資料短暫上到「對照組 I」
時間點:scp 新 code 後,忘了 sed system_id 6→7 就 restart。
症狀:sys_id=6 突然開始有資料流入(對照組 I 沒部署,不該有資料)。
恢復:sed 改回 7 + restart。
教訓:見 §7.2,scp 後**必**跑 sed。

---

## 11. 附加參考檔案

- `docs/daily-reports/2026-07-14_deployment_progress_slides.md`(昨天的 5 頁 PPT 摘要)
- `CLAUDE.md` §4(dashboard 架構 7 tab)
- `CLAUDE.md` §5(API endpoints 完整列表)
- `CLAUDE.md` §6(Z3A device map)
- Memory `feedback_scp_python_reload.md`(SCP+Python 部署陷阱)
- Memory `actuator_pin_mapping_raspberrypi_1.md`(rpi-1 推桿 pin 實測)
- Memory `epever_battery_readings.md`(EPEVER 電池 register 對照)
- Memory `project_raspberry_pi_deployment.md`(4 台 Pi 完整部署對照)

---

**Handoff 版本**:2026-07-15 晚
**上輪 session**:主要做 dashboard raw display 改動 + rpi-1 simulate_ldr bug 修正 + 各 Pi 狀況全面 dump
**下輪 session 進入時**:先跑 §8 API cheat sheet 看 3 系統最新 timestamp + LDR 讀值,確認今天做的改動 dashboard 上有生效(4 方位應顯示 raw 900-1050 附近)
