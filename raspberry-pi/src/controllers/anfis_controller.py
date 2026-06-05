#!/usr/bin/env python3
"""
實驗組控制器 — ANFIS 智慧追日
Experiment Group (system_id=7)

流程圖邏輯（依序）：
    開始
    → 讀取感測器資料（時間、LDR 絕對值、當前功率、當前角度）
    → ANFIS 格網掃描預測最佳角度
    → 記錄實際值 vs 預測值差異，檢測是否為系統性誤差
        → 是 → 計算校正係數，調整預測 → 回到格網掃描
    → 評估是否值得移動
        → 否 → 等待間隔時間 → 回到讀感測器
    → 移動至預測角度，記錄發電量
    → 判斷發電量是否接近預期
        → 是 → 保持，記錄成功經驗
        → 否 → 模糊規則微調
               → 微調是否改善？
                   → 是 → 保持，記錄成功
                   → 否 → 回到微調前位置，記錄失敗
    → 上傳 log 到 Django API（替代「更新模型」步驟）
    → 判斷太陽時間是否結束
        → 是 → 回歸東方初始位置 → 結束
        → 否 → 等待間隔時間 → 回到讀感測器

硬體連接：
    MCP3008 CH0 = 東 LDR
    MCP3008 CH1 = 西 LDR
    MCP3008 CH2 = 南 LDR
    MCP3008 CH3 = 北 LDR
    INA3221（I2C）= 電壓/電流/功率
    霍爾感測器 = 推桿行程（→ 角度對照表）

座標系統：
    tip-tilt：γ 南北（+北/−南），ζ 東西（+東/−西），範圍 ±30°
    傾角方位角：β (tilt)，φ (azimuth)，由 tiptilt_to_azalt() 轉換
    ANFIS 特徵用傾角方位角系統（與訓練資料一致）

ANFIS 模型輸入特徵（9 維，與訓練時完全一致）：
    hour_sin, hour_cos          時刻循環編碼（from timestamp）
    day_sin,  day_cos           季節循環編碼（from timestamp）
    tilt_sin, tilt_cos          傾角 β 的 sin/cos
    azimuth_sin, azimuth_cos    方位角 φ 的 sin/cos
    illumination                照度 W/m²（四 LDR 校正後平均值）
"""

import os
import math
import time
import json
import logging
import numpy as np
import requests
from datetime import datetime
from pathlib import Path
from typing import Dict, Optional, Tuple

# ── 硬體導入 ─────────────────────────────────────────────────────
try:
    from gpiozero import MCP3008
    import smbus2
    HARDWARE_AVAILABLE = True
except ImportError:
    HARDWARE_AVAILABLE = False

# ── ANFIS 模型導入（需 tensorflow + 自訂 SimpleFuzzyLayer）─────
try:
    import tensorflow as tf
    import joblib
    from anfis_layer import SimpleFuzzyLayer   # Keras 3 用 custom_objects 載入
    ANFIS_AVAILABLE = True
except ImportError:
    ANFIS_AVAILABLE = False
    print("警告：TensorFlow / anfis_layer 未安裝，將使用模擬預測")

# ════════════════════════════════════════════════════════════════
# 設定
# ════════════════════════════════════════════════════════════════
CONFIG = {
    # Django API
    'system_id': 7,
    'api_url': 'http://localhost:8000/api',

    # 模擬模式（True = 允許在無硬體環境下以隨機值測試；False = 生產模式，硬體失敗直接拋例外）
    'simulation_mode': False,

    # MCP3008
    'mcp3008': {
        'east_ch':  0,
        'west_ch':  1,
        'south_ch': 2,
        'north_ch': 3,
        'spi_port': 0,
        'device':   0,
    },

    # LDR 校正係數（每顆個別校正，ADC值 × slope + intercept = W/m²）
    # TODO：實際校正後填入各感測器的係數
    'ldr_calibration': {
        'east':  {'slope': 1.15, 'intercept': 0.0},
        'west':  {'slope': 1.10, 'intercept': 0.0},
        'south': {'slope': 1.12, 'intercept': 0.0},
        'north': {'slope': 1.08, 'intercept': 0.0},
    },

    # ANFIS 模型路徑（相對於本檔案）
    'model': {
        'keras_path':  'models/anfis_with_illumination.keras',
        'scaler_path': 'models/scaler_X_with_illumination.save',
        'config_path': 'models/model_config_with_illumination.json',
    },

    # 角度搜尋範圍（傾角方位角系統）
    # ANFIS 訓練範圍：β 10-30°、φ 160-200°
    # 物理可達範圍：β 0-41.4°、φ 90-270°
    # 目前搜尋設定略大於訓練範圍，給模型插值空間
    'search': {
        'tilt_min':     10.0,  # β 最小值（度）
        'tilt_max':     40.0,  # β 最大值（度）
        'tilt_step':     5.0,
        'azimuth_min':  90.0,  # φ 最小值（度）
        'azimuth_max': 270.0,  # φ 最大值（度）
        'azimuth_step': 10.0,
    },

    # 控制閾值
    'thresholds': {
        'movement_worthiness': 2.0,    # 預測增益須超過此值(W)才移動
        'power_expectation':   0.90,   # 實際/預期 ≥ 0.90 視為符合預期
        'fine_tune_improve':   0.5,    # 微調改善最低門檻(W)
        'systematic_error':    5.0,    # 系統性誤差閾值(W)
    },

    # 微調參數（LDR 差值 → 角度調整）
    'fine_tune': {
        'ldr_threshold':    50,    # LDR 差值超過此值才微調
        'az_step_per_unit': 0.01,  # 每單位 LDR 差值對應的方位角調整（度）
        'tl_step_per_unit': 0.007,
        'max_az_adj':       2.0,   # 單次最大方位角調整（度）
        'max_tl_adj':       1.0,   # 單次最大傾角調整（度）
    },

    # 時間
    'sun_start_hour':   6,
    'sun_end_hour':    18,
    'interval_seconds': 600,    # 10 分鐘

    # 東方初始位置（tip-tilt 座標）
    'initial_position': {'gamma': -15.0, 'zeta': 30.0},

    # 推桿步進（度）
    'step_deg': 5.0,

    # tip-tilt 物理限制
    'gamma_min': -30.0, 'gamma_max': 30.0,
    'zeta_min':  -30.0, 'zeta_max':  30.0,

    # 系統性誤差校正係數限制
    'corr_min': 0.7, 'corr_max': 1.3,

    # INA3221 設定
    'ina3221': {
        'i2c_addr':    0x40,   # A0/A1 接 GND
        'shunt_ohm':   0.1,    # 分流電阻（Ω），標準模組為 0.1Ω
        'act_channel': 1,      # CH1 = 兩隻推桿合計
        'pi_channel':  2,      # CH2 = 樹莓派本身
    },

    # MPPT RS485 設定（太陽能板電壓/電流）
    'mppt': {
        'port':     '/dev/ttyUSB0',
        'baudrate': 9600,
        # TODO：確認 MPPT 控制器通訊協定（Modbus RTU 或自訂格式）後補充
    },
}

# ── 日誌 ─────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    handlers=[
        logging.FileHandler('anfis_controller.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)


# ════════════════════════════════════════════════════════════════
# 座標轉換（tip-tilt ↔ 傾角/方位角）
# ════════════════════════════════════════════════════════════════
def tiptilt_to_azalt(gamma: float, zeta: float) -> Tuple[float, float]:
    """
    tip-tilt → 傾角(β)/方位角(φ)
    gamma: 南北向傾角（+北/−南）
    zeta:  東西向傾角（+東/−西）
    回傳 (beta, phi)，phi 在 0-360°
    """
    g = math.radians(gamma)
    z = math.radians(zeta)
    x  = math.sin(z)
    y  = math.sin(g) * math.cos(z)
    zz = math.cos(g) * math.cos(z)
    beta = math.degrees(math.acos(max(-1.0, min(1.0, zz))))
    phi  = math.degrees(math.atan2(x, y))
    if phi < 0:
        phi += 360.0
    return beta, phi


def azalt_to_tiptilt(beta: float, phi: float) -> Tuple[float, float]:
    """
    傾角(β)/方位角(φ) → tip-tilt (gamma, zeta)
    用於將 ANFIS 搜尋到的最佳角度轉回推桿控制座標
    """
    b = math.radians(beta)
    p = math.radians(phi)
    x = math.sin(b) * math.sin(p)
    y = math.sin(b) * math.cos(p)
    # z = cos(b) = cos(g)*cos(z)
    zeta  = math.degrees(math.asin(max(-1.0, min(1.0, x))))
    gamma = math.degrees(math.atan2(y, math.cos(math.radians(zeta))))
    return gamma, zeta


# ════════════════════════════════════════════════════════════════
# INA3221 電力感測器
# ════════════════════════════════════════════════════════════════
class INA3221Reader:
    """
    INA3221 三通道電流/電壓感測（I2C）
    CH1 = 兩隻推桿合計
    CH2 = 樹莓派本身
    分流電阻：0.1Ω（標準模組預設）
    """
    _REG_SHUNT = {1: 0x02, 2: 0x04, 3: 0x06}
    _REG_BUS   = {1: 0x03, 2: 0x05, 3: 0x07}
    _LSB_SHUNT = 40e-6   # 40 µV / LSB
    _LSB_BUS   = 8e-3    #  8 mV / LSB

    def __init__(self):
        cfg = CONFIG['ina3221']
        self._addr  = cfg['i2c_addr']
        self._shunt = cfg['shunt_ohm']
        self._bus   = None

        if HARDWARE_AVAILABLE and not CONFIG['simulation_mode']:
            try:
                self._bus = smbus2.SMBus(1)
                logger.info("INA3221 初始化成功（I2C 0x%02X）", self._addr)
            except Exception as e:
                logger.warning("INA3221 初始化失敗: %s", e)

    def _read_reg_signed(self, reg: int) -> int:
        data = self._bus.read_i2c_block_data(self._addr, reg, 2)
        raw  = (data[0] << 8) | data[1]
        return raw - 0x10000 if raw > 0x7FFF else raw

    def read_channel(self, ch: int) -> dict:
        """讀取指定通道電壓（V）與電流（A）"""
        if CONFIG['simulation_mode']:
            import random
            return {
                'voltage': round(random.uniform(11.5, 12.5), 3),
                'current': round(random.uniform(0.1, 2.0),   3),
            }
        if self._bus is None:
            raise RuntimeError(
                "INA3221 未初始化，若要測試請設定 simulation_mode=True"
            )
        try:
            shunt_raw = self._read_reg_signed(self._REG_SHUNT[ch])
            bus_raw   = self._read_reg_signed(self._REG_BUS[ch])
            shunt_v   = (shunt_raw >> 3) * self._LSB_SHUNT
            bus_v     = (bus_raw   >> 3) * self._LSB_BUS
            return {
                'voltage': round(bus_v,            3),
                'current': round(shunt_v / self._shunt, 4),
            }
        except Exception as e:
            raise RuntimeError(f"INA3221 CH{ch} 讀取失敗: {e}") from e

    def read_actuator(self) -> dict:
        return self.read_channel(CONFIG['ina3221']['act_channel'])

    def read_pi(self) -> dict:
        return self.read_channel(CONFIG['ina3221']['pi_channel'])


# ════════════════════════════════════════════════════════════════
# MPPT RS485 讀取（太陽能板電壓/電流）
# ════════════════════════════════════════════════════════════════
def read_mppt_power() -> dict:
    """
    從 MPPT 控制器讀取太陽能板電壓/電流（RS485-to-USB 序列埠）。
    回傳 {'voltage': V, 'current': A, 'power': W}

    TODO：確認 MPPT 控制器通訊協定後實作。
    實作範例（Modbus RTU）：
        import minimalmodbus
        instrument = minimalmodbus.Instrument(CONFIG['mppt']['port'], 1)
        instrument.serial.baudrate = CONFIG['mppt']['baudrate']
        voltage = instrument.read_register(0x0101, numberOfDecimals=1)
        current = instrument.read_register(0x0102, numberOfDecimals=2)
        return {'voltage': voltage, 'current': current, 'power': voltage * current}
    """
    if CONFIG['simulation_mode']:
        import random
        v = round(random.uniform(14.0, 18.0), 2)
        i = round(random.uniform(0.5, 5.0),   2)
        return {'voltage': v, 'current': i, 'power': round(v * i, 2)}

    raise NotImplementedError(
        "MPPT RS485 讀取尚未實作，請先確認通訊協定後填入，"
        "或設定 simulation_mode=True 進行測試"
    )


# ════════════════════════════════════════════════════════════════
# ANFIS 模型包裝
# ════════════════════════════════════════════════════════════════
class ANFISModel:
    """
    載入已訓練的 ANFIS 模型，提供功率預測。
    輸入特徵必須與訓練時完全一致（9 維 sin/cos 編碼）。
    """

    def __init__(self, model_dir: str):
        self.model   = None
        self.scaler  = None
        self.config  = None
        self.loaded  = False
        self.has_illumination = True

        base = Path(model_dir)
        k_path = base / CONFIG['model']['keras_path']
        s_path = base / CONFIG['model']['scaler_path']
        c_path = base / CONFIG['model']['config_path']

        if not ANFIS_AVAILABLE:
            logger.warning("TensorFlow 未安裝，ANFIS 模型無法載入")
            return
        if not k_path.exists():
            logger.warning("模型檔案不存在: %s", k_path)
            return

        try:
            self.model  = tf.keras.models.load_model(
                str(k_path), compile=False,
                custom_objects={'SimpleFuzzyLayer': SimpleFuzzyLayer})
            self.scaler = joblib.load(str(s_path))
            with open(c_path, encoding='utf-8') as f:
                self.config = json.load(f)
            self.has_illumination = self.config.get('has_illumination', True)
            self.loaded = True
            logger.info("ANFIS 模型載入成功（has_illumination=%s）",
                        self.has_illumination)
        except Exception as e:
            logger.error("ANFIS 模型載入失敗: %s", e)

    def predict(self, beta: float, phi: float,
                now: datetime, illumination: float) -> float:
        """
        預測給定角度和當下條件的發電功率（W）。

        beta:         傾角（度）
        phi:          方位角（度）
        now:          當下時間
        illumination: 照度（W/m²，四 LDR 校正平均值）
        """
        # 特徵工程（與訓練時完全一致）
        hour_dec = now.hour + now.minute / 60.0 + now.second / 3600.0
        day_of_year = now.timetuple().tm_yday

        features = [
            math.sin(2 * math.pi * hour_dec   / 24),   # hour_sin
            math.cos(2 * math.pi * hour_dec   / 24),   # hour_cos
            math.sin(2 * math.pi * day_of_year / 365), # day_sin
            math.cos(2 * math.pi * day_of_year / 365), # day_cos
            math.sin(math.radians(beta)),               # tilt_sin
            math.cos(math.radians(beta)),               # tilt_cos
            math.sin(math.radians(phi)),                # azimuth_sin
            math.cos(math.radians(phi)),                # azimuth_cos
        ]
        if self.has_illumination:
            features.append(illumination)              # illumination

        X = np.array(features).reshape(1, -1)

        if self.loaded:
            X_scaled = self.scaler.transform(X)
            pred = self.model.predict(X_scaled, verbose=0)
            return float(max(0.0, pred[0][0]))
        else:
            # 無模型時的模擬預測（僅供測試）
            base = illumination * 0.25
            tilt_eff = math.cos(math.radians(abs(beta - 20)))
            az_eff   = math.cos(math.radians(abs(phi - 180) * 0.5))
            return max(0.0, base * tilt_eff * az_eff)


# ════════════════════════════════════════════════════════════════
# 感測器讀取
# ════════════════════════════════════════════════════════════════
class SensorReader:
    """
    MCP3008 LDR 讀取 + INA3221 功率讀取。
    LDR 值：ADC 單位 (0-1023) → 依校正係數轉為 W/m²。
    """

    def __init__(self):
        cfg = CONFIG['mcp3008']
        if HARDWARE_AVAILABLE:
            self._adc = {
                'east':  MCP3008(channel=cfg['east_ch'],
                                 port=cfg['spi_port'], device=cfg['device']),
                'west':  MCP3008(channel=cfg['west_ch'],
                                 port=cfg['spi_port'], device=cfg['device']),
                'south': MCP3008(channel=cfg['south_ch'],
                                 port=cfg['spi_port'], device=cfg['device']),
                'north': MCP3008(channel=cfg['north_ch'],
                                 port=cfg['spi_port'], device=cfg['device']),
            }

    def _adc_to_wm2(self, direction: str, raw_adc: float) -> float:
        """ADC 值 → W/m²（個別校正）"""
        cal = CONFIG['ldr_calibration'][direction]
        return max(0.0, raw_adc * cal['slope'] + cal['intercept'])

    def read_ldr_raw(self) -> Dict[str, float]:
        """讀取 ADC 原始值（0-1023）"""
        if CONFIG['simulation_mode']:
            import random
            base = random.uniform(300, 800)
            return {d: round(base + random.uniform(-60, 60))
                    for d in ('east', 'west', 'south', 'north')}

        if not HARDWARE_AVAILABLE:
            raise RuntimeError(
                "硬體不可用（gpiozero 未安裝），若要測試請在 CONFIG 中設定 simulation_mode=True"
            )

        try:
            return {d: round(self._adc[d].value * 1023)
                    for d in ('east', 'west', 'south', 'north')}
        except Exception as e:
            raise RuntimeError(f"LDR 讀取失敗（感測器可能斷線或接觸不良）: {e}") from e

    def read_illumination(self) -> Tuple[Dict[str, float], float]:
        """
        回傳 (calibrated_ldr_dict, illumination_avg)
        illumination_avg = 四方向校正值的平均（W/m²），作為 ANFIS 輸入
        """
        raw  = self.read_ldr_raw()
        cal  = {d: self._adc_to_wm2(d, raw[d]) for d in raw}
        avg  = sum(cal.values()) / 4.0
        return cal, avg

    def read_power(self) -> float:
        """
        讀取目前面板功率（W）。
        TODO：接 INA3221 I2C，讀取電壓×電流。
              實作後移除 simulation_mode fallback。
        """
        if CONFIG['simulation_mode']:
            import random
            return random.uniform(50, 200)

        # TODO 範例（INA3221 實作後取消註解）：
        # from ina3221 import INA3221
        # sensor = INA3221(1, address=0x40)
        # return sensor.get_bus_voltage(1) * sensor.get_current(1)
        raise NotImplementedError(
            "INA3221 功率讀取尚未實作，請先在 CONFIG 中設定 simulation_mode=True 進行測試"
        )


# ════════════════════════════════════════════════════════════════
# 推桿控制器
# ════════════════════════════════════════════════════════════════
class ActuatorController:
    """
    雙軸推桿控制（同對照組，但以傾角方位角為主要介面）。
    外部呼叫 move_to_azalt(beta, phi) 即可。
    """

    def __init__(self):
        init = CONFIG['initial_position']
        self.gamma = init['gamma']
        self.zeta  = init['zeta']
        # 目前傾角/方位角（由 tip-tilt 換算）
        self.beta, self.phi = tiptilt_to_azalt(self.gamma, self.zeta)

    def move_to_azalt(self, target_beta: float, target_phi: float):
        """移動到目標傾角/方位角（轉換為 tip-tilt 後驅動推桿）"""
        tg, tz = azalt_to_tiptilt(target_beta, target_phi)
        # 限制在物理範圍
        tg = max(CONFIG['gamma_min'], min(CONFIG['gamma_max'], tg))
        tz = max(CONFIG['zeta_min'],  min(CONFIG['zeta_max'],  tz))
        self._move_to_tiptilt(tg, tz)
        self.gamma = tg
        self.zeta  = tz
        self.beta, self.phi = tiptilt_to_azalt(tg, tz)
        logger.info("移動 → β=%.1f° φ=%.1f°  (γ=%.1f° ζ=%.1f°)",
                    self.beta, self.phi, self.gamma, self.zeta)

    def return_to_initial(self):
        init = CONFIG['initial_position']
        self._move_to_tiptilt(init['gamma'], init['zeta'])
        self.gamma = init['gamma']
        self.zeta  = init['zeta']
        self.beta, self.phi = tiptilt_to_azalt(self.gamma, self.zeta)
        logger.info("回歸初始位置 γ=%.1f° ζ=%.1f°", self.gamma, self.zeta)

    # ── 硬體驅動（TODO）────────────────────────────
    def _move_to_tiptilt(self, target_gamma: float, target_zeta: float):
        """
        TODO：根據霍爾感測器行程對照表，閉迴路移動到目標 tip-tilt 角度。
        目前為軟體記錄，實際推桿未動作。
        """
        pass


# ════════════════════════════════════════════════════════════════
# Django API 上傳
# ════════════════════════════════════════════════════════════════
def upload_log(payload: dict):
    """上傳本次循環的完整記錄到 Django API"""
    try:
        url = f"{CONFIG['api_url']}/power-records/"
        resp = requests.post(url, json=payload, timeout=10)
        if resp.status_code in (200, 201):
            logger.info("log 上傳成功")
        else:
            logger.warning("log 上傳失敗 %d: %s",
                           resp.status_code, resp.text[:120])
    except Exception as e:
        logger.warning("log 上傳例外: %s", e)


# ════════════════════════════════════════════════════════════════
# 主控制器
# ════════════════════════════════════════════════════════════════
class ANFISTrackingController:

    def __init__(self, model_dir: str = '.'):
        self.anfis    = ANFISModel(model_dir)
        self.sensor   = SensorReader()
        self.actuator = ActuatorController()
        self.ina3221  = INA3221Reader()

        # 校正係數（系統性誤差修正，初始為 1.0）
        self.correction = 1.0

        # 近期預測誤差記錄（用於系統性誤差檢測）
        self._recent_errors = []   # [(predicted_W, actual_W), ...]

    # ── 工具 ─────────────────────────────────────────────────────
    def _is_sun_time(self, now: datetime) -> bool:
        return CONFIG['sun_start_hour'] <= now.hour < CONFIG['sun_end_hour']

    def _grid_search_best_angle(
        self, now: datetime, illumination: float
    ) -> Tuple[float, float, float]:
        """
        格網掃描搜尋最佳角度。
        回傳 (best_beta, best_phi, best_predicted_power_W)
        """
        cfg  = CONFIG['search']
        betas    = np.arange(cfg['tilt_min'],    cfg['tilt_max']    + 1e-9,
                             cfg['tilt_step'])
        azimuths = np.arange(cfg['azimuth_min'], cfg['azimuth_max'] + 1e-9,
                             cfg['azimuth_step'])

        best_beta, best_phi, best_power = (
            self.actuator.beta, self.actuator.phi, -1.0
        )

        for b in betas:
            for p in azimuths:
                raw_pred = self.anfis.predict(b, p, now, illumination)
                corrected = raw_pred * self.correction
                if corrected > best_power:
                    best_power = corrected
                    best_beta, best_phi = b, p

        logger.info("格網掃描最佳角度 β=%.1f° φ=%.1f° 預測=%.2fW",
                    best_beta, best_phi, best_power)
        return best_beta, best_phi, best_power

    def _check_systematic_error(self) -> bool:
        """
        檢測近 20 筆誤差是否存在系統性偏差。
        若存在，更新校正係數並回傳 True。
        """
        if len(self._recent_errors) < 10:
            return False

        recent = self._recent_errors[-20:]
        errors = [actual - predicted for predicted, actual in recent]
        mean_err = np.mean(errors)

        if abs(mean_err) > CONFIG['thresholds']['systematic_error']:
            old = self.correction
            if mean_err > 0:
                self.correction = min(CONFIG['corr_max'],
                                      self.correction * 1.05)
            else:
                self.correction = max(CONFIG['corr_min'],
                                      self.correction * 0.95)
            logger.info("系統性誤差 %.2fW → 校正係數 %.3f → %.3f",
                        mean_err, old, self.correction)
            return True
        return False

    def _is_worth_moving(
        self, current_power: float, predicted_power: float
    ) -> bool:
        gain = predicted_power - current_power
        worth = gain > CONFIG['thresholds']['movement_worthiness']
        logger.info("移動評估：當前=%.2fW 預測=%.2fW 增益=%.2fW 值得=%s",
                    current_power, predicted_power, gain, worth)
        return worth

    def _power_meets_expectation(
        self, actual: float, expected: float
    ) -> bool:
        if expected <= 0:
            return True
        ratio = actual / expected
        return ratio >= CONFIG['thresholds']['power_expectation']

    def _fine_tune(self, ldr_cal: Dict[str, float]) -> Tuple[float, float]:
        """
        根據四方向 LDR 校正值微調角度，回傳 (δβ, δφ)。
        """
        cfg   = CONFIG['fine_tune']
        ew    = ldr_cal['east']  - ldr_cal['west']
        ns    = ldr_cal['south'] - ldr_cal['north']
        d_phi  = 0.0
        d_beta = 0.0

        if abs(ew) > cfg['ldr_threshold']:
            d_phi = np.sign(ew) * min(
                cfg['max_az_adj'], abs(ew) * cfg['az_step_per_unit']
            )
        if abs(ns) > cfg['ldr_threshold']:
            d_beta = np.sign(ns) * min(
                cfg['max_tl_adj'], abs(ns) * cfg['tl_step_per_unit']
            )
        return d_beta, d_phi

    # ── 主控制迴圈 ───────────────────────────────────────────────
    def run(self):
        logger.info("=== 實驗組控制器啟動（ANFIS 智慧追日，system_id=%d）===",
                    CONFIG['system_id'])

        while True:
            now = datetime.now()

            # ── Step 1：讀取感測器資料 ───────────────────────────
            ldr_cal, illumination = self.sensor.read_illumination()
            current_power = self.sensor.read_power()
            cur_beta  = self.actuator.beta
            cur_phi   = self.actuator.phi
            logger.info("感測器：照度=%.1f W/m²  功率=%.2fW  β=%.1f° φ=%.1f°",
                        illumination, current_power, cur_beta, cur_phi)

            # ── Step 2 & 3：ANFIS 格網掃描 + 系統性誤差迴圈 ────
            best_beta, best_phi, predicted_power = \
                self._grid_search_best_angle(now, illumination)

            # 記錄本次預測誤差（用上次移動後的實際功率）
            self._recent_errors.append((predicted_power, current_power))
            if len(self._recent_errors) > 100:
                self._recent_errors = self._recent_errors[-50:]

            # 若有系統性誤差，修正後重新掃描一次
            if self._check_systematic_error():
                best_beta, best_phi, predicted_power = \
                    self._grid_search_best_angle(now, illumination)

            # ── Step 4：評估是否值得移動 ────────────────────────
            if not self._is_worth_moving(current_power, predicted_power):
                logger.info("增益不足，等待下一次循環")
                self._upload_cycle_log(now, ldr_cal, illumination,
                                       current_power, best_beta, best_phi,
                                       predicted_power, moved=False,
                                       experience='skip')
                self._wait_or_end(now)
                continue

            # ── Step 5：移動至預測角度 ──────────────────────────
            self.actuator.move_to_azalt(best_beta, best_phi)
            time.sleep(3)   # 等待推桿穩定（非阻塞式等待，3秒已足夠）
            power_after_move = self.sensor.read_power()

            # ── Step 6：判斷發電量是否接近預期 ─────────────────
            if self._power_meets_expectation(power_after_move, predicted_power):
                logger.info("發電量符合預期 %.2fW ≥ %.0f%%×%.2fW，記錄成功",
                            power_after_move,
                            CONFIG['thresholds']['power_expectation'] * 100,
                            predicted_power)
                experience = 'success'
            else:
                # ── Step 7：模糊規則微調 ──────────────────────
                logger.info("發電量低於預期，進行模糊微調")
                d_beta, d_phi = self._fine_tune(ldr_cal)

                if abs(d_beta) > 0.05 or abs(d_phi) > 0.05:
                    pre_tune_beta = self.actuator.beta
                    pre_tune_phi  = self.actuator.phi
                    new_beta = max(CONFIG['search']['tilt_min'],
                                  min(CONFIG['search']['tilt_max'],
                                      self.actuator.beta + d_beta))
                    new_phi  = max(CONFIG['search']['azimuth_min'],
                                  min(CONFIG['search']['azimuth_max'],
                                      self.actuator.phi  + d_phi))
                    self.actuator.move_to_azalt(new_beta, new_phi)

                    # 等待穩定後檢查微調效果（不使用 time.sleep(30)，改為短等）
                    time.sleep(5)
                    power_after_tune = self.sensor.read_power()
                    improvement = power_after_tune - power_after_move

                    if improvement >= CONFIG['thresholds']['fine_tune_improve']:
                        logger.info("微調成功 +%.2fW，保持新位置", improvement)
                        experience = 'fine_tune_success'
                        power_after_move = power_after_tune
                    else:
                        logger.info("微調無效 %.2fW，回退", improvement)
                        self.actuator.move_to_azalt(pre_tune_beta, pre_tune_phi)
                        experience = 'fine_tune_fail'
                else:
                    logger.info("LDR 差值不足，不執行微調")
                    experience = 'no_fine_tune'

            # ── Step 8：上傳 log（替代「更新模型」步驟）────────
            self._upload_cycle_log(now, ldr_cal, illumination,
                                   current_power, best_beta, best_phi,
                                   predicted_power,
                                   moved=True,
                                   power_after_move=power_after_move,
                                   experience=experience)

            # ── Step 9：判斷太陽時間 ──────────────────────────
            self._wait_or_end(now)

    def _wait_or_end(self, now: datetime):
        """等待間隔時間，或太陽時間結束時回歸初始位置"""
        if not self._is_sun_time(now):
            self.actuator.return_to_initial()
            logger.info("太陽時間結束，回歸初始位置，等待 %d 秒",
                        CONFIG['interval_seconds'])
        time.sleep(CONFIG['interval_seconds'])

    def _upload_cycle_log(self, now: datetime,
                          ldr_cal: Dict, illumination: float,
                          current_power: float,
                          best_beta: float, best_phi: float,
                          predicted_power: float,
                          moved: bool = False,
                          power_after_move: float = None,
                          experience: str = ''):
        # 讀取 INA3221（推桿 CH1、Pi CH2）
        try:
            ina_act = self.ina3221.read_actuator()
        except Exception as e:
            logger.warning("推桿電力讀取失敗: %s", e)
            ina_act = {'voltage': None, 'current': None}

        try:
            ina_pi = self.ina3221.read_pi()
        except Exception as e:
            logger.warning("Pi 電力讀取失敗: %s", e)
            ina_pi = {'voltage': None, 'current': None}

        # 讀取 MPPT（太陽能板 V/I）— 必填欄位
        try:
            mppt = read_mppt_power()
        except NotImplementedError:
            logger.warning("MPPT 讀取尚未實作，voltage/current 暫填 0")
            mppt = {'voltage': 0.0, 'current': 0.0, 'power': 0.0}
        except Exception as e:
            logger.warning("MPPT 讀取失敗: %s", e)
            mppt = {'voltage': 0.0, 'current': 0.0, 'power': 0.0}

        payload = {
            'system':                 CONFIG['system_id'],   # Django serializer 必填欄位名為 'system'
            'timestamp':              now.isoformat(),
            # 太陽能板（MPPT RS485）— serializer 必填
            'voltage':                mppt['voltage'],
            'current':                mppt['current'],
            'power_output':           mppt['power'],
            # 光照強度（四 LDR 校正平均，W/m²）
            'light_intensity':        round(illumination, 1),
            # 面板角度（傾角方位角系統）
            'panel_tilt':             round(self.actuator.beta, 2),
            'panel_azimuth':          round(self.actuator.phi,  2),
            # 推桿角度（tip-tilt 系統）
            'ns_actuator_angle':      round(self.actuator.gamma, 2),
            'ew_actuator_angle':      round(self.actuator.zeta,  2),
            # INA3221 CH1 推桿電力
            'actuator_total_voltage': ina_act['voltage'],
            'actuator_total_current': ina_act['current'],
            # INA3221 CH2 樹莓派電力
            'raspberry_pi_voltage':   ina_pi['voltage'],
            'raspberry_pi_current':   ina_pi['current'],
            # 備註（ANFIS 決策資訊）
            'notes': (
                f"exp={experience} moved={moved} "
                f"pred_beta={best_beta:.1f} pred_phi={best_phi:.1f} "
                f"pred_pwr={predicted_power:.1f} "
                f"corr={self.correction:.3f}"
            ),
        }
        upload_log(payload)


# ════════════════════════════════════════════════════════════════
# 進入點
# ════════════════════════════════════════════════════════════════
def main():
    # 模型目錄：預設為本檔案的上上層目錄（raspberry-pi/）
    # model_dir 是放 controller 的目錄（同層的 models/ 子資料夾)
    # 原本 .parent.parent.parent 會跑到家目錄,讓 base/'models/...' 變成 ~/models/... 找不到
    model_dir = str(Path(__file__).resolve().parent)
    controller = ANFISTrackingController(model_dir=model_dir)
    try:
        controller.run()
    except KeyboardInterrupt:
        logger.info("使用者中斷，程式結束")
    except Exception as e:
        logger.exception("未預期錯誤: %s", e)


if __name__ == '__main__':
    main()
