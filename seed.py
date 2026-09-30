"""
Populates the database with sample buses + events so the dashboard has
something to show immediately, without waiting on real edge devices.

Run once:  python seed.py
"""
import datetime as dt

from database import SessionLocal, init_db
import models

BUSES = [
    ("KA05-AB-3391", "214", "active", 12.9716, 77.5946),
    ("KA05-AC-1187", "47", "active", 12.9789, 77.6045),
    ("KA05-AD-6620", "500D", "active", 12.9611, 77.5809),
    ("KA05-AE-9004", "318", "active", 12.9352, 77.6146),
    ("KA05-AF-2233", "214", "idle", 12.9884, 77.5766),
    ("KA05-AG-7745", "401", "active", 12.9439, 77.5540),
    ("KA05-AH-3312", "500D", "active", 12.9979, 77.6412),
    ("KA05-AJ-5591", "47", "offline", 12.9166, 77.6101),
]

EVENTS = [
    ("KA05-AB-3391", "214", "pothole", 0.94, 12.9701, 77.5921, None, None),
    ("KA05-AE-9004", "318", "hit_and_run", 0.88, 12.9358, 77.6132, "KA03MN7741", 0.91),
    ("KA05-AG-7745", "401", "waterlogging", 0.81, 12.9427, 77.5551, None, None),
    ("KA05-AC-1187", "47", "traffic_congestion", 0.89, 12.9795, 77.6031, None, None),
    ("KA05-AD-6620", "500D", "damaged_traffic_signal", 0.91, 12.9605, 77.5822, None, None),
    ("KA05-AB-3391", "214", "damaged_road", 0.77, 12.9740, 77.5978, None, None),
    ("KA05-AG-7745", "401", "rash_driving", 0.85, 12.9455, 77.5502, "KA41HT2290", 0.8),
    ("KA05-AC-1187", "47", "missing_road_divider", 0.79, 12.9151, 77.6087, None, None),
    ("KA05-AH-3312", "500D", "manhole_open", 0.83, 12.9962, 77.6390, None, None),
    ("KA05-AE-9004", "318", "construction_zone", 0.92, 12.9330, 77.6168, None, None),
]


def run():
    init_db()
    db = SessionLocal()
    now = dt.datetime.utcnow()

    for bus_id, route_id, status, lat, lon in BUSES:
        if not db.query(models.Bus).filter_by(bus_id=bus_id).first():
            db.add(models.Bus(bus_id=bus_id, route_id=route_id, status=status,
                               last_lat=lat, last_lon=lon, last_seen=now))

    for i, (bus_id, route_id, event_type, conf, lat, lon, plate, plate_conf) in enumerate(EVENTS):
        db.add(models.Event(
            bus_id=bus_id, route_id=route_id, event_type=event_type,
            category=models.EVENT_CATEGORY.get(event_type, "other"),
            severity=models.EVENT_SEVERITY.get(event_type, "low"),
            confidence=conf, lat=lat, lon=lon,
            plate_number=plate, plate_confidence=plate_conf,
            event_timestamp=now - dt.timedelta(minutes=i * 7),
            received_at=now - dt.timedelta(minutes=i * 7),
        ))

    db.commit()
    db.close()
    print("Seeded database with sample buses + events.")


if __name__ == "__main__":
    run()
