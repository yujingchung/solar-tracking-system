#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
太陽能數據前處理工具 - 精簡版
核心功能:
1. 移除極低功率數據(零功率、夜間等)
2. 檢測並移除控制器過熱限制數據
"""

import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import matplotlib.font_manager as fm
from datetime import datetime
import os


class SimpleSolarPreprocessor:
    """精簡版太陽能數據前處理器"""

    def __init__(self,
                 min_power=10,  # 最低功率閾值(W)
                 overheat_power=45,  # 控制器過熱限制功率(W)
                 overheat_tolerance=10,  # 過熱功率容忍範圍(±W)
                 overheat_window=120):  # 過熱檢測窗口(分鐘)
        """
        初始化前處理器

        Args:
            min_power: 最低功率閾值,低於此值視為無效(默認10W)
            overheat_power: 控制器過熱時的限制功率(默認45W)
            overheat_tolerance: 過熱功率容忍範圍(默認±10W)
            overheat_window: 連續過熱多久才判定為故障(默認120分鐘)
        """
        self.min_power = min_power
        self.overheat_power = overheat_power
        self.overheat_tolerance = overheat_tolerance
        self.overheat_window = overheat_window

        # 設置中文字體
        self._setup_font()

        # 統計報告
        self.report = {
            'original_count': 0,
            'after_nan_removal': 0,
            'after_low_power_filter': 0,
            'after_overheat_filter': 0,
            'final_count': 0,
            'removed_nan': 0,
            'removed_low_power': 0,
            'removed_overheat': 0
        }

    def _setup_font(self):
        """設置中文字體"""
        chinese_fonts = ['Microsoft JhengHei', 'Microsoft YaHei', 'SimHei', 'Arial Unicode MS']
        for font in chinese_fonts:
            try:
                fm.findfont(fm.FontProperties(family=font))
                plt.rcParams['font.family'] = font
                plt.rcParams['axes.unicode_minus'] = False
                return
            except:
                continue

    def load_and_clean_basic(self, file_path):
        """
        載入並進行基本清理
        """
        print("\n" + "=" * 70)
        print("🚀 太陽能數據前處理 (精簡版)")
        print("=" * 70)

        # 載入數據
        print("\n📁 載入數據...")
        df = pd.read_csv(file_path, encoding='utf-8')
        self.report['original_count'] = len(df)
        print(f"✓ 原始數據: {len(df):,} 筆")

        # 從 timestamp 自動推導 day_of_year / hour_decimal（若欄位不存在）
        if 'timestamp' in df.columns:
            ts = pd.to_datetime(df['timestamp'], errors='coerce')
            if 'day_of_year' not in df.columns:
                df['day_of_year'] = ts.dt.dayofyear
                print("✓ 自動計算 day_of_year（從 timestamp）")
            if 'hour_decimal' not in df.columns:
                df['hour_decimal'] = ts.dt.hour + ts.dt.minute / 60 + ts.dt.second / 3600
                print("✓ 自動計算 hour_decimal（從 timestamp）")

        # 檢查必要欄位
        required = ['day_of_year', 'hour_decimal', 'tilt_angle',
                    'azimuth_angle', 'power_W']
        missing = [col for col in required if col not in df.columns]

        if missing:
            print(f"❌ 缺少必要欄位: {missing}")
            print("   提示：CSV 需要包含 'timestamp' 或手動提供上述欄位")
            return None

        # 轉換數據類型並移除NaN
        print("\n🔄 處理無效數據...")
        for col in required:
            df[col] = pd.to_numeric(df[col], errors='coerce')

        initial_count = len(df)
        df = df.dropna(subset=required).copy()
        removed = initial_count - len(df)

        self.report['after_nan_removal'] = len(df)
        self.report['removed_nan'] = removed

        print(f"✓ 移除無效數據: {removed:,} 筆")
        print(f"✓ 剩餘數據: {len(df):,} 筆")

        return df

    def filter_low_power(self, df):
        """
        功能1: 移除極低功率數據
        """
        print("\n" + "-" * 70)
        print(f"⚡ 功能1: 移除極低功率數據 (< {self.min_power}W)")
        print("-" * 70)

        initial_count = len(df)

        # 統計功率分布
        print(f"功率統計:")
        print(f"  範圍: {df['power_W'].min():.1f} - {df['power_W'].max():.1f} W")
        print(f"  平均: {df['power_W'].mean():.1f} ± {df['power_W'].std():.1f} W")
        print(f"  中位數: {df['power_W'].median():.1f} W")

        # 過濾
        df_filtered = df[df['power_W'] >= self.min_power].copy()

        removed = initial_count - len(df_filtered)
        removed_pct = (removed / initial_count * 100) if initial_count > 0 else 0

        self.report['after_low_power_filter'] = len(df_filtered)
        self.report['removed_low_power'] = removed

        print(f"\n✓ 移除低功率數據: {removed:,} 筆 ({removed_pct:.1f}%)")
        print(f"✓ 剩餘數據: {len(df_filtered):,} 筆")

        return df_filtered

    def detect_and_remove_overheat(self, df):
        """
        功能2: 檢測並移除控制器過熱數據（向量化版本，速度大幅提升）
        """
        print("\n" + "-" * 70)
        print(f"🌡️ 功能2: 檢測控制器過熱")
        print("-" * 70)
        print(f"檢測條件: 連續 {self.overheat_window} 分鐘功率在 "
              f"{self.overheat_power}±{self.overheat_tolerance}W")

        TIME_INTERVAL = 10  # 實際取樣間隔：10 分鐘

        # ── 排序（按面板組合 + 時間）──────────────────────────────
        if 'timestamp' in df.columns:
            df = df.sort_values(['tilt_angle', 'azimuth_angle', 'timestamp']).reset_index(drop=True)
        else:
            df = df.sort_values(
                ['tilt_angle', 'azimuth_angle', 'day_of_year', 'hour_decimal']
            ).reset_index(drop=True)

        # ── 標記落在過熱功率區間的資料點 ──────────────────────────
        lower_bound = self.overheat_power - self.overheat_tolerance
        upper_bound = self.overheat_power + self.overheat_tolerance
        df['_is_oh'] = (df['power_W'] >= lower_bound) & (df['power_W'] <= upper_bound)

        # ── 面板組合識別鍵 ──────────────────────────────────────
        df['_grp'] = df['tilt_angle'].astype(str) + '_' + df['azimuth_angle'].astype(str)

        # ── 偵測「連續段落」的起點：is_oh 改變，或換了面板組合 ────
        # 每次出現起點就讓 run_id +1，相同連續段內 run_id 相同
        prev_oh  = df.groupby('_grp')['_is_oh'].shift(fill_value=False)
        grp_break = df['_grp'] != df['_grp'].shift()
        oh_break  = df['_is_oh'] != prev_oh
        df['_run_id'] = (grp_break | oh_break).cumsum()

        # ── 在每段連續過熱段內累計時間（分鐘）──────────────────
        # cumcount() 從 0 開始，+1 後 × 10 分鐘 = 到該筆為止的連續時間
        print("計算連續過熱時間（向量化）...")
        df['_oh_duration'] = (
            (df.groupby('_run_id').cumcount() + 1) * TIME_INTERVAL
        ).where(df['_is_oh'], 0)

        # ── 標記超過門檻的資料 ─────────────────────────────────
        overheat_mask = df['_oh_duration'] >= self.overheat_window
        overheat_count = int(overheat_mask.sum())

        if overheat_count > 0:
            print(f"\n⚠ 檢測到 {overheat_count:,} 筆控制器過熱數據")
            affected = df[overheat_mask].groupby(['tilt_angle', 'azimuth_angle']).size()
            print("受影響的角度組合:")
            for (tilt, azimuth), count in affected.items():
                print(f"  - 傾角{tilt:.0f}°/方位角{azimuth:.0f}°: {count:,} 筆")
        else:
            print("✓ 未檢測到控制器過熱")

        # ── 移除過熱資料，清理暫存欄位 ────────────────────────
        df_filtered = df[~overheat_mask].drop(
            columns=['_is_oh', '_grp', '_run_id', '_oh_duration'], errors='ignore'
        ).copy()

        self.report['after_overheat_filter'] = len(df_filtered)
        self.report['removed_overheat'] = overheat_count

        print(f"\n✓ 移除過熱數據: {overheat_count:,} 筆")
        print(f"✓ 剩餘數據: {len(df_filtered):,} 筆")

        return df_filtered

    def check_angle_distribution(self, df):
        """檢查角度組合分布"""
        print("\n" + "-" * 70)
        print("📊 角度組合數據分布")
        print("-" * 70)

        angle_counts = df.groupby(['tilt_angle', 'azimuth_angle']).size().sort_values(ascending=False)

        print(f"總共 {len(angle_counts)} 個角度組合:")
        for (tilt, azimuth), count in angle_counts.items():
            print(f"  傾角{tilt:.0f}°/方位角{azimuth:.0f}°: {count:,} 筆")

        return angle_counts

    def generate_report(self):
        """生成處理報告"""
        print("\n" + "=" * 70)
        print("📋 處理報告")
        print("=" * 70)

        original = self.report['original_count']
        final = self.report['final_count']

        print(f"\n原始數據: {original:,} 筆")
        print(f"處理後數據: {final:,} 筆")
        print(f"保留比例: {(final / original * 100):.1f}%")

        print(f"\n移除統計:")
        print(f"  1. 無效數據(NaN): {self.report['removed_nan']:,} 筆 "
              f"({self.report['removed_nan'] / original * 100:.1f}%)")
        print(f"  2. 低功率(<{self.min_power}W): {self.report['removed_low_power']:,} 筆 "
              f"({self.report['removed_low_power'] / original * 100:.1f}%)")
        print(f"  3. 控制器過熱: {self.report['removed_overheat']:,} 筆 "
              f"({self.report['removed_overheat'] / original * 100:.1f}%)")

        total_removed = (self.report['removed_nan'] +
                         self.report['removed_low_power'] +
                         self.report['removed_overheat'])
        print(f"\n總移除: {total_removed:,} 筆")

        # 質量評估
        retention_rate = final / original if original > 0 else 0
        if retention_rate >= 0.7:
            status = "優秀 ✓"
        elif retention_rate >= 0.5:
            status = "良好 ○"
        elif retention_rate >= 0.3:
            status = "一般 △"
        else:
            status = "偏低 ⚠"

        print(f"\n數據保留率: {retention_rate * 100:.1f}% ({status})")

    def visualize(self, save_path=None):
        """生成簡單的視覺化報告"""
        fig, axes = plt.subplots(1, 2, figsize=(14, 5))

        # 圖1: 數據量變化
        stages = ['原始', '移除NaN', '移除低功率', '移除過熱']
        counts = [
            self.report['original_count'],
            self.report['after_nan_removal'],
            self.report['after_low_power_filter'],
            self.report['after_overheat_filter']
        ]

        colors = ['#3498db', '#2ecc71', '#f39c12', '#e74c3c']
        axes[0].bar(stages, counts, color=colors, alpha=0.7)
        axes[0].set_ylabel('數據筆數')
        axes[0].set_title('各階段數據量變化')
        axes[0].grid(True, alpha=0.3)

        # 在柱狀圖上顯示數值
        for i, (stage, count) in enumerate(zip(stages, counts)):
            axes[0].text(i, count, f'{count:,}', ha='center', va='bottom')

        # 圖2: 移除原因分布
        reasons = ['無效數據', f'低功率(<{self.min_power}W)', '控制器過熱']
        removed = [
            self.report['removed_nan'],
            self.report['removed_low_power'],
            self.report['removed_overheat']
        ]

        # 只顯示非零的部分
        non_zero = [(r, v) for r, v in zip(reasons, removed) if v > 0]
        if non_zero:
            reasons_filtered, removed_filtered = zip(*non_zero)
            axes[1].pie(removed_filtered, labels=reasons_filtered, autopct='%1.1f%%',
                        startangle=90, colors=['#e74c3c', '#f39c12', '#9b59b6'])
            axes[1].set_title('移除數據原因分布')

        plt.tight_layout()

        if save_path:
            plt.savefig(save_path, dpi=300, bbox_inches='tight')
            print(f"✓ 視覺化圖表已保存: {save_path}")

        plt.show()

    def process(self, input_file, output_file=None):
        """
        完整處理流程

        Args:
            input_file: 輸入CSV文件路徑
            output_file: 輸出CSV文件路徑(可選)

        Returns:
            DataFrame: 處理後的數據
        """
        # 1. 載入並基本清理
        df = self.load_and_clean_basic(input_file)
        if df is None:
            return None

        # 2. 移除低功率
        df = self.filter_low_power(df)

        # 3. 移除控制器過熱
        df = self.detect_and_remove_overheat(df)

        # 4. 檢查角度分布
        self.check_angle_distribution(df)

        # 5. 更新最終統計
        self.report['final_count'] = len(df)

        # 6. 生成報告
        self.generate_report()

        # 7. 保存結果
        if output_file:
            self.save_results(df, output_file)

        return df

    def save_results(self, df, output_file):
        """保存處理結果"""
        print("\n" + "-" * 70)
        print("💾 保存處理結果")
        print("-" * 70)

        try:
            # 保存CSV
            output_dir = os.path.dirname(output_file)
            if output_dir and not os.path.exists(output_dir):
                os.makedirs(output_dir)

            df.to_csv(output_file, index=False, encoding='utf-8')
            print(f"✓ CSV文件: {output_file}")

            # 保存文字報告
            report_file = output_file.replace('.csv', '_report.txt')
            with open(report_file, 'w', encoding='utf-8') as f:
                f.write("=" * 70 + "\n")
                f.write("太陽能數據前處理報告 (精簡版)\n")
                f.write("=" * 70 + "\n\n")
                f.write(f"處理時間: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
                f.write(f"配置參數:\n")
                f.write(f"  - 最低功率閾值: {self.min_power}W\n")
                f.write(f"  - 過熱檢測功率: {self.overheat_power}±{self.overheat_tolerance}W\n")
                f.write(f"  - 過熱檢測窗口: {self.overheat_window}分鐘\n\n")
                f.write(f"原始數據: {self.report['original_count']:,} 筆\n")
                f.write(f"處理後數據: {self.report['final_count']:,} 筆\n")
                f.write(f"保留比例: {(self.report['final_count'] / self.report['original_count'] * 100):.1f}%\n\n")
                f.write("移除統計:\n")
                f.write(f"  - 無效數據: {self.report['removed_nan']:,} 筆\n")
                f.write(f"  - 低功率: {self.report['removed_low_power']:,} 筆\n")
                f.write(f"  - 控制器過熱: {self.report['removed_overheat']:,} 筆\n")

            print(f"✓ 文字報告: {report_file}")

            # 生成視覺化
            viz_file = output_file.replace('.csv', '_visualization.png')
            self.visualize(viz_file)

        except Exception as e:
            print(f"❌ 保存失敗: {e}")


# ============ 快速使用函數 ============
def quick_preprocess(input_file, output_file=None,
                     min_power=10,
                     overheat_power=45,
                     overheat_tolerance=20,
                     overheat_window=60):
    """
    快速前處理函數

    Args:
        input_file: 輸入CSV文件
        output_file: 輸出CSV文件(可選)
        min_power: 最低功率閾值(默認10W)
        overheat_power: 過熱限制功率(默認45W)
        overheat_tolerance: 過熱容忍範圍(默認±10W)
        overheat_window: 過熱檢測窗口(默認120分鐘)

    Returns:
        DataFrame: 處理後的數據

    範例:
        # 使用默認參數
        df = quick_preprocess('data.csv', 'processed.csv')

        # 自定義參數
        df = quick_preprocess('data.csv', 'processed.csv',
                             min_power=15, overheat_power=50)
    """
    preprocessor = SimpleSolarPreprocessor(
        min_power=min_power,
        overheat_power=overheat_power,
        overheat_tolerance=overheat_tolerance,
        overheat_window=overheat_window
    )

    if output_file is None:
        base_name = os.path.splitext(input_file)[0]
        output_file = f"{base_name}_processed.csv"

    return preprocessor.process(input_file, output_file)


# ============ 主程式 ============
if __name__ == "__main__":
    import sys

    print("""
    ╔══════════════════════════════════════════════════════════╗
    ║     太陽能數據前處理工具 (精簡版) v1.0                   ║
    ║                                                          ║
    ║  核心功能:                                               ║
    ║  1. 移除極低功率數據 (零功率、夜間等)                    ║
    ║  2. 檢測並移除控制器過熱限制數據                         ║
    ╚══════════════════════════════════════════════════════════╝
    """)

    # 從命令行參數或交互式輸入獲取文件路徑
    if len(sys.argv) > 1:
        input_file = sys.argv[1]
    else:
        input_file = input("請輸入數據文件路徑: ").strip()

    if not os.path.exists(input_file):
        print(f"❌ 文件不存在: {input_file}")
        exit(1)

    # 生成輸出文件名
    base_name = os.path.splitext(input_file)[0]
    output_file = f"{base_name}_processed.csv"

    # 執行處理
    df = quick_preprocess(input_file, output_file)

    if df is not None:
        print("\n" + "=" * 70)
        print("✅ 處理完成!")
        print("=" * 70)
        print(f"處理後數據可用於ANFIS訓練")
    else:
        print("\n❌ 處理失敗")