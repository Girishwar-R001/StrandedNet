"""Disruption recovery: reassess everything, never silently overwrite a confirmed booking."""
from app.engines import disruption, reporting
from app.engines.network import Network
from app.models import Allocation, AuditEvent, Journey, Notification, Segment, Service, Vehicle

from .conftest import allocate_and_confirm, cancel_x5, journey, simulate_prefs


def _segment(db, a, b):
    return db.query(Segment).filter(((Segment.a == a) & (Segment.b == b)) | ((Segment.a == b) & (Segment.b == a))).one()


def _confirmed(db, vehicle_id):
    return db.query(Allocation).filter_by(vehicle_id=vehicle_id, status="confirmed").all()


def _prepare(db, op):
    cancel_x5(db, op)
    simulate_prefs(db)
    allocate_and_confirm(db, op)


def test_cancellation_affects_exactly_the_booked_passengers(db, op):
    cancel_x5(db, op)
    affected = db.query(Journey).filter_by(status="affected").all()
    assert sum(j.party_size for j in affected) == 24
    assert all(j.booked_service_id == "X5" for j in affected)
    assert db.query(Journey).filter_by(status="normal").count() == 2


def test_cancellation_notifies_each_party_and_is_audited(db, op):
    cancel_x5(db, op)
    assert db.query(Notification).filter_by(user_id=journey(db, "P-01").user_id).count() == 1
    assert db.query(AuditEvent).filter_by(event_type="disruption_created").count() == 1


def test_cancelled_service_disappears_from_alternatives(db, op):
    from app.models import JourneyOption
    cancel_x5(db, op)
    titles = [o.title for o in db.query(JourneyOption).filter_by(status="active")]
    assert titles and not any("X5" in t for t in titles)


def test_small_delay_leaves_on_time_passengers_alone(db):
    from app.models import User
    op = db.query(User).filter_by(role="operator").one()
    disruption.create(db, kind="delay", actor=op, service_id="X5", delay_min=5)
    db.commit()
    assert db.get(Service, "X5").status == "delayed"
    assert db.query(Journey).filter_by(status="affected").count() < 14


def test_long_delay_affects_those_who_would_miss_their_deadline(db, op):
    disruption.create(db, kind="delay", actor=op, service_id="X5", delay_min=120)
    db.commit()
    assert db.query(Journey).filter_by(status="affected").count() == 14


def test_vehicle_loss_flags_confirmed_bookings_rather_than_overwriting(db, op):
    _prepare(db, op)
    victims = _confirmed(db, "RV-2")
    ids = [a.id for a in victims]
    assert ids
    disruption.create(db, kind="vehicle_unavailable", actor=op, vehicle_id="RV-2")
    db.commit()
    db.expire_all()
    for aid in ids:
        a = db.get(Allocation, aid)
        assert a.status == "needs_review"          # row preserved, not rewritten
        assert a.vehicle_id == "RV-2"
        assert a.flag_reason
        assert a.seats_held is False               # those seats no longer physically exist
        assert a.journey.status == "allocated"     # nothing moved without an operator
    assert reporting.integrity(db)["over_allocated"] == 0


def test_approved_passengers_are_told_when_the_approval_is_withdrawn(db, op):
    from app.engines import allocation
    cancel_x5(db, op)
    allocation.run_allocation(db, Network.load(db), op)
    db.commit()
    a = db.query(Allocation).filter_by(vehicle_id="RV-2", status="proposed").first()
    allocation.approve(db, a, op)
    db.commit()
    disruption.create(db, kind="vehicle_unavailable", actor=op, vehicle_id="RV-2")
    db.commit()
    db.expire_all()
    assert db.get(Allocation, a.id).status == "cancelled"
    assert db.query(Notification).filter(Notification.user_id == a.journey.user_id,
                                         Notification.title.like("%was released%")).count() == 1


def test_every_flagged_passenger_is_told(db, op):
    _prepare(db, op)
    users = [a.journey.user_id for a in _confirmed(db, "RV-2")]
    disruption.create(db, kind="vehicle_unavailable", actor=op, vehicle_id="RV-2")
    db.commit()
    for uid in users:
        assert db.query(Notification).filter(Notification.user_id == uid,
                                             Notification.title.like("%needs review%")).count() == 1


def test_capacity_reduction_flags_lowest_priority_and_stays_consistent(db, op):
    _prepare(db, op)
    rows = sorted(_confirmed(db, "RV-1"), key=lambda a: a.priority_score)
    disruption.create(db, kind="capacity_reduction", actor=op, vehicle_id="RV-1", new_capacity=5)
    db.commit()
    db.expire_all()
    v = db.get(Vehicle, "RV-1")
    assert v.capacity == 5 and v.available_seats >= 0
    assert db.get(Allocation, rows[0].id).status == "needs_review"
    held = sum(a.seats for a in db.query(Allocation).filter_by(vehicle_id="RV-1", seats_held=True))
    assert held <= 5
    assert reporting.integrity(db)["over_allocated"] == 0


def test_route_closure_with_a_diversion_retimes_and_keeps_the_seat(db, op):
    _prepare(db, op)
    a = next(x for x in _confirmed(db, "RV-2") if x.journey.ref == "P-07")
    old = a.arrival_min
    disruption.create(db, kind="route_closure", actor=op, segment_id=_segment(db, "MGR", "KOR").id)
    db.commit()
    db.expire_all()
    a = db.get(Allocation, a.id)
    assert a.arrival_min > old
    assert db.query(AuditEvent).filter_by(event_type="allocation_retimed").count() >= 1
    assert db.query(Notification).filter(Notification.user_id == a.journey.user_id,
                                         Notification.title.like("%timing changed%")).count() == 1


def test_diversion_that_breaks_a_deadline_is_flagged_not_hidden(db, op):
    _prepare(db, op)
    target = next(x for x in _confirmed(db, "RV-2") if x.journey.ref == "P-07")
    disruption.create(db, kind="route_closure", actor=op, segment_id=_segment(db, "SLK", "ECY").id)
    db.commit()
    db.expire_all()
    a = db.get(Allocation, target.id)
    assert a.status == "needs_review"
    assert a.seats_held is True  # the vehicle still exists, the operator decides


def test_closure_reroutes_the_graph(db, op):
    net = Network.load(db)
    before = net.travel("MGR", "KOR")
    disruption.create(db, kind="route_closure", actor=op, segment_id=_segment(db, "MGR", "KOR").id)
    db.commit()
    assert Network.load(db).travel("MGR", "KOR") > before


def test_keep_requires_a_held_seat(client, db, op, operator):
    _prepare(db, op)
    a = _confirmed(db, "RV-2")[0]
    disruption.create(db, kind="vehicle_unavailable", actor=op, vehicle_id="RV-2")
    db.commit()
    r = client.post(f"/api/op/allocations/{a.id}/keep", json={"reason": "Fine"}, headers=operator)
    assert r.status_code == 409


def test_operator_can_keep_a_flagged_booking_with_a_reason(client, db, op, operator):
    _prepare(db, op)
    a = next(x for x in _confirmed(db, "RV-2") if x.journey.ref == "P-07")
    disruption.create(db, kind="route_closure", actor=op, segment_id=_segment(db, "SLK", "ECY").id)
    db.commit()
    r = client.post(f"/api/op/allocations/{a.id}/keep", json={"reason": "Passenger accepts late arrival"}, headers=operator)
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "confirmed" and r.json()["is_override"]


def test_reassignment_moves_seats_and_is_auditable(client, db, op, operator):
    _prepare(db, op)
    v = db.get(Vehicle, "RV-3")
    a = next(x for x in _confirmed(db, "RV-3") if x.journey.ref == "P-12")
    disruption.create(db, kind="vehicle_unavailable", actor=op, vehicle_id="RV-3")
    db.commit()
    from app.models import Vehicle as V
    db.add(V(id="RV-4", vehicle_type="Van", capacity=4, available_seats=4, stops=["HEB", "SBC", "BSK"],
             ready_min=v.ready_min + 15, wheelchair=False, luggage=True))
    db.commit()
    r = client.post(f"/api/op/allocations/{a.id}/reassign", json={"vehicle_id": "RV-4", "reason": "Spare van sent"}, headers=operator)
    assert r.status_code == 200, r.text
    db.expire_all()
    assert db.get(Allocation, a.id).status == "cancelled"
    assert db.get(V, "RV-4").available_seats == 3
    assert reporting.integrity(db)["over_allocated"] == 0
    assert db.query(AuditEvent).filter_by(event_type="operator_override").count() >= 1


def test_refused_reassignment_keeps_the_original_seat(client, db, op, operator):
    _prepare(db, op)
    a = next(x for x in _confirmed(db, "RV-2") if x.journey.ref == "P-07")
    r = client.post(f"/api/op/allocations/{a.id}/reassign", json={"vehicle_id": "RV-3", "reason": "Try it"}, headers=operator)
    assert r.status_code == 409
    db.expire_all()
    assert db.get(Allocation, a.id).status == "confirmed"
    assert reporting.integrity(db)["over_allocated"] == 0


def test_released_passengers_rejoin_carpool_demand(client, db, op, operator):
    from app.engines import carpool
    _prepare(db, op)
    a = _confirmed(db, "RV-2")[0]
    disruption.create(db, kind="vehicle_unavailable", actor=op, vehicle_id="RV-2")
    db.commit()
    r = client.post(f"/api/op/allocations/{a.id}/reject", json={"reason": "No replacement available"}, headers=operator)
    assert r.status_code == 200, r.text
    db.expire_all()
    assert a.journey_id in {j.id for j in carpool.unresolved(db)}


def test_rerunning_the_engine_never_touches_confirmed_seats(client, db, op, operator):
    _prepare(db, op)
    before = {a.id: a.vehicle_id for a in db.query(Allocation).filter_by(status="confirmed")}
    seats = {v.id: v.available_seats for v in db.query(Vehicle)}
    assert client.post("/api/op/allocation/run", headers=operator).status_code == 200
    db.expire_all()
    assert {a.id: a.vehicle_id for a in db.query(Allocation).filter_by(status="confirmed")} == before
    assert {v.id: v.available_seats for v in db.query(Vehicle)} == seats


def test_resolving_restores_the_network_without_undoing_recoveries(db, op):
    d = cancel_x5(db, op)
    simulate_prefs(db)
    allocate_and_confirm(db, op)
    confirmed = db.query(Allocation).filter_by(status="confirmed").count()
    disruption.resolve(db, d, op)
    db.commit()
    db.expire_all()
    assert db.get(Service, "X5").status == "running"
    assert db.query(Allocation).filter_by(status="confirmed").count() == confirmed


def test_duplicate_disruption_is_refused(client, db, op, operator):
    body = {"kind": "cancellation", "service_id": "X5"}
    assert client.post("/api/op/disruptions", json=body, headers=operator).status_code == 201
    assert client.post("/api/op/disruptions", json=body, headers=operator).status_code == 409
