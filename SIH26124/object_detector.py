"""
Wraps Ultralytics YOLO for detection + tracking, with a mock fallback so
the pipeline runs without trained weights or a real camera attached.
"""
import random
import logging
from pathlib import Path

import numpy as np

import config

log = logging.getLogger("urbaneye.detector")

MODEL_CLASS_ALIASES = {
    "person": "pedestrian",
    "pedestrian": "pedestrian",
    "car": "vehicle_car",
    "vehicle_car": "vehicle_car",
    "truck": "vehicle_truck",
    "vehicle_truck": "vehicle_truck",
    "bus": "vehicle_bus",
    "vehicle_bus": "vehicle_bus",
    "bicycle": "vehicle_two_wheeler",
    "bike": "vehicle_two_wheeler",
    "motorbike": "vehicle_two_wheeler",
    "motorcycle": "vehicle_two_wheeler",
    "vehicle_bike": "vehicle_two_wheeler",
    "vehicle_two_wheeler": "vehicle_two_wheeler",
    "pothole": "pothole",
    "manhole": "manhole_open",
    "open-manhole": "manhole_open",
    "open-manholes": "manhole_open",
    "fall": "fall_people",
    "fall-people": "fall_people",
    "number-plate": "number_plate",
    "license-plate": "number_plate",
    "accident": "accident",
    "crash": "accident",
    "collision": "accident",
}

AUXILIARY_MODEL_CLASSES = {
    "pothole": {"pothole"},
    "manhole": {"manhole_open"},
    "fall_people": {"fall_people"},
    "number_plate": {"number_plate"},
    "accident": {"accident"},
}


def _model_weights_path():
    path = Path(config.MODEL_WEIGHTS).expanduser()
    if not path.is_absolute():
        path = Path(__file__).resolve().parent / path
    return path


class Detection:
    __slots__ = ("cls_name", "confidence", "bbox", "track_id")

    def __init__(self, cls_name, confidence, bbox, track_id=None):
        self.cls_name = cls_name
        self.confidence = confidence
        self.bbox = bbox            # (x1, y1, x2, y2) in pixels
        self.track_id = track_id    # stable id across frames for vehicles/pedestrians

    def __repr__(self):
        return f"<Det {self.cls_name} conf={self.confidence:.2f} id={self.track_id}>"


def _mock_mode_active():
    mode = config.MOCK_MODE.lower()
    if mode == "true":
        return True
    if mode == "false":
        return False
    if mode == "auto":
        return not _model_weights_path().is_file()
    raise ValueError(
        "URBANEYE_MOCK_MODE must be 'true', 'false', or 'auto'; "
        f"received {config.MOCK_MODE!r}"
    )


class ObjectDetector:
    """
    Usage:
        det = ObjectDetector()
        detections = det.infer(frame)   # frame: HxWx3 numpy array (BGR)
    """

    def __init__(self):
        self.mock = _mock_mode_active()
        self.disabled = False
        if self.mock:
            weights_path = _model_weights_path()
            log.warning(
                "Running in MOCK detection mode (no trained weights found at %s). "
                "Detections are synthetic — replace with real weights for production.",
                weights_path,
            )
            self._mock_track_ids = {}
            self._next_track_id = 1
            self._frame_count = 0
        else:
            weights_path = _model_weights_path()
            if not weights_path.is_file():
                log.error(
                    "Real detection is disabled because model weights were "
                    "not found at %s. Set URBANEYE_MODEL_WEIGHTS to a trained "
                    "checkpoint. No synthetic boxes will be generated.",
                    weights_path,
                )
                self.disabled = True
            else:
                from ultralytics import YOLO
                self.model = YOLO(str(weights_path))
                log.info("Loaded model weights from %s", weights_path)
                self.auxiliary_models = []
                for role, configured_path in config.ADDITIONAL_MODEL_WEIGHTS.items():
                    auxiliary_path = Path(configured_path).expanduser()
                    if not auxiliary_path.is_absolute():
                        auxiliary_path = (
                            Path(__file__).resolve().parent / auxiliary_path
                        )
                    if not auxiliary_path.is_file():
                        log.warning(
                            "%s detections are unavailable: model weights "
                            "were not found at %s",
                            role,
                            auxiliary_path,
                        )
                        continue
                    self.auxiliary_models.append(
                        (role, YOLO(str(auxiliary_path)))
                    )
                    log.info(
                        "Loaded %s detection weights from %s",
                        role,
                        auxiliary_path,
                    )

    # ------------------------------------------------------------------
    def infer(self, frame):
        if self.disabled:
            return []
        if self.mock:
            return self._mock_infer(frame)
        return self._real_infer(frame)

    # ------------------------------------------------------------------
    def _real_infer(self, frame):
        results = self.model.track(
            frame,
            persist=True,
            tracker=config.TRACKER_CONFIG,
            conf=config.DETECTION_CONFIDENCE_THRESHOLD,
            verbose=False,
        )
        detections = []
        if not results:
            return detections
        r = results[0]
        if r.boxes is None:
            r = None
        if r is not None:
            detections.extend(self._convert_result(r, self.model.names))

        for role, auxiliary_model in getattr(self, "auxiliary_models", []):
            auxiliary_results = auxiliary_model.predict(
                frame,
                conf=config.DETECTION_CONFIDENCE_THRESHOLD,
                imgsz=640,
                verbose=False,
            )
            if auxiliary_results and auxiliary_results[0].boxes is not None:
                detections.extend(
                    self._convert_result(
                        auxiliary_results[0],
                        auxiliary_model.names,
                        allowed_classes=AUXILIARY_MODEL_CLASSES[role],
                    )
                )

        detections = self._suppress_duplicate_hazards(detections)
        return detections

    @staticmethod
    def _convert_result(result, model_names, allowed_classes=None):
        detections = []
        for box in result.boxes:
            cls_idx = int(box.cls[0])
            model_label = (
                model_names.get(cls_idx, f"class_{cls_idx}")
                if isinstance(model_names, dict)
                else model_names[cls_idx]
            )
            normalized_label = str(model_label).lower().replace("_", "-")
            cls_name = MODEL_CLASS_ALIASES.get(normalized_label)
            if cls_name is None and str(model_label).lower() in config.CLASS_NAMES:
                cls_name = str(model_label).lower()
            if cls_name is None:
                continue
            if allowed_classes is not None and cls_name not in allowed_classes:
                continue
            conf = float(box.conf[0])
            x1, y1, x2, y2 = [float(v) for v in box.xyxy[0]]
            track_id = (
                int(box.id[0])
                if allowed_classes is None and box.id is not None
                else None
            )
            detections.append(
                Detection(cls_name, conf, (x1, y1, x2, y2), track_id)
            )
        return detections

    @staticmethod
    def _suppress_duplicate_hazards(detections):
        """Drop overlapping duplicate hazard boxes from specialized models."""
        kept = []
        for detection in sorted(
            detections,
            key=lambda item: item.confidence,
            reverse=True,
        ):
            if detection.cls_name in config.HAZARD_CLASSES:
                x1, y1, x2, y2 = detection.bbox
                area = max(0, x2 - x1) * max(0, y2 - y1)
                duplicate = False
                for existing in kept:
                    if existing.cls_name != detection.cls_name:
                        continue
                    ax1, ay1, ax2, ay2 = existing.bbox
                    ix1, iy1 = max(x1, ax1), max(y1, ay1)
                    ix2, iy2 = min(x2, ax2), min(y2, ay2)
                    intersection = max(0, ix2 - ix1) * max(0, iy2 - iy1)
                    existing_area = max(0, ax2 - ax1) * max(0, ay2 - ay1)
                    union = area + existing_area - intersection
                    if union > 0 and intersection / union >= 0.6:
                        duplicate = True
                        break
                if duplicate:
                    continue
            kept.append(detection)
        return kept

    # ------------------------------------------------------------------
    def _mock_infer(self, frame):
        """
        Fabricates a believable stream of detections so downstream code
        (tracking continuity, event rules, dedup, sending) can be exercised
        end-to-end. Not a substitute for a trained model.
        """
        h, w = frame.shape[:2] if frame is not None else (720, 1280)
        self._frame_count += 1
        detections = []

        # a couple of "vehicles" that persist across frames with drifting
        # positions, so speed/weaving heuristics have something to chew on
        for lane_x in (int(w * 0.35), int(w * 0.62)):
            key = f"veh_{lane_x}"
            if key not in self._mock_track_ids:
                self._mock_track_ids[key] = self._next_track_id
                self._next_track_id += 1
            jitter = int(20 * np.sin(self._frame_count / 5 + lane_x))
            x1 = lane_x + jitter
            y1 = int(h * 0.55)
            detections.append(Detection(
                random.choice(["vehicle_car", "vehicle_two_wheeler"]),
                random.uniform(0.75, 0.98),
                (x1, y1, x1 + 90, y1 + 60),
                track_id=self._mock_track_ids[key],
            ))

        # occasionally emit a road hazard
        if self._frame_count % 45 == 0:
            hazard = random.choice(list(config.HAZARD_CLASSES))
            x1, y1 = random.randint(0, w - 120), random.randint(int(h * 0.6), h - 60)
            detections.append(Detection(hazard, random.uniform(0.7, 0.97), (x1, y1, x1 + 110, y1 + 50)))

        if self._frame_count % 90 == 0:
            detections.append(Detection(
                "pedestrian", random.uniform(0.72, 0.91),
                (int(w * 0.39), int(h * 0.58), int(w * 0.43), int(h * 0.78)),
            ))

        return detections
