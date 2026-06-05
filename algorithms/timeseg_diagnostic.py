#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
timeseg_diagnostic.py
=====================
時間分段診斷分析（論文 5.x「改用時間分段分析」可行性驗證）

核心問題
--------
全天資料裡，光強度（POA）隨太陽高度角大幅變化，會「淹沒」角度本身造成的功率差異，
這就是 v2~v4 per-range R² 為負的原因（光照主導）。

本腳本驗證一個假設：
    若把資料切成 1 小時時窗（8-9、9-10…），窗內太陽位置近乎固定，
    則「同一時段、不同角度」之間的功率差，幾乎純粹來自角度效應。

量化指標（每個時窗各算一次，並與全天對照）
---------------------------------------
1. eta²_angle(power_W)：窗內，角度組合對「原始功率」的變異解釋率
       eta² = SS_between(angle) / SS_total
   - 全天算一次當 baseline（預期很低 → 光照主導）
   - 每個 1hr 時窗各算一次（預期升高 → 角度效應浮現）

2. eta²_angle(PR_norm)：窗內，角度組合對「光照正規化後 PR」的變異解釋率
   - PR 已除掉光照，殘差主要是角度 + 量測噪聲；窗內 eta² 反映「乾淨的角度可分性」

3. within-timestamp 最佳角度一致性：
   - 每個 timestamp 把 12 個角度組合（A/B 平均）排名，取功率最高者
   - 每個時窗統計：眾數最佳角度、該角度的勝出比例（consistency %）
   - 比例高 → 該時段最佳角度穩定、可被模型學；比例低 → 角度差被噪聲蓋過

輸出
----
- console 表格（每時段 n / eta²_power / eta²_PR / 最佳角度 / 一致性%）
- timeseg_diagnostic.png（eta² by hour 折線 + 最佳 PR 角度×時段 heatmap）
- timeseg_diagnostic.csv（每時段數字，給論文表格用）

作者: YuJing  版本: 1.0
"""
import sys
import numpy as np
import pandas as pd

# ── 與 v5 一致的面板物理常數 ────────────────────────────────
PANEL_AREA_M2 = 1.948     # TS54-BMH-405 H1
PANEL_EFF_STC = 0.208     # 20.8% at STC

DATA_PATH = (
    "../data/combined_solar_data_20250301_20260406_processed.csv"
)

POA_MIN = 50.0            # （備用）theoretical_poa 在本資料夜間被 floor 在 ~200，無法擋夜間
ZENITH_MAX = 85.0         # 太陽天頂角 < 85° → 太陽在地平線上（真正白天）
POWER_MIN = 10.0          # 過濾近零/夜間發電（與 v5 訓練域一致）
HOUR_BIN = 1.0           # 時段寬度（小時）


# ════════════════════════════════════════════════════════════
# 工具：eta²（單因子 ANOVA 效應量）
# ════════════════════════════════════════════════════════════
def eta_squared(values: np.ndarray, groups: np.ndarray) -> float:
    """
    單因子 ANOVA 效應量 eta² = SS_between / SS_total
    回傳 [0,1]：群組（角度）能解釋多少比例的變異。
    """
    values = np.asarray(values, dtype=float)
    grand_mean = values.mean()
    ss_total = np.sum((values - grand_mean) ** 2)
    if ss_total <= 0:
        return 0.0
    ss_between = 0.0
    for g in np.unique(groups):
        v = values[groups == g]
        if len(v) == 0:
            continue
        ss_between += len(v) * (v.mean() - grand_mean) ** 2
    return float(ss_between / ss_total)


def load_fixed_panels(path: str) -> pd.DataFrame:
    print(f"讀取資料：{path}")
    df = pd.read_csv(path)
    print(f"  原始 {len(df):,} 筆")

    # 只留固定角度面板（排除追日）
    if 'is_tracking' in df.columns:
        df = df[df['is_tracking'].fillna(0).astype(float) == 0].copy()
    # azimuth 可能混入 'tracking'/'追日' 字串 → 強制數值、丟棄非數值
    df['azimuth_angle'] = pd.to_numeric(df['azimuth_angle'], errors='coerce')
    df['tilt_angle'] = pd.to_numeric(df['tilt_angle'], errors='coerce')
    df['power_W'] = pd.to_numeric(df['power_W'], errors='coerce')
    df['theoretical_poa'] = pd.to_numeric(df['theoretical_poa'], errors='coerce')
    df['solar_zenith'] = pd.to_numeric(df.get('solar_zenith'), errors='coerce')
    df = df.dropna(subset=['azimuth_angle', 'tilt_angle', 'power_W',
                           'theoretical_poa', 'solar_zenith'])
    print(f"  固定面板 {len(df):,} 筆")

    # 過濾夜間：本資料 theoretical_poa 夜間被 floor 在 ~200，改用太陽天頂角 + 發電門檻
    n0 = len(df)
    df = df[(df['solar_zenith'] < ZENITH_MAX) & (df['power_W'] >= POWER_MIN)].copy()
    print(f"  天頂角 < {ZENITH_MAX}° 且 power ≥ {POWER_MIN}W：{n0 - len(df):,} 筆移除，"
          f"剩 {len(df):,} 筆")

    # PR_norm（與 v5 完全一致）
    df['expected_power'] = df['theoretical_poa'] * PANEL_AREA_M2 * PANEL_EFF_STC
    df['PR_norm'] = (df['power_W'] / df['expected_power']).clip(0, 1.05)

    # 角度組合標籤
    df['angle_combo'] = (df['tilt_angle'].astype(int).astype(str) + '°/'
                         + df['azimuth_angle'].astype(int).astype(str) + '°')

    # 時段：用 timestamp 推 hour，若無則用 hour_decimal
    if 'hour_decimal' in df.columns:
        df['hour'] = (pd.to_numeric(df['hour_decimal'], errors='coerce')
                      // HOUR_BIN * HOUR_BIN)
    else:
        ts = pd.to_datetime(df['timestamp'], errors='coerce')
        df['hour'] = ts.dt.hour
    df = df.dropna(subset=['hour'])
    df['hour'] = df['hour'].astype(int)

    n_combo = df['angle_combo'].nunique()
    print(f"  角度組合數：{n_combo}（預期 12）")
    return df


# ════════════════════════════════════════════════════════════
# 主診斷
# ════════════════════════════════════════════════════════════
def run_diagnostic(df: pd.DataFrame):
    # ---- baseline：全天角度效應 ----
    base_eta_power = eta_squared(df['power_W'].values,
                                 df['angle_combo'].values)
    base_eta_pr = eta_squared(df['PR_norm'].values,
                              df['angle_combo'].values)
    print("\n" + "=" * 64)
    print("【全天 baseline】角度組合對功率/PR 的變異解釋率")
    print(f"  eta²_angle(power_W) = {base_eta_power:.4f}   "
          f"← 預期低（光照主導，角度被淹沒）")
    print(f"  eta²_angle(PR_norm) = {base_eta_pr:.4f}")
    print("=" * 64)

    # ---- 每個 1hr 時窗 ----
    rows = []
    print(f"\n{'時段':>6} {'樣本':>8} {'eta²_pow':>9} {'eta²_PR':>9} "
          f"{'最佳角度(PR)':>14} {'一致性%':>8}")
    print("-" * 64)

    for hour, g in df.groupby('hour'):
        if len(g) < 200:        # 樣本太少跳過（清晨/黃昏）
            continue
        eta_p = eta_squared(g['power_W'].values, g['angle_combo'].values)
        eta_pr = eta_squared(g['PR_norm'].values, g['angle_combo'].values)

        # 最佳角度：用「原始功率」排名（角度選擇的目標是最大化發電量）。
        # ⚠ 不可用 PR_norm 排名：PR = power/POA，POA 已含角度幾何，
        #    用 PR 等於把角度效應除掉，會選出反物理的角度（下午選朝東）。
        mean_pw = g.groupby('angle_combo')['power_W'].mean()
        best_combo = mean_pw.idxmax()

        # within-timestamp 一致性：每個 timestamp（A/B 先平均到 combo）取功率最高的角度
        ts_best = (g.groupby(['timestamp', 'angle_combo'])['power_W']
                     .mean().reset_index())
        winners = (ts_best.loc[ts_best.groupby('timestamp')['power_W']
                                       .idxmax(), 'angle_combo'])
        consistency = (winners == best_combo).mean() * 100

        rows.append({
            'hour': hour,
            'n': len(g),
            'eta2_power': eta_p,
            'eta2_pr': eta_pr,
            'best_combo': best_combo,
            'consistency_pct': consistency,
        })
        print(f"{hour:>4}h {len(g):>8,} {eta_p:>9.4f} {eta_pr:>9.4f} "
              f"{best_combo:>14} {consistency:>7.1f}%")

    res = pd.DataFrame(rows)
    print("-" * 64)
    if len(res):
        print(f"{'平均':>6} {res['n'].mean():>8,.0f} "
              f"{res['eta2_power'].mean():>9.4f} "
              f"{res['eta2_pr'].mean():>9.4f}")

    # ---- 解讀 ----
    print("\n" + "=" * 64)
    print("【解讀】")
    if len(res):
        avg_window_eta = res['eta2_power'].mean()
        lift = (avg_window_eta / base_eta_power
                if base_eta_power > 0 else float('inf'))
        print(f"  全天 eta²_power = {base_eta_power:.4f}")
        print(f"  時窗平均 eta²_power = {avg_window_eta:.4f}  "
              f"（提升 {lift:.1f}×）")
        if avg_window_eta > base_eta_power * 1.5:
            print("  ✓ 切到 1hr 後角度效應明顯浮現 → 時間分段有效")
        else:
            print("  ✗ 切時段後角度效應未明顯提升 → 收益有限")
        print(f"  最佳角度一致性平均 = {res['consistency_pct'].mean():.1f}%")
    print("=" * 64)
    return res, base_eta_power, base_eta_pr


def make_figure(df, res, out_png):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    try:
        plt.rcParams['font.sans-serif'] = ['Microsoft JhengHei', 'DejaVu Sans']
        plt.rcParams['axes.unicode_minus'] = False
    except Exception:
        pass

    fig, axes = plt.subplots(1, 2, figsize=(15, 5.5))

    # 左：eta² by hour
    ax = axes[0]
    ax.plot(res['hour'], res['eta2_power'], 'o-', label='eta² (raw power)',
            color='#c0392b', lw=2)
    ax.plot(res['hour'], res['eta2_pr'], 's-', label='eta² (PR_norm)',
            color='#2471a3', lw=2)
    ax.set_xlabel('Hour of day'); ax.set_ylabel('eta² (angle variance explained)')
    ax.set_title('Angle effect strength within each 1-hr window')
    ax.legend(); ax.grid(alpha=0.3)

    # 右：每小時「相對功率」heatmap（angle combo × hour）
    # 每一列(hour)除以該小時最大平均功率 → 每個時段最佳角度=1.0(最亮)，凸顯遷移
    ax = axes[1]
    pivot = (df.groupby(['angle_combo', 'hour'])['power_W']
               .mean().unstack('hour'))
    def sort_key(s):
        t, a = s.replace('°', '').split('/')
        return (int(t), int(a))
    pivot = pivot.reindex(sorted(pivot.index, key=sort_key))
    rel = pivot.div(pivot.max(axis=0), axis=1)   # 每時段(欄)正規化到 [_,1]
    im = ax.imshow(rel.values, aspect='auto', cmap='viridis', vmin=0.7, vmax=1.0)
    ax.set_yticks(range(len(rel.index)))
    ax.set_yticklabels(rel.index, fontsize=8)
    ax.set_xticks(range(len(rel.columns)))
    ax.set_xticklabels([f'{int(c)}' for c in rel.columns])
    ax.set_xlabel('Hour of day'); ax.set_ylabel('Angle combo (tilt/azimuth)')
    ax.set_title('Relative power by angle × hour (1.0 = best angle that hour)')
    fig.colorbar(im, ax=ax, label='power / hourly max')

    plt.tight_layout()
    plt.savefig(out_png, dpi=130, bbox_inches='tight')
    print(f"\n圖已輸出：{out_png}")


if __name__ == '__main__':
    path = sys.argv[1] if len(sys.argv) > 1 else DATA_PATH
    df = load_fixed_panels(path)
    res, base_p, base_pr = run_diagnostic(df)
    res.to_csv('timeseg_diagnostic.csv', index=False, encoding='utf-8-sig')
    print("數字表已輸出：timeseg_diagnostic.csv")
    try:
        make_figure(df, res, 'timeseg_diagnostic.png')
    except Exception as e:
        print(f"繪圖略過（{e}）")
