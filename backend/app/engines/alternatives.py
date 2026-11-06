"""Route engine: generates each party's alternatives from their own constraints.

Option keys are stable across regeneration, so a disruption updates options in place and
any preference pointing at one that stops working is invalidated visibly, never silently.

Only replacement-vehicle options are reservable. Scheduled services are walk-up: the system
can recommend them but cannot hold a seat on them, and says so.
"""
from collections import defaultdict

from sqlalchemy.orm import Session

from ..models import Journey, JourneyOption, Preference, Service, Vehicle
from ..services import audit, notify
from .feasibility import STEP_FREE_NEEDS, assess_vehicle
from .network import WALK_M_PER_MIN, Network, Trip

MIN_CONNECTION = 5
MAX_WALKUP = 3


def _leg(mode: str, name: str, net: Network, a: str, ta: int, b: str, tb: int) -> dict:
    return {"mode": mode, "name": name, "from": net.stops[a].name, "from_stop": a, "depart": ta,
            "to": net.stops[b].name, "to_stop": b, "arrive": tb}


def _replacement_options(j: Journey, vehicles: list[Vehicle], net: Network, now: int) -> list[dict]:
    out = []
    for v in vehicles:
        res = assess_vehicle(j, v, net, now)  # seats excluded: full vehicles still show, marked full
        if not res.ok:
            continue
        moved = res.pickup_stop != j.origin_stop
        name = net.stops[res.pickup_stop].name
        out.append({
            "key": f"veh:{v.id}:{res.pickup_stop}",
            "kind": "different_pickup" if moved else "replacement",
            "title": f"Replacement {v.vehicle_type.lower()} {v.id}" + (f" from {name}" if moved else ""),
            "vehicle_id": v.id, "pickup_stop": res.pickup_stop, "departure": res.pickup_min,
            "arrival": res.arrival_min, "transfers": 0, "walk_m": res.walk_m,
            "wait_min": max(0, res.pickup_min - max(now, j.dep_earliest)), "reservable": True,
            "meets_deadline": True,
            "legs": [_leg("replacement", v.id, net, res.pickup_stop, res.pickup_min,
                          j.dest_stop, res.arrival_min)],
        })
    return out


def _walkup_options(j: Journey, trips: list[Trip], net: Network, now: int) -> list[dict]:
    step_free = bool(set(j.requirements or []) & STEP_FREE_NEEDS)
    usable = [t for t in trips if t.accessible or not step_free]
    boarding = defaultdict(list)
    for t in usable:
        for i, (s, m) in enumerate(t.calls):
            boarding[s].append((t, i, m))

    direct, via = [], {}
    for p_stop, walk in net.nearby(j.origin_stop, j.max_walk_m):
        earliest = max(now + walk / WALK_M_PER_MIN, j.dep_earliest)
        for t, i, dep in boarding[p_stop]:
            if dep < earliest:
                continue
            rest = t.calls[i + 1:]
            hit = next((m for s, m in rest if s == j.dest_stop), None)
            if hit is not None:
                direct.append((hit, dep, t, p_stop, walk))
                continue
            for hub, arr in rest:
                for t2, k, dep2 in boarding[hub]:
                    if t2.service_id == t.service_id or dep2 < arr + MIN_CONNECTION:
                        continue
                    hit2 = next((m for s, m in t2.calls[k + 1:] if s == j.dest_stop), None)
                    if hit2 is None:
                        continue
                    cand = (hit2, dep, t, p_stop, walk, hub, arr, t2, dep2)
                    if hub not in via or cand[:2] < via[hub][:2]:
                        via[hub] = cand

    out = []
    seen = set()
    for arr, dep, t, p_stop, walk in sorted(direct, key=lambda d: (d[0], d[1], d[2].service_id)):
        key = f"svc:{t.service_id}:{p_stop}:{dep}"
        if key in seen or len(seen) >= 2:
            continue
        seen.add(key)
        out.append({
            "key": key, "kind": "later_departure",
            "title": f"{t.name} from {net.stops[p_stop].name}", "vehicle_id": None,
            "pickup_stop": p_stop, "departure": dep, "arrival": arr, "transfers": 0, "walk_m": walk,
            "wait_min": max(0, dep - max(now, j.dep_earliest)), "reservable": False,
            "meets_deadline": arr <= j.latest_arrival,
            "legs": [_leg("bus", t.service_id, net, p_stop, dep, j.dest_stop, arr)],
        })
    for arr2, dep, t, p_stop, walk, hub, arr, t2, dep2 in sorted(
            via.values(), key=lambda c: (c[0], c[1], c[5]))[:2]:
        out.append({
            "key": f"via:{t.service_id}:{hub}:{t2.service_id}:{dep}",
            "kind": "transfer", "title": f"{t.service_id} then {t2.service_id} via {net.stops[hub].name}",
            "vehicle_id": None, "pickup_stop": p_stop, "departure": dep, "arrival": arr2, "transfers": 1,
            "walk_m": walk, "wait_min": max(0, dep - max(now, j.dep_earliest)) + dep2 - arr,
            "reservable": False, "meets_deadline": arr2 <= j.latest_arrival,
            "legs": [_leg("bus", t.service_id, net, p_stop, dep, hub, arr),
                     _leg("bus", t2.service_id, net, hub, dep2, j.dest_stop, arr2)],
        })
    return out


def generate(j: Journey, vehicles: list[Vehicle], trips: list[Trip], net: Network, now: int) -> list[dict]:
    replacement = _replacement_options(j, vehicles, net, now)
    walkup = sorted(_walkup_options(j, trips, net, now),
                    key=lambda o: (not o["meets_deadline"], o["arrival"], o["key"]))
    feasible = [o for o in walkup if o["meets_deadline"]]
    # Late options are shown (flagged) only when too little else exists.
    chosen = feasible[:MAX_WALKUP]
    if len(replacement) + len(chosen) < 2:
        chosen += [o for o in walkup if not o["meets_deadline"]][:2 - len(replacement) - len(chosen)]
    return sorted(replacement, key=lambda o: o["arrival"]) + chosen


def refresh_options(db: Session, j: Journey, vehicles: list[Vehicle], trips: list[Trip],
                    net: Network, now: int) -> None:
    drafts = {d["key"]: d for d in generate(j, vehicles, trips, net, now)}
    existing = {o.key: o for o in db.query(JourneyOption).filter_by(journey_id=j.id)}
    for key, d in drafts.items():
        row = existing.get(key)
        if row is None:
            db.add(JourneyOption(journey_id=j.id, **d))
        else:
            for k, val in d.items():
                setattr(row, k, val)
            row.status = "active"
    lost = [o for k, o in existing.items() if k not in drafts and o.status == "active"]
    for o in lost:
        o.status = "unavailable"
    db.flush()

    lost_ids = {o.id for o in lost}
    if lost_ids:
        for p in db.query(Preference).filter(Preference.journey_id == j.id,
                                             Preference.option_id.in_(lost_ids),
                                             Preference.status == "submitted"):
            p.status = "invalidated"
            notify(db, j.user_id, "One of your chosen options is no longer available",
                   f"Choice {p.rank} ({p.option.title}) stopped being feasible after a network "
                   f"change. Please review your alternatives.", "warning")
            audit(db, "preference_invalidated", j.ref,
                  f"Choice {p.rank} ({p.option.title}) no longer feasible", "Network change")


def refresh_all(db: Session, net: Network, now: int) -> None:
    vehicles = db.query(Vehicle).filter_by(status="available").order_by(Vehicle.id).all()
    trips = net.trips(db.query(Service).order_by(Service.id).all(), now)
    for j in db.query(Journey).filter_by(status="affected").order_by(Journey.id):
        refresh_options(db, j, vehicles, trips, net, now)
