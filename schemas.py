import datetime as dt
from typing import Optional, Any
from pydantic import BaseModel, Field


class EventIn(BaseModel):
    """Exactly what the edge device sends — kept deliberately minimal."""
    bus_id: str
    route_id: Optional[str] = None
    event_type: str
    confidence: float = Field(ge=0, le=1)
    timestamp: dt.datetime
    lat: float
    lon: float
    plate_number: Optional[str] = None
    plate_confidence: Optional[float] = None
    thumbnail_b64: Optional[str] = None
    meta: Optional[dict[str, Any]] = None


class EventOut(EventIn):
    id: int
    category: str
    severity: str
    received_at: dt.datetime

    class Config:
        from_attributes = True


class BusHeartbeatIn(BaseModel):
    bus_id: str
    route_id: Optional[str] = None
    lat: float
    lon: float
    status: str = "active"
    speed_kmh: Optional[float] = None
    occupancy: Optional[float] = None


class BusOut(BaseModel):
    bus_id: str
    route_id: Optional[str]
    status: str
    last_lat: Optional[float]
    last_lon: Optional[float]
    last_seen: dt.datetime

    class Config:
        from_attributes = True


class FleetSummaryOut(BaseModel):
    buses_online: int
    buses_total: int
    alerts_today: int
    avg_confidence: float
    critical_open: int
