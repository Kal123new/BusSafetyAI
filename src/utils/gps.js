export function distanceMeters(a, b) {
  const rad = degrees => degrees * Math.PI / 180;
  const dLat = rad(b.latitude - a.latitude), dLon = rad(b.longitude - a.longitude);
  const h = Math.sin(dLat / 2) ** 2 + Math.cos(rad(a.latitude)) * Math.cos(rad(b.latitude)) * Math.sin(dLon / 2) ** 2;
  return 6371008.8 * 2 * Math.asin(Math.sqrt(Math.min(1, Math.max(0, h))));
}

export function positionToFix(position) {
  const { latitude, longitude, accuracy, speed } = position.coords;
  if (![latitude, longitude, accuracy, position.timestamp].every(Number.isFinite)
      || Math.abs(latitude) > 90 || Math.abs(longitude) > 180 || accuracy < 0 || position.timestamp <= 0) return null;
  return { latitude, longitude, accuracy_m: accuracy, recorded_at: position.timestamp / 1000,
    speed_mps: Number.isFinite(speed) && speed >= 0 && speed <= 80 ? speed : null };
}

export function fixQuality(fix, now = Date.now() / 1000) {
  if (!fix) return "Waiting for location";
  if (now - fix.recorded_at > 15 || now < fix.recorded_at) return "Location stale";
  if (fix.accuracy_m > 25) return "Low accuracy";
  return "Location live";
}
