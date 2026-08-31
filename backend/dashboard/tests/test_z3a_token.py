"""Z3A JWT token 解析與有效性判斷測試（不需資料庫）。

驗證「為什麼」：z3a_collect 與 dashboard 依賴 _token_valid 判斷 token 是否該換。
若 exp 解析或過期判斷改壞，會在「token 還有效時亂重登」或「過期了還硬用」
之間出錯，造成 IoT 雲端 401 或被鎖。
"""
import base64
import json
import time

from django.test import SimpleTestCase

from dashboard.z3a_api import _jwt_exp, _token_valid


def _make_jwt(payload: dict) -> str:
    def b64(d):
        raw = json.dumps(d).encode()
        return base64.urlsafe_b64encode(raw).rstrip(b"=").decode()
    header = b64({"alg": "HS256", "typ": "JWT"})
    body = b64(payload)
    return f"{header}.{body}.fakesignature"


class JwtExpTests(SimpleTestCase):
    def test_parses_exp(self):
        tok = _make_jwt({"exp": 1778646040, "iss": "www.iot7.cn"})
        self.assertEqual(_jwt_exp(tok), 1778646040)

    def test_missing_exp_returns_zero(self):
        tok = _make_jwt({"iss": "www.iot7.cn"})
        self.assertEqual(_jwt_exp(tok), 0)

    def test_malformed_token_returns_zero(self):
        self.assertEqual(_jwt_exp("not-a-jwt"), 0)
        self.assertEqual(_jwt_exp(""), 0)


class TokenValidTests(SimpleTestCase):
    def test_empty_token_invalid(self):
        self.assertFalse(_token_valid(""))

    def test_future_exp_valid(self):
        tok = _make_jwt({"exp": int(time.time()) + 3600})
        self.assertTrue(_token_valid(tok))

    def test_past_exp_invalid(self):
        tok = _make_jwt({"exp": int(time.time()) - 3600})
        self.assertFalse(_token_valid(tok))

    def test_within_60s_buffer_invalid(self):
        """距到期不足 60 秒應視為無效（提早換 token，留安全餘裕）。"""
        tok = _make_jwt({"exp": int(time.time()) + 30})
        self.assertFalse(_token_valid(tok))

    def test_exp_zero_treated_as_never_expire(self):
        tok = _make_jwt({"exp": 0})
        self.assertTrue(_token_valid(tok))
