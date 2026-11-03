# Bundle 5a - API foundation + customers, documents, businesses

## Install (PowerShell, from the repo root)
    Expand-Archive phase5a_bundle.zip -DestinationPath . -Force      # only ADDS files under backend\
    cd backend
    .\.venv\Scripts\Activate.ps1
    python -m pytest -q                 # old tests + new tests\api\*
    python -m pytest tests\api -q       # only the new API tests

## Run the API on the real 8000-customer database
    python -m generator.generate        # only if data\output\kyc.db does not exist yet
    uvicorn app.main:app --reload
    # docs: http://127.0.0.1:8000/docs     health: http://127.0.0.1:8000/api/health

## Endpoints (all GET, all under /api)
| Path | Filters / params |
|---|---|
| /health, /meta/enums, /meta/customer-types, /meta/requirements | - |
| /customers | page, page_size(<=200), status, customer_type_id, country_code, risk_level, completeness, q, sort, order |
| /customers/{id} | full detail: risk history, completeness + missing list, documents, reviews, alerts, ownership |
| /documents | page, page_size, status, state, customer_id, requirement_id, file_hash, expiring_within_days, expiry_from, expiry_to, q, sort, order |
| /documents/{id} | verifications, alerts, duplicate_of |
| /businesses | page, page_size, status, risk_level, country_of_incorporation, ownership_over_100, q, order |

Invalid values (bad enum, page=0, page_size>200, bad date) return HTTP 422. Unknown ids return 404.

## Design rules kept
* No business rule is re-implemented: completeness, document state, ownership totals and review due dates
  call app/services. The only SQL twin (document `state` filter) has a test proving it agrees with the Python rule.
* The API is read-only (writes return 405).

## PROMPT_HISTORY.md - paste and edit this entry (keep what you really asked, mark what you changed)
### Phase 5a - API foundation (3 Nov 2026)
Prompt (yours): "Please continue with Phase 5 ... FastAPI endpoints with pagination/filtering/tests ..."
AI output: app/main.py, routers (meta, customers, documents, businesses), schemas, services/customer_view.py, tests/api/*.
Human checks: ran pytest (record the number), opened /docs, tried filters; record any fix you made and why.
