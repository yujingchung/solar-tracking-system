"""
z3a_api.py  ——  QY-Z3A IoT 採集裝置歷史數據代理 API

端點：
  GET  /api/z3a/devices/    列出所有綁定裝置
  GET  /api/z3a/history/    取得單一裝置的歷史數據
  GET  /api/z3a/status/     Token / 連線狀態診斷
  POST /api/z3a/refresh/    手動觸發 Token 重新登入

設定（settings.py 或環境變數）：
  Z3A_BASE_URL  — API 根 URL
  Z3A_PHONE     — 手機號（用於自動重新登入）
  Z3A_PASSWORD  — 密碼
  Z3A_TOKEN     — 初始 Bearer Token（可留空，由 PHONE+PASSWORD 自動取得）
"""

import base64, json, logging, os, threading, time

# requests 是選用依賴（Docker 環境可能尚未安裝）
# 若未安裝，Z3A 端點會回傳 503，其他 API 不受影響
try:
    import urllib3
    urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
    import requests as _req
    _REQUESTS_OK = True
except ImportError:
    _req = None
    _REQUESTS_OK = False
    logging.getLogger(__name__).warning(
        "requests 套件未安裝，Z3A API 功能暫時停用。"
        "請執行 docker-compose build 安裝後重啟。"
    )

from django.conf import settings
from django.http import JsonResponse
from django.views import View
from django.views.decorators.csrf import csrf_exempt
from django.utils.decorators import method_decorator

logger = logging.getLogger(__name__)

# ── 從 Django settings 讀取設定 ──────────────────────────────────────────────
_BASE  = getattr(settings, 'Z3A_BASE_URL',  'https://server.qiyunwulian.com:12341')
_PHONE = getattr(settings, 'Z3A_PHONE',     '')
_PASS  = getattr(settings, 'Z3A_PASSWORD',  '')

# Token 快取（記憶體，重啟 Django 後重置）
_token     = getattr(settings, 'Z3A_TOKEN', '')
_token_exp = 0          # Unix timestamp
_token_lock = threading.Lock()


# ── JWT 工具 ─────────────────────────────────────────────────────────────────
def _jwt_exp(token: str) -> int:
    """從 JWT payload 解析 exp（不驗證簽名）"""
    try:
        part = token.split('.')[1]
        part += '=' * (-len(part) % 4)
        return int(json.loads(base64.b64decode(part)).get('exp', 0))
    except Exception:
        return 0


def _token_valid(tok: str) -> bool:
    if not tok:
        return False
    exp = _jwt_exp(tok)
    return exp == 0 or time.time() < exp - 60   # exp==0 → 永不過期


# ── Token 取得（自動重新登入）────────────────────────────────────────────────
def _get_token() -> str:
    global _token, _token_exp
    if _token_valid(_token):
        return _token
    with _token_lock:
        if _token_valid(_token):
            return _token
        if not (_PHONE and _PASS):
            return _token   # 無法重新登入，回傳現有 token（可能已過期）
        try:
            logger.info("Z3A: 嘗試自動重新登入 (%s)", _PHONE)
            r = _req.post(
                f"{_BASE}/login",
                json={"PhoneNumber": _PHONE, "Password": _PASS},
                verify=False, timeout=10,
            )
            data = r.json()
            # 嘗試常見 token 欄位名稱
            new_tok = (
                data.get('token')
                or data.get('Token')
                or (data.get('data') or {}).get('token')
                or (data.get('data') or {}).get('Token')
                or ''
            )
            if new_tok:
                _token = new_tok
                _token_exp = _jwt_exp(new_tok)
                logger.info("Z3A: Token 更新成功，exp=%s", _token_exp)
            else:
                logger.warning("Z3A: 登入回應無 token 欄位: %s", data)
        except Exception as exc:
            logger.warning("Z3A: 自動登入失敗: %s", exc)
    return _token


def _headers() -> dict:
    return {"auth": f"Bearer {_get_token()}"}


def _err(msg, status=500):
    return JsonResponse({"error": msg}, status=status)


# ── Views ────────────────────────────────────────────────────────────────────
def _no_requests():
    return JsonResponse(
        {"error": "requests 套件未安裝，請執行 docker-compose build 後重啟容器"},
        status=503
    )


class Z3ADevicesView(View):
    """GET /api/z3a/devices/ — 列出所有綁定裝置"""
    def get(self, request):
        if not _REQUESTS_OK:
            return _no_requests()
        try:
            r = _req.get(f"{_BASE}/bind/query",
                         headers=_headers(), verify=False, timeout=15)
            if r.status_code == 401:
                return _err("Token 已過期，請至後台更新 Z3A_TOKEN 環境變數", 401)
            raw = r.json()
            # Z3A 雲端有時把 data 欄位雙重編碼成 JSON 字串，需要手動 parse
            data = raw.get('data', raw) if isinstance(raw, dict) else raw
            if isinstance(data, str):
                data = json.loads(data)
            if not isinstance(data, list):
                data = []
            return JsonResponse(data, safe=False)
        except Exception as exc:
            return _err(f"無法連接 Z3A 伺服器：{exc}")


class Z3AHistoryView(View):
    """
    GET /api/z3a/history/
      ?device_id=Z3A0412115
      &device_type=<裝置類型，來自 /bind/query>
      &measured_fun=1          (1=電壓, 2=電流mA, 3=功率/電流 視裝置而定)
      &start=YYYY-MM-DD
      &end=YYYY-MM-DD
      [&accuracy=10m]          預設 10m

    回應：
      {
        "device_id": "...",
        "measured_fun": 1,
        "series": [{"time": "...", "value": 33.5}, ...]
      }
    """
    def get(self, request):
        if not _REQUESTS_OK:
            return _no_requests()
        device_id   = request.GET.get('device_id', '').strip()
        device_type = request.GET.get('device_type', '').strip()
        fun         = request.GET.get('measured_fun', '1')
        start       = request.GET.get('start', '')
        end         = request.GET.get('end', '')
        accuracy    = request.GET.get('accuracy', '10m')

        if not device_id:
            return _err("device_id 必填", 400)
        if not start or not end:
            return _err("start / end 必填（格式 YYYY-MM-DD）", 400)

        params = {
            "DeviceId":    device_id,
            "DeviceType":  device_type,
            "measured_fun": int(fun),
            "start_time":  f"{start} 00:00:00",
            "end_time":    f"{end} 23:59:59",
            "accuracy":    accuracy,
        }
        try:
            r = _req.get(f"{_BASE}/history/period",
                         headers=_headers(), params=params,
                         verify=False, timeout=20)
            if r.status_code == 401:
                return _err("Token 已過期", 401)
            raw = r.json()

            # 扁平化 InfluxDB Series 格式 → [{time, value}, ...]
            series = []
            for item in (raw.get('data') or []):
                for s in (item.get('Series') or []):
                    cols = s.get('columns', [])
                    for row in (s.get('values') or []):
                        entry = dict(zip(cols, row))
                        # 統一欄位名稱：time + value
                        t = entry.get('time', '')
                        # 數值欄位：通常是 mean 或 cols[1]
                        val = None
                        for k in cols:
                            if k != 'time':
                                val = entry.get(k)
                                break
                        series.append({"time": t, "value": val})

            return JsonResponse({
                "device_id":    device_id,
                "measured_fun": int(fun),
                "start":        start,
                "end":          end,
                "count":        len(series),
                "series":       series,
            })
        except Exception as exc:
            return _err(f"查詢歷史數據失敗：{exc}")


class Z3AStatusView(View):
    """GET /api/z3a/status/ — 診斷 Token 與連線狀態"""
    def get(self, request):
        if not _REQUESTS_OK:
            return JsonResponse({
                "token_set": False, "token_valid": False,
                "token_expires": "N/A",
                "phone_configured": False, "password_configured": False,
                "base_url": _BASE,
                "error": "requests 套件未安裝，請執行 docker-compose build"
            })
        from datetime import datetime, timezone
        tok = _get_token()
        exp = _jwt_exp(tok) if tok else 0
        exp_str = (datetime.fromtimestamp(exp, tz=timezone.utc)
                   .strftime('%Y-%m-%d %H:%M UTC')) if exp else 'N/A'
        valid = _token_valid(tok)
        return JsonResponse({
            "token_set":         bool(tok),
            "token_valid":       valid,
            "token_expires":     exp_str,
            "phone_configured":  bool(_PHONE),
            "password_configured": bool(_PASS),
            "base_url":          _BASE,
        })


@method_decorator(csrf_exempt, name='dispatch')
class Z3ARefreshView(View):
    """POST /api/z3a/refresh/ — 手動強制重新取得 Token"""
    def post(self, request):
        if not _REQUESTS_OK:
            return _no_requests()
        global _token, _token_exp
        _token = ''          # 清除，讓 _get_token() 重新登入
        _token_exp = 0
        new_tok = _get_token()
        if new_tok:
            from datetime import datetime, timezone
            exp = _jwt_exp(new_tok)
            exp_str = (datetime.fromtimestamp(exp, tz=timezone.utc)
                       .strftime('%Y-%m-%d %H:%M UTC')) if exp else 'N/A'
            return JsonResponse({
                "success": True,
                "token_valid": _token_valid(new_tok),
                "expires": exp_str,
            })
        return JsonResponse({"success": False, "error": "無法取得 Token，請確認 Z3A_PHONE / Z3A_PASSWORD 設定"}, status=401)
