# URBANEYE: SIH 26124 Prototype

A combined concept prototype for **AI-Powered Mobile Urban Intelligence Platform Using Public Transport Fleet** (Bharat Electronics Limited). It combines the officer portal, GIS dashboard, central event API, SQLite data store, and bus-edge simulation in one project.

This is a hackathon prototype, not an official government service or a validated road-safety system. The database seed includes illustrative, GPS-tagged bus/event records around reference cities in all 36 States/UTs, plus detailed Bengaluru examples. Mock edge detections are synthetic; real road-hazard detection requires trained weights and camera validation.

## Quick Start (Windows PowerShell)

Requires Python 3.10 or newer.

From this directory:

```powershell
py -3 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements-test.txt
$env:URBANEYE_SESSION_SECRET = [guid]::NewGuid().ToString('N')
$env:URBANEYE_API_KEY = 'demo-key-change-me'
python seed.py
python -m uvicorn app:app --reload --host 127.0.0.1 --port 8000
```

Open <http://127.0.0.1:8000>. Create an officer account from the portal, then sign in. The seeded sample fleet, events, GPS route samples, and vehicle counts will populate the dashboard. API documentation is at <http://127.0.0.1:8000/docs>.

The default database is `urbaneye.db` (SQLite). The server refuses to start without `URBANEYE_SESSION_SECRET`, and edge ingestion is disabled until `URBANEYE_API_KEY` is set. Both maps offer Default (OpenStreetMap), Satellite (Esri imagery with a city/road-label overlay), and Traffic (street map plus event heat overlay); map tiles need an internet connection but no map API key. To connect PostgreSQL instead, set `DATABASE_URL` before starting the server and install a PostgreSQL driver such as `psycopg[binary]`.

## Edge Simulation (Optional)

For the lightweight synthetic edge-to-cloud demo, install only the mock-camera dependencies in a second PowerShell terminal:

```powershell
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements-edge-mock.txt
$env:URBANEYE_MOCK_MODE = 'true'
$env:URBANEYE_CLOUD_URL = 'http://127.0.0.1:8000/api'
$env:URBANEYE_API_KEY = 'demo-key-change-me'
python main.py --camera front --no-display --max-frames 240
```

Mock mode generates synthetic frames and detections, sends event packets, and posts GPS/vehicle-count heartbeats every ten seconds. It does **not** prove model accuracy. Omit `--max-frames` to keep the simulator running. `--camera all` runs every configured camera feed; set `URBANEYE_CAM_REAR`, `URBANEYE_CAM_SIDE`, and `URBANEYE_CAM_CABIN` to real device indices, RTSP URLs, or video paths first.

For a real camera/model pipeline, install the larger optional set with `python -m pip install -r requirements-edge.txt`.

For a real camera, set `URBANEYE_MODEL_WEIGHTS` to a model trained with the class order in `config.py`, configure `URBANEYE_GPS_SOURCE` and the GPS port, and unset mock mode. Pixel-space behavior thresholds need camera calibration before operational use. The current OCR path also needs suitable plate crops; end-to-end incident attribution is not validated.

## Project Flow

```text
bus cameras -> edge detector/tracker -> event rules -> compact event + GPS
            -> authenticated API -> SQLite -> officer dashboard and analytics
```

Raw video is processed locally. Event payloads may include a small incident thumbnail, but no continuous video stream is uploaded. Edge event requests and heartbeats use `Authorization: Bearer <URBANEYE_API_KEY>`; officer accounts use signed server sessions and salted password hashes.

## SIH Requirement Coverage

| Problem-statement requirement | Prototype implementation | Important limitation |
|---|---|---|
| Multi-camera bus sensing | Front/rear/side/cabin camera configuration; `--camera all` runner | Multiple real feeds and synchronization have not been hardware-tested |
| Road defects and hazards | YOLO class configuration and event pipeline for potholes, damaged roads, dividers, signals, waterlogging, manholes, construction | No trained weights are included; mock detections are synthetic |
| Vehicle density and bottlenecks | Vehicle detections counted in heartbeats; sustained-count congestion rule; density chart and traffic heat layer | Density is based on edge samples; heat points are reported traffic events, not a citywide calibrated traffic model |
| Vulnerable pedestrian situations | Pedestrian/vehicle pixel-proximity alert for officer review | A heuristic only; it does not classify school children, crossing intent, or collision probability |
| Rash driving, accidents, hit-and-run, plate evidence | Tracking heuristics, incident event payloads, optional OCR and thumbnails | Pixel thresholds and OCR need trained data, camera calibration, and validation |
| Timestamp and GPS evidence | Event timestamps, GPS event coordinates, periodic bus heartbeats | Mock GPS follows a synthetic path; serial GPS needs hardware |
| Central fleet GIS and road health | Session-protected event/bus APIs; Leaflet map, alerts, defect list and fleet status; all State/UT choices and OpenStreetMap place lookup zoom/filter GPS records | Map/geocoder need internet; seeded locations are illustrative reference-city samples, and filtering uses geocoder bounds rather than official jurisdiction polygons |
| Congestion heat maps | Live layer weighted from recent traffic events | Proxy visualization, not an independently measured traffic surface |
| Origin-destination patterns | First and latest GPS heartbeat per bus over 24 hours | Observed bus endpoints only; not passenger OD inference |
| Route delay estimates | Route disruption-event counts shown as a proxy | GTFS schedules and actual arrival telemetry are not integrated |

## Useful Commands

```powershell
python -m unittest test_api -v
python seed.py
```

`requirements.txt` contains the lightweight server dependencies. `requirements-edge.txt` adds the heavier OpenCV, Ultralytics, EasyOCR, GPS, and NumPy stack. `requirements-test.txt` adds the Starlette test-client dependency.

## Deployment Notes

The default session secret and API key are for local demonstration only. Set long, unique values outside local development, set `URBANEYE_HTTPS_ONLY=true` behind TLS, restrict officer registration with `URBANEYE_REGISTRATION_CODE`, and replace the shared edge API key with per-device credentials before deployment. Add rate limiting, audit logging, database migrations/backups, jurisdiction boundaries, and security review before any real authority or fleet use.
