#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
solar_anfis_model_v6.py
=======================
v6 — Hybrid ANFIS + Physics POA Prior + 直接幾何特徵

相較 v5 增加兩個直接角度幾何特徵：
  - cos_incidence：入射角餘弦 cos(θ)
  - sin_solar_elevation：太陽仰角 sin(α_s)

動機：v5 雖然把 POA 物理項當 baseline 解決角度的「絕對效應」，但模型仍可能
忽略 tilt/azimuth 特徵（因為 sin-cos 表示太間接）。直接給 cos_incidence 可以
讓模型在學殘差時「看到」角度幾何

**核心理念：把已知的物理項從 target 中除掉，讓 ANFIS 只學殘差**

v4.1 的根本問題：efficiency_ratio target 仍把「角度對應的幾何效率」放在模型要學的部分，
但其實這 90% 可以用太陽位置幾何（cos 入射角 + 散射）算出來。

v5 解法：
    target = PR_norm = power_W / (theoretical_poa × area × η_STC)
            ≈ Performance Ratio（PV 業界標準名詞）
            範圍 0–1（已 normalize 到 STC 條件）

    預測時：predicted_power = PR_pred × theoretical_poa × area × η_STC

這樣：
- 角度的幾何效應（cos 入射角等）完全由物理 prior（theoretical_poa）負責
- ANFIS 只需學「殘差」：天氣、溫度、灰塵、本地效應
- per-range R² 有機會翻正，因為角度差異本身已不依賴模型學
- 雙軸 ±35° OOD 推論天然有解 —— pvlib 對任何角度都能算 POA

相較 v4.1 的改動：
1. [Target] efficiency_ratio (power/illumination) → PR_norm (power/(POA × area × η))
2. [輸出] sigmoid（物理上 PR ≤ 1，比 v4 sigmoid 合理多了；資料集驗證 max=0.98 從不超過 1）
3. [特徵] 8 幾何 + 1 weather proxy (illumination/1000)
4. [Split] 隨機分割 → timestamp-aware（GroupShuffleSplit）
   保證測試 timestamp 完整有 12 角度可做 ranking 評估
5. [Mode B] 用 pvlib 算 OOD 角度的 POA，再 × PR_pred 得到實際物理合理的功率預測

Panel 規格（TS54-BMH-405 H1, 元晶）：
    - STC 額定功率: 405 W
    - 效率: 20.8%
    - 推算面積: 405 / (1000 × 0.208) = 1.948 m²

實驗場域：新北先鋒金土地公廟，緯度 25.10°N，經度 121.43°E

使用方式：
    python train_pipeline.py --skip-preprocess --dataset ds02_20260506_含照度 --model v5
    python solar_anfis_model_v5.py datasets/ds02_20260506_含照度/data.csv
"""

import os
os.environ['TF_CPP_MIN_LOG_LEVEL'] = '2'

import tensorflow as tf

print("\n" + "=" * 60)
print("GPU 初始化")
gpus = tf.config.list_physical_devices('GPU')
if gpus:
    try:
        for gpu in gpus:
            tf.config.experimental.set_memory_growth(gpu, True)
        print(f"GPU: {gpus[0].name}")
    except Exception as e:
        print(f"GPU 設定警告: {e}")
else:
    print("使用 CPU 訓練")
print("=" * 60 + "\n")

import pandas as pd
import numpy as np
from datetime import datetime
import matplotlib.pyplot as plt
import matplotlib.font_manager as fm
from sklearn.model_selection import GroupShuffleSplit
from sklearn.preprocessing import MinMaxScaler
from tensorflow.keras.models import Model
from tensorflow.keras.layers import Input, Dense, Layer, Dropout
from tensorflow.keras.optimizers import Adam
from tensorflow.keras.callbacks import EarlyStopping, ReduceLROnPlateau, ModelCheckpoint
import joblib
import json
from sklearn.metrics import mean_squared_error, mean_absolute_error, r2_score
try:
    from scipy.stats import spearmanr
    HAS_SCIPY = True
except ImportError:
    HAS_SCIPY = False
try:
    import pvlib
    HAS_PVLIB = True
except ImportError:
    HAS_PVLIB = False


# ════════════════════════════════════════════════════════════════
# Panel 規格 & 場域常數
# ════════════════════════════════════════════════════════════════
PANEL_AREA_M2   = 1.948      # 1.948 m² (TS54-BMH-405 H1)
PANEL_EFF_STC   = 0.208      # 20.8% at STC
SITE_LATITUDE   = 25.10      # 新北先鋒
SITE_LONGITUDE  = 121.43
SITE_ALTITUDE   = 50         # 約值，影響很小


def setup_chinese_font():
    for font in ['DFKai-SB', 'Microsoft JhengHei', 'Microsoft YaHei',
                 'KaiTi', 'SimHei', 'Arial Unicode MS', 'Noto Sans CJK TC']:
        try:
            fm.findfont(fm.FontProperties(family=font))
            plt.rcParams['font.family'] = font
            plt.rcParams['axes.unicode_minus'] = False
            return
        except Exception:
            continue


# ════════════════════════════════════════════════════════════════
# ANFIS 架構（同 v4.1，sigmoid 輸出）
# ════════════════════════════════════════════════════════════════
class SimpleFuzzyLayer(Layer):
    def __init__(self, num_mfs, **kwargs):
        self.num_mfs = num_mfs
        super().__init__(**kwargs)

    def build(self, input_shape):
        self.centers = self.add_weight(
            name='centers',
            shape=(input_shape[-1], self.num_mfs),
            initializer=tf.keras.initializers.RandomUniform(-1.5, 1.5),
            trainable=True
        )
        self.sigmas = self.add_weight(
            name='sigmas',
            shape=(input_shape[-1], self.num_mfs),
            initializer=tf.keras.initializers.Constant(0.5),
            trainable=True
        )
        super().build(input_shape)

    def call(self, x):
        expanded_x = tf.expand_dims(x, -1)
        dist = tf.square(expanded_x - self.centers)
        return tf.exp(-dist / (2 * tf.square(tf.abs(self.sigmas) + 0.1)))

    def get_config(self):
        config = super().get_config()
        config.update({'num_mfs': self.num_mfs})
        return config

    def compute_output_shape(self, input_shape):
        return (input_shape[0], input_shape[1], self.num_mfs)


def build_anfis_model(input_dim, num_mfs=7):
    """ANFIS v6：sigmoid 輸出（PR_norm ∈ [0, 1]，物理合理）"""
    inputs = Input(shape=(input_dim,))
    fuzzified = SimpleFuzzyLayer(num_mfs)(inputs)
    flat = tf.keras.layers.Reshape((input_dim * num_mfs,))(fuzzified)
    x = Dense(128, activation='relu')(flat)
    x = Dropout(0.3)(x)
    x = tf.keras.layers.BatchNormalization()(x)
    x = Dense(64, activation='relu')(x)
    x = Dropout(0.25)(x)
    x = tf.keras.layers.BatchNormalization()(x)
    x = Dense(32, activation='relu')(x)
    x = Dropout(0.2)(x)
    x = Dense(16, activation='relu')(x)
    x = Dropout(0.1)(x)
    output = Dense(1, activation='sigmoid')(x)
    model = Model(inputs=inputs, outputs=output)
    model.compile(optimizer=Adam(learning_rate=0.001), loss='mse', metrics=['mae'])
    return model


# ════════════════════════════════════════════════════════════════
# v5 特徵工程：PR_norm target + clearness 特徵
# ════════════════════════════════════════════════════════════════
def create_features_v6(df, poa_min: float = 50.0):
    """
    target = PR_norm = power_W / (theoretical_poa × area × η_STC)
    特徵 9 維：8 幾何 + 1 clearness（illumination/1000）

    poa_min：theoretical_poa 低於此值的資料列會被過濾
    """
    print("\n=== v5 特徵工程 ===")

    if 'theoretical_poa' not in df.columns:
        print("  ❌ 缺少 theoretical_poa 欄位")
        return None, None, None

    df['theoretical_poa'] = pd.to_numeric(df['theoretical_poa'], errors='coerce')
    df['illumination']   = pd.to_numeric(df['illumination'], errors='coerce')
    df = df.dropna(subset=['theoretical_poa', 'illumination', 'power_W']).copy()

    n_before = len(df)
    df = df[df['theoretical_poa'] >= poa_min].copy()
    print(f"  過濾 theoretical_poa < {poa_min} W/m²：{n_before - len(df):,} 筆移除，剩 {len(df):,} 筆")

    # PR_norm
    df['expected_power'] = df['theoretical_poa'] * PANEL_AREA_M2 * PANEL_EFF_STC
    df['PR_norm'] = df['power_W'] / df['expected_power']

    pr_max = df['PR_norm'].max()
    pr_mean = df['PR_norm'].mean()
    pr_p99 = df['PR_norm'].quantile(0.99)
    print(f"  PR_norm 範圍: {df['PR_norm'].min():.4f}–{pr_max:.4f}  平均: {pr_mean:.4f}  P99: {pr_p99:.4f}")
    if pr_max > 1.05:
        n_over = (df['PR_norm'] > 1.05).sum()
        print(f"  ⚠ PR_norm > 1.05 樣本: {n_over:,}（可能是 POA 低估或量測誤差，會被 sigmoid 截斷）")
    else:
        print(f"  ✓ PR_norm 全在 [0, 1.05] 內，sigmoid 輸出合理")

    # 時間 sin/cos
    df['hour_sin'] = np.sin(2 * np.pi * df['hour_decimal'] / 24)
    df['hour_cos'] = np.cos(2 * np.pi * df['hour_decimal'] / 24)
    df['day_sin']  = np.sin(2 * np.pi * df['day_of_year'] / 365)
    df['day_cos']  = np.cos(2 * np.pi * df['day_of_year'] / 365)

    # 角度 sin/cos
    df['tilt_sin']    = np.sin(np.radians(df['tilt_angle']))
    df['tilt_cos']    = np.cos(np.radians(df['tilt_angle']))
    df['azimuth_sin'] = np.sin(np.radians(df['azimuth_angle']))
    df['azimuth_cos'] = np.cos(np.radians(df['azimuth_angle']))

    # Clearness index：illumination (GHI 量測) / 1000（簡單天氣 proxy）
    df['clearness'] = (df['illumination'] / 1000.0).clip(0, 1.5)

    # v6 新增：cos_incidence 與 sin_solar_elevation
    # 公式：cos(θ) = cos(zenith) cos(tilt) + sin(zenith) sin(tilt) cos(solar_azi - panel_azi)
    if 'solar_zenith' in df.columns and 'solar_azimuth' in df.columns:
        zenith_rad = np.radians(df['solar_zenith'])
        solar_azi_rad = np.radians(df['solar_azimuth'])
        tilt_rad = np.radians(df['tilt_angle'])
        panel_azi_rad = np.radians(df['azimuth_angle'])
        cos_inc = (np.cos(zenith_rad) * np.cos(tilt_rad) +
                   np.sin(zenith_rad) * np.sin(tilt_rad) *
                   np.cos(solar_azi_rad - panel_azi_rad))
        df['cos_incidence'] = np.clip(cos_inc, -1.0, 1.0)
        df['sin_solar_elev'] = np.cos(zenith_rad)  # sin(elev) = cos(zenith)
        print(f"  cos_incidence 範圍: {df['cos_incidence'].min():.3f}–{df['cos_incidence'].max():.3f}  平均: {df['cos_incidence'].mean():.3f}")
        print(f"  sin_solar_elev 範圍: {df['sin_solar_elev'].min():.3f}–{df['sin_solar_elev'].max():.3f}  平均: {df['sin_solar_elev'].mean():.3f}")
    else:
        print("  ⚠ 缺少 solar_zenith/azimuth，cos_incidence 設為 0")
        df['cos_incidence'] = 0.0
        df['sin_solar_elev'] = 0.5

    feature_columns = [
        'hour_sin', 'hour_cos', 'day_sin', 'day_cos',
        'tilt_sin', 'tilt_cos', 'azimuth_sin', 'azimuth_cos',
        'clearness',
        'cos_incidence', 'sin_solar_elev',  # v6 新增
    ]

    print(f"  特徵維度: {len(feature_columns)}")
    print(f"  Target: PR_norm = power_W / (theoretical_poa × {PANEL_AREA_M2} × {PANEL_EFF_STC})")
    return df, feature_columns, 'PR_norm'


# ════════════════════════════════════════════════════════════════
# 評估：分功率區間
# ════════════════════════════════════════════════════════════════
def evaluate_by_range(y_power_true, y_power_pred):
    ranges = [(0, 100), (100, 200), (200, 300), (300, 1e9)]
    labels = ['0-100W', '100-200W', '200-300W', '>300W']
    results = {}
    print("\n=== 分範圍評估（瓦特空間）===")
    for (lo, hi), label in zip(ranges, labels):
        mask = (y_power_true >= lo) & (y_power_true < hi)
        n = mask.sum()
        if n > 10:
            mae = mean_absolute_error(y_power_true[mask], y_power_pred[mask])
            r2  = r2_score(y_power_true[mask], y_power_pred[mask])
            print(f"  {label:10s}: n={n:6,}  MAE={mae:6.1f}W  R²={r2:+.3f}")
            results[label] = {'n': int(n), 'mae': float(mae), 'r2': float(r2)}
        else:
            print(f"  {label:10s}: 樣本數不足（{n}），跳過")
    return results


# ════════════════════════════════════════════════════════════════
# 評估 Mode A：12 角度內 ranking（timestamp-aware split 後應為完整 12）
# ════════════════════════════════════════════════════════════════
def evaluate_ranking_mode_a(df_test_meta: pd.DataFrame,
                             y_power_true: np.ndarray,
                             y_power_pred: np.ndarray):
    print("\n=== Mode A：12 角度內 Ranking 評估（timestamp-aware split）===")

    df_eval = df_test_meta[['timestamp', 'tilt_angle', 'azimuth_angle']].copy()
    df_eval['power_true'] = y_power_true
    df_eval['power_pred'] = y_power_pred

    df_agg = df_eval.groupby(
        ['timestamp', 'tilt_angle', 'azimuth_angle'], as_index=False
    ).agg(power_true=('power_true', 'mean'),
          power_pred=('power_pred', 'mean'))

    top1_correct, power_gaps, spearman_rhos, n_panels_list = [], [], [], []

    for ts, group in df_agg.groupby('timestamp'):
        if len(group) < 2:
            continue
        n_panels_list.append(len(group))
        true_max_idx = group['power_true'].idxmax()
        pred_max_idx = group['power_pred'].idxmax()
        top1_correct.append(true_max_idx == pred_max_idx)
        true_max_power    = group.loc[true_max_idx, 'power_true']
        pred_chosen_power = group.loc[pred_max_idx, 'power_true']
        power_gaps.append(true_max_power - pred_chosen_power)
        if HAS_SCIPY and len(group) >= 3:
            rho, _ = spearmanr(group['power_true'], group['power_pred'])
            if not np.isnan(rho):
                spearman_rhos.append(rho)

    if not top1_correct:
        print("  ⚠ 沒有足夠的 timestamp 含 ≥2 角度，跳過")
        return {}

    top1_acc        = np.mean(top1_correct)
    avg_n_panels    = np.mean(n_panels_list)
    spearman_mean   = np.mean(spearman_rhos) if spearman_rhos else float('nan')

    print(f"  測試集 timestamp 數: {len(top1_correct):,}")
    print(f"  每 timestamp 平均角度數: {avg_n_panels:.1f}（期望 12）")
    print(f"  Top-1 Accuracy:           {top1_acc:.4f}  ({top1_acc*100:.1f}%)  [隨機猜 1/{int(round(avg_n_panels))} ≈ {1/avg_n_panels*100:.1f}%]")
    print(f"  Top-1 Power Gap 平均:     {np.mean(power_gaps):.2f} W")
    print(f"  Top-1 Power Gap 中位數:   {np.median(power_gaps):.2f} W")
    if not np.isnan(spearman_mean):
        print(f"  時刻內 Spearman 平均:     {spearman_mean:+.4f}")

    return {
        'n_timestamps':      int(len(top1_correct)),
        'avg_n_panels':      float(avg_n_panels),
        'top1_accuracy':     float(top1_acc),
        'power_gap_mean':    float(np.mean(power_gaps)),
        'power_gap_median':  float(np.median(power_gaps)),
        'spearman_mean':     float(spearman_mean) if not np.isnan(spearman_mean) else None,
    }


# ════════════════════════════════════════════════════════════════
# Mode B：用 pvlib 算 OOD 角度的 POA
# ════════════════════════════════════════════════════════════════
def compute_poa_grid(timestamps: pd.Series, tilt_grid: np.ndarray,
                     azi_grid: np.ndarray, ghi_arr: np.ndarray):
    """
    對給定的 timestamps × tilt × azi 網格，用 pvlib 計算 POA
    使用 Erbs decomposition (GHI → DNI/DHI) + Hay-Davies transposition

    回傳 shape: (n_ts, n_tilt × n_azi)
    """
    if not HAS_PVLIB:
        raise RuntimeError("pvlib 未安裝，Mode B 無法執行")

    print(f"  [DEBUG] compute_poa_grid called, n_ts={len(timestamps)}, ghi shape={ghi_arr.shape}")
    ts_index = pd.DatetimeIndex(pd.to_datetime(timestamps))
    # 假設原始 timestamp 是 Asia/Taipei naive，加上時區
    if ts_index.tz is None:
        ts_index = ts_index.tz_localize('Asia/Taipei', ambiguous='NaT',
                                         nonexistent='shift_forward')
    dayofyear = np.asarray(ts_index.dayofyear)
    print(f"  [DEBUG] ts_index OK, dayofyear shape={dayofyear.shape}")

    # 太陽位置
    solpos = pvlib.solarposition.get_solarposition(
        ts_index, SITE_LATITUDE, SITE_LONGITUDE, altitude=SITE_ALTITUDE
    )
    zenith  = np.asarray(solpos['apparent_zenith'])
    azi_sun = np.asarray(solpos['azimuth'])

    # GHI → DNI/DHI (Erbs)
    erbs = pvlib.irradiance.erbs(ghi_arr, zenith, dayofyear)
    dni = np.asarray(erbs['dni'])
    dhi = np.asarray(erbs['dhi'])
    dni_extra = np.asarray(pvlib.irradiance.get_extra_radiation(dayofyear))

    n_ts = len(ts_index)
    n_tilt = len(tilt_grid)
    n_azi  = len(azi_grid)
    poa_matrix = np.zeros((n_ts, n_tilt * n_azi), dtype='float32')

    for i, t in enumerate(tilt_grid):
        for j, a in enumerate(azi_grid):
            poa = pvlib.irradiance.get_total_irradiance(
                surface_tilt=float(t),
                surface_azimuth=float(a),
                solar_zenith=zenith,
                solar_azimuth=azi_sun,
                dni=dni, ghi=ghi_arr, dhi=dhi,
                dni_extra=dni_extra,
                model='haydavies',
            )
            poa_global = np.asarray(poa['poa_global'])
            poa_matrix[:, i * n_azi + j] = np.nan_to_num(poa_global, nan=0.0)

    return poa_matrix


def evaluate_ranking_mode_b(model, scaler_X, df_test_meta: pd.DataFrame,
                             y_power_true: np.ndarray, feature_columns: list,
                             tilt_range=(0, 35, 5),
                             azi_range=(145, 215, 10),
                             max_timestamps=1000):
    """
    Mode B：對每個 test timestamp，在 ±35° 雙軸網格上：
    1. 用 pvlib 算每個 (tilt, azi) 的 POA
    2. ANFIS 預測 PR
    3. predicted_power = PR × POA × area × eff_stc
    4. 挑全域最大，與 12 片真冠軍比較
    """
    print(f"\n=== Mode B：雙軸 ±35° 連續網格評估（hybrid POA）===")

    if not HAS_PVLIB:
        print("  ⚠ pvlib 未安裝，跳過 Mode B")
        return {'error': 'no pvlib'}

    tilt_grid = np.arange(tilt_range[0], tilt_range[1] + 1, tilt_range[2])
    azi_grid  = np.arange(azi_range[0],  azi_range[1]  + 1, azi_range[2])
    n_grid    = len(tilt_grid) * len(azi_grid)
    print(f"  網格: {len(tilt_grid)} tilt × {len(azi_grid)} azi = {n_grid}")

    df_eval = df_test_meta[['timestamp', 'hour_decimal', 'day_of_year',
                             'illumination', 'tilt_angle', 'azimuth_angle']].copy()
    df_eval['power_true'] = y_power_true

    ts_agg = df_eval.groupby('timestamp').agg(
        true_max_power=('power_true', 'max'),
        hour_decimal=('hour_decimal', 'first'),
        day_of_year=('day_of_year', 'first'),
        illumination=('illumination', 'first'),
    ).reset_index()

    if len(ts_agg) > max_timestamps:
        ts_agg = ts_agg.sample(n=max_timestamps, random_state=42).reset_index(drop=True)
        print(f"  取樣 {max_timestamps:,} 個 timestamp")

    n_ts = len(ts_agg)
    print(f"  評估 timestamp 數: {n_ts:,}  → 預測樣本數: {n_ts * n_grid:,}")
    print(f"  用 pvlib 計算 POA 中...")

    try:
        poa_matrix = compute_poa_grid(
            ts_agg['timestamp'], tilt_grid, azi_grid,
            ts_agg['illumination'].values.astype('float32')
        )
    except Exception as e:
        import traceback
        tb_str = traceback.format_exc()
        print(f"  ⚠ pvlib POA 計算失敗: {e}")
        print("  ─── TRACEBACK ───")
        for line in tb_str.split('\n'):
            print(f"    {line}")
        print("  ─── END ───")
        return {'error': str(e)}

    # 構造特徵矩陣
    hour_arr = ts_agg['hour_decimal'].values
    day_arr  = ts_agg['day_of_year'].values
    illum_arr = ts_agg['illumination'].values
    clearness_arr = np.clip(illum_arr / 1000.0, 0, 1.5)

    hour_sin = np.repeat(np.sin(2*np.pi*hour_arr/24), n_grid)
    hour_cos = np.repeat(np.cos(2*np.pi*hour_arr/24), n_grid)
    day_sin  = np.repeat(np.sin(2*np.pi*day_arr/365), n_grid)
    day_cos  = np.repeat(np.cos(2*np.pi*day_arr/365), n_grid)
    clearness_tile = np.repeat(clearness_arr, n_grid)

    tilt_azi_grid = np.array([(t, a) for t in tilt_grid for a in azi_grid])
    tilts_tile = np.tile(tilt_azi_grid[:, 0], n_ts)
    azis_tile  = np.tile(tilt_azi_grid[:, 1], n_ts)
    tilt_sin = np.sin(np.radians(tilts_tile))
    tilt_cos = np.cos(np.radians(tilts_tile))
    azi_sin  = np.sin(np.radians(azis_tile))
    azi_cos  = np.cos(np.radians(azis_tile))

    # v6: 在網格上計算 cos_incidence 與 sin_solar_elev
    # pvlib 在 compute_poa_grid 內已算出 zenith / sun_azi，這裡重算（簡化版）
    # 用同樣的 ts_index 取得太陽位置
    ts_index_b = pd.DatetimeIndex(pd.to_datetime(ts_agg['timestamp']))
    if ts_index_b.tz is None:
        ts_index_b = ts_index_b.tz_localize('Asia/Taipei', ambiguous='NaT', nonexistent='shift_forward')
    solpos_b = pvlib.solarposition.get_solarposition(
        ts_index_b, SITE_LATITUDE, SITE_LONGITUDE, altitude=SITE_ALTITUDE
    )
    zenith_b = np.asarray(solpos_b['apparent_zenith'])
    sazi_b   = np.asarray(solpos_b['azimuth'])

    # 對每 ts × grid 算 cos_incidence
    zenith_tile = np.repeat(zenith_b, n_grid)
    sazi_tile   = np.repeat(sazi_b,   n_grid)
    cos_inc_tile = (np.cos(np.radians(zenith_tile)) * np.cos(np.radians(tilts_tile)) +
                    np.sin(np.radians(zenith_tile)) * np.sin(np.radians(tilts_tile)) *
                    np.cos(np.radians(sazi_tile) - np.radians(azis_tile)))
    cos_inc_tile = np.clip(cos_inc_tile, -1.0, 1.0)
    sin_elev_tile = np.cos(np.radians(zenith_tile))

    X_big = np.column_stack([hour_sin, hour_cos, day_sin, day_cos,
                              tilt_sin, tilt_cos, azi_sin, azi_cos,
                              clearness_tile,
                              cos_inc_tile, sin_elev_tile]).astype('float32')
    X_big_scaled = scaler_X.transform(X_big)

    print("  ANFIS 推論中...")
    pr_pred = model.predict(X_big_scaled, batch_size=4096, verbose=0).flatten()

    # predicted_power = PR × POA × area × eff_stc
    poa_flat = poa_matrix.reshape(-1)
    power_pred = pr_pred * poa_flat * PANEL_AREA_M2 * PANEL_EFF_STC

    power_pred_matrix = power_pred.reshape(n_ts, n_grid)
    best_grid_idx = np.argmax(power_pred_matrix, axis=1)
    best_tilts = tilt_azi_grid[best_grid_idx, 0]
    best_azis  = tilt_azi_grid[best_grid_idx, 1]
    best_pred_powers = power_pred_matrix[np.arange(n_ts), best_grid_idx]

    true_max = ts_agg['true_max_power'].values
    gain = best_pred_powers - true_max

    in_dataset_range = (
        (best_tilts >= 10) & (best_tilts <= 30) &
        (best_azis >= 160) & (best_azis <= 200)
    )

    print(f"  ── 結果（hybrid POA + ANFIS PR）──")
    print(f"  模型預測最佳平均: {best_pred_powers.mean():.2f} W")
    print(f"  12 片真冠軍平均:  {true_max.mean():.2f} W")
    print(f"  模型認為增益平均: {gain.mean():+.2f} W ({gain.mean()/true_max.mean()*100:+.1f}%)")
    print(f"  落在資料集 12 角度範圍內: {in_dataset_range.sum():,}/{n_ts:,} ({in_dataset_range.mean()*100:.1f}%)")
    print(f"  挑的角度分布:")
    print(f"    tilt: 平均 {best_tilts.mean():.1f}°  中位數 {np.median(best_tilts):.0f}°")
    print(f"    azi:  平均 {best_azis.mean():.1f}°  中位數 {np.median(best_azis):.0f}°")

    return {
        'n_timestamps':         int(n_ts),
        'n_grid_points':        int(n_grid),
        'tilt_range':           list(tilt_range),
        'azi_range':            list(azi_range),
        'pred_best_mean':       float(best_pred_powers.mean()),
        'true_max12_mean':      float(true_max.mean()),
        'gain_mean':            float(gain.mean()),
        'gain_pct':             float(gain.mean()/true_max.mean()*100),
        'in_dataset_range_pct': float(in_dataset_range.mean()*100),
        'best_tilt_mean':       float(best_tilts.mean()),
        'best_azi_mean':        float(best_azis.mean()),
    }


# ════════════════════════════════════════════════════════════════
# 主函式
# ════════════════════════════════════════════════════════════════
def main(file_path=None, output_dir=None, poa_min: float = 50.0,
         skip_mode_b: bool = False, **kwargs):
    print(f"=== ANFIS v6 訓練啟動 (Hybrid POA + 直接幾何特徵) ===")
    print(f"  target = PR_norm = power_W / (theoretical_poa × {PANEL_AREA_M2} × {PANEL_EFF_STC})")
    print(f"  Site: ({SITE_LATITUDE}, {SITE_LONGITUDE})")
    print(f"  pvlib available: {HAS_PVLIB}")
    setup_chinese_font()

    if file_path is None:
        file_path = input("請輸入數據文件路徑: ")

    # ── 載入
    print(f"\n載入資料: {file_path}")
    try:
        df = pd.read_csv(file_path)
        print(f"✅ {len(df):,} 筆")
    except Exception as e:
        print(f"❌ 載入失敗: {e}")
        return None

    if 'timestamp' in df.columns:
        ts_dt = pd.to_datetime(df['timestamp'], errors='coerce')
        if 'day_of_year' not in df.columns:
            df['day_of_year']  = ts_dt.dt.dayofyear
        if 'hour_decimal' not in df.columns:
            df['hour_decimal'] = ts_dt.dt.hour + ts_dt.dt.minute / 60 + ts_dt.dt.second / 3600

    required = ['day_of_year', 'hour_decimal', 'tilt_angle', 'azimuth_angle',
                'power_W', 'illumination', 'theoretical_poa', 'timestamp']
    missing = [c for c in required if c not in df.columns]
    if missing:
        print(f"❌ 缺少欄位: {missing}")
        return None

    for col in ['day_of_year', 'hour_decimal', 'tilt_angle', 'azimuth_angle',
                'power_W', 'illumination', 'theoretical_poa']:
        df[col] = pd.to_numeric(df[col], errors='coerce')
    df = df.dropna(subset=['day_of_year', 'hour_decimal', 'tilt_angle',
                            'azimuth_angle', 'power_W', 'illumination',
                            'theoretical_poa', 'timestamp'])
    print(f"清理後: {len(df):,} 筆")

    # ── 特徵工程
    result = create_features_v6(df, poa_min=poa_min)
    if result[0] is None:
        return None
    df, feature_columns, target_col = result

    df = df.dropna(subset=feature_columns + [target_col])
    # PR_norm 截斷在 [0, 1.05]（極小部分 > 1 視為 noise）
    df[target_col] = df[target_col].clip(0, 1.05)
    print(f"最終資料: {len(df):,} 筆")

    y_power = df['power_W'].values
    y       = df[target_col].values.astype('float32')
    expected_power = df['expected_power'].values.astype('float32')
    X       = df[feature_columns].values.astype('float32')
    timestamps_arr = df['timestamp'].values

    # ── timestamp-aware split：同 timestamp 不跨 train/test
    print("\n=== Timestamp-aware split ===")
    gss = GroupShuffleSplit(n_splits=1, test_size=0.2, random_state=42)
    idx_train, idx_test = next(gss.split(X, y, groups=timestamps_arr))
    n_train_ts = len(set(timestamps_arr[idx_train]))
    n_test_ts  = len(set(timestamps_arr[idx_test]))
    print(f"  訓練樣本: {len(idx_train):,}  涵蓋 {n_train_ts:,} 個 timestamp")
    print(f"  測試樣本: {len(idx_test):,}  涵蓋 {n_test_ts:,} 個 timestamp")

    X_train, X_test     = X[idx_train], X[idx_test]
    y_train, y_test     = y[idx_train], y[idx_test]
    expected_train      = expected_power[idx_train]
    expected_test       = expected_power[idx_test]
    y_power_test        = y_power[idx_test]
    df_test_meta        = df.iloc[idx_test][
        ['timestamp', 'tilt_angle', 'azimuth_angle',
         'hour_decimal', 'day_of_year', 'illumination']
    ].reset_index(drop=True)

    scaler_X = MinMaxScaler(feature_range=(-1, 1))
    X_train_scaled = scaler_X.fit_transform(X_train)
    X_test_scaled  = scaler_X.transform(X_test)

    # ── 建模
    NUM_MFS = 7
    print(f"\n建立 ANFIS v6 模型（輸入維度={X_train_scaled.shape[1]}, MF={NUM_MFS}, 輸出=sigmoid）")
    model = build_anfis_model(input_dim=X_train_scaled.shape[1], num_mfs=NUM_MFS)
    model.summary()

    if output_dir is None:
        output_dir = os.path.dirname(file_path) or '.'
    os.makedirs(output_dir, exist_ok=True)

    callbacks = [
        EarlyStopping(monitor='val_loss', patience=50,
                      restore_best_weights=True, verbose=1),
        ReduceLROnPlateau(monitor='val_loss', patience=20,
                          factor=0.5, min_lr=1e-7, verbose=1),
        ModelCheckpoint(filepath=os.path.join(output_dir, 'best_anfis.keras'),
                        monitor='val_loss', save_best_only=True, verbose=1),
    ]

    # 樣本加權：在 watts 空間等價
    # MSE_watts = Σ (expected_power × Δratio)² → weight ∝ expected_power²
    sample_weights = (expected_train ** 2)
    sample_weights = sample_weights / sample_weights.mean()
    sample_weights = np.clip(sample_weights, 0.05, 20.0)
    print(f"\n樣本加權: watts 空間等價 (∝ expected_power²)")
    print(f"  weight 範圍: {sample_weights.min():.3f}–{sample_weights.max():.3f}  平均: {sample_weights.mean():.3f}")

    # ── 訓練
    print(f"\n=== 開始訓練 ===")
    history = model.fit(
        X_train_scaled, y_train,
        epochs=800,
        batch_size=1024,
        validation_split=0.2,
        callbacks=callbacks,
        sample_weight=sample_weights,
        verbose=2
    )

    # ── 評估
    pr_pred = model.predict(X_test_scaled, batch_size=4096, verbose=0).flatten()
    y_power_pred = pr_pred * expected_test

    print(f"\n=== 整體評估（瓦特空間，與 v2/v3/v4.1 可比）===")
    rmse = float(np.sqrt(mean_squared_error(y_power_test, y_power_pred)))
    mae  = float(mean_absolute_error(y_power_test, y_power_pred))
    r2   = float(r2_score(y_power_test, y_power_pred))
    mape_mask = y_power_test > 1e-8
    mape = float(np.mean(np.abs((y_power_test[mape_mask] - y_power_pred[mape_mask]) /
                                 y_power_test[mape_mask])) * 100) if mape_mask.sum() else float('inf')
    print(f"  RMSE={rmse:.2f}W  MAE={mae:.2f}W  R²={r2:.4f}  MAPE={mape:.2f}%")

    pr_rmse = float(np.sqrt(mean_squared_error(y_test, pr_pred)))
    pr_r2   = float(r2_score(y_test, pr_pred))
    print(f"\n  PR_norm 空間：RMSE={pr_rmse:.4f}  R²={pr_r2:.4f}")
    print(f"  預測 PR 範圍: {pr_pred.min():.4f}–{pr_pred.max():.4f}")

    range_results = evaluate_by_range(y_power_test, y_power_pred)

    ranking_a = evaluate_ranking_mode_a(df_test_meta, y_power_test, y_power_pred)

    if skip_mode_b:
        print("\n  ⏭ 跳過 Mode B")
        ranking_b = {}
    else:
        try:
            ranking_b = evaluate_ranking_mode_b(model, scaler_X, df_test_meta,
                                                 y_power_test, feature_columns)
        except Exception as e:
            print(f"  ⚠ Mode B 失敗: {e}")
            import traceback
            traceback.print_exc()
            ranking_b = {'error': str(e)}

    # ── 圖表
    fig, axes = plt.subplots(2, 3, figsize=(18, 12))
    fig.suptitle(f'ANFIS v6 (Hybrid POA + Geometric Features)  '
                 f'R²(W)={r2:.3f}  Top-1 Acc={ranking_a.get("top1_accuracy", 0)*100:.1f}%  '
                 f'Top-1 Gap={ranking_a.get("power_gap_mean", 0):.1f}W',
                 fontsize=13)

    axes[0,0].scatter(y_power_test, y_power_pred, alpha=0.3, s=1)
    axes[0,0].plot([0, y_power_test.max()], [0, y_power_test.max()], 'r--')
    axes[0,0].set_xlabel('實際功率 (W)'); axes[0,0].set_ylabel('預測功率 (W)')
    axes[0,0].set_title(f'預測 vs 實際（W）R²={r2:.3f}'); axes[0,0].grid(alpha=0.3)

    axes[0,1].scatter(y_test, pr_pred, alpha=0.3, s=1, color='orange')
    axes[0,1].plot([0, 1], [0, 1], 'r--')
    axes[0,1].set_xlabel('實際 PR_norm'); axes[0,1].set_ylabel('預測 PR_norm')
    axes[0,1].set_title(f'PR_norm R²={pr_r2:.3f}'); axes[0,1].grid(alpha=0.3)

    axes[0,2].plot(history.history['loss'], label='訓練損失')
    axes[0,2].plot(history.history['val_loss'], label='驗證損失')
    axes[0,2].set_yscale('log')
    axes[0,2].set_title('訓練曲線（log）'); axes[0,2].legend(); axes[0,2].grid(alpha=0.3)

    residuals_W = y_power_pred - y_power_test
    axes[1,0].hist(residuals_W, bins=50, alpha=0.7)
    axes[1,0].axvline(0, color='r', linestyle='--')
    axes[1,0].set_title(f'殘差分布（W）MAE={mae:.1f}W'); axes[1,0].grid(alpha=0.3)

    if range_results:
        range_labels = list(range_results.keys())
        range_r2s    = [range_results[k]['r2'] for k in range_labels]
        colors = ['#e74c3c' if v < 0 else '#2ecc71' for v in range_r2s]
        axes[1,1].bar(range_labels, range_r2s, color=colors)
        axes[1,1].axhline(0, color='black', linewidth=0.8)
        axes[1,1].set_title('各功率區間 R²（紅=負，綠=正）')
        axes[1,1].set_ylabel('R²'); axes[1,1].grid(alpha=0.3)

    axes[1,2].hist(y, bins=50, alpha=0.6, color='steelblue', label='真實')
    axes[1,2].hist(pr_pred, bins=50, alpha=0.5, color='orange', label='預測')
    axes[1,2].set_xlabel('PR_norm')
    axes[1,2].set_title('PR_norm 分布比較'); axes[1,2].legend(); axes[1,2].grid(alpha=0.3)

    plt.tight_layout()
    plot_path = os.path.join(output_dir, 'anfis_v6_analysis.png')
    plt.savefig(plot_path, dpi=150, bbox_inches='tight')
    print(f"\n圖表: {plot_path}")
    plt.close()

    # ── 儲存
    model_path  = os.path.join(output_dir, 'anfis_v6.keras')
    scaler_path = os.path.join(output_dir, 'scaler_X_v6.save')
    config_path = os.path.join(output_dir, 'model_config_v6.json')

    config = {
        'model_version':    'v6',
        'target':           f'PR_norm = power_W / (theoretical_poa × {PANEL_AREA_M2} × {PANEL_EFF_STC})',
        'feature_columns':  feature_columns,
        'input_dim':        len(feature_columns),
        'num_mfs':          NUM_MFS,
        'output_activation': 'sigmoid',
        'panel_area_m2':    PANEL_AREA_M2,
        'panel_eff_stc':    PANEL_EFF_STC,
        'site_lat':         SITE_LATITUDE,
        'site_lon':         SITE_LONGITUDE,
        'poa_min':          poa_min,
        'split_method':     'timestamp_aware (GroupShuffleSplit)',
        'training_date':    datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        'performance_watts': {
            'rmse': rmse, 'mae': mae, 'r2': r2, 'mape': mape,
            'by_range': range_results,
        },
        'performance_pr': {
            'rmse': pr_rmse, 'r2': pr_r2,
        },
        'ranking_mode_a': ranking_a,
        'ranking_mode_b': ranking_b,
    }
    with open(config_path, 'w', encoding='utf-8') as f:
        json.dump(config, f, indent=2, ensure_ascii=False)

    model.save(model_path)
    joblib.dump(scaler_X, scaler_path)

    print(f"\n=== 模型已儲存 ===")
    print(f"  模型:   {model_path}")
    print(f"  Scaler: {scaler_path}")
    print(f"  Config: {config_path}")

    print(f"""
=== 控制器推論方式（v5）===
  # 給定 timestamp t 與當前/目標角度 (tilt, azi)：
  # 1. 用 pvlib 算 POA(t, tilt, azi)
  # 2. 構造特徵 (hour/day sin-cos, tilt/azi sin-cos, clearness)
  # 3. PR = model.predict(features)
  # 4. predicted_power = PR × POA × {PANEL_AREA_M2} × {PANEL_EFF_STC}
  # 5. 對候選角度集合，挑 predicted_power 最高者
""")

    return {
        'model': model,
        'scaler_X': scaler_X,
        'feature_columns': feature_columns,
        'performance': {'rmse': rmse, 'mae': mae, 'r2': r2, 'mape': mape},
        'range_results': range_results,
        'ranking_mode_a': ranking_a,
        'ranking_mode_b': ranking_b,
        'has_illumination': True,
    }


if __name__ == '__main__':
    import argparse

    parser = argparse.ArgumentParser(description='ANFIS v6 hybrid POA')
    parser.add_argument('file_path',     nargs='?', help='dataset CSV path')
    parser.add_argument('--output-dir',  default=None)
    parser.add_argument('--poa-min',     type=float, default=50.0)
    parser.add_argument('--skip-mode-b', action='store_true')
    args = parser.parse_args()
    main(file_path=args.file_path, output_dir=args.output_dir,
         poa_min=args.poa_min, skip_mode_b=args.skip_mode_b)
