"""Reproducible demonstration scenario: "Evening commute cancellation".

A fictional transport network drawn over real Bengaluru geography. Stop positions are
approximate real locations, but every service, timetable, vehicle, passenger and travel time
is simulated. No real operator's data is used.

Scenario shape: 24 affected passengers in 14 parties, 3 vehicles (8 + 7 + 5 = 20 seats).
Demand is deliberately uneven, so the engine must leave seats empty rather than force bad fits:
  * East corridor wants 12 seats, but only RV-1 (8) serves it.
  * P-13 and P-14 cannot use any replacement run at all.
  * P-10 uses a wheelchair; only RV-3 is suitable.
  * P-10 and P-13 share a destination name but approach from opposite directions.
  * P-05, a party of 4, reports late and has no walk-up alternative that arrives in time. A
    first-come queue strands them; priority-aware allocation does not. This case is designed
    to show the difference, and the baseline is recomputed live on every run.
"""
import random

from sqlalchemy.orm import Session

from .database import Base
from .models import Journey, Segment, Service, Stop, User, Vehicle
from .security import hash_password
from .services import (DEFAULT_THRESHOLDS, DEFAULT_WEIGHTS, SIM_START_MIN, audit, put_setting)

DEMO_PASSWORD = "demo1234"


def hm(text: str) -> int:
    h, m = text.split(":")
    return int(h) * 60 + int(m)


STOPS = [
    ("YEL", "Yelahanka", 13.1007, 77.5963, "North"),
    ("HEB", "Hebbal", 13.0358, 77.5970, "North"),
    ("YPR", "Yeshwanthpur", 13.0280, 77.5400, "North"),
    ("SBC", "City Railway Station", 12.9781, 77.5695, "Central"),
    ("MGR", "MG Road", 12.9756, 77.6066, "Central"),
    ("IND", "Indiranagar", 12.9719, 77.6412, "East"),
    ("DOM", "Domlur", 12.9600, 77.6387, "East"),
    ("KRP", "KR Puram", 13.0075, 77.6959, "East"),
    ("MAR", "Marathahalli", 12.9569, 77.7011, "East"),
    ("WFD", "Whitefield", 12.9698, 77.7500, "East"),
    ("KOR", "Koramangala", 12.9352, 77.6245, "South"),
    ("SLK", "Silk Board", 12.9177, 77.6238, "South"),
    ("BEL", "Bellandur", 12.9260, 77.6762, "South"),
    ("ECY", "Electronic City", 12.8452, 77.6602, "South"),
    ("JAY", "Jayanagar", 12.9299, 77.5823, "South"),
    ("BSK", "Banashankari", 12.9255, 77.5468, "South"),
]

SEGMENTS = [
    ("YEL", "HEB", 18), ("HEB", "YPR", 14), ("HEB", "SBC", 22), ("YPR", "SBC", 16), ("HEB", "MGR", 24),
    ("HEB", "KRP", 20), ("SBC", "MGR", 12), ("MGR", "IND", 10), ("IND", "MAR", 18), ("IND", "KRP", 16),
    ("KRP", "MAR", 12), ("KRP", "WFD", 18), ("MAR", "WFD", 14), ("MGR", "KOR", 14), ("KOR", "SLK", 7),
    ("KOR", "DOM", 9), ("IND", "DOM", 6), ("SLK", "ECY", 24), ("SLK", "BEL", 12), ("BEL", "MAR", 11),
    ("SBC", "JAY", 16), ("JAY", "SLK", 14), ("JAY", "BSK", 9), ("SBC", "BSK", 20),
]

SERVICES = [
    # id, name, branches, first, last, headway, accessible
    ("X5", "X5 Cross-City Express",
     [["YEL", "HEB", "SBC", "MGR", "IND", "MAR", "WFD"], ["MGR", "KOR", "SLK", "ECY"], ["SBC", "JAY", "BSK"]],
     "17:30", "19:30", 30, True),
    ("R7", "R7 Central Link", [["YPR", "SBC", "MGR", "IND", "KRP"]], "17:30", "20:00", 20, False),
    ("R12", "R12 Outer Ring", [["HEB", "KRP", "MAR", "BEL", "SLK"]], "17:30", "20:00", 25, True),
    ("R21", "R21 Tech Corridor", [["IND", "KOR", "SLK", "ECY"]], "17:45", "20:00", 30, False),
    ("R33", "R33 East Feeder", [["KRP", "WFD"]], "17:30", "20:00", 30, False),
    ("R9", "R9 South Link", [["SBC", "JAY", "SLK"]], "17:40", "20:00", 30, True),
]

VEHICLES = [
    # id, type, capacity, stops, ready, wheelchair, luggage
    ("RV-1", "Minibus", 8, ["HEB", "SBC", "MGR", "IND", "MAR", "WFD"], "17:55", False, True),
    ("RV-2", "Van", 7, ["MGR", "KOR", "SLK", "ECY"], "18:05", False, True),
    ("RV-3", "Accessible van", 5, ["YEL", "HEB", "SBC", "JAY", "BSK"], "17:50", True, True),
]

# ref, name, origin, dest, party, dep_earliest, dep_latest, latest_arrival, max_wait, walk_m, reqs, reported
PARTIES = [
    ("P-01", "Asha Menon", "HEB", "WFD", 2, "17:50", "18:20", "19:30", 45, 500, [], "17:10"),
    ("P-02", "Vikram Rao", "HEB", "WFD", 1, "17:50", "18:15", "19:40", 40, 500, [], "17:32"),
    ("P-03", "Fatima Khan", "SBC", "WFD", 3, "18:05", "18:35", "19:40", 45, 500, ["luggage"], "17:15"),
    ("P-04", "Daniel Dsouza", "MGR", "IND", 1, "18:15", "18:45", "18:55", 40, 500, [], "17:25"),
    ("P-05", "Lakshmi Iyer", "IND", "WFD", 4, "18:25", "18:55", "19:15", 45, 500, [], "17:33"),
    ("P-06", "Sanjay Gowda", "DOM", "MAR", 1, "18:25", "18:50", "19:20", 45, 1500, [], "17:35"),
    ("P-07", "Priya Nair", "MGR", "ECY", 2, "18:00", "18:25", "19:15", 40, 500, [], "17:05"),
    ("P-08", "Imran Sheikh", "KOR", "ECY", 3, "18:10", "18:40", "19:10", 40, 500, [], "17:12"),
    ("P-09", "Neha Kulkarni", "KOR", "SLK", 1, "18:10", "18:35", "18:45", 40, 500, [], "17:28"),
    ("P-10", "George Thomas", "YEL", "SBC", 2, "17:45", "18:15", "18:45", 45, 0, ["wheelchair"], "17:00"),
    ("P-11", "Kavya Reddy", "HEB", "JAY", 1, "18:00", "18:20", "19:05", 40, 500, ["step_free"], "17:18"),
    ("P-12", "Rahul Shetty", "HEB", "BSK", 1, "18:00", "18:25", "19:15", 40, 500, [], "17:22"),
    ("P-13", "Anita Joseph", "WFD", "SBC", 1, "17:55", "18:20", "19:30", 45, 500, [], "17:32"),
    ("P-14", "Harish Babu", "HEB", "ECY", 1, "18:00", "18:30", "19:30", 45, 500, [], "17:26"),
]

# On other services, so must stay unaffected. They prove the cancellation is targeted.
UNAFFECTED = [
    ("P-15", "Divya Pillai", "YPR", "IND", 1, "18:00", "18:30", "19:30", 45, 500, [], "17:30", "R7"),
    ("P-16", "Tariq Ali", "HEB", "MAR", 2, "18:00", "18:30", "19:30", 45, 500, [], "17:30", "R12"),
]

PROVIDERS = [
    ("meera@stranded.demo", "Meera Krishnan", "+91 90000 00101", 12, "2024"),
    ("arjun@stranded.demo", "Arjun Hegde", "+91 90000 00102", 3, "2025"),
]


def _email(name: str) -> str:
    return f"{name.split()[0].lower()}@stranded.demo"


def clear(db: Session) -> None:
    db.expunge_all()
    for table in reversed(Base.metadata.sorted_tables):
        db.execute(table.delete())
    db.commit()


def seed(db: Session) -> None:
    rng = random.Random(42)
    pw = hash_password(DEMO_PASSWORD)  # one hash for every demo user keeps resets fast

    put_setting(db, "clock", {"now": SIM_START_MIN})
    put_setting(db, "weights", dict(DEFAULT_WEIGHTS))
    put_setting(db, "thresholds", dict(DEFAULT_THRESHOLDS))

    positions = {}
    for sid, name, lat, lng, zone in STOPS:
        db.add(Stop(id=sid, name=name, lat=lat, lng=lng, zone=zone))
        positions[sid] = (lat, lng)
    db.flush()
    for a, b, minutes in SEGMENTS:
        db.add(Segment(a=a, b=b, minutes=minutes))
    for sid, name, branches, first, last, headway, accessible in SERVICES:
        db.add(Service(id=sid, name=name, branches=branches, first_dep=hm(first), last_dep=hm(last),
                       headway=headway, accessible=accessible))
    for vid, vtype, cap, stops, ready, wheelchair, luggage in VEHICLES:
        db.add(Vehicle(id=vid, vehicle_type=vtype, capacity=cap, available_seats=cap, stops=stops,
                       ready_min=hm(ready), wheelchair=wheelchair, luggage=luggage))

    db.add(User(email="operator@stranded.demo", password_hash=pw, role="operator",
                name="Control Room", phone=""))
    for email, name, phone, rides, since in PROVIDERS:
        db.add(User(email=email, password_hash=pw, name=name, phone=phone,
                    rides_completed=rides, member_since=since))

    rows = [(*p, "X5") for p in PARTIES] + UNAFFECTED
    for n, (ref, name, origin, dest, size, lo, hi, latest, wait, walk, reqs, reported, svc) in enumerate(rows):
        user = User(email=_email(name), password_hash=pw, name=name,
                    phone=f"+91 90000 {n + 1:05d}", member_since="2025")
        db.add(user)
        db.flush()
        lat, lng = positions[origin]
        db.add(Journey(ref=ref, user_id=user.id, origin_stop=origin, dest_stop=dest, party_size=size,
                       lat=lat + rng.uniform(-0.004, 0.004), lng=lng + rng.uniform(-0.004, 0.004),
                       dep_earliest=hm(lo), dep_latest=hm(hi), latest_arrival=hm(latest), max_wait=wait,
                       max_walk_m=walk, requirements=reqs, booked_service_id=svc, reported_min=hm(reported)))
    audit(db, "scenario_loaded", "demo", "Evening commute scenario loaded",
          "24 passengers on X5, 3 replacement vehicles, 20 official seats", "system")
    db.commit()


def reset(db: Session) -> None:
    clear(db)
    seed(db)
