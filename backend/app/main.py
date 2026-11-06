from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse

from .config import settings
from .database import Base, SessionLocal, engine
from .models import User
from .routers import carpool, common, demo, operator, passenger
from .seed import seed

DIST = Path(__file__).resolve().parents[2] / "frontend" / "dist"


@asynccontextmanager
async def lifespan(_: FastAPI):
    if not settings.demo_mode and settings.jwt_secret.startswith("dev-only"):
        raise RuntimeError("Set JWT_SECRET before running with DEMO_MODE=false")
    Base.metadata.create_all(engine)
    with SessionLocal() as db:
        if db.query(User).first() is None:
            seed(db)
    yield


app = FastAPI(title="The Stranded Network", version="1.0.0", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=settings.cors_origins.split(","),
                   allow_methods=["*"], allow_headers=["*"])


@app.middleware("http")
async def notify_clients(request: Request, call_next):
    """Handlers commit before returning, so any successful write means both dashboards
    should refresh. One place, so no endpoint can forget."""
    response = await call_next(request)
    if request.method != "GET" and response.status_code < 400 and request.url.path.startswith("/api"):
        await common.hub.broadcast()
    return response


for module in (common, passenger, carpool, operator, demo):
    app.include_router(module.router)


@app.get("/api/health")
def health():
    return {"status": "ok"}


@app.get("/{path:path}", include_in_schema=False)
def spa(path: str):
    """Serves the built frontend, so a production build runs from this single process."""
    if path.startswith("api/"):
        raise HTTPException(404, "Not found")
    target = (DIST / path).resolve()
    if path and target.is_file() and target.is_relative_to(DIST):
        return FileResponse(target)
    index = DIST / "index.html"
    if index.is_file():
        return FileResponse(index)
    raise HTTPException(404, "Frontend not built. Run `npm run build` in frontend/, or use the Vite dev server.")
