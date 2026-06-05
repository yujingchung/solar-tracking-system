#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
solar_anfis_timeseg.py
======================
分時段 ANFIS（per-hour ANFIS）— 以 v5 為基礎的時間分段升級版

動機
----
診斷（timeseg_diagnostic.py）+ 代理對照（timeseg_model_compare.py）已證明：
把資料按 1 小時切窗、每窗各訓一個模型，在「12 角度 Top-1 選擇」上勝過單一全域模型，
且非容量差（全域加大 5× 容量仍飽和、追不平）。本模組把該結論落實成真正的 ANFIS。

設計
----
- 完全重用 v5 的架構與特徵工程（build_anfis_model / create_features_v5）與評估
  （evaluate_ranking_mode_a / evaluate_by_range），確保與單一 v5 的比較公平。
- 每個 1 小時時窗（hour ∈ [HOUR_LO, HOUR_HI)）各訓一個 ANFIS，各自配一個 MinMaxScaler。
- **分時段模型拿掉 hour_sin / hour_cos 兩個小時特徵（→ 7 維）**：模型已被「時段」
  條件化，再餵小時是冗餘；且窄窗內 MinMaxScaler 會把微小的小時變化放大成噪聲。
  單一 v5 維持原本 9 特徵。這也符合部署邏輯（用時間路由選模型，模型不需知道幾點）。
- 樣本不足的邊緣時段（清晨/傍晚）→ 用 global fallback 模型補。
- 推論時依當下 hour 路由到對應子模型；缺則用 fallback。

對照實驗（compare_main）
------------------------
同一份 timestamp-aware split 下，單一 v5 vs 分時段，用相同評估比 Top-1 / 功率落差 /
per-range R²，誠實回報真模型是否複現代理實驗的優勢。

用法
----
    python solar_anfis_timeseg.py --compare \
        ../data/combined_solar_data_20250301_20260406_processed.csv \
        --epochs 30 --max-ts 6000
    # 純訓練並存模型（供部署）：
    python solar_anfis_timeseg.py --train <dataset.csv> --output-dir runs/timeseg01

作者: YuJing  版本: 1.0
"""
import os
os.environ['TF_CPP_MIN_LOG_LEVEL'] = '2'

import sys
import json
import argparse
from datetime import datetime

import numpy as np
import pandas as pd
from sklearn.model_selection import GroupShuffleSplit
from sklearn.preprocessing import MinMaxScaler
from tensorflow.keras.callbacks import EarlyStopping, ReduceLROnPlateau
import joblib

# ── 重用 v5（同架構、同特徵、同評估 → 公平比較）────────────────
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from solar_anfis_model_v5 import (
    create_features_v5, build_anfis_model,
    evaluate_ranking_mode_a, evaluate_by_range,
    PANEL_AREA_M2, PANEL_EFF_STC,
)
from sklearn.metrics import r2_score, mean_absolute_error, mean_squared_error

# 分時段模型不用的小時特徵（已用時段條件化）
SEG_DROP = ['hour_sin', 'hour_cos']
HOUR_LO, HOUR_HI = 4, 21          # 掃描的時段範圍
MIN_BIN_SAMPLES = 800             # 時段樣本低於此 → 不單獨建模，交給 fallback


# ════════════════════════════════════════════════════════════════
# 共用訓練器（單一 / 分時段共用，確保超參一致 → 公平）
# ════════════════════════════════════════════════════════════════
def _sample_weights(expected_power: np.ndarray) -> np.ndarray:
    """v5 的 watts 空間等價加權：weight ∝ expected_power²"""
    w = expected_power.astype('float64') ** 2
    w = w / w.mean()
    return np.clip(w, 0.05, 20.0)


def _train_one(X_scaled, y, sample_w, input_dim, epochs,
               num_mfs=7, val_split=0.2, verbose=0,
               patience=50, lr_patience=20):
    """patience/lr_patience 預設對齊真實 v5（50/20）；沙箱快測可調小。"""
    model = build_anfis_model(input_dim=input_dim, num_mfs=num_mfs)
    callbacks = [
        EarlyStopping(monitor='val_loss', patience=patience,
                      restore_best_weights=True, verbose=0),
        ReduceLROnPlateau(monitor='val_loss', patience=lr_patience,
                          factor=0.5, min_lr=1e-7, verbose=0),
    ]
    model.fit(X_scaled, y, epochs=epochs, batch_size=1024,
              validation_split=val_split, sample_weight=sample_w,
              callbacks=callbacks, verbose=verbose)
    return model


# ════════════════════════════════════════════════════════════════
# 單一全域模型（等同 v5，但訓練超參與分時段一致）
# ════════════════════════════════════════════════════════════════
def train_single(df_train, feats, target_col, epochs,
                 patience=50, lr_patience=20):
    X = df_train[feats].values.astype('float32')
    y = df_train[target_col].values.astype('float32')
    sw = _sample_weights(df_train['expected_power'].values)
    sc = MinMaxScaler(feature_range=(-1, 1))
    Xs = sc.fit_transform(X)
    print(f"  [single] 訓練 {len(df_train):,} 筆, {len(feats)} 特徵 ...", flush=True)
    m = _train_one(Xs, y, sw, len(feats), epochs,
                   patience=patience, lr_patience=lr_patience)
    return m, sc


def predict_single(model, scaler, df_rows, feats):
    Xs = scaler.transform(df_rows[feats].values.astype('float32'))
    return model.predict(Xs, batch_size=4096, verbose=0).flatten()


# ════════════════════════════════════════════════════════════════
# 分時段模型
# ════════════════════════════════════════════════════════════════
def train_timeseg(df_train, feats, target_col, epochs,
                  min_samples=MIN_BIN_SAMPLES, patience=50, lr_patience=20):
    """回傳 {hour:int -> {'model','scaler','features'}}，外加 'fallback'。"""
    seg_feats = [c for c in feats if c not in SEG_DROP]
    models = {}
    hours_int = df_train['hour_decimal'].astype(int)
    for h in range(HOUR_LO, HOUR_HI):
        sub = df_train[hours_int == h]
        if len(sub) < min_samples:
            continue
        X = sub[seg_feats].values.astype('float32')
        y = sub[target_col].values.astype('float32')
        sw = _sample_weights(sub['expected_power'].values)
        sc = MinMaxScaler(feature_range=(-1, 1))
        Xs = sc.fit_transform(X)
        print(f"  [seg] {h:>2}h: 訓練 {len(sub):,} 筆 ...", flush=True)
        m = _train_one(Xs, y, sw, len(seg_feats), epochs,
                       patience=patience, lr_patience=lr_patience)
        models[h] = {'model': m, 'scaler': sc, 'features': seg_feats}

    # global fallback（用 seg_feats，補沒有專屬模型的時段）
    X = df_train[seg_feats].values.astype('float32')
    y = df_train[target_col].values.astype('float32')
    sw = _sample_weights(df_train['expected_power'].values)
    sc = MinMaxScaler(feature_range=(-1, 1))
    Xs = sc.fit_transform(X)
    print(f"  [seg] fallback: 訓練 {len(df_train):,} 筆 ...", flush=True)
    models['fallback'] = {'model': _train_one(Xs, y, sw, len(seg_feats), epochs,
                                              patience=patience,
                                              lr_patience=lr_patience),
                          'scaler': sc, 'features': seg_feats}
    print(f"  [seg] 共建 {len([k for k in models if k!='fallback'])} 個時段模型 + 1 fallback",
          flush=True)
    return models


def predict_timeseg(models, df_rows):
    """依當下 hour 路由；缺該時段模型則用 fallback。"""
    seg_feats = models['fallback']['features']
    pr = np.empty(len(df_rows), dtype='float32')
    hours = df_rows['hour_decimal'].astype(int).values
    for h in np.unique(hours):
        idx = np.where(hours == h)[0]
        entry = models.get(int(h), models['fallback'])
        Xs = entry['scaler'].transform(
            df_rows.iloc[idx][entry['features']].values.astype('float32'))
        pr[idx] = entry['model'].predict(Xs, batch_size=4096, verbose=0).flatten()
    return pr


def save_timeseg(models, output_dir):
    os.makedirs(output_dir, exist_ok=True)
    manifest = {'type': 'timeseg_anfis', 'seg_drop': SEG_DROP,
                'created': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                'hours': []}
    for key, entry in models.items():
        tag = 'fallback' if key == 'fallback' else f'h{key}'
        mp = os.path.join(output_dir, f'anfis_timeseg_{tag}.keras')
        sp = os.path.join(output_dir, f'scaler_timeseg_{tag}.save')
        entry['model'].save(mp)
        joblib.dump(entry['scaler'], sp)
        manifest['hours'].append({'key': key, 'model': os.path.basename(mp),
                                  'scaler': os.path.basename(sp),
                                  'features': entry['features']})
    with open(os.path.join(output_dir, 'timeseg_manifest.json'), 'w',
              encoding='utf-8') as f:
        json.dump(manifest, f, indent=2, ensure_ascii=False)
    print(f"  分時段模型已存：{output_dir}", flush=True)


# ════════════════════════════════════════════════════════════════
# 資料載入（含白天過濾，單一/分時段共用同一份）
# ════════════════════════════════════════════════════════════════
def load_and_prepare(file_path, max_ts=None):
    df = pd.read_csv(file_path)
    if 'timestamp' in df.columns:
        ts = pd.to_datetime(df['timestamp'], errors='coerce')
        if 'day_of_year' not in df.columns:
            df['day_of_year'] = ts.dt.dayofyear
        if 'hour_decimal' not in df.columns:
            df['hour_decimal'] = ts.dt.hour + ts.dt.minute/60 + ts.dt.second/3600
    for c in ['tilt_angle', 'azimuth_angle', 'power_W', 'illumination',
              'theoretical_poa', 'solar_zenith', 'hour_decimal', 'day_of_year']:
        df[c] = pd.to_numeric(df.get(c), errors='coerce')
    df = df.dropna(subset=['tilt_angle', 'azimuth_angle', 'power_W', 'illumination',
                           'theoretical_poa', 'solar_zenith', 'timestamp',
                           'hour_decimal', 'day_of_year'])
    # 白天過濾（theoretical_poa 夜間被 floor 在 ~200，需用天頂角+功率，見 timeseg_diagnostic.py）
    n0 = len(df)
    df = df[(df.solar_zenith < 85.0) & (df.power_W >= 10.0)].copy()
    print(f"白天過濾：{n0-len(df):,} 筆移除，剩 {len(df):,} 筆", flush=True)

    df, feats, target = create_features_v5(df, poa_min=50.0)
    if df is None:
        raise RuntimeError("create_features_v5 失敗")
    df = df.dropna(subset=feats + [target]).copy()
    df[target] = df[target].clip(0, 1.05)

    if max_ts:
        uts = pd.Series(df['timestamp'].unique())
        if len(uts) > max_ts:
            keep = set(uts.sample(n=max_ts, random_state=1))
            df = df[df['timestamp'].isin(keep)].copy()
            print(f"取樣 {max_ts:,} timestamps → {len(df):,} 筆", flush=True)
    return df, feats, target


# ════════════════════════════════════════════════════════════════
# 對照實驗主程式
# ════════════════════════════════════════════════════════════════
def compare_main(file_path, epochs=30, max_ts=6000,
                 out_json='timeseg_anfis_compare.json',
                 patience=50, lr_patience=20):
    print("=" * 64, flush=True)
    print(f"分時段 ANFIS 對照實驗  epochs={epochs}  max_ts={max_ts}  "
          f"patience={patience}", flush=True)
    print("=" * 64, flush=True)
    df, feats, target = load_and_prepare(file_path, max_ts=max_ts)

    gss = GroupShuffleSplit(n_splits=1, test_size=0.2, random_state=42)
    tr, te = next(gss.split(df, groups=df['timestamp']))
    train, test = df.iloc[tr].copy(), df.iloc[te].copy()
    print(f"train {len(train):,} / test {len(test):,}  "
          f"(test {test['timestamp'].nunique():,} timestamps)\n", flush=True)

    expected_test = test['expected_power'].values.astype('float32')
    y_power_test = test['power_W'].values
    meta = test[['timestamp', 'tilt_angle', 'azimuth_angle',
                 'hour_decimal', 'day_of_year', 'illumination']].reset_index(drop=True)

    # ── 訓練
    print("── 訓練單一全域模型（v5，9 特徵）──", flush=True)
    m_s, sc_s = train_single(train, feats, target, epochs,
                             patience=patience, lr_patience=lr_patience)
    print("\n── 訓練分時段模型（每時段 7 特徵）──", flush=True)
    models = train_timeseg(train, feats, target, epochs,
                           patience=patience, lr_patience=lr_patience)

    # ── 預測（功率空間 = PR × expected_power）
    pw_single = predict_single(m_s, sc_s, test, feats) * expected_test
    pw_seg = predict_timeseg(models, test) * expected_test

    def overall(yp):
        return {'r2': float(r2_score(y_power_test, yp)),
                'mae': float(mean_absolute_error(y_power_test, yp)),
                'rmse': float(np.sqrt(mean_squared_error(y_power_test, yp)))}

    print("\n" + "#" * 64, flush=True)
    print("# 單一全域 v5", flush=True)
    print("#" * 64, flush=True)
    ov_s = overall(pw_single)
    print(f"整體（W）：R²={ov_s['r2']:.4f}  MAE={ov_s['mae']:.2f}  RMSE={ov_s['rmse']:.2f}",
          flush=True)
    a_s = evaluate_ranking_mode_a(meta, y_power_test, pw_single)
    r_s = evaluate_by_range(y_power_test, pw_single)

    print("\n" + "#" * 64, flush=True)
    print("# 分時段 ANFIS", flush=True)
    print("#" * 64, flush=True)
    ov_g = overall(pw_seg)
    print(f"整體（W）：R²={ov_g['r2']:.4f}  MAE={ov_g['mae']:.2f}  RMSE={ov_g['rmse']:.2f}",
          flush=True)
    a_g = evaluate_ranking_mode_a(meta, y_power_test, pw_seg)
    r_g = evaluate_by_range(y_power_test, pw_seg)

    # ── 並排總結
    print("\n" + "=" * 64, flush=True)
    print(f"{'指標':<22}{'單一 v5':>12}{'分時段':>12}{'差異':>10}", flush=True)
    print("-" * 64, flush=True)
    def row(name, a, b, pct=False, pp=False):
        d = b - a
        ds = f"{d*100:+.1f}pp" if pp else (f"{d:+.2f}" if not pct else f"{d:+.2f}")
        av = f"{a*100:.1f}%" if pp else f"{a:.2f}"
        bv = f"{b*100:.1f}%" if pp else f"{b:.2f}"
        print(f"{name:<22}{av:>12}{bv:>12}{ds:>10}", flush=True)
    row('Top-1 準確率', a_s.get('top1_accuracy', 0), a_g.get('top1_accuracy', 0), pp=True)
    row('功率落差均(W)', a_s.get('power_gap_mean', 0), a_g.get('power_gap_mean', 0))
    row('整體 R²(W)', ov_s['r2'], ov_g['r2'])
    print("=" * 64, flush=True)
    verdict = ("分時段勝出" if a_g.get('top1_accuracy', 0) > a_s.get('top1_accuracy', 0)
               and a_g.get('power_gap_mean', 9e9) < a_s.get('power_gap_mean', 9e9)
               else "未明顯勝出")
    print(f"判定：{verdict}", flush=True)

    result = {'epochs': epochs, 'max_ts': max_ts,
              'n_train': len(train), 'n_test': len(test),
              'single': {'overall': ov_s, 'ranking_mode_a': a_s, 'by_range': r_s},
              'timeseg': {'overall': ov_g, 'ranking_mode_a': a_g, 'by_range': r_g},
              'verdict': verdict,
              'created': datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
    with open(out_json, 'w', encoding='utf-8') as f:
        json.dump(result, f, indent=2, ensure_ascii=False)
    print(f"\n結果已寫：{out_json}", flush=True)
    return result


if __name__ == '__main__':
    ap = argparse.ArgumentParser(description='分時段 ANFIS（per-hour）')
    ap.add_argument('file_path', help='dataset CSV')
    ap.add_argument('--compare', action='store_true', help='跑單一 vs 分時段對照實驗')
    ap.add_argument('--train', action='store_true', help='只訓練分時段模型並存檔')
    ap.add_argument('--epochs', type=int, default=30)
    ap.add_argument('--max-ts', type=int, default=6000, help='取樣 timestamp 數（0=全部）')
    ap.add_argument('--patience', type=int, default=50, help='EarlyStopping patience（對齊 v5）')
    ap.add_argument('--lr-patience', type=int, default=20, help='ReduceLROnPlateau patience')
    ap.add_argument('--output-dir', default='runs/timeseg01')
    ap.add_argument('--out-json', default='timeseg_anfis_compare.json')
    args = ap.parse_args()

    max_ts = None if args.max_ts == 0 else args.max_ts
    if args.train:
        df, feats, target = load_and_prepare(args.file_path, max_ts=max_ts)
        gss = GroupShuffleSplit(n_splits=1, test_size=0.2, random_state=42)
        tr, _ = next(gss.split(df, groups=df['timestamp']))
        models = train_timeseg(df.iloc[tr].copy(), feats, target, args.epochs,
                               patience=args.patience, lr_patience=args.lr_patience)
        save_timeseg(models, args.output_dir)
    else:
        compare_main(args.file_path, epochs=args.epochs, max_ts=max_ts,
                     out_json=args.out_json,
                     patience=args.patience, lr_patience=args.lr_patience)
