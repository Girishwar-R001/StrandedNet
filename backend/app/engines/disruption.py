"""Dynamic re-routing (spec 5.2).

Every disruption runs the same pipeline: apply the change to the network, identify who is
affected, regenerate alternatives, regroup, then reassess every live allocation.

Confirmed allocations are never silently rewritten. If one stops working it moves to
`needs_review` with a stated reason, the passenger is told, and an operator must decide.
"""
from sqlalchemy.orm import Session

from ..models import (ACTIVE_ALLOCATION, Allocation, Disruption, Journey, Segment, Service,
                      Vehicle)
from ..services import audit, fmt, notify, now_min
from . import alternatives, grouping
from .allocation import release
from .carpool import sync_demand
from .feasibility import assess_vehicle
from .network import Network, service_edges

KINDS = ("cancellation", "delay", "route_closure", "vehicle_unavailable", "capacity_reduction")
KIND_LABEL = {"cancellation": "Cancellation", "delay": "Delay", "route_closure": "Route closure",
              "vehicle_unavailable": "Vehicle unavailable", "capacity_reduction": "Capacity reduction"}


def _mark_affected(db: Session, j: Journey, d: Disruption, net: Network, why: str) -> None:
    j.status = "affected"
    j.disruption_id = d.id
    j.reported_min = min(j.reported_min, d.start_min)
    notify(db, j.user_id, why,
           f"Your journey to {net.stops[j.dest_stop].name} is affected. Open your dashboard to "
           f"compare alternatives and choose what suits you.", "warning")


def _booked(db: Session, service_id: str) -> list[Journey]:
    return db.query(Journey).filter_by(status="normal", booked_service_id=service_id).order_by(Journey.ref).all()


def create(db: Session, *, kind: str, actor, service_id=None, vehicle_id=None, segment_id=None,
           delay_min=0, new_capacity=None, description="", duration_min=None) -> Disruption:
    now = now_min(db)
    count = db.query(Disruption).count() + 1
    d = Disruption(code=f"D-{count:03d}", kind=kind, service_id=service_id, vehicle_id=vehicle_id,
                   segment_id=segment_id, delay_min=delay_min, start_min=now,
                   est_end_min=now + duration_min if duration_min else None, description=description)
    db.add(d)
    db.flush()
    net = Network.load(db)
    affected = 0

    if kind == "cancellation":
        svc = db.get(Service, service_id)
        svc.status = "cancelled"
        d.description = description or f"{svc.name} cancelled for the evening peak"
        for j in _booked(db, svc.id):
            _mark_affected(db, j, d, net, f"{svc.id} has been cancelled")
            affected += j.party_size

    elif kind == "delay":
        svc = db.get(Service, service_id)
        svc.status, svc.delay_min = "delayed", svc.delay_min + delay_min
        d.description = description or f"{svc.name} delayed by {delay_min} min"
        for j in _booked(db, svc.id):
            base = net.travel(j.origin_stop, j.dest_stop) or 0
            eta = j.dep_earliest + svc.delay_min + base
            if eta > j.latest_arrival:
                _mark_affected(db, j, d, net, f"{svc.id} delay will make you late")
                affected += j.party_size
            else:
                notify(db, j.user_id, f"{svc.id} is running {svc.delay_min} min late",
                       f"You should still arrive by {fmt(j.latest_arrival)}.")

    elif kind == "route_closure":
        seg = db.get(Segment, segment_id)
        edge = frozenset((seg.a, seg.b))
        a_name, b_name = net.stops[seg.a].name, net.stops[seg.b].name
        d.description = description or f"Road closed between {a_name} and {b_name}"
        passing = {s.id for s in db.query(Service) if edge in service_edges(s)}
        for j in db.query(Journey).filter_by(status="normal").order_by(Journey.ref):
            if j.booked_service_id in passing and edge in net.path_edges(j.origin_stop, j.dest_stop):
                _mark_affected(db, j, d, net, f"Road closed between {a_name} and {b_name}")
                affected += j.party_size
        seg.blocked = True

    elif kind == "vehicle_unavailable":
        v = db.get(Vehicle, vehicle_id)
        d.description = description or f"{v.id} withdrawn from service"
        v.status = "unavailable"
        for a in db.query(Allocation).filter(Allocation.vehicle_id == v.id, Allocation.seats_held.is_(True)):
            # The seats no longer physically exist, so they cannot stay held.
            a.seats_held = False
            v.available_seats += a.seats

    elif kind == "capacity_reduction":
        v = db.get(Vehicle, vehicle_id)
        d.prior_capacity = v.capacity
        d.description = description or f"{v.id} capacity reduced from {v.capacity} to {new_capacity}"
        _shrink(db, v, new_capacity, d)

    else:
        raise ValueError(f"Unknown disruption kind {kind}")

    audit(db, "disruption_created", d.code, f"{KIND_LABEL[kind]}: {d.description}",
          f"{affected} passengers newly affected", actor)
    db.flush()
    recompute(db, d.code, actor)
    return d


def _shrink(db: Session, v: Vehicle, new_capacity: int, d: Disruption) -> None:
    held = db.query(Allocation).filter_by(vehicle_id=v.id, seats_held=True) \
             .order_by(Allocation.priority_score, Allocation.id).all()
    booked = sum(a.seats for a in held)
    for a in held:
        if booked <= new_capacity:
            break
        # Lowest priority loses the physical seat first, and is flagged for an operator decision.
        a.seats_held = False
        a.status = "needs_review"
        a.flag_reason = f"{v.id} capacity cut to {new_capacity}: this party no longer has a physical seat"
        booked -= a.seats
        notify(db, a.journey.user_id, f"Your seat on {v.id} is at risk",
               "The vehicle's capacity was reduced. An operator is reviewing your journey.", "warning")
        audit(db, "allocation_flagged", a.journey.ref, a.flag_reason, d.code)
    v.capacity = new_capacity
    v.available_seats = new_capacity - booked


def recompute(db: Session, trigger: str, actor=None) -> None:
    """Steps 3-8 of the spec's disruption pipeline."""
    db.flush()
    net = Network.load(db)
    now = now_min(db)
    alternatives.refresh_all(db, net, now)
    grouping.run_grouping(db, net, actor, f"Network change: {trigger}")
    reassess(db, net, now, trigger, actor)
    sync_demand(db, net, actor)


def reassess(db: Session, net: Network, now: int, trigger: str, actor=None) -> dict:
    flagged = withdrawn = retimed = 0
    live = db.query(Allocation).filter(Allocation.status.in_(ACTIVE_ALLOCATION)).order_by(Allocation.id).all()
    for a in live:
        res = assess_vehicle(a.journey, a.vehicle, net, now)
        over = (a.status in ("proposed", "approved") and a.seats > a.vehicle.available_seats)
        if res.ok and not over:
            if a.status == "needs_review" and not a.seats_held:
                continue
            if res.arrival_min != a.arrival_min or res.pickup_min != a.pickup_min:
                old = fmt(a.arrival_min)
                a.pickup_stop, a.pickup_min, a.arrival_min = res.pickup_stop, res.pickup_min, res.arrival_min
                a.checks = res.checks
                retimed += 1
                if a.status == "confirmed":
                    notify(db, a.journey.user_id, f"{a.vehicle_id} timing changed",
                           f"New arrival {fmt(res.arrival_min)} (was {old}). Your seat is unchanged.")
                audit(db, "allocation_retimed", a.journey.ref,
                      f"{a.vehicle_id} arrival {old} -> {fmt(res.arrival_min)}", trigger, actor)
            continue

        reason = "; ".join(res.failures) or f"{a.vehicle_id} no longer has {a.seats} seats"
        if a.status in ("proposed", "approved"):
            release(db, a, f"Withdrawn after {trigger}: {reason}", actor)
            withdrawn += 1
        elif a.status == "confirmed":
            a.status = "needs_review"
            a.flag_reason = f"After {trigger}: {reason}"
            a.checks = res.checks
            flagged += 1
            notify(db, a.journey.user_id, "Your confirmed journey needs review",
                   f"{reason}. An operator is reviewing it. You have not lost your place silently; "
                   f"we will tell you the outcome.", "warning")
            audit(db, "allocation_flagged", a.journey.ref, a.flag_reason, trigger, actor)
    return {"flagged": flagged, "withdrawn": withdrawn, "retimed": retimed}


def resolve(db: Session, d: Disruption, actor) -> None:
    """Restores the network. Parties already recovered keep their arrangements."""
    if d.status != "active":
        raise ValueError("Disruption is already resolved")
    d.status = "resolved"
    if d.kind == "cancellation":
        db.get(Service, d.service_id).status = "running"
    elif d.kind == "delay":
        svc = db.get(Service, d.service_id)
        svc.delay_min = max(0, svc.delay_min - d.delay_min)
        svc.status = "delayed" if svc.delay_min else "running"
    elif d.kind == "route_closure":
        db.get(Segment, d.segment_id).blocked = False
    elif d.kind == "vehicle_unavailable":
        db.get(Vehicle, d.vehicle_id).status = "available"
    elif d.kind == "capacity_reduction":
        v = db.get(Vehicle, d.vehicle_id)
        grown = d.prior_capacity - v.capacity
        v.capacity, v.available_seats = d.prior_capacity, v.available_seats + grown
    audit(db, "disruption_resolved", d.code, f"Resolved: {d.description}", "", actor)
    recompute(db, d.code, actor)
