import datetime as dt
from typing import Optional

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from sqlalchemy import func

from database import get_db
import models
import schemas

router = APIRouter(prefix="/api/analytics", tags=["analytics"])


@router.get("/summary", response_model=schemas.FleetSummaryOut)
def summary(db: Session = Depends(get_db)):
    total = db.query(models.Bus).count()
    online = db.query(models.Bus).filter(models.Bus.status == "active").count()
    today_start = dt.datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
    todays_events = db.query(models.Event).filter(models.Event.event_timestamp >= today_start)
    alerts_today = todays_events.count()
    avg_conf = db.query(func.avg(models.Event.confidence)).filter(
        models.Event.event_timestamp >= today_start
    ).scalar() or 0.0
    critical_open = todays_events.filter(models.Event.severity == "critical").count()
    return schemas.FleetSummaryOut(
        buses_online=online, buses_total=max(total, 1),
        alerts_today=alerts_today, avg_confidence=round(float(avg_conf), 3),
        critical_open=critical_open,
    )


@router.get("/defects-breakdown")
def defects_breakdown(days: int = 7, db: Session = Depends(get_db)):
    cutoff = dt.datetime.utcnow() - dt.timedelta(days=days)
    rows = (
        db.query(models.Event.event_type, func.count(models.Event.id))
        .filter(models.Event.category == "defect", models.Event.event_timestamp >= cutoff)
        .group_by(models.Event.event_type)
        .all()
    )
    return [{"type": t, "count": c} for t, c in rows]


@router.get("/hourly-activity")
def hourly_activity(hours: int = 24, category: Optional[str] = None, db: Session = Depends(get_db)):
    """
    Event volume bucketed by hour-of-day. Used as a proxy for traffic
    density on the dashboard chart. A production build would log raw
    vehicle counts from every frame rather than only event volume —
    this only reflects moments the rules engine judged notable.
    """
    cutoff = dt.datetime.utcnow() - dt.timedelta(hours=hours)
    q = db.query(models.Event).filter(models.Event.event_timestamp >= cutoff)
    if category:
        q = q.filter(models.Event.category == category)
    buckets = {h: 0 for h in range(24)}
    for ev in q.all():
        buckets[ev.event_timestamp.hour] += 1
    return [{"hour": h, "count": c} for h, c in sorted(buckets.items())]


@router.get("/route-delay")
def route_delay(db: Session = Depends(get_db)):
    """
    Heuristic proxy: routes with more congestion/incident events are
    assumed to be running behind schedule. Wiring in real GTFS scheduled
    vs. actual arrival times would replace this with a proper figure.
    """
    rows = (
        db.query(models.Event.route_id, func.count(models.Event.id))
        .filter(models.Event.category.in_(["traffic", "incident"]))
        .group_by(models.Event.route_id)
        .all()
    )
    return [{"route_id": r or "unknown", "disruption_events": c} for r, c in rows]
