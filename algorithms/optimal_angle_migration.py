#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
optimal_angle_migration.py — 產生「最佳角度隨時間遷移」圖(ASME 規範版)

論文 圖6.4:(a) 各小時最佳方位組成(stacked bar);(b) 平均最佳方位/傾角軌跡。
取代舊版 最佳角度隨時間遷移.png(150 dpi、圖內標題、預設配色)。

輸入:清理版 CSV(POA 補完 + 面板 AB 異常剃除)
輸出:algorithms/optimal_angle_migration.png(600 dpi、雙欄寬 6.5")

從專案根跑:
    python algorithms\optimal_angle_migration.py
"""
import os
import sys
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

# ── ASME 完整規範(2026-06-10),詳見 ASME圖表規範_完整版.md ──
plt.rcParams.update({
    'font.family': ['Times New Roman', 'Liberation Serif',
                    'Nimbus Roman No9 L', 'DejaVu Serif', 'serif'],
    'mathtext.fontset': 'stix',
    'font.size': 9,
    'axes.linewidth': 0.8,
    'lines.linewidth': 1.2,
    'xtick.major.width': 0.6,
    'ytick.major.width': 0.6,
    'axes.grid': False,
    'axes.unicode_minus': False,
    'legend.frameon': False,
    'figure.dpi': 100,
    'savefig.dpi': 600,
    'savefig.bbox': 'tight',
    'savefig.pad_inches': 0.05,
})

# colorblind-friendly(Okabe-Ito)
C_AZ = {160: '#D55E00', 180: '#009E73', 200: '#0072B2'}

HERE = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(HERE)
CSV_PATH = os.path.join(
    PROJECT_ROOT, 'data',
    'combined_solar_data_20250301_20260406_processed_poa_recovered_panel_cleaned.csv')
OUT_PNG = os.path.join(HERE, 'optimal_angle_migration.png')

if not os.path.exists(CSV_PATH):
    print(f"✗ 找不到清理版 CSV: {CSV_PATH}")
    sys.exit(1)

print(f"讀取: {CSV_PATH}")
df = pd.read_csv(CSV_PATH, usecols=['timestamp', 'tilt_angle', 'azimuth_angle',
                                    'power_W', 'solar_zenith', 'hour_decimal'])
for c in ['tilt_angle', 'azimuth_angle', 'power_W', 'solar_zenith', 'hour_decimal']:
    df[c] = pd.to_numeric(df[c], errors='coerce')
df = df.dropna()
df = df[(df.solar_zenith < 85) & (df.power_W >= 10)].copy()
df['tilt'] = df.tilt_angle.astype(int)
df['azimuth'] = df.azimuth_angle.astype(int)
df['hour'] = df.hour_decimal.astype(int)
df = df[(df.hour >= 6) & (df.hour <= 17)]
print(f"  白天固定面板資料: {len(df):,} 筆")

# ── 每個 timestamp 挑 power_W 最高的角度組合(鐵則:用原始功率排名)──
idx = df.groupby('timestamp').power_W.idxmax()
best = df.loc[idx, ['timestamp', 'hour', 'tilt', 'azimuth']]
print(f"  timestamps: {len(best):,}")

hours = sorted(best.hour.unique())
# (a) 各小時最佳方位組成(%)
comp = (best.groupby(['hour', 'azimuth']).size()
            .unstack('azimuth').reindex(columns=[160, 180, 200]).fillna(0))
comp_pct = comp.div(comp.sum(axis=1), axis=0) * 100
# (b) 平均最佳方位 / 傾角
traj = best.groupby('hour')[['azimuth', 'tilt']].mean()

# ── 畫圖:雙欄寬 1×2 ──────────────────────────────────────
fig, (ax_a, ax_b) = plt.subplots(1, 2, figsize=(6.5, 2.6))

bottom = np.zeros(len(comp_pct))
for az in [160, 180, 200]:
    ax_a.bar(comp_pct.index, comp_pct[az], bottom=bottom,
             width=0.75, color=C_AZ[az], edgecolor='white', linewidth=0.4,
             label=f'φ = {az}°')
    bottom += comp_pct[az].values
ax_a.set_xlabel('Hour of Day')
ax_a.set_ylabel('Share of Best-Angle Timestamps (%)')
ax_a.set_xticks(hours)
ax_a.set_ylim(0, 100)
ax_a.legend(loc='lower right', fontsize=8)

l1, = ax_b.plot(traj.index, traj.azimuth, color='#0072B2',
                marker='o', markersize=3, label='Mean optimal azimuth, φ')
ax_b.set_xlabel('Hour of Day')
ax_b.set_ylabel('Mean Optimal Azimuth, φ (°)')
ax_b.set_xticks(hours)
ax_b.margins(y=0.08)
ax_b2 = ax_b.twinx()
l2, = ax_b2.plot(traj.index, traj.tilt, color='#D55E00', linestyle='--',
                 marker='s', markersize=3, label='Mean optimal tilt, β')
ax_b2.set_ylabel('Mean Optimal Tilt, β (°)')
ax_b2.margins(y=0.08)
ax_b.legend(handles=[l1, l2], loc='upper left', fontsize=8)

for ax, tag in ((ax_a, '(a)'), (ax_b, '(b)')):
    ax.text(0.5, -0.32, tag, transform=ax.transAxes,
            ha='center', va='top', fontsize=9)

fig.tight_layout()
fig.savefig(OUT_PNG)
print(f"✓ 輸出: {OUT_PNG}")

print("\n=== (b) 逐時平均最佳角度 ===")
print(traj.round(1).to_string())
