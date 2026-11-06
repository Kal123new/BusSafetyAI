import { useEffect, useState } from "react";
import { Bus, CalendarDays, Clock3, Users, RefreshCw, Play, ClipboardCheck } from "lucide-react";
import { getBackendHealth } from "./api/client.js";
import { useTrip } from "./hooks/useTrip.js";
import { useLiveGps } from "./hooks/useLiveGps.js";
import { LiveDetection } from "./components/LiveDetection.jsx";
import { LocationPanel } from "./components/LocationPanel.jsx";
import { StudentManifest } from "./components/StudentManifest.jsx";
import { TopMetric } from "./components/TopMetric.jsx";
import { ReplacementDialog } from './components/ReplacementDialog.jsx';
import { TripActionDialog } from "./components/TripActionDialog.jsx";
import { PostTripWarning } from "./components/PostTripWarning.jsx";
import { useSession } from "./components/SessionGate.jsx";

const ignore = () => {};
const labels = { scheduled: "Pre-departure review", in_progress: "Trip active", awaiting_safety_check: "Inspection required", finished: "Trip finished" };

export default function App() {
  const actor = useSession();
  const state = useTrip();
  const { trip, loading, saving, error } = state;
  const gps = useLiveGps(trip);
  const [action, setAction] = useState(null);
  const [expandedPanel, setExpandedPanel] = useState(null);
  useEffect(() => {
    if (!expandedPanel) return;
    const restore = event => { if (event.key === 'Escape') setExpandedPanel(null); };
    window.addEventListener('keydown', restore);
    return () => window.removeEventListener('keydown', restore);
  }, [expandedPanel]);
  function togglePanel(panel) { setExpandedPanel(current => current === panel ? null : panel); }
  const [actionError, setActionError] = useState("");
  const [visiblePeople, setVisiblePeople] = useState(null);
  const [clock, setClock] = useState(new Date());
  const [health, setHealth] = useState({ online: false, model_loaded: false });
  useEffect(() => {
    let active = true;
    const check = async () => {
      try { const data = await getBackendHealth(); if (active) setHealth({ ...data, online: true }); }
      catch { if (active) setHealth({ online: false, model_loaded: false }); }
    };
    check(); const timer = setInterval(() => { if (!document.hidden) check(); }, 30000);
    const clockTimer = setInterval(() => setClock(new Date()), 1000);
    return () => { active = false; clearInterval(timer); clearInterval(clockTimer); };
  }, []);

  const students = (trip?.students || []).map(s => ({ ...s, id: s.student_id,
    name: `${s.first_name} ${s.last_name}`, status: s.status[0].toUpperCase() + s.status.slice(1),
    dropoff: s.status === "dropped" ? "Dropped" : "-",
    lastSeen: s.dropped_at || s.boarded_at ? new Date((s.dropped_at || s.boarded_at) * 1000).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }) : "-" }));
  const counts = trip ? { total: trip.counts.manifest_total, boarded: trip.counts.on_bus_count,
    pending: trip.counts.pending_count, dropped: trip.counts.dropped_count, absent: trip.counts.absent_count } : { total: "-", boarded: "-", pending: 0, dropped: 0, absent: 0 };
  const ready = trip?.students.every(s => s.reviewed_at && (trip.trip_type !== "dropoff" || ["boarded", "absent"].includes(s.status)));
  const disabled = loading || saving || Boolean(error) || Boolean(action) || state.pending.length > 0;
  function openAction(next) { setActionError(""); setAction({ ...next, trip, onError: setActionError }); }

  return <div className="page-shell"><div className="dashboard-frame connected-dashboard">
    <header className="main-header">
      <div className="route-block"><Bus size={22} /><div><strong>{trip?.trip_code || "No trip selected"} / Bus {trip?.bus_code || "-"}</strong><span>{['demo','sample'].includes(health.mode) ? "Sample - fictional students" : "SafeSense"}</span></div></div>
      <div className="header-metrics">
        <TopMetric icon={Users} value={counts.boarded} sublabel={`/ ${counts.total}`} label="On bus" tone="student-count" />
        <TopMetric icon={Clock3} value={clock.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })} label="Current time" />
        <TopMetric icon={CalendarDays} value={clock.toLocaleDateString()} label="Date" />
      </div>
    </header>
    <section className="trip-toolbar" aria-label="Trip controls">
      <label>Trip<select aria-label="Trip" value={state.selectedId} disabled={disabled} onChange={e => state.selectTrip(e.target.value)}>
        {!state.trips.length && <option value="">No trips available</option>}
        {state.trips.map(t => <option key={t.id} value={t.id}>{t.trip_code}</option>)}
      </select></label>
      <span role="status">{loading ? "Loading trip..." : labels[trip?.status] || "No trip"}</span>
      <button title="Refresh trip" aria-label="Refresh trip" disabled={saving || Boolean(action)} onClick={() => { setActionError(""); state.refresh(); }}><RefreshCw size={20} /></button>
      {actor.role === 'admin' && ['scheduled','in_progress'].includes(trip?.status) && <button disabled={disabled} onClick={() => openAction({kind:'replacement'})}>Replacement bus</button>}
      {trip?.status === "scheduled" && <button disabled={disabled || !ready} onClick={() => openAction({ kind: "start" })}><Play size={18} />Start trip</button>}
      {trip?.status === "awaiting_safety_check" && <button disabled={disabled} onClick={() => openAction({ kind: "finish" })}><ClipboardCheck size={18} />Inspect and finish</button>}
    </section>
    {(error || actionError) && <div role="alert" className="connection-error">{error || actionError}{error && " Displayed records may be outdated; changes are disabled."}</div>}
    {!action && state.pending.length > 0 && <section className="pending-writes" aria-label="Unconfirmed saves"><h2>Unconfirmed saves</h2>{state.pending.map(item => <div key={item.key}><span>{item.action} - {new Date(item.createdAt).toLocaleString()}</span><button disabled={saving} onClick={() => state.recover(item)}>Retry saved request</button><button disabled={saving} onClick={() => window.confirm('Discard this unconfirmed request? Check the saved trip first; this does not undo a server-side change.') && state.recover(item, true)}>Discard after review</button></div>)}</section>}
    {!loading && !error && !trip && <p>No trips scheduled. Ask an administrator to configure a service plan and school calendar in Administration.</p>}
    <main className={`content-grid${expandedPanel ? ` focused-panel focus-${expandedPanel}` : ''}`}>
      <StudentManifest students={students} counts={counts} trip={trip} disabled={disabled}
        expanded={expandedPanel === 'manifest'} onToggleExpand={() => togglePanel('manifest')}
        onStatusChange={(id, status) => openAction({ kind: "attendance", student: students.find(s => s.id === id), status })} />
      <LiveDetection expanded={expandedPanel === 'camera'} onToggleExpand={() => togglePanel('camera')} backendOnline={health.online} modelLoaded={Boolean(health.model_loaded)} onCameraStatusChange={ignore} onDetections={ignore} onObservation={setVisiblePeople} />
      <LocationPanel expanded={expandedPanel === 'location'} onToggleExpand={() => togglePanel('location')} trip={trip} gps={gps} disabled={disabled} onPlanRoute={async strategy => {
        setActionError(''); try { await state.save('route', { expected_version: trip.version, strategy }, crypto.randomUUID()); }
        catch (e) { setActionError(e.message); }
      }} />
    </main>
    {trip?.status === 'finished' && <PostTripWarning key={trip.id} tripId={trip.id} owner={actor.id} count={visiblePeople} />}
    {visiblePeople !== null && trip && trip.status !== 'finished' && visiblePeople !== trip.counts.on_bus_count && <div className="connection-error" role="alert">Check passenger count: {trip.counts.on_bus_count} marked onboard; {visiblePeople} visible people. Camera detections may include adults or miss occluded passengers.</div>}
    {action?.kind === 'replacement' && <ReplacementDialog trip={action.trip} save={state.save} refresh={state.refresh} close={() => {setAction(null);state.refresh();}} />}
    {action && action.kind !== 'replacement' && <TripActionDialog action={action} trip={action.trip} motion={trip?.motion} arrival={gps.arrival} save={state.save} refresh={state.refresh} close={() => { setAction(null); state.refresh(); }} />}
  </div></div>;
}
