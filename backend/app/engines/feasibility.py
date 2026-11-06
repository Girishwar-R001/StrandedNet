"""Feasibility is separate from prioritisation (spec 9.1).

A vehicle either passes every hard check for a party or it is not a candidate. No priority
score, passenger preference or operator weight can make an infeasible assignment feasible.
"""
from dataclasses import dataclass, field

from ..models import Journey, Vehicle
from .network import WALK_M_PER_MIN, Network

STEP_FREE_NEEDS = {"wheelchair", "step_free"}
# Checks an operator override may NOT bypass. Timing checks are the only overridable ones.
HARD_CHECKS = {"vehicle_available", "seats", "accessibility", "route_open", "pickup", "destination"}


@dataclass
class Assessment:
    ok: bool
    checks: list = field(default_factory=list)
    pickup_stop: str | None = None
    pickup_min: int | None = None
    arrival_min: int | None = None
    walk_m: int = 0

    @property
    def failures(self) -> list[str]:
        return [c["detail"] for c in self.checks if not c["ok"]]

    def passes_hard(self) -> bool:
        return all(c["ok"] for c in self.checks if c["name"] in HARD_CHECKS)

    def failed(self, *names: str) -> bool:
        return any(c["name"] in names and not c["ok"] for c in self.checks)


def _check(name: str, ok: bool, detail: str) -> dict:
    return {"name": name, "ok": ok, "detail": detail}


def _fmt(m: int) -> str:
    return f"{m // 60:02d}:{m % 60:02d}"


def assess_vehicle(j: Journey, v: Vehicle, net: Network, now: int,
                   seats_left: int | None = None) -> Assessment:
    """Evaluate one party against one vehicle. `seats_left=None` skips the seat check, which
    is how alternatives and reassessment ask 'would this work if a seat were free?'."""
    checks = [_check("vehicle_available", v.status == "available",
                     f"{v.id} is {'in service' if v.status == 'available' else 'unavailable'}")]
    if seats_left is not None:
        checks.append(_check("seats", seats_left >= j.party_size,
                             f"{seats_left} seats left for a party of {j.party_size}"))

    reqs = set(j.requirements or [])
    missing = []
    if reqs & STEP_FREE_NEEDS and not v.wheelchair:
        missing.append("step-free access")
    if "luggage" in reqs and not v.luggage:
        missing.append("luggage space")
    checks.append(_check("accessibility", not missing,
                         f"{v.id} lacks {', '.join(missing)}" if missing
                         else "Vehicle meets declared requirements"))

    calls = net.vehicle_calls(v)
    checks.append(_check("route_open", calls is not None,
                         "Run is reachable on open roads" if calls
                         else f"{v.id} run is cut by a closure with no diversion"))
    if calls is None:
        return Assessment(False, checks)

    times = {s: (i, t) for i, (s, t) in enumerate(calls)}
    pickups = [(s, w) for s, w in net.nearby(j.origin_stop, j.max_walk_m) if s in times]
    drops = [(s, w) for s, w in net.nearby(j.dest_stop, j.max_walk_m) if s in times]
    checks.append(_check("pickup", bool(pickups),
                         f"Calls at {net.stops[pickups[0][0]].name}" if pickups
                         else f"Does not call within {j.max_walk_m} m of {net.stops[j.origin_stop].name}"))

    # Choose the pickup/drop pair that passes the most checks, preferring the least walking.
    best = None
    for p_stop, p_walk in pickups:
        p_idx, p_time = times[p_stop]
        for d_stop, d_walk in drops:
            d_idx, d_time = times[d_stop]
            if d_idx <= p_idx:
                continue
            reachable = p_time >= now + p_walk / WALK_M_PER_MIN
            in_window = j.dep_earliest <= p_time <= max(j.dep_latest, j.dep_earliest + j.max_wait)
            arrival = d_time + round(d_walk / WALK_M_PER_MIN)
            on_time = arrival <= j.latest_arrival
            rank = (reachable and in_window, on_time, -(p_walk + d_walk))
            if best is None or rank > best[0]:
                best = (rank, p_stop, p_time, p_walk + d_walk, arrival, reachable and in_window, on_time)

    checks.append(_check("destination", best is not None,
                         f"Reaches {net.stops[j.dest_stop].name} after pickup" if best
                         else f"Does not serve {net.stops[j.dest_stop].name} after the pickup"))
    if best is None:
        return Assessment(False, checks)

    _, p_stop, p_time, walk, arrival, timing_ok, on_time = best
    checks.append(_check("departure_window", timing_ok,
                         f"Pickup {_fmt(p_time)} vs window {_fmt(j.dep_earliest)}–{_fmt(j.dep_latest)}"))
    checks.append(_check("arrival_deadline", on_time,
                         f"Arrives {_fmt(arrival)} vs latest {_fmt(j.latest_arrival)}"))
    return Assessment(all(c["ok"] for c in checks), checks, p_stop, p_time, arrival, walk)
