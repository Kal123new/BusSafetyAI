import { createContext, useContext, useEffect, useState } from 'react';
import { LogOut, Settings, LayoutDashboard, LogIn } from 'lucide-react';
import { getBackendHealth, requestApi, setAccessToken } from '../api/client.js';
import { GuardianInbox } from './GuardianInbox.jsx';
import { Administration } from './Administration.jsx';

const Session = createContext(null);
export const useSession = () => useContext(Session);

export function SessionGate({ children }) {
  const [actor, setActor] = useState(null);
  const [mode, setMode] = useState('production');
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(true);
  const [view, setView] = useState('dashboard');
  const [login, setLogin] = useState(false);
  async function connect() {
    setLoading(true); setError('');
    try {
      const health = await getBackendHealth(); setMode(health.mode);
      setActor(await requestApi('/api/v1/me'));
    } catch (e) { setActor(null); setError(e.status === 401 ? 'Enter your access token.' : e.message); }
    finally { setLoading(false); }
  }
  useEffect(() => { connect(); }, []);
  async function authenticate(e) {
    e.preventDefault(); setAccessToken(new FormData(e.currentTarget).get('token').trim());
    await connect(); setLogin(false);
  }
  const signOut = () => { setAccessToken(''); setActor(null); setLogin(true); setView('dashboard'); };
  if (loading) return <main className="session-screen"><h1>SafeSense</h1><p>Connecting...</p></main>;
  if (!actor || login) return <main className="session-screen"><h1>SafeSense</h1>
    <form onSubmit={authenticate}><label>Access token<input name="token" type="password" autoComplete="off" required /></label><button><LogIn size={18} />Sign in</button></form>
    {error && <p role="alert">{error}</p>}
    {mode === 'demo' && <button onClick={() => { setAccessToken(''); setLogin(false); connect(); }}>Return to local demo</button>}
    <button onClick={connect}>Reconnect</button>
  </main>;
  return <Session.Provider value={actor}><nav className="app-nav" aria-label="Application">
    <strong>SafeSense</strong><span>{actor.role === 'admin' && mode === 'demo' && actor.id === 'local-demo' ? 'Local demo administrator' : actor.role}</span>
    {actor.role !== 'guardian' && <button onClick={() => setView('dashboard')}><LayoutDashboard size={18} />Dashboard</button>}
    {actor.role === 'admin' && <button onClick={() => setView('admin')}><Settings size={18} />Administration</button>}
    <button onClick={signOut}><LogOut size={18} />{actor.id === 'local-demo' ? 'Switch account' : 'Sign out'}</button>
  </nav><div key={actor.id}>{actor.role === 'guardian' ? <GuardianInbox /> : view === 'admin' ? <Administration /> : children}</div></Session.Provider>;
}
