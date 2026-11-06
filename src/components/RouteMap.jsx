import { useEffect, useRef, useState } from 'react';
import { LocateFixed } from 'lucide-react';
import L from 'leaflet';
import 'leaflet/dist/leaflet.css';

const demo = new Set(['24.4539,54.3773', '24.455,54.379', '24.457,54.382']);
export function RouteMap({ trip, fix, route, capabilities }) {
  const host = useRef(null), map = useRef(null), group = useRef(null);
  const [following, setFollowing] = useState(true);
  const permitted = capabilities && (!capabilities.public_demo_services || trip?.stops.every(s => demo.has(`${s.latitude},${s.longitude}`)));
  useEffect(() => {
    if (!host.current || !trip || !permitted) return;
    const instance = L.map(host.current, { scrollWheelZoom: false, attributionControl: true }).setView([trip.stops[0].latitude, trip.stops[0].longitude], 15);
    map.current = instance; group.current = L.layerGroup().addTo(instance);
    setFollowing(true);
    instance.on('dragstart', () => setFollowing(false));
    if (capabilities.tile_url) L.tileLayer(capabilities.tile_url, { attribution: capabilities.tile_attribution, maxZoom: 19, referrerPolicy: 'strict-origin-when-cross-origin' }).addTo(instance);
    if (capabilities.public_demo_services) instance.setMaxBounds([[24.443, 54.366], [24.467, 54.392]]).setMinZoom(14);
    instance.fitBounds(trip.stops.map(s => [s.latitude, s.longitude]), { padding: [25, 25], maxZoom: 16 });
    const observer = new ResizeObserver(() => instance.invalidateSize()); observer.observe(host.current);
    return () => { observer.disconnect(); instance.remove(); map.current = null; group.current = null; };
  }, [trip?.id, permitted, capabilities?.tile_url, capabilities?.public_demo_services]);
  useEffect(() => {
    const layer = group.current;
    if (!layer || !trip) return;
    layer.clearLayers();
    for (const stop of trip.stops) {
      const text = document.createElement('span'); text.textContent = stop.name;
      L.circleMarker([stop.latitude, stop.longitude], { radius: 7, color: stop.completed_at ? '#19a653' : '#1565c0', fillOpacity: 1 }).bindTooltip(text).addTo(layer);
    }
    if (route?.geometry) L.geoJSON(route.geometry, { style: { color: '#bf7800', weight: 4 } }).addTo(layer);
    if (fix && !capabilities.public_demo_services) {
      L.circle([fix.latitude, fix.longitude], { radius: Math.min(fix.accuracy_m, 10000), color: '#227be0', weight: 1 }).addTo(layer);
      L.circleMarker([fix.latitude, fix.longitude], { radius: 7, color: '#ca244c', fillOpacity: 1, className: 'device-location-marker' }).bindTooltip('Device location').addTo(layer);
    }
  }, [trip, fix, route, capabilities]);
  useEffect(() => {
    if (map.current && fix && following && !capabilities?.public_demo_services) {
      map.current.setView([fix.latitude, fix.longitude], map.current.getZoom(), { animate: false });
    }
  }, [fix, following, capabilities?.public_demo_services]);
  if (!trip) return null;
  return <div className="route-map-wrap">{permitted ? <div ref={host} className="route-map" aria-label="Route map" /> : <p className="gps-warning">Private map service required for these stops.</p>}
    {!capabilities?.public_demo_services && <button type="button" title="Follow my location" aria-label="Follow my location" aria-pressed={following} disabled={!fix} onClick={() => {
      setFollowing(true);
      if (fix) map.current?.setView([fix.latitude, fix.longitude], 16, { animate: false });
    }}><LocateFixed size={20} /></button>}
    <small>{capabilities?.public_demo_services ? 'Fictional demo map - live GPS remains private' : capabilities?.public_live_locations ? 'Public map - location sharing enabled' : capabilities?.tile_url ? 'Route map' : 'Stop positions - background tiles not configured'}</small>
  </div>;
}
