"""Passenger grouping: complete-linkage agglomerative clustering on pairwise compatibility.

Two parties are compatible only if they actually travel the same way at the same time.
Route overlap uses *directed* road edges, so a party heading to the station from the north
is never merged with one heading to the same station from the east, and two parties on the
same road in opposite directions share nothing.

Complete linkage means every pair inside a group is compatible, not merely a chain of
neighbours.
"""
from collections import Counter
from dataclasses import dataclass

from sqlalchemy.orm import Session

from ..models import Journey, PassengerGroup, Vehicle
from ..services import audit, fmt
from .network import Network

SCORE_WEIGHTS = {"route": 0.35, "time": 0.25, "pickup": 0.20, "destination": 0.10, "requirements": 0.10}
DEST_RADIUS_M = 4000
MIN_ROUTE_OVERLAP = 0.4
STEP_FREE = {"wheelchair", "step_free"}


@dataclass
class PairResult:
    ok: bool
    score: float
    parts: dict
    reason: str = ""


def _directed_edges(net: Network, a: str, b: str) -> set[tuple]:
    p = net.path(a, b)
    return set(zip(p, p[1:]))


def pair_compat(a: Journey, b: Journey, net: Network) -> PairResult:
    ea = _directed_edges(net, a.origin_stop, a.dest_stop)
    eb = _directed_edges(net, b.origin_stop, b.dest_stop)
    if not ea or not eb:
        return PairResult(False, 0, {}, "No open route for one of the journeys")
    route = len(ea & eb) / min(len(ea), len(eb))
    if route < MIN_ROUTE_OVERLAP:
        return PairResult(False, 0, {"route": route}, f"Routes overlap only {route:.0%}")

    path_a = net.path(a.origin_stop, a.dest_stop)
    path_b = net.path(b.origin_stop, b.dest_stop)

    # Pickup: within walking tolerance of each other, or one boards along the other's route.
    gap = net.dist_m(a.origin_stop, b.origin_stop)
    walkable = gap <= min(a.max_walk_m, b.max_walk_m) or a.origin_stop == b.origin_stop
    a_first = b.origin_stop in path_a
    b_first = a.origin_stop in path_b
    if not (walkable or a_first or b_first):
        return PairResult(False, 0, {"route": route}, "Pickups are neither walkable nor en route")
    pickup = 1.0 if a.origin_stop == b.origin_stop else 0.85 if walkable else 0.65

    # Destination: nearby, or one alights along the other's route.
    dest_gap = net.dist_m(a.dest_stop, b.dest_stop)
    downstream = a.dest_stop in path_b or b.dest_stop in path_a
    if dest_gap > DEST_RADIUS_M and not downstream:
        return PairResult(False, 0, {"route": route}, f"Destinations are {dest_gap / 1000:.1f} km apart")
    destination = 1.0 if a.dest_stop == b.dest_stop else 0.8 if downstream else 0.6

    # Time: shift the earlier-boarding party's window by the ride to the later pickup.
    shift_a = (net.travel(a.origin_stop, b.origin_stop) or 0) if a_first else 0
    shift_b = (net.travel(b.origin_stop, a.origin_stop) or 0) if b_first and not a_first else 0
    a_lo, a_hi = a.dep_earliest + shift_a, a.dep_latest + shift_a
    b_lo, b_hi = b.dep_earliest + shift_b, b.dep_latest + shift_b
    overlap = min(a_hi, b_hi) - max(a_lo, b_lo)
    if overlap < 0:
        return PairResult(False, 0, {"route": route},
                          f"Departure windows miss each other by {-overlap} min")
    shorter = max(1, min(a_hi - a_lo, b_hi - b_lo))
    time = min(1.0, 0.5 + 0.5 * overlap / shorter)

    requirements = 1.0 if (set(a.requirements) & STEP_FREE) == (set(b.requirements) & STEP_FREE) else 0.5

    parts = {"route": route, "time": time, "pickup": pickup,
             "destination": destination, "requirements": requirements}
    return PairResult(True, sum(SCORE_WEIGHTS[k] * v for k, v in parts.items()), parts)


def cluster(journeys: list[Journey], net: Network, max_size: int,
            max_step_free: int) -> list[tuple[list[Journey], dict]]:
    """Returns clusters with their mean component scores. Deterministic: ties break by order."""
    journeys = sorted(journeys, key=lambda j: j.ref)
    pair = {}
    for i, a in enumerate(journeys):
        for b in journeys[i + 1:]:
            pair[(a.id, b.id)] = pair[(b.id, a.id)] = pair_compat(a, b, net)

    clusters = [[j] for j in journeys]
    while True:
        best = None
        for i, ca in enumerate(clusters):
            for k in range(i + 1, len(clusters)):
                cb = clusters[k]
                merged = ca + cb
                size = sum(j.party_size for j in merged)
                step_free = any(set(j.requirements) & STEP_FREE for j in merged)
                if size > (max_step_free if step_free else max_size):
                    continue
                results = [pair[(a.id, b.id)] for a in ca for b in cb]
                if not all(r.ok for r in results):
                    continue
                mean = sum(r.score for r in results) / len(results)
                if best is None or mean > best[0] + 1e-9:
                    best = (mean, i, k)
        if best is None:
            break
        _, i, k = best
        clusters[i] = clusters[i] + clusters[k]
        del clusters[k]

    out = []
    for members in clusters:
        results = [pair[(a.id, b.id)] for n, a in enumerate(members) for b in members[n + 1:]]
        mean_parts = {k: round(sum(r.parts[k] for r in results) / len(results), 3)
                      for k in SCORE_WEIGHTS} if results else {}
        out.append((members, mean_parts))
    return sorted(out, key=lambda c: c[0][0].ref)


def run_grouping(db: Session, net: Network, actor=None, reason: str = "Operator refresh") -> list[PassengerGroup]:
    """Regroup every party still waiting for transport. Confirmed parties keep their history."""
    for g in db.query(PassengerGroup).filter_by(status="active"):
        g.status = "superseded"
    journeys = db.query(Journey).filter_by(status="affected").all()
    vehicles = db.query(Vehicle).filter_by(status="available").all()
    max_size = max((v.capacity for v in vehicles), default=8)
    max_step_free = max((v.capacity for v in vehicles if v.wheelchair), default=0)

    total = db.query(PassengerGroup).count()
    groups = []
    for n, (members, parts) in enumerate(cluster(journeys, net, max_size, max_step_free), 1):
        seats = Counter()
        dests = Counter()
        for j in members:
            seats[j.origin_stop] += j.party_size
            dests[j.dest_stop] += j.party_size
        pickup = sorted(seats.items(), key=lambda kv: (-kv[1], kv[0]))[0][0]
        dest = sorted(dests.items(), key=lambda kv: (-kv[1], kv[0]))[0][0]
        score = sum(SCORE_WEIGHTS[k] * v for k, v in parts.items()) if parts else 1.0
        size = sum(j.party_size for j in members)
        lo = min(j.dep_earliest for j in members)
        hi = max(j.dep_latest for j in members)
        if len(members) == 1:
            text = (f"Single party of {size}. No other waiting party shares enough of its route "
                    f"and departure window to travel with it.")
        else:
            text = (f"{len(members)} parties ({size} passengers) share {parts['route']:.0%} of their "
                    f"route towards {net.stops[dest].zone}, with departures fitting "
                    f"{fmt(lo)}–{fmt(hi)}. Pickups are at or along the route from "
                    f"{net.stops[pickup].name}.")
        g = PassengerGroup(label=f"G-{total + n:02d}", destination_zone=net.stops[dest].zone,
                           pickup_stop=pickup, combined_size=size, score=round(score, 3),
                           est_minutes=net.travel(pickup, dest) or 0, explanation=text,
                           breakdown=parts)
        db.add(g)
        db.flush()
        for j in members:
            j.group_id = g.id
        groups.append(g)
    audit(db, "grouping_run", "groups",
          f"{len(groups)} groups formed from {len(journeys)} waiting parties", reason, actor)
    return groups
