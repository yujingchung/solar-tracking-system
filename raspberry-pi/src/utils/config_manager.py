#!/usr/bin/env python3
"""
統一配置管理系統
用於管理ANFIS控制器和傳統對照組控制器的配置
作者: YuJing
版本: 1.0
"""

import json
import os
from pathlib import Path
from typing import Dict, Any, Optional
import logging
from dataclasses import dataclass, asdict
from datetime import datetime

@dataclass
class HardwareConfig:
    """硬體配置"""
    # GPIO設定
    azimuth_servo_pin: int = 18
    tilt_servo_pin: int = 19
    
    # 光感測器GPIO
    light_sensor_east: int = 2
    light_sensor_west: int = 3
    light_sensor_south: int = 4
    light_sensor_north: int = 17
    
    # 角度限制
    azimuth_min: float = 135.0
    azimuth_max: float = 225.0
    tilt_min: float = 0.0
    tilt_max: float = 45.0

@dataclass
class SystemConfig:
    """系統配置"""
    # 基本資訊
    system_name: str = "太陽能追日系統"
    system_id: int = 1
    device_id: str = "raspberry_pi_001"
    
    # 網路設定
    api_url: str = "http://localhost:8000/api"
    collection_interval: int = 60  # 秒
    
    # 運行模式
    simulation_mode: bool = False
    debug_mode: bool = True

@dataclass
class AlgorithmConfig:
    """演算法配置"""
    # ANFIS參數
    anfis_enabled: bool = True
    learning_rate: float = 0.01
    max_iterations: int = 1000
    
    # 傳統追日參數
    light_threshold: float = 50.0
    noise_level: float = 0.1
    
    # 移動判斷參數
    power_expectation_tolerance: float = 0.95
    movement_worthiness_threshold: float = 2.0
    fine_tune_improvement_threshold: float = 0.5

@dataclass
class LocationConfig:
    """地理位置配置"""
    latitude: float = 24.8138   # 新竹緯度
    longitude: float = 120.9675 # 新竹經度
    timezone: str = "Asia/Taipei"
    elevation: float = 50.0     # 海拔高度(公尺)

class ConfigManager:
    """統一配置管理器"""
    
    def __init__(self, config_dir: Optional[str] = None):
        if config_dir is None:
            # 預設配置目錄為raspberry-pi/config
            self.config_dir = Path(__file__).parent.parent / "config"
        else:
            self.config_dir = Path(config_dir)
        
        self.config_dir.mkdir(exist_ok=True)
        
        # 初始化配置
        self.hardware = HardwareConfig()
        self.system = SystemConfig()
        self.algorithm = AlgorithmConfig()
        self.location = LocationConfig()
        
        self.logger = logging.getLogger(__name__)
    
    def load_config(self, config_file: str = "system_config.json") -> bool:
        """載入配置檔案"""
        config_path = self.config_dir / config_file
        
        try:
            if config_path.exists():
                with open(config_path, 'r', encoding='utf-8') as f:
                    config_data = json.load(f)
                
                # 更新各個配置模組
                if 'hardware' in config_data:
                    self.hardware = HardwareConfig(**config_data['hardware'])
                if 'system' in config_data:
                    self.system = SystemConfig(**config_data['system'])
                if 'algorithm' in config_data:
                    self.algorithm = AlgorithmConfig(**config_data['algorithm'])
                if 'location' in config_data:
                    self.location = LocationConfig(**config_data['location'])
                
                self.logger.info(f"成功載入配置: {config_path}")
                return True
            else:
                self.logger.warning(f"配置檔案不存在，建立預設配置: {config_path}")
                self.save_config(config_file)
                return False
                
        except Exception as e:
            self.logger.error(f"載入配置失敗: {e}")
            return False
    
    def save_config(self, config_file: str = "system_config.json"):
        """儲存配置到檔案"""
        config_path = self.config_dir / config_file
        
        config_data = {
            'metadata': {
                'created_at': datetime.now().isoformat(),
                'version': '1.0',
                'description': '太陽能追日系統統一配置'
            },
            'hardware': asdict(self.hardware),
            'system': asdict(self.system),
            'algorithm': asdict(self.algorithm),
            'location': asdict(self.location)
        }
        
        try:
            with open(config_path, 'w', encoding='utf-8') as f:
                json.dump(config_data, f, indent=4, ensure_ascii=False)
            
            self.logger.info(f"配置已儲存: {config_path}")
            
        except Exception as e:
            self.logger.error(f"儲存配置失敗: {e}")
    
    def get_config_dict(self) -> Dict[str, Any]:
        """取得完整配置字典"""
        return {
            'hardware': asdict(self.hardware),
            'system': asdict(self.system),
            'algorithm': asdict(self.algorithm),
            'location': asdict(self.location)
        }
    
    def update_hardware_config(self, **kwargs):
        """更新硬體配置"""
        for key, value in kwargs.items():
            if hasattr(self.hardware, key):
                setattr(self.hardware, key, value)
                self.logger.info(f"更新硬體配置: {key} = {value}")
    
    def update_system_config(self, **kwargs):
        """更新系統配置"""
        for key, value in kwargs.items():
            if hasattr(self.system, key):
                setattr(self.system, key, value)
                self.logger.info(f"更新系統配置: {key} = {value}")
    
    def update_algorithm_config(self, **kwargs):
        """更新演算法配置"""
        for key, value in kwargs.items():
            if hasattr(self.algorithm, key):
                setattr(self.algorithm, key, value)
                self.logger.info(f"更新演算法配置: {key} = {value}")
    
    def is_simulation_mode(self) -> bool:
        """檢查是否為模擬模式"""
        return self.system.simulation_mode
    
    def is_debug_mode(self) -> bool:
        """檢查是否為除錯模式"""
        return self.system.debug_mode
    
    def get_api_url(self) -> str:
        """取得API URL"""
        return self.system.api_url
    
    def get_device_info(self) -> Dict[str, Any]:
        """取得設備資訊"""
        return {
            'system_name': self.system.system_name,
            'system_id': self.system.system_id,
            'device_id': self.system.device_id,
            'location': {
                'latitude': self.location.latitude,
                'longitude': self.location.longitude,
                'timezone': self.location.timezone
            }
        }

# 全域配置管理器實例
_config_manager = None

def get_config_manager() -> ConfigManager:
    """取得全域配置管理器實例"""
    global _config_manager
    if _config_manager is None:
        _config_manager = ConfigManager()
        _config_manager.load_config()
    return _config_manager

# 便利函數
def get_hardware_config() -> HardwareConfig:
    """取得硬體配置"""
    return get_config_manager().hardware

def get_system_config() -> SystemConfig:
    """取得系統配置"""
    return get_config_manager().system

def get_algorithm_config() -> AlgorithmConfig:
    """取得演算法配置"""
    return get_config_manager().algorithm

def get_location_config() -> LocationConfig:
    """取得位置配置"""
    return get_config_manager().location

if __name__ == "__main__":
    # 測試配置管理器
    config_manager = ConfigManager()
    
    # 載入或建立配置
    config_manager.load_config()
    
    # 顯示配置
    print("硬體配置:", config_manager.hardware)
    print("系統配置:", config_manager.system)
    print("演算法配置:", config_manager.algorithm)
    print("位置配置:", config_manager.location)
    
    # 儲存配置
    config_manager.save_config()
    
    print("\n配置管理器測試完成！")