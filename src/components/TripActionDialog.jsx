import { useEffect, useRef, useState } from "react";
import { X, Check } from "lucide-react";

export function TripActionDialog({ action, trip, save, close, refresh, motion, arrival }) {
  const dialog = useRef(null);
  const request = useRef(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [uncertain, setUncertain] = useState(false);
  const [now, setNow] = useState(Date.now() / 1000);
  const isAttendance = action.kind === "attendance";
  const isFinish = action.kind === "finish";
  const motionFresh = motion?.recorded_at && now - motion.recorded_at <= 15;
  const stationary = motionFresh && motion.status === 'stationary';
  const moving = motionFresh && motion.status === 'moving';
  const destination = action.status === 'Dropped' ? action.student?.dropoff_stop_id : action.student?.pickup_stop_id;
  const atStop = arrival?.arrival_status === 'arrived' && arrival.trip_stop_id === destination && now - arrival.recorded_at <= 15;
  const needsOverride = isAttendance && trip.status === "in_progress" && !atStop;
  const title = isAttendance ? `${action.status} - ${action.student.name}` : isFinish ? "Final bus inspection" : "Start trip";
  useEffect(() => { dialog.current.showModal(); }, []);
  useEffect(() => { const timer = setInterval(() => setNow(Date.now() / 1000), 1000); return () => clearInterval(timer); }, []);
  async function submit(event) {
    event.preventDefault();
    if (busy) return;
    if (!request.current) {
      const form = new FormData(event.currentTarget);
      const body = { expected_version: trip.version, operator_confirmed_stopped: form.has("stopped") };
      if (isAttendance) Object.assign(body, { status: action.status.toLowerCase(), override_reason: form.get("reason") || "" });
      else if (isFinish) Object.assign(body, { physically_inspected: form.has("inspected"), physically_empty: form.has("empty"), notes: form.get("notes") });
      else body.route_confirmed = form.has("route");
      request.current = { body, key: crypto.randomUUID(), path: isAttendance ? `students/${action.student.id}` : action.kind };
    }
    setBusy(true); setError("");
    try {
      const { path, body, key } = request.current;
      await save(path, body, key); close();
    } catch (e) {
      if (e.status) { close(); await refresh(); action.onError(e.message); }
      else { setUncertain(true); setError("Save not confirmed. Retry the same request, or close and refresh to check its status."); }
    } finally { setBusy(false); }
  }
  return <dialog ref={dialog} className="trip-dialog" aria-labelledby="action-title"
    onCancel={event => { if (busy) event.preventDefault(); else close(); }}>
    <form onSubmit={submit}>
      <header><h2 id="action-title">{title}</h2><button type="button" aria-label="Close" title="Close" disabled={busy} onClick={close}><X size={20} /></button></header>
      <fieldset disabled={busy || uncertain}>
        {stationary ? <p className="green">GPS indicates stationary.</p> : moving ? <p className="action-error">GPS indicates movement. Wait until the bus is stopped.</p> : <label className="check-row"><input name="stopped" type="checkbox" required />The bus is stopped.</label>}
        {!isAttendance && !isFinish && <label className="check-row"><input name="route" type="checkbox" required />I have reviewed the route and stopping locations.</label>}
        {needsOverride && <label>Manual stop confirmation / GPS override reason<textarea name="reason" minLength={10} maxLength={500} required /></label>}
        {isFinish && <>
          <label className="check-row"><input name="inspected" type="checkbox" required />I physically inspected the entire bus.</label>
          <label className="check-row"><input name="empty" type="checkbox" required />I confirm nobody remains inside.</label>
          <label>Inspection notes<textarea name="notes" minLength={5} maxLength={1000} required /></label>
        </>}
      </fieldset>
      {error && <p role="alert" className="action-error">{error}</p>}
      <footer><button type="button" disabled={busy} onClick={close}>Cancel</button><button type="submit" disabled={busy || moving}><Check size={18} />{busy ? "Saving..." : uncertain ? "Retry same request" : "Confirm"}</button></footer>
    </form>
  </dialog>;
}
