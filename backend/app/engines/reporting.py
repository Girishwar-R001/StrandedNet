"""Read models: dashboards, the operator heat map, success metrics and demo progress."""
from collections import Counter, defaultdict

from sqlalchemy.orm import Session

from ..models import (ACTIVE_ALLOCATION, Allocation, AllocationRun, AuditEvent, CarpoolMatch,
                      CarpoolMatchMember, CarpoolOffer, CarpoolReport, CarpoolRequest, Disruption, Journey, JourneyOption, PassengerGroup,
                      Preference, Segment, Service, Vehicle)
from .carpool import LIVE_MATCH, PENDING_MATCH
from .network import Network

CELL_DEG = 0.01  # about 1.1 km. Heat-map output never carries finer precision than this.


# ---------------------------------------------------------------- journey state
def active_allocation(db: Session, j: Journey) -> Allocation | None:
    return db.query(Allocation).filter(Allocation.journey_id == j.id,
                                       Allocation.status.in_(ACTIVE_ALLOCATION)).first()


def recovery_state(j: Journey, alloc: Allocation | None) -> str:
    """One canonical status per party, shared by every dashboard and metric."""
    if j.status == "normal":
        return "unaffected"
    if j.status == "self_resolved":
        return "self_resolved"
    if j.status == "carpool_confirmed":
        return "carpool_confirmed"
    if alloc:
        return {"proposed": "proposed", "approved": "approved", "confirmed": "official_confirmed",
                "needs_review": "needs_review"}[alloc.status]
    return "unresolved"


def affected_journeys(db: Session, disruption_id: int | None = None) -> list[Journey]:
    q = db.query(Journey).filter(Journey.status != "normal")
    if disruption_id:
        q = q.filter(Journey.disruption_id == disruption_id)
    return q.order_by(Journey.ref).all()


def states(db: Session, journeys: list[Journey]) -> dict[int, str]:
    allocs = {a.journey_id: a for a in db.query(Allocation).filter(Allocation.status.in_(ACTIVE_ALLOCATION))}
    return {j.id: recovery_state(j, allocs.get(j.id)) for j in journeys}


# ---------------------------------------------------------------- preferences
def option_availability(db: Session, o: JourneyOption, party: int) -> dict:
    if o.status != "active":
        return {"code": "unavailable", "label": "No longer available", "seats_left": None}
    if not o.reservable:
        return {"code": "walk_up", "label": "Walk-up, seat not guaranteed", "seats_left": None}
    v = db.get(Vehicle, o.vehicle_id)
    if v.available_seats >= party:
        return {"code": "available", "label": f"{v.available_seats} of {v.capacity} seats free",
                "seats_left": v.available_seats}
    return {"code": "full", "label": f"Only {v.available_seats} left for a party of {party}"
            if v.available_seats else "Full", "seats_left": v.available_seats}


def preference_state(first: dict | None, second: dict | None) -> tuple[str, str]:
    """The four operator-facing outcomes from spec 9.2."""
    if first is None:
        return "none_submitted", "No preference submitted"
    usable = ("available", "walk_up")
    if first["availability"]["code"] in usable:
        return "first_available", "First choice available"
    if second and second["availability"]["code"] in usable:
        return "second_feasible", "First choice full; second choice feasible"
    return "none_feasible", "No selected option feasible"


def _pref_item(db: Session, p: Preference | None, party: int) -> dict | None:
    if p is None:
        return None
    return {"option_id": p.option_id, "title": p.option.title, "kind": p.option.kind,
            "vehicle_id": p.option.vehicle_id, "status": p.status,
            "availability": option_availability(db, p.option, party)}


def preferences_summary(db: Session) -> dict:
    journeys = [j for j in affected_journeys(db)]
    st = states(db, journeys)
    rows, tally = [], defaultdict(lambda: {"first": 0, "second": 0, "passengers": 0})
    not_selected = 0
    for j in journeys:
        prefs = {p.rank: p for p in db.query(Preference).filter_by(journey_id=j.id)}
        first, second = _pref_item(db, prefs.get(1), j.party_size), _pref_item(db, prefs.get(2), j.party_size)
        code, label = preference_state(first, second)
        if not prefs and j.status == "affected":
            not_selected += 1
        for rank, item in ((1, first), (2, second)):
            if item:
                key = item["vehicle_id"] or item["title"]
                tally[key]["first" if rank == 1 else "second"] += 1
                tally[key]["passengers"] += j.party_size if rank == 1 else 0
                tally[key]["label"] = (f"Replacement {item['vehicle_id']}" if item["vehicle_id"] else item["title"])
                tally[key]["reservable"] = bool(item["vehicle_id"])
                tally[key]["availability"] = item["availability"]["label"]
        rows.append({"journey_id": j.id, "ref": j.ref, "party_size": j.party_size,
                     "group": j.group.label if j.group else None, "first": first, "second": second,
                     "state": code, "state_label": label, "recovery": st[j.id],
                     "submitted_at": prefs[1].submitted_at.isoformat() if 1 in prefs else None})
    options = sorted(tally.values(), key=lambda t: (-t["passengers"], t["label"]))
    return {"rows": rows, "options": options, "not_selected": not_selected,
            "submitted": sum(1 for r in rows if r["first"]), "total": len(rows)}


# ---------------------------------------------------------------- heat map
def _cell(lat: float, lng: float) -> tuple[int, int]:
    return round(lat / CELL_DEG), round(lng / CELL_DEG)


def heatmap(db: Session, net: Network, *, disruption_id=None, destination=None, status=None,
            dep_from=None, dep_to=None, layer="origin") -> dict:
    """Aggregates to about 1 km grid cells server-side. Raw coordinates, names and references
    are never placed in the response, so the client cannot reveal what it does not receive."""
    journeys = affected_journeys(db, disruption_id)
    st = states(db, journeys)
    groups = {"unresolved": ("unresolved",), "official": ("official_confirmed", "approved", "proposed"),
              "carpool": ("carpool_confirmed",), "review": ("needs_review",)}

    def keep(j: Journey) -> bool:
        if destination and j.dest_stop != destination:
            return False
        if status and status != "all" and st[j.id] not in groups.get(status, ()):
            return False
        if dep_from is not None and j.dep_latest < dep_from:
            return False
        if dep_to is not None and j.dep_earliest > dep_to:
            return False
        return True

    chosen = [j for j in journeys if keep(j)]
    cells: dict = {}
    zones: dict = defaultdict(lambda: {"affected": 0, "unresolved": 0, "official": 0, "carpool": 0,
                                       "destination_demand": 0, "capacity": 0, "destinations": Counter()})
    for j in chosen:
        lat, lng = (net.stops[j.dest_stop].lat, net.stops[j.dest_stop].lng) if layer == "destination" else (j.lat, j.lng)
        key = _cell(lat, lng)
        c = cells.setdefault(key, {"affected": 0, "unresolved": 0, "official": 0, "carpool": 0,
                                   "zones": Counter(), "destinations": Counter()})
        origin_zone = net.stops[j.origin_stop].zone
        dest = net.stops[j.dest_stop]
        state = st[j.id]
        bucket = ("unresolved" if state in ("unresolved", "needs_review")
                  else "carpool" if state == "carpool_confirmed"
                  else "official" if state in groups["official"] else None)
        for target in (c, zones[origin_zone]):
            target["affected"] += j.party_size
            if bucket:
                target[bucket] += j.party_size
            target["destinations"][dest.name] += j.party_size
        c["zones"][dest.zone if layer == "destination" else origin_zone] += j.party_size
        zones[dest.zone]["destination_demand"] += j.party_size

    for v in db.query(Vehicle).filter_by(status="available"):
        for zone in {net.stops[s].zone for s in v.stops}:
            zones[zone]["capacity"] += v.available_seats

    out_cells = []
    for (la, ln), c in sorted(cells.items()):
        out_cells.append({
            "id": f"{la}_{ln}", "lat": round(la * CELL_DEG, 2), "lng": round(ln * CELL_DEG, 2),
            "size_deg": CELL_DEG, "affected": c["affected"], "unresolved": c["unresolved"],
            "official": c["official"], "carpool": c["carpool"],
            "zone": c["zones"].most_common(1)[0][0],
            "top_destinations": [{"name": n, "passengers": k} for n, k in c["destinations"].most_common(3)],
        })

    closed = []
    for seg in db.query(Segment).filter_by(blocked=True):
        closed.append({"from": seg.a, "to": seg.b})
    cancelled = [{"id": s.id, "name": s.name, "branches": s.branches}
                 for s in db.query(Service).filter(Service.status != "running")]
    return {
        "layer": layer, "cells": out_cells,
        "zones": [{"zone": z, **{k: v for k, v in d.items() if k != "destinations"},
                   "top_destinations": [{"name": n, "passengers": k} for n, k in d["destinations"].most_common(3)]}
                  for z, d in sorted(zones.items())],
        "max_intensity": max((c["affected"] for c in out_cells), default=0),
        "total": sum(j.party_size for j in chosen),
        "closed_segments": closed, "disrupted_services": cancelled,
        "cell_size_m": 1100, "simulated": True,
    }


# ---------------------------------------------------------------- metrics
def integrity(db: Session) -> dict:
    """Independently reconciles seat accounting. `over_allocated` must always be zero."""
    over = 0
    rows = []
    for v in db.query(Vehicle).order_by(Vehicle.id):
        held = sum(a.seats for a in db.query(Allocation).filter_by(vehicle_id=v.id, seats_held=True))
        ok = held <= v.capacity and v.capacity - v.available_seats == held and v.available_seats >= 0
        over += 0 if ok else 1
        rows.append({"vehicle": v.id, "capacity": v.capacity, "held": held,
                     "available": v.available_seats, "ok": ok})
    for o in db.query(CarpoolOffer):
        live = db.query(CarpoolMatch).filter(CarpoolMatch.offer_id == o.id, CarpoolMatch.status.in_(LIVE_MATCH))
        if sum(m.matched_seats for m in live) > o.available_seats:
            over += 1
    return {"over_allocated": over, "vehicles": rows}


def metrics(db: Session) -> dict:
    journeys = affected_journeys(db)
    st = states(db, journeys)
    total = sum(j.party_size for j in journeys)
    seats = Counter()
    for j in journeys:
        seats[st[j.id]] += j.party_size

    allocs = db.query(Allocation).filter(Allocation.status == "confirmed").all()
    capacity = sum(v.capacity for v in db.query(Vehicle))
    official = seats["official_confirmed"]
    carpool = seats["carpool_confirmed"]
    unmet_after_official = total - official - seats["self_resolved"]

    pref_rows = [a for a in allocs if a.preference_outcome != "no_preference"]
    satisfied = sum(1 for a in pref_rows if a.preference_outcome in ("first_choice", "second_choice"))
    extras = []
    recovery = []
    net = Network.load(db)
    for a in allocs:
        direct = net.travel(a.journey.origin_stop, a.journey.dest_stop) or 0
        extras.append(max(0, a.arrival_min - (a.journey.dep_earliest + direct)))
        if a.journey.disruption and a.confirmed_at:
            recovery.append((a.confirmed_at - a.journey.disruption.created_at).total_seconds())

    offered = sum(o.available_seats for o in db.query(CarpoolOffer).filter(CarpoolOffer.status != "withdrawn"))
    no_feasible = 0
    for j in journeys:
        if st[j.id] == "unresolved":
            usable = db.query(JourneyOption).filter_by(journey_id=j.id, status="active", meets_deadline=True).count()
            no_feasible += 0 if usable else 1
    explained = db.query(Allocation).filter(Allocation.explanation != "").count()
    all_allocs = db.query(Allocation).count()
    run = db.query(AllocationRun).order_by(AllocationRun.id.desc()).first()

    def pct(a, b):
        return round(100 * a / b, 1) if b else None

    return {
        "affected_passengers": total,
        "official_confirmed": official,
        "carpool_confirmed": carpool,
        "self_resolved": seats["self_resolved"],
        "unresolved": seats["unresolved"] + seats["needs_review"],
        "pct_official": pct(official, total),
        "pct_unmet_via_carpool": pct(carpool, unmet_after_official),
        "official_seat_utilisation": pct(sum(a.seats for a in allocs), capacity),
        "carpool_seat_utilisation": pct(carpool, offered),
        "over_allocation_count": integrity(db)["over_allocated"],
        "parties_no_feasible_option": no_feasible,
        "pct_preference_satisfied": pct(satisfied, len(pref_rows)),
        "avg_additional_minutes": round(sum(extras) / len(extras), 1) if extras else None,
        "pct_decisions_explained": pct(explained, all_allocs),
        "avg_seconds_to_confirmation": round(sum(recovery) / len(recovery), 1) if recovery else None,
        "preferences_collected": db.query(Preference.journey_id).distinct().count(),
        "baseline": run.summary.get("baseline_fcfs") if run else None,
        "engine": run.summary.get("engine") if run else None,
        "solver": run.solver if run else None,
    }


# ---------------------------------------------------------------- overview
def overview(db: Session) -> dict:
    net = Network.load(db)
    journeys = affected_journeys(db)
    st = states(db, journeys)
    by_state, by_dest, by_origin = Counter(), Counter(), Counter()
    for j in journeys:
        by_state[st[j.id]] += j.party_size
        by_dest[net.stops[j.dest_stop].name] += j.party_size
        by_origin[net.stops[j.origin_stop].name] += j.party_size
    vehicles = db.query(Vehicle).order_by(Vehicle.id).all()
    disruptions = db.query(Disruption).filter_by(status="active").order_by(Disruption.id.desc()).all()
    return {
        "active_disruptions": [{"id": d.id, "code": d.code, "kind": d.kind, "description": d.description,
                                "start_min": d.start_min} for d in disruptions],
        "affected": sum(by_state.values()), "by_state": by_state,
        "parties": len(journeys),
        "by_destination": [{"name": k, "passengers": v} for k, v in by_dest.most_common()],
        "by_origin": [{"name": k, "passengers": v} for k, v in by_origin.most_common()],
        "capacity": {"total": sum(v.capacity for v in vehicles if v.status == "available"),
                     "available": sum(v.available_seats for v in vehicles if v.status == "available")},
        "vehicles": [{"id": v.id, "type": v.vehicle_type, "capacity": v.capacity, "available": v.available_seats,
                      "status": v.status} for v in vehicles],
        "carpool": {"open_requests": db.query(CarpoolRequest).filter(
                        CarpoolRequest.status.notin_(("cancelled", "completed", "confirmed"))).count(),
                    "offers": db.query(CarpoolOffer).filter_by(status="open").count(),
                    "confirmed_passengers": by_state["carpool_confirmed"]},
        "needs_review": db.query(Allocation).filter_by(status="needs_review").count(),
        "metrics": metrics(db),
    }


def carpool_monitor(db: Session) -> dict:
    """Operator oversight: figures and statuses only. No provider identity is needed to monitor."""
    requests = db.query(CarpoolRequest).order_by(CarpoolRequest.id).all()
    offers = db.query(CarpoolOffer).order_by(CarpoolOffer.id).all()
    matches = db.query(CarpoolMatch).order_by(CarpoolMatch.id).all()
    net = Network.load(db)
    journeys = db.query(Journey).filter_by(status="affected").all()
    st = states(db, journeys)
    waiting_official = sum(j.party_size for j in journeys if st[j.id] == "unresolved")
    in_match = {m.journey_id for m in db.query(CarpoolMatchMember).join(CarpoolMatch)
                .filter(CarpoolMatch.status.in_(PENDING_MATCH), CarpoolMatchMember.acceptance != "declined")}
    return {
        "summary": {
            "needing_transport": waiting_official,
            "open_requests": sum(1 for r in requests if r.status not in ("cancelled", "completed", "confirmed")),
            "offers_received": len(offers),
            "proposed_matches": sum(1 for m in matches if m.status in PENDING_MATCH),
            "confirmed_arrangements": sum(1 for m in matches if m.status in ("confirmed", "completed")),
            "confirmed_passengers": sum(m.matched_seats for m in matches if m.status in ("confirmed", "completed")),
            "remaining_unmatched": sum(j.party_size for j in journeys
                                       if st[j.id] == "unresolved" and j.id not in in_match),
            "reports": db.query(CarpoolReport).count(),
        },
        "requests": [{"id": r.id, "label": r.label, "pickup_area": r.pickup_area, "destination": r.destination_name,
                      "passengers": r.passenger_count, "window_start": r.window_start, "window_end": r.window_end,
                      "requirements": r.requirements, "status": r.status} for r in requests],
        "offers": [{"id": o.id, "label": o.label, "origin": net.stops[o.origin_stop].name,
                    "destination": net.stops[o.dest_stop].name, "departure": o.departure,
                    "seats": o.available_seats, "reserved": o.reserved_seats, "vehicle_type": o.vehicle_type,
                    "status": o.status} for o in offers],
        "matches": [{"id": m.id, "label": m.label, "request": m.request.label, "offer": m.offer.label,
                     "seats": m.matched_seats, "status": m.status, "detour_min": m.detour_min,
                     "passenger_acceptance": m.passenger_acceptance_status,
                     "provider_confirmation": m.provider_confirmation_status,
                     "cancel_reason": m.cancel_reason} for m in matches],
    }


# ---------------------------------------------------------------- demo guide
def demo_progress(db: Session) -> list[dict]:
    has = lambda model, **kw: db.query(model).filter_by(**kw).first() is not None  # noqa: E731
    affected = db.query(Journey).filter(Journey.status != "normal").count() > 0
    grouped = has(PassengerGroup)
    options = db.query(JourneyOption).first() is not None
    prefs = db.query(Preference).count() > 0
    ran = db.query(AllocationRun).first() is not None
    reserved = db.query(Allocation).filter(Allocation.confirmed_at.isnot(None)).first() is not None
    requests = db.query(CarpoolRequest).first() is not None
    offer = db.query(CarpoolOffer).first() is not None
    matched = db.query(CarpoolMatch).first() is not None
    confirmed = db.query(CarpoolMatch).filter(CarpoolMatch.status.in_(("confirmed", "completed"))).first() is not None
    steps = [
        ("Trigger the X5 cancellation", "Operator", has(Disruption), "/operator/simulation"),
        ("Identify affected passengers", "System", affected, "/operator/passengers"),
        ("Group compatible journeys", "System", grouped, "/operator/groups"),
        ("Generate alternative journeys", "System", options, "/operator/preferences"),
        ("Passengers rank alternatives", "Passengers", prefs, "/operator/preferences"),
        ("Review preferences", "Operator", prefs, "/operator/preferences"),
        ("Run smart allocation", "Operator", ran, "/operator/allocation"),
        ("Reserve seats", "Operator", reserved, "/operator/allocation"),
        ("Inspect the heat map", "Operator", reserved, "/operator/heatmap"),
        ("Publish unmet demand as carpool requests", "System", requests, "/operator/unresolved"),
        ("An ordinary user offers a ride", "Passenger app", offer, "/operator/carpool"),
        ("Match offer to passengers", "System", matched, "/operator/carpool"),
        ("Passengers and provider consent", "Passenger app", confirmed, "/operator/carpool"),
        ("Audit the full trail", "Operator", confirmed, "/operator/audit"),
    ]
    out, current = [], False
    for title, actor, done, link in steps:
        state = "done" if done else ("next" if not current else "todo")
        current = current or not done
        out.append({"title": title, "actor": actor, "state": state, "link": link})
    return out


def audit_rows(db: Session, event_type: str | None, q: str | None, limit: int) -> list[dict]:
    query = db.query(AuditEvent)
    if event_type:
        query = query.filter(AuditEvent.event_type == event_type)
    if q:
        like = f"%{q}%"
        query = query.filter(AuditEvent.decision_or_change.ilike(like) | AuditEvent.related_entity_id.ilike(like)
                             | AuditEvent.reason.ilike(like))
    return [{"id": e.id, "event_type": e.event_type, "entity": e.related_entity_id,
             "change": e.decision_or_change, "reason": e.reason, "actor": e.actor_id,
             "timestamp": e.timestamp.isoformat() + "Z"}
            for e in query.order_by(AuditEvent.id.desc()).limit(limit)]

