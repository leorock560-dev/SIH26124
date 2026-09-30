/* Select the FastAPI origin when the page is hosted by VS Code Live Server. */
(() => {
  if (window.URBANEYE_API_BASE) return;

  const liveServerPorts = new Set(["5500", "5501"]);
  const apiOrigin = liveServerPorts.has(window.location.port)
    ? `${window.location.protocol}//${window.location.hostname}:8000`
    : window.location.origin;
  window.URBANEYE_API_BASE = `${apiOrigin}/api`;
})();
