# Validation Report

As-of date: **2026-10-22** | Seed: **20261022**

## Environment

- python: 3.12.4
- SQLAlchemy: 2.1.6
- Faker: 40.44.0
- pydantic: 2.14.2
- fastapi: 0.162.0

## Dataset row counts

| Table | Rows |
|---|---|
| audit_event | 63903 |
| beneficial_owner | 2205 |
| customer_type | 4 |
| kyc_requirement | 15 |
| customer | 8000 |
| customer_type_requirement | 29 |
| business_profile | 1000 |
| document | 20000 |
| ownership_link | 2325 |
| review_case | 3000 |
| risk_rating | 9030 |
| alert | 2908 |
| document_requirement_link | 20133 |
| verification | 24362 |

## Clean baseline (before any anomaly is injected)

- Validation checks with violations: **0**
- Anomaly findings: **0**
- Baseline is clean: **True**

## Validation checks after injection

Violations here are the deliberately injected problems and show the checks work.

| Check | Violations | Meaning |
|---|---|---|
| primary_key_uniqueness | 0 | No duplicate primary keys in any table |
| foreign_key_integrity | 0 | Every foreign key points at an existing parent row |
| allowed_enum_values | 0 | All status/level/type columns hold allowed values only |
| id_format | 0 | All identifiers follow the required formats |
| date_ordering | 0 | Dates are in a possible order and never in the future |
| ownership_reconciliation | 60 | Every business's active ownership adds up to exactly 100.00% |
| lifecycle_transitions | 60 | Customer status matches a valid audit-trail path |
| review_closure_integrity | 60 | Closed reviews have closed_at, closed_by and a resolution |
| duplicate_documents | 100 | No file hash is shared by documents of different customers |
| derived_value_reconciliation | 60 | Stored statuses and levels equal what the source records imply |
| completeness_of_approved | 60 | Every approved customer has 100% mandatory evidence |
| expiry_alert_accuracy | 0 | Expiry alerts exist exactly for documents that should have them |

## Anomaly detection against ground truth

| Issue type | Labelled | Detected | TP | FP | FN | Precision | Recall | Controls wrongly flagged |
|---|---|---|---|---|---|---|---|---|
| EXPIRED_MARKED_VALID | 60 | 60 | 60 | 0 | 0 | 1.0 | 1.0 | 0 of 29 |
| APPROVED_MISSING_EVIDENCE | 60 | 60 | 60 | 0 | 0 | 1.0 | 1.0 | 0 of 40 |
| OWNERSHIP_OVER_100 | 60 | 60 | 60 | 0 | 0 | 1.0 | 1.0 | 0 of 40 |
| REVIEW_CLOSED_NO_RESOLUTION | 60 | 60 | 60 | 0 | 0 | 1.0 | 1.0 | 0 of 40 |
| DUPLICATE_DOCUMENT | 120 | 120 | 120 | 0 | 0 | 1.0 | 1.0 | 0 of 80 |

Overall: precision **1.0**, recall **1.0**, F1 **1.0**.

## Completeness distribution (customers per bucket, by status)

| Customer status | 0 | 1-25 | 26-50 | 51-75 | 76-99 | 100 |
|---|---|---|---|---|---|---|
| APPROVED | 0 | 0 | 40 | 20 | 0 | 4000 |
| CLOSED | 27 | 9 | 97 | 76 | 8 | 83 |
| PROSPECT | 1280 | 67 | 51 | 1 | 0 | 1 |
| SUSPENDED | 58 | 8 | 121 | 84 | 6 | 23 |
| UNDER_REVIEW | 999 | 201 | 603 | 95 | 2 | 40 |

## Expiry statistics

```json
{
  "documents_by_status": {
    "EXPIRED": 637,
    "REJECTED": 1251,
    "SUBMITTED": 1203,
    "SUPERSEDED": 192,
    "VERIFIED": 16717
  },
  "verified_and_unexpired": 12351,
  "expiring_within_lead_times": {
    "30_days": 288,
    "60_days": 306,
    "90_days": 330
  },
  "expired_but_marked_verified": 60,
  "alerts_by_type": {
    "APPROVED_MISSING_EVIDENCE": 60,
    "DOCUMENT_EXPIRED": 697,
    "DUPLICATE_DOCUMENT": 120,
    "EXPIRED_MARKED_VALID": 60,
    "EXPIRY_UPCOMING": 924,
    "OWNERSHIP_OVER_100": 60,
    "REVIEW_CLOSED_NO_RESOLUTION": 60,
    "REVIEW_OVERDUE": 927
  },
  "alerts_by_status": {
    "ACKNOWLEDGED": 496,
    "OPEN": 2150,
    "RESOLVED": 262
  }
}
```

## Review statistics

```json
{
  "reviews_by_status": {
    "CLOSED": 1368,
    "IN_PROGRESS": 220,
    "OVERDUE": 927,
    "SCHEDULED": 485
  },
  "overdue_by_customer_risk": {
    "HIGH": 186,
    "LOW": 152,
    "MEDIUM": 589
  },
  "review_frequency_months": {
    "HIGH": 6,
    "MEDIUM": 12,
    "LOW": 24
  }
}
```

## Reproducibility checksums

- Baseline overall SHA-256: `c1c0fb18a27fda9843ac445e023e255289edd8f6bc923539f070bfa866d56c7a`
- Final overall SHA-256: `4b1680489c3b8e2bb58aca693d878cd5930125029d2f24890876bd917c627b0b`
