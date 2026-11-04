# KYC Onboarding Evidence System (YottaFlex AI challenge)

A small KYC (know-your-customer) evidence platform: a deterministic synthetic data generator, a
rules engine that finds evidence problems, a read-only REST API, and a 10-screen React dashboard.
Everything shown on screen comes from the real API over a real SQLite database. There is no mock data.

## What it does

* Generates **8,000 customers, 20,000 documents, 1,000 business profiles and 3,000 review cases**
  (plus owners, ownership links, risk ratings, verifications, alerts and about 64,000 audit events)
  in a 14-table schema, from one fixed seed.
* Builds a **clean baseline first** (zero rule violations), then injects **5 labelled anomaly types**
  (60 each, 120 for duplicates = 360 injected anomalies) together with **229 near-miss controls**
  (records that look suspicious but are legitimate).
* Detects the anomalies with rule code that **never sees the labels**, then scores the detectors
  against the labels (precision, recall, F1, controls wrongly flagged).
* Runs **12 automated data-quality checks** and writes a validation report.
* Proves **reproducibility**: two full runs give a byte-identical database.

## Key results (seed 20261022, as-of date 2026-10-22)

| Item | Result |
|---|---|
| Clean baseline before injection | True (0 check violations, 0 findings) |
| Injected anomalies / near-miss controls | 360 / 229 |
| Precision / recall / F1 | 1.0 / 1.0 / 1.0 |
| Controls wrongly flagged | 0 of 229 |
| Final database SHA-256 (two full runs) | `4b1680489c3b8e2bb58aca693d878cd5930125029d2f24890876bd917c627b0b` |

**Read these numbers honestly.** Precision = recall = 1.0 shows that the detection rules and the
injected labels agree with each other. The labels were written by the same project, from the same
rule definitions, so this is a consistency check, not proof of accuracy on messy real-world data.
The 229 near-miss controls exist to test that the rules do not over-flag, which is the part of the
result that carries real information. See `docs/DESIGN_AND_RULES.md`, section 9.

## Quick start (Windows PowerShell)

Requires Python 3.12 and Node 18 or newer.

```powershell
# 1. Backend: create the environment, install, run the tests
cd backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1          # the prompt should now start with (.venv)
pip install -r requirements.txt
python -m pytest -q

# 2. Generate the dataset (creates ..\data\output\kyc.db and the evidence files)
python -m generator.generate
python -m validation.reproducibility  # optional: runs the whole pipeline twice and compares checksums

# 3. Start the API (leave this window open)
uvicorn app.main:app --reload         # http://127.0.0.1:8000/docs
```

```powershell
# 4. In a second PowerShell window: the dashboard
cd frontend
npm install
npm run dev                           # open http://localhost:5173
npm run smoke                         # optional: calls all 24 endpoints the screens use (API must be running)
```

`data\output\kyc.db` is git-ignored because it is regenerated from the seed. The evidence files
`ground_truth.csv/json` and `validation_report.json/md` are committed and kept byte-exact by `.gitattributes`.

## The 10 screens

| # | Screen | Route |
|---|---|---|
| 1 | Dashboard | `/` |
| 2 | Customers | `/customers` |
| 3 | Customer detail | `/customers/:id` |
| 4 | Documents | `/documents` |
| 5 | Businesses and ownership | `/businesses` |
| 6 | Reviews | `/reviews` |
| 7 | Alerts | `/alerts` |
| 8 | Exceptions, with comparison to ground truth | `/exceptions` |
| 9 | Audit trail | `/audit` |
| 10 | Data quality | `/quality` |

## API

All endpoints are `GET` under `/api`. List endpoints take `page` (>= 1) and `page_size` (1 to 200);
bad input returns 422 and an unknown id returns 404. Interactive docs are at `/docs` while the API runs.

`health`, `meta/enums`, `meta/customer-types`, `meta/requirements`, `dashboard/summary`,
`customers` (+ `/{id}`), `documents` (+ `/{id}`), `businesses`, `reviews` (+ `/{id}`),
`alerts` (+ `/{id}`), `exceptions` (+ `/summary`), `anomalies`, `evaluation`, `validation`,
`validation/report`, `validation/row-counts`, `audit-events` (+ `/{id}`, `/facets`).

## Project layout

```
backend/
  app/            settings, models (14 tables), services (rules), routers (API), evidence.py (label joining)
  generator/      deterministic data generation and anomaly injection
  validation/     12 checks, evaluation (precision/recall), report writer, reproducibility proof
  tests/          pytest suite
frontend/         React + Vite dashboard (src/pages = the 10 screens)
data/output/      generated database (ignored) and committed evidence files
docs/             design and rules, AI disclosure
PROMPT_HISTORY.md prompts sent to AI tools, recorded verbatim
```

## Design decisions in one paragraph

All business rules live in `backend/app/services` as plain functions of their inputs. The generator,
the API and the validators call the same functions, so a rule is defined once. A guard test fails if
any file in `app/services` mentions `ground_truth`, so detectors cannot read the labels; the only code
that joins findings to labels is `app/evidence.py`. Completeness, document state and overdue status
are calculated, never stored as free-floating flags. Full detail is in `docs/DESIGN_AND_RULES.md`.

## Limitations

Synthetic data only; risk and country points are illustrative assumptions, not a regulatory table;
the API is read-only with no authentication; SQLite suits this demo size, not production load. The
anomaly evaluation measures agreement with injected labels, not real-world detection accuracy.

## Documents

* `docs/DESIGN_AND_RULES.md`: schema, every rule and threshold, evaluation method, validation checks, assumptions
* `docs/AI_DISCLOSURE.md`: how AI was used in this project
* `PROMPT_HISTORY.md`: the prompts, recorded verbatim
