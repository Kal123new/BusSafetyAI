import { useEffect, useRef, useState } from 'react';
import { ClipboardCheck } from 'lucide-react';

export function PostTripWarning({ tripId, owner, count }) {
  const key = `safesense:inspection-warning:${owner}:${tripId}`;
  const [latched, setLatched] = useState(() => {
    try { return Boolean(localStorage.getItem(key)); } catch { return false; }
  });
  const [reviewing, setReviewing] = useState(false);
  const [checked, setChecked] = useState(false);
  const dialog = useRef(null);
  useEffect(() => { if (reviewing) dialog.current?.showModal(); }, [reviewing]);
  useEffect(() => {
    if (count > 0) {
      setLatched(true);
      try { localStorage.setItem(key, String(Date.now())); } catch { /* Keep the visible warning when storage is unavailable. */ }
    }
  }, [count, key]);
  if (!latched && !(count > 0)) return null;
  return <section className="connection-error" role="alert">
    <strong>Person detected after trip completion. Check the bus.</strong>
    <p>{count === null ? 'Camera count unavailable. Physical inspection is still required.' : `${count} people currently visible. Camera counts do not certify an empty bus.`}</p>
    <button onClick={() => { setChecked(false); setReviewing(true); }}><ClipboardCheck size={18} />Record recheck</button>
    {reviewing && <dialog ref={dialog} className="trip-dialog" aria-label="Recheck bus" onCancel={() => setReviewing(false)}>
      <h2>Physical recheck</h2>
      <label className="check-row"><input type="checkbox" checked={checked} onChange={e => setChecked(e.target.checked)} />I physically rechecked the entire bus and confirmed nobody remains.</label>
      {count > 0 && <p>People are still detected. Keep checking the bus and camera view.</p>}
      <button onClick={() => setReviewing(false)}>Cancel</button>
      <button disabled={!checked || count > 0} onClick={() => {
        try { localStorage.removeItem(key); } catch { /* The warning can return on reload if storage is unavailable. */ }
        setLatched(false); setReviewing(false);
      }}>Confirm recheck</button>
    </dialog>}
  </section>;
}
