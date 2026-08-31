#!/usr/bin/env python3
"""
system_test.py — Pi 系統完整測試(單一 Pi 用,適合初次部署 + 現場校正)

功能:
    - LDR 4 方位讀值(median 20 取樣抗噪)
    - 雙軸推桿控制(WASD)+ 自動 0.3s 停止
    - Hall 位置回授(mm 即時追蹤)
    - INA3221 電力監控(即時螢幕顯示)
    - 位置歸零(讓現場設當前位置為零點)

按鍵:
    w/s     NS(南北/傾角)伸/縮
    a/d     EW(東西/方位)縮/伸
    x       全停
    L       讀 4 方位 LDR raw ADC + diff
    P       印當前位置(mm + pulse + %)
    R       重置 NS 位置為 0(當前位置 = 零點)
    E       重置 EW 位置為 0
    I       讀 INA3221 電壓/電流/功率
    Q       離開(自動 GPIO cleanup)

pin 對應(2026-07 標準,若現場實測反了,改下面常數即可):
    NS: BH=17 BLH=27 BRL=22 BLL=23  HALL=24,25
    EW: BH=5  BLH=6  BRL=13 BLL=19  HALL=16,26
"""
import RPi.GPIO as GPIO
import spidev
import statistics
import smbus2
import time, sys, tty, termios, select, threading

# ==================== 硬體 pin 對應 ====================
NS_BH, NS_BLH, NS_BRL, NS_BLL = 17, 27, 22, 23
NS_HALL1, NS_HALL2 = 24, 25
NS_PPM, NS_STROKE = 54.19, 206  # pulses/mm, mm 全行程

EW_BH, EW_BLH, EW_BRL, EW_BLL = 5, 6, 13, 19
EW_HALL1, EW_HALL2 = 16, 26
EW_PPM, EW_STROKE = 54.19, 406

LDR_CHANNELS = {'east': 0, 'west': 1, 'south': 2, 'north': 3}

INA_ADDR = 0x40  # A0/A1 接 GND
SHUNT_R = 0.1    # Ω,標準模組

AUTO_STOP = 0.3  # 秒


# ==================== 推桿控制 ====================
class Actuator:
    def __init__(self, name, bh, blh, brl, bll):
        self.name = name
        self.bh, self.blh, self.brl, self.bll = bh, blh, brl, bll
        self.state = None
        GPIO.setup([bh, blh, brl, bll], GPIO.OUT)
        self.stop()

    def extend(self):
        if self.state == 'extend': return
        GPIO.output([self.bh, self.bll], GPIO.LOW)
        time.sleep(0.01)
        GPIO.output([self.blh, self.brl], GPIO.HIGH)
        self.state = 'extend'

    def retract(self):
        if self.state == 'retract': return
        GPIO.output([self.blh, self.brl], GPIO.LOW)
        time.sleep(0.01)
        GPIO.output([self.bh, self.bll], GPIO.HIGH)
        self.state = 'retract'

    def stop(self):
        GPIO.output([self.bh, self.blh, self.brl, self.bll], GPIO.LOW)
        self.state = None


# ==================== Hall 位置追蹤 ====================
class Hall:
    def __init__(self, name, h1, h2, ppm, stroke):
        self.name = name
        self.h1, self.h2 = h1, h2
        self.ppm, self.stroke = ppm, stroke
        self.count = 0
        self.pos_mm = 0.0
        self.running = True
        GPIO.setup([h1, h2], GPIO.IN, pull_up_down=GPIO.PUD_UP)
        self.last = GPIO.input(h1)
        threading.Thread(target=self._loop, daemon=True).start()

    def _loop(self):
        while self.running:
            v1 = GPIO.input(self.h1)
            v2 = GPIO.input(self.h2)
            if v1 != self.last:
                if v1 == v2:
                    self.count -= 1
                else:
                    self.count += 1
                self.pos_mm = self.count / self.ppm
                self.last = v1
            time.sleep(0.0001)

    def reset(self, to_mm=0.0):
        self.count = int(to_mm * self.ppm)
        self.pos_mm = to_mm

    def stop(self):
        self.running = False


# ==================== INA3221 讀值 ====================
def read_ina3221():
    """回傳 (v_ch1, i_ch1, v_ch2, i_ch2),失敗 None"""
    try:
        b = smbus2.SMBus(1)
        def r(reg):
            d = b.read_i2c_block_data(INA_ADDR, reg, 2)
            v = (d[0] << 8) | d[1]
            return v - 65536 if v >= 32768 else v
        v1 = r(0x02) / 1000
        i1 = r(0x01) * 40 / 1000 / 8 / 100
        v2 = r(0x04) / 1000
        i2 = r(0x03) * 40 / 1000 / 8 / 100
        b.close()
        return v1, i1, v2, i2
    except Exception as e:
        return None, None, None, None


# ==================== LDR 讀值 ====================
class LDR:
    def __init__(self):
        self.spi = spidev.SpiDev()
        self.spi.open(0, 0)
        self.spi.max_speed_hz = 1_000_000
        self.spi.mode = 0

    def read_ch(self, ch, n=20):
        vals = []
        for _ in range(n):
            r = self.spi.xfer2([1, (8 + ch) << 4, 0])
            vals.append(((r[1] & 3) << 8) | r[2])
        return statistics.median(vals)

    def read_all(self):
        return {name: int(self.read_ch(ch)) for name, ch in LDR_CHANNELS.items()}

    def close(self):
        self.spi.close()


# ==================== 主程式 ====================
def getkey():
    if select.select([sys.stdin], [], [], 0)[0]:
        return sys.stdin.read(1)
    return None


def main():
    GPIO.setmode(GPIO.BCM)
    GPIO.setwarnings(False)

    old = termios.tcgetattr(sys.stdin)
    tty.setcbreak(sys.stdin.fileno())

    print("=" * 70)
    print("       Pi 系統完整測試(system_test.py)")
    print("=" * 70)

    ns = Actuator("NS(南北/傾角)", NS_BH, NS_BLH, NS_BRL, NS_BLL)
    ew = Actuator("EW(東西/方位)", EW_BH, EW_BLH, EW_BRL, EW_BLL)
    print("  ✓ 推桿初始化 NS + EW")

    ns_hall = Hall("NS", NS_HALL1, NS_HALL2, NS_PPM, NS_STROKE)
    ew_hall = Hall("EW", EW_HALL1, EW_HALL2, EW_PPM, EW_STROKE)
    print("  ✓ Hall 感測器啟動(執行緒監控中)")

    try:
        ldr = LDR()
        print("  ✓ MCP3008 LDR 已連線")
    except Exception as e:
        print(f"  ✗ LDR 初始化失敗: {e}")
        ldr = None

    v1, i1, v2, i2 = read_ina3221()
    if v1 is not None:
        print(f"  ✓ INA3221 baseline: CH1 {v1:.2f}V {i1*1000:.0f}mA / CH2 {v2:.2f}V {i2*1000:.0f}mA")
    else:
        print("  ✗ INA3221 讀取失敗")

    print("""
=================================================================
按鍵:
  w/s   NS 傾角 伸/縮      a/d   EW 方位 縮/伸
  x     全停                q     離開
  L     讀 4 方位 LDR       P     印當前位置
  R     NS 位置歸零         E     EW 位置歸零
  I     INA3221 讀值
=================================================================
""")

    act_ns, act_ew, last_key_t = None, None, time.time()
    last_disp = time.time()

    try:
        while True:
            k = getkey()
            if k:
                last_key_t = time.time()
                kl = k.lower()

                if kl == 'w':
                    ns.extend(); act_ns = 'extend'
                elif kl == 's':
                    ns.retract(); act_ns = 'retract'
                elif kl == 'a':
                    ew.retract(); act_ew = 'retract'
                elif kl == 'd':
                    ew.extend(); act_ew = 'extend'
                elif kl == 'x':
                    ns.stop(); ew.stop()
                    act_ns = act_ew = None
                    print("\n■ 全停                                    ")
                elif kl == 'l' and ldr is not None:
                    print()
                    vals = ldr.read_all()
                    print(f"[LDR] E={vals['east']:4d}  W={vals['west']:4d}  "
                          f"S={vals['south']:4d}  N={vals['north']:4d}")
                    print(f"      diff EW={vals['east']-vals['west']:+d}  "
                          f"NS={vals['south']-vals['north']:+d}")
                    if max(vals.values()) > 950:
                        print("      ⚠️  raw > 950 = saturate,現場需調小分壓電阻")
                elif kl == 'p':
                    print(f"\n[POS] NS={ns_hall.pos_mm:6.1f}mm  "
                          f"({ns_hall.count:+d} pulse, {ns_hall.pos_mm/NS_STROKE*100:5.1f}% of {NS_STROKE}mm)")
                    print(f"      EW={ew_hall.pos_mm:6.1f}mm  "
                          f"({ew_hall.count:+d} pulse, {ew_hall.pos_mm/EW_STROKE*100:5.1f}% of {EW_STROKE}mm)")
                elif kl == 'r':
                    ns_hall.reset(0.0)
                    print("\n✓ NS 位置歸零(當前位置設為 0mm 參考點)")
                elif kl == 'e':
                    ew_hall.reset(0.0)
                    print("\n✓ EW 位置歸零(當前位置設為 0mm 參考點)")
                elif kl == 'i':
                    v1, i1, v2, i2 = read_ina3221()
                    if v1 is not None:
                        print(f"\n[INA] CH1 推桿: {v1:.2f}V  {i1*1000:6.1f}mA  {v1*i1:5.2f}W")
                        print(f"      CH2 Pi:  {v2:.2f}V  {i2*1000:6.1f}mA  {v2*i2:5.2f}W")
                    else:
                        print("\n[INA] 讀取失敗")
                elif kl == 'q':
                    print("\n離開")
                    break

            # 自動停止
            if (act_ns or act_ew) and time.time() - last_key_t > AUTO_STOP:
                if act_ns: ns.stop(); act_ns = None
                if act_ew: ew.stop(); act_ew = None

            # 即時 status(每 0.3s 更新單行)
            if time.time() - last_disp > 0.3:
                v1, i1, _, _ = read_ina3221()
                ns_s = "↑" if act_ns == 'extend' else "↓" if act_ns == 'retract' else "■"
                ew_s = "→" if act_ew == 'extend' else "←" if act_ew == 'retract' else "■"
                cur = f"{i1*1000:4.0f}mA {v1*i1:4.1f}W" if v1 else "N/A"
                print(f"\r NS{ns_s}{ns_hall.pos_mm:6.1f}mm  "
                      f"EW{ew_s}{ew_hall.pos_mm:6.1f}mm  CH1:{cur}    ", end='', flush=True)
                last_disp = time.time()

            time.sleep(0.01)

    finally:
        ns.stop(); ew.stop()
        ns_hall.stop(); ew_hall.stop()
        if ldr: ldr.close()
        termios.tcsetattr(sys.stdin, termios.TCSADRAIN, old)
        GPIO.cleanup()
        print(f"\n\n最終位置:NS={ns_hall.pos_mm:.1f}mm  EW={ew_hall.pos_mm:.1f}mm")
        print(f"       LDR channels: {LDR_CHANNELS}")
        print("✓ GPIO 清理完成")


if __name__ == '__main__':
    main()
