"""Carpool: independent seat limits, explicit two-sided consent, privacy by construction."""
import pytest

from app.engines import allocation, carpool, reporting
from app.engines.network import Network
from app.models import (Allocation, CarpoolMatch, CarpoolOffer, CarpoolRequest, CarpoolRequestMember,
                        Journey, User, Vehicle)
from app.seed import hm
from app.services import DEFAULT_THRESHOLDS

from .conftest import allocate_and_confirm, cancel_x5, journey, simulate_prefs

OFFER = dict(origin_stop="HEB", dest_stop="WFD", departure=hm("18:10"), available_seats=3,
             vehicle_type="Hatchback", luggage=True, consent=True)


def _prepare(db, op):
    cancel_x5(db, op)
    simulate_prefs(db)
    allocate_and_confirm(db, op)


def _offer(client, headers, **changes):
    return client.post("/api/carpool/offers", json={**OFFER, **changes}, headers=headers)


def _offer_obj(db, **kw):
    provider = db.query(User).filter_by(email="meera@stranded.demo").one()
    data = dict(label="T", provider_user_id=provider.id, origin_stop="HEB", dest_stop="WFD",
                departure=hm("18:10"), available_seats=3)
    return CarpoolOffer(**{**data, **kw})


def _match(db):
    return db.query(CarpoolMatch).order_by(CarpoolMatch.id.desc()).first()


def test_unmet_demand_is_published_only_after_official_allocation(db, op):
    cancel_x5(db, op)
    assert db.query(CarpoolRequest).count() == 0
    simulate_prefs(db)
    allocate_and_confirm(db, op)
    listed = {m.journey.ref for m in db.query(CarpoolRequestMember).filter_by(active=True)}
    unresolved = {j.ref for j in carpool.unresolved(db)}
    assert listed == unresolved and listed
    assert not any(j.status == "allocated" for j in (journey(db, r) for r in listed))


def test_compatible_parties_are_aggregated_into_one_listing(db, op):
    _prepare(db, op)
    rows = [r for r in db.query(CarpoolRequest) if r.pickup_area == "Hebbal area" and r.destination_name == "Whitefield"]
    assert len(rows) == 1 and rows[0].passenger_count == 4


def test_three_seat_offer_never_takes_a_group_of_four(db, op):
    """Spec 5.7.C, verbatim."""
    cancel_x5(db, op)
    net = Network.load(db)
    j = journey(db, "P-05")
    assert j.party_size == 4
    assert carpool._best_subset([j], 3) == []
    # Leave P-05 as the only unmet demand, then offer three seats on exactly their route.
    allocation.run_allocation(db, net, op)
    for a in db.query(Allocation).filter(Allocation.status == "proposed"):
        a.status = "rejected"
    for other in db.query(Journey).filter(Journey.status == "affected", Journey.ref != "P-05"):
        other.status = "self_resolved"
    db.commit()
    carpool.sync_demand(db, net, op)
    db.commit()
    offer = _offer_obj(db, origin_stop="MGR", departure=hm("18:20"))
    db.add(offer)
    db.flush()
    result = carpool.match_offer(db, offer, net, op)
    assert result["matches"] == []
    assert any("never split" in r for n in result["notes"] for r in n["reasons"])

    # Four seats on the same journey succeeds, proving seats were the only obstacle.
    roomy = _offer_obj(db, label="T2", origin_stop="MGR", departure=hm("18:20"), available_seats=4)
    db.add(roomy)
    db.flush()
    assert [m.matched_seats for m in carpool.match_offer(db, roomy, net, op)["matches"]] == [4]


def test_match_seats_never_exceed_offer(client, db, op, as_user):
    _prepare(db, op)
    r = _offer(client, as_user("meera"), available_seats=2)
    assert r.status_code == 201, r.text
    m = _match(db)
    assert m.matched_seats == 2
    db.expire_all()
    assert db.get(CarpoolOffer, m.offer_id).reserved_seats == 2


def test_parties_fill_the_offer_as_whole_parties(client, db, op, as_user):
    _prepare(db, op)
    _offer(client, as_user("meera"), available_seats=3)
    m = _match(db)
    assert sorted(x.seats for x in m.members) == [1, 2] and m.matched_seats == 3


def test_wrong_direction_is_rejected(db, op):
    _prepare(db, op)
    net = Network.load(db)
    offer = _offer_obj(db, origin_stop="WFD", dest_stop="HEB")
    result = carpool.evaluate(offer, journey(db, "P-01"), net, DEFAULT_THRESHOLDS)
    assert not result["ok"]


def test_excess_detour_is_rejected(db, op):
    _prepare(db, op)
    net = Network.load(db)
    offer = _offer_obj(db, origin_stop="JAY", dest_stop="WFD", departure=hm("17:30"))
    result = carpool.evaluate(offer, journey(db, "P-01"), net, DEFAULT_THRESHOLDS)
    assert any(c["name"] == "detour" and not c["ok"] for c in result["checks"])


def test_incompatible_timing_is_rejected(db, op):
    _prepare(db, op)
    net = Network.load(db)
    offer = _offer_obj(db, departure=hm("20:30"))
    result = carpool.evaluate(offer, journey(db, "P-01"), net, DEFAULT_THRESHOLDS)
    assert any(c["name"] == "timing" and not c["ok"] for c in result["checks"])


def test_requirements_are_enforced_independently(db, op):
    cancel_x5(db, op)
    net = Network.load(db)
    j = journey(db, "P-10")
    plain = _offer_obj(db, origin_stop="YEL", dest_stop="SBC", departure=hm("17:50"), wheelchair=False)
    ramp = _offer_obj(db, origin_stop="YEL", dest_stop="SBC", departure=hm("17:50"), wheelchair=True)
    assert not carpool.evaluate(plain, j, net, DEFAULT_THRESHOLDS)["ok"]
    assert carpool.evaluate(ramp, j, net, DEFAULT_THRESHOLDS)["ok"]


def test_offer_requires_explicit_consent(client, db, op, as_user):
    _prepare(db, op)
    assert _offer(client, as_user("meera"), consent=False).status_code == 422


def test_offer_is_not_a_confirmation(client, db, op, as_user):
    _prepare(db, op)
    _offer(client, as_user("meera"))
    m = _match(db)
    assert m.status == "awaiting_passenger"
    assert all(x.journey.status == "affected" for x in m.members)


def test_provider_cannot_confirm_before_passengers_accept(client, db, op, as_user):
    _prepare(db, op)
    _offer(client, as_user("meera"))
    m = _match(db)
    r = client.post(f"/api/carpool/matches/{m.id}/provider-response", json={"accept": True}, headers=as_user("meera"))
    assert r.status_code == 409
    db.expire_all()
    assert _match(db).status == "awaiting_passenger"


def test_all_parties_and_provider_must_consent(client, db, op, as_user):
    _prepare(db, op)
    _offer(client, as_user("meera"))
    mid = _match(db).id
    url = f"/api/carpool/matches/{mid}"
    assert client.post(f"{url}/passenger-response", json={"accept": True}, headers=as_user("asha")).status_code == 200
    db.expire_all()
    assert _match(db).status == "awaiting_passenger"  # Vikram has not answered
    client.post(f"{url}/passenger-response", json={"accept": True}, headers=as_user("vikram"))
    db.expire_all()
    assert _match(db).status == "awaiting_provider"
    assert journey(db, "P-01").status == "affected"   # still not confirmed
    client.post(f"{url}/provider-response", json={"accept": True}, headers=as_user("meera"))
    db.expire_all()
    assert _match(db).status == "confirmed"
    assert journey(db, "P-01").status == "carpool_confirmed"


def test_one_party_declining_releases_only_their_seats(client, db, op, as_user):
    _prepare(db, op)
    _offer(client, as_user("meera"))
    m = _match(db)
    url = f"/api/carpool/matches/{m.id}"
    client.post(f"{url}/passenger-response", json={"accept": False}, headers=as_user("vikram"))
    client.post(f"{url}/passenger-response", json={"accept": True}, headers=as_user("asha"))
    db.expire_all()
    m = db.get(CarpoolMatch, m.id)
    assert m.matched_seats == 2 and m.status == "awaiting_provider"
    assert journey(db, "P-02").status == "affected"
    # The freed seat goes straight to the next compatible party, as its own proposal.
    newest = _match(db)
    assert newest.id != m.id and [x.journey.ref for x in newest.members] == ["P-14"]
    assert db.get(CarpoolOffer, m.offer_id).reserved_seats == 3


def test_strangers_cannot_answer_a_match(client, db, op, as_user):
    _prepare(db, op)
    _offer(client, as_user("meera"))
    url = f"/api/carpool/matches/{_match(db).id}"
    assert client.post(f"{url}/passenger-response", json={"accept": True}, headers=as_user("arjun")).status_code == 403


def test_listing_contains_no_personal_data(client, db, op, as_user):
    _prepare(db, op)
    body = client.get("/api/carpool/requests", headers=as_user("arjun")).text
    for j in db.query(Journey):
        assert j.user.name.split()[0] not in body and j.user.phone not in body
        assert j.ref not in body
        assert f"{j.lat:.4f}" not in body
    assert "journey_id" not in body


def test_contact_details_are_hidden_until_confirmed(client, db, op, as_user):
    _prepare(db, op)
    _offer(client, as_user("meera"))
    mid = _match(db).id
    url = f"/api/carpool/matches/{mid}"

    def views():
        return (client.get("/api/carpool/matches/mine", headers=as_user("meera")).json()[0],
                client.get("/api/carpool/matches/mine", headers=as_user("asha")).json()[0])

    provider, passenger = views()
    assert provider["contact"] is None and passenger["contact"] is None
    assert "Meera" not in str(passenger) and "Asha" not in str(provider)
    assert "pickup_stop" not in provider

    client.post(f"{url}/passenger-response", json={"accept": True}, headers=as_user("asha"))
    client.post(f"{url}/passenger-response", json={"accept": True}, headers=as_user("vikram"))
    assert views()[0]["contact"] is None  # passenger consent alone releases nothing

    client.post(f"{url}/provider-response", json={"accept": True}, headers=as_user("meera"))
    provider, passenger = views()
    assert provider["contact"][0]["phone"] and passenger["contact"][0]["name"] == "Meera"
    assert client.get("/api/carpool/matches/mine", headers=as_user("arjun")).json() == []


def test_no_verification_is_claimed(client, db, op, as_user):
    _prepare(db, op)
    _offer(client, as_user("meera"))
    view = client.get("/api/carpool/matches/mine", headers=as_user("asha")).json()[0]
    assert view["provider_trust"]["verified"] is False


def test_carpool_is_never_counted_as_official(client, db, op, as_user):
    _prepare(db, op)
    allocations_before = db.query(Allocation).count()
    seats_before = {v.id: v.available_seats for v in db.query(Vehicle)}
    official_before = reporting.metrics(db)["official_confirmed"]
    _offer(client, as_user("meera"))
    mid = _match(db).id
    url = f"/api/carpool/matches/{mid}"
    client.post(f"{url}/passenger-response", json={"accept": True}, headers=as_user("asha"))
    client.post(f"{url}/passenger-response", json={"accept": True}, headers=as_user("vikram"))
    client.post(f"{url}/provider-response", json={"accept": True}, headers=as_user("meera"))
    db.expire_all()
    assert db.query(Allocation).count() == allocations_before
    assert {v.id: v.available_seats for v in db.query(Vehicle)} == seats_before
    m = reporting.metrics(db)
    assert m["official_confirmed"] == official_before and m["carpool_confirmed"] == 3


def test_cancelling_a_confirmed_ride_returns_passengers_to_demand(client, db, op, as_user):
    _prepare(db, op)
    _offer(client, as_user("meera"))
    mid = _match(db).id
    url = f"/api/carpool/matches/{mid}"
    client.post(f"{url}/passenger-response", json={"accept": True}, headers=as_user("asha"))
    client.post(f"{url}/passenger-response", json={"accept": True}, headers=as_user("vikram"))
    client.post(f"{url}/provider-response", json={"accept": True}, headers=as_user("meera"))
    r = client.post(f"{url}/cancel", json={"reason": "Car trouble"}, headers=as_user("meera"))
    assert r.status_code == 200, r.text
    db.expire_all()
    assert db.get(CarpoolMatch, mid).status == "cancelled"
    assert journey(db, "P-01").status == "affected"
    offer = db.get(CarpoolOffer, db.get(CarpoolMatch, mid).offer_id)
    assert offer.reserved_seats <= offer.available_seats
    assert journey(db, "P-01").id in {j.id for j in carpool.unresolved(db)}


def test_withdrawing_an_offer_cancels_pending_matches(client, db, op, as_user):
    _prepare(db, op)
    offer_id = _offer(client, as_user("meera")).json()["offer"]["id"]
    assert client.post(f"/api/carpool/offers/{offer_id}/withdraw", headers=as_user("meera")).status_code == 200
    db.expire_all()
    assert _match(db).status == "cancelled"
    assert db.get(CarpoolOffer, offer_id).reserved_seats == 0


def test_reports_are_recorded_and_restricted(client, db, op, as_user, operator):
    _prepare(db, op)
    _offer(client, as_user("meera"))
    url = f"/api/carpool/matches/{_match(db).id}/report"
    assert client.post(url, json={"reason": "Unsafe"}, headers=as_user("arjun")).status_code == 403
    assert client.post(url, json={"reason": "Unsafe driving"}, headers=as_user("asha")).status_code == 200
    assert client.get("/api/op/carpool", headers=operator).json()["summary"]["reports"] == 1


def test_official_seat_withdraws_a_party_from_pending_carpool(client, db, op, as_user):
    """A party must never hold an official seat and a carpool seat together."""
    _prepare(db, op)
    _offer(client, as_user("meera"))
    m = _match(db)
    j = journey(db, "P-02")
    v = Vehicle(id="RV-9", vehicle_type="Van", capacity=4, available_seats=4, stops=["HEB", "WFD"], ready_min=hm("18:05"))
    db.add(v)
    db.commit()
    allocation.create_confirmed(db, j, v, Network.load(db), "Extra run added", op)
    db.commit()
    db.expire_all()
    m = _match(db)
    assert next(x for x in m.members if x.journey_id == j.id).acceptance == "declined"
    assert m.matched_seats == 2


def test_carpool_confirmed_party_cannot_also_take_an_official_seat(client, db, op, as_user):
    """An official proposal raised while a carpool is pending must not double-seat the party."""
    _prepare(db, op)
    _offer(client, as_user("meera"))
    mid = _match(db).id
    j = journey(db, "P-02")
    v = db.get(Vehicle, "RV-2")
    v.stops = ["HEB", "WFD"]
    db.commit()
    stale = Allocation(journey_id=j.id, vehicle_id="RV-2", seats=1, pickup_stop="HEB",
                       pickup_min=hm("18:05"), arrival_min=hm("18:50"), status="proposed")
    db.add(stale)
    db.commit()
    stale_id, seats_before = stale.id, v.available_seats

    url = f"/api/carpool/matches/{mid}"
    client.post(f"{url}/passenger-response", json={"accept": True}, headers=as_user("asha"))
    client.post(f"{url}/passenger-response", json={"accept": True}, headers=as_user("vikram"))
    client.post(f"{url}/provider-response", json={"accept": True}, headers=as_user("meera"))
    db.expire_all()
    assert db.get(Allocation, stale_id).status == "cancelled"

    # Even with the proposal forced back to life, the reservation path refuses it.
    db.get(Allocation, stale_id).status = "proposed"
    db.commit()
    with pytest.raises(allocation.ReservationError):
        allocation.reserve(db, db.get(Allocation, stale_id), Network.load(db), op)
    db.rollback()
    db.expire_all()
    assert journey(db, "P-02").status == "carpool_confirmed"
    assert db.get(Vehicle, "RV-2").available_seats == seats_before


def test_provider_can_complete_and_trust_count_rises(client, db, op, as_user):
    _prepare(db, op)
    _offer(client, as_user("meera"))
    url = f"/api/carpool/matches/{_match(db).id}"
    assert client.post(f"{url}/complete", headers=as_user("meera")).status_code == 409
    client.post(f"{url}/passenger-response", json={"accept": True}, headers=as_user("asha"))
    client.post(f"{url}/passenger-response", json={"accept": True}, headers=as_user("vikram"))
    client.post(f"{url}/provider-response", json={"accept": True}, headers=as_user("meera"))
    assert client.post(f"{url}/complete", headers=as_user("meera")).status_code == 200
    db.expire_all()
    assert db.query(User).filter_by(email="meera@stranded.demo").one().rides_completed == 13
