"""Abstract notification provider interface.

All notification channels (Kapso, SNS, SES, etc.) implement this interface.
The Dispatcher Lambda calls provider.send() with post-validation enriched data
after the Claim Check passes.
"""

from abc import ABC, abstractmethod


class NotificationProvider(ABC):
    @abstractmethod
    async def send(
        self,
        user_id: int,
        rule_id: int,
        triggered_value: float,
        correlation_id: str,
        metric_type: str = "",
    ) -> bool:
        """Send a notification. Returns True on success, raises on failure."""
        ...
