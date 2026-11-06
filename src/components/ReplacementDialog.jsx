import { useEffect, useRef, useState } from 'react';
import { requestApi } from '../api/client.js';

export function ReplacementDialog({trip, save, close, refresh}) {
  const dialog = useRef(null), request = useRef(null);
  const [catalog, setCatalog] = useState(null), [selected, setSelected] = useState([]);
  const [error, setError] = useState(''), [busy, setBusy] = useState(false), [uncertain, setUncertain] = useState(false);
  useEffect(() => { dialog.current.showModal(); requestApi('/api/v1/catalog').then(setCatalog).catch(e => setError(e.message)); }, []);
  const eligible = trip.students.filter(s => ['pending','boarded'].includes(s.status));
  const physical = eligible.some(s => selected.includes(s.student_id) && s.status === 'boarded');
  async function submit(event) {
    event.preventDefault(); if (busy) return;
    if (!request.current) {
      const f = new FormData(event.currentTarget);
      request.current = {key: crypto.randomUUID(), body: {expected_version: trip.version,
        target_bus_id: f.get('bus'), handover_stop_id: f.get('stop'), student_ids: selected,
        reason: f.get('reason'), source_stopped: f.has('source_stopped'), target_stopped: f.has('target_stopped'), handover_confirmed: f.has('handover')}};
    }
    setBusy(true); setError('');
    try { await save('replacement', request.current.body, request.current.key); close(); await refresh(); }
    catch(e) {setError(e.message); if (!e.status) setUncertain(true); else request.current = null;}
    finally {setBusy(false);}
  }
  return <dialog ref={dialog} className="trip-dialog" aria-labelledby="replacement-title" onCancel={e => {if(busy)e.preventDefault();else close();}}><form onSubmit={submit}>
    <header><h2 id="replacement-title">Replacement bus / exceptional trip</h2><button type="button" onClick={close} disabled={busy}>Close</button></header>
    <p>Creates a separate trip and preserves this trip's history. The receiving driver must review the route and press Start trip. The original bus still requires physical inspection when all passengers are resolved.</p>
    <fieldset disabled={busy || uncertain || !catalog}>
      <label>Receiving bus<select name="bus" required><option value="">Choose replacement bus</option>{catalog?.buses.filter(b => b.id !== trip.bus_id && b.default_driver_id && b.default_driver_id !== trip.driver_id).map(b => <option key={b.id} value={b.id}>{b.bus_code} — {catalog.drivers.find(d => d.id === b.default_driver_id)?.display_name} ({b.passenger_capacity} seats)</option>)}</select></label>
      <label>Safe handover / starting stop<select name="stop" required><option value="">Choose an approved stop</option>{catalog?.stops.map(s => <option key={s.id} value={s.id}>{s.name}</option>)}</select></label>
      <p>Select only students who will use the replacement bus. Pending students are reassigned for pickup; they are not marked onboard.</p>
      {eligible.map(s => <label key={s.student_id} className="check-row"><input type="checkbox" checked={selected.includes(s.student_id)} onChange={e => setSelected(e.target.checked ? [...selected,s.student_id] : selected.filter(id => id !== s.student_id))} />{s.first_name} {s.last_name} — {s.status}</label>)}
      <label>Reason<textarea name="reason" required minLength={10} maxLength={500} placeholder="Breakdown, road disruption, or other exceptional circumstances" /></label>
      <label className="check-row"><input type="checkbox" name="source_stopped" required />The original bus is stopped.</label>
      <label className="check-row"><input type="checkbox" name="target_stopped" required />The receiving bus is stopped.</label>
      {physical && <label className="check-row"><input type="checkbox" name="handover" required />Both drivers have confirmed physical handover of every selected onboard student to the receiving bus.</label>}
    </fieldset>
    {error && <p role="alert" className="action-error">{error}</p>}
    <footer><button type="button" onClick={close} disabled={busy}>Cancel</button><button disabled={busy || !catalog || !selected.length}>{busy ? 'Saving...' : uncertain ? 'Retry same request' : 'Confirm replacement trip'}</button></footer>
  </form></dialog>;
}
