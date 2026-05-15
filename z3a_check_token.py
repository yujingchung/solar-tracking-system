#!/usr/bin/env python3
"""
z3a_check_token.py — 隨時查看 Z3A token 狀態
使用：python z3a_check_token.py
"""
import base64, json, time
from pathlib import Path
from datetime import datetime

def load_env(p):
    env = {}
    if not p.exists(): return env
    for line in p.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line: continue
        k, _, v = line.partition("=")
        env[k.strip()] = v.strip().strip('"').strip("'")
    return env

def jwt_exp(token):
    try:
        part = token.split(".")[1]
        part += "=" * (-len(part) % 4)
        return int(json.loads(base64.b64decode(part)).get("exp", 0))
    except: return 0

env = load_env(Path(__file__).parent / ".env.dev")
now = time.time()

print("══════════════════════════════════════════════════════")
print("  Z3A Token 狀態檢查")
print("══════════════════════════════════════════════════════")

for label, key in [("Access Token (Z3A_TOKEN)", "Z3A_TOKEN"),
                   ("Refresh Token (Z3A_REFRESH_TOKEN)", "Z3A_REFRESH_TOKEN")]:
    tok = env.get(key, "")
    print(f"\n{label}:")
    if not tok:
        print(f"  ✗ 未設定")
        continue
    exp = jwt_exp(tok)
    if not exp:
        print(f"  ⚠ 無法解析 JWT")
        continue
    dt = datetime.fromtimestamp(exp)
    days = (exp - now) / 86400
    print(f"  到期時間：{dt.strftime('%Y-%m-%d %H:%M:%S')}")
    if days < 0:
        print(f"  狀態：✗ 已過期 {-days:.1f} 天前")
    elif days < 1:
        print(f"  狀態：⚠ 緊急 — 剩 {days*24:.1f} 小時")
    elif days < 3:
        print(f"  狀態：⚠ 即將過期 — 剩 {days:.1f} 天")
    elif days < 7:
        print(f"  狀態：⚠ 注意 — 剩 {days:.1f} 天，建議本週更新")
    else:
        print(f"  狀態：✓ 有效 — 剩 {days:.1f} 天")

print()
print("══════════════════════════════════════════════════════")
print("如果 Access Token 剩 < 3 天，請依下列步驟更新：")
print("  1. 開 Fiddler（HTTPS 解密設定要打開）")
print("  2. 啟雲物聯桌面 App 完全登出後重新登入")
print("  3. Fiddler 找 POST /user/login 那筆，看 Response Body")
print("  4. 把 data.tokenString  → 貼到 .env.dev 的 Z3A_TOKEN=")
print("     data.tokenString2 → 貼到 .env.dev 的 Z3A_REFRESH_TOKEN=")
print("  5. 跑 docker-compose -f docker-compose-dev.yml restart solar_backend")
print("     讓 backend 載入新 token")
