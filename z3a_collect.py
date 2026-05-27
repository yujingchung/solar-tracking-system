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
import hashlib
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
# ⚠ 若 token 過期且設定了 Z3A_PHONE/Z3A_PASSWORD，會自動重新登入
TOKEN = os.environ.get(
    "Z3A_TOKEN",
    "",
)

# 自動登入用的帳密（取自 .env.dev 或環境變數）
Z3A_PHONE    = os.environ.get("Z3A_PHONE", "")
Z3A_PASSWORD = os.environ.get("Z3A_PASSWORD", "")

# Refresh token (tokenString2)，用於免驗證碼換新的 access token
# 3 個月有效，過期才需要手動再抓一次 Fiddler
Z3A_REFRESH_TOKEN = os.environ.get("Z3A_REFRESH_TOKEN", "")

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


def _load_env_file(env_path: Path = None) -> dict:
    """讀取專案根目錄的 .env.dev (KEY=VALUE 格式)，回傳 dict。"""
    if env_path is None:
        env_path = Path(__file__).parent / ".env.dev"
    env = {}
    if not env_path.exists():
        return env
    try:
        for line in env_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, _, v = line.partition("=")
            v = v.strip().strip('"').strip("'")
            env[k.strip()] = v
    except Exception as e:
        log.warning("讀取 .env.dev 失敗：%s", e)
    return env


def _login_with_phone(phone: str, password: str) -> str | None:
    """
    用手機/密碼向 Z3A 雲端登入，回傳新 JWT token；失敗回 None。
    格式（從 Fiddler 抓回來確認）：
      POST /user/login
      Content-Type: application/x-www-form-urlencoded
      Body: PhoneNumber=...&PassWord=<MD5>&Safetynum=<captcha>&Safetyid=<sid>
    ⚠ 此 API 強制要圖形驗證碼（Safetynum），純自動登入不可行；
    本函式僅作為「使用者已手動取得 captcha」時的接口，預設情況下 Z3A 雲端會拒絕。
    """
    if not (phone and password):
        return None
    try:
        log.info("嘗試 /user/login (PHONE=%s)…（注意：雲端要驗證碼，此呼叫多半會失敗）", phone)
        pw_md5 = hashlib.md5(password.encode("utf-8")).hexdigest()
        r = requests.post(
            f"{BASE_URL}/user/login",
            data={"PhoneNumber": phone, "PassWord": pw_md5},
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            verify=False, timeout=15,
        )
        data = r.json()
        new_tok = (data.get("data") or {}).get("tokenString") or ""
        if new_tok:
            exp = _jwt_exp(new_tok)
            exp_str = datetime.fromtimestamp(exp).strftime("%Y-%m-%d %H:%M") if exp else "未知"
            log.info("✓ 登入成功，新 token 到期：%s", exp_str)
            return new_tok
        log.warning("登入失敗：%s", str(data)[:300])
        return None
    except Exception as e:
        log.warning("登入請求例外：%s", e)
        return None


def _refresh_with_token2(refresh_token: str) -> str | None:
    """
    用 tokenString2 (refresh token) 換新的 access token。
    嘗試多個可能的端點，找到能用的就回傳新 token。
    成功比 _login_with_phone 重要 — 因為不用驗證碼。
    """
    if not refresh_token:
        return None
    # 嘗試的端點與請求模式（已知對的會排前面，逐步驗證後縮小範圍）
    attempts = [
        ("POST", "/user/refreshToken", {"refreshToken": refresh_token}, "header_auth"),
        ("POST", "/user/refreshToken", {}, "header_auth_t2_only"),
        ("GET",  "/user/refreshToken", None, "header_auth_t2_only"),
        ("POST", "/user/refresh",      {"refreshToken": refresh_token}, "header_auth"),
        ("POST", "/token/refresh",     {"refreshToken": refresh_token}, "header_auth"),
        ("POST", "/user/refreshToken", {}, "form_t2"),
    ]
    for method, path, body, mode in attempts:
        url = f"{BASE_URL}{path}"
        headers = {}
        params = None
        data_body = None
        try:
            if mode == "header_auth":
                headers["auth"] = f"Bearer {TOKEN}"
                data_body = body
            elif mode == "header_auth_t2_only":
                headers["auth"] = f"Bearer {refresh_token}"
            elif mode == "form_t2":
                data_body = {"refreshToken": refresh_token}
            if data_body is not None:
                headers["Content-Type"] = "application/x-www-form-urlencoded"

            if method == "GET":
                r = requests.get(url, headers=headers, params=params, verify=False, timeout=10)
            else:
                r = requests.post(url, headers=headers, data=data_body, verify=False, timeout=10)

            j = r.json() if r.text else {}
            new_tok = (
                (j.get("data") or {}).get("tokenString")
                or (j.get("data") or {}).get("token")
                or j.get("tokenString")
                or j.get("token") or ""
            )
            if new_tok and new_tok != refresh_token:
                exp = _jwt_exp(new_tok)
                exp_str = datetime.fromtimestamp(exp).strftime("%Y-%m-%d %H:%M") if exp else "未知"
                log.info("✓ Refresh 成功 (%s %s)，新 token 到期：%s", method, path, exp_str)
                return new_tok
        except Exception:
            continue
    log.warning("✗ 所有 refresh 端點都失敗（tokenString2 可能也過期或端點未知）")
    return None


def _ensure_valid_token() -> bool:
    """
    確認當前 TOKEN 有效。若過期：
      1. 先試 refresh token 換新 access token（免驗證碼，最佳）
      2. 再退而求其次試自動登入（會被驗證碼擋住，多半失敗）
      3. 都失敗就回 False，由 caller 通知 user 手動更新 .env.dev
    """
    global TOKEN, Z3A_PHONE, Z3A_PASSWORD, Z3A_REFRESH_TOKEN

    # 從 .env.dev 補齊環境變數
    env = _load_env_file()
    Z3A_PHONE         = Z3A_PHONE         or env.get("Z3A_PHONE",         "")
    Z3A_PASSWORD      = Z3A_PASSWORD      or env.get("Z3A_PASSWORD",      "")
    Z3A_REFRESH_TOKEN = Z3A_REFRESH_TOKEN or env.get("Z3A_REFRESH_TOKEN", "")
    if env.get("Z3A_TOKEN") and (not TOKEN or TOKEN.count(".") != 2):
        TOKEN = env["Z3A_TOKEN"]

    exp = _jwt_exp(TOKEN)
    now = time.time()
    if exp and now < exp - 3600:   # 提前 1 小時換，避免邊緣 case
        exp_dt = datetime.fromtimestamp(exp).strftime("%Y-%m-%d %H:%M")
        log.info("Token 有效，到期：%s", exp_dt)
        return True

    # 過期 → 試 refresh token 換新
    log.warning("⚠ access token 已過期或即將過期")
    if Z3A_REFRESH_TOKEN:
        rexp = _jwt_exp(Z3A_REFRESH_TOKEN)
        if rexp and now > rexp:
            log.warning("⚠ refresh token 也過期（exp=%s），跳過 refresh",
                        datetime.fromtimestamp(rexp).strftime("%Y-%m-%d"))
        else:
            log.info("→ 嘗試用 refresh token 換新 access token…")
            new_tok = _refresh_with_token2(Z3A_REFRESH_TOKEN)
            if new_tok:
                TOKEN = new_tok
                return True

    # 最後一招：自動登入（會被驗證碼擋）
    log.info("→ 嘗試用帳密自動登入（雲端強制驗證碼，多半失敗）…")
    new_tok = _login_with_phone(Z3A_PHONE, Z3A_PASSWORD)
    if new_tok:
        TOKEN = new_tok
        return True

    log.error("✗ 所有取得 token 的方式都失敗。")
    log.error("  請手動更新 .env.dev 的 Z3A_TOKEN：")
    log.error("    1. 啟雲物聯 App 重新登入一次")
    log.error("    2. Fiddler 抓 POST /user/login 回應，取 data.tokenString")
    log.error("    3. 貼到 Z3A_TOKEN= 後重試")
    return False


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
        raw = r.json()
        data = raw.get("data") or []
        # Z3A 雲端有時把 data 欄位雙重編碼成 JSON 字串，需要手動 parse
        if isinstance(data, str):
            data = json.loads(data)
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
# Pipeline 整合（--pipeline 模式）
# ════════════════════════════════════════════════════════════════════════════════

PIPELINE_DIR = Path(__file__).parent / "fixed_data_process_visualization"


def _panel_id_to_filename(panel_id: str) -> str:
    """
    將 panel_id 轉換為 pipeline 步驟 4 能識別的檔名格式。
      Panel_20_180_A → 傾角20度方位角180度.csv
      Panel_20_180_B → 傾角20度方位角180度1.csv
      Tracking_2_25_上 → 追日系統2 傾角25上.csv
    步驟 4 邏輯：檔名含「1」→ _B 面板；不含「1」→ _A 面板。
    """
    if panel_id.startswith("Panel_"):
        parts = panel_id.split("_")          # ['Panel', '20', '180', 'A']
        tilt, azimuth, ab = parts[1], parts[2], parts[3]
        suffix = "1" if ab == "B" else ""
        return f"傾角{tilt}度方位角{azimuth}度{suffix}.csv"
    elif panel_id.startswith("Tracking_"):
        parts = panel_id.split("_")          # ['Tracking', '2', '25', '上']
        system, tilt, position = parts[1], parts[2], parts[3]
        return f"追日系統{system} 傾角{tilt}{position}.csv"
    return f"{panel_id}.csv"


def _load_pipeline_module(filename: str, module_name: str):
    """載入 fixed_data_process_visualization/ 下（檔名可能含空格的）.py 檔。"""
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        module_name, str(PIPELINE_DIR / filename)
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _save_raw_csvs(all_panel_raw: dict, output_dir: Path):
    """
    將所有面板的原始資料存成 pipeline 步驟 2 能讀的 CSV 格式。
    每台裝置一個檔案，欄位：日期时间 / 直流电压V / 直流电电流mA / 直流电电流A
    all_panel_raw: {device_id: [(dt, voltage_V, current_mA, current_A), ...]}
    """
    output_dir.mkdir(parents=True, exist_ok=True)

    for device_id, meta in PANEL_MAP.items():
        panel_id = meta[0]
        rows = all_panel_raw.get(device_id, [])

        if not rows:
            log.warning("  %-25s → 無資料，跳過", panel_id)
            continue

        df = pd.DataFrame(rows, columns=["_dt", "直流电压V", "直流电电流mA", "直流电电流A"])
        df = df.drop_duplicates("_dt").sort_values("_dt")
        df.insert(0, "日期时间", df["_dt"].dt.strftime("%Y-%m-%d %H:%M:%S"))
        df = df.drop(columns=["_dt"])

        filename = _panel_id_to_filename(panel_id)
        df.to_csv(output_dir / filename, index=False, encoding="utf-8-sig")
        log.info("  %-25s → %s（%d 筆）", panel_id, filename, len(df))


def _run_step2(folder: Path):
    """步驟 2：計算功率（power calculation2.py），更新 folder 內所有 CSV。"""
    log.info("步驟 2：計算功率（power calculation2.py）…")
    mod = _load_pipeline_module("power calculation2.py", "power_calculation2")
    mod.batch_process_folder(str(folder))
    log.info("步驟 2 完成")


def _run_step4(folder: Path) -> Path:
    """步驟 4：pvlib 太陽角度計算，匯出 complete_solar_data.csv。"""
    log.info("步驟 4：太陽角度計算（data preprocessing4.py）…")
    mod = _load_pipeline_module("data preprocessing4.py", "data_preprocessing4")

    db_path = str(folder / "_pipeline_temp.db")
    proc = mod.SolarAngleDataProcessor(db_path=db_path)
    proc.import_csv_files(str(folder), clear_existing=True)
    proc.process_data(overwrite=True, filter_azimuth=False)
    proc.remove_duplicates()

    complete_csv = folder / "complete_solar_data.csv"
    proc.export_complete_data(str(complete_csv))
    proc.close()

    Path(db_path).unlink(missing_ok=True)
    log.info("步驟 4 完成 → %s", complete_csv)
    return complete_csv


def _run_step5_combine(new_csv: Path, dry_run: bool = False):
    """步驟 5：將 pipeline 輸出合併進主 CSV（去重 + 排序 + 備份）。"""
    log.info("步驟 5：合併進主資料集…")

    new_df = pd.read_csv(new_csv, dtype=str, low_memory=False)
    log.info("  新資料（pipeline 輸出）：%d 筆", len(new_df))

    if dry_run:
        log.info("[DRY RUN] 不寫入 CSV，印出前 5 筆：")
        print(new_df.head().to_string())
        return

    if CSV_PATH.exists():
        existing = pd.read_csv(CSV_PATH, dtype=str, low_memory=False)
        log.info("  現有資料：%d 筆", len(existing))
    else:
        existing = pd.DataFrame()

    combined = pd.concat([existing, new_df], ignore_index=True)
    before = len(combined)
    combined = combined.drop_duplicates(subset=["timestamp", "panel_id"], keep="last")
    log.info("  去重後：%d 筆（移除 %d 筆）", len(combined), before - len(combined))

    combined["_ts_sort"] = pd.to_datetime(combined["timestamp"], format="mixed", errors="coerce")
    combined = combined.sort_values(["_ts_sort", "panel_id"]).drop(columns=["_ts_sort"])

    if CSV_PATH.exists():
        import shutil
        backup = CSV_PATH.with_suffix(f".bak.{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv")
        shutil.copy2(CSV_PATH, backup)
        log.info("  備份至：%s", backup)

    combined.to_csv(CSV_PATH, index=False, encoding="utf-8-sig")
    log.info("✓ 已寫入 %s（共 %d 筆）", CSV_PATH, len(combined))


# ════════════════════════════════════════════════════════════════════════════════
# 主流程
# ════════════════════════════════════════════════════════════════════════════════

def main():
    global CSV_PATH

    parser = argparse.ArgumentParser(description="Z3A 資料收集並合併至 combined CSV")
    parser.add_argument("--days",  type=int, default=7,
                        help="抓最近幾天的資料（預設 7 天）")
    parser.add_argument("--start", type=str, default=None,
                        help="開始日期 YYYY-MM-DD（優先於 --days）")
    parser.add_argument("--end",   type=str, default=None,
                        help="結束日期 YYYY-MM-DD（預設今天）")
    parser.add_argument("--dry-run", action="store_true",
                        help="只印出會做什麼，不寫入 CSV")
    parser.add_argument("--pipeline", action="store_true",
                        help="輸出原始 CSV → 自動執行前處理 pipeline（步驟 2+4+5）再合併")
    args = parser.parse_args()

    env = _load_env_file()
    csv_path = os.environ.get("Z3A_CSV_PATH") or env.get("Z3A_CSV_PATH")
    if csv_path:
        CSV_PATH = Path(csv_path)

    # 日期範圍
    end_date   = args.end   or date.today().strftime("%Y-%m-%d")
    start_date = args.start or (
        date.today() - timedelta(days=args.days - 1)
    ).strftime("%Y-%m-%d")

    log.info("═" * 60)
    log.info("Z3A 資料收集  %s → %s", start_date, end_date)
    log.info("目標 CSV：%s", CSV_PATH)
    log.info("═" * 60)

    # 確認 Token 有效期（過期會自動用 PHONE/PASSWORD 重新登入）
    if not _ensure_valid_token():
        log.error("無法取得有效 token，中止。")
        sys.exit(1)

    # 取得 DeviceType 對照
    device_types = fetch_device_types()

    # 把日期範圍拆成 ≤7 天的區段，確保 API 回傳 10 分鐘解析度
    CHUNK_DAYS = 7
    start_dt = datetime.strptime(start_date, "%Y-%m-%d")
    end_dt   = datetime.strptime(end_date,   "%Y-%m-%d")
    chunks = []
    cur = start_dt
    while cur <= end_dt:
        chunk_end = min(cur + timedelta(days=CHUNK_DAYS - 1), end_dt)
        chunks.append((cur.strftime("%Y-%m-%d"), chunk_end.strftime("%Y-%m-%d")))
        cur = chunk_end + timedelta(days=1)
    log.info("日期範圍拆成 %d 個區段（每段 ≤%d 天）", len(chunks), CHUNK_DAYS)

    # ── Pipeline 模式 ──────────────────────────────────────────────────────────
    if args.pipeline:
        all_panel_raw: dict = {did: [] for did in PANEL_MAP}

        for chunk_start, chunk_end in chunks:
            log.info("── 區段 %s → %s（抓取原始資料）──", chunk_start, chunk_end)
            for device_id, meta in PANEL_MAP.items():
                dtype = device_types.get(device_id, "2")
                panel_id = meta[0]

                v_series = fetch_series(device_id, dtype, 1, chunk_start, chunk_end)
                i_series = fetch_series(device_id, dtype, 5, chunk_start, chunk_end)

                # 電流原始值對照表（時間 → raw dca_value）
                i_raw_dict: dict = {}
                for p in i_series:
                    dt = parse_z3a_time(p["time"])
                    if dt and p["value"] is not None:
                        i_raw_dict[dt] = float(p["value"])
                # 電壓對照表（時間 → V）
                v_dict: dict = {}
                for p in v_series:
                    dt = parse_z3a_time(p["time"])
                    if dt and p["value"] is not None:
                        v_dict[dt] = float(p["value"]) / VOLTAGE_DIV

                all_ts = sorted(set(v_dict) | set(i_raw_dict))
                for dt in all_ts:
                    raw_i = i_raw_dict.get(dt, 0.0)
                    all_panel_raw[device_id].append((
                        dt,
                        v_dict.get(dt, 0.0),
                        raw_i / 1_000_000,
                        raw_i / CURRENT_DIV,
                    ))
                log.info("    %-20s -> %-25s (%d 筆)",
                         device_id, panel_id, len(all_ts))

        log.info("═" * 60)
        out_dir = (Path(__file__).parent / "z3a_pipeline_output"
                   / f"{start_date}_{end_date}")
        log.info("儲存原始 CSV -> %s", out_dir)
        _save_raw_csvs(all_panel_raw, out_dir)

        _run_step2(out_dir)
        complete_csv = _run_step4(out_dir)
        _run_step5_combine(complete_csv, dry_run=args.dry_run)

        log.info("═" * 60)
        log.info("Pipeline 完成！日期範圍：%s -> %s", start_date, end_date)
        return

    # ── 一般模式（不跑 pipeline，直接合併 build_panel_df 的輸出）──────────
    all_new_dfs = []
    for chunk_start, chunk_end in chunks:
        log.info("── 區段 %s -> %s ──", chunk_start, chunk_end)
        for device_id, meta in PANEL_MAP.items():
            dtype = device_types.get(device_id, "2")
            df = build_panel_df(device_id, dtype, chunk_start, chunk_end)
            if df is not None and not df.empty:
                all_new_dfs.append(df)

    if not all_new_dfs:
        log.error("沒有抓到任何資料，請確認 Token 是否有效或時段是否正確。")
        sys.exit(1)

    new_df = pd.concat(all_new_dfs, ignore_index=True)
    log.info("新抓取資料：%d 筆 (%d 台裝置)", len(new_df), len(all_new_dfs))

    if args.dry_run:
        log.info("[DRY RUN] 不寫入 CSV，印出前 5 筆：")
        print(new_df.head().to_string())
        return

    if CSV_PATH.exists():
        log.info("讀取現有 CSV (%s) …", CSV_PATH)
        try:
            existing = pd.read_csv(CSV_PATH, dtype=str, low_memory=False)
            log.info("  現有資料：%d 筆", len(existing))
        except Exception as e:
            log.error("讀取失敗：%s", e)
            sys.exit(1)
    else:
        log.info("CSV 不存在，建立新檔案")
        existing = pd.DataFrame()

    new_df_str = new_df.astype(str).replace("nan", "").replace("<NA>", "")
    combined = pd.concat([existing, new_df_str], ignore_index=True)

    before = len(combined)
    combined = combined.drop_duplicates(subset=["timestamp", "panel_id"], keep="last")
    log.info("去重後：%d 筆 (移除 %d 筆重複)", len(combined), before - len(combined))

    combined["_ts_sort"] = pd.to_datetime(combined["timestamp"], format="mixed", errors="coerce")
    combined = combined.sort_values(["_ts_sort", "panel_id"]).drop(columns=["_ts_sort"])

    if CSV_PATH.exists():
        import shutil
        backup_path = CSV_PATH.with_suffix(f".bak.{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv")
        shutil.copy2(CSV_PATH, backup_path)
        log.info("原始檔案備份至：%s", backup_path)

    combined.to_csv(CSV_PATH, index=False, encoding="utf-8-sig")
    log.info("✓ 已寫入 %s (共 %d 筆)", CSV_PATH, len(combined))
    log.info("═" * 60)
    log.info("完成！新增資料：%d 筆，覆蓋日期範圍：%s -> %s",
             len(new_df), start_date, end_date)

    panel_counts = new_df.groupby("panel_id").size().sort_index()
    log.info("\n各面板新增筆數：")
    for pid, cnt in panel_counts.items():
        log.info("  %-25s  %4d 筆", pid, cnt)


if __name__ == "__main__":
    main()
