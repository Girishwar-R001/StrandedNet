"""Core data entities (spec section 8).

Times of day are stored as integer minutes since midnight on the simulated service day.
Audit and notification timestamps are real wall-clock UTC.

Capacity invariants live in the schema, not only in application code:
  * vehicles.available_seats is CHECK-constrained to 0..capacity
  * carpool_offers.reserved_seats is CHECK-constrained to 0..available_seats
  * a journey can hold at most one active official allocation (partial unique index)
"""
from datetime import datetime, timezone

from sqlalchemy import (JSON, Boolean, CheckConstraint, DateTime, Float, ForeignKey, Index,
                        Integer, String, Text, UniqueConstraint, text)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .database import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


ACTIVE_ALLOCATION = ("proposed", "approved", "confirmed", "needs_review")
_ACTIVE_SQL = "status IN ('proposed','approved','confirmed','needs_review')"


class User(Base):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(200), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(300))
    role: Mapped[str] = mapped_column(String(20), default="passenger")  # passenger | operator
    name: Mapped[str] = mapped_column(String(120))
    phone: Mapped[str] = mapped_column(String(40), default="")
    rides_completed: Mapped[int] = mapped_column(Integer, default=0)
    member_since: Mapped[str] = mapped_column(String(20), default="2026")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class Stop(Base):
    __tablename__ = "stops"
    id: Mapped[str] = mapped_column(String(8), primary_key=True)
    name: Mapped[str] = mapped_column(String(120))
    lat: Mapped[float] = mapped_column(Float)
    lng: Mapped[float] = mapped_column(Float)
    zone: Mapped[str] = mapped_column(String(40))


class Segment(Base):
    __tablename__ = "segments"
    id: Mapped[int] = mapped_column(primary_key=True)
    a: Mapped[str] = mapped_column(ForeignKey("stops.id"))
    b: Mapped[str] = mapped_column(ForeignKey("stops.id"))
    minutes: Mapped[int] = mapped_column(Integer)
    blocked: Mapped[bool] = mapped_column(Boolean, default=False)


class Service(Base):
    __tablename__ = "services"
    id: Mapped[str] = mapped_column(String(12), primary_key=True)
    name: Mapped[str] = mapped_column(String(120))
    mode: Mapped[str] = mapped_column(String(20), default="bus")
    branches: Mapped[list] = mapped_column(JSON)  # list of ordered stop-id lists
    first_dep: Mapped[int] = mapped_column(Integer)
    last_dep: Mapped[int] = mapped_column(Integer)
    headway: Mapped[int] = mapped_column(Integer)
    accessible: Mapped[bool] = mapped_column(Boolean, default=False)
    status: Mapped[str] = mapped_column(String(20), default="running")  # running|delayed|cancelled
    delay_min: Mapped[int] = mapped_column(Integer, default=0)


class Vehicle(Base):
    __tablename__ = "vehicles"
    __table_args__ = (
        CheckConstraint("available_seats >= 0", name="ck_vehicle_seats_nonneg"),
        CheckConstraint("available_seats <= capacity", name="ck_vehicle_seats_le_capacity"),
    )
    id: Mapped[str] = mapped_column(String(12), primary_key=True)
    vehicle_type: Mapped[str] = mapped_column(String(40))
    capacity: Mapped[int] = mapped_column(Integer)
    available_seats: Mapped[int] = mapped_column(Integer)
    stops: Mapped[list] = mapped_column(JSON)  # ordered stop ids on the replacement run
    ready_min: Mapped[int] = mapped_column(Integer)  # departure from first stop
    wheelchair: Mapped[bool] = mapped_column(Boolean, default=False)
    luggage: Mapped[bool] = mapped_column(Boolean, default=True)
    status: Mapped[str] = mapped_column(String(20), default="available")  # available|unavailable


class Disruption(Base):
    __tablename__ = "disruptions"
    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(16))
    kind: Mapped[str] = mapped_column(String(30))
    # cancellation | delay | route_closure | vehicle_unavailable | capacity_reduction
    service_id: Mapped[str | None] = mapped_column(ForeignKey("services.id"), nullable=True)
    vehicle_id: Mapped[str | None] = mapped_column(ForeignKey("vehicles.id"), nullable=True)
    segment_id: Mapped[int | None] = mapped_column(ForeignKey("segments.id"), nullable=True)
    delay_min: Mapped[int] = mapped_column(Integer, default=0)
    prior_capacity: Mapped[int | None] = mapped_column(Integer, nullable=True)
    description: Mapped[str] = mapped_column(Text, default="")
    start_min: Mapped[int] = mapped_column(Integer)
    est_end_min: Mapped[int | None] = mapped_column(Integer, nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="active")  # active|resolved
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class PassengerGroup(Base):
    __tablename__ = "passenger_groups"
    id: Mapped[int] = mapped_column(primary_key=True)
    label: Mapped[str] = mapped_column(String(12))
    destination_zone: Mapped[str] = mapped_column(String(40))
    pickup_stop: Mapped[str] = mapped_column(ForeignKey("stops.id"))
    combined_size: Mapped[int] = mapped_column(Integer)
    score: Mapped[float] = mapped_column(Float)
    est_minutes: Mapped[int] = mapped_column(Integer)
    explanation: Mapped[str] = mapped_column(Text)
    breakdown: Mapped[dict] = mapped_column(JSON, default=dict)
    status: Mapped[str] = mapped_column(String(20), default="active")  # active|superseded
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class Journey(Base):
    """The spec's Passenger entity: one travelling party led by a registered user."""
    __tablename__ = "journeys"
    __table_args__ = (CheckConstraint("party_size >= 1", name="ck_party_size"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    ref: Mapped[str] = mapped_column(String(12), unique=True, index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    origin_stop: Mapped[str] = mapped_column(ForeignKey("stops.id"))
    dest_stop: Mapped[str] = mapped_column(ForeignKey("stops.id"))
    lat: Mapped[float] = mapped_column(Float)  # current location; never leaves the backend raw
    lng: Mapped[float] = mapped_column(Float)
    party_size: Mapped[int] = mapped_column(Integer, default=1)
    dep_earliest: Mapped[int] = mapped_column(Integer)
    dep_latest: Mapped[int] = mapped_column(Integer)
    latest_arrival: Mapped[int] = mapped_column(Integer)
    max_wait: Mapped[int] = mapped_column(Integer, default=45)
    max_walk_m: Mapped[int] = mapped_column(Integer, default=500)
    requirements: Mapped[list] = mapped_column(JSON, default=list)  # wheelchair|step_free|luggage
    booked_service_id: Mapped[str | None] = mapped_column(ForeignKey("services.id"), nullable=True)
    # normal | affected | allocated | carpool_confirmed | self_resolved
    status: Mapped[str] = mapped_column(String(24), default="normal", index=True)
    disruption_id: Mapped[int | None] = mapped_column(ForeignKey("disruptions.id"), nullable=True)
    group_id: Mapped[int | None] = mapped_column(ForeignKey("passenger_groups.id"), nullable=True)
    reported_min: Mapped[int] = mapped_column(Integer)
    self_reported: Mapped[bool] = mapped_column(Boolean, default=False)
    carpool_opt_out: Mapped[bool] = mapped_column(Boolean, default=False)
    outcome_note: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

    user: Mapped[User] = relationship()
    group: Mapped[PassengerGroup | None] = relationship()
    disruption: Mapped[Disruption | None] = relationship()


class JourneyOption(Base):
    __tablename__ = "journey_options"
    __table_args__ = (UniqueConstraint("journey_id", "key", name="uq_option_key"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    journey_id: Mapped[int] = mapped_column(ForeignKey("journeys.id"), index=True)
    key: Mapped[str] = mapped_column(String(80))  # stable across regeneration, so preferences survive
    kind: Mapped[str] = mapped_column(String(24))
    # replacement | different_pickup | later_departure | transfer
    title: Mapped[str] = mapped_column(String(160))
    vehicle_id: Mapped[str | None] = mapped_column(ForeignKey("vehicles.id"), nullable=True)
    legs: Mapped[list] = mapped_column(JSON, default=list)
    pickup_stop: Mapped[str] = mapped_column(ForeignKey("stops.id"))
    departure: Mapped[int] = mapped_column(Integer)
    arrival: Mapped[int] = mapped_column(Integer)
    transfers: Mapped[int] = mapped_column(Integer, default=0)
    walk_m: Mapped[int] = mapped_column(Integer, default=0)
    wait_min: Mapped[int] = mapped_column(Integer, default=0)
    reservable: Mapped[bool] = mapped_column(Boolean, default=False)
    meets_deadline: Mapped[bool] = mapped_column(Boolean, default=True)
    status: Mapped[str] = mapped_column(String(20), default="active")  # active|unavailable


class Preference(Base):
    __tablename__ = "preferences"
    __table_args__ = (
        UniqueConstraint("journey_id", "rank", name="uq_pref_rank"),
        CheckConstraint("rank IN (1, 2)", name="ck_pref_rank"),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    journey_id: Mapped[int] = mapped_column(ForeignKey("journeys.id"), index=True)
    option_id: Mapped[int] = mapped_column(ForeignKey("journey_options.id"))
    rank: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(20), default="submitted")
    # submitted | invalidated | satisfied | not_satisfied
    submitted_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    option: Mapped[JourneyOption] = relationship()


class AllocationRun(Base):
    __tablename__ = "allocation_runs"
    id: Mapped[int] = mapped_column(primary_key=True)
    solver: Mapped[str] = mapped_column(String(20))
    summary: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class Allocation(Base):
    __tablename__ = "allocations"
    __table_args__ = (
        CheckConstraint("seats >= 1", name="ck_alloc_seats"),
        Index("uq_active_allocation_per_journey", "journey_id", unique=True,
              sqlite_where=text(_ACTIVE_SQL), postgresql_where=text(_ACTIVE_SQL)),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    journey_id: Mapped[int] = mapped_column(ForeignKey("journeys.id"), index=True)
    group_id: Mapped[int | None] = mapped_column(ForeignKey("passenger_groups.id"), nullable=True)
    vehicle_id: Mapped[str] = mapped_column(ForeignKey("vehicles.id"), index=True)
    run_id: Mapped[int | None] = mapped_column(ForeignKey("allocation_runs.id"), nullable=True)
    seats: Mapped[int] = mapped_column(Integer)
    pickup_stop: Mapped[str] = mapped_column(ForeignKey("stops.id"))
    pickup_min: Mapped[int] = mapped_column(Integer)
    arrival_min: Mapped[int] = mapped_column(Integer)
    priority_score: Mapped[float] = mapped_column(Float, default=0)
    breakdown: Mapped[dict] = mapped_column(JSON, default=dict)
    checks: Mapped[list] = mapped_column(JSON, default=list)
    explanation: Mapped[str] = mapped_column(Text, default="")
    preference_outcome: Mapped[str] = mapped_column(String(24), default="no_preference")
    # proposed | approved | confirmed | needs_review | rejected | cancelled
    status: Mapped[str] = mapped_column(String(20), default="proposed", index=True)
    seats_held: Mapped[bool] = mapped_column(Boolean, default=False)
    is_override: Mapped[bool] = mapped_column(Boolean, default=False)
    override_reason: Mapped[str] = mapped_column(Text, default="")
    flag_reason: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    approved_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    confirmed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    journey: Mapped[Journey] = relationship()
    vehicle: Mapped[Vehicle] = relationship()
    group: Mapped[PassengerGroup | None] = relationship()


class CarpoolRequest(Base):
    __tablename__ = "carpool_requests"
    id: Mapped[int] = mapped_column(primary_key=True)
    label: Mapped[str] = mapped_column(String(12))
    origin_zone: Mapped[str] = mapped_column(String(40))
    pickup_area: Mapped[str] = mapped_column(String(120))  # general area only
    destination_zone: Mapped[str] = mapped_column(String(40))
    destination_name: Mapped[str] = mapped_column(String(120))
    dest_stop: Mapped[str] = mapped_column(ForeignKey("stops.id"))
    origin_stop: Mapped[str] = mapped_column(ForeignKey("stops.id"))
    passenger_count: Mapped[int] = mapped_column(Integer, default=0)
    window_start: Mapped[int] = mapped_column(Integer)
    window_end: Mapped[int] = mapped_column(Integer)
    requirements: Mapped[list] = mapped_column(JSON, default=list)
    # open | offer_received | match_proposed | awaiting_passenger | awaiting_provider
    # | confirmed | cancelled | completed
    status: Mapped[str] = mapped_column(String(24), default="open")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class CarpoolRequestMember(Base):
    __tablename__ = "carpool_request_members"
    __table_args__ = (UniqueConstraint("request_id", "journey_id", name="uq_request_member"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    request_id: Mapped[int] = mapped_column(ForeignKey("carpool_requests.id"), index=True)
    journey_id: Mapped[int] = mapped_column(ForeignKey("journeys.id"), index=True)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    journey: Mapped[Journey] = relationship()


class CarpoolOffer(Base):
    __tablename__ = "carpool_offers"
    __table_args__ = (
        CheckConstraint("available_seats >= 1", name="ck_offer_seats"),
        CheckConstraint("reserved_seats >= 0", name="ck_offer_reserved_nonneg"),
        CheckConstraint("reserved_seats <= available_seats", name="ck_offer_reserved_le_seats"),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    label: Mapped[str] = mapped_column(String(12))
    provider_user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    origin_stop: Mapped[str] = mapped_column(ForeignKey("stops.id"))
    dest_stop: Mapped[str] = mapped_column(ForeignKey("stops.id"))
    departure: Mapped[int] = mapped_column(Integer)
    available_seats: Mapped[int] = mapped_column(Integer)
    reserved_seats: Mapped[int] = mapped_column(Integer, default=0)
    vehicle_type: Mapped[str] = mapped_column(String(40), default="Car")
    wheelchair: Mapped[bool] = mapped_column(Boolean, default=False)
    luggage: Mapped[bool] = mapped_column(Boolean, default=True)
    pickup_zone: Mapped[str] = mapped_column(String(40), default="")
    notes: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(20), default="open")  # open|withdrawn|completed
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    provider: Mapped[User] = relationship()


class CarpoolMatch(Base):
    __tablename__ = "carpool_matches"
    id: Mapped[int] = mapped_column(primary_key=True)
    label: Mapped[str] = mapped_column(String(12))
    request_id: Mapped[int] = mapped_column(ForeignKey("carpool_requests.id"), index=True)
    offer_id: Mapped[int] = mapped_column(ForeignKey("carpool_offers.id"), index=True)
    matched_seats: Mapped[int] = mapped_column(Integer)
    # awaiting_passenger | awaiting_provider | confirmed | cancelled | completed
    status: Mapped[str] = mapped_column(String(24), default="awaiting_passenger", index=True)
    passenger_acceptance_status: Mapped[str] = mapped_column(String(20), default="pending")
    provider_confirmation_status: Mapped[str] = mapped_column(String(20), default="pending")
    pickup_stop: Mapped[str] = mapped_column(ForeignKey("stops.id"))
    pickup_min: Mapped[int] = mapped_column(Integer)
    detour_min: Mapped[int] = mapped_column(Integer, default=0)
    checks: Mapped[list] = mapped_column(JSON, default=list)
    cancel_reason: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    confirmed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    offer: Mapped[CarpoolOffer] = relationship()
    request: Mapped[CarpoolRequest] = relationship()
    members: Mapped[list["CarpoolMatchMember"]] = relationship(back_populates="match")


class CarpoolMatchMember(Base):
    __tablename__ = "carpool_match_members"
    __table_args__ = (UniqueConstraint("match_id", "journey_id", name="uq_match_member"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    match_id: Mapped[int] = mapped_column(ForeignKey("carpool_matches.id"), index=True)
    journey_id: Mapped[int] = mapped_column(ForeignKey("journeys.id"), index=True)
    seats: Mapped[int] = mapped_column(Integer)
    acceptance: Mapped[str] = mapped_column(String(20), default="pending")  # pending|accepted|declined
    match: Mapped[CarpoolMatch] = relationship(back_populates="members")
    journey: Mapped[Journey] = relationship()


class CarpoolReport(Base):
    __tablename__ = "carpool_reports"
    id: Mapped[int] = mapped_column(primary_key=True)
    match_id: Mapped[int] = mapped_column(ForeignKey("carpool_matches.id"))
    reporter_user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    reason: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class Notification(Base):
    __tablename__ = "notifications"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    kind: Mapped[str] = mapped_column(String(20), default="info")  # info|success|warning
    title: Mapped[str] = mapped_column(String(160))
    body: Mapped[str] = mapped_column(Text, default="")
    read: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class AuditEvent(Base):
    __tablename__ = "audit_events"
    id: Mapped[int] = mapped_column(primary_key=True)
    event_type: Mapped[str] = mapped_column(String(50), index=True)
    related_entity_id: Mapped[str] = mapped_column(String(40), default="")
    decision_or_change: Mapped[str] = mapped_column(Text)
    reason: Mapped[str] = mapped_column(Text, default="")
    actor_id: Mapped[str] = mapped_column(String(80), default="system")
    timestamp: Mapped[datetime] = mapped_column(DateTime, default=utcnow, index=True)


class Setting(Base):
    __tablename__ = "settings"
    key: Mapped[str] = mapped_column(String(40), primary_key=True)
    value: Mapped[dict] = mapped_column(JSON)
