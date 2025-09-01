#!/usr/bin/env python3
"""
樹莓派實時數據採集與上傳程式
支援電壓電流計數據讀取並上傳至Django網站
"""

import time
import json
import requests
from datetime import datetime
import logging
import random  # 用於模擬數據

# 日誌設定
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

class SolarDataCollector:
    def __init__(self, config_file='config.json'):
        """初始化數據採集器"""
        self.load_config(config_file)
        
    def load_config(self, config_file):
        """載入配置檔案"""
        try:
            with open(config_file, 'r', encoding='utf-8') as f:
                config = json.load(f)
            
            # API設定
            self.api_url = config.get('api_url', 'http://localhost:8000/api')
            self.system_id = config.get('system_id', 5)
            self.device_id = config.get('device_id', 'raspberry_pi_001')
            
            # 採集設定
            self.collection_interval = config.get('collection_interval', 30)  # 30秒
            
            # 模擬模式設定
            self.simulation_mode = config.get('simulation_mode', True)
            
            logger.info("配置載入成功")
            
        except FileNotFoundError:
            logger.warning("配置檔案不存在，使用預設設定並建立配置檔案")
            self.create_default_config(config_file)
    
    def create_default_config(self, config_file):
        """創建預設配置檔案"""
        default_config = {
            "api_url": "http://localhost:8000/api",
            "system_id": 5,  # 預設使用模擬測試系統
            "device_id": "simulation_test_device",
            "collection_interval": 30,
            "simulation_mode": True,
            "system_info": {
                "5": "模擬測試系統", 
                "6": "山上對照組",
                "7": "山上實驗組",
                "8": "頂樓對照組", 
                "9": "頂樓實驗組"
            },
            "note": "修改 system_id 來選擇不同的系統組別"
        }
        
        with open(config_file, 'w', encoding='utf-8') as f:
            json.dump(default_config, f, indent=4, ensure_ascii=False)
        
        # 載入預設值
        for key, value in default_config.items():
            if key not in ['system_info', 'note']:
                setattr(self, key, value)
    
    def read_sensors(self):
        """讀取感測器數據"""
        try:
            if self.simulation_mode:
                # 模擬真實的太陽能板數據
                hour = datetime.now().hour
                
                # 根據時間模擬不同的發電狀況
                if 6 <= hour <= 18:  # 白天
                    # 模擬太陽能板在不同時間的發電情況
                    time_factor = 1.0
                    if hour < 8 or hour > 16:  # 早晚
                        time_factor = 0.3
                    elif 10 <= hour <= 14:  # 中午
                        time_factor = 1.0
                    else:  # 上午下午
                        time_factor = 0.7
                    
                    base_voltage = 20.0 * time_factor
                    base_current = 3.0 * time_factor
                    
                    # 加入一些隨機變動（模擬雲層等影響）
                    voltage = base_voltage + random.uniform(-2, 2)
                    current = base_current + random.uniform(-0.5, 0.5)
                    
                    # 環境數據
                    temperature = random.uniform(25, 35)
                    humidity = random.uniform(50, 80)
                    
                else:  # 夜晚
                    voltage = random.uniform(0, 0.5)
                    current = random.uniform(0, 0.1)
                    temperature = random.uniform(18, 25)
                    humidity = random.uniform(60, 90)
                
                # 確保數值為正
                voltage = max(0, voltage)
                current = max(0, current)
                power = voltage * current
                
                return {
                    'voltage': round(voltage, 2),
                    'current': round(current, 3),
                    'power_output': round(power, 2),
                    'temperature': round(temperature, 1),
                    'humidity': round(humidity, 1),
                    'light_intensity': round(power * 50, 1) if power > 0 else 0,  # 模擬光照強度
                    'panel_azimuth': 180.0,  # 假設固定朝南
                    'panel_tilt': 20.0,      # 假設固定傾角
                    'timestamp': datetime.now().isoformat(),
                    'device_id': self.device_id,
                    'sensor_status': 'normal'
                }
            else:
                # 這裡之後會替換為真實感測器代碼
                logger.warning("真實感測器模式尚未實現，使用模擬數據")
                return self.read_sensors()  # 遞迴調用模擬模式
            
        except Exception as e:
            logger.error(f"感測器讀取錯誤: {e}")
            return None
    
    def upload_data(self, data):
        """上傳數據到Django API"""
        try:
            # 準備API數據
            api_data = {
                'system_id': self.system_id,
                'voltage': data['voltage'],
                'current': data['current'],
                'power_output': data['power_output'],
                'temperature': data.get('temperature'),
                'humidity': data.get('humidity'),
                'light_intensity': data.get('light_intensity'),
                'panel_azimuth': data.get('panel_azimuth'),
                'panel_tilt': data.get('panel_tilt'),
                'notes': f"設備: {data['device_id']}, 狀態: {data['sensor_status']}"
            }
            
            # 發送到 RealTimeData API
            response = requests.post(
                f"{self.api_url}/realtime-data/",
                json=api_data,
                headers={'Content-Type': 'application/json'},
                timeout=10
            )
            
            if response.status_code == 201:
                response_data = response.json()
                logger.info(f"✅ 數據上傳成功: {data['power_output']}W (記錄ID: {response_data.get('record_id')})")
                return True
            else:
                logger.error(f"❌ API錯誤 {response.status_code}: {response.text}")
                return False
                
        except requests.exceptions.RequestException as e:
            logger.error(f"❌ 網路錯誤: {e}")
            return False
        except Exception as e:
            logger.error(f"❌ 上傳錯誤: {e}")
            return False
    
    def save_local_backup(self, data):
        """本地備份數據（網路故障時使用）"""
        try:
            backup_file = f"backup_data_{datetime.now().strftime('%Y%m%d')}.json"
            
            # 讀取現有備份
            try:
                with open(backup_file, 'r', encoding='utf-8') as f:
                    backup_data = json.load(f)
            except FileNotFoundError:
                backup_data = []
            
            # 添加新數據
            backup_data.append(data)
            
            # 儲存備份
            with open(backup_file, 'w', encoding='utf-8') as f:
                json.dump(backup_data, f, indent=2, ensure_ascii=False)
            
            logger.info("數據已保存到本地備份")
            
        except Exception as e:
            logger.error(f"本地備份失敗: {e}")
    
    def test_api_connection(self):
        """測試API連接"""
        try:
            response = requests.get(
                f"{self.api_url}/realtime-data/status/",
                timeout=5
            )
            if response.status_code == 200:
                logger.info("✅ API連接測試成功")
                return True
            else:
                logger.error(f"❌ API連接測試失敗: {response.status_code}")
                return False
        except Exception as e:
            logger.error(f"❌ API連接測試錯誤: {e}")
            return False
    
    def run(self):
        """主執行循環"""
        logger.info("🚀 太陽能數據採集系統啟動中...")
        logger.info(f"採集間隔: {self.collection_interval}秒")
        logger.info(f"目標API: {self.api_url}")
        logger.info(f"當前系統: ID {self.system_id} - 模擬測試系統")
        logger.info(f"設備ID: {self.device_id}")
        logger.info(f"模擬模式: {'開啟' if self.simulation_mode else '關閉'}")
        
        # 測試API連接
        if not self.test_api_connection():
            logger.error("無法連接到API，請檢查網路和API地址")
            return
    
        logger.info("🎯 開始模擬數據採集...")
        # ... 其餘程式碼保持不變
        
        logger.info("🎯 開始數據採集...")
        
        while True:
            try:
                # 讀取感測器數據
                sensor_data = self.read_sensors()
                
                if sensor_data is None:
                    logger.warning("感測器讀取失敗，跳過本次採集")
                    time.sleep(self.collection_interval)
                    continue
                
                # 顯示讀取的數據
                logger.info(f"📊 電壓: {sensor_data['voltage']}V, "
                           f"電流: {sensor_data['current']}A, "
                           f"功率: {sensor_data['power_output']}W, "
                           f"溫度: {sensor_data.get('temperature', 'N/A')}°C")
                
                # 嘗試上傳數據
                upload_success = self.upload_data(sensor_data)
                
                # 如果上傳失敗，保存本地備份
                if not upload_success:
                    self.save_local_backup(sensor_data)
                
                # 等待下次採集
                time.sleep(self.collection_interval)
                
            except KeyboardInterrupt:
                logger.info("👋 用戶中斷，停止數據採集")
                break
            except Exception as e:
                logger.error(f"主循環錯誤: {e}")
                time.sleep(5)  # 錯誤後短暫等待

def main():
    """主程式"""
    print("🌞 太陽能數據採集系統")
    print("=" * 50)
    
    collector = SolarDataCollector()
    collector.run()

if __name__ == "__main__":
    main()