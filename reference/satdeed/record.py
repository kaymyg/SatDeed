"""Construction and structural validation of SatDeed records."""

from __future__ import annotations

import re
from typing import Any

from . import schnorr
from .canonical import canonicalize
from .hashing import document_commitment, record_hash
from .identifiers import display_form, parse_display_form

__all__ = [
    "SPEC_VERSION",
    "RECORD_TYPES",
    "RECORD_STATUSES",
    "VERIFICATION_LEVELS",
    "StructuralError",
    "build_asset_record",
    "build_status_record",
    "sign_record",
    "validate_structure",
    "make_document_entry",
]

SPEC_VERSION = "0.1"
RECORD_TYPES = ("asset", "status")
RECORD_STATUSES = ("active", "superseded", "revoked", "disputed")
VERIFICATION_LEVELS = (0, 1, 2, 3, 4)

_HEX32 = re.compile(r"^[0-9a-f]{64}$")
_HEX64 = re.compile(r"^[0-9a-f]{128}$")
_TIMESTAMP = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")
_ISSUER_ID = re.compile(r"^[a-z0-9]([a-z0-9._-]{0,62}[a-z0-9])?$")


class StructuralError(ValueError):
    """Raised when a record does not satisfy the v0.1 structural rules."""


def make_document_entry(
    doc_type: str,
    salt: bytes,
    file_digest: bytes,
    storage: list[str] | None = None,
) -> dict[str, Any]:
    """Build one entry for the ``documents`` array.

    Note what is published and what is not. The commitment goes on the record.
    The salt and the file itself are held by the issuer and disclosed only to a
    party entitled to see them, which is what allows a public record to
    reference a private title deed without leaking its contents.
    """
    return {
        "type": doc_type,
        "digest_algorithm": "SHA-256",
        "commitment": document_commitment(salt, file_digest).hex(),
        "storage": list(storage or []),
    }


def build_asset_record(
    *,
    asset_uid: bytes,
    asset_class: str,
    issuer_id: str,
    issuer_pubkey: bytes,
    issued_at: str,
    verification_level: int,
    attributes: dict[str, Any] | None = None,
    attribute_commitments: list[dict[str, str]] | None = None,
    documents: list[dict[str, Any]] | None = None,
    supersedes: str | None = None,
    status: str = "active",
) -> dict[str, Any]:
    """Assemble an unsigned asset record."""
    record = {
        "satdeed": SPEC_VERSION,
        "record_type": "asset",
        "asset_id": display_form(asset_uid),
        "asset_uid": asset_uid.hex(),
        "asset_class": asset_class,
        "issuer": {"issuer_id": issuer_id, "public_key": issuer_pubkey.hex()},
        "issued_at": issued_at,
        "verification_level": verification_level,
        "attributes": attributes or {},
        "attribute_commitments": attribute_commitments or [],
        "documents": documents or [],
        "supersedes": supersedes,
        "status": status,
    }
    validate_structure(record)
    return record


def build_status_record(
    *,
    asset_uid: bytes,
    issuer_id: str,
    issuer_pubkey: bytes,
    issued_at: str,
    status: str,
    supersedes: str,
    reason: str,
) -> dict[str, Any]:
    """Assemble an unsigned status record.

    Status records are how SatDeed corrects itself. Nothing is ever deleted or
    rewritten: a revocation is a new signed statement that points at the record
    it supersedes, and both stay verifiable forever. A reader who only sees the
    original record and not the revocation is reading an incomplete history,
    which is why the verifier treats an unresolved status chain as a warning
    rather than a pass.
    """
    record = {
        "satdeed": SPEC_VERSION,
        "record_type": "status",
        "asset_uid": asset_uid.hex(),
        "issuer": {"issuer_id": issuer_id, "public_key": issuer_pubkey.hex()},
        "issued_at": issued_at,
        "status": status,
        "supersedes": supersedes,
        "reason": reason,
    }
    validate_structure(record)
    return record


def sign_record(record: dict[str, Any], seckey: bytes) -> dict[str, Any]:
    """Return a copy of ``record`` carrying an issuer signature.

    The signature covers the tagged hash of the canonical serialization of
    every member except the signature itself, so adding, removing or reordering
    any field invalidates it.
    """
    pubkey = schnorr.pubkey_from_seckey(seckey)
    declared = bytes.fromhex(record["issuer"]["public_key"])
    if pubkey != declared:
        raise StructuralError(
            "the signing key does not match the public key declared in the record"
        )
    digest = record_hash(record)
    signature = schnorr.sign(digest, seckey)
    signed = dict(record)
    signed["issuer_signature"] = {
        "algorithm": "BIP340-schnorr-secp256k1",
        "signature": signature.hex(),
    }
    return signed


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise StructuralError(message)


def validate_structure(record: dict[str, Any]) -> None:
    """Check the structural rules that do not require any external data."""
    _require(isinstance(record, dict), "record must be a JSON object")
    _require(record.get("satdeed") == SPEC_VERSION, "unsupported or missing satdeed version")

    record_type = record.get("record_type")
    _require(record_type in RECORD_TYPES, f"record_type must be one of {RECORD_TYPES}")

    uid = record.get("asset_uid")
    _require(isinstance(uid, str) and bool(_HEX32.match(uid)),
             "asset_uid must be 64 lowercase hex characters")

    issuer = record.get("issuer")
    _require(isinstance(issuer, dict), "issuer must be an object")
    _require(isinstance(issuer.get("issuer_id"), str)
             and bool(_ISSUER_ID.match(issuer["issuer_id"])),
             "issuer_id must be a lowercase label of up to 64 characters")
    _require(isinstance(issuer.get("public_key"), str)
             and bool(_HEX32.match(issuer["public_key"])),
             "issuer public_key must be a 32 byte x only key in lowercase hex")

    _require(isinstance(record.get("issued_at"), str)
             and bool(_TIMESTAMP.match(record["issued_at"])),
             "issued_at must be a UTC timestamp of the form YYYY-MM-DDTHH:MM:SSZ")

    _require(record.get("status") in RECORD_STATUSES,
             f"status must be one of {RECORD_STATUSES}")

    supersedes = record.get("supersedes")
    _require(supersedes is None or (isinstance(supersedes, str) and bool(_HEX32.match(supersedes))),
             "supersedes must be null or a 64 character record hash")

    if record_type == "asset":
        _require(isinstance(record.get("asset_class"), str) and record["asset_class"] != "",
                 "asset_class is required on an asset record")
        _require(record.get("verification_level") in VERIFICATION_LEVELS,
                 f"verification_level must be one of {VERIFICATION_LEVELS}")
        try:
            prefix = parse_display_form(record.get("asset_id", ""))
        except Exception as exc:  # noqa: BLE001 - surfaced as a structural error
            raise StructuralError(f"asset_id is not a valid identifier: {exc}") from exc
        _require(prefix == bytes.fromhex(uid)[:20],
                 "asset_id does not correspond to asset_uid")
        _validate_documents(record.get("documents"))
        _validate_attribute_commitments(record.get("attribute_commitments"))
    else:
        _require(isinstance(record.get("reason"), str) and record["reason"] != "",
                 "a status record must state a reason")
        _require(supersedes is not None,
                 "a status record must name the record it supersedes")

    signature = record.get("issuer_signature")
    if signature is not None:
        _require(isinstance(signature, dict), "issuer_signature must be an object")
        _require(signature.get("algorithm") == "BIP340-schnorr-secp256k1",
                 "unsupported signature algorithm")
        _require(isinstance(signature.get("signature"), str)
                 and bool(_HEX64.match(signature["signature"])),
                 "signature must be 128 lowercase hex characters")

    # Canonicalization must succeed, which also rejects floats and bad strings.
    canonicalize({k: v for k, v in record.items() if k != "issuer_signature"})


def _validate_documents(documents: Any) -> None:
    _require(isinstance(documents, list), "documents must be an array")
    for i, doc in enumerate(documents):
        _require(isinstance(doc, dict), f"documents[{i}] must be an object")
        _require(isinstance(doc.get("type"), str) and doc["type"] != "",
                 f"documents[{i}].type is required")
        _require(doc.get("digest_algorithm") == "SHA-256",
                 f"documents[{i}].digest_algorithm must be SHA-256 in v0.1")
        _require(isinstance(doc.get("commitment"), str)
                 and bool(_HEX32.match(doc["commitment"])),
                 f"documents[{i}].commitment must be 64 lowercase hex characters")
        _require(isinstance(doc.get("storage"), list),
                 f"documents[{i}].storage must be an array, which may be empty")


def _validate_attribute_commitments(commitments: Any) -> None:
    _require(isinstance(commitments, list), "attribute_commitments must be an array")
    for i, item in enumerate(commitments):
        _require(isinstance(item, dict), f"attribute_commitments[{i}] must be an object")
        _require(isinstance(item.get("name"), str) and item["name"] != "",
                 f"attribute_commitments[{i}].name is required")
        _require(isinstance(item.get("commitment"), str)
                 and bool(_HEX32.match(item["commitment"])),
                 f"attribute_commitments[{i}].commitment must be 64 hex characters")
