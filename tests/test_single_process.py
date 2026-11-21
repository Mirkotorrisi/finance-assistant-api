"""The services refuse to run as one of several workers (their state lives in the process)."""

import pytest

from src.clock import to_naive_utc, utc_now
from src.single_process import assert_single_process, configured_workers


def test_workers_are_read_from_uvicorn_flags_and_web_concurrency():
    assert configured_workers(["/x/bin/uvicorn", "app:app"], {}) == 1
    assert configured_workers(["/x/bin/uvicorn", "app:app", "--workers", "4"], {}) == 4
    assert configured_workers(["/x/bin/uvicorn", "--workers=3", "app:app"], {}) == 3
    assert configured_workers(["gunicorn", "-w", "2", "app:app"], {}) == 2
    assert configured_workers(["/x/bin/uvicorn", "app:app"], {"WEB_CONCURRENCY": "2"}) == 2
    assert configured_workers(["/x/bin/uvicorn", "app:app", "--workers", "x"], {"WEB_CONCURRENCY": ""}) == 1
    # other launchers (pytest, scripts) have flags of their own that are not worker counts
    assert configured_workers(["/x/bin/pytest", "-w", "4"], {}) == 1


def test_several_workers_refuse_to_start_unless_allowed():
    assert_single_process("api", ["/x/bin/uvicorn", "app:app"], {})
    with pytest.raises(RuntimeError, match="2 workers"):
        assert_single_process("api", ["/x/bin/uvicorn", "app:app", "--workers", "2"], {})
    assert_single_process("api", ["/x/bin/uvicorn", "app:app", "--workers", "2"], {"FINANCE_ALLOW_WORKERS": "1"})


def test_clock_gives_naive_utc():
    from datetime import datetime, timedelta, timezone

    now = utc_now()
    assert now.tzinfo is None and abs(now - datetime.now(timezone.utc).replace(tzinfo=None)) < timedelta(seconds=5)
    aware = datetime(2026, 11, 21, 12, 0, tzinfo=timezone(timedelta(hours=2)))
    assert to_naive_utc(aware) == datetime(2026, 11, 21, 10, 0)
    assert to_naive_utc(datetime(2026, 11, 21, 10, 0)) == datetime(2026, 11, 21, 10, 0) and to_naive_utc(None) is None
