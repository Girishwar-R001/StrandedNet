"""Passenger API. Every route is scoped to the signed-in user's own journeys."""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..database import get_db
from ..engines import alternatives, carpool, reporting
from ..engines.allocation import ReservationError, release
from ..engines.network import Network
from ..models import (Allocation, CarpoolMatch, CarpoolMatchMember, CarpoolRequestMember,
                      Disruption, Journey, JourneyOption, Notification, Preference, Service,
                      Stop, User, Vehicle, utcnow)
from ..schemas import JourneyIn, PreferenceIn, ReasonIn, SelfResolve
from ..security import require_passenger
from ..services import audit, now_min

router = APIRouter(prefix="/api/me", tags=["passenger"])


def _own(db: Session, user: User, journey_id: int) -> Journey:
    j = db.get(Journey, journey_id)
    if not j or j.user_id != user.id:
        raise HTTPException(404, "Journey not found")
    return j


def _option_view(db: Session, o: JourneyOption, party: int) -> dict:
    return {"id": o.id, "kind": o.kind, "title": o.title, "vehicle_id": o.vehicle_id, "legs": o.legs,
            "pickup_stop": o.pickup_stop, "departure": o.departure, "arrival": o.arrival,
            "transfers": o.transfers, "walk_m": o.walk_m, "wait_min": o.wait_min,
            "duration": o.arrival - o.departure, "reservable": o.reservable,
            "meets_deadline": o.meets_deadline, "status": o.status,
            # A suggestion is always a suggestion. Only an allocation can say otherwise.
            "option_status": "suggested",
            "availability": reporting.option_availability(db, o, party)}


def _stage(db: Session, j: Journey, alloc: Allocation | None, prefs: list[Preference]) -> dict:
    """Plain-language state. Engine proposals are hidden, as nothing has been promised yet."""
    state = reporting.recovery_state(j, alloc)
    live_match = db.query(CarpoolMatch).join(CarpoolMatchMember).filter(
        CarpoolMatchMember.journey_id == j.id, CarpoolMatchMember.acceptance != "declined",
        CarpoolMatch.status.in_(carpool.PENDING_MATCH)).first()
    listed = db.query(CarpoolRequestMember).filter_by(journey_id=j.id, active=True).first()
    if state == "unaffected":
        return {"code": "on_track", "headline": "Your journey is running as planned",
                "detail": "We'll tell you straight away if anything changes.", "tone": "good"}
    if state == "official_confirmed":
        return {"code": "seat_confirmed", "headline": f"Your seat on {alloc.vehicle_id} is confirmed",
                "detail": "Your seat is reserved. Head to your pickup point on time.", "tone": "good"}
    if state == "carpool_confirmed":
        return {"code": "carpool_confirmed", "headline": "Your community carpool is confirmed",
                "detail": "This is a ride from a community member, not official transport.", "tone": "good"}
    if state == "self_resolved":
        return {"code": "self_resolved", "headline": "You're making your own way",
                "detail": "You told us you've sorted your journey, so we've released your place.", "tone": "neutral"}
    if state == "needs_review":
        return {"code": "under_review", "headline": "Your confirmed journey is being reviewed",
                "detail": alloc.flag_reason, "tone": "warn"}
    if state == "approved":
        return {"code": "operator_approved", "headline": "An operator has approved a seat for you",
                "detail": "It isn't final until the seat is reserved. You'll be told in moments.", "tone": "info"}
    if live_match:
        needs_me = live_match.status == "awaiting_passenger"
        return {"code": "carpool_proposed",
                "headline": "A community driver may be able to help" if needs_me else "Waiting for the driver to confirm",
                "detail": "Review the proposal below." if needs_me else "You've accepted. The ride isn't confirmed yet.",
                "tone": "info"}
    if listed:
        return {"code": "carpool_listed", "headline": "No official seat yet",
                "detail": "You're on an anonymous carpool listing while we keep looking.", "tone": "warn"}
    if j.outcome_note:
        return {"code": "no_official_seat", "headline": "No official seat is available right now",
                "detail": "Compare your other options below.", "tone": "warn"}
    if prefs:
        return {"code": "preference_submitted", "headline": "We have your preferences",
                "detail": "This isn't a booking yet. You'll be told as soon as a seat is confirmed or unavailable.",
                "tone": "info"}
    return {"code": "choose_options", "headline": "Your service is disrupted. Choose what suits you",
            "detail": "Compare the options below and rank your top two.", "tone": "warn"}


def _journey_view(db: Session, j: Journey) -> dict:
    alloc = reporting.active_allocation(db, j)
    prefs = db.query(Preference).filter_by(journey_id=j.id).order_by(Preference.rank).all()
    stops = {s.id: s.name for s in db.query(Stop)}
    allocation = None
    if alloc and alloc.status in ("approved", "confirmed", "needs_review"):
        v = alloc.vehicle
        allocation = {"id": alloc.id, "status": alloc.status, "vehicle_id": alloc.vehicle_id,
                      "vehicle_type": v.vehicle_type, "seats": alloc.seats,
                      "pickup_stop": stops[alloc.pickup_stop], "pickup_min": alloc.pickup_min,
                      "arrival_min": alloc.arrival_min, "flag_reason": alloc.flag_reason,
                      "seats_remaining": v.available_seats}
    d = j.disruption
    return {
        "id": j.id, "ref": j.ref, "status": j.status, "origin": stops[j.origin_stop],
        "origin_stop": j.origin_stop, "destination": stops[j.dest_stop], "dest_stop": j.dest_stop,
        "party_size": j.party_size, "dep_earliest": j.dep_earliest, "dep_latest": j.dep_latest,
        "latest_arrival": j.latest_arrival, "requirements": j.requirements,
        "booked_service_id": j.booked_service_id, "carpool_opt_out": j.carpool_opt_out,
        "stage": _stage(db, j, alloc, prefs), "allocation": allocation,
        "disruption": {"code": d.code, "kind": d.kind, "description": d.description, "status": d.status} if d else None,
        "preferences": [{"rank": p.rank, "option_id": p.option_id, "title": p.option.title, "status": p.status,
                         "availability": reporting.option_availability(db, p.option, j.party_size)} for p in prefs],
        "outcome_note": j.outcome_note,
        "preferences_locked": bool(alloc and alloc.status in ("confirmed", "needs_review"))
                              or j.status != "affected",
    }


@router.get("/journeys")
def my_journeys(user: User = Depends(require_passenger), db: Session = Depends(get_db)):
    rows = db.query(Journey).filter_by(user_id=user.id).order_by(Journey.id.desc()).all()
    return [_journey_view(db, j) for j in rows]


@router.post("/journeys", status_code=201)
def register_journey(body: JourneyIn, user: User = Depends(require_passenger), db: Session = Depends(get_db)):
    if not db.get(Stop, body.origin_stop) or not db.get(Stop, body.dest_stop):
        raise HTTPException(422, "Unknown stop")
    if body.booked_service_id and not db.get(Service, body.booked_service_id):
        raise HTTPException(422, "Unknown service")
    stop = db.get(Stop, body.origin_stop)
    now = now_min(db)
    ref = f"P-{db.query(Journey).count() + 1:02d}"
    j = Journey(ref=ref, user_id=user.id, lat=stop.lat, lng=stop.lng, reported_min=now, **body.model_dump())
    db.add(j)
    db.flush()
    audit(db, "journey_registered", ref, "Passenger registered a journey", "", user)
    svc = db.get(Service, body.booked_service_id) if body.booked_service_id else None
    if svc and svc.status == "cancelled":
        d = db.query(Disruption).filter_by(service_id=svc.id, status="active").first()
        _mark_affected(db, j, d)
    db.commit()
    return _journey_view(db, j)


def _mark_affected(db: Session, j: Journey, d: Disruption | None) -> None:
    j.status = "affected"
    j.disruption_id = d.id if d else None
    net = Network.load(db)
    now = now_min(db)
    alternatives.refresh_options(db, j, db.query(Vehicle).filter_by(status="available").order_by(Vehicle.id).all(),
                                 net.trips(db.query(Service).order_by(Service.id).all(), now), net, now)


@router.post("/journeys/{journey_id}/report-affected")
def report_affected(journey_id: int, user: User = Depends(require_passenger), db: Session = Depends(get_db)):
    j = _own(db, user, journey_id)
    if j.status != "normal":
        raise HTTPException(409, "This journey is already being handled")
    d = db.query(Disruption).filter_by(status="active").order_by(Disruption.id.desc()).first()
    j.self_reported = True
    _mark_affected(db, j, d)
    audit(db, "journey_self_reported", j.ref, "Passenger reported their journey as affected", "", user)
    db.commit()
    return _journey_view(db, j)


@router.get("/journeys/{journey_id}/options")
def options(journey_id: int, user: User = Depends(require_passenger), db: Session = Depends(get_db)):
    j = _own(db, user, journey_id)
    rows = db.query(JourneyOption).filter_by(journey_id=j.id, status="active").all()
    rows.sort(key=lambda o: (not o.meets_deadline, not o.reservable, o.arrival))
    return [_option_view(db, o, j.party_size) for o in rows]


@router.put("/journeys/{journey_id}/preferences")
def set_preferences(journey_id: int, body: PreferenceIn, user: User = Depends(require_passenger),
                    db: Session = Depends(get_db)):
    j = _own(db, user, journey_id)
    alloc = reporting.active_allocation(db, j)
    if j.status != "affected" or (alloc and alloc.status in ("confirmed", "needs_review")):
        raise HTTPException(409, "Preferences can't be changed once your journey is confirmed")
    ids = [body.first_option_id] + ([body.second_option_id] if body.second_option_id else [])
    if len(set(ids)) != len(ids):
        raise HTTPException(422, "First and second choice must be different")
    chosen = []
    for oid in ids:
        o = db.get(JourneyOption, oid)
        if not o or o.journey_id != j.id or o.status != "active":
            raise HTTPException(422, "That option isn't available for this journey")
        chosen.append(o)
    db.query(Preference).filter_by(journey_id=j.id).delete()
    db.flush()
    for rank, o in enumerate(chosen, 1):
        db.add(Preference(journey_id=j.id, option_id=o.id, rank=rank))
    audit(db, "preference_submitted", j.ref,
          "; ".join(f"Choice {n}: {o.title}" for n, o in enumerate(chosen, 1)),
          "Preference recorded. No seat reserved.", user)
    db.commit()
    return _journey_view(db, j)


@router.post("/journeys/{journey_id}/self-resolve")
def self_resolve(journey_id: int, body: SelfResolve, user: User = Depends(require_passenger),
                 db: Session = Depends(get_db)):
    """Passenger takes a walk-up option or leaves. Frees demand without operator effort."""
    j = _own(db, user, journey_id)
    if j.status not in ("affected", "allocated"):
        raise HTTPException(409, "This journey can't be released")
    alloc = reporting.active_allocation(db, j)
    if alloc:
        release(db, alloc, "Passenger arranged their own travel", user)
    j.status = "self_resolved"
    carpool.withdraw_from_carpool(db, j, "Passenger arranged their own travel")
    audit(db, "journey_self_resolved", j.ref, "Passenger made their own arrangements", "", user)
    carpool.sync_demand(db, Network.load(db), user)
    db.commit()
    return _journey_view(db, j)


@router.post("/journeys/{journey_id}/leave-carpool")
def leave_carpool(journey_id: int, user: User = Depends(require_passenger), db: Session = Depends(get_db)):
    j = _own(db, user, journey_id)
    carpool.leave_listing(db, j, Network.load(db), user)
    db.commit()
    return _journey_view(db, j)


@router.post("/journeys/{journey_id}/join-carpool")
def join_carpool(journey_id: int, user: User = Depends(require_passenger), db: Session = Depends(get_db)):
    j = _own(db, user, journey_id)
    j.carpool_opt_out = False
    audit(db, "carpool_opt_in", j.ref, "Passenger rejoined the carpool listing", "", user)
    carpool.sync_demand(db, Network.load(db), user)
    db.commit()
    return _journey_view(db, j)


@router.post("/journeys/{journey_id}/decline-seat")
def decline_seat(journey_id: int, body: ReasonIn, user: User = Depends(require_passenger),
                 db: Session = Depends(get_db)):
    j = _own(db, user, journey_id)
    alloc = reporting.active_allocation(db, j)
    if not alloc or alloc.status != "confirmed":
        raise HTTPException(409, "No confirmed seat to give up")
    try:
        release(db, alloc, f"Declined by passenger: {body.reason}", user)
    except ReservationError as e:
        raise HTTPException(409, str(e))
    carpool.sync_demand(db, Network.load(db), user)
    db.commit()
    return _journey_view(db, j)


@router.get("/disruptions")
def disruptions(_: User = Depends(require_passenger), db: Session = Depends(get_db)):
    rows = db.query(Disruption).filter_by(status="active").order_by(Disruption.id.desc()).all()
    return [{"code": d.code, "kind": d.kind, "description": d.description, "start_min": d.start_min,
             "est_end_min": d.est_end_min} for d in rows]


@router.get("/notifications")
def notifications(user: User = Depends(require_passenger), db: Session = Depends(get_db)):
    rows = db.query(Notification).filter_by(user_id=user.id).order_by(Notification.id.desc()).limit(50).all()
    return [{"id": n.id, "kind": n.kind, "title": n.title, "body": n.body, "read": n.read,
             "created_at": n.created_at.isoformat() + "Z"} for n in rows]


@router.post("/notifications/read")
def mark_read(user: User = Depends(require_passenger), db: Session = Depends(get_db)):
    db.query(Notification).filter_by(user_id=user.id, read=False).update({"read": True})
    db.commit()
    return {"ok": True, "at": utcnow().isoformat()}

