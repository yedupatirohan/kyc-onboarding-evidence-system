# Bundle 5c - evidence endpoints (completes the API)

Install from the repo root (replaces backend\app\main.py and backend\tests\api\conftest.py, adds the rest):
    Expand-Archive "<full path to zip>" -DestinationPath . -Force
    cd backend ; python -m pytest -q        # expect 250 + 15 = 265

New endpoints (GET, under /api)
| Path | What it returns |
|---|---|
| /dashboard/summary | customers, completeness, documents, alerts, reviews, exceptions, evaluation, reproducibility in ONE call |
| /anomalies | every ground-truth label + any unlabelled finding, with detected? and outcome; filters issue_type, outcome, label_kind, detected, customer_id, q |
| /evaluation | live detectors vs ground truth: per-issue-type and overall precision / recall / F1 |
| /validation | the 12 validation checks run live |
| /validation/report | stored validation_report.json (clean-baseline proof, checksums, environment) |
| /validation/row-counts | rows in all 14 tables |

Notes
* Detectors never read labels; only /anomalies, /evaluation and the dashboard join them.
* Results are cached for up to 2 minutes (keyed on alert/audit counts), so repeated screen loads are fast.
* If data/output/ground_truth.csv is missing the endpoints return 404 with the command to regenerate it.

PROMPT_HISTORY.md draft: "Phase 5c - evidence endpoints (3 Nov 2026)". Record your real prompt, the pytest count, any fix.
