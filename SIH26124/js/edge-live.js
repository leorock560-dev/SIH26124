/* Receives edge detections from the Flask/Socket.IO process on port 5000. */
(() => {
  const edgeUrl = new URL(window.location.href);
  edgeUrl.port = "5000";
  edgeUrl.pathname = "/";
  edgeUrl.search = "";
  edgeUrl.hash = "";

  const categories = {
    pothole: "defect",
    damaged_road: "defect",
    manhole_open: "defect",
    missing_road_divider: "defect",
    damaged_traffic_signal: "defect",
    waterlogging: "defect",
    construction_zone: "defect",
    traffic_congestion: "traffic",
    rash_driving: "safety",
    unsafe_driving: "safety",
    accident: "incident",
    hit_and_run: "incident",
  };
  const severities = {
    pothole: "high",
    damaged_road: "medium",
    manhole_open: "high",
    missing_road_divider: "medium",
    damaged_traffic_signal: "medium",
    waterlogging: "medium",
    construction_zone: "low",
    traffic_congestion: "medium",
    rash_driving: "medium",
    unsafe_driving: "low",
    accident: "critical",
    hit_and_run: "critical",
  };
  function describeMetadata(meta) {
    if (!meta || typeof meta !== "object") return "";

    const details = [];
    if (Array.isArray(meta.vehicle_track_ids) && meta.vehicle_track_ids.length) {
      details.push(`Vehicles ${meta.vehicle_track_ids.join(", ")}`);
    }
    if (Number.isFinite(Number(meta.fall_confidence))) {
      details.push(`Fall confidence ${Math.round(Number(meta.fall_confidence) * 100)}%`);
    }
    if (Number.isFinite(Number(meta.vehicle_distance))) {
      details.push(`Vehicle proximity ${Number(meta.vehicle_distance).toFixed(3)}`);
    }
    if (meta.source === "accident_model") {
      details.push("Detected by accident model");
    }
    return details.length ? details.join(" · ") : "";
  }

  const receivedAlerts = new Map();
  let nextAlertId = 1;
  let apiIsLive = false;
  let socket = null;

  function updateSourceBadge(edgeConnected) {
    const badge = document.getElementById("dataSourceBadge");
    if (!badge) return;
    badge.textContent = edgeConnected
      ? (apiIsLive ? "Live API · edge connected" : "Edge connected · illustrative API data")
      : (apiIsLive ? "Live API · edge disconnected" : "Illustrative data · edge disconnected");
  }

  function makeAlert(event) {
    if (!event || typeof event !== "object") return null;

    const lat = Number(event.lat);
    const lng = Number(event.lon);
    const confidence = Number(event.confidence);
    const eventType = String(event.event_type || "").trim().toLowerCase();
    if (
      !eventType
      || !Number.isFinite(lat) || lat < -90 || lat > 90
      || !Number.isFinite(lng) || lng < -180 || lng > 180
    ) {
      console.warn("Ignoring edge incident with invalid event type or GPS coordinates.", event);
      return null;
    }

    const timestamp = event.timestamp || new Date().toISOString();
    const key = [
      event.bus_id || "",
      eventType,
      timestamp,
      lat.toFixed(6),
      lng.toFixed(6),
    ].join("|");
    if (receivedAlerts.has(key)) return null;

    const metadata = describeMetadata(event.meta);
    return {
      key,
      id: `EDGE-${nextAlertId++}`,
      type: eventType.replace(/_/g, " ").replace(/\b\w/g, letter => letter.toUpperCase()),
      category: categories[eventType] || "safety",
      severity: severities[eventType] || "low",
      route: event.route_id || "—",
      lat,
      lng,
      confidence: Number.isFinite(confidence) ? Math.min(1, Math.max(0, confidence)) : 0,
      ts: timestamp,
      plate: event.plate_number || undefined,
      plateConfidence: event.plate_confidence,
      note: [event.bus_id ? `Bus ${event.bus_id}` : "", metadata].filter(Boolean).join(" · "),
    };
  }

  function mergeEdgeAlerts() {
    const edgeAlerts = [...receivedAlerts.values()].reverse();
    const backendAlerts = ALL_ALERTS.filter(alert => !edgeAlerts.some(edgeAlert => (
      String(alert.type).toLowerCase() === edgeAlert.type.toLowerCase()
      && String(alert.route) === String(edgeAlert.route)
      && String(alert.ts || "") === edgeAlert.ts
      && Number(alert.lat) === edgeAlert.lat
      && Number(alert.lng) === edgeAlert.lng
    )));
    ALL_ALERTS = [...edgeAlerts, ...backendAlerts].slice(0, 200);

    if (typeof applyJurisdictionFilter === "function") {
      applyJurisdictionFilter();
    } else {
      ALERTS = ALL_ALERTS.slice();
      recomputeRoadDefects();
      recomputeFleetSummary();
      refreshDashboard();
    }
  }

  document.addEventListener("urbaneye:data-source", event => {
    apiIsLive = Boolean(event.detail?.live);
    updateSourceBadge(Boolean(socket?.connected));
    mergeEdgeAlerts();
  });

  if (typeof io !== "function") {
    console.error("Socket.IO client is unavailable; edge incidents will not reach the dashboard.");
    updateSourceBadge(false);
    return;
  }

  socket = io(edgeUrl.origin, {
    transports: ["websocket", "polling"],
    reconnection: true,
  });

  socket.on("connect", () => {
    console.info(`Connected to edge event stream at ${edgeUrl.origin}.`);
    updateSourceBadge(true);
  });

  socket.on("disconnect", reason => {
    console.warn("Disconnected from edge event stream:", reason);
    updateSourceBadge(false);
  });

  socket.on("connect_error", error => {
    console.warn("Could not connect to the Flask edge event stream:", error.message);
    updateSourceBadge(false);
  });

  socket.on("incident", event => {
    const alert = makeAlert(event);
    if (!alert) return;

    receivedAlerts.set(alert.key, alert);
    while (receivedAlerts.size > 200) {
      receivedAlerts.delete(receivedAlerts.keys().next().value);
    }
    mergeEdgeAlerts();
  });
})();
