"""Community carpooling fallback (spec 5.7, 9.3).

Deliberately independent of official allocation: its own seat accounting (offer.reserved_seats),
its own statuses, and it never creates an Allocation row. Nothing here counts as official.

Privacy: listings and proposals carry zones, counts and windows only. Names, phone numbers and
exact pickups are released by `match_view` only after a match reaches `confirmed`, and only to
the parties in that match.
"""
from sqlalchemy import update
from sqlalchemy.orm import Session

from ..models import (ACTIVE_ALLOCATION, Allocation, AllocationRun, CarpoolMatch,
                      CarpoolMatchMember, CarpoolOffer, CarpoolReport, CarpoolRequest,
                      CarpoolRequestMember, Journey, User, utcnow)
from ..services import audit, fmt, notify, thresholds
from .grouping import pair_compat
from .network import Network

PENDING_MATCH = ("awaiting_passenger", "awaiting_provider")
LIVE_MATCH = PENDING_MATCH + ("confirmed",)
STEP_FREE = {"wheelchair", "step_free"}


class CarpoolError(Exception):
    pass


# ---------------------------------------------------------------- demand
def unresolved(db: Session) -> list[Journey]:
    """Parties with no official seat in play and no confirmed carpool."""
    held = {a.journey_id for a in db.query(Allocation).filter(Allocation.status.in_(ACTIVE_ALLOCATION))}
    return [j for j in db.query(Journey).filter_by(status="affected").order_by(Journey.ref)
            if j.id not in held]


def _active_members(db: Session, request_id: int) -> list[CarpoolRequestMember]:
    return db.query(CarpoolRequestMember).filter_by(request_id=request_id, active=True).all()


def _in_pending_match(db: Session, journey_id: int) -> bool:
    return db.query(CarpoolMatchMember).join(CarpoolMatch).filter(
        CarpoolMatchMember.journey_id == journey_id, CarpoolMatchMember.acceptance != "declined",
        CarpoolMatch.status.in_(LIVE_MATCH)).first() is not None


def refresh_request(db: Session, r: CarpoolRequest) -> None:
    """Recompute aggregate figures and status from membership and matches."""
    members = _active_members(db, r.id)
    waiting = [m.journey for m in members if m.journey.status == "affected"]
    matches = db.query(CarpoolMatch).filter_by(request_id=r.id).all()
    live = [m for m in matches if m.status != "cancelled"]
    r.passenger_count = sum(j.party_size for j in waiting)
    if waiting:
        r.window_start = min(j.dep_earliest for j in waiting)
        r.window_end = max(j.dep_latest for j in waiting)
        r.requirements = sorted({q for j in waiting for q in (j.requirements or [])})

    if any(m.status == "awaiting_provider" for m in live):
        r.status = "awaiting_provider"
    elif any(m.status == "awaiting_passenger" for m in live):
        responded = any(x.acceptance != "pending" for m in live for x in m.members)
        r.status = "awaiting_passenger" if responded else "match_proposed"
    elif waiting:
        if r.status not in ("offer_received",):
            r.status = "open"
    elif live:
        r.status = "completed" if all(m.status == "completed" for m in live) else "confirmed"
    else:
        r.status = "cancelled"


def sync_demand(db: Session, net: Network, actor=None) -> None:
    """Turn unmet demand into aggregated listings. Runs after allocation and whenever a seat
    or a carpool falls through. A no-op until the first allocation run has happened."""
    if not db.query(AllocationRun).first():
        return
    need = {j.id: j for j in unresolved(db) if not j.carpool_opt_out}

    for m in db.query(CarpoolRequestMember).filter_by(active=True):
        keep = m.journey_id in need or m.journey.status == "carpool_confirmed" \
               or _in_pending_match(db, m.journey_id)
        if not keep:
            m.active = False
    db.flush()

    listed = {m.journey_id for m in db.query(CarpoolRequestMember).filter_by(active=True)}
    open_requests = db.query(CarpoolRequest).filter(CarpoolRequest.status.notin_(("cancelled", "completed"))) \
                      .order_by(CarpoolRequest.id).all()
    for j in need.values():
        if j.id in listed:
            continue
        home = None
        for r in open_requests:
            members = [m.journey for m in _active_members(db, r.id) if m.journey.status == "affected"]
            same_zone = net.stops[j.origin_stop].zone == r.origin_zone
            if members and same_zone and all(pair_compat(j, o, net).ok for o in members):
                home = r
                break
        if home is None:
            origin, dest = net.stops[j.origin_stop], net.stops[j.dest_stop]
            home = CarpoolRequest(
                label=f"CR-{db.query(CarpoolRequest).count() + 1:02d}", origin_zone=origin.zone,
                pickup_area=f"{origin.name} area", destination_zone=dest.zone,
                destination_name=dest.name, dest_stop=dest.id, origin_stop=origin.id,
                window_start=j.dep_earliest, window_end=j.dep_latest)
            db.add(home)
            db.flush()
            open_requests.append(home)
            audit(db, "carpool_request_published", home.label,
                  f"Listing for {dest.name} from {origin.zone}", "Unmet demand after official allocation", actor)
        existing = db.query(CarpoolRequestMember).filter_by(request_id=home.id, journey_id=j.id).first()
        if existing:
            existing.active = True
        else:
            db.add(CarpoolRequestMember(request_id=home.id, journey_id=j.id))
        db.flush()
        notify(db, j.user_id, "Added to a community carpool listing",
               f"No official seat is available yet. Your request is listed anonymously as {home.label}. "
               f"Nobody can see your name or number. You can leave the listing at any time.")

    for r in db.query(CarpoolRequest).filter(CarpoolRequest.status.notin_(("cancelled", "completed"))):
        refresh_request(db, r)
    db.flush()
    for offer in db.query(CarpoolOffer).filter_by(status="open").order_by(CarpoolOffer.id):
        match_offer(db, offer, net, actor)


def withdraw_from_carpool(db: Session, j: Journey, reason: str) -> None:
    """Called when a party secures official transport, so nobody holds two seats."""
    for mm in db.query(CarpoolMatchMember).join(CarpoolMatch).filter(
            CarpoolMatchMember.journey_id == j.id, CarpoolMatch.status.in_(PENDING_MATCH),
            CarpoolMatchMember.acceptance != "declined").all():
        _drop_member(db, mm, reason)
    for m in db.query(CarpoolRequestMember).filter_by(journey_id=j.id, active=True):
        m.active = False
        db.flush()
        refresh_request(db, db.get(CarpoolRequest, m.request_id))


# ---------------------------------------------------------------- matching
def evaluate(offer: CarpoolOffer, j: Journey, net: Network, cfg: dict) -> dict:
    """Independent compatibility check of one party against one offer (everything but seats)."""
    checks = []

    def add(name, ok, detail):
        checks.append({"name": name, "ok": bool(ok), "detail": detail})

    direct = net.travel(offer.origin_stop, offer.dest_stop)
    to_pick = net.travel(offer.origin_stop, j.origin_stop)
    pick_to_dest = net.travel(j.origin_stop, offer.dest_stop)
    if None in (direct, to_pick, pick_to_dest):
        add("route", False, "No open road links this journey")
        return {"ok": False, "checks": checks, "detour": None, "pickup_min": None, "arrival": None}

    provider_path = net.path(j.origin_stop, offer.dest_stop)
    gap = net.dist_m(j.dest_stop, offer.dest_stop)
    served = j.dest_stop in provider_path or gap <= cfg["carpool_dest_radius_m"]
    add("route", served, f"Destination is {'on your route' if j.dest_stop in provider_path else f'{gap / 1000:.1f} km from yours'}")

    detour = to_pick + pick_to_dest - direct
    add("detour", detour <= cfg["carpool_max_detour_min"],
        f"Pickup adds {detour} min (limit {cfg['carpool_max_detour_min']})")

    pickup = offer.departure + to_pick
    tol = cfg["carpool_time_tolerance_min"]
    add("timing", j.dep_earliest - tol <= pickup <= j.dep_latest + tol,
        f"Pickup {fmt(pickup)} vs window {fmt(j.dep_earliest)}–{fmt(j.dep_latest)}")

    on_path = j.dest_stop in provider_path
    ride = net.travel(j.origin_stop, j.dest_stop if on_path else offer.dest_stop) or 0
    arrival = pickup + ride
    add("deadline", arrival <= j.latest_arrival,
        f"Arrives {fmt(arrival)} vs latest {fmt(j.latest_arrival)}")

    reqs = set(j.requirements or [])
    lacks = []
    if reqs & STEP_FREE and not offer.wheelchair:
        lacks.append("step-free access")
    if "luggage" in reqs and not offer.luggage:
        lacks.append("luggage space")
    add("suitability", not lacks, f"Vehicle lacks {', '.join(lacks)}" if lacks else "Vehicle suits requirements")

    if offer.pickup_zone:
        add("pickup_zone", net.stops[j.origin_stop].zone == offer.pickup_zone,
            f"Pickup zone {net.stops[j.origin_stop].zone} vs offered {offer.pickup_zone}")
    return {"ok": all(c["ok"] for c in checks), "checks": checks, "detour": detour,
            "pickup_min": pickup, "arrival": arrival}


def _best_subset(parties: list[Journey], seats: int) -> list[Journey]:
    """Knapsack over whole parties: fill as many seats as possible, never splitting a party.
    `parties` is pre-sorted longest-waiting first, and earlier parties win ties."""
    best: dict[int, list[Journey]] = {0: []}
    for j in parties:
        for used, chosen in sorted(best.items(), reverse=True):
            total = used + j.party_size
            if total <= seats and total not in best:
                best[total] = chosen + [j]
    return best[max(best)]


def _reserve_offer_seats(db: Session, offer: CarpoolOffer, n: int) -> bool:
    res = db.execute(update(CarpoolOffer)
                     .where(CarpoolOffer.id == offer.id, CarpoolOffer.status == "open",
                            CarpoolOffer.reserved_seats + n <= CarpoolOffer.available_seats)
                     .values(reserved_seats=CarpoolOffer.reserved_seats + n)
                     .execution_options(synchronize_session=False))
    db.refresh(offer)
    return res.rowcount == 1


def _release_offer_seats(db: Session, offer: CarpoolOffer, n: int) -> None:
    db.execute(update(CarpoolOffer).where(CarpoolOffer.id == offer.id, CarpoolOffer.reserved_seats >= n)
               .values(reserved_seats=CarpoolOffer.reserved_seats - n)
               .execution_options(synchronize_session=False))
    db.refresh(offer)


def match_offer(db: Session, offer: CarpoolOffer, net: Network, actor=None) -> dict:
    """Propose matches for an open offer. A proposal holds offer seats but confirms nothing."""
    cfg = thresholds(db)
    made, notes = [], []
    requests = db.query(CarpoolRequest).filter(CarpoolRequest.status.notin_(("cancelled", "completed", "confirmed"))) \
                 .order_by(CarpoolRequest.id).all()
    for r in requests:
        left = offer.available_seats - offer.reserved_seats
        waiting = [m.journey for m in _active_members(db, r.id)
                   if m.journey.status == "affected" and m.journey.user_id != offer.provider_user_id
                   and not _in_pending_match(db, m.journey_id)]
        declined = {x.journey_id for x in db.query(CarpoolMatchMember).join(CarpoolMatch)
                    .filter(CarpoolMatch.offer_id == offer.id, CarpoolMatchMember.acceptance == "declined")}
        waiting = sorted((j for j in waiting if j.id not in declined), key=lambda j: (j.reported_min, j.ref))
        if not waiting:
            continue
        results = {j.id: evaluate(offer, j, net, cfg) for j in waiting}
        compatible = [j for j in waiting if results[j.id]["ok"]]
        if not compatible:
            fails = sorted({c["detail"] for res in results.values() for c in res["checks"] if not c["ok"]})
            notes.append({"request": r.label, "matched": False, "reasons": fails[:3]})
            continue

        fits = [j for j in compatible if j.party_size <= left]
        if not fits:
            if left > 0:
                smallest = min(j.party_size for j in compatible)
                notes.append({"request": r.label, "matched": False,
                              "reasons": [f"Compatible, but the smallest party needs {smallest} seats "
                                          f"and {left} are free. Parties are never split."]})
                if r.status == "open":
                    r.status = "offer_received"
            continue

        # One pickup per match: choose the stop that fills the most seats.
        chosen: list[Journey] = []
        for stop in sorted({j.origin_stop for j in fits}):
            subset = _best_subset([j for j in fits if j.origin_stop == stop], left)
            if sum(j.party_size for j in subset) > sum(j.party_size for j in chosen):
                chosen = subset
        seats = sum(j.party_size for j in chosen)
        if not chosen or not _reserve_offer_seats(db, offer, seats):
            continue

        anchor = results[chosen[0].id]
        checks = [{"name": "seats", "ok": True, "detail": f"{seats} of {offer.available_seats} seats matched"}]
        checks += anchor["checks"]
        match = CarpoolMatch(label=f"CM-{db.query(CarpoolMatch).count() + 1:02d}", request_id=r.id,
                             offer_id=offer.id, matched_seats=seats, pickup_stop=chosen[0].origin_stop,
                             pickup_min=anchor["pickup_min"], detour_min=anchor["detour"], checks=checks)
        db.add(match)
        db.flush()
        for j in chosen:
            db.add(CarpoolMatchMember(match_id=match.id, journey_id=j.id, seats=j.party_size))
            notify(db, j.user_id, "A community driver may be able to help",
                   f"A ride around {fmt(anchor['pickup_min'])} is proposed from the "
                   f"{net.stops[j.origin_stop].zone} area. Review it and accept or decline. Nothing "
                   f"is confirmed until you and the driver both agree.")
        notify(db, offer.provider_user_id, "Your offer has a proposed match",
               f"{seats} seat(s) proposed. We will ask you to confirm after the passengers respond.")
        audit(db, "carpool_match_proposed", match.label,
              f"{offer.label} matched to {r.label} for {seats} seat(s)",
              f"Detour {anchor['detour']} min; passes route, timing, seat and suitability checks", actor)
        db.flush()
        refresh_request(db, r)
        made.append(match)
        notes.append({"request": r.label, "matched": True, "reasons": [f"{seats} seat(s) proposed"]})
    return {"matches": made, "notes": notes}


# ---------------------------------------------------------------- consent lifecycle
def _drop_member(db: Session, mm: CarpoolMatchMember, reason: str) -> None:
    match = mm.match
    mm.acceptance = "declined"
    match.matched_seats -= mm.seats
    _release_offer_seats(db, match.offer, mm.seats)
    db.flush()
    _settle_passengers(db, match, reason)


def _settle_passengers(db: Session, match: CarpoolMatch, reason: str) -> None:
    """Advance a match once every party has answered."""
    if match.status != "awaiting_passenger":
        if match.status in ("awaiting_provider", "confirmed") and match.matched_seats == 0:
            _close(db, match, reason)
        return
    answers = [m.acceptance for m in match.members]
    if "pending" in answers:
        refresh_request(db, match.request)
        return
    if "accepted" in answers:
        match.status = "awaiting_provider"
        match.passenger_acceptance_status = "accepted"
        notify(db, match.offer.provider_user_id, "Passengers accepted, your confirmation is needed",
               f"{match.matched_seats} seat(s) accepted. Please confirm the arrangement.", "success")
    else:
        match.passenger_acceptance_status = "declined"
        _close(db, match, reason)
    refresh_request(db, match.request)


def _close(db: Session, match: CarpoolMatch, reason: str) -> None:
    match.status = "cancelled"
    match.cancel_reason = reason
    remaining = sum(m.seats for m in match.members if m.acceptance != "declined")
    if remaining:
        _release_offer_seats(db, match.offer, remaining)
    match.matched_seats = 0
    for m in match.members:
        if m.journey.status == "carpool_confirmed":
            m.journey.status = "affected"
    db.flush()
    refresh_request(db, match.request)


def passenger_respond(db: Session, match: CarpoolMatch, user: User, accept: bool, net: Network) -> None:
    if match.status != "awaiting_passenger":
        raise CarpoolError(f"This match is {match.status.replace('_', ' ')} and cannot be answered")
    mine = [m for m in match.members if m.journey.user_id == user.id]
    if not mine:
        raise PermissionError("You are not part of this match")
    for mm in mine:
        if mm.acceptance != "pending":
            raise CarpoolError("You have already answered")
        audit(db, "carpool_passenger_response", match.label,
              f"{mm.journey.ref} {'accepted' if accept else 'declined'}", "", user)
        if accept:
            mm.acceptance = "accepted"
            db.flush()
            _settle_passengers(db, match, "")
        else:
            _drop_member(db, mm, "Passengers declined the proposal")
    if not accept:
        sync_demand(db, net, user)


def provider_respond(db: Session, match: CarpoolMatch, user: User, accept: bool, net: Network) -> None:
    if match.offer.provider_user_id != user.id:
        raise PermissionError("This is not your offer")
    if match.status not in PENDING_MATCH:
        raise CarpoolError(f"This match is {match.status.replace('_', ' ')}")
    if not accept:
        match.provider_confirmation_status = "rejected"
        _notify_members(db, match, "The driver could not take this ride",
                        "You are back on the carpool listing and still awaiting transport.", "warning")
        audit(db, "carpool_provider_response", match.label, "Provider rejected", "", user)
        _close(db, match, "Provider rejected the proposal")
        sync_demand(db, net, user)
        return
    if match.status != "awaiting_provider":
        raise CarpoolError("Passengers must accept before you can confirm")

    accepted = [m for m in match.members if m.acceptance == "accepted"]
    seats = sum(m.seats for m in accepted)
    # Independent recheck: consent alone never overrides capacity.
    if seats > match.offer.available_seats or any(m.journey.status != "affected" for m in accepted):
        raise CarpoolError("This arrangement is no longer valid")
    match.status = "confirmed"
    match.provider_confirmation_status = "confirmed"
    match.confirmed_at = utcnow()
    for m in accepted:
        m.journey.status = "carpool_confirmed"
        m.journey.outcome_note = ""
        # Withdraw any unreserved official proposal, so it can't be confirmed later by mistake.
        for a in db.query(Allocation).filter(Allocation.journey_id == m.journey_id,
                                             Allocation.status.in_(("proposed", "approved"))):
            a.status = "cancelled"
            a.flag_reason = "Passenger confirmed a community carpool instead"
    _notify_members(db, match, "Your community carpool is confirmed",
                    "Driver contact details and the exact pickup are now on your dashboard.", "success")
    audit(db, "carpool_confirmed", match.label,
          f"{seats} seat(s) confirmed on {match.offer.label}",
          "Both passenger and provider consented; contact details released to those parties only", user)
    db.flush()
    refresh_request(db, match.request)


def cancel_match(db: Session, match: CarpoolMatch, user: User, reason: str, net: Network) -> None:
    if match.status not in LIVE_MATCH:
        raise CarpoolError(f"This match is already {match.status}")
    is_provider = match.offer.provider_user_id == user.id
    mine = [m for m in match.members if m.journey.user_id == user.id and m.acceptance != "declined"]
    if not is_provider and not mine:
        raise PermissionError("You are not part of this match")
    audit(db, "carpool_cancelled", match.label,
          f"Cancelled by {'provider' if is_provider else 'passenger'}", reason, user)
    if is_provider:
        _notify_members(db, match, "Your carpool was cancelled by the driver",
                        "You are back on the listing and still awaiting transport.", "warning")
        _close(db, match, reason or "Cancelled by provider")
    else:
        notify(db, match.offer.provider_user_id, "A passenger cancelled",
               f"{sum(m.seats for m in mine)} seat(s) on your offer are free again.", "warning")
        for mm in mine:
            if mm.journey.status == "carpool_confirmed":
                mm.journey.status = "affected"
            _drop_member(db, mm, reason or "Cancelled by passenger")
    sync_demand(db, net, user)


def complete_match(db: Session, match: CarpoolMatch, user: User) -> None:
    if match.offer.provider_user_id != user.id:
        raise PermissionError("Only the driver can mark a ride complete")
    if match.status != "confirmed":
        raise CarpoolError("Only a confirmed ride can be completed")
    match.status = "completed"
    match.offer.provider.rides_completed += 1
    audit(db, "carpool_completed", match.label, f"{match.matched_seats} seat(s) completed", "", user)
    db.flush()
    refresh_request(db, match.request)


def report_match(db: Session, match: CarpoolMatch, user: User, reason: str) -> None:
    involved = match.offer.provider_user_id == user.id or any(m.journey.user_id == user.id for m in match.members)
    if not involved:
        raise PermissionError("You are not part of this match")
    db.add(CarpoolReport(match_id=match.id, reporter_user_id=user.id, reason=reason))
    audit(db, "carpool_reported", match.label, "Safety or conduct report filed", reason, user)


def withdraw_offer(db: Session, offer: CarpoolOffer, user: User, net: Network) -> None:
    if offer.provider_user_id != user.id:
        raise PermissionError("This is not your offer")
    if offer.status != "open":
        raise CarpoolError(f"Offer is already {offer.status}")
    offer.status = "withdrawn"
    for match in db.query(CarpoolMatch).filter(CarpoolMatch.offer_id == offer.id,
                                               CarpoolMatch.status.in_(LIVE_MATCH)):
        _notify_members(db, match, "A carpool offer was withdrawn",
                        "You are back on the listing and still awaiting transport.", "warning")
        _close(db, match, "Offer withdrawn by provider")
    audit(db, "carpool_offer_withdrawn", offer.label, "Offer withdrawn", "", user)
    sync_demand(db, net, user)


def leave_listing(db: Session, j: Journey, net: Network, user: User) -> None:
    j.carpool_opt_out = True
    withdraw_from_carpool(db, j, "Passenger left the listing")
    audit(db, "carpool_opt_out", j.ref, "Passenger left the carpool listing", "", user)


def _notify_members(db: Session, match: CarpoolMatch, title: str, body: str, kind: str) -> None:
    for m in match.members:
        if m.acceptance != "declined":
            notify(db, m.journey.user_id, title, body, kind)


# ---------------------------------------------------------------- privacy-aware views
def listing_view(r: CarpoolRequest) -> dict:
    """Public to signed-in users. Aggregates only, by construction: no member data is touched."""
    return {"id": r.id, "label": r.label, "destination": r.destination_name,
            "destination_zone": r.destination_zone, "dest_stop": r.dest_stop,
            "pickup_area": r.pickup_area, "origin_zone": r.origin_zone, "origin_stop": r.origin_stop,
            "passengers_waiting": r.passenger_count, "window_start": r.window_start,
            "window_end": r.window_end, "requirements": r.requirements, "status": r.status}


def match_view(db: Session, match: CarpoolMatch, user: User, net: Network) -> dict:
    offer = match.offer
    is_provider = offer.provider_user_id == user.id
    confirmed = match.status in ("confirmed", "completed")
    mine = [m for m in match.members if m.journey.user_id == user.id]
    view = {
        "id": match.id, "label": match.label, "status": match.status, "role": "provider" if is_provider else "passenger",
        "matched_seats": match.matched_seats, "detour_min": match.detour_min, "checks": match.checks,
        "pickup_min": match.pickup_min, "pickup_area": match.request.pickup_area,
        "destination": match.request.destination_name, "departure": offer.departure,
        "vehicle_type": offer.vehicle_type, "cancel_reason": match.cancel_reason,
        "passenger_acceptance_status": match.passenger_acceptance_status,
        "provider_confirmation_status": match.provider_confirmation_status,
        "parties": [{"seats": m.seats, "acceptance": m.acceptance,
                     "requirements": m.journey.requirements} for m in match.members],
        "my_acceptance": mine[0].acceptance if mine else None,
        "provider_trust": {"rides_completed": offer.provider.rides_completed,
                           "member_since": offer.provider.member_since, "verified": False},
        "contact": None,
    }
    if confirmed:
        view["pickup_stop"] = net.stops[match.pickup_stop].name
        if is_provider:
            view["contact"] = [{"name": m.journey.user.name.split()[0], "phone": m.journey.user.phone,
                                "seats": m.seats} for m in match.members if m.acceptance == "accepted"]
        elif mine and mine[0].acceptance == "accepted":
            view["contact"] = [{"name": offer.provider.name.split()[0], "phone": offer.provider.phone,
                                "seats": match.matched_seats}]
    return view
