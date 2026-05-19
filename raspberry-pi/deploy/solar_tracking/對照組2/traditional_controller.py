#!/usr/bin/env python3
"""
對照組控制器 — 傳統 LDR 差值追日
Control Group (system_id=6)

流程圖邏輯：
    開始
    → 判斷太陽時間？否 → 回歸東方初始位置 → 等待
    → 讀取四方向 LDR
    → 計算東西差異 → 超過閾值？→ 東>西 向東轉 / 西>東 向西轉
    → 計算南北差異 → 超過閾值？→ 南>北 向南轉 / 北>南 向北轉
    → 上傳資料到 Django API
    → 等待 10 分鐘

硬體連接：
    MCP3008 CH0 = 東 (East)   LDR
    MCP3008 CH1 = 西 (West)   LDR
    MCP3008 CH2 = 南 (South)  LDR
    MCP3008 CH3 = 北 (North)  LDR
    INA3221  CH1 = 兩隻推桿合計電力
    INA3221  CH2 = 樹莓派本身電力
    RS485-to-USB  = MPPT 控制器（太陽能板 V/I）

座標系統（tip-tilt）：
    γ  南北向傾角，+北 / −南，範圍 ±30°
    ζ  東西向傾角，+東 / −西，範圍 ±30°
"""

import time
import logging
import requests
from datetime import datetime
from pathlib import Path

# ── 硬體導入（僅 Raspberry Pi 可用）─────────────────────────────
try:
    from gpiozero import MCP3008
    import smbus2
    HARDWARE_AVAILABLE = True
except ImportError:
    HARDWARE_AVAILABLE = False

# ── 設定 ─────────────────────────────────────────────────────────
CONFIG = {
    # Django API
    'system_id': 4,
    'api_url': 'https://solar-dashboard.tail7c1eb9.ts.net/api',

    # 模擬模式（True = 允許在無硬體環境下以隨機值測試；False = 生產模式，硬體失敗直接拋例外）
    'simulation_mode': False,

    # MCP3008 通道
    'mcp3008': {
        'east_ch':  0,   # CH0
        'west_ch':  1,   # CH1
        'south_ch': 2,   # CH2
        'north_ch': 3,   # CH3
        'spi_port': 0,
        'device':   0,
    },

    # LDR 閾值（ADC 單位 0-1023，超過才移動）
    'threshold': 50,

    # LDR ADC → W/m² 轉換係數（簡易線性校正，用於 light_intensity 欄位上傳）
    # W/m² = ADC × slope + intercept
    'ldr_sensitivity': {'slope': 1.15, 'intercept': 0.0},

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

    # 太陽時間
    'sun_start_hour': 6,
    'sun_end_hour':  18,

    # 控制間隔（秒）
    'interval_seconds': 600,   # 10 分鐘

    # 東方初始位置（tip-tilt 座標，度）
    'initial_position': {
        'gamma': -15.0,
        'zeta':   30.0,
    },

    # 推桿每次移動步進量（度）
    'step_deg': 5.0,

    # tip-tilt 物理限制（±30°）
    'gamma_min': -30.0, 'gamma_max': 30.0,
    'zeta_min':  -30.0, 'zeta_max':  30.0,
}

# ── 日誌 ─────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    handlers=[
        logging.FileHandler('traditional_controller.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)


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
        """讀取 16-bit 暫存器（big-endian，有符號）"""
        data = self._bus.read_i2c_block_data(self._addr, reg, 2)
        raw  = (data[0] << 8) | data[1]
        return raw - 0x10000 if raw > 0x7FFF else raw

    def read_channel(self, ch: int) -> dict:
        """
        讀取指定通道的匯流排電壓（V）與電流（A）。
        回傳 {'voltage': float, 'current': float}
        """
        if CONFIG['simulation_mode']:
            import random
            return {
                'voltage': round(random.uniform(11.5, 12.5), 3),
                'current': round(random.uniform(0.1, 2.0),   3),
            }

        if self._bus is None:
            raise RuntimeError(
                f"INA3221 未初始化（硬體不可用），"
                "若要測試請設定 simulation_mode=True"
            )

        try:
            shunt_raw = self._read_reg_signed(self._REG_SHUNT[ch])
            bus_raw   = self._read_reg_signed(self._REG_BUS[ch])
            shunt_v   = (shunt_raw >> 3) * self._LSB_SHUNT   # V
            bus_v     = (bus_raw   >> 3) * self._LSB_BUS     # V
            current   = shunt_v / self._shunt                # A
            return {
                'voltage': round(bus_v,   3),
                'current': round(current, 4),
            }
        except Exception as e:
            raise RuntimeError(f"INA3221 CH{ch} 讀取失敗: {e}") from e

    def read_actuator(self) -> dict:
        """CH1：推桿電力"""
        return self.read_channel(CONFIG['ina3221']['act_channel'])

    def read_pi(self) -> dict:
        """CH2：樹莓派電力"""
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
# 推桿控制器
# ════════════════════════════════════════════════════════════════
class ActuatorController:
    """
    雙軸推桿控制器。
    角度以 tip-tilt 系統記錄（γ = 南北向, ζ = 東西向）。
    """

    def __init__(self):
        self.gamma = CONFIG['initial_position']['gamma']
        self.zeta  = CONFIG['initial_position']['zeta']

    def move_east(self) -> bool:
        new = min(self.zeta + CONFIG['step_deg'], CONFIG['zeta_max'])
        if new == self.zeta:
            logger.info("向東已達極限")
            return False
        self._drive_ew('+')
        self.zeta = new
        logger.info(f"向東 → ζ={self.zeta:.1f}°")
        return True

    def move_west(self) -> bool:
        new = max(self.zeta - CONFIG['step_deg'], CONFIG['zeta_min'])
        if new == self.zeta:
            logger.info("向西已達極限")
            return False
        self._drive_ew('-')
        self.zeta = new
        logger.info(f"向西 → ζ={self.zeta:.1f}°")
        return True

    def move_south(self) -> bool:
        new = max(self.gamma - CONFIG['step_deg'], CONFIG['gamma_min'])
        if new == self.gamma:
            logger.info("向南已達極限")
            return False
        self._drive_ns('-')
        self.gamma = new
        logger.info(f"向南 → γ={self.gamma:.1f}°")
        return True

    def move_north(self) -> bool:
        new = min(self.gamma + CONFIG['step_deg'], CONFIG['gamma_max'])
        if new == self.gamma:
            logger.info("向北已達極限")
            return False
        self._drive_ns('+')
        self.gamma = new
        logger.info(f"向北 → γ={self.gamma:.1f}°")
        return True

    def return_to_initial(self):
        init_g = CONFIG['initial_position']['gamma']
        init_z = CONFIG['initial_position']['zeta']
        if self.gamma != init_g or self.zeta != init_z:
            self._move_to(init_g, init_z)
            self.gamma = init_g
            self.zeta  = init_z
            logger.info(f"回歸初始位置 γ={self.gamma:.1f}° ζ={self.zeta:.1f}°")

    # ── 硬體驅動（TODO：填入實際 GPIO 控制）────────────────────
    def _drive_ew(self, direction: str):
        """
        東西向推桿控制。direction: '+' 向東, '-' 向西
        TODO：
            if direction == '+':
                GPIO.output(EW_FWD_PIN, GPIO.HIGH)
                time.sleep(MOVE_DURATION)
                GPIO.output(EW_FWD_PIN, GPIO.LOW)
            else:
                GPIO.output(EW_REV_PIN, GPIO.HIGH)
                time.sleep(MOVE_DURATION)
                GPIO.output(EW_REV_PIN, GPIO.LOW)
        """
        pass

    def _drive_ns(self, direction: str):
        """
        南北向推桿控制。direction: '+' 向北, '-' 向南
        TODO：同 _drive_ew
        """
        pass

    def _move_to(self, target_gamma: float, target_zeta: float):
        """
        閉迴路移動到目標角度（利用霍爾感測器回授）。
        TODO：建立行程-角度對照表後實作。
        """
        pass


# ════════════════════════════════════════════════════════════════
# 感測器讀取
# ════════════════════════════════════════════════════════════════
class LDRReader:
    """MCP3008 四通道 LDR 讀取器（ADC 單位 0-1023）"""

    def __init__(self):
        cfg = CONFIG['mcp3008']
        if HARDWARE_AVAILABLE and not CONFIG['simulation_mode']:
            self._east  = MCP3008(channel=cfg['east_ch'],
                                  port=cfg['spi_port'], device=cfg['device'])
            self._west  = MCP3008(channel=cfg['west_ch'],
                                  port=cfg['spi_port'], device=cfg['device'])
            self._south = MCP3008(channel=cfg['south_ch'],
                                  port=cfg['spi_port'], device=cfg['device'])
            self._north = MCP3008(channel=cfg['north_ch'],
                                  port=cfg['spi_port'], device=cfg['device'])

    def read(self) -> dict:
        """
        讀取四方向 ADC 值，並計算光照強度平均值（W/m²）。
        回傳 dict 包含 east/west/south/north（ADC）與 illumination（W/m²）。
        """
        if CONFIG['simulation_mode']:
            import random
            base = random.uniform(400, 700)
            raw = {
                'east':  round(base + random.uniform(-50, 50)),
                'west':  round(base + random.uniform(-50, 50)),
                'south': round(base + random.uniform(-50, 50)),
                'north': round(base + random.uniform(-50, 50)),
            }
        else:
            if not HARDWARE_AVAILABLE:
                raise RuntimeError(
                    "硬體不可用（gpiozero 未安裝），"
                    "若要測試請在 CONFIG 中設定 simulation_mode=True"
                )
            try:
                raw = {
                    'east':  round(self._east.value  * 1023),
                    'west':  round(self._west.value  * 1023),
                    'south': round(self._south.value * 1023),
                    'north': round(self._north.value * 1023),
                }
            except Exception as e:
                raise RuntimeError(
                    f"LDR 讀取失敗（感測器可能斷線或接觸不良）: {e}"
                ) from e

        # ADC → W/m²（簡易線性，四方向平均作為光照強度）
        s = CONFIG['ldr_sensitivity']
        illumination = sum(
            max(0.0, v * s['slope'] + s['intercept']) for v in raw.values()
        ) / 4.0

        return {**raw, 'illumination': round(illumination, 1)}


# ════════════════════════════════════════════════════════════════
# Django API 上傳
# ════════════════════════════════════════════════════════════════
def upload_to_api(payload: dict):
    try:
        url  = f"{CONFIG['api_url']}/power-records/"
        resp = requests.post(url, json=payload, timeout=10)
        if resp.status_code in (200, 201):
            logger.info("API 上傳成功")
        else:
            logger.warning(f"API 上傳失敗 {resp.status_code}: {resp.text[:200]}")
    except Exception as e:
        logger.warning(f"API 上傳例外: {e}")


# ════════════════════════════════════════════════════════════════
# 主控制迴圈
# ════════════════════════════════════════════════════════════════
def is_sun_time(now: datetime) -> bool:
    return CONFIG['sun_start_hour'] <= now.hour < CONFIG['sun_end_hour']


def main():
    logger.info("=== 對照組控制器啟動（傳統 LDR 差值追日，system_id=%d）===",
                CONFIG['system_id'])

    actuator  = ActuatorController()
    ldr       = LDRReader()
    ina3221   = INA3221Reader()
    threshold = CONFIG['threshold']

    while True:
        now = datetime.now()

        # ── Step 1：判斷太陽時間 ─────────────────────────────────
        if not is_sun_time(now):
            actuator.return_to_initial()
            logger.info("非太陽時間，回歸初始位置，等待 %d 秒",
                        CONFIG['interval_seconds'])
            time.sleep(CONFIG['interval_seconds'])
            continue

        # ── Step 2：讀取 LDR ─────────────────────────────────────
        values = ldr.read()
        logger.info("LDR  東=%-5d 西=%-5d 南=%-5d 北=%-5d 照度=%.1f W/m²",
                    values['east'], values['west'],
                    values['south'], values['north'], values['illumination'])

        decision_ew = '保持'
        decision_ns = '保持'

        # ── Step 3：東西差異判斷（控制 ζ）───────────────────────
        ew_diff = values['east'] - values['west']
        if abs(ew_diff) > threshold:
            if ew_diff > 0:
                if actuator.move_east():
                    decision_ew = '向東'
            else:
                if actuator.move_west():
                    decision_ew = '向西'

        # ── Step 4：南北差異判斷（控制 γ）───────────────────────
        ns_diff = values['south'] - values['north']
        if abs(ns_diff) > threshold:
            if ns_diff > 0:
                if actuator.move_south():
                    decision_ns = '向南'
            else:
                if actuator.move_north():
                    decision_ns = '向北'

        logger.info("決策 EW=%-4s NS=%-4s  γ=%.1f° ζ=%.1f°",
                    decision_ew, decision_ns, actuator.gamma, actuator.zeta)

        # ── Step 5：讀取 INA3221 與 MPPT ────────────────────────
        try:
            ina_act = ina3221.read_actuator()
        except Exception as e:
            logger.warning("推桿電力讀取失敗: %s", e)
            ina_act = {'voltage': None, 'current': None}

        try:
            ina_pi = ina3221.read_pi()
        except Exception as e:
            logger.warning("Pi 電力讀取失敗: %s", e)
            ina_pi = {'voltage': None, 'current': None}

        try:
            mppt = read_mppt_power()
        except NotImplementedError:
            logger.warning("MPPT 讀取尚未實作，voltage/current 將為 null")
            mppt = {'voltage': 0.0, 'current': 0.0, 'power': 0.0}
        except Exception as e:
            logger.warning("MPPT 讀取失敗: %s", e)
            mppt = {'voltage': 0.0, 'current': 0.0, 'power': 0.0}

        # ── Step 6：上傳資料 ─────────────────────────────────────
        upload_to_api({
            'system_id':              CONFIG['system_id'],
            'timestamp':              now.isoformat(),
            # 太陽能板（MPPT RS485）— 必填欄位
            'voltage':                mppt['voltage'],
            'current':                mppt['current'],
            'power_output':           mppt['power'],
            # 光照強度（四 LDR 平均，W/m²）
            'light_intensity':        values['illumination'],
            # 推桿角度（tip-tilt）
            'ns_actuator_angle':      actuator.gamma,
            'ew_actuator_angle':      actuator.zeta,
            # INA3221 CH1 推桿電力
            'actuator_total_voltage': ina_act['voltage'],
            'actuator_total_current': ina_act['current'],
            # INA3221 CH2 樹莓派電力
            'raspberry_pi_voltage':   ina_pi['voltage'],
            'raspberry_pi_current':   ina_pi['current'],
            # 備註（追日決策）
            'notes': (
                f"EW={decision_ew} NS={decision_ns} "
                f"ew_diff={ew_diff} ns_diff={ns_diff}"
            ),
        })

        # ── Step 7：等待 10 分鐘 ────────────────────────────────
        time.sleep(CONFIG['interval_seconds'])


if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        logger.info("使用者中斷，程式結束")
    except Exception as e:
        logger.exception("未預期錯誤: %s", e)
