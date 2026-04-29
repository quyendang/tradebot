from __future__ import annotations

import logging

import httpx

from app.config import Settings
from app.models.schema import SignalState

logger = logging.getLogger(__name__)


class TelegramNotifier:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    def is_enabled(self) -> bool:
        return bool(self._settings.telegram_bot_token and self._settings.telegram_chat_id)

    def build_message(self, signal: SignalState) -> str:
        risks = ', '.join(signal.ai_analysis.risk_notes[:3]) or 'None'
        conflicts = ', '.join(signal.ai_analysis.conflicts[:3]) or 'None'
        dominant_score = max(signal.buy_score, signal.sell_score)
        return (
            f'{signal.symbol} | {signal.action} | {signal.confidence}\n'
            f'Price: {signal.price:.2f}\n'
            f'Buy: {signal.buy_score} | Sell: {signal.sell_score} | Dominant: {dominant_score}\n'
            f'Support: {signal.support:.2f} | Resistance: {signal.resistance:.2f}\n'
            f'Invalidation: {signal.invalidation:.2f}\n'
            f'Summary: {signal.ai_analysis.summary}\n'
            f'Note: {signal.ai_analysis.telegram_note}\n'
            f'Risks: {risks}\n'
            f'Conflicts: {conflicts}'
        )

    def build_startup_message(
        self,
        signals: dict[str, SignalState],
        interval_seconds: int,
        startup_error: str | None = None,
    ) -> str:
        lines = [
            'Tradebot started',
            f'Interval: {interval_seconds}s',
            f'OpenAI configured: {"yes" if self._settings.openai_api_key else "no"}',
        ]

        if startup_error is not None:
            lines.append(f'Initial analysis error: {startup_error}')
            return '\n'.join(lines)

        if not signals:
            lines.append('Initial analysis: no signals available')
            return '\n'.join(lines)

        lines.append('Initial analysis:')
        for symbol in sorted(signals):
            signal = signals[symbol]
            ai_status = (
                'warning'
                if signal.ai_analysis.data_quality_warning
                else 'ok'
                if signal.ai_analysis.summary != 'AI analysis unavailable'
                else 'unavailable'
            )
            lines.append(
                f'{signal.symbol}: {signal.action} {signal.confidence} | '
                f'Buy {signal.buy_score} Sell {signal.sell_score} | AI {ai_status}'
            )
            lines.append(f'Note: {signal.ai_analysis.telegram_note}')

        return '\n'.join(lines)

    async def send_text(self, text: str) -> str | None:
        if not self.is_enabled():
            logger.info('Telegram not configured, skipping text notification')
            return None

        payload = {
            'chat_id': self._settings.telegram_chat_id,
            'text': text,
        }
        url = f'https://api.telegram.org/bot{self._settings.telegram_bot_token}/sendMessage'
        timeout = httpx.Timeout(self._settings.request_timeout_seconds)

        try:
            async with httpx.AsyncClient(timeout=timeout) as client:
                response = await client.post(url, json=payload)
                response.raise_for_status()
            return payload['text']
        except Exception as exc:  # noqa: BLE001
            logger.warning('Telegram startup/status send failed: %s', exc)
            return None

    async def send(self, signal: SignalState) -> str | None:
        if not self.is_enabled():
            logger.info('Telegram not configured, skipping notification for %s', signal.symbol)
            return None
        return await self.send_text(self.build_message(signal))
