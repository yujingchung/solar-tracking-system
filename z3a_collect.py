#!/usr/bin/env python3
"""
z3a_collect.py — 從 QY-Z3A 雲端 API 抓取所有面板資料，合併進 combined_solar_data CSV

使用方式：
  python z3a_collect.py                          # 抓最近 7 天（預設）
  python z3a_collect.py --days 30                # 抓最近 30 天
  python z3a_collect.py --start 2026-04-07 --end 2026-05-03  # 指定日期範圍

作者：自動生成（先鋒金土地公廟太陽能追日系統）
"""

import argparse
import base64
import json
import logging
import os
import sys
import time
import urllib3
from datetime import datetime, timedelta, date
from pathlib import Path

import pandas as pd
import requests

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger(__name__)

# ════════════════════════════════════════════════════════════════════════════════
# 設定區（可改這裡或用環境變數覆蓋）
# ════════════════════════════════════════════════════════════════════════════════

BASE_URL = os.environ.get("Z3A_BASE_URL", "https://server.qiyunwulian.com:12341")

# Bearer Token（從 App 或 Fiddler 取得，到期後需要更新）
TOKEN = os.environ.get(
    "Z3A_TOKEN",
    "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9"
    ".eyJQaG9uZU51bWJlciI6IjEzNTg0ODA5MzUzIiwiZXhwIjoxNzc4NjQ2MDQwLCJpc3MiOiJ3d3cuaW90Ny5jbiJ9"
    ".UkjrCG_dUUcJzYkk9LYsSYqS8njW14sVWCJnMce2qSQ",
)

# 合併目標 CSV 路徑
CSV_PATH = Path(
    os.environ.get(
        "Z3A_CSV_PATH",
        r"D:\宇靖\solar-tracking-dashboard\data"
        r"\combined_solar_data_20250301_20260406_processed.csv",
    )
)

# 單位換算
#   dcv_value / 1_000_000 → 電壓 (V)
#   dca_value / 1_000_000 → 電流 (mA)，再 / 1000 → A
# ⚠ 若電流值看起來偏小，請依分流器規格調整 CURRENT_SCALE：
#   分流器 20A/75mV → 理論換算因子 = 20 / (75/1000) / 1000 = 266.67
#   目前先用直接換算；確認後再乘以修正係數
VOLTAGE_DIV   = 1_000_000     # dcv_value → V
CURRENT_DIV   = 1_000_000_000 # dca_value → A  (先÷1e9；實際電流需乘以分流器修正)

# ════════════════════════════════════════════════════════════════════════════════
# 面板對照表：DeviceId → (panel_id, tilt_angle, azimuth_angle, is_tracking)
# ⚠ L2-4 的 DeviceId (Z3A0512125) 與 R2-4 重複，目前暫時跳過 Panel_15_200_A
#   請確認 L2-4 的正確 DeviceId 後補上
# ════════════════════════════════════════════════════════════════════════════════

PANEL_MAP = {
    # DeviceId           panel_id             tilt  azimuth  is_tracking
    # ── R1 群 ──
    "Z3A0412097": ("Panel_20_180_A",  20, 180, 0),   # R1-4
    "Z3A0412118": ("Panel_20_180_B",  20, 180, 0),   # R1-3
    "Z3A0412115": ("Panel_30_180_A",  30, 180, 0),   # R1-2
    "Z3A0412106": ("Panel_30_180_B",  30, 180, 0),   # R1-1
    # ── L1 群 ──
    "Z3A0412107": ("Panel_30_160_A",  30, 160, 0),   # L1-8
    "Z3A0512127": ("Panel_30_160_B",  30, 160, 0),   # L1-7
    "Z3A0512134": ("Panel_20_160_A",  20, 160, 0),   # L1-6
    "Z3A0412116": ("Panel_20_160_B",  20, 160, 0),   # L1-5
    "Z3A0412095": ("Panel_20_200_A",  20, 200, 0),   # L1-4
    "Z3A0512128": ("Panel_20_200_B",  20, 200, 0),   # L1-3
    "Z3A0512135": ("Panel_30_200_A",  30, 200, 0),   # L1-2
    "Z3A0412112": ("Panel_30_200_B",  30, 200, 0),   # L1-1
    # ── R2 群 ──
    "Z3A0512133": ("Panel_10_180_A",  10, 180, 0),   # R2-4（已確認）
    "Z3A0412122": ("Panel_10_180_B",  10, 180, 0),   # R2-3
    "Z3A0412099": ("Panel_15_180_A",  15, 180, 0),   # R2-2
    "Z3A0412108": ("Panel_15_180_B",  15, 180, 0),   # R2-1
    # ── L2 群 ──
    "Z3A0512132": ("Panel_10_160_A",  10, 160, 0),   # L2-8
    "Z3A0512129": ("Panel_10_160_B",  10, 160, 0),   # L2-7
    "Z3A0412098": ("Panel_15_160_A",  15, 160, 0),   # L2-6
    "Z3A0412113": ("Panel_15_160_B",  15, 160, 0),   # L2-5
    "Z3A0512125": ("Panel_15_200_A",  15, 200, 0),   # L2-4（已確認，非 R2-4 重複）
    "Z3A0412105": ("Panel_15_200_B",  15, 200, 0),   # L2-3
    "Z3A0512126": ("Panel_10_200_A",  10, 200, 0),   # L2-2
    "Z3A0412120": ("Panel_10_200_B",  10, 200, 0),   # L2-1
    # ── 追日面板 ──
    "Z3A0412111": ("Tracking_2_25_上", 25, None, 1), # 追日A樹上
    "Z3A0512124": ("Tracking_2_25_下", 25, None, 1), # 追日A樹下
    "Z3A0412103": ("Tracking_1_20_上", 20, None, 1), # 追日B上
    "Z3A0312076": ("Tracking_1_20_下", 20, None, 1), # 追日B下
}

# DeviceType 查詢快取（從 /bind/query 自動取得）
_DEVICE_TYPE_CACHE: dict = {}

# ════════════════════════════════════════════════════════════════════════════════
# Token / Auth
# ════════════════════════════════════════════════════════════════════════════════

def _jwt_exp(token: str) -> int:
    try:
        part = token.split(".")[1]
        part += "=" * (-len(part) % 4)
        return int(json.loads(base64.b64decode(part)).get("exp", 0))
    except Exception:
        return 0


def _headers() -> dict:
    return {"auth": f"Bearer {TOKEN}"}


# ════════════════════════════════════════════════════════════════════════════════
# API 呼叫
# ════════════════════════════════════════════════════════════════════════════════

def fetch_device_types() -> dict:
    """從 /bind/query 取得所有裝置的 DeviceType，建立快取。"""
    global _DEVICE_TYPE_CACHE
    if _DEVICE_TYPE_CACHE:
        return _DEVICE_TYPE_CACHE
    try:
        r = requests.get(f"{BASE_URL}/bind/query", headers=_headers(),
                         verify=False, timeout=15)
        r.raise_for_status()
        data = r.json().get("data") or []
        _DEVICE_TYPE_CACHE = {d["DeviceId"]: str(d.get("DeviceType", "2")) for d in data}
        log.info("已取得 %d 個裝置的 DeviceType", len(_DEVICE_TYPE_CACHE))
    except Exception as e:
        log.warning("無法取得 DeviceType，使用預設值 '2'：%s", e)
        _DEVICE_TYPE_CACHE = {did: "2" for did in PANEL_MAP}
    return _DEVICE_TYPE_CACHE


def fetch_series(device_id: str, device_type: str,
                 measured_fun: int,
                 start: str, end: str,
                 accuracy: str = "10m") -> list[dict]:
    """
    呼叫 /history/period，回傳 [{time, value}, ...] 列表。
    time 為 UTC ISO 格式，value 為原始數值。
    """
    params = {
        "DeviceId":    device_id,
        "DeviceType":  device_type,
        "measured_fun": measured_fun,
        "start_time":  f"{start} 00:00:00",
        "end_time":    f"{end} 23:59:59",
        "accuracy":    accuracy,
    }
    for attempt in range(3):
        try:
            r = requests.get(f"{BASE_URL}/history/period",
                             headers=_headers(), params=params,
                             verify=False, timeout=30)
            r.raise_for_status()
            raw = r.json()
            series = []
            for item in (raw.get("data") or []):
                for s in (item.get("Series") or []):
                    cols = s.get("columns", [])
                    for row in (s.get("values") or []):
                        entry = dict(zip(cols, row))
                        t = entry.get("time", "")
                        val = next((entry[k] for k in cols if k != "time"), None)
                        series.append({"time": t, "value": val})
            return series
        except Exception as e:
            log.warning("  嘗試 %d/3 失敗 (device=%s fun=%d)：%s",
                        attempt + 1, device_id, measured_fun, e)
            time.sleep(2)
    return []


# ════════════════════════════════════════════════════════════════════════════════
# 資料轉換
# ════════════════════════════════════════════════════════════════════════════════

def parse_z3a_time(t: str) -> datetime | None:
    """將 Z3A 的 UTC ISO 時間字串轉成台北時間 datetime。"""
    try:
        # Z3A 回傳格式通常是 "2026-05-03T05:30:00Z" (UTC)
        # 轉成台北時間（UTC+8）
        dt = datetime.strptime(t[:19], "%Y-%m-%dT%H:%M:%S")
        dt = dt + timedelta(hours=8)   # UTC → Asia/Taipei
        return dt
    except Exception:
        try:
            dt = datetime.strptime(t[:19], "%Y-%m-%d %H:%M:%S")
            return dt
        except Exception:
            return None


def build_panel_df(device_id: str, device_type: str,
                   start: str, end: str) -> pd.DataFrame | None:
    """
    抓取單一裝置的電壓 (fun=1) + 電流 (fun=5)，
    轉換單位，計算功率 & 每日累積電量，
    回傳格式與 combined_solar_data CSV 相同的 DataFrame。
    """
    meta = PANEL_MAP.get(device_id)
    if meta is None:
        log.warning("  DeviceId %s 不在 PANEL_MAP 中，跳過", device_id)
        return None

    panel_id, tilt, azimuth, is_tracking = meta
    log.info("  %-20s → %-25s", device_id, panel_id)

    # 拉電壓 (measured_fun=1)
    v_series = fetch_series(device_id, device_type, 1, start, end)
    # 拉電流 (measured_fun=5)
    i_series = fetch_series(device_id, device_type, 5, start, end)

    if not v_series and not i_series:
        log.warning("    無資料，跳過")
        return None

    # 轉成 DataFrame，以時間為 key join
    def to_df(series, col_name, divisor):
        rows = []
        for p in series:
            dt = parse_z3a_time(p["time"])
            val = p["value"]
            if dt is None or val is None:
                continue
            rows.append({"_ts": dt, col_name: float(val) / divisor})
        return pd.DataFrame(rows).set_index("_ts") if rows else pd.DataFrame()

    df_v = to_df(v_series, "voltage", VOLTAGE_DIV)     # V
    df_i = to_df(i_series, "current_A", CURRENT_DIV)   # A

    # 合併電壓 & 電流
    if df_v.empty and df_i.empty:
        return None
    elif df_v.empty:
        df = df_i
        df["voltage"] = float("nan")
    elif df_i.empty:
        df = df_v
        df["current_A"] = float("nan")
    else:
        df = df_v.join(df_i, how="outer")

    # 計算功率
    df["power_W"] = df["voltage"] * df["current_A"]
    df["power_W"] = df["power_W"].clip(lower=0)

    # 時間相關欄位
    df = df.reset_index().rename(columns={"_ts": "_dt"})
    df["timestamp"]   = df["_dt"].dt.strftime("%Y-%m-%d %H:%M:%S")
    df["date"]        = df["_dt"].dt.strftime("%Y-%m-%d")
    df["time"]        = df["_dt"].dt.strftime("%H:%M:%S")
    df["day_of_year"] = df["_dt"].dt.dayofyear
    df["hour_decimal"] = df["_dt"].dt.hour + df["_dt"].dt.minute / 60.0

    # 面板資訊
    df["panel_id"]     = panel_id
    df["tilt_angle"]   = float(tilt)
    df["azimuth_angle"] = float(azimuth) if azimuth is not None else "追日"
    df["is_tracking"]  = is_tracking

    # 每日累積電量 (Wh)：每 10 分鐘 = 1/6 小時
    # 對每天獨立做 cumsum（只計正值）
    df_sorted = df.sort_values("_dt")
    df_sorted["_energy_interval"] = df_sorted["power_W"].clip(lower=0) * (10 / 60)
    df_sorted["daily_energy_Wh"] = (
        df_sorted.groupby("date")["_energy_interval"]
        .cumsum()
        .round(6)
    )

    # 其他欄位填空（原始處理 pipeline 才有的計算值）
    for col in ["solar_zenith", "solar_azimuth", "theoretical_poa",
                "id", "illumination", "tracking_system", "tracking_position"]:
        df_sorted[col] = float("nan") if col in ["solar_zenith", "solar_azimuth",
                                                   "theoretical_poa"] else ""

    # 選出目標欄位，順序與 combined CSV 一致
    COLS = [
        "timestamp", "date", "time", "day_of_year", "hour_decimal",
        "tilt_angle", "azimuth_angle", "power_W",
        "solar_zenith", "solar_azimuth", "theoretical_poa",
        "panel_id", "voltage", "current_A", "daily_energy_Wh",
        "id", "illumination", "is_tracking", "tracking_system", "tracking_position",
    ]
    return df_sorted[COLS]


# ════════════════════════════════════════════════════════════════════════════════
# 主流程
# ════════════════════════════════════════════════════════════════════════════════

def main():
    parser = argparse.ArgumentParser(description="Z3A 資料收集並合併至 combined CSV")
    parser.add_argument("--days",  type=int, default=7,
                        help="抓最近幾天的資料（預設 7 天）")
    parser.add_argument("--start", type=str, default=None,
                        help="開始日期 YYYY-MM-DD（優先於 --days）")
    parser.add_argument("--end",   type=str, default=None,
                        help="結束日期 YYYY-MM-DD（預設今天）")
    parser.add_argument("--dry-run", action="store_true",
                        help="只印出會做什麼，不寫入 CSV")
    args = parser.parse_args()

    # 日期範圍
    end_date   = args.end   or date.today().strftime("%Y-%m-%d")
    start_date = args.start or (
        date.today() - timedelta(days=args.days - 1)
    ).strftime("%Y-%m-%d")

    log.info("═" * 60)
    log.info("Z3A 資料收集  %s → %s", start_date, end_date)
    log.info("目標 CSV：%s", CSV_PATH)
    log.info("═" * 60)

    # 確認 Token 有效期
    exp = _jwt_exp(TOKEN)
    if exp and time.time() > exp:
        log.error("⚠ Token 已過期！請更新 TOKEN 後重試。")
        sys.exit(1)
    elif exp:
        exp_dt = datetime.fromtimestamp(exp).strftime("%Y-%m-%d %H:%M")
        log.info("Token 到期：%s", exp_dt)

    # 取得 DeviceType 對照
    device_types = fetch_device_types()

    # 逐一抓取所有裝置
    all_new_dfs = []
    for device_id, meta in PANEL_MAP.items():
        dtype = device_types.get(device_id, "2")
        df = build_panel_df(device_id, dtype, start_date, end_date)
        if df is not None and not df.empty:
            all_new_dfs.append(df)

    if not all_new_dfs:
        log.error("沒有抓到任何資料，請確認 Token 是否有效。")
        sys.exit(1)

    new_df = pd.concat(all_new_dfs, ignore_index=True)
    log.info("新抓取資料：%d 筆（%d 台裝置）", len(new_df), len(all_new_dfs))

    if args.dry_run:
        log.info("[DRY RUN] 不寫入 CSV，印出前 5 筆：")
        print(new_df.head().to_string())
        return

    # 讀取現有 CSV
    if CSV_PATH.exists():
        log.info("讀取現有 CSV（%s）…", CSV_PATH)
        try:
            existing = pd.read_csv(CSV_PATH, dtype=str, low_memory=False)
            log.info("  現有資料：%d 筆", len(existing))
        except Exception as e:
            log.error("讀取失敗：%s", e)
            sys.exit(1)
    else:
        log.info("CSV 不存在，建立新檔案")
        existing = pd.DataFrame()

    # 合併：新資料轉 str 後 concat，再去重
    new_df_str = new_df.astype(str).replace("nan", "").replace("<NA>", "")
    combined = pd.concat([existing, new_df_str], ignore_index=True)

    # 去重：以 (timestamp, panel_id) 為 key，保留最新（後面的）
    before = len(combined)
    combined = combined.drop_duplicates(
        subset=["timestamp", "panel_id"], keep="last"
    )
    log.info("去重後：%d 筆（移除 %d 筆重複）", len(combined), before - len(combined))

    # 排序
    combined["_ts_sort"] = pd.to_datetime(combined["timestamp"], format="mixed", errors="coerce")
    combined = combined.sort_values(["_ts_sort", "panel_id"]).drop(columns=["_ts_sort"])

    # 備份原始檔案
    backup_path = CSV_PATH.with_suffix(f".bak.{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv")
    if CSV_PATH.exists():
        import shutil
        shutil.copy2(CSV_PATH, backup_path)
        log.info("原始檔案備份至：%s", backup_path)

    # 寫入
    combined.to_csv(CSV_PATH, index=False, encoding="utf-8-sig")
    log.info("✓ 已寫入 %s（共 %d 筆）", CSV_PATH, len(combined))
    log.info("═" * 60)
    log.info("完成！新增資料：%d 筆，覆蓋日期範圍：%s → %s",
             len(new_df), start_date, end_date)

    # 輸出摘要
    panel_counts = new_df.groupby("panel_id").size().sort_index()
    log.info("\n各面板新增筆數：")
    for pid, cnt in panel_counts.items():
        log.info("  %-25s  %4d 筆", pid, cnt)


if __name__ == "__main__":
    main()
