#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
timeseg_model_compare.py
========================
輕量對照實驗：單一全域模型 vs 每小時專屬模型，在「12 角度 Top-1 選擇準確率」
與「選錯造成的功率落差」上的差異。

用途
----
驗證論文「改用時間分段分析」的模型端收益：把資料切成 1 小時時窗、每窗訓練一個
專屬模型，是否比單一全域模型更會「在當下選對最佳角度」。

用 HistGradientBoosting 當 ANFIS 的快速代理（秒級訓練），特徵比照 v5（含 POA
物理 prior），所以結論可直接套用到「該不該把 v5 分時段」。

關鍵設計
--------
- timestamp-aware split（GroupShuffleSplit）：同一時刻的 12 個角度不可跨 train/test
  外洩，否則 Top-1 會虛高。
- 角度選擇目標 = 最大化「原始功率」（不是 PR；PR 已把角度幾何除掉，見
  timeseg_diagnostic.py 的方法論註記）。
- 每個 test timestamp 把 A/B 平均到 combo，再比 actual argmax vs pred argmax。
- 穩健性檢查：把全域模型加大容量（800/1500 輪），若仍追不平分時段，
  證明優勢來自「時間分段」本身而非「更多模型容量」。

實測結論（2026-05-24, 230k 白天樣本）
-------------------------------------
    全域 基準(300輪)            Top-1 30.4%   gap 7.55W
    全域 加大(800輪,d12)        Top-1 33.3%   gap 6.29W
    全域 超大(1500輪,深度不限)   Top-1 33.1%   gap 6.15W  ← 飽和
    分時段(每時段僅300輪)        Top-1 38.0%   gap 5.83W  ← 勝出
  → 全域模型灌 5× 容量即飽和於 ~33%，仍輸給分時段 38% → 時間分段本身有效。
  機制：窗內角度效應僅佔 3.6% 變異（小訊號），壓在巨大的小時→功率趨勢下；
        全域貪婪 boosting 先吃大趨勢、提早飽和；分時段用切割消掉趨勢，
        容量全用於分辨角度。

作者: YuJing  版本: 1.0
"""
import sys
import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingRegressor
from sklearn.model_selection import GroupShuffleSplit
from scipy.stats import spearmanr

DATA_PATH = "../data/combined_solar_data_20250301_20260406_processed.csv"
ZENITH_MAX = 85.0
POWER_MIN = 10.0
FEATS = ['tilt_angle', 'azimuth_angle', 'hour_decimal', 'day_of_year',
         'illumination', 'solar_zenith', 'solar_azimuth', 'theoretical_poa']


def load(path):
    df = pd.read_csv(path)
    df = df[df['is_tracking'].fillna(0).astype(float) == 0].copy()
    for c in set(FEATS + ['power_W']):
        df[c] = pd.to_numeric(df.get(c), errors='coerce')
    df = df.dropna(subset=FEATS + ['power_W', 'timestamp'])
    df = df[(df.solar_zenith < ZENITH_MAX) & (df.power_W >= POWER_MIN)].copy()
    df['combo'] = (df.tilt_angle.astype(int).astype(str) + '/'
                   + df.azimuth_angle.astype(int).astype(str))
    df['hbin'] = (df.hour_decimal // 1).astype(int)
    return df


def topk(test, predcol):
    """每個 timestamp（A/B 平均到 combo）比 actual vs pred 的最佳角度。"""
    agg = (test.groupby(['timestamp', 'combo'])
                .agg(actual=('power_W', 'mean'), pred=(predcol, 'mean'),
                     hbin=('hbin', 'first')).reset_index())
    rows = []
    for ts, g in agg.groupby('timestamp'):
        if len(g) < 6:        # 角度數不足無法排名
            continue
        a_best = g.loc[g.actual.idxmax(), 'combo']
        p_best = g.loc[g.pred.idxmax(), 'combo']
        gap = g.actual.max() - g.loc[g.pred.idxmax(), 'actual']
        sp = spearmanr(g.actual, g.pred).correlation
        rows.append({'hbin': g.hbin.iloc[0], 'hit': int(a_best == p_best),
                     'gap': gap, 'spearman': sp})
    return pd.DataFrame(rows)


def fit_global(train, **kw):
    m = HistGradientBoostingRegressor(random_state=0, **kw)
    m.fit(train[FEATS], train['power_W'])
    return m


def predict_perhour(train, test, **kw):
    pred = pd.Series(np.nan, index=test.index)
    for h, g in train.groupby('hbin'):
        if len(g) < 500:
            continue
        m = HistGradientBoostingRegressor(random_state=0, **kw)
        m.fit(g[FEATS], g['power_W'])
        idx = test.index[test.hbin == h]
        if len(idx):
            pred.loc[idx] = m.predict(test.loc[idx, FEATS])
    miss = pred.isna()
    if miss.any():                       # 缺該時段模型 → fallback 全域
        gm = fit_global(train, **kw)
        pred.loc[miss] = gm.predict(test.loc[miss, FEATS])
    return pred


def main(path=DATA_PATH):
    df = load(path)
    print(f"資料 {len(df):,} 筆, {df.combo.nunique()} 角度組合")
    gss = GroupShuffleSplit(n_splits=1, test_size=0.25, random_state=42)
    tr, te = next(gss.split(df, groups=df['timestamp']))
    train, test = df.iloc[tr].copy(), df.iloc[te].copy()
    print(f"train {len(train):,} / test {len(test):,}\n")

    print(f"{'設定':<30}{'Top1%':>8}{'GapW':>9}{'Spear':>8}")
    print("-" * 56)
    # 全域：基準 / 加大 / 超大（穩健性檢查）
    for name, kw in [
        ('全域 基準(300,d8)', dict(max_iter=300, learning_rate=0.08, max_depth=8)),
        ('全域 加大(800,d12)', dict(max_iter=800, learning_rate=0.08, max_depth=12)),
        ('全域 超大(1500,d∞)', dict(max_iter=1500, learning_rate=0.05, max_depth=None)),
    ]:
        m = fit_global(train, **kw)
        test['p'] = m.predict(test[FEATS])
        r = topk(test, 'p')
        print(f"{name:<30}{r.hit.mean()*100:>8.1f}{r.gap.mean():>9.2f}"
              f"{r.spearman.mean():>8.3f}")
    # 分時段
    test['p'] = predict_perhour(train, test,
                                max_iter=300, learning_rate=0.08, max_depth=8)
    rp = topk(test, 'p')
    print(f"{'分時段(每時段300,d8)':<30}{rp.hit.mean()*100:>8.1f}"
          f"{rp.gap.mean():>9.2f}{rp.spearman.mean():>8.3f}")
    print("-" * 56)
    print("若全域加大/超大仍追不平分時段 → 時間分段本身有效（非容量差）")

    # 逐時 Top-1（分時段）
    print("\n分時段 逐時 Top-1 %：")
    by = rp.groupby('hbin').hit.mean() * 100
    cnt = rp.groupby('hbin').size()
    for h in sorted(by.index):
        print(f"  {h:>2}h  {by[h]:>5.1f}%  (n_ts={cnt[h]})")


if __name__ == '__main__':
    main(sys.argv[1] if len(sys.argv) > 1 else DATA_PATH)
