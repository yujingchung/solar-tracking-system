#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
solar_anfis_model_v4.py
=======================
相較 v3 的改動：

**核心思路：消除照度主導效應**

v2/v3 的問題：power_W 90%+ 的變異來自照度（幾點、天氣），
角度差異只有 10-20%，模型學到的全是「時間→功率」，
per-range R² 全負就是這個原因。

v4 解法：把 target 換成效率比（幾何捕獲效率）：
    target = power_W / illumination   (無因次，~0.0–0.4)

這樣照度的主導效應被除掉，剩下的是：
「這個角度在這個時間點能捕獲多少比例的可用光」
不同角度的差異在這個 target 上會放大 5-10 倍，角度信號才看得見。

改動摘要：
1. [Target] power_W → power_W / illumination（需過濾 illumination < 10 W/m²）
2. [特徵]  回到乾淨 8 維：hour_sin/cos, day_sin/cos, tilt_sin/cos, azimuth_sin/cos
           不放 illumination（已在 target 分母）、不放 theoretical_poa、不放 solar_elev
3. [評估]  預測的是 efficiency_ratio，乘回 illumination 換算成瓦特再算 R²/RMSE/MAE
4. [加權]  預設不加權（alpha=0），因為 target 已相對均勻；可用 --weight-alpha > 0 開啟

使用方式：
    python train_pipeline.py --skip-preprocess --dataset ds02_20260506_含照度 --model v4
    python solar_anfis_model_v4.py datasets/ds02_20260506_含照度/data.csv
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
# ANFIS 模型（架構與 v2/v3 相同）
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
    # sigmoid 輸出，效率比不應超過 1
    output = Dense(1, activation='sigmoid')(x)
    model = Model(inputs=inputs, outputs=output)
    model.compile(optimizer=Adam(learning_rate=0.001), loss='mse', metrics=['mae'])
    return model


# ════════════════════════════════════════════════════════════════
# v4 特徵工程
# ════════════════════════════════════════════════════════════════
def create_features_v4(df, illum_min: float = 10.0):
    """
    v4 特徵集：純 8 維幾何特徵（不放照度）
    target：efficiency_ratio = power_W / illumination

    illum_min：照度低於此值的資料列會被過濾（避免除以近零值）
    """
    print("\n=== v4 特徵工程 ===")

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

    # ── 建立 efficiency_ratio target
    if 'illumination' not in df.columns or df['illumination'].notna().sum() == 0:
        print("  ❌ illumination 欄位不存在或全為空，v4 無法執行")
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
    print(f"  efficiency_ratio 範圍：{ratio_min:.4f}–{ratio_max:.4f}  平均：{ratio_mean:.4f}")
    print(f"  (相當於 {ratio_mean*100:.1f}% 捕獲效率，max {ratio_max*100:.1f}%)")

    print(f"\n  特徵維度: {len(feature_columns)}  ({' | '.join(feature_columns)})")
    print(f"  Target: efficiency_ratio = power_W / illumination")

    return df, feature_columns, 'efficiency_ratio'


# ════════════════════════════════════════════════════════════════
# 樣本加權（可選，預設不加權）
# ════════════════════════════════════════════════════════════════
def compute_sample_weights(y, alpha: float = 0.0,
                           w_min: float = 0.2, w_max: float = 5.0) -> np.ndarray:
    if alpha == 0:
        return np.ones(len(y))
    p_mean = y.mean() + 1e-8
    weights = np.power(y / p_mean, alpha)
    return np.clip(weights, w_min, w_max)


# ════════════════════════════════════════════════════════════════
# 分功率區間評估（back-transform 回瓦特）
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
# 主函式
# ════════════════════════════════════════════════════════════════
def main(file_path=None, output_dir=None, weight_alpha: float = 0.0,
         illum_min: float = 10.0):
    print(f"=== ANFIS v4 訓練啟動（target=efficiency_ratio, weight_alpha={weight_alpha}）===")
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

    # ── 必要欄位
    required = ['day_of_year', 'hour_decimal', 'tilt_angle', 'azimuth_angle',
                'power_W', 'illumination']
    missing = [c for c in required if c not in df.columns]
    if missing:
        print(f"❌ 缺少欄位: {missing}")
        return None

    for col in required:
        df[col] = pd.to_numeric(df[col], errors='coerce')
    df = df.dropna(subset=required)
    print(f"清理後: {len(df):,} 筆")

    # ── v4 特徵工程（含 efficiency_ratio 計算）
    result = create_features_v4(df, illum_min=illum_min)
    if result[0] is None:
        return None
    df, feature_columns, target_col = result

    # ── 移除特徵空值
    df = df.dropna(subset=feature_columns + [target_col, 'illumination', 'power_W'])
    print(f"最終資料: {len(df):,} 筆")

    # ── 功率分布（以瓦特顯示，方便和 v2/v3 比較）
    y_power = df['power_W'].values
    print(f"\n功率範圍（W）: {y_power.min():.1f}–{y_power.max():.1f}  平均: {y_power.mean():.1f}")
    print("\n功率分布：")
    for lo, hi, label in [(0,50,'<50W'),(50,100,'50-100W'),(100,200,'100-200W'),
                           (200,300,'200-300W'),(300,1e9,'>300W')]:
        n = ((y_power >= lo) & (y_power < hi)).sum()
        print(f"  {label:10s}: {n:,} ({n/len(y_power)*100:.1f}%)")

    # efficiency_ratio 分布
    y = df[target_col].values.astype('float32')
    illum_vals = df['illumination'].values.astype('float32')
    X = df[feature_columns].values.astype('float32')

    print(f"\nefficiency_ratio 分布：")
    for lo, hi, label in [(0,0.1,'<0.10'),(0.1,0.2,'0.10-0.20'),(0.2,0.3,'0.20-0.30'),
                           (0.3,0.4,'0.30-0.40'),(0.4,1.0,'>0.40')]:
        n = ((y >= lo) & (y < hi)).sum()
        print(f"  {label:12s}: {n:,} ({n/len(y)*100:.1f}%)")

    # ── 分割（按照度保留對應值）
    idx = np.arange(len(X))
    idx_train, idx_test = train_test_split(idx, test_size=0.2, random_state=42)

    X_train, X_test       = X[idx_train], X[idx_test]
    y_train, y_test       = y[idx_train], y[idx_test]
    illum_train           = illum_vals[idx_train]
    illum_test            = illum_vals[idx_test]
    y_power_test          = y_power[idx_test]

    # ── 標準化（特徵）
    scaler_X = MinMaxScaler(feature_range=(-1, 1))
    X_train_scaled = scaler_X.fit_transform(X_train)
    X_test_scaled  = scaler_X.transform(X_test)

    print(f"\n訓練集: {len(X_train):,}  測試集: {len(X_test):,}")

    # ── 建模
    NUM_MFS = 7
    print(f"\n建立 ANFIS v4 模型（輸入維度={X_train_scaled.shape[1]}, MF={NUM_MFS}）")
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

    # ── 樣本加權（對 efficiency_ratio 加權，預設不加權）
    sample_weights = compute_sample_weights(y_train, alpha=weight_alpha)
    if weight_alpha > 0:
        print(f"\n=== 樣本加權（alpha={weight_alpha}，對 efficiency_ratio）===")
        ranges = [(0,0.1),(0.1,0.2),(0.2,0.3),(0.3,1.0)]
        labels = ['<0.10','0.10-0.20','0.20-0.30','>0.30']
        for (lo,hi),lab in zip(ranges,labels):
            mask = (y_train >= lo) & (y_train < hi)
            if mask.sum() > 0:
                print(f"  {lab:12s}: n={mask.sum():,}  avg_w={sample_weights[mask].mean():.3f}")
    else:
        print(f"\n樣本加權：關閉（alpha=0）")

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

    # ── 評估（efficiency_ratio 空間）
    ratio_pred = np.clip(model.predict(X_test_scaled, verbose=0).flatten(), 0, 1)

    # Back-transform：乘回照度，回到瓦特空間
    y_power_pred = ratio_pred * illum_test

    print(f"\n=== 整體評估（瓦特空間，與 v2/v3 可比）===")
    rmse = float(np.sqrt(mean_squared_error(y_power_test, y_power_pred)))
    mae  = float(mean_absolute_error(y_power_test, y_power_pred))
    r2   = float(r2_score(y_power_test, y_power_pred))
    mape_mask = y_power_test > 1e-8
    mape = float(np.mean(np.abs((y_power_test[mape_mask] - y_power_pred[mape_mask]) /
                                 y_power_test[mape_mask])) * 100) if mape_mask.sum() else float('inf')
    print(f"  RMSE={rmse:.2f}W  MAE={mae:.2f}W  R²={r2:.4f}  MAPE={mape:.2f}%")

    # efficiency_ratio 空間評估
    ratio_rmse = float(np.sqrt(mean_squared_error(y_test, ratio_pred)))
    ratio_r2   = float(r2_score(y_test, ratio_pred))
    print(f"\n  efficiency_ratio 空間：RMSE={ratio_rmse:.4f}  R²={ratio_r2:.4f}")

    range_results = evaluate_by_range(y_power_test, y_power_pred)

    # ── 圖表（6 張）
    fig, axes = plt.subplots(2, 3, figsize=(18, 12))
    fig.suptitle(f'ANFIS v4  target=efficiency_ratio  R²(W)={r2:.3f}', fontsize=14)

    # 1. 瓦特空間預測 vs 實際
    axes[0,0].scatter(y_power_test, y_power_pred, alpha=0.3, s=1)
    axes[0,0].plot([0, y_power_test.max()], [0, y_power_test.max()], 'r--')
    axes[0,0].set_xlabel('實際功率 (W)'); axes[0,0].set_ylabel('預測功率 (W)')
    axes[0,0].set_title(f'預測 vs 實際（W）R²={r2:.3f}'); axes[0,0].grid(alpha=0.3)

    # 2. efficiency_ratio 預測 vs 實際
    axes[0,1].scatter(y_test, ratio_pred, alpha=0.3, s=1, color='orange')
    axes[0,1].plot([0, y_test.max()], [0, y_test.max()], 'r--')
    axes[0,1].set_xlabel('實際 efficiency_ratio'); axes[0,1].set_ylabel('預測 efficiency_ratio')
    axes[0,1].set_title(f'efficiency_ratio R²={ratio_r2:.3f}'); axes[0,1].grid(alpha=0.3)

    # 3. 訓練曲線
    axes[0,2].plot(history.history['loss'],     label='訓練損失')
    axes[0,2].plot(history.history['val_loss'], label='驗證損失')
    axes[0,2].set_title('訓練曲線'); axes[0,2].legend(); axes[0,2].grid(alpha=0.3)

    # 4. 殘差分布（瓦特）
    residuals_W = y_power_pred - y_power_test
    axes[1,0].hist(residuals_W, bins=50, alpha=0.7)
    axes[1,0].axvline(0, color='r', linestyle='--')
    axes[1,0].set_title(f'殘差分布（W）MAE={mae:.1f}W'); axes[1,0].grid(alpha=0.3)

    # 5. 各功率區間 R²（關鍵診斷圖）
    if range_results:
        range_labels = list(range_results.keys())
        range_r2s    = [range_results[k]['r2'] for k in range_labels]
        colors = ['#e74c3c' if v < 0 else '#2ecc71' for v in range_r2s]
        axes[1,1].bar(range_labels, range_r2s, color=colors)
        axes[1,1].axhline(0, color='black', linewidth=0.8)
        axes[1,1].set_title('各功率區間 R²（紅=負，綠=正）')
        axes[1,1].set_ylabel('R²'); axes[1,1].grid(alpha=0.3)

    # 6. efficiency_ratio 分布（確認 target 分布）
    axes[1,2].hist(y, bins=50, alpha=0.7, color='steelblue', label='真實')
    axes[1,2].hist(ratio_pred, bins=50, alpha=0.5, color='orange', label='預測')
    axes[1,2].set_xlabel('efficiency_ratio')
    axes[1,2].set_title('efficiency_ratio 分布比較')
    axes[1,2].legend(); axes[1,2].grid(alpha=0.3)

    plt.tight_layout()
    plot_path = os.path.join(output_dir, f'anfis_v4_analysis.png')
    plt.savefig(plot_path, dpi=150, bbox_inches='tight')
    print(f"\n圖表: {plot_path}")
    plt.show()

    # ── 儲存模型
    model_path  = os.path.join(output_dir, 'anfis_v4_efficiency_ratio.keras')
    scaler_path = os.path.join(output_dir, 'scaler_X_v4.save')
    config_path = os.path.join(output_dir, 'model_config_v4.json')

    config = {
        'model_version':    'v4',
        'target':           'efficiency_ratio = power_W / illumination',
        'feature_columns':  feature_columns,
        'input_dim':        len(feature_columns),
        'num_mfs':          NUM_MFS,
        'weight_alpha':     weight_alpha,
        'illum_min':        illum_min,
        'training_date':    datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        'performance_watts': {
            'rmse': rmse, 'mae': mae, 'r2': r2, 'mape': mape,
            'by_range': range_results,
        },
        'performance_ratio': {
            'rmse': ratio_rmse, 'r2': ratio_r2,
        }
    }
    with open(config_path, 'w', encoding='utf-8') as f:
        json.dump(config, f, indent=2, ensure_ascii=False)

    model.save(model_path)
    joblib.dump(scaler_X, scaler_path)

    print(f"\n=== 模型已儲存 ===")
    print(f"  模型:   {model_path}")
    print(f"  Scaler: {scaler_path}")
    print(f"  Config: {config_path}")

    # ── 推論範例（供控制器參考）
    print(f"""
=== 控制器推論方式（v4）===
  # 1. 對每個候選角度建立特徵向量
  # 2. model 輸出 efficiency_ratio（0~1）
  # 3. 乘以當前照度 → 預測功率
  # 4. 選 efficiency_ratio 最大的角度

  predicted_ratio = model.predict(X_scaled)        # shape: (N, 1)
  predicted_power = predicted_ratio * illumination  # back-transform
  best_angle_idx  = np.argmax(predicted_ratio)      # 用 ratio 就夠，不需乘照度
""")

    return {
        'model': model,
        'scaler_X': scaler_X,
        'feature_columns': feature_columns,
        'performance': {'rmse': rmse, 'mae': mae, 'r2': r2, 'mape': mape},
        'range_results': range_results,
        'weight_alpha': weight_alpha,
        'has_illumination': True,
    }


if __name__ == '__main__':
    import argparse

    parser = argparse.ArgumentParser(description='ANFIS v4 訓練（target=efficiency_ratio）')
    parser.add_argument('file_path',       nargs='?', help='資料集 CSV 路徑')
    parser.add_argument('--output-dir',    default=None)
    parser.add_argument('--weight-alpha',  type=float, default=0.0,
                        help='樣本加權強度（0=不加權預設, 0.7=強加權）')
    parser.add_argument('--illum-min',     type=float, default=10.0,
                        help='最小照度門檻 W/m²（低於此值過濾，預設 10）')
    args = parser.parse_args()

    main(
        file_path=args.file_path,
        output_dir=args.output_dir,
        weight_alpha=args.weight_alpha,
        illum_min=args.illum_min,
    )
