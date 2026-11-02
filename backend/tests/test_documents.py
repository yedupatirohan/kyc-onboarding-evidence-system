"""Tests for step 3C: documents, verification events and requirement links."""
import re
from collections import Counter, defaultdict
from datetime import datetime, time, timedelta

import pytest
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session

import app.models  # noqa: F401
from app.config import settings
from app.database import Base
from app.models import Document, Verification, document_requirement_link
from app.seed_reference import seed_reference_data
from app.services.requirements import applicable_requirements
from generator.customers import generate_customers, load_customers
from generator.db_utils import clear_tables
from generator.documents import (
    generate_documents, load_documents, read_customers, specs_from_seed_data,
)

AS_OF = settings.as_of_date
SPECS = specs_from_seed_data()
VALID_STATUSES = {"VERIFIED", "SUBMITTED", "REJECTED", "EXPIRED", "SUPERSEDED"}
LATEST_RESULT_FOR_STATUS = {
    "VERIFIED": "VERIFIED", "EXPIRED": "VERIFIED", "SUPERSEDED": "VERIFIED",
    "SUBMITTED": "PENDING", "REJECTED": "REJECTED",
}


def risk_map(customers_data):
    return {r["customer_id"]: r["level"] for r in customers_data.risk_ratings if r["effective_to"] is None}


@pytest.fixture(scope="module")
def world():
    """Real-size dataset, generated once for this file."""
    cust = generate_customers()
    risk = risk_map(cust)
    docs = generate_documents(cust.customers, risk, SPECS)
    return cust, risk, docs


@pytest.fixture(scope="module")
def small_world():
    cust = generate_customers(n_customers=400, n_business=50)
    risk = risk_map(cust)
    docs = generate_documents(cust.customers, risk, SPECS, n_documents=1200)
    return cust, risk, docs


# ---------- volume and identifiers ----------

def test_exactly_20000_documents(world):
    assert len(world[2].documents) == 20000


def test_document_ids_unique_formatted_and_belong_to_their_customer(world):
    docs = world[2].documents
    ids = [d["document_id"] for d in docs]
    assert len(set(ids)) == len(ids)
    for d in docs:
        assert re.fullmatch(r"DOC-CUS-\d{6}-\d{3}", d["document_id"])
        assert d["document_id"][4:14] == d["customer_id"]     # traceability inside the ID


def test_document_sequence_per_customer_starts_at_1_without_gaps(world):
    seqs = defaultdict(list)
    for d in world[2].documents:
        seqs[d["customer_id"]].append(int(d["document_id"][-3:]))
    for customer_id, values in seqs.items():
        assert sorted(values) == list(range(1, len(values) + 1)), customer_id


def test_file_hashes_are_unique_in_the_clean_baseline(world):
    hashes = [d["file_hash"] for d in world[2].documents]
    assert len(set(hashes)) == len(hashes)
    assert all(re.fullmatch(r"[0-9a-f]{64}", h) for h in hashes)


def test_documents_reference_existing_customers_only(world):
    customer_ids = {c["customer_id"] for c in world[0].customers}
    assert {d["customer_id"] for d in world[2].documents} <= customer_ids


# ---------- dates and statuses ----------

def test_date_ordering(world):
    created = {c["customer_id"]: c["created_at"] for c in world[0].customers}
    for d in world[2].documents:
        assert d["status"] in VALID_STATUSES
        assert d["issue_date"] <= d["submitted_at"] <= AS_OF
        assert d["submitted_at"] >= created[d["customer_id"]]
        if d["expiry_date"] is not None:
            assert d["expiry_date"] >= d["issue_date"]
        assert 40_000 <= d["file_size_bytes"] < 3_500_000


def test_baseline_has_no_expired_document_marked_valid(world):
    for d in world[2].documents:
        if d["expiry_date"] is not None and d["expiry_date"] < AS_OF:
            assert d["status"] not in {"VERIFIED", "SUBMITTED"}, d["document_id"]


def test_expired_status_always_means_past_expiry(world):
    for d in world[2].documents:
        if d["status"] == "EXPIRED":
            assert d["expiry_date"] is not None and d["expiry_date"] < AS_OF


def test_some_documents_expire_soon_for_alerts(world):
    soon = [
        d for d in world[2].documents
        if d["status"] == "VERIFIED" and d["expiry_date"]
        and AS_OF <= d["expiry_date"] <= AS_OF + timedelta(days=90)
    ]
    assert len(soon) > 200


# ---------- the completeness rule (decision D14) ----------

def satisfied_requirements(docs):
    links = defaultdict(list)
    for l in docs.links:
        links[l["document_id"]].append(l["requirement_id"])
    satisfied = defaultdict(set)
    for d in docs.documents:
        if d["status"] == "VERIFIED" and (d["expiry_date"] is None or d["expiry_date"] >= AS_OF):
            satisfied[d["customer_id"]].update(links[d["document_id"]])
    return satisfied


def test_every_approved_customer_is_complete(world):
    cust, risk, docs = world
    satisfied = satisfied_requirements(docs)
    for c in cust.customers:
        if c["status"] != "APPROVED":
            continue
        required = applicable_requirements(c["customer_type_id"], risk[c["customer_id"]], SPECS, AS_OF, True)
        missing = [s.requirement_id for s in required if s.requirement_id not in satisfied[c["customer_id"]]]
        assert not missing, (c["customer_id"], missing)


def test_other_statuses_are_mostly_incomplete(world):
    cust, risk, docs = world
    satisfied = satisfied_requirements(docs)
    complete = Counter()
    total = Counter()
    for c in cust.customers:
        required = applicable_requirements(c["customer_type_id"], risk[c["customer_id"]], SPECS, AS_OF, True)
        total[c["status"]] += 1
        if all(s.requirement_id in satisfied[c["customer_id"]] for s in required):
            complete[c["status"]] += 1
    assert complete["PROSPECT"] / total["PROSPECT"] < 0.05
    assert complete["UNDER_REVIEW"] / total["UNDER_REVIEW"] < 0.10
    assert complete["UNDER_REVIEW"] > 0          # some are genuinely ready for approval


def test_documents_only_link_to_applicable_requirements(world):
    cust, risk, docs = world
    by_doc = {d["document_id"]: d["customer_id"] for d in docs.documents}
    allowed = {}
    for c in cust.customers:
        allowed[c["customer_id"]] = {
            s.requirement_id for s in applicable_requirements(
                c["customer_type_id"], risk[c["customer_id"]], SPECS, AS_OF)
        }
    for l in docs.links:
        assert l["requirement_id"] in allowed[by_doc[l["document_id"]]]


# ---------- links (N:M) ----------

def test_every_document_has_at_least_one_link_and_some_have_two(world):
    per_doc = Counter(l["document_id"] for l in world[2].links)
    assert set(per_doc) == {d["document_id"] for d in world[2].documents}
    assert set(per_doc.values()) == {1, 2}
    assert len({(l["document_id"], l["requirement_id"]) for l in world[2].links}) == len(world[2].links)


def test_two_requirement_documents_belong_to_companies_only(world):
    cust, _, docs = world
    types = {c["customer_id"]: c["customer_type_id"] for c in cust.customers}
    doc_customer = {d["document_id"]: d["customer_id"] for d in docs.documents}
    for doc_id, n in Counter(l["document_id"] for l in docs.links).items():
        if n == 2:
            assert types[doc_customer[doc_id]] == "COMPANY"


# ---------- verification history ----------

def test_verification_ids_unique_and_formatted(world):
    ids = [v["verification_id"] for v in world[2].verifications]
    assert len(set(ids)) == len(ids)
    assert all(re.fullmatch(r"VER-CUS-\d{6}-\d{3}-\d{2}", i) for i in ids)


def test_latest_verification_result_matches_document_status(world):
    docs = world[2]
    latest = {}
    for v in docs.verifications:                      # events are generated oldest first
        latest[v["document_id"]] = v["result"]
    for d in docs.documents:
        assert latest[d["document_id"]] == LATEST_RESULT_FOR_STATUS[d["status"]], d["document_id"]


def test_verified_at_rules(world):
    docs = world[2]
    submitted = {d["document_id"]: d["submitted_at"] for d in docs.documents}
    end_of_as_of = datetime.combine(AS_OF, time.max)
    for v in docs.verifications:
        if v["result"] == "PENDING":
            assert v["verified_at"] is None and v["verified_by"] is None
        else:
            assert v["verified_by"] and v["verified_at"] is not None
            assert v["verified_at"].date() >= submitted[v["document_id"]]
            assert v["verified_at"] <= end_of_as_of


def test_history_documents_exist_in_both_kinds(world):
    kinds = Counter(d["status"] for d in world[2].documents)
    assert kinds["SUPERSEDED"] > 0 and kinds["REJECTED"] > 0


# ---------- determinism and errors ----------

def test_same_seed_gives_identical_documents(small_world):
    cust, risk, first = small_world
    second = generate_documents(cust.customers, risk, SPECS, n_documents=1200)
    assert first == second


def test_different_seed_gives_different_documents(small_world):
    cust, risk, first = small_world
    other = generate_documents(cust.customers, risk, SPECS, n_documents=1200, seed=7)
    assert first != other


def test_too_small_document_target_is_rejected(small_world):
    cust, risk, _ = small_world
    with pytest.raises(ValueError):
        generate_documents(cust.customers, risk, SPECS, n_documents=50)


# ---------- loading into a database ----------

@pytest.fixture()
def session():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with Session(engine) as s:
        seed_reference_data(s)
        yield s
    engine.dispose()


def test_load_with_valid_foreign_keys_and_read_back(session, small_world):
    cust, risk, docs = small_world
    load_customers(session, cust)
    counts = load_documents(session, docs)
    assert counts == {
        "document": 1200,
        "verification": len(docs.verifications),
        "document_requirement_link": len(docs.links),
    }
    assert session.scalar(select(func.count()).select_from(Document)) == 1200
    assert session.scalar(select(func.count()).select_from(document_requirement_link)) == len(docs.links)
    customers, current = read_customers(session)
    assert len(customers) == 400 and current == risk


def test_clear_tables_removes_only_the_named_tables(session, small_world):
    cust, _, docs = small_world
    load_customers(session, cust)
    load_documents(session, docs)
    clear_tables(session, ["verification", "document_requirement_link", "document"])
    assert session.scalar(select(func.count()).select_from(Document)) == 0
    assert session.scalar(select(func.count()).select_from(Verification)) == 0
    from app.models import Customer
    assert session.scalar(select(func.count()).select_from(Customer)) == 400
    with pytest.raises(ValueError):
        clear_tables(session, ["not_a_table"])
