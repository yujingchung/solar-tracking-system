#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
decision_layer.py
=================
論文 5.4 實驗組策略「效益評估層」：決定是否值得移動

輸入：當前角度、目標角度、當前功率、預測功率、推桿能耗特性
輸出：(should_move: bool, reason: str, details: dict)

決策邏輯（cost-benefit）：
    淨能源收益 = 預期增益 × 持續時間 − 移動能耗 − safety_margin

    移動能耗 ≈ 推桿平均功率 × 估計移動時間
        - 估計移動時間 = max(Δtilt, Δazi) / 推桿角速度
        - 推桿平均功率 = 從歷史 INA3221 CH1 量測平均

    預期增益 = (predicted_power - current_power)
    持續時間 = 下一次決策週期長度（如 600s）

可調參數：
    actuator_power_w        推桿運作平均功率 (W)
    actuator_deg_per_sec    推桿角速度 (°/s)
    safety_margin_j         決策安全餘量 (J)，避免邊界處頻繁進出
    min_gain_threshold      最低絕對增益門檻 (W)，過小直接拒絕
"""
from dataclasses import dataclass, field
from typing import Optional, Dict, Tuple


@dataclass
class DecisionConfig:
    # 推桿能耗特性（從硬體手冊或實測得到）
    actuator_power_w: float = 30.0          # HB-DJ809 額定 ~30W
    actuator_deg_per_sec: float = 2.0       # 推桿速度（保守值）

    # 決策週期（必須與控制器 interval_seconds 一致）
    cycle_seconds: float = 600.0

    # 拒絕門檻
    min_gain_threshold_w: float = 1.0       # 增益 < 1W 不考慮（量測噪聲級）
    safety_margin_j: float = 50.0           # 安全餘量（焦耳）

    # 移動上限保護
    max_move_degrees: float = 35.0          # 單次移動角度上限（避免遠程跳轉）


@dataclass
class DecisionDetails:
    delta_tilt: float
    delta_azi: float
    move_degrees: float                     # max(|Δtilt|, |Δazi|)
    estimated_move_seconds: float
    estimated_move_cost_j: float
    expected_gain_w: float
    expected_gain_j: float                  # gain × cycle - move duration
    net_benefit_j: float
    threshold_j: float
    should_move: bool
    reason: str


class MovementDecisionLayer:
    """效益評估決策層"""

    def __init__(self, config: Optional[DecisionConfig] = None):
        self.config = config or DecisionConfig()

    def evaluate(self,
                  current_tilt: float, current_azi: float,
                  target_tilt: float,  target_azi: float,
                  current_power_w: float,
                  predicted_power_w: float,
                  actuator_power_w: Optional[float] = None
                  ) -> DecisionDetails:
        """
        判斷是否值得從 (current_tilt, current_azi) 移動到 (target_tilt, target_azi)

        Parameters
        ----------
        current_power_w     當前實測功率
        predicted_power_w   ANFIS 對 target 角度的預測功率
        actuator_power_w    可選，本次決策用的推桿功率（覆寫 config 預設）
        """
        c = self.config
        act_p = actuator_power_w if actuator_power_w is not None \
                                else c.actuator_power_w

        d_tilt = target_tilt - current_tilt
        d_azi  = target_azi  - current_azi
        move_deg = max(abs(d_tilt), abs(d_azi))

        # 短路：移動距離為 0 或微小 → 不動
        if move_deg < 0.5:
            return DecisionDetails(
                delta_tilt=d_tilt, delta_azi=d_azi, move_degrees=move_deg,
                estimated_move_seconds=0.0, estimated_move_cost_j=0.0,
                expected_gain_w=predicted_power_w - current_power_w,
                expected_gain_j=0.0, net_benefit_j=0.0,
                threshold_j=c.safety_margin_j, should_move=False,
                reason='已在目標附近（移動角度 < 0.5°）',
            )

        # 短路：移動角度過大（可能異常）
        if move_deg > c.max_move_degrees:
            return DecisionDetails(
                delta_tilt=d_tilt, delta_azi=d_azi, move_degrees=move_deg,
                estimated_move_seconds=0.0, estimated_move_cost_j=0.0,
                expected_gain_w=predicted_power_w - current_power_w,
                expected_gain_j=0.0, net_benefit_j=0.0,
                threshold_j=c.safety_margin_j, should_move=False,
                reason=f'移動角度過大 ({move_deg:.1f}° > {c.max_move_degrees}°)',
            )

        # 增益（瓦）
        gain_w = predicted_power_w - current_power_w

        # 短路：增益小於量測雜訊
        if gain_w < c.min_gain_threshold_w:
            return DecisionDetails(
                delta_tilt=d_tilt, delta_azi=d_azi, move_degrees=move_deg,
                estimated_move_seconds=0.0, estimated_move_cost_j=0.0,
                expected_gain_w=gain_w, expected_gain_j=0.0,
                net_benefit_j=-c.safety_margin_j, threshold_j=c.safety_margin_j,
                should_move=False,
                reason=f'預測增益 {gain_w:.2f}W < 門檻 {c.min_gain_threshold_w}W',
            )

        # 移動時間估計
        move_sec = move_deg / c.actuator_deg_per_sec

        # 移動能耗（焦耳） = power × time
        move_cost_j = act_p * move_sec

        # 增益累積能量（焦耳）= gain × 有效時段
        # 有效時段 = 整個 cycle - 移動本身佔用的時間
        effective_sec = max(0.0, c.cycle_seconds - move_sec)
        gain_j = gain_w * effective_sec

        # 淨收益 = 增益能量 - 移動能耗
        net_j = gain_j - move_cost_j

        # 決策：淨收益 > safety_margin 才動
        should_move = net_j > c.safety_margin_j

        if should_move:
            reason = (f'淨收益 +{net_j:.1f}J 大於餘量 {c.safety_margin_j}J')
        else:
            reason = (f'淨收益 {net_j:+.1f}J 不達餘量 {c.safety_margin_j}J '
                      f'(增益{gain_j:.1f}J - 移動{move_cost_j:.1f}J)')

        return DecisionDetails(
            delta_tilt=d_tilt, delta_azi=d_azi, move_degrees=move_deg,
            estimated_move_seconds=move_sec,
            estimated_move_cost_j=move_cost_j,
            expected_gain_w=gain_w, expected_gain_j=gain_j,
            net_benefit_j=net_j, threshold_j=c.safety_margin_j,
            should_move=should_move, reason=reason,
        )


# ════════════════════════════════════════════════════════════════
# 單元測試
# ════════════════════════════════════════════════════════════════
if __name__ == '__main__':
    layer = MovementDecisionLayer()

    print("=== Cost-Benefit Decision Layer 測試 ===\n")

    # Case 1: 大增益、小移動 → 應該動
    r = layer.evaluate(current_tilt=20, current_azi=180,
                       target_tilt=25, target_azi=185,
                       current_power_w=150, predicted_power_w=180)
    print(f"Case 1 (Δ=5°, gain=30W): should_move={r.should_move}")
    print(f"  reason: {r.reason}\n")

    # Case 2: 小增益、大移動 → 不該動
    r = layer.evaluate(current_tilt=20, current_azi=180,
                       target_tilt=35, target_azi=200,
                       current_power_w=150, predicted_power_w=152)
    print(f"Case 2 (Δ=20°, gain=2W): should_move={r.should_move}")
    print(f"  reason: {r.reason}\n")

    # Case 3: 增益為負 → 不該動
    r = layer.evaluate(current_tilt=20, current_azi=180,
                       target_tilt=25, target_azi=185,
                       current_power_w=200, predicted_power_w=180)
    print(f"Case 3 (Δ=5°, gain=-20W): should_move={r.should_move}")
    print(f"  reason: {r.reason}\n")

    # Case 4: 已在目標 → 不動
    r = layer.evaluate(current_tilt=20.1, current_azi=180.2,
                       target_tilt=20.3, target_azi=180.0,
                       current_power_w=150, predicted_power_w=160)
    print(f"Case 4 (在目標附近): should_move={r.should_move}")
    print(f"  reason: {r.reason}\n")
