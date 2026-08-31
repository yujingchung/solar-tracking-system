"""
ldr_module.py — 4 方位 LDR(MJ7537)讀取模組

用途:給 anfis_controller / traditional_controller 取代原本 single-shot MCP3008 讀取,
改成「median 20 取樣 + channel calibration」抗噪聲設計。

硬體:
    MCP3008 CH0 = 東 LDR
    MCP3008 CH1 = 西 LDR
    MCP3008 CH2 = 南 LDR
    MCP3008 CH3 = 北 LDR
    分壓電阻 10kΩ 在樹莓派端洞洞板(非感測器端)

校正:
    channel_calibration.json(放在與 controller 同目錄)
    內容範例 {"ch0": 0.9928, "ch1": 1.0222, "ch2": 0.9934, "ch3": 0.9922}
    係數來源:用單一參考 LDR 輪流插入 4 個插座、同光源下測得(電路基準校正)

軟體三層保護(從 ldr_pairing 移植):
    1. 每通道 20 次取樣取 median(抗 ADC 抖動)
    2. 套 channel calibration(補償電路偏差)
    3. 上層 controller 可加 MIN_TOTAL 與 DEAD_ZONE 判定

依賴:spidev(輕量、純 SPI 操作,不像 gpiozero 需要 lgpio backend)
"""
import json
import statistics
from pathlib import Path
from typing import Dict, Optional

try:
    import spidev
    SPIDEV_AVAILABLE = True
except ImportError:
    SPIDEV_AVAILABLE = False


# 方位 → MCP3008 通道對應
CHANNELS = {'east': 0, 'west': 1, 'south': 2, 'north': 3}


class LDRReader:
    """4 通道 MCP3008 讀取器 + 校正"""

    def __init__(self, calibration_path: Optional[Path] = None,
                 samples_per_read: int = 20,
                 spi_bus: int = 0, spi_device: int = 0,
                 spi_speed_hz: int = 1_000_000):
        """
        calibration_path: channel_calibration.json 路徑(預設找同目錄)
        samples_per_read: 每次讀取的 sample 數(median 抗噪)
        """
        self.samples = samples_per_read
        self.calib = self._load_calibration(calibration_path)
        self.spi = None
        if SPIDEV_AVAILABLE:
            self.spi = spidev.SpiDev()
            self.spi.open(spi_bus, spi_device)
            self.spi.max_speed_hz = spi_speed_hz
            self.spi.mode = 0

    def _load_calibration(self, path: Optional[Path]) -> Dict[str, float]:
        """載入 channel calibration;找不到就用 1.0 (無校正)"""
        if path is None:
            path = Path(__file__).parent / 'channel_calibration.json'
        if Path(path).exists():
            return json.loads(Path(path).read_text())
        # 沒校正檔 → 1.0 (raw ADC,backward compat)
        return {f'ch{ch}': 1.0 for ch in range(4)}

    def _read_adc_raw(self, channel: int) -> int:
        """MCP3008 single-ended read,回傳 0-1023"""
        if self.spi is None:
            raise RuntimeError("spidev 不可用,無法讀 MCP3008")
        adc = self.spi.xfer2([1, (8 + channel) << 4, 0])
        return ((adc[1] & 3) << 8) + adc[2]

    def _read_channel_median(self, channel: int) -> float:
        """每通道取 N 個 sample 取 median"""
        return statistics.median(
            self._read_adc_raw(channel) for _ in range(self.samples)
        )

    def read_calibrated(self) -> Dict[str, float]:
        """
        讀 4 個 LDR,套 channel calibration,回傳 dict
        例:{'east': 845.3, 'west': 821.7, 'south': 832.4, 'north': 850.1}
        值為 0-1023 之 ADC 經 calibration 後的浮點數(尚未轉 lux/W/m²)
        """
        out = {}
        for name, ch in CHANNELS.items():
            raw = self._read_channel_median(ch)
            cal = self.calib.get(f'ch{ch}', 1.0)
            out[name] = round(raw * cal, 1)
        return out

    def close(self):
        if self.spi is not None:
            self.spi.close()
            self.spi = None

    def __del__(self):
        try:
            self.close()
        except Exception:
            pass
