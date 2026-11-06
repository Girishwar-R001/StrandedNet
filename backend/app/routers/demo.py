"""Demonstration controls. All disabled unless DEMO_MODE is on."""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..config import settings
from ..database import get_db
from ..engines import reporting, scenarios, telemetry
from ..engines.scenarios import SILENT, WALKUP_FIRST  # noqa: F401  (used by scripts/scenario_check.py)
from ..models import Journey, User
from ..security import require_operator
from ..seed import DEMO_PASSWORD, SIM_DOMAIN, reset

router = APIRouter(prefix="/api/demo", tags=["demo"])


def _demo_only():
    if not settings.demo_mode:
        raise HTTPException(404, "Not found")


@router.get("/accounts", dependencies=[Depends(_demo_only)])
def accounts(db: Session = Depends(get_db)):
    refs = {j.user_id: j for j in db.query(Journey)}
    rows = []
    for u in db.query(User).order_by(User.id):
        if u.email.endswith(SIM_DOMAIN):
            continue  # Surge crowds are simulated, not people to sign in as.
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
    done = scenarios.simulate_preferences(db, operator)
    db.commit()
    return {"simulated": done}


# ---------------------------------------------------------------- judge control bar
@router.post("/scenario/baseline", dependencies=[Depends(_demo_only)])
def scenario_baseline(_: User = Depends(require_operator), db: Session = Depends(get_db)):
    return scenarios.load_baseline(db)


@router.post("/scenario/surge", dependencies=[Depends(_demo_only)])
def scenario_surge(_: User = Depends(require_operator), db: Session = Depends(get_db)):
    return scenarios.load_surge(db)


@router.post("/run-allocation", dependencies=[Depends(_demo_only)])
def run_allocation(operator: User = Depends(require_operator), db: Session = Depends(get_db)):
    return scenarios.run_and_reserve(db, operator)


@router.post("/carpool-wave", dependencies=[Depends(_demo_only)])
def carpool_wave(operator: User = Depends(require_operator), db: Session = Depends(get_db)):
    return scenarios.carpool_wave(db, operator)


@router.post("/carpool-consent", dependencies=[Depends(_demo_only)])
def carpool_consent(operator: User = Depends(require_operator), db: Session = Depends(get_db)):
    return scenarios.simulate_consent(db, operator)


@router.post("/telemetry/restore", dependencies=[Depends(_demo_only)])
def telemetry_restore(operator: User = Depends(require_operator), db: Session = Depends(get_db)):
    restored = telemetry.restore(db, operator)
    db.commit()
    return {"restored": restored}


@router.post("/telemetry/{fault}", dependencies=[Depends(_demo_only)])
def telemetry_fault(fault: str, operator: User = Depends(require_operator), db: Session = Depends(get_db)):
    if fault not in ("spike", "storm", "gps", "conflict"):
        raise HTTPException(404, "Unknown fault")
    return scenarios.inject(db, fault, operator)
