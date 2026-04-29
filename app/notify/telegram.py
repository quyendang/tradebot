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
        risks = self._format_list(signal.ai_analysis.risk_notes, default='Khong co')
        conflicts = self._format_list(signal.ai_analysis.conflicts, default='Khong co')
        dominant_score = max(signal.buy_score, signal.sell_score)
        dominant_side = 'Mua' if signal.buy_score >= signal.sell_score else 'Ban'
        return (
            f'Tradebot | {signal.symbol}\n'
            f'Tin hieu: {self._action_label(signal.action)}\n'
            f'Do tin cay: {self._confidence_label(signal.confidence)}\n'
            f'Gia hien tai: {signal.price:.2f}\n'
            f'Diem uu the: {dominant_side} ({dominant_score})\n'
            f'Diem Mua/Ban: {signal.buy_score}/{signal.sell_score}\n'
            f'Ho tro: {signal.support:.2f}\n'
            f'Khang cu: {signal.resistance:.2f}\n'
            f'Moc vo hieu: {signal.invalidation:.2f}\n'
            f'\n'
            f'Tom tat AI:\n{signal.ai_analysis.summary}\n'
            f'\n'
            f'Ghi chu nhanh:\n{signal.ai_analysis.telegram_note}\n'
            f'\n'
            f'Rui ro:\n{risks}\n'
            f'\n'
            f'Xung dot:\n{conflicts}'
        )

    def build_startup_message(
        self,
        signals: dict[str, SignalState],
        interval_seconds: int,
        startup_error: str | None = None,
    ) -> str:
        lines = [
            'Tradebot da khoi dong',
            f'Chu ky quet: {interval_seconds}s',
            f'OpenAI: {"da cau hinh" if self._settings.openai_api_key else "chua cau hinh"}',
        ]

        if startup_error is not None:
            lines.append(f'Loi phan tich ban dau: {startup_error}')
            return '\n'.join(lines)

        if not signals:
            lines.append('Phan tich ban dau: chua co du lieu')
            return '\n'.join(lines)

        lines.append('Phan tich ban dau:')
        for symbol in sorted(signals):
            signal = signals[symbol]
            ai_status = self._ai_status_label(signal)
            lines.append(
                f'{signal.symbol}: {self._action_label(signal.action)} | '
                f'{self._confidence_label(signal.confidence)} | '
                f'M/B {signal.buy_score}/{signal.sell_score} | AI {ai_status}'
            )
            lines.append(f'Nhanh: {signal.ai_analysis.telegram_note}')

        return '\n'.join(lines)

    @staticmethod
    def _format_list(items: list[str], default: str) -> str:
        if not items:
            return default
        return '\n'.join(f'- {item}' for item in items[:3])

    @staticmethod
    def _action_label(action: str) -> str:
        labels = {
            'BUY_WATCH': 'Theo doi Mua',
            'SELL_WATCH': 'Theo doi Ban',
            'WAIT_CONFLICT': 'Cho xac nhan',
            'HOLD': 'Dung quan sat',
        }
        return labels.get(action, action)

    @staticmethod
    def _confidence_label(confidence: str) -> str:
        labels = {
            'high': 'Cao',
            'medium': 'Trung binh',
            'low': 'Thap',
        }
        return labels.get(confidence, confidence)

    @staticmethod
    def _ai_status_label(signal: SignalState) -> str:
        if signal.ai_analysis.data_quality_warning:
            return 'Canh bao du lieu'
        if signal.ai_analysis.summary == 'AI analysis unavailable':
            return 'Khong kha dung'
        return 'Binh thuong'

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
