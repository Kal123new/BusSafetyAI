import { useCallback, useEffect, useRef, useState } from "react";
import { getTrip, listTrips, saveTripAction } from "../api/client.js";
import { useSession } from '../components/SessionGate.jsx';
import { getPendingWrites, rememberWrite, forgetWrite } from '../api/pendingWrites.js';

export function useTrip() {
  const actor = useSession();
  const owner = actor?.id || 'local-demo';
  const [pending, setPending] = useState([]);
  const [trips, setTrips] = useState([]);
  const [trip, setTrip] = useState(null);
  const [selectedId, setSelectedId] = useState("");
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const revision = useRef(0);
  const selected = useRef("");
  const locked = useRef(false);
  const loadPending = useCallback(async () => { setPending(await getPendingWrites(owner)); }, [owner]);
  useEffect(() => { loadPending().catch(() => setError('Browser storage unavailable; save recovery requires IndexedDB.')); }, [loadPending]);
  const refresh = useCallback(async () => {
    if (locked.current) return;
    const ticket = ++revision.current;
    try {
      const items = await listTrips();
      const id = items.some(t => t.id === selected.current) ? selected.current : items[0]?.id || "";
      const next = id ? await getTrip(id) : null;
      if (ticket !== revision.current) return;
      selected.current = id;
      setSelectedId(id); setTrips(items); setTrip(next); setError("");
    } catch (e) {
      if (ticket === revision.current) setError(e.status === 401 ? "Your access token is missing or revoked. Sign out and sign in again." : e.message);
    } finally { if (ticket === revision.current) setLoading(false); }
  }, []);
  useEffect(() => {
    refresh(); const timer = setInterval(refresh, 10000);
    return () => { clearInterval(timer); revision.current++; };
  }, [refresh]);
  function selectTrip(id) {
    selected.current = id;
    setSelectedId(id); setTrip(null); setLoading(true); refresh();
  }
  async function save(action, body, key) {
    if (locked.current) throw new Error("An update is already being saved");
    locked.current = true; revision.current++; setSaving(true);
    try {
      await rememberWrite({ key, owner, tripId: selected.current, action, body, createdAt: Date.now() });
      const next = await saveTripAction(selected.current, action, body, key);
      await forgetWrite(key); setTrip(next); setError(""); return next;
    } catch (e) {
      if (e.status) await forgetWrite(key);
      throw e;
    } finally { locked.current = false; setSaving(false); await loadPending(); }
  }
  async function recover(item, discard = false) {
    if (locked.current) return;
    locked.current = true; revision.current++; setSaving(true);
    let succeeded = false;
    try {
      if (!discard) await saveTripAction(item.tripId, item.action, item.body, item.key);
      await forgetWrite(item.key); setError(''); succeeded = true;
    } catch (e) { setError(`Unconfirmed save: ${e.message}. Review before discarding or correcting it.`); }
    finally { locked.current = false; setSaving(false); await loadPending(); }
    if (succeeded) await refresh();
  }
  return { trips, trip, selectedId, selectTrip, refresh, save, loading, saving, error, pending, recover };
}
