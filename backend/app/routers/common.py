"""Auth, shared network reference data and live updates."""
import asyncio

from fastapi import APIRouter, Depends, HTTPException, WebSocket, WebSocketDisconnect
from sqlalchemy.orm import Session

from ..config import settings
from ..database import get_db
from ..models import Segment, Service, Stop, User, Vehicle
from ..schemas import Login, Register
from ..security import create_token, current_user, decode_token, hash_password, verify_password
from ..services import audit, now_min

router = APIRouter(prefix="/api")


class Hub:
    """Pushes a contentless 'something changed' ping. Clients refetch through the normal
    role-checked endpoints, so no data can leak over the socket."""

    def __init__(self):
        self.clients: set[WebSocket] = set()

    async def broadcast(self) -> None:
        for ws in list(self.clients):
            try:
                await ws.send_json({"type": "changed"})
            except Exception:
                self.clients.discard(ws)


hub = Hub()


def user_view(u: User) -> dict:
    return {"id": u.id, "email": u.email, "name": u.name, "role": u.role, "phone": u.phone,
            "rides_completed": u.rides_completed, "member_since": u.member_since}


@router.post("/auth/login")
def login(body: Login, db: Session = Depends(get_db)):
    user = db.query(User).filter_by(email=body.email.strip().lower()).first()
    if not user or not verify_password(body.password, user.password_hash):
        raise HTTPException(401, "Incorrect email or password")
    return {"token": create_token(user), "user": user_view(user)}


@router.post("/auth/register", status_code=201)
def register(body: Register, db: Session = Depends(get_db)):
    email = body.email.strip().lower()
    if db.query(User).filter_by(email=email).first():
        raise HTTPException(409, "An account with this email already exists")
    # Public registration can only ever create passenger accounts.
    user = User(email=email, password_hash=hash_password(body.password), name=body.name,
                phone=body.phone, role="passenger")
    db.add(user)
    db.flush()
    audit(db, "user_registered", f"user-{user.id}", "New passenger account", "", user)
    db.commit()
    return {"token": create_token(user), "user": user_view(user)}


@router.get("/auth/me")
def me(user: User = Depends(current_user)):
    return user_view(user)


@router.get("/meta")
def meta(db: Session = Depends(get_db)):
    return {"now": now_min(db), "demo_mode": settings.demo_mode, "simulated": True}


@router.get("/network/stops")
def stops(_: User = Depends(current_user), db: Session = Depends(get_db)):
    return [{"id": s.id, "name": s.name, "lat": s.lat, "lng": s.lng, "zone": s.zone}
            for s in db.query(Stop).order_by(Stop.name)]


@router.get("/network/services")
def services(_: User = Depends(current_user), db: Session = Depends(get_db)):
    return [{"id": s.id, "name": s.name, "status": s.status, "delay_min": s.delay_min,
             "branches": s.branches} for s in db.query(Service).order_by(Service.id)]


@router.get("/network/segments")
def segments(_: User = Depends(current_user), db: Session = Depends(get_db)):
    names = {s.id: s.name for s in db.query(Stop)}
    return [{"id": s.id, "a": s.a, "b": s.b, "a_name": names[s.a], "b_name": names[s.b],
             "minutes": s.minutes, "blocked": s.blocked} for s in db.query(Segment).order_by(Segment.id)]


@router.get("/network/vehicles")
def vehicle_runs(_: User = Depends(current_user), db: Session = Depends(get_db)):
    return [{"id": v.id, "type": v.vehicle_type, "stops": v.stops, "status": v.status}
            for v in db.query(Vehicle).order_by(Vehicle.id)]


@router.websocket("/ws")
async def live(ws: WebSocket, token: str = ""):
    if not decode_token(token):
        await ws.close(code=4401)
        return
    await ws.accept()
    hub.clients.add(ws)
    try:
        while True:
            await asyncio.wait_for(ws.receive_text(), timeout=60)
    except (WebSocketDisconnect, asyncio.TimeoutError, RuntimeError):
        pass
    finally:
        hub.clients.discard(ws)
