
import argparse
import base64
import logging
import os
import queue
import threading
import tkinter as tk
from pathlib import Path

import cv2
import numpy as np
from flask import Flask, Response, render_template_string, stream_with_context
from flask_socketio import SocketIO

import config
from object_detector import ObjectDetector
from event_rules import EventRuleEngine
from plate_ocr import PlateReader
from event_bus import EventBus
from gps import GPSReader
from sender import CloudSender

# --------------------------------------------------
# CONFIGURATION
# --------------------------------------------------

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s"
)
log = logging.getLogger("urbaneye.main")

PROJECT_DIR = Path(__file__).resolve().parent

INCIDENT_EVENTS_NEEDING_PLATE = {
    "hit_and_run", "rash_driving", "unsafe_driving", "accident"
}

FRAME_WIDTH = 960
JPEG_QUALITY = 75

app = Flask(__name__)
app.config["SECRET_KEY"] = os.getenv(
    "URBANEYE_SECRET_KEY", "urbaneye-dev"
)
socketio = SocketIO(
    app,
    cors_allowed_origins="*",
    async_mode="threading"
)

# Latest processed frame, shared with the Flask feed.
frame_condition = threading.Condition()
latest_jpeg = None
frame_counter = 0
stop_event = threading.Event()


# --------------------------------------------------
# VIDEO AND IMAGE HELPERS
# --------------------------------------------------

def make_thumbnail_b64(frame, bbox=None):
    if frame is None:
        return None

    img = frame

    if bbox:
        x1, y1, x2, y2 = [int(v) for v in bbox]
        x1 = max(0, x1 - 20)
        y1 = max(0, y1 - 20)
        x2 = min(frame.shape[1], x2 + 20)
        y2 = min(frame.shape[0], y2 + 20)

        if x2 > x1 and y2 > y1:
            img = frame[y1:y2, x1:x2]

    h, w = img.shape[:2]
    if w > config.THUMBNAIL_MAX_WIDTH:
        scale = config.THUMBNAIL_MAX_WIDTH / w
        img = cv2.resize(
            img,
            (config.THUMBNAIL_MAX_WIDTH, int(h * scale))
        )

    ok, buf = cv2.imencode(
        ".jpg",
        img,
        [cv2.IMWRITE_JPEG_QUALITY, config.THUMBNAIL_JPEG_QUALITY]
    )

    if not ok:
        return None

    return base64.b64encode(buf).decode("ascii")


def crop_for_bbox(frame, bbox):
    if frame is None or bbox is None:
        return None

    x1, y1, x2, y2 = [int(v) for v in bbox]
    x1 = max(0, x1)
    y1 = max(0, y1)
    x2 = min(frame.shape[1], x2)
    y2 = min(frame.shape[0], y2)

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


def resize_frame(frame):
    h, w = frame.shape[:2]

    if w <= FRAME_WIDTH:
        return frame

    new_h = int(h * FRAME_WIDTH / w)
    return cv2.resize(frame, (FRAME_WIDTH, new_h))


def resolve_video_source(source):
    """Resolve relative video paths from the current or nested project folder."""
    source_text = str(source)
    if source_text.isdigit():
        return int(source_text)

    path = Path(source_text).expanduser()
    if path.is_absolute():
        return str(path)

    candidates = (
        Path.cwd() / path,
        PROJECT_DIR / path,
        PROJECT_DIR / "SIH26124" / path,
    )
    for candidate in candidates:
        if candidate.is_file():
            return str(candidate.resolve())

    return str((Path.cwd() / path).resolve())


def draw_debug(frame, detections):
    # These detections remain available to the rules engine,
    # but their bounding boxes are hidden from the display.
    hidden_classes = {"number", "number_plate", "license_plate"}

    for d in detections:
        if d.cls_name.lower() in hidden_classes:
            continue

        x1, y1, x2, y2 = [int(v) for v in d.bbox]

        color = (
            (0, 165, 255)
            if d.cls_name in config.HAZARD_CLASSES
            else (0, 200, 0)
        )

        cv2.rectangle(
            frame, (x1, y1), (x2, y2), color, 2
        )

        label = f"{d.cls_name} {d.confidence:.2f}"
        if d.track_id:
            label += f" #{d.track_id}"

        cv2.putText(
            frame,
            label,
            (x1, max(20, y1 - 6)),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.5,
            color,
            2
        )


# --------------------------------------------------
# MOCK VIDEO FOR TESTING
# --------------------------------------------------

def mock_video_source():
    state = {"t": 0}

    def next_frame():
        state["t"] += 1
        frame = np.full((480, 640, 3), 40, dtype=np.uint8)

        cv2.putText(
            frame,
            f"MOCK FEED frame {state['t']}",
            (20, 40),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.7,
            (150, 150, 150),
            2
        )
        return frame

    return next_frame


def is_mock(detector):
    return detector.mock


def start_cloud_sender_worker(sender):
    pending_events = queue.Queue()

    def send_pending_events():
        while True:
            payload = pending_events.get()
            try:
                sender.send(payload)
            except Exception:
                log.exception(
                    "Cloud sender worker failed for event %s",
                    payload.get("event_type", "unknown")
                )
            finally:
                pending_events.task_done()

    threading.Thread(
        target=send_pending_events,
        name="cloud-event-sender",
        daemon=True
    ).start()
    return pending_events


# --------------------------------------------------
# FLASK FRONTEND
# --------------------------------------------------

@app.route("/")
def index():
    return render_template_string("""
    <!DOCTYPE html>
    <html lang="en">
    <head>
      <meta charset="UTF-8">
      <meta name="viewport"
            content="width=device-width, initial-scale=1">
      <title>UrbanEye Monitoring</title>
      <style>
        body {
          margin: 0;
          padding: 24px;
          background: #101820;
          color: #f4f4f4;
          font-family: Arial, sans-serif;
        }
        main { max-width: 1100px; margin: auto; }
        h1 { color: #f5c542; }
        .panel {
          background: #1b2733;
          border-radius: 10px;
          padding: 18px;
          margin-top: 18px;
        }
        img {
          display: block;
          width: 100%;
          background: #080d12;
          border-radius: 8px;
        }
        .alert {
          background: #7f1d1d;
          padding: 12px;
          margin: 10px 0;
          border-radius: 6px;
        }
        #status { color: #7dd3fc; }
      </style>
    </head>
    <body>
      <main>
        <h1>UrbanEye Live Monitoring</h1>
        <p id="status">Waiting for video...</p>

        <div class="panel">
          <h2>Live Detection</h2>
          <img src="/video_feed" alt="Live annotated video">
        </div>

        <div class="panel">
          <h2>Incident Alerts</h2>
          <div id="alerts"></div>
        </div>
      </main>

      <script src="https://cdn.socket.io/4.8.1/socket.io.min.js"></script>
      <script>
        const socket = io();
        const status = document.getElementById("status");
        const alerts = document.getElementById("alerts");

        socket.on("connect", () => {
          status.textContent = "Connected to UrbanEye";
        });

        socket.on("disconnect", () => {
          status.textContent = "Disconnected from server";
        });

        socket.on("video_status", data => {
          status.textContent = data.message;
        });

        socket.on("incident", data => {
          const div = document.createElement("div");
          div.className = "alert";

          const title = document.createElement("strong");
          title.textContent = data.event_type || "Incident";
          div.appendChild(title);

          const plate = document.createElement("p");
          plate.textContent =
            "Plate: " + (data.plate || "Not identified");
          div.appendChild(plate);

          const time = document.createElement("p");
          time.textContent = data.timestamp || "";
          div.appendChild(time);

          alerts.prepend(div);
        });

        socket.on("video_error", data => {
          status.textContent = "Error: " + data.message;
        });
      </script>
    </body>
    </html>
    """)


@app.route("/video_feed")
def video_feed():
    def generate():
        last_sent = -1

        while not stop_event.is_set():
            with frame_condition:
                frame_condition.wait_for(
                    lambda: (
                        latest_jpeg is not None
                        and frame_counter != last_sent
                    ) or stop_event.is_set(),
                    timeout=5
                )

                if stop_event.is_set():
                    break

                if latest_jpeg is None or frame_counter == last_sent:
                    continue

                jpeg = latest_jpeg
                last_sent = frame_counter

            yield (
                b"--frame\r\n"
                b"Content-Type: image/jpeg\r\n\r\n"
                + jpeg
                + b"\r\n"
            )

    return Response(
        stream_with_context(generate()),
        mimetype="multipart/x-mixed-replace; boundary=frame"
    )


# --------------------------------------------------
# MAIN DETECTION LOOP
# --------------------------------------------------

def run(camera_key, show_display=True, video_source=None):
    global latest_jpeg, frame_counter

    source = (
        video_source
        if video_source is not None
        else config.CAMERAS.get(camera_key)
    )

    if source is None:
        raise SystemExit(
            f"No source configured for camera '{camera_key}'. "
            f"Set URBANEYE_CAM_{camera_key.upper()}."
        )

    source = resolve_video_source(source)

    detector = ObjectDetector()
    rules = EventRuleEngine()
    plates = PlateReader(mock=detector.mock)
    gps = GPSReader()
    bus = EventBus(config.BUS_ID, config.ROUTE_ID)
    sender = CloudSender()
    pending_cloud_events = start_cloud_sender_worker(sender)

    sender.flush_offline_queue_periodically()

    mock_video = (
        mock_video_source()
        if is_mock(detector) and str(source) in ("0", "None")
        else None
    )

    cap = None
    if mock_video is None:
        cap = cv2.VideoCapture(
            int(source) if str(source).isdigit() else source
        )

        if not cap.isOpened():
            raise RuntimeError(
                f"Unable to open camera/video source: {source}"
            )

    log.info(
        "Starting UrbanEye | bus=%s camera=%s mock=%s",
        config.BUS_ID, camera_key, detector.mock
    )

    display_active = show_display
    display_root = None
    display_label = None
    if display_active:
        try:
            display_root = tk.Tk()
            display_root.title("UrbanEye - Live Detection")
            display_root.geometry("960x600")
            display_label = tk.Label(display_root, bg="#101820")
            display_label.pack(fill=tk.BOTH, expand=True)

            def close_display():
                nonlocal display_active
                display_active = False
                display_root.destroy()

            display_root.protocol("WM_DELETE_WINDOW", close_display)
            display_root.bind(
                "<KeyPress-q>",
                lambda *_: stop_event.set()
            )
            log.info("Showing local video window; press q to stop.")
        except tk.TclError as exc:
            log.warning(
                "Local display is unavailable; continuing without a window: %s",
                exc
            )
            display_active = False

    socketio.emit("video_status", {
        "message": "Live detection started"
    })

    try:
        while not stop_event.is_set():
            if mock_video is not None:
                frame = mock_video()
            else:
                ok, frame = cap.read()
                if not ok:
                    log.info("End of video or camera stream.")
                    break

            frame = resize_frame(frame)

            # Run detection and event rules.
            detections = detector.infer(frame)
            events = rules.update(
                detections,
                frame_shape=frame.shape
            )

            lat, lon = gps.read()

            # Handle generated incidents.
            for ev in events:
                if not bus.should_send(ev.event_type, lat, lon):
                    continue

                plate, plate_conf = None, 0.0

                if ev.event_type in INCIDENT_EVENTS_NEEDING_PLATE:
                    plate, plate_conf = read_plate_for_event(
                        frame,
                        ev,
                        detections,
                        plates,
                    )

                thumb = None
                if ev.event_type in config.SEND_THUMBNAILS_FOR:
                    thumb = make_thumbnail_b64(frame, ev.bbox)

                payload = bus.build_payload(
                    ev,
                    lat,
                    lon,
                    plate=plate,
                    plate_confidence=plate_conf,
                    thumbnail_b64=thumb
                )

                socketio.emit("incident", payload)
                pending_cloud_events.put(payload)

                log.info(
                    "EVENT %-24s conf=%.2f bus=%s",
                    ev.event_type,
                    ev.confidence,
                    config.BUS_ID
                )

            display_frame = frame.copy()
            draw_debug(display_frame, detections)

            if display_active:
                try:
                    ok, png_buffer = cv2.imencode(".png", display_frame)
                    if not ok:
                        raise RuntimeError(
                            "OpenCV could not encode the frame for display"
                        )

                    photo = tk.PhotoImage(
                        data=base64.b64encode(png_buffer).decode("ascii")
                    )
                    display_label.configure(image=photo)
                    display_label.image = photo
                    display_root.update_idletasks()
                    display_root.update()
                except (tk.TclError, RuntimeError) as exc:
                    log.warning(
                        "Local display failed; continuing without a window: %s",
                        exc
                    )
                    display_active = False

            # Publish the most recent frame for Flask.
            ok, buffer = cv2.imencode(
                ".jpg",
                display_frame,
                [cv2.IMWRITE_JPEG_QUALITY, JPEG_QUALITY]
            )

            if ok:
                with frame_condition:
                    latest_jpeg = buffer.tobytes()
                    frame_counter += 1
                    frame_condition.notify_all()

    except KeyboardInterrupt:
        log.info("Stopping on keyboard interrupt.")

    except Exception as exc:
        log.exception("Detection loop failed: %s", exc)
        socketio.emit("video_error", {
            "message": str(exc)
        })

    finally:
        stop_event.set()
        pending_cloud_events.join()

        with frame_condition:
            frame_condition.notify_all()

        if cap is not None:
            cap.release()

        if display_root is not None:
            try:
                display_root.destroy()
            except tk.TclError as exc:
                log.debug("Local display cleanup failed: %s", exc)

        log.info("UrbanEye stopped.")


# --------------------------------------------------
# ENTRYPOINT
# --------------------------------------------------

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--camera",
        default="front",
        choices=["front", "rear", "side", "cabin"]
    )
    parser.add_argument(
        "--source",
        default=None,
        help="Override configured camera with a video file or camera index"
    )
    display_options = parser.add_mutually_exclusive_group()
    display_options.add_argument(
        "--show",
        dest="show_display",
        action="store_true",
        help="Show the live processed video in a local window"
    )
    display_options.add_argument(
        "--no-display",
        dest="show_display",
        action="store_false",
        help="Disable the local OpenCV window"
    )
    parser.set_defaults(show_display=False)
    parser.add_argument(
        "--server",
        action="store_true",
        help="Start the browser dashboard server"
    )
    args = parser.parse_args()

    if args.server:
        # Start Flask in a background thread.
        def start_flask():
            socketio.run(
                app,
                host="127.0.0.1",
                port=5000,
                debug=False,
                use_reloader=False
            )

        server = threading.Thread(
            target=start_flask,
            daemon=True
        )
        server.start()
        log.info("Frontend: http://127.0.0.1:5000")

    run(
        camera_key=args.camera,
        show_display=args.show_display,
        video_source=args.source
    )