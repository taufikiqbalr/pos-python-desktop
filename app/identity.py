from __future__ import annotations

from dataclasses import dataclass

from app.config import DEVICE_ID, REGISTER_ID, STORE_ID


@dataclass(frozen=True)
class TerminalIdentity:
    store_id: str
    register_id: str
    device_id: str

    def as_dict(self) -> dict:
        return {
            "store_id": self.store_id,
            "register_id": self.register_id,
            "device_id": self.device_id,
        }


TERMINAL_IDENTITY = TerminalIdentity(
    store_id=STORE_ID,
    register_id=REGISTER_ID,
    device_id=DEVICE_ID,
)
