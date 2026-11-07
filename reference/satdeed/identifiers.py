"""Deterministic SatDeed asset identifiers.

An identifier must be stable for the life of the asset, so it cannot be
derived from anything that changes: not an inscription number, not a wallet
address, not a storage URL, not a row number in the issuer's database.

It is therefore derived from the issuer namespace plus the attributes that
identify the physical thing, under a per asset salt:

    asset_uid = tagged_hash(TAG_ASSET_ID,
                            utf8(namespace) || 0x00 || salt || canonical(attrs))

The salt is what makes this safe to publish. A vehicle identification number
carries far less entropy than its 17 characters suggest once make, model and
year are known, so an unsalted derivation would let anyone confirm a guess
against the public identifier. The issuer keeps the salt and discloses it only
to parties entitled to confirm which asset the record describes.

The display form is a Crockford base32 encoding of the first 20 bytes of the
uid with a four character checksum, which gives a string that survives being
read aloud, written on a windscreen sticker or typed from a printed document.
"""

from __future__ import annotations

import secrets

from .canonical import canonical_bytes
from .hashing import TAG_ASSET_ID, TAG_ASSET_ID_CHECKSUM, tagged_hash

__all__ = [
    "ALPHABET",
    "derive_asset_uid",
    "display_form",
    "parse_display_form",
    "new_salt",
    "InvalidIdentifier",
]

# Crockford base32: no I, L, O or U, so the characters most often confused in
# handwriting and speech cannot appear.
ALPHABET = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"
_DECODE = {c: i for i, c in enumerate(ALPHABET)}
# Accept the usual misreadings on input, reject nothing the user did not cause.
_DECODE.update({"I": 1, "L": 1, "O": 0, "U": _DECODE["V"]})


class InvalidIdentifier(ValueError):
    """Raised when a display form identifier fails its checksum or syntax."""


def new_salt() -> bytes:
    return secrets.token_bytes(32)


def derive_asset_uid(namespace: str, attributes: dict, salt: bytes) -> bytes:
    """Derive the 32 byte asset uid.

    ``attributes`` should contain only the attributes that identify the asset
    itself and that will never change, for example chassis number and engine
    number for a vehicle, or title number and parcel reference for land. Do
    not include the owner, the price, the condition or anything else that can
    be revised, because the identifier must survive those changes.
    """
    if len(salt) != 32:
        raise ValueError("asset salt must be exactly 32 bytes")
    if not namespace:
        raise ValueError("namespace must not be empty")
    if not attributes:
        raise ValueError("at least one identifying attribute is required")
    return tagged_hash(
        TAG_ASSET_ID,
        namespace.encode("utf-8"),
        b"\x00",
        salt,
        canonical_bytes(attributes),
    )


def _b32_encode(data: bytes) -> str:
    acc = int.from_bytes(data, "big")
    width = (len(data) * 8 + 4) // 5
    out = []
    for i in range(width - 1, -1, -1):
        out.append(ALPHABET[(acc >> (5 * i)) & 0x1F])
    return "".join(out)


def _b32_decode(text: str, length: int) -> bytes:
    acc = 0
    for ch in text:
        try:
            acc = (acc << 5) | _DECODE[ch]
        except KeyError as exc:
            raise InvalidIdentifier(f"invalid character {ch!r}") from exc
    return acc.to_bytes((len(text) * 5 + 7) // 8, "big")[-length:]


def _checksum(body: bytes) -> str:
    return _b32_encode(tagged_hash(TAG_ASSET_ID_CHECKSUM, body))[:4]


def display_form(asset_uid: bytes) -> str:
    """Return the human transcribable identifier, for example SD0-...-XXXX."""
    if len(asset_uid) != 32:
        raise ValueError("asset uid must be exactly 32 bytes")
    body = asset_uid[:20]
    encoded = _b32_encode(body)
    groups = "-".join(encoded[i : i + 8] for i in range(0, len(encoded), 8))
    return f"SD0-{groups}-{_checksum(body)}"


def parse_display_form(identifier: str) -> bytes:
    """Validate a display form identifier and return its 20 byte prefix."""
    text = identifier.strip().upper().replace(" ", "")
    if not text.startswith("SD0-"):
        raise InvalidIdentifier("identifier must begin with the SD0 prefix")
    parts = text[4:].split("-")
    if len(parts) < 2:
        raise InvalidIdentifier("identifier is missing its checksum")
    checksum = parts[-1]
    encoded = "".join(parts[:-1])
    if len(encoded) != 32:
        raise InvalidIdentifier(
            f"identifier body must be 32 characters, got {len(encoded)}"
        )
    body = _b32_decode(encoded, 20)
    if _checksum(body) != checksum:
        raise InvalidIdentifier("checksum does not match, the identifier is mistyped")
    return body


def matches(asset_uid: bytes, identifier: str) -> bool:
    """True when a display form identifier belongs to this uid."""
    try:
        return parse_display_form(identifier) == asset_uid[:20]
    except InvalidIdentifier:
        return False
