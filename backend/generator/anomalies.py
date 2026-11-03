"""Step 3G: inject the five labelled anomalies (and near-miss controls) AFTER the clean baseline.

Every injection touches only the rows it names and is recorded as a ground-truth row.
Ground truth is written to files only; no operational table holds a label, and the detectors
(app/services/anomaly_detection.py) never read these files.
"""
import csv
import hashlib
import json
from collections import defaultdict
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path

from sqlalchemy import update

from app.config import PROJECT_ROOT, settings
from app.services.anomaly_detection import (
    APPROVED_MISSING_EVIDENCE, DUPLICATE_DOCUMENT, EXPECTED_DECISION, EXPIRED_MARKED_VALID,
    OWNERSHIP_OVER_100, REVIEW_CLOSED_NO_RESOLUTION, RULES,
)
from app.services.completeness import calculate_completeness
from app.services.snapshot import load_snapshot
from generator.rng import make_rng

SCENARIOS = {
    1: EXPIRED_MARKED_VALID, 2: APPROVED_MISSING_EVIDENCE, 3: OWNERSHIP_OVER_100,
    4: REVIEW_CLOSED_NO_RESOLUTION, 5: DUPLICATE_DOCUMENT,
}
COLUMNS = ["ground_truth_id", "scenario", "issue_type", "label_kind", "ground_truth", "entity_type",
           "entity_id", "customer_id", "group_id", "rule_applied", "injected_change", "expected_business_decision"]
EXTRA_PERCENT_CHOICES = [10, 15, 20, 25, 30]


def inject_anomalies(session, n_anomalies=60, n_controls=40, seed=None, as_of=None) -> list[dict]:
    from app.models import Customer, Document, OwnershipLink, ReviewCase

    as_of = settings.as_of_date if as_of is None else as_of
    rng = make_rng("anomalies", seed)
    snap = load_snapshot(session, as_of)
    docs = {d["document_id"]: d for d in snap.documents}
    rows: list[dict] = []
    used_docs: set[str] = set()

    def label(scenario, kind, entity_type, entity_id, customer_id, change, group_id=""):
        positive = kind == "injected_anomaly"
        rows.append({
            "scenario": scenario, "issue_type": SCENARIOS[scenario], "label_kind": kind,
            "ground_truth": positive, "entity_type": entity_type, "entity_id": entity_id,
            "customer_id": customer_id, "group_id": group_id, "rule_applied": RULES[SCENARIOS[scenario]],
            "injected_change": change,
            "expected_business_decision": EXPECTED_DECISION[SCENARIOS[scenario]] if positive
            else "No exception: the record is valid. A correct detector must NOT flag it.",
        })

    def take(candidates, n):
        candidates = sorted(candidates)
        return sorted(rng.sample(candidates, min(n, len(candidates))))

    # ---- Scenario 1: document expired but marked valid -----------------------------------
    chosen = take([d["document_id"] for d in snap.documents if d["status"] == "EXPIRED"], n_anomalies)
    session.execute(update(Document).where(Document.document_id.in_(chosen)).values(status="VERIFIED"))
    for doc_id in chosen:
        d = docs[doc_id]
        label(1, "injected_anomaly", "document", doc_id, d["customer_id"],
              f"status EXPIRED -> VERIFIED; expiry_date {d['expiry_date']} unchanged")
    used_docs.update(chosen)
    near = [d["document_id"] for d in snap.documents
            if d["status"] == "VERIFIED" and d["expiry_date"] is not None
            and as_of <= d["expiry_date"] <= as_of + timedelta(days=3)]
    for doc_id in take(near, n_controls):
        label(1, "near_miss_control", "document", doc_id, docs[doc_id]["customer_id"],
              f"valid VERIFIED document expiring on {docs[doc_id]['expiry_date']} (within 3 days)")
        used_docs.add(doc_id)

    # ---- Scenario 2: customer approved with missing mandatory evidence --------------------
    incomplete = {}
    for c in snap.customers:
        if c["status"] == "UNDER_REVIEW":
            result = calculate_completeness(c["customer_type_id"], snap.current_risk[c["customer_id"]],
                                            snap.specs, snap.docs_by_customer.get(c["customer_id"], []), as_of)
            if 40.0 <= result.percent < 100.0:
                incomplete[c["customer_id"]] = result.percent
    created = {c["customer_id"]: c["created_at"] for c in snap.customers}
    for customer_id in take(incomplete, n_anomalies):
        session.execute(update(Customer).where(Customer.customer_id == customer_id).values(
            status="APPROVED", onboarded_at=created[customer_id] + timedelta(days=10)))
        label(2, "injected_anomaly", "customer", customer_id, customer_id,
              f"status UNDER_REVIEW -> APPROVED while completeness is {incomplete[customer_id]}%")
    approved_with_history = {d["customer_id"] for d in snap.documents if d["status"] in ("REJECTED", "SUBMITTED")}
    approved = {c["customer_id"] for c in snap.customers if c["status"] == "APPROVED"}
    for customer_id in take(approved & approved_with_history, n_controls):
        label(2, "near_miss_control", "customer", customer_id, customer_id,
              "APPROVED and complete; also has rejected or pending history documents")

    # ---- Scenario 3: beneficial ownership above 100% ---------------------------------------
    active = defaultdict(list)
    history_customers = set()
    for l in snap.owner_links:
        if l["effective_to"] is None:
            active[l["customer_id"]].append(l)
        else:
            history_customers.add(l["customer_id"])
    eligible3 = {cid: ls for cid, ls in active.items()
                 if len(ls) >= 2 and any(Decimal(str(l["ownership_pct"])) <= 70 for l in ls)}
    over_customers = take(eligible3, n_anomalies)
    for customer_id in over_customers:
        link = next(l for l in sorted(eligible3[customer_id], key=lambda l: l["link_id"])
                    if Decimal(str(l["ownership_pct"])) <= 70)
        extra = Decimal(rng.choice(EXTRA_PERCENT_CHOICES))
        new_pct = Decimal(str(link["ownership_pct"])) + extra
        session.execute(update(OwnershipLink).where(OwnershipLink.link_id == link["link_id"]).values(ownership_pct=new_pct))
        label(3, "injected_anomaly", "customer", customer_id, customer_id,
              f"{link['link_id']} ownership_pct {link['ownership_pct']} -> {new_pct}; active total becomes {Decimal(100) + extra}")
    for customer_id in take(history_customers - set(over_customers), n_controls):
        label(3, "near_miss_control", "customer", customer_id, customer_id,
              "has end-dated historical ownership links; ACTIVE total is exactly 100.00")

    # ---- Scenario 4: review closed without resolution --------------------------------------
    closed = [r["review_id"] for r in snap.reviews if r["status"] == "CLOSED" and (r["resolution"] or "").strip()]
    reviews = {r["review_id"]: r for r in snap.reviews}
    for review_id in take(closed, n_anomalies):
        session.execute(update(ReviewCase).where(ReviewCase.review_id == review_id).values(resolution=None))
        label(4, "injected_anomaly", "review_case", review_id, reviews[review_id]["customer_id"],
              f"resolution '{reviews[review_id]['resolution']}' removed while status stays CLOSED")
    for review_id in take([r["review_id"] for r in snap.reviews if r["status"] == "OVERDUE"], n_controls):
        label(4, "near_miss_control", "review_case", review_id, reviews[review_id]["customer_id"],
              "OVERDUE review: open and without resolution, but NOT closed")

    # ---- Scenario 5: duplicate document across customers ------------------------------------
    owners_of = defaultdict(set)
    customers_of = defaultdict(set)
    for l in snap.owner_links:
        owners_of[l["customer_id"]].add(l["owner_id"])
        customers_of[l["owner_id"]].add(l["customer_id"])
    pool = sorted(d["document_id"] for d in snap.documents if d["status"] == "VERIFIED" and d["document_id"] not in used_docs)
    pairs, attempts = [], 0
    while len(pairs) < n_anomalies and attempts < 200_000:
        attempts += 1
        a, b = rng.sample(pool, 2)
        ca, cb = docs[a]["customer_id"], docs[b]["customer_id"]
        if ca != cb and not (owners_of[ca] & owners_of[cb]) and a not in used_docs and b not in used_docs:
            pairs.append((a, b))
            used_docs.update((a, b))
    for number, (a, b) in enumerate(pairs, start=1):
        session.execute(update(Document).where(Document.document_id == b).values(file_hash=docs[a]["file_hash"]))
        group = f"DUP-{number:03d}"
        for doc_id, other in ((a, b), (b, a)):
            label(5, "injected_anomaly", "document", doc_id, docs[doc_id]["customer_id"],
                  f"{b} now has the same file hash as {a}; customers share no beneficial owner", group)

    related_pairs = []
    for owner_id in sorted(customers_of):
        group_customers = sorted(customers_of[owner_id])
        if len(group_customers) < 2 or len(related_pairs) >= n_controls:
            continue
        ca, cb = rng.sample(group_customers, 2)
        docs_a = [d for d in pool if docs[d]["customer_id"] == ca and d not in used_docs]
        docs_b = [d for d in pool if docs[d]["customer_id"] == cb and d not in used_docs]
        if docs_a and docs_b:
            a, b = docs_a[0], docs_b[0]
            related_pairs.append((a, b, owner_id))
            used_docs.update((a, b))
    for number, (a, b, owner_id) in enumerate(related_pairs, start=1):
        session.execute(update(Document).where(Document.document_id == b).values(file_hash=docs[a]["file_hash"]))
        for doc_id in (a, b):
            label(5, "near_miss_control", "document", doc_id, docs[doc_id]["customer_id"],
                  f"same file hash shared by related customers (common beneficial owner {owner_id})", f"DUPREL-{number:03d}")

    session.commit()
    rows.sort(key=lambda r: (r["scenario"], r["label_kind"], r["entity_id"]))
    for number, r in enumerate(rows, start=1):
        r["ground_truth_id"] = f"GT-{number:06d}"
    return rows


def write_ground_truth(rows: list[dict], out_dir: Path | None = None) -> dict:
    """Write ground_truth.csv and ground_truth.json; return their paths and SHA-256 checksums."""
    out_dir = Path(out_dir) if out_dir else PROJECT_ROOT / "data" / "output"
    out_dir.mkdir(parents=True, exist_ok=True)
    csv_path, json_path = out_dir / "ground_truth.csv", out_dir / "ground_truth.json"
    with open(csv_path, "w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=COLUMNS, lineterminator="\n")
        writer.writeheader()
        writer.writerows([{k: r[k] for k in COLUMNS} for r in rows])
    with open(json_path, "w", encoding="utf-8", newline="\n") as handle:
        json.dump([{k: r[k] for k in COLUMNS} for r in rows], handle, indent=2, sort_keys=False)
        handle.write("\n")
    sha = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()
    return {"csv": str(csv_path), "json": str(json_path), "csv_sha256": sha(csv_path), "json_sha256": sha(json_path)}


def read_ground_truth(path: Path | None = None) -> list[dict]:
    path = Path(path) if path else PROJECT_ROOT / "data" / "output" / "ground_truth.csv"
    with open(path, newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    for r in rows:
        r["ground_truth"] = r["ground_truth"] == "True"
    return rows
