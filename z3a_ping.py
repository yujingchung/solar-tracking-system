#!/usr/bin/env python3
"""快速確認 Z3A 雲端能不能通。"""
import requests, urllib3
urllib3.disable_warnings()
BASE = "https://server.qiyunwulian.com:12341"
# 試一個「我們知道存在」的端點：/user/login（之前回 5000 Missing parameter）
print("測試 /user/login (預期 5000 = 連線正常但缺參數)...")
try:
    r = requests.post(f"{BASE}/user/login", verify=False, timeout=6)
    print(f"  ✓ status={r.status_code}  body={r.text[:200]}")
    print("  → 結論：Z3A 雲端通的，問題是 refresh endpoint 真的不存在")
except requests.exceptions.Timeout:
    print("  ⏱ timeout → Fiddler 還在攔截，或 IP 被臨時封鎖")
    print("  → 解法：1) 確認 Fiddler 完全關閉  2) 等 15-60 分鐘 IP 解封")
except Exception as e:
    print(f"  ✗ {type(e).__name__}: {e}")
