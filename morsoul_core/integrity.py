"""Canonical JSON, state hash and HMAC signature for save snapshots.

The HMAC key ships with the game, so the signature is tamper-evidence against casual editing.
It is not a secret and it is not anti-cheat.
"""

import hashlib
import hmac
import json
from typing import Any


def canonical(obj: Any) -> bytes:
    """Sorted keys, compact separators, UTF-8. The same data always gives the same bytes."""
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False).encode(
        "utf-8"
    )


def state_hash(payload: Any) -> str:
    return hashlib.sha256(canonical(payload)).hexdigest()


def sign(snapshot: dict, key: bytes) -> str:
    """HMAC-SHA256 over the whole envelope except the signature field."""
    body = {k: v for k, v in snapshot.items() if k != "signature"}
    return hmac.new(key, canonical(body), hashlib.sha256).hexdigest()


def seal(snapshot: dict, key: bytes) -> dict:
    """The sender fills in stateHash and signature before uploading."""
    snapshot["stateHash"] = state_hash(snapshot["payload"])
    snapshot["signature"] = sign(snapshot, key)
    return snapshot


def verify(snapshot: dict, key: bytes) -> list[str]:
    """Return a list of problems. An empty list means the hash and the signature are fine."""
    problems: list[str] = []
    if snapshot.get("stateHash") != state_hash(snapshot.get("payload")):
        problems.append("stateHash does not match the payload")
    if not hmac.compare_digest(str(snapshot.get("signature", "")), sign(snapshot, key)):
        problems.append("signature does not match")
    return problems
