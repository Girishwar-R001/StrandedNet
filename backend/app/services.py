"""Cross-cutting helpers: audit trail, notifications, simulated clock, configurable rules."""
from sqlalchemy.orm import Session

from .models import AuditEvent, Notification, Setting, User

DEFAULT_WEIGHTS = {"waiting": 0.30, "urgency": 0.30, "scarcity": 0.20, "group": 0.10, "preference": 0.10}
DEFAULT_THRESHOLDS = {
    "waiting_cap_min": 60,        # waiting time at which the factor saturates
    "urgency_horizon_min": 90,    # slack beyond which a deadline is not urgent
    "group_full_party": 4,        # party size at which the integrity factor saturates
    "no_preference_value": 0.3,   # neutral value so non-responders are not heavily penalised
    "second_choice_value": 0.6,
    "carpool_max_detour_min": 15,
    "carpool_time_tolerance_min": 20,
    "carpool_dest_radius_m": 2500,
}
SIM_START_MIN = 17 * 60 + 40


def get_setting(db: Session, key: str, default):
    row = db.get(Setting, key)
    return row.value if row else default


def put_setting(db: Session, key: str, value) -> None:
    row = db.get(Setting, key)
    if row:
        row.value = value
    else:
        db.add(Setting(key=key, value=value))


def now_min(db: Session) -> int:
    return get_setting(db, "clock", {"now": SIM_START_MIN})["now"]


def weights(db: Session) -> dict:
    return get_setting(db, "weights", DEFAULT_WEIGHTS)


def thresholds(db: Session) -> dict:
    return {**DEFAULT_THRESHOLDS, **get_setting(db, "thresholds", {})}


def audit(db: Session, event_type: str, entity: str, change: str, reason: str = "",
          actor: "User | str | None" = None) -> None:
    label = actor if isinstance(actor, str) else (f"{actor.role}:{actor.email}" if actor else "system")
    db.add(AuditEvent(event_type=event_type, related_entity_id=str(entity),
                      decision_or_change=change, reason=reason, actor_id=label))


def notify(db: Session, user_id: int, title: str, body: str = "", kind: str = "info") -> None:
    db.add(Notification(user_id=user_id, title=title, body=body, kind=kind))


def fmt(minutes: int) -> str:
    return f"{minutes // 60 % 24:02d}:{minutes % 60:02d}"
