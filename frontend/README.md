# KYC Evidence Dashboard (React + Vite)

Ten screens, every number from the real FastAPI endpoints (no mock data).

| # | Screen | Route | Endpoints |
|---|---|---|---|
| 1 | Dashboard | / | /dashboard/summary |
| 2 | Customers | /customers | /customers, /meta/* |
| 3 | Customer detail | /customers/:id | /customers/{id} |
| 4 | Documents | /documents | /documents, /meta/requirements |
| 5 | Businesses & ownership | /businesses | /businesses |
| 6 | Reviews | /reviews | /reviews |
| 7 | Alerts | /alerts | /alerts |
| 8 | Exceptions (+ ground-truth comparison) | /exceptions | /exceptions, /exceptions/summary, /anomalies, /evaluation |
| 9 | Audit trail | /audit | /audit-events, /audit-events/facets |
| 10 | Data quality | /quality | /validation, /validation/report, /validation/row-counts |

## Run (two PowerShell windows)
    # window 1 - API (needs data\output\kyc.db; create it with: python -m generator.generate)
    cd backend ; .\.venv\Scripts\Activate.ps1 ; uvicorn app.main:app --reload

    # window 2 - UI
    cd frontend ; npm install ; npm run dev          # open http://localhost:5173

## Verify against the real API
    npm run smoke        # calls all 24 endpoints the screens use and checks their shape (backend must be running)
    npm run build        # production build into frontend\dist

Vite proxies /api to http://127.0.0.1:8000, so there are no CORS settings to change.
Requires Node 18 or newer.
