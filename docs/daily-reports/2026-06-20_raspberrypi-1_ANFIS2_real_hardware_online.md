# 太陽能追日系統 — raspberrypi-1 (ANFIS 2) 真實硬體上線報告

**日期**：2026-06-20
**地點**：raspberrypi-1 現場
**作業人**：鐘宇靖
**主要協作**：Claude (Cowork)

---

## 一、本日目標

「除了四方位 LDR 感測器之外,raspberrypi-1 ANFIS 2 系統所有硬體層都要上線真實運作」

具體要驗證的子系統:
1. MPPT 真實讀取(RS485 → EPEVER 充電控制器)
2. 雙軸推桿真實 GPIO 驅動
3. ANFIS 模型推論與決策邏輯
4. Dashboard 上傳鏈路

---

## 二、起點現況(上午)

- raspberrypi-1 上 `solar_tracking.service` 從 2026-06-12 啟動,持續執行 8 天
- `systemctl status` 顯示 `active (running)`、上傳 dashboard 正常
- 但 `'simulation_mode': True` —— **所有數據都是 `random.uniform()` 生成的假值**
- Dashboard 看似累積資料,實際是 sim 噪聲
- GitHub task tracker:**task #57「MPPT RS485 NoResponse」掛了 8 個月未解**

---

## 三、主要工作分塊

### 3.1 MPPT RS485 真實讀取上線(8 個月卡點解決)

**多層問題逐一拆解**:

| 層次 | 錯誤 | 修正 |
|---|---|---|
| 1. Port 路徑 | `test_mppt.py` 寫死 `/dev/serial0`(樹莓派 GPIO UART) | 改 `/dev/ttyUSB0`(USB-RS485 dongle, FTDI FT231X) |
| 2. RJ45 線色 | 藍/白綠/棕 接到 dongle A/B/GND,**藍跟白綠都接到 RS485-B**(dongle A 端沒接到 EPEVER A) | 從 EPEVER 官方手冊查實際腳位,改用 藍 (Pin 4=B) + 白藍 (Pin 5=A) + 棕 (Pin 8=GND) |
| 3. Baudrate | CONFIG 寫 9600,EPEVER Tracer-AN-G3 預設是 115200 | 改 115200 |
| 4. 函式實作 | `read_power()` 跟 `read_mppt_power()` **兩個都是 `raise NotImplementedError` stub** | 實作 EPEVER Modbus RTU 真實讀取,register 0x3100/0x3101/0x3102/0x3103 |

**EPEVER Tracer-AN-G3 RJ45 真實腳位**(從官方手冊):

```
Pin 1, 2 = +5VDC       (絕對不要接 — 會燒 dongle)
Pin 3, 4 = RS485-B
Pin 5, 6 = RS485-A
Pin 7, 8 = GND
```

**T568B 色碼對應**:
- Pin 4 (藍) = RS485-B → 接 dongle B
- Pin 5 (白藍) = RS485-A → 接 dongle A
- Pin 8 (棕) = GND → 接 dongle GND
- ⚠️ Pin 1 (白橙) / Pin 2 (橙) = +5V,**絕對不要碰**

**Sweep 結果**:`baud=115200 slave=1 V_raw=3500 V=35.00V` → 真實開路電壓 Voc

**最終驗證**:
```
[INFO] EPEVER MPPT 連線: /dev/ttyUSB0 baud=115200 slave=1
[INFO] MPPT 讀取: V=34.87V I=0.00A P=0.29W
```

---

### 3.2 推桿真實 GPIO 驅動(重大發現)

**Bug 發現**:`ActuatorController._move_to_tiptilt` 是個 stub:

```python
def _move_to_tiptilt(self, target_gamma, target_zeta):
    """TODO：根據霍爾感測器行程對照表..."""
    pass
```

過去 8 個月 log 一直印「移動 → β=29.8°」實際**完全沒打任何 GPIO 命令**,推桿從未真實動過。所有「移動成功」訊息只是更新內部 Python 變數。

**Pin 對應實測**(`test_actuator.py` 獨立打 GPIO):

| Pin Group (BCM) | dual_actuator 標籤 | **實測對應** | extend → | retract → |
|---|---|---|---|---|
| 17, 27, 22, 23 | `AZ_*`(錯) | NS / 傾角 / γ | 南 | 北 |
| 5, 6, 13, 19 | `TILT_*`(錯) | EW / 方位角 / ζ | 西 | 東 |

**`dual_actuator_upload.py` 把 AZ/TILT 命名反了**,直接照搬會方向錯亂。

**實作**(replace stub with real GPIO drive):

```python
def _move_to_tiptilt(self, target_gamma, target_zeta):
    cfg = CONFIG['actuator']
    d_gamma = (target_gamma - self.gamma) * cfg['ns_extend_dir']
    d_zeta  = (target_zeta  - self.zeta)  * cfg['ew_extend_dir']

    # NS / γ 軸
    if abs(d_gamma) > cfg['min_move_deg']:
        t = abs(d_gamma) * cfg['ns_sec_per_deg']
        action = 'extend' if d_gamma > 0 else 'retract'
        # 驅動 NS pin group(17/27/22/23)的 H 橋 t 秒
        self._drive_pins(ns_pins, action, t)
    # EW 同理...
```

**現場驗證**(身體確認):
- NS extend 2.65 秒 → 物理上面板真往南 ✓
- EW retract 14.14 秒 → 物理上面板真往東 ✓
- 時長公式正確:`Δ角度 × 0.5 s/°`(12.41° × 0.5 = 6.20s,實測一致)

---

### 3.3 4 方位 LDR 模組(實驗室端 raspberrypi-v4)

(這部分是 raspberrypi-v4 實驗室預備,raspberrypi-1 場域還沒接 LDR)

- 新檔 `ldr_module.py`:封裝 spidev + channel calibration + median 20 取樣
- 加 per-component simulation flag:`simulate_ldr` / `simulate_mppt` / `simulate_actuator`
  - 用途:「LDR 已接、MPPT 還沒接」之類的混搭情境
- Backend 加 4 方位欄位到 PowerRecord(`light_north/east/west/south`)+ Migration 0004
- ANFIS controller 上傳 payload 加 4 個方位獨立讀值

---

### 3.4 周邊發現

#### INA3221 I2C 失聯

- `i2cdetect -y 1` 完全看不到 chip(包括 0x40)
- INA3221 模組上的 VCC 量到 3.3V,有電
- 但 SMBus 讀 register 全部 `[Errno 110] Connection timed out`
- 影響:dashboard 上 `actuator_total_voltage` / `raspberry_pi_voltage` 等 6 個欄位 null
- **不影響核心追日**(MPPT 真讀、推桿真動、ANFIS 真推論都是獨立路徑)
- 延後處理:下次到場域帶 multimeter 量 SDA/SCL 線路

#### CONFIG misconfig:`api_url` 預設值寫錯

- Source 預設 `'http://localhost:8000/api'`(generic dev default)
- 部署到場域前要改成 Tailscale URL:`https://solar-dashboard.tail7c1eb9.ts.net/api`
- 一行 sed 修掉,上傳成功

---

## 四、⚠️ 關鍵硬體問題:24V 保險絲熔斷

### 現象

**接上第二個控制箱(對照組 / 另一追日系統)的 24V 接線後,24V 電力來源的保險絲立即燒斷。**

### 影響

- 單一控制箱目前可正常運作
- **無法擴展為兩個控制箱共用同一 24V 電源**
- 場域要部署「對照組 + 實驗組」兩個系統前,必須先解決

### 推測原因(待現場驗證)

| 可能原因 | 驗證方式 | 應對 |
|---|---|---|
| 兩控制箱電流總和超過保險絲額定 | 量測單一控制箱穩態電流 × 2 + 啟動 inrush peak | 換大一級保險絲(留 1.5x 安全裕度)|
| Inrush current 過大(電容充電瞬間)| 用 oscilloscope 或 clamp meter 量啟動瞬間 | 加 inrush limiter / soft-start 電路 |
| 第二個控制箱對地短路 | 接線前用 multimeter 量端子對機殼電阻 | 找到短路點修復 |
| Grounding loop | 量兩個控制箱接地電位差 | 拆成獨立 24V 電源 / 加隔離 |
| 接線極性反接 | 視覺檢查 + multimeter 確認 + - | 重接 |

### 建議下次到場域時的順序

1. 量單一控制箱穩態工作電流 → 確認當前保險絲額定是否合理
2. 將第二個控制箱拆離主電源,用獨立 24V 電源 + 隔離測試其穩態電流
3. 兩個控制箱在不接共用電源狀態下,各自獨立 power on,確認沒短路
4. 接共用電源前再做一次極性、電阻、grounding 三項檢查
5. 連接時用 clamp meter 同時監控電流,**有任何異常立刻拔線**

---

## 五、最終上線狀態

| 子系統 | 狀態 | 備註 |
|---|:---:|---|
| ANFIS 模型推論 | ✅ | 9 維特徵(時間 + 角度 + 照度)|
| MPPT 真實讀取(EPEVER RS485)| ✅ | task #57 8 個月卡點解了 |
| 推桿 GPIO 真實驅動(NS + EW)| ✅ | 開迴路時間驅動,方向實測正確 |
| Dashboard 上傳(Tailscale)| ✅ | 真實數據持續累積 |
| 4 方位 LDR | ⏸ | 還沒接,sim 中 |
| INA3221 輔助監測 | ⏸ | I2C timeout,核心追日不受影響 |
| **24V 並聯保險絲熔斷** | ❌ | **擴展為兩控制箱前必解** |

---

## 六、技術 Takeaway

### A. simulation_mode 的雙面刃
`simulation_mode=True` 讓系統「看似運作」很方便,但**會掩蓋根本問題長達數月**。8 個月來 dashboard 一直有數據,所有人以為系統 OK,實際 MPPT、推桿、INA3221 全部從未真實工作過。
**對策**:加 per-component sim flag,允許「部分元件 sim、部分元件真實」,逼迫每條真實路徑都有實測 KPI。

### B. Stub 函式 + 假 log 訊息 = 最危險的偽 OK
`_move_to_tiptilt` 函式內容是 `pass`,但外層 log 寫「移動 → β=29.8°」。看 log 完全察覺不出推桿沒動。
**對策**:code review 找這類「函式有訊息但無實作」的反模式;TODO 註解要加期限或 hard error。

### C. 命名 vs 實體不一致是 8 個月 bug 的源頭
`dual_actuator_upload.py` 把 AZ/TILT 命名反了,後續所有沿用者繼承錯誤標籤。**實測 > 文件描述**。
**對策**:硬體 commit 前必須有一份「實測對應表 + 拍照」存到 repo,後人不要靠猜。

### D. 電子線材腳位:看官方手冊不要猜
RS485 線色我先依「業界常識」猜了 Pin 4/5 = A/B(實際對),但對 Pin 7/8(我以為 +5V,實際 GND)猜錯。EPEVER 官方手冊一頁就解。
**對策**:接線前**先翻官方手冊**,5 分鐘 vs 燒 dongle 的 5 分鐘風險。

### E. 8 個月卡點往往是「組合層 bug」不是「單一 bug」
今天 MPPT 從卡到通,**累計動了 4 個地方**:port、線色、baudrate、函式實作。任何一個沒修都會 NoResponse。
**對策**:NoResponse 不要只看一層,從物理層(線)→ 鏈路層(port / baud)→ 應用層(register / 函式實作)一條條檢查。

---

## 七、後續工作清單

| Priority | 工作 | 何時 |
|:---:|---|---|
| 🔴 P0 | 解決 24V 並聯保險絲熔斷,場域才能擴兩控制箱 | 下次到場域 |
| 🟡 P1 | LDR 4 方位實體接線 → 切 `simulate_ldr=False` | 下次到場域 |
| 🟡 P1 | INA3221 I2C debug(0x40 失聯)| 下次到場域(帶 multimeter)|
| 🟢 P2 | sec_per_deg 校正(目前 0.5 估值)→ 真實量時間 / 行程 | 場域有空時 |
| 🟢 P2 | git commit + push 本輪改動 | 今晚 / 明天 |
| 🟢 P3 | 把 stub-detect 加進 CI 或 lint(防 `_move_to_tiptilt` 復發)| 有空 |

---

## 八、檔案異動清單(待 commit)

### 新增
- `raspberry-pi/src/controllers/ldr_module.py`(4 方位 LDR 讀取模組)
- `backend/dashboard/migrations/0004_powerrecord_light_east_and_more.py`
- `docs/daily-reports/2026-06-20_raspberrypi-1_ANFIS2_real_hardware_online.md`(本文件)

### 修改
- `raspberry-pi/src/controllers/anfis_controller.py`
  - Import `RPi.GPIO`
  - CONFIG 加 `'actuator'` 區(8 個 pin + 時長/方向/限制)
  - CONFIG 加 `'simulate_ldr/mppt/actuator'` per-component flag
  - CONFIG `'mppt': baudrate` 9600 → 115200
  - `read_mppt_power()`:`raise NotImplementedError` → 真實 EPEVER Modbus RTU 讀取
  - `SensorReader.read_power()`:`raise NotImplementedError` → 委派 `read_mppt_power()`
  - `ActuatorController._move_to_tiptilt()`:`pass` → 真實 GPIO 開迴路時間驅動
  - `ActuatorController.__init__()`:加 GPIO setup
  - 加 `_drive_pins()` H 橋驅動 helper
- `backend/dashboard/models.py`
  - PowerRecord 加 `light_north/east/west/south` 4 個 FloatField
- `build_pi_deploy.ps1`
  - 把 `ldr_module.py` 加到 deploy 複製清單

---

## 九、關鍵指令備忘

### EPEVER MPPT 接線(T568B 標準線)
```
藍 (Pin 4) → dongle B
白藍 (Pin 5) → dongle A
棕 (Pin 8) → dongle GND
其他 5 條:絕緣膠帶包好,Pin 1/2 +5V 絕對不要接
```

### 推桿 GPIO Pin 對應
```
NS / 傾角 / γ:BCM 17, 27, 22, 23(extend=南,retract=北)
EW / 方位角 / ζ:BCM 5, 6, 13, 19(extend=西,retract=東)
```

### CONFIG 旗標(raspberrypi-1 當前)
```python
'simulation_mode':   False,
'simulate_ldr':      True,    # 還沒接
'simulate_mppt':     None,    # 跟隨 master → False(真實)
'simulate_actuator': None,    # 跟隨 master → False(真實)
'mppt': {'port': '/dev/ttyUSB0', 'baudrate': 115200, 'slave': 1}
'api_url': 'https://solar-dashboard.tail7c1eb9.ts.net/api'
```

### 服務管理
```bash
sudo systemctl status solar_tracking.service
sudo systemctl restart solar_tracking.service
tail -f ~/solar_tracking/anfis_2/anfis_controller.log
```

---

**結語**:今天解了 8 個月的 task #57,實質意義是 raspberrypi-1 從「軟體模擬」進化到「真實硬體閉迴路」,真實實驗資料從這一刻才開始累積。論文資料蒐集週期從今天算起。
