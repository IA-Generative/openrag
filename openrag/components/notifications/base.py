"""Base class for notification dispatchers."""

from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass
class DispatchResult:
    success: bool
    message: str = ""
    error: str | None = None


class BaseDispatcher(ABC):
    """Abstract base for notification dispatchers."""

    def __init__(self, config: dict):
        self.config = config

    @abstractmethod
    async def send(self, title: str, body: str, url: str | None = None) -> DispatchResult:
        """Send a notification.

        Args:
            title: Announcement title
            body: Announcement body (markdown)
            url: Optional link (e.g., poll voting page)

        Returns:
            DispatchResult indicating success or failure
        """
        ...

    async def send_test(self) -> DispatchResult:
        """Send a test notification to verify configuration."""
        return await self.send(
            title="OpenRAG Test Notification",
            body="This is a test notification from OpenRAG. If you received this, your notification channel is configured correctly.",
        )
