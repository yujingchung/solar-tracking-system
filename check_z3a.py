import requests, json, urllib3
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

BASE  = "https://server.qiyunwulian.com:12341"
TOKEN = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJQaG9uZU51bWJlciI6IjEzNTg0ODA5MzUzIiwiZXhwIjoxNzc4NjQ2MDQwLCJpc3MiOiJ3d3cuaW90Ny5jbiJ9.UkjrCG_dUUcJzYkk9LYsSYqS8njW14sVWCJnMce2qSQ"
H     = {"auth": f"Bearer {TOKEN}"}

# ① 列出所有裝置
print("=== 所有綁定裝置 ===")
r = requests.get(f"{BASE}/bind/query", headers=H, verify=False)
devices = r.json()
print(json.dumps(devices, indent=2, ensure_ascii=False))

# ② 對第一台裝置試 measured_fun 1~6，看看有哪些有資料
from datetime import datetime, timedelta
end   = datetime.now()
start = end - timedelta(hours=2)

try:
    first_id = devices["data"][0]["DeviceId"]
    dtype    = devices["data"][0]["DeviceType"]
    print(f"\n=== 用裝置 {first_id} 試各 measured_fun ===")
    for fun in range(1, 7):
        try:
            p = {"DeviceId": first_id, "DeviceType": dtype,
                 "measured_fun": fun,
                 "start_time": start.strftime("%Y-%m-%d %H:%M:%S"),
                 "end_time":   end.strftime("%Y-%m-%d %H:%M:%S"),
                 "accuracy": "10m"}
            resp = requests.get(f"{BASE}/history/period", headers=H, params=p, verify=False, timeout=5)
            d = resp.json()
            has_data = bool(d.get("data") and d["data"][0].get("Series"))
            sample   = d["data"][0]["Series"][0]["values"][:1] if has_data else []
            print(f"  measured_fun={fun}: {'✓ 有資料' if has_data else '✗ 無資料'} {sample}")
        except Exception as e:
            print(f"  measured_fun={fun}: error {e}")
except Exception as e:
    print(f"裝置解析失敗: {e}")
