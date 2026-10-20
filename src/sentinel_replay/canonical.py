"""Versioned, type aware serialization for evidence hashes."""

import base64
import hashlib
import json
from datetime import UTC, datetime
from enum import Enum
from typing import Any


class CanonicalizationError(ValueError):
    """A value cannot be represented under the current evidence contract."""


def _normalize(value: object) -> object:
    if value is None:
        return ["null"]
    if isinstance(value, Enum):
        enum_name = f"{type(value).__module__}.{type(value).__qualname__}"
        return ["enum", enum_name, _normalize(value.value)]
    if isinstance(value, bool):
        return ["bool", value]
    if isinstance(value, int):
        return ["int", str(value)]
    if isinstance(value, float):
        raise CanonicalizationError("floating point values are unsupported; use a decimal string")
    if isinstance(value, str):
        return ["str", value]
    if isinstance(value, bytes):
        return ["bytes", base64.b64encode(value).decode("ascii")]
    if isinstance(value, datetime):
        if value.tzinfo is None or value.utcoffset() is None:
            raise CanonicalizationError("datetime must include a timezone")
        utc = value.astimezone(UTC)
        return ["datetime", utc.isoformat(timespec="microseconds")]
    if isinstance(value, (list, tuple)):
        return ["list", [_normalize(item) for item in value]]
    if isinstance(value, dict):
        if not all(isinstance(key, str) for key in value):
            raise CanonicalizationError("map keys must be strings")
        return ["map", [[key, _normalize(value[key])] for key in sorted(value)]]
    raise CanonicalizationError(f"unsupported type: {type(value).__name__}")


def canonical_bytes(value: object) -> bytes:
    """Encode a supported value without ambiguous JSON types or key order."""
    normalized = _normalize(value)
    return json.dumps(normalized, ensure_ascii=False, separators=(",", ":")).encode("utf-8")


def event_digest(value: object) -> str:
    """Return a domain separated SHA-256 digest of a canonical event."""
    payload = b"sentinel-replay:event:v1\x00" + canonical_bytes(value)
    return "sha256:" + hashlib.sha256(payload).hexdigest()


def load_json_unique(text: str) -> Any:
    """Read JSON while rejecting duplicate keys and unsupported floats."""

    def pairs_to_map(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in pairs:
            if key in result:
                raise CanonicalizationError(f"duplicate JSON key: {key}")
            result[key] = value
        return result

    def reject_float(value: str) -> None:
        raise CanonicalizationError(f"floating point value is unsupported: {value}")

    def reject_constant(value: str) -> None:
        raise CanonicalizationError(f"nonfinite JSON value is unsupported: {value}")

    try:
        return json.loads(
            text,
            object_pairs_hook=pairs_to_map,
            parse_float=reject_float,
            parse_constant=reject_constant,
        )
    except json.JSONDecodeError as error:
        raise CanonicalizationError(f"invalid JSON: {error.msg}") from error
