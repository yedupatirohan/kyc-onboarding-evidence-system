// One place that talks to the backend. Everything the screens show comes from these real endpoints.
const BASE = "/api";

export async function api(path, params = {}) {
  const qs = new URLSearchParams();
  Object.entries(params).forEach(([k, v]) => {
    if (v !== "" && v !== null && v !== undefined) qs.set(k, v);
  });
  const url = `${BASE}${path}${qs.toString() ? "?" + qs.toString() : ""}`;
  const res = await fetch(url);
  if (!res.ok) {
    let detail = res.statusText;
    try {
      const body = await res.json();
      detail = typeof body.detail === "string" ? body.detail : JSON.stringify(body.detail);
    } catch (e) { /* body was not JSON */ }
    throw new Error(`${res.status}: ${detail}`);
  }
  return res.json();
}
