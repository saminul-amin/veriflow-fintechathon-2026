import os
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


@pytest.fixture(autouse=True)
def isolated_db(tmp_path, monkeypatch):
    """Every test gets a fresh SQLite file and the offline (rule-based) agent."""
    monkeypatch.setenv("VERIFLOW_DB", str(tmp_path / "test.db"))
    monkeypatch.setenv("VERIFLOW_AGENT", "fallback")
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    yield


@pytest.fixture
def scenario_a():
    from app import state
    return state.load("A")


@pytest.fixture
def scenario_b():
    from app import state
    return state.load("B")


@pytest.fixture
def client():
    from fastapi.testclient import TestClient
    from app.main import app
    with TestClient(app) as c:
        yield c


OWNER = {"X-Role": "owner", "X-Actor": "owner-test"}
ANALYST = {"X-Role": "analyst", "X-Actor": "analyst-test"}
