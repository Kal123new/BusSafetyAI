const API_BASE_URL = import.meta.env.VITE_API_BASE_URL
  || (import.meta.env.DEV ? "http://127.0.0.1:8000" : "");
let accessToken = "";
export const setAccessToken = value => { accessToken = value; };
const authHeaders = () => accessToken ? { Authorization: `Bearer ${accessToken}` } : {};

export async function requestApi(path, options = {}) {
  const response = await fetch(`${API_BASE_URL}${path}`, {
    ...options, signal: options.signal ? AbortSignal.any([options.signal, AbortSignal.timeout(15000)]) : AbortSignal.timeout(15000),
    headers: { Accept: "application/json", ...authHeaders(), ...(options.body ? { "Content-Type": "application/json" } : {}), ...options.headers }
  });
  const data = await response.json();
  if (!response.ok) {
    const detail = data.detail;
    const message = typeof detail === "string" ? detail : Array.isArray(detail)
      ? detail.map(item => item.msg).join("; ") : detail?.message || `Request failed (${response.status})`;
    const error = new Error(message);
    error.status = response.status;
    throw error;
  }
  return data;
}

export const listTrips = async () => { await requestApi("/api/v1/trips/ensure-daily", {method: "POST"}); return requestApi("/api/v1/trips"); };
export const getTrip = id => requestApi(`/api/v1/trips/${encodeURIComponent(id)}`);
export const sendLocation = (id, body, signal) => requestApi(`/api/v1/trips/${encodeURIComponent(id)}/locations`, {
  method: "POST", body: JSON.stringify(body), signal
});
export function saveTripAction(id, action, body, key) {
  return requestApi(`/api/v1/trips/${encodeURIComponent(id)}/${action}`, {
    method: action.startsWith("students/") ? "PATCH" : "POST",
    headers: { "Idempotency-Key": key }, body: JSON.stringify(body) });
}

export async function getBackendHealth() {
  const response = await fetch(`${API_BASE_URL}/health`, {
    method: "GET",
    signal: AbortSignal.timeout(10000),
    headers: { Accept: "application/json" }
  });

  if (!response.ok) {
    throw new Error(`Backend health check failed: ${response.status}`);
  }

  return response.json();
}

export async function predictFrame(frameBlob, capturedAt = Date.now() / 1000, signal) {
  const body = new FormData();
  body.append("file", frameBlob, "frame.jpg");
  body.append("captured_at", String(capturedAt));
  body.append("frame_id", crypto.randomUUID());

  const response = await fetch(`${API_BASE_URL}/predict`, {
    method: "POST",
    headers: authHeaders(),
    signal: signal ? AbortSignal.any([signal, AbortSignal.timeout(15000)]) : AbortSignal.timeout(15000),
    body
  });

  if (!response.ok) {
    let data;
    try { data = await response.json(); } catch { data = null; }
    const error = new Error(typeof data?.detail === 'string' ? data.detail : `Prediction failed (${response.status})`);
    error.status = response.status;
    const retryAfter = Number(response.headers.get('Retry-After'));
    error.retryAfterMs = Number.isFinite(retryAfter) && retryAfter > 0 ? Math.min(retryAfter * 1000, 60000) : 0;
    throw error;
  }

  return response.json();
}
