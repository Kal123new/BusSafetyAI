import { useEffect, useState } from 'react';
import { Plus, ArrowUp, ArrowDown, X, Copy, KeyRound } from 'lucide-react';
import { requestApi } from '../api/client.js';

const empty = { students: [], guardians: [], drivers: [], buses: [], stops: [] };
const fields = {
  guardians: [['display_name', 'Name']], drivers: [['display_name', 'Name']],
  buses: [['bus_code', 'Bus ID'], ['plate_number', 'Plate'], ['passenger_capacity', 'Passenger capacity', 'number']],
  stops: [['name', 'Stop name'], ['latitude', 'Latitude', 'number'], ['longitude', 'Longitude', 'number']],
  students: [['first_name', 'First name'], ['last_name', 'Last name']]
};
const label = row => !row ? 'Unassigned' : row.display_name || row.name || row.bus_code || `${row.first_name} ${row.last_name}`;

export function Administration() {
  const [catalog, setCatalog] = useState(empty), [section, setSection] = useState('service-plans');
  const [plans, setPlans] = useState([]), [editing, setEditing] = useState(null);
  const [accounts, setAccounts] = useState([]), [error, setError] = useState(''), [notice, setNotice] = useState('');
  const [busy, setBusy] = useState(false), [token, setToken] = useState('');
  const [order, setOrder] = useState([]), [assignments, setAssignments] = useState({}), [role, setRole] = useState('driver');
  async function refresh() {
    try { setCatalog(await requestApi('/api/v1/catalog')); setAccounts(await requestApi('/api/v1/accounts')); setPlans(await requestApi('/api/v1/service-plans')); }
    catch (e) { setError(e.message); }
  }
  useEffect(() => { refresh(); }, []);
  async function create(event) {
    event.preventDefault(); const form = event.currentTarget, data = new FormData(form);
    setBusy(true); setError(''); setNotice(''); setToken('');
    try {
      let body;
      if (section === 'service-plans') {
        body = { name: data.get('name'), bus_id: data.get('bus_id'), timezone: data.get('timezone'), start_date: data.get('start_date'), end_date: data.get('end_date'), weekdays: data.getAll('weekdays').map(Number), excluded_dates: data.get('excluded_dates').split(/[\s,]+/).filter(Boolean), active: data.get('active') === 'on', shift: data.get('shift'), trip_type: data.get('trip_type'), stop_ids: order.map(stop => stop.id),
          students: data.getAll('students').map(id => ({ student_id: id, pickup_sequence: order.findIndex(stop => stop.key === data.get(`pickup-${id}`)), dropoff_sequence: order.findIndex(stop => stop.key === data.get(`dropoff-${id}`)) })) };
      } else if (section === 'accounts') {
        body = { display_name: data.get('display_name'), role, subject_id: role === 'admin' ? null : data.get('subject_id') };
      } else {
        body = Object.fromEntries(fields[section].map(([key, , type]) => [key, type === 'number' ? Number(data.get(key)) : data.get(key)]));
        if (section === 'buses') body.default_driver_id = data.get('default_driver_id') || null;
        if (section === 'students') body.guardian_ids = data.getAll('guardian_ids');
      }
      const result = await requestApi(`/api/v1/${section}${section === 'service-plans' && editing ? `/${editing.id}` : ''}`, { method: section === 'service-plans' && editing ? 'PATCH' : 'POST', body: JSON.stringify(body) });
      if (result.token) setToken(result.token);
      form.reset(); setEditing(null); setOrder([]); setAssignments({}); setNotice('Saved successfully.'); await refresh();
    } catch (e) { setError(e.message); }
    finally { setBusy(false); }
  }
  function editPlan(plan) {
    setEditing(plan); setError(''); setNotice('');
    const stops = plan.stop_ids.map(id => ({id, key: crypto.randomUUID()}));
    setOrder(stops);
    setAssignments(Object.fromEntries(plan.students.flatMap(s => [[`${s.student_id}-pickup`, stops[s.pickup_sequence]?.key || ''], [`${s.student_id}-dropoff`, stops[s.dropoff_sequence]?.key || '']])));
    window.scrollTo({top: 0, behavior: 'smooth'});
  }
  function move(index, delta) {
    setOrder(current => { const next = [...current]; [next[index], next[index + delta]] = [next[index + delta], next[index]]; return next; });
  }
  return <main className="admin-page"><h1>Administration</h1>
    <nav className="admin-tabs" aria-label="Record types">{['service-plans', ...Object.keys(fields), 'accounts'].map(key => <button key={key} aria-pressed={section === key} onClick={() => { setSection(key); setEditing(null); setOrder([]); setAssignments({}); setError(''); setNotice(''); setToken(''); }}>{key === 'service-plans' ? 'Service plans' : key}</button>)}</nav>
    {error && <p className="connection-error" role="alert">{error}</p>}{notice && <p role="status">{notice}</p>}
    <form key={`${section}-${editing?.id || "new"}`} onSubmit={create} className="admin-form"><fieldset disabled={busy}>
      <legend>{editing ? 'Edit' : 'New'} {section === 'service-plans' ? 'service plan' : section.replace(/s$/, '')}</legend>
      {fields[section]?.map(([key, name, type]) => <label key={key}>{name}<input name={key} type={type || 'text'} step={key === 'latitude' || key === 'longitude' ? 'any' : '1'} required maxLength={100}
        min={key === 'latitude' ? -90 : key === 'longitude' ? -180 : key === 'passenger_capacity' ? 1 : undefined}
        max={key === 'latitude' ? 90 : key === 'longitude' ? 180 : key === 'passenger_capacity' ? 100 : undefined} /></label>)}
      {section === 'buses' && <label>Default driver<select name="default_driver_id"><option value="">Unassigned</option>{catalog.drivers.map(d => <option key={d.id} value={d.id}>{label(d)}</option>)}</select></label>}
      {section === 'students' && <label>Guardians<select name="guardian_ids" multiple required>{catalog.guardians.map(g => <option key={g.id} value={g.id}>{label(g)}</option>)}</select></label>}
      {section === 'accounts' && <>
        <label>Account name<input name="display_name" required /></label><label>Role<select aria-label="Role" value={role} onChange={e => setRole(e.target.value)}><option>driver</option><option>guardian</option><option>admin</option></select></label>
        {role !== 'admin' && <label>Linked {role}<select aria-label={`Linked ${role}`} name="subject_id" required>{catalog[role === 'driver' ? 'drivers' : 'guardians'].map(row => <option key={row.id} value={row.id}>{label(row)}</option>)}</select></label>}
      </>}
      {section === 'service-plans' && <>
        <p className="wide-field">Set up one plan for each morning or afternoon run. Trips are created automatically on school days. Pausing or editing a plan affects future creation; existing trips keep their saved manifest and driver.</p>
        <label>Plan name<input name="name" defaultValue={editing?.name || ''} required maxLength={100} /></label>
        <label>Bus and default driver<select name="bus_id" defaultValue={editing?.bus_id || ''} required><option value="">Choose an assigned bus</option>{catalog.buses.filter(b => b.default_driver_id || b.id === editing?.bus_id).map(b => <option key={b.id} value={b.id}>{label(b)} — {label(catalog.drivers.find(d => d.id === b.default_driver_id))}</option>)}</select></label>
        {!catalog.buses.some(b => b.default_driver_id) && <p className="wide-field">First create a driver and assign that driver to a bus in the Buses tab.</p>}
        <label>Shift<select name="shift" defaultValue={editing?.shift || 'morning'}><option>morning</option><option>afternoon</option></select></label>
        <label>Trip type<select name="trip_type" defaultValue={editing?.trip_type || 'pickup'}><option value="pickup">Pickup — collect students</option><option value="dropoff">Drop-off — students board at first stop</option></select></label>
        <label>School timezone<input name="timezone" defaultValue={editing?.timezone || Intl.DateTimeFormat().resolvedOptions().timeZone || 'Asia/Dubai'} required placeholder="Asia/Dubai" /></label>
        <label>First service date<input name="start_date" type="date" defaultValue={editing?.start_date || new Date().toLocaleDateString('en-CA')} required /></label>
        <label>Last service date<input name="end_date" type="date" defaultValue={editing?.end_date || ''} required /></label>
        <div className="wide-field"><h2>School days</h2>{['Monday','Tuesday','Wednesday','Thursday','Friday','Saturday','Sunday'].map((day,i) => <label className="check-row" key={day}><input type="checkbox" name="weekdays" value={i} defaultChecked={(editing?.weekdays || [0,1,2,3,4]).includes(i)} />{day}</label>)}</div>
        <label className="wide-field">Holiday dates (YYYY-MM-DD, separated by commas)<input name="excluded_dates" defaultValue={(editing?.excluded_dates || []).join(', ')} placeholder="2026-12-02, 2026-12-03" /></label>
        <label className="check-row"><input name="active" type="checkbox" defaultChecked={editing?.active ?? true} />Enable automatic trips</label>
        <section className="wide-field"><h2>Ordered stops</h2><select aria-label="Add stop" value="" onChange={e => e.target.value && setOrder([...order, { id: e.target.value, key: crypto.randomUUID() }])}><option value="">Add stop...</option>{catalog.stops.map(r => <option key={r.id} value={r.id}>{label(r)}</option>)}</select>
          <ol>{order.map(({id, key}, index) => <li key={key} className="stop-editor"><span>{index}: {label(catalog.stops.find(s => s.id === id))}</span><button type="button" title="Move up" disabled={!index} onClick={() => move(index, -1)}><ArrowUp size={18} /></button><button type="button" title="Move down" disabled={index === order.length - 1} onClick={() => move(index, 1)}><ArrowDown size={18} /></button><button type="button" title="Remove stop" onClick={() => setOrder(order.filter((_, i) => i !== index))}><X size={18} /></button></li>)}</ol>
        </section>
        <section className="wide-field"><h2>Manifest assignments</h2><div className="table-wrap"><table><thead><tr><th>Student</th><th>Pickup</th><th>Drop-off</th></tr></thead><tbody>{catalog.students.map(s => <tr key={s.id}><td><label className="check-row"><input type="checkbox" name="students" value={s.id} defaultChecked={editing?.students.some(a => a.student_id === s.id) || false} />{label(s)}</label></td>
          <td><select name={`pickup-${s.id}`} aria-label={`${label(s)} pickup`} value={assignments[`${s.id}-pickup`] || ''} onChange={e => setAssignments({...assignments, [`${s.id}-pickup`]: e.target.value})}><option value="">Choose stop</option>{order.map(({id, key}, i) => <option key={key} value={key}>{i}: {label(catalog.stops.find(stop => stop.id === id))}</option>)}</select></td>
          <td><select name={`dropoff-${s.id}`} aria-label={`${label(s)} drop-off`} value={assignments[`${s.id}-dropoff`] || ''} onChange={e => setAssignments({...assignments, [`${s.id}-dropoff`]: e.target.value})}><option value="">Choose stop</option>{order.map(({id, key}, i) => <option key={key} value={key}>{i}: {label(catalog.stops.find(stop => stop.id === id))}</option>)}</select></td></tr>)}</tbody></table></div></section>
      </>}
      <button type="submit" disabled={busy || (section === 'service-plans' && order.length < 2)}><Plus size={18} />{busy ? 'Saving...' : editing ? 'Save changes' : section === 'service-plans' ? 'Save service plan' : 'Create'}</button>
    </fieldset></form>
    {section === 'service-plans' && <section><h2>Saved service plans</h2><p>While the server is awake, it checks every minute. After a sleep, today's trips are prepared when the dashboard opens. Past missed days are not generated.</p>{!plans.length && <p>No service plans yet. Add a morning plan and an afternoon plan using the form above.</p>}<ul className="record-list">{plans.map(plan => <li key={plan.id}><div><strong>{plan.name}</strong><p>{label(catalog.buses.find(b => b.id === plan.bus_id))} · {plan.shift} · {plan.active ? 'Enabled' : 'Paused'} · {plan.timezone}</p><p>{plan.start_date} to {plan.end_date}</p>{plan.last_error && <p role="alert">Trip creation needs attention: {plan.last_error}</p>}</div><button type="button" onClick={() => editPlan(plan)}>Edit plan / calendar</button></li>)}</ul>{editing && <button type="button" onClick={() => {setEditing(null);setOrder([]);setAssignments({});}}>Cancel editing</button>}</section>}
    {token && <section className="token-result"><h2><KeyRound size={18} />New access token</h2><p>Shown only here. Share privately with the intended account holder.</p><input readOnly type="password" value={token} aria-label="New access token" /><button onClick={async () => { try { await navigator.clipboard.writeText(token); setNotice('Token copied.'); } catch { setError('Clipboard unavailable. Select the token field to copy it manually.'); } }}><Copy size={18} />Copy token</button></section>}
    {section === 'accounts' ? <ul className="record-list">{accounts.map(a => <li key={a.id}><span>{a.display_name} - {a.role} - {a.active ? 'Active' : 'Revoked'}</span><button disabled={!a.active} onClick={async () => { if (!window.confirm(`Revoke access for ${a.display_name}?`)) return; try { await requestApi(`/api/v1/accounts/${a.id}/revoke`, { method: 'POST' }); await refresh(); } catch (e) { setError(e.message); } }}>Revoke</button></li>)}</ul>
      : section !== 'service-plans' && <ul className="record-list">{catalog[section].map(row => <li key={row.id}><span>{label(row)}{section === 'students' && ` — Guardians: ${(row.guardian_ids || []).map(id => label(catalog.guardians.find(g => g.id === id))).join(', ') || 'None'}`}{section === 'drivers' && ` — Buses: ${catalog.buses.filter(b => b.default_driver_id === row.id).map(b => b.bus_code).join(', ') || 'None'}`}</span>{section === 'buses' && <label>Default driver<select aria-label={`Driver for ${row.bus_code}`} value={row.default_driver_id || ''} disabled={busy} onChange={async e => { setBusy(true); setError(''); try { await requestApi(`/api/v1/buses/${row.id}/driver`, {method: 'PATCH', body: JSON.stringify({default_driver_id: e.target.value || null})}); await refresh(); setNotice('Default driver saved. Existing trips keep their assigned driver.'); } catch(e) {setError(e.message);} finally {setBusy(false);} }}><option value="">Unassigned</option>{catalog.drivers.map(d => <option key={d.id} value={d.id}>{label(d)}</option>)}</select></label>}</li>)}</ul>}
  </main>;
}
