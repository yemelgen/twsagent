"""
IB API rate limiter using sliding window with threading.Condition.

Enforces pacing rules at the service level to prevent IB API pacing violations:
- Historical data: max N requests per M-second window,
  plus identical-request gap
- General requests: minimum interval between calls
"""

from __future__ import annotations

import collections
import logging
import threading
import time

logger = logging.getLogger(__name__)


class IBPacer:
    """Thread-safe rate limiter for IB API requests."""

    def __init__(
        self,
        historical_max_requests: int = 50,
        historical_window_seconds: int = 600,
        identical_gap_seconds: int = 15,
        general_min_interval_seconds: float = 1.0,
    ) -> None:
        self._condition = threading.Condition()
        self._history = {
            "historical": collections.deque(),
            "general": collections.deque(),
        }

        self._historical_max = historical_max_requests
        self._historical_window = historical_window_seconds
        self._identical_gap = identical_gap_seconds
        self._general_min_interval = general_min_interval_seconds

        # Track identical request signatures for the gap rule
        self._last_request_by_signature = {}

        # Timestamp of most recent IB API call (any category)
        self._last_call_time = 0.0

        # Backoff: force a cooldown after timeout
        self._backoff_until = 0.0
        self._backoff_seconds = 5.0

    def acquire(
        self,
        category: str,
        signature: str | None = None,
        timeout: float = 120.0,
    ) -> bool:
        """Block until it is safe to send a request in the given category.

        Args:
            category: 'historical' or 'general'
            signature: Optional key for identical-request dedup
                (historical only)
            timeout: Max seconds to wait. Returns False if exceeded.

        Returns:
            True if acquired, False if timed out.
        """

        deadline = time.monotonic() + timeout

        with self._condition:
            while True:
                now = time.monotonic()
                if now >= deadline:
                    logger.warning(f"Pacer timeout for category={category}")
                    return False

                self._cleanup(now)
                wait_time = self._compute_wait(category, signature, now)

                if wait_time <= 0:
                    self._record(category, signature, now)
                    return True

                remaining = deadline - now
                self._condition.wait(timeout=min(wait_time + 0.01, remaining))

    def backoff(self) -> None:
        """Signal that the last request timed out -- force a cooldown."""

        with self._condition:
            self._backoff_until = time.monotonic() + self._backoff_seconds
            logger.info(f"Pacer: backing off for {self._backoff_seconds}s after timeout")
            self._condition.notify_all()

    def _compute_wait(self, category: str, signature: str | None, now: float) -> float:
        """Compute how long to wait before this request can proceed."""

        wait = 0.0

        # Backoff cooldown after timeout
        if now < self._backoff_until:
            wait = max(wait, self._backoff_until - now)

        # Global minimum interval between any IB calls
        if self._last_call_time > 0:
            elapsed = now - self._last_call_time
            if elapsed < self._general_min_interval:
                wait = max(wait, self._general_min_interval - elapsed)

        if category == "historical":
            # Sliding window capacity check
            window = self._history["historical"]
            if len(window) >= self._historical_max:
                oldest = window[0]
                window_wait = self._historical_window - (now - oldest)
                if window_wait > 0:
                    wait = max(wait, window_wait)

            # Identical request gap
            if signature and signature in self._last_request_by_signature:
                last_time = self._last_request_by_signature[signature]
                gap_elapsed = now - last_time
                if gap_elapsed < self._identical_gap:
                    wait = max(wait, self._identical_gap - gap_elapsed)

        return wait

    def _record(self, category: str, signature: str | None, now: float) -> None:
        """Record a request and notify waiting threads."""

        if category in self._history:
            self._history[category].append(now)
        self._last_call_time = now

        if signature:
            self._last_request_by_signature[signature] = now

        logger.debug(f"Pacer: acquired category={category} signature={signature}")
        self._condition.notify_all()

    def _cleanup(self, now: float) -> None:
        """Remove stale entries from sliding windows and signature tracking."""

        # Clean historical window
        window = self._history["historical"]
        cutoff = now - self._historical_window
        while window and window[0] < cutoff:
            window.popleft()

        # Clean stale signatures
        stale = [
            k
            for k, v in self._last_request_by_signature.items()
            if now - v > self._identical_gap
        ]
        for k in stale:
            del self._last_request_by_signature[k]
