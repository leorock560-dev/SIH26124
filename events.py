import datetime as dt
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Header
from sqlalchemy.orm import Session
from sqlalchemy import desc

from database import get_db
import models
import schemas

router = APIRouter(prefix="/api", tags=["events"])

VALID_API_KEY = None  # set from app.py at startup (kept simple for a demo)


def require_api_key(authorization: Optional[str] = Header(None)):
    """Very light bearer-token check — swap for real auth (OAuth/mTLS) in production."""
    import os
    expected = os.environ.get("URBANEYE_API_KEY", "demo-key-change-me")
    if authorization != f"Bearer {expected}":
        raise HTTPException(status_code=401, detail="Invalid or missing API key")


@router.post("/events", response_model=schemas.EventOut, status_code=201)
def ingest_event(event: schemas.EventIn, db: Session = Depends(get_db), _=Depends(require_api_key)):
    category = models.EVENT_CATEGORY.get(event.event_type, "other")
    severity = models.EVENT_SEVERITY.get(event.event_type, "low")

    row = models.Event(
        bus_id=event.bus_id, route_id=event.route_id, event_type=event.event_type,
        category=category, severity=severity, confidence=event.confidence,
        lat=event.lat, lon=event.lon, plate_number=event.plate_number,
        plate_confidence=event.plate_confidence, thumbnail_b64=event.thumbnail_b64,
        meta=event.meta, event_timestamp=event.timestamp,
    )
    db.add(row)

    # keep the bus's last-known position fresh even on event-triggered updates
    bus = db.query(models.Bus).filter(models.Bus.bus_id == event.bus_id).first()
    if bus is None:
        bus = models.Bus(bus_id=event.bus_id, route_id=event.route_id, status="active")
        db.add(bus)
    bus.last_lat, bus.last_lon = event.lat, event.lon
    bus.last_seen = dt.datetime.utcnow()
    bus.status = "active"

    db.commit()
    db.refresh(row)
    return row


@router.get("/events", response_model=list[schemas.EventOut])
def list_events(
    limit: int = 100,
    category: Optional[str] = None,
    severity: Optional[str] = None,
    bus_id: Optional[str] = None,
    since_hours: Optional[int] = None,
    db: Session = Depends(get_db),
):
    q = db.query(models.Event)
    if category:
        q = q.filter(models.Event.category == category)
    if severity:
        q = q.filter(models.Event.severity == severity)
    if bus_id:
        q = q.filter(models.Event.bus_id == bus_id)
    if since_hours:
        cutoff = dt.datetime.utcnow() - dt.timedelta(hours=since_hours)
        q = q.filter(models.Event.event_timestamp >= cutoff)
    return q.order_by(desc(models.Event.event_timestamp)).limit(min(limit, 500)).all()


@router.get("/events/{event_id}", response_model=schemas.EventOut)
def get_event(event_id: int, db: Session = Depends(get_db)):
    row = db.query(models.Event).filter(models.Event.id == event_id).first()
    if not row:
        raise HTTPException(status_code=404, detail="Event not found")
    return row
