"""
Populates the database with sample buses + events so the dashboard has
something to show immediately, without waiting on real edge devices.

Run once:  python seed.py
"""
import datetime as dt
import random

from database import SessionLocal, init_db
import models
from time_utils import utc_now_naive

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

STATE_SAMPLE_CENTERS = [
    ("Andaman and Nicobar Islands", 11.7401, 92.6586),
    ("Andhra Pradesh", 16.5062, 80.6480),
    ("Arunachal Pradesh", 27.0844, 93.6053),
    ("Assam", 26.1433, 91.7898),
    ("Bihar", 25.5941, 85.1376),
    ("Chandigarh", 30.7333, 76.7794),
    ("Chhattisgarh", 21.2514, 81.6296),
    ("Dadra and Nagar Haveli and Daman and Diu", 20.2763, 73.0083),
    ("Delhi", 28.5629, 77.1678),
    ("Goa", 15.4909, 73.8278),
    ("Gujarat", 23.2156, 72.6369),
    ("Haryana", 29.0588, 76.0856),
    ("Himachal Pradesh", 31.1048, 77.1734),
    ("Jammu and Kashmir", 34.0837, 74.7973),
    ("Jharkhand", 23.3441, 85.3096),
    ("Karnataka", 12.9716, 77.5946),
    ("Kerala", 8.5241, 76.9366),
    ("Ladakh", 34.1526, 77.5771),
    ("Lakshadweep", 10.5667, 72.6417),
    ("Madhya Pradesh", 23.2599, 77.4126),
    ("Maharashtra", 19.0760, 72.8777),
    ("Manipur", 24.8170, 93.9368),
    ("Meghalaya", 25.5788, 91.8933),
    ("Mizoram", 23.7271, 92.7176),
    ("Nagaland", 25.6751, 94.1086),
    ("Odisha", 20.2961, 85.8245),
    ("Puducherry", 11.9416, 79.8083),
    ("Punjab", 31.6340, 74.8723),
    ("Rajasthan", 26.9124, 75.7873),
    ("Sikkim", 27.3389, 88.6065),
    ("Tamil Nadu", 13.0827, 80.2707),
    ("Telangana", 17.3850, 78.4867),
    ("Tripura", 23.8315, 91.2868),
    ("Uttar Pradesh", 26.8467, 80.9462),
    ("Uttarakhand", 30.3165, 78.0322),
    ("West Bengal", 22.5726, 88.3639),
]

REGIONAL_EVENT_TYPES = [
    "pothole", "waterlogging", "traffic_congestion", "damaged_road",
    "missing_road_divider", "manhole_open", "rash_driving",
    "damaged_traffic_signal", "construction_zone", "vulnerable_pedestrian",
    "missing_zebra_crossing", "damaged_traffic_signboard",
]


def seed_regional_samples(db, now):
    rng = random.Random(26124)
    for index, (region, center_lat, center_lon) in enumerate(STATE_SAMPLE_CENTERS, start=1):
        bus_id = f"DEMO-{index:02d}-01"
        route_id = str(100 + index)
        bus_lat = center_lat + rng.uniform(-0.008, 0.008)
        bus_lon = center_lon + rng.uniform(-0.008, 0.008)

        bus = db.query(models.Bus).filter_by(bus_id=bus_id).first()
        if bus is None:
            bus = models.Bus(bus_id=bus_id)
            db.add(bus)
        bus.route_id, bus.status = route_id, "active"
        bus.last_lat, bus.last_lon, bus.last_seen = bus_lat, bus_lon, now

        if not db.query(models.TripSample).filter_by(bus_id=bus_id).first():
            for sample_index, offset in enumerate((-0.003, 0.003)):
                sample_time = now - dt.timedelta(minutes=sample_index * 12)
                db.add(models.TripSample(
                    bus_id=bus_id, route_id=route_id,
                    lat=bus_lat + offset, lon=bus_lon + offset,
                    recorded_at=sample_time,
                ))
                db.add(models.VehicleCountSample(
                    bus_id=bus_id,
                    vehicle_count=rng.randint(4, 18),
                    recorded_at=sample_time,
                ))

        if not db.query(models.Event).filter_by(bus_id=bus_id).first():
            event_type = REGIONAL_EVENT_TYPES[(index - 1) % len(REGIONAL_EVENT_TYPES)]
            event_time = now - dt.timedelta(minutes=index)
            db.add(models.Event(
                bus_id=bus_id,
                route_id=route_id,
                event_type=event_type,
                category=models.EVENT_CATEGORY.get(event_type, "other"),
                severity=models.EVENT_SEVERITY.get(event_type, "low"),
                confidence=round(rng.uniform(0.72, 0.97), 2),
                lat=bus_lat + rng.uniform(-0.002, 0.002),
                lon=bus_lon + rng.uniform(-0.002, 0.002),
                meta={"prototype_sample": True, "sample_region": region},
                event_timestamp=event_time,
                received_at=event_time,
            ))


def run():
    init_db()
    db = SessionLocal()
    now = utc_now_naive()

    for bus_id, route_id, status, lat, lon in BUSES:
        bus = db.query(models.Bus).filter_by(bus_id=bus_id).first()
        if bus is None:
            bus = models.Bus(bus_id=bus_id)
            db.add(bus)
        bus.route_id, bus.status = route_id, status
        bus.last_lat, bus.last_lon, bus.last_seen = lat, lon, now

        if not db.query(models.TripSample).filter_by(bus_id=bus_id).first():
            for sample_index, (lat_offset, lon_offset, count) in enumerate(((-0.004, -0.003, 8), (0.0, 0.0, 16), (0.004, 0.003, 11))):
                sample_time = now - dt.timedelta(minutes=sample_index * 20 + len(bus_id))
                db.add(models.TripSample(bus_id=bus_id, route_id=route_id,
                                         lat=lat + lat_offset, lon=lon + lon_offset,
                                         recorded_at=sample_time))
                db.add(models.VehicleCountSample(bus_id=bus_id, vehicle_count=count,
                                                 recorded_at=sample_time))

    if db.query(models.Event).count() == 0:
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

    seed_regional_samples(db, now)

    db.commit()
    db.close()
    print(f"Seeded database with sample buses/events for {len(STATE_SAMPLE_CENTERS)} States/UTs.")


if __name__ == "__main__":
    run()
