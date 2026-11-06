"""Explicit durable outbox for an offline operator client, not automatic merging."""
import json
import sqlite3

import httpx


class OfflineQueue:
    def __init__(self, path):
        self.db = sqlite3.connect(path)
        self.db.execute("CREATE TABLE IF NOT EXISTS pending (event_id TEXT PRIMARY KEY, payload TEXT NOT NULL, state TEXT NOT NULL DEFAULT 'queued')")
        self.db.commit()

    def enqueue(self, event):
        payload = json.dumps(event, sort_keys=True)
        existing = self.db.execute("SELECT payload FROM pending WHERE event_id=?", (event["event_id"],)).fetchone()
        if existing and existing[0] != payload:
            raise ValueError("Event ID reused with a different mutation")
        self.db.execute("INSERT OR IGNORE INTO pending(event_id,payload) VALUES (?,?)", (event["event_id"], payload))
        self.db.commit()

    def flush(self, base_url, token, client=None):
        with httpx.Client(timeout=10) if client is None else client as sender:
            for event_id, payload, state in self.db.execute("SELECT event_id,payload,state FROM pending ORDER BY rowid").fetchall():
                if state in {"sent", "discarded"}:
                    continue
                if state == "conflict":
                    return "conflict"
                try:
                    response = sender.post(f"{base_url.rstrip('/')}/api/v1/sync/attendance",
                                           json={"events": [json.loads(payload)]},
                                           headers={"Authorization": f"Bearer {token}"})
                except httpx.HTTPError:
                    return "offline"
                if response.status_code >= 500:
                    return "offline"
                if response.status_code in {401, 403}:
                    return "authentication_required"
                if not response.is_success:
                    self.db.execute("UPDATE pending SET state='conflict' WHERE event_id=?", (event_id,))
                    self.db.commit()
                    return "conflict"
                self.db.execute("UPDATE pending SET state='sent' WHERE event_id=?", (event_id,))
                self.db.commit()
        return "synced"

    def resolve_conflict(self, event_id, *, discard_confirmed=False):
        """Keep the original record; an operator must explicitly authorize discard.

        After reviewing the server snapshot, enqueue a corrected mutation with
        a NEW event ID/version. Never edit and replay the original request.
        """
        if not discard_confirmed:
            raise ValueError("Explicit operator confirmation is required")
        result = self.db.execute("UPDATE pending SET state='discarded' WHERE event_id=? AND state='conflict'", (event_id,))
        if result.rowcount != 1:
            raise ValueError("Conflicting event not found")
        self.db.commit()

    def close(self):
        self.db.close()
