from __future__ import annotations

import json
import logging
from typing import Any

from openai import AsyncOpenAI

from app.ai.prompts import SYSTEM_PROMPT, build_user_prompt
from app.models.schema import OpenAIAnalysis, SignalState

logger = logging.getLogger(__name__)


class OpenAIAnalyzer:
    def __init__(self, api_key: str | None, model: str) -> None:
        self._model = model
        self._client = AsyncOpenAI(api_key=api_key) if api_key else None

    async def analyze(self, signal: SignalState) -> OpenAIAnalysis:
        if self._client is None:
            return OpenAIAnalysis()

        payload = {
            'symbol': signal.symbol,
            'action': signal.action,
            'confidence': signal.confidence,
            'buy_score': signal.buy_score,
            'sell_score': signal.sell_score,
            'price': signal.price,
            'support': signal.support,
            'resistance': signal.resistance,
            'invalidation': signal.invalidation,
            'timeframes': [
                {
                    'timeframe': score.timeframe,
                    'buy_score': score.buy_score,
                    'sell_score': score.sell_score,
                    'support': score.support,
                    'resistance': score.resistance,
                    'invalidation': score.invalidation,
                    'close': score.indicators.close,
                    'ema_50': score.indicators.ema_50,
                    'ema_200': score.indicators.ema_200,
                    'rsi_14': score.indicators.rsi_14,
                    'macd_histogram': score.indicators.macd_histogram,
                    'reasons': score.reasons[:4],
                }
                for score in signal.timeframe_scores
            ],
            'reasons': signal.reasons[:8],
        }

        try:
            response = await self._client.responses.create(
                model=self._model,
                input=[
                    {'role': 'system', 'content': SYSTEM_PROMPT},
                    {'role': 'user', 'content': build_user_prompt(payload)},
                ],
                text={
                    'format': {
                        'type': 'json_schema',
                        'name': 'technical_signal_ai_analysis',
                        'schema': {
                            'type': 'object',
                            'properties': {
                                'summary': {'type': 'string'},
                                'risk_notes': {'type': 'array', 'items': {'type': 'string'}},
                                'conflicts': {'type': 'array', 'items': {'type': 'string'}},
                                'telegram_note': {'type': 'string'},
                                'data_quality_warning': {'type': 'boolean'},
                            },
                            'required': [
                                'summary',
                                'risk_notes',
                                'conflicts',
                                'telegram_note',
                                'data_quality_warning',
                            ],
                            'additionalProperties': False,
                        },
                    }
                },
            )
            content: dict[str, Any] = json.loads(response.output_text)
            return OpenAIAnalysis.model_validate(content)
        except Exception as exc:  # noqa: BLE001
            logger.warning('OpenAI analysis failed for %s: %s', signal.symbol, exc)
            return OpenAIAnalysis()
