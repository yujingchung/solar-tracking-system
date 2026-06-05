# 控制器整合狀態（INTEGRATION_STATUS）

> 最後更新：2026-05（本檔記錄 deploy 與 src 兩套控制器架構的分工，避免混淆）

## TL;DR

- **deploy/ = 生產版（V2）**：要上樹莓派的就是這套，已就緒、可部署。
- **src/ = 研究版（v5，開發中）**：下一階段升級用，模組已寫好但**尚未整合成完整控制器、未上機測試**。
- **目前策略**：先用 deploy/ 的 V2 系統上 Pi 收資料 → 等基本系統在硬體上跑穩 → 再把 src/ 的 v5 整合進來升級。

---

## 一、兩套架構的分工

### deploy/solar_tracking/（生產版 V2）— 要上 Pi 的

| 資料夾 | system_id | 控制器 | 模型 |
|---|---|---|---|
| 實驗組1 | 1 | anfis_controller.py（V2 單檔）| models/anfis_with_illumination.keras（V2）|
| 實驗組2 | 2 | anfis_controller.py（V2 單檔）| models/（V2）|
| 對照組1 | 3 | traditional_controller.py | 無（LDR 差值法）|
| 對照組2 | 4 | traditional_controller.py | 無 |

特性：
- ANFIS 模型 = **V2**（9 維特徵含 illumination，target = power_W）
- 控制器 = 單檔 monolithic，內含 grid search + 簡單 _is_worth_moving（gain > 2W）+ 模糊微調
- 依賴：TensorFlow（實驗組）；對照組無需 TF
- config.json 為記錄用，實際設定在各 .py 的 CONFIG dict
- **狀態：完整可跑，README 有 7 步驟部署流程**

### src/（研究版 v5）— 下一階段升級

| 檔案 | 角色 | 狀態 |
|---|---|---|
| controllers/anfis_controller.py | V2-style 開發版（system_id 7）| 舊版，與 deploy 的 V2 邏輯相同 |
| **controllers/anfis_inference.py** | **v5 推論模組**（POA + ANFIS 殘差 + 候選角度選最佳）| ✅ 已寫、單元測試過，**未整合進控制器** |
| **controllers/decision_layer.py** | **Cost-benefit 決策層**（移動能耗 vs 增益）| ✅ 已寫、單元測試過，**未整合** |
| **hardware/dual_actuator.py** | **雙軸推桿硬體模組**（從 test_actuator.py 抽出）| ✅ 已寫，**未上機測試** |

特性：
- ANFIS 模型 = **v5**（hybrid POA prior，target = PR_norm = power / (POA × area × η)）
- 架構 = 模組化（inference / decision / hardware 分離）
- 依賴：TensorFlow + **pvlib**（Pi 上要額外裝）
- 模型表現：選錯時功率損失比 V2/純物理砍半（14.7W → 7.9W）

---

## 二、為什麼先 V2 後 v5

1. **deploy V2 已就緒**：部署流程、config、模型檔都齊，風險低
2. **v5 未上機測試**：模組各自測過，但沒串成完整控制器、沒在 Pi 上跑過
3. **v5 多一個 pvlib 依賴**：Pi 上要多裝、多一個出錯點
4. **先讓實驗系統跑起來收資料最重要**：4 台 Pi + 24 片固定面板的完整資料流，比模型微優先

> 核心邏輯：先求「系統能跑、能收資料」，再求「模型更聰明」。

---

## 三、v5 整合待辦（未來升級時要做的事）

當 V2 系統在 Pi 上跑穩、要升級到 v5 時，依序做：

1. **整合 src 模組進控制器**
   - anfis_controller.py 的舊 ANFISModel 類別 → 換成 anfis_inference.AnfisInference
   - _grid_search_best_angle → 改用 inference.predict_best_angle（batch 推論，更快）
   - _is_worth_moving → 換成 decision_layer.MovementDecisionLayer
   - 推桿 stub（_drive_ew/_drive_ns/_move_to_tiptilt）→ 接 hardware.dual_actuator.DualAxisActuator

2. **部署 v5 模型檔**
   - 把 algorithms/runs/runXX_v5/ 的 anfis_v5.keras + scaler_X_v5.save + model_config_v5.json 複製到 deploy/*/models/

3. **Pi 環境加 pvlib**
   - requirements.txt 加 `pvlib`

4. **同步到 4 個部署資料夾**
   - 改完 src 後，同步到 deploy/實驗組1,2（system_id 1,2）

---

## 四、整合前已知待釐清問題（檢視時發現）

| # | 問題 | 嚴重度 | 備註 |
|---|---|---|---|
| 1 | LDR 四方向平均當 GHI 餵模型 | 中 | v5 訓練用獨立 GHI 計，推論用 LDR 平均，有系統性偏差。已確認：訓練用 GHI、推論用 LDR 平均 |
| 2 | 場域座標 | 低 | system_config.json 寫新竹(24.81/120.97)，但實際在新北先鋒(25.10/121.43)。v5 inference 已用正確的 25.10/121.43 |
| 3 | 搜尋角度範圍 | 中 | 訓練 tilt 10-30/azi 160-200；雙軸推桿物理範圍是東西±30°、南北±30°（tip-tilt 座標）|
| 4 | systematic_error baseline | 中 | 舊控制器用移動前功率當 baseline（錯）；整合時改為「該角度的預測 vs 實際」|
| 5 | __init__.py 編碼 | 已修 | 原為 UTF-16，已全部轉 UTF-8（否則 Python 無法 import src 模組）|

---

## 五、檔案位置速查

```
raspberry-pi/
├── deploy/solar_tracking/          ← 生產版 V2（上 Pi 的）
│   ├── 實驗組1/  (system_id 1, V2 ANFIS)
│   ├── 實驗組2/  (system_id 2, V2 ANFIS)
│   ├── 對照組1/  (system_id 3, LDR)
│   └── 對照組2/  (system_id 4, LDR)
├── src/
│   ├── controllers/
│   │   ├── anfis_controller.py     ← V2-style 開發版
│   │   ├── anfis_inference.py      ← ★ v5 推論模組（下一階段）
│   │   └── decision_layer.py       ← ★ v5 決策層（下一階段）
│   ├── hardware/
│   │   └── dual_actuator.py        ← ★ 推桿硬體模組（下一階段）
│   └── test_actuator.py            ← 手動鍵盤測試工具（推桿實際可動）
└── INTEGRATION_STATUS.md           ← 本檔

algorithms/
├── solar_anfis_model_v5.py         ← v5 訓練（hybrid POA，含分時段評估）
├── solar_anfis_model_v6.py         ← v6（加幾何特徵，已知無顯著改善）
└── solar_anfis_model_v8.py         ← v8（panel-aware，已知退步）
```

★ = 本輪新增、屬於 v5 升級、尚未整合進生產部署
