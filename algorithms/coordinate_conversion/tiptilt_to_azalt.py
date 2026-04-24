#!/usr/bin/env python3
# tiptilt_to_azalt_converter.py
"""
Tip-Tilt 座標轉換計算器
從南北向傾角 (γ) 和東西向傾角 (ζ) 計算方位角 (φ) 和傾角 (β)
"""

import math
import csv
import numpy as np


def tiptilt_to_azalt(gamma, zeta):
    """
    從 Tip-Tilt 角度轉換為方位角-傾角系統

    Args:
        gamma: 南北向傾角 (度) [+北, -南]
        zeta: 東西向傾角 (度) [+東, -西]

    Returns:
        (beta, phi): 傾角, 方位角 (度)
    """
    # 轉為弧度
    gamma_rad = math.radians(gamma)
    zeta_rad = math.radians(zeta)

    # 計算法向量分量（串聯旋轉）
    x = math.sin(zeta_rad)
    y = math.sin(gamma_rad) * math.cos(zeta_rad)
    z = math.cos(gamma_rad) * math.cos(zeta_rad)

    # 從法向量計算傾角 β
    # z = cos(β) → β = arccos(z)
    beta = math.degrees(math.acos(max(-1, min(1, z))))

    # 從法向量計算方位角 φ
    # x = sin(β)sin(φ), y = sin(β)cos(φ)
    # φ = atan2(x, y)
    phi = math.degrees(math.atan2(x, y))

    # 確保方位角在 0-360° 範圍
    if phi < 0:
        phi += 360

    return beta, phi


def generate_conversion_table(gamma_range, zeta_range, step=5):
    """
    生成完整的角度轉換對照表

    Args:
        gamma_range: γ 範圍 (度) [min, max]
        zeta_range: ζ 範圍 (度) [min, max]
        step: 角度間隔 (度)

    Returns:
        list: 包含所有轉換結果的列表
    """
    results = []

    # 生成所有 γ 和 ζ 的組合
    gamma_values = np.arange(gamma_range[0], gamma_range[1] + step, step)
    zeta_values = np.arange(zeta_range[0], zeta_range[1] + step, step)

    for gamma in gamma_values:
        for zeta in zeta_values:
            # 計算對應的方位角和傾角
            beta, phi = tiptilt_to_azalt(gamma, zeta)

            # 計算法向量（用於驗證）
            gamma_rad = math.radians(gamma)
            zeta_rad = math.radians(zeta)
            x = math.sin(zeta_rad)
            y = math.sin(gamma_rad) * math.cos(zeta_rad)
            z = math.cos(gamma_rad) * math.cos(zeta_rad)

            results.append({
                'gamma': gamma,
                'zeta': zeta,
                'beta': beta,
                'phi': phi,
                'nx': x,
                'ny': y,
                'nz': z
            })

    return results


def save_to_csv(results, filename='tiptilt_conversion_table.csv'):
    """
    將結果保存為 CSV 文件

    Args:
        results: 轉換結果列表
        filename: 輸出文件名
    """
    with open(filename, 'w', newline='', encoding='utf-8') as csvfile:
        fieldnames = ['gamma', 'zeta', 'beta', 'phi', 'nx', 'ny', 'nz']
        writer = csv.DictWriter(csvfile, fieldnames=fieldnames)

        # 寫入表頭
        writer.writeheader()

        # 寫入數據
        for row in results:
            # 格式化數值
            writer.writerow({
                'gamma': f"{row['gamma']:.1f}",
                'zeta': f"{row['zeta']:.1f}",
                'beta': f"{row['beta']:.4f}",
                'phi': f"{row['phi']:.4f}",
                'nx': f"{row['nx']:.6f}",
                'ny': f"{row['ny']:.6f}",
                'nz': f"{row['nz']:.6f}"
            })

    print(f"✓ 數據已保存至: {filename}")


def print_summary(results):
    """顯示統計摘要"""
    print("\n" + "=" * 70)
    print("轉換結果統計")
    print("=" * 70)

    betas = [r['beta'] for r in results]
    phis = [r['phi'] for r in results]

    print(f"\n總共計算: {len(results)} 個角度組合")

    print(f"\n傾角 β 範圍:")
    print(f"  最小: {min(betas):.2f}°")
    print(f"  最大: {max(betas):.2f}°")
    print(f"  平均: {np.mean(betas):.2f}°")

    print(f"\n方位角 φ 分布:")
    print(f"  最小: {min(phis):.2f}°")
    print(f"  最大: {max(phis):.2f}°")

    # 按方位角分區統計
    north = sum(1 for p in phis if 337.5 <= p or p < 22.5)
    east = sum(1 for p in phis if 67.5 <= p < 112.5)
    south = sum(1 for p in phis if 157.5 <= p < 202.5)
    west = sum(1 for p in phis if 247.5 <= p < 292.5)

    print(f"\n方位角分布:")
    print(f"  北方 (337.5-22.5°): {north} 個")
    print(f"  東方 (67.5-112.5°): {east} 個")
    print(f"  南方 (157.5-202.5°): {south} 個")
    print(f"  西方 (247.5-292.5°): {west} 個")


def show_examples():
    """顯示幾個典型案例"""
    print("\n" + "=" * 70)
    print("典型案例")
    print("=" * 70)

    test_cases = [
        (0, 0, "水平朝天"),
        (20, 0, "向北傾斜20°"),
        (0, 20, "向東傾斜20°"),
        (-20, 0, "向南傾斜20°"),
        (0, -20, "向西傾斜20°"),
        (20, 20, "向東北傾斜"),
        (-20, 20, "向東南傾斜"),
        (-20, -20, "向西南傾斜"),
    ]

    print(f"\n{'γ(南北)':>8} {'ζ(東西)':>8} | {'β(傾角)':>10} {'φ(方位)':>10} | 描述")
    print("-" * 70)

    for gamma, zeta, description in test_cases:
        beta, phi = tiptilt_to_azalt(gamma, zeta)
        print(f"{gamma:>8.1f}° {zeta:>8.1f}° | {beta:>10.2f}° {phi:>10.2f}° | {description}")


def main():
    """主程式"""
    print("\n" + "=" * 70)
    print("Tip-Tilt 座標轉換計算器")
    print("=" * 70)

    # 設定範圍
    gamma_range = (-30, 30)  # 南北向傾角
    zeta_range = (-35, 35)  # 東西向傾角

    print(f"\n設定範圍:")
    print(f"  γ (南北向傾角): {gamma_range[0]}° 到 {gamma_range[1]}°")
    print(f"  ζ (東西向傾角): {zeta_range[0]}° 到 {zeta_range[1]}°")

    # 選擇角度間隔
    print(f"\n選擇角度間隔:")
    print(f"  1 - 每 1° (2601 個組合)")
    print(f"  2 - 每 2° (1296 個組合)")
    print(f"  5 - 每 5° (225 個組合)")
    print(f"  10 - 每 10° (64 個組合)")

    choice = input(f"\n請選擇 (1/2/5/10) [預設5]: ").strip() or "5"
    step = int(choice)

    # 生成轉換表
    print(f"\n正在計算...")
    results = generate_conversion_table(gamma_range, zeta_range, step=step)

    # 顯示典型案例
    show_examples()

    # 顯示統計
    print_summary(results)

    # 保存到 CSV
    filename = f'tiptilt_conversion_step{step}.csv'
    save_to_csv(results, filename)

    print(f"\n" + "=" * 70)
    print("完成！")
    print("=" * 70)


if __name__ == "__main__":
    main()