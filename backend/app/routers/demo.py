"""Demonstration controls. All disabled unless DEMO_MODE is on."""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..config import settings
from ..database import get_db
from ..engines import reporting
from ..models import Journey, JourneyOption, Preference, User
from ..security import require_operator
from ..seed import DEMO_PASSWORD, reset
from ..services import audit

router = APIRouter(prefix="/api/demo", tags=["demo"])

# These parties stay silent in the simulation, so "no preference submitted" can be demonstrated.
SILENT = {"P-06", "P-13"}
# This party prefers a walk-up service over a replacement seat.
WALKUP_FIRST = {"P-02"}


def _demo_only():
    if not settings.demo_mode:
        raise HTTPException(404, "Not found")


@router.get("/accounts", dependencies=[Depends(_demo_only)])
def accounts(db: Session = Depends(get_db)):
    refs = {j.user_id: j for j in db.query(Journey)}
    rows = []
    for u in db.query(User).order_by(User.id):
        j = refs.get(u.id)
        rows.append({"email": u.email, "name": u.name, "role": u.role, "ref": j.ref if j else None,
                     "party_size": j.party_size if j else None})
    return {"password": DEMO_PASSWORD, "accounts": rows}


@router.post("/reset", dependencies=[Depends(_demo_only)])
def reset_demo(_: User = Depends(require_operator), db: Session = Depends(get_db)):
    reset(db)
    return {"ok": True}


@router.get("/progress", dependencies=[Depends(_demo_only)])
def progress(_: User = Depends(require_operator), db: Session = Depends(get_db)):
    return reporting.demo_progress(db)


@router.post("/simulate-preferences", dependencies=[Depends(_demo_only)])
def simulate_preferences(operator: User = Depends(require_operator), db: Session = Depends(get_db)):
    """Stands in for the passengers who aren't physically in the demo. Deterministic, clearly
    audited as simulated, and never overwrites a choice a real demo user already made."""
    done = 0
    for j in db.query(Journey).filter_by(status="affected").order_by(Journey.ref):
        if j.ref in SILENT or db.query(Preference).filter_by(journey_id=j.id).first():
            continue
        options = db.query(JourneyOption).filter_by(journey_id=j.id, status="active", meets_deadline=True).all()
        options.sort(key=lambda o: (not o.reservable, o.arrival, o.key))
        if j.ref in WALKUP_FIRST:
            options.sort(key=lambda o: (o.reservable, o.arrival, o.key))
        for rank, o in enumerate(options[:2], 1):
            db.add(Preference(journey_id=j.id, option_id=o.id, rank=rank))
        if options:
            done += 1
            audit(db, "preference_submitted", j.ref,
                  "; ".join(f"Choice {n}: {o.title}" for n, o in enumerate(options[:2], 1)),
                  "SIMULATED passenger response (demo control)", operator)
    db.commit()
    return {"simulated": done}
