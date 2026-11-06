"""Simulated transport network: road graph, timetabled trips and replacement-vehicle schedules.

Deterministic by construction. Closed segments are removed from the graph, so every travel
time, trip and vehicle schedule automatically re-routes around them or reports unreachable.
"""
import heapq
import math
from dataclasses import dataclass

from sqlalchemy.orm import Session

from ..models import Segment, Service, Stop, Vehicle

WALK_M_PER_MIN = 80


def haversine_m(lat1, lng1, lat2, lng2) -> float:
    r = 6371000
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = p2 - p1, math.radians(lng2 - lng1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


@dataclass(frozen=True)
class Trip:
    service_id: str
    name: str
    calls: tuple  # ((stop_id, minute), ...)
    accessible: bool


class Network:
    def __init__(self, stops: list[Stop], segments: list[Segment]):
        self.stops = {s.id: s for s in stops}
        self.adj: dict[str, list[tuple[str, int]]] = {s.id: [] for s in stops}
        for seg in segments:
            if not seg.blocked:
                self.adj[seg.a].append((seg.b, seg.minutes))
                self.adj[seg.b].append((seg.a, seg.minutes))
        for edges in self.adj.values():
            edges.sort()
        self._sp: dict[str, tuple[dict, dict]] = {}

    @classmethod
    def load(cls, db: Session) -> "Network":
        return cls(db.query(Stop).order_by(Stop.id).all(), db.query(Segment).order_by(Segment.id).all())

    def _dijkstra(self, src: str):
        if src not in self._sp:
            dist, prev, heap = {src: 0}, {}, [(0, src)]
            while heap:
                d, u = heapq.heappop(heap)
                if d > dist.get(u, math.inf):
                    continue
                for v, w in self.adj[u]:
                    if d + w < dist.get(v, math.inf):
                        dist[v], prev[v] = d + w, u
                        heapq.heappush(heap, (d + w, v))
            self._sp[src] = (dist, prev)
        return self._sp[src]

    def travel(self, a: str, b: str) -> int | None:
        """Minutes from a to b on open roads, or None when closures disconnect them."""
        return self._dijkstra(a)[0].get(b)

    def path(self, a: str, b: str) -> list[str]:
        dist, prev = self._dijkstra(a)
        if b not in dist:
            return []
        out = [b]
        while out[-1] != a:
            out.append(prev[out[-1]])
        return out[::-1]

    def path_edges(self, a: str, b: str) -> set[frozenset]:
        p = self.path(a, b)
        return {frozenset(e) for e in zip(p, p[1:])}

    def dist_m(self, a: str, b: str) -> float:
        s, t = self.stops[a], self.stops[b]
        return haversine_m(s.lat, s.lng, t.lat, t.lng)

    def nearby(self, stop: str, radius_m: int) -> list[tuple[str, int]]:
        """Stops within walking radius of `stop`, nearest first, always including itself."""
        found = [(stop, 0)]
        for sid in self.stops:
            if sid != stop:
                d = round(self.dist_m(stop, sid))
                if d <= radius_m:
                    found.append((sid, d))
        return sorted(found, key=lambda x: (x[1], x[0]))

    def run_calls(self, stops: list[str], start: int, delay: int = 0) -> list[tuple[str, int]] | None:
        """Timed calls along a stop sequence; None if any consecutive pair is unreachable."""
        calls, t = [(stops[0], start + delay)], start + delay
        for a, b in zip(stops, stops[1:]):
            leg = self.travel(a, b)
            if leg is None:
                return None
            t += leg
            calls.append((b, t))
        return calls

    def vehicle_calls(self, v: Vehicle) -> list[tuple[str, int]] | None:
        return self.run_calls(v.stops, v.ready_min)

    def trips(self, services: list[Service], after: int) -> list[Trip]:
        """All running trips with at least one call at or after `after`."""
        out = []
        for svc in services:
            if svc.status == "cancelled":
                continue
            for branch in svc.branches:
                for stops in (branch, branch[::-1]):
                    for dep in range(svc.first_dep, svc.last_dep + 1, svc.headway):
                        calls = self.run_calls(stops, dep, svc.delay_min)
                        if calls and calls[-1][1] >= after:
                            out.append(Trip(svc.id, svc.name, tuple(calls), svc.accessible))
        return out


def service_edges(svc: Service) -> set[frozenset]:
    return {frozenset(e) for branch in svc.branches for e in zip(branch, branch[1:])}
