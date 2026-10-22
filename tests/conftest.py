"""Keep the test suite away from the user's real database (~/.finance-assistant/finance.db).

The variable is set at import time because some test modules initialise the database while
they are being collected, before any fixture runs.
"""

import os
import tempfile

import pytest

_TEST_DB_DIR = tempfile.mkdtemp(prefix="finance-test-db-")
os.environ["FINANCE_DB_PATH"] = os.path.join(_TEST_DB_DIR, "finance-test.db")


@pytest.fixture(autouse=True)
def isolated_sqlite_file(tmp_path, monkeypatch):
    monkeypatch.setenv("FINANCE_DB_PATH", str(tmp_path / "finance-test.db"))
