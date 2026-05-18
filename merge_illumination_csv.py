#!/usr/bin/env python3
"""
merge_illumination_csv.py
─────────────────────────
從另一個 CSV 檔（例如 Mongo 匯出的 solar.radiation-v2_*.csv）拉照度資料，
補進 combined_solar_data CSV 的 illumination 欄位。

策略：「舊優先，新 CSV 只補舊檔沒有的時間點」
  - 主 CSV 已有 illumination 數值的時間點 → 保留原值，不覆蓋
  - 主 CSV illumination 為空（或 NaN）的時間點 → 用新 CSV 的資料填入

用法：
    python merge_illumination_csv.py --csv "D:\\宇靖\\先鋒\\太陽能板採集數據\\照度\\solar.radiation-v2_0518.csv"
    python merge_illumination_csv.py --csv path/to/your.csv --dry-run    # 只列預覽
    python merge_illumination_csv.py --csv path/to/your.csv --force-overwrite  # 改為新 CSV 覆蓋

自動偵測欄位（不分大小寫）：
  - 時間欄：datetime / timestamp / time / date / _time
  - 照度欄：data.avg / illumination / irradiance / radiation / value / w/m2
"""

import argparse
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
import shutil

import pandas as pd


# 主 CSV 路徑（從 .env.dev 覆蓋，否則用預設）
def _load_env():
    env = {}
    p = Path(__file__).parent / ".env.dev"
    if p.exists():
        for line in p.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, _, v = line.partition("=")
                env[k.strip()] = v.strip().strip('"').strip("'")
    return env

_env = _load_env()


def _resolve_main_csv() -> Path:
    """
    解析主 CSV 路徑：
    1. 優先用相對於本腳本的 data/ 目錄找 combined_solar_data_*.csv（host 環境）
    2. 否則才用 .env.dev 的 Z3A_CSV_PATH（docker 環境用）
    """
    script_data = Path(__file__).parent / "data"
    if script_data.exists():
        matches = sorted(script_data.glob("combined_solar_data_*_processed.csv"))
        # 排除 .bak.*.csv 備份檔
        matches = [m for m in matches if ".bak." not in m.name]
        if matches:
            return matches[-1]
    env_path = _env.get("Z3A_CSV_PATH")
    if env_path:
        return Path(env_path)
    return Path(r"D:\宇靖\solar-tracking-dashboard\data\combined_solar_data_20250301_20260406_processed.csv")


DEFAULT_CSV = _resolve_main_csv()


# ─────────────────────────────────────────────────────────────────────────────
# 欄位偵測
# ─────────────────────────────────────────────────────────────────────────────

TIMESTAMP_CANDIDATES = ["datetime", "timestamp", "time", "date", "_time", "DateTime"]
ILLUM_CANDIDATES = [
    "data.avg", "illumination", "irradiance", "radiation",
    "value", "solar_radiation", "w/m2", "W/m2", "data.value",
    "data.max", "data.min",  # 最後 fallback
]


def detect_fields(df: pd.DataFrame) -> dict:
    """從 DataFrame columns 偵測 timestamp 與 illumination 欄位名"""
    cols_lower = {c.lower(): c for c in df.columns}

    def pick(candidates):
        for cand in candidates:
            if cand.lower() in cols_lower:
                return cols_lower[cand.lower()]
        return None

    ts = pick(TIMESTAMP_CANDIDATES)
    illum = pick(ILLUM_CANDIDATES)
    return {"timestamp": ts, "illumination": illum}


# ─────────────────────────────────────────────────────────────────────────────
# 主流程
# ─────────────────────────────────────────────────────────────────────────────

def load_new_csv(path: Path) -> pd.DataFrame:
    """讀新 CSV，自動偵測欄位、轉時區、回傳 (timestamp, illumination) DataFrame"""
    print(f"讀取新 CSV：{path}")
    df = pd.read_csv(path)
    print(f"  原始：{len(df):,} 筆 · {len(df.columns)} 欄")
    print(f"  欄位：{list(df.columns)[:10]}{'…' if len(df.columns) > 10 else ''}")

    fields = detect_fields(df)
    if not fields["timestamp"]:
        sys.exit(f"✗ 找不到時間欄位（試過：{TIMESTAMP_CANDIDATES}）")
    if not fields["illumination"]:
        sys.exit(f"✗ 找不到照度欄位（試過：{ILLUM_CANDIDATES}）")
    print(f"  → 時間欄：{fields['timestamp']!r}，照度欄：{fields['illumination']!r}")

    # 重新命名
    out = df[[fields["timestamp"], fields["illumination"]]].copy()
    out.columns = ["timestamp", "illumination"]

    # 解析時間
    # ⚠ 雖然 Mongo CSV 的 datetime 帶 Z 後綴看似 UTC，
    #   但實測 5/12 峰值在 hour 11（中午），跟主 CSV power 峰值對齊，
    #   證明該 datetime 已經是台北時間（Mongo 寫入時誤標 Z）。
    # 因此這裡直接 parse 然後 drop tz info（不做 +8 小時轉換）。
    out["timestamp"] = pd.to_datetime(out["timestamp"], errors="coerce", utc=True)
    out = out.dropna(subset=["timestamp"])
    out["timestamp"] = out["timestamp"].dt.tz_localize(None)   # 丟掉 fake Z，直接當台北 naive

    # 照度轉數值，丟掉 NaN
    out["illumination"] = pd.to_numeric(out["illumination"], errors="coerce")
    out = out.dropna(subset=["illumination"])

    # 統一格式為 main CSV 用的字串（10 分鐘解析度自動 floor）
    out["timestamp"] = out["timestamp"].dt.strftime("%Y-%m-%d %H:%M:%S")

    # 去重（同一時間點取平均，避免 raw 有多筆同時間）
    before = len(out)
    out = out.groupby("timestamp", as_index=False)["illumination"].mean()
    print(f"  解析後：{len(out):,} 個時間點（去重移除 {before - len(out):,} 筆）")

    return out


def merge_into_main(new_ill: pd.DataFrame, main_path: Path,
                    dry_run: bool, force_overwrite: bool) -> tuple[int, int]:
    """
    讀主 CSV、用新照度補進去。
    回傳 (補進去的筆數, 跳過的筆數)。
    """
    print(f"\n讀主 CSV：{main_path}")
    if not main_path.exists():
        sys.exit(f"✗ 找不到主 CSV：{main_path}")

    df = pd.read_csv(main_path, dtype=str, low_memory=False)
    print(f"  共 {len(df):,} 筆 · {len(df.columns)} 欄")

    if "timestamp" not in df.columns:
        sys.exit("✗ 主 CSV 缺 timestamp 欄位")
    if "illumination" not in df.columns:
        df["illumination"] = ""
        print("  加上 illumination 欄位（原本沒有）")

    # 為了快速 lookup
    ill_map = dict(zip(new_ill["timestamp"], new_ill["illumination"]))

    # 統計
    if force_overwrite:
        # 全部以新值覆蓋（在新 CSV 有的時間點）
        mask = df["timestamp"].isin(ill_map)
        merged = mask.sum()
        skipped = 0
    else:
        # 舊優先：只更新 illumination 為空 / NaN 的時間點
        is_empty = df["illumination"].isin(["", "nan", "NaN", "<NA>"]) | df["illumination"].isna()
        has_new = df["timestamp"].isin(ill_map)
        mask = is_empty & has_new
        merged = mask.sum()
        skipped = (has_new & ~is_empty).sum()

    print(f"\n[策略] {'強制覆蓋（新優先）' if force_overwrite else '舊優先，新補缺'}")
    print(f"  新 CSV 涵蓋 {df['timestamp'].isin(ill_map).sum():,} 個主 CSV 時間點")
    print(f"  將寫入：{merged:,} 筆")
    print(f"  跳過（舊已有值）：{skipped:,} 筆")

    if merged == 0:
        print("\n沒有要更新的資料，結束。")
        return 0, skipped

    if dry_run:
        print("\n[DRY RUN] 不寫檔。前 5 筆預覽：")
        sample = df[mask].head(5)[["timestamp", "illumination"]].copy()
        sample["new_illumination"] = sample["timestamp"].map(ill_map).round(2)
        print(sample.to_string(index=False))
        return merged, skipped

    # 實際寫入
    df.loc[mask, "illumination"] = df.loc[mask, "timestamp"].map(ill_map).round(3).astype(str)

    # 備份
    backup = main_path.with_suffix(
        f".bak.illumination.{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
    )
    shutil.copy2(main_path, backup)
    print(f"\n  備份：{backup.name}")

    # 寫回主 CSV
    df.to_csv(main_path, index=False, encoding="utf-8-sig")
    print(f"  ✓ 已寫回 {main_path.name}")

    return merged, skipped


def main():
    parser = argparse.ArgumentParser(description="從 CSV 補照度進主資料集")
    parser.add_argument("--csv", required=True, help="新照度 CSV 的完整路徑")
    parser.add_argument("--main", default=str(DEFAULT_CSV), help="主 CSV 路徑（預設讀 .env.dev）")
    parser.add_argument("--dry-run", action="store_true", help="只預覽不寫檔")
    parser.add_argument("--force-overwrite", action="store_true",
                        help="改為新優先：新 CSV 覆蓋舊資料")
    args = parser.parse_args()

    new_path = Path(args.csv)
    if not new_path.exists():
        sys.exit(f"✗ 找不到新 CSV：{new_path}")

    main_path = Path(args.main)

    print("═" * 70)
    print("照度 CSV 合併工具")
    print("═" * 70)

    new_ill = load_new_csv(new_path)
    merged, skipped = merge_into_main(new_ill, main_path, args.dry_run, args.force_overwrite)

    print("\n" + "═" * 70)
    print(f"完成：補進 {merged:,} 筆，跳過 {skipped:,} 筆")
    print("═" * 70)


if __name__ == "__main__":
    main()
