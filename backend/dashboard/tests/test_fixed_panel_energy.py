"""compute_energy_wh 能量積分邏輯測試（不需資料庫）。

驗證「為什麼」：daily_energy_Wh 欄位 99% 為空，能量必須用「瞬時功率 × 取樣間隔」
重新積分。這裡的三條規則一旦改壞，整個固定面板研究的能量排行榜都會錯：
  1. 每片面板第一筆無前值 → 補 10 分鐘
  2. 一般間隔 = 與同面板前一筆的時間差
  3. 離線大缺口（>15 分鐘）要被夾到 15 分鐘上限，避免灌水
  4. 重複 timestamp（間隔 0）→ 能量 0，天然去重
"""
import pandas as pd
from django.test import SimpleTestCase

from dashboard.fixed_panel_api import (
    compute_energy_wh, ENERGY_GAP_CAP_H, ENERGY_FIRST_SAMPLE_H,
)


def _df(rows):
    """rows: list of (panel_id, 'YYYY-MM-DD HH:MM', power_W)"""
    df = pd.DataFrame(rows, columns=["panel_id", "timestamp", "power_W"])
    df["timestamp"] = pd.to_datetime(df["timestamp"])
    return df.sort_values(["panel_id", "timestamp"]).reset_index(drop=True)


class ComputeEnergyWhTests(SimpleTestCase):
    def test_first_sample_uses_10min(self):
        df = _df([("P1", "2026-01-01 08:00", 60.0)])
        e = compute_energy_wh(df)
        # 60W × (10/60)h = 10 Wh
        self.assertAlmostEqual(float(e.iloc[0]), 60.0 * ENERGY_FIRST_SAMPLE_H, places=3)

    def test_regular_10min_interval(self):
        df = _df([
            ("P1", "2026-01-01 08:00", 60.0),
            ("P1", "2026-01-01 08:10", 120.0),
        ])
        e = compute_energy_wh(df)
        self.assertAlmostEqual(float(e.iloc[0]), 60.0 * ENERGY_FIRST_SAMPLE_H, places=3)
        self.assertAlmostEqual(float(e.iloc[1]), 120.0 * (10.0 / 60.0), places=3)

    def test_large_gap_clipped_to_15min(self):
        """缺口 2 小時 → 間隔應被夾到 15 分鐘，而非用 2 小時灌水。"""
        df = _df([
            ("P1", "2026-01-01 08:00", 60.0),
            ("P1", "2026-01-01 10:00", 100.0),   # 2 小時缺口
        ])
        e = compute_energy_wh(df)
        self.assertAlmostEqual(float(e.iloc[1]), 100.0 * ENERGY_GAP_CAP_H, places=3)

    def test_duplicate_timestamp_yields_zero(self):
        """同面板同時間戳重複 → 間隔 0 → 能量 0（天然去重）。"""
        df = _df([
            ("P1", "2026-01-01 08:00", 60.0),
            ("P1", "2026-01-01 08:00", 60.0),
        ])
        e = compute_energy_wh(df)
        # 兩筆其中一筆為首筆(10min)，另一筆間隔 0 → 0 Wh
        self.assertIn(0.0, [round(float(v), 6) for v in e])

    def test_panels_are_independent(self):
        """不同面板各自從首筆 10 分鐘起算，不互相污染。"""
        df = _df([
            ("P1", "2026-01-01 08:00", 60.0),
            ("P2", "2026-01-01 08:05", 90.0),
        ])
        e = compute_energy_wh(df)
        # 兩筆都是各自面板首筆 → 都用 10 分鐘
        for v, p in zip(e, df["power_W"]):
            self.assertAlmostEqual(float(v), p * ENERGY_FIRST_SAMPLE_H, places=3)
