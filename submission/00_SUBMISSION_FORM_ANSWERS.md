# VeriFlow — Ready-to-paste answers for the submission form

Copy each block into the matching form field. Only the fields marked **YOU FILL** need your input: personal and team details I don't have, and links that exist only after you upload.

---

## Team and contact — YOU FILL

| Field | Value |
|---|---|
| Team name | **Team VeriFlow** |
| Team members (2–5) | YOU FILL — full name, university, programme, year, nationality, email for each |
| Team leader / contact person | YOU FILL |
| Contact email / phone | YOU FILL |
| GitHub repository link | YOU FILL after pushing (see "Push to GitHub" below) |
| Demo video link (if uploading instead of attaching) | YOU FILL (unlisted YouTube or Google Drive "anyone with the link") |

## Competition details

| Field | Value |
|---|---|
| Competition | 2026 Shenzhen International FinTech Competition (FinTechathon) — International Track |
| Theme | AI as a Financial Participant |
| Topic | **Topic E — SME Finance Copilot** |
| Project name | **VeriFlow** |
| Full title | VeriFlow — Evidence-Verified Financial Agent for Cash-on-Delivery SMEs |
| Tagline | From orders to evidence. From evidence to action. |
| On-chain / non-on-chain | Non-on-chain (sandbox / simulated-account execution) |
| Language of materials | English |

## Project summary (≈50 words)

VeriFlow is an AI finance copilot for small online businesses. It reconciles customer orders, courier records, settlement statements and bank receipts to separate reported sales from verified cash. Its agent investigates discrepancies, forecasts cash-flow pressure, compares financing options, and proposes evidence-backed actions through an approval-controlled, auditable sandbox workflow.

## Project description (≈150 words)

Cash-on-delivery merchants see strong sales while cash stays short. Cancellations, returns, courier fees and late settlements sit in four separate systems. VeriFlow joins the order, delivery, settlement and bank evidence:
- A deterministic engine reconciles them and explains every figure with its source records. In the demo it traces BDT 500,000 of orders down to a BDT 42,000 overdue courier settlement, with a duplicate bank row counted once.
- It keeps confirmed cash apart from expected inflows and raises a 7-day cash alert only when the evidence supports one.
- It compares sample financing offers on total cost, never claiming credit approval.

An AI agent (Claude, or an offline rule-based engine with the same output format) answers plain-English questions with cited evidence and proposes one concrete action: a courier follow-up case with a draft reminder. Only the owner can approve it. Execution happens in a sandbox, and every step goes into a SHA-256 hash-chained audit log. Instructions hidden in uploaded data are detected and ignored. All data is synthetic.

## Problem addressed

For COD e-commerce SMEs, "sales" are not spendable cash. The order platform, courier status, courier settlement statement and bank statement each describe a different stage of the same money. Owners without a finance team cannot see what is confirmed, what is owed and by whom, or whether next week's bills are covered. That leads to cash shortfalls and costly, uninformed borrowing.

## Solution and key features

1. **Evidence intake:** 6 datasets validated. Bad rows are flagged, never guessed. Every record keeps its source line, and each file's SHA-256 is logged.
2. **Deterministic reconciliation:** a placed → cancelled → returned → delivered → fees → expected → banked → outstanding waterfall. Bank receipts are matched one-to-one, duplicates are detected, and every figure lists its source records.
3. **Investigation cases:** ranked by transparent rules (amount and days overdue), with evidence and explicit uncertainty. They never use "fraud" language.
4. **Cash-flow outlook:** confirmed cash vs expected inflows, a conservative vs expected 7-day case, and an alert only when warranted.
5. **Financing comparison:** sample offers compared on total cost for the forecast gap, with "no financing needed" and "no suitable option" paths. Informational only.
6. **AI agent with real task ownership:** cited, plain-English answers. It proposes a courier follow-up, and the owner approves before a sandbox case and a draft reminder (never sent) are created.
7. **Security and audit:** role tiers, separation of duties, prompt-injection handling, guards on model output, and a hash-chained audit trail.

## Innovation and interaction

- **A closed, evidence-linked loop:** records → reconciliation → explainable investigation → liquidity assessment → permission-checked action → verifiable outcome.
- **Numbers are deterministic:** the LLM only explains and proposes. Every figure in an AI answer is checked against computed values, and the answer is replaced if it doesn't match.
- **Every answer is clickable down to the original evidence row,** and the interface labels each state: confirmed, estimated, unresolved, simulated.
- **The agent's action is meaningful but bounded:** the amount and target come from evidence, never from AI text.
- **Honest urgency:** Scenario A deliberately shows no alert; Scenario B shows a genuine shortfall.

## Security and compliance design

- **Permission tiers:**
  - Analyst: read, ask, propose. Attempting to approve returns HTTP 403 and is logged.
  - Owner: approve or reject.
  - Agent: proposes one allow-listed action and can never approve its own proposal.
- **Untrusted-input boundary:** instruction-like text in data is detected, withheld from the LLM and logged as ignored. Settlement status comes only from bank evidence.
- **Capability removal:** no function exists to mark payments settled, change accounts, move money or apply for credit.
- **Model-output guards:** unknown evidence ids are dropped. Invented figures and prohibited claims cause the answer to be replaced with the deterministic one.
- **Evidence and audit:** source evidence is read-only, files are hashed at load, and the audit log is append-only and SHA-256 hash-chained, so tampering is detected.
- **Disclosure:** synthetic data and simulated actions are labelled on every screen. Financing is labelled "not a credit approval".
- **Known risks:** 14 risks with mitigations and next steps are listed in the Security Self-Assessment, e.g. header-based roles instead of authentication, regex detection limits, and exact-reference matching.

## Technology stack

Python 3.11 · FastAPI · SQLite · single-page HTML/JS UI (no build step) · Anthropic Claude API (`claude-opus-5-5`, structured JSON output, optional) with an offline rule-based fallback · pytest. Deployment is one command: `pip install -r requirements.txt` then `python -m uvicorn app.main:app`.

## Evidence of completion

- 23 automated tests pass (`python -m pytest -q`).
- Sandbox execution log (`logs/sandbox_run.log`) and full audit export (`logs/audit_export.json`) from a real end-to-end run. 25 audit entries; hash chain verified.
- Demo video, 2 min 51 s, showing the complete loop.

## Data and licences

- **Data:** all synthetic, generated by `scripts/generate_data.py`. No real personal or financial data. No third-party datasets.
- **Third-party software:**
  - FastAPI (MIT)
  - Uvicorn (BSD-3)
  - Pydantic (MIT)
  - Anthropic Python SDK (MIT)
  - HTTPX (BSD-3)
  - pytest (MIT)

---

## Files to upload or attach (in this folder)

| # | Official item | File |
|---|---|---|
| 01 | Technical documentation | `01_VeriFlow_Technical_Documentation.pdf` |
| 02 | Presentation deck (≤ 10 min) | `02_VeriFlow_Presentation_Deck.pdf` (editable `.pptx` also included) |
| 03 | Demo video (optional, ≤ 5 min) | `03_VeriFlow_Demo_Video.mp4` (2:51, 5.5 MB, captioned) |
| 04 | Source code (README, deployment, tests) | `04_VeriFlow_Source_Code.zip` + GitHub link |
| 05 | Security self-assessment | `05_VeriFlow_Security_Self_Assessment.pdf` |
| 06 | Execution evidence (sandbox logs + video) | `06_VeriFlow_Execution_Evidence.zip` (logs, audit export, screenshots) + the video from item 03 |

## Push to GitHub (do this before filling the repo link)

```bash
gh repo create veriflow-fintechathon-2026 --public --source . --remote origin --push
```

If you don't use the GitHub CLI: create an empty repository on github.com, then run:

```bash
git remote add origin https://github.com/<your-username>/veriflow-fintechathon-2026.git
```

```bash
git push -u origin main
```

Open the link in a private browser window to confirm it is public.
