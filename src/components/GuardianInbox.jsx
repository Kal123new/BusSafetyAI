import { useEffect, useState } from 'react';
import { Check, RefreshCw } from 'lucide-react';
import { requestApi } from '../api/client.js';

export function GuardianInbox() {
  const [items, setItems] = useState([]), [error, setError] = useState('');
  async function refresh() {
    try { setItems(await requestApi('/api/v1/inbox')); setError(''); }
    catch (e) { setError(e.message); }
  }
  useEffect(() => { refresh(); const timer = setInterval(refresh, 15000); return () => clearInterval(timer); }, []);
  async function read(id) {
    try { await requestApi(`/api/v1/inbox/${id}/read`, { method: 'POST' }); await refresh(); }
    catch (e) { setError(e.message); }
  }
  return <main className="admin-page"><header><h1>Family updates</h1><button onClick={refresh} title="Refresh inbox" aria-label="Refresh inbox"><RefreshCw size={20} /></button></header>
    {error && <p role="alert">{error}</p>}{!items.length && !error && <p>No updates yet.</p>}
    <ul className="inbox-list">{items.map(item => <li key={item.id}><div><time>{new Date(item.created_at * 1000).toLocaleString()}</time><p>{item.message}</p></div>
      <button disabled={Boolean(item.read_at)} onClick={() => read(item.id)}><Check size={18} />{item.read_at ? 'Read' : 'Mark read'}</button></li>)}</ul>
  </main>;
}
