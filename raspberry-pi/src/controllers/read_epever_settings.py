#!/usr/bin/env python3
"""
讀 EPEVER Tracer-AN-G3 所有充電設定 + 即時狀態(只讀不寫,安全)

跑法:
    cd ~/solar_tracking/anfis_2
    source .venv/bin/activate
    python read_epever_settings.py
"""
import minimalmodbus
import sys

PORT = '/dev/ttyUSB0'
SLAVE = 1
BAUD = 115200


def connect():
    m = minimalmodbus.Instrument(PORT, SLAVE)
    m.serial.baudrate = BAUD
    m.serial.bytesize = 8
    m.serial.parity = 'N'
    m.serial.stopbits = 1
    m.serial.timeout = 1.0
    m.mode = minimalmodbus.MODE_RTU
    m.clear_buffers_before_each_transaction = True
    return m


def read_one(m, reg, name, scale=100.0, signed=False, fc=None):
    """讀單一 register 並印出"""
    # 自動判斷 function code:0x3xxx = input(fc=4)、0x9xxx = holding(fc=3)
    if fc is None:
        fc = 3 if reg >= 0x9000 else 4
    try:
        raw = m.read_register(reg, 0, functioncode=fc)
        if signed and raw > 0x7FFF:
            raw -= 0x10000
        val = raw / scale if scale else raw
        unit = ''
        if scale == 100.0:
            unit = ' V' if 'V' in name or 'voltage' in name.lower() else \
                   (' A' if 'I' in name or 'current' in name.lower() else '')
        print(f"  0x{reg:04X}  {name:38s} = {val:10.3f}{unit}")
        return val
    except Exception as e:
        print(f"  0x{reg:04X}  {name:38s} = ERR: {type(e).__name__}")
        return None


def read_uint32(m, reg_l, reg_h, name, scale=100.0, fc=None):
    """讀 32-bit 跨兩個 register(L + H 組合)"""
    if fc is None:
        fc = 3 if reg_l >= 0x9000 else 4
    try:
        l = m.read_register(reg_l, 0, functioncode=fc)
        h = m.read_register(reg_h, 0, functioncode=fc)
        val = ((h << 16) | l) / scale
        print(f"  0x{reg_l:04X}+ {name:38s} = {val:10.3f}")
        return val
    except Exception as e:
        print(f"  0x{reg_l:04X}+ {name:38s} = ERR: {type(e).__name__}")
        return None


def main():
    print(f"連線 EPEVER:port={PORT} baud={BAUD} slave={SLAVE}")
    m = connect()

    # ── 即時狀態(input registers, fc=4)─────────────────
    print(f"\n{'='*70}")
    print("【即時狀態】PV 端(input registers 0x3100-3103)")
    print('='*70)
    read_one(m, 0x3100, "PV voltage")
    read_one(m, 0x3101, "PV current")
    read_uint32(m, 0x3102, 0x3103, "PV power (組合)")

    print(f"\n{'='*70}")
    print("【即時狀態】電池端(input registers 0x3104-3107)")
    print('='*70)
    read_one(m, 0x3104, "Battery voltage")
    read_one(m, 0x3105, "Battery charging current", signed=True)
    read_uint32(m, 0x3106, 0x3107, "Battery charging power (組合)")
    read_one(m, 0x311A, "Battery SOC (%)", scale=1.0)
    read_one(m, 0x311B, "Remote battery temperature")

    print(f"\n{'='*70}")
    print("【即時狀態】Load Output 負載輸出(input registers 0x310C-310F)")
    print('='*70)
    read_one(m, 0x310C, "Load voltage")
    read_one(m, 0x310D, "Load current")
    read_uint32(m, 0x310E, 0x310F, "Load power (組合)")

    print(f"\n{'='*70}")
    print("【充電狀態旗標】(0x3201)")
    print('='*70)
    try:
        status = m.read_register(0x3201, 0, functioncode=4)
        # bit decoding(EPEVER doc):
        charging_mode = status & 0x03  # bits 0-1
        mode_text = {0: 'No charging', 1: 'Float', 2: 'Boost (absorption)', 3: 'Equalize'}.get(charging_mode, '?')
        running = bool(status & 0x4000)  # bit 14
        fault   = bool(status & 0x8000)  # bit 15
        print(f"  0x3201  Charging status raw           = 0x{status:04X}")
        print(f"          → Charging mode (bit 0-1)     = {charging_mode} ({mode_text})")
        print(f"          → Charging running (bit 14)   = {running}")
        print(f"          → Fault (bit 15)              = {fault}")
    except Exception as e:
        print(f"  0x3201  Charging status                = ERR: {e}")

    # ── 充電設定(holding registers, fc=3)─────────────────
    print(f"\n{'='*70}")
    print("【充電設定】電池類型 + 容量(holding registers 0x9000-9002)")
    print('='*70)
    try:
        bt = m.read_register(0x9000, 0, functioncode=3)
        bt_text = {0: 'User-defined', 1: 'Sealed/AGM', 2: 'GEL', 3: 'Flooded'}.get(bt, '?')
        print(f"  0x9000  Battery type                   = {bt} ({bt_text})")
    except Exception as e:
        print(f"  0x9000  Battery type                   = ERR: {e}")
    read_one(m, 0x9001, "Battery capacity (Ah)", scale=1.0)
    read_one(m, 0x9002, "Temp comp coeff (mV/°C/2V)", scale=100.0)

    print(f"\n{'='*70}")
    print("【充電設定】★ 電壓閾值(holding registers 0x9003-900A)")
    print('='*70)
    read_one(m, 0x9003, "High voltage disconnect")
    read_one(m, 0x9004, "Charging limit voltage")
    read_one(m, 0x9005, "Over voltage reconnect")
    read_one(m, 0x9006, "★ Equalize voltage")
    read_one(m, 0x9007, "★ Boost (absorption) voltage")
    read_one(m, 0x9008, "★ Float voltage")
    read_one(m, 0x9009, "★ Boost reconnect voltage")
    read_one(m, 0x900A, "Low voltage reconnect")
    read_one(m, 0x900B, "Under voltage warning recover")
    read_one(m, 0x900C, "Under voltage warning")
    read_one(m, 0x900D, "Low voltage disconnect")
    read_one(m, 0x900E, "Discharging limit voltage")

    print(f"\n{'='*70}")
    print("【充電設定】充電時間 / 模式(holding registers 0x9013-9014)")
    print('='*70)
    read_one(m, 0x9013, "Equalization duration (min)", scale=1.0)
    read_one(m, 0x9014, "Boost duration (min)", scale=1.0)

    # ── 簡易自動診斷 ─────────────────────────────────────
    print(f"\n{'='*70}")
    print("【自動診斷】")
    print('='*70)
    try:
        batt_v = m.read_register(0x3104, 0, functioncode=4) / 100.0
        batt_i_raw = m.read_register(0x3105, 0, functioncode=4)
        if batt_i_raw > 0x7FFF:
            batt_i_raw -= 0x10000
        batt_i = batt_i_raw / 100.0
        boost_v = m.read_register(0x9007, 0, functioncode=3) / 100.0
        float_v = m.read_register(0x9008, 0, functioncode=3) / 100.0
        boost_reconnect = m.read_register(0x9009, 0, functioncode=3) / 100.0

        print(f"  當前電池 V = {batt_v:.2f} V, I = {batt_i:.3f} A")
        print(f"  Boost 設定 = {boost_v:.2f} V")
        print(f"  Float 設定 = {float_v:.2f} V")
        print(f"  Boost reconnect = {boost_reconnect:.2f} V(降到這個值才重啟 bulk)")
        print()
        if batt_v >= boost_v - 0.1:
            print(f"  → 電池接近/已達 Boost 上限,MPPT 在 absorption 模式")
        elif batt_v >= float_v - 0.1:
            print(f"  → 電池在 float 範圍,MPPT 維持壓平,不會大量充電")
        elif batt_v >= boost_reconnect:
            print(f"  → 電池介於 float 跟 boost reconnect 之間,可能在 absorption")
        else:
            print(f"  → 電池夠低,應該在 bulk 充電模式(最大功率)")
        print()
        print(f"  研究瓶頸建議:接 Load 到 EPEVER LOAD 輸出端子,讓電池能放電,")
        print(f"  才有機會讓 V_batt 跌到 {boost_reconnect:.2f}V 以下重啟 bulk 充電。")
    except Exception as e:
        print(f"  自動診斷失敗: {e}")

    print(f"\n{'='*70}\n讀取完成 ✓\n")


if __name__ == '__main__':
    main()
