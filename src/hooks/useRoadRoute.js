import { useEffect, useState } from 'react';
import { requestApi } from '../api/client.js';

export function useRoadRoute(trip, gps) {
  const [capabilities, setCapabilities] = useState(null), [route, setRoute] = useState(null);
  const [navigation, setNavigation] = useState(null), [error, setError] = useState('');
  useEffect(() => { let alive = true; requestApi('/api/v1/capabilities').then(v => { if (alive) setCapabilities(v); }).catch(() => {}); return () => { alive = false; }; }, []);
  useEffect(() => {
    let alive = true; setRoute(null); setError('');
    if (trip) requestApi(`/api/v1/trips/${trip.id}/route`).then(v => { if (alive) setRoute(v.route); }).catch(e => { if (alive) setError(e.message); });
    return () => { alive = false; };
  }, [trip?.id, trip?.version]);
  useEffect(() => {
    let alive = true; setNavigation(null);
    if (!trip || trip.status !== 'in_progress' || !gps.fresh || !capabilities?.routing_configured || capabilities.public_demo_services) return;
    async function update() {
      try { const result = await requestApi(`/api/v1/trips/${trip.id}/navigation`); if (alive) { setNavigation(result); setError(''); } }
      catch (e) { if (alive) { setNavigation(null); setError(e.message); } }
    }
    update(); const timer = setInterval(update, 20000);
    return () => { alive = false; clearInterval(timer); };
  }, [trip?.id, trip?.status, trip?.version, gps.fresh, capabilities]);
  const fresh = navigation?.available && Date.now() / 1000 - navigation.calculated_at < 45 && gps.fresh;
  return { capabilities, route, navigation: fresh ? navigation : null, error };
}
