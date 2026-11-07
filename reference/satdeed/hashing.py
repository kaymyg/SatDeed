"""Tagged hashes and domain separation for SatDeed.

Every hash SatDeed computes is a tagged hash in the style introduced by
BIP-340:

    tagged_hash(tag, msg) = SHA256(SHA256(tag) || SHA256(tag) || msg)

Prefixing with the doubled tag digest costs one extra compression block and
buys domain separation: a 32 byte value produced for one purpose can never be
mistaken for, or substituted into, another. Without it, a document commitment
and a Merkle branch would both be bare SHA-256 outputs over attacker
influenced input, and a record could be crafted whose document hash doubles as
an internal node of a tree, a classic second preimage opening.
"""

from __future__ import annotations

import hashlib
from typing import Any

from .canonical import canonical_bytes

__all__ = [
    "TAG_RECORD",
    "TAG_LEAF",
    "TAG_BRANCH",
    "TAG_DOCUMENT",
    "TAG_ASSET_ID",
    "TAG_ASSET_ID_CHECKSUM",
    "TAG_ATTRIBUTE",
    "tagged_hash",
    "sha256",
    "record_hash",
    "document_commitment",
    "attribute_commitment",
]

TAG_RECORD = "SatDeed/v0.1/record"
TAG_LEAF = "SatDeed/v0.1/leaf"
TAG_BRANCH = "SatDeed/v0.1/branch"
TAG_DOCUMENT = "SatDeed/v0.1/document"
TAG_ASSET_ID = "SatDeed/v0.1/asset-id"
TAG_ASSET_ID_CHECKSUM = "SatDeed/v0.1/asset-id-checksum"
TAG_ATTRIBUTE = "SatDeed/v0.1/attribute"

_TAG_CACHE: dict[str, bytes] = {}


def sha256(data: bytes) -> bytes:
    return hashlib.sha256(data).digest()


def tagged_hash(tag: str, *parts: bytes) -> bytes:
    """Return the 32 byte tagged hash of the concatenated ``parts``."""
    prefix = _TAG_CACHE.get(tag)
    if prefix is None:
        digest = sha256(tag.encode("utf-8"))
        prefix = digest + digest
        _TAG_CACHE[tag] = prefix
    h = hashlib.sha256()
    h.update(prefix)
    for part in parts:
        h.update(part)
    return h.digest()


def record_hash(record: dict[str, Any]) -> bytes:
    """Hash a record over its canonical serialization.

    The ``issuer_signature`` member, if present, is removed before hashing: the
    signature commits to the hash, so it cannot be part of the preimage.
    """
    payload = {k: v for k, v in record.items() if k != "issuer_signature"}
    return tagged_hash(TAG_RECORD, canonical_bytes(payload))


def document_commitment(salt: bytes, file_digest: bytes) -> bytes:
    """Commit to a document digest under a per document salt.

    Hashing a document alone is not a hiding commitment. Registration
    certificates, invoices and title documents are highly structured, so an
    unsalted digest can be brute forced over a plausible field space, which
    turns a public record into an oracle for private content. The salt is
    revealed only to a party that is already entitled to see the document.
    """
    if len(salt) != 32:
        raise ValueError("document salt must be exactly 32 bytes")
    if len(file_digest) != 32:
        raise ValueError("file digest must be exactly 32 bytes (SHA-256)")
    return tagged_hash(TAG_DOCUMENT, salt, file_digest)


def attribute_commitment(salt: bytes, name: str, value: str) -> bytes:
    """Commit to a single identifying attribute, for example a chassis number.

    Same reasoning as ``document_commitment``. A vehicle identification number
    has roughly 10**12 plausible values once make and year are known, which is
    trivially searchable against a bare digest.
    """
    if len(salt) != 32:
        raise ValueError("attribute salt must be exactly 32 bytes")
    return tagged_hash(
        TAG_ATTRIBUTE,
        salt,
        canonical_bytes({"name": name, "value": value}),
    )
