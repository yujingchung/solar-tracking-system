# ===== 環境設定 =====
import os

os.environ['TF_CPP_MIN_LOG_LEVEL'] = '2'

# ===== 🔥 GPU 加速配置 =====
import tensorflow as tf

# 🔥🔥🔥 GPU 加速配置（加在這裡）
print("\n" + "=" * 60)
print("🚀 GPU 加速初始化")
print("=" * 60)

gpus = tf.config.list_physical_devices('GPU')
if gpus:
    try:
        # GPU 記憶體動態增長
        for gpu in gpus:
            tf.config.experimental.set_memory_growth(gpu, True)

        print(f"✅ GPU: {gpus[0].name}")

        # 🔥 混合精度訓練（關鍵加速）
        # from tensorflow.keras import mixed_precision

        # policy = mixed_precision.Policy('mixed_float16')
        # mixed_precision.set_global_policy(policy)
        # print("✅ FP16 混合精度已啟用")
        # print("   預期加速: 2-3x")

    except Exception as e:
        print(f"GPU 設定警告: {e}")

print("=" * 60 + "\n")

# ===== 導入所需庫 =====
import pandas as pd
import numpy as np
from datetime import datetime
import matplotlib.pyplot as plt
import matplotlib.font_manager as fm
from sklearn.model_selection import train_test_split
from sklearn.preprocessing import MinMaxScaler
import tensorflow as tf
from tensorflow.keras.models import Model
from tensorflow.keras.layers import Input, Dense, Layer, Dropout
from tensorflow.keras.optimizers import Adam
from tensorflow.keras.callbacks import EarlyStopping, ReduceLROnPlateau, ModelCheckpoint
import joblib
import json
from sklearn.metrics import mean_squared_error, mean_absolute_error, r2_score


# 設定中文字體
def setup_chinese_font():
    try:
        plt.rcParams['font.family'] = 'DFKai-SB'
        plt.rcParams['axes.unicode_minus'] = False
        print("使用中文字體: 標楷體")
        return
    except:
        pass

    chinese_fonts = [
        'KaiTi', 'STKaiti', 'Microsoft JhengHei', 'Microsoft YaHei',
        'SimHei', 'SimSun', 'Arial Unicode MS'
    ]

    for font in chinese_fonts:
        try:
            fm.findfont(fm.FontProperties(family=font))
            plt.rcParams['font.family'] = font
            print(f"使用中文字體: {font}")
            break
        except:
            continue


# 改進的模糊層
class SimpleFuzzyLayer(Layer):
    def __init__(self, num_mfs, **kwargs):
        self.num_mfs = num_mfs
        super(SimpleFuzzyLayer, self).__init__(**kwargs)

    def build(self, input_shape):
        # 改進初始化策略
        self.centers = self.add_weight(
            name='centers',
            shape=(input_shape[-1], self.num_mfs),
            initializer=tf.keras.initializers.RandomUniform(minval=-1.5, maxval=1.5),
            trainable=True
        )

        self.sigmas = self.add_weight(
            name='sigmas',
            shape=(input_shape[-1], self.num_mfs),
            initializer=tf.keras.initializers.Constant(0.5),
            trainable=True
        )

        super(SimpleFuzzyLayer, self).build(input_shape)

    def call(self, x):
        expanded_x = tf.expand_dims(x, -1)
        dist = tf.square(expanded_x - self.centers)
        mf_values = tf.exp(-dist / (2 * tf.square(tf.abs(self.sigmas) + 0.1)))
        return mf_values

    def get_config(self):
        # 獲取父類別的配置
        config = super(SimpleFuzzyLayer, self).get_config()

        # 將自定義的參數添加到配置中
        config.update({
            'num_mfs': self.num_mfs,
        })
        return config

    def compute_output_shape(self, input_shape):
        return (input_shape[0], input_shape[1], self.num_mfs)


def build_simple_anfis_model(input_dim, num_mfs=7):
    """建立改進的ANFIS模型"""
    inputs = Input(shape=(input_dim,))

    # 模糊化層
    fuzzified = SimpleFuzzyLayer(num_mfs)(inputs)
    flat_fuzzified = tf.keras.layers.Reshape((input_dim * num_mfs,))(fuzzified)

    # 🔥 增加網絡容量
    x = Dense(128, activation='relu')(flat_fuzzified)  # 64→128
    x = Dropout(0.3)(x)
    x = tf.keras.layers.BatchNormalization()(x)  # 加入BN

    x = Dense(64, activation='relu')(x)  # 32→64
    x = Dropout(0.25)(x)
    x = tf.keras.layers.BatchNormalization()(x)

    x = Dense(32, activation='relu')(x)  # 16→32
    x = Dropout(0.2)(x)

    x = Dense(16, activation='relu')(x)  # 新增一層
    x = Dropout(0.1)(x)

    # 輸出層
    output = Dense(1, activation='relu')(x)

    model = Model(inputs=inputs, outputs=output)

    # 🔥 調整學習率
    model.compile(
        optimizer=Adam(learning_rate=0.001),  # 0.0005→0.001
        loss='mse',
        metrics=['mae', 'mse']
    )

    return model


def create_features_with_illumination(df):
    """創建特徵 - 照度完全可選"""
    print("\n=== 特徵工程（照度可選） ===")

    # 時間循環特徵
    df['hour_sin'] = np.sin(2 * np.pi * df['hour_decimal'] / 24)
    df['hour_cos'] = np.cos(2 * np.pi * df['hour_decimal'] / 24)
    df['day_sin'] = np.sin(2 * np.pi * df['day_of_year'] / 365)
    df['day_cos'] = np.cos(2 * np.pi * df['day_of_year'] / 365)

    # 角度特徵
    df['tilt_sin'] = np.sin(np.radians(df['tilt_angle']))
    df['tilt_cos'] = np.cos(np.radians(df['tilt_angle']))
    df['azimuth_sin'] = np.sin(np.radians(df['azimuth_angle']))
    df['azimuth_cos'] = np.cos(np.radians(df['azimuth_angle']))

    # 特徵列表
    feature_columns = [
        'hour_sin', 'hour_cos', 'day_sin', 'day_cos',
        'tilt_sin', 'tilt_cos', 'azimuth_sin', 'azimuth_cos'
    ]

    # 檢查照度
    has_illumination = False
    if 'illumination' in df.columns:
        valid_illum = df['illumination'].notna().sum()

        if valid_illum > 0:
            has_illumination = True
            feature_columns.append('illumination')
            print(f"✅ 找到照度資料: {valid_illum:,} / {len(df):,} 筆有效")
            print(f"   照度範圍: {df['illumination'].min():.1f} - {df['illumination'].max():.1f}")
        else:
            print("⚠️  照度欄位存在但全部為空值")
    else:
        print("⚠️  找不到照度欄位")

    print(f"\n特徵維度: {len(feature_columns)}")
    print(f"特徵列表: {feature_columns}")

    return df, feature_columns, has_illumination


def analyze_illumination_power_relationship(df, has_illumination):
    """分析照度與發電量的關係"""
    if not has_illumination:
        print("\n=== 跳過照度分析（無照度資料） ===")
        return None

    print("\n=== 照度與發電量關係分析 ===")

    df_with_illum = df[df['illumination'].notna()].copy()

    if len(df_with_illum) == 0:
        print("沒有有效的照度資料可分析")
        return None

    df_with_illum['illum_range'] = pd.cut(
        df_with_illum['illumination'],
        bins=5,
        labels=['很低', '低', '中', '高', '很高']
    )

    illum_power_stats = df_with_illum.groupby('illum_range')['power_W'].agg([
        'count', 'mean', 'std', 'min', 'max'
    ]).round(2)

    print("不同照度範圍的發電量統計：")
    print(illum_power_stats)

    correlation = df_with_illum['illumination'].corr(df_with_illum['power_W'])
    print(f"\n照度與發電量的相關係數: {correlation:.4f}")

    return illum_power_stats


def analyze_data_balance(df):
    """分析數據平衡性"""
    print("\n=== 數據平衡性分析 ===")

    # 按角度組合統計（只顯示原始角度組合）
    original_tilts = [10, 15, 20, 30]
    original_azimuths = [160, 180, 200]

    df_original = df[
        df['tilt_angle'].isin(original_tilts) &
        df['azimuth_angle'].isin(original_azimuths)
        ]

    agg_dict = {'power_W': ['count', 'mean', 'std', 'min', 'max']}
    if 'illumination' in df.columns:
        agg_dict['illumination'] = ['mean', 'std']

    angle_stats = df_original.groupby(['tilt_angle', 'azimuth_angle']).agg(agg_dict).round(2)

    print("原始角度組合統計:")
    print(angle_stats)

    # 功率範圍統計
    power_ranges = [(0, 50), (50, 100), (100, 150), (150, 200), (200, 300), (300, float('inf'))]
    print(f"\n功率範圍分佈:")
    for min_p, max_p in power_ranges:
        mask = (df['power_W'] >= min_p) & (df['power_W'] < max_p)
        count = mask.sum()
        percentage = count / len(df) * 100

        if 'illumination' in df.columns:
            avg_illum = df.loc[mask, 'illumination'].mean() if count > 0 else 0
            print(
                f"{min_p}-{max_p if max_p != float('inf') else '∞'}W: {count:,} 筆 ({percentage:.1f}%), 平均照度: {avg_illum:.1f}")
        else:
            print(f"{min_p}-{max_p if max_p != float('inf') else '∞'}W: {count:,} 筆 ({percentage:.1f}%)")

    return angle_stats


def main(file_path=None):
    print("開始ANFIS模型訓練...")
    setup_chinese_font()

    if file_path is None:
        file_path = input("請輸入數據文件的完整路徑: ")

    # === 1. 載入數據 ===
    print(f"\n載入數據: {file_path}")
    try:
        df = pd.read_csv(file_path)
        print(f"✅ 成功載入 {len(df):,} 筆記錄")
        print(f"數據欄位: {df.columns.tolist()}")
    except Exception as e:
        print(f"❌ 載入失敗: {e}")
        return

    # === 2. 定義必要欄位 ===
    required_columns = [
        'day_of_year',
        'hour_decimal',
        'tilt_angle',
        'azimuth_angle',
        'power_W'
    ]

    missing_columns = [col for col in required_columns if col not in df.columns]

    if missing_columns:
        print(f"❌ 缺少必要欄位: {missing_columns}")
        return

    # === 3. 數據類型轉換 ===
    print(f"\n轉換數據類型...")
    for col in required_columns:
        df[col] = pd.to_numeric(df[col], errors='coerce')

    if 'illumination' in df.columns:
        df['illumination'] = pd.to_numeric(df['illumination'], errors='coerce')

    # === 4. 清理缺失值 ===
    initial_count = len(df)
    df = df.dropna(subset=required_columns)
    removed_count = initial_count - len(df)

    if removed_count > 0:
        print(f"⚠️  移除了 {removed_count:,} 筆必要欄位缺失的資料")
    print(f"✅ 剩餘 {len(df):,} 筆有效記錄")

    # === 6. 創建特徵 ===
    df, feature_columns, has_illumination = create_features_with_illumination(df)

    # === 7. 如果使用照度，移除照度為空的資料 ===
    if has_illumination:
        before_count = len(df)
        df = df.dropna(subset=['illumination'])
        after_count = len(df)

        if before_count > after_count:
            print(f"⚠️  移除了 {before_count - after_count:,} 筆照度缺失的資料")
            print(f"✅ 最終剩餘 {after_count:,} 筆完整資料")

    # === 8. 分析 ===
    illum_stats = analyze_illumination_power_relationship(df, has_illumination)
    angle_stats = analyze_data_balance(df)

    # === 9. 準備訓練資料 ===
    X = df[feature_columns]
    y = df['power_W']

    print(f"\n=== 數據統計 ===")
    print(f"特徵維度: {X.shape}")
    print(f"功率範圍: {y.min():.1f} - {y.max():.1f}W")
    print(f"功率平均: {y.mean():.1f} ± {y.std():.1f}W")
    if has_illumination:
        print(f"照度範圍: {df['illumination'].min():.1f} - {df['illumination'].max():.1f}")

    # === 10. 數據分割 ===
    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=0.2, random_state=42, stratify=None
    )

    # === 11. 特徵標準化 ===
    scaler_X = MinMaxScaler(feature_range=(-1, 1))
    X_train_scaled = scaler_X.fit_transform(X_train)
    X_test_scaled = scaler_X.transform(X_test)

    y_train_original = y_train.values
    y_test_original = y_test.values

    print(f"\n=== 數據分割結果 ===")
    print(f"訓練集: {len(X_train):,} 筆")
    print(f"測試集: {len(X_test):,} 筆")
    print(f"X縮放範圍: [{X_train_scaled.min():.3f}, {X_train_scaled.max():.3f}]")
    print(f"y保持原始範圍: [{y_train_original.min():.1f}, {y_train_original.max():.1f}]W")

    # === 12. 建立模型 ===
    print(f"\n=== 建立ANFIS模型 ===")
    print(f"特徵配置: {'包含照度' if has_illumination else '僅時間+角度'}")
    print(f"輸入維度: {X_train_scaled.shape[1]}")
    NUM_MFS = 7   # 每個輸入變數的高斯歸屬函數數量
    print(f"模糊集數量: {NUM_MFS}")

    anfis_model = build_simple_anfis_model(input_dim=X_train_scaled.shape[1], num_mfs=NUM_MFS)
    anfis_model.summary()

    # === 13. 訓練配置 ===
    output_dir = os.path.dirname(file_path) if os.path.dirname(file_path) else '.'

    callbacks = [
        EarlyStopping(
            monitor='val_loss',
            patience=50,
            restore_best_weights=True,
            verbose=1
        ),
        ReduceLROnPlateau(
            monitor='val_loss',
            patience=20,
            factor=0.5,
            min_lr=1e-7,
            verbose=1
        ),
        ModelCheckpoint(
            filepath=os.path.join(output_dir, 'best_anfis.h5'),
            monitor='val_loss',
            save_best_only=True,
            verbose=1
        )
    ]

    # === 14. 開始訓練 ===
    print(f"\n=== 開始訓練模型 ===")

    # 🔥 Sample Weighting：讓高功率樣本（真正需要選角度的時刻）有更高的訓練權重
    # 低功率時（早晚/陰天）各角度發電量幾乎相同，不需要模型花太多資源在這裡
    # power^0.7：非線性縮放，避免 300W 樣本的權重是 30W 的 1000 倍（太極端）
    sample_weights = np.power(y_train_original / (y_train_original.mean() + 1e-8), 0.7)
    sample_weights = np.clip(sample_weights, 0.2, 5.0)   # 限制在 0.2~5 倍之間
    print(f"樣本權重範圍: {sample_weights.min():.2f} ~ {sample_weights.max():.2f}")
    print(f"低功率(<50W)平均權重 : {sample_weights[y_train_original < 50].mean():.2f}")
    print(f"中功率(100-200W)平均權重: {sample_weights[(y_train_original >= 100) & (y_train_original < 200)].mean():.2f}")
    print(f"高功率(>200W)平均權重 : {sample_weights[y_train_original >= 200].mean():.2f}")

    history = anfis_model.fit(
        X_train_scaled, y_train_original,
        epochs=800,
        batch_size=1024,
        validation_split=0.2,
        callbacks=callbacks,
        sample_weight=sample_weights,   # 🔥 高功率樣本多學幾遍
        verbose=1
    )

    # === 15. 模型評估 ===
    print(f"\n=== 模型評估 ===")
    y_pred = anfis_model.predict(X_test_scaled, verbose=0).flatten()
    y_pred = np.maximum(0, y_pred)

    mse = mean_squared_error(y_test_original, y_pred)
    rmse = np.sqrt(mse)
    mae = mean_absolute_error(y_test_original, y_pred)
    r2 = r2_score(y_test_original, y_pred)

    non_zero_mask = y_test_original > 1e-8
    if non_zero_mask.sum() > 0:
        mape = np.mean(np.abs((y_test_original[non_zero_mask] - y_pred[non_zero_mask]) /
                              y_test_original[non_zero_mask])) * 100
    else:
        mape = float('inf')

    print(f"\n=== 模型性能 ===")
    print(f"特徵配置: {'包含照度特徵' if has_illumination else '僅時間和角度特徵'}")
    print(f"均方根誤差 (RMSE): {rmse:.2f}W")
    print(f"平均絕對誤差 (MAE): {mae:.2f}W")
    print(f"決定係數 (R²): {r2:.4f}")
    print(f"平均絕對百分比誤差 (MAPE): {mape:.2f}%")

    # 按功率範圍評估
    print(f"\n=== 分範圍性能評估 ===")
    power_ranges = [(0, 100), (100, 200), (200, 300), (300, float('inf'))]

    for min_p, max_p in power_ranges:
        mask = (y_test_original >= min_p) & (y_test_original < max_p)
        if mask.sum() > 10:
            range_mae = mean_absolute_error(y_test_original[mask], y_pred[mask])
            range_r2 = r2_score(y_test_original[mask], y_pred[mask])
            range_samples = mask.sum()
            print(
                f"{min_p}-{max_p if max_p != float('inf') else '∞'}W: MAE={range_mae:.1f}W, R²={range_r2:.3f}, 樣本數={range_samples}")

    # 特徵重要性
    print(f"\n=== 特徵統計分析 ===")
    feature_importance = np.abs(X_train_scaled.std(axis=0))
    feature_ranking = sorted(zip(feature_columns, feature_importance),
                             key=lambda x: x[1], reverse=True)

    print("特徵變異度排序：")
    for i, (feature, importance) in enumerate(feature_ranking[:8]):
        print(f"{i + 1}. {feature}: {importance:.4f}")

    # === 16. 繪製分析圖 ===
    fig, axes = plt.subplots(2, 3, figsize=(18, 12))

    # 1. 預測vs實際
    axes[0, 0].scatter(y_test_original, y_pred, alpha=0.3, s=1)
    axes[0, 0].plot([y_test_original.min(), y_test_original.max()],
                    [y_test_original.min(), y_test_original.max()], 'r--', linewidth=2)
    axes[0, 0].set_xlabel('實際發電功率 (W)')
    axes[0, 0].set_ylabel('預測發電功率 (W)')
    axes[0, 0].set_title(f'預測 vs 實際 (R²={r2:.3f})')
    axes[0, 0].grid(True, alpha=0.3)

    # 2. 殘差分析
    residuals = y_pred - y_test_original
    axes[0, 1].scatter(y_pred, residuals, alpha=0.3, s=1)
    axes[0, 1].axhline(y=0, color='r', linestyle='--', linewidth=2)
    axes[0, 1].set_xlabel('預測發電功率 (W)')
    axes[0, 1].set_ylabel('殘差 (W)')
    axes[0, 1].set_title('殘差分析')
    axes[0, 1].grid(True, alpha=0.3)

    # 3. 訓練曲線
    axes[0, 2].plot(history.history['loss'], label='訓練損失', linewidth=2)
    axes[0, 2].plot(history.history['val_loss'], label='驗證損失', linewidth=2)
    axes[0, 2].set_title('訓練過程')
    axes[0, 2].set_xlabel('迭代次數')
    axes[0, 2].set_ylabel('MSE損失')
    axes[0, 2].legend()
    axes[0, 2].grid(True, alpha=0.3)

    # 4. 殘差分佈
    axes[1, 0].hist(residuals, bins=50, alpha=0.7, edgecolor='black')
    axes[1, 0].axvline(x=0, color='r', linestyle='--', linewidth=2)
    axes[1, 0].set_xlabel('殘差 (W)')
    axes[1, 0].set_ylabel('頻率')
    axes[1, 0].set_title(f'殘差分佈 (MAE = {mae:.1f}W)')
    axes[1, 0].grid(True, alpha=0.3)

    # 5. 照度 vs 預測誤差
    if has_illumination:
        test_indices = y_test.index
        test_df = df.loc[test_indices].reset_index(drop=True)
        y_test_reset = y_test.reset_index(drop=True)

        if len(test_df) == len(y_test_reset):
            test_illumination = test_df['illumination'].values
            abs_residuals = np.abs(residuals)
            axes[1, 1].scatter(test_illumination, abs_residuals, alpha=0.3, s=1)
            axes[1, 1].set_xlabel('照度')
            axes[1, 1].set_ylabel('絕對誤差 (W)')
            axes[1, 1].set_title('照度 vs 預測誤差')
            axes[1, 1].grid(True, alpha=0.3)
        else:
            axes[1, 1].text(0.5, 0.5, '索引不匹配', ha='center', va='center',
                            transform=axes[1, 1].transAxes)
    else:
        axes[1, 1].text(0.5, 0.5, '無照度資料', ha='center', va='center',
                        transform=axes[1, 1].transAxes, fontsize=14)

    # 6. 特徵重要性
    features_to_show = [f[0] for f in feature_ranking[:min(8, len(feature_ranking))]]
    importances_to_show = [f[1] for f in feature_ranking[:min(8, len(feature_ranking))]]

    axes[1, 2].barh(features_to_show, importances_to_show)
    axes[1, 2].set_xlabel('變異度')
    axes[1, 2].set_title('特徵重要性')
    axes[1, 2].grid(True, alpha=0.3)

    plt.tight_layout()

    model_suffix = "with_illumination" if has_illumination else "without_illumination"
    plot_path = os.path.join(output_dir, f'anfis_{model_suffix}_analysis.png')
    plt.savefig(plot_path, dpi=300, bbox_inches='tight')
    print(f"\n圖表已保存: {plot_path}")
    plt.show()

    # === 17. 保存模型 ===
    model_path = os.path.join(output_dir, f'anfis_{model_suffix}.h5')
    scaler_x_path = os.path.join(output_dir, f'scaler_X_{model_suffix}.save')
    config_path = os.path.join(output_dir, f'model_config_{model_suffix}.json')

    # 保存配置
    model_config = {
        'has_illumination': has_illumination,
        'feature_columns': feature_columns,
        'input_dim': len(feature_columns),
        'num_mfs': NUM_MFS,   # 實際使用的 MF 數量（build_simple_anfis_model 的 num_mfs 參數）
        'training_date': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        'performance': {
            'rmse': float(rmse),
            'mae': float(mae),
            'r2': float(r2),
            'mape': float(mape)
        }
    }

    with open(config_path, 'w', encoding='utf-8') as f:
        json.dump(model_config, f, indent=2, ensure_ascii=False)

    anfis_model.save(model_path)
    joblib.dump(scaler_X, scaler_x_path)

    print(f"\n=== 模型已保存 ===")
    print(f"模型檔: {model_path}")
    print(f"標準化器: {scaler_x_path}")
    print(f"配置檔: {config_path}")

    # === 18. 創建預測函數 ===
    def predict_power(hour_decimal, day_of_year, tilt_angle, azimuth_angle, illumination=None):
        """
        功率預測函數

        參數:
            hour_decimal: 小時 (0-24)
            day_of_year: 一年中的第幾天 (1-365)
            tilt_angle: 傾角 (度)
            azimuth_angle: 方位角 (度)
            illumination: 照度 (可選，僅當模型有使用照度時需要)

        返回:
            預測功率 (W)
        """
        # 特徵工程
        hour_sin = np.sin(2 * np.pi * hour_decimal / 24)
        hour_cos = np.cos(2 * np.pi * hour_decimal / 24)
        day_sin = np.sin(2 * np.pi * day_of_year / 365)
        day_cos = np.cos(2 * np.pi * day_of_year / 365)
        tilt_sin = np.sin(np.radians(tilt_angle))
        tilt_cos = np.cos(np.radians(tilt_angle))
        azimuth_sin = np.sin(np.radians(azimuth_angle))
        azimuth_cos = np.cos(np.radians(azimuth_angle))

        # 組合特徵
        feature_list = [
            hour_sin, hour_cos, day_sin, day_cos,
            tilt_sin, tilt_cos, azimuth_sin, azimuth_cos
        ]

        # 如果模型使用了照度特徵
        if has_illumination:
            if illumination is None:
                raise ValueError("此模型需要照度參數，請提供 illumination 值")
            feature_list.append(illumination)

        features = np.array([feature_list])
        features_scaled = scaler_X.transform(features)
        pred = anfis_model.predict(features_scaled, verbose=0)

        return max(0.0, float(pred[0][0]))

    # === 19. 完成訊息 ===
    print(f"\n=== 訓練完成 ===")
    if r2 > 0.85:
        print("✅ 模型性能優秀！")
    elif r2 > 0.80:
        print("✅ 模型性能良好！")
    elif r2 > 0.70:
        print("⚠️  模型性能一般")
    else:
        print("❌ 模型性能需要改進")

    print(f"\n使用範例:")
    if has_illumination:
        print("# 使用固定角度，例如 15° 傾角, 180° 方位角")
        print("power = predict_power(hour_decimal=12.5, day_of_year=180,")
        print("                      tilt_angle=15, azimuth_angle=180,")
        print("                      illumination=50000)")
    else:
        print("# 使用固定角度，例如 15° 傾角, 180° 方位角")
        print("power = predict_power(hour_decimal=12.5, day_of_year=180,")
        print("                      tilt_angle=15, azimuth_angle=180)")

    return {
        'model': anfis_model,
        'scaler_X': scaler_X,
        'has_illumination': has_illumination,
        'feature_columns': feature_columns,
        'performance': {'rmse': rmse, 'mae': mae, 'r2': r2, 'mape': mape},
        'predict_function': predict_power
    }


if __name__ == "__main__":
    import sys

    if len(sys.argv) > 1:
        result = main(sys.argv[1])
    else:
        result = main()

    # 如果訓練成功，顯示額外的使用說明
    if result is not None:
        print("\n" + "=" * 60)
        print("📚 模型使用指南")
        print("=" * 60)

        print("\n1️⃣ 載入已訓練的模型:")
        print("```python")
        print("import joblib")
        print("import json")
        print("import numpy as np")
        print("from tensorflow.keras.models import load_model")
        print("")
        print("# 載入配置")
        if result['has_illumination']:
            config_file = 'model_config_with_illumination.json'
            model_file = 'anfis_with_illumination.h5'
            scaler_file = 'scaler_X_with_illumination.save'
        else:
            config_file = 'model_config_without_illumination.json'
            model_file = 'anfis_without_illumination.h5'
            scaler_file = 'scaler_X_without_illumination.save'

        print(f"with open('{config_file}', 'r') as f:")
        print("    config = json.load(f)")
        print("")
        print(f"model = load_model('{model_file}', compile=False)")
        print(f"scaler = joblib.load('{scaler_file}')")
        print("```")

        print("\n2️⃣ 使用模型進行預測:")
        print("```python")
        print("def predict_power(hour_decimal, day_of_year, tilt_angle, azimuth_angle, illumination=None):")
        print("    # 特徵工程")
        print("    hour_sin = np.sin(2 * np.pi * hour_decimal / 24)")
        print("    hour_cos = np.cos(2 * np.pi * hour_decimal / 24)")
        print("    day_sin = np.sin(2 * np.pi * day_of_year / 365)")
        print("    day_cos = np.cos(2 * np.pi * day_of_year / 365)")
        print("    tilt_sin = np.sin(np.radians(tilt_angle))")
        print("    tilt_cos = np.cos(np.radians(tilt_angle))")
        print("    azimuth_sin = np.sin(np.radians(azimuth_angle))")
        print("    azimuth_cos = np.cos(np.radians(azimuth_angle))")
        print("    ")
        print("    feature_list = [hour_sin, hour_cos, day_sin, day_cos,")
        print("                    tilt_sin, tilt_cos, azimuth_sin, azimuth_cos]")
        print("    ")
        if result['has_illumination']:
            print("    if config['has_illumination']:")
            print("        if illumination is None:")
            print("            raise ValueError('需要照度參數')")
            print("        feature_list.append(illumination)")
        print("    ")
        print("    features = np.array([feature_list])")
        print("    features_scaled = scaler.transform(features)")
        print("    pred = model.predict(features_scaled, verbose=0)")
        print("    return max(0.0, float(pred[0][0]))")
        print("```")

        print("\n3️⃣ 預測範例:")
        print("```python")
        print("# 例1: 預測正午時刻，傾角15°，方位角180°")
        if result['has_illumination']:
            print("power = predict_power(12.0, 180, 15, 180, illumination=55000)")
        else:
            print("power = predict_power(12.0, 180, 15, 180)")
        print("print(f'預測功率: {power:.2f}W')")
        print("")
        print("# 例2: 查看不同固定角度的性能")
        print("for tilt in [10, 15, 20, 30]:  # 固定的傾角選項")
        print("    for azimuth in [160, 180, 200]:  # 固定的方位角選項")
        if result['has_illumination']:
            print("        power = predict_power(12.0, 180, tilt, azimuth, illumination=60000)")
        else:
            print("        power = predict_power(12.0, 180, tilt, azimuth)")
        print("        print(f'傾角={tilt}°, 方位角={azimuth}°: {power:.2f}W')")
        print("```")

        print("\n4️⃣ 模型特性:")
        print("✅ 基於ANFIS神經模糊推論系統")
        print("✅ 使用高斯成員函數進行模糊化")
        print("✅ 深層神經網絡實現模糊規則推論")
        print("✅ 批量正規化和Dropout防止過擬合")

        print("\n5️⃣ 性能指標:")
        print(f"   R² (決定係數): {result['performance']['r2']:.4f}")
        print(f"   MAE (平均絕對誤差): {result['performance']['mae']:.2f}W")
        print(f"   RMSE (均方根誤差): {result['performance']['rmse']:.2f}W")

        print("\n" + "=" * 60)
        print("訓練完成！可以開始使用模型了 🎉")
        print("=" * 60)