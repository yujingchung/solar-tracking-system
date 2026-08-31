#!/usr/bin/env python3
"""Fixed panel vs ANFIS tracker, 6/25-6/28, KG style"""
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.ticker import AutoMinorLocator, MultipleLocator
from matplotlib.dates import DateFormatter, HourLocator, DayLocator
import pandas as pd
import numpy as np

plt.rcParams.update({
    'font.family': ['Times New Roman', 'Liberation Serif', 'DejaVu Serif', 'serif'],
    'font.size': 13, 'axes.linewidth': 1.6, 'axes.grid': False,
    'xtick.direction': 'in', 'ytick.direction': 'in',
    'xtick.major.size': 6, 'xtick.minor.size': 3,
    'ytick.major.size': 6, 'ytick.minor.size': 3,
    'xtick.major.width': 1.3, 'xtick.minor.width': 0.8,
    'ytick.major.width': 1.3, 'ytick.minor.width': 0.8,
    'xtick.top': True,
    'mathtext.fontset': 'cm', 'mathtext.default': 'it',
})

DATE_START = pd.Timestamp('2026-06-25')
DATE_END   = pd.Timestamp('2026-06-29')

# 固定面板
fp = pd.read_csv('/sessions/peaceful-upbeat-keller/mnt/solar-tracking-dashboard/data/combined_solar_data_20250301_20260406_processed.csv',
                 parse_dates=['timestamp'], low_memory=False)
fp = fp[fp['panel_id'].notna()].copy()
# 強制 timestamp 為 datetime(parse_dates 有時不完全)
fp['timestamp'] = pd.to_datetime(fp['timestamp'], errors='coerce')
fp = fp[fp['timestamp'].notna()].copy()
fp_fixed = fp[~fp['panel_id'].astype(str).str.startswith('Tracking_')].copy()
fp_recent = fp_fixed[(fp_fixed['timestamp'] >= DATE_START) & (fp_fixed['timestamp'] < DATE_END)].copy()
fixed_avg = fp_recent.groupby('timestamp')['power_W'].mean().reset_index()
fixed_avg.columns = ['ts', 'p_mean']

# ANFIS
anfis = pd.read_csv('/sessions/peaceful-upbeat-keller/mnt/uploads/power_records_20260629_094356.csv',
                    encoding='utf-8-sig')
anfis['ts'] = pd.to_datetime(anfis['時間戳(CST)'].str.replace('﻿', ''))
anfis_recent = anfis[(anfis['ts'] >= DATE_START) & (anfis['ts'] < DATE_END)].copy()
anfis_real = anfis_recent[anfis_recent['PV電壓(V)'] > 1].copy().sort_values('ts')

# 照度
g = pd.read_csv('/sessions/peaceful-upbeat-keller/mnt/uploads/solar.radiation-v2_20260629.csv',
                encoding='utf-8-sig', parse_dates=['datetime'])
g = g[g['site'] == 'PMP-TPE-TEMPLE'].copy()
g['ts'] = g['datetime'].dt.tz_localize(None)
g_recent = g[(g['ts'] >= DATE_START) & (g['ts'] < DATE_END)].copy().sort_values('ts')

print(f"固定平均: {len(fixed_avg)} | ANFIS: {len(anfis_real)} | G: {len(g_recent)}")

# 轉成 numpy 避免 pandas/matplotlib 互動問題
fixed_ts = fixed_avg['ts'].values
fixed_p  = fixed_avg['p_mean'].values
anfis_ts = anfis_real['ts'].values
anfis_p  = anfis_real['PV功率(W)'].values
anfis_vb = anfis_real['電池電壓(V)'].values
soc_df = anfis_real.dropna(subset=['電池SOC(%)'])
soc_ts = soc_df['ts'].values
soc_v  = soc_df['電池SOC(%)'].values
g_ts = g_recent['ts'].values
g_v  = g_recent['data.avg'].values

bar_w = 10 / (24 * 60)

fig, axes = plt.subplots(3, 1, figsize=(14, 10), sharex=True,
                         gridspec_kw={'hspace': 0.10})
ax1, ax2, ax3 = axes

# Subplot 1: Power + G
ax1g = ax1.twinx()
ax1g.bar(g_ts, g_v, width=bar_w, color='#ffc0cb', alpha=0.7, edgecolor='none', zorder=1)
ax1.plot(fixed_ts, fixed_p, color='#1f77b4', linewidth=1.5, zorder=3)
ax1.plot(anfis_ts, anfis_p, color='#d62728', linewidth=1.5, zorder=4)
ax1.set_ylabel('Panel Power, $P$ (W)', fontsize=13)
ax1.set_ylim(0, max(fixed_p.max(), 30) * 1.15)
ax1.yaxis.set_major_locator(MultipleLocator(20))
ax1.yaxis.set_minor_locator(AutoMinorLocator(4))
ax1g.set_ylabel('Solar irradiance, $G$ (W/m$^2$)', fontsize=13)
ax1g.set_ylim(0, 1400)
ax1g.yaxis.set_major_locator(MultipleLocator(300))
ax1g.yaxis.set_minor_locator(AutoMinorLocator(3))
ax1g.tick_params(axis='y', direction='in', right=True, length=6, width=1.3, which='major')
ax1g.tick_params(axis='y', direction='in', right=True, length=3, width=0.8, which='minor')
ax1.set_zorder(ax1g.get_zorder() + 1)
ax1.patch.set_visible(False)

# Custom legend
import matplotlib.patches as mpatches
from matplotlib.lines import Line2D
h1 = Line2D([0],[0], color='#1f77b4', linewidth=1.5, label='Fixed-panel avg, $P_{fix}$')
h2 = Line2D([0],[0], color='#d62728', linewidth=1.5, label='ANFIS tracker, $P_{trk}$')
h3 = mpatches.Patch(color='#ffc0cb', alpha=0.7, label='Irradiance, $G$')
ax1.legend(handles=[h1, h2, h3], loc='upper center', frameon=False, fontsize=11, ncol=3,
           bbox_to_anchor=(0.5, 1.13))

# Subplot 2: V_batt
ax2.plot(anfis_ts, anfis_vb, color='#2ca02c', linewidth=1.4)
ax2.axhline(14.4, color='#d62728', linestyle=':', linewidth=1.2, alpha=0.7)
ax2.axhline(13.8, color='#ff7f0e', linestyle=':', linewidth=1.2, alpha=0.7)
ax2.axhline(13.2, color='#1f77b4', linestyle=':', linewidth=1.2, alpha=0.7)
ax2.set_ylabel('Battery voltage, $V_{batt}$ (V)', fontsize=13)
ax2.set_ylim(11.5, 15.5)
ax2.yaxis.set_major_locator(MultipleLocator(0.5))
ax2.yaxis.set_minor_locator(AutoMinorLocator(5))
# 標註閾值文字(右上角)
ax2.text(0.99, 0.95, 'Boost 14.4V', transform=ax2.transAxes, ha='right', va='top',
         fontsize=10, color='#d62728', style='italic')
ax2.text(0.99, 0.83, 'Float 13.8V', transform=ax2.transAxes, ha='right', va='top',
         fontsize=10, color='#ff7f0e', style='italic')
ax2.text(0.99, 0.71, 'Reconnect 13.2V', transform=ax2.transAxes, ha='right', va='top',
         fontsize=10, color='#1f77b4', style='italic')

# Subplot 3: SOC
if len(soc_v) > 0:
    ax3.plot(soc_ts, soc_v, color='#9467bd', linewidth=1.6)
ax3.axhline(100, color='gray', linestyle=':', linewidth=1.0, alpha=0.5)
ax3.set_ylabel('Battery SOC (%)', fontsize=13)
ax3.set_ylim(60, 105)
ax3.yaxis.set_major_locator(MultipleLocator(10))
ax3.yaxis.set_minor_locator(AutoMinorLocator(2))
ax3.set_xlabel('Time (CST)', fontsize=13)

ax3.xaxis.set_major_locator(DayLocator())
ax3.xaxis.set_minor_locator(HourLocator(byhour=[6, 12, 18]))
ax3.xaxis.set_major_formatter(DateFormatter('%m-%d'))

for ax in axes.flatten():
    for spine in ax.spines.values():
        spine.set_linewidth(1.6)
for spine in ax1g.spines.values():
    spine.set_linewidth(1.6)

ax1.set_title('Fixed Panels vs ANFIS Tracker — 4-day Comparison (2026-06-25 ~ 06-28)',
              fontsize=14, pad=24)

plt.tight_layout()
for outdir in ['/sessions/peaceful-upbeat-keller/mnt/solar-tracking-dashboard/docs/daily-reports/V2_figures',
                '/sessions/peaceful-upbeat-keller/mnt/太陽能追日系統的演算法優化/V2_figures']:
    plt.savefig(f"{outdir}/fig_fixed_vs_anfis_5days.png", dpi=300, bbox_inches='tight')
plt.close()
print("✓ saved")

print(f"\n=== 摘要 ===")
print(f"固定平均 P 峰值: {fixed_p.max():.2f} W (取 22+ 片瞬時平均)")
print(f"ANFIS PV P 峰值: {anfis_p.max():.2f} W")
print(f"ANFIS PV P 平均: {anfis_p.mean():.2f} W")
print(f"電池 V 範圍: {anfis_vb.min():.2f} ~ {anfis_vb.max():.2f} V")
if len(soc_v) > 0:
    print(f"SOC 範圍: {soc_v.min():.0f}% ~ {soc_v.max():.0f}%")
print(f"G 峰值: {g_v.max():.0f} W/m²")
