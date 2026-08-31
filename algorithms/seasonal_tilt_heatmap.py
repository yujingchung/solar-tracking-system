#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
seasonal_tilt_heatmap.py — 分季產生「Hour × Tilt 相對功率」熱力圖 + 數字表

理論預期(緯度 25° 北):
- Summer:正午太陽近頂(zenith ≈ 0-15°),flat tilt 10° 最佳
- Winter:正午太陽低(zenith ≈ 45°),steep tilt 30° 偏向最佳
- Spring/Fall:過渡,15° 應主導
- → 若數據呈現此趨勢,代表資料正確捕捉到物理上預期的季節依賴

輸入:清理版 CSV(POA 補完 + 面板 AB 異常剃除)
輸出:
  - algorithms/seasonal_tilt_heatmap.png      4 季並排熱力圖
  - algorithms/seasonal_tilt_table.csv        分季 × Hour × Tilt 平均功率

風格:Times New Roman、無格線、無 legend 框、英文

從專案根跑:python algorithms\\seasonal_tilt_heatmap.py
"""
import os
import sys
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

plt.rcParams.update({
    # ASME 完整規範(2026-06-10),詳見 ASME圖表規範_完整版.md
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

HERE = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(HERE)
CSV_PATH = os.path.join(
    PROJECT_ROOT, 'data',
    'combined_solar_data_20250301_20260406_processed_poa_recovered_panel_cleaned.csv'
)
OUT_PNG = os.path.join(HERE, 'seasonal_tilt_heatmap.png')
OUT_CSV = os.path.join(HERE, 'seasonal_tilt_table.csv')


def month_to_season(m):
    """北半球四季劃分(氣象學標準)"""
    if m in (3, 4, 5):   return 'Spring'
    if m in (6, 7, 8):   return 'Summer'
    if m in (9, 10, 11): return 'Fall'
    return 'Winter'


if not os.path.exists(CSV_PATH):
    print(f"✗ 找不到清理版 CSV: {CSV_PATH}")
    sys.exit(1)

print(f"讀取: {CSV_PATH}")
df = pd.read_csv(CSV_PATH)
for c in ['tilt_angle', 'azimuth_angle', 'power_W', 'solar_zenith', 'hour_decimal']:
    df[c] = pd.to_numeric(df[c], errors='coerce')
df['timestamp'] = pd.to_datetime(df['timestamp'], errors='coerce')
df = df.dropna(subset=['power_W', 'solar_zenith', 'tilt_angle', 'azimuth_angle',
                       'hour_decimal', 'timestamp'])
df = df[pd.to_numeric(df['azimuth_angle'], errors='coerce').notna()]
df = df[(df.solar_zenith < 85) & (df.power_W >= 10)].copy()
df['tilt'] = df['tilt_angle'].astype(int)
df['hour'] = df['hour_decimal'].astype(int)
df['month'] = df['timestamp'].dt.month
df['season'] = df['month'].map(month_to_season)
print(f"  白天固定面板資料: {len(df):,} 筆")

# ── 表:Season × Hour × Tilt 平均功率 ────────────────────
SEASONS = ['Spring', 'Summer', 'Fall', 'Winter']

all_tables = {}
for sea in SEASONS:
    sub = df[df.season == sea]
    table = sub.groupby(['hour', 'tilt']).power_W.mean().unstack('tilt').round(1)
    table = table.reindex(columns=[10, 15, 20, 30])
    # 只保留 6-17h(白天有意義時段)
    table = table.loc[6:17].copy() if not table.empty else table
    all_tables[sea] = table
    print(f"\n=== {sea} (n={len(sub):,}) ===")
    print(table.to_string())

# 存合併版 CSV
combined = pd.concat({s: t for s, t in all_tables.items()},
                     names=['season', 'hour'])
combined.to_csv(OUT_CSV, encoding='utf-8-sig')
print(f"\n表已存: {OUT_CSV}")

# ── 圖:四季並排熱力圖(每季內 per-hour normalised)──────
fig, axes = plt.subplots(1, 4, figsize=(16, 3.5), sharey=True)

for ax, sea in zip(axes, SEASONS):
    table = all_tables[sea]
    if table.empty:
        ax.text(0.5, 0.5, 'no data', transform=ax.transAxes, ha='center')
        ax.set_title(sea, fontsize=12)
        continue
    rel = table.div(table.max(axis=1), axis=0)
    im = ax.imshow(rel.T.values, aspect='auto', cmap='viridis',
                   vmin=0.85, vmax=1.0)
    ax.set_xticks(range(len(rel.index)))
    ax.set_xticklabels([str(h) for h in rel.index], fontsize=9)
    ax.set_yticks(range(4))
    ax.set_yticklabels(['10°', '15°', '20°', '30°'], fontsize=10)
    ax.set_xlabel('Hour of Day', fontsize=11)
    ax.set_title(f'{sea} (n={len(df[df.season==sea]):,})', fontsize=11)

axes[0].set_ylabel('Tilt Angle, β (°)', fontsize=11)

# 共用 colorbar
fig.subplots_adjust(right=0.92)
cbar_ax = fig.add_axes([0.94, 0.15, 0.012, 0.7])
cb = fig.colorbar(im, cax=cbar_ax)
cb.set_label('power / hourly max', fontsize=10)
cb.ax.tick_params(labelsize=8)

fig.suptitle('Relative Power by Tilt × Hour — Seasonal Comparison',
             fontsize=13, y=1.02)
plt.savefig(OUT_PNG, dpi=150, bbox_inches='tight')
plt.close()
print(f"圖已存: {OUT_PNG}")

# ── 統計摘要:每季最常見的「中午最佳傾角」+ 邊際平均 ──────
print("\n=== 四季中午(10-13h)平均功率 ===")
for sea in SEASONS:
    sub = df[(df.season == sea) & (df.hour.between(10, 13))]
    if len(sub) == 0:
        continue
    mid = sub.groupby('tilt').power_W.mean().round(1)
    mid = mid.reindex([10, 15, 20, 30])
    best_tilt = mid.idxmax()
    print(f"  {sea:<7}: 10°={mid[10]:.1f}  15°={mid[15]:.1f}  "
          f"20°={mid[20]:.1f}  30°={mid[30]:.1f}  → best={best_tilt}°")

print("\n=== 四季全天(6-17h)平均功率(每季 best tilt 統計次數)===")
for sea in SEASONS:
    sub = df[df.season == sea]
    if len(sub) == 0:
        continue
    hourly = sub.groupby(['hour', 'tilt']).power_W.mean().unstack('tilt')
    hourly = hourly.reindex(columns=[10, 15, 20, 30])
    hourly = hourly.loc[6:17].dropna(how='all')
    best_per_hour = hourly.idxmax(axis=1)
    counts = best_per_hour.value_counts().reindex([10, 15, 20, 30], fill_value=0)
    print(f"  {sea:<7}: best 出現次數 10°={counts[10]}  15°={counts[15]}  "
          f"20°={counts[20]}  30°={counts[30]}  (共 {best_per_hour.notna().sum()} 小時)")
