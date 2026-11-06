"""Operator API. Authorisation is applied once at router level, so no route can omit it."""
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from ..database import get_db
from ..engines import allocation as alloc_engine
from ..engines import carpool as cp
from ..engines import disruption as dis
from ..engines import grouping, reporting, scenarios, telemetry
from ..engines.allocation import ReservationError
from ..engines.feasibility import assess_vehicle
from ..engines.network import Network
from ..models import (ACTIVE_ALLOCATION, Allocation, AllocationRun, AuditEvent, CarpoolRequest,
                      CarpoolRequestMember, Disruption, Journey, JourneyOption, PassengerGroup,
                      Stop, User, Vehicle)
from ..schemas import (ConflictDecisionIn, DisruptionIn, OverrideIn, ReasonIn, ReassignIn, RulesIn,
                       TelemetryIn, VehicleIn, VehicleStatusIn)
from ..security import require_operator
from ..services import audit, notify, now_min, put_setting, thresholds, weights

router = APIRouter(prefix="/api/op", tags=["operator"], dependencies=[Depends(require_operator)])


def _allocation(db: Session, allocation_id: int) -> Allocation:
    a = db.get(Allocation, allocation_id)
    if not a:
        raise HTTPException(404, "Allocation not found")
    return a


def _allocation_view(a: Allocation, names: dict) -> dict:
    return {"id": a.id, "ref": a.journey.ref, "journey_id": a.journey_id, "party_size": a.seats,
            "group": a.group.label if a.group else None, "vehicle_id": a.vehicle_id,
            "pickup_stop": names[a.pickup_stop], "pickup_min": a.pickup_min, "arrival_min": a.arrival_min,
            "latest_arrival": a.journey.latest_arrival, "destination": names[a.journey.dest_stop],
            "priority_score": a.priority_score, "breakdown": a.breakdown, "checks": a.checks,
            "explanation": a.explanation, "preference_outcome": a.preference_outcome, "status": a.status,
            "seats_held": a.seats_held, "is_override": a.is_override, "override_reason": a.override_reason,
            "flag_reason": a.flag_reason, "run_id": a.run_id}


def _names(db: Session) -> dict:
    return {s.id: s.name for s in db.query(Stop)}


def _vehicle_view(db: Session, v: Vehicle, net: Network, names: dict) -> dict:
    calls = net.vehicle_calls(v)
    held = db.query(Allocation).filter_by(vehicle_id=v.id, seats_held=True).all()
    return {"id": v.id, "vehicle_type": v.vehicle_type, "capacity": v.capacity,
            "available_seats": v.available_seats, "booked": sum(a.seats for a in held),
            "status": v.status, "wheelchair": v.wheelchair, "luggage": v.luggage, "ready_min": v.ready_min,
            "stops": v.stops, "route_blocked": calls is None,
            "calls": [{"stop": names[s], "time": t} for s, t in calls] if calls else [],
            "manifest": [{"ref": a.journey.ref, "seats": a.seats, "pickup": names[a.pickup_stop],
                          "status": a.status} for a in held]}


# ---------------------------------------------------------------- overview
@router.get("/overview")
def overview(db: Session = Depends(get_db)):
    return reporting.overview(db)


@router.get("/metrics")
def metrics(db: Session = Depends(get_db)):
    return {**reporting.metrics(db), "integrity": reporting.integrity(db)}


@router.get("/stress")
def stress(db: Session = Depends(get_db)):
    return scenarios.status(db)


# ---------------------------------------------------------------- telemetry
@router.post("/telemetry/ingest")
def ingest_telemetry(body: TelemetryIn, user: User = Depends(require_operator), db: Session = Depends(get_db)):
    try:
        result = telemetry.ingest(db, body.model_dump(exclude_none=True), Network.load(db), user)
    except ValueError as e:
        raise HTTPException(404, str(e))
    db.commit()
    return result


@router.post("/telemetry/{vehicle_id}/resolve")
def resolve_telemetry(vehicle_id: str, body: ConflictDecisionIn, user: User = Depends(require_operator),
                      db: Session = Depends(get_db)):
    v = db.get(Vehicle, vehicle_id)
    if not v:
        raise HTTPException(404, "Vehicle not found")
    try:
        telemetry.resolve_conflict(db, v, body.reason, user)
    except ValueError as e:
        raise HTTPException(409, str(e))
    if body.decision == "withdraw":
        dis.create(db, kind="vehicle_unavailable", actor=user, vehicle_id=v.id,
                   description=f"{v.id} confirmed offline by operator after sensor conflict")
    db.commit()
    return {"ok": True}


# ---------------------------------------------------------------- disruptions
@router.get("/disruptions")
def disruptions(db: Session = Depends(get_db)):
    rows = db.query(Disruption).order_by(Disruption.id.desc()).all()
    counts = {}
    for j in reporting.affected_journeys(db):
        counts[j.disruption_id] = counts.get(j.disruption_id, 0) + j.party_size
    return [{"id": d.id, "code": d.code, "kind": d.kind, "description": d.description, "status": d.status,
             "service_id": d.service_id, "vehicle_id": d.vehicle_id, "segment_id": d.segment_id,
             "start_min": d.start_min, "est_end_min": d.est_end_min, "affected": counts.get(d.id, 0)} for d in rows]


@router.post("/disruptions", status_code=201)
def create_disruption(body: DisruptionIn, user: User = Depends(require_operator), db: Session = Depends(get_db)):
    needs = {"cancellation": "service_id", "delay": "service_id", "route_closure": "segment_id",
             "vehicle_unavailable": "vehicle_id", "capacity_reduction": "vehicle_id"}[body.kind]
    if getattr(body, needs) is None:
        raise HTTPException(422, f"{body.kind} requires {needs}")
    if body.kind == "capacity_reduction":
        v = db.get(Vehicle, body.vehicle_id)
        if not v or body.new_capacity is None or body.new_capacity >= v.capacity:
            raise HTTPException(422, "New capacity must be below the current capacity")
    if body.kind == "delay" and body.delay_min < 1:
        raise HTTPException(422, "Delay must be at least 1 minute")
    live = db.query(Disruption).filter_by(status="active", kind=body.kind, service_id=body.service_id,
                                          vehicle_id=body.vehicle_id, segment_id=body.segment_id).first()
    if live:
        raise HTTPException(409, f"{live.code} already covers this")
    d = dis.create(db, kind=body.kind, actor=user, service_id=body.service_id, vehicle_id=body.vehicle_id,
                   segment_id=body.segment_id, delay_min=body.delay_min, new_capacity=body.new_capacity,
                   description=body.description, duration_min=body.duration_min)
    db.commit()
    return {"id": d.id, "code": d.code, "description": d.description}


@router.post("/disruptions/{disruption_id}/resolve")
def resolve_disruption(disruption_id: int, user: User = Depends(require_operator), db: Session = Depends(get_db)):
    d = db.get(Disruption, disruption_id)
    if not d:
        raise HTTPException(404, "Disruption not found")
    try:
        dis.resolve(db, d, user)
    except ValueError as e:
        raise HTTPException(409, str(e))
    db.commit()
    return {"ok": True}


# ---------------------------------------------------------------- passengers and groups
@router.get("/passengers")
def passengers(scope: str = "affected", db: Session = Depends(get_db)):
    names = _names(db)
    q = db.query(Journey).order_by(Journey.ref)
    rows = q.all() if scope == "all" else reporting.affected_journeys(db)
    st = reporting.states(db, rows)
    prefs = reporting.preferences_summary(db)["rows"]
    pref_state = {r["journey_id"]: r["state_label"] for r in prefs}
    return [{"id": j.id, "ref": j.ref, "name": j.user.name, "origin": names[j.origin_stop],
             "destination": names[j.dest_stop], "party_size": j.party_size, "dep_earliest": j.dep_earliest,
             "dep_latest": j.dep_latest, "latest_arrival": j.latest_arrival, "max_wait": j.max_wait,
             "max_walk_m": j.max_walk_m, "requirements": j.requirements, "service": j.booked_service_id,
             "group": j.group.label if j.group else None, "state": st[j.id] if j.id in st else "unaffected",
             "preference": pref_state.get(j.id), "reported_min": j.reported_min,
             "self_reported": j.self_reported} for j in rows]


@router.get("/groups")
def groups(db: Session = Depends(get_db)):
    names = _names(db)
    out = []
    for g in db.query(PassengerGroup).filter_by(status="active").order_by(PassengerGroup.id):
        members = db.query(Journey).filter_by(group_id=g.id).order_by(Journey.ref).all()
        out.append({"id": g.id, "label": g.label, "passengers": g.combined_size, "parties": len(members),
                    "destination_zone": g.destination_zone, "pickup_point": names[g.pickup_stop],
                    "est_minutes": g.est_minutes, "score": g.score, "breakdown": g.breakdown,
                    "explanation": g.explanation, "status": g.status,
                    "members": [{"ref": j.ref, "party_size": j.party_size, "origin": names[j.origin_stop],
                                 "destination": names[j.dest_stop], "dep_earliest": j.dep_earliest,
                                 "dep_latest": j.dep_latest, "requirements": j.requirements} for j in members]})
    return out


@router.post("/groups/run")
def run_groups(user: User = Depends(require_operator), db: Session = Depends(get_db)):
    made = grouping.run_grouping(db, Network.load(db), user)
    db.commit()
    return {"groups": len(made)}


# ---------------------------------------------------------------- vehicles
@router.get("/vehicles")
def vehicles(db: Session = Depends(get_db)):
    net, names = Network.load(db), _names(db)
    return [_vehicle_view(db, v, net, names) for v in db.query(Vehicle).order_by(Vehicle.id)]


@router.post("/vehicles", status_code=201)
def add_vehicle(body: VehicleIn, user: User = Depends(require_operator), db: Session = Depends(get_db)):
    if db.get(Vehicle, body.id):
        raise HTTPException(409, "A vehicle with this ID exists")
    stops = {s.id for s in db.query(Stop)}
    if not set(body.stops) <= stops or len(set(body.stops)) != len(body.stops):
        raise HTTPException(422, "Route must use distinct, known stops")
    v = Vehicle(available_seats=body.capacity, **body.model_dump())
    db.add(v)
    audit(db, "vehicle_added", v.id, f"{v.vehicle_type}, {v.capacity} seats, via {' > '.join(v.stops)}", "", user)
    db.flush()
    dis.recompute(db, f"vehicle {v.id} added", user)
    db.commit()
    return _vehicle_view(db, v, Network.load(db), _names(db))


@router.patch("/vehicles/{vehicle_id}")
def set_vehicle_status(vehicle_id: str, body: VehicleStatusIn, user: User = Depends(require_operator),
                       db: Session = Depends(get_db)):
    v = db.get(Vehicle, vehicle_id)
    if not v:
        raise HTTPException(404, "Vehicle not found")
    if body.status == "unavailable":
        if v.status == "unavailable":
            raise HTTPException(409, "Already unavailable")
        dis.create(db, kind="vehicle_unavailable", actor=user, vehicle_id=v.id)
    else:
        for d in db.query(Disruption).filter_by(status="active", kind="vehicle_unavailable", vehicle_id=v.id):
            dis.resolve(db, d, user)
        v.status = "available"
    db.commit()
    return _vehicle_view(db, v, Network.load(db), _names(db))


# ---------------------------------------------------------------- rules
@router.get("/rules")
def rules(db: Session = Depends(get_db)):
    return {"weights": weights(db), "thresholds": thresholds(db),
            "formula": "priority = Σ weight × factor, each factor normalised to 0–1",
            "constraints": ["Enough seats for the whole party", "Vehicle meets declared accessibility and luggage needs",
                            "Route open or diverted", "Pickup and destination served in order",
                            "Pickup inside the party's departure window", "Arrival before the party's deadline"]}


@router.put("/rules")
def update_rules(body: RulesIn, user: User = Depends(require_operator), db: Session = Depends(get_db)):
    before = weights(db)
    put_setting(db, "weights", body.weights)
    audit(db, "rules_changed", "priority-weights", f"{before} -> {body.weights}", body.reason, user)
    db.commit()
    return {"weights": body.weights}


# ---------------------------------------------------------------- allocation
@router.post("/allocation/run")
def run_allocation(user: User = Depends(require_operator), db: Session = Depends(get_db)):
    run = alloc_engine.run_allocation(db, Network.load(db), user)
    db.commit()
    return {"run_id": run.id, "solver": run.solver, "summary": run.summary}


@router.get("/allocation/latest")
def latest_run(db: Session = Depends(get_db)):
    run = db.query(AllocationRun).order_by(AllocationRun.id.desc()).first()
    return {"run_id": run.id, "solver": run.solver, "summary": run.summary} if run else None


@router.get("/allocations")
def allocations(include_closed: bool = False, db: Session = Depends(get_db)):
    q = db.query(Allocation)
    if not include_closed:
        q = q.filter(Allocation.status.in_(ACTIVE_ALLOCATION))
    names = _names(db)
    rows = q.order_by(Allocation.priority_score.desc(), Allocation.id).all()
    return [_allocation_view(a, names) for a in rows]


@router.post("/allocations/confirm-all")
def confirm_all(user: User = Depends(require_operator), db: Session = Depends(get_db)):
    net = Network.load(db)
    result = alloc_engine.reserve_all(db, net, user)
    cp.sync_demand(db, net, user)
    db.commit()
    return result


@router.post("/allocations/override", status_code=201)
def override(body: OverrideIn, user: User = Depends(require_operator), db: Session = Depends(get_db)):
    j, v = db.get(Journey, body.journey_id), db.get(Vehicle, body.vehicle_id)
    if not j or not v:
        raise HTTPException(404, "Journey or vehicle not found")
    existing = reporting.active_allocation(db, j)
    if existing and existing.status != "proposed":
        raise HTTPException(409, f"{j.ref} already has a {existing.status} allocation")
    net = Network.load(db)
    if existing:
        alloc_engine.release(db, existing, f"Replaced by override: {body.reason}", user, status="rejected")
    try:
        a = alloc_engine.create_confirmed(db, j, v, net, body.reason, user)
    except ReservationError as e:
        db.rollback()
        raise HTTPException(409, str(e))
    cp.sync_demand(db, net, user)
    db.commit()
    return _allocation_view(a, _names(db))


@router.post("/allocations/{allocation_id}/approve")
def approve(allocation_id: int, user: User = Depends(require_operator), db: Session = Depends(get_db)):
    a = _allocation(db, allocation_id)
    try:
        alloc_engine.approve(db, a, user)
    except ReservationError as e:
        raise HTTPException(409, str(e))
    db.commit()
    return _allocation_view(a, _names(db))


@router.post("/allocations/{allocation_id}/confirm")
def confirm(allocation_id: int, user: User = Depends(require_operator), db: Session = Depends(get_db)):
    a, net = _allocation(db, allocation_id), Network.load(db)
    try:
        alloc_engine.reserve(db, a, net, user)
    except ReservationError as e:
        db.rollback()
        raise HTTPException(409, str(e))
    cp.sync_demand(db, net, user)
    db.commit()
    return _allocation_view(a, _names(db))


@router.post("/allocations/{allocation_id}/reject")
def reject(allocation_id: int, body: ReasonIn, user: User = Depends(require_operator), db: Session = Depends(get_db)):
    a = _allocation(db, allocation_id)
    try:
        alloc_engine.release(db, a, body.reason, user, status="rejected")
    except ReservationError as e:
        raise HTTPException(409, str(e))
    cp.sync_demand(db, Network.load(db), user)
    db.commit()
    return {"ok": True}


@router.post("/allocations/{allocation_id}/keep")
def keep(allocation_id: int, body: ReasonIn, user: User = Depends(require_operator), db: Session = Depends(get_db)):
    """Operator accepts a flagged allocation as it stands. Only possible while it holds seats."""
    a = _allocation(db, allocation_id)
    if a.status != "needs_review":
        raise HTTPException(409, "Allocation is not flagged")
    if not a.seats_held:
        raise HTTPException(409, "This party has no physical seat. Reassign or release instead")
    a.status = "confirmed"
    a.is_override = True
    a.override_reason = body.reason
    a.flag_reason = ""
    audit(db, "operator_override", a.journey.ref, f"Kept on {a.vehicle_id} despite flag", body.reason, user)
    notify(db, a.journey.user_id, f"Your seat on {a.vehicle_id} stands", body.reason, "success")
    db.commit()
    return _allocation_view(a, _names(db))


@router.post("/allocations/{allocation_id}/reassign")
def reassign(allocation_id: int, body: ReassignIn, user: User = Depends(require_operator),
             db: Session = Depends(get_db)):
    a = _allocation(db, allocation_id)
    v = db.get(Vehicle, body.vehicle_id)
    if not v:
        raise HTTPException(404, "Vehicle not found")
    if a.status not in ("confirmed", "needs_review"):
        raise HTTPException(409, "Only confirmed or flagged allocations can be reassigned")
    if a.vehicle_id == v.id:
        raise HTTPException(409, "Already on this vehicle")
    net = Network.load(db)
    j = a.journey
    # Check the destination first, so a refused move never loses the seat the party already has.
    res = assess_vehicle(j, v, net, now_min(db), v.available_seats)
    if not res.passes_hard():
        raise HTTPException(409, "Reassignment refused: " + "; ".join(res.failures))
    try:
        alloc_engine.release(db, a, f"Reassigned to {v.id}: {body.reason}", user)
        new = alloc_engine.create_confirmed(db, j, v, net, body.reason, user)
    except ReservationError as e:
        db.rollback()
        raise HTTPException(409, str(e))
    cp.sync_demand(db, net, user)
    db.commit()
    return _allocation_view(new, _names(db))


@router.get("/allocations/{allocation_id}/vehicle-options")
def vehicle_options(allocation_id: int, db: Session = Depends(get_db)):
    a = _allocation(db, allocation_id)
    return _vehicle_fit(db, a.journey, exclude=a.vehicle_id)


@router.get("/journeys/{journey_id}/vehicle-options")
def journey_vehicle_options(journey_id: int, db: Session = Depends(get_db)):
    j = db.get(Journey, journey_id)
    if not j:
        raise HTTPException(404, "Journey not found")
    return _vehicle_fit(db, j)


def _vehicle_fit(db: Session, j: Journey, exclude: str | None = None) -> list[dict]:
    net, now = Network.load(db), now_min(db)
    out = []
    for v in db.query(Vehicle).order_by(Vehicle.id):
        if v.id == exclude:
            continue
        res = assess_vehicle(j, v, net, now, v.available_seats)
        out.append({"vehicle_id": v.id, "seats_left": v.available_seats, "feasible": res.ok,
                    "overridable": res.passes_hard(), "checks": res.checks})
    return out


@router.get("/preferences")
def preferences(db: Session = Depends(get_db)):
    return reporting.preferences_summary(db)


@router.get("/unresolved")
def unresolved(db: Session = Depends(get_db)):
    names = _names(db)
    rows = cp.unresolved(db)
    review = db.query(Allocation).filter_by(status="needs_review").all()
    listings = {}
    for m in db.query(CarpoolRequestMember).filter_by(active=True):
        listings[m.journey_id] = db.get(CarpoolRequest, m.request_id).label
    pending = {r["journey_id"]: r for r in reporting.preferences_summary(db)["rows"]}
    usable = {}
    for j in rows:
        usable[j.id] = db.query(JourneyOption).filter_by(journey_id=j.id, status="active", meets_deadline=True).count()
    return {
        "passengers": sum(j.party_size for j in rows),
        "parties": [{"id": j.id, "ref": j.ref, "party_size": j.party_size, "origin": names[j.origin_stop],
                     "destination": names[j.dest_stop], "latest_arrival": j.latest_arrival,
                     "requirements": j.requirements, "reason": j.outcome_note or "Awaiting allocation run",
                     "carpool_listing": listings.get(j.id), "opted_out": j.carpool_opt_out,
                     "usable_alternatives": usable[j.id],
                     "preference": pending.get(j.id, {}).get("state_label")} for j in rows],
        "needs_review": [_allocation_view(a, names) for a in review],
    }


@router.get("/carpool")
def carpool_monitor(db: Session = Depends(get_db)):
    return reporting.carpool_monitor(db)


@router.post("/carpool/publish")
def publish_demand(user: User = Depends(require_operator), db: Session = Depends(get_db)):
    cp.sync_demand(db, Network.load(db), user)
    db.commit()
    return reporting.carpool_monitor(db)["summary"]


# ---------------------------------------------------------------- heat map (operator-only)
@router.get("/heatmap")
def heatmap(disruption_id: int | None = None, destination: str | None = None,
            status: str = Query("all", pattern="^(all|unresolved|official|carpool|review)$"),
            dep_from: int | None = None, dep_to: int | None = None,
            layer: str = Query("origin", pattern="^(origin|destination)$"), db: Session = Depends(get_db)):
    return reporting.heatmap(db, Network.load(db), disruption_id=disruption_id, destination=destination,
                             status=status, dep_from=dep_from, dep_to=dep_to, layer=layer)


@router.get("/audit")
def audit_log(event_type: str | None = None, q: str | None = None, limit: int = Query(200, le=1000),
              db: Session = Depends(get_db)):
    types = [t[0] for t in db.query(AuditEvent.event_type).distinct().order_by(AuditEvent.event_type)]
    return {"events": reporting.audit_rows(db, event_type, q, limit), "types": types}

