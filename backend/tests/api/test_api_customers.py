import pytest

from app.config import settings
from app.services.completeness import calculate_completeness
from app.services.snapshot import load_snapshot
from tests.api.conftest import all_pages


def test_filter_by_status_and_unknown_value(client):
    items = all_pages(client, "/api/customers", status="APPROVED")
    assert items and all(i["status"] == "APPROVED" for i in items)
    assert client.get("/api/customers", params={"status": "NOPE"}).status_code == 422


def test_filter_by_risk_country_and_type(client):
    risk = all_pages(client, "/api/customers", risk_level="HIGH")
    assert risk and all(i["risk_level"] == "HIGH" for i in risk)
    country = all_pages(client, "/api/customers", country_code="in")      # lower case accepted
    assert all(i["country_code"] == "IN" for i in country)
    first_type = client.get("/api/meta/customer-types").json()[0]["customer_type_id"]
    typed = all_pages(client, "/api/customers", customer_type_id=first_type)
    assert typed and all(i["customer_type_id"] == first_type for i in typed)
    assert client.get("/api/customers", params={"country_code": "IND"}).status_code == 422


def test_combined_filters_narrow_the_result(client):
    approved = client.get("/api/customers", params={"status": "APPROVED"}).json()["total"]
    both = client.get("/api/customers", params={"status": "APPROVED", "risk_level": "HIGH"}).json()["total"]
    assert 0 <= both <= approved < 900


def test_search_by_id_and_by_name_and_wildcards_are_literal(client):
    one = client.get("/api/customers", params={"q": "CUS-000001"}).json()
    assert [i["customer_id"] for i in one["items"]] == ["CUS-000001"]
    name = client.get("/api/customers/CUS-000001").json()["full_name"]
    by_name = all_pages(client, "/api/customers", q=name.upper())           # case-insensitive
    assert "CUS-000001" in [i["customer_id"] for i in by_name]
    assert client.get("/api/customers", params={"q": "%"}).json()["total"] == 0   # % is not a wildcard


def test_completeness_filter_partitions_the_population(client):
    counts = {label: client.get("/api/customers", params={"completeness": label, "page_size": 1}).json()["total"]
              for label in ("COMPLETE", "INCOMPLETE", "PENDING_VERIFICATION")}
    assert sum(counts.values()) == 900
    complete = all_pages(client, "/api/customers", completeness="COMPLETE")
    assert all(i["completeness_percent"] == 100.0 and i["missing_count"] == 0 for i in complete)
    assert client.get("/api/customers", params={"completeness": "SORT_OF"}).status_code == 422


def test_sorting(client):
    asc = [i["full_name"].lower() for i in all_pages(client, "/api/customers", sort="full_name")]
    assert asc == sorted(asc)
    desc = [i["customer_id"] for i in all_pages(client, "/api/customers", order="desc")]
    assert desc == sorted(desc, reverse=True)
    scores = [i["risk_score"] for i in all_pages(client, "/api/customers", sort="risk_score", order="desc")
              if i["risk_score"] is not None]
    assert scores == sorted(scores, reverse=True)
    assert client.get("/api/customers", params={"sort": "password"}).status_code == 422


def test_list_completeness_matches_the_rule_service(client, db):
    """The API must report exactly what the rule layer calculates (no second implementation)."""
    snap = load_snapshot(db)
    api = {i["customer_id"]: i for i in all_pages(client, "/api/customers")}
    for c in snap.customers[:150]:
        expected = calculate_completeness(c["customer_type_id"], snap.current_risk[c["customer_id"]], snap.specs,
                                          snap.docs_by_customer.get(c["customer_id"], []), snap.as_of)
        item = api[c["customer_id"]]
        assert (item["completeness_percent"], item["completeness_label"], item["missing_count"]) == (
            expected.percent, expected.label, len(expected.missing)), c["customer_id"]


def test_detail_contains_everything_the_screen_needs(client):
    body = client.get("/api/customers/CUS-000001").json()
    for key in ("completeness", "documents", "reviews", "alerts", "risk_history", "ownership", "business_profile"):
        assert key in body
    assert body["customer_type_name"]
    current = [r for r in body["risk_history"] if r["effective_to"] is None]
    assert len(current) == 1 and current[0]["level"] == body["risk_level"]
    assert all(d["customer_id"] == "CUS-000001" for d in body["documents"])


def test_detail_agrees_with_list_row(client):
    detail = client.get("/api/customers/CUS-000002").json()
    row = client.get("/api/customers", params={"q": "CUS-000002"}).json()["items"][0]
    assert detail["completeness"]["percent"] == row["completeness_percent"]
    assert detail["completeness"]["label"] == row["completeness_label"]


def test_business_customer_detail_has_ownership(client):
    biz = client.get("/api/businesses", params={"page_size": 1}).json()["items"][0]
    body = client.get(f"/api/customers/{biz['customer_id']}").json()
    assert body["business_profile"]["registration_number"] == biz["registration_number"]
    assert body["ownership"] and round(body["ownership_active_total"], 2) == biz["active_ownership_pct"]


def test_unknown_customer_is_404(client):
    r = client.get("/api/customers/CUS-999999")
    assert r.status_code == 404 and "not found" in r.json()["detail"]


def test_write_methods_are_not_allowed(client):
    assert client.delete("/api/customers/CUS-000001").status_code == 405
    assert client.post("/api/customers", json={}).status_code == 405
