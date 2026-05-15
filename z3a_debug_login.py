#!/usr/bin/env python3
"""
z3a_debug_login.py — 測試 Z3A 雲端登入的各種可能格式
從 .env.dev 讀帳密，依序試多種登入格式，找出能成功的那個。
"""
import os, sys, json, base64, hashlib, urllib3
from pathlib import Path
import requests

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# 讀 .env.dev
def load_env(path):
    env = {}
    if not path.exists(): return env
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line: continue
        k, _, v = line.partition("=")
        env[k.strip()] = v.strip().strip('"').strip("'")
    return env

env = load_env(Path(__file__).parent / ".env.dev")
BASE  = env.get("Z3A_BASE_URL", "https://server.qiyunwulian.com:12341")
PHONE = env.get("Z3A_PHONE", "")
PASS  = env.get("Z3A_PASSWORD", "")

if not (PHONE and PASS):
    print("✗ .env.dev 缺 Z3A_PHONE 或 Z3A_PASSWORD"); sys.exit(1)

print(f"=== Z3A 登入 debug ===")
print(f"BASE  = {BASE}")
print(f"PHONE = {PHONE}")
print(f"PASS  = ({len(PASS)} 字元，前 2 後 2 = {PASS[:2]}***{PASS[-2:]})")
print(f"Pass MD5  = {hashlib.md5(PASS.encode()).hexdigest()}")
print(f"Pass SHA256= {hashlib.sha256(PASS.encode()).hexdigest()[:16]}...")
print()

# 多種登入格式
candidates = [
    # (label, path, body, content-type)
    ("A. JSON  /login        明文 PhoneNumber/Password", "/login",
        {"PhoneNumber": PHONE, "Password": PASS}, "json"),
    ("B. JSON  /login        明文 phoneNumber/password (小寫)", "/login",
        {"phoneNumber": PHONE, "password": PASS}, "json"),
    ("C. JSON  /login        明文 phone/password", "/login",
        {"phone": PHONE, "password": PASS}, "json"),
    ("D. JSON  /login        MD5 大寫", "/login",
        {"PhoneNumber": PHONE, "Password": hashlib.md5(PASS.encode()).hexdigest().upper()}, "json"),
    ("E. JSON  /login        MD5 小寫", "/login",
        {"PhoneNumber": PHONE, "Password": hashlib.md5(PASS.encode()).hexdigest()}, "json"),
    ("F. JSON  /user/login   明文", "/user/login",
        {"PhoneNumber": PHONE, "Password": PASS}, "json"),
    ("G. JSON  /auth/login   明文", "/auth/login",
        {"PhoneNumber": PHONE, "Password": PASS}, "json"),
    ("H. FORM  /login        明文", "/login",
        {"PhoneNumber": PHONE, "Password": PASS}, "form"),
    ("I. JSON  /login        明文 + UserAgent", "/login",
        {"PhoneNumber": PHONE, "Password": PASS}, "json_ua"),
]

for label, path, body, mode in candidates:
    print(f"───── {label} ─────")
    url = f"{BASE}{path}"
    try:
        if mode == "form":
            r = requests.post(url, data=body, verify=False, timeout=10)
        elif mode == "json_ua":
            headers = {"User-Agent": "okhttp/4.9.0", "Content-Type": "application/json"}
            r = requests.post(url, json=body, headers=headers, verify=False, timeout=10)
        else:
            r = requests.post(url, json=body, verify=False, timeout=10)

        print(f"  status: {r.status_code}")
        # 截短 response 印出
        text = r.text[:500] if r.text else "(empty)"
        print(f"  body  : {text}")

        # 嘗試 parse 找 token
        try:
            j = r.json()
            tok = (j.get("token") or j.get("Token") or
                   (j.get("data") or {}).get("token") or
                   (j.get("data") or {}).get("Token") or "")
            if tok:
                print(f"  ✓✓✓ 成功！TOKEN = {tok[:50]}...{tok[-20:]}")
                # 解 JWT exp
                if tok.count(".") == 2:
                    try:
                        part = tok.split(".")[1]
                        part += "=" * (-len(part) % 4)
                        payload = json.loads(base64.b64decode(part))
                        print(f"  JWT payload: {payload}")
                    except: pass
                print(f"\n>>> 找到可用格式：{label}")
                sys.exit(0)
        except Exception as e:
            print(f"  (無法解析 JSON: {e})")
    except Exception as e:
        print(f"  ✗ 例外：{e}")
    print()

print("─────────────────────────────────")
print("✗ 所有格式都失敗")
print("建議：1) 用 Fiddler 攔截 Z3A App 的登入請求，看實際格式")
print("      2) 確認密碼正確（在 Z3A App 上能登入嗎？）")
print("      3) Z3A 雲端可能要求 captcha 或裝置綁定驗證")
