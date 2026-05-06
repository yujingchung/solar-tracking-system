"""
fetch_illumination.py
─────────────────────
從 MongoDB Atlas 的 solar.radiation-v2 collection 拉取照度資料，
補進 combined_solar_data CSV 的 illumination 欄位。

用法：
    python fetch_illumination.py                      # 補最近 7 天
    python fetch_illumination.py --days 30            # 補最近 30 天
    python fetch_illumination.py --start 2026-01-01 --end 2026-04-06
    python fetch_illumination.py --probe              # 只印出 collection 前幾筆，確認欄位結構

設定方式（任選一）：
  A. 在 .env.dev 加入：
       MONGO_URI=mongodb+srv://<user>:<password>@atlascluster.puaiwhp.mongodb.net/solar
  B. 設定環境變數 MONGO_URI
  C. 直接在腳本第 47 行填入 MONGO_URI_FALLBACK
"""

import argparse
import os
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

# ── 嘗試載入 .env.dev ────────────────────────────────────────────────────────
_env_path = Path(__file__).parent / ".env.dev"
if _env_path.exists():
    for line in _env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, _, v = line.partition("=")
            os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))

# ── 設定 ─────────────────────────────────────────────────────────────────────

# 若 .env.dev 沒有 MONGO_URI，在這裡填入（或留空讓程式提示）
MONGO_URI_FALLBACK = ""
# 範例：
# MONGO_URI_FALLBACK = "mongodb+srv://youruser:yourpassword@atlascluster.puaiwhp.mongodb.net/solar"

MONGO_DB   = "solar"
MONGO_COL  = "radiation-v2"
STATION_ID = "PMP-TPE-TEMPLE"   # 案場站點識別碼

CSV_PATH = Path(__file__).parent / "data" / "combined_solar_data_20250301_20260406_processed.csv"

# ── 套件載入 ─────────────────────────────────────────────────────────────────
try:
    import pandas as pd
except ImportError:
    print("❌ 請安裝 pandas：pip install pandas"); sys.exit(1)

try:
    from pymongo import MongoClient
    from pymongo.errors import ConnectionFailure, ServerSelectionTimeoutError
except ImportError:
    print("❌ 請安裝 pymongo：pip install 'pymongo[srv]'"); sys.exit(1)

# ── 輔助函式 ─────────────────────────────────────────────────────────────────

def get_mongo_uri() -> str:
    uri = os.environ.get("MONGO_URI", "").strip() or MONGO_URI_FALLBACK.strip()
    if not uri:
        print("❌ 找不到 MONGO_URI。")
        print("   請在 .env.dev 加入：")
        print("   MONGO_URI=mongodb+srv://<user>:<password>@atlascluster.puaiwhp.mongodb.net/solar")
        sys.exit(1)
    return uri


def connect(uri: str):
    print("🔌 連接 MongoDB Atlas……", end="", flush=True)
    try:
        client = MongoClient(uri, serverSelectionTimeoutMS=15000, tls=True)
        client.admin.command("ping")
        print(" 成功")
        return client
    except (ConnectionFailure, ServerSelectionTimeoutError) as e:
        print(f"\n❌ 無法連接：{e}")
        sys.exit(1)


def probe_collection(col):
    """印出前 3 筆文件，幫助確認欄位名稱。"""
    print("\n── 前 3 筆文件（確認欄位結構）─────────────────────────────────")
    docs = list(col.find().limit(3))
    if not docs:
        print("  （collection 為空）")
        return
    for i, doc in enumerate(docs, 1):
        print(f"\n  文件 {i}:")
        for k, v in doc.items():
            if k != "_id":
                print(f"    {k!r}: {v!r}")
    print()


def detect_fields(col) -> dict:
    """
    自動偵測 collection 中的欄位名稱。
    返回 {'timestamp': ..., 'station': ..., 'illumination': ...}
    """
    sample = col.find_one({})
    if not sample:
        return {}

    keys = [k for k in sample.keys() if k != "_id"]

    # 時間戳欄位
    ts_candidates = ["timestamp", "datetime", "time", "date", "createdAt", "recordTime", "record_time"]
    station_candidates = ["station", "station_id", "stationId", "site", "location", "name"]
    illum_candidates = ["illumination", "irradiance", "radiation", "value", "solar_radiation",
                        "solar_irradiance", "lux", "w_m2", "wm2", "pv"]

    def pick(candidates):
        for c in candidates:
            if c in keys:
                return c
        # 模糊匹配
        for c in candidates:
            for k in keys:
                if c.lower() in k.lower():
                    return k
        return None

    return {
        "timestamp": pick(ts_candidates),
        "station":   pick(station_candidates),
        "illumination": pick(illum_candidates),
        "_all_keys": keys,
    }


def fetch_illumination(col, start: datetime, end: datetime, fields: dict) -> pd.DataFrame:
    """
    從 collection 查詢指定時間範圍的照度資料。
    返回 DataFrame，欄位：timestamp（UTC+8 naive）, illumination
    """
    ts_field  = fields["timestamp"]
    sta_field = fields.get("station")
    ill_field = fields["illumination"]

    if not ts_field or not ill_field:
        print(f"❌ 無法自動偵測欄位，請用 --probe 查看結構並手動設定。")
        print(f"   目前找到的欄位：{fields.get('_all_keys')}")
        sys.exit(1)

    # 轉成 UTC（Atlas 通常存 UTC）
    tz_utc = timezone.utc
    start_utc = datetime(start.year, start.month, start.day, tzinfo=tz_utc)
    end_utc   = datetime(end.year,   end.month,   end.day,   23, 59, 59, tzinfo=tz_utc)

    query: dict = {ts_field: {"$gte": start_utc, "$lte": end_utc}}
    if sta_field:
        query[sta_field] = STATION_ID

    print(f"📡 查詢範圍：{start} ～ {end}，站點：{STATION_ID if sta_field else '（無站點篩選）'}")

    projection = {"_id": 0, ts_field: 1, ill_field: 1}
    docs = list(col.find(query, projection))
    print(f"   取得 {len(docs):,} 筆原始記錄")

    if not docs:
        return pd.DataFrame(columns=["timestamp", "illumination"])

    df = pd.DataFrame(docs)
    df = df.rename(columns={ts_field: "timestamp", ill_field: "illumination"})

    # 時間轉換：UTC → Asia/Taipei（+8），去除 tz info
    df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)
    df["timestamp"] = df["timestamp"].dt.tz_convert("Asia/Taipei").dt.tz_localize(None)
    df["timestamp"] = df["timestamp"].dt.strftime("%Y-%m-%d %H:%M:%S")

    df["illumination"] = pd.to_numeric(df["illumination"], errors="coerce")
    df = df.dropna(subset=["illumination"])
    df = df.drop_duplicates(subset=["timestamp"])

    return df[["timestamp", "illumination"]]


def update_csv(new_ill: pd.DataFrame, dry_run: bool = False) -> int:
    """
    將照度資料 merge 進 combined CSV。
    回傳更新筆數。
    """
    if not CSV_PATH.exists():
        print(f"❌ 找不到 CSV：{CSV_PATH}"); sys.exit(1)

    print(f"\n📂 讀取 CSV……", end="", flush=True)
    df = pd.read_csv(CSV_PATH)
    print(f" 完成（{len(df):,} 筆）")

    if "illumination" not in df.columns:
        df["illumination"] = float("nan")

    # 建立 timestamp → illumination 對照字典
    ill_map = dict(zip(new_ill["timestamp"], new_ill["illumination"]))

    # 只更新對應時間的列（同一 timestamp 所有面板共享同一照度值）
    before = df["illumination"].notna().sum()
    mask = df["timestamp"].isin(ill_map)
    df.loc[mask, "illumination"] = df.loc[mask, "timestamp"].map(ill_map)
    after = df["illumination"].notna().sum()
    updated = int(after - before)

    print(f"✏️  新增有效照度值：{updated:,} 筆（原有 {before:,} → 現有 {after:,}）")

    if dry_run:
        print("（dry-run 模式，未寫入）")
        return updated

    # 備份
    backup = CSV_PATH.with_suffix(f".bak.{datetime.now():%Y%m%d_%H%M%S}.csv")
    import shutil
    shutil.copy2(CSV_PATH, backup)
    print(f"💾 備份至：{backup.name}")

    df.to_csv(CSV_PATH, index=False)
    print(f"✅ 已寫入 {CSV_PATH.name}")
    return updated


# ── 主程式 ────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="從 MongoDB Atlas 拉取照度資料補進 combined CSV")
    parser.add_argument("--days",  type=int, default=7, help="補最近幾天（預設 7）")
    parser.add_argument("--start", type=str, help="起始日期 YYYY-MM-DD")
    parser.add_argument("--end",   type=str, help="結束日期 YYYY-MM-DD（含）")
    parser.add_argument("--probe", action="store_true", help="只印出 collection 結構，不寫入 CSV")
    parser.add_argument("--dry-run", action="store_true", help="計算更新筆數但不寫入")
    args = parser.parse_args()

    uri    = get_mongo_uri()
    client = connect(uri)
    col    = client[MONGO_DB][MONGO_COL]

    if args.probe:
        probe_collection(col)
        fields = detect_fields(col)
        print("自動偵測欄位：")
        for k, v in fields.items():
            if k != "_all_keys":
                print(f"  {k}: {v!r}")
        client.close()
        return

    # 決定日期範圍
    if args.start and args.end:
        start = datetime.strptime(args.start, "%Y-%m-%d").date()
        end   = datetime.strptime(args.end,   "%Y-%m-%d").date()
    else:
        end   = date.today()
        start = end - timedelta(days=args.days - 1)

    print(f"\n{'='*55}")
    print(f"  MongoDB 照度資料補抓")
    print(f"  範圍：{start} ～ {end}")
    print(f"{'='*55}\n")

    fields  = detect_fields(col)
    new_ill = fetch_illumination(col, start, end, fields)
    client.close()

    if new_ill.empty:
        print("⚠️  未取得任何照度資料，CSV 未更新。")
        return

    update_csv(new_ill, dry_run=args.dry_run)
    print(f"\n完成。建議執行 check_completeness.py 確認資料完整度。")


if __name__ == "__main__":
    main()
