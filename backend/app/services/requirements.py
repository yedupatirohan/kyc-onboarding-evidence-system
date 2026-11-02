"""Which KYC requirements apply to a customer.  Pure rule, shared by the generator,
the completeness calculation and the API (one definition, never duplicated)."""
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date

from app.enums import RISK_RANK


@dataclass(frozen=True)
class RequirementSpec:
    """A KYC requirement as plain data (decoupled from the database)."""
    requirement_id: str
    name: str
    is_mandatory: bool
    min_risk_level: str
    validity_months: int | None
    effective_from: date
    effective_to: date | None
    customer_type_ids: frozenset[str]


def is_effective(spec: RequirementSpec, on: date) -> bool:
    """True if the requirement is in force on the given date."""
    return spec.effective_from <= on and (spec.effective_to is None or on <= spec.effective_to)


def applicable_requirements(
    customer_type_id: str,
    risk_level: str,
    specs: Iterable[RequirementSpec],
    as_of: date,
    mandatory_only: bool = False,
) -> list[RequirementSpec]:
    """Requirements that apply to this customer type and risk level on as_of.

    A requirement applies when: the customer type is listed for it, the customer's
    risk is at or above its minimum risk, and it is in force on as_of.
    Result is sorted by requirement_id so every caller sees the same order.
    """
    if risk_level not in RISK_RANK:
        raise ValueError(f"Unknown risk level: {risk_level!r}")
    rank = RISK_RANK[risk_level]
    result = [
        s for s in specs
        if customer_type_id in s.customer_type_ids
        and RISK_RANK[s.min_risk_level] <= rank
        and is_effective(s, as_of)
        and (s.is_mandatory or not mandatory_only)
    ]
    return sorted(result, key=lambda s: s.requirement_id)


def load_requirement_specs(session) -> list[RequirementSpec]:
    """Read requirements from the database into plain RequirementSpec objects."""
    from sqlalchemy import select

    from app.models import KYCRequirement

    rows = session.scalars(select(KYCRequirement).order_by(KYCRequirement.requirement_id))
    return [
        RequirementSpec(
            requirement_id=r.requirement_id,
            name=r.name,
            is_mandatory=r.is_mandatory,
            min_risk_level=r.min_risk_level,
            validity_months=r.validity_months,
            effective_from=r.effective_from,
            effective_to=r.effective_to,
            customer_type_ids=frozenset(t.customer_type_id for t in r.customer_types),
        )
        for r in rows
    ]
