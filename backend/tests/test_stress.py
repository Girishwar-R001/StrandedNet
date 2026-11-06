"""Hackathon stress constraints: the numbers judges will see, and the guarantees behind them."""
from datetime import timedelta

import pytest

from app.engines import allocation, reporting, scenarios, telemetry
from app.engines.network import Network
from app.models import Allocation, AuditEvent, CarpoolMatch, Journey, Vehicle, utcnow

from .conftest import journey


@pytest.fixture
def net(db):
    return Network.load(db)


def _packet(vehicle="RV-1", ts=None, **fields):
    return {"vehicle_id": vehicle, "sensor_id": "primary", "timestamp": ts or utcnow().timestamp(), **fields}


def _events(db, kind):
    return db.query(AuditEvent).filter_by(event_type=kind).all()


def _kpis(db):
    return scenarios.status(db)["kpis"]


def _seats_snapshot(db):
    db.expire_all()
    return {v.id: (v.available_seats, v.capacity, v.status) for v in db.query(Vehicle)}


def _baseline_confirmed(db, op):
    scenarios.load_baseline(db)
    scenarios.run_and_reserve(db, _op(db))


def _op(db):
    return scenarios._operator(db)


# ---------------------------------------------------------------- preset 1: baseline
def test_baseline_seats_twenty_and_rolls_four_into_one_corridor(db, op):
    scenarios.load_baseline(db)
    before = _kpis(db)
    assert (before["stranded_passengers"], before["official_seats"], before["carpool_rollover"]) == (24, 20, 0)

    result = scenarios.run_and_reserve(db, _op(db))
    assert result["seats"] == 20 and result["failed"] == []
    after = _kpis(db)
    assert after["carpool_rollover"] == 4 and after["over_allocation"] == 0
    assert [p["passengers"] for p in scenarios.status(db)["corridors"]] == [4]


def test_baseline_rollover_can_be_carried_by_one_four_seat_driver(db, op, client, as_user):
    scenarios.load_baseline(db)
    scenarios.run_and_reserve(db, _op(db))
    body = {"origin_stop": "HEB", "dest_stop": "WFD", "departure": 18 * 60 + 10, "available_seats": 4,
            "vehicle_type": "Hatchback", "consent": True}
    r = client.post("/api/carpool/offers", json=body, headers=as_user("meera"))
    assert r.status_code == 201 and r.json()["matches_proposed"] == 1
    db.expire_all()
    assert db.query(CarpoolMatch).one().matched_seats == 4


def test_presets_are_reproducible(db, op):
    def run():
        scenarios.load_surge(db)
        scenarios.run_and_reserve(db, _op(db))
        db.expire_all()
        return sorted((a.journey.ref, a.vehicle_id) for a in db.query(Allocation).filter_by(status="confirmed"))
    assert run() == run()


# ---------------------------------------------------------------- preset 2: surge
def test_surge_triples_demand_and_halves_the_fleet(db, op):
    scenarios.load_surge(db)
    k = _kpis(db)
    assert k["stranded_passengers"] == 72 and k["official_seats"] == 10
    assert db.get(Vehicle, "RV-2").status == "unavailable"
    assert db.get(Vehicle, "RV-1").capacity == 5 and db.get(Vehicle, "RV-3").capacity == 5


def test_surge_fills_exactly_ten_seats_with_zero_over_allocation(db, op):
    scenarios.load_surge(db)
    result = scenarios.run_and_reserve(db, _op(db))
    db.expire_all()
    assert result["seats"] == 10 and result["failed"] == []
    assert sum(a.seats for a in db.query(Allocation).filter_by(status="confirmed")) == 10
    assert reporting.integrity(db)["over_allocated"] == 0
    k = _kpis(db)
    assert k["official_seats_free"] == 0 and k["carpool_rollover"] == 62


def test_surge_cascades_sixty_two_into_four_corridor_pools(db, op):
    scenarios.load_surge(db)
    scenarios.run_and_reserve(db, _op(db))
    assert [p["passengers"] for p in scenarios.status(db)["corridors"]] == [18, 16, 15, 13]


def test_accessibility_is_a_hard_gate_under_surge(db, op):
    scenarios.load_surge(db)
    scenarios.run_and_reserve(db, _op(db))
    db.expire_all()
    a = db.query(Allocation).filter_by(journey_id=journey(db, "P-10").id, status="confirmed").one()
    assert a.vehicle_id == "RV-3"
    for row in db.query(Allocation).filter_by(status="confirmed"):
        if set(row.journey.requirements) & {"wheelchair", "step_free"}:
            assert row.vehicle.wheelchair


def test_surge_explanations_name_the_fleet_cut_and_the_requirement(db, op):
    scenarios.load_surge(db)
    scenarios.run_and_reserve(db, _op(db))
    db.expire_all()
    a = db.query(Allocation).filter_by(journey_id=journey(db, "P-10").id, status="confirmed").one()
    assert a.explanation.startswith("Prioritised under 50% fleet reduction:")
    assert "wheelchair requirement" in a.explanation


def test_baseline_explanations_do_not_claim_a_fleet_cut(db, op):
    _baseline_confirmed(db, op)
    db.expire_all()
    assert not any("fleet reduction" in a.explanation for a in db.query(Allocation))


def test_wave_matches_all_sixty_two_and_needs_consent_to_confirm(db, op):
    scenarios.load_surge(db)
    scenarios.run_and_reserve(db, _op(db))
    wave = scenarios.carpool_wave(db, _op(db))
    assert wave["seats_proposed"] == 62 and wave["still_unmatched"] == 0
    assert _kpis(db)["carpool_confirmed"] == 0     # a proposal confirms nothing

    scenarios.simulate_consent(db, _op(db))
    k = _kpis(db)
    assert k["carpool_confirmed"] == 62 and k["over_allocation"] == 0


def test_wave_is_audited_as_simulated_and_drivers_stay_off_the_login_list(db, op, client):
    scenarios.load_surge(db)
    scenarios.run_and_reserve(db, _op(db))
    scenarios.carpool_wave(db, _op(db))
    assert all("SIMULATED" in e.reason for e in _events(db, "carpool_offer_created"))
    accounts = client.get("/api/demo/accounts").json()["accounts"]
    assert not [a for a in accounts if "sim.stranded" in a["email"]] and len(accounts) == 19


def test_surge_banner_exposes_counts_only(db, op, client, as_user):
    scenarios.load_surge(db)
    scenarios.run_and_reserve(db, _op(db))
    body = client.get("/api/me/surge", headers=as_user("asha")).json()
    assert body["active"] and body["pooled"] == 62
    text = str(body)
    assert "Asha" not in text and "P-01" not in text and "+91" not in text


def test_surge_banner_is_off_for_the_baseline(db, op, client, as_user):
    _baseline_confirmed(db, op)
    assert client.get("/api/me/surge", headers=as_user("asha")).json()["active"] is False


# ---------------------------------------------------------------- constraint 10: sanitizer
@pytest.mark.parametrize("seats", [50, 9, -1])
def test_spike_is_rejected_and_seat_count_is_untouched(db, op, net, seats):
    scenarios.load_baseline(db)
    before = _seats_snapshot(db)
    assert telemetry.ingest(db, _packet(available_seats=seats), net)["outcome"] == "spike_rejected"
    db.commit()
    assert _seats_snapshot(db) == before
    assert len(_events(db, "TELEMETRY_SPIKE_REJECTED")) == 1


def test_spike_audit_message_matches_the_brief(db, op):
    scenarios.load_baseline(db)
    scenarios.inject(db, "spike", _op(db))
    change = _events(db, "TELEMETRY_SPIKE_REJECTED")[0].decision_or_change
    assert change == "[REJECTED] Sensor spike: Vehicle A reported 50 seats (max 8). Enforcing DB Atomic Lock."


def test_valid_seat_reading_is_recorded_but_never_applied(db, op, net):
    scenarios.load_baseline(db)
    before = _seats_snapshot(db)
    assert telemetry.ingest(db, _packet(available_seats=3), net)["outcome"] == "accepted"
    db.commit()
    assert _seats_snapshot(db) == before
    assert db.get(telemetry.VehicleTelemetry, "RV-1").last_reported_seats == 3


def test_packet_storm_drops_fourteen_of_fifteen_as_one_audit_line(db, op):
    scenarios.load_baseline(db)
    result = scenarios.inject(db, "storm", _op(db))
    assert result["dropped"] == 14
    rows = _events(db, "TELEMETRY_DUPLICATE_DROPPED")
    assert len(rows) == 1 and rows[0].reason.startswith("14 repeated frames")
    assert scenarios.status(db)["telemetry"]["duplicates_dropped"] == 14


def test_repeat_outside_the_window_is_not_a_duplicate(db, op, net):
    scenarios.load_baseline(db)
    ts = utcnow().timestamp()
    start = utcnow()
    telemetry.ingest(db, _packet(ts=ts, available_seats=8), net, at=start)
    late = start + timedelta(seconds=telemetry.DEDUP_WINDOW_S + 1)
    assert telemetry.ingest(db, _packet(ts=ts, available_seats=8), net, at=late)["outcome"] == "accepted"


def test_lost_gps_goes_stale_and_keeps_a_moving_position(db, op):
    scenarios.load_baseline(db)
    scenarios.inject(db, "gps", _op(db))
    feeds = {f["vehicle_id"]: f for f in scenarios.status(db)["telemetry"]["vehicles"]}
    c = feeds["RV-3"]
    assert c["status"] == "STALE_DEAD_RECKONING" and c["position"]["source"] == "dead_reckoning"
    assert c["position"]["lat"] is not None and db.get(Vehicle, "RV-3").status == "available"
    first = Network.load(db).stops["YEL"]
    assert (c["position"]["lat"], c["position"]["lng"]) != (first.lat, first.lng)
    assert feeds["RV-1"]["status"] == "VERIFIED"


def test_delayed_packet_is_not_applied_and_triggers_fallback(db, op, net):
    scenarios.load_baseline(db)
    old = utcnow().timestamp() - telemetry.STALE_AFTER_S - 5
    assert telemetry.ingest(db, _packet(ts=old, lat=1.0, lng=1.0), net)["outcome"] == "delayed"
    row = db.get(telemetry.VehicleTelemetry, "RV-1")
    assert row.status == telemetry.STALE and row.lat != 1.0


def test_fresh_packet_recovers_a_stale_feed(db, op, net):
    scenarios.load_baseline(db)
    scenarios.inject(db, "gps", _op(db))
    assert telemetry.ingest(db, _packet("RV-3", lat=13.0, lng=77.6), net)["outcome"] == "accepted"
    assert db.get(telemetry.VehicleTelemetry, "RV-3").status == telemetry.VERIFIED


def test_conflict_on_confirmed_bus_quarantines_without_touching_bookings(db, op):
    _baseline_confirmed(db, op)
    db.expire_all()
    seats = _seats_snapshot(db)
    bookings = sorted((a.id, a.status, a.seats_held) for a in db.query(Allocation).filter_by(vehicle_id="RV-1"))
    journeys = {j.ref: j.status for j in db.query(Journey)}
    assert bookings

    result = scenarios.inject(db, "conflict", _op(db))
    assert result["outcome"] == "quarantined" and result["confirmed_seats_preserved"] == 8

    assert _seats_snapshot(db) == seats
    assert sorted((a.id, a.status, a.seats_held) for a in db.query(Allocation).filter_by(vehicle_id="RV-1")) == bookings
    assert {j.ref: j.status for j in db.query(Journey)} == journeys
    event = _events(db, "TELEMETRY_CONFLICT_QUARANTINED")[0]
    assert "NON-DESTRUCTIVE LOCK ACTIVE" in event.decision_or_change
    assert "TELEMETRY_CONFLICT_PENDING_OPERATOR_REVIEW" in event.decision_or_change
    health = scenarios.status(db)["telemetry"]
    assert health["status"] == "SENSOR_CONFLICT_QUARANTINED" and health["conflicts"] == 1


def test_conflict_with_no_confirmed_passengers_changes_nothing(db, op):
    scenarios.load_baseline(db)
    assert scenarios.inject(db, "conflict", _op(db))["outcome"] == "offline_logged"
    assert scenarios.status(db)["telemetry"]["conflicts"] == 0


def test_quarantined_vehicle_takes_no_new_passengers(db, op):
    _baseline_confirmed(db, op)
    scenarios.inject(db, "conflict", _op(db))
    db.expire_all()
    a = db.query(Allocation).filter_by(vehicle_id="RV-1", status="confirmed").first()
    allocation.release(db, a, "Test frees a seat", _op(db))
    db.commit()
    run = allocation.run_allocation(db, Network.load(db), _op(db))
    db.commit()
    assert not db.query(Allocation).filter_by(run_id=run.id, vehicle_id="RV-1").first()


def test_restore_does_not_clear_a_quarantine(db, op, client, operator):
    _baseline_confirmed(db, op)
    scenarios.inject(db, "conflict", _op(db))
    assert client.post("/api/demo/telemetry/restore", headers=operator).status_code == 200
    db.expire_all()
    assert scenarios.status(db)["telemetry"]["conflicts"] == 1


def test_operator_can_keep_a_quarantined_vehicle(db, op, client, operator):
    _baseline_confirmed(db, op)
    scenarios.inject(db, "conflict", _op(db))
    r = client.post("/api/op/telemetry/RV-1/resolve", json={"decision": "keep", "reason": "Driver confirmed by radio"},
                    headers=operator)
    assert r.status_code == 200
    db.expire_all()
    assert scenarios.status(db)["telemetry"]["status"] == "VERIFIED"
    assert db.query(Allocation).filter_by(vehicle_id="RV-1", status="confirmed").count() > 0
    assert "radio" in _events(db, "TELEMETRY_CONFLICT_RESOLVED")[0].reason


def test_operator_withdrawal_flags_passengers_rather_than_dropping_them(db, op, client, operator):
    _baseline_confirmed(db, op)
    scenarios.inject(db, "conflict", _op(db))
    r = client.post("/api/op/telemetry/RV-1/resolve", json={"decision": "withdraw", "reason": "Bus confirmed broken down"},
                    headers=operator)
    assert r.status_code == 200
    db.expire_all()
    assert db.get(Vehicle, "RV-1").status == "unavailable"
    assert db.query(Allocation).filter_by(vehicle_id="RV-1", status="needs_review").count() > 0


def test_resolving_with_no_conflict_is_refused(db, op, client, operator):
    scenarios.load_baseline(db)
    r = client.post("/api/op/telemetry/RV-1/resolve", json={"decision": "keep", "reason": "Nothing"}, headers=operator)
    assert r.status_code == 409


def test_faults_during_surge_keep_over_allocation_at_zero(db, op):
    scenarios.load_surge(db)
    scenarios.run_and_reserve(db, _op(db))
    for fault in ("spike", "storm", "gps", "conflict"):
        scenarios.inject(db, fault, _op(db))
    k = _kpis(db)
    assert k["over_allocation"] == 0 and k["official_seats"] == 10


# ---------------------------------------------------------------- access
def test_stress_controls_are_operator_only(db, client, as_user):
    headers = as_user("asha")
    assert client.get("/api/op/stress", headers=headers).status_code == 403
    assert client.post("/api/op/telemetry/ingest", json={"vehicle_id": "RV-1"}, headers=headers).status_code == 403
    for path in ("/api/demo/scenario/surge", "/api/demo/telemetry/spike", "/api/demo/carpool-wave"):
        assert client.post(path, headers=headers).status_code == 403


def test_ingest_endpoint_runs_the_sanitizer(db, op, client, operator):
    scenarios.load_baseline(db)
    body = {"vehicle_id": "RV-1", "available_seats": 50}
    assert client.post("/api/op/telemetry/ingest", json=body, headers=operator).json()["outcome"] == "spike_rejected"
    assert client.post("/api/op/telemetry/ingest", json={"vehicle_id": "NOPE"}, headers=operator).status_code == 404
