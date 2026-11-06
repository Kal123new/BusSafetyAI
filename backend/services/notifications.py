import time

import httpx
from sqlalchemy import select

from ..models import Guardian, Notification, StudentGuardian


def enqueue(db, event, student_name, shift, trip_type):
    guardians = db.scalars(select(StudentGuardian.guardian_id).where(StudentGuardian.student_id == event.student_id))
    action = "boarded the bus" if event.event_type == "student.boarded" else "was confirmed dropped off"
    for guardian_id in guardians:
        db.add(Notification(event_id=event.id, guardian_id=guardian_id,
                            message=f"{student_name} {action} on the {shift} {trip_type} trip."))


def dispatch(db, settings, client=None, now=None):
    """Durable inbox first. Push is optional, at-least-once, never 'delivered'."""
    now = time.time() if now is None else now
    rows = db.scalars(select(Notification).where(
        Notification.state.in_(["queued", "retry"]), Notification.next_attempt_at <= now
    ).limit(100).with_for_update(skip_locked=True)).all()
    processed = 0
    with httpx.Client(timeout=5) if client is None else client as sender:
        for row in rows:
            row.published_at = row.published_at or now
            guardian = db.get(Guardian, row.guardian_id)
            row.attempts += 1
            if not settings.ntfy_url or not guardian.push_topic:
                row.state = "inbox"
            else:
                try:
                    # Push payload excludes names and location; authenticated inbox holds details.
                    response = sender.post(settings.ntfy_url, json={
                        "topic": guardian.push_topic, "title": "SafeSense update",
                        "message": "A new trip update is available in your private inbox.",
                        "tags": ["bus"],
                    }, headers={"Authorization": f"Bearer {settings.ntfy_token}"} if settings.ntfy_token else {})
                    response.raise_for_status()
                    row.state = "sent"
                    row.last_error = None
                except httpx.HTTPError:
                    row.state = "failed" if row.attempts >= 6 else "retry"
                    row.next_attempt_at = now + min(3600, 5 * 2 ** row.attempts)
                    row.last_error = "push_delivery_failed"
            processed += 1
    return processed
