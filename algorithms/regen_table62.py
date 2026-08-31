# -*- coding: utf-8 -*-
"""
regen_table62.py — 重新生成論文表6.2(指定日期之12組合最佳角度預測表)

用法(在 algorithms/ 下,建議 python -X utf8):
    python -X utf8 regen_table62.py                          # 用預設 run05 模型、2025-06-21
    python -X utf8 regen_table62.py --run runs/run13_xxx     # 指定其他 run
    python -X utf8 regen_table62.py --date 2025-09-15        # 指定其他日期
    python -X utf8 regen_table62.py --retrain                # 先重訓(train_pipeline)再用最新 run 生成

重點:僅在訓練過的 12 個離散角度組合內取 argmax(不做連續外插),
照度使用該日實測值(ds02 資料集),並附上實測最佳組合對照與 Top-1 命中率。
輸出:CSV 存到所用 run 資料夾內。
"""
import argparse, os, sys, glob, subprocess, warnings
warnings.filterwarnings("ignore")
import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
DEFAULT_RUN = os.path.join(HERE, "runs", "run05_ds02_20260506_含照度")
DS_CSV = os.path.join(HERE, "datasets", "ds02_20260506_含照度", "data.csv")
COMBOS = [(t, a) for t in (10, 15, 20, 30) for a in (160, 180, 200)]


def latest_run():
    runs = [d for d in glob.glob(os.path.join(HERE, "runs", "run*")) if os.path.isdir(d)]
    runs = [d for d in runs if glob.glob(os.path.join(d, "*with_illumination.keras"))]
    return max(runs, key=os.path.getmtime) if runs else None


def load_model_and_scaler(run_dir):
    import joblib
    import tensorflow as tf
    sys.path.insert(0, HERE)
    from solar_anfis_model_v2 import SimpleFuzzyLayer  # custom layer
    keras_files = glob.glob(os.path.join(run_dir, "anfis_with_illumination.keras")) or \
                  glob.glob(os.path.join(run_dir, "best_anfis.keras"))
    scaler_files = glob.glob(os.path.join(run_dir, "scaler_X*.save"))
    if not keras_files or not scaler_files:
        sys.exit(f"[錯誤] {run_dir} 缺 .keras 或 scaler .save")
    model = tf.keras.models.load_model(
        keras_files[0], custom_objects={"SimpleFuzzyLayer": SimpleFuzzyLayer})
    scaler = joblib.load(scaler_files[0])
    print(f"[模型] {keras_files[0]}")
    return model, scaler


def features(hour, doy, tilt, azi, ill):
    n = len(np.atleast_1d(tilt))
    return np.column_stack([
        np.full(n, np.sin(2 * np.pi * hour / 24)), np.full(n, np.cos(2 * np.pi * hour / 24)),
        np.full(n, np.sin(2 * np.pi * doy / 365)), np.full(n, np.cos(2 * np.pi * doy / 365)),
        np.sin(np.radians(tilt)), np.cos(np.radians(tilt)),
        np.sin(np.radians(azi)), np.cos(np.radians(azi)),
        np.full(n, ill)])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", default="2025-06-21")
    ap.add_argument("--run", default=None)
    ap.add_argument("--retrain", action="store_true")
    args = ap.parse_args()

    if args.retrain:
        print("[重訓] train_pipeline --skip-preprocess --dataset ds02_20260506_含照度 ...")
        subprocess.run([sys.executable, "-X", "utf8", os.path.join(HERE, "train_pipeline.py"),
                        "--skip-preprocess", "--dataset", "ds02_20260506_含照度"], check=True)
        run_dir = latest_run()
    else:
        run_dir = args.run or DEFAULT_RUN
        if args.run is None and not os.path.isdir(run_dir):
            run_dir = latest_run()
    if not run_dir or not os.path.isdir(run_dir):
        sys.exit("[錯誤] 找不到可用的 run 資料夾")

    model, scaler = load_model_and_scaler(run_dir)

    ds = pd.read_csv(DS_CSV, usecols=["timestamp", "day_of_year", "hour_decimal",
                                      "tilt_angle", "azimuth_angle", "power_W",
                                      "illumination"])
    day = ds[ds.timestamp.str.startswith(args.date)].copy()
    if day.empty:
        sys.exit(f"[錯誤] ds02 內沒有 {args.date} 的資料")
    day["hm"] = day.timestamp.str[11:16]
    doy = int(day.day_of_year.iloc[0])

    T = np.array([t for t, a in COMBOS]); A = np.array([a for t, a in COMBOS])
    rows = []
    for hm, grp in sorted(day.groupby("hm")):
        if hm[3:] not in ("00", "30"):
            continue
        ill = grp.illumination.median()
        if np.isnan(ill):
            continue
        hour = float(grp.hour_decimal.iloc[0])
        X = scaler.transform(features(hour, doy, T, A, ill))
        pred = model.predict(X, verbose=0).ravel()
        k = int(pred.argmax())
        meas = grp.groupby(["tilt_angle", "azimuth_angle"]).power_W.mean()
        mk, mv = meas.idxmax(), meas.max()
        rows.append({"時間": hm,
                     "預測最佳傾角β(°)": COMBOS[k][0], "預測最佳方位角φ(°)": COMBOS[k][1],
                     "預測功率(W)": round(float(pred[k]), 1),
                     "實測最佳傾角β(°)": int(mk[0]), "實測最佳方位角φ(°)": int(mk[1]),
                     "實測功率(W)": round(float(mv), 1),
                     "Top-1命中": "V" if (COMBOS[k][0], COMBOS[k][1]) == (int(mk[0]), int(mk[1])) else ""})
    tb = pd.DataFrame(rows)
    print(tb.to_string(index=False))
    hit = (tb["Top-1命中"] == "V").mean() * 100
    azi_hit = (tb["預測最佳方位角φ(°)"] == tb["實測最佳方位角φ(°)"]).mean() * 100
    print(f"\nTop-1 命中率: {hit:.0f}% | 方位角命中率: {azi_hit:.0f}%")
    out = os.path.join(run_dir, f"table62_{args.date}.csv")
    tb.to_csv(out, index=False, encoding="utf-8-sig")
    print(f"[輸出] {out}")


if __name__ == "__main__":
    main()
