#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
solar_anfis_model_v4_1.py
=========================
v4.1 — 在 v4 efficiency_ratio target 基礎上修正三個瑕疵 + 加入 ranking metrics

相較 v4 的改動：
1. [輸出層] sigmoid → softplus
   v4 sigmoid 把 ratio 截斷在 1，但低太陽仰角時 ratio > 1 是物理上合理的（傾斜面板
   收到的光大於 GHI）。softplus 允許 > 1 同時保持平滑與梯度。

2. [Loss 空間] ratio 空間 MSE → watts 空間 MSE
   v4 在 ratio 空間算 MSE，等於讓「低照度高雜訊樣本」與「白天高照度樣本」有同等權重，
   訓練被低照度雜訊干擾。改用 sample_weight ∝ illumination² 即可在 ratio 空間下
   等價於 watts 空間 MSE：
       MSE_watts = Σ (illum_i · Δratio_i)² = Σ illum_i² · Δratio_i²
   保留 Keras 標準 MSE，但梯度等價於 watts 空間。

3. [照度門檻] illum_min 10 → 50 W/m²
   過濾清晨/傍晚不穩定樣本，避免 power/illumination 在分母接近 0 時雜訊放大。

4. [評估] 加入 ranking metrics
   每 timestamp 對 12 個唯一角度（取 A/B 兩片均值）做：
   - Top-1 Accuracy：模型挑的最佳角度 = 實際最佳角度的比例
   - Top-1 Power Gap：選錯時的功率損失（瓦），均值與中位數
   - Spearman 相關：時刻內預測排序與實際排序的相關性

5. [Mode B 連續推論評估]
   對每個 test timestamp，在雙軸 ±35° 範圍（tilt 0–35°、azimuth 145–215°）的
   5° 網格上推論，挑出模型認為的全域最佳角度，與「12 片實測中的真冠軍」比較功率差。
   這個指標模擬實際雙軸追日系統的最大化空間，反映 OOD 角度推論能力。

使用方式：
    python train_pipeline.py --skip-preprocess --dataset ds02_20260506_含照度 --model v4_1
    python solar_anfis_model_v4_1.py datasets/ds02_20260506_含照度/data.csv
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
from sklearn.model_selection import train_test_split
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
# ANFIS 模型（架構同 v2/v3/v4，唯一改動：output activation = softplus）
# ════════════════════════════════════════════════════════════════
class SimpleFuzzyLayer(Layer):
    """模糊化層：每個輸入特徵使用 num_mfs 個高斯型成員函數"""

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
    """建立 ANFIS 模型（v4.1：softplus 輸出，允許 ratio > 1）"""
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
    # softplus = ln(1 + e^x)，平滑且可超過 1
    output = Dense(1, activation='softplus')(x)
    model = Model(inputs=inputs, outputs=output)
    model.compile(optimizer=Adam(learning_rate=0.001), loss='mse', metrics=['mae'])
    return model


# ════════════════════════════════════════════════════════════════
# v4.1 特徵工程
# ════════════════════════════════════════════════════════════════
def create_features_v4_1(df, illum_min: float = 50.0):
    """
    v4.1 特徵集：8 維純幾何特徵
    target：efficiency_ratio = power_W / illumination

    illum_min：照度低於此值的資料列會被過濾（避免分母接近零的雜訊放大）
               v4 預設 10，v4.1 提高到 50
    """
    print("\n=== v4.1 特徵工程 ===")

    # 時間循環編碼
    df['hour_sin'] = np.sin(2 * np.pi * df['hour_decimal'] / 24)
    df['hour_cos'] = np.cos(2 * np.pi * df['hour_decimal'] / 24)
    df['day_sin']  = np.sin(2 * np.pi * df['day_of_year'] / 365)
    df['day_cos']  = np.cos(2 * np.pi * df['day_of_year'] / 365)

    # 角度 sin/cos
    df['tilt_sin']    = np.sin(np.radians(df['tilt_angle']))
    df['tilt_cos']    = np.cos(np.radians(df['tilt_angle']))
    df['azimuth_sin'] = np.sin(np.radians(df['azimuth_angle']))
    df['azimuth_cos'] = np.cos(np.radians(df['azimuth_angle']))

    feature_columns = [
        'hour_sin', 'hour_cos', 'day_sin', 'day_cos',
        'tilt_sin', 'tilt_cos', 'azimuth_sin', 'azimuth_cos'
    ]

    if 'illumination' not in df.columns or df['illumination'].notna().sum() == 0:
        print("  ❌ illumination 欄位不存在或全為空，v4.1 無法執行")
        return None, None, None

    df['illumination'] = pd.to_numeric(df['illumination'], errors='coerce')
    n_before = len(df)
    df = df[df['illumination'] >= illum_min].copy()
    n_after = len(df)
    print(f"  過濾 illumination < {illum_min} W/m²：{n_before - n_after:,} 筆移除，剩 {n_after:,} 筆")

    df['efficiency_ratio'] = df['power_W'] / df['illumination']

    ratio_min = df['efficiency_ratio'].min()
    ratio_max = df['efficiency_ratio'].max()
    ratio_mean = df['efficiency_ratio'].mean()
    ratio_q99 = df['efficiency_ratio'].quantile(0.99)
    print(f"  efficiency_ratio 範圍：{ratio_min:.4f}–{ratio_max:.4f}  平均：{ratio_mean:.4f}  P99：{ratio_q99:.4f}")
    print(f"  (相當於平均 {ratio_mean*100:.1f}% 捕獲效率，max {ratio_max*100:.1f}%)")

    if ratio_max > 1.0:
        n_over = (df['efficiency_ratio'] > 1.0).sum()
        print(f"  ⚠ ratio > 1 的樣本: {n_over:,} 筆 ({n_over/len(df)*100:.2f}%)  ← softplus 處理")

    print(f"\n  特徵維度: {len(feature_columns)}  ({' | '.join(feature_columns)})")
    print(f"  Target: efficiency_ratio = power_W / illumination")

    return df, feature_columns, 'efficiency_ratio'


# ════════════════════════════════════════════════════════════════
# 樣本加權：watts 空間等價
# ════════════════════════════════════════════════════════════════
def compute_sample_weights_watts(illum: np.ndarray, w_min: float = 0.05,
                                  w_max: float = 20.0) -> np.ndarray:
    """
    watts 空間 MSE 等價權重：weight = illumination² / mean(illumination²)
    這樣 ratio-space MSE × weight = watts-space MSE
    """
    w = illum.astype('float32') ** 2
    w = w / w.mean()
    return np.clip(w, w_min, w_max)


def compute_sample_weights_power(y_ratio: np.ndarray, alpha: float,
                                  w_min: float = 0.2, w_max: float = 5.0) -> np.ndarray:
    """v3-style 功率加權（向後相容）"""
    if alpha == 0:
        return np.ones(len(y_ratio))
    p_mean = y_ratio.mean() + 1e-8
    weights = np.power(y_ratio / p_mean, alpha)
    return np.clip(weights, w_min, w_max)


# ════════════════════════════════════════════════════════════════
# 評估：瓦特空間分功率區間
# ════════════════════════════════════════════════════════════════
def evaluate_by_range(y_power_true, y_power_pred):
    """在瓦特空間評估，y_power = efficiency_ratio × illumination"""
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
# 評估 Mode A：12 角度內 ranking
# ════════════════════════════════════════════════════════════════
def evaluate_ranking_mode_a(df_test_meta: pd.DataFrame,
                             y_power_true: np.ndarray,
                             y_power_pred: np.ndarray):
    """
    Mode A：在每個 timestamp 的 12 個唯一角度中做 Top-1 ranking 評估

    Parameters
    ----------
    df_test_meta : DataFrame  必須包含 timestamp, tilt_angle, azimuth_angle 欄位
    y_power_true : 對應的真實功率 (W)
    y_power_pred : 對應的預測功率 (W)
    """
    print("\n=== Mode A：12 角度內 Ranking 評估 ===")

    df_eval = df_test_meta[['timestamp', 'tilt_angle', 'azimuth_angle']].copy()
    df_eval['power_true'] = y_power_true
    df_eval['power_pred'] = y_power_pred

    # 將同角度的 A/B 兩片取均值 → 每 timestamp 12 個唯一角度
    df_agg = df_eval.groupby(
        ['timestamp', 'tilt_angle', 'azimuth_angle'], as_index=False
    ).agg(power_true=('power_true', 'mean'),
          power_pred=('power_pred', 'mean'))

    # 對每個 timestamp 找 top-1
    top1_correct = []
    power_gaps   = []
    spearman_rhos = []
    n_panels_list = []

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
        print("  ⚠ 沒有足夠的 timestamp 包含 ≥2 個角度，跳過 Mode A")
        return {}

    top1_acc        = np.mean(top1_correct)
    power_gap_mean  = np.mean(power_gaps)
    power_gap_median = np.median(power_gaps)
    avg_n_panels    = np.mean(n_panels_list)
    spearman_mean   = np.mean(spearman_rhos) if spearman_rhos else float('nan')

    print(f"  測試集 timestamp 數: {len(top1_correct):,}")
    print(f"  每 timestamp 平均角度數: {avg_n_panels:.1f}")
    print(f"  Top-1 Accuracy:           {top1_acc:.4f}  ({top1_acc*100:.1f}%)  [隨機猜 1/{int(round(avg_n_panels))} ≈ {1/avg_n_panels*100:.1f}%]")
    print(f"  Top-1 Power Gap 平均:     {power_gap_mean:.2f} W")
    print(f"  Top-1 Power Gap 中位數:   {power_gap_median:.2f} W")
    if not np.isnan(spearman_mean):
        print(f"  時刻內 Spearman 平均:     {spearman_mean:+.4f}")
    else:
        print(f"  時刻內 Spearman:          N/A (scipy 未安裝或樣本太少)")

    return {
        'n_timestamps':      int(len(top1_correct)),
        'avg_n_panels':      float(avg_n_panels),
        'top1_accuracy':     float(top1_acc),
        'power_gap_mean':    float(power_gap_mean),
        'power_gap_median':  float(power_gap_median),
        'spearman_mean':     float(spearman_mean) if not np.isnan(spearman_mean) else None,
    }


# ════════════════════════════════════════════════════════════════
# 評估 Mode B：雙軸 ±35° 連續網格推論
# ════════════════════════════════════════════════════════════════
def evaluate_ranking_mode_b(model, scaler_X, df_test_meta: pd.DataFrame,
                             y_power_true: np.ndarray,
                             tilt_range=(0, 35, 5),
                             azi_range=(145, 215, 10),
                             max_timestamps=2000):
    """
    Mode B：對每個 test timestamp，在 ±35° 雙軸範圍的網格上推論，
    挑出模型認為的全域最佳角度，與 12 片實測中的真冠軍比較。

    為了控制計算時間，可用 max_timestamps 取樣（隨機選 N 個 unique timestamp）
    """
    print(f"\n=== Mode B：雙軸 ±35° 連續網格評估 ===")
    print(f"  tilt 網格: {tilt_range[0]}–{tilt_range[1]}° step {tilt_range[2]}°")
    print(f"  azimuth 網格: {azi_range[0]}–{azi_range[1]}° step {azi_range[2]}°")

    tilt_grid = np.arange(tilt_range[0], tilt_range[1] + 1, tilt_range[2])
    azi_grid  = np.arange(azi_range[0],  azi_range[1]  + 1, azi_range[2])
    n_grid    = len(tilt_grid) * len(azi_grid)
    print(f"  網格點數: {len(tilt_grid)} × {len(azi_grid)} = {n_grid}")

    df_eval = df_test_meta[['timestamp', 'hour_decimal', 'day_of_year',
                             'illumination', 'tilt_angle', 'azimuth_angle']].copy()
    df_eval['power_true'] = y_power_true

    # 每 timestamp 的真冠軍功率（從 12 角度中取最大）
    ts_true_max = df_eval.groupby('timestamp').agg(
        true_max_power=('power_true', 'max'),
        hour_decimal=('hour_decimal', 'first'),
        day_of_year=('day_of_year', 'first'),
        illumination=('illumination', 'first'),
    ).reset_index()

    # 取樣以控制計算量
    if len(ts_true_max) > max_timestamps:
        ts_true_max = ts_true_max.sample(n=max_timestamps, random_state=42).reset_index(drop=True)
        print(f"  從 {len(df_eval['timestamp'].unique()):,} 個 timestamp 取樣 {max_timestamps:,} 個做 Mode B")

    n_ts = len(ts_true_max)
    print(f"  評估 timestamp 數: {n_ts:,}  → 預測樣本數: {n_ts * n_grid:,}")

    # 構建大批次特徵矩陣
    hour_arr = ts_true_max['hour_decimal'].values
    day_arr  = ts_true_max['day_of_year'].values
    illum_arr = ts_true_max['illumination'].values

    # 預先算好時間特徵（每 timestamp 重複 n_grid 次）
    hour_sin = np.repeat(np.sin(2*np.pi*hour_arr/24), n_grid)
    hour_cos = np.repeat(np.cos(2*np.pi*hour_arr/24), n_grid)
    day_sin  = np.repeat(np.sin(2*np.pi*day_arr/365), n_grid)
    day_cos  = np.repeat(np.cos(2*np.pi*day_arr/365), n_grid)

    # 角度網格（每 timestamp 都用相同的網格）
    tilt_azi_grid = np.array([(t, a) for t in tilt_grid for a in azi_grid])
    tilts_tile = np.tile(tilt_azi_grid[:, 0], n_ts)
    azis_tile  = np.tile(tilt_azi_grid[:, 1], n_ts)
    tilt_sin = np.sin(np.radians(tilts_tile))
    tilt_cos = np.cos(np.radians(tilts_tile))
    azi_sin  = np.sin(np.radians(azis_tile))
    azi_cos  = np.cos(np.radians(azis_tile))

    X_big = np.column_stack([hour_sin, hour_cos, day_sin, day_cos,
                              tilt_sin, tilt_cos, azi_sin, azi_cos]).astype('float32')
    X_big_scaled = scaler_X.transform(X_big)

    # 推論
    print("  推論中...")
    ratio_pred = model.predict(X_big_scaled, batch_size=4096, verbose=0).flatten()
    illum_tile = np.repeat(illum_arr, n_grid)
    power_pred = ratio_pred * illum_tile

    # reshape: (n_ts, n_grid)
    power_pred_matrix = power_pred.reshape(n_ts, n_grid)
    best_grid_idx = np.argmax(power_pred_matrix, axis=1)
    best_tilts = tilt_azi_grid[best_grid_idx, 0]
    best_azis  = tilt_azi_grid[best_grid_idx, 1]
    best_pred_powers = power_pred_matrix[np.arange(n_ts), best_grid_idx]

    # 比較：模型認為的「連續最佳功率」 vs 12 片實測真冠軍
    true_max = ts_true_max['true_max_power'].values
    regret = true_max - best_pred_powers   # 注意這是用 model prediction 比，不嚴格
    gain   = best_pred_powers - true_max   # 模型認為的增益

    # 更嚴格的指標：模型挑的角度是否落在 12 角度範圍內？
    in_dataset_range = (
        (best_tilts >= 10) & (best_tilts <= 30) &
        (best_azis >= 160) & (best_azis <= 200)
    )

    print(f"  ── 結果 ──")
    print(f"  模型認為的最佳功率 vs 12 片真冠軍:")
    print(f"    模型預測平均: {best_pred_powers.mean():.2f} W")
    print(f"    12 片真冠軍平均: {true_max.mean():.2f} W")
    print(f"    模型認為增益平均: {gain.mean():+.2f} W ({gain.mean()/true_max.mean()*100:+.1f}%)")
    print(f"  模型挑的最佳角度落在資料集 12 角度範圍內: {in_dataset_range.sum():,}/{n_ts:,} ({in_dataset_range.mean()*100:.1f}%)")
    print(f"  模型挑的角度 (tilt, azi) 分布:")
    print(f"    tilt: 平均 {best_tilts.mean():.1f}°, 中位數 {np.median(best_tilts):.0f}°")
    print(f"    azi:  平均 {best_azis.mean():.1f}°, 中位數 {np.median(best_azis):.0f}°")

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
def main(file_path=None, output_dir=None, weight_alpha: float = 0.0,
         illum_min: float = 50.0, weight_mode: str = 'watts',
         skip_mode_b: bool = False):
    """
    Parameters
    ----------
    weight_mode : 'watts'（預設，watts 空間 MSE 等價）
                  'ratio'（純 ratio 空間 MSE，等同 v4）
                  'power_alpha'（v3 式功率加權）
    """
    print(f"=== ANFIS v4.1 訓練啟動 ===")
    print(f"  target = efficiency_ratio (power_W / illumination)")
    print(f"  weight_mode = {weight_mode}")
    print(f"  illum_min = {illum_min} W/m²")
    setup_chinese_font()

    if file_path is None:
        file_path = input("請輸入數據文件路徑: ")

    # ── 載入資料
    print(f"\n載入資料: {file_path}")
    try:
        df = pd.read_csv(file_path)
        print(f"✅ {len(df):,} 筆")
    except Exception as e:
        print(f"❌ 載入失敗: {e}")
        return None

    # ── 推導時間欄位
    if 'timestamp' in df.columns:
        ts = pd.to_datetime(df['timestamp'], errors='coerce')
        if 'day_of_year' not in df.columns:
            df['day_of_year']  = ts.dt.dayofyear
        if 'hour_decimal' not in df.columns:
            df['hour_decimal'] = ts.dt.hour + ts.dt.minute / 60 + ts.dt.second / 3600

    required = ['day_of_year', 'hour_decimal', 'tilt_angle', 'azimuth_angle',
                'power_W', 'illumination', 'timestamp']
    missing = [c for c in required if c not in df.columns]
    if missing:
        print(f"❌ 缺少欄位: {missing}")
        return None

    for col in ['day_of_year', 'hour_decimal', 'tilt_angle', 'azimuth_angle',
                'power_W', 'illumination']:
        df[col] = pd.to_numeric(df[col], errors='coerce')
    df = df.dropna(subset=['day_of_year', 'hour_decimal', 'tilt_angle',
                            'azimuth_angle', 'power_W', 'illumination'])
    print(f"清理後: {len(df):,} 筆")

    # ── v4.1 特徵工程
    result = create_features_v4_1(df, illum_min=illum_min)
    if result[0] is None:
        return None
    df, feature_columns, target_col = result

    df = df.dropna(subset=feature_columns + [target_col, 'illumination', 'power_W'])
    print(f"最終資料: {len(df):,} 筆")

    y_power = df['power_W'].values
    y       = df[target_col].values.astype('float32')
    illum_vals = df['illumination'].values.astype('float32')
    X       = df[feature_columns].values.astype('float32')

    # ── 分割（保留索引以便取 metadata）
    idx = np.arange(len(X))
    idx_train, idx_test = train_test_split(idx, test_size=0.2, random_state=42)

    X_train, X_test       = X[idx_train],         X[idx_test]
    y_train, y_test       = y[idx_train],         y[idx_test]
    illum_train           = illum_vals[idx_train]
    illum_test            = illum_vals[idx_test]
    y_power_test          = y_power[idx_test]
    df_test_meta          = df.iloc[idx_test][
        ['timestamp', 'tilt_angle', 'azimuth_angle',
         'hour_decimal', 'day_of_year', 'illumination']
    ].reset_index(drop=True)

    # ── 標準化
    scaler_X = MinMaxScaler(feature_range=(-1, 1))
    X_train_scaled = scaler_X.fit_transform(X_train)
    X_test_scaled  = scaler_X.transform(X_test)

    print(f"\n訓練集: {len(X_train):,}  測試集: {len(X_test):,}")

    # ── 建模
    NUM_MFS = 7
    print(f"\n建立 ANFIS v4.1 模型（輸入維度={X_train_scaled.shape[1]}, MF={NUM_MFS}, 輸出=softplus）")
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

    # ── 樣本加權
    if weight_mode == 'watts':
        sample_weights = compute_sample_weights_watts(illum_train)
        print(f"\n=== 樣本加權: watts 空間等價 (∝ illumination²) ===")
        print(f"  weight 範圍: {sample_weights.min():.3f}–{sample_weights.max():.3f}  平均: {sample_weights.mean():.3f}")
    elif weight_mode == 'power_alpha':
        sample_weights = compute_sample_weights_power(y_train, alpha=weight_alpha)
        print(f"\n=== 樣本加權: power^{weight_alpha} ===")
    else:  # 'ratio'
        sample_weights = np.ones(len(y_train))
        print(f"\n=== 樣本加權: 關閉（純 ratio 空間 MSE）===")

    # ── 訓練
    print(f"\n=== 開始訓練 ===")
    history = model.fit(
        X_train_scaled, y_train,
        epochs=800,
        batch_size=1024,
        validation_split=0.2,
        callbacks=callbacks,
        sample_weight=sample_weights,
        verbose=2  # 沙箱簡潔輸出
    )

    # ── 評估
    ratio_pred = model.predict(X_test_scaled, batch_size=4096, verbose=0).flatten()
    ratio_pred = np.clip(ratio_pred, 0, None)  # 不上限，但下限 0
    y_power_pred = ratio_pred * illum_test

    print(f"\n=== 整體評估（瓦特空間，與 v2/v3/v4 可比）===")
    rmse = float(np.sqrt(mean_squared_error(y_power_test, y_power_pred)))
    mae  = float(mean_absolute_error(y_power_test, y_power_pred))
    r2   = float(r2_score(y_power_test, y_power_pred))
    mape_mask = y_power_test > 1e-8
    mape = float(np.mean(np.abs((y_power_test[mape_mask] - y_power_pred[mape_mask]) /
                                 y_power_test[mape_mask])) * 100) if mape_mask.sum() else float('inf')
    print(f"  RMSE={rmse:.2f}W  MAE={mae:.2f}W  R²={r2:.4f}  MAPE={mape:.2f}%")

    ratio_rmse = float(np.sqrt(mean_squared_error(y_test, ratio_pred)))
    ratio_r2   = float(r2_score(y_test, ratio_pred))
    print(f"\n  efficiency_ratio 空間：RMSE={ratio_rmse:.4f}  R²={ratio_r2:.4f}")
    print(f"  預測 ratio 範圍: {ratio_pred.min():.4f}–{ratio_pred.max():.4f}  (>1 的有 {(ratio_pred>1).sum():,} 筆)")

    range_results = evaluate_by_range(y_power_test, y_power_pred)

    # ── Ranking 評估
    ranking_a = evaluate_ranking_mode_a(df_test_meta, y_power_test, y_power_pred)

    if skip_mode_b:
        print("\n  ⏭ 跳過 Mode B")
        ranking_b = {}
    else:
        try:
            ranking_b = evaluate_ranking_mode_b(model, scaler_X, df_test_meta, y_power_test)
        except Exception as e:
            print(f"  ⚠ Mode B 失敗: {e}")
            ranking_b = {'error': str(e)}

    # ── 圖表
    fig, axes = plt.subplots(2, 3, figsize=(18, 12))
    fig.suptitle(f'ANFIS v4.1  softplus + watts-MSE + illum_min={illum_min}\n'
                 f'R²(W)={r2:.3f}  Top-1 Acc={ranking_a.get("top1_accuracy", 0)*100:.1f}%  '
                 f'Top-1 Gap={ranking_a.get("power_gap_mean", 0):.1f}W',
                 fontsize=13)

    axes[0,0].scatter(y_power_test, y_power_pred, alpha=0.3, s=1)
    axes[0,0].plot([0, y_power_test.max()], [0, y_power_test.max()], 'r--')
    axes[0,0].set_xlabel('實際功率 (W)'); axes[0,0].set_ylabel('預測功率 (W)')
    axes[0,0].set_title(f'預測 vs 實際（W）R²={r2:.3f}'); axes[0,0].grid(alpha=0.3)

    axes[0,1].scatter(y_test, ratio_pred, alpha=0.3, s=1, color='orange')
    max_val = max(y_test.max(), ratio_pred.max())
    axes[0,1].plot([0, max_val], [0, max_val], 'r--')
    axes[0,1].set_xlabel('實際 efficiency_ratio'); axes[0,1].set_ylabel('預測 efficiency_ratio')
    axes[0,1].set_title(f'efficiency_ratio R²={ratio_r2:.3f}'); axes[0,1].grid(alpha=0.3)

    axes[0,2].plot(history.history['loss'],     label='訓練損失')
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
    axes[1,2].hist(ratio_pred, bins=50, alpha=0.5, color='orange', label='預測')
    axes[1,2].set_xlabel('efficiency_ratio')
    axes[1,2].set_title('efficiency_ratio 分布比較')
    axes[1,2].legend(); axes[1,2].grid(alpha=0.3)

    plt.tight_layout()
    plot_path = os.path.join(output_dir, 'anfis_v4_1_analysis.png')
    plt.savefig(plot_path, dpi=150, bbox_inches='tight')
    print(f"\n圖表: {plot_path}")
    plt.close()

    # ── 儲存
    model_path  = os.path.join(output_dir, 'anfis_v4_1.keras')
    scaler_path = os.path.join(output_dir, 'scaler_X_v4_1.save')
    config_path = os.path.join(output_dir, 'model_config_v4_1.json')

    config = {
        'model_version':    'v4.1',
        'target':           'efficiency_ratio = power_W / illumination',
        'feature_columns':  feature_columns,
        'input_dim':        len(feature_columns),
        'num_mfs':          NUM_MFS,
        'output_activation': 'softplus',
        'weight_mode':      weight_mode,
        'weight_alpha':     weight_alpha,
        'illum_min':        illum_min,
        'training_date':    datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        'performance_watts': {
            'rmse': rmse, 'mae': mae, 'r2': r2, 'mape': mape,
            'by_range': range_results,
        },
        'performance_ratio': {
            'rmse': ratio_rmse, 'r2': ratio_r2,
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

    return {
        'model': model,
        'scaler_X': scaler_X,
        'feature_columns': feature_columns,
        'performance': {'rmse': rmse, 'mae': mae, 'r2': r2, 'mape': mape},
        'range_results': range_results,
        'ranking_mode_a': ranking_a,
        'ranking_mode_b': ranking_b,
        'weight_mode': weight_mode,
        'weight_alpha': weight_alpha,
        'has_illumination': True,
    }


if __name__ == '__main__':
    import argparse

    parser = argparse.ArgumentParser(description='ANFIS v4.1 訓練（softplus + watts-MSE + ranking metrics）')
    parser.add_argument('file_path',       nargs='?', help='資料集 CSV 路徑')
    parser.add_argument('--output-dir',    default=None)
    parser.add_argument('--weight-mode',   default='watts',
                        choices=['watts', 'ratio', 'power_alpha'],
                        help='樣本加權模式（預設 watts）')
    parser.add_argument('--weight-alpha',  type=float, default=0.0,
                        help='power_alpha 模式下的加權強度')
    parser.add_argument('--illum-min',     type=float, default=50.0,
                        help='最小照度門檻 W/m²（預設 50）')
    parser.add_argument('--skip-mode-b',   action='store_true',
                        help='跳過 Mode B 連續網格評估（加速）')
    args = parser.parse_args()

    main(
        file_path=args.file_path,
        output_dir=args.output_dir,
        weight_mode=args.weight_mode,
        weight_alpha=args.weight_alpha,
        illum_min=args.illum_min,
        skip_mode_b=args.skip_mode_b,
    )
