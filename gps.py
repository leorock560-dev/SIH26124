"""
GPS source. Real deployments read NMEA sentences off a serial GPS module;
for development/demo, mock mode synthesizes a slowly-moving position so
events carry plausible coordinates without hardware attached.
"""
import time
import math
import logging

import config

log = logging.getLogger("urbaneye.gps")


class GPSReader:
    def __init__(self):
        self.mode = config.GPS_SOURCE
        self._t0 = time.time()
        if self.mode == "serial":
            import serial  # pyserial
            self._ser = serial.Serial(config.GPS_SERIAL_PORT, baudrate=9600, timeout=1)

    def read(self):
        """Returns (lat, lon) as floats."""
        if self.mode == "serial":
            return self._read_serial()
        return self._read_mock()

    def _read_serial(self):
        try:
            import pynmea2
            line = self._ser.readline().decode("ascii", errors="ignore").strip()
            if line.startswith("$GPGGA") or line.startswith("$GPRMC"):
                msg = pynmea2.parse(line)
                return float(msg.latitude), float(msg.longitude)
        except Exception as e:
            log.warning("GPS read failed (%s), falling back to last known / mock", e)
        return self._read_mock()

    def _read_mock(self):
        # slow circular drift around the configured start point, ~ a bus
        # looping its route, so successive events don't all land on one dot
        elapsed = time.time() - self._t0
        lat0, lon0 = config.GPS_MOCK_START
        radius = 0.01
        lat = lat0 + radius * math.sin(elapsed / 40)
        lon = lon0 + radius * math.cos(elapsed / 55)
        return round(lat, 6), round(lon, 6)
