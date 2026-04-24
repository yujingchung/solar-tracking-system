# 座標系轉換工具

## 角色

把**固定式太陽能板**描述方式 `(β 傾角, φ 方位角)` 與**追日式系統**實際驅動量 `(γ 南北向傾角, ζ 東西向傾角)` 之間的對應關係建立起來。這是 ANFIS 訓練資料準備的關鍵前處理。

```
  固定式資料 (β, φ)          追日式控制 (γ, ζ)
  ─── β=傾角 ────┐         ┌─── γ=南北向傾角 (+北, -南)
  └── φ=方位角 ──┤ ⇄ ⇄ ⇄ ──┤
                 │ 座標轉換  │──── ζ=東西向傾角 (+東, -西)
  面板法向量 n⃗ ─┘         └──── 面板法向量 n⃗
```

## 檔案

| 檔名 | 功能 |
|------|------|
| `tiptilt_to_azalt.py` | 核心轉換公式 `tiptilt_to_azalt(gamma, zeta) → (beta, phi)`，可批次產生對照表 CSV |
| `visualization.py` | 讀取對照表 CSV，用 HSV 色彩映射（色相=φ, 明度=β）將兩座標系並排可視化，並標註 A/B/C/D 四組實驗配置 |

## 數學原理

以 **ZYX 串聯旋轉**（先繞東西軸再繞南北軸），求面板法向量 `n⃗ = (x, y, z)`：

```
x = sin(ζ)
y = sin(γ) · cos(ζ)
z = cos(γ) · cos(ζ)
```

接著：

```
β = arccos(z)           # 從法向量 z 分量得傾角
φ = atan2(x, y)         # 從 x/y 分量得方位角（0–360°）
```

## 使用方式

### 1. 產生對照表

```bash
python tiptilt_to_azalt.py
# 互動輸入角度間隔（1 / 2 / 5 / 10°）
# 輸出: tiptilt_conversion_step{N}.csv
```

預設掃描範圍：γ ∈ [-30°, +30°]、ζ ∈ [-35°, +35°]。

### 2. 視覺化對照關係

```bash
python visualization.py tiptilt_conversion_step1.csv
# 輸出: mapping_combined.png
```

左圖：方位角-傾角座標系（φ 橫軸、β 縱軸）。
右圖：Tip-Tilt 座標系（γ 橫軸、ζ 縱軸）。
兩圖用相同顏色編碼，相同顏色 = 相同物理姿態。

## 與 ANFIS 訓練流程的接點

```
fixed_data_process_visualization/
   └── 產出 (β, φ, power, illumination, solar_zenith, solar_azimuth) ──┐
                                                                        ▼
                     algorithms/coordinate_conversion/tiptilt_to_azalt
                                                                        │
                          ↓ 把每筆 (β, φ) 轉成 (γ, ζ)                  │
                                                                        ▼
                     algorithms/solar_anfis_model_v2.py
                     （以 γ, ζ, 太陽位置, 光照 → 預測功率/最佳角度）
```

四組實驗配置（A/B/C/D）：
- A: β=10°, φ=160°（東南傾）
- B: β=10°, φ=180°（正南傾）
- C: β=20°, φ=180°（正南傾，較陡）
- D: β=30°, φ=200°（西南傾）
