"""Runtime configuration, read from environment variables."""
from __future__ import annotations

import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"
STATIC_DIR = ROOT / "static"

SCENARIOS = {
    "A": DATA_DIR,
    "B": DATA_DIR / "scenario_b",
}

ROLES = ("analyst", "owner")
APPROVER_ROLES = ("owner",)


def db_path() -> str:
    return os.environ.get("VERIFLOW_DB", str(ROOT / "veriflow.db"))


def default_scenario() -> str:
    return os.environ.get("VERIFLOW_SCENARIO", "A").upper()


def claude_model() -> str:
    return os.environ.get("VERIFLOW_MODEL", "claude-opus-5-5")


def agent_mode() -> str:
    """'claude' when an API key is configured and not disabled, else 'fallback'."""
    if os.environ.get("VERIFLOW_AGENT", "").lower() == "fallback":
        return "fallback"
    return "claude" if os.environ.get("ANTHROPIC_API_KEY") else "fallback"
