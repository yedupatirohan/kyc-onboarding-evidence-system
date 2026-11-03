"""Health, reference data and the shared pagination contract."""
import pytest

from tests.api.conftest import SMALL, all_pages


def test_health_reports_counts(client):
    body = client.get("/api/health").json()
    assert body["status"] == "ok" and body["as_of_date"] == "2026-10-22"
    assert body["counts"]["customers"] == SMALL["n_customers"]
    assert body["counts"]["documents"] == SMALL["n_documents"]


def test_enums_endpoint_lists_every_filter_value(client):
    body = client.get("/api/meta/enums").json()
    assert body["risk_level"] == ["LOW", "MEDIUM", "HIGH"]
    assert set(body["document_state"]) == {"VALID", "PENDING", "EXPIRED", "REJECTED", "IGNORED"}
    assert "EXPIRED_MARKED_VALID" in body["alert_type"]


def test_reference_endpoints(client):
    types = client.get("/api/meta/customer-types").json()
    assert types and {"customer_type_id", "name", "is_business"} <= set(types[0])
    reqs = client.get("/api/meta/requirements").json()
    assert reqs and all(r["customer_type_ids"] for r in reqs)


def test_pagination_envelope_and_totals(client):
    body = client.get("/api/customers", params={"page": 2, "page_size": 100}).json()
    assert (body["page"], body["page_size"], body["total"], body["pages"]) == (2, 100, 900, 9)
    assert len(body["items"]) == 100


def test_pages_do_not_overlap_and_cover_everything(client):
    ids = [c["customer_id"] for c in all_pages(client, "/api/customers")]
    assert len(ids) == 900 and len(set(ids)) == 900 and ids == sorted(ids)


def test_last_partial_page_and_page_beyond_the_end(client):
    last = client.get("/api/customers", params={"page": 5, "page_size": 200}).json()
    assert len(last["items"]) == 100                      # 900 = 4 x 200 + 100
    beyond = client.get("/api/customers", params={"page": 99, "page_size": 200}).json()
    assert beyond["items"] == [] and beyond["total"] == 900


@pytest.mark.parametrize("params", [{"page": 0}, {"page": -1}, {"page_size": 0}, {"page_size": 201}, {"page": "x"}])
def test_bad_pagination_is_rejected_with_422(client, params):
    assert client.get("/api/customers", params=params).status_code == 422


def test_empty_result_is_a_valid_page(client):
    body = client.get("/api/customers", params={"q": "zzzz-no-such-customer"}).json()
    assert body["items"] == [] and body["total"] == 0 and body["pages"] == 0
