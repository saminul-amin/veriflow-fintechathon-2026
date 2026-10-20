# Submission email — DRAFT (team to review, complete and send)

All files referenced below are in the `submission/` folder. Form-field answers are in `submission/00_SUBMISSION_FORM_ANSWERS.md`.

**To:** wangyr@pbcsf.tsinghua.edu.cn
*(Before sending, confirm this is the authoritative address. The IEEE CIS Singapore page lists fintechathon@ican-x.com; see vision doc §15.3.)*
**Subject:** [FinTechathon 2026 International Track] Topic E Submission — Team VeriFlow — VeriFlow
**Send by:** 21:00 Bangladesh time / 23:00 Beijing time, 20 October 2026 (deadline 23:59 Beijing)

---

Dear FinTechathon Organizing Committee,

Please find our team's submission for the 2026 Shenzhen International FinTech Competition, International Track, **Topic E — SME Finance Copilot**.

**Project:** VeriFlow — Evidence-Verified Financial Agent for Cash-on-Delivery SMEs
**Team name:** Team VeriFlow
**Members:** `<Name — University — Programme>` (×2–5)
**Contact:** `<email, phone>`

VeriFlow reconciles orders, courier deliveries, settlement statements and bank receipts to separate reported sales from verified cash. Its AI agent investigates discrepancies, assesses near-term cash flow, compares sample financing options, and proposes evidence-backed actions. Every action is executed only after owner approval, in a sandbox, with a hash-chained audit trail. All data is synthetic, and all actions are simulated.

**Submission items**

| # | Item | Attached / link |
|---|---|---|
| 01 | Technical documentation | `01_VeriFlow_Technical_Documentation.pdf` |
| 02 | Presentation deck (≤ 10 min) | `02_VeriFlow_Presentation_Deck.pdf` (+ editable `.pptx`) |
| 03 | Demo video (optional, ≤ 5 min) | `03_VeriFlow_Demo_Video.mp4` (2:51) or `<link>` |
| 04 | Source code (README, deployment instructions, tests) | GitHub: `<repo URL>` · `04_VeriFlow_Source_Code.zip` |
| 05 | Security self-assessment | `05_VeriFlow_Security_Self_Assessment.pdf` |
| 06 | Execution evidence (sandbox logs + demo video) | `06_VeriFlow_Execution_Evidence.zip` (sandbox log, audit export, screenshots) + the video in item 03 |

To run: `pip install -r requirements.txt` then `python -m uvicorn app.main:app`, and open http://localhost:8000. Tests: `python -m pytest -q` (23 passing).

`<If registration was sent separately: "Our registration form was sent on <date/time>.">`

Thank you for your consideration. We are happy to provide anything further.

Kind regards,
`<Name>` on behalf of Team VeriFlow

---

**Checklist before pressing Send**
- [ ] Member names, contact and repo link filled in above
- [ ] GitHub repo is public, or the organiser has been invited; link tested in a private window
- [ ] The PDFs open, and the file names match the table
- [ ] Video plays and is ≤ 5 min (if it is over the attachment size limit, use a Drive/YouTube unlisted link)
- [ ] Zip contains the source without `veriflow.db`, `__pycache__` or `.venv`
- [ ] Keep the sent copy; check for a bounce within 30 minutes
