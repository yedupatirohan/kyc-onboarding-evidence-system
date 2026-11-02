"""Step 3B: customers, business profiles and risk-rating history.

Pure generation (no database) plus a loader.  Run from the backend folder:
    python -m generator.customers
"""
from dataclasses import dataclass
from datetime import date, timedelta

from app.config import settings
from app.enums import CustomerStatus
from app.services.risk import compute_risk_score, risk_level_for_score
from generator import ids
from generator.rng import make_faker, make_rng

# Share of businesses that are companies (the rest are trusts), and of non-businesses
# that are individuals (the rest are sole proprietors).
COMPANY_SHARE_OF_BUSINESS = 0.85
INDIVIDUAL_SHARE_OF_NON_BUSINESS = 6 / 7

# Status mix (decision D13): about half approved and complete, the rest partially documented.
STATUS_SHARES = [
    (CustomerStatus.APPROVED.value, 0.50),
    (CustomerStatus.UNDER_REVIEW.value, 0.25),
    (CustomerStatus.PROSPECT.value, 0.175),
    (CustomerStatus.SUSPENDED.value, 0.0375),
    # CLOSED takes whatever remains, so the quotas always add up to the total.
]

# When each kind of customer was created (keeps the story realistic).
CREATED_WINDOWS = {
    "APPROVED": (date(2024, 1, 1), date(2026, 6, 30)),
    "SUSPENDED": (date(2024, 1, 1), date(2026, 6, 30)),
    "CLOSED": (date(2024, 1, 1), date(2026, 6, 30)),
    "UNDER_REVIEW": (date(2026, 3, 1), date(2026, 9, 30)),
    "PROSPECT": (date(2026, 8, 1), date(2026, 10, 15)),
}
STATUSES_WITH_ONBOARDING = {"APPROVED", "SUSPENDED", "CLOSED"}

COUNTRY_WEIGHTS = [
    ("IN", 60), ("GB", 8), ("US", 8), ("DE", 4), ("AU", 4), ("SG", 4),
    ("AE", 6), ("PA", 2), ("NG", 2), ("MM", 2),
]
EXTRA_POINTS_MAX = 55          # simulated "other risk factors", see app/services/risk.py
MIN_DAYS_BEFORE_REASSESSMENT = 60
SHARE_WITH_REASSESSMENT = 0.15


@dataclass
class GeneratedCustomers:
    customers: list[dict]
    business_profiles: list[dict]
    risk_ratings: list[dict]


def type_counts(n_customers: int, n_business: int) -> dict[str, int]:
    """Exact number of customers per type, e.g. 8000/1000 -> 6000/1000/850/150."""
    if not (0 <= n_business <= n_customers):
        raise ValueError("n_business must be between 0 and n_customers")
    companies = round(n_business * COMPANY_SHARE_OF_BUSINESS)
    non_business = n_customers - n_business
    individuals = round(non_business * INDIVIDUAL_SHARE_OF_NON_BUSINESS)
    return {
        "INDIVIDUAL": individuals,
        "SOLE_PROPRIETOR": non_business - individuals,
        "COMPANY": companies,
        "TRUST": n_business - companies,
    }


def status_counts(n_customers: int) -> dict[str, int]:
    """Exact number of customers per status; CLOSED gets the remainder."""
    counts, used = {}, 0
    for status, share in STATUS_SHARES:
        counts[status] = round(n_customers * share)
        used += counts[status]
    counts[CustomerStatus.CLOSED.value] = n_customers - used
    return counts


def _expand(counts: dict[str, int]) -> list[str]:
    return [name for name, n in counts.items() for _ in range(n)]


def _random_date(rng, start: date, end: date) -> date:
    return start + timedelta(days=rng.randint(0, (end - start).days))


def generate_customers(
    n_customers: int | None = None,
    n_business: int | None = None,
    seed: int | None = None,
    as_of: date | None = None,
) -> GeneratedCustomers:
    n_customers = settings.n_customers if n_customers is None else n_customers
    n_business = settings.n_business if n_business is None else n_business
    as_of = settings.as_of_date if as_of is None else as_of

    # Independent streams: changing one part never shifts the others.
    type_rng = make_rng("customer_types", seed)
    status_rng = make_rng("customer_status", seed)
    attr_rng = make_rng("customer_attributes", seed)
    risk_rng = make_rng("risk_ratings", seed)
    fake = make_faker("customers", seed)

    types = _expand(type_counts(n_customers, n_business))
    statuses = _expand(status_counts(n_customers))
    type_rng.shuffle(types)
    status_rng.shuffle(statuses)

    country_codes = [c for c, _ in COUNTRY_WEIGHTS]
    country_weights = [w for _, w in COUNTRY_WEIGHTS]

    customers, profiles, ratings = [], [], []

    for number in range(1, n_customers + 1):
        customer_type = types[number - 1]
        status = statuses[number - 1]
        is_business = customer_type in ("COMPANY", "TRUST")

        country = attr_rng.choices(country_codes, country_weights)[0]
        start, end = CREATED_WINDOWS[status]
        created_at = _random_date(attr_rng, start, end)
        onboarded_at = (
            created_at + timedelta(days=attr_rng.randint(3, 45))
            if status in STATUSES_WITH_ONBOARDING else None
        )

        if customer_type == "COMPANY":
            name, dob = fake.company(), None
        elif customer_type == "TRUST":
            name, dob = f"{fake.last_name()} Family Trust", None
        else:
            name = fake.name()
            dob = as_of - timedelta(days=attr_rng.randint(21 * 365, 80 * 365))

        customer_id = ids.customer_id(number)
        customers.append({
            "customer_id": customer_id,
            "customer_type_id": customer_type,
            "full_name": name,
            "date_of_birth": dob,
            "country_code": country,
            "email": fake.safe_email(),   # example.com style domains only
            "status": status,
            "created_at": created_at,
            "onboarded_at": onboarded_at,
        })

        if is_business:
            incorporated = _random_date(attr_rng, date(1985, 1, 1), created_at - timedelta(days=180))
            profiles.append({
                "customer_id": customer_id,
                "registration_number": f"REG-{incorporated.year}-{number:06d}",
                "incorporation_date": incorporated,
                "country_of_incorporation": country,
            })

        # ---- risk rating history -------------------------------------------------
        extra = risk_rng.randint(0, EXTRA_POINTS_MAX)
        current_score = compute_risk_score(customer_type, country, extra)
        eligible = (as_of - created_at).days >= MIN_DAYS_BEFORE_REASSESSMENT
        has_history = eligible and risk_rng.random() < SHARE_WITH_REASSESSMENT

        if has_history:
            change_date = created_at + timedelta(
                days=risk_rng.randint(30, (as_of - created_at).days - 1)
            )
            delta = risk_rng.choice([-1, 1]) * risk_rng.randint(5, 20)
            earlier_score = max(0, min(100, current_score + delta))
            ratings.append(_rating(number, 1, earlier_score, created_at,
                                   change_date - timedelta(days=1), "Initial onboarding risk assessment"))
            ratings.append(_rating(number, 2, current_score, change_date,
                                   None, "Periodic risk reassessment"))
        else:
            ratings.append(_rating(number, 1, current_score, created_at,
                                   None, "Initial onboarding risk assessment"))

    return GeneratedCustomers(customers, profiles, ratings)


def _rating(number, sequence, score, effective_from, effective_to, reason) -> dict:
    return {
        "rating_id": ids.risk_rating_id(number, sequence),
        "customer_id": ids.customer_id(number),
        "level": risk_level_for_score(score),   # level is DERIVED from the score
        "score": score,
        "effective_from": effective_from,
        "effective_to": effective_to,
        "reason": reason,
    }


def load_customers(session, data: GeneratedCustomers) -> dict[str, int]:
    """Bulk-insert the generated rows (parents first). Master data must already exist."""
    from sqlalchemy import insert

    from app.models import BusinessProfile, Customer, RiskRating

    session.execute(insert(Customer), data.customers)
    if data.business_profiles:
        session.execute(insert(BusinessProfile), data.business_profiles)
    session.execute(insert(RiskRating), data.risk_ratings)
    session.commit()
    return {
        "customer": len(data.customers),
        "business_profile": len(data.business_profiles),
        "risk_rating": len(data.risk_ratings),
    }


def main() -> None:
    from collections import Counter

    from app.database import Base, SessionLocal, engine
    from app.seed_reference import seed_reference_data
    from generator.db_utils import clear_generated_data

    Base.metadata.create_all(engine)
    with SessionLocal() as session:
        seed_reference_data(session)          # safe to repeat
        clear_generated_data(session)         # regenerate from a clean slate
        data = generate_customers()
        counts = load_customers(session, data)

    print(f"Inserted: {counts}")
    current = [r for r in data.risk_ratings if r["effective_to"] is None]
    print("Customer types :", dict(Counter(c["customer_type_id"] for c in data.customers)))
    print("Customer status:", dict(Counter(c["status"] for c in data.customers)))
    print("Current risk   :", dict(Counter(r["level"] for r in current)))


if __name__ == "__main__":
    main()
