"""
URBANEYE central platform API.

Run:
    uvicorn app:app --reload --port 8000

Then visit http://localhost:8000/docs for interactive API docs.
"""
import os
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.sessions import SessionMiddleware

from database import init_db
import analytics
import auth
import buses
import events

BASE_DIR = Path(__file__).resolve().parent
SESSION_SECRET = os.environ.get("URBANEYE_SESSION_SECRET")
if not SESSION_SECRET and os.environ.get("URBANEYE_ENV") != "development":
    raise RuntimeError("Set URBANEYE_SESSION_SECRET, or explicitly set URBANEYE_ENV=development for local testing.")
SESSION_SECRET = SESSION_SECRET or "development-only-session-key"


@asynccontextmanager
async def lifespan(_: FastAPI):
    init_db()
    yield


app = FastAPI(
    title="UrbanEye Fleet Intelligence API",
    description="Ingests edge events from the bus fleet and serves the command dashboard.",
    version="1.0.0",
    lifespan=lifespan,
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://127.0.0.1:5500",
        "http://localhost:5500",
        "http://127.0.0.1:5501",
        "http://localhost:5501",
    ],
    allow_credentials=True,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["Content-Type"],
)
app.add_middleware(
    SessionMiddleware,
    secret_key=SESSION_SECRET,
    same_site="lax",
    https_only=os.environ.get("URBANEYE_HTTPS_ONLY", "false").lower() == "true",
)

app.include_router(events.router)
app.include_router(buses.router)
app.include_router(analytics.router)
app.include_router(auth.router)


@app.get("/api/health")
def health():
    return {"status": "ok"}


@app.get("/")
def home():
    return FileResponse(BASE_DIR / "index.html")


@app.get("/dashboard.html")
def dashboard(request: Request):
    if not request.session.get("officer_id"):
        return RedirectResponse("/", status_code=303)
    return FileResponse(BASE_DIR / "dashboard.html")


@app.get("/portal.css")
def portal_stylesheet():
    return FileResponse(BASE_DIR / "portal.css", media_type="text/css")


app.mount("/css", StaticFiles(directory=BASE_DIR / "css"), name="css")
app.mount("/js", StaticFiles(directory=BASE_DIR / "js"), name="js")
app.mount("/assets", StaticFiles(directory=BASE_DIR / "assets"), name="assets")
