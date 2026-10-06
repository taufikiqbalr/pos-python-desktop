from __future__ import annotations

import json


def write_audit(
    conn,
    *,
    user_id: int | None,
    action: str,
    entity_type: str,
    entity_id: str | int | None = None,
    metadata: dict | None = None,
) -> None:
    conn.execute(
        """
        INSERT INTO audit_events(user_id, action, entity_type, entity_id, metadata_json)
        VALUES (?, ?, ?, ?, ?)
        """,
        (
            user_id,
            action,
            entity_type,
            None if entity_id is None else str(entity_id),
            json.dumps(metadata or {}, ensure_ascii=False, sort_keys=True),
        ),
    )
