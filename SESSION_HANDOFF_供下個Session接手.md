# Session Handoff — 給下個 Session 統整論文用

> **本檔用途**:整理本次 session 的所有進度,讓下一個 Claude session 能接手寫論文。
> **user 同時繼續在本 session 工作**,所以兩邊不衝突 — 這份是「截至目前的快照」。
>
> **時間範圍**:約 2026-06-04 ~ 2026-06-10(跨越兩天工作日 + 後續論文整理)
> **研究者**:鐘宇靖

---

## 0. 給下個 Session 的快速入口

下個 session 啟動後,**最先做的事**:

1. 讀本檔(這份就是地圖)
2. 讀關鍵記憶(順序如下,都在 `~/AppData/Roaming/Claude/.../memory/`):
   - `MEMORY.md`(總索引)
   - `user_profile.md`(user 是誰)
   - `feedback_coding_style.md`(回覆風格 — 繁中、PowerShell)
   - `feedback_figure_style.md`(ASME 完整圖表規範,2026-06-10 升級)
   - `feedback_quantify_visual.md`(教授要求視覺發現要數值佐證)
   - `project_solar_tracking_dashboard.md`(專案總覽)
   - `project_timeseg_study.md`(時間分段研究結論,**重要**:含真 ANFIS 大預算反轉結論)
   - `anfis_model_versions.md`(v2-v8 各版本)
   - `project_raspberry_pi_deployment.md`(4 台 Pi 對應)
3. 看本次 session 產出的 deliverable markdowns(下方第 6 節有索引)

---

## 1. 本 session 完成的工作(主題索引)

### 1.1 模型對照 — 時間分段 ANFIS 的「最終定論」

| 階段 | 結論 |
|---|---|
| 診斷(η²) | 全天 0.89% → 窗內 3.6%(提升 **~4×**) |
| 代理對照(HistGBM) | 分時段 +7.6pp(38.0% vs 30.4% Top-1)勝出 |
| **真 ANFIS 大預算**(user 本機 GPU 跑) | **單一 v5 33.4% 勝過分時段 29.9%(-3.6pp)** |
| **最終決定** | **部署用單一 v5**;時間分段定位為**診斷層方法**,不進部署 |

📁 完整研究報告:`完整研究報告_時間分段_資料清理_ANFIS驗證.md`

### 1.2 教授要求的量化邊際表

教授指示:「視覺發現必須用數值平均佐證」。已產出:

- **方位 × 小時 邊際平均**(早 160° / 中 180° / 午 200° 完全遷移)
- **傾角 × 小時 邊際平均**(15° 中午、10° 早晚 主導,20°/30° 全時段未領先)
- **分季 × 傾角 邊際平均**(春 10°、夏 30° 異常、秋 15°、冬 15°-30° 共享)
  - 加碼發現:**秋季發電量比其他三季高 30-50%**(199W vs 132-155W)
  - 加碼:**夏季 30° 中午勝出反物理**(誠實寫進限制章節)

📁 投影片素材:`PPT_熱力圖數值呈現_傾角.md`、`PPT_分季傾角熱力圖.md`
📁 圖檔:`algorithms/timeseg_tilt_heatmap.png`、`algorithms/seasonal_tilt_heatmap.png`
📁 數字表:`algorithms/seasonal_tilt_table.csv`
📁 產生腳本:`algorithms/tilt_heatmap.py`、`algorithms/seasonal_tilt_heatmap.py`

### 1.3 資料層深度清理

**POA 補救**(`recover_poa.py`):
- 發現原始前處理 row-by-row 迴圈漏掉 17 萬筆 POA 計算
- 重跑同一公式(dni=800/ghi=1000/dhi=200,isotropic 模型)向量化補回
- 一致性驗證 max|diff|=0.0000(新值完全對齊既有)
- v5 可用白天資料 230k → **298k(+30%)**

**面板 AB 配對清理**:
- A vs B 同 MPPT 同瞬間配對,差距 > 5% 判定單片異常
- 12 組中 2 組超標:**Panel_30_160_A**(-5.79%)、**Panel_30_200_A**(-6.64%)
- 剃除這兩片,共 70,329 列(原資料 7.2%)
- **結論修正**:原「30° 全時段最差」**部分是兩片異常 A 面板偽影**,清理後 30° 中午與 20° 相當

📁 報告:`面板AB配對清理與邊際量化分析.md`
📁 清理版資料:`data/combined_solar_data_20250301_20260406_processed_poa_recovered_panel_cleaned.csv`

### 1.4 MPPT 整體偏差診斷(發現但未處理)

- 12 顆 MPPT 之間有 **17% 的校正偏差**(MPPT_index 0.85 ~ 1.02)
- 最差:**10°/200°**(讀低 15%)、**30°/160°**(讀低 13%)
- 最好:**10°/180°**(讀高 2%)
- **結構性 confound**:每顆 MPPT 只服務一個角度組合,「MPPT 偏差」與「角度本身好壞」1:1 綁定,無獨立參考可作絕對校正
- **本次保留為下一階段工作**

### 1.5 文獻檢索(Deep Research,定錨 Top-1 評估框架)

**三層學術定錨**:

**理論基礎(IR / 排名)**:
- Cao et al. 2007 (ICML)「Learning to Rank: From Pairwise to Listwise」
- Liu 2009 (Foundations and Trends in IR) — LTR 教科書
- Burges 2010 (MSR) — LambdaMART 綜述

**跨域先例(再生能源)**:
- **Wen et al. 2025** (Scientific Reports, Nature, IF≈4)「Ranking-oriented ML for wind power forecasting」
- 原句:"Operators often care not about whether wind site A will generate 102 MW versus 105 MW, but **whether it will outperform site B, C, or D**"

**本研究位置**:
- 把 LTR 評估框架從 IR + 風能延伸到 **PV 太陽追日角度選擇**
- ANFIS-PV 文獻**首次明確採用 Top-K 評估**

📁 詳細報告:`文獻檢索_排名指標與LTR_for_PV_thesis.md`(含英文版方法論小節範文 + BibTeX)

### 1.6 樹莓派部署(2026-06-05 上線)

**部署狀態**(4 系統由右到左排列):

| 位置 | 角色 | system_id | Pi | systemd | 硬體狀態 |
|:---:|---|:---:|---|:---:|---|
| 右1 | 傳統 1 | 3 | raspberrypi-v2 | ❌ 未部署 | offline 48 天(未到場無法修) |
| 右2 | ANFIS 1 | 1 | raspberrypi-v4 | ❌ 未部署 | offline 2 hr(等下次到場) |
| 右3 | **傳統 2** | **4** | raspberrypi-v3 | ✅ **active** | 部分(LDR 未裝、MPPT 線材問題) |
| 右4 | **ANFIS 2** | **2** | raspberrypi-1 | ✅ **active** | 部分(LDR 未裝、MPPT 線材問題 + RS485 GND 錯接風險) |

**部署過程修補的 3 + 1 個 bug(已 backport 到源碼 + push GitHub)**:

1. payload 漏 `system` 欄位(Django 必填) → 從 `system_id` 改 `system`
2. 模型路徑 `.parent.parent.parent` 跑到家目錄 → 改 `.parent`
3. Keras 3 找不到 `SimpleFuzzyLayer` → 新增 `anfis_layer.py` + `custom_objects`
4. (+ requirements 漏 scikit-learn → 已補)

📁 部署日誌:`2026-06-05_部署工作日誌與TODO.md`

### 1.7 GitHub Push(2026-06-05 完成)

- 14 個檔案 push 到 `origin/main`
- 含:時間分段研究檔、POA 補救、分時段 ANFIS、Pi 源碼 bug 修補、anfis_layer.py 新檔、build_pi_deploy.ps1 修補
- Commit: "feat(deploy+research): 時間分段分析定錨 + ANFIS Pi 部署 bug 修補"

### 1.8 ASME 圖表規範定錨(2026-06-10)

**完整 ASME 規範**(配 user 偏好的「Latin 斜 / Greek 正」方案 B):

- Times New Roman(Linux fallback Liberation Serif)
- 600 dpi、雙欄寬 6.5" / 單欄 3.25"
- 線寬 0.5-1.5pt(`axes.linewidth=0.8, lines.linewidth=1.2`)
- 無格線、無 legend 框
- 配色 viridis / plasma(避免 jet rainbow)
- 軸標籤格式 `Quantity name, Symbol (unit)`,Latin 用 `$G$` 斜體,Greek 用 unicode `β` 正體

📁 完整規範:`ASME圖表規範_完整版.md`(可手動建成 Skill)
📁 記憶已升級:`feedback_figure_style.md`

### 1.9 MPPT RS485 通訊除錯(進行中 ⚠)

**狀態**:
- raspberrypi-1 (ANFIS 2):dongle 不能用,USB 線疑似充電線、GND 可能誤接到 MPPT 5V pin → **back-feed Pi 風險,需現場修**
- raspberrypi-v3 (傳統 2):CH340 dongle 認到了,但**全部 baud/slave 掃描都 NoResponse**
- **8 成嫌疑:LEOREK 板的 RS232/RS485 模式開關設在 232**(無法遠端確認)

**已知 EPEVER Tracer-AN-G3 規格**:
- Modbus RTU, baudrate 115200, 8N1, slave 1
- Register 0x3100 = V×100, 0x3101 = I×100, 0x3102-3 = P 32-bit ×100
- RJ45 pinout: pin 3=B-(綠白)/ pin 5=A+(藍白)/ pin 7=GND(棕白)
- ⚠ Pin 1/2 是 +5V 輸出 給 MT-50 用,dongle **千萬不能接**

📁 通訊狀況:待下次到場才能繼續

---

## 2. 兩台 Pi 的軟體層完整狀態

### 2.1 raspberrypi-1(ANFIS 2,system_id=2)

- SSH 用戶:`rte`,密碼存對話內(不寫進記憶 / 不寫進 deliverable)
- 工作目錄:`/home/rte/solar_tracking/anfis_2/`
- Python:venv 內 Python 3.13.5 + TF 2.21 + sklearn + minimalmodbus + lgpio
- 控制器:`anfis_controller.py`(已修 3 bug)+ `anfis_layer.py`(新檔)
- systemd:`solar_tracking.service` enabled + active running
- log:`/home/rte/solar_tracking/anfis_2/service.log`
- 上傳:每 10 分鐘一次 simulation 資料到 dashboard
- ⚠ 風險:RS485 GND 可能誤接 5V pin,長時間運作會燒 EPEVER 5V LDO

### 2.2 raspberrypi-v3(傳統 2,system_id=4)

- SSH 用戶:`raspberrypi`
- 工作目錄:`/home/raspberrypi/solar_tracking/traditional_2/`
- Python:venv 內(無 TF)+ minimalmodbus(剛裝為了測 MPPT)
- 控制器:`traditional_controller.py`(LDR 差值法,已修 system 欄位)
- systemd:active running
- log:`/home/raspberrypi/solar_tracking/traditional_2/service.log`

### 2.3 Dashboard

- URL:`https://solar-dashboard.tail7c1eb9.ts.net/dashboard/`
- 預期持續看到 system_id=2 和 system_id=4 每 10 分鐘新時間戳

---

## 3. 硬體現況 + 待補(現場 TODO)

### 緊急(避免燒晶片)
- raspberrypi-1 的 dongle GND 線從 MPPT pin 1/2 改接到 pin 7(棕白)
- 確認 12V→24V 升壓器規格(目前在 voltage foldback,24V 變 16V)

### 必備工具(下次到場帶)
- 萬用表(測 RS485 pin + 5V rail)
- 可傳資料的 USB-A 線(現在那條疑似充電線)
- 原廠 Pi 5V/3A USB-C 電源
- 照度計(LDR 校正,可選)

### 場域任務優先序
1. raspberrypi-1 RS485 GND 改接
2. LEOREK 模式開關確認設在 RS485
3. 升壓器升級
4. LDR 實體安裝 + 校正
5. raspberrypi-v4 / v2 上線
6. 推桿真實 GPIO 驅動 + 測試

### 程式碼 TODO(可遠端)
- 寫真實 MPPT RS485 讀取函式(register、baudrate、slave 都已知)
- 寫真實推桿 GPIO 驅動(整合 dual_actuator.py 的 H-bridge 邏輯)
- 加 `simulate_ldr` 旗標(LDR 假、其他真混合模式)

---

## 4. 給下個 Session 寫論文的整合建議

### 4.1 已備齊的章節素材

**Methods / 評估指標(完整)**:
- `文獻檢索_排名指標與LTR_for_PV_thesis.md` — 有英文方法論小節範文 + BibTeX
- Top-1 vs R² 的論述完備
- 文獻 chain:Cao 2007 → Liu 2009 → Wen 2025 → 你的研究

**Methods / 資料前處理(完整)**:
- POA 補救方法(`recover_poa.py` 註解詳細)
- 面板 AB 配對清理(`面板AB配對清理與邊際量化分析.md` 完整)
- 5% 閾值的選擇理由可直接引用

**Results / 時間分段(完整,但結論需誠實)**:
- η² 4× 提升的數字
- 最佳角度遷移圖(物理正確)
- 邊際平均表(方位 + 傾角 + 分季)
- **重要**:**真 ANFIS 大預算下單一 v5 勝出**,要誠實寫進結果,不能只說代理實驗

**Discussion / 限制(必寫)**:
- per-range R² 仍為負(v5 hybrid POA 根本性限制)
- MPPT 整體 17% 校正未處理
- 夏季 30° 中午勝出是反物理異常(待解釋)
- 真 ANFIS 大預算下分時段對 ANFIS 沒有額外收益的反轉

### 4.2 建議論文章節順序(初稿)

1. Introduction(背景 + 太陽追日問題 + ANFIS 動機)
2. Related Work(LTR 文獻 + ANFIS-PV 文獻 + 跨域先例 Wen 2025)
3. **Methods**:
   - 3.1 系統與資料採集(場域 + 12 角度組合)
   - 3.2 ANFIS 模型架構(v5 hybrid POA)
   - 3.3 評估指標(**Top-1 為主、R² 輔**,用文獻 chain 支撐)
   - 3.4 資料前處理(POA 補救、面板清理)
   - 3.5 時間分段診斷方法(η² + 邊際平均)
4. **Results**:
   - 4.1 角度可分性提升(時間分段 η² 4×)
   - 4.2 最佳角度物理遷移(熱力圖 + 邊際表)
   - 4.3 分季差異(秋季發電量最高 + 傾角季節依賴)
   - 4.4 真 ANFIS 對照(單一 v5 vs 分時段,Top-1 33.4% vs 29.9%)
5. **Discussion / 限制**:
   - per-range R² 為負的原因
   - MPPT 17% 偏差未校正
   - 夏季 30° 反物理異常的可能解釋
   - 分時段對 ANFIS 沒額外收益的機制(容量已足以隱式建模)
6. Conclusion(部署採用單一 v5、時間分段為診斷層方法)

---

## 5. 鐵則(避免下個 session 踩過去的坑)

1. **R² 不是部署目標,Top-1 是** — 不要因為 v2 R²=0.84 比 v5 R²=0.70 高就建議退回 v2
2. **per-range R² 為負是 v5 已知限制**,不要重新震驚
3. **分時段 ANFIS 不會贏單一 v5**(真模型驗證過兩次),不要再嘗試
4. **挑「最佳角度」用 power_W 排名,絕不用 PR_norm**(PR 已除掉角度幾何)
5. **熱力圖視覺發現必須用邊際平均表佐證**(教授要求)
6. **圖表用 ASME 規範**(Times New Roman、600 dpi、Latin 斜 / Greek 正)
7. **修硬體前先看是不是程式碼問題,反之亦然** — 兩次都有混淆過
8. **中文資料夾名在 PowerShell SCP 會被截斷** — 部署用英文名

---

## 6. 所有 Deliverable Markdown 索引

全部在 `C:\Users\user\Documents\Claude\Projects\太陽能追日系統的演算法優化\`:

### 研究核心
- `完整研究報告_時間分段_資料清理_ANFIS驗證.md` — 主報告(10 章節)
- `時間分段分析_模型優化摘要.md` — 簡報用
- `時間分段分析_名詞解釋.md` — 詞彙表
- `面板AB配對清理與邊際量化分析.md` — 面板清理完整
- `文獻檢索_排名指標與LTR_for_PV_thesis.md` — Top-1 文獻支撐(含英文範文 + BibTeX)
- `2026-06-04_05_兩天工作整理_供PPT.md` — 完整 20 張投影片素材
- `PPT_13_19_硬體部署與現況.md` — 部署/硬體 7 張投影片
- `PPT_熱力圖數值呈現_傾角.md` — 傾角熱力圖投影片
- `PPT_分季傾角熱力圖.md` — 分季傾角投影片

### 技術規範
- `ASME圖表規範_完整版.md` — 圖表規範(可手動建成 Skill)

### 部署
- `2026-06-05_部署工作日誌與TODO.md` — 部署細節

### 本檔(handoff)
- `SESSION_HANDOFF_供下個Session接手.md` ← **這份**

---

## 7. 程式碼產出(在 git repo `D:\宇靖\solar-tracking-dashboard\`)

### algorithms/
- `timeseg_diagnostic.py` — η² 診斷
- `timeseg_model_compare.py` — HistGBM 代理對照
- `solar_anfis_timeseg.py` — 分時段 ANFIS 模組
- `recover_poa.py` — POA 補救
- `tilt_heatmap.py` — 單時段傾角熱力圖
- `seasonal_tilt_heatmap.py` — 分季傾角熱力圖
- `solar_anfis_model_v5.py` — 加了 `evaluate_ranking_mode_a_by_timeseg`

### raspberry-pi/
- `src/controllers/anfis_controller.py` — 3 個 bug 修補(已 push)
- `src/controllers/traditional_controller.py` — system 欄位 bug 修(已 push)
- `src/controllers/anfis_layer.py` — 新檔(已 push)
- `INTEGRATION_STATUS.md`

### 根目錄
- `build_pi_deploy.ps1` — 更新(已 push)

---

## 8. 進行中 / 未完任務

- `#49` 硬體 TODO(現場補完才能切 production)
- `#57` 除錯 MPPT RS485 通訊(NoResponse)— **8 成是 LEOREK 模式開關,需現場確認**

---

## 9. 給下個 Session 的開場白建議

> 「請先讀 `SESSION_HANDOFF_供下個Session接手.md` 跟記憶,然後我們開始整合論文章節。」

下個 session 收到這句話 + 本檔,加上記憶,**完整脈絡就 100% 接上**,不會重踩坑、不會問已經回答過的問題。

---

## 結語

本 session 從**研究層定錨**(時間分段定論、文獻支撐、量化邊際表)推到**實機部署**(2 台 Pi systemd 上線)再延伸到**圖表規範升級**(ASME),工作密度高。下個 session 接論文整合,**所有素材都在 `太陽能追日系統的演算法優化/` 與 git repo 內**,憑這份 handoff + 記憶就能完整還原情境。

**你繼續在本 session 工作 OK,因為本檔已凍結快照,新進度只是在這份基礎上往前加,不會回頭推翻。**
