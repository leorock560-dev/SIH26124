"""
URBANEYE edge entrypoint. Run one of these per camera-equipped bus:

    python main.py --camera front

For a quick end-to-end test without hardware or trained weights:

    URBANEYE_MOCK_MODE=true python main.py --camera front --no-display

This loop is intentionally simple (single process, single camera) so it's
easy to read end-to-end. A production build would run one process per
camera and fuse their events, or process all 4 feeds in one process with
threads — the detection/rules/sending pieces below don't change either way.
"""
import argparse
import base64
import logging
import os
import time
from concurrent.futures import ThreadPoolExecutor

import cv2
import numpy as np

import config
from object_detector import ObjectDetector
from event_rules import EventRuleEngine
from plate_ocr import PlateReader
from event_bus import EventBus
from gps import GPSReader
from sender import CloudSender

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("urbaneye.main")

INCIDENT_EVENTS_NEEDING_PLATE = {"hit_and_run", "rash_driving", "unsafe_driving", "accident"}


def make_thumbnail_b64(frame, bbox=None):
    if frame is None:
        return None
    img = frame
    if bbox:
        x1, y1, x2, y2 = [int(v) for v in bbox]
        x1, y1 = max(0, x1 - 20), max(0, y1 - 20)
        x2, y2 = min(frame.shape[1], x2 + 20), min(frame.shape[0], y2 + 20)
        if x2 > x1 and y2 > y1:
            img = frame[y1:y2, x1:x2]
    h, w = img.shape[:2]
    if w > config.THUMBNAIL_MAX_WIDTH:
        scale = config.THUMBNAIL_MAX_WIDTH / w
        img = cv2.resize(img, (config.THUMBNAIL_MAX_WIDTH, int(h * scale)))
    ok, buf = cv2.imencode(".jpg", img, [cv2.IMWRITE_JPEG_QUALITY, config.THUMBNAIL_JPEG_QUALITY])
    if not ok:
        return None
    return base64.b64encode(buf).decode("ascii")


def crop_for_bbox(frame, bbox):
    if frame is None or bbox is None:
        return None
    x1, y1, x2, y2 = [int(v) for v in bbox]
    x1, y1 = max(0, x1), max(0, y1)
    x2, y2 = min(frame.shape[1], x2), min(frame.shape[0], y2)
    if x2 <= x1 or y2 <= y1:
        return None
    return frame[y1:y2, x1:x2]


def read_plate_for_event(frame, event, detections, plate_reader):
    plate_detections = [
        detection
        for detection in detections
        if detection.cls_name == "number_plate"
    ]
    if not plate_detections:
        return None, 0.0

    involved_ids = set(event.extra.get("vehicle_track_ids", []))
    if event.track_id is not None:
        involved_ids.add(event.track_id)
    vehicles = [
        detection
        for detection in detections
        if detection.cls_name in config.VEHICLE_CLASSES
        and (not involved_ids or detection.track_id in involved_ids)
    ]
    if not vehicles:
        return None, 0.0

    if event.bbox is not None:
        event_center = (
            (event.bbox[0] + event.bbox[2]) / 2,
            (event.bbox[1] + event.bbox[3]) / 2,
        )
        vehicles.sort(
            key=lambda vehicle: (
                (vehicle.bbox[0] + vehicle.bbox[2]) / 2 - event_center[0]
            ) ** 2
            + (
                (vehicle.bbox[1] + vehicle.bbox[3]) / 2 - event_center[1]
            ) ** 2
        )

    for vehicle in vehicles:
        vx1, vy1, vx2, vy2 = vehicle.bbox
        matching_plates = []
        for plate_detection in plate_detections:
            px1, py1, px2, py2 = plate_detection.bbox
            plate_area = max(1.0, (px2 - px1) * (py2 - py1))
            intersection_width = max(0, min(vx2, px2) - max(vx1, px1))
            intersection_height = max(0, min(vy2, py2) - max(vy1, py1))
            containment = intersection_width * intersection_height / plate_area
            if containment >= 0.5:
                matching_plates.append(plate_detection)

        if matching_plates:
            best_plate = max(
                matching_plates,
                key=lambda detection: detection.confidence,
            )
            plate_crop = crop_for_bbox(frame, best_plate.bbox)
            return plate_reader.read(plate_crop)

    return None, 0.0


def _is_mock():
    return config.MOCK_MODE == "true" or (config.MOCK_MODE == "auto" and not os.path.exists(config.MODEL_WEIGHTS))


def _mock_video_source():
    """Returns a callable that yields synthetic frames, for demos without a camera."""
    state = {"t": 0}
    def _next():
        state["t"] += 1
        frame = np.full((480, 640, 3), 40, dtype=np.uint8)
        cv2.putText(frame, f"MOCK FEED frame {state['t']}", (20, 40),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.7, (150, 150, 150), 2)
        return frame
    return _next


def _read_frame(cap):
    if cap is None or not cap.isOpened():
        return None
    ok, frame = cap.read()
    return frame if ok else None


def _draw_debug(frame, detections):
    for d in detections:
        if d.cls_name in {"number", "number_plate", "license_plate"}:
            continue
        x1, y1, x2, y2 = [int(v) for v in d.bbox]
        color = (0, 165, 255) if d.cls_name in config.HAZARD_CLASSES else (219, 201, 59)
        cv2.rectangle(frame, (x1, y1), (x2, y2), color, 2)
        label = f"{d.cls_name} {d.confidence:.2f}" + (f" #{d.track_id}" if d.track_id else "")
        cv2.putText(frame, label, (x1, max(0, y1 - 6)), cv2.FONT_HERSHEY_SIMPLEX, 0.45, color, 1)


def run(camera_key, show_display, max_frames=0):
    source = config.CAMERAS.get(camera_key)
    if source is None:
        raise SystemExit(f"No source configured for camera '{camera_key}' — set URBANEYE_CAM_{camera_key.upper()}")

    mock_video = _mock_video_source() if _is_mock() and source in ("0", None) else None
    cap = None if mock_video is not None else cv2.VideoCapture(int(source) if str(source).isdigit() else source)

    detector = ObjectDetector()
    rules = EventRuleEngine()
    plates = PlateReader(mock=detector.mock)
    gps = GPSReader()
    bus = EventBus(config.BUS_ID, config.ROUTE_ID)
    sender = CloudSender()
    sender.flush_offline_queue_periodically()
    last_heartbeat = 0.0
    frames_processed = 0

    log.info("Starting URBANEYE edge loop | bus=%s camera=%s mock=%s", config.BUS_ID, camera_key, detector.mock)

    try:
        while max_frames <= 0 or frames_processed < max_frames:
            frame = mock_video() if mock_video else _read_frame(cap)
            if frame is None:
                log.info("End of stream / camera unavailable, stopping.")
                break
            frames_processed += 1

            detections = detector.infer(frame)
            events = rules.update(detections)
            lat, lon = gps.read()

            now = time.monotonic()
            if now - last_heartbeat >= 10:
                vehicle_count = sum(d.cls_name in config.VEHICLE_CLASSES for d in detections)
                sender.heartbeat(config.BUS_ID, config.ROUTE_ID, lat, lon, vehicle_count)
                last_heartbeat = now

            for ev in events:
                if not bus.should_send(ev.event_type, lat, lon):
                    continue

                plate, plate_conf = (None, 0.0)
                if ev.event_type in INCIDENT_EVENTS_NEEDING_PLATE:
                    plate, plate_conf = read_plate_for_event(
                        frame, ev, detections, plates
                    )

                thumb = None
                if ev.event_type in config.SEND_THUMBNAILS_FOR:
                    thumb = make_thumbnail_b64(frame, ev.bbox)

                payload = bus.build_payload(ev, lat, lon, plate=plate, plate_confidence=plate_conf, thumbnail_b64=thumb)
                sender.send(payload)
                log.info("EVENT %-24s conf=%.2f  bus=%s  t=%s", ev.event_type, ev.confidence,
                          config.BUS_ID, payload["timestamp"])

            if show_display and frame is not None:
                _draw_debug(frame, detections)
                cv2.imshow("URBANEYE edge (debug)", frame)
                if cv2.waitKey(1) & 0xFF == ord("q"):
                    break
            if mock_video is not None:
                time.sleep(0.05)
    finally:
        if cap is not None:
            cap.release()
        if show_display:
            cv2.destroyAllWindows()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--camera", default="front", choices=["front", "rear", "side", "cabin", "all"])
    parser.add_argument("--no-display", action="store_true", help="run headless (required on a real bus box)")
    parser.add_argument("--max-frames", type=int, default=0, help="stop after this many frames; 0 runs continuously")
    args = parser.parse_args()
    if args.camera == "all":
        configured = [key for key, source in config.CAMERAS.items() if source is not None]
        if not configured:
            raise SystemExit("No cameras configured")
        with ThreadPoolExecutor(max_workers=len(configured)) as pool:
            futures = [pool.submit(run, key, show_display=not args.no_display, max_frames=args.max_frames) for key in configured]
            for future in futures:
                future.result()
    else:
        run(args.camera, show_display=not args.no_display, max_frames=args.max_frames)
