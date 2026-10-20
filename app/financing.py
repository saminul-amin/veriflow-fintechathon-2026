"""Sample financing comparison for a forecast cash gap.

Informational simulation only: no credit decision, no application, no
eligibility claim. Offers come from data/financing_offers.csv (SYNTHETIC).
"""
from __future__ import annotations

DISCLAIMER = ("Sample terms for comparison only (SYNTHETIC). This is not a credit approval, an offer of credit, "
              "or personalised lending advice. Actual eligibility and pricing are decided by the lender.")


def _num(v, default=0.0) -> float:
    try:
        return float(v) if v is not None and str(v).strip() != "" else default
    except ValueError:
        return default


def evaluate_offer(offer: dict, gap: int, verified_receivable: int) -> dict:
    cap = offer["max_amount"]
    cap_reason = f"product maximum BDT {cap:,}"
    adv = _num(offer.get("advance_pct_of_receivable"), 0)
    if adv:
        rc_cap = int(verified_receivable * adv / 100)
        if rc_cap < cap:
            cap = rc_cap
            cap_reason = f"{adv:g}% of verified receivable BDT {verified_receivable:,}"
    borrow = max(gap, offer["min_amount"])
    term = int(_num(offer["term_days"]))
    rate = _num(offer["rate_pct"])
    if borrow > cap:
        return {**_base(offer), "fit": "cannot_cover", "borrow": None, "cap": cap, "cap_reason": cap_reason,
                "explanation": f"Can lend at most BDT {cap:,} ({cap_reason}), below the BDT {gap:,} gap."}
    if offer["rate_type"] == "flat":
        interest = round(borrow * rate / 100)
        rate_desc = f"{rate:g}% flat for {term} days"
    else:
        months = term / 30
        interest = round(borrow * rate / 100 * months)
        rate_desc = f"{rate:g}% per month x {months:g} months"
    processing = round(_num(offer.get("processing_fee_flat")) + borrow * _num(offer.get("processing_fee_pct")) / 100)
    cost = interest + processing
    fit = "covers_gap" if borrow == gap else "covers_gap_overborrow"
    explanation = (f"Borrow BDT {borrow:,} for {term} days: interest BDT {interest:,} ({rate_desc}) + processing "
                   f"BDT {processing:,} = total cost BDT {cost:,}; repay BDT {borrow + cost:,}.")
    if fit == "covers_gap_overborrow":
        explanation += f" Minimum loan is BDT {offer['min_amount']:,}, so BDT {borrow - gap:,} more than needed is borrowed."
    return {**_base(offer), "fit": fit, "borrow": borrow, "cap": cap, "cap_reason": cap_reason,
            "term_days": term, "interest": interest, "processing_fee": processing, "total_cost": cost,
            "total_repayment": borrow + cost, "explanation": explanation}


def _base(offer: dict) -> dict:
    return {"offer_id": offer["offer_id"], "provider": offer["provider"], "product": offer.get("product", ""),
            "collateral": offer.get("collateral", ""), "source": offer["_source"]}


def compare(offers: list[dict], cash: dict) -> dict:
    gap = cash["alert"]["gap"]
    verified_receivable = cash["expected_inflows"]["total"]
    if gap <= 0:
        return {"needed": False, "gap": 0, "options": [], "recommendation": None,
                "message": "No financing needed: the conservative cash outlook shows no shortfall. "
                           "Borrowing would add cost without a cash need.",
                "disclaimer": DISCLAIMER}
    options = [evaluate_offer(o, gap, verified_receivable) for o in offers]
    covering = [o for o in options if o["fit"] != "cannot_cover"]
    rec = None
    if covering:
        best = min(covering, key=lambda o: (o["total_cost"], o["borrow"]))
        rec = {"offer_id": best["offer_id"],
               "reason": f"Lowest total cost (BDT {best['total_cost']:,}) among options that cover the BDT {gap:,} gap"
                         + ("" if best["fit"] == "covers_gap" else ", though it requires over-borrowing") + ".",
               "label": "appears to fit - not a credit approval"}
    msg = (f"Conservative gap of BDT {gap:,}. " + (
        "No sample option can cover it." if not covering else
        "Compare against collecting the outstanding receivable, which would close the gap at no financing cost "
        "if it arrives in time." if verified_receivable >= gap else ""))
    return {"needed": True, "gap": gap, "options": options, "recommendation": rec,
            "no_suitable_option": not covering, "message": msg.strip(), "disclaimer": DISCLAIMER}
