"""Community carpool API for ordinary signed-in users."""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..database import get_db
from ..engines import carpool as cp
from ..engines.network import Network
from ..models import CarpoolMatch, CarpoolMatchMember, CarpoolOffer, CarpoolRequest, Journey, Stop, User
from ..schemas import CancelIn, OfferIn, ReasonIn, RespondIn
from ..security import require_passenger
from ..services import audit

router = APIRouter(prefix="/api/carpool", tags=["carpool"])


def _match(db: Session, match_id: int) -> CarpoolMatch:
    m = db.get(CarpoolMatch, match_id)
    if not m:
        raise HTTPException(404, "Match not found")
    return m


def _guarded(fn, *args):
    try:
        fn(*args)
    except PermissionError as e:
        raise HTTPException(403, str(e))
    except cp.CarpoolError as e:
        raise HTTPException(409, str(e))


def _offer_view(db: Session, o: CarpoolOffer) -> dict:
    names = {s.id: s.name for s in db.query(Stop)}
    return {"id": o.id, "label": o.label, "origin": names[o.origin_stop], "destination": names[o.dest_stop],
            "departure": o.departure, "available_seats": o.available_seats, "reserved_seats": o.reserved_seats,
            "vehicle_type": o.vehicle_type, "wheelchair": o.wheelchair, "luggage": o.luggage,
            "pickup_zone": o.pickup_zone, "notes": o.notes, "status": o.status}


@router.get("/requests")
def requests(_: User = Depends(require_passenger), db: Session = Depends(get_db)):
    rows = db.query(CarpoolRequest).filter(
        CarpoolRequest.status.notin_(("cancelled", "completed")), CarpoolRequest.passenger_count > 0
    ).order_by(CarpoolRequest.id).all()
    return [cp.listing_view(r) for r in rows]


@router.post("/offers", status_code=201)
def create_offer(body: OfferIn, user: User = Depends(require_passenger), db: Session = Depends(get_db)):
    if not db.get(Stop, body.origin_stop) or not db.get(Stop, body.dest_stop):
        raise HTTPException(422, "Unknown stop")
    label = f"CO-{db.query(CarpoolOffer).count() + 1:02d}"
    data = body.model_dump(exclude={"consent"})
    offer = CarpoolOffer(label=label, provider_user_id=user.id, **data)
    db.add(offer)
    db.flush()
    audit(db, "carpool_offer_created", label, f"{offer.available_seats} seat(s) offered",
          "Provider accepted the community carpool terms", user)
    result = cp.match_offer(db, offer, Network.load(db), user)
    db.commit()
    return {"offer": _offer_view(db, offer), "notes": result["notes"], "matches_proposed": len(result["matches"])}


@router.get("/offers/mine")
def my_offers(user: User = Depends(require_passenger), db: Session = Depends(get_db)):
    rows = db.query(CarpoolOffer).filter_by(provider_user_id=user.id).order_by(CarpoolOffer.id.desc()).all()
    return [_offer_view(db, o) for o in rows]


@router.post("/offers/{offer_id}/withdraw")
def withdraw(offer_id: int, user: User = Depends(require_passenger), db: Session = Depends(get_db)):
    offer = db.get(CarpoolOffer, offer_id)
    if not offer:
        raise HTTPException(404, "Offer not found")
    _guarded(cp.withdraw_offer, db, offer, user, Network.load(db))
    db.commit()
    return _offer_view(db, offer)


@router.get("/matches/mine")
def my_matches(user: User = Depends(require_passenger), db: Session = Depends(get_db)):
    net = Network.load(db)
    as_provider = db.query(CarpoolMatch).join(CarpoolOffer).filter(CarpoolOffer.provider_user_id == user.id)
    as_passenger = db.query(CarpoolMatch).join(CarpoolMatchMember).join(Journey).filter(Journey.user_id == user.id)
    rows = {m.id: m for m in list(as_provider) + list(as_passenger)}
    return [cp.match_view(db, m, user, net) for _, m in sorted(rows.items(), reverse=True)]


@router.post("/matches/{match_id}/passenger-response")
def passenger_response(match_id: int, body: RespondIn, user: User = Depends(require_passenger),
                       db: Session = Depends(get_db)):
    m, net = _match(db, match_id), Network.load(db)
    _guarded(cp.passenger_respond, db, m, user, body.accept, net)
    db.commit()
    return cp.match_view(db, m, user, net)


@router.post("/matches/{match_id}/provider-response")
def provider_response(match_id: int, body: RespondIn, user: User = Depends(require_passenger),
                      db: Session = Depends(get_db)):
    m, net = _match(db, match_id), Network.load(db)
    _guarded(cp.provider_respond, db, m, user, body.accept, net)
    db.commit()
    return cp.match_view(db, m, user, net)


@router.post("/matches/{match_id}/cancel")
def cancel(match_id: int, body: CancelIn, user: User = Depends(require_passenger), db: Session = Depends(get_db)):
    m, net = _match(db, match_id), Network.load(db)
    _guarded(cp.cancel_match, db, m, user, body.reason, net)
    db.commit()
    return cp.match_view(db, m, user, net)


@router.post("/matches/{match_id}/complete")
def complete(match_id: int, user: User = Depends(require_passenger), db: Session = Depends(get_db)):
    m = _match(db, match_id)
    _guarded(cp.complete_match, db, m, user)
    db.commit()
    return cp.match_view(db, m, user, Network.load(db))


@router.post("/matches/{match_id}/report")
def report(match_id: int, body: ReasonIn, user: User = Depends(require_passenger), db: Session = Depends(get_db)):
    m = _match(db, match_id)
    _guarded(cp.report_match, db, m, user, body.reason)
    db.commit()
    return {"ok": True}
