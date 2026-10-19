"""Domain models and data structures for OCA tracking."""

from dataclasses import dataclass, field
from datetime import datetime
import hashlib
from typing import Optional, Dict, Any, List


@dataclass
class TrackingEvent:
    """Represents a single status or checkpoint event for a package."""
    tracking_number: str
    status: str
    motive: str = ""
    branch: str = ""
    event_date: str = ""
    raw_data: Optional[Dict[str, Any]] = None

    @property
    def event_hash(self) -> str:
        """SHA-256 signature of tracking_number:status:event_date (see sqlite-state-tracker skill)."""
        canonical = (
            f"{self.tracking_number.strip().upper()}:"
            f"{self.status.strip().lower()}:"
            f"{self.event_date.strip()}"
        )
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()

    @property
    def parsed_datetime(self) -> Optional[datetime]:
        """Attempts to parse event_date into a datetime object for sorting."""
        if not self.event_date:
            return None
        # Try common formats returned by OCA
        formats = [
            "%Y-%m-%dT%H:%M:%S",
            "%Y-%m-%d %H:%M:%S",
            "%d/%m/%Y %H:%M:%S",
            "%d/%m/%Y %H:%M",
            "%Y-%m-%d",
            "%d/%m/%Y",
        ]
        clean_date = self.event_date.strip()
        for fmt in formats:
            try:
                return datetime.strptime(clean_date, fmt)
            except ValueError:
                continue
        return None


@dataclass
class TrackingResponse:
    """Represents the complete result of querying the OCA API for a package."""
    tracking_number: str
    events: List[TrackingEvent] = field(default_factory=list)
    success: bool = True
    error_message: Optional[str] = None

    @property
    def latest_event(self) -> Optional[TrackingEvent]:
        """Returns the most recent event (last row; OCA lists events chronologically)."""
        return self.events[-1] if self.events else None

    @property
    def is_delivered(self) -> bool:
        """Determines if the package has been delivered."""
        for ev in self.events:
            status_lower = ev.status.lower()
            if "entregad" in status_lower or "entrega efectuada" in status_lower:
                return True
        return False


@dataclass
class PackageConfig:
    """Configuration and current state of a tracked package."""
    tracking_number: str
    alias: str
    active: bool = True
    current_status: str = "Pendiente"
    last_event_date: Optional[str] = None
    last_checked_at: Optional[str] = None
    is_delivered: bool = False


@dataclass
class DeltaResult:
    """Represents new, unrecorded tracking events detected for a package."""
    package: PackageConfig
    new_events: List[TrackingEvent]
    previous_status: Optional[str]
    current_status: Optional[str]

    @property
    def has_deltas(self) -> bool:
        return len(self.new_events) > 0
