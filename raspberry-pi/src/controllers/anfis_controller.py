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
import threading
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

# RPi.GPIO 給推桿 H 橋驅動用(dual_actuator_upload.py 證實可行)
try:
    import RPi.GPIO as GPIO
    RPI_GPIO_AVAILABLE = True
except ImportError:
    RPI_GPIO_AVAILABLE = False

# ── LDR 模組(spidev + channel calibration + median 抗噪)─────────
try:
    from ldr_module import LDRReader
    LDR_MODULE_AVAILABLE = True
except ImportError:
    LDR_MODULE_AVAILABLE = False

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
    # Django API(預設指向 Tailscale 生產 URL,本機開發改成 http://localhost:8000/api)
    'system_id': 7,
    'api_url': 'https://solar-dashboard.tail7c1eb9.ts.net/api',

    # 模擬模式（True = 允許在無硬體環境下以隨機值測試；False = 生產模式，硬體失敗直接拋例外）
    'simulation_mode': False,

    # 分項模擬旗標（None = 跟隨 simulation_mode;True/False = 個別覆蓋)
    # 用途:LDR 已裝、但 MPPT/推桿尚未時,設 simulate_ldr=False 同時 simulation_mode=True
    'simulate_ldr':      None,    # None / True / False
    'simulate_mppt':     None,
    'simulate_actuator': None,

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

    # 時間(2026-06-23 起,end 從 18 → 19 抓傍晚日落充電窗口)
    'sun_start_hour':   6,
    'sun_end_hour':    19,
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

    # MPPT RS485 設定（EPEVER Tracer-AN-G3 over /dev/ttyUSB0）
    'mppt': {
        'port':     '/dev/ttyUSB0',
        'baudrate': 115200,
        'slave':    1,
    },

    # 推桿 GPIO 設定(2026-06-20 raspberrypi-1 現場實測;dual_actuator_upload.py 命名反了,以此為準)
    # H 橋 4-pin 驅動:extend = blue_high + brown_low HIGH;retract = brown_high + blue_low HIGH
    'actuator': {
        # NS / 南北 / 傾角(γ)— 對應 ANFIS β 主要組成
        'ns_brown_high': 17, 'ns_blue_high': 27,
        'ns_brown_low':  22, 'ns_blue_low':  23,
        # EW / 東西 / 方位角(ζ)
        'ew_brown_high': 5,  'ew_blue_high': 6,
        'ew_brown_low': 13,  'ew_blue_low': 19,
        # 動作時長(秒/度)— 開迴路估算,需現場校正
        'ns_sec_per_deg': 0.5,
        'ew_sec_per_deg': 0.5,
        # 方向慣例:+1 = γ↑ 用 extend(往南),如果實測方向反了改 -1
        'ns_extend_dir':  +1,
        'ew_extend_dir':  +1,
        # 安全限制
        'min_move_deg':   0.5,    # 角度差小於此值不動(避免抖動)
        'max_move_sec':   30.0,   # 單次最大移動秒數

        # 霍爾感測器(2026-06-23 新增,閉迴路位置回授)
        'hall': {
            'enabled':       True,   # False 退回開迴路時間驅動
            'pulses_per_mm': 54.19,  # dual_actuator_upload.py 實測值
            # NS 推桿(南北/傾角):24/25 兩線
            'ns_hall1':      24, 'ns_hall2': 25,
            'ns_stroke_mm':  206,
            # EW 推桿(東西/方位):16/26 兩線
            'ew_hall1':      16, 'ew_hall2': 26,
            'ew_stroke_mm':  406,
            # 閉迴路移動最小門檻(mm)+ 安全 timeout
            'min_move_mm':   2.0,
            'move_timeout':  30.0,
            'tolerance_mm':  1.5,    # 到位容差
        },
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


def _is_simulating(component: str) -> bool:
    """
    判斷某個元件(ldr / mppt / actuator)是否該用模擬值。
    優先看 simulate_<component>(若 None 則 fallback 到 simulation_mode 總開關)。

    例:simulation_mode=True、simulate_ldr=False → LDR 走真實硬體,其他模擬。
    """
    key = f'simulate_{component}'
    override = CONFIG.get(key)
    if override is not None:
        return bool(override)
    return bool(CONFIG.get('simulation_mode', False))


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
    # 2026-07-14 修正 off-by-1 bug(舊值都 +1,實際 INA3221 datasheet:)
    # 0x01=CH1 SHUNT, 0x02=CH1 BUS, 0x03=CH2 SHUNT, 0x04=CH2 BUS, 0x05=CH3 SHUNT, 0x06=CH3 BUS
    _REG_SHUNT = {1: 0x01, 2: 0x03, 3: 0x05}
    _REG_BUS   = {1: 0x02, 2: 0x04, 3: 0x06}
    _LSB_SHUNT = 40e-6   # 40 µV / LSB
    _LSB_BUS   = 8e-3    #  8 mV / LSB

    def __init__(self):
        cfg = CONFIG['ina3221']
        self._addr  = cfg['i2c_addr']
        self._shunt = cfg['shunt_ohm']
        self._bus   = None

        # INA3221 跟著 mppt / actuator 共用「電力量測」這個元件分類,
        # 任何一個不模擬就會試著啟動 I2C
        if HARDWARE_AVAILABLE and not (_is_simulating('mppt') and _is_simulating('actuator')):
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
        """讀取指定通道電壓（V）與電流（A）。CH1=推桿、CH2=Pi,共用 actuator 模擬旗標"""
        if _is_simulating('actuator'):
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
# Module-level singleton(避免 read_power 與 read_mppt_power 同時開 serial 打架)
_mppt_instrument = None


def read_mppt_power() -> dict:
    """
    從 EPEVER Tracer-AN-G3 經 Modbus RTU 讀 PV 端 + 電池端 V/I/P。
    回傳 {
        'voltage': PV V,
        'current': PV A,
        'power':   PV W,
        'batt_voltage': 電池 V,
        'batt_current': 充電電流 A,(>0 充電,< 0 放電)
        'batt_power':   充電功率 W,
    }

    Register map(EPEVER Tracer-AN-G3 input registers, function code 4):
        0x3100 = PV voltage           (÷100 → V)
        0x3101 = PV current           (÷100 → A)
        0x3102/0x3103 = PV power L/H  (組合 ÷100 → W)
        0x3104 = Battery voltage      (÷100 → V)
        0x3105 = Battery charge curr  (signed, ÷100 → A)
        0x3106/0x3107 = Battery power L/H (組合 ÷100 → W)
        0x311A = Battery SOC          (整數 0-100,直接讀不除)
    """
    if _is_simulating('mppt'):
        import random
        v = round(random.uniform(14.0, 18.0), 2)
        i = round(random.uniform(0.5, 5.0),   2)
        bv = round(random.uniform(12.5, 14.5), 2)
        bi = round(random.uniform(0.0, 3.0),   2)
        soc = random.randint(85, 100)
        return {
            'voltage': v, 'current': i, 'power': round(v * i, 2),
            'batt_voltage': bv, 'batt_current': bi,
            'batt_power': round(bv * bi, 2),
            'batt_soc': soc,
        }

    global _mppt_instrument
    try:
        if _mppt_instrument is None:
            import minimalmodbus
            cfg = CONFIG.get('mppt', {})
            port  = cfg.get('port',     '/dev/ttyUSB0')
            slave = cfg.get('slave',    1)
            baud  = cfg.get('baudrate', 115200)
            _mppt_instrument = minimalmodbus.Instrument(port, slave)
            _mppt_instrument.serial.baudrate = baud
            _mppt_instrument.serial.bytesize = 8
            _mppt_instrument.serial.parity   = 'N'
            _mppt_instrument.serial.stopbits = 1
            _mppt_instrument.serial.timeout  = 1.0
            _mppt_instrument.mode = minimalmodbus.MODE_RTU
            _mppt_instrument.clear_buffers_before_each_transaction = True
            logger.info("EPEVER MPPT 連線: %s baud=%d slave=%d", port, baud, slave)

        # PV 端
        v   = _mppt_instrument.read_register(0x3100, 0, functioncode=4) / 100.0
        i   = _mppt_instrument.read_register(0x3101, 0, functioncode=4) / 100.0
        p_l = _mppt_instrument.read_register(0x3102, 0, functioncode=4)
        p_h = _mppt_instrument.read_register(0x3103, 0, functioncode=4)
        power = ((p_h << 16) | p_l) / 100.0

        # 電池端(新增)
        bv = _mppt_instrument.read_register(0x3104, 0, functioncode=4) / 100.0
        # 充電電流可能是 signed(2 補數),需手動處理
        bi_raw = _mppt_instrument.read_register(0x3105, 0, functioncode=4)
        if bi_raw > 0x7FFF:
            bi_raw -= 0x10000
        bi = bi_raw / 100.0
        bp_l = _mppt_instrument.read_register(0x3106, 0, functioncode=4)
        bp_h = _mppt_instrument.read_register(0x3107, 0, functioncode=4)
        bp = ((bp_h << 16) | bp_l) / 100.0

        # SOC (0-100,整數,EPEVER 內建估算)
        try:
            soc = _mppt_instrument.read_register(0x311A, 0, functioncode=4)
        except Exception:
            soc = None

        logger.info("MPPT 讀取: PV V=%.2fV I=%.2fA P=%.2fW | Batt V=%.2fV I=%.2fA P=%.2fW SOC=%s%%",
                    v, i, power, bv, bi, bp, soc if soc is not None else 'N/A')
        return {
            'voltage': round(v, 2), 'current': round(i, 2), 'power': round(power, 2),
            'batt_voltage': round(bv, 2), 'batt_current': round(bi, 2),
            'batt_power':   round(bp, 2),
            'batt_soc':     soc,
        }
    except Exception as e:
        logger.warning("MPPT 讀取失敗 fallback 0: %s", e)
        return {
            'voltage': 0.0, 'current': 0.0, 'power': 0.0,
            'batt_voltage': 0.0, 'batt_current': 0.0, 'batt_power': 0.0,
            'batt_soc': None,
        }


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
        # 新版優先用 ldr_module(spidev + channel calibration + median 抗噪)
        # 舊版 fallback 用 gpiozero.MCP3008 single-shot 讀取
        self._ldr_reader = None
        if LDR_MODULE_AVAILABLE and not _is_simulating('ldr'):
            try:
                self._ldr_reader = LDRReader(samples_per_read=20,
                                             spi_bus=cfg['spi_port'],
                                             spi_device=cfg['device'])
                logger.info("LDR 讀取:使用 ldr_module(median 20 取樣 + channel calibration)")
            except Exception as e:
                logger.warning("ldr_module 初始化失敗,fallback gpiozero:%s", e)
        if self._ldr_reader is None and HARDWARE_AVAILABLE:
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
        """讀取 ADC 原始值(0-1023)。優先用 ldr_module(median + calibration),fallback gpiozero。"""
        if _is_simulating('ldr'):
            import random
            base = random.uniform(300, 800)
            return {d: round(base + random.uniform(-60, 60))
                    for d in ('east', 'west', 'south', 'north')}

        # 新版:ldr_module 已套校正,直接回傳
        if self._ldr_reader is not None:
            try:
                return self._ldr_reader.read_calibrated()
            except Exception as e:
                raise RuntimeError(f"LDR 讀取失敗(ldr_module): {e}") from e

        # 舊版 fallback:gpiozero single-shot(無校正、無 median)
        if not HARDWARE_AVAILABLE:
            raise RuntimeError(
                "硬體不可用(gpiozero / spidev 未安裝),若要測試請在 CONFIG 中設定 simulate_ldr=True"
            )
        try:
            return {d: round(self._adc[d].value * 1023)
                    for d in ('east', 'west', 'south', 'north')}
        except Exception as e:
            raise RuntimeError(f"LDR 讀取失敗(感測器可能斷線或接觸不良): {e}") from e

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
        """讀取目前面板功率(W),委派給 read_mppt_power() 避免 serial 打架"""
        return float(read_mppt_power().get('power', 0.0))


# ════════════════════════════════════════════════════════════════
# 推桿控制器
# ════════════════════════════════════════════════════════════════
class HallSensorMonitor:
    """
    霍爾感測器位置監控(2026-06-23 新增,從 dual_actuator_upload.py 移植 + 改良)。

    背景 thread 偵測 GPIO 邊緣,依當前驅動方向(由 set_direction 提示)加減 pulse,
    換算成位置 mm。初始位置由 ActuatorController 從 CONFIG['initial_position'] 設定,
    不做 homing(假設啟動時推桿位置已知)。
    """

    def __init__(self, name: str, hall1_pin: int, hall2_pin: int,
                 pulses_per_mm: float, stroke_mm: float,
                 initial_position_mm: float = 0.0):
        self.name = name
        self.hall1_pin     = hall1_pin
        self.hall2_pin     = hall2_pin
        self.pulses_per_mm = pulses_per_mm
        self.stroke_mm     = stroke_mm
        self.pulse_count   = int(initial_position_mm * pulses_per_mm)
        self.position_mm   = initial_position_mm
        self._direction    = +1     # +1=extend / -1=retract;由 ActuatorController 設定
        self.monitoring    = False
        self._thread       = None

        if RPI_GPIO_AVAILABLE:
            try:
                GPIO.setup([hall1_pin, hall2_pin], GPIO.IN,
                           pull_up_down=GPIO.PUD_UP)
                self._last_hall1 = GPIO.input(hall1_pin)
                self.monitoring  = True
                self._thread = threading.Thread(target=self._monitor_loop, daemon=True)
                self._thread.start()
                logger.info("Hall %s 啟動: pin=%d,%d init=%.1f mm (stroke=%.0f mm)",
                            name, hall1_pin, hall2_pin, initial_position_mm, stroke_mm)
            except Exception as e:
                logger.warning("Hall %s 初始化失敗: %s", name, e)

    def set_direction(self, direction: int):
        """提示當前驅動方向 — 在打 GPIO 之前呼叫"""
        self._direction = +1 if direction >= 0 else -1

    def _monitor_loop(self):
        """偵測 hall1 邊緣 → 加減 pulse"""
        while self.monitoring:
            try:
                hall1 = GPIO.input(self.hall1_pin)
                if hall1 != self._last_hall1:
                    self.pulse_count += self._direction
                    self.position_mm  = self.pulse_count / self.pulses_per_mm
                    # 限制在 [0, stroke]
                    self.position_mm  = max(0.0, min(self.stroke_mm, self.position_mm))
                    self._last_hall1  = hall1
                time.sleep(0.0001)
            except Exception:
                time.sleep(0.01)

    def get_position_mm(self) -> float:
        return self.position_mm

    def get_position_percent(self) -> float:
        return (self.position_mm / self.stroke_mm) * 100.0 if self.stroke_mm > 0 else 0.0

    def reset_position(self, position_mm: float = 0.0):
        self.position_mm = position_mm
        self.pulse_count = int(position_mm * self.pulses_per_mm)

    def stop(self):
        self.monitoring = False


class ActuatorController:
    """
    雙軸推桿控制（同對照組，但以傾角方位角為主要介面）。
    外部呼叫 move_to_azalt(beta, phi) 即可。

    2026-06-20 實作 _move_to_tiptilt 開迴路時間驅動(取代原 stub):
      - NS pin group(17/27/22/23):γ extend → 南,retract → 北
      - EW pin group(5/6/13/19): ζ extend → 西,retract → 東
      - 時長 = abs(角度差) × CONFIG['actuator']['<axis>_sec_per_deg']
    """

    def __init__(self):
        init = CONFIG['initial_position']
        self.gamma = init['gamma']
        self.zeta  = init['zeta']
        # 目前傾角/方位角（由 tip-tilt 換算）
        self.beta, self.phi = tiptilt_to_azalt(self.gamma, self.zeta)

        # GPIO 初始化(只在真實模式且 RPi.GPIO 可用時)
        self._gpio_ready = False
        self.ns_hall = None
        self.ew_hall = None

        if RPI_GPIO_AVAILABLE and not _is_simulating('actuator'):
            try:
                cfg = CONFIG['actuator']
                GPIO.setmode(GPIO.BCM)
                GPIO.setwarnings(False)
                self._all_pins = [
                    cfg['ns_brown_high'], cfg['ns_blue_high'],
                    cfg['ns_brown_low'],  cfg['ns_blue_low'],
                    cfg['ew_brown_high'], cfg['ew_blue_high'],
                    cfg['ew_brown_low'],  cfg['ew_blue_low'],
                ]
                GPIO.setup(self._all_pins, GPIO.OUT)
                GPIO.output(self._all_pins, GPIO.LOW)
                self._gpio_ready = True
                logger.info("推桿 GPIO 初始化成功 NS=%s EW=%s",
                            self._all_pins[:4], self._all_pins[4:])

                # 霍爾感測器初始化(2026-06-23 新增)
                hcfg = cfg.get('hall', {})
                if hcfg.get('enabled', False):
                    # 從 CONFIG 初始 γ/ζ 算對應 mm 位置
                    ns_init_mm = self._gamma_to_mm(self.gamma)
                    ew_init_mm = self._zeta_to_mm(self.zeta)
                    self.ns_hall = HallSensorMonitor(
                        'NS', hcfg['ns_hall1'], hcfg['ns_hall2'],
                        hcfg['pulses_per_mm'], hcfg['ns_stroke_mm'], ns_init_mm)
                    self.ew_hall = HallSensorMonitor(
                        'EW', hcfg['ew_hall1'], hcfg['ew_hall2'],
                        hcfg['pulses_per_mm'], hcfg['ew_stroke_mm'], ew_init_mm)
                    logger.info("霍爾閉迴路啟用: NS init=%.1fmm EW init=%.1fmm",
                                ns_init_mm, ew_init_mm)
            except Exception as e:
                logger.warning("推桿 GPIO 初始化失敗:%s", e)

    # ── 角度 ↔ mm 線性映射 ────────────────────────────────────────
    def _gamma_to_mm(self, gamma: float) -> float:
        """γ(度)→ NS 推桿伸長量(mm),線性映射 γ_min→0、γ_max→stroke"""
        hcfg = CONFIG['actuator']['hall']
        g_min = CONFIG['gamma_min']
        g_max = CONFIG['gamma_max']
        return ((gamma - g_min) / (g_max - g_min)) * hcfg['ns_stroke_mm']

    def _zeta_to_mm(self, zeta: float) -> float:
        hcfg = CONFIG['actuator']['hall']
        z_min = CONFIG['zeta_min']
        z_max = CONFIG['zeta_max']
        return ((zeta - z_min) / (z_max - z_min)) * hcfg['ew_stroke_mm']

    def _mm_to_gamma(self, mm: float) -> float:
        hcfg = CONFIG['actuator']['hall']
        g_min = CONFIG['gamma_min']
        g_max = CONFIG['gamma_max']
        return g_min + (mm / hcfg['ns_stroke_mm']) * (g_max - g_min)

    def _mm_to_zeta(self, mm: float) -> float:
        hcfg = CONFIG['actuator']['hall']
        z_min = CONFIG['zeta_min']
        z_max = CONFIG['zeta_max']
        return z_min + (mm / hcfg['ew_stroke_mm']) * (z_max - z_min)

    def get_ns_position_mm(self) -> Optional[float]:
        return self.ns_hall.get_position_mm() if self.ns_hall else None

    def get_ew_position_mm(self) -> Optional[float]:
        return self.ew_hall.get_position_mm() if self.ew_hall else None

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

    # ── 硬體驅動(2026-06-20 開迴路時間驅動實作)──────────────────────
    def _drive_pins(self, pins: tuple, action: str, duration: float):
        """
        pins = (brown_high, blue_high, brown_low, blue_low)
        action ∈ {'extend','retract'};extend = 南/西,retract = 北/東
        """
        bh, blh, bl, bll = pins
        if action == 'extend':
            GPIO.output([bh, bll], GPIO.LOW)
            time.sleep(0.01)
            GPIO.output([blh, bl], GPIO.HIGH)
        elif action == 'retract':
            GPIO.output([blh, bl], GPIO.LOW)
            time.sleep(0.01)
            GPIO.output([bh, bll], GPIO.HIGH)
        time.sleep(duration)
        # 結束停止(四 pin 都 LOW)
        GPIO.output([bh, blh, bl, bll], GPIO.LOW)

    def _drive_until_target(self, pins: tuple, hall: 'HallSensorMonitor',
                            target_mm: float, direction: int,
                            timeout: float, tolerance: float) -> dict:
        """
        閉迴路驅動:打 GPIO + 同時 poll hall,到位即停。
        direction: +1 extend / -1 retract
        回傳 stats {'final_mm', 'actual_delta', 'duration'}
        """
        bh, blh, bl, bll = pins
        # 提示 hall 當前方向(讓 pulse 計數正確加減)
        hall.set_direction(direction)

        # 啟動驅動
        if direction > 0:
            GPIO.output([bh, bll], GPIO.LOW)
            time.sleep(0.01)
            GPIO.output([blh, bl], GPIO.HIGH)
        else:
            GPIO.output([blh, bl], GPIO.LOW)
            time.sleep(0.01)
            GPIO.output([bh, bll], GPIO.HIGH)

        start_mm = hall.get_position_mm()
        start_t = time.time()
        last_log = start_t

        while True:
            current_mm = hall.get_position_mm()
            elapsed = time.time() - start_t

            # 到位判斷:依方向看是否已過 target
            reached = (current_mm >= target_mm - tolerance) if direction > 0 \
                      else (current_mm <= target_mm + tolerance)
            if reached:
                break
            if elapsed > timeout:
                logger.warning("Hall 閉迴路超時:%s 當前=%.1fmm 目標=%.1fmm",
                               hall.name, current_mm, target_mm)
                break

            # 每秒 log 一次進度
            if time.time() - last_log > 1.0:
                logger.debug("  %s 移動中 %.1f → %.1f mm (目標 %.1f)",
                             hall.name, start_mm, current_mm, target_mm)
                last_log = time.time()
            time.sleep(0.01)

        # 停
        GPIO.output([bh, blh, bl, bll], GPIO.LOW)
        final_mm = hall.get_position_mm()
        return {
            'final_mm': final_mm,
            'actual_delta': final_mm - start_mm,
            'duration': time.time() - start_t,
        }

    def _move_to_tiptilt(self, target_gamma: float, target_zeta: float):
        """
        移動到 (target_gamma, target_zeta):
          - 有 hall + enabled → 閉迴路位置驅動(到位即停)
          - 無 hall → fallback 開迴路時間驅動
        """
        if _is_simulating('actuator'):
            return
        if not self._gpio_ready:
            logger.warning("推桿 GPIO 未就緒,略過實際移動")
            return

        cfg  = CONFIG['actuator']
        hcfg = cfg.get('hall', {})
        use_hall = hcfg.get('enabled', False) and self.ns_hall is not None

        if use_hall:
            self._move_closed_loop(target_gamma, target_zeta)
        else:
            self._move_open_loop(target_gamma, target_zeta)

    def _move_closed_loop(self, target_gamma: float, target_zeta: float):
        """閉迴路:用 hall 真實位置回授,到位即停"""
        cfg  = CONFIG['actuator']
        hcfg = cfg['hall']
        min_mm    = hcfg['min_move_mm']
        timeout   = hcfg['move_timeout']
        tol       = hcfg['tolerance_mm']

        # NS / γ
        target_ns_mm = self._gamma_to_mm(target_gamma)
        current_ns_mm = self.ns_hall.get_position_mm()
        delta_ns_mm = (target_ns_mm - current_ns_mm) * cfg['ns_extend_dir']
        if abs(delta_ns_mm) > min_mm:
            direction = +1 if delta_ns_mm > 0 else -1
            action_txt = '往南 extend' if direction > 0 else '往北 retract'
            ns_pins = (cfg['ns_brown_high'], cfg['ns_blue_high'],
                       cfg['ns_brown_low'],  cfg['ns_blue_low'])
            logger.info("NS 閉迴路 %s: %.1f → %.1f mm (Δ%+.1fmm, γ→%.1f°)",
                        action_txt, current_ns_mm, target_ns_mm,
                        delta_ns_mm, target_gamma)
            stats = self._drive_until_target(ns_pins, self.ns_hall,
                                             target_ns_mm, direction,
                                             timeout, tol)
            logger.info("  NS 完成 final=%.1fmm Δreal=%+.1fmm t=%.2fs",
                        stats['final_mm'], stats['actual_delta'],
                        stats['duration'])

        # EW / ζ
        target_ew_mm = self._zeta_to_mm(target_zeta)
        current_ew_mm = self.ew_hall.get_position_mm()
        delta_ew_mm = (target_ew_mm - current_ew_mm) * cfg['ew_extend_dir']
        if abs(delta_ew_mm) > min_mm:
            direction = +1 if delta_ew_mm > 0 else -1
            action_txt = '往西 extend' if direction > 0 else '往東 retract'
            ew_pins = (cfg['ew_brown_high'], cfg['ew_blue_high'],
                       cfg['ew_brown_low'],  cfg['ew_blue_low'])
            logger.info("EW 閉迴路 %s: %.1f → %.1f mm (Δ%+.1fmm, ζ→%.1f°)",
                        action_txt, current_ew_mm, target_ew_mm,
                        delta_ew_mm, target_zeta)
            stats = self._drive_until_target(ew_pins, self.ew_hall,
                                             target_ew_mm, direction,
                                             timeout, tol)
            logger.info("  EW 完成 final=%.1fmm Δreal=%+.1fmm t=%.2fs",
                        stats['final_mm'], stats['actual_delta'],
                        stats['duration'])

    def _move_open_loop(self, target_gamma: float, target_zeta: float):
        """fallback:開迴路時間驅動 = 角度差 × sec_per_deg"""
        cfg = CONFIG['actuator']
        d_gamma = (target_gamma - self.gamma) * cfg['ns_extend_dir']
        d_zeta  = (target_zeta  - self.zeta)  * cfg['ew_extend_dir']
        min_d   = cfg['min_move_deg']
        max_t   = cfg['max_move_sec']

        if abs(d_gamma) > min_d:
            t = min(abs(d_gamma) * cfg['ns_sec_per_deg'], max_t)
            action = 'extend' if d_gamma > 0 else 'retract'
            direction_txt = '南' if action == 'extend' else '北'
            ns_pins = (cfg['ns_brown_high'], cfg['ns_blue_high'],
                       cfg['ns_brown_low'],  cfg['ns_blue_low'])
            logger.info("NS 推桿 %s(往%s)%.2f 秒 (Δγ=%+.2f°)",
                        action, direction_txt, t, d_gamma)
            self._drive_pins(ns_pins, action, t)

        if abs(d_zeta) > min_d:
            t = min(abs(d_zeta) * cfg['ew_sec_per_deg'], max_t)
            action = 'extend' if d_zeta > 0 else 'retract'
            direction_txt = '西' if action == 'extend' else '東'
            ew_pins = (cfg['ew_brown_high'], cfg['ew_blue_high'],
                       cfg['ew_brown_low'],  cfg['ew_blue_low'])
            logger.info("EW 推桿 %s(往%s)%.2f 秒 (Δζ=%+.2f°)",
                        action, direction_txt, t, d_zeta)
            self._drive_pins(ew_pins, action, t)


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

            # ── ★ 太陽時間檢查(2026-07-14 修:移到決策之前)────────
            # 非白天:只記錄不移動,第一次進夜間才回歸初始位置一次
            if not self._is_sun_time(now):
                if not getattr(self, '_night_mode', False):
                    logger.info("進入非太陽時間(%d:00~%d:00),回歸初始位置一次",
                                CONFIG['sun_start_hour'], CONFIG['sun_end_hour'])
                    self.actuator.return_to_initial()
                    self._night_mode = True
                logger.info("非太陽時間,只記錄不移動")
                self._upload_cycle_log(now, ldr_cal, illumination,
                                       current_power,
                                       self.actuator.beta, self.actuator.phi,
                                       0.0, moved=False,
                                       experience='night_idle')
                time.sleep(CONFIG['interval_seconds'])
                continue
            else:
                if getattr(self, '_night_mode', False):
                    logger.info("進入太陽時間,恢復追日決策")
                self._night_mode = False

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
        """等待間隔時間。太陽時間結束的處理已提前到 run() 迴圈開頭,這裡只 sleep。"""
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
            mppt = {'voltage': 0.0, 'current': 0.0, 'power': 0.0,
                    'batt_voltage': 0.0, 'batt_current': 0.0, 'batt_power': 0.0,
                    'batt_soc': None}

        payload = {
            'system':                 CONFIG['system_id'],   # Django serializer 必填欄位名為 'system'
            'timestamp':              now.isoformat(),
            # 太陽能板（MPPT RS485）— serializer 必填
            'voltage':                mppt['voltage'],
            'current':                mppt['current'],
            'power_output':           mppt['power'],
            # 電池端讀值(2026-06-23 補,真實判斷 MPPT 是否在 float 模式的依據)
            'battery_voltage':        mppt.get('batt_voltage', 0.0),
            'battery_current':        mppt.get('batt_current', 0.0),
            'battery_power':          mppt.get('batt_power', 0.0),
            'battery_soc':            mppt.get('batt_soc'),  # 0x311A,0-100%
            # 光照強度(四 LDR 校正平均,W/m² 或 lux)
            'light_intensity':        round(illumination, 1),
            # 四方位獨立讀值(2026-07-15 改成 raw ADC 0-1023,對照組差動 + ANFIS 訓練可用)
            # ldr_cal 是「raw × slope」,反除 slope 拿回 raw ADC 給 dashboard 顯示;
            # ANFIS 決策層仍用 ldr_cal 不受影響
            'light_north':            round(ldr_cal.get('north', 0.0) / CONFIG['ldr_calibration']['north']['slope'], 1),
            'light_east':             round(ldr_cal.get('east',  0.0) / CONFIG['ldr_calibration']['east']['slope'],  1),
            'light_west':             round(ldr_cal.get('west',  0.0) / CONFIG['ldr_calibration']['west']['slope'],  1),
            'light_south':            round(ldr_cal.get('south', 0.0) / CONFIG['ldr_calibration']['south']['slope'], 1),
            # 面板角度（傾角方位角系統）
            'panel_tilt':             round(self.actuator.beta, 2),
            'panel_azimuth':          round(self.actuator.phi,  2),
            # 推桿角度（tip-tilt 系統）
            'ns_actuator_angle':      round(self.actuator.gamma, 2),
            'ew_actuator_angle':      round(self.actuator.zeta,  2),
            # 推桿真實伸展長度(mm)— 來自霍爾感測器,若 hall 未啟用則 null
            'ns_actuator_extension':  (round(self.actuator.get_ns_position_mm(), 1)
                                       if self.actuator.get_ns_position_mm() is not None else None),
            'ew_actuator_extension':  (round(self.actuator.get_ew_position_mm(), 1)
                                       if self.actuator.get_ew_position_mm() is not None else None),
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
