from __future__ import annotations

from typing import Literal


Action = Literal['BUY_WATCH', 'SELL_WATCH', 'WAIT_CONFLICT', 'HOLD']
Confidence = Literal['high', 'medium', 'low']


class DecisionEngine:
    @staticmethod
    def decide_action(buy_score: int, sell_score: int) -> Action:
        if buy_score >= 72 and sell_score <= 45:
            return 'BUY_WATCH'
        if sell_score >= 72 and buy_score <= 45:
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
