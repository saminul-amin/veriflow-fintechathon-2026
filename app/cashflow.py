"""Near-term cash-flow outlook.

Confirmed cash and expected inflows are kept apart. They are never added into
a single headline figure; the only place they meet is the explicitly labelled
"expected case" closing position, which states its assumption.
"""
from __future__ import annotations

from datetime import date, timedelta

from .load import Dataset


def outlook(ds: Dataset, recon: dict) -> dict:
    as_of = ds.as_of
    days = int(ds.meta.get("outlook_days", 7))
    window_end = as_of + timedelta(days=days)

    confirmed = {
        "amount": recon["totals"]["confirmed_cash"],
        "inputs": recon["confirmed_receipt_ids"],
        "basis": ds.meta.get("opening_cash_basis", "Sum of deduplicated bank receipts."),
        "label": "confirmed",
    }

    inflows = []
    for s in recon["settlements"]:
        if s["status"] == "confirmed":
            continue
        inflows.append({
            "source_id": s["settlement_id"],
            "amount": s["net_payable"],
            "status": s["status"],
            "assumption": f"Expected case assumes {s['settlement_id']} is remitted within the next {days} days. "
                          "Conservative case assumes it is not.",
            "label": "estimated",
        })
    expected_total = sum(i["amount"] for i in inflows)

    in_window, excluded, limitations = [], [], []
    for ob in ds.records["obligations"]:
        if ob["status"] == "paid":
            excluded.append({**_brief(ob), "reason": "already paid"})
            continue
        if not ob["due_date"]:
            limitations.append(f"{ob['obligation_id']} has no due date; not included in the {days}-day window.")
            excluded.append({**_brief(ob), "reason": "no due date"})
            continue
        due = date.fromisoformat(ob["due_date"])
        if due <= window_end:
            in_window.append({**_brief(ob), "overdue": due < as_of})
        else:
            excluded.append({**_brief(ob), "reason": f"due after {window_end.isoformat()}"})
    for m in ds.malformed:
        if m["kind"] == "obligations":
            limitations.append(f"{m['record_id']} ({m['source']}) could not be read ({m['reason']}); "
                               "its amount is unknown and is NOT included - the outflow may be understated.")
    obligations_total = sum(o["amount"] for o in in_window)

    conservative = confirmed["amount"] - obligations_total
    expected = conservative + expected_total

    if conservative < 0 and expected < 0:
        alert = {"level": "shortfall_both", "gap": -conservative,
                 "message": f"Shortfall in both cases: obligations of BDT {obligations_total:,} exceed confirmed cash, "
                            f"even if the BDT {expected_total:,} receivable arrives."}
    elif conservative < 0:
        alert = {"level": "shortfall_conservative", "gap": -conservative,
                 "message": f"Cash alert: confirmed cash of BDT {confirmed['amount']:,} does not cover BDT "
                            f"{obligations_total:,} of obligations due by {window_end.isoformat()}. Gap BDT "
                            f"{-conservative:,} unless the BDT {expected_total:,} receivable is collected in time."}
    else:
        alert = {"level": "none", "gap": 0,
                 "message": f"No shortfall: confirmed cash covers the BDT {obligations_total:,} of obligations due by "
                            f"{window_end.isoformat()} even if no receivable arrives."}

    limitations.append("Outlook covers only obligations recorded in obligations.csv; unrecorded spending is not included.")

    return {
        "as_of": as_of.isoformat(),
        "window_days": days,
        "window_end": window_end.isoformat(),
        "confirmed_cash": confirmed,
        "expected_inflows": {"items": inflows, "total": expected_total, "label": "estimated"},
        "obligations": {"items": in_window, "total": obligations_total, "excluded": excluded},
        "scenarios": {
            "conservative": {"closing": conservative,
                             "formula": "confirmed cash - obligations due in window",
                             "assumption": "No uncertain receivable arrives in the window."},
            "expected": {"closing": expected,
                         "formula": "conservative closing + expected inflows",
                         "assumption": "Every listed outstanding settlement is remitted within the window."},
        },
        "alert": alert,
        "limitations": limitations,
    }


def _brief(ob: dict) -> dict:
    return {"obligation_id": ob["obligation_id"], "description": ob["description"],
            "counterparty": ob.get("counterparty", ""), "amount": ob["amount"], "due_date": ob["due_date"]}
