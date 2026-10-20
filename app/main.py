"""VeriFlow HTTP API (FastAPI). Run: uvicorn app.main:app --port 8000

Roles are passed in the X-Role header ('analyst' = read-only analysis,
'owner' = may approve/reject actions) and the actor name in X-Actor.
This is a sandbox demo: role headers stand in for real authentication.
"""
from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI, Header, HTTPException
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel

from . import actions, agent, config, db, state
from .load import LoadError, SCHEMAS


@asynccontextmanager
async def lifespan(_app: FastAPI):
    db.init()
    state.load(config.default_scenario())
    yield


app = FastAPI(title="VeriFlow (SYNTHETIC sandbox)", version="1.0.0", lifespan=lifespan)


def who(x_role: str | None, x_actor: str | None) -> tuple[str, str]:
    role = (x_role or "analyst").strip().lower()
    if role not in config.ROLES:
        raise HTTPException(400, f"unknown role '{role}'; use one of {', '.join(config.ROLES)}")
    actor = (x_actor or f"{role}-demo-user").strip()[:60]
    if actor.startswith("veriflow-"):
        raise HTTPException(400, "reserved actor name")
    return actor, role


@app.exception_handler(actions.ActionError)
async def action_error(_req, exc: actions.ActionError):
    return JSONResponse(status_code=exc.status_code, content={"detail": str(exc)})


class LoadRequest(BaseModel):
    scenario: str = "A"


class AskRequest(BaseModel):
    question: str


class ProposeRequest(BaseModel):
    case_id: str
    action_type: str = "create_courier_followup_case"


class DecisionRequest(BaseModel):
    note: str = ""


@app.get("/")
def index():
    return FileResponse(config.STATIC_DIR / "index.html")


@app.get("/status")
def status():
    a = state.current()
    return {"scenario": a.scenario, "label": a.dataset.meta.get("label"), "synthetic": True,
            "agent_mode": config.agent_mode(), "model": config.claude_model() if config.agent_mode() == "claude" else "rule-based",
            "as_of": a.recon["as_of"], "roles": config.ROLES}


@app.post("/load")
def load(req: LoadRequest, x_role: str | None = Header(None), x_actor: str | None = Header(None)):
    actor, role = who(x_role, x_actor)
    try:
        a = state.load(req.scenario, actor, role)
    except (LoadError, ValueError) as exc:
        raise HTTPException(400, str(exc))
    return {"scenario": a.scenario, "meta": a.dataset.meta, "files": a.dataset.files,
            "malformed": a.dataset.malformed, "security_flags": a.flags,
            "checks": a.recon["checks"]}


@app.get("/overview")
def overview():
    a = state.current()
    cases = a.cases_with_status()
    return {
        "scenario": a.scenario, "meta": a.dataset.meta, "files": a.dataset.files,
        "waterfall": a.recon["waterfall"], "totals": a.recon["totals"], "checks": a.recon["checks"],
        "confirmed_cash": a.cash["confirmed_cash"], "expected_inflows": a.cash["expected_inflows"],
        "alert": a.cash["alert"],
        "open_cases": sum(1 for c in cases if c["actionable"] and c["status"] != "action_prepared"),
        "security_flags": len(a.flags), "malformed_rows": len(a.dataset.malformed),
    }


@app.get("/records/{kind}")
def records(kind: str):
    a = state.current()
    if kind not in SCHEMAS:
        raise HTTPException(404, f"unknown dataset {kind}")
    return {"kind": kind, "label": SCHEMAS[kind]["label"], "records": a.dataset.records[kind],
            "malformed": [m for m in a.dataset.malformed if m["kind"] == kind]}


@app.get("/evidence/{record_id}")
def evidence(record_id: str):
    a = state.current()
    rec = a.dataset.index().get(record_id)
    if rec is None:
        c = a.case(record_id)
        if c:
            return {"kind": "case", **c}
        raise HTTPException(404, f"no evidence record {record_id}")
    flag = next((f for f in a.flags if f["record_id"] == record_id), None)
    return {**rec, "security_flag": flag}


@app.get("/reconciliation")
def reconciliation():
    a = state.current()
    return {k: a.recon[k] for k in ("as_of", "totals", "settlements", "receipts", "orders",
                                    "unsettled_deliveries", "issues", "checks")}


@app.get("/cases")
def cases():
    return state.current().cases_with_status()


@app.get("/cases/{case_id}")
def case(case_id: str):
    a = state.current()
    c = a.case(case_id)
    if c is None:
        raise HTTPException(404, f"unknown case {case_id}")
    idx = a.dataset.index()
    c["evidence"] = [idx[e] for e in c["evidence_ids"] if e in idx]
    c["actions"] = [x for x in actions.list_actions() if x["case_id"] == case_id]
    return c


@app.get("/cashflow")
def cashflow():
    return state.current().cash


@app.get("/financing")
def financing():
    return state.current().finance


@app.post("/agent/ask")
def ask(req: AskRequest, x_role: str | None = Header(None), x_actor: str | None = Header(None)):
    actor, role = who(x_role, x_actor)
    return agent.ask(state.current(), req.question, actor, role)


@app.get("/actions")
def list_actions():
    return {"actions": actions.list_actions(), "followups": actions.followups()}


@app.post("/actions")
def propose(req: ProposeRequest, x_role: str | None = Header(None), x_actor: str | None = Header(None)):
    actor, role = who(x_role, x_actor)
    return actions.propose(state.current(), req.case_id, actor, role, req.action_type, origin="user")


@app.post("/actions/{action_id}/approve")
def approve(action_id: str, req: DecisionRequest | None = None,
            x_role: str | None = Header(None), x_actor: str | None = Header(None)):
    actor, role = who(x_role, x_actor)
    return actions.approve(state.current(), action_id, actor, role, (req.note if req else ""))


@app.post("/actions/{action_id}/reject")
def reject(action_id: str, req: DecisionRequest | None = None,
           x_role: str | None = Header(None), x_actor: str | None = Header(None)):
    actor, role = who(x_role, x_actor)
    return actions.reject(action_id, actor, role, (req.note if req else ""))


@app.get("/audit")
def audit(limit: int = 200):
    return {"entries": db.audit_entries(limit), "chain": db.verify_audit_chain()}


@app.get("/audit/verify")
def audit_verify():
    return db.verify_audit_chain()
