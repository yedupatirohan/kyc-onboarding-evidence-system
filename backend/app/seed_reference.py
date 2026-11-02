"""Reference (master) data: customer types, KYC requirements and who needs what.

Run from the backend folder:
    python -m app.seed_reference

IMPORTANT: REQUIREMENTS is append-only. A requirement's ID is its position in the
list (position 1 -> KYC-2026-000001), so reordering or inserting would change IDs.
"""
from datetime import date

from sqlalchemy.orm import Session

from app.enums import RISK_RANK
from app.models import CustomerType, KYCRequirement

SEED_EFFECTIVE_FROM = date(2026, 1, 1)

# (customer_type_id, name, description, is_business)
CUSTOMER_TYPES = [
    ("INDIVIDUAL", "Individual", "A natural person opening a personal relationship.", False),
    ("SOLE_PROPRIETOR", "Sole proprietor", "A person trading in their own name.", False),
    ("COMPANY", "Company", "A registered legal entity with directors and shareholders.", True),
    ("TRUST", "Trust", "An arrangement where trustees hold assets for beneficiaries.", True),
]


def _req(name, description, applies_to, min_risk, validity_months, mandatory=True):
    """Small helper so each requirement below is one readable block."""
    return {
        "name": name,
        "description": description,
        "applies_to": tuple(applies_to),
        "min_risk": min_risk,
        "validity_months": validity_months,
        "mandatory": mandatory,
    }


REQUIREMENTS = [
    _req("Government photo ID", "Passport or national ID card.",
         ["INDIVIDUAL", "SOLE_PROPRIETOR"], "LOW", 120),
    _req("Proof of address", "Recent utility bill or bank statement.",
         ["INDIVIDUAL", "SOLE_PROPRIETOR"], "LOW", 12),
    _req("Tax ID proof", "Tax identification number evidence.",
         ["INDIVIDUAL", "SOLE_PROPRIETOR", "COMPANY", "TRUST"], "MEDIUM", None),
    _req("Source of funds declaration", "Where the money used in the relationship comes from.",
         ["INDIVIDUAL", "SOLE_PROPRIETOR", "COMPANY", "TRUST"], "HIGH", 12),
    _req("Source of wealth evidence", "How the customer accumulated their overall wealth.",
         ["INDIVIDUAL", "SOLE_PROPRIETOR", "TRUST"], "HIGH", 24),
    _req("Employment or income proof", "Payslip or employer letter (optional supporting evidence).",
         ["INDIVIDUAL"], "MEDIUM", 12, mandatory=False),
    _req("Trade licence", "Licence to operate the business.",
         ["SOLE_PROPRIETOR"], "LOW", 12),
    _req("Certificate of incorporation", "Proof the company is legally registered.",
         ["COMPANY"], "LOW", None),
    _req("Articles of association", "The company's governing rules.",
         ["COMPANY"], "LOW", None),
    _req("Register of directors and shareholders", "Current list of directors and shareholders.",
         ["COMPANY"], "MEDIUM", 12),
    _req("Beneficial ownership declaration", "Signed declaration naming the real owners.",
         ["COMPANY", "TRUST"], "LOW", 12),
    _req("Authorised signatory ID", "ID of the person allowed to act for the entity.",
         ["COMPANY", "TRUST"], "LOW", 120),
    _req("Trust deed", "The document that created the trust.",
         ["TRUST"], "LOW", None),
    _req("Business address proof", "Proof of the registered business address.",
         ["COMPANY", "TRUST"], "MEDIUM", 12),
    _req("Enhanced due diligence report", "Extra investigation report for high-risk entities.",
         ["COMPANY", "TRUST"], "HIGH", 12),
]


def requirement_id(position: int) -> str:
    """Position 1 -> 'KYC-2026-000001'."""
    return f"KYC-2026-{position:06d}"


def _validate_specs() -> None:
    """Fail loudly at import time if the lists above contain a typo."""
    type_ids = {row[0] for row in CUSTOMER_TYPES}
    for spec in REQUIREMENTS:
        if spec["min_risk"] not in RISK_RANK:
            raise ValueError(f"Unknown risk level {spec['min_risk']!r} in {spec['name']!r}")
        if not spec["applies_to"]:
            raise ValueError(f"{spec['name']!r} applies to no customer type")
        unknown = set(spec["applies_to"]) - type_ids
        if unknown:
            raise ValueError(f"{spec['name']!r} uses unknown customer types {sorted(unknown)}")


_validate_specs()


def seed_reference_data(session: Session) -> dict[str, int]:
    """Insert customer types, requirements and links. Safe to run repeatedly.

    Returns how many rows were created THIS run, e.g.
    {'customer_types': 4, 'requirements': 15, 'links': 29}.
    """
    created = {"customer_types": 0, "requirements": 0, "links": 0}

    types_by_id: dict[str, CustomerType] = {}
    for type_id, name, description, is_business in CUSTOMER_TYPES:
        customer_type = session.get(CustomerType, type_id)
        if customer_type is None:
            customer_type = CustomerType(
                customer_type_id=type_id, name=name,
                description=description, is_business=is_business,
            )
            session.add(customer_type)
            created["customer_types"] += 1
        types_by_id[type_id] = customer_type

    for position, spec in enumerate(REQUIREMENTS, start=1):
        req_id = requirement_id(position)
        requirement = session.get(KYCRequirement, req_id)
        if requirement is None:
            requirement = KYCRequirement(
                requirement_id=req_id,
                name=spec["name"],
                description=spec["description"],
                is_mandatory=spec["mandatory"],
                min_risk_level=spec["min_risk"],
                validity_months=spec["validity_months"],
                effective_from=SEED_EFFECTIVE_FROM,
                effective_to=None,
            )
            session.add(requirement)
            created["requirements"] += 1

        for type_id in spec["applies_to"]:
            customer_type = types_by_id[type_id]
            if requirement not in customer_type.requirements:
                customer_type.requirements.append(requirement)
                created["links"] += 1

    session.commit()
    return created


def main() -> None:
    from sqlalchemy import func, select

    from app.database import Base, SessionLocal, engine
    from app.models import customer_type_requirement

    Base.metadata.create_all(engine)  # make sure the tables exist
    with SessionLocal() as session:
        created = seed_reference_data(session)
        n_types = session.scalar(select(func.count()).select_from(CustomerType))
        n_reqs = session.scalar(select(func.count()).select_from(KYCRequirement))
        n_links = session.scalar(select(func.count()).select_from(customer_type_requirement))

    print(f"Created this run : {created}")
    print(f"Totals in database: customer_types={n_types}, requirements={n_reqs}, links={n_links}")


if __name__ == "__main__":
    main()
