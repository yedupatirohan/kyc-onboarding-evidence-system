"""Tests for step 3D: beneficial owners and ownership links."""
import re
from collections import Counter, defaultdict
from datetime import timedelta
from decimal import Decimal

import pytest
from sqlalchemy import create_engine, func, select, text
from sqlalchemy.orm import Session

import app.models  # noqa: F401
from app.config import settings
from app.database import Base
from app.models import BeneficialOwner, OwnershipLink
from app.seed_reference import seed_reference_data
from generator.customers import COUNTRY_WEIGHTS, generate_customers, load_customers
from generator.db_utils import clear_tables
from generator.owners import (
    BUSINESS_TYPES, TOTAL_UNITS, MIN_UNITS, UNIT,
    generate_owners, load_owners, read_business_customers, split_ownership,
)
from generator.rng import make_rng

AS_OF = settings.as_of_date
HUNDRED = Decimal("100.00")


@pytest.fixture(scope="module")
def world():
    cust = generate_customers()
    return cust, generate_owners(cust.customers)


@pytest.fixture(scope="module")
def small_world():
    cust = generate_customers(n_customers=400, n_business=60)
    return cust, generate_owners(cust.customers)


def structures(owners_data):
    """Group links into ownership structures: one per (customer, effective_from)."""
    groups = defaultdict(list)
    for l in owners_data.links:
        groups[(l["customer_id"], l["effective_from"])].append(l)
    return groups


# ---------- split_ownership (the arithmetic core) ----------

@pytest.mark.parametrize("n", [1, 2, 3, 4])
def test_split_sums_to_exactly_100(n):
    rng = make_rng("test_split")
    for _ in range(500):
        shares = split_ownership(n, rng)
        assert len(shares) == n
        assert sum(shares) == HUNDRED
        assert all(s >= Decimal("5.00") for s in shares)
        assert all(s % UNIT == 0 for s in shares)


def test_single_owner_holds_everything():
    assert split_ownership(1, make_rng("x")) == [HUNDRED]


def test_split_rejects_impossible_owner_counts():
    for bad in (0, -1, TOTAL_UNITS // MIN_UNITS + 1):
        with pytest.raises(ValueError):
            split_ownership(bad, make_rng("x"))


def test_float_addition_would_fail_but_decimal_does_not():
    """Why we use Decimal: this is the classic floating-point trap."""
    assert sum([0.1, 0.2]) != 0.3
    assert Decimal("0.1") + Decimal("0.2") == Decimal("0.3")


# ---------- who gets owners ----------

def test_every_business_has_active_owners_and_nobody_else_does(world):
    cust, data = world
    business_ids = {c["customer_id"] for c in cust.customers if c["customer_type_id"] in BUSINESS_TYPES}
    linked = {l["customer_id"] for l in data.links}
    assert len(business_ids) == 1000
    assert linked == business_ids
    active = {l["customer_id"] for l in data.links if l["effective_to"] is None}
    assert active == business_ids


# ---------- reconciliation: the core business rule ----------

def test_every_ownership_structure_sums_to_exactly_100(world):
    groups = structures(world[1])
    assert len(groups) > 1000                         # some businesses have history
    for key, links in groups.items():
        assert sum(l["ownership_pct"] for l in links) == HUNDRED, key


def test_each_share_is_valid(world):
    for l in world[1].links:
        pct = l["ownership_pct"]
        assert Decimal("5.00") <= pct <= HUNDRED
        assert pct == pct.quantize(Decimal("0.01"))


def test_owners_per_structure_between_1_and_4(world):
    sizes = Counter(len(links) for links in structures(world[1]).values())
    assert set(sizes) == {1, 2, 3, 4}


def test_no_owner_appears_twice_in_the_same_structure(world):
    for key, links in structures(world[1]).items():
        owner_ids = [l["owner_id"] for l in links]
        assert len(owner_ids) == len(set(owner_ids)), key


# ---------- identifiers and references ----------

def test_ids_unique_and_formatted(world):
    data = world[1]
    owner_ids = [o["owner_id"] for o in data.owners]
    link_ids = [l["link_id"] for l in data.links]
    assert owner_ids == [f"BO-{n:06d}" for n in range(1, len(owner_ids) + 1)]
    assert len(set(link_ids)) == len(link_ids)
    assert all(re.fullmatch(r"OWN-CUS-\d{6}-\d{2}", i) for i in link_ids)
    assert all(l["link_id"][4:14] == l["customer_id"] for l in data.links)


def test_every_link_points_at_an_existing_owner(world):
    owner_ids = {o["owner_id"] for o in world[1].owners}
    assert {l["owner_id"] for l in world[1].links} <= owner_ids
    assert {l["owner_id"] for l in world[1].links} == owner_ids      # nobody is left unlinked


def test_owner_attributes(world):
    countries = {c for c, _ in COUNTRY_WEIGHTS}
    for o in world[1].owners:
        assert o["full_name"]
        assert o["nationality"] in countries
        assert (AS_OF - o["date_of_birth"]).days >= 25 * 365


# ---------- dates and history ----------

def test_structures_start_at_customer_creation_or_later(world):
    cust, data = world
    created = {c["customer_id"]: c["created_at"] for c in cust.customers}
    first_start = {}
    for l in data.links:
        assert l["effective_from"] >= created[l["customer_id"]]
        assert l["effective_to"] is None or l["effective_to"] >= l["effective_from"]
        first_start[l["customer_id"]] = min(first_start.get(l["customer_id"], l["effective_from"]), l["effective_from"])
    assert all(first_start[cid] == created[cid] for cid in first_start)


def test_history_is_contiguous_and_single_active_structure(world):
    per_customer = defaultdict(list)
    for (customer_id, start), links in structures(world[1]).items():
        per_customer[customer_id].append((start, links))
    with_history = 0
    for customer_id, items in per_customer.items():
        items.sort(key=lambda item: item[0])
        assert len(items) in (1, 2)
        assert items[-1][1][0]["effective_to"] is None                # latest structure is active
        if len(items) == 2:
            with_history += 1
            earlier_end = items[0][1][0]["effective_to"]
            assert earlier_end == items[1][0] - timedelta(days=1)       # no gap, no overlap
            assert all(l["effective_to"] == earlier_end for l in items[0][1])
    assert 0 < with_history < 200


# ---------- shared owners (N:M) ----------

def test_some_owners_are_linked_to_several_customers(world):
    per_owner = defaultdict(set)
    for l in world[1].links:
        per_owner[l["owner_id"]].add(l["customer_id"])
    shared = [o for o, customers in per_owner.items() if len(customers) > 1]
    assert len(shared) > 20
    assert len(shared) / len(per_owner) < 0.15


# ---------- determinism ----------

def test_same_seed_gives_identical_owners(small_world):
    cust, first = small_world
    assert generate_owners(cust.customers) == first


def test_different_seed_gives_different_owners(small_world):
    cust, first = small_world
    assert generate_owners(cust.customers, seed=11) != first


# ---------- database ----------

@pytest.fixture()
def session():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with Session(engine) as s:
        seed_reference_data(s)
        yield s
    engine.dispose()


def test_load_and_reconcile_in_the_database(session, small_world):
    cust, data = small_world
    load_customers(session, cust)
    counts = load_owners(session, data)
    assert counts == {"beneficial_owner": len(data.owners), "ownership_link": len(data.links)}
    assert session.scalar(select(func.count()).select_from(BeneficialOwner)) == len(data.owners)

    # The Phase 1 query: businesses whose ACTIVE ownership exceeds 100 -> none in the baseline
    over = session.execute(text(
        "SELECT customer_id, SUM(ownership_pct) FROM ownership_link "
        "WHERE effective_to IS NULL GROUP BY customer_id HAVING SUM(ownership_pct) <> 100"
    )).all()
    assert over == []


def test_read_business_customers_and_clear(session, small_world):
    cust, data = small_world
    load_customers(session, cust)
    businesses = read_business_customers(session)
    assert len(businesses) == 60
    assert all(b["customer_type_id"] in BUSINESS_TYPES for b in businesses)
    load_owners(session, data)
    clear_tables(session, ["ownership_link", "beneficial_owner"])
    assert session.scalar(select(func.count()).select_from(OwnershipLink)) == 0
