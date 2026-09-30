/* ============================================================
   URBANEYE — map layer (Leaflet)
   ============================================================ */
let map, busLayer, alertLayer, heatLayer;
let liveHeatPoints = [];
let streetLayer, satelliteLayer, satelliteLabelsLayer, activeBaseLayer, mapModeControl;
let mapOptions = {};

function initMap(targetId = 'map', options = {}){
  const mapElement = document.getElementById(targetId);
  if (!mapElement) return;
  if (typeof L === 'undefined') {
    mapElement.textContent = 'Map tiles are unavailable. Connect to the internet and reload.';
    return;
  }
  mapOptions = {...options, targetId};
  map = L.map(targetId, { zoomControl:true, attributionControl:true }).setView(CITY_CENTER, 12);

  streetLayer = L.tileLayer('https://tile.openstreetmap.org/{z}/{x}/{y}.png', {
    attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap contributors</a>',
    maxZoom: 19
  });
  satelliteLayer = L.tileLayer('https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}', {
    attribution: 'Tiles &copy; Esri and its imagery contributors',
    maxZoom: 19
  });
  satelliteLabelsLayer = L.tileLayer('https://server.arcgisonline.com/ArcGIS/rest/services/Reference/World_Reference_Overlay/MapServer/tile/{z}/{y}/{x}', {
    attribution: 'Labels &copy; Esri and its contributors',
    maxZoom: 19
  });

  heatLayer = L.heatLayer ? L.heatLayer([], { radius:38, blur:28, maxZoom:14,
    gradient:{0.3:'#1F5158', 0.55:'#3BC9DB', 0.75:'#F2A93B', 1:'#E5484D'} }) : null;
  busLayer = L.layerGroup().addTo(map);
  alertLayer = L.layerGroup().addTo(map);
  addMapTypeControl();
  setMapType('default');
  refreshMap();
}

function addMapTypeControl(){
  mapModeControl = L.control({position:'topright'});
  mapModeControl.onAdd = () => {
    const control = L.DomUtil.create('div', 'leaflet-control map-type-control');
    control.setAttribute('role', 'group');
    control.setAttribute('aria-label', 'Map type');
    control.innerHTML = `
      <button type="button" data-map-type="default" aria-pressed="true">Default</button>
      <button type="button" data-map-type="satellite" aria-pressed="false">Satellite</button>
      <button type="button" data-map-type="traffic" aria-pressed="false">Traffic</button>`;
    L.DomEvent.disableClickPropagation(control);
    L.DomEvent.disableScrollPropagation(control);
    control.querySelectorAll('button').forEach(button => {
      L.DomEvent.on(button, 'click', () => setMapType(button.dataset.mapType));
    });
    return control;
  };
  mapModeControl.addTo(map);
}

function setMapType(type){
  if (!map || !streetLayer || !satelliteLayer) return;
  const nextLayer = type === 'satellite' ? satelliteLayer : streetLayer;
  if (activeBaseLayer && map.hasLayer(activeBaseLayer)) map.removeLayer(activeBaseLayer);
  if (satelliteLabelsLayer && map.hasLayer(satelliteLabelsLayer)) map.removeLayer(satelliteLabelsLayer);
  activeBaseLayer = nextLayer;
  activeBaseLayer.addTo(map);
  if (type === 'satellite') satelliteLabelsLayer.addTo(map);

  if (heatLayer) {
    if (type === 'traffic') heatLayer.addTo(map);
    else if (map.hasLayer(heatLayer)) map.removeLayer(heatLayer);
  }

  document.querySelectorAll(`#${mapOptions.targetId} .map-type-control button`).forEach(button => {
    button.setAttribute('aria-pressed', String(button.dataset.mapType === type));
  });
}

function escapeMapText(value){
  return String(value ?? '').replace(/[&<>"']/g, character => ({
    '&':'&amp;', '<':'&lt;', '>':'&gt;', '"':'&quot;', "'":'&#39;'
  })[character]);
}

function refreshMap(){
  if (!map || !busLayer || !alertLayer) return;
  busLayer.clearLayers();
  alertLayer.clearLayers();
  const busesToShow = mapOptions.preview ? BUSES.slice(0, 3) : BUSES;
  const alertsToShow = mapOptions.preview ? ALERTS.slice(0, 4) : ALERTS;
  busesToShow.forEach(b => {
    const color = b.status === 'active' ? '#0D67B5' : (b.status === 'idle' ? '#E87817' : '#718092');
    const icon = L.divIcon({
      className:'', html:`<div style="width:12px;height:12px;border-radius:50%;background:${color};border:2px solid #FFFFFF;box-shadow:0 0 0 2px ${color}55;"></div>`,
      iconSize:[12,12], iconAnchor:[6,6]
    });
    L.marker([b.lat,b.lng], {icon}).addTo(busLayer)
      .bindPopup(`<b>${escapeMapText(b.id)}</b><br>Route ${escapeMapText(b.route)} · ${escapeMapText(b.status)}<br>${Number(b.speed || 0)} km/h`);
  });

  alertsToShow.forEach(a => {
    const color = SEVERITY_COLOR[a.severity] || '#8B98A5';
    const icon = L.divIcon({
      className:'', html:`<div style="width:16px;height:16px;border-radius:3px;transform:rotate(45deg);background:${color}33;border:1.5px solid ${color};"></div>`,
      iconSize:[16,16], iconAnchor:[8,8]
    });
    L.marker([a.lat,a.lng], {icon}).addTo(alertLayer)
      .bindPopup(`<b>${escapeMapText(a.type)}</b><br>Route ${escapeMapText(a.route)} · conf ${Number(a.confidence).toFixed(2)}<br>GPS ${Number(a.lat).toFixed(5)}, ${Number(a.lng).toFixed(5)}<br>${escapeMapText(a.note)}`);
  });
  if (heatLayer && heatLayer.setLatLngs) {
    const heatPoints = liveHeatPoints.length ? liveHeatPoints : CONGESTION_POINTS;
    const visibleHeatPoints = typeof isJurisdictionFiltered === 'function' && isJurisdictionFiltered()
      ? heatPoints.filter(([lat, lon]) => jurisdictionPointMatches(lat, lon))
      : heatPoints;
    heatLayer.setLatLngs(visibleHeatPoints);
  }
}

function toggleLayer(name, chipEl){
  let layer, target;
  if(name === 'heat') layer = heatLayer;
  if(name === 'buses') layer = busLayer;
  if(name === 'alerts') layer = alertLayer;
  if(!layer) return;
  if(map.hasLayer(layer)){ map.removeLayer(layer); chipEl.classList.remove('on'); }
  else { map.addLayer(layer); chipEl.classList.add('on'); }
}