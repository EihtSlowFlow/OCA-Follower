"""Base class for alert notifiers."""

from abc import ABC, abstractmethod
from src.models import DeltaResult


class BaseNotifier(ABC):
    """Abstract base notifier interface."""

    @abstractmethod
    def notify(self, delta: DeltaResult) -> bool:
        """Formats and dispatches a notification for newly detected events.
        
        Returns True if successful, False otherwise.
        """
        pass

    @abstractmethod
    def send_raw_message(self, message: str) -> bool:
        """Sends an arbitrary formatted text message."""
        pass
