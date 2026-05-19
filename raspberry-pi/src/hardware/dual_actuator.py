#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
dual_actuator.py
================
雙軸推桿硬體模組（自 test_actuator.py 抽出為共用模組）

提供：
  - SingleActuator      單一推桿（東西/南北任一軸）的 extend/retract/stop
  - HallSensorMonitor   霍爾感測器計數線程，提供推桿即時位置
  - DualPowerMonitor    INA3221 雙通道電力監控（CH1=推桿總、CH2=Pi）
  - DualAxisActuator    高階雙軸控制：給定目標 (gamma, zeta) 自動推到位

對 anfis_controller / traditional_controller 提供清楚的高階 API：
  - act = DualAxisActuator()
  - act.move_to_tiptilt(target_gamma, target_zeta)   # 度，閉迴路移動
  - act.read_position()                                # (gamma, zeta)
  - act.read_actuator_power()                          # (voltage, current)
  - act.read_pi_power()                                # (voltage, current)
  - act.close()

硬體假設（與 test_actuator.py 一致，可在 CONFIG 覆寫）：
  - GPIO BCM 模式
  - 兩支 HB-DJ809 線性推桿 + INA3221 + 霍爾感測器
  - AZ 推桿 = 控制 zeta (東西向)
  - TILT 推桿 = 控制 gamma (南北向)
  - 推桿行程 → 板面角度需要校正表（_stroke_mm_to_angle_deg）
"""
import math
import time
import threading
import logging
from typing import Optional, Tuple, Dict

logger = logging.getLogger(__name__)

# ── 硬體導入 ─────────────────────────────────────────────────────
try:
    import RPi.GPIO as GPIO
    GPIO_AVAILABLE = True
except ImportError:
    GPIO_AVAILABLE = False
    GPIO = None

try:
    from SDL_Pi_INA3221 import INA3221
    INA3221_AVAILABLE = True
except ImportError:
    INA3221_AVAILABLE = False


# ════════════════════════════════════════════════════════════════
# 預設配置（可在建構時覆寫）
# ════════════════════════════════════════════════════════════════
DEFAULT_HARDWARE_CONFIG = {
    # AZ 推桿（東西向，控制 zeta）— 206mm 行程
    'az_brown_high': 17, 'az_blue_high':  27,
    'az_brown_low':  22, 'az_blue_low':   23,
    'az_hall1':      24, 'az_hall2':      25,
    'az_pulses_per_mm': 54.19,
    'az_stroke_mm':     206,

    # TILT 推桿（南北向，控制 gamma）— 406mm 行程
    'tilt_brown_high': 5,  'tilt_blue_high':  6,
    'tilt_brown_low':  13, 'tilt_blue_low':   19,
    'tilt_hall1':      16, 'tilt_hall2':      26,
    'tilt_pulses_per_mm': 54.19,
    'tilt_stroke_mm':     406,

    # INA3221
    'ina3221_addr':   0x40,
    'ina3221_shunt':  0.1,
    'ch_actuator':    1,    # CH1 = 推桿總電力
    'ch_pi':          2,    # CH2 = Pi 電力

    # 角度轉換校正（行程%對應角度，需實機校正後填入）
    # 預設：行程 0% → 角度極限負；100% → 角度極限正；線性插值
    'az_angle_min_deg':   -30.0,   # zeta 最小
    'az_angle_max_deg':    30.0,   # zeta 最大
    'tilt_angle_min_deg': -30.0,   # gamma 最小
    'tilt_angle_max_deg':  30.0,   # gamma 最大

    # 移動行為
    'move_timeout_sec':       60.0,  # 單次移動逾時
    'tolerance_pulses':       3,     # 到位容忍誤差（pulses）
    'auto_stop_check_sec':    0.05,  # 移動中位置檢查頻率
}


# ════════════════════════════════════════════════════════════════
# 單一推桿控制
# ════════════════════════════════════════════════════════════════
class SingleActuator:
    """單一推桿正反轉控制（與 test_actuator.py ActuatorController 等價）"""

    def __init__(self, name: str, brown_high: int, blue_high: int,
                 brown_low: int, blue_low: int):
        self.name = name
        self.brown_high = brown_high
        self.blue_high  = blue_high
        self.brown_low  = brown_low
        self.blue_low   = blue_low
        self.current_state: Optional[str] = None  # None / 'extend' / 'retract'

        if GPIO_AVAILABLE:
            GPIO.setup([brown_high, blue_high, brown_low, blue_low], GPIO.OUT)
            self.stop()

    def extend(self):
        if self.current_state == 'extend':
            return
        if not GPIO_AVAILABLE:
            self.current_state = 'extend'
            return
        GPIO.output([self.brown_high, self.blue_low], GPIO.LOW)
        time.sleep(0.01)
        GPIO.output([self.blue_high, self.brown_low], GPIO.HIGH)
        self.current_state = 'extend'

    def retract(self):
        if self.current_state == 'retract':
            return
        if not GPIO_AVAILABLE:
            self.current_state = 'retract'
            return
        GPIO.output([self.blue_high, self.brown_low], GPIO.LOW)
        time.sleep(0.01)
        GPIO.output([self.brown_high, self.blue_low], GPIO.HIGH)
        self.current_state = 'retract'

    def stop(self):
        if self.current_state is None:
            return
        if not GPIO_AVAILABLE:
            self.current_state = None
            return
        GPIO.output([self.brown_high, self.blue_high,
                     self.brown_low,  self.blue_low], GPIO.LOW)
        self.current_state = None


# ════════════════════════════════════════════════════════════════
# 霍爾感測器計數
# ════════════════════════════════════════════════════════════════
class HallSensorMonitor:
    """霍爾感測器位置計數（背景線程，與 test_actuator.py HallSensorMonitor 等價）"""

    def __init__(self, name: str, hall1_pin: int, hall2_pin: int,
                 pulses_per_mm: float, stroke_mm: float):
        self.name = name
        self.hall1_pin = hall1_pin
        self.hall2_pin = hall2_pin
        self.pulses_per_mm = pulses_per_mm
        self.stroke_mm = stroke_mm

        self.pulse_count = 0
        self.position_mm = 0.0
        self.monitoring = True

        if GPIO_AVAILABLE:
            GPIO.setup([hall1_pin, hall2_pin], GPIO.IN, pull_up_down=GPIO.PUD_UP)
            self.last_hall1 = GPIO.input(hall1_pin)
            self._thread = threading.Thread(target=self._monitor, daemon=True)
            self._thread.start()
        else:
            self.last_hall1 = 0
            self._thread = None

    def _monitor(self):
        while self.monitoring:
            h1 = GPIO.input(self.hall1_pin)
            h2 = GPIO.input(self.hall2_pin)
            if h1 != self.last_hall1:
                # quadrature 解碼：兩條 hall 相位差判方向
                if h1 == h2:
                    self.pulse_count -= 1
                else:
                    self.pulse_count += 1
                self.position_mm = self.pulse_count / self.pulses_per_mm
                self.last_hall1 = h1
            time.sleep(0.0001)

    def get_pulse_count(self) -> int:
        return self.pulse_count

    def get_position_mm(self) -> float:
        return self.position_mm

    def get_position_percentage(self) -> float:
        if self.stroke_mm <= 0:
            return 0.0
        return (self.position_mm / self.stroke_mm) * 100.0

    def reset(self):
        self.pulse_count = 0
        self.position_mm = 0.0

    def stop(self):
        self.monitoring = False


# ════════════════════════════════════════════════════════════════
# INA3221 雙通道電力監控
# ════════════════════════════════════════════════════════════════
class DualPowerMonitor:
    """INA3221 兩通道電力監控（CH1 推桿、CH2 Pi）"""

    def __init__(self, addr: int = 0x40, shunt_ohm: float = 0.1):
        self.ina = None
        self.ch1_enabled = False
        self.ch2_enabled = False

        if not INA3221_AVAILABLE:
            logger.warning("SDL_Pi_INA3221 未安裝，電力監控停用")
            return

        try:
            self.ina = INA3221(bus_num=1, addr=addr, shunt_resistor=shunt_ohm)
            # 探測 CH1
            try:
                _ = self.ina.bus_voltage(1)
                self.ch1_enabled = True
            except Exception as e:
                logger.warning("INA3221 CH1 探測失敗: %s", e)
            # 探測 CH2
            try:
                _ = self.ina.bus_voltage(2)
                self.ch2_enabled = True
            except Exception as e:
                logger.warning("INA3221 CH2 探測失敗: %s", e)
        except Exception as e:
            logger.warning("INA3221 初始化失敗: %s", e)

    def read_channel(self, ch: int) -> Tuple[Optional[float], Optional[float],
                                              Optional[float]]:
        """讀取通道，回傳 (voltage_V, current_mA, power_W)"""
        if self.ina is None:
            return None, None, None
        try:
            v = self.ina.bus_voltage(ch)
            i = self.ina.current(ch)       # mA
            p = self.ina.power(ch) / 1000  # mW → W
            return v, i, p
        except Exception:
            return None, None, None

    def read_actuator(self, ch_actuator: int = 1) -> Dict:
        v, i_ma, p = self.read_channel(ch_actuator)
        return {
            'voltage': round(v, 3) if v is not None else None,
            'current': round(i_ma / 1000.0, 4) if i_ma is not None else None,  # A
            'power':   round(p, 3) if p is not None else None,
        }

    def read_pi(self, ch_pi: int = 2) -> Dict:
        v, i_ma, p = self.read_channel(ch_pi)
        return {
            'voltage': round(v, 3) if v is not None else None,
            'current': round(i_ma / 1000.0, 4) if i_ma is not None else None,
            'power':   round(p, 3) if p is not None else None,
        }

    def close(self):
        if self.ina is not None:
            try:
                self.ina.close()
            except Exception:
                pass


# ════════════════════════════════════════════════════════════════
# 雙軸高階控制
# ════════════════════════════════════════════════════════════════
class DualAxisActuator:
    """
    雙軸閉迴路控制：給定目標 (gamma, zeta) 角度，自動驅動推桿到位

    座標：
        gamma = TILT 推桿控制（南北向，+北/-南）
        zeta  = AZ   推桿控制（東西向，+東/-西）

    假設：
        推桿行程 0–stroke_mm 線性對應角度 [angle_min, angle_max]
        實際校正：在實機上記錄推桿全縮/全伸時的板面角度，調整 angle_min/max
    """

    def __init__(self, config: Optional[Dict] = None):
        self.cfg = dict(DEFAULT_HARDWARE_CONFIG)
        if config:
            self.cfg.update(config)
        c = self.cfg

        if GPIO_AVAILABLE:
            GPIO.setmode(GPIO.BCM)
            GPIO.setwarnings(False)

        # AZ 推桿（控制 zeta）
        self.az_act = SingleActuator(
            'AZ', c['az_brown_high'], c['az_blue_high'],
            c['az_brown_low'], c['az_blue_low']
        )
        self.az_hall = HallSensorMonitor(
            'AZ', c['az_hall1'], c['az_hall2'],
            c['az_pulses_per_mm'], c['az_stroke_mm']
        )

        # TILT 推桿（控制 gamma）
        self.tilt_act = SingleActuator(
            'TILT', c['tilt_brown_high'], c['tilt_blue_high'],
            c['tilt_brown_low'], c['tilt_blue_low']
        )
        self.tilt_hall = HallSensorMonitor(
            'TILT', c['tilt_hall1'], c['tilt_hall2'],
            c['tilt_pulses_per_mm'], c['tilt_stroke_mm']
        )

        # 電力監控
        self.power = DualPowerMonitor(c['ina3221_addr'], c['ina3221_shunt'])

        # 初始位置假設：推桿全縮 → 對應 angle_min
        # 實機開機前應先 home（全縮觸發極限），這裡僅做軟體預設
        self.az_hall.reset()
        self.tilt_hall.reset()

        logger.info("DualAxisActuator 初始化完成（GPIO_AVAILABLE=%s, INA=%s）",
                    GPIO_AVAILABLE, self.power.ina is not None)

    # ── 行程 (mm) → 角度 (度) 線性轉換 ────────────────────────────
    def _az_stroke_to_zeta(self, stroke_mm: float) -> float:
        c = self.cfg
        ratio = stroke_mm / c['az_stroke_mm']
        return c['az_angle_min_deg'] + ratio * (
            c['az_angle_max_deg'] - c['az_angle_min_deg']
        )

    def _zeta_to_az_stroke(self, zeta_deg: float) -> float:
        c = self.cfg
        ratio = (zeta_deg - c['az_angle_min_deg']) / (
            c['az_angle_max_deg'] - c['az_angle_min_deg']
        )
        ratio = max(0.0, min(1.0, ratio))
        return ratio * c['az_stroke_mm']

    def _tilt_stroke_to_gamma(self, stroke_mm: float) -> float:
        c = self.cfg
        ratio = stroke_mm / c['tilt_stroke_mm']
        return c['tilt_angle_min_deg'] + ratio * (
            c['tilt_angle_max_deg'] - c['tilt_angle_min_deg']
        )

    def _gamma_to_tilt_stroke(self, gamma_deg: float) -> float:
        c = self.cfg
        ratio = (gamma_deg - c['tilt_angle_min_deg']) / (
            c['tilt_angle_max_deg'] - c['tilt_angle_min_deg']
        )
        ratio = max(0.0, min(1.0, ratio))
        return ratio * c['tilt_stroke_mm']

    # ── 公開 API ──────────────────────────────────────────────────
    def read_position(self) -> Tuple[float, float]:
        """回傳當前 (gamma, zeta) 度數"""
        zeta  = self._az_stroke_to_zeta(self.az_hall.get_position_mm())
        gamma = self._tilt_stroke_to_gamma(self.tilt_hall.get_position_mm())
        return gamma, zeta

    def move_to_tiptilt(self, target_gamma: float, target_zeta: float):
        """同步移動兩軸到目標角度（閉迴路，到位後自動停止）"""
        # 限制在物理範圍
        c = self.cfg
        target_gamma = max(c['tilt_angle_min_deg'],
                            min(c['tilt_angle_max_deg'], target_gamma))
        target_zeta  = max(c['az_angle_min_deg'],
                            min(c['az_angle_max_deg'],  target_zeta))

        # 計算目標 pulse count
        target_az_stroke   = self._zeta_to_az_stroke(target_zeta)
        target_tilt_stroke = self._gamma_to_tilt_stroke(target_gamma)
        target_az_pulse    = int(target_az_stroke   * c['az_pulses_per_mm'])
        target_tilt_pulse  = int(target_tilt_stroke * c['tilt_pulses_per_mm'])

        # 起始方向判斷
        self._drive_axis(self.az_act, self.az_hall, target_az_pulse,
                          c['tolerance_pulses'])
        self._drive_axis(self.tilt_act, self.tilt_hall, target_tilt_pulse,
                          c['tolerance_pulses'])

        # 兩軸同時動 → 各自迴圈檢查到位
        # 改為「順序而非並行」以便首版穩定；併行控制可後續加
        # （這裡先 sequential 做完）
        logger.info("move_to_tiptilt: γ=%.1f° ζ=%.1f° (pulses az=%d tilt=%d)",
                    target_gamma, target_zeta, target_az_pulse, target_tilt_pulse)

    def _drive_axis(self, act: SingleActuator, hall: HallSensorMonitor,
                     target_pulse: int, tol: int):
        """單軸閉迴路：根據當前 pulse 與 target_pulse 差，extend/retract 到位"""
        c = self.cfg
        start = time.time()
        while time.time() - start < c['move_timeout_sec']:
            cur = hall.get_pulse_count()
            err = target_pulse - cur
            if abs(err) <= tol:
                act.stop()
                return
            if err > 0:
                act.extend()
            else:
                act.retract()
            time.sleep(c['auto_stop_check_sec'])
        act.stop()
        logger.warning("%s 移動逾時 (target=%d cur=%d)",
                       act.name, target_pulse, hall.get_pulse_count())

    def stop_all(self):
        """緊急停止所有推桿"""
        self.az_act.stop()
        self.tilt_act.stop()

    def read_actuator_power(self) -> Dict:
        return self.power.read_actuator(self.cfg['ch_actuator'])

    def read_pi_power(self) -> Dict:
        return self.power.read_pi(self.cfg['ch_pi'])

    def home(self):
        """歸位：兩軸全縮，重設位置為角度極限負值"""
        c = self.cfg
        logger.info("執行 home：兩軸全縮歸位中...")
        self.az_act.retract()
        self.tilt_act.retract()
        # 全縮估計時間：206 / 5mm/s ≈ 41s（保守）
        time.sleep(50)
        self.stop_all()
        self.az_hall.reset()
        self.tilt_hall.reset()
        logger.info("home 完成，當前位置設為 γ=%.1f° ζ=%.1f°",
                    c['tilt_angle_min_deg'], c['az_angle_min_deg'])

    def close(self):
        """清理：停止所有推桿、霍爾線程、INA3221、GPIO"""
        self.stop_all()
        self.az_hall.stop()
        self.tilt_hall.stop()
        self.power.close()
        if GPIO_AVAILABLE:
            try:
                GPIO.cleanup()
            except Exception:
                pass
