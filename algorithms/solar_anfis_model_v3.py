#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
solar_anfis_model_v3.py
=======================
相較 v2 的改動：

1. [樣本加權] weight_alpha 可由外部傳入（預設 0.7）
   - alpha=0  → 不加權（等同 v2 無加權版）
   - alpha=0.5 → 溫和加權
   - alpha=0.7 → v2 預設值
   - alpha=1.0 → 線性加權（高功率樣本權重最大）
   公式：w_i = clip( (P_i / P̄)^alpha, 0.2, 5.0 )

2. [新增特徵] 若資料集有以下欄位，自動納入：
   - theoretical_poa   → 理論平面輻射量（W/m²），直接加入（ScalerX 會標準化）
   - solar_zenith      → 推導 solar_elevation = 90 - zenith，取 sin/cos

3. [訓練記錄] model_config.json 記錄 weight_alpha 與特徵列表
   方便跨 run 比較結果

透過 train_pipeline.py 呼叫（加 --model v3 --weight-alpha 0.7）或直接執行。
"""

import os
os.environ['TF_CPP_MIN_LOG_LEVEL'] = '2'

import tensorflow as tf

# GPU 設定
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


def setup_chinese_font():
    for font in ['DFKai-SB', 'Microsoft JhengHei', 'Microsoft YaHei',
                 'KaiTi', 'SimHei', 'Arial Unicode MS']:
        try:
            fm.findfont(fm.FontProperties(family=font))
            plt.rcParams['font.family'] = font
            plt.rcParams['axes.unicode_minus'] = False
            return
        except:
            continue


# ════════════════════════════════════════════════════════════════
# ANFIS 模型（與 v2 相同架構）
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
    output = Dense(1, activation='relu')(x)
    model = Model(inputs=inputs, outputs=output)
    model.compile(optimizer=Adam(learning_rate=0.001), loss='mse', metrics=['mae'])
    return model


# ════════════════════════════════════════════════════════════════
# v3 特徵工程（比 v2 多 theoretical_poa 和 solar_elevation）
# ════════════════════════════════════════════════════════════════
def create_features_v3(df):
    """
    v3 特徵集：
      基礎（8維）：hour_sin/cos, day_sin/cos, tilt_sin/cos, azimuth_sin/cos
      可選：illumination, theoretical_poa, solar_elev_sin, solar_elev_cos
    """
    print("\n=== v3 特徵工程 ===")

    # 時間循環
    df['hour_sin'] = np.sin(2 * np.pi * df['hour_decimal'] / 24)
    df['hour_cos'] = np.cos(2 * np.pi * df['hour_decimal'] / 24)
    df['day_sin']  = np.sin(2 * np.pi * df['day_of_year'] / 365)
    df['day_cos']  = np.cos(2 * np.pi * df['day_of_year'] / 365)

    # 角度 sin/cos
    df['tilt_sin']     = np.sin(np.radians(df['tilt_angle']))
    df['tilt_cos']     = np.cos(np.radians(df['tilt_angle']))
    df['azimuth_sin']  = np.sin(np.radians(df['azimuth_angle']))
    df['azimuth_cos']  = np.cos(np.radians(df['azimuth_angle']))

    feature_columns = [
        'hour_sin', 'hour_cos', 'day_sin', 'day_cos',
        'tilt_sin', 'tilt_cos', 'azimuth_sin', 'azimuth_cos'
    ]

    # ── 照度（同 v2）
    has_illumination = False
    if 'illumination' in df.columns and df['illumination'].notna().sum() > 0:
        has_illumination = True
        feature_columns.append('illumination')
        print(f"  ✅ illumination: {df['illumination'].min():.1f}–{df['illumination'].max():.1f} W/m²")
    else:
        print("  ⚠️  illumination 不可用")

    # ── [v3 新增] theoretical_poa：理論平面輻射量
    has_poa = False
    if 'theoretical_poa' in df.columns:
        valid = df['theoretical_poa'].notna() & (df['theoretical_poa'] > 0)
        if valid.sum() > 0:
            has_poa = True
            feature_columns.append('theoretical_poa')
            print(f"  ✅ theoretical_poa: {df['theoretical_poa'].min():.1f}–{df['theoretical_poa'].max():.1f} W/m²  [v3 新增]")
        else:
            print("  ⚠️  theoretical_poa 全為 0 或空值，跳過")
    else:
        print("  ⚠️  theoretical_poa 欄位不存在")

    # ── [v3 新增] solar_elevation = 90 - solar_zenith，取 sin/cos
    has_solar_elev = False
    if 'solar_zenith' in df.columns and df['solar_zenith'].notna().sum() > 0:
        df['solar_elevation'] = 90.0 - df['solar_zenith']
        df['solar_elev_sin']  = np.sin(np.radians(df['solar_elevation']))
        df['solar_elev_cos']  = np.cos(np.radians(df['solar_elevation']))
        has_solar_elev = True
        feature_columns += ['solar_elev_sin', 'solar_elev_cos']
        print(f"  ✅ solar_elevation sin/cos（由 solar_zenith 推導）  [v3 新增]")
    else:
        print("  ⚠️  solar_zenith 不可用，跳過太陽高度角特徵")

    print(f"\n  特徵維度: {len(feature_columns)}  ({' | '.join(feature_columns)})")

    return df, feature_columns, has_illumination, has_poa, has_solar_elev


# ════════════════════════════════════════════════════════════════
# 樣本加權（可設定 alpha）
# ════════════════════════════════════════════════════════════════
def compute_sample_weights(y, alpha: float = 0.7,
                           w_min: float = 0.2, w_max: float = 5.0) -> np.ndarray:
    """
    w_i = clip( (P_i / P̄)^alpha, w_min, w_max )
    alpha=0 → 全部權重=1（不加權）
    alpha=1 → 線性加權
    """
    if alpha == 0:
        return np.ones(len(y))
    p_mean = y.mean() + 1e-8
    weights = np.power(y / p_mean, alpha)
    return np.clip(weights, w_min, w_max)


def print_weight_distribution(weights, y):
    """印出各功率區間的平均權重（供對比用）"""
    ranges = [(0, 50), (50, 100), (100, 200), (200, 300), (300, 1e9)]
    labels = ['<50W', '50-100W', '100-200W', '200-300W', '>300W']
    print("\n  功率區間平均權重：")
    for (lo, hi), label in zip(ranges, labels):
        mask = (y >= lo) & (y < hi)
        n = mask.sum()
        if n > 0:
            w_avg = weights[mask].mean()
            print(f"    {label:12s}: 樣本數 {n:6,}  平均權重 {w_avg:.3f}")


# ════════════════════════════════════════════════════════════════
# 分範圍評估
# ════════════════════════════════════════════════════════════════
def evaluate_by_range(y_true, y_pred):
    ranges = [(0, 100), (100, 200), (200, 300), (300, 1e9)]
    labels = ['0-100W', '100-200W', '200-300W', '>300W']
    results = {}
    print("\n=== 分範圍評估 ===")
    for (lo, hi), label in zip(ranges, labels):
        mask = (y_true >= lo) & (y_true < hi)
        n = mask.sum()
        if n > 10:
            mae = mean_absolute_error(y_true[mask], y_pred[mask])
            r2  = r2_score(y_true[mask], y_pred[mask])
            print(f"  {label:10s}: n={n:6,}  MAE={mae:6.1f}W  R²={r2:+.3f}")
            results[label] = {'n': int(n), 'mae': float(mae), 'r2': float(r2)}
        else:
            print(f"  {label:10s}: 樣本數不足（{n}），跳過")
    return results


# ════════════════════════════════════════════════════════════════
# 主函式
# ════════════════════════════════════════════════════════════════
def main(file_path=None, output_dir=None, weight_alpha: float = 0.7):
    print(f"=== ANFIS v3 訓練啟動（weight_alpha={weight_alpha}）===")
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

    # ── 必要欄位檢查
    required = ['day_of_year', 'hour_decimal', 'tilt_angle', 'azimuth_angle', 'power_W']
    missing = [c for c in required if c not in df.columns]
    if missing:
        print(f"❌ 缺少欄位: {missing}")
        return None

    for col in required:
        df[col] = pd.to_numeric(df[col], errors='coerce')
    if 'illumination' in df.columns:
        df['illumination'] = pd.to_numeric(df['illumination'], errors='coerce')
    if 'theoretical_poa' in df.columns:
        df['theoretical_poa'] = pd.to_numeric(df['theoretical_poa'], errors='coerce')

    df = df.dropna(subset=required)
    print(f"清理後: {len(df):,} 筆")

    # ── v3 特徵工程
    df, feature_columns, has_illumination, has_poa, has_solar_elev = create_features_v3(df)

    # ── 移除特徵欄位有空值的資料
    df = df.dropna(subset=[c for c in feature_columns if c in df.columns])
    print(f"特徵完整後: {len(df):,} 筆")

    # ── 數據統計
    X = df[feature_columns].values
    y = df['power_W'].values
    print(f"\n功率範圍: {y.min():.1f}–{y.max():.1f}W  平均: {y.mean():.1f}W")

    # 功率分布
    print("\n功率分布：")
    for lo, hi, label in [(0,50,'<50W'),(50,100,'50-100W'),(100,200,'100-200W'),(200,300,'200-300W'),(300,1e9,'>300W')]:
        n = ((y >= lo) & (y < hi)).sum()
        print(f"  {label:10s}: {n:,} ({n/len(y)*100:.1f}%)")

    # ── 分割
    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=0.2, random_state=42
    )

    # ── 標準化
    scaler_X = MinMaxScaler(feature_range=(-1, 1))
    X_train_scaled = scaler_X.fit_transform(X_train)
    X_test_scaled  = scaler_X.transform(X_test)

    print(f"\n訓練集: {len(X_train):,}  測試集: {len(X_test):,}")

    # ── 建模
    NUM_MFS = 7
    print(f"\n建立 ANFIS 模型（輸入維度={X_train_scaled.shape[1]}, MF={NUM_MFS}）")
    model = build_anfis_model(input_dim=X_train_scaled.shape[1], num_mfs=NUM_MFS)
    model.summary()

    # ── 輸出目錄
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

    # ── [v3 核心] 樣本加權
    print(f"\n=== 樣本加權（weight_alpha={weight_alpha}）===")
    sample_weights = compute_sample_weights(y_train, alpha=weight_alpha)
    print_weight_distribution(sample_weights, y_train)
    if weight_alpha == 0:
        print("  ℹ️  alpha=0，不加權（等同標準訓練）")

    # ── 訓練
    print(f"\n=== 開始訓練 ===")
    history = model.fit(
        X_train_scaled, y_train,
        epochs=800,
        batch_size=1024,
        validation_split=0.2,
        callbacks=callbacks,
        sample_weight=sample_weights,
        verbose=1
    )

    # ── 評估
    print(f"\n=== 整體評估 ===")
    y_pred = np.maximum(0, model.predict(X_test_scaled, verbose=0).flatten())
    rmse = float(np.sqrt(mean_squared_error(y_test, y_pred)))
    mae  = float(mean_absolute_error(y_test, y_pred))
    r2   = float(r2_score(y_test, y_pred))
    mape_mask = y_test > 1e-8
    mape = float(np.mean(np.abs((y_test[mape_mask] - y_pred[mape_mask]) /
                                y_test[mape_mask])) * 100) if mape_mask.sum() else float('inf')

    print(f"  RMSE={rmse:.2f}W  MAE={mae:.2f}W  R²={r2:.4f}  MAPE={mape:.2f}%")

    range_results = evaluate_by_range(y_test, y_pred)

    # ── 圖表
    fig, axes = plt.subplots(2, 3, figsize=(18, 12))
    fig.suptitle(f'ANFIS v3  weight_alpha={weight_alpha}  R²={r2:.3f}', fontsize=14)

    axes[0,0].scatter(y_test, y_pred, alpha=0.3, s=1)
    axes[0,0].plot([0, y_test.max()], [0, y_test.max()], 'r--')
    axes[0,0].set_xlabel('實際 (W)'); axes[0,0].set_ylabel('預測 (W)')
    axes[0,0].set_title(f'預測 vs 實際 R²={r2:.3f}'); axes[0,0].grid(alpha=0.3)

    residuals = y_pred - y_test
    axes[0,1].scatter(y_pred, residuals, alpha=0.3, s=1)
    axes[0,1].axhline(0, color='r', linestyle='--')
    axes[0,1].set_xlabel('預測 (W)'); axes[0,1].set_ylabel('殘差 (W)')
    axes[0,1].set_title('殘差分析'); axes[0,1].grid(alpha=0.3)

    axes[0,2].plot(history.history['loss'],     label='訓練損失')
    axes[0,2].plot(history.history['val_loss'], label='驗證損失')
    axes[0,2].set_title('訓練曲線'); axes[0,2].legend(); axes[0,2].grid(alpha=0.3)

    axes[1,0].hist(residuals, bins=50, alpha=0.7)
    axes[1,0].axvline(0, color='r', linestyle='--')
    axes[1,0].set_title(f'殘差分布 MAE={mae:.1f}W'); axes[1,0].grid(alpha=0.3)

    # 各功率區間 R²（v3 新增）
    range_labels = list(range_results.keys())
    range_r2s    = [range_results[k]['r2'] for k in range_labels]
    colors = ['#e74c3c' if v < 0 else '#2ecc71' for v in range_r2s]
    axes[1,1].bar(range_labels, range_r2s, color=colors)
    axes[1,1].axhline(0, color='black', linewidth=0.8)
    axes[1,1].set_title('各功率區間 R²（紅=負，綠=正）')
    axes[1,1].set_ylabel('R²'); axes[1,1].grid(alpha=0.3)

    # 樣本加權分布
    bins = np.arange(0, y_train.max() + 20, 20)
    bin_centers = (bins[:-1] + bins[1:]) / 2
    for lo, hi in zip(bins[:-1], bins[1:]):
        mask = (y_train >= lo) & (y_train < hi)
        if mask.sum() > 0:
            w_avg = sample_weights[mask].mean()
            axes[1,2].bar(lo, w_avg, width=18, color='steelblue', alpha=0.7)
    axes[1,2].set_xlabel('功率 (W)'); axes[1,2].set_ylabel('平均樣本權重')
    axes[1,2].set_title(f'樣本加權分布 alpha={weight_alpha}')
    axes[1,2].axhline(1.0, color='r', linestyle='--', label='無加權基準')
    axes[1,2].legend(); axes[1,2].grid(alpha=0.3)

    plt.tight_layout()
    suffix = "with_illumination" if has_illumination else "without_illumination"
    plot_path = os.path.join(output_dir, f'anfis_v3_{suffix}_alpha{weight_alpha:.1f}_analysis.png')
    plt.savefig(plot_path, dpi=150, bbox_inches='tight')
    print(f"\n圖表: {plot_path}")
    plt.show()

    # ── 儲存模型
    model_path  = os.path.join(output_dir, f'anfis_v3_{suffix}.keras')
    scaler_path = os.path.join(output_dir, f'scaler_X_v3_{suffix}.save')
    config_path = os.path.join(output_dir, f'model_config_v3_{suffix}.json')

    config = {
        'model_version':   'v3',
        'has_illumination': has_illumination,
        'has_poa':          has_poa,
        'has_solar_elev':   has_solar_elev,
        'feature_columns':  feature_columns,
        'input_dim':        len(feature_columns),
        'num_mfs':          NUM_MFS,
        'weight_alpha':     weight_alpha,
        'training_date':    datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        'performance': {
            'rmse': rmse, 'mae': mae, 'r2': r2, 'mape': mape,
            'by_range': range_results,
        }
    }
    with open(config_path, 'w', encoding='utf-8') as f:
        json.dump(config, f, indent=2, ensure_ascii=False)

    model.save(model_path)
    joblib.dump(scaler_X, scaler_path)

    print(f"\n=== 模型已儲存 ===")
    print(f"  模型:    {model_path}")
    print(f"  Scaler:  {scaler_path}")
    print(f"  Config:  {config_path}")

    return {
        'model': model,
        'scaler_X': scaler_X,
        'has_illumination': has_illumination,
        'feature_columns': feature_columns,
        'performance': {'rmse': rmse, 'mae': mae, 'r2': r2, 'mape': mape},
        'range_results': range_results,
        'weight_alpha': weight_alpha,
    }


if __name__ == '__main__':
    import sys
    import argparse

    parser = argparse.ArgumentParser(description='ANFIS v3 訓練')
    parser.add_argument('file_path',    nargs='?', help='資料集 CSV 路徑')
    parser.add_argument('--output-dir', default=None)
    parser.add_argument('--weight-alpha', type=float, default=0.7,
                        help='樣本加權強度（0=不加權, 0.7=預設, 1.0=線性）')
    args = parser.parse_args()

    result = main(
        file_path=args.file_path,
        output_dir=args.output_dir,
        weight_alpha=args.weight_alpha,
    )
