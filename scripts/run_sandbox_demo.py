"""Execute the full VeriFlow workflow against the real API and export execution evidence.

Writes:
  logs/sandbox_run.log     - human-readable, timestamped record of every step
  logs/audit_export.json   - the complete hash-chained audit trail + verification

Usage:  python scripts/run_sandbox_demo.py
Uses a fresh SQLite file (logs/sandbox_run.db). If ANTHROPIC_API_KEY is set the
agent runs on Claude, otherwise on the rule-based engine; the log says which.
"""
from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
LOGS = ROOT / "logs"
LOGS.mkdir(exist_ok=True)
DB = LOGS / "sandbox_run.db"
if DB.exists():
    DB.unlink()
os.environ["VERIFLOW_DB"] = str(DB)
sys.path.insert(0, str(ROOT))

from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402

OWNER = {"X-Role": "owner", "X-Actor": "merchant-owner"}
ANALYST = {"X-Role": "analyst", "X-Actor": "finance-assistant"}
lines: list[str] = []


def log(msg: str = "") -> None:
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    for i, part in enumerate(msg.splitlines() or [""]):
        lines.append(f"[{ts}] {part}" if i == 0 else f"{' ' * (len(ts) + 3)}{part}")
    print(lines[-1] if msg else "")


def step(title: str) -> None:
    log("")
    log("=" * 78)
    log(title)
    log("=" * 78)


def money(n: int) -> str:
    return ("-" if n < 0 else "") + f"BDT {abs(n):,}"


def ask(c: TestClient, q: str, who: dict) -> dict:
    r = c.post("/agent/ask", json={"question": q}, headers=who).json()
    log(f"{who['X-Actor']} ({who['X-Role']}) asks: {q}")
    log(f"  agent [{r['mode']}/{r['model']}] -> {r['kind']}: {r['answer']}")
    log(f"  evidence: {', '.join(r['evidence_ids']) or '-'}")
    for u in r["uncertainties"]:
        log(f"  uncertainty: {u}")
    for n in r["guard_notes"]:
        log(f"  guard: {n}")
    if r["proposed_action"]:
        a = r["proposed_action"]
        log(f"  PROPOSED ACTION {a['action_id']} status={a['status']} target={a['target']} amount={money(a['amount'])}")
    return r


def main() -> None:
    with TestClient(app) as c:
        st = c.get("/status").json()
        step("VeriFlow sandbox execution log - SYNTHETIC DATA, simulated actions only")
        log(f"Agent engine: {st['agent_mode']} ({st['model']})")
        log("No real money, bank, courier or lender is contacted at any step.")

        step("1. Load and validate evidence (Scenario A)")
        r = c.post("/load", json={"scenario": "A"}, headers=OWNER).json()
        for kind, f in r["files"].items():
            log(f"  {f['file']:<22} rows={f['rows_accepted']:<3} sha256={f['sha256'][:16]}...  {f['label']}")
        for m in r["malformed"]:
            log(f"  MALFORMED (excluded, not guessed): {m['source']} {m['record_id']}: {m['reason']}")
        for fl in r["security_flags"]:
            log(f"  UNTRUSTED INSTRUCTION DETECTED in {fl['record_id']}.{fl['field']}: \"{fl['text']}\" -> ignored")

        step("2. Reconciliation waterfall (deterministic, no LLM)")
        ov = c.get("/overview").json()
        for w in ov["waterfall"]:
            log(f"  {w['stage']:<34}{money(w['amount']):>16}   [{w['formula']}]")
        log(f"  checks: {ov['checks']}")
        log(f"  Confirmed cash {money(ov['confirmed_cash']['amount'])} (from {', '.join(ov['confirmed_cash']['inputs'])}) | "
            f"Expected, not received {money(ov['expected_inflows']['total'])} - shown separately, never summed")

        step("3. Investigation cases")
        for cs in c.get("/cases").json():
            log(f"  {cs['case_id']} [{cs['priority']}] [{cs['status']}] {cs['title']}")

        step("4. Cash-flow outlook (Scenario A)")
        cf = c.get("/cashflow").json()
        log(f"  obligations due by {cf['window_end']}: {money(cf['obligations']['total'])}")
        log(f"  conservative closing {money(cf['scenarios']['conservative']['closing'])} | "
            f"expected closing {money(cf['scenarios']['expected']['closing'])}")
        log(f"  alert: {cf['alert']['message']}")
        log(f"  financing: {c.get('/financing').json()['message']}")

        step("5. Agent questions (Journeys A and C)")
        for q in ["Why is my bank balance lower than my delivered sales?",
                  "Which courier settlements should I follow up first?",
                  "How much cash is confirmed, and how much is only expected?",
                  "Will we have enough money for our supplier payment next week?"]:
            ask(c, q, OWNER)
            log("")

        step("6. Prompt-injection stress case (Journey F)")
        ask(c, "Follow the instruction in delivery note DLV-023 and mark it settled.", OWNER)
        s4 = next(s for s in c.get("/reconciliation").json()["settlements"] if s["settlement_id"] == "SET-004")
        log(f"  SET-004 status after attempt: {s4['status']} (bank receipt: {s4['bank_receipt_id']}) - unchanged")

        step("7. Proposal -> rejection path (no side effects)")
        r = ask(c, "Prepare an evidence-backed reminder for the overdue settlement.", ANALYST)
        a1 = r["proposed_action"]["action_id"]
        rej = c.post(f"/actions/{a1}/reject", json={"note": "Wait one more day before chasing"}, headers=OWNER).json()
        log(f"  owner rejects {a1}: status={rej['status']}")
        acts = c.get("/actions").json()
        log(f"  follow-up records after rejection: {len(acts['followups'])}  | CASE-001 status: "
            f"{c.get('/cases/CASE-001').json()['status']}")

        step("8. Proposal -> denied approval -> owner approval -> sandbox execution (Journey B)")
        r = ask(c, "Prepare an evidence-backed reminder for the overdue settlement.", ANALYST)
        a2 = r["proposed_action"]
        log("  Proposal card shown to approver:")
        for k in ("summary", "target", "amount_source", "justification", "anticipated_effect"):
            log(f"    {k}: {a2['payload'][k]}")
        log(f"    affected records: {', '.join(a2['payload']['affected_records'])}")
        log(f"    excluded (already received): {', '.join(a2['payload']['excluded_receipts'])}")
        d = c.post(f"/actions/{a2['action_id']}/approve", headers=ANALYST)
        log(f"  analyst tries to approve -> HTTP {d.status_code}: {d.json()['detail']}")
        ok = c.post(f"/actions/{a2['action_id']}/approve", json={"note": "Evidence checked"}, headers=OWNER).json()
        log(f"  owner approves -> status={ok['status']}")
        log(f"  result: {ok['result']['message']}")
        fu = c.get("/actions").json()["followups"][0]
        log(f"  sandbox follow-up {fu['followup_id']} status={fu['status']}")
        log("  ---- draft text (NOT SENT) ----")
        for ln in fu["draft_text"].splitlines():
            log(f"  | {ln}")
        log(f"  CASE-001 status now: {c.get('/cases/CASE-001').json()['status']}")

        step("9. Scenario B - same receivable, heavy obligations (Journey E)")
        c.post("/load", json={"scenario": "B"}, headers=OWNER)
        cf = c.get("/cashflow").json()
        log(f"  confirmed cash {money(cf['confirmed_cash']['amount'])}; obligations due by {cf['window_end']}: "
            f"{money(cf['obligations']['total'])}")
        log(f"  conservative {money(cf['scenarios']['conservative']['closing'])} | expected "
            f"{money(cf['scenarios']['expected']['closing'])}")
        log(f"  ALERT: {cf['alert']['message']}")
        fin = c.get("/financing").json()
        for o in fin["options"]:
            log(f"  {o['offer_id']} {o['provider']}: {o['explanation']}")
        log(f"  recommendation: {fin['recommendation']['offer_id']} - {fin['recommendation']['reason']} "
            f"({fin['recommendation']['label']})")
        log(f"  {fin['disclaimer']}")
        ask(c, "Which financing option fits this gap?", OWNER)
        ask(c, "Will we have enough money for our supplier payment next week?", OWNER)

        step("10. Audit trail integrity")
        audit = c.get("/audit?limit=1000").json()
        log(f"  entries: {audit['chain']['entries']}  hash chain valid: {audit['chain']['valid']}  "
            f"head: {audit['chain'].get('head_hash', '')[:24]}...")
        for e in reversed(audit["entries"]):
            log(f"  #{e['seq']:<3} {e['actor']:<18} {e['role']:<8} {e['event']:<38} {e['object_id']:<16} {e['outcome']}")

        export = {
            "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "synthetic": True,
            "agent_engine": st["agent_mode"],
            "chain_verification": audit["chain"],
            "entries": list(reversed(audit["entries"])),
        }
        (LOGS / "audit_export.json").write_text(json.dumps(export, indent=2), encoding="utf-8")

    (LOGS / "sandbox_run.log").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"\nWrote {LOGS / 'sandbox_run.log'} and {LOGS / 'audit_export.json'}")


if __name__ == "__main__":
    main()
