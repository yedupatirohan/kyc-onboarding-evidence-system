from datetime import timedelta

import pytest

from app.config import settings
from app.services.anomaly_detection import OWNERSHIP_OVER_100, run_all_detectors
from app.services.snapshot import load_snapshot
from tests.api.conftest import SMALL, all_pages


def test_documents_total_and_state_buckets_partition(client):
    total = client.get("/api/documents", params={"page_size": 1}).json()["total"]
    assert total == SMALL["n_documents"]
    buckets = sum(client.get("/api/documents", params={"state": s, "page_size": 1}).json()["total"]
                  for s in ("VALID", "PENDING", "EXPIRED", "REJECTED", "IGNORED"))
    assert buckets == total


@pytest.mark.parametrize("state", ["VALID", "PENDING", "EXPIRED", "REJECTED", "IGNORED"])
def test_sql_state_filter_agrees_with_the_python_rule(client, state):
    items = all_pages(client, "/api/documents", state=state)
    assert items and all(i["effective_state"] == state for i in items)


def test_status_filter_and_invalid_status(client):
    items = all_pages(client, "/api/documents", status="VERIFIED")
    assert items and all(i["status"] == "VERIFIED" for i in items)
    assert client.get("/api/documents", params={"status": "MAYBE"}).status_code == 422


def test_expiring_within_days(client):
    items = all_pages(client, "/api/documents", expiring_within_days=60)
    assert items
    for i in items:
        assert i["status"] == "VERIFIED" and 0 <= i["days_to_expiry"] <= 60
    wider = client.get("/api/documents", params={"expiring_within_days": 90, "page_size": 1}).json()["total"]
    assert wider >= len(items)
    assert client.get("/api/documents", params={"expiring_within_days": -1}).status_code == 422


def test_expiry_range_and_bad_dates(client):
    lo, hi = settings.as_of_date, settings.as_of_date + timedelta(days=30)
    items = all_pages(client, "/api/documents", expiry_from=lo.isoformat(), expiry_to=hi.isoformat())
    assert all(lo.isoformat() <= i["expiry_date"] <= hi.isoformat() for i in items)
    assert client.get("/api/documents", params={"expiry_from": "2026-13-45"}).status_code == 422
    assert client.get("/api/documents", params={"expiry_from": "yesterday"}).status_code == 422


def test_filter_by_customer_and_requirement(client):
    mine = all_pages(client, "/api/documents", customer_id="CUS-000001")
    assert all(d["customer_id"] == "CUS-000001" for d in mine)
    req = client.get("/api/meta/requirements").json()[0]["requirement_id"]
    for d in all_pages(client, "/api/documents", requirement_id=req)[:50]:
        assert req in d["requirement_ids"]


def test_documents_sorted_by_expiry(client):
    dates = [i["expiry_date"] for i in all_pages(client, "/api/documents", sort="expiry_date", state="VALID")
             if i["expiry_date"]]
    assert dates == sorted(dates)


def test_document_detail_and_duplicate_detection(client, db):
    dup_hashes = {}
    for d in load_snapshot(db).documents:
        dup_hashes.setdefault(d["file_hash"], []).append(d["document_id"])
    dup = next(ids for ids in dup_hashes.values() if len(ids) > 1)       # injected duplicate scenario
    body = client.get(f"/api/documents/{dup[0]}").json()
    assert set(body["duplicate_of"]) == set(dup) - {dup[0]}
    assert body["customer_name"] and "verifications" in body and "alerts" in body
    by_hash = all_pages(client, "/api/documents", file_hash=body["file_hash"])
    assert {d["document_id"] for d in by_hash} == set(dup)


def test_unknown_document_is_404_and_bad_hash_is_422(client):
    assert client.get("/api/documents/DOC-NOPE").status_code == 404
    assert client.get("/api/documents", params={"file_hash": "abc"}).status_code == 422


def test_businesses_list(client):
    body = client.get("/api/businesses", params={"page_size": 200}).json()
    assert body["total"] == SMALL["n_business"] and len(body["items"]) == SMALL["n_business"]
    assert all(b["registration_number"] for b in body["items"])


def test_ownership_over_100_filter_matches_the_detector(client, db):
    snap = load_snapshot(db)
    expected = {f.customer_id for f in run_all_detectors(snap) if f.issue_type == OWNERSHIP_OVER_100}
    assert expected                                                      # scenario was injected
    flagged = all_pages(client, "/api/businesses", ownership_over_100="true")
    assert {b["customer_id"] for b in flagged} == expected
    assert all(b["ownership_exceeds_100"] and b["active_ownership_pct"] > 100 for b in flagged)
    clean = all_pages(client, "/api/businesses", ownership_over_100="false")
    assert len(clean) + len(flagged) == SMALL["n_business"]
    assert not any(b["ownership_exceeds_100"] for b in clean)


def test_business_filters_and_search(client):
    reg = client.get("/api/businesses", params={"page_size": 1}).json()["items"][0]["registration_number"]
    found = client.get("/api/businesses", params={"q": reg}).json()
    assert found["total"] == 1 and found["items"][0]["registration_number"] == reg
    assert client.get("/api/businesses", params={"risk_level": "EXTREME"}).status_code == 422
