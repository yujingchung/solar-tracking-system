#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
train_pipeline.py — ANFIS 訓練一鍵啟動器
=========================================
自動建立 datasets/ 和 runs/ 資料夾，管理每次訓練的資料集與結果。

使用方式:
    # 完整流程（前處理 + 訓練）
    python train_pipeline.py

    # 加上描述標籤
    python train_pipeline.py --desc 含照度

    # 跳過前處理，直接用最新的資料集訓練
    python train_pipeline.py --skip-preprocess

    # 指定用哪個資料集訓練
    python train_pipeline.py --skip-preprocess --dataset ds01_20260506_含照度

    # 指定原始 CSV 路徑（預設自動找 data/ 底下）
    python train_pipeline.py --source-csv "D:/path/to/data.csv"

    # 自訂前處理參數
    python train_pipeline.py --min-power 15 --overheat-window 90
"""

import argparse
import importlib.util
import os
import sys
from datetime import datetime
from pathlib import Path

# ── 路徑設定 ──────────────────────────────────────────────────────────
BASE        = Path(__file__).parent                          # algorithms/
DATASETS    = BASE / "datasets"
RUNS        = BASE / "runs"
DEFAULT_CSV = BASE.parent / "data" / "combined_solar_data_20250301_20260406_processed.csv"


# ── 工具函式 ──────────────────────────────────────────────────────────
def _next_idx(folder: Path, prefix: str) -> int:
    """掃描資料夾，回傳下一個可用編號（從 01 開始）"""
    nums = []
    for d in folder.glob(f"{prefix}*"):
        if d.is_dir():
            try:
                nums.append(int(d.name[len(prefix):len(prefix) + 2]))
            except ValueError:
                pass
    return max(nums) + 1 if nums else 1


def _load_module(name: str, path: Path):
    """動態載入 Python 模組"""
    spec = importlib.util.spec_from_file_location(name, str(path))
    mod  = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _write(path: Path, text: str):
    path.write_text(text, encoding="utf-8")


# ── 主流程 ────────────────────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser(description="ANFIS 訓練管線")
    parser.add_argument("--desc",               default="",           help="本次描述（會出現在資料夾名稱）")
    parser.add_argument("--skip-preprocess",    action="store_true",  help="跳過前處理，直接訓練")
    parser.add_argument("--dataset",            default="",           help="指定資料集資料夾名稱（配合 --skip-preprocess）")
    parser.add_argument("--source-csv",         default=str(DEFAULT_CSV), help="原始 CSV 路徑")
    parser.add_argument("--min-power",          type=float, default=10,   help="低功率門檻 W（預設 10）")
    parser.add_argument("--overheat-power",     type=float, default=45,   help="過熱判定功率 W（預設 45）")
    parser.add_argument("--overheat-tolerance", type=float, default=10,   help="過熱容忍範圍 ±W（預設 10）")
    parser.add_argument("--overheat-window",    type=float, default=120,  help="連續過熱時間門檻 min（預設 120）")
    parser.add_argument("--model",              default="v2",             help="模型版本：v2 / v3 / v4 / v4_1 / v5 / v6 / v8（預設 v2）")
    parser.add_argument("--weight-alpha",       type=float, default=0.7,  help="樣本加權指數 alpha（v3/v4_1 power_alpha 模式用，預設 0.7；0=不加權）")
    parser.add_argument("--weight-mode",        default="watts",          help="v4_1 樣本加權模式：watts / ratio / power_alpha（預設 watts）")
    parser.add_argument("--illum-min",          type=float, default=50.0, help="v4_1 最小照度門檻 W/m²（預設 50）")
    parser.add_argument("--poa-min",            type=float, default=50.0, help="v5 最小 theoretical_poa 門檻 W/m²（預設 50）")
    parser.add_argument("--skip-mode-b",        action="store_true",      help="v4_1/v5 跳過 Mode B 連續網格評估")
    args = parser.parse_args()

    DATASETS.mkdir(exist_ok=True)
    RUNS.mkdir(exist_ok=True)

    today    = datetime.now().strftime("%Y%m%d")
    desc_tag = args.desc.strip().replace(" ", "_") if args.desc else ""

    # ════════════════════════════════════════════════
    # Step 1：前處理
    # ════════════════════════════════════════════════
    if not args.skip_preprocess:
        ds_idx  = _next_idx(DATASETS, "ds")
        ds_name = f"ds{ds_idx:02d}_{today}" + (f"_{desc_tag}" if desc_tag else "")
        ds_dir  = DATASETS / ds_name
        ds_dir.mkdir()

        print(f"\n{'='*60}")
        print(f"  Step 1 — 前處理")
        print(f"  資料集資料夾: {ds_name}")
        print(f"{'='*60}")

        # 載入前處理模組
        pre_mod = _load_module(
            "preprocessor",
            BASE / "datapreprocessor" / "data preprocessor.py"
        )

        # 只取固定式面板（過濾追日）
        import pandas as pd
        source_csv = Path(args.source_csv)
        if not source_csv.exists():
            print(f"❌ 找不到原始 CSV: {source_csv}")
            return

        print(f"\n載入原始資料: {source_csv.name}")
        df_raw   = pd.read_csv(source_csv)
        df_fixed = df_raw[df_raw["is_tracking"] == False].copy()
        print(f"  固定式面板: {len(df_fixed):,} 筆 / 總計 {len(df_raw):,} 筆")

        # 存暫存檔，前處理後輸出到 ds_dir
        tmp_in  = ds_dir / "_tmp_input.csv"
        out_csv = ds_dir / "data.csv"
        df_fixed.to_csv(tmp_in, index=False)

        pre = pre_mod.SimpleSolarPreprocessor(
            min_power=args.min_power,
            overheat_power=args.overheat_power,
            overheat_tolerance=args.overheat_tolerance,
            overheat_window=int(args.overheat_window),
        )
        df_clean = pre.process(str(tmp_in), str(out_csv))
        tmp_in.unlink(missing_ok=True)

        if df_clean is None:
            print("❌ 前處理失敗，中止")
            return

        # 把自動產生的 report.txt 移到 ds_dir（前處理程式會產生 _tmp_input_report.txt）
        auto_report = ds_dir / "_tmp_input_report.txt"
        if auto_report.exists():
            auto_report.rename(ds_dir / "report.txt")
        auto_viz = ds_dir / "_tmp_input_visualization.png"
        if auto_viz.exists():
            auto_viz.rename(ds_dir / "preprocessing_visualization.png")

        # 寫 README
        has_illum = "illumination" in df_clean.columns
        n_illum   = int(df_clean["illumination"].notna().sum()) if has_illum else 0
        illum_pct = n_illum / len(df_clean) * 100 if has_illum and len(df_clean) else 0
        angle_dist = df_clean.groupby(["tilt_angle", "azimuth_angle"]).size().to_dict()
        angle_lines = "\n".join(
            f"    傾角{int(t)}°/方位角{int(a)}°: {c:,} 筆"
            for (t, a), c in sorted(angle_dist.items())
        )

        readme_ds = f"""\
資料集: {ds_name}
建立日期: {datetime.now().strftime('%Y-%m-%d %H:%M')}

來源 CSV: {source_csv}

前處理參數:
    min_power           = {args.min_power} W
    overheat_power      = {args.overheat_power} ± {args.overheat_tolerance} W
    overheat_window     = {int(args.overheat_window)} min

資料統計:
    原始固定面板筆數    = {len(df_fixed):,}
    前處理後筆數        = {len(df_clean):,}
    保留率              = {len(df_clean)/len(df_fixed)*100:.1f}%
    照度欄位            = {'有' if has_illum else '無'}（覆蓋率 {illum_pct:.1f}%）

角度組合分布:
{angle_lines}

備註:
"""
        _write(ds_dir / "README.txt", readme_ds)
        print(f"\n✅ 資料集建立完成: datasets/{ds_name}/")

    else:
        # ── 跳過前處理，找現有資料集 ────────────────────
        if args.dataset:
            ds_dir  = DATASETS / args.dataset
            ds_name = args.dataset
        else:
            ds_dirs = sorted([d for d in DATASETS.iterdir() if d.is_dir()])
            if not ds_dirs:
                print("❌ datasets/ 裡沒有資料集，請先執行前處理")
                return
            ds_dir  = ds_dirs[-1]
            ds_name = ds_dir.name

        if not (ds_dir / "data.csv").exists():
            print(f"❌ 找不到 {ds_dir / 'data.csv'}")
            return

        print(f"\n⏭  跳過前處理，使用資料集: {ds_name}")

    # ════════════════════════════════════════════════
    # Step 2：訓練
    # ════════════════════════════════════════════════
    run_idx  = _next_idx(RUNS, "run")
    run_name = f"run{run_idx:02d}_{ds_name}" + (f"_{desc_tag}" if desc_tag and args.skip_preprocess else "")
    run_dir  = RUNS / run_name
    run_dir.mkdir()

    print(f"\n{'='*60}")
    print(f"  Step 2 — 訓練")
    print(f"  訓練資料夾: {run_name}")
    print(f"{'='*60}")

    model_ver = args.model.lower().strip()
    if model_ver == "v8":
        model_file = BASE / "solar_anfis_model_v8.py"
        print(f"  使用模型版本: v8 (Hybrid POA + Panel Calibration, poa_min={args.poa_min})")
    elif model_ver == "v6":
        model_file = BASE / "solar_anfis_model_v6.py"
        print(f"  使用模型版本: v6 (Hybrid POA + 直接幾何特徵, poa_min={args.poa_min})")
    elif model_ver == "v5":
        model_file = BASE / "solar_anfis_model_v5.py"
        print(f"  使用模型版本: v5 (Hybrid POA + ANFIS, poa_min={args.poa_min})")
    elif model_ver in ("v4_1", "v4.1", "v41"):
        model_ver = "v4_1"
        model_file = BASE / "solar_anfis_model_v4_1.py"
        print(f"  使用模型版本: v4.1  (softplus + weight_mode={args.weight_mode}, illum_min={args.illum_min})")
    elif model_ver == "v4":
        model_file = BASE / "solar_anfis_model_v4.py"
        print(f"  使用模型版本: v4  (target=efficiency_ratio, weight_alpha={args.weight_alpha})")
    elif model_ver == "v3":
        model_file = BASE / "solar_anfis_model_v3.py"
        print(f"  使用模型版本: v3  (weight_alpha={args.weight_alpha})")
    else:
        model_file = BASE / "solar_anfis_model_v2.py"
        print(f"  使用模型版本: v2")

    anfis_mod = _load_module("solar_anfis", model_file)

    if model_ver in ("v5", "v6", "v8"):
        result = anfis_mod.main(
            file_path=str(ds_dir / "data.csv"),
            output_dir=str(run_dir),
            poa_min=args.poa_min,
            skip_mode_b=args.skip_mode_b,
        )
    elif model_ver == "v4_1":
        result = anfis_mod.main(
            file_path=str(ds_dir / "data.csv"),
            output_dir=str(run_dir),
            weight_mode=args.weight_mode,
            weight_alpha=args.weight_alpha,
            illum_min=args.illum_min,
            skip_mode_b=args.skip_mode_b,
        )
    elif model_ver in ("v3", "v4"):
        result = anfis_mod.main(
            file_path=str(ds_dir / "data.csv"),
            output_dir=str(run_dir),
            weight_alpha=args.weight_alpha,
        )
    else:
        result = anfis_mod.main(
            file_path=str(ds_dir / "data.csv"),
            output_dir=str(run_dir),
        )

    if result is None:
        print("❌ 訓練失敗")
        return

    # ── 寫訓練 README ──────────────────────────────
    perf      = result["performance"]
    feat_cols = result["feature_columns"]

    weight_alpha_line = f"\n    weight_alpha = {args.weight_alpha}" if model_ver == "v3" else ""
    readme_run = f"""\
訓練結果: {run_name}
訓練日期: {datetime.now().strftime('%Y-%m-%d %H:%M')}

使用資料集: {ds_name}
模型版本: {model_ver}

模型配置:
    特徵維度    = {len(feat_cols)}
    MF 數量     = 7
    照度特徵    = {'是' if result['has_illumination'] else '否'}
    特徵列表    = {', '.join(feat_cols)}{weight_alpha_line}

測試集結果:
    RMSE  = {perf['rmse']:.2f} W
    MAE   = {perf['mae']:.2f} W
    R²    = {perf['r2']:.4f}
    MAPE  = {perf['mape']:.2f} %

輸出檔案:
    {'anfis_with_illumination.keras' if result['has_illumination'] else 'anfis_without_illumination.keras'}
    {'scaler_X_with_illumination.save' if result['has_illumination'] else 'scaler_X_without_illumination.save'}
    {'model_config_with_illumination.json' if result['has_illumination'] else 'model_config_without_illumination.json'}
    best_anfis.keras

備註:
"""
    _write(run_dir / "README.txt", readme_run)

    # ── 最終摘要 ──────────────────────────────────
    print(f"\n{'='*60}")
    print(f"  訓練完成！")
    print(f"  R² = {perf['r2']:.4f}  |  MAE = {perf['mae']:.2f} W  |  RMSE = {perf['rmse']:.2f} W")
    print(f"  結果位置: algorithms/runs/{run_name}/")
    print(f"{'='*60}\n")


if __name__ == "__main__":
    main()
