import requests
import json
from datetime import datetime

def test_api_status():
    """測試API狀態"""
    print("🔍 測試API狀態...")
    try:
        response = requests.get("http://localhost:8000/api/realtime-data/status/")
        print(f"狀態碼: {response.status_code}")
        print(f"回應: {response.json()}")
        return response.status_code == 200
    except Exception as e:
        print(f"❌ API狀態測試失敗: {e}")
        return False

def test_send_data():
    """測試發送實時數據"""
    print("\n📤 測試發送實時數據...")
    
    # 測試數據
    test_data = {
        "system_id": 1,  # 確保這個系統ID存在
        "voltage": 18.5,
        "current": 2.3,
        "power_output": 42.55,
        "temperature": 28.5,
        "humidity": 65.0,
        "panel_azimuth": 180.0,
        "panel_tilt": 20.0,
        "device_id": "test_device",
        "notes": "API測試數據"
    }
    
    try:
        response = requests.post(
            "http://localhost:8000/api/realtime-data/",
            json=test_data,
            headers={'Content-Type': 'application/json'}
        )
        
        print(f"狀態碼: {response.status_code}")
        print(f"回應: {response.json()}")
        
        if response.status_code == 201:
            print("✅ 數據發送成功！")
            return True
        else:
            print("❌ 數據發送失敗")
            return False
            
    except Exception as e:
        print(f"❌ 數據發送錯誤: {e}")
        return False

def test_get_latest():
    """測試獲取最新記錄"""
    print("\n📊 測試獲取最新記錄...")
    try:
        response = requests.get("http://localhost:8000/api/power-records/latest/")
        print(f"狀態碼: {response.status_code}")
        if response.status_code == 200:
            data = response.json()
            print(f"最新記錄: {data['timestamp']} - {data['power_output']}W")
            return True
        else:
            print(f"回應: {response.json()}")
            return False
    except Exception as e:
        print(f"❌ 獲取記錄錯誤: {e}")
        return False

def main():
    """主測試函數"""
    print("🚀 開始API測試...")
    
    # 測試1: API狀態
    if not test_api_status():
        print("❌ API狀態測試失敗，停止測試")
        return
    
    # 測試2: 發送數據
    if not test_send_data():
        print("❌ 數據發送測試失敗")
        return
    
    # 測試3: 獲取最新記錄
    if not test_get_latest():
        print("❌ 獲取記錄測試失敗")
        return
    
    print("\n🎉 所有API測試通過！")

if __name__ == "__main__":
    main()