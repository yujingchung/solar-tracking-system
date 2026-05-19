#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""sandbox quick test v4.1 (10% sample, 25 epochs)"""

import os
import sys
import pandas as pd
import numpy as np
import importlib.util
import tensorflow as tf
import tensorflow.keras.callbacks as cbk

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
spec = importlib.util.spec_from_file_location(
    "solar_anfis_model_v4_1",
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "solar_anfis_model_v4_1.py")
)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)

_original_fit = tf.keras.Model.fit
def patched_fit(self, *args, **kwargs):
    kwargs['epochs'] = 25
    kwargs['verbose'] = 0
    return _original_fit(self, *args, **kwargs)
tf.keras.Model.fit = patched_fit

_OriginalES = cbk.EarlyStopping
class _PatchedES(_OriginalES):
    def __init__(self, *args, **kwargs):
        kwargs['patience'] = 5
        kwargs['verbose'] = 0
        super().__init__(*args, **kwargs)
cbk.EarlyStopping = _PatchedES

_OriginalRLR = cbk.ReduceLROnPlateau
class _PatchedRLR(_OriginalRLR):
    def __init__(self, *args, **kwargs):
        kwargs['patience'] = 3
        kwargs['verbose'] = 0
        super().__init__(*args, **kwargs)
cbk.ReduceLROnPlateau = _PatchedRLR

_OriginalMCP = cbk.ModelCheckpoint
class _PatchedMCP(_OriginalMCP):
    def __init__(self, *args, **kwargs):
        kwargs['verbose'] = 0
        super().__init__(*args, **kwargs)
cbk.ModelCheckpoint = _PatchedMCP

INPUT_CSV = "/sessions/peaceful-upbeat-keller/mnt/solar-tracking-dashboard/algorithms/datasets/ds02_20260506_含照度/data.csv"
OUTPUT_DIR = "/sessions/peaceful-upbeat-keller/mnt/solar-tracking-dashboard/algorithms/runs/run08_v4_1_quicktest"
os.makedirs(OUTPUT_DIR, exist_ok=True)

print("=" * 60)
print("v4.1 sandbox quick test (10% sample, 25 epochs)")
print("=" * 60)

df_full = pd.read_csv(INPUT_CSV)
print("Total rows:", len(df_full))
df_sample = df_full.sample(frac=0.10, random_state=42)
sample_csv = os.path.join(OUTPUT_DIR, "_sample.csv")
df_sample.to_csv(sample_csv, index=False)
print("Sampled:", len(df_sample))

result = mod.main(
    file_path=sample_csv,
    output_dir=OUTPUT_DIR,
    weight_mode='watts',
    illum_min=50.0,
    skip_mode_b=False,
)

if result:
    print("")
    print("=" * 60)
    print("SUMMARY")
    print("=" * 60)
    perf = result['performance']
    rk_a = result['ranking_mode_a']
    rk_b = result['ranking_mode_b']
    print("Overall (W): R2={:.4f}  RMSE={:.2f}W  MAE={:.2f}W".format(perf['r2'], perf['rmse'], perf['mae']))
    if rk_a:
        sp = rk_a.get('spearman_mean')
        sp_str = ("{:.3f}".format(sp)) if sp is not None else "N/A"
        print("Mode A: Top1Acc={:.1f}%  Gap={:.2f}W  Spearman={}".format(
            rk_a['top1_accuracy']*100, rk_a['power_gap_mean'], sp_str))
    if rk_b and 'pred_best_mean' in rk_b:
        print("Mode B: pred_best={:.1f}W vs 12best={:.1f}W  Gain={:+.1f}W ({:+.1f}%)".format(
            rk_b['pred_best_mean'], rk_b['true_max12_mean'], rk_b['gain_mean'], rk_b['gain_pct']))
else:
    print("FAILED")
