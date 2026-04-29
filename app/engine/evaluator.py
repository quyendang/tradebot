from __future__ import annotations

from app.ai.openai_analyzer import OpenAIAnalyzer
from app.engine.decision import DecisionEngine
from app.engine.scorer import TechnicalScorer
from app.models.schema import OpenAIAnalysis, PriceZone, SignalState, TimeframeScore


TIMEFRAME_WEIGHTS: dict[str, float] = {
    '1h': 0.25,
    '4h': 0.35,
    '1d': 0.40,
}


class SignalEvaluator:
    def __init__(self, ai_analyzer: OpenAIAnalyzer) -> None:
        self._scorer = TechnicalScorer()
        self._decision_engine = DecisionEngine()
        self._ai_analyzer = ai_analyzer

    async def evaluate(self, symbol: str, timeframe_frames: dict[str, object]) -> SignalState:
        timeframe_scores = [
            self._scorer.score_timeframe(symbol, timeframe, frame)
            for timeframe, frame in timeframe_frames.items()
        ]

        buy_score = self._weighted_score(timeframe_scores, 'buy_score')
        sell_score = self._weighted_score(timeframe_scores, 'sell_score')
        technical_action = self._decision_engine.decide_action(buy_score, sell_score)
        confidence = self._decision_engine.decide_confidence(buy_score, sell_score)

        reference = timeframe_scores[-1]
        price = timeframe_frames['1h'].iloc[-1]['close']
        support = self._weighted_float(timeframe_scores, 'support')
        resistance = self._weighted_float(timeframe_scores, 'resistance')

        if technical_action == 'BUY_WATCH':
            invalidation = support - reference.indicators.atr_14
        elif technical_action == 'SELL_WATCH':
            invalidation = resistance + reference.indicators.atr_14
        elif buy_score >= sell_score:
            invalidation = support - (reference.indicators.atr_14 * 0.5)
        else:
            invalidation = resistance + (reference.indicators.atr_14 * 0.5)

        reasons = self._aggregate_reasons(timeframe_scores, buy_score, sell_score, technical_action)
        buy_zone, sell_zone = self._build_price_zones(
            timeframe_scores=timeframe_scores,
            price=float(price),
            support=support,
            resistance=resistance,
            action=technical_action,
        )
        signal = SignalState(
            symbol=symbol,
            action=technical_action,
            confidence=confidence,
            buy_score=buy_score,
            sell_score=sell_score,
            price=float(price),
            support=support,
            resistance=resistance,
            invalidation=float(invalidation),
            as_of=reference.indicators.close_time,
            reasons=reasons,
            timeframe_scores=timeframe_scores,
            ai_analysis=OpenAIAnalysis(),
            buy_zone=buy_zone,
            sell_zone=sell_zone,
        )

        ai_analysis = await self._ai_analyzer.analyze(signal)
        signal.ai_analysis = ai_analysis
        if ai_analysis.data_quality_warning:
            signal.action = 'HOLD'
            if 'AI flagged data quality warning' not in signal.reasons:
                signal.reasons.insert(0, 'AI flagged data quality warning')
        return signal

    def _build_price_zones(
        self,
        timeframe_scores: list[TimeframeScore],
        price: float,
        support: float,
        resistance: float,
        action: str,
    ) -> tuple[PriceZone | None, PriceZone | None]:
        reference = timeframe_scores[-1]
        atr = reference.indicators.atr_14
        ema_50 = reference.indicators.ema_50
        bb_lower = reference.indicators.bollinger_lower
        bb_upper = reference.indicators.bollinger_upper

        pullback_buy_low = min(support - (atr * 0.25), bb_lower)
        pullback_buy_high = min(max(support + (atr * 0.35), support), ema_50)
        breakout_buy_low = max(resistance - (atr * 0.15), support)
        breakout_buy_high = resistance + (atr * 0.45)

        rejection_sell_low = max(resistance - (atr * 0.35), ema_50)
        rejection_sell_high = max(resistance + (atr * 0.25), bb_upper)
        breakdown_sell_low = support - (atr * 0.45)
        breakdown_sell_high = min(support + (atr * 0.15), resistance)

        if action == 'BUY_WATCH' and price >= resistance * 0.992:
            buy_zone = PriceZone(
                low=float(breakout_buy_low),
                high=float(breakout_buy_high),
                zone_type='breakout_buy',
                note='Vùng mua breakout nếu giá vượt kháng cự với động lượng tốt.',
            )
        else:
            buy_zone = PriceZone(
                low=float(min(pullback_buy_low, pullback_buy_high)),
                high=float(max(pullback_buy_low, pullback_buy_high)),
                zone_type='pullback_buy',
                note='Vùng mua pullback quanh hỗ trợ và EMA ngắn hạn.',
            )

        if action == 'SELL_WATCH' and price <= support * 1.008:
            sell_zone = PriceZone(
                low=float(min(breakdown_sell_low, breakdown_sell_high)),
                high=float(max(breakdown_sell_low, breakdown_sell_high)),
                zone_type='breakdown_sell',
                note='Vùng bán breakdown nếu giá thủng hỗ trợ quan trọng.',
            )
        else:
            sell_zone = PriceZone(
                low=float(min(rejection_sell_low, rejection_sell_high)),
                high=float(max(rejection_sell_low, rejection_sell_high)),
                zone_type='rejection_sell',
                note='Vùng bán/reduce quanh kháng cự khi xuất hiện từ chối giá.',
            )

        return buy_zone, sell_zone

    def _weighted_score(self, timeframe_scores: list[TimeframeScore], field: str) -> int:
        total = 0.0
        weight_total = 0.0
        for score in timeframe_scores:
            weight = TIMEFRAME_WEIGHTS.get(score.timeframe, 1 / max(len(timeframe_scores), 1))
            total += getattr(score, field) * weight
            weight_total += weight
        return round(total / weight_total) if weight_total else 0

    def _weighted_float(self, timeframe_scores: list[TimeframeScore], field: str) -> float:
        total = 0.0
        weight_total = 0.0
        for score in timeframe_scores:
            weight = TIMEFRAME_WEIGHTS.get(score.timeframe, 1 / max(len(timeframe_scores), 1))
            total += float(getattr(score, field)) * weight
            weight_total += weight
        return float(total / weight_total) if weight_total else 0.0

    def _aggregate_reasons(
        self,
        timeframe_scores: list[TimeframeScore],
        buy_score: int,
        sell_score: int,
        action: str,
    ) -> list[str]:
        reasons = [f'Action {action} from buy_score={buy_score} and sell_score={sell_score}']
        for score in timeframe_scores:
            reasons.extend(score.reasons[:4])
        return reasons[:16]
