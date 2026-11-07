"""Canonical JSON serialization for SatDeed records.

Implements the subset of RFC 8785 (JSON Canonicalization Scheme) that SatDeed
records are permitted to use. The subset is deliberately narrow so that an
independent implementation in another language can reproduce it byte for byte
without carrying a full JCS library.

Permitted value types: object, array, string, integer, boolean, null.

Floating point numbers are NOT permitted anywhere in a SatDeed record. Their
canonical form under RFC 8785 depends on the ECMAScript number-to-string
algorithm, which is a common source of cross-language disagreement, and no
field in the v0.1 record format needs one. Quantities that would otherwise be
fractional are expressed as integers in a stated minor unit.
"""

from __future__ import annotations

import json
import re
from typing import Any

__all__ = ["canonicalize", "canonical_bytes", "CanonicalizationError"]

# RFC 8785 requires integers to be representable exactly as IEEE 754 doubles.
_MAX_SAFE_INT = 2**53 - 1
_MIN_SAFE_INT = -(2**53 - 1)

_INVALID_SURROGATE = re.compile(r"[\ud800-\udfff]")


class CanonicalizationError(ValueError):
    """Raised when a value cannot be canonicalized under the SatDeed subset."""


def _check_string(value: str, path: str) -> None:
    if _INVALID_SURROGATE.search(value):
        raise CanonicalizationError(
            f"{path}: string contains an unpaired surrogate code point"
        )


def _check(value: Any, path: str = "$") -> None:
    if value is None or isinstance(value, bool):
        return
    if isinstance(value, int):
        if not (_MIN_SAFE_INT <= value <= _MAX_SAFE_INT):
            raise CanonicalizationError(
                f"{path}: integer {value} is outside the safe range "
                f"[{_MIN_SAFE_INT}, {_MAX_SAFE_INT}]"
            )
        return
    if isinstance(value, float):
        raise CanonicalizationError(
            f"{path}: floating point numbers are not permitted in SatDeed records"
        )
    if isinstance(value, str):
        _check_string(value, path)
        return
    if isinstance(value, list):
        for i, item in enumerate(value):
            _check(item, f"{path}[{i}]")
        return
    if isinstance(value, dict):
        for key in value:
            if not isinstance(key, str):
                raise CanonicalizationError(f"{path}: object keys must be strings")
            _check_string(key, f"{path}.{key}")
        for key, item in value.items():
            _check(item, f"{path}.{key}")
        return
    raise CanonicalizationError(f"{path}: unsupported type {type(value).__name__}")


def canonicalize(value: Any) -> str:
    """Return the canonical JSON text for ``value``.

    Object members are ordered by the code point sequence of their UTF-16
    representation, as required by RFC 8785. Python sorts ``str`` by Unicode
    code point, which differs from UTF-16 order only for keys containing
    characters above U+FFFF, so those are reordered explicitly.
    """
    _check(value)
    return _serialize(value)


def _utf16_sort_key(key: str) -> tuple:
    return tuple(key.encode("utf-16-be"))


def _serialize(value: Any) -> str:
    if value is None:
        return "null"
    if value is True:
        return "true"
    if value is False:
        return "false"
    if isinstance(value, int):
        return str(value)
    if isinstance(value, str):
        # json.dumps with ensure_ascii=False produces the RFC 8785 escape set:
        # it escapes only the two mandatory characters and the C0 controls.
        return json.dumps(value, ensure_ascii=False)
    if isinstance(value, list):
        return "[" + ",".join(_serialize(v) for v in value) + "]"
    if isinstance(value, dict):
        members = sorted(value.items(), key=lambda kv: _utf16_sort_key(kv[0]))
        return (
            "{"
            + ",".join(f"{_serialize(k)}:{_serialize(v)}" for k, v in members)
            + "}"
        )
    raise CanonicalizationError(f"unsupported type {type(value).__name__}")


def canonical_bytes(value: Any) -> bytes:
    """Return the canonical JSON encoding of ``value`` as UTF-8 bytes."""
    return canonicalize(value).encode("utf-8")
