#!/usr/bin/env python3
# dual_actuator_with_upload.py
"""
雙軸太陽能追日系統 - 網站數據上傳整合版本
- 雙通道電源監控（24V推桿 + 24V樹莓派）
- 即時上傳數據到 Django 後端
- 完整的位置、電力、推桿數據記錄
"""
import RPi.GPIO as GPIO
import time
import sys
import tty
import termios
import select
from datetime import datetime
import csv
import threading
import requests
import json
from SDL_Pi_INA3221 import INA3221

# ==================== 網站配置 ====================
# 請修改為你的實際 IP 和端口
API_BASE_URL = "http://140.114.59.214:8000/api"
SYSTEM_ID = 1  # 請修改為你系統的 ID（從 Django admin 查看）

# 數據上傳設定
UPLOAD_INTERVAL = 5.0  # 每秒上傳一次（可調整）
UPLOAD_ENABLED = True  # 是否啟用上傳功能

# ==================== GPIO定義 ====================
# 推桿1（方位角 Azimuth）- 206mm行程
AZ_BROWN_HIGH = 17
AZ_BLUE_HIGH = 27
AZ_BROWN_LOW = 22
AZ_BLUE_LOW = 23
AZ_HALL1 = 24
AZ_HALL2 = 25

# 推桿2（傾角 Tilt）- 406mm行程
TILT_BROWN_HIGH = 5
TILT_BLUE_HIGH = 6
TILT_BROWN_LOW = 13
TILT_BLUE_LOW = 19
TILT_HALL1 = 16
TILT_HALL2 = 26

# ==================== 硬件設定 ====================
# INA3221設定
INA3221_ADDRESS = 0x40
SHUNT_RESISTOR = 0.1  # 0.1Ω 分流電阻

# 推桿參數
AZ_PULSES_PER_MM = 54.19
AZ_STROKE_MM = 206
TILT_PULSES_PER_MM = 54.19
TILT_STROKE_MM = 406

# ==================== 優化參數 ====================
AUTO_STOP_TIMEOUT = 0.5
POLL_INTERVAL = 0.01
DEBUG_MODE = False


class ActuatorController:
    """單一推桿控制器"""
    
    def __init__(self, name, brown_high, blue_high, brown_low, blue_low):
        self.name = name
        self.brown_high = brown_high
        self.blue_high = blue_high
        self.brown_low = brown_low
        self.blue_low = blue_low
        self.current_state = None
        
        GPIO.setup([brown_high, blue_high, brown_low, blue_low], GPIO.OUT)
        self.stop()
        print(f"  ✓ {name} 推桿控制器初始化")
    
    def extend(self):
        if self.current_state == 'extend':
            return
        GPIO.output([self.brown_high, self.blue_low], GPIO.LOW)
        time.sleep(0.01)
        GPIO.output([self.blue_high, self.brown_low], GPIO.HIGH)
        self.current_state = 'extend'
    
    def retract(self):
        if self.current_state == 'retract':
            return
        GPIO.output([self.blue_high, self.brown_low], GPIO.LOW)
        time.sleep(0.01)
        GPIO.output([self.brown_high, self.blue_low], GPIO.HIGH)
        self.current_state = 'retract'
    
    def stop(self):
        if self.current_state is None:
            return
        GPIO.output([self.brown_high, self.blue_high, 
                    self.brown_low, self.blue_low], GPIO.LOW)
        self.current_state = None


class HallSensorMonitor:
    """霍爾感測器監控器"""
    
    def __init__(self, name, hall1_pin, hall2_pin, pulses_per_mm, stroke_mm):
        self.name = name
        self.hall1_pin = hall1_pin
        self.hall2_pin = hall2_pin
        self.pulses_per_mm = pulses_per_mm
        self.stroke_mm = stroke_mm
        
        self.pulse_count = 0
        self.position_mm = 0.0
        self.monitoring = True
        
        GPIO.setup([hall1_pin, hall2_pin], GPIO.IN, pull_up_down=GPIO.PUD_UP)
        self.last_hall1 = GPIO.input(hall1_pin)
        
        self.monitor_thread = threading.Thread(target=self._hall_monitor)
        self.monitor_thread.daemon = True
        self.monitor_thread.start()
        
        print(f"  ✓ {name} 霍爾感測器監控啟動")
    
    def _hall_monitor(self):
        while self.monitoring:
            hall1 = GPIO.input(self.hall1_pin)
            hall2 = GPIO.input(self.hall2_pin)
            
            if hall1 != self.last_hall1:
                if hall1 == hall2:
                    self.pulse_count -= 1
                else:
                    self.pulse_count += 1
                
                self.position_mm = self.pulse_count / self.pulses_per_mm
                self.last_hall1 = hall1
            
            time.sleep(0.0001)
    
    def get_position(self):
        return self.position_mm
    
    def get_pulse_count(self):
        return self.pulse_count
    
    def get_position_percentage(self):
        return (self.position_mm / self.stroke_mm) * 100.0
    
    def reset_position(self):
        self.pulse_count = 0
        self.position_mm = 0.0
    
    def stop(self):
        self.monitoring = False


class DualPowerMonitor:
    """INA3221雙通道電源監控器"""
    
    def __init__(self, address=0x40, shunt_resistor=0.1):
        self.ina = None
        self.ch1_enabled = False
        self.ch2_enabled = False
        
        print(f"\n正在初始化 INA3221 雙通道監控...")
        
        try:
            self.ina = INA3221(bus_num=1, addr=address, shunt_resistor=shunt_resistor)
            
            # 測試CH1（24V推桿系統）
            print(f"\n  【CH1 - 24V推桿系統】")
            try:
                ch1_voltage = self.ina.bus_voltage(1)
                ch1_current = self.ina.current(1)
                ch1_power = self.ina.power(1) / 1000.0
                
                print(f"    電壓: {ch1_voltage:.2f}V")
                print(f"    電流: {ch1_current:.1f}mA")
                print(f"    功率: {ch1_power:.2f}W")
                
                if ch1_voltage > 5.0:  # 確保有實際電壓
                    print(f"    ✓ CH1 監控正常")
                    self.ch1_enabled = True
                else:
                    print(f"    ⚠️ 警告: 電壓偏低")
                
            except Exception as e:
                print(f"    ✗ CH1 讀取失敗: {e}")
            
            # 測試CH2（24V樹莓派供電）
            print(f"\n  【CH2 - 24V樹莓派供電】")
            try:
                ch2_voltage = self.ina.bus_voltage(2)
                ch2_current = self.ina.current(2)
                ch2_power = self.ina.power(2) / 1000.0
                
                print(f"    電壓: {ch2_voltage:.2f}V")
                print(f"    電流: {ch2_current:.1f}mA")
                print(f"    功率: {ch2_power:.2f}W")
                
                if ch2_voltage > 5.0:
                    print(f"    ✓ CH2 監控正常")
                    self.ch2_enabled = True
                else:
                    print(f"    ⚠️ 警告: 電壓偏低")
                
            except Exception as e:
                print(f"    ✗ CH2 讀取失敗: {e}")
            
        except Exception as e:
            print(f"  ✗ INA3221 初始化失敗: {e}")
    
    def read_ch1(self):
        """讀取CH1 (24V推桿系統)"""
        if not self.ch1_enabled or not self.ina:
            return None, None, None
        
        try:
            voltage = self.ina.bus_voltage(1)
            current = self.ina.current(1)
            power = self.ina.power(1) / 1000.0
            return voltage, current, power
        except:
            return None, None, None
    
    def read_ch2(self):
        """讀取CH2 (24V樹莓派供電)"""
        if not self.ch2_enabled or not self.ina:
            return None, None, None
        
        try:
            voltage = self.ina.bus_voltage(2)
            current = self.ina.current(2)
            power = self.ina.power(2) / 1000.0
            return voltage, current, power
        except:
            return None, None, None
    
    def read_all(self):
        ch1_data = self.read_ch1()
        ch2_data = self.read_ch2()
        return ch1_data, ch2_data
    
    def close(self):
        if self.ina:
            self.ina.close()


class WebUploader:
    """網站數據上傳器"""
    
    def __init__(self, base_url, system_id):
        self.base_url = base_url
        self.system_id = system_id
        self.upload_url = f"{base_url}/realtime-data/"
        self.success_count = 0
        self.fail_count = 0
        self.last_upload_time = time.time()
        
        print(f"\n【網站數據上傳器初始化】")
        print(f"  API URL: {self.upload_url}")
        print(f"  系統 ID: {self.system_id}")
        
        # 測試連接
        if self.test_connection():
            print(f"  ✓ 網站連接正常")
        else:
            print(f"  ⚠️ 無法連接到網站，數據將僅本地保存")
    
    def test_connection(self):
        """測試網站連接"""
        try:
            response = requests.get(f"{self.base_url}/systems/", timeout=3)
            return response.status_code == 200
        except:
            return False
    
    def upload_data(self, data_dict):
        """上傳數據到網站
        
        data_dict 應包含:
        - voltage: 太陽能板電壓
        - current: 太陽能板電流
        - power_output: 太陽能板功率
        - panel_azimuth: 方位角
        - panel_tilt: 傾角
        - actuator_voltage: 推桿電壓
        - actuator_current: 推桿電流
        - actuator_power: 推桿功率
        - actuator_extension_az: 方位角推桿伸展長度
        - actuator_extension_tilt: 傾角推桿伸展長度
        """
        if not UPLOAD_ENABLED:
            return False, "上傳功能已停用"
        
        # 準備上傳的數據（包含所有新欄位）
        payload = {
            "system_id": self.system_id,
            # 太陽能板數據
            "voltage": data_dict.get("voltage", 0.0),
            "current": data_dict.get("current", 0.0),
            "power_output": data_dict.get("power_output", 0.0),
            "panel_azimuth": data_dict.get("panel_azimuth"),
            "panel_tilt": data_dict.get("panel_tilt"),
            
            # 樹莓派電源（CH2數據）
            "raspberry_pi_voltage": data_dict.get("raspberry_pi_voltage"),
            "raspberry_pi_current": data_dict.get("raspberry_pi_current"),
            "raspberry_pi_power": data_dict.get("raspberry_pi_power"),
            
            # 南北推桿（傾角）
            "ns_actuator_angle": data_dict.get("ns_actuator_angle"),
            "ns_actuator_extension": data_dict.get("actuator_extension_tilt"),
            
            # 東西推桿（方位角）
            "ew_actuator_angle": data_dict.get("ew_actuator_angle"),
            "ew_actuator_extension": data_dict.get("actuator_extension_az"),
            
            # 推桿總功率（CH1數據）
            "actuator_total_voltage": data_dict.get("actuator_voltage"),
            "actuator_total_current": data_dict.get("actuator_current"),
            "actuator_total_power": data_dict.get("actuator_power"),
            
            # 備註
            "notes": f"Az:{data_dict.get('actuator_extension_az',0):.1f}mm, Tilt:{data_dict.get('actuator_extension_tilt',0):.1f}mm"
        }
        
        try:
            response = requests.post(
                self.upload_url, 
                json=payload,
                headers={"Content-Type": "application/json"},
                timeout=2
            )
            
            if response.status_code in [200, 201]:
                self.success_count += 1
                self.last_upload_time = time.time()
                return True, "上傳成功"
            else:
                self.fail_count += 1
                return False, f"HTTP {response.status_code}: {response.text[:100]}"
                
        except requests.exceptions.Timeout:
            self.fail_count += 1
            return False, "上傳超時"
        except Exception as e:
            self.fail_count += 1
            return False, f"上傳錯誤: {str(e)}"
    
    def get_stats(self):
        """獲取上傳統計"""
        return {
            "success": self.success_count,
            "failed": self.fail_count,
            "last_upload": self.last_upload_time
        }


class DataLogger:
    """數據記錄器（CSV + 網站上傳）"""
    
    def __init__(self, filename=None, uploader=None):
        if filename is None:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"dual_power_log_{timestamp}.csv"
        
        self.filename = filename
        self.file = None
        self.writer = None
        self.uploader = uploader
        self.init_file()
    
    def init_file(self):
        self.file = open(self.filename, 'w', newline='')
        self.writer = csv.writer(self.file)
        
        # CSV標頭
        self.writer.writerow([
            'Timestamp',
            'AZ_Action', 'AZ_Position_mm', 'AZ_Position_%', 'AZ_Pulse',
            'TILT_Action', 'TILT_Position_mm', 'TILT_Position_%', 'TILT_Pulse',
            'CH1_Actuator_Voltage_V', 'CH1_Actuator_Current_mA', 'CH1_Actuator_Power_W',
            'CH2_Pi_Voltage_V', 'CH2_Pi_Current_mA', 'CH2_Pi_Power_W',
            'Total_Power_W',
            'Upload_Status'
        ])
        self.file.flush()
        print(f"  ✓ 數據記錄文件: {self.filename}")
    
    def log(self, az_data, tilt_data, ch1_data, ch2_data, panel_voltage=0, panel_current=0):
        """記錄數據並上傳到網站"""
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
        
        # 計算總功率
        ch1_power = float(ch1_data[2]) if ch1_data[2] != "N/A" else 0
        ch2_power = float(ch2_data[2]) if ch2_data[2] != "N/A" else 0
        total_power = ch1_power + ch2_power
        
        # 寫入 CSV
        row = [timestamp]
        row.extend(az_data)
        row.extend(tilt_data)
        row.extend(ch1_data)
        row.extend(ch2_data)
        row.append(f"{total_power:.3f}")
        
        # 準備上傳數據
        upload_status = "N/A"
        if self.uploader:
            data_dict = {
                "voltage": panel_voltage,
                "current": panel_current,
                "power_output": panel_voltage * panel_current,
                "panel_azimuth": float(az_data[1]),  # 方位角位置(mm)
                "panel_tilt": float(tilt_data[1]),  # 傾角位置(mm)
                
                # 推桿總功率（CH1數據）
                "actuator_voltage": ch1_data[0] if ch1_data[0] != "N/A" else None,
                "actuator_current": ch1_data[1] if ch1_data[1] != "N/A" else None,
                "actuator_power": ch1_data[2] if ch1_data[2] != "N/A" else None,
                
                # 樹莓派電源（CH2數據）
                "raspberry_pi_voltage": ch2_data[0] if ch2_data[0] != "N/A" else None,
                "raspberry_pi_current": ch2_data[1] if ch2_data[1] != "N/A" else None,
                "raspberry_pi_power": ch2_data[2] if ch2_data[2] != "N/A" else None,
                
                # 推桿角度（位置轉換為角度，請根據實際機構調整轉換公式）
                # 假設: 0mm = 0度, 最大行程 = 90度
                "ns_actuator_angle": (float(tilt_data[1]) / TILT_STROKE_MM) * 90.0,  # 南北=傾角
                "ew_actuator_angle": (float(az_data[1]) / AZ_STROKE_MM) * 180.0,     # 東西=方位
                
                # 推桿伸展長度
                "actuator_extension_az": float(az_data[1]),
                "actuator_extension_tilt": float(tilt_data[1])
            }
            
            success, message = self.uploader.upload_data(data_dict)
            upload_status = "OK" if success else "FAIL"
        
        row.append(upload_status)
        self.writer.writerow(row)
        self.file.flush()
    
    def close(self):
        if self.file:
            self.file.close()
        
        # 顯示上傳統計
        if self.uploader:
            stats = self.uploader.get_stats()
            print(f"\n【上傳統計】")
            print(f"  成功: {stats['success']} 次")
            print(f"  失敗: {stats['failed']} 次")


def get_key():
    """非阻塞讀取按鍵"""
    if select.select([sys.stdin], [], [], 0)[0]:
        return sys.stdin.read(1)
    return None


# ========== 主程式 ==========
az_actuator = None
tilt_actuator = None
az_hall = None
tilt_hall = None
power_monitor = None
uploader = None
logger = None

try:
    GPIO.setmode(GPIO.BCM)
    GPIO.setwarnings(False)
    
    old_settings = termios.tcgetattr(sys.stdin)
    tty.setcbreak(sys.stdin.fileno())
    
    print("=" * 90)
    print("     雙軸太陽能追日系統 - 網站數據上傳整合版本")
    print("=" * 90)
    
    # 初始化推桿控制器
    print("\n【初始化推桿控制器】")
    az_actuator = ActuatorController(
        "方位角(Azimuth)",
        AZ_BROWN_HIGH, AZ_BLUE_HIGH, AZ_BROWN_LOW, AZ_BLUE_LOW
    )
    tilt_actuator = ActuatorController(
        "傾角(Tilt)",
        TILT_BROWN_HIGH, TILT_BLUE_HIGH, TILT_BROWN_LOW, TILT_BLUE_LOW
    )
    
    # 初始化霍爾感測器
    print("\n【初始化霍爾感測器】")
    az_hall = HallSensorMonitor(
        "方位角(Azimuth)", 
        AZ_HALL1, AZ_HALL2,
        AZ_PULSES_PER_MM,
        AZ_STROKE_MM
    )
    tilt_hall = HallSensorMonitor(
        "傾角(Tilt)", 
        TILT_HALL1, TILT_HALL2,
        TILT_PULSES_PER_MM,
        TILT_STROKE_MM
    )
    
    # 初始化雙通道電源監控
    power_monitor = DualPowerMonitor(
        address=INA3221_ADDRESS,
        shunt_resistor=SHUNT_RESISTOR
    )
    
    # 初始化網站上傳器
    uploader = WebUploader(API_BASE_URL, SYSTEM_ID)
    
    # 初始化數據記錄
    print("\n【初始化數據記錄】")
    logger = DataLogger(uploader=uploader)
    
    print("\n" + "=" * 90)
    print("【操作說明】")
    print("=" * 90)
    print("\n組合動作（數字鍵）:")
    print("  1  - 左上 (A+W)  │  2  - 上 (W)      │  3  - 右上 (D+W)")
    print("  4  - 左 (A)      │  5  - 全停        │  6  - 右 (D)")
    print("  7  - 左下 (A+S)  │  8  - 下 (S)      │  9  - 右下 (D+S)")
    print("\n方位角: A/D - 左/右  │  F - 停止  │  Z - 歸零")
    print("傾角:   W/S - 上/下  │  X - 停止  │  C - 歸零")
    print("系統:   E - 緊急停止 │  Q - 退出  │  U - 切換上傳")
    print("\n⚡ 系統參數:")
    print(f"   - 數據上傳: {'啟用' if UPLOAD_ENABLED else '停用'}")
    print(f"   - 上傳間隔: {UPLOAD_INTERVAL}秒")
    print(f"   - API URL: {API_BASE_URL}")
    print(f"   - 系統 ID: {SYSTEM_ID}")
    print("=" * 90)
    print("\n系統就緒，等待指令...\n")
    
    # 狀態變數
    az_action = None
    tilt_action = None
    last_key_time = time.time()
    last_log_time = time.time()
    last_upload_time = time.time()
    log_interval = 0.1
    
    while True:
        key = get_key()
        
        if key:
            last_key_time = time.time()
            key = key.lower()
            
            # 數字鍵組合動作
            if key == '1':  # 左上
                az_actuator.retract()
                az_action = 'left'
                tilt_actuator.extend()
                tilt_action = 'up'
            elif key == '2':  # 上
                tilt_actuator.extend()
                tilt_action = 'up'
            elif key == '3':  # 右上
                az_actuator.extend()
                az_action = 'right'
                tilt_actuator.extend()
                tilt_action = 'up'
            elif key == '4':  # 左
                az_actuator.retract()
                az_action = 'left'
            elif key == '5':  # 全停
                az_actuator.stop()
                tilt_actuator.stop()
                az_action = None
                tilt_action = None
            elif key == '6':  # 右
                az_actuator.extend()
                az_action = 'right'
            elif key == '7':  # 左下
                az_actuator.retract()
                az_action = 'left'
                tilt_actuator.retract()
                tilt_action = 'down'
            elif key == '8':  # 下
                tilt_actuator.retract()
                tilt_action = 'down'
            elif key == '9':  # 右下
                az_actuator.extend()
                az_action = 'right'
                tilt_actuator.retract()
                tilt_action = 'down'
            
            # 方位角控制
            elif key == 'a':
                az_actuator.retract()
                az_action = 'left'
            elif key == 'd':
                az_actuator.extend()
                az_action = 'right'
            elif key == 'f':
                az_actuator.stop()
                az_action = None
            elif key == 'z':
                az_hall.reset_position()
                print("\n✓ 方位角位置已重置為 0mm           ")
            
            # 傾角控制
            elif key == 'w':
                tilt_actuator.extend()
                tilt_action = 'up'
            elif key == 's':
                tilt_actuator.retract()
                tilt_action = 'down'
            elif key == 'x':
                tilt_actuator.stop()
                tilt_action = None
            elif key == 'c':
                tilt_hall.reset_position()
                print("\n✓ 傾角位置已重置為 0mm           ")
            
            # 系統控制
            elif key == 'e':
                az_actuator.stop()
                tilt_actuator.stop()
                az_action = None
                tilt_action = None
                print("\n⚠️ 緊急停止！           ")
            
            elif key == 'u':
                UPLOAD_ENABLED = not UPLOAD_ENABLED
                status = "啟用" if UPLOAD_ENABLED else "停用"
                print(f"\n📡 數據上傳已{status}           ")
            
            elif key == 'q':
                print("\n✓ 退出程式")
                break
        
        # 自動停止
        if (az_action or tilt_action) and (time.time() - last_key_time > AUTO_STOP_TIMEOUT):
            if az_action:
                az_actuator.stop()
                az_action = None
            if tilt_action:
                tilt_actuator.stop()
                tilt_action = None
        
        # 定期記錄和顯示數據
        if time.time() - last_log_time >= log_interval:
            # 讀取兩個通道
            ch1_data = power_monitor.read_ch1()  # 24V推桿
            ch2_data = power_monitor.read_ch2()  # 24V樹莓派
            
            # 位置數據
            az_pos = az_hall.get_position()
            az_pct = az_hall.get_position_percentage()
            az_pulse = az_hall.get_pulse_count()
            
            tilt_pos = tilt_hall.get_position()
            tilt_pct = tilt_hall.get_position_percentage()
            tilt_pulse = tilt_hall.get_pulse_count()
            
            az_action_str = az_action if az_action else "STOP"
            tilt_action_str = tilt_action if tilt_action else "STOP"
            
            az_data = [az_action_str, f"{az_pos:.2f}", f"{az_pct:.1f}", az_pulse]
            tilt_data = [tilt_action_str, f"{tilt_pos:.2f}", f"{tilt_pct:.1f}", tilt_pulse]
            
            # 格式化電源數據
            ch1_formatted = [
                f"{ch1_data[0]:.3f}" if ch1_data[0] is not None else "N/A",
                f"{ch1_data[1]:.2f}" if ch1_data[1] is not None else "N/A",
                f"{ch1_data[2]:.3f}" if ch1_data[2] is not None else "N/A"
            ]
            ch2_formatted = [
                f"{ch2_data[0]:.3f}" if ch2_data[0] is not None else "N/A",
                f"{ch2_data[1]:.2f}" if ch2_data[1] is not None else "N/A",
                f"{ch2_data[2]:.3f}" if ch2_data[2] is not None else "N/A"
            ]
            
            # 記錄到CSV和上傳
            # TODO: 這裡應該讀取實際的太陽能板電壓電流，目前使用假數據
            panel_voltage = 0.1
            panel_current = 0.1
            
            logger.log(az_data, tilt_data, ch1_formatted, ch2_formatted, 
                      panel_voltage, panel_current)
            
            # 即時顯示
            az_symbol = "←" if az_action == 'left' else "→" if az_action == 'right' else "■"
            tilt_symbol = "↑" if tilt_action == 'up' else "↓" if tilt_action == 'down' else "■"
            
            # 顯示上傳狀態
            upload_indicator = "📡" if UPLOAD_ENABLED else "⊗"
            stats = uploader.get_stats()
            
            if ch1_data[0] is not None and ch2_data[0] is not None:
                print(f"{upload_indicator} {az_symbol}Az:{az_pos:5.1f}mm({az_pct:4.1f}%) | "
                      f"{tilt_symbol}Tilt:{tilt_pos:5.1f}mm({tilt_pct:4.1f}%) | "
                      f"推桿:{ch1_data[0]:5.1f}V {ch1_data[1]:5.0f}mA {ch1_data[2]:5.1f}W | "
                      f"Upload:{stats['success']}/{stats['success']+stats['failed']}",
                      end='\r', flush=True)
            
            last_log_time = time.time()
        
        time.sleep(POLL_INTERVAL)

except KeyboardInterrupt:
    print("\n\n⚠️ 程序中斷")
    
except Exception as e:
    print(f"\n⚠️ 錯誤: {e}")
    import traceback
    traceback.print_exc()
    
finally:
    if az_actuator:
        az_actuator.stop()
    if tilt_actuator:
        tilt_actuator.stop()
    
    termios.tcsetattr(sys.stdin, termios.TCSADRAIN, old_settings)
    if az_hall:
        az_hall.stop()
    if tilt_hall:
        tilt_hall.stop()
    if power_monitor:
        power_monitor.close()
    if logger:
        logger.close()
    
    GPIO.cleanup()
    print("\n✓ GPIO已清理")
    if logger:
        print(f"✓ 數據已保存至: {logger.filename}\n")
