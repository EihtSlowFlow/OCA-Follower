"""CLI and daemon scheduler entrypoint for OCA WhatsApp Tracker."""

import argparse
from datetime import datetime
import logging
import os
import random
import signal
import sys
import threading
import time
from typing import Any, Dict, Optional

# Optional dependencies fallback
try:
    import yaml
except ImportError:
    yaml = None

try:
    from dotenv import load_dotenv
except ImportError:
    def load_dotenv(dotenv_path: Optional[str] = None):
        """Simple standard library fallback for loading key=value from .env."""
        path = dotenv_path or ".env"
        if os.path.exists(path):
            try:
                with open(path, "r", encoding="utf-8") as f:
                    for line in f:
                        clean_line = line.strip()
                        if clean_line and not clean_line.startswith("#") and "=" in clean_line:
                            key, val = clean_line.split("=", 1)
                            key = key.strip()
                            val = val.strip().strip("'\"")
                            if key and key not in os.environ:
                                os.environ[key] = val
            except Exception:
                pass


from src.clients.oca_client import OCAClient
from src.models import PackageConfig
from src.notifiers.whatsapp import CallMeBotWhatsAppNotifier
from src.storage.state_store import StateStore

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("oca_tracker")


class GracefulKiller:
    """Catches POSIX signals and exposes a thread-safe stop event."""

    def __init__(self):
        self.stop_event = threading.Event()
        signal.signal(signal.SIGINT, self._handle_signal)
        signal.signal(signal.SIGTERM, self._handle_signal)

    def _handle_signal(self, signum, frame):
        sig_name = signal.Signals(signum).name
        logger.info("Signal %s received. Requesting graceful shutdown...", sig_name)
        self.stop_event.set()

    @property
    def should_stop(self) -> bool:
        return self.stop_event.is_set()

    def wait(self, timeout_seconds: float) -> bool:
        """Returns True if stopped, False if timeout elapsed."""
        return self.stop_event.wait(timeout_seconds)


def load_configuration(config_path: str = "config.yaml", env_path: str = ".env") -> Dict[str, Any]:
    """Loads YAML configuration file and overrides with environment variables."""
    if os.path.exists(env_path):
        load_dotenv(env_path)
    else:
        load_dotenv()

    config: Dict[str, Any] = {}
    if os.path.exists(config_path):
        if yaml is not None:
            with open(config_path, "r", encoding="utf-8") as f:
                config = yaml.safe_load(f) or {}
        else:
            logger.warning("PyYAML not installed. Run 'pip install -r requirements.txt' to load config.yaml.")

    # Read environment variable overrides
    db_config = config.setdefault("database", {})
    if os.getenv("TRACKER_DB_PATH"):
        db_config["path"] = os.getenv("TRACKER_DB_PATH")

    notifier_config = config.setdefault("notifier", {})
    if os.getenv("CALLMEBOT_PHONE"):
        notifier_config["phone"] = os.getenv("CALLMEBOT_PHONE")
    if os.getenv("CALLMEBOT_API_KEY"):
        notifier_config["api_key"] = os.getenv("CALLMEBOT_API_KEY")

    daemon_config = config.setdefault("daemon", {})
    if os.getenv("POLL_INTERVAL_SECONDS"):
        try:
            daemon_config["poll_interval_seconds"] = int(os.getenv("POLL_INTERVAL_SECONDS"))
        except ValueError:
            pass

    log_level = os.getenv("LOG_LEVEL", "INFO").upper()
    logging.getLogger().setLevel(getattr(logging, log_level, logging.INFO))

    return config


def calculate_backoff(
    consecutive_errors: int,
    base_backoff: float = 60.0,
    max_backoff: float = 900.0,
    jitter_factor: float = 0.2,
) -> float:
    """Calculates exponential backoff with randomized jitter."""
    delay = min(max_backoff, base_backoff * (2 ** max(0, consecutive_errors - 1)))
    jitter = delay * random.uniform(-jitter_factor, jitter_factor)
    return max(5.0, delay + jitter)


def run_sync_cycle(
    client: OCAClient,
    store: StateStore,
    notifier: CallMeBotWhatsAppNotifier,
    cooldown_seconds: float = 5.0,
) -> int:
    """Executes a single check and delta synchronization for all active packages.
    
    Returns the count of new events alerted.
    """
    active_packages = store.get_active_packages()
    if not active_packages:
        logger.info("No active packages to track. Add packages in config.yaml or using --add-package.")
        return 0

    logger.info("Checking %d active package(s)...", len(active_packages))
    total_new_events = 0

    for pkg in active_packages:
        logger.info("Checking '%s' (Tracking: %s)...", pkg.alias, pkg.tracking_number)
        resp = client.track_piece(pkg.tracking_number)

        if not resp.success:
            logger.warning(
                "Could not fetch tracking for %s: %s",
                pkg.tracking_number,
                resp.error_message,
            )
            store.update_last_checked(pkg.tracking_number)
            continue

        delta = store.detect_and_save_deltas(pkg, resp.events)
        if delta.has_deltas:
            logger.info(
                "Detected %d new event(s) for '%s' (Latest status: %s)",
                len(delta.new_events),
                pkg.alias,
                delta.current_status,
            )
            total_new_events += len(delta.new_events)

            # Dispatch notification
            if notifier.enabled:
                success = notifier.notify(delta)
                if success:
                    logger.info("Alert dispatched via WhatsApp for '%s'.", pkg.alias)
                else:
                    logger.warning("Failed to dispatch WhatsApp alert for '%s'.", pkg.alias)

                # Rate-limiting cooldown between notifications
                time.sleep(cooldown_seconds)
        else:
            logger.info("No status changes for '%s' (Current: %s).", pkg.alias, pkg.current_status)

    return total_new_events


def print_status_table(store: StateStore):
    """Prints a terminal formatted summary table of all packages."""
    packages = store.get_all_packages()
    if not packages:
        print("\nNo packages registered in the database yet.\n")
        return

    print("\n" + "=" * 90)
    print(f"{'ALIAS':<25} | {'TRACKING NUMBER':<22} | {'ESTADO':<22} | {'ENTREGADO'}")
    print("=" * 90)
    for p in packages:
        delivered_str = "✅ Sí" if p.is_delivered else "⏳ No"
        print(f"{p.alias[:24]:<25} | {p.tracking_number:<22} | {p.current_status[:20]:<22} | {delivered_str}")
    print("=" * 90 + "\n")


def main():
    parser = argparse.ArgumentParser(
        description="OCA WhatsApp Tracker - Monitor package statuses via OCA ASMX and alert via WhatsApp"
    )
    parser.add_argument("--config", default="config.yaml", help="Path to config.yaml file")
    parser.add_argument("--env", default=".env", help="Path to .env file")
    parser.add_argument("--once", action="store_true", help="Run once and exit immediately")
    parser.add_argument("--daemon", action="store_true", help="Run continuous background polling daemon")
    parser.add_argument("--status", action="store_true", help="Print tracked packages status table")
    parser.add_argument(
        "--add-package",
        nargs="+",
        metavar=("TRACKING", "ALIAS"),
        help="Add or update a package in the database: --add-package 3890200000000012345 'Mi Pedido'",
    )
    parser.add_argument("--test-whatsapp", type=str, metavar="MESSAGE", help="Send a test message to WhatsApp")

    args = parser.parse_args()

    config = load_configuration(args.config, args.env)

    # Database
    db_config = config.get("database", {})
    db_path = db_config.get("path", "data/tracker.db")
    store = StateStore(
        db_path=db_path,
        timeout=db_config.get("timeout_seconds", 10.0),
        wal_mode=db_config.get("wal_mode", True),
    )

    # Sync configured packages from YAML
    raw_packages = config.get("packages", [])
    configured_pkgs = [
        PackageConfig(
            tracking_number=str(item.get("tracking_number", "")),
            alias=item.get("alias", "Sin alias"),
            active=bool(item.get("active", True)),
        )
        for item in raw_packages
        if item.get("tracking_number")
    ]
    if configured_pkgs:
        store.sync_configured_packages(configured_pkgs)

    # Handle quick helper options
    if args.status:
        print_status_table(store)
        return

    if args.add_package:
        tracking_num = args.add_package[0]
        alias = " ".join(args.add_package[1:]) if len(args.add_package) > 1 else f"Envío {tracking_num}"
        store.add_package(tracking_num, alias, active=True)
        print(f"Added package '{alias}' ({tracking_num}) to database.")
        return

    # Notifier
    notif_config = config.get("notifier", {})
    notifier = CallMeBotWhatsAppNotifier(
        phone=notif_config.get("phone"),
        api_key=notif_config.get("api_key"),
        enabled=notif_config.get("enabled", True),
    )

    if args.test_whatsapp:
        print(f"Sending test WhatsApp message to {notifier.phone}...")
        ok = notifier.send_raw_message(args.test_whatsapp)
        if ok:
            print("Message sent successfully!")
        else:
            print("Failed to send message. Check your .env CALLMEBOT credentials.")
        return

    # OCA Client
    oca_config = config.get("oca", {})
    client = OCAClient(
        asmx_url=oca_config.get("asmx_url"),
        fallback_url=oca_config.get("fallback_url"),
        timeout=oca_config.get("timeout_seconds", 15),
    )

    cooldown = notif_config.get("cooldown_between_alerts_seconds", 5.0)

    # Single-run mode
    if args.once or not args.daemon:
        logger.info("Running single sync cycle (--once)...")
        run_sync_cycle(client, store, notifier, cooldown_seconds=cooldown)
        logger.info("Single sync cycle finished.")
        return

    # Daemon mode
    daemon_config = config.get("daemon", {})
    poll_interval = daemon_config.get(
        "poll_interval_seconds",
        int(daemon_config.get("polling_interval_minutes", 15)) * 60
    )
    min_backoff = daemon_config.get("min_backoff_seconds", 30)
    max_backoff = daemon_config.get("max_backoff_seconds", 1800)

    logger.info("Starting OCA WhatsApp Tracker daemon (Polling every %d seconds)...", poll_interval)
    killer = GracefulKiller()
    consecutive_errors = 0

    while not killer.should_stop:
        try:
            run_sync_cycle(client, store, notifier, cooldown_seconds=cooldown)
            consecutive_errors = 0
            sleep_duration = poll_interval
            logger.info("Next polling cycle in %d seconds.", sleep_duration)
        except Exception as exc:
            consecutive_errors += 1
            sleep_duration = calculate_backoff(
                consecutive_errors,
                base_backoff=min_backoff,
                max_backoff=max_backoff,
            )
            logger.error(
                "Error during sync cycle (consecutive error #%d): %s. Backing off for %.1f seconds.",
                consecutive_errors,
                exc,
                sleep_duration,
            )

        if killer.wait(sleep_duration):
            logger.info("Daemon gracefully terminated.")
            break


if __name__ == "__main__":
    main()
