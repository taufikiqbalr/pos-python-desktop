from __future__ import annotations

import json
from urllib import error, request

from app.config import (
    SYNC_API_TOKEN,
    SYNC_API_URL,
    SYNC_ENABLED,
    SYNC_TIMEOUT_SECONDS,
)
from app.identity import TERMINAL_IDENTITY


def enqueue_outbox(
    conn,
    *,
    event_type: str,
    aggregate_type: str,
    aggregate_id: str | int,
    payload: dict,
) -> int:
    envelope = {
        "event_type": event_type,
        "aggregate_type": aggregate_type,
        "aggregate_id": str(aggregate_id),
        "terminal": TERMINAL_IDENTITY.as_dict(),
        "payload": payload,
    }
    cur = conn.execute(
        """
        INSERT INTO integration_outbox(
            event_type, aggregate_type, aggregate_id,
            store_id, register_id, device_id, payload_json
        ) VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (
            event_type,
            aggregate_type,
            str(aggregate_id),
            TERMINAL_IDENTITY.store_id,
            TERMINAL_IDENTITY.register_id,
            TERMINAL_IDENTITY.device_id,
            json.dumps(envelope, ensure_ascii=False, sort_keys=True),
        ),
    )
    return int(cur.lastrowid)


class SyncService:
    def __init__(self, db) -> None:
        self.db = db

    def pending_count(self) -> int:
        with self.db.connect() as conn:
            return int(
                conn.execute(
                    "SELECT COUNT(*) FROM integration_outbox WHERE status IN ('PENDING','FAILED')"
                ).fetchone()[0]
            )

    def list_pending(self, limit: int = 50) -> list[dict]:
        with self.db.connect() as conn:
            rows = conn.execute(
                """
                SELECT * FROM integration_outbox
                WHERE status IN ('PENDING','FAILED')
                ORDER BY id
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
        return [dict(row) for row in rows]

    def sync_once(self, limit: int = 50) -> dict:
        if not SYNC_ENABLED:
            return {"enabled": False, "sent": 0, "failed": 0, "pending": self.pending_count()}
        if not SYNC_API_URL:
            raise ValueError("POS_SYNC_API_URL wajib diisi jika POS_SYNC_ENABLED=true")

        sent = 0
        failed = 0
        for event in self.list_pending(limit):
            try:
                self._send_event(event)
            except Exception as exc:
                failed += 1
                with self.db.connect() as conn:
                    conn.execute(
                        """
                        UPDATE integration_outbox
                        SET status='FAILED', attempts=attempts+1, last_error=?
                        WHERE id=?
                        """,
                        (str(exc)[:1000], event["id"]),
                    )
            else:
                sent += 1
                with self.db.connect() as conn:
                    conn.execute(
                        """
                        UPDATE integration_outbox
                        SET status='SENT', attempts=attempts+1,
                            last_error=NULL, sent_at=CURRENT_TIMESTAMP
                        WHERE id=?
                        """,
                        (event["id"],),
                    )

        return {
            "enabled": True,
            "sent": sent,
            "failed": failed,
            "pending": self.pending_count(),
        }

    @staticmethod
    def _send_event(event: dict) -> None:
        body = event["payload_json"].encode("utf-8")
        headers = {
            "Content-Type": "application/json",
            "Idempotency-Key": f"pos-outbox-{event['id']}",
        }
        if SYNC_API_TOKEN:
            headers["Authorization"] = f"Bearer {SYNC_API_TOKEN}"

        req = request.Request(
            f"{SYNC_API_URL}/api/v1/pos/events",
            data=body,
            headers=headers,
            method="POST",
        )
        try:
            with request.urlopen(req, timeout=SYNC_TIMEOUT_SECONDS) as response:
                if response.status < 200 or response.status >= 300:
                    raise RuntimeError(f"Sync endpoint HTTP {response.status}")
        except error.HTTPError as exc:
            raise RuntimeError(f"Sync endpoint HTTP {exc.code}") from exc
        except error.URLError as exc:
            raise RuntimeError(f"Sync endpoint tidak dapat diakses: {exc.reason}") from exc
