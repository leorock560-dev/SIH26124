let densityData = HOURLY_VEHICLE_DENSITY;
let apiDefectData = null;
let apiRouteData = null;
const dashboardCharts = {};

const chartColors = {
  blue: '#0D67B5',
  blueFill: 'rgba(13, 103, 181, 0.14)',
  orange: '#E87817',
  grid: 'rgba(23, 37, 53, 0.10)',
  text: '#5D6B79',
};

function chartSelectionData(){
  const defectCounts = new Map();
  (ROAD_DEFECTS || []).forEach(defect => {
    const label = defect.type || 'Other';
    defectCounts.set(label, (defectCounts.get(label) || 0) + 1);
  });

  const routeCounts = new Map();
  (ALERTS || []).filter(alert => ['traffic', 'incident'].includes(alert.category)).forEach(alert => {
    const route = alert.route && alert.route !== '—' ? alert.route : 'Unassigned';
    routeCounts.set(route, (routeCounts.get(route) || 0) + 1);
  });

  const jurisdictionSelected = typeof isJurisdictionFiltered === 'function' && isJurisdictionFiltered();
  const localDefects = { labels:[...defectCounts.keys()], values:[...defectCounts.values()] };
  const localRoutes = { labels:[...routeCounts.keys()], values:[...routeCounts.values()] };
  return {
    defects: !jurisdictionSelected && apiDefectData ? apiDefectData : localDefects,
    routes: !jurisdictionSelected && apiRouteData ? apiRouteData : localRoutes,
    jurisdictionSelected,
  };
}

function updateChart(id, type, labels, dataset, scales){
  const canvas = document.getElementById(id);
  if (!canvas || typeof Chart === 'undefined') return;

  const config = {
    type,
    data: { labels, datasets:[dataset] },
    options: {
      responsive:true,
      maintainAspectRatio:false,
      indexAxis:type === 'bar' ? 'y' : 'x',
      animation:{ duration:350 },
      interaction:{ intersect:false, mode:'index' },
      plugins:{
        legend:{ display:false },
        tooltip:{
          enabled:true,
          displayColors:false,
          callbacks:{
            label: context => `${context.dataset.label}: ${context.chart.config.type === 'line' ? context.parsed.y : context.parsed.x}`,
          },
        },
      },
      scales,
    },
  };

  if (dashboardCharts[id]){
    dashboardCharts[id].data = config.data;
    dashboardCharts[id].options = config.options;
    dashboardCharts[id].update();
  } else {
    dashboardCharts[id] = new Chart(canvas, config);
  }
}

function setChartSummaries({defects, routes, jurisdictionSelected}){
  const defectTotal = defects.values.reduce((sum, value) => sum + value, 0);
  const routeTotal = routes.values.reduce((sum, value) => sum + value, 0);
  const defectSummary = document.getElementById('defectChartSummary');
  const routeSummary = document.getElementById('routeAlertChartSummary');
  const defectBreakdown = defects.labels.map((label, index) => `${label}: ${defects.values[index]}`).join(' · ');
  const routeBreakdown = routes.labels.map((label, index) => `Route ${label}: ${routes.values[index]}`).join(' · ');

  if (defectSummary){
    const range = jurisdictionSelected ? 'in the current selection' : 'in the last 7 days, fleet-wide';
    defectSummary.textContent = `${defectTotal} road ${defectTotal === 1 ? 'defect' : 'defects'} ${range}${defectBreakdown ? ` — ${defectBreakdown}` : ''}.`;
  }
  if (routeSummary){
    const range = jurisdictionSelected ? 'in the current selection' : 'fleet-wide';
    routeSummary.textContent = `${routeTotal} traffic or incident ${routeTotal === 1 ? 'event' : 'events'} across ${routes.labels.length} ${routes.labels.length === 1 ? 'route' : 'routes'} ${range}${routeBreakdown ? ` — ${routeBreakdown}` : ''}.`;
  }
}

function drawAllCharts(){
  if (typeof Chart === 'undefined'){
    const note = document.getElementById('densityChartSummary');
    if (note) note.textContent = 'Charts could not load. Check the internet connection and refresh the page.';
    return;
  }

  const selection = chartSelectionData();
  const densityLabels = densityData?.labels || [];
  const densityValues = densityData?.values || [];

  updateChart('chartDensity', 'line', densityLabels, {
    label:'Average vehicles per heartbeat',
    data:densityValues,
    borderColor:chartColors.blue,
    backgroundColor:chartColors.blueFill,
    fill:true,
    tension:0.32,
    pointRadius:2,
    pointHoverRadius:5,
    borderWidth:2,
  }, {
    x:{ grid:{ display:false }, ticks:{ color:chartColors.text, maxTicksLimit:8 } },
    y:{ beginAtZero:true, title:{ display:true, text:'Vehicles per heartbeat' }, grid:{ color:chartColors.grid }, ticks:{ color:chartColors.text, precision:0 } },
  });

  updateChart('chartDefects', 'bar', selection.defects.labels, {
    label:'Road defects',
    data:selection.defects.values,
    backgroundColor:chartColors.orange,
    borderRadius:4,
    maxBarThickness:30,
  }, {
    x:{ beginAtZero:true, title:{ display:true, text:'Number of defects' }, grid:{ color:chartColors.grid }, ticks:{ color:chartColors.text, precision:0 } },
    y:{ grid:{ display:false }, ticks:{ color:chartColors.text, autoSkip:false } },
  });

  updateChart('chartDelay', 'bar', selection.routes.labels, {
    label:'Traffic and incident events',
    data:selection.routes.values,
    backgroundColor:chartColors.blue,
    borderRadius:4,
    maxBarThickness:34,
  }, {
    x:{ beginAtZero:true, title:{ display:true, text:'Events' }, grid:{ color:chartColors.grid }, ticks:{ color:chartColors.text, precision:0 } },
    y:{ grid:{ display:false }, ticks:{ color:chartColors.text, autoSkip:false, callback(value){ return `Route ${this.getLabelForValue(value)}`; } } },
  });

  setChartSummaries(selection);
}

function initCharts(){
  drawAllCharts();
}

function refreshCharts(data){
  if (data?.density) densityData = data.density;
  if (data?.defects){
    apiDefectData = {
      labels:data.defects.map(row => String(row.type || 'other').replaceAll('_', ' ')),
      values:data.defects.map(row => Number(row.count) || 0),
    };
  }
  if (data?.delay){
    apiRouteData = {
      labels:data.delay.map(row => String(row.route_id || 'unknown')),
      values:data.delay.map(row => Number(row.disruption_events) || 0),
    };
  }
  drawAllCharts();
}
