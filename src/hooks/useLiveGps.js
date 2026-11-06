import { useEffect, useState } from "react";
import { sendLocation } from "../api/client.js";
import { fixQuality, positionToFix } from "../utils/gps.js";

export function useLiveGps(trip) {
  const [session, setSession] = useState(null);
  const [fix, setFix] = useState(null);
  const [error, setError] = useState("");
  const [sync, setSync] = useState(null);
  const [now, setNow] = useState(Date.now() / 1000);
  const allowed = Boolean(trip && ["scheduled", "in_progress"].includes(trip.status));
  const enabled = allowed && session?.tripId === trip?.id;
  const activeTrip = trip?.status === "in_progress";

  function toggle() {
    if (enabled) { setSession(null); setFix(null); setSync(null); setError(""); return; }
    if (!allowed) return;
    if (!window.isSecureContext) { setError("Location requires HTTPS or localhost."); return; }
    if (!navigator.geolocation) { setError("This browser does not provide device location."); return; }
    setError(""); setFix(null); setSync(null);
    setSession({ tripId: trip.id, deviceId: `browser-${crypto.randomUUID()}` });
  }

  useEffect(() => {
    if (!enabled) { setSession(null); setFix(null); setSync(null); return; }
    let alive = true, latest = null, pending = null, sequence = 0;
    let sending = false, requesting = false, lastAttempt = 0, lastTimestamp = 0, interval = 2;
    const controller = new AbortController();
    const onPosition = position => {
      if (!alive) return;
      const next = positionToFix(position);
      if (!next || (latest && next.recorded_at <= latest.recorded_at)) return;
      latest = next; setNow(Date.now() / 1000); setFix(next); setError("");
    };
    const onError = problem => {
      if (!alive) return;
      setError(problem.code === 1 ? "Location permission denied. Allow location in your browser's site settings, then enable GPS again."
        : problem.code === 3 ? "Location timed out. Waiting for a fresh reading." : "Device location unavailable. Check device location services.");
      if (problem.code === 1) setSession(null);
    };
    const options = { enableHighAccuracy: true, maximumAge: 0, timeout: 12000 };
    const watch = navigator.geolocation.watchPosition(onPosition, onError, options);
    // Stationary devices may not emit watch events; explicitly request new fixes.
    const poll = setInterval(() => {
      if (requesting) return;
      requesting = true;
      navigator.geolocation.getCurrentPosition(p => { requesting = false; onPosition(p); }, e => { requesting = false; onError(e); }, options);
    }, 5000);
    const tick = setInterval(async () => {
      const time = Date.now() / 1000;
      setNow(time);
      if (!activeTrip || sending || !latest || time - lastAttempt < interval) return;
      if (pending && time - pending.recorded_at > 15) pending = null;
      if (!pending) {
        if (latest.recorded_at <= lastTimestamp || time - latest.recorded_at > 15 || latest.recorded_at > time
            || latest.accuracy_m > 10000) return;
        pending = { ...latest, device_id: session.deviceId, sequence_number: ++sequence };
        lastTimestamp = latest.recorded_at;
      }
      sending = true; lastAttempt = time;
      try {
        const result = await sendLocation(session.tripId, pending, controller.signal);
        if (!alive) return;
        setSync({ ...result, recorded_at: pending.recorded_at, state: "saved" });
        interval = result.sample_interval_s || 2;
        pending = null;
      } catch (e) {
        if (!alive) return;
        setSync({ state: "error", message: e.status ? e.message : "GPS update not confirmed. Retrying while the reading is fresh." });
        if (e.status) pending = null;
        interval = 5;
      } finally { sending = false; }
    }, 1000);
    return () => {
      alive = false; controller.abort(); navigator.geolocation.clearWatch(watch);
      clearInterval(poll); clearInterval(tick);
    };
  }, [enabled, session, activeTrip]);

  const quality = enabled ? fixQuality(fix, now) : "GPS off";
  const arrival = enabled && sync?.state === "saved" && now - sync.recorded_at <= 15
    && quality === "Location live" ? sync : null;
  return { enabled, allowed, toggle, fix: enabled ? fix : null, quality, error, sync, arrival,
    activeTrip, fresh: enabled && ["Location live", "Low accuracy"].includes(quality) };
}
