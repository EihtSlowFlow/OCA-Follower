"""Notification dispatchers package."""

from src.notifiers.base import BaseNotifier
from src.notifiers.whatsapp import CallMeBotWhatsAppNotifier

__all__ = ["BaseNotifier", "CallMeBotWhatsAppNotifier"]
