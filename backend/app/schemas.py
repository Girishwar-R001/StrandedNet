"""Pydantic request bodies. Responses are shaped explicitly by privacy-aware view functions."""
from typing import Literal

from pydantic import BaseModel, Field, model_validator

Requirement = Literal["wheelchair", "step_free", "luggage"]
Minute = Field(ge=0, le=1800)


class Login(BaseModel):
    email: str
    password: str


class Register(BaseModel):
    email: str = Field(pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$", max_length=200)
    password: str = Field(min_length=8, max_length=200)
    name: str = Field(min_length=2, max_length=120)
    phone: str = Field(default="", max_length=40)


class JourneyIn(BaseModel):
    origin_stop: str
    dest_stop: str
    party_size: int = Field(ge=1, le=8)
    dep_earliest: int = Minute
    dep_latest: int = Minute
    latest_arrival: int = Minute
    max_wait: int = Field(default=45, ge=5, le=180)
    max_walk_m: int = Field(default=500, ge=0, le=3000)
    requirements: list[Requirement] = []
    booked_service_id: str | None = None

    @model_validator(mode="after")
    def _times(self):
        if self.origin_stop == self.dest_stop:
            raise ValueError("Origin and destination must differ")
        if self.dep_latest < self.dep_earliest:
            raise ValueError("Latest departure is before earliest departure")
        if self.latest_arrival <= self.dep_earliest:
            raise ValueError("Latest arrival must be after departure")
        return self


class PreferenceIn(BaseModel):
    first_option_id: int
    second_option_id: int | None = None


class SelfResolve(BaseModel):
    option_id: int | None = None


class DisruptionIn(BaseModel):
    kind: Literal["cancellation", "delay", "route_closure", "vehicle_unavailable", "capacity_reduction"]
    service_id: str | None = None
    vehicle_id: str | None = None
    segment_id: int | None = None
    delay_min: int = Field(default=0, ge=0, le=240)
    new_capacity: int | None = Field(default=None, ge=0, le=100)
    description: str = Field(default="", max_length=400)
    duration_min: int | None = Field(default=None, ge=1, le=1440)


class VehicleIn(BaseModel):
    id: str = Field(min_length=2, max_length=12)
    vehicle_type: str = Field(min_length=2, max_length=40)
    capacity: int = Field(ge=1, le=100)
    stops: list[str] = Field(min_length=2)
    ready_min: int = Minute
    wheelchair: bool = False
    luggage: bool = True


class VehicleStatusIn(BaseModel):
    status: Literal["available", "unavailable"]


class RulesIn(BaseModel):
    weights: dict[str, float]
    reason: str = Field(min_length=3, max_length=400)

    @model_validator(mode="after")
    def _keys(self):
        expected = {"waiting", "urgency", "scarcity", "group", "preference"}
        if set(self.weights) != expected:
            raise ValueError(f"Weights must be exactly {sorted(expected)}")
        if any(v < 0 or v > 1 for v in self.weights.values()):
            raise ValueError("Each weight must be between 0 and 1")
        if abs(sum(self.weights.values()) - 1) > 0.001:
            raise ValueError("Weights must sum to 1.00")
        return self


class ReasonIn(BaseModel):
    reason: str = Field(min_length=3, max_length=400)


class OverrideIn(BaseModel):
    journey_id: int
    vehicle_id: str
    reason: str = Field(min_length=3, max_length=400)


class ReassignIn(BaseModel):
    vehicle_id: str
    reason: str = Field(min_length=3, max_length=400)


class OfferIn(BaseModel):
    origin_stop: str
    dest_stop: str
    departure: int = Minute
    available_seats: int = Field(ge=1, le=7)
    vehicle_type: str = Field(default="Car", min_length=2, max_length=40)
    wheelchair: bool = False
    luggage: bool = True
    pickup_zone: str = Field(default="", max_length=40)
    notes: str = Field(default="", max_length=300)
    consent: bool  # the provider must explicitly accept the community-ride terms

    @model_validator(mode="after")
    def _check(self):
        if self.origin_stop == self.dest_stop:
            raise ValueError("Origin and destination must differ")
        if not self.consent:
            raise ValueError("You must accept the community carpool terms")
        return self


class RespondIn(BaseModel):
    accept: bool


class CancelIn(BaseModel):
    reason: str = Field(default="", max_length=400)
