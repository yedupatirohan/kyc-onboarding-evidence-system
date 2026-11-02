"""Step 3D: beneficial owners and ownership links for business customers.

Rules (decisions D17 to D19):
  * every business has 1 to 4 owners; their active percentages sum to EXACTLY 100.00
  * about 5% of owner slots reuse an existing owner, so one person can own several businesses
  * about 8% of businesses changed ownership once; the old structure is kept as history

Percentages are built from whole quarter-percent units (0.25%) and Decimal, never float,
so the total is exactly 100.00 with no rounding error.

Run from the backend folder (after python -m generator.customers):
    python -m generator.owners
"""
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal

from app.config import settings
from generator import ids
from generator.customers import COUNTRY_WEIGHTS
from generator.rng import make_faker, make_rng

BUSINESS_TYPES = ("COMPANY", "TRUST")

OWNER_COUNT_WEIGHTS = {1: 0.25, 2: 0.40, 3: 0.25, 4: 0.10}
UNIT = Decimal("0.25")            # one unit = 0.25 percent
TOTAL_UNITS = 400                 # 400 units x 0.25 = 100.00 percent
MIN_UNITS = 20                    # every owner holds at least 5 percent
REUSE_OWNER_SHARE = 0.05
OWNERSHIP_CHANGE_SHARE = 0.08
MIN_DAYS_BEFORE_CHANGE = 120


@dataclass
class GeneratedOwners:
    owners: list[dict]
    links: list[dict]


def split_ownership(n_owners: int, rng) -> list[Decimal]:
    """Split 100.00 percent into n_owners shares, each >= 5%, in 0.25% steps.

    Stars-and-bars: after giving everyone the minimum, the remaining units are cut
    at random points. Integer arithmetic first, Decimal only at the end.
    """
    if not (1 <= n_owners <= TOTAL_UNITS // MIN_UNITS):
        raise ValueError(f"n_owners must be between 1 and {TOTAL_UNITS // MIN_UNITS}, got {n_owners}")
    remaining = TOTAL_UNITS - n_owners * MIN_UNITS
    cuts = sorted(rng.randint(0, remaining) for _ in range(n_owners - 1))
    bounds = [0] + cuts + [remaining]
    units = [MIN_UNITS + bounds[i + 1] - bounds[i] for i in range(n_owners)]
    assert sum(units) == TOTAL_UNITS
    return [UNIT * u for u in units]


def generate_owners(
    customers: list[dict],
    seed: int | None = None,
    as_of: date | None = None,
) -> GeneratedOwners:
    """customers: dicts with customer_id, customer_type_id, created_at (any types; non-business are skipped)."""
    as_of = settings.as_of_date if as_of is None else as_of

    rng = make_rng("owners", seed)
    fake = make_faker("owners", seed)
    country_codes = [c for c, _ in COUNTRY_WEIGHTS]
    country_weights = [w for _, w in COUNTRY_WEIGHTS]
    count_values = list(OWNER_COUNT_WEIGHTS)
    count_weights = list(OWNER_COUNT_WEIGHTS.values())

    owners: list[dict] = []
    links: list[dict] = []

    def new_owner() -> str:
        owner_id = ids.owner_id(len(owners) + 1)
        owners.append({
            "owner_id": owner_id,
            "full_name": fake.name(),
            "date_of_birth": as_of - timedelta(days=rng.randint(25 * 365, 85 * 365)),
            "nationality": rng.choices(country_codes, country_weights)[0],
        })
        return owner_id

    def pick_owners(n: int) -> list[str]:
        """n distinct owners; each slot is a new person, or (rarely) an existing one."""
        chosen: list[str] = []
        for _ in range(n):
            reuse = owners and rng.random() < REUSE_OWNER_SHARE
            if reuse:
                candidate = owners[rng.randrange(len(owners))]["owner_id"]
                if candidate not in chosen:
                    chosen.append(candidate)
                    continue
            chosen.append(new_owner())
        return chosen

    for customer in customers:
        if customer["customer_type_id"] not in BUSINESS_TYPES:
            continue
        customer_id = customer["customer_id"]
        number = ids.parse_customer_number(customer_id)
        created = customer["created_at"]
        sequence = 0

        def add_structure(start: date, end: date | None) -> None:
            nonlocal sequence
            n = rng.choices(count_values, count_weights)[0]
            for owner_id, pct in zip(pick_owners(n), split_ownership(n, rng)):
                sequence += 1
                links.append({
                    "link_id": ids.ownership_link_id(number, sequence),
                    "customer_id": customer_id,
                    "owner_id": owner_id,
                    "ownership_pct": pct,
                    "effective_from": start,
                    "effective_to": end,
                })

        days_available = (as_of - created).days
        if days_available >= MIN_DAYS_BEFORE_CHANGE and rng.random() < OWNERSHIP_CHANGE_SHARE:
            change_date = created + timedelta(days=rng.randint(60, days_available - 1))
            add_structure(created, change_date - timedelta(days=1))   # earlier structure (history)
            add_structure(change_date, None)                           # current structure
        else:
            add_structure(created, None)

    return GeneratedOwners(owners, links)


def load_owners(session, data: GeneratedOwners) -> dict[str, int]:
    """Bulk-insert owners first, then the links that point at them."""
    from sqlalchemy import insert

    from app.models import BeneficialOwner, OwnershipLink

    session.execute(insert(BeneficialOwner), data.owners)
    session.execute(insert(OwnershipLink), data.links)
    session.commit()
    return {"beneficial_owner": len(data.owners), "ownership_link": len(data.links)}


def read_business_customers(session) -> list[dict]:
    from sqlalchemy import select

    from app.models import Customer

    return [
        dict(row) for row in session.execute(
            select(Customer.customer_id, Customer.customer_type_id, Customer.created_at)
            .where(Customer.customer_type_id.in_(BUSINESS_TYPES))
            .order_by(Customer.customer_id)
        ).mappings()
    ]


def main() -> None:
    from collections import Counter

    from app.database import Base, SessionLocal, engine
    from generator.db_utils import clear_tables

    Base.metadata.create_all(engine)
    with SessionLocal() as session:
        businesses = read_business_customers(session)
        if not businesses:
            raise SystemExit("No business customers found. Run: python -m generator.customers")
        clear_tables(session, ["ownership_link", "beneficial_owner"])
        data = generate_owners(businesses)
        counts = load_owners(session, data)

    active = [l for l in data.links if l["effective_to"] is None]
    owners_per_business = Counter(Counter(l["customer_id"] for l in active).values())
    shared = sum(1 for n in Counter(l["owner_id"] for l in data.links).values() if n > 1)
    print(f"Inserted: {counts}")
    print("Businesses by number of active owners:", dict(sorted(owners_per_business.items())))
    print("Businesses with ownership history:", len({l["customer_id"] for l in data.links if l["effective_to"] is not None}))
    print("Owners linked to more than one link:", shared)


if __name__ == "__main__":
    main()
