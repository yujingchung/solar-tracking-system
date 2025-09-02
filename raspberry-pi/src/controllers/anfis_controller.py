import numpy as np
import pandas as pd
from datetime import datetime, timedelta
from typing import Tuple, Dict, Optional, List
import json
import logging
from enum import Enum
import csv
import os

class SystemState(Enum):
    """系統狀態枚舉"""
    INITIALIZING = "initializing"
    TRACKING = "tracking"
    ADJUSTING = "adjusting"
    RETURNING = "returning"
    IDLE = "idle"

class SolarTrackingController:
    """
    基於ANFIS流程圖的太陽能追日控制系統
    """
    
    def __init__(self, anfis_model=None):
        self.anfis_model = anfis_model
        self.system_state = SystemState.INITIALIZING
        self.last_theoretical_angles = None  # 上次理論角度
        self.last_fine_tune = None           # 上次微調資訊
        
        # 系統參數
        self.angle_ranges = {
            'azimuth': (160, 200),    # 方位角範圍
            'elevation': (10, 30)     # 傾角範圍
        }
        
        # 閾值設定
        self.thresholds = {
            'power_expectation_tolerance': 0.95,  # 發電量接近預期的容忍度
            'movement_worthiness': 2.0,           # 移動價值閾值(W)
            'fine_tune_improvement': 0.5,         # 微調改善閾值(W)
            'system_error_threshold': 5.0,        # 系統性誤差閾值(W)
        }
        
        # 時間設定
        self.timing = {
            'wait_interval': 5,          # 等待間隔時間(秒)
            'sun_start_hour': 6,           # 日出開始時間
            'sun_end_hour': 18,            # 日落結束時間
            'east_initial_azimuth': 160,   # 東方初始方位角
            'east_initial_elevation': 15   # 東方初始傾角
        }
        
        # 歷史記錄
        self.experience_database = {
            'successful_experiences': [],
            'failed_experiences': [],
            'prediction_errors': [],
            'model_corrections': []
        }
        
        # 當前狀態記錄
        self.current_data = {
            'angles': {'azimuth': 180, 'elevation': 15},
            'power': 0.0,
            'sensor_readings': {},
            'last_movement_time': None,
            'correction_coefficient': 1.0
        }
        
        # 設定日誌
        logging.basicConfig(level=logging.INFO)
        self.logger = logging.getLogger(__name__)
        
    def main_control_loop(self):
        """
        主控制循環 - 實現流程圖的主要邏輯
        """
            # 設定模擬起始與結束時間
        simulate_start = datetime(2024, 7, 28, 6, 0, 0)  # 早上6點
        simulate_end = simulate_start + timedelta(days=1) # 模擬一天
        simulate_time = simulate_start
        simulate_step = timedelta(minutes=10)  # 每10分鐘模擬一次
        # 在 __init__ 或 main_control_loop 開頭加
        action_csv = r"d:\宇靖\研究\tracking_action_log.csv"
        action_fields = [
            "predict_time", "predicted_power", "predicted_azimuth", "predicted_elevation",
            "moved", "move_time", "moved_azimuth", "moved_elevation", "power_after_move"
        ]
        if not os.path.exists(action_csv):
            with open(action_csv, "w", newline="", encoding="utf-8") as f:
                writer = csv.DictWriter(f, fieldnames=action_fields)
                writer.writeheader()

        self.logger.info("啟動太陽能追日控制系統")
        csv_file = r"d:\宇靖\研究\tracking_status_log.csv"
        csv_fields = [
            "timestamp", "system_state", "azimuth", "elevation",
            "theoretical_azimuth", "theoretical_elevation",
            "predicted_power", "current_power",
            "fine_tune_azimuth", "fine_tune_elevation",
            "correction_coefficient", "successful", "failed",
            "prediction_errors", "corrections", "last_movement"
        ]
        # 若檔案不存在，先寫入標題
        if not os.path.exists(csv_file):
            with open(csv_file, "w", newline="", encoding="utf-8") as f:
                writer = csv.DictWriter(f, fieldnames=csv_fields)
                writer.writeheader()

        while simulate_time < simulate_end:
            try:
                # 步驟1: 讀取時間及感測器數據（傳入模擬時間）
                sensor_data = self.read_sensor_data(simulate_time)
                current_time = simulate_time

                # 檢查是否為追日時間
                if not self.is_sun_tracking_time(current_time):
                    self.system_state = SystemState.RETURNING  # <--- 新增
                    self.return_to_east_position()
                    # 取得狀態並寫入CSV
                    status = self.get_system_status()
                    row = {
                        "timestamp": status["timestamp"].strftime("%Y-%m-%d %H:%M:%S") if isinstance(status["timestamp"], datetime) else status["timestamp"],
                        "system_state": status["system_state"],
                        "azimuth": status["current_angles"]["azimuth"],
                        "elevation": status["current_angles"]["elevation"],
                        "theoretical_azimuth": status["theoretical_angles"]["azimuth"] if status["theoretical_angles"] else "",
                        "theoretical_elevation": status["theoretical_angles"]["elevation"] if status["theoretical_angles"] else "",
                        "predicted_power": status["predicted_power"],
                        "current_power": status["current_power"],
                        "fine_tune_azimuth": status["fine_tune"]["azimuth_adjustment"] if status["fine_tune"] else "",
                        "fine_tune_elevation": status["fine_tune"]["elevation_adjustment"] if status["fine_tune"] else "",
                        "correction_coefficient": status["correction_coefficient"],
                        "successful": status["experience_counts"]["successful"],
                        "failed": status["experience_counts"]["failed"],
                        "prediction_errors": status["experience_counts"]["prediction_errors"],
                        "corrections": status["experience_counts"]["corrections"],
                        "last_movement": status["last_movement"].strftime("%Y-%m-%d %H:%M:%S") if status["last_movement"] else ""
                    }
                    with open(csv_file, "a", newline="", encoding="utf-8") as f:
                        writer = csv.DictWriter(f, fieldnames=csv_fields)
                        writer.writerow(row)
                    # 不用 sleep，直接進入下一個模擬時間
                    simulate_time += simulate_step
                    continue

                # 步驟2: 判斷發電量是否接近預期
                power_meets_expectation = self.check_power_expectation(sensor_data)

                if power_meets_expectation:
                    self.maintain_position_and_record_success(sensor_data)
                else:
                    self.system_state = SystemState.ADJUSTING  # <--- 新增
                    self.optimize_tracking_position(sensor_data)

                # 取得狀態並寫入CSV
                status = self.get_system_status()
                row = {
                    "timestamp": status["timestamp"].strftime("%Y-%m-%d %H:%M:%S") if isinstance(status["timestamp"], datetime) else status["timestamp"],
                    "system_state": status["system_state"],
                    "azimuth": status["current_angles"]["azimuth"],
                    "elevation": status["current_angles"]["elevation"],
                    "theoretical_azimuth": status["theoretical_angles"]["azimuth"] if status["theoretical_angles"] else "",
                    "theoretical_elevation": status["theoretical_angles"]["elevation"] if status["theoretical_angles"] else "",
                    "predicted_power": status["predicted_power"],
                    "current_power": status["current_power"],
                    "fine_tune_azimuth": status["fine_tune"]["azimuth_adjustment"] if status["fine_tune"] else "",
                    "fine_tune_elevation": status["fine_tune"]["elevation_adjustment"] if status["fine_tune"] else "",
                    "correction_coefficient": status["correction_coefficient"],
                    "successful": status["experience_counts"]["successful"],
                    "failed": status["experience_counts"]["failed"],
                    "prediction_errors": status["experience_counts"]["prediction_errors"],
                    "corrections": status["experience_counts"]["corrections"],
                    "last_movement": status["last_movement"].strftime("%Y-%m-%d %H:%M:%S") if status["last_movement"] else ""
                }
                with open(csv_file, "a", newline="", encoding="utf-8") as f:
                    writer = csv.DictWriter(f, fieldnames=csv_fields)
                    writer.writerow(row)

                # 不用 sleep，直接進入下一個模擬時間
                simulate_time += simulate_step
            except Exception as e:
                self.logger.error(f"控制循環發生錯誤: {e}")
                self.handle_system_error(e)
    
    def read_sensor_data(self, custom_time=None) -> Dict:
        now = custom_time if custom_time else datetime.now()
        """
        讀取感測器數據
        包括：光強度絕對值、太陽能板輸出功率、當前角度
        """
        # 模擬感測器讀取（實際實現時替換為真實硬體接口）
        sensor_data = {
            'timestamp':now,
            'light_intensity': {
                'east': np.random.uniform(500, 1000),
                'west': np.random.uniform(500, 1000),
                'south': np.random.uniform(500, 1000),
                'north': np.random.uniform(500, 1000),
                'absolute_total': 0  # 光強度絕對值
            },
            'current_power': np.random.uniform(40, 60),  # 當前功率
            'current_angles': self.current_data['angles'].copy(),
            'environmental': {
                'temperature': np.random.uniform(20, 35),
                'humidity': np.random.uniform(40, 80),
                'wind_speed': np.random.uniform(0, 10)
            }
        }
        
        # 計算光強度絕對值
        sensor_data['light_intensity']['absolute_total'] = sum([
            sensor_data['light_intensity']['east'],
            sensor_data['light_intensity']['west'],
            sensor_data['light_intensity']['south'],
            sensor_data['light_intensity']['north']
        ])
        
        # 更新當前數據
        self.current_data['sensor_readings'] = sensor_data
        self.current_data['power'] = sensor_data['current_power']
        
        return sensor_data
    
    def is_sun_tracking_time(self, current_time: datetime) -> bool:
        """判斷是否為太陽追日時間"""
        current_hour = current_time.hour
        return self.timing['sun_start_hour'] <= current_hour <= self.timing['sun_end_hour']
    
    def check_power_expectation(self, sensor_data: Dict) -> bool:
        """
        判斷發電量是否接近預期
        """
        if self.anfis_model is None:
            # 模擬預期功率計算
            expected_power = self.calculate_expected_power_simulation(sensor_data)
        else:
            # 使用ANFIS模型預測預期功率
            expected_power = self.predict_expected_power(sensor_data)
        
        current_power = sensor_data['current_power']
        power_ratio = current_power / expected_power if expected_power > 0 else 0
        
        is_meeting_expectation = power_ratio >= self.thresholds['power_expectation_tolerance']
        
        self.logger.info(f"當前功率: {current_power:.2f}W, 預期功率: {expected_power:.2f}W, "
                        f"比率: {power_ratio:.2%}, 符合預期: {is_meeting_expectation}")
        
        return is_meeting_expectation
    
    def calculate_expected_power_simulation(self, sensor_data: Dict) -> float:
        """模擬預期功率計算（實際使用時會被ANFIS模型替換）"""
        base_power = sensor_data['light_intensity']['absolute_total'] / 50
        angle_efficiency = self.calculate_angle_efficiency(sensor_data['current_angles'])
        return base_power * angle_efficiency * self.current_data['correction_coefficient']
    
    def predict_expected_power(self, sensor_data: Dict) -> float:
        """使用ANFIS模型預測預期功率"""
        # 準備模型輸入
        input_features = self.prepare_model_input(sensor_data)
        
        # ANFIS模型推理
        predicted_power = self.anfis_model.predict(input_features)
        
        # 應用修正係數
        corrected_power = predicted_power * self.current_data['correction_coefficient']
        
        return corrected_power[0] if isinstance(corrected_power, np.ndarray) else corrected_power
    
    def maintain_position_and_record_success(self, sensor_data: Dict):
        """保持當前位置並記錄成功經驗"""
        success_record = {
            'timestamp': datetime.now(),
            'position': self.current_data['angles'].copy(),
            'power': sensor_data['current_power'],
            'light_conditions': sensor_data['light_intensity'].copy(),
            'environmental': sensor_data['environmental'].copy(),
            'action': 'maintain_position'
        }
        
        self.experience_database['successful_experiences'].append(success_record)
        self.logger.info(f"記錄成功經驗: 位置({self.current_data['angles']['azimuth']:.1f}°, "
                        f"{self.current_data['angles']['elevation']:.1f}°), 功率: {sensor_data['current_power']:.2f}W")
        
        # 限制經驗數據庫大小
        if len(self.experience_database['successful_experiences']) > 1000:
            self.experience_database['successful_experiences'] = \
                self.experience_database['successful_experiences'][-500:]
    
    def optimize_tracking_position(self, sensor_data: Dict):
        """
        優化追日位置 - 實現流程圖中的優化邏輯
        """
        # 預測最佳角度
        predicted_angles = self.anfis_predict_optimal_angles(sensor_data)
        self.last_theoretical_angles = predicted_angles.copy()
        # 預測功率
        temp_data = sensor_data.copy()
        temp_data['current_angles'] = predicted_angles
        if self.anfis_model is not None:
            predicted_power = float(self.predict_expected_power(temp_data))
        else:
            predicted_power = float(self.calculate_expected_power_simulation(temp_data))

        # 評估是否值得移動
        is_worth_moving = self.evaluate_movement_worthiness(sensor_data, predicted_angles)

        moved = False
        move_time = ""
        moved_azimuth = ""
        moved_elevation = ""
        power_after_move = ""

        if is_worth_moving:
            moved = True
            self.move_to_predicted_angles(predicted_angles)
            move_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            moved_azimuth = predicted_angles['azimuth']
            moved_elevation = predicted_angles['elevation']
            new_sensor_data = self.read_sensor_data()
            power_after_move = new_sensor_data['current_power']
            self.record_prediction_accuracy(predicted_angles, new_sensor_data)
            self.check_and_correct_systematic_error()
        else:
            self.logger.info("移動價值不足，保持當前位置")

        # 動作紀錄寫入
        with open(r"d:\宇靖\研究\tracking_action_log.csv", "a", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=[
                "predict_time", "predicted_power", "predicted_azimuth", "predicted_elevation",
                "moved", "move_time", "moved_azimuth", "moved_elevation", "power_after_move"
            ])
            writer.writerow({
                "predict_time": sensor_data['timestamp'].strftime("%Y-%m-%d %H:%M:%S"),
                "predicted_power": predicted_power,
                "predicted_azimuth": predicted_angles['azimuth'],
                "predicted_elevation": predicted_angles['elevation'],
                "moved": moved,
                "move_time": move_time,
                "moved_azimuth": moved_azimuth,
                "moved_elevation": moved_elevation,
                "power_after_move": power_after_move
            })

        # 透過模糊規則微調
        self.fine_tune_with_fuzzy_rules(sensor_data)
    
    def anfis_predict_optimal_angles(self, sensor_data: Dict) -> Dict:
        """使用ANFIS預測最佳角度"""
        if self.anfis_model is None:
            # 模擬預測結果
            current_angles = sensor_data['current_angles']
            predicted_angles = {
                'azimuth': current_angles['azimuth'] + np.random.uniform(-5, 5),
                'elevation': current_angles['elevation'] + np.random.uniform(-3, 3)
            }
        else:
            # 實際ANFIS模型預測
            input_features = self.prepare_model_input(sensor_data)
            prediction = self.anfis_model.predict_angles(input_features)
            predicted_angles = {
                'azimuth': np.clip(prediction[0], *self.angle_ranges['azimuth']),
                'elevation': np.clip(prediction[1], *self.angle_ranges['elevation'])
            }
        
        self.logger.info(f"ANFIS預測最佳角度: 方位角 {predicted_angles['azimuth']:.1f}°, "
                        f"傾角 {predicted_angles['elevation']:.1f}°")
        
        return predicted_angles
    
    def evaluate_movement_worthiness(self, sensor_data: Dict, target_angles: Dict) -> bool:
        """評估是否值得移動"""
        current_angles = sensor_data['current_angles']
        
        # 計算角度變化
        angle_change = abs(target_angles['azimuth'] - current_angles['azimuth']) + \
                      abs(target_angles['elevation'] - current_angles['elevation'])
        
        # 估算移動後的功率增益
        if self.anfis_model is None:
            # 模擬功率增益計算
            estimated_gain = angle_change * 0.5  # 簡化計算
        else:
            # 使用模型預測移動後功率
            temp_data = sensor_data.copy()
            temp_data['current_angles'] = target_angles
            predicted_power = self.predict_expected_power(temp_data)
            estimated_gain = predicted_power - sensor_data['current_power']
        
        # 計算移動成本（能耗）
        movement_cost = angle_change * 0.1  # 假設每度移動消耗0.1W
        
        # 淨收益
        net_gain = estimated_gain - movement_cost
        
        is_worthwhile = net_gain > self.thresholds['movement_worthiness']
        
        self.logger.info(f"移動評估: 預估增益 {estimated_gain:.2f}W, 移動成本 {movement_cost:.2f}W, "
                        f"淨收益 {net_gain:.2f}W, 值得移動: {is_worthwhile}")
        
        return is_worthwhile
    
    def move_to_predicted_angles(self, target_angles: Dict):
        """移動到預測角度"""
        self.logger.info(f"執行移動: 從 ({self.current_data['angles']['azimuth']:.1f}°, "
                        f"{self.current_data['angles']['elevation']:.1f}°) "
                        f"到 ({target_angles['azimuth']:.1f}°, {target_angles['elevation']:.1f}°)")
        
        # 模擬移動過程（實際實現時調用硬體控制）
        self.current_data['angles'] = target_angles.copy()
        self.current_data['last_movement_time'] = datetime.now()
        
        # 實際硬體控制接口
        # self.hardware_controller.move_to_angles(target_angles)
    
    def record_prediction_accuracy(self, predicted_angles: Dict, actual_data: Dict):
        """記錄預測準確度"""
        if self.anfis_model is None:
            return
        
        # 預測移動後的功率
        temp_data = self.current_data['sensor_readings'].copy()
        temp_data['current_angles'] = predicted_angles
        predicted_power = self.predict_expected_power(temp_data)
        
        # 實際移動後的功率
        actual_power = actual_data['current_power']
        
        # 記錄誤差
        error_record = {
            'timestamp': datetime.now(),
            'predicted_power': predicted_power,
            'actual_power': actual_power,
            'error': actual_power - predicted_power,
            'relative_error': (actual_power - predicted_power) / predicted_power if predicted_power > 0 else 0,
            'predicted_angles': predicted_angles.copy(),
            'conditions': self.current_data['sensor_readings']['light_intensity'].copy()
        }
        
        self.experience_database['prediction_errors'].append(error_record)
        
        self.logger.info(f"記錄預測誤差: 預測 {predicted_power:.2f}W, 實際 {actual_power:.2f}W, "
                        f"誤差 {error_record['error']:.2f}W ({error_record['relative_error']:.1%})")
    
    def check_and_correct_systematic_error(self):
        """檢測系統性誤差並計算校正係數"""
        if len(self.experience_database['prediction_errors']) < 10:
            return
        
        # 分析最近的預測誤差
        recent_errors = self.experience_database['prediction_errors'][-20:]
        errors = [e['error'] for e in recent_errors]
        
        # 計算平均誤差
        mean_error = np.mean(errors)
        
        # 檢測是否存在系統性誤差
        if abs(mean_error) > self.thresholds['system_error_threshold']:
            # 計算校正係數
            old_coefficient = self.current_data['correction_coefficient']
            
            if mean_error > 0:  # 預測偏低
                self.current_data['correction_coefficient'] *= 1.05
            else:  # 預測偏高
                self.current_data['correction_coefficient'] *= 0.95
            
            # 限制校正係數範圍
            self.current_data['correction_coefficient'] = np.clip(
                self.current_data['correction_coefficient'], 0.7, 1.3
            )
            
            correction_record = {
                'timestamp': datetime.now(),
                'mean_error': mean_error,
                'old_coefficient': old_coefficient,
                'new_coefficient': self.current_data['correction_coefficient'],
                'sample_size': len(recent_errors)
            }
            
            self.experience_database['model_corrections'].append(correction_record)
            
            self.logger.info(f"檢測到系統性誤差 {mean_error:.2f}W, "
                           f"校正係數從 {old_coefficient:.3f} 調整為 {self.current_data['correction_coefficient']:.3f}")
    
    def fine_tune_with_fuzzy_rules(self, sensor_data: Dict):
        """透過模糊規則微調"""
        # 基於光感測器差異的微調邏輯
        light_data = sensor_data['light_intensity']
        
        # 計算東西光差和南北光差
        ew_diff = light_data['east'] - light_data['west']
        ns_diff = light_data['south'] - light_data['north']
        
        # 模糊規則微調
        azimuth_adjustment = 0
        elevation_adjustment = 0
        
        # 東西微調
        if abs(ew_diff) > 50:  # 閾值
            azimuth_adjustment = np.sign(ew_diff) * min(2, abs(ew_diff) / 200)
        
        # 南北微調
        if abs(ns_diff) > 50:  # 閾值
            elevation_adjustment = np.sign(ns_diff) * min(1, abs(ns_diff) / 300)
        
        if abs(azimuth_adjustment) > 0.5 or abs(elevation_adjustment) > 0.5:
            # 執行微調
            old_angles = self.current_data['angles'].copy()
            
            self.current_data['angles']['azimuth'] += azimuth_adjustment
            self.current_data['angles']['elevation'] += elevation_adjustment

            self.last_fine_tune = {
            "azimuth_adjustment": azimuth_adjustment,
            "elevation_adjustment": elevation_adjustment,
            "result_angles": self.current_data['angles'].copy()
            }
            # 限制角度範圍
            self.current_data['angles']['azimuth'] = np.clip(
                self.current_data['angles']['azimuth'], *self.angle_ranges['azimuth']
            )
            self.current_data['angles']['elevation'] = np.clip(
                self.current_data['angles']['elevation'], *self.angle_ranges['elevation']
            )
            
            self.logger.info(f"模糊規則微調: 方位角 {azimuth_adjustment:+.1f}°, "
                           f"傾角 {elevation_adjustment:+.1f}°")
            
            # 檢查微調效果
            self.check_fine_tune_improvement(old_angles, sensor_data)
        else:
            self.last_fine_tune = None
            
    
    def check_fine_tune_improvement(self, old_angles: Dict, sensor_data: Dict):
        """檢查微調前後是否改善發電"""
        # 等待一段時間讓系統穩定
        import time
        time.sleep(30)  # 實際應用中可能需要調整
        
        # 讀取微調後的功率
        new_sensor_data = self.read_sensor_data()
        
        power_improvement = new_sensor_data['current_power'] - sensor_data['current_power']
        
        if power_improvement > self.thresholds['fine_tune_improvement']:
            # 微調有效，記錄成功經驗
            self.record_successful_fine_tune(old_angles, power_improvement)
        else:
            # 微調無效，記錄錯誤經驗並回退
            self.record_failed_fine_tune(old_angles, power_improvement)
            self.current_data['angles'] = old_angles.copy()
    
    def record_successful_fine_tune(self, old_angles: Dict, improvement: float):
        """記錄成功的微調經驗"""
        success_record = {
            'timestamp': datetime.now(),
            'action': 'fine_tune_success',
            'old_angles': old_angles.copy(),
            'new_angles': self.current_data['angles'].copy(),
            'power_improvement': improvement,
            'conditions': self.current_data['sensor_readings']['light_intensity'].copy()
        }
        
        self.experience_database['successful_experiences'].append(success_record)
        self.logger.info(f"微調成功: 功率提升 {improvement:.2f}W")
    
    def record_failed_fine_tune(self, old_angles: Dict, change: float):
        """記錄失敗的微調經驗"""
        failure_record = {
            'timestamp': datetime.now(),
            'action': 'fine_tune_failed',
            'old_angles': old_angles.copy(),
            'attempted_angles': self.current_data['angles'].copy(),
            'power_change': change,
            'conditions': self.current_data['sensor_readings']['light_intensity'].copy()
        }
        
        self.experience_database['failed_experiences'].append(failure_record)
        self.logger.info(f"微調失敗: 功率變化 {change:.2f}W，回退到原位置")
    
    def return_to_east_position(self):
        """回歸至東方初始位置"""
        east_position = {
            'azimuth': self.timing['east_initial_azimuth'],
            'elevation': self.timing['east_initial_elevation']
        }
        
        if (self.current_data['angles']['azimuth'] != east_position['azimuth'] or
            self.current_data['angles']['elevation'] != east_position['elevation']):
            
            self.logger.info("太陽時間結束，回歸東方初始位置")
            self.current_data['angles'] = east_position.copy()
            
            # 實際硬體控制
            # self.hardware_controller.move_to_angles(east_position)
    
    def wait_for_next_cycle(self):
        """等待下一個循環"""
        import time
        #time.sleep(self.timing['wait_interval'])
    
    def prepare_model_input(self, sensor_data: Dict) -> np.ndarray:
        """準備模型輸入特徵"""
        current_time = datetime.now()
        
        features = [
            current_time.hour,
            current_time.minute,
            current_time.day,
            sensor_data['light_intensity']['east'],
            sensor_data['light_intensity']['west'],
            sensor_data['light_intensity']['south'],
            sensor_data['light_intensity']['north'],
            sensor_data['light_intensity']['absolute_total'],
            sensor_data['current_angles']['azimuth'],
            sensor_data['current_angles']['elevation'],
            sensor_data['current_power'],
            sensor_data['environmental']['temperature'],
            sensor_data['environmental']['humidity']
        ]
        
        return np.array(features).reshape(1, -1)
    
    def calculate_angle_efficiency(self, angles: Dict) -> float:
        """計算角度效率（簡化模型）"""
        # 簡化的角度效率計算
        optimal_azimuth = 180  # 正南
        optimal_elevation = 20  # 假設最佳傾角
        
        azimuth_loss = abs(angles['azimuth'] - optimal_azimuth) / 180
        elevation_loss = abs(angles['elevation'] - optimal_elevation) / 90
        
        efficiency = 1.0 - (azimuth_loss * 0.3 + elevation_loss * 0.2)
        return max(0.1, efficiency)  # 最小效率10%
    
    def handle_system_error(self, error: Exception):
        """處理系統錯誤"""
        self.logger.error(f"系統錯誤: {error}")
        
        # 錯誤恢復邏輯
        try:
            # 嘗試回到安全位置
            safe_position = {'azimuth': 180, 'elevation': 15}
            self.current_data['angles'] = safe_position
            
            # 短暫等待後重新開始
            import time
            time.sleep(60)
            
        except Exception as recovery_error:
            self.logger.critical(f"錯誤恢復失敗: {recovery_error}")
            raise
    
    def get_system_status(self) -> Dict:
        """獲取系統狀態"""
        # 取得最新感測資料
        sensor_data = self.current_data['sensor_readings']
        # 預設預測功率為空
        predicted_power = ""
        # 若有理論角度，計算預測功率
        if self.last_theoretical_angles:
            temp_data = sensor_data.copy()
            temp_data['current_angles'] = self.last_theoretical_angles
            if self.anfis_model is not None:
                predicted_power = float(self.predict_expected_power(temp_data))
            else:
                predicted_power = float(self.calculate_expected_power_simulation(temp_data))
        return {
            'timestamp': sensor_data.get('timestamp', datetime.now()),
            'system_state': self.system_state.value,
            'current_angles': self.current_data['angles'].copy(),
            'theoretical_angles': self.last_theoretical_angles.copy() if self.last_theoretical_angles else None,
            'predicted_power': predicted_power,
            'fine_tune': self.last_fine_tune.copy() if self.last_fine_tune else None,
            'current_power': self.current_data['power'],
            'correction_coefficient': self.current_data['correction_coefficient'],
            'experience_counts': {
                'successful': len(self.experience_database['successful_experiences']),
                'failed': len(self.experience_database['failed_experiences']),
                'prediction_errors': len(self.experience_database['prediction_errors']),
                'corrections': len(self.experience_database['model_corrections'])
            },
            'last_movement': self.current_data['last_movement_time']
        }

# 使用範例
def main():
    """主程序"""
    # 初始化控制器
    controller = SolarTrackingController()
    
    # 啟動控制循環
    try:
        controller.main_control_loop()
    except KeyboardInterrupt:
        print("\n系統停止")
    except Exception as e:
        print(f"系統錯誤: {e}")

if __name__ == "__main__":
    main()