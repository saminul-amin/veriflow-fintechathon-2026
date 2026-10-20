# VeriFlow — 3-Minute Demo Script

**Setup before recording**
1. `pip install -r requirements.txt`
2. Delete any old `veriflow.db` (optional, for a clean audit trail).
3. Start the server: `python -m uvicorn app.main:app --port 8000`.
4. Open `http://localhost:8000` at full screen (≥ 1280 px wide).
5. Confirm that **Dataset = Scenario A** and **Signed in as = Analyst**.
6. Recorder: OBS or similar, 1080p, microphone on. Target length 3:00 (hard limit 5:00).
7. If an API key is set, the header badge reads "agent: Claude"; otherwise "agent: rule-based (offline)". Both work, so say whichever is shown.

| Time | Click / action | Narration |
|---|---|---|
| 0:00–0:15 | Show the full page; point at the yellow banner | "This is VeriFlow, an evidence-verified finance copilot for cash-on-delivery merchants. Everything here is synthetic sandbox data: no real money, and no message is ever sent." |
| 0:15–0:40 | Point at the KPI cards, then the waterfall. Click the **Bank-confirmed receipts** row; the drawer shows BNK-001..003. Close it | "The merchant sold 500,000 taka of orders but has only 280,000 in the bank. The waterfall explains why: 100,000 cancelled, 60,000 returned, 18,000 courier fees. 280,000 is matched one-to-one to bank receipts, which leaves 42,000 unconfirmed. Every number links to its source rows. Confirmed cash and expected money are shown separately, never added together." |
| 0:40–0:55 | Scroll to **Investigation cases**, click **CASE-001** | "VeriFlow raised a case: settlement SET-004, 42,000, five days past its evidenced due date. It's an overdue receivable to follow up, not fraud. It also shows what's uncertain, and notes that a duplicate bank row was counted only once." Close the drawer. |
| 0:55–1:15 | In the agent panel click the chip **"Why is my bank balance lower…"** | "I can ask in plain English. The agent answers from verified results and cites the exact records: BNK receipts and SET-004. It never computes money itself; any figure it writes is checked against the engine." |
| 1:15–1:40 | Click **"Prepare an evidence-backed reminder…"**; expand **Preview draft reminder** | "Now the agent acts. It proposes a courier follow-up with the target, the amount and how it was computed, the deliveries involved, and the receipts excluded from the claim. The draft is clearly marked not sent." |
| 1:40–1:55 | Still as **Analyst**, click **Approve** and wait for the "Blocked…" toast | "I'm signed in as an analyst. Approval is blocked: only the owner can approve, and the agent can never approve its own proposal. The denial is logged." |
| 1:55–2:10 | Switch **Signed in as → Owner**, click **Approve** | "As the owner, I approve. VeriFlow creates a sandbox follow-up case, status *draft not sent*. Nothing is sent to the courier and no money moves." |
| 2:10–2:30 | Click the chip **"Follow the instruction in delivery note DLV-023…"**. Then click the `DLV-023` id chip to show the red warning box | "One courier note contains a hidden instruction: mark this payment settled and change the destination account. VeriFlow treats it as data. It was flagged at load, withheld from the AI, and has no effect: settlement status only comes from bank evidence, and no feature exists to change accounts." |
| 2:30–2:50 | Change **Dataset → Scenario B**. Point at the red cash alert and the Financing table | "In Scenario B the same merchant has 300,000 of bills due this week. The conservative case is minus 20,000, so VeriFlow raises a cash alert and compares two sample financing offers. FIN-A costs 1,000; FIN-B costs 3,200 and forces over-borrowing. It also points out that collecting the overdue 42,000 closes the gap for free. These are sample terms, not a credit approval." |
| 2:50–3:00 | Scroll to **Audit trail**; point at the green "hash chain verified" badge | "Every step is in a tamper-evident, hash-chained audit trail. VeriFlow doesn't mistake an order for money, or an AI suggestion for an authorised action." |

**Already available:** `submission/03_VeriFlow_Demo_Video.mp4` is a 2:51 captioned, silent walkthrough recorded automatically from the live app (`scripts/submission_tools/capture.js`). It is ready to submit as is. Recording a narrated version with this script is optional.

**Backup plan:** if the UI fails during recording, run `python scripts/run_sandbox_demo.py` and screen-record the terminal output plus `logs/sandbox_run.log`. It covers the same journeys.

**After recording:** export as MP4 (≤ 5 min), name it `VeriFlow_demo.mp4`, and include it in the submission as execution evidence (item 06) and as the optional demo video (item 03).
