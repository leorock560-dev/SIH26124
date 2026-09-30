"""
URBANEYE — edge device configuration.
Everything a deployment engineer would need to tune lives here.
"""
import os

# ---------------------------------------------------------------------------
# Identity
# ---------------------------------------------------------------------------
BUS_ID = os.environ.get("URBANEYE_BUS_ID", "KA05-AB-3391")
ROUTE_ID = os.environ.get("URBANEYE_ROUTE_ID", "214")

# ---------------------------------------------------------------------------
# Camera sources. Each bus has up to 4 feeds; index/path can be a device
# index (0,1,2..), an RTSP url, or a video file for testing.
# ---------------------------------------------------------------------------
CAMERAS = {
    "front": os.environ.get("URBANEYE_CAM_FRONT", "0"),
    "rear": os.environ.get("URBANEYE_CAM_REAR", None),
    "side": os.environ.get("URBANEYE_CAM_SIDE", None),
    "cabin": os.environ.get("URBANEYE_CAM_CABIN", None),
}
# For the demo, only the front camera is required to be non-empty.

# ---------------------------------------------------------------------------
# Model
# ---------------------------------------------------------------------------
# Bundled vehicle checkpoint detects common COCO objects (vehicles/people).
# For road-hazard classes, provide a custom-trained checkpoint via the
# URBANEYE_MODEL_WEIGHTS environment variable.
MODEL_WEIGHTS = os.environ.get(
    "URBANEYE_MODEL_WEIGHTS",
    "models/damaged road,vehicles.pt"
)
ADDITIONAL_MODEL_WEIGHTS = {
    "pothole": os.environ.get(
        "URBANEYE_POTHOLE_MODEL_WEIGHTS",
        "models/pothhole_best.pt"
    ),
    "manhole": os.environ.get(
        "URBANEYE_MANHOLE_MODEL_WEIGHTS",
        "models/manhole_model.pt"
    ),
    "fall_people": os.environ.get(
        "URBANEYE_FALL_MODEL_WEIGHTS",
        "models/fall_people.pt"
    ),
    "number_plate": os.environ.get(
        "URBANEYE_NUMBER_MODEL_WEIGHTS",
        "models/number.pt"
    ),
    "accident": os.environ.get(
        "URBANEYE_ACCIDENT_MODEL_WEIGHTS",
        "models/accident.pt"
    ),
}

# Synthetic detections are opt-in; set URBANEYE_MOCK_MODE=true for demos
# without trained weights.
MOCK_MODE = os.environ.get("URBANEYE_MOCK_MODE", "false").lower()

DETECTION_CONFIDENCE_THRESHOLD = 0.25
TRACKER_CONFIG = "bytetrack.yaml"  # built into ultralytics

# Custom class list the model is trained on. Index order must match training.
CLASS_NAMES = [
    "vehicle_car", "vehicle_truck", "vehicle_bus", "vehicle_two_wheeler",
    "pedestrian", "license_plate",
    "pothole", "damaged_road", "manhole_open", "missing_road_divider",
    "missing_zebra_crossing", "damaged_traffic_signboard", "missing_traffic_signboard",
    "damaged_traffic_signal", "waterlogging", "construction_zone",
]

# Which classes are static road-hazard detections vs. tracked moving objects
HAZARD_CLASSES = {
    "pothole", "damaged_road", "manhole_open", "missing_road_divider",
    "missing_zebra_crossing", "damaged_traffic_signboard", "missing_traffic_signboard",
    "damaged_traffic_signal", "waterlogging", "construction_zone",
}
VEHICLE_CLASSES = {"vehicle_car", "vehicle_truck", "vehicle_bus", "vehicle_two_wheeler"}
PEDESTRIAN_CLASSES = {"pedestrian"}

# ---------------------------------------------------------------------------
# Behavior-rule thresholds (see event_rules.py)
# ---------------------------------------------------------------------------
CONGESTION_VEHICLE_COUNT = 12          # active tracks in frame to flag congestion
CONGESTION_SUSTAIN_SECONDS = 8         # must hold for this long
RASH_LATERAL_JITTER_PX = 55            # per-frame lateral swing considered "weaving"
RASH_MIN_EVENTS_IN_WINDOW = 4          # weaving occurrences in window -> rash driving
RASH_WINDOW_SECONDS = 6
ACCIDENT_IOU_THRESHOLD = 0.35          # bbox overlap between two vehicle tracks
HIT_AND_RUN_FLEE_SPEED_PX_S = 260      # departing speed right after a collision event
HIT_RUN_VEHICLE_PROXIMITY = 0.12       # normalized center distance between vehicles
HIT_RUN_FALL_PROXIMITY = 0.12          # normalized fall-to-vehicle center distance
EVENT_COOLDOWN_SECONDS = {             # per (event_type, rough-location) dedup window
    "default": 60,
    "traffic_congestion": 120,
}

# ---------------------------------------------------------------------------
# GPS
# ---------------------------------------------------------------------------
GPS_SOURCE = os.environ.get("URBANEYE_GPS_SOURCE", "mock")  # "mock" or "serial"
GPS_SERIAL_PORT = os.environ.get("URBANEYE_GPS_PORT", "/dev/ttyUSB0")
GPS_MOCK_START = (12.9716, 77.5946)  # Bengaluru, used to synthesize a route for demo

# ---------------------------------------------------------------------------
# Cloud connection
# ---------------------------------------------------------------------------
CLOUD_API_URL = os.environ.get("URBANEYE_CLOUD_URL", "http://localhost:8000/api")
CLOUD_API_KEY = os.environ.get("URBANEYE_API_KEY", "demo-key-change-me")
SEND_RETRY_BACKOFF_SECONDS = [2, 5, 15, 60]
OFFLINE_QUEUE_PATH = os.environ.get("URBANEYE_OFFLINE_QUEUE", "offline_queue.jsonl")

# ---------------------------------------------------------------------------
# Thumbnails (small JPEGs attached to incident-grade events only, to keep
# payloads tiny — never raw video, per the bandwidth requirement)
# ---------------------------------------------------------------------------
THUMBNAIL_MAX_WIDTH = 320
THUMBNAIL_JPEG_QUALITY = 60
SEND_THUMBNAILS_FOR = {"pothole", "manhole_open", "hit_and_run", "accident"}
