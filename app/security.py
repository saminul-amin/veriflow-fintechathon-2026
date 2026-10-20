"""Untrusted-input boundary.

Every free-text field in uploaded evidence is DATA, never an instruction.
This module:
1. detects instruction-like text in evidence and reports it (it is logged and ignored);
2. neutralises evidence text before it is placed into an LLM prompt;
3. defines the closed allowlist of things the agent may ever request.

Defence does not rely on detection alone: settlement status is computed only
from bank evidence, the agent can only request actions from ACTION_ALLOWLIST,
and the action amount/target are always taken from computed case data, never
from model output or free text.
"""
from __future__ import annotations

import re

from .load import TEXT_FIELDS, SCHEMAS, Dataset

INSTRUCTION_PATTERNS: list[tuple[str, re.Pattern]] = [
    ("override_rules", re.compile(r"\b(ignore|disregard|forget|override)\b.{0,40}\b(rules?|instructions?|polic(y|ies)|prompts?)\b", re.I)),
    ("force_settlement_status", re.compile(r"\bmark\b.{0,40}\b(settled|paid|resolved|received|confirmed)\b", re.I)),
    ("change_payment_destination", re.compile(r"\b(change|update|replace|redirect)\b.{0,40}\b(destination|beneficiary|bank|account|payee)\b", re.I)),
    ("approval_bypass", re.compile(r"\b(approve|authori[sz]e|execute|transfer|send money|pay out)\b.{0,30}\b(now|immediately|automatically|without)\b", re.I)),
    ("role_hijack", re.compile(r"\b(you are now|act as|system prompt|developer mode|as the assistant)\b", re.I)),
]

# The only action types the agent may propose. Nothing that moves money,
# changes a settlement status, or edits a beneficiary exists in the system.
ACTION_ALLOWLIST = {"create_courier_followup_case"}


def scan_text(text: str) -> list[str]:
    return [name for name, pat in INSTRUCTION_PATTERNS if text and pat.search(text)]


def scan_dataset(ds: Dataset) -> list[dict]:
    flags = []
    for kind, fields in TEXT_FIELDS.items():
        id_field = SCHEMAS[kind]["id"]
        for rec in ds.records.get(kind, []):
            for f in fields:
                hits = scan_text(rec.get(f, ""))
                if hits:
                    flags.append({
                        "record_id": rec[id_field],
                        "kind": kind,
                        "field": f,
                        "source": rec["_source"],
                        "text": rec[f],
                        "patterns": hits,
                        "handling": "Treated as untrusted evidence text only; not executed, "
                                    "no effect on settlement status or action targets.",
                    })
    return flags


def neutralise(text: str, record_id: str, flagged_ids: set[str]) -> str:
    """Prepare evidence text for an LLM prompt: flagged text is withheld, the rest is escaped."""
    if record_id in flagged_ids:
        return f"[WITHHELD: instruction-like text detected in {record_id}; retained as evidence only]"
    return text.replace("<", "&lt;").replace(">", "&gt;")[:200]


def untrusted_notes_block(ds: Dataset, flagged_ids: set[str]) -> str:
    lines = []
    for rec in ds.records.get("deliveries", []):
        if rec.get("note"):
            lines.append(f'- {rec["delivery_id"]}: "{neutralise(rec["note"], rec["delivery_id"], flagged_ids)}"')
    return "\n".join(lines)
