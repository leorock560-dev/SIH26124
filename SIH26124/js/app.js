/* ============================================================
   URBANEYE — dashboard app logic
   ============================================================ */

function fmtTime(iso){
  const d = new Date(iso);
  return d.toLocaleTimeString('en-GB', { hour12:false, hour:'2-digit', minute:'2-digit' });
}

function sevBadgeStyle(sev){
  const c = SEVERITY_COLOR[sev] || '#8B98A5';
  return `background:${c}22;color:${c};`;
}

function escapeHtml(value){
  return String(value ?? '').replace(/[&<>"']/g, char => ({
    '&':'&amp;', '<':'&lt;', '>':'&gt;', '"':'&quot;', "'":'&#39;'
  })[char]);
}

function severityGaugeMarkup(severity){
  const levels = {low:1, medium:2, high:3, critical:4};
  const shortLabels = {low:'LOW', medium:'MED', high:'HIGH', critical:'CRIT'};
  const level = levels[severity];
  const progress = level * 25;
  return `<div class="severity-gauge severity-${severity}" style="--gauge-progress:${progress}%" role="img" aria-label="${severity} severity, level ${level} of 4"><span>${shortLabels[severity]}</span></div>`;
}

function renderSeveritySummary(){
  const summary = document.getElementById('alertsSeveritySummary');
  if (!summary) return;
  const severities = ['critical', 'high', 'medium', 'low'];
  const counts = Object.fromEntries(severities.map(severity => [severity, 0]));
  ALERTS.forEach(alert => {
    if (Object.hasOwn(counts, alert.severity)) counts[alert.severity]++;
  });
  const countLabel = document.getElementById('alertRecordCount');
  if (countLabel) countLabel.textContent = `${ALERTS.length} ${ALERTS.length === 1 ? 'event' : 'events'}`;
  summary.innerHTML = severities.map(severity => `
    <div class="severity-summary-item severity-${severity}">
      <span class="severity-summary-indicator" aria-hidden="true"></span>
      <span class="severity-summary-name">${severity}</span>
      <b>${counts[severity]}</b>
    </div>
  `).join('');
}

function renderStats(){
  document.getElementById('statBusesOnline').textContent = `${FLEET_SUMMARY.busesOnline}/${FLEET_SUMMARY.busesTotal}`;
  document.getElementById('statAlerts').textContent = FLEET_SUMMARY.alertsToday;
  document.getElementById('statConfidence').textContent = Math.round(FLEET_SUMMARY.avgConfidence*100)+'%';
  document.getElementById('statCritical').textContent = FLEET_SUMMARY.criticalOpen;
}

function renderAlertFeed(targetId, limit){
  const el = document.getElementById(targetId);
  const list = limit ? ALERTS.slice(0, limit) : ALERTS;
  if (!list.length){
    const message = isJurisdictionFiltered() ? 'No alerts match this jurisdiction.' : 'No alerts have been reported.';
    el.innerHTML = `<div class="alert-empty">${message}</div>`;
    return;
  }
  el.innerHTML = list.map(a => `
    <div class="alert-row">
      <div class="sev severity-${Object.hasOwn(SEVERITY_COLOR, a.severity) ? a.severity : 'low'}"></div>
      <div class="body">
        <b>${escapeHtml(a.type)}</b>
        <div class="meta">Route ${escapeHtml(a.route)}${a.region ? ` · ${escapeHtml(a.region)}` : ''} · ${fmtTime(a.ts || new Date().toISOString())} · conf ${Number(a.confidence).toFixed(2)}${a.plate ? ' · '+escapeHtml(a.plate) : ''}${a.plateConfidence != null ? ` · plate ${Math.round(a.plateConfidence * 100)}%` : ''}${Number.isFinite(Number(a.lat)) && Number.isFinite(Number(a.lng)) ? ` · GPS ${Number(a.lat).toFixed(5)}, ${Number(a.lng).toFixed(5)}` : ''}</div>
        <div class="note">${escapeHtml(a.note)}</div>
      </div>
      ${severityGaugeMarkup(Object.hasOwn(SEVERITY_COLOR, a.severity) ? a.severity : 'low')}
    </div>
  `).join('');
}

function renderDefectsTable(){
  const el = document.getElementById('defectsTableBody');
  if (!ROAD_DEFECTS.length){
    const message = isJurisdictionFiltered() ? 'No road defects match this jurisdiction.' : 'No road defects have been reported.';
    el.innerHTML = `<tr><td colspan="6">${message}</td></tr>`;
    return;
  }
  el.innerHTML = ROAD_DEFECTS.map(d => `
    <tr>
      <td class="strong mono">${d.id}</td>
      <td class="strong">${escapeHtml(d.type)}</td>
      <td>Route ${escapeHtml(d.route)}</td>
      <td><span class="badge" style="${sevBadgeStyle(d.severity)}">${d.severity}</span></td>
      <td class="mono">${d.confidence.toFixed(2)}</td>
      <td>${escapeHtml(d.status)}</td>
    </tr>
  `).join('');
}

function renderFleet(){
  const el = document.getElementById('fleetGrid');
  if (!BUSES.length){
    el.innerHTML = `<div class="fleet-empty">${isJurisdictionFiltered() ? 'No buses have reported GPS positions in this jurisdiction.' : 'No buses are registered yet.'}</div>`;
    return;
  }
  el.innerHTML = BUSES.map(b => {
    const color = b.status === 'active' ? 'var(--cyan)' : (b.status === 'idle' ? 'var(--amber)' : 'var(--text-faint)');
    return `
    <div class="bus-card">
      <div class="bus-card-top">
        <b>${b.id}</b>
        <span class="badge" style="background:${color}22;color:${color}">${b.status}</span>
      </div>
      <div class="bus-meta"><span>Route</span><span>${escapeHtml(b.route)}</span></div>
      <div class="bus-meta"><span>State / UT</span><span>${escapeHtml(b.region || 'Not tagged')}</span></div>
      <div class="bus-meta"><span>GPS</span><span>${Number.isFinite(Number(b.lat)) && Number.isFinite(Number(b.lng)) ? `${Number(b.lat).toFixed(4)}, ${Number(b.lng).toFixed(4)}` : '—'}</span></div>
      <div class="bus-meta"><span>Last seen</span><span>${b.lastSeen ? fmtTime(b.lastSeen) : 'Sample'}</span></div>
      <div class="bus-meta"><span>Speed</span><span>${b.speed} km/h</span></div>
      <div class="bus-meta"><span>Occupancy</span><span>${Math.round(b.occupancy*100)}%</span></div>
      <div class="occ-bar"><div style="width:${Math.round(b.occupancy*100)}%"></div></div>
    </div>
  `;}).join('');
}

function setupTabs(){
  const buttons = document.querySelectorAll('.sidebar button[data-panel]');
  buttons.forEach(btn => {
    btn.addEventListener('click', () => {
      buttons.forEach(b => b.classList.remove('active'));
      document.querySelectorAll('.panel').forEach(p => p.classList.remove('active'));
      btn.classList.add('active');
      document.getElementById(btn.dataset.panel).classList.add('active');
      if(btn.dataset.panel === 'panel-overview' && map){ setTimeout(()=>map.invalidateSize(), 50); }
      if(btn.dataset.panel === 'panel-analytics'){ setTimeout(()=>refreshCharts(), 50); }
    });
  });
}

function setupMapToggles(){
  document.querySelectorAll('.toggle-chip[data-layer]').forEach(chip => {
    chip.addEventListener('click', () => toggleLayer(chip.dataset.layer, chip));
  });
}

function tickClock(){
  const el = document.getElementById('dashClock');
  if(el) el.textContent = new Date().toLocaleTimeString('en-GB', { hour12:false });
}

function renderOdPairs(data){
  const body = document.getElementById('odPairsBody');
  if (!body) return;
  const pairs = data?.pairs || [];
  body.innerHTML = pairs.length ? pairs.map(pair => `
    <tr><td>${escapeHtml(pair.bus_id)}</td><td>${escapeHtml(pair.route_id)}</td>
    <td>${pair.origin.lat.toFixed(4)}, ${pair.origin.lon.toFixed(4)}</td>
    <td>${pair.destination.lat.toFixed(4)}, ${pair.destination.lon.toFixed(4)}</td>
    <td>${pair.samples}</td></tr>`).join('') : '<tr><td colspan="5">Waiting for two or more GPS heartbeats per bus.</td></tr>';
  const note = document.getElementById('odMethod');
  if (note) note.textContent = data?.method || 'First and last observed GPS samples; not a validated passenger OD estimate.';
}

function refreshDashboard(){
  renderStats();
  renderAlertFeed('alertFeedOverview', 6);
  renderAlertFeed('alertFeedFull', null);
  renderSeveritySummary();
  renderDefectsTable();
  renderFleet();
  refreshMap();
  refreshCharts();
}

document.addEventListener('DOMContentLoaded', () => {
  renderStats();
  renderAlertFeed('alertFeedOverview', 6);
  renderAlertFeed('alertFeedFull', null);
  renderSeveritySummary();
  renderDefectsTable();
  renderFleet();
  setupTabs();
  initMap();
  setupMapToggles();
  initCharts();
  tickClock();
  setInterval(tickClock, 1000);
  document.addEventListener('urbaneye:data-source', event => {
    if (event.detail.live) refreshDashboard();
  });
  document.addEventListener('urbaneye:jurisdiction-change', refreshDashboard);
  tryLoadLiveData().then(live => {
    if (live) tryLoadInsights();
  });
  setInterval(async () => {
    if (await tryLoadLiveData()) tryLoadInsights();
  }, 15000);
});
