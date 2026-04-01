"""Mock notification provider for local development. Logs instead of sending."""

import logging

from src.providers.base import NotificationProvider

logger = logging.getLogger(__name__)


class MockProvider(NotificationProvider):
    async def send(
        self,
        user_id: int,
        rule_id: int,
        triggered_value: float,
        correlation_id: str,
        metric_type: str = "",
    ) -> bool:
        logger.info(
            "MOCK NOTIFICATION: user_id=%s rule_id=%s metric=%s value=%s correlation_id=%s",
            user_id, rule_id, metric_type, triggered_value, correlation_id,
        )
        return True
