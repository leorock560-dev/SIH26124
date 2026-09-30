/* ============================================================
   URBANEYE — live API client.
   If urbaneye-backend's server (FastAPI) is running, this replaces the
   mock arrays in data.js with real data. If it's not reachable (e.g.
   you're just opening the static demo), the mock data already loaded
   from data.js is left untouched — the dashboard works either way.
   ============================================================ */

const API_BASE = window.URBANEYE_API_BASE || "/api";
const API_TIMEOUT_MS = 4000;

function fetchWithTimeout(url, ms){
  const controller = new AbortController();
  const id = setTimeout(() => controller.abort(), ms);
  return fetch(url, { signal: controller.signal, credentials: 'same-origin' }).finally(() => clearTimeout(id));
}

function mapEventToAlert(ev){
  return {
    id: `A-${ev.id}`,
    type: ev.event_type.replace(/_/g, " ").replace(/\b\w/g, c => c.toUpperCase()),
    category: ev.category,
    severity: ev.severity,
    route: ev.route_id || "—",
    lat: ev.lat, lng: ev.lon,
    confidence: ev.confidence,
    ts: ev.timestamp,
    plate: ev.plate_number || undefined,
    plateConfidence: ev.plate_confidence,
    region: ev.meta?.sample_region,
    note: ev.meta ? JSON.stringify(ev.meta) : "",
    status: undefined,
  };
}

function mapBus(b){
  const sampleMatch = /^DEMO-(\d+)-01$/.exec(b.bus_id);
  const sampleRegion = sampleMatch && typeof STATE_UTS !== 'undefined'
    ? STATE_UTS[Number(sampleMatch[1]) - 1]
    : undefined;
  return {
    id: b.bus_id, route: b.route_id || "—",
    lat: b.last_lat, lng: b.last_lon,
    status: b.status, speed: 0, occupancy: 0,
    region: sampleRegion || (b.bus_id.startsWith('KA') ? 'Karnataka' : undefined),
    lastSeen: b.last_seen,
  };
}

async function tryLoadLiveData(){
  try {
    const [eventsRes, busesRes] = await Promise.all([
      fetchWithTimeout(`${API_BASE}/events?limit=200`, API_TIMEOUT_MS),
      fetchWithTimeout(`${API_BASE}/buses`, API_TIMEOUT_MS),
    ]);
    if(!eventsRes.ok || !busesRes.ok) throw new Error("API responded with an error");

    const events = await eventsRes.json();
    const buses = await busesRes.json();

    ALL_ALERTS = events.map(mapEventToAlert);
    ALL_BUSES = buses.map(mapBus);
    applyJurisdictionFilter();

    document.dispatchEvent(new CustomEvent('urbaneye:data-source', { detail:{ live:true } }));
    return true;
  } catch (err){
    console.info("UrbanEye: backend not reachable, using bundled demo data.", err.message);
    document.dispatchEvent(new CustomEvent('urbaneye:data-source', { detail:{ live:false } }));
    return false;
  }
}

async function tryLoadInsights(){
  try {
    const [density, defects, delay, od, heat] = await Promise.all([
      fetchWithTimeout(`${API_BASE}/analytics/vehicle-density`, API_TIMEOUT_MS),
      fetchWithTimeout(`${API_BASE}/analytics/defects-breakdown?days=7`, API_TIMEOUT_MS),
      fetchWithTimeout(`${API_BASE}/analytics/route-delay`, API_TIMEOUT_MS),
      fetchWithTimeout(`${API_BASE}/analytics/origin-destination`, API_TIMEOUT_MS),
      fetchWithTimeout(`${API_BASE}/analytics/congestion-heat`, API_TIMEOUT_MS),
    ]);
    if ([density, defects, delay, od, heat].some(response => !response.ok)) return;
    const [densityData, defectData, delayData, odData, heatData] = await Promise.all([
      density.json(), defects.json(), delay.json(), od.json(), heat.json(),
    ]);
    refreshCharts({ density: densityData, defects: defectData, delay: delayData });
    renderOdPairs(odData);
    liveHeatPoints = heatData.map(point => [point.lat, point.lon, point.weight]);
    refreshMap();
  } catch (error) {
    console.info('URBANEYE: analytics unavailable; showing illustrative values.', error.message);
  }
}
