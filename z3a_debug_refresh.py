#!/usr/bin/env python3
"""
z3a_debug_refresh.py — 探測 Z3A refresh 端點（每次嘗試都印進度，不會看起來當機）
"""
import json, base64, urllib3, sys
from pathlib import Path
import requests

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

def load_env(p):
    env = {}
    if not p.exists(): return env
    for line in p.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line: continue
        k, _, v = line.partition("=")
        env[k.strip()] = v.strip().strip('"').strip("'")
    return env

env = load_env(Path(__file__).parent / ".env.dev")
BASE   = env.get("Z3A_BASE_URL", "https://server.qiyunwulian.com:12341")
TOKEN  = env.get("Z3A_TOKEN", "")
TOKEN2 = env.get("Z3A_REFRESH_TOKEN", "")

if not TOKEN2:
    print("✗ .env.dev 缺 Z3A_REFRESH_TOKEN"); sys.exit(1)

print(f"=== Z3A refresh 端點探測 ===")
print(f"BASE   = {BASE}")
print(f"TOKEN  (前20) = {TOKEN[:20]}...")
print(f"TOKEN2 (前20) = {TOKEN2[:20]}...")
print(f"timeout=4 秒/次，總共 ~36 個請求，最壞 2.5 分鐘\n")

# 縮減嘗試數量，每次都印進度
attempts = [
    # (label, method, path, headers, body_dict, body_mode)
    ("POST /user/refreshToken  + Bearer T2 in auth header (no body)",
        "POST", "/user/refreshToken", {"auth": f"Bearer {TOKEN2}"}, None, None),
    ("POST /user/refreshToken  + Bearer T1 in auth, refresh in form",
        "POST", "/user/refreshToken",
        {"auth": f"Bearer {TOKEN}", "Content-Type": "application/x-www-form-urlencoded"},
        {"refreshToken": TOKEN2}, "form"),
    ("POST /user/refreshToken  + form: tokenString2",
        "POST", "/user/refreshToken",
        {"auth": f"Bearer {TOKEN}", "Content-Type": "application/x-www-form-urlencoded"},
        {"tokenString2": TOKEN2}, "form"),
    ("POST /user/refreshToken  + form: PhoneNumber + refresh",
        "POST", "/user/refreshToken",
        {"Content-Type": "application/x-www-form-urlencoded"},
        {"PhoneNumber": "13584809353", "refreshToken": TOKEN2}, "form"),
    ("GET  /user/refreshToken  + Bearer T2 only",
        "GET",  "/user/refreshToken", {"auth": f"Bearer {TOKEN2}"}, None, None),
    ("GET  /user/refreshToken  + Bearer T1 in header",
        "GET",  "/user/refreshToken", {"auth": f"Bearer {TOKEN}"}, None, None),
    ("POST /user/refresh       + Bearer T2",
        "POST", "/user/refresh", {"auth": f"Bearer {TOKEN2}"}, None, None),
    ("POST /user/refresh       + form refreshToken",
        "POST", "/user/refresh",
        {"Content-Type": "application/x-www-form-urlencoded"},
        {"refreshToken": TOKEN2}, "form"),
    ("POST /token/refresh      + Bearer T2",
        "POST", "/token/refresh", {"auth": f"Bearer {TOKEN2}"}, None, None),
    ("POST /user/renewToken    + Bearer T2",
        "POST", "/user/renewToken", {"auth": f"Bearer {TOKEN2}"}, None, None),
    ("POST /auth/refresh       + form refresh_token",
        "POST", "/auth/refresh",
        {"Content-Type": "application/x-www-form-urlencoded"},
        {"refresh_token": TOKEN2}, "form"),
    ("POST /user/login         + Authorization header T2 (試 login 端點認 T2)",
        "POST", "/user/login",
        {"Authorization": f"Bearer {TOKEN2}", "Content-Type": "application/x-www-form-urlencoded"},
        {"PhoneNumber": "13584809353"}, "form"),
]

hits = []
N = len(attempts)
for i, (label, method, path, headers, body, mode) in enumerate(attempts, 1):
    url = f"{BASE}{path}"
    sys.stdout.write(f"[{i:2}/{N}] {label[:60]:60s} ... ")
    sys.stdout.flush()
    try:
        kwargs = {"headers": headers, "verify": False, "timeout": 4}
        if body is not None:
            if mode == "form":
                kwargs["data"] = body
            else:
                kwargs["json"] = body
        if method == "GET":
            r = requests.get(url, **kwargs)
        else:
            r = requests.post(url, **kwargs)
        text = (r.text or "")[:150]
        try:
            j = r.json()
            code = j.get("code")
        except:
            code = None
        # 判斷：找 token 字串 = ✓✓✓
        if "tokenString" in r.text or ("eyJhbGc" in r.text and r.text.count("eyJ") >= 1):
            print(f"✓✓✓ HIT")
            print(f"           body: {text[:400]}")
            hits.append((label, r.text))
        else:
            print(f"code={code} text={text[:80]}")
    except requests.exceptions.Timeout:
        print("⏱ timeout")
    except Exception as e:
        print(f"✗ {type(e).__name__}")

print()
print("─" * 60)
if hits:
    print(f"✓ 找到 {len(hits)} 個可用端點：")
    for label, text in hits:
        print(f"\n>>> {label}\n{text[:500]}")
else:
    print("✗ 全部測試完，沒有可 refresh 的端點")
    print()
    print("下一步建議：")
    print("  1. 維持手動更新 token 模式（每 10 天從 Fiddler 抓一次）")
    print("  2. 或再抓一次 Fiddler — 但這次「等」")
    print("     - 登入後 App 維持開著 4-8 小時")
    print("     - App 內部會自動 refresh token，那筆請求會被攔到")
    print("     - 通常會是 /user/refreshXXX 或 /token/XXX 之類")
