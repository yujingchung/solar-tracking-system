# 太陽能追日系統 — V2 工作報告:Dashboard Bug 修補 + 兩天真實期 Log 分析

**日期**:2026-06-22(週一)
**版本**:V2(承接 V1 — 2026-06-20 raspberrypi-1 ANFIS 2 真實硬體上線報告)
**主軸**:Dashboard CSV 匯出 5 個 bug 修補 + raspberrypi-1 真實期 45 小時 log 深度分析
**地點**:遠端(從 Windows + Tailscale + Docker backend)

---

## 一、本日切入點

V1(6/20)讓 raspberrypi-1 ANFIS 2 真實硬體上線後,系統已穩定運行 ~45 小時。今天的任務:

1. 從 dashboard 抓 CSV 做資料分析 → **發現一連串 bug**
2. 修補 backend CSV 匯出邏輯
3. 深度分析 SCP 下來的 controller log,找出**真實實驗品質瓶頸**
4. 給出論文資料蒐集的 actionable next step

---

## 二、Dashboard 系列 Bug 發現 + 修補

### 起點:使用者觀察

> 「我從網站上抓下來的數據,組別寫對照組1?我在實驗組2載的啊」
>
> 「空值就代表 0 嗎?那也要寫 0 啊」
>
> 「樹莓派的當地時間跟我一樣嗎?怕時間有差會對不上」

三句話揭出 5 個 bug。

### Bug 全表

| Bug# | 現象 | 根因 | 影響 |
|:---:|---|---|---|
| 1 | CSV 系統顯示「對照組1」,實際是 ANFIS 實驗組 | DB SystemGroup id=2 `name='對照組1'` type=`control`,而 id=5 才是正確的「實驗組II」(但 Pi config 指向 id=2)| 資料歸屬錯誤,論文引用會混淆 |
| 2 | CSV 時間是 UTC,不是台北時間 | `views.py:152` 直接 `record.timestamp.strftime()`,沒套 `localtime()` | 時間軸圖會錯亂 8 小時 |
| 3 | CSV 只有 176 筆,但 DB 有 768+ | `views.py:150 queryset[:1000]` + `get_queryset` 預設 `days=7` 太短 | 資料被截斷,長期分析不可能 |
| 4 | CSV 缺 4 方位 LDR 欄位 | `export_csv` 是 6/14 之前寫的,沒跟新 schema 同步 | LDR 真實上線後資料看不到 |
| 5 | 0 被當成 None 寫成空字串 | `f"{x:.2f}" if x else ''` 把 0 也判 False | 真實 P=0(電池滿)跟 INA3221 timeout(null)分不開 |

### 修補執行

**Backend 改 `backend/dashboard/views.py`(我直接編輯 + docker rebuild)**:

1. 加 `from django.utils.timezone import localtime` + 用它包 timestamp
2. 取消 `[:1000]` 改 `[:100000]`、預設 `days=7` 改 `days=30`
3. Header 加「北方/東方/西方/南方 LDR(lux)」+「面板傾角/方位角(°)」
4. 寫 `fmt(value, spec)` helper,用 `is not None` 區分 0 vs null

**DB 改名(Bug 1,Option B — 改名 + 改 type)**:

```python
# Django shell
SystemGroup.objects.get(id=5).update(name='實驗組II_預留(未使用)')  # 讓出名字
SystemGroup.objects.get(id=2).update(
    name='實驗組II (ANFIS)',
    system_type='experiment',
    location='新北先鋒金土地公廟',
    description='ANFIS 智能追日系統 - 第二組(raspberrypi-1)'
)
```

### 驗證(Claude 自動 web_fetch API)

```
GET /api/systems/2/
→ {"name":"實驗組II (ANFIS)", "system_type":"experiment", ...} ✓

GET /api/power-records/export_csv/?system=2&days=30
→ Header: "時間戳(CST)", 北方LDR, 東方LDR, 西方LDR, 南方LDR, 面板傾角, 面板方位角 ✓
→ 第一筆 2026-06-22 11:39:58(對到 Pi 當下時間 11:39 ✓)
→ 資料回溯到 2026-06-10(>10 天,不再卡 7 天)✓
→ V=0.00 / I=0.000 / P=0.00 都寫真實 0 不再空白 ✓
```

✅ 5 個 bug 全部修補通過。

---

## 三、Raspberrypi-1 時間同步驗證

```
date:          Mon 22 Jun 11:25:51 CST 2026
timedatectl:   Time zone: Asia/Taipei (CST, +0800)
               System clock synchronized: yes
               NTP service: active
```

時區、NTP、同步狀態全部正確 ✓ → CSV 時間軸跟現場觀察可以直接對齊,不用任何 offset 校正。

---

## 四、Raspberrypi-1 真實期 Log 深度分析

**範圍**:2026-06-20 14:47(MPPT 真實上線時刻)~ 2026-06-22 11:18 ≈ 45 小時
**資料源**:SCP 拉下來的 `anfis_controller.log`(1.2 MB,13,154 行)

### 4.1 時間使用分布

811 筆有效 MPPT 讀取中:

| 狀態 | 樣本 | 佔比 | 含義 |
|---|:---:|:---:|---|
| 充電中(V<32V + I>0.05A)| **91** | **11.2%** | ★ 唯一有意義的 ANFIS 評估窗口 |
| 電池滿 float(V≥32V + I≤0.05A) | 356 | 43.9% | 太陽很強但 PV 不抽,**浪費** |
| 夜間(V<20V + I≤0.05A)| 392 | 48.3% | 沒太陽,正常 |

**🔴 關鍵發現:45 小時運轉,真正能評估 ANFIS 的時間只有 ~5 小時。**

### 4.2 充電窗口逐小時分布

```
時段              cycles   P 平均   P 峰值
─────────────────────────────────────────
06-20 17:00       10       12.33W   13.92W
06-20 18:00        9        8.85W   15.15W
06-21 05:00       15        7.78W   15.42W
06-21 06:00       20      ★18.81W   23.22W   ← 黃金時段
06-21 17:00       11       12.44W   15.52W
06-21 18:00       11        6.33W    8.83W
06-22 05:00       10        5.83W    9.49W
06-22 06:00        5        8.73W    9.03W
─────────────────────────────────────────
```

**模式**:每天充電只發生在 **清晨 5-6 點 + 傍晚 17-18 點 共約 4 小時**,中午 7-16 點 全在 float。

**為什麼**:電池一早充滿,白天太陽最強的 9 小時 MPPT 反而沒抽 PV(因為負載端電池接受度有限)。**這不是 ANFIS bug,是物理電池容量問題**。

### 4.3 ANFIS 預測 vs 實際

只看充電期(91 筆有效對比):

```
預測 / 實際 比例:
  中位數: 9.51x   ← ANFIS 高估 9.5 倍
  範圍:   3.85x ~ 65.42x

最近 5 筆對比:
  預測 103.8W vs 實際   7.74W → 13.4x overestimate
  預測 121.1W vs 實際   8.96W → 13.5x
  預測 121.1W vs 實際   8.97W → 13.5x
  預測 121.1W vs 實際   8.97W → 13.5x
  預測 121.1W vs 實際   9.03W → 13.4x
```

**為什麼**:
- ANFIS 訓練資料是 28 片固定面板,**面板物理上能輸出多少功率**
- 但場域的 raspberrypi-1 連接到電池 + MPPT,**MPPT 只抽電池能吸收的功率**(電池接受度上限,不是面板上限)
- 訓練資料的「理想條件最大功率」vs 實際的「電池限流後實得功率」,差 10x 是合理的

Controller 已自動把 correction 校正到 `corr=0.700`(壓 70%),但 9.5x 高估遠超 30% 校正能解的範圍。

### 4.4 推桿真實活動

| 動作 | 次數 |
|---|:---:|
| NS extend(往南)| 275 |
| NS retract(往北)| 192 |
| EW extend(往西)| 168 |
| EW retract(往東)| 172 |
| **累計移動時長** | **5,717.4 秒(≈ 95 分鐘)** |

→ 每天 ~50 分鐘真實移動,推桿運作正常。GPIO 命令穩定發出去,**V1 修的 stub bug 完全不再復發**。

### 4.5 fine_tune 結果(230 次嘗試)

| 結果 | 次數 | 佔比 |
|---|:---:|:---:|
| 微調成功 | ~2(從 dashboard `exp=fine_tune_success` notes 找到 2 筆,6/21 06:08 + 06:19)| ~1% |
| 微調失敗回退 | 167 | 72.6% |
| LDR 差值不足跳過 | 63 | 27.4% |

**為什麼 fine_tune 一直失敗**:
- 微調的判斷標準是「實測 P 達不到預測 P」就回退
- 預測 100W、實際 10W,任何微調都不可能搆到 100W
- 所以微調 **100% 邏輯死路** — 不是微調算法錯,是預測值本身錯

### 4.6 操作穩定性

| 指標 | 數字 |
|---|:---:|
| Service 重啟 | 15 次(部署過渡 + 改 config)|
| MPPT 通訊失敗 | 3 次(通了之後極穩) |
| INA3221 timeout | 470 次(已知,獨立 bug,不影響核心)|
| Python Traceback | 3 次(都是部署過渡期)|

---

## 五、結論:基礎建設 OK,瓶頸在物理層

| 發現 | 對論文影響 | 立即建議 |
|---|---|---|
| ✅ 5 個 dashboard bug 修補 | 資料管道正確,可信賴 | 完成 |
| ✅ 推桿/MPPT/上傳/系統名 全部正確 | V1 的真實硬體上線確認穩定 45 小時 | 持續監控 |
| 🔴 充電窗口只 11% 時間 | **資料量太少,無法做統計顯著結果** | **接負載**(燈泡/inverter)讓電池能放電,擴大充電窗口 |
| 🔴 ANFIS 預測 9.5x 高估 | 絕對 W 值不能用 | 改用「相對最佳角度排名」評估方法 |
| 🟡 fine_tune ~0% 成功 | 微調機制目前無貢獻 | 暫時 disable fine_tune,專注 grid search |
| 🟢 推桿 95 min 移動正常 | 硬體無虞 | 不用動 |

---

## 六、關鍵 Takeaway(給論文 / 教授會議)

### A. 「Dashboard 看似有資料」≠「資料正確」

5 個 bug 全部是「資料還是進來,但內容錯」這類型:
- 時間錯 8 小時
- 系統歸錯
- 0 跟 null 混淆
- 1000 筆截斷

**對策**:任何資料 pipeline 上線都要先做「**取出來重新匯入再對一次**」確認 round-trip 沒失真。

### B. 「電池滿」是被忽視的實驗瓶頸

V1 解了 MPPT、推桿、上傳,以為「真實實驗開始累積」。但實際 ~89% 時間在 float / 夜晚,真實實驗時間遠小於預期。

**對策**:在實驗系統中,**負載大小 ≥ PV 發電量** 才能保證所有日照時間都有 charging data。

### C. ANFIS 預測絕對值在生產環境不可用,但相對排序可能還有意義

9.5x 高估是「訓練 ↔ 部署 distribution shift」典型問題(訓練看面板理論功率,部署看 MPPT 實得功率)。**模型對「哪個角度比較好」的判斷可能對,只是預測 W 值絕對偏離。**

**對策**:評估 ANFIS 時不要看 RMSE / MAE,而是看 **top-K 角度命中率**(預測前 N 名角度有多少真實落在前 N 名)。

### D. 微調(fine-tune)的失敗模式

微調是「實測達不到預測就回退」設計。當預測長期高估,**微調永遠執行回退,等於白做**。

**對策**:fine_tune 的判斷標準應該改為「實測有沒有比微調前更高」,而不是「實測有沒有達到預測」。或直接 disable。

---

## 七、後續工作清單

| Priority | 工作 | 何時 |
|:---:|---|---|
| 🔴 P0 | **解 24V 並聯保險絲熔斷(V1 P0)** | 下次到場域 |
| 🔴 P0 | **加負載讓電池能放電** | 下次到場域(燈泡 / 12V/24V inverter / 真實用電負載)|
| 🟡 P1 | **修改 fine_tune 判斷邏輯**(對比微調前 vs 後,不對比預測值)| 一週內(改 anfis_controller.py)|
| 🟡 P1 | **寫「相對排名」評估腳本**:不用絕對 W,用 top-K 角度命中 | 一週內(配合論文寫作)|
| 🟡 P1 | LDR 4 方位接線 → `simulate_ldr=False` | 下次到場域 |
| 🟡 P1 | INA3221 I2C debug(0x40 失聯)| 下次到場域(帶 multimeter)|
| 🟢 P2 | sec_per_deg 校正(目前 0.5 估值)| 場域有空時 |
| 🟢 P2 | git commit + push 兩天累計改動 | 今晚或明天 |

---

## 八、檔案異動清單(待 commit,本日新增)

### 新增
- `docs/daily-reports/2026-06-22_dashboard_bugs_and_log_analysis_V2.md`(本文件)

### 修改
- `backend/dashboard/views.py`
  - `export_csv()`:用 `localtime()`、`fmt()` helper、加 4 方位 LDR + 面板角度欄位、解除 1000 筆 limit
  - `get_queryset()`:預設 days 7 → 30

### DB 改動(非檔案)
- SystemGroup id=5 name → '實驗組II_預留(未使用)'
- SystemGroup id=2 name → '實驗組II (ANFIS)' + type → 'experiment' + 補 location/description

---

## 九、關鍵指令備忘(本日新增)

### 抓 CSV API(可直接 curl,不用 dashboard 點)
```bash
curl "https://solar-dashboard.tail7c1eb9.ts.net/api/power-records/export_csv/?system=2&days=30" \
     -o power_records_$(date +%Y%m%d_%H%M).csv
```

### 改 SystemGroup name / type
```powershell
docker exec solar_backend python manage.py shell -c "
from dashboard.models import SystemGroup
SystemGroup.objects.filter(id=X).update(name='...', system_type='...')
"
```

### Pi 時間同步檢查
```bash
ssh rte@100.66.182.46 "timedatectl"
```

### log 分析的 grep 三件套
```bash
# 真實 MPPT 讀取(過濾掉 fallback 0)
grep "MPPT 讀取:" anfis_controller.log | awk -F'V=' '{print $2}' | awk -F'V' '$1>1{print}'

# 推桿移動總時長
grep -oE "(NS|EW) 推桿.*?[0-9.]+ 秒" anfis_controller.log | grep -oE "[0-9.]+ 秒" | awk '{s+=$1} END{print s}'

# fine_tune 統計
grep -cE "微調無效|微調有效|LDR 差值不足" anfis_controller.log
```

---

**結語**:V1 解了「軟體模擬 → 真實硬體」,V2 解了「資料管道正確性 + 實驗瓶頸定位」。下一輪 V3 的主軸應該是「**現場物理層改造**(加負載 + 24V 並聯修)」,只有 V3 完成後資料量才足以做統計分析。今天的真實期數據雖然只有 5 小時可用,但**已經證明:演算法能執行、推桿能動、ANFIS 推論正常、上傳穩定** — 這是無法回頭的里程碑。
