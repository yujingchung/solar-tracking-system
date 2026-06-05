#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
recover_poa.py
==============
補救主資料集裡缺失的 theoretical_poa（固定面板）

背景
----
原始前處理 (data preprocessing4.py) 使用 row-by-row pandas 迴圈逐筆呼叫
pvlib.irradiance.get_total_irradiance，途中某些列因為例外或迴圈邏輯被
跳過，導致 ~17 萬筆「明明有照度與太陽位置卻 POA = NaN」的列。

關鍵發現：原始 POA 計算**用寫死的 dni=800, ghi=1000, dhi=200**（非實測
照度），所以 theoretical_poa 實質是「標準光照下的角度幾何因子」。本腳本
**完全沿用同一條公式**，新補的值與既有值在同一基準。

工作內容
--------
1. 載入主資料集
2. 鎖定可補的列：固定面板 + theoretical_poa NaN + tilt/azi/solar_zenith/
   solar_azimuth 四欄皆有值
3. 用向量化 pvlib（同一條 get_total_irradiance + dni=800/ghi=1000/dhi=200
   + default isotropic 模型）一次算完
4. 一致性驗證：對既有 POA 的隨機抽樣重算，確認新公式輸出與既有值在容差內
5. 輸出新版 CSV：<input>_poa_recovered.csv

作者: YuJing  版本: 1.0
"""
import sys
import argparse
import numpy as np
import pandas as pd
import pvlib

# 原始前處理的寫死光照值（必須保留以對齊既有資料）
HARDCODED_DNI = 800
HARDCODED_GHI = 1000
HARDCODED_DHI = 200


def compute_poa_vec(tilt, azi, zen, sun_azi):
    """向量化的 POA 計算 — 完全沿用 data preprocessing4.py 的設定。"""
    res = pvlib.irradiance.get_total_irradiance(
        surface_tilt=tilt, surface_azimuth=azi,
        solar_zenith=zen, solar_azimuth=sun_azi,
        dni=HARDCODED_DNI, ghi=HARDCODED_GHI, dhi=HARDCODED_DHI,
    )
    return np.asarray(res['poa_global'], dtype=float)


def main(input_csv, output_csv=None, verify_n=1000):
    if output_csv is None:
        output_csv = input_csv.replace('.csv', '_poa_recovered.csv')
    print(f"載入：{input_csv}", flush=True)
    df = pd.read_csv(input_csv)
    n0 = len(df)
    print(f"  總筆數 {n0:,}", flush=True)

    # 數值化必要欄位
    for c in ['tilt_angle', 'azimuth_angle', 'solar_zenith',
              'solar_azimuth', 'theoretical_poa']:
        df[c] = pd.to_numeric(df[c], errors='coerce')

    # ── 一致性驗證：對既有 POA 列重算，看新公式是否吻合
    print("\n── 一致性驗證 ──", flush=True)
    has_poa = df[df['theoretical_poa'].notna() &
                 df[['tilt_angle', 'azimuth_angle',
                     'solar_zenith', 'solar_azimuth']].notna().all(axis=1)]
    if len(has_poa) > verify_n:
        sample = has_poa.sample(n=verify_n, random_state=42)
    else:
        sample = has_poa
    new_poa = compute_poa_vec(
        sample['tilt_angle'].values, sample['azimuth_angle'].values,
        sample['solar_zenith'].values, sample['solar_azimuth'].values)
    diff = new_poa - sample['theoretical_poa'].values
    print(f"  抽 {len(sample):,} 筆既有 POA 重算")
    print(f"  與既有值差異：mean {diff.mean():+.4f}  std {diff.std():.4f}  "
          f"max|diff| {np.abs(diff).max():.4f}")
    if np.abs(diff).max() > 1e-3:
        print(f"  ⚠ 差異超過 1e-3，公式可能不一致，請檢查 data preprocessing4.py",
              flush=True)
    else:
        print(f"  ✓ 一致性 OK，新補的 POA 與既有 POA 同一基準", flush=True)

    # ── 鎖定可補的列：固定面板 + POA NaN + 四欄皆有值
    print("\n── 識別可補列 ──", flush=True)
    poa_na = df['theoretical_poa'].isna()
    fixed = df['azimuth_angle'].notna() & df['tilt_angle'].notna()
    inputs_ok = (df['solar_zenith'].notna() & df['solar_azimuth'].notna())
    target_mask = poa_na & fixed & inputs_ok
    n_recover = int(target_mask.sum())
    print(f"  POA NaN 總計            : {int(poa_na.sum()):,}")
    print(f"    其中固定面板且輸入齊全 : {n_recover:,}  ← 將補")
    print(f"    其中追日/欄位缺        : {int(poa_na.sum())-n_recover:,}  (略過)")

    if n_recover == 0:
        print("  沒有可補的列。")
        return

    # ── 補
    print("\n── 計算 POA ──", flush=True)
    sub = df.loc[target_mask]
    new_vals = compute_poa_vec(
        sub['tilt_angle'].values, sub['azimuth_angle'].values,
        sub['solar_zenith'].values, sub['solar_azimuth'].values)
    df.loc[target_mask, 'theoretical_poa'] = new_vals
    print(f"  新填入 {n_recover:,} 筆 POA")
    print(f"  新值統計：min {new_vals.min():.1f}  max {new_vals.max():.1f}  "
          f"mean {new_vals.mean():.1f}")

    # ── 補後盤點
    print("\n── 補救後盤點 ──", flush=True)
    print(f"  原本 POA NaN: {int(poa_na.sum()):,}")
    print(f"  現在 POA NaN: {int(df['theoretical_poa'].isna().sum()):,}")
    # 對 v5 真正有意義的：白天 + 有照度 + 有 POA
    illum = pd.to_numeric(df['illumination'], errors='coerce')
    pw = pd.to_numeric(df['power_W'], errors='coerce')
    zen = df['solar_zenith']
    day_v5 = ((zen < 85) & (pw >= 10) & illum.notna()
              & df['theoretical_poa'].notna() & fixed)
    print(f"  v5 可用白天列(zen<85 & P>=10 & 有照度 & 有POA): {int(day_v5.sum()):,}",
          flush=True)

    # ── 輸出
    print(f"\n寫出：{output_csv}", flush=True)
    df.to_csv(output_csv, index=False, encoding='utf-8')
    print("完成。", flush=True)


if __name__ == '__main__':
    ap = argparse.ArgumentParser(description='補救主資料集缺失的 theoretical_poa')
    ap.add_argument('input_csv', nargs='?',
                    default='../data/combined_solar_data_20250301_20260406_processed.csv')
    ap.add_argument('--output-csv', default=None,
                    help='預設在輸入旁加 _poa_recovered 後綴')
    ap.add_argument('--verify-n', type=int, default=1000,
                    help='一致性驗證抽樣筆數')
    args = ap.parse_args()
    main(args.input_csv, args.output_csv, args.verify_n)
