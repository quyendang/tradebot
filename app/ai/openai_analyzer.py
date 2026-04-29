from __future__ import annotations

import asyncio
import json
import logging
from typing import Any
from urllib.parse import urlparse

from openai import AsyncOpenAI
from portkey_ai import Portkey

from app.ai.prompts import SYSTEM_PROMPT, build_user_prompt
from app.models.schema import OpenAIAnalysis, SignalState

logger = logging.getLogger(__name__)


class OpenAIAnalyzer:
    def __init__(
        self,
        api_key: str | None,
        model: str,
        base_url: str | None = None,
        portkey_api_key: str | None = None,
        timeout_seconds: int = 20,
    ) -> None:
        self._model = model
        normalized_base_url = self._normalize_base_url(base_url)
        self._base_url = normalized_base_url
        self._timeout_seconds = timeout_seconds
        self._portkey_api_key = portkey_api_key
        self._use_portkey = bool(normalized_base_url and 'api.portkey.ai' in normalized_base_url)
        self._force_chat_completions = normalized_base_url is not None
        self._portkey_client = Portkey(api_key=portkey_api_key) if self._use_portkey and portkey_api_key else None
        self._client = None
        if not self._use_portkey and api_key:
            self._client = AsyncOpenAI(api_key=api_key, base_url=normalized_base_url)

    async def analyze(self, signal: SignalState) -> OpenAIAnalysis:
        if self._use_portkey:
            return await self._analyze_with_portkey(signal)
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

        if not self._force_chat_completions:
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

    async def _analyze_with_portkey(self, signal: SignalState) -> OpenAIAnalysis:
        if self._portkey_client is None:
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
            content = await asyncio.to_thread(self._portkey_chat_completion, payload)
            if not content:
                raise ValueError('Empty Portkey chat completion content')
            return OpenAIAnalysis.model_validate(json.loads(content))
        except Exception as exc:  # noqa: BLE001
            logger.warning('Portkey analysis failed for %s: %s', signal.symbol, exc)
            return OpenAIAnalysis()

    def _portkey_chat_completion(self, payload: dict[str, Any]) -> str:
        response = self._portkey_client.chat.completions.create(
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
            MAX_TOKENS=512,
        )
        return response.choices[0].message.content

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
