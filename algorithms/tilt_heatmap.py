#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
tilt_heatmap.py — 產生「Hour × Tilt 相對功率」熱力圖 + 數字表

用於 PPT 投影片「熱力圖數值呈現(傾角)」,跟方位版那頁對照。

輸入:清理版 CSV(POA 補完 + 面板 AB 異常剃除)
輸出:
  - algorithms/timeseg_tilt_heatmap.png    熱力圖(風格規範: Times New Roman、無格線、無 legend 框、英文)
  - algorithms/timeseg_tilt_table.csv      數字表(供 PPT/論文使用)

從專案根跑:
    python algorithms\\tilt_heatmap.py

從 algorithms/ 跑:
    python tilt_heatmap.py
"""
import os
import sys
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

# ── 風格規範 ───────────────────────────────────────────────────
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

# ── 路徑(自動找專案根)──────────────────────────────────────
HERE = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(HERE)   # algorithms/ 的上一層 = 專案根
CSV_PATH = os.path.join(
    PROJECT_ROOT, 'data',
    'combined_solar_data_20250301_20260406_processed_poa_recovered_panel_cleaned.csv'
)
OUT_PNG = os.path.join(HERE, 'timeseg_tilt_heatmap.png')
OUT_CSV = os.path.join(HERE, 'timeseg_tilt_table.csv')

if not os.path.exists(CSV_PATH):
    print(f"✗ 找不到清理版 CSV: {CSV_PATH}")
    print(f"  → 先確認 data/ 內有 combined_solar_data_..._poa_recovered_panel_cleaned.csv")
    sys.exit(1)

# ── 載入 + 過濾 ────────────────────────────────────────────
print(f"讀取: {CSV_PATH}")
df = pd.read_csv(CSV_PATH)
for c in ['tilt_angle', 'azimuth_angle', 'power_W', 'solar_zenith', 'hour_decimal']:
    df[c] = pd.to_numeric(df[c], errors='coerce')
df = df.dropna(subset=['power_W', 'solar_zenith', 'tilt_angle', 'azimuth_angle', 'hour_decimal'])
df = df[pd.to_numeric(df['azimuth_angle'], errors='coerce').notna()]
df = df[(df.solar_zenith < 85) & (df.power_W >= 10)].copy()
df['tilt'] = df['tilt_angle'].astype(int)
df['hour'] = df['hour_decimal'].astype(int)
print(f"  白天固定面板資料: {len(df):,} 筆")

# ── 表:Hour × Tilt 平均功率 ───────────────────────────────
table = df.groupby(['hour', 'tilt']).power_W.mean().unstack('tilt').round(1)
table = table.reindex(columns=[10, 15, 20, 30])
# 只保留 6-17h(白天有意義時段)
table = table.loc[6:17]

print("\n=== Hour × Tilt 平均功率(W,清理後)===")
print(table.to_string())

try:
    table.to_csv(OUT_CSV, encoding='utf-8-sig')
    print(f"\n表已存: {OUT_CSV}")
except PermissionError as e:
    print(f"\n⚠ 無法覆寫 {OUT_CSV}(權限/檔案被佔用),跳過")

# ── 圖:每小時內正規化的熱力圖 ────────────────────────────
rel = table.div(table.max(axis=1), axis=0)   # 每列除以該小時最大值

fig, ax = plt.subplots(figsize=(8, 3))
im = ax.imshow(rel.T.values, aspect='auto', cmap='viridis', vmin=0.85, vmax=1.0)

ax.set_yticks(range(4))
ax.set_yticklabels(['10°', '15°', '20°', '30°'], fontsize=11)
ax.set_xticks(range(len(rel.index)))
ax.set_xticklabels([str(h) for h in rel.index], fontsize=11)

# 軸標籤格式: Name, symbol (unit) — 拉丁字母符號用 mathtext 斜體,希臘正體用 unicode
ax.set_xlabel('Hour of Day', fontsize=12)
ax.set_ylabel('Tilt Angle, β (°)', fontsize=12)
ax.set_title('Relative Power by Tilt × Hour (1.0 = best tilt that hour)',
             fontsize=12)

cbar = fig.colorbar(im, ax=ax, label='power / hourly max')
cbar.ax.tick_params(labelsize=9)

plt.tight_layout()
plt.savefig(OUT_PNG, dpi=150, bbox_inches='tight')
plt.close()
print(f"圖已存: {OUT_PNG}")
