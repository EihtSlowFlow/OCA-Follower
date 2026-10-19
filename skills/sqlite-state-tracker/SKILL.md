---
name: sqlite-state-tracker
description: Manages shipment state persistence in SQLite, computes SHA-256 signatures, and filters duplicate polling cycles to prevent spam.
---

# SQLite State Tracker & Delta Detection Skill

## 1. Purpose
Maintains a local persistent audit trail of all package events in SQLite, ensuring that notifications are triggered only when a verified status transition occurs and preventing duplicate alerts.

---

## 2. Schema Specification

The database utilizes SQLite with Write-Ahead Logging (WAL) and busy timeout protection (`PRAGMA busy_timeout = 5000;`).

```sql
-- Tracked packages configuration and current snapshot
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

-- Historical event registry and deduplication signatures
CREATE TABLE IF NOT EXISTS shipment_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    tracking_number TEXT NOT NULL,
    status TEXT NOT NULL,
    event_timestamp TEXT NOT NULL,
    location TEXT,
    signature_hash TEXT UNIQUE NOT NULL,
    recorded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY(tracking_number) REFERENCES packages(tracking_number) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_shipment_events_tracking ON shipment_events(tracking_number);
CREATE INDEX IF NOT EXISTS idx_shipment_events_sig ON shipment_events(signature_hash);
```

---

## 3. Deduplication Signature Specification

To guarantee idempotency regardless of whitespace, casing, or server reordering, each event is fingerprinted using a SHA-256 hash computed over canonical fields:

$$\text{signature\_hash} = \text{SHA256}(\text{tracking\_number} + \text{":"} + \text{status} + \text{":"} + \text{timestamp})$$

---

## 4. Operational Workflow

1. **Connection Setup**: Open connection with WAL mode (`PRAGMA journal_mode = WAL;`) and 5-second busy timeout (`PRAGMA busy_timeout = 5000;`).
2. **Signature Calculation**: Compute the event signature hash for each incoming record.
3. **Delta Check**:
   - Query whether `signature_hash` already exists in the database.
   - If present: mark as previously processed (`has_changed = False`) and skip.
   - If absent: insert the new event into the database and collect it as a delta (`has_changed = True`).
4. **Package Snapshot Update**:
   - Update `packages.current_status`, `last_event_date`, and `last_checked_at`.
   - If the event indicates delivery (`"entregado"`), set `is_delivered = 1` to exclude it from future polling sweeps.

---

## 5. Implementation References

The state management and delta detection logic are implemented in:

- **State Store Manager**: [`StateStore`](file:///home/ramiro/Documentos/Seguidor_de_OCA/oca-whatsapp-tracker/src/storage/state_store.py#L14-L262) in [`src/storage/state_store.py`](file:///home/ramiro/Documentos/Seguidor_de_OCA/oca-whatsapp-tracker/src/storage/state_store.py).
- **Delta Detection Logic**: [`detect_and_save_deltas`](file:///home/ramiro/Documentos/Seguidor_de_OCA/oca-whatsapp-tracker/src/storage/state_store.py#L148-L240) in [`src/storage/state_store.py`](file:///home/ramiro/Documentos/Seguidor_de_OCA/oca-whatsapp-tracker/src/storage/state_store.py).
- **Domain Models**: [`PackageConfig`](file:///home/ramiro/Documentos/Seguidor_de_OCA/oca-whatsapp-tracker/src/models.py#L79-L86) and [`DeltaResult`](file:///home/ramiro/Documentos/Seguidor_de_OCA/oca-whatsapp-tracker/src/models.py#L88-L100) in [`src/models.py`](file:///home/ramiro/Documentos/Seguidor_de_OCA/oca-whatsapp-tracker/src/models.py).

---

## 6. Edge Cases & Resilience

- **Database Locks**: Setting a busy timeout of 5000ms prevents `database is locked` errors during concurrent status checks or CLI additions.
- **Out-of-Order Delivery**: Deduplication matches against the entire historical table rather than only the latest record, preventing duplicate alerts even if events arrive out of chronological order.
- **Transactional Safety**: Execute inserts and snapshot updates within a single transaction to maintain consistency.
