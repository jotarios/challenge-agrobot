"""Unit tests for alert cooldown logic."""

from datetime import datetime, timedelta, timezone

from src.shared.constants import ALERT_COOLDOWN_MINUTES


class TestCooldownLogic:
    """Tests the cooldown window check used by the Dispatcher.

    The Dispatcher skips notification if:
        now() - last_notified_at < ALERT_COOLDOWN_MINUTES
    """

    def _is_cooldown_active(self, last_notified_at: datetime | None) -> bool:
        """Replicate the Dispatcher's cooldown check."""
        if last_notified_at is None:
            return False
        cooldown_until = last_notified_at + timedelta(minutes=ALERT_COOLDOWN_MINUTES)
        return datetime.now(timezone.utc) < cooldown_until

    def test_no_previous_notification(self):
        assert self._is_cooldown_active(None) is False

    def test_just_notified(self):
        # Notified right now, cooldown should be active
        assert self._is_cooldown_active(datetime.now(timezone.utc)) is True

    def test_notified_1_minute_ago(self):
        one_min_ago = datetime.now(timezone.utc) - timedelta(minutes=1)
        assert self._is_cooldown_active(one_min_ago) is True

    def test_notified_14_minutes_ago(self):
        fourteen_min_ago = datetime.now(timezone.utc) - timedelta(minutes=14)
        assert self._is_cooldown_active(fourteen_min_ago) is True

    def test_notified_exactly_15_minutes_ago(self):
        # At exactly the boundary, cooldown_until == now, so < fails, cooldown expired
        exactly_15 = datetime.now(timezone.utc) - timedelta(minutes=ALERT_COOLDOWN_MINUTES)
        assert self._is_cooldown_active(exactly_15) is False

    def test_notified_16_minutes_ago(self):
        sixteen_min_ago = datetime.now(timezone.utc) - timedelta(minutes=16)
        assert self._is_cooldown_active(sixteen_min_ago) is False

    def test_notified_1_hour_ago(self):
        one_hour_ago = datetime.now(timezone.utc) - timedelta(hours=1)
        assert self._is_cooldown_active(one_hour_ago) is False

    def test_notified_yesterday(self):
        yesterday = datetime.now(timezone.utc) - timedelta(days=1)
        assert self._is_cooldown_active(yesterday) is False

    def test_cooldown_constant_is_15(self):
        assert ALERT_COOLDOWN_MINUTES == 15
