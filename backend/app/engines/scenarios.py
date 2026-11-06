"""One-click judge scenarios: the baseline, the 3x/-50% crisis surge and telemetry faults.

Presets drive the real engines; nothing here shortcuts allocation or consent. Everything that
stands in for a person is audited as SIMULATED.
"""
import time

from sqlalchemy.orm import Session

from ..models import (CarpoolMatch, CarpoolOffer, Disruption, Journey, JourneyOption, Preference, User,
                      Vehicle)
from ..security import hash_password
from ..seed import DEMO_PASSWORD, SIM_DOMAIN, reset
from ..services import audit, get_setting, now_min, put_setting
from . import allocation, carpool, disruption, reporting, telemetry
from .network import Network

# These parties stay silent in the simulation, so "no preference submitted" can be demonstrated.
SILENT = {"P-06", "P-13"}
# This party prefers a walk-up service over a replacement seat.
WALKUP_FIRST = {"P-02"}

MAX_OFFER_SEATS = 6
MAX_WAVE_ROUNDS = 4
SURGE_REDUCTION_PCT = 50


def simulate_preferences(db: Session, actor) -> int:
    """Stands in for passengers who aren't physically in the demo. Deterministic, audited as
    simulated, and never overwrites a choice a real demo user already made."""
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
                  "SIMULATED passenger response (demo control)", actor)
    return done


def _operator(db: Session) -> User:
    """The reset replaces every user row, so the caller's object is stale after a preset."""
    return db.query(User).filter_by(role="operator").order_by(User.id).first()


def load_baseline(db: Session) -> dict:
    reset(db)
    op = _operator(db)
    disruption.create(db, kind="cancellation", actor=op, service_id="X5")
    simulate_preferences(db, op)
    put_setting(db, "scenario", {"name": "baseline", "label": "Baseline: 24 passengers, 20 seats"})
    audit(db, "scenario_loaded", "baseline", "Baseline scenario loaded", "Judge control bar", op)
    db.commit()
    return {"scenario": "baseline"}


def load_surge(db: Session) -> dict:
    """Always starts from a clean state. Stacking on confirmed bookings would make the numbers
    depend on whatever happened before, and the preset must be reproducible."""
    reset(db, surge=True)
    op = _operator(db)
    disruption.create(db, kind="vehicle_unavailable", actor=op, vehicle_id="RV-2",
                      description="Vehicle B (RV-2) withdrawn: crisis surge fleet cut")
    disruption.create(db, kind="capacity_reduction", actor=op, vehicle_id="RV-1", new_capacity=5,
                      description="Vehicle A (RV-1) reduced from 8 to 5 usable seats: crisis surge fleet cut")
    disruption.create(db, kind="cancellation", actor=op, service_id="X5",
                      description="X5 Cross-City Express cancelled: demand surge across 4 corridors")
    simulate_preferences(db, op)
    put_setting(db, "scenario", {"name": "surge", "label": "Crisis surge: 72 passengers, 10 seats",
                                 "reduction_pct": SURGE_REDUCTION_PCT})
    audit(db, "scenario_loaded", "surge", "Crisis surge loaded: demand x3, official fleet cut by 50%",
          "72 passengers across 4 corridors compete for 10 seats", op)
    db.commit()
    return {"scenario": "surge"}


def run_and_reserve(db: Session, actor) -> dict:
    """The control bar's single click. The Smart allocation page keeps its separate approval."""
    net = Network.load(db)
    run = allocation.run_allocation(db, net, actor)
    db.commit()
    result = allocation.reserve_all(db, net, actor)
    carpool.sync_demand(db, net, actor)
    db.commit()
    return {"seats": run.summary["engine"]["seats"], "confirmed_parties": result["confirmed"],
            "failed": result["failed"], "rollover": sum(p["passengers"] for p in reporting.corridor_pools(db, net))}


def _sim_driver(db: Session, n: int, password_hash: str) -> User:
    email = f"driver{n:02d}@{SIM_DOMAIN}"
    user = db.query(User).filter_by(email=email).first()
    if user is None:
        user = User(email=email, password_hash=password_hash, name=f"Driver-{n:02d} (simulated)",
                    phone=f"+91 90000 2{n:04d}", rides_completed=4 + n % 9, member_since="2025")
        db.add(user)
        db.flush()
    return user


def _bins(parties: list[Journey]) -> list[list[Journey]]:
    """Fills one car at a time. Parties are never split, and share a pickup and destination."""
    bins, lanes = [], {}
    for j in sorted(parties, key=lambda j: (j.origin_stop, j.dest_stop, -j.party_size, j.ref)):
        step_free = bool(set(j.requirements or []) & carpool.STEP_FREE)
        lane = lanes.setdefault((j.origin_stop, j.dest_stop, step_free), [])
        target = next((b for b in lane if sum(x.party_size for x in b) + j.party_size <= MAX_OFFER_SEATS), None)
        if target is None:
            target = []
            lane.append(target)
            bins.append(target)
        target.append(j)
    return bins


def _unmatched(db: Session) -> list[Journey]:
    return [j for j in carpool.unresolved(db) if not j.carpool_opt_out and not carpool._in_pending_match(db, j.id)]


def _offer_for(db: Session, chunk: list[Journey], now: int, password_hash: str, actor) -> CarpoolOffer:
    n = db.query(CarpoolOffer).count() + 1
    step_free = any(set(j.requirements or []) & carpool.STEP_FREE for j in chunk)
    seats = sum(j.party_size for j in chunk)
    offer = CarpoolOffer(
        label=f"CO-{n:02d}", provider_user_id=_sim_driver(db, n, password_hash).id, origin_stop=chunk[0].origin_stop,
        dest_stop=chunk[0].dest_stop, departure=max(now + 10, max(j.dep_earliest for j in chunk)),
        available_seats=seats, vehicle_type="Accessible MPV" if step_free else "Family car", wheelchair=step_free,
        luggage=True, notes="Simulated wave driver")
    db.add(offer)
    db.flush()
    audit(db, "carpool_offer_created", offer.label, f"{seats} seat(s) offered",
          "SIMULATED community driver (surge wave)", actor)
    return offer


def carpool_wave(db: Session, actor) -> dict:
    """Registered drivers along each corridor offer seats. Offers go through the real matcher, so
    every proposal still has to pass route, timing, deadline and suitability checks.

    The matcher may give a driver's seats to anyone compatible along the way, so a planned party
    can miss out. Each round re-reads who is still waiting and sends more drivers for them."""
    net = Network.load(db)
    carpool.sync_demand(db, net, actor)
    pw = hash_password(DEMO_PASSWORD)
    now = now_min(db)
    drivers = made = proposed = 0
    for _ in range(MAX_WAVE_ROUNDS):
        waiting = _unmatched(db)
        if not waiting:
            break
        progress = False
        for chunk in _bins(waiting):
            offer = _offer_for(db, chunk, now, pw, actor)
            result = carpool.match_offer(db, offer, net, actor)
            drivers += 1
            made += len(result["matches"])
            proposed += sum(m.matched_seats for m in result["matches"])
            progress = progress or bool(result["matches"])
            if not result["matches"]:
                offer.status = "withdrawn"  # Nobody compatible left, so no idle offer lingers.
        if not progress:
            break
    db.commit()
    return {"drivers": drivers, "matches": made, "seats_proposed": proposed,
            "still_unmatched": sum(j.party_size for j in _unmatched(db))}


def simulate_consent(db: Session, actor) -> dict:
    """Both sides answer, in the real order: passengers first, then the driver. Real demo drivers
    keep their own decision, so a judge can still press the button themselves."""
    net = Network.load(db)
    answered = confirmed = 0
    rows = db.query(CarpoolMatch).filter(CarpoolMatch.status.in_(carpool.PENDING_MATCH)).order_by(CarpoolMatch.id).all()
    for m in rows:
        if m.status == "awaiting_passenger":
            for mm in list(m.members):
                if mm.acceptance == "pending":
                    carpool.passenger_respond(db, m, mm.journey.user, True, net)
                    answered += 1
        provider = m.offer.provider
        if m.status == "awaiting_provider" and provider.email.endswith(SIM_DOMAIN):
            carpool.provider_respond(db, m, provider, True, net)
            confirmed += 1
    audit(db, "carpool_consent_simulated", "wave",
          f"{answered} passenger acceptances and {confirmed} driver confirmations",
          "SIMULATED mutual consent (demo control)", actor)
    db.commit()
    return {"passengers_accepted": answered, "matches_confirmed": confirmed}


# ---------------------------------------------------------------- telemetry faults
def _packet(v: Vehicle, sensor: str = "primary", **fields) -> dict:
    return {"vehicle_id": v.id, "sensor_id": sensor, "timestamp": time.time(), **fields}


def inject(db: Session, fault: str, actor) -> dict:
    net = Network.load(db)
    target = "RV-3" if fault == "gps" else "RV-1"
    v = db.get(Vehicle, target)
    if fault == "spike":
        result = telemetry.ingest(db, _packet(v, available_seats=v.capacity + 42), net, actor)
    elif fault == "storm":
        frame = _packet(v, available_seats=v.available_seats)
        outcomes = [telemetry.ingest(db, dict(frame), net, actor)["outcome"] for _ in range(15)]
        result = {"outcome": "storm", "vehicle_id": v.id, "frames": 15, "dropped": outcomes.count("duplicate"),
                  "reroutes_triggered": 0}
    elif fault == "gps":
        telemetry.lose_signal(db, v, net)
        result = {"outcome": "stale", "vehicle_id": v.id, "status": telemetry.STALE}
    elif fault == "conflict":
        telemetry.feed(db, v, net)
        result = telemetry.ingest(db, _packet(v, "secondary", status="offline"), net, actor)
    else:
        raise ValueError(f"Unknown fault {fault}")
    db.commit()
    return result


# ---------------------------------------------------------------- read model
def status(db: Session) -> dict:
    """Everything the control bar shows, from the same sources the rest of the dashboard uses."""
    net = Network.load(db)
    telemetry.sweep(db, net)
    vehicles = db.query(Vehicle).order_by(Vehicle.id).all()
    feeds = [telemetry.view(db, v, net) for v in vehicles]
    db.commit()
    journeys = reporting.affected_journeys(db)
    pools = reporting.corridor_pools(db, net)
    in_service = [v for v in vehicles if v.status == "available"]
    return {
        "scenario": get_setting(db, "scenario", {"name": None, "label": "No preset loaded"}),
        "kpis": {
            "stranded_passengers": sum(j.party_size for j in journeys),
            "official_seats": sum(v.capacity for v in in_service),
            "official_seats_free": sum(v.available_seats for v in in_service),
            "over_allocation": reporting.integrity(db)["over_allocated"],
            "carpool_rollover": sum(p["passengers"] for p in pools),
            "carpool_confirmed": sum(p["confirmed"] for p in pools),
        },
        "telemetry": {**telemetry.health(feeds), "vehicles": feeds},
        "corridors": pools,
        "disruptions": db.query(Disruption).filter_by(status="active").count(),
    }
