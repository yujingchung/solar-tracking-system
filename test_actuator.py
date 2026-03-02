#!/usr/bin/env python3
# dual_actuator_control_dual_power.py
"""
雙軸太陽能追日系統 - 雙通道電源監控版本
- 改善按鍵響應（0.5秒自動停止）
- CH1: 24V推桿系統總功率
- CH2: 24V樹莓派供電（含DC-DC轉5V損耗）
- 完整數據記錄
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
from SDL_Pi_INA3221 import INA3221

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

# INA3221設定（雙通道電源監控）
INA3221_ADDRESS = 0x40
SHUNT_RESISTOR = 0.1  # 0.1Ω 分流電阻

# 推桿參數
AZ_PULSES_PER_MM = 54.19
AZ_STROKE_MM = 206
TILT_PULSES_PER_MM = 54.19
TILT_STROKE_MM = 406

# ==================== 優化參數 ====================

# 按鍵響應優化
AUTO_STOP_TIMEOUT = 0.5  # 自動停止時間（秒）
POLL_INTERVAL = 0.01     # 輪詢間隔（秒）
DEBUG_MODE = False       # 除錯模式：顯示按鍵事件


class ActuatorController:
    """單一推桿控制器（改善版）"""
    
    def __init__(self, name, brown_high, blue_high, brown_low, blue_low):
        self.name = name
        self.brown_high = brown_high
        self.blue_high = blue_high
        self.brown_low = brown_low
        self.blue_low = blue_low
        
        self.current_state = None  # 當前狀態：None, 'extend', 'retract'
        
        # 設定GPIO
        GPIO.setup([brown_high, blue_high, brown_low, blue_low], GPIO.OUT)
        self.stop()
        
        print(f"  ✓ {name} 推桿控制器初始化")
    
    def extend(self):
        """伸展（避免重複切換）"""
        if self.current_state == 'extend':
            return  # 已經在伸展，不重複操作
        
        GPIO.output([self.brown_high, self.blue_low], GPIO.LOW)
        time.sleep(0.01)
        GPIO.output([self.blue_high, self.brown_low], GPIO.HIGH)
        self.current_state = 'extend'
    
    def retract(self):
        """收縮（避免重複切換）"""
        if self.current_state == 'retract':
            return  # 已經在收縮，不重複操作
        
        GPIO.output([self.blue_high, self.brown_low], GPIO.LOW)
        time.sleep(0.01)
        GPIO.output([self.brown_high, self.blue_low], GPIO.HIGH)
        self.current_state = 'retract'
    
    def stop(self):
        """停止（避免重複切換）"""
        if self.current_state is None:
            return  # 已經停止，不重複操作
        
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
        
        # 設定GPIO
        GPIO.setup([hall1_pin, hall2_pin], GPIO.IN, pull_up_down=GPIO.PUD_UP)
        
        # 讀取初始狀態
        self.last_hall1 = GPIO.input(hall1_pin)
        
        # 啟動監控線程
        self.monitor_thread = threading.Thread(target=self._hall_monitor)
        self.monitor_thread.daemon = True
        self.monitor_thread.start()
        
        print(f"  ✓ {name} 霍爾感測器監控啟動")
        print(f"    - 行程: {stroke_mm}mm")
        print(f"    - 校準值: {pulses_per_mm:.2f} pulse/mm")
    
    def _hall_monitor(self):
        """霍爾感測器監控線程"""
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
    """INA3221雙通道電源監控器
    
    CH1: 24V推桿系統總功率
    CH2: 24V樹莓派供電功率（經DC-DC轉5V）
    """
    
    def __init__(self, address=0x40, shunt_resistor=0.1):
        self.ina = None
        self.ch1_enabled = False
        self.ch2_enabled = False
        
        print(f"\n正在初始化 INA3221 雙通道監控...")
        print(f"  I2C 地址: 0x{address:02X}")
        print(f"  分流電阻: {shunt_resistor}Ω")
        
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
                
                if ch1_voltage < 20.0:
                    print(f"    ⚠️ 警告: 電壓偏低 ({ch1_voltage:.2f}V)")
                else:
                    print(f"    ✓ CH1 監控正常")
                
                self.ch1_enabled = True
                
            except Exception as e:
                print(f"    ✗ CH1 讀取失敗: {e}")
                self.ch1_enabled = False
            
            # 測試CH2（24V樹莓派供電）
            print(f"\n  【CH2 - 24V樹莓派供電】")
            try:
                ch2_voltage = self.ina.bus_voltage(2)
                ch2_current = self.ina.current(2)
                ch2_power = self.ina.power(2) / 1000.0
                
                print(f"    電壓: {ch2_voltage:.2f}V")
                print(f"    電流: {ch2_current:.1f}mA")
                print(f"    功率: {ch2_power:.2f}W (含DC-DC轉換損耗)")
                
                if ch2_voltage < 20.0:
                    print(f"    ⚠️ 警告: 電壓偏低 ({ch2_voltage:.2f}V)")
                else:
                    print(f"    ✓ CH2 監控正常")
                
                self.ch2_enabled = True
                
            except Exception as e:
                print(f"    ✗ CH2 讀取失敗: {e}")
                self.ch2_enabled = False
            
            # 總結
            print(f"\n  監控狀態:")
            print(f"    CH1 (24V推桿): {'✓ 啟用' if self.ch1_enabled else '✗ 停用'}")
            print(f"    CH2 (24V樹莓派): {'✓ 啟用' if self.ch2_enabled else '✗ 停用'}")
            
        except Exception as e:
            print(f"  ✗ INA3221 初始化失敗: {e}")
            self.ch1_enabled = False
            self.ch2_enabled = False
    
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
        """讀取所有通道"""
        ch1_data = self.read_ch1()
        ch2_data = self.read_ch2()
        return ch1_data, ch2_data
    
    def close(self):
        if self.ina:
            self.ina.close()


class DataLogger:
    """數據記錄器（雙通道版本）"""
    
    def __init__(self, filename=None):
        if filename is None:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"dual_power_log_{timestamp}.csv"
        
        self.filename = filename
        self.file = None
        self.writer = None
        self.init_file()
    
    def init_file(self):
        self.file = open(self.filename, 'w', newline='')
        self.writer = csv.writer(self.file)
        
        # CSV標頭（包含兩個通道）
        self.writer.writerow([
            'Timestamp',
            'AZ_Action', 'AZ_Position_mm', 'AZ_Position_%', 'AZ_Pulse',
            'TILT_Action', 'TILT_Position_mm', 'TILT_Position_%', 'TILT_Pulse',
            'CH1_24V_Actuator_Voltage_V', 'CH1_24V_Actuator_Current_mA', 'CH1_24V_Actuator_Power_W',
            'CH2_24V_Pi_Voltage_V', 'CH2_24V_Pi_Current_mA', 'CH2_24V_Pi_Power_W',
            'Total_Power_W'
        ])
        self.file.flush()
        print(f"  ✓ 數據記錄文件: {self.filename}")
    
    def log(self, az_data, tilt_data, ch1_data, ch2_data):
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
        
        # 計算總功率
        ch1_power = float(ch1_data[2]) if ch1_data[2] != "N/A" else 0
        ch2_power = float(ch2_data[2]) if ch2_data[2] != "N/A" else 0
        total_power = ch1_power + ch2_power
        
        row = [timestamp]
        row.extend(az_data)
        row.extend(tilt_data)
        row.extend(ch1_data)
        row.extend(ch2_data)
        row.append(f"{total_power:.3f}")
        
        self.writer.writerow(row)
        self.file.flush()
    
    def close(self):
        if self.file:
            self.file.close()


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
logger = None

try:
    GPIO.setmode(GPIO.BCM)
    GPIO.setwarnings(False)
    
    old_settings = termios.tcgetattr(sys.stdin)
    tty.setcbreak(sys.stdin.fileno())
    
    print("=" * 90)
    print("     雙軸太陽能追日系統 - 雙通道電源監控版本")
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
    
    # 初始化數據記錄
    print("\n【初始化數據記錄】")
    logger = DataLogger()
    
    print("\n" + "=" * 90)
    print("【按鍵說明】")
    print("=" * 90)
    print("\n組合動作（數字鍵）:")
    print("  1  - 左上 (A+W)  │  2  - 上 (W)      │  3  - 右上 (D+W)")
    print("  4  - 左 (A)      │  5  - 全停        │  6  - 右 (D)")
    print("  7  - 左下 (A+S)  │  8  - 下 (S)      │  9  - 右下 (D+S)")
    print("\n方位角: A/D - 左/右  │  F - 停止  │  Z - 歸零")
    print("傾角:   W/S - 上/下  │  X - 停止  │  C - 歸零")
    print("系統:   E - 緊急停止 │  Q - 退出")
    print("\n⚡ 系統參數:")
    print(f"   - 自動停止時間: {AUTO_STOP_TIMEOUT}秒")
    print(f"   - 輪詢間隔: {POLL_INTERVAL*1000:.0f}毫秒")
    print(f"   - 電源監控: CH1(24V推桿) + CH2(5V樹莓派)")
    print("=" * 90)
    print("\n系統就緒，等待指令...\n")
    
    # 狀態變數
    az_action = None
    tilt_action = None
    last_key_time = time.time()
    last_log_time = time.time()
    log_interval = 0.1
    
    # 按鍵統計
    key_count = 0
    last_key = None
    
    while True:
        key = get_key()
        
        if key:
            key_count += 1
            last_key_time = time.time()
            key = key.lower()
            
            # 除錯模式
            if DEBUG_MODE:
                if key != last_key:
                    print(f"\n[DEBUG] 按鍵: {key} (計數: {key_count})")
                    last_key = key
            
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
            
            if DEBUG_MODE:
                print(f"\n[DEBUG] 自動停止（超時 {AUTO_STOP_TIMEOUT}秒）")
        
        # 定期記錄和顯示數據
        if time.time() - last_log_time >= log_interval:
            # 讀取兩個通道
            ch1_data = power_monitor.read_ch1()  # 24V推桿
            ch2_data = power_monitor.read_ch2()  # 5V樹莓派
            
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
            
            # 記錄到CSV
            logger.log(az_data, tilt_data, ch1_formatted, ch2_formatted)
            
            # 即時顯示
            az_symbol = "←" if az_action == 'left' else "→" if az_action == 'right' else "■"
            tilt_symbol = "↑" if tilt_action == 'up' else "↓" if tilt_action == 'down' else "■"
            
            # 顯示格式：位置 | 24V推桿 | 24V樹莓派
            if ch1_data[0] is not None and ch2_data[0] is not None:
                print(f"{az_symbol}方位:{az_pos:5.1f}mm({az_pct:4.1f}%) | "
                      f"{tilt_symbol}傾角:{tilt_pos:5.1f}mm({tilt_pct:4.1f}%) | "
                      f"推桿:{ch1_data[0]:5.1f}V {ch1_data[1]:5.0f}mA {ch1_data[2]:5.1f}W | "
                      f"Pi:{ch2_data[0]:5.1f}V {ch2_data[1]:4.0f}mA {ch2_data[2]:4.1f}W",
                      end='\r', flush=True)
            elif ch1_data[0] is not None:
                print(f"{az_symbol}方位:{az_pos:5.1f}mm({az_pct:4.1f}%) | "
                      f"{tilt_symbol}傾角:{tilt_pos:5.1f}mm({tilt_pct:4.1f}%) | "
                      f"推桿:{ch1_data[0]:5.1f}V {ch1_data[1]:5.0f}mA {ch1_data[2]:5.1f}W | "
                      f"Pi: N/A",
                      end='\r', flush=True)
            else:
                print(f"{az_symbol}方位:{az_pos:5.1f}mm({az_pct:4.1f}%) | "
                      f"{tilt_symbol}傾角:{tilt_pos:5.1f}mm({tilt_pct:4.1f}%) | "
                      f"電源: N/A",
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
