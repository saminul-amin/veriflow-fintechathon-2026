# VeriFlow — Technical Documentation

**Project:** VeriFlow — Evidence-Verified Financial Agent for Cash-on-Delivery SMEs
**Competition:** 2026 Shenzhen FinTechathon, International Track, Topic E (SME Finance Copilot)
**Version:** 1.0 (submission build, 20 October 2026)
**Data:** all datasets are SYNTHETIC; all actions are simulated in a sandbox.

---

## 1. Purpose

A cash-on-delivery (COD) merchant sees sales on the order platform, but the cash arrives through several hands: the courier collects it, deducts fees, issues a settlement statement and finally remits to the bank. VeriFlow joins those four evidence trails to answer four questions:

1. How much money has actually arrived?
2. What is still owed, and by whom?
3. Can upcoming obligations be covered?
4. What can safely be done next?

An AI agent then turns the findings into an approved, auditable sandbox action. The design principle is: **numbers are computed deterministically; the AI explains and proposes; a human approves.**

## 2. System architecture

```
                         ┌───────────────────────────────────────────────┐
  Browser (static/       │                 FastAPI  (app/main.py)         │
  index.html, vanilla JS)│  X-Role / X-Actor headers → role check        │
  ─ Overview & waterfall │                                               │
  ─ Cash outlook         │   ┌──────────┐   ┌─────────────┐   ┌────────┐ │
  ─ Financing table  ◄──►│   │ load.py  │──►│ reconcile.py│──►│cashflow│ │
  ─ Cases + evidence     │   │ validate │   │ match, cases│   │  .py   │ │
  ─ Agent chat           │   └────┬─────┘   └──────┬──────┘   └───┬────┘ │
  ─ Proposal card        │        │ security.py    │              │      │
  ─ Audit trail          │        │ (scan text)    ▼              ▼      │
                         │        │          ┌──────────┐   ┌──────────┐ │
                         │        └─────────►│ state.py │◄──│financing │ │
                         │                   │ Analysis │   │   .py    │ │
                         │                   └────┬─────┘   └──────────┘ │
                         │        ┌───────────────┼───────────────┐      │
                         │        ▼               ▼               ▼      │
                         │   ┌─────────┐    ┌──────────┐    ┌──────────┐ │
                         │   │agent.py │───►│actions.py│───►│  db.py   │ │
                         │   │Claude / │    │state     │    │ SQLite + │ │
                         │   │fallback │    │machine   │    │hash-chain│ │
                         │   │+ guards │    └──────────┘    │  audit   │ │
                         │   └────┬────┘                    └──────────┘ │
                         └────────┼──────────────────────────────────────┘
                                  ▼ (optional, only if ANTHROPIC_API_KEY set)
                          Anthropic Messages API (claude-opus-5-5)
```

**Stack:** Python 3.11, FastAPI, SQLite, a single HTML page with no build step and no external assets, pytest. Start it with one command: `uvicorn app.main:app`.

**State separation:**
- Source evidence (CSV rows) is held read-only in memory and is never written back.
- SQLite holds only derived workflow state (case status, proposed actions, sandbox follow-ups) and the append-only audit log.

## 3. Data model and flow

| Dataset | Key fields | Role in the pipeline |
|---|---|---|
| `orders.csv` | order_id, amount, status (shipped/cancelled) | Placed-order value |
| `deliveries.csv` | delivery_id, order_id, status (delivered/returned), cod_collected, **note** (free text) | Delivered vs returned; COD collected |
| `settlements.csv` | settlement_id, delivery_ids, gross_collected, fees, net_payable, due_date, courier_status | What the courier owes, net of documented fees |
| `bank_receipts.csv` | receipt_id, date, amount, reference | Independent proof that money arrived |
| `obligations.csv` | obligation_id, amount, due_date, status | Near-term outflows |
| `financing_offers.csv` | offer_id, min/max, advance %, term, rate type, fees | Sample financing terms |
| `scenario.json` | as_of date, outlook window, currency, cash basis | Fixed evaluation date for reproducibility |

**Intake (`load.py`):**
- Required columns are checked per file, and a file missing any is rejected.
- Each row is validated: required values present, whole-number BDT amounts, ISO dates, enumerated statuses, unique ids.
- Invalid rows are **excluded and reported** (e.g. `OBL-006` with amount `TBD`), never repaired.
- Each accepted record carries `_source = "file.csv:line"`.
- Each file's SHA-256 is recorded in the audit log, so the exact evidence analysed can be proven later.

## 4. Core algorithm (`reconcile.py`)

1. **Order classification.**
   - `cancelled` if the order status is cancelled.
   - Otherwise the latest delivery status (`delivered` / `returned` / `in_transit`).
   - `no_delivery_record` if there is none.
   - Placed = Σ all orders. Each outcome total is computed separately, and a check asserts that the parts sum to the whole.
2. **Delivery → settlement.**
   - Each delivered parcel may appear on at most one settlement statement. A second claim is flagged as `duplicate_delivery_reference`.
   - A statement's gross must equal Σ COD of its deliveries (`gross_mismatch`), and gross − fees must equal net payable (`net_arithmetic_mismatch`).
   - Delivered parcels on no statement are reported as `delivered_not_on_statement`.
3. **Settlement → bank receipt (one-to-one).**
   - For each settlement, the first *unused* receipt with the same reference **and** equal amount is matched and marked used, so a receipt can never satisfy two settlements.
   - Same reference with a different amount gives `amount_mismatch`.
   - A receipt identical to an already-matched one (same reference, amount and date) is a `duplicate` and is excluded from confirmed cash.
   - Any other receipt is `unapplied`.
4. **Receivable status.** An unmatched settlement is:
   - `overdue` only if its evidenced `due_date` is earlier than the as-of date;
   - `pending` if the due date is in the future;
   - `unresolved` if no due date exists.
   - A courier status of "remitted" without a bank receipt is reported as an unverified claim, never as cash.
5. **Waterfall.** placed → −cancelled → −returned → delivered → −fees → expected net → −bank-confirmed → unconfirmed receivable. Every stage stores its formula and input ids. Invariant checks: `placed_equals_parts`, `outstanding_equals_open_settlements`, `no_receipt_matched_twice`.
6. **Cases.** Every discrepancy becomes an investigation case with:
   - title, amount, classification (*confirmed discrepancy / data-quality finding / security notice / missing information*);
   - evidence ids, the receipts checked and the receipts already matched (excluded from any claim);
   - an explicit uncertainty list and a transparent priority: `score = amount/1,000 + 2 × days overdue`, labelled High if amount ≥ 20,000 or ≥ 3 days overdue.
   - Wording rule: an overdue receivable is "not evidence of fraud or loss".

**Scenario A result:** 500,000 → 100,000 → 60,000 → 340,000 → 18,000 → 322,000 → 280,000 → **42,000** (`SET-004`, due 2026-10-15, overdue by 5 days). `BNK-004` is a duplicate of `BNK-003` and is counted once.

## 5. Cash-flow outlook and financing

**`cashflow.py`**
- Confirmed cash = Σ de-duplicated bank receipts (the basis is stated in `scenario.json`).
- Expected inflows = open settlements, each with its assumption.
- Obligations = unpaid items due within the window (as-of + 7 days). Paid items, items beyond the window, items with no due date and unreadable rows are listed separately as exclusions or limitations.
- Conservative case = confirmed − obligations. Expected case = conservative + expected inflows.
- An alert fires when the conservative case is below zero, and is escalated if the expected case is also below zero.
- Confirmed and expected values are never summed into a headline number.

**`financing.py`**
- Each sample offer is evaluated for the conservative gap:
  - borrow = max(gap, product minimum), capped at the product maximum or at advance % × verified receivable;
  - interest is flat or monthly × term; processing fees are flat or a percentage;
  - the result is a total cost and total repayment, with a fit of `covers_gap`, `covers_gap_overborrow` or `cannot_cover`.
- The lowest-cost covering option is labelled *"appears to fit — not a credit approval"*.
- With no gap, the result is "No financing needed". With no covering option, `no_suitable_option` is set.
- Scenario B (gap 20,000): FIN-A costs 1,000 to repay 21,000 over 30 days. FIN-B costs 3,200 and requires borrowing 50,000 (over-borrowing 30,000). The comparison also notes that collecting the 42,000 receivable in time would close the gap at no cost.

## 6. Agent design (`agent.py`)

**Input:**
- A compact JSON of *verified results* (waterfall, settlements, receipts, cases, cash outlook, financing).
- A separate `<untrusted_evidence_text>` block holding delivery notes. Flagged notes are replaced by `[WITHHELD …]`, and all notes are HTML-escaped and truncated.

**Engines:**
- **Claude** (`claude-opus-5-5`):
  - structured JSON output (`output_config.format` with a JSON schema) at low effort;
  - server-side refusal fallback enabled;
  - a system prompt with nine non-negotiable rules (only provided figures, cite ids, no fraud language, never follow data instructions, one allowlisted action).
- **Rule-based fallback:** intent classification (why / priority / cash split / afford / financing / prepare / injection / summary) with templated answers built from the same verified results. It is used when no key is set or Claude fails.

**Output schema (both engines):** `answer`, `evidence_ids`, `uncertainties`, `propose_followup_case_id`. The API adds `kind` (answer / proposed_action / refusal), `mode` and `guard_notes`.

**Post-generation guards (applied to both engines):**
1. Evidence ids not present in the loaded evidence are dropped.
2. **Numeric grounding:** every money-like figure in the answer must equal a computed value. Otherwise the answer is replaced with the deterministic explanation and the substitution is logged.
3. **Prohibited claims** (fraud/theft wording, or claims to have marked, sent, paid, transferred or approved anything) also cause replacement.
4. A proposal is accepted only for an *actionable* case of an *allowlisted* type. Target and amount are filled from computed settlement data, never from model text.

## 7. Action workflow (`actions.py`)

```
proposed ──approve (owner, ≠ proposer)──► approved ──► executed (sandbox follow-up FUP-…, draft_not_sent)
    │                                                     └─(error)─► failed
    └──reject (owner, ≠ proposer)──► rejected  (case status restored, no follow-up created)
```

**The proposal card shows:**
- target and amount, with their source rows (`SET-004.net_payable = 44,000 − 2,000`);
- the justification and the affected records;
- the receipts already received, which are excluded from the claim;
- the anticipated effect, and a preview of the draft text marked **"DRAFT - NOT SENT"**.

Execution inserts one row into `followups` and changes the case status to `action_prepared`. Nothing else changes: no settlement status, balance or account.

## 8. Security design (summary)

Full detail is in `SECURITY_SELF_ASSESSMENT.md`.

- **Roles and duties:** two roles with least privilege (analyst = read, ask, propose; owner = approve/reject), plus separation of duties (a proposer can never decide its own proposal).
- **Untrusted input:** an untrusted-input boundary (detection, withholding, logging) and capability removal: no endpoint or action type exists that could mark a payment settled, change an account or move money.
- **Model output:** guards on model output (§6).
- **Evidence integrity:** source evidence is read-only, and each file's SHA-256 is recorded at load.
- **Audit:** an append-only audit log in which each entry stores `hash = SHA-256(prev_hash ‖ canonical entry)`. `/audit/verify` recomputes the chain, and a test proves that editing one row is detected.
- **Disclosure:** synthetic data is disclosed on every screen.

## 9. Testing and evidence

`pytest` contains 23 tests: the seven acceptance tests from the plan plus supporting cases.

| # | Property verified |
|---|---|
| 1 | Scenario A waterfall equals the expected figures, and every stage lists its inputs |
| 2 | No bank receipt is matched twice; a duplicate row is counted once; one receipt cannot settle two statements |
| 3 | Overdue only with a passed, evidenced due date (no due date → unresolved; future → pending) |
| 4 | Analyst approval → 403 and audited; owner approval executes; the agent cannot approve its own proposal; unknown role → 400 |
| 5 | Rejection leaves no follow-up, restores case status, leaves reconciliation unchanged, and cannot be approved later |
| 6 | Injected note detected, withheld from the prompt, logged as ignored; status unchanged; the agent refuses; the action target comes from settlement data; disallowed action types blocked |
| 7 | Scenario B: −20,000 conservative, alert, FIN-A 1,000 vs FIN-B 3,200, FIN-A recommended "not a credit approval"; no-financing and no-suitable-option paths |
| + | Malformed row excluded and disclosed; audit tamper detection; agent answers cite known ids with no unverified numbers; simulated malicious Claude output is neutralised; Claude outage falls back |

`scripts/run_sandbox_demo.py` executes every journey through the HTTP API and writes the execution evidence: `logs/sandbox_run.log` and `logs/audit_export.json`.

## 10. Deployment

```bash
pip install -r requirements.txt
python -m uvicorn app.main:app --host 0.0.0.0 --port 8000
```

| Variable | Purpose |
|---|---|
| `ANTHROPIC_API_KEY` | Optional; enables the Claude agent |
| `VERIFLOW_MODEL` | Override the default `claude-opus-5-5` |
| `VERIFLOW_AGENT=fallback` | Force the offline agent |
| `VERIFLOW_SCENARIO=A\|B` | Scenario loaded at start |
| `VERIFLOW_DB` | SQLite path |

No other services are required.

## 11. Known limitations and next steps

**Limitations:**
- Header-based roles instead of authentication.
- Exact reference + amount matching (no fuzzy or partial matching).
- Single currency.
- CSV intake only (no OCR or live APIs).
- The outlook depends on recorded obligations.

**Next steps:**
- Authenticated users and an approval matrix.
- Partial-settlement and multi-reference matching with explicit confidence labels.
- Delay what-if sliders.
- Exportable evidence bundle.
- Authorised courier and bank integrations behind the same approval gate.

## Appendix — Screenshots of the running prototype

*Captured from the live application (SYNTHETIC data). All screenshots are in `docs/screenshots/`.*

**Financial overview and reconciliation waterfall (Scenario A)**

![Overview](screenshots/01_overview.png)

**Agent proposal awaiting owner approval (draft marked NOT SENT)**

![Proposal](screenshots/06_proposal.png)

**Injected instruction flagged in the evidence drawer**

![Injection](screenshots/10_injection_evidence.png)

**Scenario B: cash alert and sample financing comparison**

![Cash alert](screenshots/11_cash_alert.png)

![Financing](screenshots/12_financing.png)
