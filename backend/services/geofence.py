from math import asin, cos, radians, sin, sqrt


def distance_m(lat1, lon1, lat2, lon2):
    lat1, lon1, lat2, lon2 = map(radians, (lat1, lon1, lat2, lon2))
    a = sin((lat2 - lat1) / 2) ** 2 + cos(lat1) * cos(lat2) * sin((lon2 - lon1) / 2) ** 2
    return 6371008.8 * 2 * asin(sqrt(min(1, max(0, a))))


def observe(previous, *, now, fix, distance, accuracy, speed):
    """Prototype thresholds. Arrival is not a passenger event."""
    if not 0 <= now - fix <= 15 or accuracy > 25 or speed is None:
        return {"status": "unknown"}
    last = previous.get("last_fix")
    if last is not None and fix <= last:
        return previous
    if last is not None and fix - last > 12:
        previous = {}
    if speed > 1.4:
        return {"status": "outside", "last_fix": fix}
    if previous.get("status") == "arrived" and distance - accuracy <= 80:
        return {"status": "arrived", "last_fix": fix}
    if distance + accuracy > 50 or speed > 1.4:
        return {"status": "outside", "last_fix": fix}
    since = previous.get("since", fix)
    count = previous.get("count", 0) + 1
    return {"status": "arrived" if count >= 3 and fix - since >= 10 else "candidate",
            "since": since, "count": count, "last_fix": fix}
