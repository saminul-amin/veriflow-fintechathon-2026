"""Approval-governed sandbox actions.

State machine:  proposed --approve(owner)--> approved --> executed (sandbox)
                proposed --reject(owner)---> rejected (no side effects)

- Only the 'owner' role may approve or reject.
- The proposer (e.g. the agent) can never approve its own proposal.
- Target and amount are copied from the computed case, never from free text
  or model output.
- Execution only creates an internal follow-up record with a DRAFT message.
  Nothing is sent to any courier; nothing moves money.
"""
from __future__ import annotations

import json
import uuid

from . import config, db
from .security import ACTION_ALLOWLIST
from .state import Analysis


class ActionError(Exception):
    def __init__(self, message: str, status_code: int = 400):
        super().__init__(message)
        self.status_code = status_code


def _row(action_id: str) -> dict | None:
    rows = db.query("SELECT * FROM actions WHERE action_id = ?", (action_id,))
    if not rows:
        return None
    r = rows[0]
    r["payload"] = json.loads(r["payload"])
    r["result"] = json.loads(r["result"]) if r["result"] else None
    return r


def list_actions() -> list[dict]:
    out = []
    for r in db.query("SELECT action_id FROM actions ORDER BY proposed_at DESC, action_id DESC"):
        out.append(_row(r["action_id"]))
    return out


def get(action_id: str) -> dict | None:
    return _row(action_id)


def followups() -> list[dict]:
    return db.query("SELECT * FROM followups ORDER BY created_at")


def draft_text(analysis: Analysis, case: dict) -> str:
    s = next(x for x in analysis.recon["settlements"] if x["settlement_id"] == case["settlement_id"])
    deliveries = {d["delivery_id"]: d for d in analysis.dataset.records["deliveries"]}
    lines = [
        "DRAFT - NOT SENT (VeriFlow sandbox, SYNTHETIC data)",
        f"To: {s['courier']} - merchant settlements desk",
        f"Subject: Settlement {s['settlement_id']} - BDT {s['net_payable']:,} not yet received",
        "",
        "Hello,",
        f"Our records show settlement statement {s['settlement_id']} (period {s.get('period_start', '')} to "
        f"{s.get('period_end', '')}) with net payable BDT {s['net_payable']:,} "
        f"(gross COD BDT {s['gross_collected']:,} less fees BDT {s['fees']:,}).",
        "Deliveries covered:",
    ]
    for did in s["delivery_list"]:
        d = deliveries.get(did)
        if d:
            lines.append(f"  - {did} / order {d['order_id']} - delivered {d['status_date']} - COD BDT {d['cod_collected']:,}")
    lines += [
        (f"The statement due date was {s['due_date']}. As of {analysis.recon['as_of']} we have no bank receipt "
         f"referencing {s['settlement_id']}.") if s.get("due_date") else
        f"As of {analysis.recon['as_of']} we have no bank receipt referencing {s['settlement_id']}.",
        f"Already received and excluded from this request: "
        + ", ".join(f"{r['receipt_id']} ({r['settlement_id']})" for r in analysis.recon["receipts"] if r["status"] == "matched")
        + ".",
        "Please confirm the remittance date and transaction reference, or the expected payment date.",
        "",
        "Thank you.",
    ]
    return "\n".join(lines)


def propose(analysis: Analysis, case_id: str, proposed_by: str, proposer_role: str,
            action_type: str = "create_courier_followup_case", origin: str = "user") -> dict:
    if action_type not in ACTION_ALLOWLIST:
        db.audit(proposed_by, proposer_role, "action_blocked", "action", action_type, "blocked",
                 details={"reason": "action type not in allowlist", "origin": origin})
        raise ActionError(f"action type '{action_type}' is not permitted", 403)
    case = analysis.case(case_id)
    if case is None:
        raise ActionError(f"unknown case {case_id}", 404)
    if not case.get("actionable"):
        raise ActionError(f"{case_id} is informational; no follow-up action applies", 409)
    open_rows = db.query("SELECT action_id FROM actions WHERE case_id = ? AND status = 'proposed'", (case_id,))
    if open_rows:
        return _row(open_rows[0]["action_id"])
    if case["status"] == "action_prepared":
        raise ActionError(f"{case_id} already has an executed sandbox follow-up", 409)

    s = next(x for x in analysis.recon["settlements"] if x["settlement_id"] == case["settlement_id"])
    payload = {
        "summary": f"Create courier settlement follow-up case for {s['settlement_id']} and prepare a reminder draft",
        "target": s["courier"],
        "target_source": f"settlements.csv ({s['_source']})",
        "amount": s["net_payable"],
        "amount_source": f"{s['settlement_id']}.net_payable = gross {s['gross_collected']:,} - fees {s['fees']:,}",
        "justification": case["classification"],
        "affected_records": case["evidence_ids"],
        "excluded_receipts": case.get("excluded_matched_receipts", []),
        "anticipated_effect": "Creates an internal sandbox follow-up case with a DRAFT reminder (not sent). "
                              "No settlement status, balance or bank account is changed.",
        "draft_text": draft_text(analysis, case),
        "simulated": True,
        "origin": origin,
    }
    action_id = "ACT-" + uuid.uuid4().hex[:8].upper()
    db.execute(
        "INSERT INTO actions (action_id, action_type, case_id, target, amount, payload, status, proposed_by,"
        " proposed_at, prev_case_status) VALUES (?,?,?,?,?,?,?,?,?,?)",
        (action_id, action_type, case_id, payload["target"], payload["amount"], json.dumps(payload),
         "proposed", proposed_by, db.now(), case["status"]),
    )
    db.execute("UPDATE cases SET status = 'awaiting_approval', updated_at = ? WHERE case_id = ?", (db.now(), case_id))
    db.audit(proposed_by, proposer_role, "action_proposed", "action", action_id, "awaiting_approval",
             evidence_ids=case["evidence_ids"],
             details={"case_id": case_id, "type": action_type, "target": payload["target"],
                      "amount": payload["amount"], "origin": origin})
    return _row(action_id)


def _check_approver(action: dict | None, action_id: str, actor: str, role: str, verb: str) -> dict:
    if action is None:
        raise ActionError(f"unknown action {action_id}", 404)
    if role not in config.APPROVER_ROLES:
        db.audit(actor, role, f"{verb}_denied", "action", action_id, "denied",
                 details={"reason": f"role '{role}' may not {verb} actions; owner role required"})
        raise ActionError(f"role '{role}' is not permitted to {verb} actions (owner required)", 403)
    if actor == action["proposed_by"]:
        db.audit(actor, role, f"{verb}_denied", "action", action_id, "denied",
                 details={"reason": "proposer cannot decide on its own proposal"})
        raise ActionError("the proposer cannot approve or reject its own proposal", 403)
    if action["status"] != "proposed":
        raise ActionError(f"action is already {action['status']}", 409)
    return action


def approve(analysis: Analysis, action_id: str, actor: str, role: str, note: str = "") -> dict:
    action = _check_approver(_row(action_id), action_id, actor, role, "approve")
    ts = db.now()
    db.execute("UPDATE actions SET status='approved', decided_by=?, decided_role=?, decided_at=?, decision_note=?"
               " WHERE action_id=?", (actor, role, ts, note, action_id))
    db.audit(actor, role, "action_approved", "action", action_id, "approved",
             evidence_ids=action["payload"]["affected_records"], details={"note": note})
    return _execute(analysis, action_id)


def _execute(analysis: Analysis, action_id: str) -> dict:
    action = _row(action_id)
    try:
        followup_id = "FUP-" + uuid.uuid4().hex[:6].upper()
        db.execute(
            "INSERT INTO followups (followup_id, action_id, case_id, courier, amount, draft_text, status, created_at)"
            " VALUES (?,?,?,?,?,?,?,?)",
            (followup_id, action_id, action["case_id"], action["target"], action["amount"],
             action["payload"]["draft_text"], "draft_not_sent", db.now()),
        )
        result = {"followup_id": followup_id, "status": "draft_not_sent",
                  "message": f"Sandbox follow-up case {followup_id} created for BDT {action['amount']:,}. "
                             "Reminder saved as a DRAFT - it has NOT been sent to the courier.",
                  "simulated": True}
        db.execute("UPDATE actions SET status='executed', executed_at=?, result=? WHERE action_id=?",
                   (db.now(), json.dumps(result), action_id))
        db.execute("UPDATE cases SET status='action_prepared', updated_at=? WHERE case_id=?",
                   (db.now(), action["case_id"]))
        db.audit("veriflow-sandbox", "system", "action_executed", "action", action_id, "executed_in_sandbox",
                 evidence_ids=action["payload"]["affected_records"], details=result)
    except Exception as exc:  # pragma: no cover - defensive
        db.execute("UPDATE actions SET status='failed', result=? WHERE action_id=?",
                   (json.dumps({"error": str(exc)}), action_id))
        db.audit("veriflow-sandbox", "system", "action_failed", "action", action_id, "failed",
                 details={"error": str(exc)})
    return _row(action_id)


def reject(action_id: str, actor: str, role: str, note: str = "") -> dict:
    action = _check_approver(_row(action_id), action_id, actor, role, "reject")
    db.execute("UPDATE actions SET status='rejected', decided_by=?, decided_role=?, decided_at=?, decision_note=?"
               " WHERE action_id=?", (actor, role, db.now(), note, action_id))
    db.execute("UPDATE cases SET status=?, updated_at=? WHERE case_id=?",
               (action["prev_case_status"], db.now(), action["case_id"]))
    db.audit(actor, role, "action_rejected", "action", action_id, "rejected_no_side_effects",
             evidence_ids=action["payload"]["affected_records"], details={"note": note})
    return _row(action_id)
