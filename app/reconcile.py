"""Deterministic reconciliation: orders -> deliveries -> settlements -> bank receipts.

No LLM is involved in any number produced here. Every figure carries the ids
of the records it was computed from.

Financial truth rules enforced:
- order placed != cash received
- delivered != bank settled
- courier "remitted" != independently confirmed bank receipt
- a bank receipt is matched to at most one settlement; repeated statement
  rows for the same payment are flagged as duplicates and counted once
- "overdue" requires an evidenced due date that has passed; otherwise the
  receivable stays "pending" or "unresolved"
"""
from __future__ import annotations

from datetime import date

from .load import Dataset


def _wf(stage: str, amount: int, inputs: list[str], formula: str, kind: str) -> dict:
    return {"stage": stage, "amount": amount, "inputs": inputs, "formula": formula, "kind": kind}


def reconcile(ds: Dataset) -> dict:
    as_of = ds.as_of
    orders = ds.records["orders"]
    deliveries = ds.records["deliveries"]
    settlements = ds.records["settlements"]
    receipts = ds.records["bank_receipts"]

    deliveries_by_order: dict[str, list[dict]] = {}
    for d in deliveries:
        deliveries_by_order.setdefault(d["order_id"], []).append(d)

    # ---- 1. classify every order -------------------------------------------------
    classified = []
    for o in orders:
        dl = deliveries_by_order.get(o["order_id"], [])
        if o["status"] == "cancelled":
            outcome, evidence = "cancelled", [o["order_id"]]
        elif not dl:
            outcome, evidence = "no_delivery_record", [o["order_id"]]
        else:
            latest = sorted(dl, key=lambda d: d["status_date"])[-1]
            outcome = latest["status"]  # delivered / returned / in_transit
            evidence = [o["order_id"], latest["delivery_id"]]
        classified.append({"order_id": o["order_id"], "amount": o["amount"], "outcome": outcome,
                           "evidence_ids": evidence})

    def ids(outcome):
        return [c["order_id"] for c in classified if c["outcome"] == outcome]

    def total(outcome):
        return sum(c["amount"] for c in classified if c["outcome"] == outcome)

    placed = sum(o["amount"] for o in orders)
    cancelled, returned, delivered = total("cancelled"), total("returned"), total("delivered")

    issues: list[dict] = []

    # ---- 2. deliveries -> settlements -------------------------------------------
    delivered_rows = {d["delivery_id"]: d for d in deliveries if d["status"] == "delivered"}
    delivery_to_settlement: dict[str, str] = {}
    settlement_rows = []
    for s in settlements:
        dids = [x.strip() for x in s["delivery_ids"].split(";") if x.strip()]
        problems = []
        for did in dids:
            if did in delivery_to_settlement:
                problems.append(f"{did} already claimed by {delivery_to_settlement[did]}")
                issues.append({"kind": "duplicate_delivery_reference", "settlement_id": s["settlement_id"],
                               "delivery_id": did, "other_settlement": delivery_to_settlement[did]})
                continue
            if did not in delivered_rows:
                problems.append(f"{did} is not a delivered parcel")
                issues.append({"kind": "settlement_references_undelivered", "settlement_id": s["settlement_id"],
                               "delivery_id": did})
                continue
            delivery_to_settlement[did] = s["settlement_id"]
        collected = sum(delivered_rows[d]["cod_collected"] for d in dids if delivery_to_settlement.get(d) == s["settlement_id"])
        if collected != s["gross_collected"]:
            problems.append(f"statement gross {s['gross_collected']} != delivered COD {collected}")
            issues.append({"kind": "gross_mismatch", "settlement_id": s["settlement_id"],
                           "statement_gross": s["gross_collected"], "delivered_cod": collected})
        if s["gross_collected"] - s["fees"] != s["net_payable"]:
            problems.append("gross - fees != net payable on statement")
            issues.append({"kind": "net_arithmetic_mismatch", "settlement_id": s["settlement_id"]})
        settlement_rows.append({**s, "delivery_list": dids, "delivered_cod": collected, "problems": problems})

    unsettled = [d for did, d in delivered_rows.items() if did not in delivery_to_settlement]
    for d in unsettled:
        issues.append({"kind": "delivered_not_on_statement", "delivery_id": d["delivery_id"],
                       "order_id": d["order_id"], "amount": d["cod_collected"]})

    # ---- 3. settlements -> bank receipts (each receipt used at most once) --------
    used: dict[str, str] = {}
    receipt_status: dict[str, dict] = {}
    for s in settlement_rows:
        match = None
        candidates = [r for r in receipts if r["reference"] == s["settlement_id"] and r["receipt_id"] not in used]
        for r in candidates:
            if r["amount"] == s["net_payable"]:
                match = r
                break
        if match:
            used[match["receipt_id"]] = s["settlement_id"]
            receipt_status[match["receipt_id"]] = {"status": "matched", "settlement_id": s["settlement_id"]}
            s["bank_receipt_id"] = match["receipt_id"]
            s["status"] = "confirmed"
            s["days_overdue"] = 0
            continue
        s["bank_receipt_id"] = None
        partial = [r for r in candidates if r["amount"] != s["net_payable"]]
        if partial:
            s["status"] = "amount_mismatch"
            s["mismatch_receipts"] = [r["receipt_id"] for r in partial]
            issues.append({"kind": "receipt_amount_mismatch", "settlement_id": s["settlement_id"],
                           "receipt_ids": [r["receipt_id"] for r in partial],
                           "expected": s["net_payable"], "received": sum(r["amount"] for r in partial)})
        if not s.get("due_date"):
            s.setdefault("status", "unresolved")
            s["days_overdue"] = None
            s["due_basis"] = "No due date in the settlement evidence - cannot be classified as overdue."
        else:
            due = date.fromisoformat(s["due_date"])
            if as_of > due:
                s.setdefault("status", "overdue")
                s["days_overdue"] = (as_of - due).days
            else:
                s.setdefault("status", "pending")
                s["days_overdue"] = 0
            s["due_basis"] = f"Due date {s['due_date']} from {s['_source']}; as-of date {as_of.isoformat()}."
        s["courier_claim_unverified"] = s.get("courier_status") == "remitted"
        if s["status"] in ("overdue", "pending", "unresolved"):
            issues.append({"kind": "no_bank_receipt", "settlement_id": s["settlement_id"],
                           "status": s["status"], "amount": s["net_payable"]})

    # Remaining receipts: duplicates of an already-matched payment, or unapplied cash.
    for r in receipts:
        if r["receipt_id"] in receipt_status:
            continue
        twin = next((m for m in receipts if m["receipt_id"] in used and m["reference"] == r["reference"]
                     and m["amount"] == r["amount"] and m["date"] == r["date"]), None)
        if twin:
            receipt_status[r["receipt_id"]] = {"status": "duplicate", "duplicate_of": twin["receipt_id"]}
            issues.append({"kind": "duplicate_receipt", "receipt_id": r["receipt_id"],
                           "duplicate_of": twin["receipt_id"], "amount": r["amount"]})
        elif any(s.get("mismatch_receipts") and r["receipt_id"] in s["mismatch_receipts"] for s in settlement_rows):
            receipt_status[r["receipt_id"]] = {"status": "amount_mismatch"}
        else:
            receipt_status[r["receipt_id"]] = {"status": "unapplied"}
            issues.append({"kind": "unapplied_receipt", "receipt_id": r["receipt_id"], "amount": r["amount"]})

    matched_ids = [rid for rid, st in receipt_status.items() if st["status"] == "matched"]
    banked = sum(r["amount"] for r in receipts if r["receipt_id"] in matched_ids)
    unique_receipt_ids = [r["receipt_id"] for r in receipts if receipt_status[r["receipt_id"]]["status"] != "duplicate"]
    confirmed_cash = sum(r["amount"] for r in receipts if r["receipt_id"] in unique_receipt_ids)

    fees = sum(s["fees"] for s in settlement_rows)
    expected_net = delivered - fees
    outstanding = expected_net - banked
    outstanding_settlements = [s for s in settlement_rows if s["status"] != "confirmed"]

    waterfall = [
        _wf("Orders placed", placed, [o["order_id"] for o in orders], "sum(orders.amount)", "evidence"),
        _wf("Cancelled orders", -cancelled, ids("cancelled"), "orders with status=cancelled", "evidence"),
        _wf("Returned orders", -returned, ids("returned"), "orders whose latest delivery status=returned", "evidence"),
        _wf("Delivered & COD collected", delivered, ids("delivered"),
            "placed - cancelled - returned (orders with delivery status=delivered)", "computed"),
        _wf("Documented courier fees", -fees, [s["settlement_id"] for s in settlement_rows],
            "sum(settlements.fees)", "evidence"),
        _wf("Expected net settlement", expected_net, ["Delivered & COD collected", "Documented courier fees"],
            "delivered - fees", "computed"),
        _wf("Bank-confirmed receipts", -banked, matched_ids,
            "bank receipts matched 1:1 to a settlement by reference and amount", "evidence"),
        _wf("Unconfirmed courier receivable", outstanding,
            [s["settlement_id"] for s in outstanding_settlements] + [d["delivery_id"] for d in unsettled],
            "expected net settlement - bank-confirmed receipts", "computed"),
    ]

    checks = {
        "placed_equals_parts": placed == cancelled + returned + delivered + sum(
            c["amount"] for c in classified if c["outcome"] not in ("cancelled", "returned", "delivered")),
        "outstanding_equals_open_settlements": outstanding == sum(s["net_payable"] for s in outstanding_settlements)
            + sum(d["cod_collected"] for d in unsettled),
        "no_receipt_matched_twice": len(set(used)) == len(used) and len(set(used.values())) == len(used),
    }

    return {
        "as_of": as_of.isoformat(),
        "currency": ds.meta.get("currency", "BDT"),
        "totals": {
            "placed": placed, "cancelled": cancelled, "returned": returned, "delivered": delivered,
            "fees": fees, "expected_net": expected_net, "banked": banked, "outstanding": outstanding,
            "confirmed_cash": confirmed_cash,
        },
        "waterfall": waterfall,
        "orders": classified,
        "settlements": settlement_rows,
        "receipts": [{**r, **receipt_status[r["receipt_id"]]} for r in receipts],
        "unsettled_deliveries": unsettled,
        "confirmed_receipt_ids": unique_receipt_ids,
        "matched_receipt_ids": matched_ids,
        "issues": issues,
        "checks": checks,
    }


# ---- investigation cases ------------------------------------------------------------

def _priority(amount: int, days_overdue: int | None) -> tuple[int, str, list[str]]:
    """Transparent rule: amount (per 1,000 BDT) + 2 points per day overdue."""
    days = days_overdue or 0
    score = amount // 1000 + 2 * days
    reasons = [f"amount BDT {amount:,} -> {amount // 1000} pts"]
    if days:
        reasons.append(f"{days} days past evidenced due date -> {2 * days} pts")
    label = "High" if amount >= 20000 or days >= 3 else ("Medium" if amount >= 5000 else "Low")
    return score, label, reasons


def build_cases(ds: Dataset, recon: dict, security_flags: list[dict]) -> list[dict]:
    cases = []
    settlements = {s["settlement_id"]: s for s in recon["settlements"]}
    deliveries = {d["delivery_id"]: d for d in ds.records["deliveries"]}

    for s in recon["settlements"]:
        if s["status"] == "confirmed":
            continue
        dl = [deliveries[d] for d in s["delivery_list"] if d in deliveries]
        order_ids = [d["order_id"] for d in dl]
        score, label, reasons = _priority(s["net_payable"], s.get("days_overdue"))
        status_word = {"overdue": "Overdue", "pending": "Pending", "unresolved": "Unresolved",
                       "amount_mismatch": "Amount mismatch on"}[s["status"]]
        uncertainties = [
            "No bank receipt referencing this settlement exists in the supplied bank evidence.",
            "The courier may have remitted under a different reference; this has not been verified.",
        ]
        if s["status"] == "unresolved":
            uncertainties.append("No due date was supplied, so the receivable cannot be called overdue.")
        if s.get("courier_status") == "remitted":
            uncertainties.append("Courier statement says 'remitted' but there is no matching bank receipt.")
        flagged = [f["record_id"] for f in security_flags if f["record_id"] in s["delivery_list"]]
        if flagged:
            uncertainties.append(f"Delivery note on {', '.join(flagged)} contains instruction-like text; "
                                 "it was ignored and does not change this finding.")
        cases.append({
            "kind": "overdue_receivable" if s["status"] == "overdue" else "unconfirmed_receivable",
            "title": f"{status_word} courier settlement {s['settlement_id']} - BDT {s['net_payable']:,} not in bank",
            "amount": s["net_payable"],
            "counterparty": s["courier"],
            "settlement_id": s["settlement_id"],
            "classification": "Confirmed discrepancy: expected settlement has no matching bank receipt"
                              + (" (overdue by evidenced due date)" if s["status"] == "overdue" else ""),
            "description": (
                f"Settlement statement {s['settlement_id']} covers deliveries {', '.join(s['delivery_list'])} "
                f"(orders {', '.join(order_ids)}). Gross COD collected BDT {s['gross_collected']:,}, documented fees "
                f"BDT {s['fees']:,}, net payable BDT {s['net_payable']:,}. {s.get('due_basis', '')} "
                f"Bank receipts checked: {', '.join(r['receipt_id'] for r in recon['receipts'])}; none matches. "
                "This is an overdue receivable to follow up, not evidence of fraud or loss."
                if s["status"] == "overdue" else
                f"Settlement {s['settlement_id']} (net BDT {s['net_payable']:,}) has no matching bank receipt yet. "
                f"{s.get('due_basis', '')}"
            ),
            "evidence_ids": [s["settlement_id"], *s["delivery_list"], *order_ids],
            "checked_receipt_ids": [r["receipt_id"] for r in recon["receipts"]],
            "excluded_matched_receipts": recon["matched_receipt_ids"],
            "days_overdue": s.get("days_overdue"),
            "due_date": s.get("due_date") or None,
            "priority_score": score, "priority": label, "priority_reasons": reasons,
            "uncertainties": uncertainties,
            "actionable": True,
            "suggested_action": "create_courier_followup_case",
        })

    for issue in recon["issues"]:
        if issue["kind"] == "duplicate_receipt":
            cases.append({
                "kind": "duplicate_receipt",
                "title": f"Duplicate bank statement row {issue['receipt_id']} counted once",
                "amount": issue["amount"], "counterparty": "Bank statement export",
                "settlement_id": None,
                "classification": "Data-quality finding (resolved by rule)",
                "description": (f"{issue['receipt_id']} repeats {issue['duplicate_of']} (same reference, date and amount). "
                                "It is treated as the same payment and excluded from confirmed cash to avoid double counting."),
                "evidence_ids": [issue["receipt_id"], issue["duplicate_of"]],
                "priority_score": 0, "priority": "Low", "priority_reasons": ["no cash impact after de-duplication"],
                "uncertainties": ["If these are genuinely two payments, the bank should confirm a second transaction id."],
                "actionable": False,
            })
        elif issue["kind"] in ("unapplied_receipt", "gross_mismatch", "delivered_not_on_statement",
                               "duplicate_delivery_reference", "settlement_references_undelivered",
                               "net_arithmetic_mismatch"):
            ref = issue.get("receipt_id") or issue.get("settlement_id") or issue.get("delivery_id")
            cases.append({
                "kind": issue["kind"], "title": f"{issue['kind'].replace('_', ' ').capitalize()} - {ref}",
                "amount": issue.get("amount", 0), "counterparty": "", "settlement_id": issue.get("settlement_id"),
                "classification": "Suspected discrepancy - needs review",
                "description": str(issue), "evidence_ids": [x for x in (issue.get("receipt_id"), issue.get("settlement_id"),
                                                                      issue.get("delivery_id")) if x],
                "priority_score": issue.get("amount", 0) // 1000, "priority": "Medium", "priority_reasons": [],
                "uncertainties": ["Requires manual review of the source documents."], "actionable": False,
            })

    for f in security_flags:
        cases.append({
            "kind": "untrusted_instruction",
            "title": f"Instruction-like text in {f['record_id']} ignored",
            "amount": 0, "counterparty": "", "settlement_id": None,
            "classification": "Security notice - input treated as data",
            "description": (f"Field '{f['field']}' of {f['record_id']} ({f['source']}) contains text that tries to give "
                            f"instructions ({', '.join(f['patterns'])}). VeriFlow does not follow it: settlement status "
                            "comes only from bank evidence and no action can change payment status or accounts."),
            "evidence_ids": [f["record_id"]],
            "priority_score": 0, "priority": "Info", "priority_reasons": [],
            "uncertainties": [], "actionable": False, "flagged_text": f["text"],
        })

    for m in ds.malformed:
        cases.append({
            "kind": "malformed_row",
            "title": f"Unreadable row {m['record_id']} excluded ({m['source']})",
            "amount": 0, "counterparty": "", "settlement_id": None,
            "classification": "Missing information - excluded from calculations",
            "description": f"{m['source']}: {m['reason']}. The row was not guessed or repaired.",
            "evidence_ids": [m["record_id"]],
            "priority_score": 0, "priority": "Info", "priority_reasons": [],
            "uncertainties": ["Calculations that depend on this row are incomplete until it is corrected at source."],
            "actionable": False,
        })

    cases.sort(key=lambda c: (-c["priority_score"], c["kind"]))
    for i, c in enumerate(cases, start=1):
        c["case_id"] = f"CASE-{i:03d}"
    return cases
