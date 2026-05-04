"""
fixed_panel_api.py  -  固定式面板歷史數據 API（pandas in-memory cache）
"""
import os, threading, gzip as _gzip, io, shutil
import pandas as pd
from django.http import JsonResponse, HttpResponse, FileResponse, StreamingHttpResponse
from django.views import View
from django.conf import settings

_GZ_CACHE_PATH = "/tmp/fp_data_cache.csv.gz"   # 磁碟上的 gzip 快取（節省記憶體）

_df = None
_df_lock = threading.Lock()
_load_error = None


def _get_data_path():
    return getattr(settings, "FIXED_PANEL_DATA_PATH",
                   "/usr/src/app/data/combined_solar_data_20250301_20260406_processed.csv")


def get_df():
    global _df, _load_error
    if _df is not None:
        return _df
    with _df_lock:
        if _df is not None:
            return _df
        path = _get_data_path()
        if not os.path.exists(path):
            _load_error = f"找不到資料檔案: {path}"
            return None
        try:
            df = pd.read_csv(path, usecols=[
                "timestamp", "date", "tilt_angle", "azimuth_angle",
                "power_W", "panel_id", "voltage", "current_A",
                "daily_energy_Wh", "hour_decimal",
            ], dtype={
                "power_W": "float32", "voltage": "float32",
                "current_A": "float32", "daily_energy_Wh": "float32",
                "hour_decimal": "float32",
            })
            # 追日面板的 azimuth_angle 為字串（「追日」/「tracking」）
            # 轉成數值，無法轉換的變 NaN，再過濾掉 → 只留固定式面板
            df["azimuth_angle"] = pd.to_numeric(df["azimuth_angle"], errors="coerce")
            df["tilt_angle"]    = pd.to_numeric(df["tilt_angle"],    errors="coerce")
            df = df.dropna(subset=["azimuth_angle", "tilt_angle"])
            df["azimuth_angle"] = df["azimuth_angle"].astype("float32")
            df["tilt_angle"]    = df["tilt_angle"].astype("float32")
            df["date"]      = pd.to_datetime(df["date"],      format="mixed")
            df["timestamp"] = pd.to_datetime(df["timestamp"], format="mixed")
            df["month"]     = df["date"].dt.to_period("M").astype(str)
            df["date_str"]  = df["date"].dt.strftime("%Y-%m-%d")
            df["year"]      = df["date"].dt.year
            df["tilt_i"]    = df["tilt_angle"].astype(int)
            df["azimuth_i"] = df["azimuth_angle"].astype(int)
            df["group"]     = df["tilt_i"].astype(str) + "°/" + df["azimuth_i"].astype(str) + "°"
            _df = df
            _load_error = None
        except Exception as exc:
            _load_error = str(exc)
            return None
    return _df


def _err(msg, status=500):
    return JsonResponse({"error": msg}, status=status)


# ── Summary ──────────────────────────────────────────────────────────
class FixedPanelSummaryView(View):
    def get(self, request):
        df = get_df()
        if df is None:
            return _err(_load_error or "資料未載入", 404)
        groups = (
            df[["tilt_i", "azimuth_i", "group"]].drop_duplicates()
            .sort_values(["tilt_i", "azimuth_i"])
            .apply(lambda r: {"tilt": r["tilt_i"], "azimuth": r["azimuth_i"], "label": r["group"]}, axis=1)
            .tolist()
        )
        return JsonResponse({
            "total_records":    int(len(df)),
            "date_range":       {"start": df["date"].min().strftime("%Y-%m-%d"),
                                 "end":   df["date"].max().strftime("%Y-%m-%d")},
            "panel_groups":     groups,
            "available_months": sorted(df["month"].unique().tolist()),
            "available_years":  sorted(df["year"].unique().tolist()),
        })


# ── Monthly avg hourly power curve (by group) ────────────────────────
class FixedPanelPowerCurveView(View):
    def get(self, request):
        df = get_df()
        if df is None:
            return _err(_load_error or "資料未載入", 404)
        month = request.GET.get("month")
        filtered = df if not month else df[df["month"] == month]
        if filtered.empty:
            return JsonResponse({"labels": [], "datasets": []})
        curve = (filtered.groupby(["hour_decimal", "group", "tilt_i", "azimuth_i"])["power_W"]
                 .mean().reset_index())
        groups = (curve[["group", "tilt_i", "azimuth_i"]].drop_duplicates()
                  .sort_values(["tilt_i", "azimuth_i"]))
        labels = sorted(curve["hour_decimal"].unique().tolist())
        datasets = []
        for _, g in groups.iterrows():
            gd = curve[curve["group"] == g["group"]].set_index("hour_decimal")["power_W"]
            datasets.append({"label": g["group"], "tilt": int(g["tilt_i"]), "azimuth": int(g["azimuth_i"]),
                             "data": [round(float(gd.get(h, 0)), 2) for h in labels]})
        return JsonResponse({"labels": labels, "datasets": datasets})


# ── Monthly average per group ────────────────────────────────────────
class FixedPanelMonthlyView(View):
    def get(self, request):
        df = get_df()
        if df is None:
            return _err(_load_error or "資料未載入", 404)
        year = request.GET.get("year")
        filtered = df if not year else df[df["year"] == int(year)]
        if filtered.empty:
            return JsonResponse({"months": [], "groups": [], "matrix": {}})
        monthly = (filtered.groupby(["month", "group", "tilt_i", "azimuth_i"])["power_W"]
                   .mean().round(2).reset_index())
        months = sorted(monthly["month"].unique().tolist())
        groups = (monthly[["group", "tilt_i", "azimuth_i"]].drop_duplicates()
                  .sort_values(["tilt_i", "azimuth_i"]).to_dict(orient="records"))
        matrix = {}
        for _, row in monthly.iterrows():
            matrix.setdefault(row["group"], {})[row["month"]] = float(row["power_W"])
        return JsonResponse({"months": months, "groups": groups, "matrix": matrix})


# ── Daily avg per group for one month ───────────────────────────────
class FixedPanelDailyView(View):
    def get(self, request):
        df = get_df()
        if df is None:
            return _err(_load_error or "資料未載入", 404)
        month   = request.GET.get("month")
        tilt    = request.GET.get("tilt")
        azimuth = request.GET.get("azimuth")
        filtered = df if not month else df[df["month"] == month]
        if tilt:    filtered = filtered[filtered["tilt_i"]    == int(tilt)]
        if azimuth: filtered = filtered[filtered["azimuth_i"] == int(azimuth)]
        if filtered.empty:
            return JsonResponse({"labels": [], "datasets": []})
        daily = (filtered.groupby(["date_str", "group", "tilt_i", "azimuth_i"])["power_W"]
                 .mean().round(2).reset_index())
        labels = sorted(daily["date_str"].unique().tolist())
        groups = (daily[["group", "tilt_i", "azimuth_i"]].drop_duplicates()
                  .sort_values(["tilt_i", "azimuth_i"]))
        datasets = []
        for _, g in groups.iterrows():
            gd = daily[daily["group"] == g["group"]].set_index("date_str")["power_W"]
            datasets.append({"label": g["group"], "tilt": int(g["tilt_i"]), "azimuth": int(g["azimuth_i"]),
                             "data": [round(float(gd.get(d, 0)), 2) for d in labels]})
        return JsonResponse({"labels": labels, "datasets": datasets})


# ── Panel list ───────────────────────────────────────────────────────
class FixedPanelPanelListView(View):
    def get(self, request):
        df = get_df()
        if df is None:
            return _err(_load_error or "資料未載入", 404)
        panels = (
            df[["panel_id", "tilt_i", "azimuth_i", "group"]].drop_duplicates()
            .sort_values(["tilt_i", "azimuth_i", "panel_id"])
            .apply(lambda r: {"panel_id": str(r["panel_id"]), "tilt": int(r["tilt_i"]),
                              "azimuth": int(r["azimuth_i"]), "group": r["group"]}, axis=1)
            .tolist()
        )
        return JsonResponse({"panels": panels})


# ── Single-day hourly curve — supports panel_id OR tilt+azimuth ──────
class FixedPanelDayCurveView(View):
    """
    GET /api/fixed-panels/day-curve/?date=YYYY-MM-DD
        [&panel_id=Panel_20_180_A]   single panel
        [&tilt=20&azimuth=180]       whole group (A+B)
    """
    def get(self, request):
        df = get_df()
        if df is None:
            return _err(_load_error or "資料未載入", 404)
        date     = request.GET.get("date")
        panel_id = request.GET.get("panel_id")
        tilt     = request.GET.get("tilt")
        azimuth  = request.GET.get("azimuth")
        if not date:
            return _err("date 參數必填", 400)

        filtered = df[df["date_str"] == date]
        if panel_id:
            filtered = filtered[filtered["panel_id"] == panel_id]
        else:
            if tilt:    filtered = filtered[filtered["tilt_i"]    == int(tilt)]
            if azimuth: filtered = filtered[filtered["azimuth_i"] == int(azimuth)]

        if filtered.empty:
            return JsonResponse({"date": date, "labels": [], "datasets": [], "energy_wh": {}})

        curve = (filtered
                 .groupby(["hour_decimal", "panel_id", "tilt_i", "azimuth_i", "group"])["power_W"]
                 .mean().reset_index())
        labels = sorted(curve["hour_decimal"].unique().tolist())
        panels_df = (curve[["panel_id", "tilt_i", "azimuth_i", "group"]].drop_duplicates()
                     .sort_values(["tilt_i", "azimuth_i", "panel_id"]))
        datasets = []
        for _, p in panels_df.iterrows():
            pid = str(p["panel_id"])
            pd_data = curve[curve["panel_id"] == p["panel_id"]].set_index("hour_decimal")["power_W"]
            datasets.append({
                "label":   pid,
                "group":   p["group"],
                "tilt":    int(p["tilt_i"]),
                "azimuth": int(p["azimuth_i"]),
                "data":    [round(float(pd_data.get(h, 0)), 2) for h in labels],
            })
        energy = (filtered.groupby("panel_id")["daily_energy_Wh"].max().round(1).reset_index())
        energy_map = {str(r["panel_id"]): float(r["daily_energy_Wh"]) for _, r in energy.iterrows()}
        return JsonResponse({"date": date, "labels": labels, "datasets": datasets, "energy_wh": energy_map})


# ── Panel-group trend: A vs B for a tilt+azimuth combo ───────────────
class FixedPanelPanelTrendView(View):
    """
    GET /api/fixed-panels/panel-trend/
        ?tilt=20&azimuth=180          returns both A and B panels
        [&month=2025-06]              optional month filter
        [&panel_id=Panel_20_180_A]    single panel fallback
    """
    def get(self, request):
        df = get_df()
        if df is None:
            return _err(_load_error or "資料未載入", 404)

        panel_id = request.GET.get("panel_id")
        tilt     = request.GET.get("tilt")
        azimuth  = request.GET.get("azimuth")
        month    = request.GET.get("month")

        if panel_id:
            filtered = df[df["panel_id"] == panel_id]
        elif tilt and azimuth:
            filtered = df[(df["tilt_i"] == int(tilt)) & (df["azimuth_i"] == int(azimuth))]
        else:
            return _err("需要提供 panel_id 或 tilt+azimuth", 400)

        if month:
            filtered = filtered[filtered["month"] == month]

        if filtered.empty:
            return JsonResponse({"labels": [], "datasets": []})

        # daily avg per panel_id
        daily = (
            filtered
            .groupby(["date_str", "panel_id"])
            .agg(power_W=("power_W", "mean"), daily_energy_Wh=("daily_energy_Wh", "max"))
            .round(2).reset_index().sort_values("date_str")
        )
        labels = sorted(daily["date_str"].unique().tolist())
        panel_ids = sorted(daily["panel_id"].unique().tolist())

        datasets = []
        for pid in panel_ids:
            p_data = daily[daily["panel_id"] == pid].set_index("date_str")
            datasets.append({
                "panel_id":  pid,
                "label":     pid.replace("Panel_", ""),
                "power":     [round(float(p_data["power_W"].get(d, 0)), 2) for d in labels],
                "energy_wh": [round(float(p_data["daily_energy_Wh"].get(d, 0)), 2) for d in labels],
            })

        return JsonResponse({"labels": labels, "datasets": datasets})


# ─────────────────────────────────────────────────────────────────────────────
# 固定式面板 CSV 下載端點（供前端自動載入，無需手動上傳）
# ─────────────────────────────────────────────────────────────────────────────
class FixedPanelRawCSVView(View):
    """
    GET /api/fixed-panels/raw-csv/
    回傳 DataFrame 中前端所需欄位的 CSV，gzip 壓縮後回傳並快取。
    前端僅需 fetch 一次，之後由瀏覽器快取（ETag + Cache-Control）。
    """
    def get(self, request):
        path = _get_data_path()
        if not os.path.exists(path):
            return JsonResponse({"error": "找不到資料檔案"}, status=404)

        # 直接串流原始 CSV，不做 gz 快取（避免截斷問題）
        resp = FileResponse(
            open(path, "rb"),
            content_type="text/csv; charset=utf-8",
        )
        resp["Content-Disposition"] = 'inline; filename="fixed_panel_data.csv"'
        resp["Content-Length"] = os.path.getsize(path)
        resp["Cache-Control"] = "no-cache"
        return resp


# ── 診斷端點：看後端載入狀態與錯誤 ──────────────────────────────────────────
class FixedPanelStatusView(View):
    def get(self, request):
        import os
        path = _get_data_path()
        file_exists = os.path.exists(path)
        file_size = os.path.getsize(path) if file_exists else 0
        return JsonResponse({
            "df_loaded": _df is not None,
            "df_rows": int(len(_df)) if _df is not None else 0,
            "load_error": _load_error,
            "csv_path": path,
            "file_exists": file_exists,
            "file_size_mb": round(file_size / 1024 / 1024, 1),
        })
