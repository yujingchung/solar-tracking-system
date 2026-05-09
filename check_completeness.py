"""
check_completeness.py
---------------------
檢查 combined_solar_data CSV 是否完整，找出缺失的面板/日期組合，
並印出對應的 z3a_collect.py 補抓指令。

用法：
    python check_completeness.py              # 檢查最近 7 天
    python check_completeness.py --days 14    # 檢查最近 14 天
    python check_completeness.py --start 2026-04-01 --end 2026-05-04
"""

import argparse
import sys
from datetime import date, timedelta, datetime
from pathlib import Path

try:
    import pandas as pd
except ImportError:
    print("請先安裝 pandas：pip install pandas")
    sys.exit(1)

# ── 設定 ──────────────────────────────────────────────────────────────────────

CSV_PATH = Path(r"D:\宇靖\solar-tracking-dashboard\data\combined_solar_data_20250301_20260406_processed.csv")

PYTHON_EXE = r"C:\Users\user\anaconda3\envs\solar_gpu\python.exe"
SCRIPT_PATH = r"D:\宇靖\solar-tracking-dashboard\z3a_collect.py"

# 26 個預期面板（排除 Tracking_2_25_上/下 硬體故障）
EXPECTED_PANELS = [
    "Panel_10_160_A", "Panel_10_160_B",
    "Panel_10_180_A", "Panel_10_180_B",
    "Panel_10_200_A", "Panel_10_200_B",
    "Panel_15_160_A", "Panel_15_160_B",
    "Panel_15_180_A", "Panel_15_180_B",
    "Panel_15_200_A", "Panel_15_200_B",
    "Panel_20_160_A", "Panel_20_160_B",
    "Panel_20_180_A", "Panel_20_180_B",
    "Panel_20_200_A", "Panel_20_200_B",
    "Panel_30_160_A", "Panel_30_160_B",
    "Panel_30_180_A", "Panel_30_180_B",
    "Panel_30_200_A", "Panel_30_200_B",
    "Tracking_1_20_上", "Tracking_1_20_下",
]

# 每天至少要有幾筆有效功率（power_W > 0）才算「有資料」
MIN_VALID_ROWS = 5

# ── 主邏輯 ────────────────────────────────────────────────────────────────────

def parse_args():
    parser = argparse.ArgumentParser(description="檢查 combined CSV 資料完整度")
    parser.add_argument("--days", type=int, default=7, help="檢查最近幾天（預設 7）")
    parser.add_argument("--start", type=str, help="起始日期 YYYY-MM-DD")
    parser.add_argument("--end", type=str, help="結束日期 YYYY-MM-DD（含）")
    return parser.parse_args()


def date_range(start: date, end: date):
    d = start
    while d <= end:
        yield d
        d += timedelta(days=1)


def consecutive_ranges(dates: list[date]) -> list[tuple[date, date]]:
    """將離散日期清單合併成連續區間。"""
    if not dates:
        return []
    dates = sorted(set(dates))
    ranges = []
    start = end = dates[0]
    for d in dates[1:]:
        if (d - end).days <= 1:
            end = d
        else:
            ranges.append((start, end))
            start = end = d
    ranges.append((start, end))
    return ranges


def main():
    args = parse_args()

    # 決定檢查範圍
    if args.start and args.end:
        start_date = datetime.strptime(args.start, "%Y-%m-%d").date()
        end_date = datetime.strptime(args.end, "%Y-%m-%d").date()
    else:
        end_date = date.today() - timedelta(days=1)   # 昨天（今天還沒跑完）
        start_date = end_date - timedelta(days=args.days - 1)

    check_days = list(date_range(start_date, end_date))
    total_expected = len(check_days) * len(EXPECTED_PANELS)

    print(f"\n{'='*60}")
    print(f"  Z3A 資料完整度檢查")
    print(f"  檢查範圍：{start_date} ～ {end_date}（{len(check_days)} 天）")
    print(f"  預期面板：{len(EXPECTED_PANELS)} 片")
    print(f"  預期組合：{total_expected} 個（日期 × 面板）")
    print(f"{'='*60}\n")

    # 讀 CSV
    if not CSV_PATH.exists():
        print(f"❌ 找不到 CSV 檔案：{CSV_PATH}")
        sys.exit(1)

    print("讀取 CSV 中……", end="", flush=True)
    df = pd.read_csv(CSV_PATH, usecols=["timestamp", "panel_id", "power_W"])
    df["date"] = pd.to_datetime(df["timestamp"]).dt.date
    print(f" 完成（共 {len(df):,} 筆）\n")

    # 篩出檢查範圍內的資料
    mask = df["date"].apply(lambda d: start_date <= d <= end_date)
    df_range = df[mask]

    # 逐日逐面板檢查
    missing_combos: list[tuple[date, str]] = []
    missing_dates_by_panel: dict[str, list[date]] = {p: [] for p in EXPECTED_PANELS}

    for day in check_days:
        day_df = df_range[df_range["date"] == day]
        for panel in EXPECTED_PANELS:
            valid = ((day_df["panel_id"] == panel) & (day_df["power_W"] > 0)).sum()
            if valid < MIN_VALID_ROWS:
                missing_combos.append((day, panel))
                missing_dates_by_panel[panel].append(day)

    # ── 結果輸出 ────────────────────────────────────────────────────────────

    if not missing_combos:
        print("✅ 全部完整！所有面板所有日期均有足夠資料。")
        print(f"\n共 {total_expected} 個組合，缺失 0 個。\n")
        return

    # 統計
    missing_count = len(missing_combos)
    missing_panels = sorted(set(p for _, p in missing_combos))
    all_missing_dates = sorted(set(d for d, _ in missing_combos))

    print(f"⚠️  發現缺失：{missing_count} 個組合（共 {total_expected} 個中的 {missing_count/total_expected*100:.1f}%）\n")

    # 按面板列出缺失日期
    print("── 各面板缺失日期 ──────────────────────────────────────")
    for panel in missing_panels:
        missing_d = missing_dates_by_panel[panel]
        ranges = consecutive_ranges(missing_d)
        range_str = ", ".join(
            str(s) if s == e else f"{s}~{e}" for s, e in ranges
        )
        print(f"  {panel:<22}  缺 {len(missing_d):2d} 天  [{range_str}]")

    # 計算整體缺失日期區間（用來產生補抓指令）
    print("\n── 建議補抓指令 ─────────────────────────────────────────")
    overall_ranges = consecutive_ranges(all_missing_dates)
    for s, e in overall_ranges:
        cmd = (
            f'"{PYTHON_EXE}" '
            f'"{SCRIPT_PATH}" '
            f"--pipeline --start {s} --end {e}"
        )
        print(f"\n  {cmd}")

    print(f"\n{'='*60}")
    print(f"  缺失 {missing_count} / {total_expected} 個組合")
    print(f"  補抓後請重新執行此腳本確認\n")


if __name__ == "__main__":
    main()
