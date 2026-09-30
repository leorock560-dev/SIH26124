"""
Sits between the rule engine and the network sender. Two jobs:

1. Dedup/cooldown — the same pothole shouldn't generate a fresh alert every
   frame as the bus drives past it for two seconds. We collapse repeats of
   the same event type within a rough location+time window.

2. Payload shaping — this is where "take only the essential things"
   actually happens: raw detections/tracks never leave this module. Only a
   small structured record does.
"""
import time
import logging

import config

log = logging.getLogger("urbaneye.event_bus")


class EventBus:
    def __init__(self, bus_id, route_id):
        self.bus_id = bus_id
        self.route_id = route_id
        self._last_sent = {}  # (event_type, location_bucket) -> timestamp

    def _location_bucket(self, lat, lon):
        # ~11m grid at the equator; coarse enough to dedup "the same pothole"
        # without needing exact repeat coordinates.
        return (round(lat, 4), round(lon, 4))

    def _cooldown_for(self, event_type):
        return config.EVENT_COOLDOWN_SECONDS.get(event_type, config.EVENT_COOLDOWN_SECONDS["default"])

    def should_send(self, event_type, lat, lon, now=None):
        now = now or time.time()
        key = (event_type, self._location_bucket(lat, lon))
        last = self._last_sent.get(key)
        if last is not None and now - last < self._cooldown_for(event_type):
            return False
        self._last_sent[key] = now
        return True

    def build_payload(self, raw_event, lat, lon, plate=None, plate_confidence=None, thumbnail_b64=None):
        """
        Returns the exact minimal JSON body sent to the cloud API.
        Matches server/schemas.py: EventIn
        """
        payload = {
            "bus_id": self.bus_id,
            "route_id": self.route_id,
            "event_type": raw_event.event_type,
            "confidence": round(float(raw_event.confidence), 3),
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime(raw_event.ts)),
            "lat": lat,
            "lon": lon,
        }
        if plate:
            payload["plate_number"] = plate
            payload["plate_confidence"] = round(float(plate_confidence or 0), 3)
        if thumbnail_b64:
            payload["thumbnail_b64"] = thumbnail_b64
        if raw_event.extra:
            # small, JSON-serialisable extras only (counts, ids) — never raw frames
            payload["meta"] = raw_event.extra
        return payload
