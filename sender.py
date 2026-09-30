"""
Delivers event payloads to the central platform. Handles the case every
fleet deployment eventually hits — the bus drives through a dead zone —
by queueing to disk and flushing when connectivity returns.
"""
import json
import time
import logging
import os
import threading

import requests

import config

log = logging.getLogger("urbaneye.sender")


class CloudSender:
    def __init__(self):
        self._lock = threading.Lock()
        self._session = requests.Session()
        self._session.headers.update({
            "Authorization": f"Bearer {config.CLOUD_API_KEY}",
            "Content-Type": "application/json",
        })

    def send(self, payload):
        """Best-effort send; queues to disk on failure instead of dropping data."""
        for attempt, backoff in enumerate([0] + config.SEND_RETRY_BACKOFF_SECONDS):
            if backoff:
                time.sleep(backoff)
            try:
                resp = self._session.post(
                    f"{config.CLOUD_API_URL}/events", data=json.dumps(payload), timeout=5
                )
                if resp.status_code in (200, 201):
                    log.info("Sent event %s (%s)", payload["event_type"], payload["timestamp"])
                    self._flush_offline_queue()
                    return True
                log.warning("Cloud rejected event (status %s): %s", resp.status_code, resp.text[:200])
            except requests.RequestException as e:
                log.warning("Send attempt %d failed: %s", attempt + 1, e)
        self._queue_offline(payload)
        return False

    # ------------------------------------------------------------------
    def _queue_offline(self, payload):
        with self._lock:
            with open(config.OFFLINE_QUEUE_PATH, "a") as f:
                f.write(json.dumps(payload) + "\n")
        log.info("Queued event offline (%s pending)", self._offline_count())

    def _offline_count(self):
        if not os.path.exists(config.OFFLINE_QUEUE_PATH):
            return 0
        with open(config.OFFLINE_QUEUE_PATH) as f:
            return sum(1 for _ in f)

    def _flush_offline_queue(self):
        if not os.path.exists(config.OFFLINE_QUEUE_PATH):
            return
        with self._lock:
            with open(config.OFFLINE_QUEUE_PATH) as f:
                lines = f.readlines()
            os.remove(config.OFFLINE_QUEUE_PATH)
        sent, failed = 0, []
        for line in lines:
            try:
                payload = json.loads(line)
                resp = self._session.post(f"{config.CLOUD_API_URL}/events", data=json.dumps(payload), timeout=5)
                if resp.status_code in (200, 201):
                    sent += 1
                else:
                    failed.append(line)
            except requests.RequestException:
                failed.append(line)
        if failed:
            with open(config.OFFLINE_QUEUE_PATH, "a") as f:
                f.writelines(failed)
        if sent:
            log.info("Flushed %d queued events from offline backlog", sent)

    def flush_offline_queue_periodically(self, interval_seconds=30):
        """Call once in a background thread from main.py."""
        def loop():
            while True:
                time.sleep(interval_seconds)
                self._flush_offline_queue()
        threading.Thread(target=loop, daemon=True).start()
