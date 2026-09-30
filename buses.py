import datetime as dt

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from database import get_db
import models
import schemas
from routers.events import require_api_key

router = APIRouter(prefix="/api", tags=["buses"])


@router.post("/buses/heartbeat", status_code=204)
def heartbeat(hb: schemas.BusHeartbeatIn, db: Session = Depends(get_db), _=Depends(require_api_key)):
    """
    Edge devices call this periodically (e.g. every 10s) even when no event
    fired, so the fleet map shows live positions rather than only wherever
    the last alert happened.
    """
    bus = db.query(models.Bus).filter(models.Bus.bus_id == hb.bus_id).first()
    if bus is None:
        bus = models.Bus(bus_id=hb.bus_id)
        db.add(bus)
    bus.route_id = hb.route_id or bus.route_id
    bus.last_lat, bus.last_lon = hb.lat, hb.lon
    bus.status = hb.status
    bus.last_seen = dt.datetime.utcnow()
    db.commit()
    return None


@router.get("/buses", response_model=list[schemas.BusOut])
def list_buses(db: Session = Depends(get_db)):
    buses = db.query(models.Bus).all()
    # mark stale buses (no heartbeat in 2 min) as offline for display purposes
    cutoff = dt.datetime.utcnow() - dt.timedelta(minutes=2)
    for b in buses:
        if b.last_seen and b.last_seen < cutoff and b.status != "offline":
            b.status = "offline"
    db.commit()
    return buses
