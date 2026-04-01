"""Kapso notification provider."""

import logging

import httpx

from src.providers.base import NotificationProvider
from src.shared.config import settings

logger = logging.getLogger(__name__)


class KapsoProvider(NotificationProvider):
    def __init__(self):
        self._client = httpx.AsyncClient(timeout=10.0)

    async def send(
        self,
        user_id: int,
        rule_id: int,
        triggered_value: float,
        correlation_id: str,
        metric_type: str = "",
    ) -> bool:
        payload = {
            "user_id": user_id,
            "rule_id": rule_id,
            "metric_type": metric_type,
            "triggered_value": triggered_value,
            "correlation_id": correlation_id,
        }

        response = await self._client.post(
            settings.kapso_api_url,
            json=payload,
            headers={"Authorization": f"Bearer {settings.kapso_api_key}"},
        )

        if response.status_code >= 500:
            logger.warning(
                "Kapso 5xx: status=%d correlation_id=%s",
                response.status_code,
                correlation_id,
            )
            raise KapsoServerError(f"Kapso returned {response.status_code}")

        if response.status_code >= 400:
            logger.error(
                "Kapso 4xx: status=%d correlation_id=%s body=%s",
                response.status_code,
                correlation_id,
                response.text,
            )
            raise KapsoClientError(f"Kapso returned {response.status_code}")

        # Validate response body
        try:
            response.json()
        except Exception:
            logger.error(
                "Kapso malformed response: correlation_id=%s body=%s",
                correlation_id,
                response.text[:200],
            )
            raise KapsoResponseError("Kapso returned malformed response")

        logger.info("Notification sent: correlation_id=%s", correlation_id)
        return True


class KapsoServerError(Exception):
    pass


class KapsoClientError(Exception):
    pass


class KapsoResponseError(Exception):
    pass
