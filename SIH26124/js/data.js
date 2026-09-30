/* ============================================================
   URBANEYE — sample dataset for the dashboard demo
   All data below is illustrative/mock, generated for this
   concept demo (city centre: Bengaluru).
   ============================================================ */

const CITY_CENTER = [12.9716, 77.5946];

let BUSES = [
  { id:"KA05-AB-3391", route:"214", lat:12.9716, lng:77.5946, status:"active", speed:22, occupancy:0.71 },
  { id:"KA05-AC-1187", route:"47",  lat:12.9789, lng:77.6045, status:"active", speed:14, occupancy:0.44 },
  { id:"KA05-AD-6620", route:"500D",lat:12.9611, lng:77.5809, status:"active", speed:0,  occupancy:0.92 },
  { id:"KA05-AE-9004", route:"318", lat:12.9352, lng:77.6146, status:"active", speed:31, occupancy:0.28 },
  { id:"KA05-AF-2233", route:"214", lat:12.9884, lng:77.5766, status:"idle",   speed:0,  occupancy:0.10 },
  { id:"KA05-AG-7745", route:"401", lat:12.9439, lng:77.5540, status:"active", speed:19, occupancy:0.63 },
  { id:"KA05-AH-3312", route:"500D",lat:12.9979, lng:77.6412, status:"active", speed:26, occupancy:0.35 },
  { id:"KA05-AJ-5591", route:"47",  lat:12.9166, lng:77.6101, status:"offline",speed:0,  occupancy:0 },
];

let ALERTS = [
  { id:"A-10231", type:"Pothole", category:"defect", severity:"high", route:"214", lat:12.9701, lng:77.5921,
    confidence:0.94, ts:"2026-09-06T08:12:04", note:"Deep pothole, right lane, near Richmond Circle." },
  { id:"A-10230", type:"Hit-and-run tracked", category:"incident", severity:"critical", route:"318", lat:12.9358, lng:77.6132,
    confidence:0.88, plate:"KA 03 MN 7741", note:"Two-wheeler struck, offending vehicle tracked 40s, plate captured." },
  { id:"A-10229", type:"Waterlogging", category:"defect", severity:"medium", route:"401", lat:12.9427, lng:77.5551,
    confidence:0.81, note:"Standing water covering half the carriageway after rain." },
  { id:"A-10228", type:"Congestion building", category:"traffic", severity:"medium", route:"47", lat:12.9795, lng:77.6031,
    confidence:0.89, note:"Vehicle density up 3.2x baseline, MG Road junction approach." },
  { id:"A-10227", type:"School children crossing", category:"safety", severity:"high", route:"500D", lat:12.9605, lng:77.5822,
    confidence:0.91, note:"Group of 6+ children crossing outside marked zebra crossing." },
  { id:"A-10226", type:"Missing signboard", category:"defect", severity:"low", route:"214", lat:12.9740, lng:77.5978,
    confidence:0.77, note:"Speed-limit sign post present, board missing." },
  { id:"A-10225", type:"Rash driving pattern", category:"safety", severity:"medium", route:"401", lat:12.9455, lng:77.5502,
    confidence:0.85, plate:"KA 41 HT 2290", note:"Repeated lane weaving over 18s, flagged for review." },
  { id:"A-10224", type:"Faded zebra crossing", category:"defect", severity:"low", route:"47", lat:12.9151, lng:77.6087,
    confidence:0.79, note:"Crossing markings under 30% visible reflectivity." },
  { id:"A-10223", type:"Missing lane divider", category:"defect", severity:"medium", route:"500D", lat:12.9962, lng:77.6390,
    confidence:0.83, note:"~60m stretch with no visible lane marking." },
  { id:"A-10222", type:"Pothole cluster", category:"defect", severity:"high", route:"318", lat:12.9330, lng:77.6168,
    confidence:0.92, note:"Cluster of 4 potholes across 25m, high-traffic stretch." },
];

let ALL_BUSES = BUSES.slice();
let ALL_ALERTS = ALERTS.slice();

const SEVERITY_COLOR = { critical:"#E5484D", high:"#E5484D", medium:"#F2A93B", low:"#8B98A5" };
const CATEGORY_COLOR = { defect:"#F2A93B", incident:"#E5484D", traffic:"#3BC9DB", safety:"#4CC38A" };

const CONGESTION_POINTS = [
  [12.9716, 77.5946, 0.9], [12.9720, 77.5952, 0.8], [12.9705, 77.5938, 0.6],
  [12.9789, 77.6045, 0.7], [12.9795, 77.6031, 0.95], [12.9780, 77.6055, 0.5],
  [12.9439, 77.5540, 0.55], [12.9427, 77.5551, 0.4],
  [12.9352, 77.6146, 0.65], [12.9358, 77.6132, 0.7],
  [12.9979, 77.6412, 0.3],
];

let ROAD_DEFECTS = ALERTS.filter(a => a.category === "defect").map(a => ({
  id:a.id, type:a.type, route:a.route, severity:a.severity, confidence:a.confidence,
  location:a.note, status: a.severity === "low" ? "logged" : (a.id === "A-10231" ? "dispatched" : "logged")
}));

const HOURLY_VEHICLE_DENSITY = {
  labels:["06:00","08:00","10:00","12:00","14:00","16:00","18:00","20:00","22:00"],
  values:[4, 8, 11, 12, 9, 14, 16, 10, 5]
};

const DEFECT_BREAKDOWN = {
  labels:["Potholes","Waterlogging","Missing signage","Faded crossing","Missing divider"],
  values:[18, 6, 9, 7, 5]
};

const ROUTE_DELAY = {
  labels:["214","47","500D","318","401"],
  planned:[0, 0, 0, 0, 0],
  actual:[3, 2, 4, 1, 3]
};

let FLEET_SUMMARY = {};
function recomputeRoadDefects(){
  ROAD_DEFECTS = ALERTS.filter(a => a.category === "defect").map(a => ({
    id:a.id, type:a.type, route:a.route, severity:a.severity, confidence:a.confidence,
    location:a.note, status:a.status || (a.severity === "low" ? "logged" : "dispatched")
  }));
}
function recomputeFleetSummary(){
  FLEET_SUMMARY = {
    busesOnline: BUSES.filter(b=>b.status==="active").length,
    busesTotal: BUSES.length,
    alertsToday: ALERTS.length,
    avgConfidence: ALERTS.length ? ALERTS.reduce((sum, alert)=>sum+alert.confidence,0)/ALERTS.length : 0,
    criticalOpen: ALERTS.filter(a=>a.severity==="critical").length,
  };
}
recomputeRoadDefects();
recomputeFleetSummary();