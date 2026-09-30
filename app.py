"""
URBANEYE central platform API.

Run:
    uvicorn app:app --reload --port 8000

Then visit http://localhost:8000/docs for interactive API docs.
"""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from database import init_db
from routers import events, buses, analytics

app = FastAPI(
    title="UrbanEye Fleet Intelligence API",
    description="Ingests edge events from the bus fleet and serves the command dashboard.",
    version="1.0.0",
)

# Allow the dashboard (served from a different origin/port, e.g. file:// or
# a static host) to call this API directly from the browser.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],       # tighten this to your dashboard's real origin in production
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(events.router)
app.include_router(buses.router)
app.include_router(analytics.router)


@app.on_event("startup")
def on_startup():
    init_db()


@app.get("/api/health")
def health():
    return {"status": "ok"}
