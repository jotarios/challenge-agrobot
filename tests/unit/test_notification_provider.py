"""Unit tests for the notification provider interface."""

import pytest

from src.providers.base import NotificationProvider


class MockProvider(NotificationProvider):
    def __init__(self):
        self.sent = []

    async def send(self, user_id, rule_id, triggered_value, correlation_id, metric_type=""):
        self.sent.append({
            "user_id": user_id,
            "rule_id": rule_id,
            "triggered_value": triggered_value,
            "correlation_id": correlation_id,
            "metric_type": metric_type,
        })
        return True


class TestNotificationProvider:
    @pytest.mark.asyncio
    async def test_mock_provider_sends(self):
        provider = MockProvider()
        result = await provider.send(
            user_id=1, rule_id=42, triggered_value=36.5,
            correlation_id="test-123", metric_type="temperature",
        )
        assert result is True
        assert len(provider.sent) == 1
        assert provider.sent[0]["user_id"] == 1

    @pytest.mark.asyncio
    async def test_mock_provider_accumulates(self):
        provider = MockProvider()
        for i in range(5):
            await provider.send(
                user_id=i, rule_id=i, triggered_value=float(i),
                correlation_id=f"id-{i}",
            )
        assert len(provider.sent) == 5

    def test_cannot_instantiate_abstract(self):
        with pytest.raises(TypeError):
            NotificationProvider()
