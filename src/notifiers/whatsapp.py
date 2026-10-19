"""CallMeBot WhatsApp notification implementation."""

import logging
import re
from typing import Optional
import requests

from src.models import DeltaResult, TrackingEvent
from src.notifiers.base import BaseNotifier

logger = logging.getLogger(__name__)


class CallMeBotWhatsAppNotifier(BaseNotifier):
    """Dispatches WhatsApp alerts using CallMeBot HTTP API."""

    API_URL = "https://api.callmebot.com/whatsapp.php"

    def __init__(
        self,
        phone: Optional[str] = None,
        api_key: Optional[str] = None,
        timeout: int = 15,
        enabled: bool = True,
        session: Optional[requests.Session] = None,
    ):
        self.raw_phone = phone or ""
        self.phone = self._clean_phone(self.raw_phone)
        self.api_key = (api_key or "").strip()
        self.timeout = timeout
        self.enabled = enabled and bool(self.phone and self.api_key)
        self.session = session or requests.Session()

        if not self.enabled:
            logger.info("CallMeBot WhatsApp notifier is disabled (missing phone or api_key).")

    @staticmethod
    def _clean_phone(phone: str) -> str:
        """Strips '+', dashes, spaces, and non-numeric characters."""
        return re.sub(r"[^\d]", "", phone.strip())

    def format_event_message(self, delta: DeltaResult) -> str:
        """Constructs an aesthetic, emoji-rich WhatsApp markdown message."""
        pkg = delta.package
        events: list[TrackingEvent] = delta.new_events

        if not events:
            return ""

        # Take the most recent event from the delta batch
        latest = events[-1]

        # Choose status icon
        status_lower = latest.status.lower()
        if "entregad" in status_lower:
            status_icon = "✅"
        elif "sucursal" in status_lower:
            status_icon = "🏢"
        elif "distribuci" in status_lower or "móvil" in status_lower:
            status_icon = "🚚"
        elif "viaje" in status_lower or "tránsito" in status_lower:
            status_icon = "✈️"
        elif "planta" in status_lower:
            status_icon = "🏭"
        else:
            status_icon = "📦"

        lines = [
            "📦 *Novedad en tu paquete OCA*",
            "",
            f"🏷️ *Paquete:* {pkg.alias}",
            f"• *Estado:* {status_icon} *{latest.status}*",
            f"• *Fecha:* {latest.event_date or 'No informada'}",
            f"• *Ubicación:* {latest.branch or 'En tránsito'}",
            f"• *Tracking:* `{pkg.tracking_number}`",
        ]

        if delta.previous_status and delta.previous_status != latest.status:
            lines.append(f"🔄 *Estado anterior:* {delta.previous_status}")

        if latest.motive:
            lines.append(f"📝 *Detalle:* {latest.motive}")

        if len(events) > 1:
            lines.append(f"ℹ️ *(+ {len(events) - 1} evento(s) intermedio(s) registrados)*")

        if "entregad" in status_lower:
            lines.append("🎉 *¡Paquete entregado con éxito!*")

        return "\n".join(lines)

    def notify(self, delta: DeltaResult) -> bool:
        """Formats and sends alert for newly detected tracking events."""
        if not self.enabled:
            logger.debug("Notifier disabled. Skipping alert for %s", delta.package.tracking_number)
            return False

        message = self.format_event_message(delta)
        if not message:
            return False

        return self.send_raw_message(message)

    def send_raw_message(self, message: str) -> bool:
        """Sends raw message text to CallMeBot."""
        if not self.enabled:
            logger.warning("Attempted to send message, but CallMeBot is not enabled/configured.")
            return False

        params = {
            "phone": self.phone,
            "text": message,
            "apikey": self.api_key,
        }

        try:
            logger.info("Sending WhatsApp notification to %s via CallMeBot...", self.phone)
            response = self.session.get(self.API_URL, params=params, timeout=self.timeout)

            response_text = response.text.lower()
            if response.status_code == 200 and ("message queued" in response_text or "ok" in response_text):
                logger.info("WhatsApp notification delivered successfully.")
                return True
            else:
                logger.error(
                    "CallMeBot responded with status %d: %s",
                    response.status_code,
                    response.text.strip(),
                )
                return False

        except requests.RequestException as exc:
            logger.error("Network error sending WhatsApp alert: %s", exc)
            return False
