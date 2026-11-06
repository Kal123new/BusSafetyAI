import { Navigation, MapPin, CheckCircle2 } from "lucide-react";
import { distanceMeters } from "../utils/gps.js";
import { useState } from 'react';
import { RouteMap } from './RouteMap.jsx';
import { useRoadRoute } from '../hooks/useRoadRoute.js';
import { PanelExpandButton } from './PanelExpandButton.jsx';

export function LocationPanel({ trip, gps, onPlanRoute, disabled, expanded, onToggleExpand }) {
  const road = useRoadRoute(trip, gps);
  const [strategy, setStrategy] = useState('fixed');
  const stops = trip?.stops || [];
  const completed = stops.filter(s => s.completed_at).length;
  const next = stops.find(s => !s.completed_at);
  const distance = gps.fresh && next ? distanceMeters(gps.fix, next) : null;
  const arrival = gps.arrival?.trip_stop_id === next?.id ? gps.arrival?.arrival_status : null;
  return <section className="panel location-panel saved-route-panel">
    <header className="panel-header"><h2><Navigation size={14} />Location</h2><span role="status">{gps.quality}</span><PanelExpandButton label="location" expanded={expanded} onToggle={onToggleExpand} /></header>
    <div className="gps-readout">
      <label className="gps-toggle"><input type="checkbox" role="switch" aria-label="Live GPS" checked={gps.enabled} disabled={!gps.allowed} onChange={gps.toggle} />Live GPS</label>
      {gps.enabled && <>
        {road.capabilities?.public_live_locations && <p className="gps-mode">OpenStreetMap receives the viewed area. OSRM receives location and next-stop coordinates for driving estimates.</p>}
        {arrival && <p className="gps-arrival">{({ arrived: "Arrival confirmed", candidate: "Confirming arrival...", outside: "Outside stop zone", unknown: "Arrival not confirmed" })[arrival] || "No remaining stops"}</p>}
      </>}
      {gps.error && <p className="gps-warning" role="alert">{gps.error}</p>}
      {gps.enabled && gps.sync?.state === "error" && <p className="gps-warning" role="alert">{gps.sync.message}</p>}
    </div>
    <RouteMap trip={trip} fix={gps.fresh ? gps.fix : null} route={road.navigation || road.route} capabilities={road.capabilities} />
    {trip?.status === 'scheduled' && <div className="route-planning"><select aria-label="Route ordering" value={strategy} onChange={e => setStrategy(e.target.value)}><option value="fixed">Keep stop order</option><option value="nearest">Nearest first</option><option value="ortools">Optimize order</option></select><button disabled={disabled || !road.capabilities?.routing_configured} onClick={() => onPlanRoute(strategy)}>Calculate route</button></div>}
    {road.error && <p className="gps-warning" role="alert">{road.error}</p>}
    <ol className="saved-stops">{stops.map(s => <li key={s.id} className={s.completed_at ? "completed" : ""}>
      {s.completed_at ? <CheckCircle2 size={20} /> : <MapPin size={20} />}<span>{s.name}</span>
    </li>)}</ol>
    <div className="route-progress"><div><span>Stops resolved</span><b>{completed} / {stops.length}</b></div><div className="progress"><span style={{ width: `${stops.length ? completed / stops.length * 100 : 0}%` }} /></div></div>
    <div className="current-location"><small>Next unresolved stop</small><strong>{next?.name || (stops.length ? "All stops resolved" : "No route selected")}</strong></div>
    <div className="location-stats"><div><small>{road.navigation ? 'Road distance to next stop' : 'Straight-line distance'}</small><b>{road.navigation ? `${(road.navigation.distance_m / 1000).toFixed(1)} km` : distance === null ? 'No fresh location' : distance >= 1000 ? `${(distance / 1000).toFixed(1)} km` : `${Math.round(distance)} m`}</b></div><div><small>{road.navigation ? 'Driving ETA (no traffic)' : road.route ? 'Planned total drive' : 'Road ETA'}</small><b>{road.navigation ? `${Math.ceil(road.navigation.eta_s / 60)} min` : road.route ? `${Math.ceil(road.route.eta_s / 60)} min` : 'Route not calculated'}</b></div></div>
  </section>;
}
