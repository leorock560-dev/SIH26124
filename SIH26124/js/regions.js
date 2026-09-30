const STATE_UTS = [
	"Andaman and Nicobar Islands", "Andhra Pradesh", "Arunachal Pradesh", "Assam",
	"Bihar", "Chandigarh", "Chhattisgarh", "Dadra and Nagar Haveli and Daman and Diu",
	"Delhi", "Goa", "Gujarat", "Haryana", "Himachal Pradesh", "Jammu and Kashmir",
	"Jharkhand", "Karnataka", "Kerala", "Ladakh", "Lakshadweep", "Madhya Pradesh",
	"Maharashtra", "Manipur", "Meghalaya", "Mizoram", "Nagaland", "Odisha",
	"Puducherry", "Punjab", "Rajasthan", "Sikkim", "Tamil Nadu", "Telangana",
	"Tripura", "Uttar Pradesh", "Uttarakhand", "West Bengal",
];

const REGION_HINTS = {
	Karnataka: {
		Bengaluru: {
			Bengaluru_North: ["Yelahanka", "Hebbal", "Byatarayanapura"],
			Bengaluru_East: ["Mahadevapura", "Krishnarajapuram", "Hoodi"],
		},
		Mysuru: {Mysuru: ["Mysuru", "Hunsur", "Nanjangud"]},
	},
	Maharashtra: {
		Mumbai: {
			Mumbai_City: ["Fort", "Colaba", "Byculla"],
			Mumbai_Suburban: ["Andheri", "Borivali", "Kurla"],
		},
		Pune: {Haveli: ["Pune City", "Kothrud", "Shivajinagar"]},
	},
	Delhi: {
		"New Delhi": {"New Delhi": ["Connaught Place", "Chanakyapuri", "Vasant Vihar"]},
		"North Delhi": {"Civil Lines": ["Model Town", "Narela", "Sadar Bazar"]},
	},
};

let selectedRegionBounds = null;
let jurisdictionFilterActive = false;
let locationRequestId = 0;
let lastLocationRequestAt = 0;

function isJurisdictionFiltered(){
	return jurisdictionFilterActive;
}

function regionParts(){
	return ["selState", "selDistrict", "selSubdistrict", "selTaluk"]
		.map(id => document.getElementById(id)?.value.trim() || "")
		.filter(Boolean);
}

function setOptions(listId, values){
	const list = document.getElementById(listId);
	list.replaceChildren(...[...new Set(values)].map(value => {
		const option = document.createElement("option");
		option.value = value.replaceAll("_", " ");
		return option;
	}));
}

function matchingKey(object, value){
	if (!object || !value) return null;
	return Object.keys(object).find(key => key.replaceAll("_", " ").toLowerCase() === value.toLowerCase()) || null;
}

function updateRegionSuggestions(){
	const state = document.getElementById("selState").value;
	const district = document.getElementById("selDistrict").value.trim();
	const subdistrict = document.getElementById("selSubdistrict").value.trim();
	const districts = REGION_HINTS[state] || {};
	const districtKey = matchingKey(districts, district);
	const subdistricts = districtKey ? districts[districtKey] : {};
	const subdistrictKey = matchingKey(subdistricts, subdistrict);
	setOptions("districtOptions", Object.keys(districts));
	setOptions("subdistrictOptions", Object.keys(subdistricts || {}));
	setOptions("talukOptions", subdistrictKey ? subdistricts[subdistrictKey] || [] : []);
}

function jurisdictionPointMatches(lat, lon){
	if (!jurisdictionFilterActive) return true;
	if (!selectedRegionBounds || !Number.isFinite(lat) || !Number.isFinite(lon)) return false;
	const {south, north, west, east} = selectedRegionBounds;
	return lat >= south && lat <= north && lon >= west && lon <= east;
}

function applyJurisdictionFilter(){
	const sourceBuses = typeof ALL_BUSES === "undefined" ? BUSES : ALL_BUSES;
	const sourceAlerts = typeof ALL_ALERTS === "undefined" ? ALERTS : ALL_ALERTS;
	BUSES = sourceBuses.filter(bus => jurisdictionPointMatches(Number(bus.lat), Number(bus.lng)));
	ALERTS = sourceAlerts.filter(alert => jurisdictionPointMatches(Number(alert.lat), Number(alert.lng)));
	recomputeRoadDefects();
	recomputeFleetSummary();
	document.dispatchEvent(new CustomEvent("urbaneye:jurisdiction-change"));
}

function expandGeocoderBounds(result, parts){
	const [southValue, northValue, westValue, eastValue] = (result.boundingbox || []).map(Number);
	const latitude = Number(result.lat);
	const longitude = Number(result.lon);
	let south = Number.isFinite(southValue) ? southValue : latitude;
	let north = Number.isFinite(northValue) ? northValue : latitude;
	let west = Number.isFinite(westValue) ? westValue : longitude;
	let east = Number.isFinite(eastValue) ? eastValue : longitude;
	if (![south, north, west, east].every(Number.isFinite)) return null;

	const minimumSpan = parts.length >= 4 ? 0.025 : parts.length === 3 ? 0.06 : parts.length === 2 ? 0.2 : 0.8;
	const centerLat = (south + north) / 2;
	const centerLon = (west + east) / 2;
	const latitudeSpan = Math.max(north - south, minimumSpan);
	const longitudeSpan = Math.max(east - west, minimumSpan / Math.max(Math.cos(centerLat * Math.PI / 180), 0.25));
	return {
		south:centerLat - latitudeSpan / 2,
		north:centerLat + latitudeSpan / 2,
		west:centerLon - longitudeSpan / 2,
		east:centerLon + longitudeSpan / 2,
	};
}

async function resolveJurisdiction(parts, requestId){
	const note = document.getElementById("regionNote");
	const status = document.getElementById("regionStatus");
	const locationName = parts.join(", ");
	status.textContent = `${locationName} · locating`;
	note.textContent = "Finding this place with OpenStreetMap…";

	const wait = Math.max(0, 1100 - (Date.now() - lastLocationRequestAt));
	if (wait) await new Promise(resolve => setTimeout(resolve, wait));
	if (requestId !== locationRequestId) return;
	lastLocationRequestAt = Date.now();

	try {
		const params = new URLSearchParams({
			q:`${parts.slice().reverse().join(", ")}, India`,
			format:"jsonv2",
			limit:"1",
			countrycodes:"in",
			addressdetails:"1",
		});
		const response = await fetch(`https://nominatim.openstreetmap.org/search?${params}`, {
			headers:{"Accept-Language":"en"},
		});
		if (!response.ok) throw new Error(`Location lookup failed (${response.status})`);
		const results = await response.json();
		if (requestId !== locationRequestId) return;

		const place = results[0];
		selectedRegionBounds = place ? expandGeocoderBounds(place, parts) : null;
		if (!selectedRegionBounds){
			status.textContent = `${locationName} · no map match`;
			note.textContent = "No matching place was found. The map and lists show no records until a place can be resolved.";
			applyJurisdictionFilter();
			return;
		}

		status.textContent = locationName;
		note.textContent = `Matched ${place.display_name}. Map, alerts, road health and fleet use GPS bounds; analytics charts remain fleet-wide. Place lookup uses OpenStreetMap Nominatim.`;
		if (typeof map !== "undefined" && map && typeof L !== "undefined"){
			map.fitBounds([[selectedRegionBounds.south, selectedRegionBounds.west],
										 [selectedRegionBounds.north, selectedRegionBounds.east]],
										{padding:[24, 24], maxZoom:15});
		}
		applyJurisdictionFilter();
	} catch (error){
		if (requestId !== locationRequestId) return;
		selectedRegionBounds = null;
		status.textContent = `${locationName} · lookup unavailable`;
		note.textContent = "Location lookup failed. Check internet access; the data list is left unfiltered.";
		jurisdictionFilterActive = false;
		applyJurisdictionFilter();
	}
}

function scheduleJurisdictionLookup(){
	const parts = regionParts();
	jurisdictionFilterActive = parts.length > 0;
	selectedRegionBounds = null;
	const requestId = ++locationRequestId;
	if (!parts.length){
		document.getElementById("regionStatus").textContent = "All regions";
		document.getElementById("regionNote").textContent = "Place names are resolved with OpenStreetMap. Synthetic sample buses and alerts are seeded across all States/UTs; real coverage depends on bus GPS reports.";
		applyJurisdictionFilter();
		return;
	}
	applyJurisdictionFilter();
	window.clearTimeout(scheduleJurisdictionLookup.timer);
	scheduleJurisdictionLookup.timer = window.setTimeout(() => resolveJurisdiction(parts, requestId), 500);
}

document.addEventListener("DOMContentLoaded", () => {
	const state = document.getElementById("selState");
	const district = document.getElementById("selDistrict");
	const subdistrict = document.getElementById("selSubdistrict");
	const taluk = document.getElementById("selTaluk");
	if (!state) return;

	state.replaceChildren(new Option("State / UT", ""), ...STATE_UTS.map(name => new Option(name, name)));
	state.addEventListener("change", () => {
		district.value = "";
		subdistrict.value = "";
		taluk.value = "";
		district.disabled = !state.value;
		subdistrict.disabled = true;
		taluk.disabled = true;
		updateRegionSuggestions();
		scheduleJurisdictionLookup();
	});
	district.addEventListener("change", () => {
		subdistrict.value = "";
		taluk.value = "";
		subdistrict.disabled = !district.value.trim();
		taluk.disabled = !district.value.trim();
		updateRegionSuggestions();
		scheduleJurisdictionLookup();
	});
	subdistrict.addEventListener("change", () => {
		taluk.value = "";
		taluk.disabled = !subdistrict.value.trim();
		updateRegionSuggestions();
		scheduleJurisdictionLookup();
	});
	taluk.addEventListener("change", scheduleJurisdictionLookup);
	updateRegionSuggestions();
});
