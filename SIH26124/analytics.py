import datetime as dt
from typing import Optional

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from sqlalchemy import func

from database import get_db
from time_utils import utc_now_naive
import models
import schemas
from auth import require_officer

router = APIRouter(prefix="/api/analytics", tags=["analytics"])


@router.get(
    "/summary",
    response_model=schemas.FleetSummaryOut,
    dependencies=[Depends(require_officer)],
)
def summary(db: Session = Depends(get_db)):
    total = db.query(models.Bus).count()
    online = db.query(models.Bus).filter(models.Bus.status == "active").count()
    today_start = utc_now_naive().replace(hour=0, minute=0, second=0, microsecond=0)
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


@router.get("/defects-breakdown", dependencies=[Depends(require_officer)])
def defects_breakdown(days: int = 7, db: Session = Depends(get_db)):
    cutoff = utc_now_naive() - dt.timedelta(days=days)
    rows = (
        db.query(models.Event.event_type, func.count(models.Event.id))
        .filter(models.Event.category == "defect", models.Event.event_timestamp >= cutoff)
        .group_by(models.Event.event_type)
        .all()
    )
    return [{"type": t, "count": c} for t, c in rows]


@router.get("/hourly-activity", dependencies=[Depends(require_officer)])
def hourly_activity(
    hours: int = 24,
    category: Optional[str] = None,
    db: Session = Depends(get_db),
):
    """
    Event volume bucketed by hour-of-day. Used as a proxy for traffic
    density on the dashboard chart. A production build would log raw
    vehicle counts from every frame rather than only event volume —
    this only reflects moments the rules engine judged notable.
    """
    cutoff = utc_now_naive() - dt.timedelta(hours=hours)
    q = db.query(models.Event).filter(models.Event.event_timestamp >= cutoff)
    if category:
        q = q.filter(models.Event.category == category)
    buckets = {h: 0 for h in range(24)}
    for ev in q.all():
        buckets[ev.event_timestamp.hour] += 1
    return [{"hour": h, "count": c} for h, c in sorted(buckets.items())]


@router.get("/route-delay", dependencies=[Depends(require_officer)])
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


@router.get("/origin-destination", dependencies=[Depends(require_officer)])
def origin_destination(db: Session = Depends(get_db)):
    """Estimate observed route endpoints from recent heartbeat samples."""
    cutoff = utc_now_naive() - dt.timedelta(hours=24)
    samples = (
        db.query(models.TripSample)
        .filter(models.TripSample.recorded_at >= cutoff)
        .order_by(models.TripSample.bus_id, models.TripSample.recorded_at)
        .limit(5000)
        .all()
    )
    by_bus = {}
    for sample in samples:
        by_bus.setdefault(sample.bus_id, []).append(sample)
    pairs = []
    for bus_id, points in by_bus.items():
        if len(points) < 2:
            continue
        first, last = points[0], points[-1]
        pairs.append({
            "bus_id": bus_id,
            "route_id": last.route_id or first.route_id or "unknown",
            "origin": {"lat": first.lat, "lon": first.lon},
            "destination": {"lat": last.lat, "lon": last.lon},
            "samples": len(points),
        })
    return {"method": "first and last GPS heartbeat in the previous 24 hours", "pairs": pairs}


@router.get("/congestion-heat", dependencies=[Depends(require_officer)])
def congestion_heat(db: Session = Depends(get_db)):
    """Return GPS points for recorded traffic events, weighted by confidence."""
    cutoff = utc_now_naive() - dt.timedelta(hours=24)
    rows = db.query(models.Event).filter(
        models.Event.category == "traffic",
        models.Event.event_timestamp >= cutoff,
    ).limit(2000).all()
    return [{"lat": row.lat, "lon": row.lon, "weight": row.confidence} for row in rows]


@router.get("/vehicle-density", dependencies=[Depends(require_officer)])
def vehicle_density(db: Session = Depends(get_db)):
    """Average observed vehicle detections per edge heartbeat, grouped by hour."""
    cutoff = utc_now_naive() - dt.timedelta(hours=24)
    samples = db.query(models.VehicleCountSample).filter(
        models.VehicleCountSample.recorded_at >= cutoff,
    ).all()
    buckets = {hour: [] for hour in range(24)}
    for sample in samples:
        buckets[sample.recorded_at.hour].append(sample.vehicle_count)
    now = utc_now_naive()
    hours = [(now - dt.timedelta(hours=offset)).hour for offset in reversed(range(24))]
    return {
        "labels": [f"{hour:02d}:00" for hour in hours],
        "values": [round(sum(buckets[hour]) / len(buckets[hour]), 1) if buckets[hour] else 0 for hour in hours],
        "metric": "average detected vehicles per heartbeat",
    }
