#!/usr/bin/env python3
"""
z3a_debug_login2.py — 鎖定 /user/login，試各種欄位名 + GET hint
"""
import os, sys, json, base64, hashlib, urllib3
from pathlib import Path
import requests

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

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

print(f"=== Z3A /user/login 欄位偵測 ===")
print(f"BASE  = {BASE}")
print(f"PHONE = {PHONE}")
print(f"PASS  = ({len(PASS)} 字元，前 2 後 2 = {PASS[:2]}***{PASS[-2:]})\n")

URL = f"{BASE}/user/login"
PASS_MD5 = hashlib.md5(PASS.encode()).hexdigest()

# 試很多欄位名組合 + 不同 password 形式
candidates = []
phone_keys = ["phone", "Phone", "phoneNumber", "PhoneNumber", "mobile", "account",
              "username", "userName", "user", "loginName", "tel", "phoneNum"]
password_keys = ["password", "Password", "pwd", "Pwd", "passwd", "userPwd"]
password_values = [
    ("明文", PASS),
    ("md5 小寫", PASS_MD5),
    ("md5 大寫", PASS_MD5.upper()),
]

# A) 先試簡單 phone/password 組合（明文）
for pk in phone_keys:
    for pwk in password_keys:
        candidates.append((f"{pk}+{pwk} (明文)", {pk: PHONE, pwk: PASS}))

# B) phone + 加密 password
for pwk in ["password", "Password", "pwd"]:
    for label, val in [("md5低", PASS_MD5), ("md5高", PASS_MD5.upper())]:
        candidates.append((f"phone+{pwk} ({label})", {"phone": PHONE, pwk: val}))
        candidates.append((f"Phone+{pwk} ({label})", {"Phone": PHONE, pwk: val}))

# 去重
seen = set(); uniq = []
for label, body in candidates:
    key = tuple(sorted(body.items()))
    if key not in seen:
        seen.add(key); uniq.append((label, body))

# 先 GET 看看
print(f"── GET {URL}（探 hint）──")
try:
    r = requests.get(URL, verify=False, timeout=10)
    print(f"  status: {r.status_code}\n  body: {r.text[:400]}\n")
except Exception as e:
    print(f"  ✗ {e}\n")

# 開始試 POST
hits = []
for i, (label, body) in enumerate(uniq, 1):
    try:
        r = requests.post(URL, json=body, verify=False, timeout=8)
        text = r.text[:200] if r.text else "(empty)"
        # 試 parse 看 code
        code = None
        try:
            j = r.json()
            code = j.get("code")
        except: pass

        # 判定有趣的回應（不是 5000 Missing parameter 也不是 4xx 找不到）
        is_interesting = code not in (5000, 404) if code is not None else False

        marker = "✓" if is_interesting else "·"
        print(f"  [{i:2}/{len(uniq)}] {marker} {label:35s} code={code}  body={text[:120]}")

        if is_interesting:
            hits.append((label, body, r.text))
            # 完整 body
            print(f"           full body: {r.text[:600]}")
    except Exception as e:
        print(f"  [{i:2}/{len(uniq)}] ✗ {label}: {e}")

print("\n─────────────────────────────────")
if hits:
    print(f"✓ 有趣的回應：{len(hits)} 個")
    for label, body, text in hits:
        print(f"\n>>> {label}")
        print(f"    body sent: {body}")
        print(f"    response : {text[:400]}")
else:
    print("✗ 全部是 Missing parameter 或 404，可能需要更多必填欄位")
    print("   建議：(1) 用 Fiddler 攔截 Z3A App 的登入流量，看真實的 request body")
    print("        (2) 也可能需要 verifyCode / captcha / clientType / appVersion 等額外欄位")
