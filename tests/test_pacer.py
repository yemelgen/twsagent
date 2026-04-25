"""
Tests for IBPacer rate limiter
"""

import sys
import threading
import time
from pathlib import Path

# Add app directory to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root / "app"))

from pacer import IBPacer


def test_acquire_basic():
    """Basic acquire should succeed immediately"""

    pacer = IBPacer(historical_max_requests=10, general_min_interval_seconds=0.0)
    assert pacer.acquire("general") is True
    assert pacer.acquire("historical") is True


def test_general_min_interval():
    """Sequential general requests should respect minimum interval"""

    interval = 0.2
    pacer = IBPacer(general_min_interval_seconds=interval)

    start = time.monotonic()
    pacer.acquire("general")
    pacer.acquire("general")
    elapsed = time.monotonic() - start

    assert elapsed >= interval


def test_historical_window_enforcement():
    """Requests should block when historical window is full"""

    pacer = IBPacer(
        historical_max_requests=3,
        historical_window_seconds=5,
        general_min_interval_seconds=0.0,
    )

    # Fill the window
    for _ in range(3):
        assert pacer.acquire("historical") is True

    # Next one should timeout since window is full
    assert pacer.acquire("historical", timeout=0.5) is False


def test_identical_request_gap():
    """Same signature should enforce the identical request gap"""

    gap = 0.3
    pacer = IBPacer(
        identical_gap_seconds=gap,
        general_min_interval_seconds=0.0,
        historical_max_requests=100,
    )

    sig = "hist_data:123:1D:5mins:TRADES:False"

    start = time.monotonic()
    pacer.acquire("historical", signature=sig)
    pacer.acquire("historical", signature=sig)
    elapsed = time.monotonic() - start

    assert elapsed >= gap


def test_different_signatures_no_gap():
    """Different signatures should not enforce the identical gap"""

    pacer = IBPacer(
        identical_gap_seconds=10,
        general_min_interval_seconds=0.0,
        historical_max_requests=100,
    )

    start = time.monotonic()
    pacer.acquire("historical", signature="sig_a")
    pacer.acquire("historical", signature="sig_b")
    elapsed = time.monotonic() - start

    # Should complete quickly (no gap between different signatures)
    assert elapsed < 1.0


def test_timeout_returns_false():
    """acquire should return False when timeout expires"""

    pacer = IBPacer(
        historical_max_requests=1,
        historical_window_seconds=60,
        general_min_interval_seconds=0.0,
    )

    pacer.acquire("historical")

    start = time.monotonic()
    result = pacer.acquire("historical", timeout=0.3)
    elapsed = time.monotonic() - start

    assert result is False
    assert elapsed >= 0.3
    assert elapsed < 1.0


def test_concurrent_access():
    """Multiple threads should not exceed window capacity"""

    max_req = 5
    pacer = IBPacer(
        historical_max_requests=max_req,
        historical_window_seconds=60,
        general_min_interval_seconds=0.0,
    )

    results = []
    lock = threading.Lock()

    def worker():
        result = pacer.acquire("historical", timeout=1.0)
        with lock:
            results.append(result)

    threads = [threading.Thread(target=worker) for _ in range(10)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=5)

    acquired = sum(1 for r in results if r is True)
    denied = sum(1 for r in results if r is False)

    # Exactly max_req should succeed, rest should timeout
    assert acquired == max_req
    assert denied == 5


def test_general_does_not_count_against_historical():
    """General requests should not consume historical window capacity"""

    pacer = IBPacer(
        historical_max_requests=2,
        historical_window_seconds=60,
        general_min_interval_seconds=0.0,
    )

    # Make several general requests
    for _ in range(5):
        assert pacer.acquire("general") is True

    # Historical window should still have full capacity
    assert pacer.acquire("historical") is True
    assert pacer.acquire("historical") is True


def test_window_slides():
    """Requests should succeed after old entries expire from the window"""

    pacer = IBPacer(
        historical_max_requests=2,
        historical_window_seconds=0.5,
        general_min_interval_seconds=0.0,
    )

    # Fill window
    pacer.acquire("historical")
    pacer.acquire("historical")

    # Wait for window to slide
    time.sleep(0.6)

    # Should succeed now
    assert pacer.acquire("historical") is True


def test_backoff_delays_next_request():
    """After backoff(), next acquire should wait the cooldown period"""

    pacer = IBPacer(
        historical_max_requests=100,
        general_min_interval_seconds=0.0,
    )
    pacer._backoff_seconds = 0.3

    pacer.acquire("general")
    pacer.backoff()

    start = time.monotonic()
    pacer.acquire("general")
    elapsed = time.monotonic() - start

    assert elapsed >= 0.3


def test_contract_burst_limit():
    """Same contract key should be limited within the burst window"""

    pacer = IBPacer(
        historical_max_requests=100,
        general_min_interval_seconds=0.0,
        contract_max_requests=3,
        contract_window_seconds=5,
    )

    key = "12345:SMART:TRADES"

    # Fill the per-contract window
    for _ in range(3):
        assert pacer.acquire("historical", contract_key=key) is True

    # Next one for the same contract should timeout
    assert pacer.acquire("historical", contract_key=key, timeout=0.5) is False


def test_contract_burst_different_contracts():
    """Different contract keys should not interfere with each other"""

    pacer = IBPacer(
        historical_max_requests=100,
        general_min_interval_seconds=0.0,
        contract_max_requests=2,
        contract_window_seconds=5,
    )

    # Fill one contract's window
    for _ in range(2):
        pacer.acquire("historical", contract_key="111:SMART:TRADES")

    # Different contract should still work
    assert pacer.acquire("historical", contract_key="222:SMART:TRADES") is True


def test_contract_burst_window_slides():
    """Per-contract limit should clear after the window expires"""

    pacer = IBPacer(
        historical_max_requests=100,
        general_min_interval_seconds=0.0,
        contract_max_requests=2,
        contract_window_seconds=0.3,
    )

    key = "12345:SMART:TRADES"
    pacer.acquire("historical", contract_key=key)
    pacer.acquire("historical", contract_key=key)

    # Wait for window to expire
    time.sleep(0.4)

    assert pacer.acquire("historical", contract_key=key) is True


def test_backoff_expires():
    """After cooldown period, requests should proceed without delay"""

    pacer = IBPacer(
        historical_max_requests=100,
        general_min_interval_seconds=0.0,
    )
    pacer._backoff_seconds = 0.2

    pacer.backoff()
    time.sleep(0.25)

    start = time.monotonic()
    pacer.acquire("general")
    elapsed = time.monotonic() - start

    assert elapsed < 0.1
