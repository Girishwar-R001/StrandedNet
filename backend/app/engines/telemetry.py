"""Telemetry sanitizer (hackathon constraint 10: unreliable sensors).

Every vehicle reading passes through `ingest` before it can touch application state. The
guarantee is structural: **no code in this module writes `Vehicle.available_seats`,
`Vehicle.status` or any Allocation**. A bad reading can therefore never create phantom seats or
cancel a booking. Sensors inform; the database's atomic seat count and the operator decide.

Pipeline, in order:
  1. Duplicate filter   identical packet within DEDUP_WINDOW_S is dropped and counted.
  2. Spike check        seats outside 0..capacity are rejected against the static capacity.
  3. Delay check        an observation older than STALE_AFTER_S is not applied; the vehicle falls
                        back to dead reckoning from its last verified fix.
  4. Conflict check     sensors disagreeing about a vehicle with confirmed passengers quarantine
                        it for operator review. Bookings are left exactly as they were.
"""
import hashlib
import json
from datetime import datetime, timedelta

from sqlalchemy.orm import Session

from ..models import Allocation, AuditEvent, Vehicle, VehicleTelemetry, utcnow
from ..services import audit
from .network import Network

VERIFIED = "VERIFIED"
STALE = "STALE_DEAD_RECKONING"
QUARANTINED = "SENSOR_CONFLICT_QUARANTINED"

DEDUP_WINDOW_S = 5
STALE_AFTER_S = 30
DEAD_RECKON_S_PER_LEG = 60  # demo speed: one stop-to-stop leg per minute of lost signal

HEALTH_LABEL = {VERIFIED: "Verified Feed", STALE: "Stale Feed (Dead-Reckoning Active)",
                QUARANTINED: "Sensor Conflict Quarantined — DB Lock Enforced"}
HEALTH_TONE = {VERIFIED: "good", STALE: "warn", QUARANTINED: "bad"}
ALIAS = {"RV-1": "Vehicle A", "RV-2": "Vehicle B", "RV-3": "Vehicle C"}


def display(vehicle_id: str) -> str:
    return ALIAS.get(vehicle_id, vehicle_id)


def feed(db: Session, v: Vehicle, net: Network) -> VehicleTelemetry:
    """Created on first use, so vehicles added mid-demo get a feed with no extra wiring."""
    row = db.get(VehicleTelemetry, v.id)
    if row is None:
        first = net.stops[v.stops[0]]
        row = VehicleTelemetry(vehicle_id=v.id, lat=first.lat, lng=first.lng, sensors={"primary": "online"},
                               last_ping_at=utcnow())
        db.add(row)
        db.flush()
    return row


def _fingerprint(p: dict) -> str:
    return hashlib.sha256(json.dumps(p, sort_keys=True, default=str).encode()).hexdigest()


def _has_confirmed(db: Session, vehicle_id: str) -> int:
    return sum(a.seats for a in db.query(Allocation).filter_by(vehicle_id=vehicle_id, status="confirmed"))


def _note_duplicate(db: Session, row: VehicleTelemetry, at: datetime, actor) -> None:
    """A storm is one audit line with a running count, so noise cannot bury real events."""
    name = display(row.vehicle_id)
    recent = db.query(AuditEvent).filter(
        AuditEvent.event_type == "TELEMETRY_DUPLICATE_DROPPED", AuditEvent.related_entity_id == row.vehicle_id,
        AuditEvent.timestamp >= at - timedelta(seconds=DEDUP_WINDOW_S)).order_by(AuditEvent.id.desc()).first()
    if recent:
        count = int(recent.reason.split()[0]) + 1
        recent.reason = f"{count} repeated frames dropped in this burst. No re-routing was triggered."
        return
    audit(db, "TELEMETRY_DUPLICATE_DROPPED", row.vehicle_id,
          f"[DEDUPLICATED] Repeated packet from {name} dropped",
          "1 repeated frames dropped in this burst. No re-routing was triggered.", actor)


def ingest(db: Session, packet: dict, net: Network, actor=None, at: datetime | None = None) -> dict:
    """Sanitise one reading. `packet`: vehicle_id, sensor_id, timestamp (epoch seconds) and any
    of available_seats, lat, lng, status ('online' | 'offline')."""
    at = at or utcnow()
    v = db.get(Vehicle, packet["vehicle_id"])
    if v is None:
        raise ValueError(f"Unknown vehicle {packet['vehicle_id']}")
    row = feed(db, v, net)
    name = display(v.id)

    digest = _fingerprint(packet)
    if (row.last_packet_hash == digest and row.last_packet_at
            and (at - row.last_packet_at).total_seconds() <= DEDUP_WINDOW_S):
        row.duplicates_dropped += 1
        _note_duplicate(db, row, at, actor)
        return {"outcome": "duplicate", "vehicle_id": v.id}
    row.last_packet_hash, row.last_packet_at = digest, at

    seats = packet.get("available_seats")
    if seats is not None and not 0 <= seats <= v.capacity:
        row.spikes_rejected += 1
        audit(db, "TELEMETRY_SPIKE_REJECTED", v.id,
              f"[REJECTED] Sensor spike: {name} reported {seats} seats (max {v.capacity}). Enforcing DB Atomic Lock.",
              f"Sensor {packet.get('sensor_id', 'primary')} ignored. The database still shows "
              f"{v.available_seats} of {v.capacity} seats free.", actor)
        return {"outcome": "spike_rejected", "vehicle_id": v.id, "reported": seats, "max": v.capacity,
                "true_available": v.available_seats}

    observed = packet.get("timestamp")
    if observed is not None and at.timestamp() - observed > STALE_AFTER_S:
        late = round(at.timestamp() - observed)
        row.delayed_packets += 1
        row.gps_suspended = True
        if row.status == VERIFIED:
            row.status = STALE
        audit(db, "TELEMETRY_DELAYED", v.id, f"Delayed observation from {name} not applied ({late}s old)",
              "Keeping the last verified position and dead reckoning from it.", actor)
        return {"outcome": "delayed", "vehicle_id": v.id, "age_s": late}

    reported = packet.get("status")
    if reported:
        row.sensors = {**row.sensors, packet.get("sensor_id", "primary"): reported}
        readings = set(row.sensors.values())
        if reported == "offline":
            return _handle_offline(db, row, v, readings, actor)

    if seats is not None:
        row.last_reported_seats = seats
    if packet.get("lat") is not None and packet.get("lng") is not None:
        row.lat, row.lng = packet["lat"], packet["lng"]
    row.last_ping_at = at
    row.gps_suspended = False
    if row.status == STALE:
        row.status = VERIFIED
        audit(db, "TELEMETRY_RECOVERED", v.id, f"{name} feed verified again", "A fresh valid packet arrived.", actor)
    return {"outcome": "accepted", "vehicle_id": v.id}


def _handle_offline(db: Session, row: VehicleTelemetry, v: Vehicle, readings: set, actor) -> dict:
    name = display(v.id)
    booked = _has_confirmed(db, v.id)
    disputed = "online" in readings
    if disputed and booked:
        row.status = QUARANTINED
        row.conflict_flag = True
        row.conflict_detail = (f"Sensors disagree: {row.sensors}. {booked} confirmed seat(s) preserved "
                               f"until an operator decides.")
        audit(db, "TELEMETRY_CONFLICT_QUARANTINED", v.id,
              f"[NON-DESTRUCTIVE LOCK ACTIVE] {name} reported offline by one sensor and online by another. "
              f"STATUS: TELEMETRY_CONFLICT_PENDING_OPERATOR_REVIEW",
              f"{booked} confirmed seat(s) left untouched. Operator must verify the vehicle or override.", actor)
        return {"outcome": "quarantined", "vehicle_id": v.id, "confirmed_seats_preserved": booked}
    audit(db, "TELEMETRY_OFFLINE_REPORTED", v.id, f"{name} reported offline by a sensor; no state changed",
          "No confirmed passengers are at risk. Telemetry never withdraws a vehicle; an operator must.", actor)
    return {"outcome": "offline_logged", "vehicle_id": v.id}


def sweep(db: Session, net: Network, at: datetime | None = None) -> None:
    """Marks vehicles whose pings have stopped. Only vehicles with a lost signal are considered:
    the demo has no physical devices, so every other feed is treated as nominal."""
    at = at or utcnow()
    for row in db.query(VehicleTelemetry).filter_by(gps_suspended=True, status=VERIFIED):
        if (at - row.last_ping_at).total_seconds() > STALE_AFTER_S:
            row.status = STALE
            audit(db, "TELEMETRY_STALE", row.vehicle_id,
                  f"{display(row.vehicle_id)} switched to {STALE}",
                  "GPS pings stopped. Holding the last verified state and interpolating position along the route.")


def position(row: VehicleTelemetry, v: Vehicle, net: Network, at: datetime | None = None) -> dict:
    """The last fix, or an estimate along the route if the signal is lost. Never missing."""
    if row.status != STALE and not row.gps_suspended:
        return {"lat": row.lat, "lng": row.lng, "source": "verified", "signal_age_s": 0}
    age = max(0, ((at or utcnow()) - row.last_ping_at).total_seconds())
    pts = [net.stops[s] for s in v.stops]
    start = min(range(len(pts)), key=lambda i: (pts[i].lat - row.lat) ** 2 + (pts[i].lng - row.lng) ** 2)
    progress = start + age / DEAD_RECKON_S_PER_LEG
    i = min(int(progress), len(pts) - 1)
    if i == len(pts) - 1:
        return {"lat": pts[i].lat, "lng": pts[i].lng, "source": "dead_reckoning", "signal_age_s": round(age)}
    f = progress - i
    return {"lat": pts[i].lat + (pts[i + 1].lat - pts[i].lat) * f,
            "lng": pts[i].lng + (pts[i + 1].lng - pts[i].lng) * f,
            "source": "dead_reckoning", "signal_age_s": round(age)}


def lose_signal(db: Session, v: Vehicle, net: Network, at: datetime | None = None) -> None:
    row = feed(db, v, net)
    row.gps_suspended = True
    row.last_ping_at = (at or utcnow()) - timedelta(seconds=STALE_AFTER_S + 1)
    sweep(db, net, at)


def restore(db: Session, actor=None) -> int:
    """Brings lost signals back. A quarantine stays: only an operator decision may clear it."""
    restored = 0
    for row in db.query(VehicleTelemetry).filter_by(gps_suspended=True):
        row.gps_suspended = False
        row.last_ping_at = utcnow()
        if row.status == STALE:
            row.status = VERIFIED
        restored += 1
        audit(db, "TELEMETRY_RECOVERED", row.vehicle_id, f"{display(row.vehicle_id)} feed verified again",
              "GPS pings resumed.", actor)
    return restored


def resolve_conflict(db: Session, v: Vehicle, reason: str, actor) -> None:
    """The operator has verified the vehicle is running. Withdrawing it instead goes through the
    ordinary disruption pipeline, so affected passengers are flagged and told."""
    row = db.get(VehicleTelemetry, v.id)
    if row is None or not row.conflict_flag:
        raise ValueError("No sensor conflict to resolve")
    row.conflict_flag = False
    row.conflict_detail = ""
    row.status = STALE if row.gps_suspended else VERIFIED
    row.sensors = {"primary": "online"}
    audit(db, "TELEMETRY_CONFLICT_RESOLVED", v.id, f"Operator cleared the sensor conflict on {display(v.id)}", reason, actor)


def view(db: Session, v: Vehicle, net: Network) -> dict:
    row = feed(db, v, net)
    return {"vehicle_id": v.id, "name": display(v.id), "status": row.status, "label": HEALTH_LABEL[row.status],
            "tone": HEALTH_TONE[row.status], "conflict": row.conflict_flag, "conflict_detail": row.conflict_detail,
            "spikes_rejected": row.spikes_rejected, "duplicates_dropped": row.duplicates_dropped,
            "delayed_packets": row.delayed_packets, "last_reported_seats": row.last_reported_seats,
            "true_available": v.available_seats, "capacity": v.capacity, "position": position(row, v, net)}


def health(rows: list[dict]) -> dict:
    """Worst feed wins, so the header can never look healthier than the fleet."""
    worst = next((s for s in (QUARANTINED, STALE) if any(r["status"] == s for r in rows)), VERIFIED)
    return {"status": worst, "label": HEALTH_LABEL[worst], "tone": HEALTH_TONE[worst],
            "spikes_rejected": sum(r["spikes_rejected"] for r in rows),
            "duplicates_dropped": sum(r["duplicates_dropped"] for r in rows),
            "delayed_packets": sum(r["delayed_packets"] for r in rows),
            "conflicts": sum(1 for r in rows if r["conflict"]),
            "stale": sum(1 for r in rows if r["status"] == STALE)}
