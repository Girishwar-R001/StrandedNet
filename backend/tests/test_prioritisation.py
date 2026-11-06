"""Prioritisation: documented, configurable, explained, and unable to override feasibility."""
import pytest

from app.engines import allocation, priority
from app.engines.feasibility import assess_vehicle
from app.engines.network import Network
from app.models import Allocation, AllocationRun, AuditEvent, Vehicle
from app.services import DEFAULT_THRESHOLDS, DEFAULT_WEIGHTS, put_setting

from .conftest import allocate_and_confirm, cancel_x5, journey, simulate_prefs


def test_default_weights_sum_to_one():
    assert sum(DEFAULT_WEIGHTS.values()) == pytest.approx(1)


def test_score_is_exactly_the_documented_formula(db, op):
    cancel_x5(db, op)
    j, v = journey(db, "P-05"), db.get(Vehicle, "RV-1")
    total, breakdown, _ = priority.score(j, v, 1151, [], [], DEFAULT_WEIGHTS, DEFAULT_THRESHOLDS, 1060)
    expected = sum(DEFAULT_WEIGHTS[k] * f["value"] for k, f in breakdown["factors"].items())
    assert total == pytest.approx(expected, abs=0.002)


def test_every_allocation_has_breakdown_checks_and_explanation(db, op):
    cancel_x5(db, op)
    allocation.run_allocation(db, Network.load(db), op)
    db.commit()
    rows = db.query(Allocation).filter_by(status="proposed").all()
    assert rows
    for a in rows:
        assert set(a.breakdown["factors"]) == set(DEFAULT_WEIGHTS)
        assert all(c["ok"] for c in a.checks)
        assert a.journey.ref in a.explanation and a.vehicle_id in a.explanation


def test_every_unplaced_party_has_a_stated_reason(db, op):
    cancel_x5(db, op)
    run = allocation.run_allocation(db, Network.load(db), op)
    db.commit()
    assert run.summary["unplaced"]
    assert all(u["reason"] for u in run.summary["unplaced"])


def test_accessibility_is_a_constraint_not_a_score(db, op):
    cancel_x5(db, op)
    net = Network.load(db)
    wheelchair = journey(db, "P-10")
    assert not assess_vehicle(wheelchair, db.get(Vehicle, "RV-1"), net, 1060, 8).ok
    assert "accessibility" not in priority.FACTOR_LABELS


def test_no_weighting_can_place_a_wheelchair_user_on_an_unsuitable_vehicle(db, op):
    cancel_x5(db, op)
    put_setting(db, "weights", {"waiting": 1.0, "urgency": 0, "scarcity": 0, "group": 0, "preference": 0})
    db.commit()
    allocate_and_confirm(db, op)
    a = db.query(Allocation).filter_by(journey_id=journey(db, "P-10").id, status="confirmed").one()
    assert db.get(Vehicle, a.vehicle_id).wheelchair


def test_override_cannot_bypass_accessibility_or_capacity(db, op):
    cancel_x5(db, op)
    net = Network.load(db)
    with pytest.raises(allocation.ReservationError):
        allocation.create_confirmed(db, journey(db, "P-10"), db.get(Vehicle, "RV-1"), net, "Test", op)
    db.rollback()
    v = db.get(Vehicle, "RV-1")
    v.available_seats = 3
    db.commit()
    with pytest.raises(allocation.ReservationError):
        allocation.create_confirmed(db, journey(db, "P-05"), v, net, "Test", op)
    db.rollback()


def test_changing_weights_changes_the_scores(db, op):
    cancel_x5(db, op)
    allocation.run_allocation(db, Network.load(db), op)
    db.commit()
    before = {a.journey_id: a.priority_score for a in db.query(Allocation).filter_by(status="proposed")}
    put_setting(db, "weights", {"waiting": 0, "urgency": 0, "scarcity": 0, "group": 1.0, "preference": 0})
    db.commit()
    allocation.run_allocation(db, Network.load(db), op)
    db.commit()
    after = {a.journey_id: a.priority_score for a in db.query(Allocation).filter_by(status="proposed")}
    assert before != after


def test_rules_api_validates_and_audits(client, operator, db):
    bad = {"weights": {**DEFAULT_WEIGHTS, "waiting": 0.9}, "reason": "Testing"}
    assert client.put("/api/op/rules", json=bad, headers=operator).status_code == 422
    good = {"weights": {"waiting": 0.2, "urgency": 0.4, "scarcity": 0.2, "group": 0.1, "preference": 0.1},
            "reason": "Prioritise deadlines tonight"}
    assert client.put("/api/op/rules", json=good, headers=operator).status_code == 200
    event = db.query(AuditEvent).filter_by(event_type="rules_changed").one()
    assert event.reason == "Prioritise deadlines tonight"


def test_override_requires_a_reason_and_is_audited(client, operator, db, op):
    cancel_x5(db, op)
    j = journey(db, "P-04")
    body = {"journey_id": j.id, "vehicle_id": "RV-1"}
    assert client.post("/api/op/allocations/override", json=body, headers=operator).status_code == 422
    r = client.post("/api/op/allocations/override", json={**body, "reason": "Medical appointment"}, headers=operator)
    assert r.status_code == 201, r.text
    assert r.json()["is_override"] and r.json()["status"] == "confirmed"
    event = db.query(AuditEvent).filter_by(event_type="operator_override").one()
    assert event.reason == "Medical appointment"


def test_engine_beats_first_come_baseline_on_stranding(db, op):
    """Scenario design: a late-reporting party of 4 with no in-time alternative."""
    cancel_x5(db, op)
    simulate_prefs(db)
    run = allocation.run_allocation(db, Network.load(db), op)
    db.commit()
    s = run.summary
    assert s["engine"]["seats"] >= s["baseline_fcfs"]["seats"]
    assert s["engine"]["stranded_no_alternative"] < s["baseline_fcfs"]["stranded_no_alternative"]
    assert db.query(AllocationRun).count() == 1
