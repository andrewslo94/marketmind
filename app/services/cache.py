"""
app/services/cache.py — a small time-to-live (TTL) cache for external API calls.

Every call to an outside provider goes through get_or_fetch(). It answers
from memory first, then from the cache_entries table, and only calls the
provider when the stored copy is older than the TTL. If the provider fails
(network down, rate limit) and a stale copy exists, the stale copy is
returned with stale=True so the page can say "last updated 2 hours ago"
instead of crashing or showing nothing.

Usage:
    result = get_or_fetch("quote:AAPL", ttl_seconds=900, fetch=lambda: ...)
    result.value        # whatever fetch() returned (must be JSON-serializable)
    result.fetched_at   # when it was really fetched from the provider (UTC)
    result.from_cache   # True if we didn't call the provider this time
    result.stale        # True if older than the TTL (provider failed)
    result.error        # provider error message when stale, else None
"""
import json
import logging
import threading
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Optional

from app.extensions import db
from app.models import CacheEntry

log = logging.getLogger(__name__)

# In-memory layer: key -> (value, fetched_at). A lock makes it safe when the
# dev server handles two requests at once (it is multi-threaded by default).
_memory: dict[str, tuple[Any, datetime]] = {}
_lock = threading.Lock()


@dataclass
class CacheResult:
    """What get_or_fetch() hands back. A dataclass is a plain container
    class whose __init__ and __repr__ Python writes for us."""

    value: Any
    fetched_at: datetime
    from_cache: bool = False
    stale: bool = False
    error: Optional[str] = None

    @property
    def age(self) -> timedelta:
        return datetime.now(timezone.utc) - self.fetched_at


def _utc(dt: datetime) -> datetime:
    """SQLite drops timezone info; treat naive datetimes as UTC."""
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def _is_fresh(fetched_at: datetime, ttl_seconds: int) -> bool:
    return datetime.now(timezone.utc) - _utc(fetched_at) < timedelta(seconds=ttl_seconds)


def _read_db(key: str) -> Optional[tuple[Any, datetime]]:
    row = db.session.get(CacheEntry, key)
    if row is None:
        return None
    try:
        return json.loads(row.value), _utc(row.fetched_at)
    except json.JSONDecodeError:
        log.warning("Corrupt cache entry for %s; ignoring it.", key)
        return None


def _write_db(key: str, value: Any, fetched_at: datetime) -> None:
    row = db.session.get(CacheEntry, key)
    if row is None:
        row = CacheEntry(key=key)
        db.session.add(row)
    row.value = json.dumps(value)
    row.fetched_at = fetched_at
    db.session.commit()


def get_or_fetch(key: str, ttl_seconds: int, fetch: Callable[[], Any]) -> CacheResult:
    """
    Return the cached value for `key` if it is younger than ttl_seconds;
    otherwise call fetch(), store its result, and return that.

    fetch() must return JSON-serializable data (dicts, lists, str, numbers,
    None). If fetch() raises, the newest stale copy is returned (stale=True);
    if there is no copy at all, the exception is re-raised for the caller.
    """
    # 1. Memory
    with _lock:
        hit = _memory.get(key)
    if hit and _is_fresh(hit[1], ttl_seconds):
        return CacheResult(hit[0], hit[1], from_cache=True)

    # 2. Database
    stored = _read_db(key)
    if stored and _is_fresh(stored[1], ttl_seconds):
        with _lock:
            _memory[key] = stored
        return CacheResult(stored[0], stored[1], from_cache=True)

    # 3. Provider
    try:
        value = fetch()
    except Exception as exc:  # noqa: BLE001 — any provider failure
        fallback = hit or stored
        if fallback is not None:
            log.warning("Fetch failed for %s (%s); serving stale copy.", key, exc)
            return CacheResult(
                fallback[0], fallback[1], from_cache=True, stale=True, error=str(exc)
            )
        raise

    now = datetime.now(timezone.utc)
    _write_db(key, value, now)
    with _lock:
        _memory[key] = (value, now)
    return CacheResult(value, now)


def clear_memory() -> None:
    """Forget the in-memory layer (used by tests)."""
    with _lock:
        _memory.clear()
