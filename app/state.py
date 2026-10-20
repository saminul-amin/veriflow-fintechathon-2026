"""In-memory analysis state for the currently loaded SYNTHETIC dataset."""
from __future__ import annotations

import threading
from dataclasses import dataclass

from . import cashflow, config, db, financing, reconcile, security
from .load import Dataset, load_dataset


@dataclass
class Analysis:
    scenario: str
    dataset: Dataset
    recon: dict
    cash: dict
    finance: dict
    flags: list[dict]
    cases: list[dict]

    @property
    def flagged_ids(self) -> set[str]:
        return {f["record_id"] for f in self.flags}

    def case(self, case_id: str) -> dict | None:
        c = next((c for c in self.cases if c["case_id"] == case_id), None)
        if c is None:
            return None
        row = db.query("SELECT status FROM cases WHERE case_id = ?", (case_id,))
        return {**c, "status": row[0]["status"] if row else "open"}

    def cases_with_status(self) -> list[dict]:
        statuses = {r["case_id"]: r["status"] for r in db.query("SELECT case_id, status FROM cases")}
        return [{**c, "status": statuses.get(c["case_id"], "open")} for c in self.cases]

    def known_ids(self) -> set[str]:
        return set(self.dataset.index()) | {c["case_id"] for c in self.cases}


_current: Analysis | None = None
_lock = threading.RLock()


def load(scenario: str, actor: str = "system", role: str = "system") -> Analysis:
    global _current
    scenario = scenario.upper()
    if scenario not in config.SCENARIOS:
        raise ValueError(f"unknown scenario {scenario}")
    with _lock:
        ds = load_dataset(config.SCENARIOS[scenario])
        recon = reconcile.reconcile(ds)
        cash = cashflow.outlook(ds, recon)
        finance = financing.compare(ds.records["financing_offers"], cash)
        flags = security.scan_dataset(ds)
        cases = reconcile.build_cases(ds, recon, flags)

        db.init()
        db.reset_sandbox_state()
        for c in cases:
            initial = "open" if c["actionable"] else "informational"
            db.execute("INSERT INTO cases (case_id, status, updated_at) VALUES (?,?,?)",
                       (c["case_id"], initial, db.now()))

        db.audit(actor, role, "dataset_loaded", "dataset", f"scenario_{scenario}", "loaded",
                 details={"label": ds.meta.get("label"), "synthetic": ds.meta.get("synthetic", True),
                          "files": ds.files, "malformed_rows": ds.malformed and
                          [{"id": m["record_id"], "source": m["source"], "reason": m["reason"]} for m in ds.malformed]})
        for f in flags:
            db.audit("veriflow-guard", "system", "untrusted_instruction_detected", f["kind"], f["record_id"],
                     "ignored", evidence_ids=[f["record_id"]],
                     details={"field": f["field"], "source": f["source"], "patterns": f["patterns"],
                              "text": f["text"], "handling": f["handling"]})
        db.audit("veriflow-engine", "system", "reconciliation_completed", "dataset", f"scenario_{scenario}",
                 "completed", evidence_ids=recon["matched_receipt_ids"],
                 details={"totals": recon["totals"], "checks": recon["checks"],
                          "cases": [c["case_id"] + ": " + c["title"] for c in cases],
                          "cash_alert": cash["alert"]["level"]})
        _current = Analysis(scenario, ds, recon, cash, finance, flags, cases)
        return _current


def current() -> Analysis:
    if _current is None:
        return load(config.default_scenario())
    return _current
