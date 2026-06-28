"""JSON-file audit store.

Append-only record of every decision. The audit log NEVER contains a secret
value — `AuditEntry` has no field for one, and the executor only ever returns
masked, safe results.
"""

from __future__ import annotations

import json
import threading
from pathlib import Path

from .config import get_settings
from .models import AuditEntry

_lock = threading.Lock()


def _path() -> Path:
    return get_settings().audit_path


def _read_raw() -> list[dict]:
    path = _path()
    if not path.exists():
        return []
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, list) else []
    except (json.JSONDecodeError, OSError):
        return []


def _write_raw(entries: list[dict]) -> None:
    path = _path()
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(entries, f, indent=2)
    tmp.replace(path)


def append(entry: AuditEntry) -> None:
    with _lock:
        entries = _read_raw()
        entries.append(entry.model_dump())
        _write_raw(entries)


def all_entries() -> list[AuditEntry]:
    with _lock:
        return [AuditEntry(**e) for e in _read_raw()]


def reset() -> None:
    """Clear the audit log (used by the demo reset button)."""
    with _lock:
        _write_raw([])
