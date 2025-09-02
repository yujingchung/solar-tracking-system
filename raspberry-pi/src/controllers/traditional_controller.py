#!/usr/bin/env python3
"""
整合太陽能追日系統 - 理想追日 vs 噪聲感測器追日
同時產生兩條CSV數據進行比較
作者: 研究生實驗用程式
版本: 5.0 - 雙軌道整合版本
"""

import time
import datetime
import json
import csv
from typing import Dict, List, Tuple
import logging
import math
import random
import os
import numpy as np
import pvlib
import pandas as pd

# 嘗試導入硬體相關模組
try:
    import RPi.GPIO as GPIO
    from gpiozero import MCP3008
    HARDWARE_AVAILABLE = True
except ImportError:
    HARDWARE_AVAILABLE = False

class IntegratedSolarTracker:
    """整合的太陽能追日系統 - 同時運行理想追日和噪聲感測器追日"""
    
    def __init__(self, 
                 simulation_mode: bool = True,
                 light_threshold: float = 50.0,
                 latitude: float = 24.8138,     # 新竹緯度
                 longitude: float = 120.9675,   # 新竹經度
                 timezone: str = 'Asia/Taipei',
                 data_interval: int = 30,
                 simulation_speed: float = 1.0,
                 noise_level: float = 0.1,      # 感測器噪聲水平
                 log_prefix: str = None,
                 start_date: str = None):
        """
        初始化整合追日系統
        
        Args:
            simulation_mode: 是否使用模擬模式
            light_threshold: 光照差異閾值
            latitude: 緯度
            longitude: 經度
            timezone: 時區
            data_interval: 檢測間隔 (秒)
            simulation_speed: 模擬速度倍率
            noise_level: 感測器噪聲水平 (0-1)
            log_prefix: 記錄檔案前綴
        """
        print("="*60)
        print("整合太陽能追日系統 - 雙軌道比較版本")
        print("="*60)
        
        self.simulation_mode = simulation_mode
        self.light_threshold = light_threshold
        self.data_interval = data_interval
        self.simulation_speed = simulation_speed if simulation_mode else 1.0
        self.noise_level = noise_level
        
        # 地理位置和時區
        self.latitude = latitude
        self.longitude = longitude
        self.timezone = timezone
        
        # 檔案設置
        data_dir = "data"
        if not os.path.exists(data_dir):
            os.makedirs(data_dir)
            print(f"已創建資料夾: {data_dir}")
        
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        prefix = log_prefix or "integrated"
        
        # 兩個CSV檔案
        self.ideal_log_file = os.path.join(data_dir, f"{prefix}_ideal_{timestamp}.csv")
        self.sensor_log_file = os.path.join(data_dir, f"{prefix}_sensor_{timestamp}.csv")
        
        # 理想追日器狀態
        self.ideal_azimuth = 135.0
        self.ideal_tilt = 45.0
        self.ideal_energy = 0.0
        self.ideal_movement_count = 0
        self.ideal_movement_angle = 0.0
        
        # 感測器追日器狀態
        self.sensor_azimuth = 135.0
        self.sensor_tilt = 45.0
        self.sensor_energy = 0.0
        self.sensor_movement_count = 0
        self.sensor_movement_angle = 0.0
        
        # 角度限制
        self.azimuth_limits = (135, 225)   # 東到西
        self.tilt_limits = (0, 45)        # 水平到垂直
        
        # 模擬參數
        self.virtual_time_offset = 0
        self.cycle_count = 0
        self.is_running = False
        # 開始日期設定
        if start_date:
            try:
                self.start_date = datetime.datetime.strptime(start_date, "%Y-%m-%d")
            except ValueError:
                print(f"日期格式錯誤，使用今天日期")
                self.start_date = datetime.datetime.now()
        else:
            self.start_date = datetime.datetime.now()
        
        # 初始化
        self.setup_logging()
        self.setup_data_files()
        
        print(f"初始化完成")
        print(f"地理位置: 緯度={self.latitude}, 經度={self.longitude}")
        print(f"光照閾值: {self.light_threshold}")
        print(f"檢測間隔: {self.data_interval}秒")
        print(f"噪聲水平: {self.noise_level}")
        print(f"理想追日檔案: {self.ideal_log_file}")
        print(f"感測器追日檔案: {self.sensor_log_file}")
        print("-"*60)
    
    def setup_logging(self):
        """設定日誌系統"""
        log_filename = f'integrated_tracker_{datetime.date.today()}.log'
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - %(levelname)s - %(message)s',
            handlers=[
                logging.FileHandler(log_filename),
                logging.StreamHandler()
            ]
        )
        self.logger = logging.getLogger(__name__)
    
    def setup_data_files(self):
        """設定數據記錄檔案"""
        # 理想追日CSV標題
        ideal_headers = [
            'timestamp', 'date', 'time',
            'azimuth', 'tilt',
            'sun_azimuth', 'sun_elevation',
            'optimal_azimuth', 'optimal_tilt',
            'azimuth_error', 'tilt_error',
            'ghi', 'dni', 'dhi',
            'panel_irradiance', 'power_output', 'total_energy',
            'movement_count', 'total_movement_angle', 'decision',
            'tracker_type'
        ]
        
        # 感測器追日CSV標題
        sensor_headers = [
            'timestamp', 'date', 'time',
            'azimuth', 'tilt',
            'light_east', 'light_west', 'light_north', 'light_south',
            'ew_difference', 'ns_difference',
            'sun_azimuth', 'sun_elevation',
            'ghi', 'dni', 'dhi',
            'panel_irradiance', 'power_output', 'total_energy',
            'movement_count', 'total_movement_angle', 'decision',
            'noise_level', 'tracker_type'
        ]
        
        try:
            # 創建理想追日檔案
            with open(self.ideal_log_file, 'w', newline='', encoding='utf-8') as f:
                writer = csv.writer(f)
                writer.writerow(ideal_headers)
            
            # 創建感測器追日檔案
            with open(self.sensor_log_file, 'w', newline='', encoding='utf-8') as f:
                writer = csv.writer(f)
                writer.writerow(sensor_headers)
            
            self.logger.info(f"數據記錄檔案已建立")
            
        except Exception as e:
            self.logger.error(f"建立數據檔案失敗: {e}")
    def get_virtual_time(self) -> datetime.datetime:
        """獲取虛擬時間"""
        if not hasattr(self, 'cycle_count'):
            self.cycle_count = 0
        
        virtual_seconds = self.cycle_count * self.data_interval
        self.virtual_time_offset = virtual_seconds
        
        # 使用設定的開始日期，早上6點開始
        base_time = self.start_date.replace(hour=6, minute=0, second=0, microsecond=0)
        virtual_time = base_time + datetime.timedelta(seconds=virtual_seconds)
        
        return virtual_time

    def calculate_solar_data(self, current_time: datetime.datetime) -> Dict:
        """使用PVlib計算完整的太陽數據"""
        try:
            # 明確創建台灣時區的時間
            taiwan_tz = datetime.timezone(datetime.timedelta(hours=8))
            if current_time.tzinfo is None:
                taiwan_time = current_time.replace(tzinfo=taiwan_tz)
            else:
                taiwan_time = current_time.astimezone(taiwan_tz)
            
            # 創建時間索引
            times = pd.DatetimeIndex([taiwan_time])
            
            # 太陽位置計算
            solar_position = pvlib.solarposition.get_solarposition(
                times, 
                self.latitude, 
                self.longitude
            )
            
            sun_azimuth = float(solar_position['azimuth'].iloc[0])
            sun_elevation = float(solar_position['elevation'].iloc[0])
            
            print(f"PVlib計算: {taiwan_time} -> 方位角={sun_azimuth:.1f}°, 仰角={sun_elevation:.1f}°")
            
            # 簡單的輻射估算
            if sun_elevation > 0:
                base_irradiance = 1000 * max(0, math.sin(math.radians(sun_elevation)))
            else:
                base_irradiance = 0
            
            solar_data = {
                'sun_azimuth': sun_azimuth,
                'sun_elevation': sun_elevation,
                'ghi': base_irradiance,
                'dni': base_irradiance * 0.8,
                'dhi': base_irradiance * 0.2,
            }
            
            return solar_data
            
        except Exception as e:
            self.logger.warning(f"PVlib計算失敗: {e}")
            return self.calculate_simple_solar_data(current_time)

    def calculate_simple_solar_data(self, current_time: datetime.datetime) -> Dict:
        """簡化的太陽數據計算（備用）"""
        hour = current_time.hour + current_time.minute / 60.0
        
        if 6 <= hour <= 18:
            sun_elevation = 60 * math.sin(math.pi * (hour - 6) / 12)
            sun_azimuth = 90 + (hour - 6) * 15
            
            base_irradiance = 800 * math.sin(math.radians(max(0, sun_elevation)))
            
            return {
                'sun_azimuth': sun_azimuth,
                'sun_elevation': max(0, sun_elevation),
                'ghi': base_irradiance,
                'dni': base_irradiance * 0.8,
                'dhi': base_irradiance * 0.2,
            }
        else:
            return {
                'sun_azimuth': 0,
                'sun_elevation': 0,
                'ghi': 0, 'dni': 0, 'dhi': 0,
            }

    def calculate_panel_irradiance(self, solar_data: Dict, panel_azimuth: float, panel_tilt: float) -> float:
        """計算特定角度面板接收的輻射量"""
        if solar_data['sun_elevation'] <= 0:
            return 0.0
        
        # 計算入射角餘弦值
        panel_azimuth_rad = math.radians(panel_azimuth)
        panel_tilt_rad = math.radians(panel_tilt)
        sun_azimuth_rad = math.radians(solar_data['sun_azimuth'])
        sun_elevation_rad = math.radians(solar_data['sun_elevation'])
        
        cos_incidence = (
            math.sin(sun_elevation_rad) * math.cos(panel_tilt_rad) +
            math.cos(sun_elevation_rad) * math.sin(panel_tilt_rad) *
            math.cos(sun_azimuth_rad - panel_azimuth_rad)
        )
        
        cos_incidence = max(0, cos_incidence)
        
        # 計算面板接收的總輻射
        direct_irradiance = solar_data['dni'] * cos_incidence
        diffuse_irradiance = solar_data['dhi'] * (1 + math.cos(panel_tilt_rad)) / 2
        
        total_irradiance = direct_irradiance + diffuse_irradiance
        
        return max(0, total_irradiance)

    def calculate_power_output(self, panel_irradiance: float) -> float:
        """計算發電功率"""
        if panel_irradiance <= 0:
            return 0.0
        
        # 太陽能板參數
        panel_area = 2.0      # m²
        efficiency = 0.20     # 20%效率
        system_efficiency = 0.85  # 系統效率（逆變器等損失）
        
        # 功率計算 (W)
        power = panel_irradiance * panel_area * efficiency * system_efficiency
        
        return max(0, power)

    def calculate_optimal_angles(self, solar_data: Dict) -> Tuple[float, float]:
        """計算理論最佳角度"""
        if solar_data['sun_elevation'] <= 0:
            return None, None
        
        # 最佳方位角 = 太陽方位角（直接對準太陽）
        optimal_azimuth = solar_data['sun_azimuth']
        
        # 最佳傾角 = 90° - 太陽仰角（讓面板垂直於太陽光）
        optimal_tilt = 90 - solar_data['sun_elevation']
        
        # 限制在可行範圍內
        optimal_azimuth = max(self.azimuth_limits[0], min(self.azimuth_limits[1], optimal_azimuth))
        optimal_tilt = max(self.tilt_limits[0], min(self.tilt_limits[1], optimal_tilt))
        
        return optimal_azimuth, optimal_tilt

    def simulate_light_sensors(self, solar_data: Dict, panel_azimuth: float, panel_tilt: float) -> Dict[str, float]:
        """模擬光感測器數值 - 基於PVlib數據但加入噪聲"""
        if solar_data['sun_elevation'] <= 0:
            return {'east': 0, 'west': 0, 'north': 0, 'south': 0}
        
        # 計算面板接收的基礎輻射
        base_irradiance = self.calculate_panel_irradiance(solar_data, panel_azimuth, panel_tilt)
        
        # 感測器位置偏移（模擬四個感測器在面板邊緣的位置）
        sensor_offset_angle = 2.0  # 度
        
        light_values = {}
        
       # 東西感測器 - 基於方位角差異
        azimuth_error = panel_azimuth - solar_data['sun_azimuth']

        # 當角度差異過大時，使用簡化邏輯
        if azimuth_error < -45:  # 太陽在面板西邊很遠
            light_values['east'] = base_irradiance * 0.3   # 東邊較暗
            light_values['west'] = base_irradiance * 0.7   # 西邊較亮
        elif azimuth_error > 45:   # 太陽在面板東邊很遠  
            light_values['east'] = base_irradiance * 0.7   # 東邊較亮
            light_values['west'] = base_irradiance * 0.3   # 西邊較暗
        else:
            # 原來的精確邏輯
            east_angle_diff = azimuth_error - sensor_offset_angle
            east_cos = math.cos(math.radians(east_angle_diff))
            light_values['east'] = base_irradiance * max(0.1, east_cos)
            
            west_angle_diff = azimuth_error + sensor_offset_angle
            west_cos = math.cos(math.radians(west_angle_diff))
            light_values['west'] = base_irradiance * max(0.1, west_cos)
        
        # 南北感測器 - 基於傾角差異
        optimal_tilt = 90 - solar_data['sun_elevation']
        tilt_error = panel_tilt - optimal_tilt

        # 當傾角差異過大時，使用簡化邏輯
        if tilt_error > 20:  # 面板傾角太大
            light_values['north'] = base_irradiance * 0.7   # 北邊較亮（提示減少傾角）
            light_values['south'] = base_irradiance * 0.3   # 南邊較暗
        elif tilt_error < -20:  # 面板傾角太小
            light_values['north'] = base_irradiance * 0.3   # 北邊較暗
            light_values['south'] = base_irradiance * 0.7   # 南邊較亮（提示增加傾角）
        else:
            # 原來的精確邏輯
            north_angle_diff = tilt_error - sensor_offset_angle
            north_cos = math.cos(math.radians(north_angle_diff))
            light_values['north'] = base_irradiance * max(0.1, north_cos)
            
            south_angle_diff = tilt_error + sensor_offset_angle
            south_cos = math.cos(math.radians(south_angle_diff))
            light_values['south'] = base_irradiance * max(0.1, south_cos)
        
        # 添加感測器噪聲（這裡用噪聲模擬天氣變化）
        for direction in light_values:
            if self.noise_level > 0:
                # 基礎噪聲
                noise_std = light_values[direction] * self.noise_level
                noise = np.random.normal(0, noise_std)
                
                # 額外的天氣噪聲（模擬雲層遮擋等）
                weather_noise_factor = np.random.uniform(0.7, 1.3)  # 70%-130%的變化
                
                light_values[direction] = light_values[direction] * weather_noise_factor + noise
                light_values[direction] = max(0, light_values[direction])
        
        return light_values

    def move_ideal_tracker(self, optimal_azimuth: float, optimal_tilt: float) -> str:
        """移動理想追日器到最佳角度"""
        moved = False
        movement_description = []
        
        # 移動方位角
        if optimal_azimuth is not None and abs(self.ideal_azimuth - optimal_azimuth) > 0.5:
            old_azimuth = self.ideal_azimuth
            self.ideal_azimuth = optimal_azimuth
            angle_change = abs(optimal_azimuth - old_azimuth)
            self.ideal_movement_angle += angle_change
            movement_description.append(f"方位角: {old_azimuth:.1f}°→{optimal_azimuth:.1f}°")
            moved = True
        
        # 移動傾角
        if optimal_tilt is not None and abs(self.ideal_tilt - optimal_tilt) > 0.5:
            old_tilt = self.ideal_tilt
            self.ideal_tilt = optimal_tilt
            angle_change = abs(optimal_tilt - old_tilt)
            self.ideal_movement_angle += angle_change
            movement_description.append(f"傾角: {old_tilt:.1f}°→{optimal_tilt:.1f}°")
            moved = True
        
        if moved:
            self.ideal_movement_count += 1
            return "理想移動: " + ", ".join(movement_description)
        else:
            return "理想保持最佳位置"

    def sensor_tracking_decision(self, light_values: Dict[str, float]) -> str:
        """感測器追日決策邏輯"""
        ew_difference = light_values['east'] - light_values['west']
        ns_difference = light_values['south'] - light_values['north']
        
        # 檢查夜間
        max_light = max(light_values.values())
        if max_light < 10:
            return self.return_sensor_to_east()
        
        actions = []
        moved = False
        
        # 東西方向判斷（方位角控制）
        if abs(ew_difference) > self.light_threshold:
            old_azimuth = self.sensor_azimuth
            if ew_difference > 0:  # 東邊較亮，向東轉
                new_azimuth = max(self.azimuth_limits[0], self.sensor_azimuth - 5)
                actions.append("向東轉動")
            else:  # 西邊較亮，向西轉
                new_azimuth = min(self.azimuth_limits[1], self.sensor_azimuth + 5)
                actions.append("向西轉動")
            
            if abs(new_azimuth - old_azimuth) > 0.1:
                angle_change = abs(new_azimuth - old_azimuth)
                self.sensor_azimuth = new_azimuth
                self.sensor_movement_angle += angle_change
                moved = True
        
        # 南北方向判斷（傾角控制）
        if abs(ns_difference) > self.light_threshold:
            old_tilt = self.sensor_tilt
            if ns_difference > 0:  # 南邊較亮，增加傾角
                new_tilt = min(self.tilt_limits[1], self.sensor_tilt + 2)
                actions.append("增加傾角")
            else:  # 北邊較亮，減少傾角
                new_tilt = max(self.tilt_limits[0], self.sensor_tilt - 2)
                actions.append("減少傾角")
            
            if abs(new_tilt - old_tilt) > 0.1:
                angle_change = abs(new_tilt - old_tilt)
                self.sensor_tilt = new_tilt
                self.sensor_movement_angle += angle_change
                moved = True
        
        if moved:
            self.sensor_movement_count += 1
            return "感測器移動: " + " + ".join(actions)
        else:
            return "感測器保持位置"

    def return_sensor_to_east(self) -> str:
        """感測器追日器回歸東方初始位置"""
        moved = False
        if abs(self.sensor_azimuth - 135) > 0.1:
            old_azimuth = self.sensor_azimuth
            self.sensor_azimuth = 135.0
            self.sensor_movement_angle += abs(135 - old_azimuth)
            moved = True
        
        if abs(self.sensor_tilt - 45) > 0.1:
            old_tilt = self.sensor_tilt
            self.sensor_tilt = 45.0
            self.sensor_movement_angle += abs(45 - old_tilt)
            moved = True
        
        if moved:
            self.sensor_movement_count += 1
            return "感測器回歸東方位置"
        return "感測器保持東方位置"

    def log_ideal_data(self, current_time: datetime.datetime, solar_data: Dict, 
                      optimal_azimuth: float, optimal_tilt: float, 
                      panel_irradiance: float, power: float, decision: str):
        """記錄理想追日數據"""
        energy_increment = (power / 1000.0) * (self.data_interval / 3600.0)
        self.ideal_energy += energy_increment
        
        # 計算誤差（理想追日應該誤差接近0）
        azimuth_error = abs(self.ideal_azimuth - solar_data['sun_azimuth']) if solar_data['sun_azimuth'] else 0
        tilt_error = abs(self.ideal_tilt - (90 - solar_data['sun_elevation'])) if solar_data['sun_elevation'] > 0 else 0
        
        row_data = [
            current_time.isoformat(),
            current_time.strftime('%Y-%m-%d'),
            current_time.strftime('%H:%M:%S'),
            self.ideal_azimuth,
            self.ideal_tilt,
            solar_data['sun_azimuth'],
            solar_data['sun_elevation'],
            optimal_azimuth or 0,
            optimal_tilt or 0,
            azimuth_error,
            tilt_error,
            solar_data['ghi'],
            solar_data['dni'],
            solar_data['dhi'],
            panel_irradiance,
            power,
            self.ideal_energy,
            self.ideal_movement_count,
            self.ideal_movement_angle,
            decision,
            'IDEAL'
        ]
        
        try:
            with open(self.ideal_log_file, 'a', newline='', encoding='utf-8') as f:
                writer = csv.writer(f)
                writer.writerow(row_data)
        except Exception as e:
            self.logger.error(f"理想追日數據記錄失敗: {e}")

    def log_sensor_data(self, current_time: datetime.datetime, solar_data: Dict,
                       light_values: Dict[str, float], panel_irradiance: float, 
                       power: float, decision: str):
        """記錄感測器追日數據"""
        energy_increment = (power / 1000.0) * (self.data_interval / 3600.0)
        self.sensor_energy += energy_increment
        
        ew_difference = light_values['east'] - light_values['west']
        ns_difference = light_values['south'] - light_values['north']
        
        row_data = [
            current_time.isoformat(),
            current_time.strftime('%Y-%m-%d'),
            current_time.strftime('%H:%M:%S'),
            self.sensor_azimuth,
            self.sensor_tilt,
            light_values['east'],
            light_values['west'],
            light_values['north'],
            light_values['south'],
            ew_difference,
            ns_difference,
            solar_data['sun_azimuth'],
            solar_data['sun_elevation'],
            solar_data['ghi'],
            solar_data['dni'],
            solar_data['dhi'],
            panel_irradiance,
            power,
            self.sensor_energy,
            self.sensor_movement_count,
            self.sensor_movement_angle,
            decision,
            self.noise_level,
            'SENSOR'
        ]
        
        try:
            with open(self.sensor_log_file, 'a', newline='', encoding='utf-8') as f:
                writer = csv.writer(f)
                writer.writerow(row_data)
        except Exception as e:
            self.logger.error(f"感測器追日數據記錄失敗: {e}")

    def display_status(self, current_time: datetime.datetime, solar_data: Dict,
                      light_values: Dict[str, float], ideal_power: float, 
                      sensor_power: float, ideal_decision: str, sensor_decision: str):
        """顯示當前狀態"""
        print(f"\n=== {current_time.strftime('%H:%M:%S')} ===")
        
        if solar_data['sun_elevation'] > 0:
            print(f"太陽位置: 方位角={solar_data['sun_azimuth']:.1f}°, 仰角={solar_data['sun_elevation']:.1f}°")
            print(f"輻射量: GHI={solar_data['ghi']:.1f}, DNI={solar_data['dni']:.1f}, DHI={solar_data['dhi']:.1f} W/m²")
        
        print(f"\n【理想追日器】")
        print(f"  角度: 方位角={self.ideal_azimuth:.1f}°, 傾角={self.ideal_tilt:.1f}°")
        print(f"  功率: {ideal_power:.2f}W")
        print(f"  累計發電: {self.ideal_energy:.4f}kWh")
        print(f"  移動次數: {self.ideal_movement_count}")
        print(f"  決策: {ideal_decision}")
        
        print(f"\n【感測器追日器】(噪聲水平: {self.noise_level})")
        print(f"  角度: 方位角={self.sensor_azimuth:.1f}°, 傾角={self.sensor_tilt:.1f}°")
        print(f"  光照: 東={light_values['east']:.1f}, 西={light_values['west']:.1f}, "
              f"南={light_values['south']:.1f}, 北={light_values['north']:.1f}")
        print(f"  差異: 東西={light_values['east'] - light_values['west']:.1f}, "
              f"南北={light_values['south'] - light_values['north']:.1f}")
        print(f"  功率: {sensor_power:.2f}W")
        print(f"  累計發電: {self.sensor_energy:.4f}kWh")
        print(f"  移動次數: {self.sensor_movement_count}")
        print(f"  決策: {sensor_decision}")
        
        # 比較統計
        energy_diff = self.ideal_energy - self.sensor_energy
        efficiency_ratio = (self.sensor_energy / self.ideal_energy * 100) if self.ideal_energy > 0 else 0
        print(f"\n【比較】")
        print(f"  發電差異: {energy_diff:.4f}kWh")
        print(f"  感測器效率: {efficiency_ratio:.1f}%")

    def print_summary(self):
        """顯示實驗摘要"""
        print("\n" + "="*60)
        print("雙軌道追日實驗摘要")
        print("="*60)
        
        print(f"【理想追日器】")
        print(f"  總發電量: {self.ideal_energy:.4f} kWh")
        print(f"  移動次數: {self.ideal_movement_count}")
        print(f"  總移動角度: {self.sensor_movement_angle:.1f}°")
        print(f"  最終位置: 方位角={self.sensor_azimuth:.1f}°, 傾角={self.sensor_tilt:.1f}°")
        print(f"  數據檔案: {self.sensor_log_file}")
        
        # 比較分析
        print(f"\n【性能比較】")
        energy_diff = self.ideal_energy - self.sensor_energy
        efficiency_ratio = (self.sensor_energy / self.ideal_energy * 100) if self.ideal_energy > 0 else 0
        
        if self.ideal_energy > 0:
            print(f"  發電量差異: {energy_diff:.4f} kWh ({energy_diff/self.ideal_energy*100:.1f}%)")
        else:
            print(f"  發電量差異: {energy_diff:.4f} kWh (理想發電量為0，無法計算百分比)")
        print(f"  感測器追日效率: {efficiency_ratio:.1f}%")
        print(f"  移動次數比較: 理想{self.ideal_movement_count} vs 感測器{self.sensor_movement_count}")
        
        if self.ideal_movement_count > 0 and self.sensor_movement_count > 0:
            ideal_efficiency = self.ideal_energy / self.ideal_movement_count
            sensor_efficiency = self.sensor_energy / self.sensor_movement_count
            print(f"  每次移動發電效率: 理想{ideal_efficiency:.6f} vs 感測器{sensor_efficiency:.6f} kWh/次")
        
        print("="*60)

    def get_experiment_summary(self) -> Dict:
        """獲取實驗摘要"""
        return {
            'ideal_tracker': {
                'total_energy': self.ideal_energy,
                'movement_count': self.ideal_movement_count,
                'total_movement_angle': self.ideal_movement_angle,
                'final_position': {
                    'azimuth': self.ideal_azimuth,
                    'tilt': self.ideal_tilt
                },
                'log_file': self.ideal_log_file
            },
            'sensor_tracker': {
                'total_energy': self.sensor_energy,
                'movement_count': self.sensor_movement_count,
                'total_movement_angle': self.sensor_movement_angle,
                'final_position': {
                    'azimuth': self.sensor_azimuth,
                    'tilt': self.sensor_tilt
                },
                'log_file': self.sensor_log_file,
                'noise_level': self.noise_level
            },
            'comparison': {
                'energy_difference': self.ideal_energy - self.sensor_energy,
                'efficiency_ratio': (self.sensor_energy / self.ideal_energy * 100) if self.ideal_energy > 0 else 0,
                'movement_difference': self.sensor_movement_count - self.ideal_movement_count
            }
        }

    def run_dual_tracking_experiment(self, duration_hours: int = 12, display_interval: int = 3):
        """執行雙軌道追日實驗"""
        self.is_running = True
        
        self.logger.info(f"開始雙軌道追日實驗")
        self.logger.info(f"實驗時長: {duration_hours}虛擬小時")
        self.logger.info(f"檢測間隔: {self.data_interval}秒")
        self.logger.info(f"噪聲水平: {self.noise_level}")
        
        print(f"開始雙軌道追日實驗 - {duration_hours}小時")
        print("按 Ctrl+C 可隨時停止實驗")
        
        cycle_count = 0
        self.cycle_count = 0

        try:
            while self.is_running:
                cycle_count += 1
                self.cycle_count = cycle_count
                
                # 檢查實驗結束條件
                if self.virtual_time_offset > duration_hours * 3600:
                    print(f"雙軌道實驗完成! 總時長: {duration_hours}虛擬小時")
                    break
                
                # 獲取當前時間和太陽數據
                current_time = self.get_virtual_time()
                solar_data = self.calculate_solar_data(current_time)
                
                # === 理想追日器邏輯 ===
                optimal_azimuth, optimal_tilt = self.calculate_optimal_angles(solar_data)
                
                if optimal_azimuth is not None and optimal_tilt is not None:
                    ideal_decision = self.move_ideal_tracker(optimal_azimuth, optimal_tilt)
                else:
                    ideal_decision = "理想追日器 - 夜間保持位置"
                
                # 計算理想追日器功率
                ideal_irradiance = self.calculate_panel_irradiance(solar_data, self.ideal_azimuth, self.ideal_tilt)
                ideal_power = self.calculate_power_output(ideal_irradiance)
                
                # 記錄理想追日器數據
                self.log_ideal_data(current_time, solar_data, optimal_azimuth, optimal_tilt, 
                                   ideal_irradiance, ideal_power, ideal_decision)
                
                # === 感測器追日器邏輯 ===
                light_values = self.simulate_light_sensors(solar_data, self.sensor_azimuth, self.sensor_tilt)
                sensor_decision = self.sensor_tracking_decision(light_values)
                
                # 計算感測器追日器功率
                sensor_irradiance = self.calculate_panel_irradiance(solar_data, self.sensor_azimuth, self.sensor_tilt)
                sensor_power = self.calculate_power_output(sensor_irradiance)
                
                # 記錄感測器追日器數據
                self.log_sensor_data(current_time, solar_data, light_values, 
                                    sensor_irradiance, sensor_power, sensor_decision)
                
                # 顯示狀態
                if cycle_count % display_interval == 0:
                    self.display_status(current_time, solar_data, light_values, 
                                       ideal_power, sensor_power, ideal_decision, sensor_decision)
                
                # 等待下一次檢測
                sleep_time = self.data_interval / self.simulation_speed
                time.sleep(sleep_time)
                
        except KeyboardInterrupt:
            self.logger.info("實驗被用戶中斷")
        except Exception as e:
            self.logger.error(f"實驗執行錯誤: {e}")
        finally:
            self.is_running = False
            self.print_summary()


def get_user_input():
    """獲取用戶輸入"""
    print("整合太陽能追日系統配置")
    print("="*40)
    
    # 地理位置設定
    print("地理位置設定:")
    print("1. 新竹 (預設)")
    print("2. 台北")
    print("3. 台中")
    print("4. 台南")
    print("5. 高雄")
    print("6. 自訂")
    
    location_choice = input("請選擇地理位置 (1-6) 或按Enter使用新竹: ").strip()
    
    locations = {
        "1": (24.8138, 120.9675, "新竹"),
        "2": (25.0330, 121.5654, "台北"),
        "3": (24.1477, 120.6736, "台中"),
        "4": (22.9997, 120.2270, "台南"),
        "5": (22.6273, 120.3014, "高雄")
    }
    
    if location_choice in locations:
        latitude, longitude, city_name = locations[location_choice]
        print(f"選擇地點: {city_name}")
    elif location_choice == "6":
        latitude = float(input("請輸入緯度: "))
        longitude = float(input("請輸入經度: "))
    else:
        latitude, longitude, city_name = locations["1"]
        print(f"使用預設地點: {city_name}")
    
    # 基本參數設定
    print("\n基本參數設定:")
    light_threshold = float(input("光照差異閾值 (建議50): ") or "50")
    data_interval = int(input("檢測間隔 (秒, 建議30): ") or "30")
    
    # 噪聲參數
    print("\n噪聲模擬參數:")
    noise_level = float(input("感測器噪聲水平 0-1 (建議0.1): ") or "0.1")
    
    # 日期設定
    print("\n日期設定:")
    print("1. 夏至 (2024-06-21) - 最高太陽仰角")
    print("2. 春分/秋分 (2024-03-20)")
    print("3. 冬至 (2024-12-21) - 最低太陽仰角")
    print("4. 今天")
    print("5. 自訂日期")

    date_choice = input("請選擇日期 (1-5) 或按Enter使用今天: ").strip()

    date_options = {
        "1": "2024-06-21",  # 夏至
        "2": "2024-03-20",  # 春分
        "3": "2024-12-21",  # 冬至
        "4": None           # 今天
    }

    if date_choice in date_options:
        start_date = date_options[date_choice]
        if date_choice == "1":
            print("選擇: 夏至 (太陽仰角最高)")
        elif date_choice == "2":
            print("選擇: 春分 (太陽仰角中等)")
        elif date_choice == "3":
            print("選擇: 冬至 (太陽仰角最低)")
        else:
            print("選擇: 今天")
    elif date_choice == "5":
        start_date = input("請輸入日期 (YYYY-MM-DD): ")
    else:
        start_date = None
        print("使用今天日期")

    # 實驗參數
    print("\n實驗參數:")
    duration_hours = int(input("實驗時長 (小時, 建議12): ") or "12")
    simulation_speed = float(input("模擬速度倍率 (建議10): ") or "10")
    
    # 顯示間隔
    display_interval = int(input("顯示狀態間隔 (週期數, 建議3): ") or "3")
    
    return {
        'latitude': latitude,
        'longitude': longitude,
        'light_threshold': light_threshold,
        'data_interval': data_interval,
        'noise_level': noise_level,
        'duration_hours': duration_hours,
        'simulation_speed': simulation_speed,
        'display_interval': display_interval,
        'start_date': start_date
    }


def quick_test():
    """快速測試功能"""
    print("快速測試模式 - 2小時模擬，60倍速")
    
    tracker = IntegratedSolarTracker(
        simulation_mode=True,
        latitude=24.8138,  # 新竹
        longitude=120.9675,
        light_threshold=50.0,
        data_interval=10,
        simulation_speed=60.0,
        noise_level=0.1,
        log_prefix="quicktest"
    )
    
    tracker.run_dual_tracking_experiment(duration_hours=2, display_interval=5)
    
    summary = tracker.get_experiment_summary()
    print(f"\n快速測試完成!")
    print(f"理想追日發電量: {summary['ideal_tracker']['total_energy']:.4f} kWh")
    print(f"感測器追日發電量: {summary['sensor_tracker']['total_energy']:.4f} kWh")
    print(f"感測器效率: {summary['comparison']['efficiency_ratio']:.1f}%")
    print(f"理想追日檔案: {summary['ideal_tracker']['log_file']}")
    print(f"感測器追日檔案: {summary['sensor_tracker']['log_file']}")


def run_comparison_experiments():
    """運行不同噪聲水平的比較實驗"""
    print("多噪聲水平比較實驗")
    print("="*30)
    
    noise_levels = [0.0, 0.05, 0.1, 0.2, 0.3]
    results = []
    
    for noise in noise_levels:
        print(f"\n運行噪聲水平 {noise} 的實驗...")
        
        tracker = IntegratedSolarTracker(
            simulation_mode=True,
            latitude=24.8138,
            longitude=120.9675,
            light_threshold=50.0,
            data_interval=30,
            simulation_speed=30.0,
            noise_level=noise,
            log_prefix=f"noise_{noise:.2f}"
        )
        
        tracker.run_dual_tracking_experiment(duration_hours=6, display_interval=10)
        summary = tracker.get_experiment_summary()
        
        results.append({
            'noise_level': noise,
            'ideal_energy': summary['ideal_tracker']['total_energy'],
            'sensor_energy': summary['sensor_tracker']['total_energy'],
            'efficiency': summary['comparison']['efficiency_ratio'],
            'ideal_movements': summary['ideal_tracker']['movement_count'],
            'sensor_movements': summary['sensor_tracker']['movement_count']
        })
        
        print(f"完成噪聲水平 {noise}: 效率 {summary['comparison']['efficiency_ratio']:.1f}%")
    
    # 顯示比較結果
    print(f"\n噪聲水平比較結果:")
    print("="*60)
    print(f"{'噪聲':<6} {'理想kWh':<10} {'感測kWh':<10} {'效率%':<8} {'理想移動':<10} {'感測移動':<10}")
    print("-"*60)
    for result in results:
        print(f"{result['noise_level']:<6.2f} {result['ideal_energy']:<10.4f} "
              f"{result['sensor_energy']:<10.4f} {result['efficiency']:<8.1f} "
              f"{result['ideal_movements']:<10} {result['sensor_movements']:<10}")


# 主程式
if __name__ == "__main__":
    try:
        print("整合太陽能追日系統 v5.0")
        print("雙軌道比較: 理想PVlib追日 vs 噪聲感測器追日")
        print("="*50)
        
        # 檢查依賴
        try:
            import pvlib
            print("✓ PVlib模組已安裝")
        except ImportError:
            print("✗ 警告: PVlib模組未安裝，將使用簡化模型")
            print("建議安裝: pip install pvlib")
        
        try:
            import numpy as np
            print("✓ NumPy模組已安裝")
        except ImportError:
            print("✗ 錯誤: NumPy模組未安裝")
            print("請安裝: pip install numpy")
            exit(1)
        
        print("\n選擇執行模式:")
        print("1. 完整配置模式")
        print("2. 快速測試模式")
        print("3. 多噪聲水平比較實驗")
        
        mode = input("請選擇 (1-3) 或按Enter進入完整配置: ").strip()
        
        if mode == "2":
            quick_test()
        elif mode == "3":
            run_comparison_experiments()
        else:
            # 獲取用戶設定
            config = get_user_input()
            
            # 創建整合追日控制器
            tracker = IntegratedSolarTracker(
                simulation_mode=True,
                latitude=config['latitude'],
                longitude=config['longitude'],
                light_threshold=config['light_threshold'],
                data_interval=config['data_interval'],
                simulation_speed=config['simulation_speed'],
                noise_level=config['noise_level'],
                start_date=config['start_date'],
                log_prefix="custom"
            )
            
            # 執行實驗
            print(f"\n開始雙軌道實驗...")
            print("按 Ctrl+C 可隨時停止實驗")
            
            tracker.run_dual_tracking_experiment(
                duration_hours=config['duration_hours'],
                display_interval=config['display_interval']
            )
            
            # 獲取實驗摘要
            summary = tracker.get_experiment_summary()
            print(f"\n最終摘要:")
            print(f"理想追日發電量: {summary['ideal_tracker']['total_energy']:.4f} kWh")
            print(f"感測器追日發電量: {summary['sensor_tracker']['total_energy']:.4f} kWh")
            print(f"感測器效率: {summary['comparison']['efficiency_ratio']:.1f}%")
            print(f"發電差異: {summary['comparison']['energy_difference']:.4f} kWh")
            print(f"移動次數差異: {summary['comparison']['movement_difference']}")
            print(f"\n數據檔案:")
            print(f"理想追日: {summary['ideal_tracker']['log_file']}")
            print(f"感測器追日: {summary['sensor_tracker']['log_file']}")
        
        print("\n實驗完成!")
        
    except KeyboardInterrupt:
        print("\n程式被用戶中斷")
    except Exception as e:
        print(f"程式執行錯誤: {e}")
        import traceback
        traceback.print_exc()
    finally:
        print("程式結束")