"""
Turns raw per-frame detections + tracking into the higher-level events this
platform actually cares about. Static hazards (pothole, manhole, ...) map
almost 1:1 to a detection. Behavior events (rash driving, congestion,
accident, hit-and-run) require looking at track history over a short window.

NOTE ON REALISM: pixel-space speed/overlap heuristics below are a reasonable
starting point for a hackathon/demo build. A production system would
calibrate pixel-to-metres via camera homography, fuse in vehicle
odometry/IMU data, and likely use a purpose-trained action-recognition or
trajectory model for rash-driving/accident classification rather than
hand-tuned thresholds.
"""
import time
import math
import logging
from collections import defaultdict, deque

import config

log = logging.getLogger("urbaneye.rules")


class RawEvent:
    def __init__(self, event_type, confidence, bbox=None, track_id=None, extra=None):
        self.event_type = event_type
        self.confidence = confidence
        self.bbox = bbox
        self.track_id = track_id
        self.extra = extra or {}
        self.ts = time.time()


def _center(bbox):
    x1, y1, x2, y2 = bbox
    return ((x1 + x2) / 2, (y1 + y2) / 2)


def _normalized_distance(a, b, frame_shape):
    ax, ay = _center(a)
    bx, by = _center(b)
    height, width = frame_shape[:2]
    diagonal = math.hypot(width, height)
    return math.hypot(ax - bx, ay - by) / max(diagonal, 1.0)


def _iou(a, b):
    ax1, ay1, ax2, ay2 = a
    bx1, by1, bx2, by2 = b
    ix1, iy1 = max(ax1, bx1), max(ay1, by1)
    ix2, iy2 = min(ax2, bx2), min(ay2, by2)
    iw, ih = max(0, ix2 - ix1), max(0, iy2 - iy1)
    inter = iw * ih
    if inter == 0:
        return 0.0
    area_a = (ax2 - ax1) * (ay2 - ay1)
    area_b = (bx2 - bx1) * (by2 - by1)
    return inter / (area_a + area_b - inter)


class EventRuleEngine:
    def __init__(self):
        # track_id -> deque[(timestamp, center_x, center_y, bbox)]
        self.track_history = defaultdict(lambda: deque(maxlen=60))
        self.congestion_since = None
        self.recent_collisions = {}  # frozenset({id_a,id_b}) -> timestamp

    def update(self, detections, frame_shape=None):
        """detections: list[Detection] from ObjectDetector.infer()"""
        now = time.time()
        events = []
        vehicle_dets = [d for d in detections if d.cls_name in config.VEHICLE_CLASSES]
        fallen_people = [d for d in detections if d.cls_name == "fall_people"]

        # 1) static hazards -> direct events
        for d in detections:
            if d.cls_name in config.HAZARD_CLASSES:
                events.append(RawEvent(d.cls_name, d.confidence, bbox=d.bbox))
            elif d.cls_name == "accident":
                events.append(RawEvent(
                    "accident",
                    d.confidence,
                    bbox=d.bbox,
                    extra={"source": "accident_model"},
                ))

        # 2) a fall near a close pair of vehicles raises a suspected hit/run.
        if frame_shape is not None and len(vehicle_dets) >= 2:
            for fallen_person in fallen_people:
                nearby_vehicles = [
                    vehicle
                    for vehicle in vehicle_dets
                    if _normalized_distance(
                        fallen_person.bbox,
                        vehicle.bbox,
                        frame_shape,
                    ) <= config.HIT_RUN_FALL_PROXIMITY
                ]
                for index, first in enumerate(nearby_vehicles):
                    for second in nearby_vehicles[index + 1:]:
                        vehicle_distance = _normalized_distance(
                            first.bbox,
                            second.bbox,
                            frame_shape,
                        )
                        if vehicle_distance > config.HIT_RUN_VEHICLE_PROXIMITY:
                            continue
                        involved_ids = [
                            vehicle.track_id
                            for vehicle in (first, second)
                            if vehicle.track_id is not None
                        ]
                        nearest_vehicle = min(
                            (first, second),
                            key=lambda vehicle: _normalized_distance(
                                fallen_person.bbox,
                                vehicle.bbox,
                                frame_shape,
                            ),
                        )
                        events.append(RawEvent(
                            "hit_and_run",
                            min(
                                fallen_person.confidence,
                                first.confidence,
                                second.confidence,
                            ),
                            bbox=fallen_person.bbox,
                            track_id=nearest_vehicle.track_id,
                            extra={
                                "vehicle_track_ids": involved_ids,
                                "fall_confidence": round(
                                    fallen_person.confidence,
                                    3,
                                ),
                                "vehicle_distance": round(
                                    vehicle_distance,
                                    4,
                                ),
                            },
                        ))

        # 3) update track history for vehicles
        for d in vehicle_dets:
            if d.track_id is None:
                continue
            cx, cy = _center(d.bbox)
            self.track_history[d.track_id].append((now, cx, cy, d.bbox))

        # 4) congestion: sustained high vehicle count
        events.extend(self._check_congestion(vehicle_dets, now))

        # 5) per-track behavior: rash / unsafe driving
        for d in vehicle_dets:
            if d.track_id is None:
                continue
            ev = self._check_rash_driving(d.track_id, now)
            if ev:
                events.append(ev)

        # 6) pairwise: accident / fleeing after an overlap
        events.extend(self._check_collisions(vehicle_dets, now))

        return events

    # ------------------------------------------------------------------
    def _check_congestion(self, vehicle_dets, now):
        if len(vehicle_dets) >= config.CONGESTION_VEHICLE_COUNT:
            if self.congestion_since is None:
                self.congestion_since = now
            elif now - self.congestion_since >= config.CONGESTION_SUSTAIN_SECONDS:
                return [RawEvent("traffic_congestion", 0.85, extra={"vehicle_count": len(vehicle_dets)})]
        else:
            self.congestion_since = None
        return []

    # ------------------------------------------------------------------
    def _check_rash_driving(self, track_id, now):
        hist = self.track_history[track_id]
        window = [h for h in hist if now - h[0] <= config.RASH_WINDOW_SECONDS]
        if len(window) < 4:
            return None
        # count direction reversals in lateral (x) movement = "weaving"
        reversals = 0
        last_dir = None
        for i in range(1, len(window)):
            dx = window[i][1] - window[i - 1][1]
            if abs(dx) < 3:
                continue
            d = 1 if dx > 0 else -1
            if last_dir is not None and d != last_dir and abs(dx) > 5:
                reversals += 1
            last_dir = d
        max_swing = max(w[1] for w in window) - min(w[1] for w in window)
        if reversals >= config.RASH_MIN_EVENTS_IN_WINDOW and max_swing >= config.RASH_LATERAL_JITTER_PX:
            severity_conf = min(0.95, 0.6 + 0.05 * reversals)
            event_type = "rash_driving" if reversals >= config.RASH_MIN_EVENTS_IN_WINDOW + 2 else "unsafe_driving"
            return RawEvent(event_type, severity_conf, track_id=track_id,
                             extra={"lane_reversals": reversals, "lateral_swing_px": max_swing})
        return None

    # ------------------------------------------------------------------
    def _check_collisions(self, vehicle_dets, now):
        events = []
        for i in range(len(vehicle_dets)):
            for j in range(i + 1, len(vehicle_dets)):
                a, b = vehicle_dets[i], vehicle_dets[j]
                if a.track_id is None or b.track_id is None:
                    continue
                overlap = _iou(a.bbox, b.bbox)
                pair_key = frozenset({a.track_id, b.track_id})
                if overlap >= config.ACCIDENT_IOU_THRESHOLD and pair_key not in self.recent_collisions:
                    self.recent_collisions[pair_key] = now
                    events.append(RawEvent("accident", min(0.95, 0.5 + overlap), extra={
                        "track_ids": list(pair_key), "iou": round(overlap, 2)
                    }))

        # hit-and-run: one party from a recent collision now fleeing fast
        for pair_key, collided_at in list(self.recent_collisions.items()):
            if now - collided_at > 8:
                del self.recent_collisions[pair_key]
                continue
            for track_id in pair_key:
                hist = self.track_history.get(track_id)
                if not hist or len(hist) < 2:
                    continue
                t1, x1, y1, _ = hist[-2]
                t2, x2, y2, _ = hist[-1]
                dt = max(t2 - t1, 1e-3)
                speed_px_s = math.hypot(x2 - x1, y2 - y1) / dt
                if speed_px_s >= config.HIT_AND_RUN_FLEE_SPEED_PX_S:
                    events.append(RawEvent("hit_and_run", 0.88, track_id=track_id,
                                            extra={"flee_speed_px_s": round(speed_px_s, 1)}))
        return events
