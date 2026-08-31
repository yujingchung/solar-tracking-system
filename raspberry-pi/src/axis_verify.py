#!/usr/bin/env python3
"""
axis_verify.py — 逐一測試 pin group 對應到哪個物理軸 + extend/retract 方向

依序做 4 個動作,每個動 1.5 秒,間隔 3 秒讓你觀察並記筆記。
測完後**回報**每段對應的物理軸(EW 東西 / NS 南北)和方向。

按 Ctrl+C 可隨時中斷,GPIO 會清理。
"""
import RPi.GPIO as GPIO
import time

# 兩組 pin(我目前的猜測,實測後可能要對調)
GROUP_A = {'label': 'Group A(目前 code 稱 NS 傾角)',
           'pins': [17, 27, 22, 23], 'BH': 17, 'BLH': 27, 'BRL': 22, 'BLL': 23}
GROUP_B = {'label': 'Group B(目前 code 稱 EW 方位)',
           'pins': [5, 6, 13, 19], 'BH': 5, 'BLH': 6, 'BRL': 13, 'BLL': 19}

MOVE_TIME = 1.5   # 每次動的秒數
PAUSE_TIME = 3.0  # 兩次動作間暫停秒數


def extend(g):
    GPIO.output([g['BH'], g['BLL']], GPIO.LOW)
    time.sleep(0.01)
    GPIO.output([g['BLH'], g['BRL']], GPIO.HIGH)


def retract(g):
    GPIO.output([g['BLH'], g['BRL']], GPIO.LOW)
    time.sleep(0.01)
    GPIO.output([g['BH'], g['BLL']], GPIO.HIGH)


def stop(g):
    GPIO.output([g['BH'], g['BLH'], g['BRL'], g['BLL']], GPIO.LOW)


def do_test(idx, total, group, action_fn, action_name):
    print(f"\n{'=' * 60}")
    print(f"  [{idx}/{total}] {group['label']}")
    print(f"     pin={group['pins']}  →  {action_name}")
    print(f"     動 {MOVE_TIME}s...", flush=True)
    action_fn(group)
    time.sleep(MOVE_TIME)
    stop(group)
    print(f"     ■ 停止")
    print(f"     ★ 觀察:哪個物理軸動了?方向是?")
    if idx < total:
        print(f"     (下一個動作在 {PAUSE_TIME}s 後開始)")
        time.sleep(PAUSE_TIME)


try:
    GPIO.setmode(GPIO.BCM)
    GPIO.setwarnings(False)
    for g in [GROUP_A, GROUP_B]:
        GPIO.setup(g['pins'], GPIO.OUT)
        stop(g)

    print("=" * 60)
    print("     推桿軸向 + 方向驗證")
    print("=" * 60)
    print("""
測試計畫:4 個動作依序執行,每個動 1.5s、間隔 3s。
準備好紙筆記錄「哪個物理軸動了 + 動的方向」。

  [1] Group A extend  (pin 17/27/22/23)
  [2] Group A retract (pin 17/27/22/23)
  [3] Group B extend  (pin 5/6/13/19)
  [4] Group B retract (pin 5/6/13/19)

3 秒後開始...
""")
    time.sleep(3)

    do_test(1, 4, GROUP_A, extend,  "extend  (往外伸)")
    do_test(2, 4, GROUP_A, retract, "retract (往內縮)")
    do_test(3, 4, GROUP_B, extend,  "extend  (往外伸)")
    do_test(4, 4, GROUP_B, retract, "retract (往內縮)")

    print(f"\n{'=' * 60}")
    print("  ✅ 測試完成!請回報 4 段觀察結果:")
    print(f"{'=' * 60}")
    print("""
   格式:
     [1] Group A extend  → 動了哪個軸(EW/NS)?方向?
     [2] Group A retract → ...
     [3] Group B extend  → ...
     [4] Group B retract → ...

   方向詞彙:
     NS 軸(傾角):朝天空抬 = "抬高" / 朝地面倒 = "低頭"
     EW 軸(方位):往東轉 = "東" / 往西轉 = "西"
""")

except KeyboardInterrupt:
    print("\n\n⚠️ 使用者中斷")

finally:
    stop(GROUP_A)
    stop(GROUP_B)
    GPIO.cleanup()
    print("\n✓ GPIO 已清理\n")
