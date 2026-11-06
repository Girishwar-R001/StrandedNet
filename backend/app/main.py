import asyncio
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException
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


class RequestGate:
    """Bounds API requests in flight, and tells dashboards when something changed.

    A request holds its database connection until its session closes, and closing needs a worker
    thread. Unbounded, a crowd fills every thread with requests waiting for a connection while
    the connection holders wait for a thread, and the server freezes with idle CPU. Admitting no
    more requests than there are connections makes that wait impossible.

    Handlers commit before returning, so any successful write means dashboards should refresh.
    One place, so no endpoint can forget. Written as plain ASGI so it adds no per-request task.
    """

    def __init__(self, inner):
        self.inner = inner
        self.gate: asyncio.Semaphore | None = None
        self.loop: asyncio.AbstractEventLoop | None = None

    def _semaphore(self) -> asyncio.Semaphore:
        loop = asyncio.get_running_loop()
        if self.loop is not loop:  # A semaphore belongs to one event loop; test clients each start their own.
            self.loop, self.gate = loop, asyncio.Semaphore(settings.max_concurrent_requests)
        return self.gate

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http" or not scope["path"].startswith("/api"):
            await self.inner(scope, receive, send)
            return
        status = 500

        async def capture(message):
            nonlocal status
            if message["type"] == "http.response.start":
                status = message["status"]
            await send(message)

        async with self._semaphore():
            await self.inner(scope, receive, capture)
        if scope["method"] != "GET" and status < 400:
            await common.hub.broadcast()


app.add_middleware(RequestGate)


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
