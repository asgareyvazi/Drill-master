# core/cache_manager.py
"""
Cache Manager - centralized caching for DrillMaster
====================================================

Usage:
    from core.cache_manager import cache, cached

    # Simple get/set
    cache.set("my_key", value, ttl=60)
    value = cache.get("my_key")

    # get_or_set
    data = cache.get_or_set("key", lambda: expensive_call(), ttl=30)

    # Decorator
    @cached(ttl=60, key_prefix="well")
    def get_well_info(well_id: int):
        return db.get_well_by_id(well_id)

    # Invalidate well cache
    cache.clear_well(well_id)
"""

import time
import logging
from typing import Any, Optional, Dict, Callable
from functools import wraps
from threading import Lock

logger = logging.getLogger(__name__)

# =====================================================
# Constants
# =====================================================
DEFAULT_TTL = 30.0          # seconds
MAX_TTL = 86400.0           # 24 hours
MAX_CACHE_SIZE = 1000       # max entries before auto-cleanup
CLEANUP_THRESHOLD = 0.8     # cleanup when 80% full


# =====================================================
# CacheEntry
# =====================================================
class CacheEntry:
    """Single cache entry with TTL and stats."""

    __slots__ = ('value', 'created_at', 'ttl', 'hit_count', 'is_none')

    def __init__(self, value: Any, ttl: float = DEFAULT_TTL):
        self.value = value
        self.created_at = time.monotonic()  # ✅ monotonic is safer than time()
        self.ttl = ttl
        self.hit_count = 0
        self.is_none = (value is None)      # ✅ track None separately

    @property
    def is_expired(self) -> bool:
        return (time.monotonic() - self.created_at) > self.ttl

    @property
    def age(self) -> float:
        return time.monotonic() - self.created_at

    @property
    def remaining_ttl(self) -> float:
        return max(0.0, self.ttl - self.age)


# =====================================================
# AppCache
# =====================================================
class AppCache:
    """
    Central application cache - Singleton.

    Features:
    - TTL-based expiry
    - None-value caching (avoids repeated failed lookups)
    - Auto-cleanup when full
    - Prefix-based invalidation
    - Thread-safe
    """

    _instance = None
    _class_lock = Lock()    # ✅ separate lock for singleton creation

    def __new__(cls):
        if cls._instance is None:
            with cls._class_lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        if hasattr(self, '_initialized'):
            return
        self._cache: Dict[str, CacheEntry] = {}
        self._lock = Lock()             # ✅ instance lock only here
        self._initialized = True
        self._miss_count = 0
        self._hit_count = 0
        logger.debug("AppCache initialized")

    # ================================================================
    # Core Methods
    # ================================================================

    def get(self, key: str) -> Optional[Any]:
        """
        Get value from cache.
        Returns None if key not found or expired.
        Note: also returns None if value was explicitly cached as None.
        Use `has(key)` to distinguish.
        """
        with self._lock:
            entry = self._cache.get(key)
            if entry is None:
                self._miss_count += 1
                return None
            if entry.is_expired:
                del self._cache[key]
                self._miss_count += 1
                return None
            entry.hit_count += 1
            self._hit_count += 1
            return entry.value

    def has(self, key: str) -> bool:
        """Check if key exists and is not expired."""
        with self._lock:
            entry = self._cache.get(key)
            if entry is None:
                return False
            if entry.is_expired:
                del self._cache[key]
                return False
            return True

    def set(
        self,
        key: str,
        value: Any,
        ttl: float = DEFAULT_TTL,
    ) -> None:
        """
        Store value in cache.
        Accepts None as a valid value (prevents repeated failed lookups).
        """
        if not isinstance(key, str) or not key:
            logger.warning("Cache key must be a non-empty string")
            return

        ttl = max(0.1, min(float(ttl), MAX_TTL))

        with self._lock:
            # Auto-cleanup if too full
            if len(self._cache) >= MAX_CACHE_SIZE * CLEANUP_THRESHOLD:
                self._cleanup_expired_unsafe()

            self._cache[key] = CacheEntry(value, ttl)

    def delete(self, key: str) -> bool:
        """Delete a key. Returns True if key existed."""
        with self._lock:
            if key in self._cache:
                del self._cache[key]
                return True
            return False

    def get_or_set(
        self,
        key: str,
        factory: Callable,
        ttl: float = DEFAULT_TTL,
        cache_none: bool = False,
    ) -> Any:
        """
        Get from cache or compute and store.

        Args:
            key: Cache key
            factory: Callable that returns the value
            ttl: Time to live in seconds
            cache_none: If True, cache None results too (avoids repeated calls)

        Returns:
            Cached or freshly computed value
        """
        # Check cache first (including None entries)
        with self._lock:
            entry = self._cache.get(key)
            if entry is not None and not entry.is_expired:
                entry.hit_count += 1
                self._hit_count += 1
                return entry.value
            if entry is not None and entry.is_expired:
                del self._cache[key]
            self._miss_count += 1

        # ✅ Compute outside lock to avoid deadlock
        try:
            value = factory()
        except Exception as e:
            logger.error(
                f"Cache factory error for '{key}': {e}",
                exc_info=True,
            )
            return None

        # Cache the result
        if value is not None or cache_none:
            self.set(key, value, ttl)

        return value

    # ================================================================
    # Invalidation
    # ================================================================

    def clear(self, prefix: str = None) -> int:
        """
        Clear cache entries.

        Args:
            prefix: If given, only clear keys starting with prefix.

        Returns:
            Number of entries removed.
        """
        with self._lock:
            if prefix:
                keys = [k for k in self._cache if k.startswith(prefix)]
                for k in keys:
                    del self._cache[k]
                count = len(keys)
            else:
                count = len(self._cache)
                self._cache.clear()

        if count:
            logger.debug(
                f"Cache cleared: {count} entries"
                f"{f' with prefix {prefix!r}' if prefix else ''}"
            )
        return count

    def clear_well(self, well_id: int) -> int:
        """Clear all cache entries for a specific well."""
        return self.clear(prefix=f"well_{well_id}_")

    def clear_report(self, report_id: int) -> int:
        """Clear all cache entries for a specific report."""
        return self.clear(prefix=f"report_{report_id}_")

    def clear_section(self, section_id: int) -> int:
        """Clear all cache entries for a specific section."""
        return self.clear(prefix=f"section_{section_id}_")

    def invalidate_pattern(self, pattern: str) -> int:
        """
        Clear entries whose key contains the pattern.

        Example:
            cache.invalidate_pattern("hierarchy")
        """
        with self._lock:
            keys = [k for k in self._cache if pattern in k]
            for k in keys:
                del self._cache[k]
        if keys:
            logger.debug(
                f"Cache invalidated: {len(keys)} entries "
                f"matching '{pattern}'"
            )
        return len(keys)

    # ================================================================
    # Cleanup
    # ================================================================

    def cleanup_expired(self) -> int:
        """Remove all expired entries. Returns count removed."""
        with self._lock:
            return self._cleanup_expired_unsafe()

    def _cleanup_expired_unsafe(self) -> int:
        """Remove expired entries WITHOUT acquiring lock (call inside lock)."""
        expired = [
            k for k, v in self._cache.items() if v.is_expired
        ]
        for k in expired:
            del self._cache[k]
        if expired:
            logger.debug(f"Cache cleanup: removed {len(expired)} expired entries")
        return len(expired)

    # ================================================================
    # Stats
    # ================================================================

    def stats(self) -> Dict:
        """Get cache statistics."""
        with self._lock:
            total = len(self._cache)
            expired = sum(
                1 for e in self._cache.values() if e.is_expired
            )
            total_hits = sum(
                e.hit_count for e in self._cache.values()
            )
            top_keys = sorted(
                self._cache.items(),
                key=lambda x: x[1].hit_count,
                reverse=True,
            )[:5]

        hit_rate = 0.0
        total_requests = self._hit_count + self._miss_count
        if total_requests > 0:
            hit_rate = self._hit_count / total_requests

        return {
            "total_entries": total,
            "active_entries": total - expired,
            "expired_entries": expired,
            "total_hits": self._hit_count,
            "total_misses": self._miss_count,
            "hit_rate": f"{hit_rate:.1%}",
            "top_keys": [
                (k, v.hit_count) for k, v in top_keys
            ],
        }

    def __len__(self) -> int:
        with self._lock:
            return len(self._cache)

    def __repr__(self) -> str:
        return (
            f"AppCache("
            f"entries={len(self._cache)}, "
            f"hits={self._hit_count}, "
            f"misses={self._miss_count})"
        )


# =====================================================
# Global Instance
# =====================================================
cache = AppCache()


# =====================================================
# Cached Decorator
# =====================================================
def cached(
    ttl: float = DEFAULT_TTL,
    key_prefix: str = "",
    cache_none: bool = False,
):
    """
    Decorator to cache function results.

    Args:
        ttl: Cache duration in seconds
        key_prefix: Prefix for cache key (default: function name)
        cache_none: Cache None results to prevent repeated calls

    Example:
        @cached(ttl=60, key_prefix="well")
        def get_well_info(well_id: int):
            return db.get_well_by_id(well_id)

        # With instance methods - skip 'self':
        @cached(ttl=30, key_prefix="report")
        def load_report(self, report_id: int):
            ...
    """
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            prefix = key_prefix or func.__name__

            # ✅ Skip 'self' / 'cls' for instance/class methods
            cache_args = args
            if args and hasattr(args[0], '__class__'):
                # Check if first arg looks like self/cls
                first = args[0]
                if hasattr(first, '__dict__') or hasattr(first, '__slots__'):
                    cache_args = args[1:]

            key_parts = [prefix]
            key_parts.extend(str(a) for a in cache_args)
            key_parts.extend(
                f"{k}={v}" for k, v in sorted(kwargs.items())
            )
            cache_key = "_".join(filter(None, key_parts))

            return cache.get_or_set(
                cache_key,
                lambda: func(*args, **kwargs),
                ttl=ttl,
                cache_none=cache_none,
            )

        # Expose cache control on the function
        wrapper.invalidate = lambda *args, **kwargs: cache.delete(
            "_".join(
                filter(None, [key_prefix or func.__name__]
                       + [str(a) for a in args])
            )
        )
        wrapper.clear_all = lambda: cache.clear(
            prefix=key_prefix or func.__name__
        )

        return wrapper
    return decorator


# =====================================================
# Common Cache Keys
# =====================================================
class CacheKeys:
    """
    Standard cache key builders.
    Use these to avoid typos and keep keys consistent.
    """

    @staticmethod
    def well(well_id: int, suffix: str = "") -> str:
        return f"well_{well_id}_{suffix}" if suffix else f"well_{well_id}"

    @staticmethod
    def section(section_id: int, suffix: str = "") -> str:
        return (
            f"section_{section_id}_{suffix}"
            if suffix else f"section_{section_id}"
        )

    @staticmethod
    def report(report_id: int, suffix: str = "") -> str:
        return (
            f"report_{report_id}_{suffix}"
            if suffix else f"report_{report_id}"
        )

    @staticmethod
    def hierarchy() -> str:
        return "main_window_hierarchy"

    @staticmethod
    def well_sections(well_id: int) -> str:
        return f"well_{well_id}_sections"

    @staticmethod
    def well_reports(well_id: int, section_id: int) -> str:
        return f"well_{well_id}_section_{section_id}_reports"