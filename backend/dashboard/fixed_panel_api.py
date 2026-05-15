"""
fixed_panel_api.py  -  固定式面板歷史數據 API（pandas in-memory cache）
"""
import os
import threading
import pandas as pd
from django.http import JsonResponse, FileResponse
from django.views import View
from django.conf import settings


_df = None
_df_mtime = 0          # 上次載入時的檔案 mtime，用於偵測檔案是否被外部更新
_df_lock = threading.Lock()
_load_error = None


def _get_data_path():
    return getattr(settings, "FIXED_PANEL_DATA_PATH",
                   "/usr/src/app/data/combined_solar_data_20250301_20260406_processed.csv")


def invalidate_df_cache():
    """手動清除快取，下次呼叫 get_df() 會重新從 CSV 載入。"""
    global _df, _df_mtime
    with _df_lock:
        _df = None
        _df_mtime = 0


def get_df():
    global _df, _df_mtime, _load_error
    path = _get_data_path()
    # mtime 自動重載：若 CSV 比快取版本新，丟掉快取重讀
    if _df is not None and os.path.exists(path):
        try:
            current_mtime = os.path.getmtime(path)
            if current_mtime > _df_mtime:
                _df = None   # 觸發重載
        except OSError:
            pass
    if _df is not None:
        return _df
    with _df_lock:
        if _df is not None:
            return _df
        if not os.path.exists(path):
            _load_error = f"找不到資料檔案: {path}"
            return None
        try:
            available_cols = pd.read_csv(path, nrows=0).columns.tolist()
            base_cols = [
                "timestamp", "date", "tilt_angle", "azimuth_angle",
                "power_W", "panel_id", "voltage", "current_A",
                "daily_energy_Wh", "hour_decimal",
            ]
            optional_cols = ["illumination"]
            usecols = base_cols + [c for c in optional_cols if c in available_cols]
            dtype_map = {
                "power_W": "float32", "voltage": "float32",
                "current_A": "float32", "daily_energy_Wh": "float32",
                "hour_decimal": "float32",
            }
            if "illumination" in usecols:
                dtype_map["illumination"] = "float32"
            df = pd.read_csv(path, usecols=usecols, dtype=dtype_map)
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
            try:
                _df_mtime = os.path.getmtime(path)
            except OSError:
                _df_mtime = 0
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


# ── Single-day hourly curve ─────────────────────────────────────────
class FixedPanelDayCurveView(View):
    """GET /api/fixed-panels/day-curve/?date=YYYY-MM-DD [&panel_id=...] [&tilt=&azimuth=]"""
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
    """GET /api/fixed-panels/panel-trend/?tilt=20&azimuth=180 [&month=YYYY-MM] [&panel_id=...]"""
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
# 固定式面板 CSV 下載端點
# ─────────────────────────────────────────────────────────────────────────────
class FixedPanelRawCSVView(View):
    def get(self, request):
        path = _get_data_path()
        if not os.path.exists(path):
            return JsonResponse({"error": "找不到資料檔案"}, status=404)
        resp = FileResponse(
            open(path, "rb"),
            content_type="text/csv; charset=utf-8",
        )
        resp["Content-Disposition"] = 'inline; filename="fixed_panel_data.csv"'
        resp["Content-Length"] = os.path.getsize(path)
        resp["Cache-Control"] = "no-cache"
        return resp


# ── 快取重載端點（scheduled task 抓完新資料後呼叫）─────────────────
from django.views.decorators.csrf import csrf_exempt
from django.utils.decorators import method_decorator

@method_decorator(csrf_exempt, name='dispatch')
class FixedPanelReloadView(View):
    """POST /api/fixed-panels/reload/ — 強制丟掉記憶體 cache，下次查詢會重讀 CSV"""
    def post(self, request):
        invalidate_df_cache()
        df = get_df()
        if df is None:
            return JsonResponse({"success": False, "error": _load_error or "資料未載入"}, status=500)
        return JsonResponse({
            "success":  True,
            "df_rows":  int(len(df)),
            "date_range": {
                "start": df["date"].min().strftime("%Y-%m-%d"),
                "end":   df["date"].max().strftime("%Y-%m-%d"),
            },
            "reloaded_at": _now_str(),
        })

    # 也允許 GET 方便手動測試
    def get(self, request):
        return self.post(request)


def _now_str():
    from datetime import datetime
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


# ── 診斷端點 ─────────────────────────────────────────────────────────
class FixedPanelStatusView(View):
    def get(self, request):
        path = _get_data_path()
        df = get_df()
        return JsonResponse({
            "data_path":     path,
            "file_exists":   os.path.exists(path),
            "file_size_mb":  round(os.path.getsize(path) / 1024 / 1024, 2) if os.path.exists(path) else None,
            "df_loaded":     df is not None,
            "df_rows":       int(len(df)) if df is not None else 0,
            "df_columns":    list(df.columns) if df is not None else [],
            "load_error":    _load_error,
        })


# ─────────────────────────────────────────────────────────────────────────────
# 固定式面板研究 KPI 摘要 endpoint — 給總覽頁 + 研究頁的 KPI 卡使用
# 由後端 pandas 直接算累計 kWh、各組合 / 方位 / 傾角 / 季節能量等
# ─────────────────────────────────────────────────────────────────────────────
class FixedPanelKpiSummaryView(View):
    """
    GET /api/fixed-panels/kpi-summary/[?season=spring|summer|fall|winter|all]

    回傳：
      total_energy_kwh, total_panels, date_range
      per_group:  [{group, tilt, azimuth, energy_kwh, rank, panels_n}, ...]
      best_group / worst_group / diff_pct
      by_tilt / by_azimuth / by_season
      ab_consistency: [{group, panel_a, panel_b, energy_a, energy_b, diff_pct}, ...]
    """
    SEASON_MONTHS = {
        "spring": (3, 4, 5),
        "summer": (6, 7, 8),
        "fall":   (9, 10, 11),
        "winter": (12, 1, 2),
    }

    def get(self, request):
        df = get_df()
        if df is None:
            return _err(_load_error or "資料未載入", 404)

        season = (request.GET.get("season") or "all").lower()
        if season != "all" and season in self.SEASON_MONTHS:
            months = self.SEASON_MONTHS[season]
            df_s = df[df["date"].dt.month.isin(months)]
        else:
            df_s = df

        if df_s.empty:
            return JsonResponse({"error": "filtered_empty"}, status=200)

        # 每片面板每天的最大 daily_energy_Wh = 該天該片的累計能量
        day_energy = (
            df_s.groupby(["panel_id", "date_str", "tilt_i", "azimuth_i", "group"])
                ["daily_energy_Wh"].max().reset_index()
        )
        total_wh = float(day_energy["daily_energy_Wh"].sum())
        total_kwh = round(total_wh / 1000, 2)
        total_panels = int(df_s["panel_id"].nunique())

        grp = (day_energy.groupby(["group", "tilt_i", "azimuth_i"])
               ["daily_energy_Wh"].sum().reset_index()
               .rename(columns={"daily_energy_Wh": "energy_wh"}))
        grp["energy_kwh"] = (grp["energy_wh"] / 1000).round(2)
        grp = grp.sort_values("energy_kwh", ascending=False).reset_index(drop=True)
        grp["rank"] = grp.index + 1

        panels_per_group = (
            day_energy.groupby("group")["panel_id"].nunique().to_dict()
        )

        per_group = [{
            "group":      row["group"],
            "tilt":       int(row["tilt_i"]),
            "azimuth":    int(row["azimuth_i"]),
            "energy_kwh": float(row["energy_kwh"]),
            "rank":       int(row["rank"]),
            "panels_n":   int(panels_per_group.get(row["group"], 0)),
        } for _, row in grp.iterrows()]

        best  = per_group[0]  if per_group else None
        worst = per_group[-1] if per_group else None
        diff_pct = None
        if best and worst and worst["energy_kwh"] > 0:
            diff_pct = round((best["energy_kwh"] - worst["energy_kwh"]) / worst["energy_kwh"] * 100, 1)

        by_tilt = (day_energy.groupby("tilt_i")["daily_energy_Wh"].sum() / 1000).round(2)
        by_tilt = [{"tilt": int(k), "energy_kwh": float(v)} for k, v in by_tilt.items()]
        by_tilt.sort(key=lambda r: r["tilt"])

        by_azi = (day_energy.groupby("azimuth_i")["daily_energy_Wh"].sum() / 1000).round(2)
        by_azi = [{"azimuth": int(k), "energy_kwh": float(v)} for k, v in by_azi.items()]
        by_azi.sort(key=lambda r: r["azimuth"])

        by_season = []
        if season == "all":
            for sname, months in self.SEASON_MONTHS.items():
                sdf = df[df["date"].dt.month.isin(months)]
                if sdf.empty:
                    continue
                s_day = (sdf.groupby(["panel_id", "date_str"])["daily_energy_Wh"]
                          .max().reset_index())
                e = float(s_day["daily_energy_Wh"].sum()) / 1000
                by_season.append({"season": sname, "energy_kwh": round(e, 2)})

        # A vs B 一致性檢定
        ab = []
        panel_sums = (day_energy.groupby(["panel_id", "group", "tilt_i", "azimuth_i"])
                      ["daily_energy_Wh"].sum().reset_index())
        panel_sums["energy_kwh"] = (panel_sums["daily_energy_Wh"] / 1000).round(2)
        for group_name, gdf in panel_sums.groupby("group"):
            panels = gdf.sort_values("panel_id")
            if len(panels) < 2:
                continue
            pa = panels[panels["panel_id"].astype(str).str.endswith("_A")]
            pb = panels[panels["panel_id"].astype(str).str.endswith("_B")]
            if pa.empty or pb.empty:
                continue
            ea = float(pa.iloc[0]["energy_kwh"])
            eb = float(pb.iloc[0]["energy_kwh"])
            mn = min(ea, eb)
            diff = round(abs(ea - eb) / mn * 100, 2) if mn > 0 else 0
            ab.append({
                "group":     group_name,
                "tilt":      int(panels.iloc[0]["tilt_i"]),
                "azimuth":   int(panels.iloc[0]["azimuth_i"]),
                "panel_a":   str(pa.iloc[0]["panel_id"]),
                "panel_b":   str(pb.iloc[0]["panel_id"]),
                "energy_a":  ea,
                "energy_b":  eb,
                "diff_pct":  diff,
            })
        ab.sort(key=lambda r: (r["tilt"], r["azimuth"]))

        return JsonResponse({
            "season":           season,
            "total_energy_kwh": total_kwh,
            "total_panels":     total_panels,
            "date_range": {
                "start": df_s["date"].min().strftime("%Y-%m-%d"),
                "end":   df_s["date"].max().strftime("%Y-%m-%d"),
            },
            "per_group":      per_group,
            "best_group":     best,
            "worst_group":    worst,
            "diff_pct":       diff_pct,
            "by_tilt":        by_tilt,
            "by_azimuth":     by_azi,
            "by_season":      by_season,
            "ab_consistency": ab,
        })
