#!/usr/bin/env python3
"""
azalt_to_tiptilt.py
從固定式面板座標 (β 傾角, φ 方位角) 反推追日系統的致動器座標 (γ 南北向傾角, ζ 東西向傾角)

這是 tiptilt_to_azalt.py 的逆運算，用途是：
  ANFIS 模型預測出最佳 (β, φ) → 本模組換算為 (γ, ζ) → 控制線性致動器

數學推導
---------
正向（tiptilt_to_azalt.py）：ZYX 串聯旋轉得面板法向量 n⃗
    x = sin(ζ)
    y = sin(γ) · cos(ζ)
    z = cos(γ) · cos(ζ)
  再由 n⃗ 反推：
    β = arccos(z)
    φ = atan2(x, y)      [0°~360°]

逆向（本模組）：給定 (β, φ) 反推 (γ, ζ)
  由 (β, φ) 重建法向量：
    nx = sin(β) · sin(φ)
    ny = sin(β) · cos(φ)
    nz = cos(β)
  對應正向公式：
    x = nx  →  ζ = arcsin(nx)
    y = ny,  z = nz  →  γ = atan2(ny, nz)

致動器限制
----------
    γ ∈ [-30°, +30°]   南北向
    ζ ∈ [-35°, +35°]   東西向

若目標 (β, φ) 超出致動器可達範圍，函式會回傳夾限後的最近可達點，
並以 reachable=False 告知呼叫方。
"""

import math
import numpy as np
from typing import Tuple, Dict, List


# ── 致動器硬體限制 ──────────────────────────────────────────────────────────────
GAMMA_MIN, GAMMA_MAX = -30.0, 30.0   # 南北向傾角範圍 (度)
ZETA_MIN,  ZETA_MAX  = -35.0, 35.0   # 東西向傾角範圍 (度)


def azalt_to_tiptilt(beta: float, phi: float) -> Tuple[float, float, bool]:
    """
    將固定式面板座標 (β, φ) 轉換為追日系統致動器座標 (γ, ζ)。

    Parameters
    ----------
    beta : float
        傾角，面板與水平面夾角，0°~90°。
    phi : float
        方位角，0°~360°，以正北為 0°，順時針增加。
        正南 = 180°。

    Returns
    -------
    gamma : float
        南北向傾角（度）。正值 = 向北傾，負值 = 向南傾。
    zeta : float
        東西向傾角（度）。正值 = 向東傾，負值 = 向西傾。
    reachable : bool
        True  → 目標角度在致動器可達範圍內，回傳值即為精確解。
        False → 目標超出範圍，回傳值為夾限後最近可達點（近似解）。
    """
    beta_rad = math.radians(beta)
    phi_rad  = math.radians(phi)

    # 由 (β, φ) 重建面板法向量
    nx = math.sin(beta_rad) * math.sin(phi_rad)
    ny = math.sin(beta_rad) * math.cos(phi_rad)
    nz = math.cos(beta_rad)

    # 逆推 ζ：由 sin(ζ) = nx → ζ = arcsin(nx)
    # arcsin 定義域 [-1, 1]，正常 β≤90° 時 |nx|≤1，保護一下
    zeta_rad  = math.asin(max(-1.0, min(1.0, nx)))
    zeta      = math.degrees(zeta_rad)

    # 逆推 γ：由 ny = sin(γ)·cos(ζ)、nz = cos(γ)·cos(ζ) → γ = atan2(ny, nz)
    gamma     = math.degrees(math.atan2(ny, nz))

    # 檢查是否在致動器可達範圍
    reachable = (GAMMA_MIN <= gamma <= GAMMA_MAX) and (ZETA_MIN <= zeta <= ZETA_MAX)

    # 夾限到可達範圍（保持最接近的可達點）
    gamma = max(GAMMA_MIN, min(GAMMA_MAX, gamma))
    zeta  = max(ZETA_MIN,  min(ZETA_MAX,  zeta))

    return gamma, zeta, reachable


def find_best_reachable_angle(
    anfis_predict_fn,
    hour_decimal: float,
    day_of_year: int,
    illumination: float = None,
    tilt_candidates: List[float] = None,
    azimuth_candidates: List[float] = None,
    scan_step: float = 5.0,
    use_training_range_only: bool = True,
) -> Dict:
    """
    在可達的 (β, φ) 空間中掃描，找出 ANFIS 預測功率最高的角度，
    並回傳對應的 (γ, ζ) 致動器目標值。

    Parameters
    ----------
    anfis_predict_fn : callable
        ANFIS 預測函數，簽名：
            predict(hour_decimal, day_of_year, tilt_angle, azimuth_angle,
                    illumination=None) -> float (W)
    hour_decimal : float
        當前時間，小時（0.0~24.0）。
    day_of_year : int
        當天是一年的第幾天（1~365）。
    illumination : float, optional
        當前照度（W/m²），如果 ANFIS 模型需要的話。
    tilt_candidates : list of float, optional
        要搜尋的傾角列表。預設使用訓練資料的 12 組：[10, 15, 20, 30]。
    azimuth_candidates : list of float, optional
        要搜尋的方位角列表。預設：[160, 180, 200]。
    scan_step : float
        若不用 candidates 清單，改用此步長做網格搜尋（度）。
    use_training_range_only : bool
        True  → 只搜尋 12 組訓練用固定角度（最安全，避免外推）。
        False → 在 β=5~40°、φ=140~220° 範圍以 scan_step 網格搜尋。

    Returns
    -------
    dict with keys:
        best_beta        : float   最佳傾角 (度)
        best_phi         : float   最佳方位角 (度)
        best_gamma       : float   對應的南北向致動器角度 (度)
        best_zeta        : float   對應的東西向致動器角度 (度)
        predicted_power  : float   預測功率 (W)
        reachable        : bool    是否在致動器範圍內
        all_results      : list    所有候選點的完整結果（方便 debug）
    """
    if tilt_candidates is None:
        tilt_candidates = [10.0, 15.0, 20.0, 30.0]
    if azimuth_candidates is None:
        azimuth_candidates = [160.0, 180.0, 200.0]

    if use_training_range_only:
        search_grid = [
            (t, a)
            for t in tilt_candidates
            for a in azimuth_candidates
        ]
    else:
        # 擴展網格搜尋（注意：模型可能對訓練範圍外的值外推不準）
        betas    = np.arange(5.0, 41.0, scan_step)
        azimuths = np.arange(140.0, 221.0, scan_step)
        search_grid = [(float(b), float(a)) for b in betas for a in azimuths]

    best = None
    all_results = []

    for beta, phi in search_grid:
        gamma, zeta, reachable = azalt_to_tiptilt(beta, phi)

        # 預測功率
        try:
            if illumination is not None:
                power = anfis_predict_fn(hour_decimal, day_of_year, beta, phi,
                                         illumination=illumination)
            else:
                power = anfis_predict_fn(hour_decimal, day_of_year, beta, phi)
        except Exception:
            power = 0.0

        entry = {
            'beta': beta, 'phi': phi,
            'gamma': gamma, 'zeta': zeta,
            'reachable': reachable,
            'predicted_power': power,
        }
        all_results.append(entry)

        if best is None or power > best['predicted_power']:
            best = entry

    return {
        'best_beta':       best['beta'],
        'best_phi':        best['phi'],
        'best_gamma':      best['gamma'],
        'best_zeta':       best['zeta'],
        'predicted_power': best['predicted_power'],
        'reachable':       best['reachable'],
        'all_results':     all_results,
    }


# ── 驗證工具 ───────────────────────────────────────────────────────────────────
def verify_roundtrip(beta: float, phi: float, tol: float = 0.01) -> bool:
    """
    驗證 (β, φ) → (γ, ζ) → (β', φ') 的往返誤差是否在容忍範圍內。
    用於單元測試。
    """
    from tiptilt_to_azalt import tiptilt_to_azalt   # 正向轉換

    gamma, zeta, reachable = azalt_to_tiptilt(beta, phi)
    beta2, phi2 = tiptilt_to_azalt(gamma, zeta)

    err_beta = abs(beta - beta2)
    err_phi  = abs(phi  - phi2)
    # 方位角是循環的，需要處理 360° 跳躍
    if err_phi > 180:
        err_phi = 360 - err_phi

    ok = reachable and (err_beta < tol) and (err_phi < tol)
    return ok, beta2, phi2, gamma, zeta


def print_conversion_table():
    """印出 12 組固定面板角度對應的追日致動器角度"""
    training_combinations = [
        (10, 160), (10, 180), (10, 200),
        (15, 160), (15, 180), (15, 200),
        (20, 160), (20, 180), (20, 200),
        (30, 160), (30, 180), (30, 200),
    ]

    print("=" * 65)
    print("固定式面板角度 ↔ 追日系統致動器角度 對照表")
    print("=" * 65)
    print(f"{'β(傾角)':>8} {'φ(方位角)':>10} | {'γ(南北)':>10} {'ζ(東西)':>10} | {'可達?':>6}")
    print("-" * 65)

    for beta, phi in training_combinations:
        gamma, zeta, reachable = azalt_to_tiptilt(beta, phi)
        ok_str = "✅" if reachable else "❌ 超限"
        print(f"{beta:>7.0f}° {phi:>9.0f}° | {gamma:>9.2f}° {zeta:>9.2f}° | {ok_str}")

    print("=" * 65)
    print("γ 範圍：-30° ~ +30°（正 = 北傾，負 = 南傾）")
    print("ζ 範圍：-35° ~ +35°（正 = 東傾，負 = 西傾）")


if __name__ == "__main__":
    print_conversion_table()

    print("\n── 往返誤差驗證 ──")
    test_cases = [(10, 180), (20, 160), (30, 200), (15, 180)]
    for b, p in test_cases:
        ok, b2, p2, g, z = verify_roundtrip(b, p)
        status = "✅ OK" if ok else "⚠️  誤差過大"
        print(f"(β={b}°, φ={p}°) → (γ={g:.2f}°, ζ={z:.2f}°) → "
              f"(β'={b2:.2f}°, φ'={p2:.2f}°)  {status}")
