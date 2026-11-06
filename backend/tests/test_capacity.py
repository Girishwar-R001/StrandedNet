"""Capacity enforcement: the over-allocation count must always be zero."""
import threading

import pytest
from sqlalchemy.exc import IntegrityError

from app.database import SessionLocal
from app.engines import allocation, reporting
from app.engines.allocation import ReservationError, _take_seats
from app.engines.network import Network
from app.models import Allocation, Vehicle

from .conftest import allocate_and_confirm, cancel_x5, journey, simulate_prefs


def _proposal(db, ref, vehicle_id, seats=None):
    j = journey(db, ref)
    a = Allocation(journey_id=j.id, vehicle_id=vehicle_id, seats=seats or j.party_size,
                   pickup_stop=j.origin_stop, pickup_min=1100, arrival_min=1150)
    db.add(a)
    db.commit()
    return a


def test_spec_example_three_plus_four_leaves_one_and_refuses_two(db):
    """Spec 5.3: 8 seats, groups of 3 and 4 assigned, a group of 2 cannot be."""
    assert _take_seats(db, "RV-1", 3)
    assert _take_seats(db, "RV-1", 4)
    db.commit()
    db.expire_all()
    assert db.get(Vehicle, "RV-1").available_seats == 1
    assert not _take_seats(db, "RV-1", 2)
    db.commit()
    db.expire_all()
    assert db.get(Vehicle, "RV-1").available_seats == 1


def test_database_rejects_negative_seats_even_if_code_is_bypassed(db):
    v = db.get(Vehicle, "RV-3")
    v.available_seats = -1
    with pytest.raises(IntegrityError):
        db.commit()
    db.rollback()


def test_database_rejects_seats_above_capacity(db):
    v = db.get(Vehicle, "RV-3")
    v.available_seats = v.capacity + 1
    with pytest.raises(IntegrityError):
        db.commit()
    db.rollback()


def test_a_journey_cannot_hold_two_active_allocations(db):
    _proposal(db, "P-02", "RV-1")
    with pytest.raises(IntegrityError):
        _proposal(db, "P-02", "RV-2")
    db.rollback()


def test_simultaneous_reservations_cannot_oversell(db):
    """20 threads race for a 5-seat vehicle, each wanting 1 seat: exactly 5 may win."""
    wins, barrier = [], threading.Barrier(20)

    def race():
        s = SessionLocal()
        barrier.wait()
        try:
            if _take_seats(s, "RV-3", 1):
                s.commit()
                wins.append(1)
            else:
                s.rollback()
        finally:
            s.close()

    threads = [threading.Thread(target=race) for _ in range(20)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    db.expire_all()
    assert len(wins) == 5
    assert db.get(Vehicle, "RV-3").available_seats == 0


def test_concurrent_confirmation_of_one_allocation_reserves_once(db, op):
    cancel_x5(db, op)
    simulate_prefs(db)
    allocation.run_allocation(db, Network.load(db), op)
    db.commit()
    target_id = db.query(Allocation).filter_by(status="proposed", vehicle_id="RV-2").first().id
    seats = db.get(Allocation, target_id).seats
    outcomes, barrier = [], threading.Barrier(6)

    def confirm():
        s = SessionLocal()
        barrier.wait()
        try:
            allocation.reserve(s, s.get(Allocation, target_id), Network.load(s), None)
            s.commit()
            outcomes.append("ok")
        except ReservationError:
            s.rollback()
            outcomes.append("refused")
        finally:
            s.close()

    threads = [threading.Thread(target=confirm) for _ in range(6)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    db.expire_all()
    assert outcomes.count("ok") == 1
    assert db.get(Vehicle, "RV-2").available_seats == 7 - seats


def test_reservation_rechecks_capacity_at_confirmation(db, op):
    cancel_x5(db, op)
    allocation.run_allocation(db, Network.load(db), op)
    db.commit()
    a = db.query(Allocation).filter_by(status="proposed", vehicle_id="RV-1").first()
    # Another process takes every seat between proposal and confirmation.
    other = SessionLocal()
    assert _take_seats(other, "RV-1", 8)
    other.commit()
    other.close()
    with pytest.raises(ReservationError):
        allocation.reserve(db, a, Network.load(db), op)
    db.rollback()
    db.expire_all()
    assert db.get(Allocation, a.id).status == "proposed"
    assert db.get(Vehicle, "RV-1").available_seats == 0


def test_proposals_hold_no_seats(db, op):
    cancel_x5(db, op)
    allocation.run_allocation(db, Network.load(db), op)
    db.commit()
    db.expire_all()
    assert {v.id: v.available_seats for v in db.query(Vehicle)} == {"RV-1": 8, "RV-2": 7, "RV-3": 5}


def test_engine_fills_the_fleet_exactly_and_never_exceeds_a_vehicle(db, op):
    cancel_x5(db, op)
    simulate_prefs(db)
    run, result = allocate_and_confirm(db, op)
    db.expire_all()
    assert result["failed"] == []
    assert reporting.integrity(db)["over_allocated"] == 0
    assert all(v.available_seats >= 0 for v in db.query(Vehicle))
    assert run.summary["engine"]["seats"] == 20


def test_parties_are_never_split_across_vehicles(db, op):
    cancel_x5(db, op)
    allocate_and_confirm(db, op)
    for a in db.query(Allocation).filter_by(status="confirmed"):
        assert a.seats == a.journey.party_size
    per_journey = [a.journey_id for a in db.query(Allocation).filter_by(status="confirmed")]
    assert len(per_journey) == len(set(per_journey))


def test_release_returns_seats_exactly_once(db, op):
    cancel_x5(db, op)
    allocate_and_confirm(db, op)
    a = db.query(Allocation).filter_by(status="confirmed", vehicle_id="RV-2").first()
    before = db.get(Vehicle, "RV-2").available_seats
    allocation.release(db, a, "Passenger no longer travelling", op)
    db.commit()
    db.expire_all()
    assert db.get(Vehicle, "RV-2").available_seats == before + a.seats
    with pytest.raises(ReservationError):
        allocation.release(db, a, "Again", op)
    db.expire_all()
    assert db.get(Vehicle, "RV-2").available_seats == before + a.seats
    assert reporting.integrity(db)["over_allocated"] == 0


def test_greedy_fallback_is_also_capacity_safe(db, op):
    cancel_x5(db, op)
    run = allocation.run_allocation(db, Network.load(db), op, solver="greedy")
    db.commit()
    assert run.solver == "greedy"
    for v in db.query(Vehicle):
        seats = sum(a.seats for a in db.query(Allocation).filter_by(vehicle_id=v.id, status="proposed"))
        assert seats <= v.capacity


def test_cp_sat_is_reproducible(db, op):
    cancel_x5(db, op)
    simulate_prefs(db)
    plans = []
    for _ in range(3):
        allocation.run_allocation(db, Network.load(db), op, solver="cp_sat")
        db.commit()
        plans.append(sorted((a.journey_id, a.vehicle_id) for a in db.query(Allocation).filter_by(status="proposed")))
    assert plans[0] == plans[1] == plans[2]
