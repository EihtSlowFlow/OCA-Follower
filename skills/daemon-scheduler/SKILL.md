---
name: daemon-scheduler
description: Controls the polling lifecycle, coordinates tracking checks across multiple shipments, applies exponential backoff, and listens for termination signals.
---

# Daemon Scheduler Skill

## 1. Purpose
Orchestrates continuous background execution, preventing resource exhaustion, managing adaptive polling cycles, and ensuring clean, immediate process shutdown upon receiving termination signals.

---

## 2. Configuration Requirements (`config.yaml`)

| Parameter | Type | Default | Description |
| :--- | :--- | :--- | :--- |
| `polling_interval_minutes` | Integer | `15` | Interval in minutes between complete tracking sweeps (recommended: 15–30 min). |
| `poll_interval_seconds` | Integer | `900` | Alternative definition in seconds (takes precedence if provided). |
| `max_retries` | Integer | `3` | Maximum consecutive network retries before applying progressive backoff. |
| `min_backoff_seconds` | Integer | `30` | Initial delay upon consecutive upstream failures. |
| `max_backoff_seconds` | Integer | `1800` | Upper bound for exponential backoff delay (30 minutes). |

---

## 3. Operational Workflow

1. **Signal Interception**: Bind POSIX OS signals (`SIGINT`, `SIGTERM`) to a thread-safe stop flag (`threading.Event`).
2. **Environment & Target Loading**: Read configuration from [`config.yaml`](file:///home/ramiro/Documentos/Seguidor_de_OCA/oca-whatsapp-tracker/config.yaml) and secrets from [`.env`](file:///home/ramiro/Documentos/Seguidor_de_OCA/oca-whatsapp-tracker/.env).
3. **Synchronization Loop**:
   - Query all active, non-delivered shipments through [`oca-soap-query`](../oca-soap-query/SKILL.md).
   - Pass event streams to [`sqlite-state-tracker`](../sqlite-state-tracker/SKILL.md) for delta detection.
   - For every verified change (`has_changed == True`), dispatch an alert via [`whatsapp-callmebot-alert`](../whatsapp-callmebot-alert/SKILL.md).
   - Introduce a rate-limiting cooldown (~5s) between notifications to respect CallMeBot API limits.
   - On a successful pass: reset consecutive failure counters.
   - On connection/service failures: compute exponential backoff with randomized jitter and sleep before retrying.
4. **Interruptible Sleep**: Sleep for the configured interval using non-blocking event waits rather than blocking sleeps.

---

## 4. Implementation References

The runtime logic is implemented in the following modules:

- **Signal Interception & State**: [`GracefulKiller`](file:///home/ramiro/Documentos/Seguidor_de_OCA/oca-whatsapp-tracker/src/main.py#L32-L50) in [`src/main.py`](file:///home/ramiro/Documentos/Seguidor_de_OCA/oca-whatsapp-tracker/src/main.py).
- **Backoff & Jitter Algorithm**: [`calculate_backoff`](file:///home/ramiro/Documentos/Seguidor_de_OCA/oca-whatsapp-tracker/src/main.py#L104-L115) in [`src/main.py`](file:///home/ramiro/Documentos/Seguidor_de_OCA/oca-whatsapp-tracker/src/main.py).
- **Batch Processing Cycle**: [`run_sync_cycle`](file:///home/ramiro/Documentos/Seguidor_de_OCA/oca-whatsapp-tracker/src/main.py#L118-L184) in [`src/main.py`](file:///home/ramiro/Documentos/Seguidor_de_OCA/oca-whatsapp-tracker/src/main.py).
- **CLI & Daemon Runner**: [`main`](file:///home/ramiro/Documentos/Seguidor_de_OCA/oca-whatsapp-tracker/src/main.py#L201-L328) in [`src/main.py`](file:///home/ramiro/Documentos/Seguidor_de_OCA/oca-whatsapp-tracker/src/main.py).

---

## 5. Edge Cases & Resilience

- **Sleep Interruption**: Never execute blocking calls like `time.sleep(900)`. Always utilize `stop_event.wait(timeout)` so that `Ctrl+C` or `systemctl stop` terminates the process instantly without lingering.
- **Unhandled Exceptions**: Catch and log cycle-level network and API errors to ensure that temporary server downtime never crashes the continuous daemon.
- **Atomic State Persistence**: Database updates must commit immediately per package so interrupted cycles don't lose confirmed progress.

---

## 6. Linux Systemd Service Setup

To run as a system daemon on Linux:

```ini
[Unit]
Description=OCA WhatsApp Tracking Daemon
After=network.target

[Service]
Type=simple
User=ramiro
WorkingDirectory=/home/ramiro/Documentos/Seguidor_de_OCA/oca-whatsapp-tracker
ExecStart=/usr/bin/python3 -m src.main --daemon
Restart=always
RestartSec=15

[Install]
WantedBy=multi-user.target
```
