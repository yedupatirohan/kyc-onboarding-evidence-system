"""Step 3E-a: periodic review cases, scheduled from risk level and review frequency."""
from datetime import date, timedelta

from app.config import settings
from app.services.review_schedule import current_cycle_due_date
from generator import ids
from generator.rng import make_rng

ELIGIBLE_STATUSES = {"APPROVED", "SUSPENDED"}     # only onboarded customers are reviewed periodically
LOOK_AHEAD_DAYS = 180
CLOSED_SHARE_WHEN_PAST_DUE = 0.60
IN_PROGRESS_SHARE_WHEN_FUTURE = 0.30
OPENED_SHARE_WHEN_OVERDUE = 0.50
RESOLUTIONS = [
    "No change: risk rating confirmed",
    "Documents refreshed and verified",
    "Risk rating updated after review",
    "Additional information received and accepted",
    "Source of funds re-confirmed",
]
REVIEWERS = [f"analyst_{i:02d}" for i in range(1, 9)]


def generate_reviews(customers, current_risk, n_reviews=None, seed=None, as_of=None) -> list[dict]:
    """One review case per selected customer for their current review cycle.

    Stored status follows the rules in app.services.review_schedule:
      due date passed and not closed -> OVERDUE; otherwise SCHEDULED / IN_PROGRESS / CLOSED.
    """
    n_reviews = settings.n_reviews if n_reviews is None else n_reviews
    as_of = settings.as_of_date if as_of is None else as_of
    rng = make_rng("reviews", seed)

    candidates = []
    for c in customers:
        if c["status"] in ELIGIBLE_STATUSES and c["onboarded_at"] is not None:
            due = current_cycle_due_date(c["onboarded_at"], current_risk[c["customer_id"]], as_of)
            if due <= as_of + timedelta(days=LOOK_AHEAD_DAYS):
                candidates.append((c["customer_id"], due))
    if len(candidates) < n_reviews:
        raise ValueError(f"Only {len(candidates)} customers have a review due; {n_reviews} requested.")

    chosen = sorted(rng.sample(candidates, n_reviews))
    reviews = []
    for customer_id, due in chosen:
        opened = closed = resolution = closed_by = None
        if due < as_of:
            if rng.random() < CLOSED_SHARE_WHEN_PAST_DUE:
                status = "CLOSED"
                opened = due - timedelta(days=rng.randint(0, 20))
                closed = max(opened, min(as_of, due + timedelta(days=rng.randint(-5, 30))))   # never before it opened
                resolution = rng.choice(RESOLUTIONS)
                closed_by = rng.choice(REVIEWERS)
            else:
                status = "OVERDUE"
                if rng.random() < OPENED_SHARE_WHEN_OVERDUE:
                    opened = due - timedelta(days=rng.randint(0, 15))
        elif rng.random() < IN_PROGRESS_SHARE_WHEN_FUTURE:
            status = "IN_PROGRESS"
            opened = as_of - timedelta(days=rng.randint(0, 20))
        else:
            status = "SCHEDULED"
        reviews.append({
            "review_id": ids.review_id(ids.parse_customer_number(customer_id), due.year),
            "customer_id": customer_id,
            "due_date": due,
            "status": status,
            "opened_at": opened,
            "closed_at": closed,
            "resolution": resolution,
            "closed_by": closed_by,
        })
    return reviews
