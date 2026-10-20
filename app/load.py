"""Evidence intake: read the CSVs, validate them, keep source row references.

Rules:
- Missing required columns -> the whole file is rejected (LoadError).
- A row with a missing/invalid value is kept out of the calculations and
  reported as malformed, never silently repaired or guessed.
- Every accepted record carries `_source` ("file.csv:line") so findings can
  be traced back to the exact evidence row.
"""
from __future__ import annotations

import csv
import hashlib
import json
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path


class LoadError(Exception):
    pass


SCHEMAS: dict[str, dict] = {
    "orders": {
        "file": "orders.csv", "id": "order_id",
        "required": ["order_id", "order_date", "amount", "status"],
        "money": ["amount"], "dates": ["order_date"],
        "enums": {"status": {"shipped", "cancelled"}},
        "label": "Order records (order platform export)",
    },
    "deliveries": {
        "file": "deliveries.csv", "id": "delivery_id",
        "required": ["delivery_id", "order_id", "courier", "status", "status_date", "cod_collected"],
        "money": ["cod_collected"], "dates": ["status_date"],
        "enums": {"status": {"delivered", "returned", "in_transit"}},
        "label": "Courier delivery statuses",
    },
    "settlements": {
        "file": "settlements.csv", "id": "settlement_id",
        "required": ["settlement_id", "courier", "delivery_ids", "gross_collected", "fees", "net_payable"],
        "money": ["gross_collected", "fees", "net_payable"], "dates": ["period_start", "period_end"],
        "optional_dates": ["due_date"],
        "enums": {},
        "label": "Courier settlement statements",
    },
    "bank_receipts": {
        "file": "bank_receipts.csv", "id": "receipt_id",
        "required": ["receipt_id", "date", "amount", "reference"],
        "money": ["amount"], "dates": ["date"],
        "enums": {},
        "label": "Bank receipts (bank statement export)",
    },
    "obligations": {
        "file": "obligations.csv", "id": "obligation_id",
        "required": ["obligation_id", "description", "amount", "due_date", "status"],
        "money": ["amount"], "dates": [], "optional_dates": ["due_date"],
        "enums": {"status": {"paid", "unpaid"}},
        "label": "Expenses and upcoming obligations",
    },
    "financing_offers": {
        "file": "financing_offers.csv", "id": "offer_id",
        "required": ["offer_id", "provider", "min_amount", "max_amount", "term_days", "rate_type", "rate_pct"],
        "money": ["min_amount", "max_amount"], "dates": [],
        "enums": {"rate_type": {"flat", "monthly"}},
        "label": "Sample financing offers (SYNTHETIC, informational)",
    },
}

# Free-text fields: always treated as untrusted data.
TEXT_FIELDS = {
    "orders": ["channel", "customer_ref"],
    "deliveries": ["note"],
    "settlements": [],
    "bank_receipts": ["counterparty", "reference"],
    "obligations": ["description", "counterparty"],
    "financing_offers": ["note", "product", "collateral"],
}


@dataclass
class Dataset:
    meta: dict
    records: dict[str, list[dict]] = field(default_factory=dict)
    malformed: list[dict] = field(default_factory=list)
    files: dict[str, dict] = field(default_factory=dict)

    def index(self) -> dict[str, dict]:
        """Map every record id -> record (with its kind)."""
        out = {}
        for kind, rows in self.records.items():
            id_field = SCHEMAS[kind]["id"]
            for r in rows:
                out[r[id_field]] = {"kind": kind, **r}
        return out

    @property
    def as_of(self) -> date:
        return date.fromisoformat(self.meta["as_of"])


def _parse_money(value: str) -> int:
    v = (value or "").strip().replace(",", "")
    if not v:
        raise ValueError("missing amount")
    if not v.lstrip("-").isdigit():
        raise ValueError(f"not a whole-number BDT amount: {value!r}")
    return int(v)


def _parse_date(value: str) -> str:
    return date.fromisoformat(value.strip()).isoformat()


def _load_file(folder: Path, kind: str, ds: Dataset) -> None:
    schema = SCHEMAS[kind]
    path = folder / schema["file"]
    if not path.exists():
        raise LoadError(f"missing evidence file: {schema['file']}")
    raw = path.read_bytes()
    ds.files[kind] = {
        "file": schema["file"],
        "label": schema["label"],
        "sha256": hashlib.sha256(raw).hexdigest(),
    }
    reader = csv.DictReader(raw.decode("utf-8-sig").splitlines())
    missing_cols = [c for c in schema["required"] if c not in (reader.fieldnames or [])]
    if missing_cols:
        raise LoadError(f"{schema['file']} is missing required columns: {', '.join(missing_cols)}")

    rows, seen = [], set()
    for line_no, row in enumerate(reader, start=2):
        source = f"{schema['file']}:{line_no}"
        rid = (row.get(schema["id"]) or "").strip()
        try:
            for col in schema["required"]:
                if not (row.get(col) or "").strip():
                    raise ValueError(f"missing required value '{col}'")
            if rid in seen:
                raise ValueError(f"duplicate id {rid}")
            rec = {k: (v or "").strip() for k, v in row.items() if k is not None}
            for col in schema["money"]:
                rec[col] = _parse_money(rec.get(col, ""))
            for col in schema.get("dates", []):
                if rec.get(col):
                    rec[col] = _parse_date(rec[col])
            for col in schema.get("optional_dates", []):
                rec[col] = _parse_date(rec[col]) if rec.get(col) else ""
            for col, allowed in schema["enums"].items():
                if rec.get(col) not in allowed:
                    raise ValueError(f"unexpected {col} '{rec.get(col)}'")
        except ValueError as exc:
            ds.malformed.append({"kind": kind, "record_id": rid or "(no id)", "source": source,
                                 "reason": str(exc), "raw": {k: v for k, v in row.items() if k}})
            continue
        seen.add(rid)
        rec["_source"] = source
        rows.append(rec)
    ds.records[kind] = rows
    ds.files[kind]["rows_accepted"] = len(rows)


def load_dataset(folder: Path) -> Dataset:
    meta_path = folder / "scenario.json"
    if not meta_path.exists():
        raise LoadError(f"missing scenario.json in {folder}")
    ds = Dataset(meta=json.loads(meta_path.read_text(encoding="utf-8")))
    for kind in SCHEMAS:
        _load_file(folder, kind, ds)
    ds.meta["malformed_rows"] = len(ds.malformed)
    return ds
