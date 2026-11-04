# Design and Rules

This document describes how the system is built and exactly which rules it applies. Every threshold
below is read from the code (file names are given) and can be checked there.

## 1. Architecture

```
generator/  ->  SQLite kyc.db  <-  app/services (rules)  <-  FastAPI routers  <-  React dashboard
                     ^                    ^
                     |                    +-- validation/ (12 checks, evaluation, report)
                     +-- ground_truth.csv/json (labels, joined only in app/evidence.py)
```

* **One definition of each rule.** Rules are plain functions in `backend/app/services`. The
  generator, the API and the validators all import them. No rule is written twice.
* **Settings in one place.** `backend/app/config.py` holds the seed, as-of date, alert lead times,
  review frequencies and data volumes. Environment variables with the prefix `KYC_` override them.
* **Fixed "today".** All calculations use the as-of date (`2026-10-22`), never the machine clock,
  so results do not change from day to day.
* **Derived values are calculated, not trusted.** Completeness, document state and overdue status
  are computed from source records. Validation check 10 confirms the stored values agree.

## 2. Data model (14 tables)

| Table | Rows | Purpose |
|---|---|---|
| customer_type | 4 | INDIVIDUAL, SOLE_PROPRIETOR, COMPANY, TRUST |
| kyc_requirement | 15 | Document requirements: mandatory flag, minimum risk level, validity, effective dates |
| customer_type_requirement | 29 | Which requirement applies to which customer type |
| customer | 8,000 | The onboarded party and its status |
| business_profile | 1,000 | Extra details for business customers |
| beneficial_owner | 2,205 | People who own business customers |
| ownership_link | 2,325 | Ownership percentage between a business and an owner, with effective dates |
| document | 20,000 | Submitted evidence with status, expiry date and file hash |
| document_requirement_link | 20,133 | Which requirement(s) a document satisfies |
| verification | 24,362 | Verification history of documents |
| risk_rating | 9,030 | Risk score and level history per customer |
| review_case | 3,000 | Periodic reviews with due date, status and resolution |
| alert | 2,908 | Raised alerts (expiry, overdue, and the five exception types) |
| audit_event | 63,903 | Audit trail of status changes and alert actions |

Row counts are from `data/output/validation_report.md`. Primary keys, foreign keys and allowed
values are enforced by the schema (CHECK constraints built from `app/enums.py`) and re-checked by
the validation suite.

Enumerations (`app/enums.py`): risk level LOW/MEDIUM/HIGH; customer status PROSPECT, UNDER_REVIEW,
APPROVED, SUSPENDED, CLOSED; document status SUBMITTED, VERIFIED, REJECTED, EXPIRED, SUPERSEDED;
review status SCHEDULED, IN_PROGRESS, CLOSED, OVERDUE; alert severity LOW to CRITICAL; alert status
OPEN, ACKNOWLEDGED, RESOLVED.

## 3. Risk scoring (`app/services/risk.py`)

`score = type points + country points + extra points`, limited to 0..100.

* Type points: INDIVIDUAL 10, SOLE_PROPRIETOR 20, COMPANY 30, TRUST 40.
* Country points: IN, GB, US, DE, AU, SG = 0; AE = 10; PA, NG, MM = 25.
* Extra points stand for factors not modelled in detail (for example a politically exposed person flag).
* Levels: 0 to 34 LOW, 35 to 64 MEDIUM, 65 to 100 HIGH.

**Assumption:** the points and the country list are illustrative. They are not taken from any
regulator or sanctions list and must not be used for real decisions.

## 4. Requirements and completeness

**Which requirements apply** (`app/services/requirements.py`): a requirement applies to a customer when
(a) the customer type is linked to it, (b) the customer's risk level is at or above the requirement's
minimum risk level, and (c) the requirement is in force on the as-of date.

**Document state** (`app/services/completeness.py`):

| Stored status | Condition | State |
|---|---|---|
| VERIFIED | expiry date missing or not yet passed | VALID |
| VERIFIED | expiry date before the as-of date | EXPIRED |
| EXPIRED | any | EXPIRED |
| SUBMITTED | any | PENDING |
| REJECTED | any | REJECTED |
| SUPERSEDED | any | ignored |

**Completeness** is measured over the applicable **mandatory** requirements. For each requirement the
strongest evidence wins (VALID, then PENDING, then EXPIRED, then REJECTED, then MISSING).
`percent = satisfied / required x 100`, rounded to one decimal; a customer with no mandatory
requirements is 100%. Label: COMPLETE when all are satisfied; PENDING_VERIFICATION when everything
missing is only pending; otherwise INCOMPLETE. Each gap carries a reason such as "Document expired on 2026-10-12".

## 5. Expiry alerts (`app/services/expiry.py`)

Lead times are 90, 60 and 30 days (`KYC_ALERT_LEAD_DAYS`).

* A VERIFIED document that expires within a lead time gets one EXPIRY_UPCOMING alert, in the tightest
  bucket already crossed (45 days left gives the 60-day bucket). Expired documents never get this alert.
* A VERIFIED or EXPIRED document whose expiry date has passed gets DOCUMENT_EXPIRED.
* SUBMITTED, REJECTED and SUPERSEDED documents never raise expiry alerts.

Validation check 12 confirms expiry alerts exist for exactly the documents that should have them.

## 6. Review scheduling (`app/services/review_schedule.py`)

Review frequency by risk level: HIGH every 6 months, MEDIUM every 12, LOW every 24 (`KYC_REVIEW_MONTHS_*`).
A review is overdue when its due date has passed and its status is not CLOSED. The reconciliation
rule is: past due and not closed must be stored as OVERDUE.

## 7. The five exception rules (`app/services/anomaly_detection.py`)

| Type | Rule | Severity | Expected decision |
|---|---|---|---|
| EXPIRED_MARKED_VALID | document.status = VERIFIED AND expiry_date < as_of_date | HIGH | Downgrade the document to EXPIRED, request a fresh one, mark the customer Requires Review |
| APPROVED_MISSING_EVIDENCE | customer.status = APPROVED AND mandatory completeness < 100% | CRITICAL | Suspend the approval until every mandatory document is supplied and verified |
| OWNERSHIP_OVER_100 | sum of ownership_pct over ACTIVE links of a business > 100.00 | HIGH | Block approval and obtain a corrected beneficial ownership declaration |
| REVIEW_CLOSED_NO_RESOLUTION | review.status = CLOSED AND resolution is empty | MEDIUM | Reopen the review and record a resolution |
| DUPLICATE_DOCUMENT | same file hash on documents of two customers that share no beneficial owner | HIGH | Escalate to compliance for possible document fraud; request originals from both customers |

Details that matter: ownership links are active when `effective_from <= as_of` and `effective_to` is
empty or not yet passed, and percentages are summed as exact decimals (not floats). A shared file hash
between customers who have a common beneficial owner is **not** flagged, because related parties may
legitimately share a document.

**Exception management** (`app/services/exceptions.py`): re-running the scan raises an alert for each new
finding, leaves existing alerts untouched, and auto-resolves alerts whose condition no longer holds.
Each change writes an audit event (`ALERT_RAISED`, `ALERT_AUTO_RESOLVED`) by actor `anomaly_detector`.

## 8. Data generation and anomaly injection (`backend/generator`)

Pipeline (`python -m generator.generate`): reference data, customers, documents, owners, reviews,
alerts, audit events, then **verify the baseline is clean**, **inject labelled anomalies and write the
ground truth**, run the detectors and raise exception alerts, then evaluate and write the reports.

Decision: **a valid baseline first, anomalies injected afterwards.** This makes it possible to prove the
starting data had zero violations, so every violation found later is attributable to an injection.

Injection per scenario: 60 anomalies and up to 40 near-miss controls. Duplicates are injected as 60 pairs,
labelled as 120 documents, with 40 related-customer pairs labelled as 80 control documents. Scenario 1 has 29
controls rather than 40: the generator takes as many as it finds, and only 29 documents matched the boundary rule. Controls are deliberately close to the rule boundary:

1. Expired-marked-valid: a VERIFIED document expiring within 3 days after the as-of date (still valid).
2. Approved-missing-evidence: an APPROVED, complete customer that also has rejected or pending history documents.
3. Ownership over 100: a customer with end-dated historical links whose ACTIVE total is exactly 100.00.
4. Review closed without resolution: an OVERDUE review (open and without resolution, but not closed).
5. Duplicate document: the same file hash shared by customers that have a common beneficial owner.

Every random choice comes from seeded streams (`generator/rng.py`) and IDs from deterministic builders
(`generator/ids.py`).

Ground truth (`data/output/ground_truth.csv` and `.json`) has 589 rows: 360 `injected_anomaly` and 229
`near_miss_control`, each with the rule applied, the exact injected change and the expected business decision.

## 9. Evaluation and what it does and does not show

`validation/evaluate.py` compares detector findings with the labels per issue type: true positives,
false positives (including wrongly flagged controls), false negatives, precision, recall and F1.

Result: **TP 360, FP 0, FN 0; precision = recall = F1 = 1.0; 0 of 229 controls flagged.**

Honest reading:

* The detectors do not read the labels. A guard test (`test_detectors_never_read_ground_truth`) fails if
  any file in `app/services` contains the text `ground_truth` or `generator.anomalies`.
* The injected labels and the detection rules come from the same project and the same rule definitions.
  Perfect scores therefore show that **the rules and the injections agree**; they do not prove the rules
  would find real-world problems in messy data.
* The 229 near-miss controls are what make the result meaningful: a rule that simply flagged everything
  near the boundary would be caught as a false positive.
* Real data would add problems this dataset does not contain (typos, partial records, conflicting
  sources), and precision and recall would be expected to fall below 1.0.

## 10. Validation suite (`validation/checks.py`)

Twelve checks, run live by `/api/validation` and stored in `validation_report.json/md`:

| # | Check | After injection |
|---|---|---|
| 1 | primary_key_uniqueness | 0 |
| 2 | foreign_key_integrity | 0 |
| 3 | allowed_enum_values | 0 |
| 4 | id_format | 0 |
| 5 | date_ordering (possible order, never in the future) | 0 |
| 6 | ownership_reconciliation (active total = 100.00%) | 60 |
| 7 | lifecycle_transitions (status matches an audit-trail path) | 60 |
| 8 | review_closure_integrity | 60 |
| 9 | duplicate_documents | 100 |
| 10 | derived_value_reconciliation | 60 |
| 11 | completeness_of_approved | 60 |
| 12 | expiry_alert_accuracy | 0 |

On the **clean baseline** every check reports 0 violations. After injection, checks 6 to 11 report
violations that correspond to the deliberately injected problems, which shows the checks can fail.

## 11. Reproducibility

`python -m validation.reproducibility` runs the entire pipeline twice and compares SHA-256 checksums of
the database, the ground-truth files and the reports. Result for seed 20261022: **identical**, no differences.
Final database SHA-256: `4b1680489c3b8e2bb58aca693d878cd5930125029d2f24890876bd917c627b0b`.
(The checksum is of the SQLite file produced by the environment recorded in the validation report;
a different library version could in principle produce a different file with the same logical content.)

## 12. API and dashboard

The API is read-only (`GET`), paginated, validated (422) and consistent about missing ids (404).
The dashboard calls it through one module (`frontend/src/api.js`); Vite proxies `/api` to the backend.
`/dashboard/summary` returns all headline figures in one call; analysis results are cached for up to two
minutes, keyed on alert and audit counts. Endpoints that need labels return 404 with the regeneration
command if `ground_truth.csv` is missing.

## 13. Assumptions and limitations

* Synthetic data; names and documents are fictional.
* Risk points, country list, review frequencies and lead times are illustrative settings.
* Read-only API without authentication; not hardened for production use.
* SQLite is used for portability and exact reproducibility.
* The as-of date is fixed, so "overdue" and "expired" describe the data as of 2026-10-22.
