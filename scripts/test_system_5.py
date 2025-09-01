import requests
import json

def test_system_5():
    """測試系統ID 5的數據上傳"""
    
    # 測試數據
    test_data = {
        "system_id": 5,
        "voltage": 18.5,
        "current": 2.3,
        "power_output": 42.55,
        "temperature": 28.5,
        "humidity": 65.0,
        "device_id": "test_system_5",
        "notes": "測試系統ID 5"
    }
    
    print("=== 測試系統ID 5 ===")
    print(f"測試數據: {test_data}")
    
    try:
        response = requests.post(
            "http://localhost:8000/api/realtime-data/",
            json=test_data,
            headers={'Content-Type': 'application/json'}
        )
        
        print(f"狀態碼: {response.status_code}")
        print(f"回應內容: {response.text}")
        
        if response.status_code == 201:
            print("✅ 系統ID 5 測試成功！")
            return True
        else:
            print("❌ 系統ID 5 測試失敗")
            return False
            
    except Exception as e:
        print(f"測試錯誤: {e}")
        return False

def check_systems():
    """檢查所有可用系統"""
    try:
        response = requests.get("http://localhost:8000/api/systems/")
        if response.status_code == 200:
            systems = response.json()
            print("\n=== 系統列表 ===")
            for system in systems:
                print(f"ID: {system['id']}, 名稱: {system['name']}")
            return systems
        else:
            print("無法獲取系統列表")
            return None
    except Exception as e:
        print(f"檢查系統錯誤: {e}")
        return None

if __name__ == "__main__":
    systems = check_systems()
    if systems:
        test_system_5()