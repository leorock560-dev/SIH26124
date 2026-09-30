import datetime as dt

from sqlalchemy import Column, Integer, String, Float, DateTime, Text, JSON
from database import Base

# ---------------------------------------------------------------------------
# Event taxonomy — single source of truth for severity/category, used by
# the API when it ingests events and by the dashboard for badge colours.
# ---------------------------------------------------------------------------
EVENT_CATEGORY = {
    "pothole": "defect", "damaged_road": "defect", "manhole_open": "defect",
    "missing_road_divider": "defect", "damaged_traffic_signal": "defect",
    "waterlogging": "defect", "construction_zone": "defect",
    "traffic_congestion": "traffic",
    "rash_driving": "safety", "unsafe_driving": "safety",
    "accident": "incident", "hit_and_run": "incident",
}
EVENT_SEVERITY = {
    "pothole": "high", "damaged_road": "medium", "manhole_open": "high",
    "missing_road_divider": "medium", "damaged_traffic_signal": "medium",
    "waterlogging": "medium", "construction_zone": "low",
    "traffic_congestion": "medium",
    "rash_driving": "medium", "unsafe_driving": "low",
    "accident": "critical", "hit_and_run": "critical",
}


class Bus(Base):
    __tablename__ = "buses"

    id = Column(Integer, primary_key=True, index=True)
    bus_id = Column(String(32), unique=True, index=True, nullable=False)
    route_id = Column(String(16), nullable=True)
    status = Column(String(16), default="active")   # active | idle | offline
    last_lat = Column(Float, nullable=True)
    last_lon = Column(Float, nullable=True)
    last_seen = Column(DateTime, default=dt.datetime.utcnow)


class Event(Base):
    __tablename__ = "events"

    id = Column(Integer, primary_key=True, index=True)
    bus_id = Column(String(32), index=True, nullable=False)
    route_id = Column(String(16), nullable=True)
    event_type = Column(String(48), index=True, nullable=False)
    category = Column(String(16), index=True, nullable=False)
    severity = Column(String(16), index=True, nullable=False)
    confidence = Column(Float, nullable=False)
    lat = Column(Float, nullable=False)
    lon = Column(Float, nullable=False)
    plate_number = Column(String(16), nullable=True)
    plate_confidence = Column(Float, nullable=True)
    thumbnail_b64 = Column(Text, nullable=True)
    meta = Column(JSON, nullable=True)
    event_timestamp = Column(DateTime, nullable=False)   # when it happened on the bus
    received_at = Column(DateTime, default=dt.datetime.utcnow)  # when the cloud got it
