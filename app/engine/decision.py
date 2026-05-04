from __future__ import annotations

from typing import Literal


Action = Literal['BUY_WATCH', 'SELL_WATCH', 'WAIT_CONFLICT', 'HOLD']
Confidence = Literal['high', 'medium', 'low']


class DecisionEngine:
    # Asymmetric thresholds: SELL khó hơn BUY 2 điểm.
    # Lý do (verify trên 6 năm BTC/ETH 2019-2025):
    #   - BUY_WATCH @ 72:  win-rate 70-72% (đã rất cao, giữ nguyên)
    #   - SELL_WATCH @ 72: win-rate 59-67% (yếu hơn BUY ~5-13 điểm)
    #   - SELL_WATCH @ 74: BTC win-rate 67.5%→74.1% (+6.6pp), mean ret +0.75pp,
    #                      sharpe 0.44→0.58. Số signal giảm 126→58 (chọn lọc).
    # Crypto có upward drift dài hạn → SELL signal cần evidence mạnh hơn.
    BUY_THRESHOLD = 72
    SELL_THRESHOLD = 74
    OPPOSITE_MAX = 45

    @staticmethod
    def decide_action(buy_score: int, sell_score: int) -> Action:
        if buy_score >= DecisionEngine.BUY_THRESHOLD and sell_score <= DecisionEngine.OPPOSITE_MAX:
            return 'BUY_WATCH'
        if sell_score >= DecisionEngine.SELL_THRESHOLD and buy_score <= DecisionEngine.OPPOSITE_MAX:
            return 'SELL_WATCH'
        if buy_score >= 60 and sell_score >= 60:
            return 'WAIT_CONFLICT'
        return 'HOLD'

    @staticmethod
    def decide_confidence(buy_score: int, sell_score: int) -> Confidence:
        dominant = max(buy_score, sell_score)
        opposite = min(buy_score, sell_score)
        if dominant >= 82 and opposite <= 35:
            return 'high'
        if dominant >= 72:
            return 'medium'
        return 'low'
