"""Canonical, secret-free identity primitives for replayable research state."""

from __future__ import annotations

import hashlib
import json
import math
import re
from collections.abc import Iterator, Mapping
from typing import Any


_ID_RE = re.compile(r"^[a-z][a-z0-9]*(?:[-_][a-z0-9]+)*$")
_SECRET_KEY_RE = re.compile(r"(?:api[_-]?key|auth[_-]?token|access[_-]?token|secret|password|credential)", re.IGNORECASE)
_SECRET_TEXT_RE = re.compile(r"(?:api[_-]?key|auth[_-]?token|access[_-]?token|password)\s*[:=]", re.IGNORECASE)
_WINDOWS_PATH_RE = re.compile(r"^[A-Za-z]:[\\/]")


class FrozenMapping(Mapping[str, Any]):
    """A recursively frozen, deterministic string-key mapping."""

    __slots__ = ("_items", "_lookup")

    def __init__(self, items: tuple[tuple[str, Any], ...]):
        self._items = tuple(items)
        self._lookup = {key: value for key, value in self._items}

    def __getitem__(self, key: str) -> Any:
        return self._lookup[key]

    def __iter__(self) -> Iterator[str]:
        return (key for key, _value in self._items)

    def __len__(self) -> int:
        return len(self._items)

    def __repr__(self) -> str:
        return f"FrozenMapping({self._items!r})"


def validate_identifier(value: str, location: str) -> str:
    if not isinstance(value, str) or not _ID_RE.fullmatch(value):
        raise ValueError(f"{location} must be a source-neutral identifier")
    return value


def _validate_string(value: str) -> str:
    if value.startswith("file://") or value.startswith("/") or _WINDOWS_PATH_RE.match(value):
        raise ValueError("machine-local paths are not allowed in research state")
    if _SECRET_TEXT_RE.search(value):
        raise ValueError("credential-like text is not allowed in research state")
    return value


def _freeze(value: Any, *, redact: bool) -> Any:
    if isinstance(value, Mapping):
        if any(not isinstance(key, str) for key in value):
            raise ValueError("canonical research state requires string mapping keys")
        pairs = []
        for key in sorted(value):
            item = value[key]
            if _SECRET_KEY_RE.search(key):
                if redact or item == "[REDACTED]":
                    frozen = "[REDACTED]"
                else:
                    raise ValueError("credential fields are not allowed in research state")
            else:
                frozen = _freeze(item, redact=redact)
            pairs.append((key, frozen))
        return FrozenMapping(tuple(pairs))
    if isinstance(value, (list, tuple)):
        return tuple(_freeze(item, redact=redact) for item in value)
    if isinstance(value, set):
        raise ValueError("unordered sets are not allowed in canonical research state")
    if isinstance(value, float) and not math.isfinite(value):
        raise ValueError("non-finite numbers are not allowed in canonical research state")
    if isinstance(value, str):
        return _validate_string(value)
    if value is None or isinstance(value, (bool, int, float)):
        return value
    raise ValueError(f"unsupported canonical state value: {type(value).__name__}")


def freeze_mapping(value: Mapping[str, Any]) -> FrozenMapping:
    if not isinstance(value, Mapping):
        raise ValueError("state mapping must be an object")
    return _freeze(value, redact=False)


def _thaw(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(key): _thaw(item) for key, item in value.items()}
    if isinstance(value, tuple):
        return [_thaw(item) for item in value]
    return value


def thaw(value: Any) -> Any:
    """Return a detached JSON-compatible representation."""
    return _thaw(value)


def redact_sensitive(value: Any) -> Any:
    return thaw(_freeze(value, redact=True))


def canonical_json(value: Any) -> str:
    frozen = _freeze(value, redact=False)
    return json.dumps(thaw(frozen), ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


def digest_value(value: Any) -> str:
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()
