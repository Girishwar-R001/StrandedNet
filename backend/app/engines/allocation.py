"""Official allocation: feasibility filter -> priority score -> optimiser -> atomic reservation.

The solver only produces *proposals*. A seat exists only after `reserve()` has run a
conditional UPDATE in the database. Available seats are never read, adjusted in Python and
written back, which is what makes simultaneous confirmations safe.

Solvers
  cp_sat  OR-Tools CP-SAT over a multiple-knapsack: x[party, vehicle] binary, one vehicle per
          party, seats per vehicle bounded, maximising priority-weighted seats plus a bonus
          for keeping a whole group on one vehicle. Solves packing that greedy cannot.
  greedy  Priority-ordered best-fit. Used if OR-Tools is unavailable.

A first-come-first-served baseline is computed on every run, on identical feasibility rules,
so improvement claims are always measured rather than asserted.
"""
from sqlalchemy import update
from sqlalchemy.orm import Session

from ..config import settings
from ..models import (ACTIVE_ALLOCATION, Allocation, AllocationRun, Journey, JourneyOption,
                      PassengerGroup, Preference, Vehicle, utcnow)
from ..services import audit, fmt, notify, now_min, thresholds, weights
from . import priority
from .carpool import withdraw_from_carpool
from .feasibility import Assessment, assess_vehicle
from .network import Network

try:
    from ortools.sat.python import cp_model
except ImportError:  # pragma: no cover - exercised by forcing solver="greedy" in tests
    cp_model = None

SEAT_BASE = 0.4        # value of filling a seat at all, before priority
GROUP_BONUS = 0.05     # per seat, for a whole group sharing one vehicle


class ReservationError(Exception):
    pass


# ---------------------------------------------------------------- solvers
def _value(c: dict) -> float:
    return c["seats"] * (SEAT_BASE + c["score"])


def solve_greedy(cands: dict, parties: list[Journey], capacity: dict) -> dict:
    left = dict(capacity)
    placed = {}
    order = sorted(parties, key=lambda j: (-max((c["score"] for c in cands[j.id].values()), default=0), j.ref))
    for j in order:
        options = [(vid, c) for vid, c in cands[j.id].items() if left[vid] >= j.party_size]
        if options:
            # Highest score (which includes preference); ties go to the tightest fit.
            vid = sorted(options, key=lambda o: (-o[1]["score"], left[o[0]], o[0]))[0][0]
            placed[j.id] = vid
            left[vid] -= j.party_size
    return placed


def solve_cp_sat(cands: dict, parties: list[Journey], capacity: dict) -> dict:
    m = cp_model.CpModel()
    x = {(j.id, vid): m.new_bool_var(f"x{j.id}_{vid}") for j in parties for vid in cands[j.id]}
    for j in parties:
        m.add(sum(x[j.id, vid] for vid in cands[j.id]) <= 1)
    for vid, cap in capacity.items():
        m.add(sum(j.party_size * x[j.id, vid] for j in parties if vid in cands[j.id]) <= cap)

    objective = [round(1000 * _value(cands[j.id][vid])) * x[j.id, vid]
                 for j in parties for vid in cands[j.id]]
    groups: dict[int, list[Journey]] = {}
    for j in parties:
        if j.group_id:
            groups.setdefault(j.group_id, []).append(j)
    for gid, members in groups.items():
        if len(members) < 2:
            continue
        shared = set.intersection(*(set(cands[j.id]) for j in members))
        size = sum(j.party_size for j in members)
        for vid in sorted(shared):
            together = m.new_bool_var(f"g{gid}_{vid}")
            for j in members:
                m.add_implication(together, x[j.id, vid])
            objective.append(round(1000 * GROUP_BONUS * size) * together)
    m.maximize(sum(objective))

    solver = cp_model.CpSolver()
    solver.parameters.num_workers = 1   # single worker + fixed seed keeps runs reproducible
    solver.parameters.random_seed = 7
    solver.parameters.max_time_in_seconds = 5
    if solver.solve(m) not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        return solve_greedy(cands, parties, capacity)
    return {jid: vid for (jid, vid), var in x.items() if solver.value(var)}


def baseline_fcfs(cands: dict, parties: list[Journey], capacity: dict) -> dict:
    """What a counter queue would do: earliest reporter takes the first vehicle that fits."""
    left = dict(capacity)
    placed = {}
    for j in sorted(parties, key=lambda j: (j.reported_min, j.ref)):
        for vid in sorted(cands[j.id]):
            if left[vid] >= j.party_size:
                placed[j.id] = vid
                left[vid] -= j.party_size
                break
    return placed


def _plan_stats(placed: dict, cands: dict, parties: list[Journey], in_time_walkups: dict) -> dict:
    by_id = {j.id: j for j in parties}
    stranded = sum(j.party_size for j in parties if j.id not in placed and not in_time_walkups[j.id])
    seats = sum(by_id[jid].party_size for jid in placed)
    pref = {"first_choice": 0, "second_choice": 0}
    for jid, vid in placed.items():
        out = cands[jid][vid]["outcome"]
        if out in pref:
            pref[out] += 1
    return {"seats": seats, "parties": len(placed), "first_choice": pref["first_choice"],
            "second_choice": pref["second_choice"],
            # Passengers left with no seat AND no walk-up option that arrives in time.
            "stranded_no_alternative": stranded,
            "priority_value": round(sum(cands[j][v]["score"] * by_id[j].party_size
                                        for j, v in placed.items()), 2)}


# ---------------------------------------------------------------- engine run
def seats_committed_unreserved(db: Session, vehicle_id: str) -> int:
    rows = db.query(Allocation).filter_by(vehicle_id=vehicle_id, status="approved", seats_held=False)
    return sum(a.seats for a in rows)


def _why_unplaced(j: Journey, assessments: dict[str, Assessment], cands: dict, placed: dict,
                  left: dict) -> str:
    feasible = cands.get(j.id, {})
    if feasible:
        names = ", ".join(f"{vid} ({left[vid]} left)" for vid in sorted(feasible))
        return (f"Feasible on {names}, but a party of {j.party_size} did not fit once "
                f"higher-value parties were seated.")
    reasons = sorted({f for a in assessments.values() for f in a.failures})
    return "No vehicle is feasible: " + "; ".join(reasons[:3])


def run_allocation(db: Session, net: Network, actor=None, solver: str | None = None) -> AllocationRun:
    now = now_min(db)
    w, cfg = weights(db), thresholds(db)
    solver = solver or settings.allocation_solver
    use_cp = solver in ("auto", "cp_sat") and cp_model is not None

    # A re-run replaces unreviewed proposals; anything approved or confirmed is left alone.
    for a in db.query(Allocation).filter_by(status="proposed"):
        a.status = "cancelled"
        a.flag_reason = "Superseded by a newer engine run"
    db.flush()

    locked = {a.journey_id for a in db.query(Allocation).filter(Allocation.status.in_(ACTIVE_ALLOCATION))}
    parties = [j for j in db.query(Journey).filter_by(status="affected").order_by(Journey.ref)
               if j.id not in locked]
    vehicles = db.query(Vehicle).filter_by(status="available").order_by(Vehicle.id).all()
    capacity = {v.id: v.available_seats - seats_committed_unreserved(db, v.id) for v in vehicles}

    cands: dict[int, dict] = {}
    assessments: dict[int, dict[str, Assessment]] = {}
    in_time_walkups: dict[int, int] = {}
    for j in parties:
        options = db.query(JourneyOption).filter_by(journey_id=j.id).all()
        in_time_walkups[j.id] = sum(1 for o in options if o.status == "active"
                                    and not o.reservable and o.meets_deadline)
        prefs = db.query(Preference).filter_by(journey_id=j.id).all()
        cands[j.id], assessments[j.id] = {}, {}
        for v in vehicles:
            res = assess_vehicle(j, v, net, now, capacity[v.id])
            assessments[j.id][v.id] = res
            if res.ok:
                total, breakdown, outcome = priority.score(j, v, res.arrival_min, options, prefs, w, cfg, now)
                cands[j.id][v.id] = {"score": total, "breakdown": breakdown, "outcome": outcome,
                                     "res": res, "seats": j.party_size}

    placed = (solve_cp_sat if use_cp else solve_greedy)(cands, parties, capacity)
    base = baseline_fcfs(cands, parties, capacity)

    left = dict(capacity)
    run = AllocationRun(solver="cp_sat" if use_cp else "greedy")
    db.add(run)
    db.flush()

    by_id = {j.id: j for j in parties}
    labels = {g.id: g.label for g in db.query(PassengerGroup)}
    vmap = {v.id: v for v in vehicles}
    for jid, vid in sorted(placed.items(), key=lambda kv: -cands[kv[0]][kv[1]]["score"]):
        j, c = by_id[jid], cands[jid][vid]
        left[vid] -= j.party_size
        res = c["res"]
        db.add(Allocation(
            journey_id=jid, group_id=j.group_id, vehicle_id=vid, run_id=run.id, seats=j.party_size,
            pickup_stop=res.pickup_stop, pickup_min=res.pickup_min, arrival_min=res.arrival_min,
            priority_score=c["score"], breakdown=c["breakdown"], checks=res.checks,
            explanation=priority.describe(j, vmap[vid], c["score"], c["breakdown"], c["outcome"],
                                          labels.get(j.group_id)),
            preference_outcome=c["outcome"]))

    unplaced = []
    for j in parties:
        if j.id in placed:
            j.outcome_note = ""
            continue
        why = _why_unplaced(j, assessments[j.id], cands, placed, left)
        j.outcome_note = why
        unplaced.append({"journey_id": j.id, "ref": j.ref, "party_size": j.party_size, "reason": why})

    run.summary = {
        "engine": _plan_stats(placed, cands, parties, in_time_walkups),
        "baseline_fcfs": _plan_stats(base, cands, parties, in_time_walkups),
        "unplaced": unplaced,
        "seats_remaining": left,
        "candidates": len(parties),
        "demand_seats": sum(j.party_size for j in parties),
        "supply_seats": sum(capacity.values()),
    }
    audit(db, "allocation_run", f"run-{run.id}",
          f"{run.solver}: {len(placed)} parties / {run.summary['engine']['seats']} seats proposed, "
          f"{len(unplaced)} parties unplaced",
          f"First-come baseline would seat {run.summary['baseline_fcfs']['seats']} and leave "
          f"{run.summary['baseline_fcfs']['stranded_no_alternative']} with no in-time alternative "
          f"(engine: {run.summary['engine']['stranded_no_alternative']})", actor)
    return run


# ---------------------------------------------------------------- reservation
def _take_seats(db: Session, vehicle_id: str, seats: int) -> bool:
    """The only code path that consumes seats. Atomic check-and-decrement in one statement."""
    res = db.execute(update(Vehicle)
                     .where(Vehicle.id == vehicle_id, Vehicle.status == "available",
                            Vehicle.available_seats >= seats)
                     .values(available_seats=Vehicle.available_seats - seats)
                     .execution_options(synchronize_session=False))
    return res.rowcount == 1


def _return_seats(db: Session, vehicle_id: str, seats: int) -> None:
    db.execute(update(Vehicle)
               .where(Vehicle.id == vehicle_id, Vehicle.available_seats + seats <= Vehicle.capacity)
               .values(available_seats=Vehicle.available_seats + seats)
               .execution_options(synchronize_session=False))


def _mark_preferences(db: Session, a: Allocation) -> None:
    for p in db.query(Preference).filter_by(journey_id=a.journey_id):
        if p.status != "invalidated":
            p.status = "satisfied" if p.option.vehicle_id == a.vehicle_id else "not_satisfied"


def approve(db: Session, a: Allocation, actor) -> None:
    if a.status != "proposed":
        raise ReservationError(f"Allocation is {a.status}, not proposed")
    a.status = "approved"
    a.approved_at = utcnow()
    audit(db, "allocation_approved", a.journey.ref, f"Approved on {a.vehicle_id}, seats not yet reserved", "", actor)
    notify(db, a.journey.user_id, "Operator approved a seat for you",
           f"{a.vehicle_id} has been approved for your party. This is not final until the seat is reserved.")


def reserve(db: Session, a: Allocation, net: Network, actor) -> None:
    """Recheck, then atomically reserve. Raises ReservationError with the transaction rolled
    back to a clean state; the caller commits on success."""
    db.flush()
    db.refresh(a.journey)
    if a.journey.status != "affected":
        # e.g. their carpool was confirmed after this proposal. A party never holds two seats.
        raise ReservationError(f"{a.journey.ref} is no longer awaiting transport ({a.journey.status})")
    db.refresh(a.vehicle)
    res = assess_vehicle(a.journey, a.vehicle, net, now_min(db), a.vehicle.available_seats)
    if not res.ok and not (a.is_override and res.passes_hard()):
        raise ReservationError("; ".join(res.failures))

    # Status flip first: two concurrent confirmations of one allocation cannot both win.
    flipped = db.execute(update(Allocation)
                         .where(Allocation.id == a.id, Allocation.status.in_(("proposed", "approved")))
                         .values(status="confirmed", seats_held=True, confirmed_at=utcnow(),
                                 checks=res.checks)
                         .execution_options(synchronize_session=False))
    if flipped.rowcount != 1:
        db.rollback()
        raise ReservationError("Allocation was already processed")
    if not _take_seats(db, a.vehicle_id, a.seats):
        db.rollback()
        raise ReservationError(f"{a.vehicle_id} no longer has {a.seats} seats")
    db.refresh(a)
    db.refresh(a.vehicle)

    j = a.journey
    j.status = "allocated"
    j.outcome_note = ""
    _mark_preferences(db, a)
    withdraw_from_carpool(db, j, "Official seat confirmed")
    stop = net.stops[a.pickup_stop].name
    notify(db, j.user_id, f"Seat confirmed on {a.vehicle_id}",
           f"Be at {stop} for {fmt(a.pickup_min)}. Estimated arrival {fmt(a.arrival_min)}. "
           f"{a.seats} seat(s) reserved.", "success")
    audit(db, "seat_reserved", j.ref,
          f"{a.seats} seat(s) reserved on {a.vehicle_id}; {a.vehicle.available_seats} of "
          f"{a.vehicle.capacity} remain", a.explanation, actor)


def reserve_all(db: Session, net: Network, actor) -> dict:
    """Each reservation commits independently, so one failure cannot undo the others."""
    ids = [a.id for a in db.query(Allocation).filter(Allocation.status.in_(("proposed", "approved")))
           .order_by(Allocation.priority_score.desc(), Allocation.id)]
    confirmed, failed = [], []
    for aid in ids:
        a = db.get(Allocation, aid)
        try:
            if a.status == "proposed":
                a.status = "approved"
                a.approved_at = utcnow()
                audit(db, "allocation_approved", a.journey.ref, f"Bulk approved on {a.vehicle_id}", "", actor)
            reserve(db, a, net, actor)
            db.commit()
            confirmed.append(aid)
        except ReservationError as e:
            db.rollback()
            a = db.get(Allocation, aid)
            a.status = "cancelled"
            a.flag_reason = f"Reservation failed: {e}"
            audit(db, "reservation_failed", a.journey.ref, f"Could not reserve {a.vehicle_id}", str(e), actor)
            db.commit()
            failed.append({"allocation_id": aid, "reason": str(e)})
    return {"confirmed": len(confirmed), "failed": failed}


def release(db: Session, a: Allocation, reason: str, actor, status: str = "cancelled") -> None:
    """Cancel an allocation, returning any held seats. Visible to the passenger and audited."""
    if a.status not in ACTIVE_ALLOCATION:
        raise ReservationError(f"Allocation is already {a.status}")
    was_promised = a.status in ("approved", "confirmed", "needs_review")
    if a.seats_held:
        _return_seats(db, a.vehicle_id, a.seats)
    a.seats_held = False
    a.status = status
    a.flag_reason = reason
    j = a.journey
    if j.status == "allocated":
        j.status = "affected"
    db.flush()
    db.refresh(a.vehicle)
    if was_promised:
        notify(db, j.user_id, f"Your seat on {a.vehicle_id} was released", reason, "warning")
    audit(db, "allocation_released", j.ref,
          f"{a.seats} seat(s) on {a.vehicle_id} released; {a.vehicle.available_seats} now free", reason, actor)


def create_confirmed(db: Session, j: Journey, v: Vehicle, net: Network, reason: str, actor) -> Allocation:
    """Operator override. May bypass timing and ranking, never seats, accessibility or routing."""
    if j.status != "affected":
        raise ReservationError(f"{j.ref} is not awaiting transport ({j.status})")
    db.refresh(v)
    res = assess_vehicle(j, v, net, now_min(db), v.available_seats)
    if not res.passes_hard():
        raise ReservationError("Override refused: " + "; ".join(
            c["detail"] for c in res.checks if not c["ok"]))
    prefs = db.query(Preference).filter_by(journey_id=j.id).all()
    _, outcome = priority.preference_match(prefs, v.id, thresholds(db))
    a = Allocation(journey_id=j.id, group_id=j.group_id, vehicle_id=v.id, seats=j.party_size,
                   pickup_stop=res.pickup_stop, pickup_min=res.pickup_min, arrival_min=res.arrival_min,
                   checks=res.checks, is_override=True, override_reason=reason, status="approved",
                   preference_outcome=outcome, approved_at=utcnow(),
                   explanation=f"Operator override of {j.ref} onto {v.id}: {reason}")
    db.add(a)
    db.flush()
    audit(db, "operator_override", j.ref, f"Manually assigned to {v.id}", reason, actor)
    reserve(db, a, net, actor)
    return a
