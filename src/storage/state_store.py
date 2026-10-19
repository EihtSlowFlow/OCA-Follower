"""SQLite state store for package tracking and delta detection."""

from datetime import datetime
import logging
import os
import sqlite3
from typing import List, Optional

from src.models import DeltaResult, PackageConfig, TrackingEvent

logger = logging.getLogger(__name__)


class StateStore:
    """Manages SQLite database connection, tables, and delta state operations."""

    def __init__(self, db_path: str = "data/tracker.db", timeout: float = 10.0, wal_mode: bool = True):
        self.db_path = db_path
        self.timeout = timeout
        self.wal_mode = wal_mode

        # Ensure parent directory exists
        db_dir = os.path.dirname(os.path.abspath(self.db_path))
        if db_dir and not os.path.exists(db_dir):
            os.makedirs(db_dir, exist_ok=True)

        self._init_db()

    def _get_connection(self) -> sqlite3.Connection:
        """Creates and configures a new SQLite connection."""
        conn = sqlite3.connect(self.db_path, timeout=self.timeout)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON;")
        conn.execute("PRAGMA busy_timeout = 5000;")
        if self.wal_mode:
            conn.execute("PRAGMA journal_mode = WAL;")
        return conn

    def _init_db(self):
        """Initializes tables and indexes if they do not exist."""
        schema = """
        CREATE TABLE IF NOT EXISTS packages (
            tracking_number TEXT PRIMARY KEY,
            alias TEXT NOT NULL,
            current_status TEXT DEFAULT 'Pendiente',
            last_event_date TEXT,
            last_checked_at TEXT,
            is_delivered INTEGER DEFAULT 0,
            active INTEGER DEFAULT 1,
            created_at TEXT DEFAULT (datetime('now', 'localtime')),
            updated_at TEXT DEFAULT (datetime('now', 'localtime'))
        );

        CREATE TABLE IF NOT EXISTS shipment_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            tracking_number TEXT NOT NULL,
            status TEXT NOT NULL,
            event_timestamp TEXT NOT NULL,
            location TEXT,
            motive TEXT,
            signature_hash TEXT UNIQUE NOT NULL,
            recorded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(tracking_number) REFERENCES packages(tracking_number) ON DELETE CASCADE
        );

        CREATE INDEX IF NOT EXISTS idx_shipment_events_tracking ON shipment_events(tracking_number);
        CREATE INDEX IF NOT EXISTS idx_shipment_events_sig ON shipment_events(signature_hash);
        """
        with self._get_connection() as conn:
            conn.executescript(schema)
            conn.commit()

    def sync_configured_packages(self, configured_packages: List[PackageConfig]):
        """Synchronizes packages defined in config.yaml without overriding runtime status."""
        with self._get_connection() as conn:
            for pkg in configured_packages:
                conn.execute(
                    """
                    INSERT INTO packages (tracking_number, alias, active)
                    VALUES (?, ?, ?)
                    ON CONFLICT(tracking_number) DO UPDATE SET
                        alias = excluded.alias,
                        active = excluded.active,
                        updated_at = datetime('now', 'localtime');
                    """,
                    (pkg.tracking_number, pkg.alias, 1 if pkg.active else 0),
                )
            conn.commit()

    def add_package(self, tracking_number: str, alias: str, active: bool = True):
        """Adds or updates a single package."""
        with self._get_connection() as conn:
            conn.execute(
                """
                INSERT INTO packages (tracking_number, alias, active)
                VALUES (?, ?, ?)
                ON CONFLICT(tracking_number) DO UPDATE SET
                    alias = excluded.alias,
                    active = excluded.active,
                    updated_at = datetime('now', 'localtime');
                """,
                (tracking_number.strip(), alias.strip(), 1 if active else 0),
            )
            conn.commit()

    def get_active_packages(self) -> List[PackageConfig]:
        """Returns all packages that are active and not yet delivered."""
        with self._get_connection() as conn:
            cursor = conn.execute(
                """
                SELECT tracking_number, alias, active, current_status, 
                       last_event_date, last_checked_at, is_delivered
                FROM packages
                WHERE active = 1 AND is_delivered = 0
                ORDER BY updated_at DESC;
                """
            )
            return [self._row_to_package(row) for row in cursor.fetchall()]

    def get_all_packages(self) -> List[PackageConfig]:
        """Returns all packages in the database."""
        with self._get_connection() as conn:
            cursor = conn.execute(
                """
                SELECT tracking_number, alias, active, current_status, 
                       last_event_date, last_checked_at, is_delivered
                FROM packages
                ORDER BY created_at DESC;
                """
            )
            return [self._row_to_package(row) for row in cursor.fetchall()]

    def get_package(self, tracking_number: str) -> Optional[PackageConfig]:
        """Retrieves a single package by tracking number."""
        with self._get_connection() as conn:
            cursor = conn.execute(
                """
                SELECT tracking_number, alias, active, current_status, 
                       last_event_date, last_checked_at, is_delivered
                FROM packages
                WHERE tracking_number = ?;
                """,
                (tracking_number,),
            )
            row = cursor.fetchone()
            return self._row_to_package(row) if row else None

    def detect_and_save_deltas(
        self, package: PackageConfig, incoming_events: List[TrackingEvent]
    ) -> DeltaResult:
        """Compares incoming events against database history.
        
        Persists new events and returns a DeltaResult containing unnotified events.
        """
        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        previous_status = package.current_status
        new_events: List[TrackingEvent] = []

        with self._get_connection() as conn:
            # Query known event signatures for this package
            cursor = conn.execute(
                "SELECT signature_hash FROM shipment_events WHERE tracking_number = ?",
                (package.tracking_number,),
            )
            known_hashes = {row["signature_hash"] for row in cursor.fetchall()}

            for ev in incoming_events:
                ev_hash = ev.event_hash
                if ev_hash not in known_hashes:
                    # New event detected!
                    conn.execute(
                        """
                        INSERT INTO shipment_events (
                            tracking_number, status, event_timestamp,
                            location, motive, signature_hash
                        ) VALUES (?, ?, ?, ?, ?, ?);
                        """,
                        (
                            package.tracking_number,
                            ev.status,
                            ev.event_date,
                            ev.branch,
                            ev.motive,
                            ev_hash,
                        ),
                    )
                    known_hashes.add(ev_hash)
                    new_events.append(ev)

            # Determine updated latest status
            current_status = previous_status
            last_date = package.last_event_date
            is_delivered = 1 if package.is_delivered else 0

            if incoming_events:
                # Latest event is the last one in chronological order
                latest = incoming_events[-1]
                current_status = latest.status or previous_status
                last_date = latest.event_date or last_date
                
                # Check delivery status
                status_lower = current_status.lower()
                if "entregad" in status_lower or "entrega efectuada" in status_lower:
                    is_delivered = 1

            # Update package record
            conn.execute(
                """
                UPDATE packages
                SET current_status = ?,
                    last_event_date = ?,
                    last_checked_at = ?,
                    is_delivered = ?,
                    updated_at = ?
                WHERE tracking_number = ?;
                """,
                (
                    current_status,
                    last_date,
                    now_str,
                    is_delivered,
                    now_str,
                    package.tracking_number,
                ),
            )
            conn.commit()

        # Update in-memory package object
        package.current_status = current_status
        package.last_event_date = last_date
        package.last_checked_at = now_str
        package.is_delivered = bool(is_delivered)

        return DeltaResult(
            package=package,
            new_events=new_events,
            previous_status=previous_status,
            current_status=current_status,
        )

    def update_last_checked(self, tracking_number: str):
        """Updates the last_checked_at timestamp for a package."""
        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        with self._get_connection() as conn:
            conn.execute(
                "UPDATE packages SET last_checked_at = ? WHERE tracking_number = ?",
                (now_str, tracking_number),
            )
            conn.commit()

    @staticmethod
    def _row_to_package(row: sqlite3.Row) -> PackageConfig:
        return PackageConfig(
            tracking_number=row["tracking_number"],
            alias=row["alias"],
            active=bool(row["active"]),
            current_status=row["current_status"] or "Pendiente",
            last_event_date=row["last_event_date"],
            last_checked_at=row["last_checked_at"],
            is_delivered=bool(row["is_delivered"]),
        )
