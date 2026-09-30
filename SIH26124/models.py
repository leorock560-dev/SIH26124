from sqlalchemy import Column, Integer, String, Float, DateTime, Text, JSON
from database import Base
from time_utils import utc_now_naive

# ---------------------------------------------------------------------------
# Event taxonomy — single source of truth for severity/category, used by
# the API when it ingests events and by the dashboard for badge colours.
# ---------------------------------------------------------------------------
EVENT_CATEGORY = {
    "pothole": "defect", "damaged_road": "defect", "manhole_open": "defect",
    "missing_road_divider": "defect", "damaged_traffic_signal": "defect",
    "missing_zebra_crossing": "defect", "damaged_traffic_signboard": "defect",
    "missing_traffic_signboard": "defect",
    "waterlogging": "defect", "construction_zone": "defect",
    "traffic_congestion": "traffic",
    "vulnerable_pedestrian": "safety",
    "rash_driving": "safety", "unsafe_driving": "safety",
    "accident": "incident", "hit_and_run": "incident",
}
EVENT_SEVERITY = {
    "pothole": "high", "damaged_road": "medium", "manhole_open": "high",
    "missing_road_divider": "medium", "damaged_traffic_signal": "medium",
    "missing_zebra_crossing": "medium", "damaged_traffic_signboard": "medium",
    "missing_traffic_signboard": "medium",
    "waterlogging": "medium", "construction_zone": "low",
    "traffic_congestion": "medium",
    "vulnerable_pedestrian": "high",
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
    last_seen = Column(DateTime, default=utc_now_naive)


class Officer(Base):
    __tablename__ = "officers"

    id = Column(Integer, primary_key=True, index=True)
    full_name = Column(String(100), nullable=False)
    email = Column(String(254), nullable=False, unique=True, index=True)
    department = Column(String(150), nullable=False, default="Transport Authority")
    password_hash = Column(String(255), nullable=False)


class TripSample(Base):
    __tablename__ = "trip_samples"

    id = Column(Integer, primary_key=True, index=True)
    bus_id = Column(String(32), index=True, nullable=False)
    route_id = Column(String(16), nullable=True)
    lat = Column(Float, nullable=False)
    lon = Column(Float, nullable=False)
    recorded_at = Column(DateTime, default=utc_now_naive, index=True)


class VehicleCountSample(Base):
    __tablename__ = "vehicle_count_samples"

    id = Column(Integer, primary_key=True, index=True)
    bus_id = Column(String(32), index=True, nullable=False)
    vehicle_count = Column(Integer, nullable=False)
    recorded_at = Column(DateTime, default=utc_now_naive, index=True)


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
    received_at = Column(DateTime, default=utc_now_naive)  # when the cloud got it
