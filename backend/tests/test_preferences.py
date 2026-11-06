"""A preference is never a booking."""
from app.engines import allocation, disruption, reporting
from app.engines.network import Network
from app.models import Allocation, JourneyOption, Preference, Vehicle

from .conftest import allocate_and_confirm, cancel_x5, journey, simulate_prefs


def _options(db, ref):
    j = journey(db, ref)
    return j, db.query(JourneyOption).filter_by(journey_id=j.id, status="active").order_by(JourneyOption.id).all()


def _submit(client, headers, j, first, second=None):
    return client.put(f"/api/me/journeys/{j.id}/preferences", headers=headers,
                      json={"first_option_id": first, "second_option_id": second})


def test_options_reflect_the_passengers_constraints(db, op):
    cancel_x5(db, op)
    j, options = _options(db, "P-10")
    # A wheelchair user is only offered step-free transport.
    assert options and all(o.vehicle_id == "RV-3" for o in options if o.reservable)
    for o in options:
        assert o.meets_deadline == (o.arrival <= j.latest_arrival)


def test_replacement_options_are_suggested_never_confirmed(client, db, op, as_user):
    cancel_x5(db, op)
    j = journey(db, "P-01")
    rows = client.get(f"/api/me/journeys/{j.id}/options", headers=as_user("asha")).json()
    assert rows and all(r["option_status"] == "suggested" for r in rows)


def test_selecting_does_not_reserve_anything(client, db, op, as_user):
    cancel_x5(db, op)
    j, options = _options(db, "P-01")
    r = _submit(client, as_user("asha"), j, options[0].id)
    assert r.status_code == 200, r.text
    db.expire_all()
    assert db.get(Vehicle, "RV-1").available_seats == 8
    assert db.query(Allocation).count() == 0
    assert r.json()["stage"]["code"] == "preference_submitted"
    assert "isn't a booking" in r.json()["stage"]["detail"]


def test_preferences_appear_immediately_for_operators(client, db, op, operator, as_user):
    cancel_x5(db, op)
    j, options = _options(db, "P-01")
    _submit(client, as_user("asha"), j, options[0].id, options[1].id)
    body = client.get("/api/op/preferences", headers=operator).json()
    row = next(r for r in body["rows"] if r["ref"] == "P-01")
    assert row["first"]["option_id"] == options[0].id
    assert row["second"]["option_id"] == options[1].id
    assert row["first"]["availability"]["code"] == "available"
    assert row["state"] == "first_available"
    assert body["submitted"] == 1 and body["not_selected"] == 13
    assert any(o["first"] >= 1 for o in body["options"])


def test_passengers_without_a_preference_are_shown(client, db, op, operator):
    cancel_x5(db, op)
    body = client.get("/api/op/preferences", headers=operator).json()
    assert body["not_selected"] == 14
    assert {r["state"] for r in body["rows"]} == {"none_submitted"}


def test_first_choice_full_falls_to_feasible_choice_with_explanation(db, op):
    cancel_x5(db, op)
    simulate_prefs(db)
    v = db.get(Vehicle, "RV-1")
    v.available_seats = 2  # the first choice for several East parties can no longer fit them
    db.commit()
    summary = reporting.preferences_summary(db)
    row = next(r for r in summary["rows"] if r["ref"] == "P-03")
    assert row["first"]["availability"]["code"] == "full"
    assert row["state"] in ("second_feasible", "none_feasible")


def test_preference_cannot_override_capacity(db, op):
    """Every East party ranks RV-1 first; only 8 seats may be given regardless."""
    cancel_x5(db, op)
    simulate_prefs(db)
    allocate_and_confirm(db, op)
    db.expire_all()
    seated = sum(a.seats for a in db.query(Allocation).filter_by(vehicle_id="RV-1", status="confirmed"))
    assert seated <= 8
    assert db.get(Vehicle, "RV-1").available_seats == 8 - seated


def test_engine_honours_preference_when_two_vehicles_are_feasible(db, op):
    """A party able to use RV-1 or RV-3 (Hebbal to City Railway) gets the one it ranked first."""
    cancel_x5(db, op)
    j = journey(db, "P-12")
    j.dest_stop = "SBC"
    db.commit()
    from app.engines import alternatives
    alternatives.refresh_all(db, Network.load(db), 1060)
    db.commit()
    rv3 = db.query(JourneyOption).filter_by(journey_id=j.id, vehicle_id="RV-3", status="active").one()
    db.add(Preference(journey_id=j.id, option_id=rv3.id, rank=1))
    db.commit()
    allocation.run_allocation(db, Network.load(db), op)
    db.commit()
    a = db.query(Allocation).filter_by(journey_id=j.id, status="proposed").one()
    assert a.vehicle_id == "RV-3" and a.preference_outcome == "first_choice"


def test_preferences_can_change_until_confirmation_then_lock(client, db, op, as_user):
    cancel_x5(db, op)
    j, options = _options(db, "P-07")
    headers = as_user("priya")
    assert _submit(client, headers, j, options[0].id).status_code == 200
    assert _submit(client, headers, j, options[1].id, options[0].id).status_code == 200
    assert db.query(Preference).filter_by(journey_id=j.id).count() == 2
    allocate_and_confirm(db, op)
    assert journey(db, "P-07").status == "allocated"
    assert _submit(client, headers, j, options[0].id).status_code == 409


def test_stages_keep_proposed_approved_and_confirmed_distinct(client, db, op, as_user):
    """The passenger never sees an engine proposal, and approval is not yet a seat."""
    cancel_x5(db, op)
    headers = as_user("priya")
    allocation.run_allocation(db, Network.load(db), op)
    db.commit()
    view = lambda: client.get("/api/me/journeys", headers=headers).json()[0]  # noqa: E731
    assert view()["allocation"] is None
    a = db.query(Allocation).filter_by(journey_id=journey(db, "P-07").id, status="proposed").one()
    allocation.approve(db, a, op)
    db.commit()
    assert view()["stage"]["code"] == "operator_approved"
    assert view()["allocation"]["status"] == "approved"
    db.expire_all()
    assert db.get(Vehicle, "RV-2").available_seats == 7
    allocation.reserve(db, db.get(Allocation, a.id), Network.load(db), op)
    db.commit()
    assert view()["stage"]["code"] == "seat_confirmed"


def test_first_and_second_must_differ(client, db, op, as_user):
    cancel_x5(db, op)
    j, options = _options(db, "P-01")
    assert _submit(client, as_user("asha"), j, options[0].id, options[0].id).status_code == 422


def test_cannot_select_another_passengers_option(client, db, op, as_user):
    cancel_x5(db, op)
    j, _ = _options(db, "P-01")
    _, theirs = _options(db, "P-07")
    assert _submit(client, as_user("asha"), j, theirs[0].id).status_code == 422


def test_cannot_touch_another_passengers_journey(client, db, op, as_user):
    cancel_x5(db, op)
    j, options = _options(db, "P-07")
    assert _submit(client, as_user("asha"), j, options[0].id).status_code == 404
    assert client.get(f"/api/me/journeys/{j.id}/options", headers=as_user("asha")).status_code == 404


def test_disruption_invalidates_a_chosen_option_visibly(db, op):
    cancel_x5(db, op)
    j, options = _options(db, "P-07")
    rv2 = next(o for o in options if o.vehicle_id == "RV-2")
    db.add(Preference(journey_id=j.id, option_id=rv2.id, rank=1))
    db.commit()
    disruption.create(db, kind="vehicle_unavailable", actor=op, vehicle_id="RV-2")
    db.commit()
    db.expire_all()
    assert db.query(Preference).filter_by(journey_id=j.id).one().status == "invalidated"
    assert db.get(JourneyOption, rv2.id).status == "unavailable"


def test_self_resolving_frees_a_seat_for_others(client, db, op, as_user):
    cancel_x5(db, op)
    allocate_and_confirm(db, op)
    j = journey(db, "P-07")
    before = db.get(Vehicle, "RV-2").available_seats
    r = client.post(f"/api/me/journeys/{j.id}/self-resolve", json={}, headers=as_user("priya"))
    assert r.status_code == 200, r.text
    db.expire_all()
    assert db.get(Vehicle, "RV-2").available_seats == before + j.party_size
    assert journey(db, "P-07").status == "self_resolved"
