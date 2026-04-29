from __future__ import annotations

import json
import logging
from typing import Any
from urllib.parse import urlparse

from openai import AsyncOpenAI

from app.ai.prompts import SYSTEM_PROMPT, build_user_prompt
from app.models.schema import OpenAIAnalysis, SignalState

logger = logging.getLogger(__name__)


class OpenAIAnalyzer:
    def __init__(self, api_key: str | None, model: str, base_url: str | None = None) -> None:
        self._model = model
        normalized_base_url = self._normalize_base_url(base_url)
        self._client = AsyncOpenAI(api_key=api_key, base_url=normalized_base_url) if api_key else None

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
            content = await self._analyze_with_responses(payload)
            return OpenAIAnalysis.model_validate(content)
        except Exception as responses_exc:  # noqa: BLE001
            logger.warning(
                'OpenAI responses API failed for %s, falling back to chat.completions: %s',
                signal.symbol,
                responses_exc,
            )
        try:
            content = await self._analyze_with_chat_completions(payload)
            return OpenAIAnalysis.model_validate(content)
        except Exception as exc:  # noqa: BLE001
            logger.warning('OpenAI analysis failed for %s: %s', signal.symbol, exc)
            return OpenAIAnalysis()

    async def _analyze_with_responses(self, payload: dict[str, Any]) -> dict[str, Any]:
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
                    'schema': self._analysis_schema(),
                }
            },
        )
        return json.loads(response.output_text)

    async def _analyze_with_chat_completions(self, payload: dict[str, Any]) -> dict[str, Any]:
        response = await self._client.chat.completions.create(
            model=self._model,
            messages=[
                {'role': 'system', 'content': SYSTEM_PROMPT},
                {'role': 'user', 'content': build_user_prompt(payload)},
            ],
            response_format={
                'type': 'json_schema',
                'json_schema': {
                    'name': 'technical_signal_ai_analysis',
                    'schema': self._analysis_schema(),
                },
            },
        )
        content = response.choices[0].message.content
        if not content:
            raise ValueError('Empty chat completion content')
        return json.loads(content)

    @staticmethod
    def _analysis_schema() -> dict[str, Any]:
        return {
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
        }

    @staticmethod
    def _normalize_base_url(base_url: str | None) -> str | None:
        if not base_url:
            return None
        parsed = urlparse(base_url)
        path = parsed.path.rstrip('/')
        if path in ('', '/'):
            return base_url.rstrip('/') + '/v1'
        return base_url.rstrip('/')
