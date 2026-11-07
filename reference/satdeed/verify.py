"""The SatDeed verification pipeline.

Verification answers a narrow question, and the value of the standard depends
on stating that question precisely.

What a passing verification establishes:
  * the record is well formed under v0.1
  * the record was signed by the key it names
  * the record hash is committed under a Merkle root
  * that root appears in a Bitcoin transaction at a stated confirmation depth
  * a presented document matches the commitment the record carries

What it does NOT establish:
  * that the issuer had the authority to make the statement
  * that the physical asset exists, or matches the description
  * that the asset is unencumbered, undisputed or not already financed
  * that the holder of the signing key is the legal owner
  * that no later record revokes this one, unless the caller supplied the
    issuer's status set

The pipeline therefore returns a structured result listing each check and its
outcome, rather than a single boolean, so that an integrator is forced to
decide which of these guarantees their use case actually needs.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from . import schnorr
from .anchor import AnchorKind, AnchorPayload, decode_payload
from .hashing import document_commitment, record_hash, sha256
from .merkle import MerkleProof, verify_proof
from .record import StructuralError, validate_structure

__all__ = ["Check", "VerificationResult", "AnchorObservation", "verify_record",
           "verify_document"]


@dataclass(frozen=True)
class Check:
    name: str
    passed: bool
    detail: str


@dataclass
class VerificationResult:
    checks: list[Check] = field(default_factory=list)

    def add(self, name: str, passed: bool, detail: str) -> None:
        self.checks.append(Check(name, passed, detail))

    @property
    def passed(self) -> bool:
        return all(c.passed for c in self.checks)

    @property
    def failures(self) -> list[Check]:
        return [c for c in self.checks if not c.passed]

    def report(self) -> str:
        lines = [f"{'PASS' if c.passed else 'FAIL'}  {c.name}: {c.detail}"
                 for c in self.checks]
        lines.append("")
        lines.append("RESULT: " + ("verified" if self.passed else "NOT verified"))
        return "\n".join(lines)


@dataclass(frozen=True)
class AnchorObservation:
    """What an independent observer read off the Bitcoin chain.

    This is supplied by the caller rather than fetched, because the point of
    the standard is that any node, explorer or indexer can produce it. The
    reference library deliberately does not ship a chain client: a verifier
    that trusts one API endpoint has reintroduced exactly the dependency
    SatDeed exists to remove.
    """

    txid: str
    output_index: int
    op_return_data: bytes
    block_height: int | None
    confirmations: int


def verify_record(
    record: dict[str, Any],
    *,
    proof: MerkleProof | None = None,
    anchor: AnchorObservation | None = None,
    min_confirmations: int = 6,
    known_issuer_keys: dict[str, str] | None = None,
) -> VerificationResult:
    """Run every check for which the caller supplied the necessary evidence."""
    result = VerificationResult()

    try:
        validate_structure(record)
        result.add("structure", True, "record satisfies the v0.1 structural rules")
    except StructuralError as exc:
        result.add("structure", False, str(exc))
        return result  # nothing downstream is meaningful on a malformed record

    digest = record_hash(record)
    result.add("record_hash", True, digest.hex())

    signature = record.get("issuer_signature")
    if signature is None:
        result.add("issuer_signature", False, "record carries no issuer signature")
    else:
        pubkey = bytes.fromhex(record["issuer"]["public_key"])
        ok = schnorr.verify(digest, pubkey, bytes.fromhex(signature["signature"]))
        result.add(
            "issuer_signature",
            ok,
            "signature is valid for the declared key" if ok
            else "signature does not verify against the declared key",
        )

    issuer_id = record["issuer"]["issuer_id"]
    if known_issuer_keys is not None:
        expected = known_issuer_keys.get(issuer_id)
        if expected is None:
            result.add("issuer_identity", False,
                       f"issuer {issuer_id!r} is not in the supplied key directory")
        else:
            ok = expected == record["issuer"]["public_key"]
            result.add("issuer_identity", ok,
                       f"key matches the directory entry for {issuer_id!r}" if ok
                       else f"key does NOT match the directory entry for {issuer_id!r}")

    if anchor is not None:
        _verify_anchor(result, digest, proof, anchor, min_confirmations)

    return result


def _verify_anchor(
    result: VerificationResult,
    digest: bytes,
    proof: MerkleProof | None,
    anchor: AnchorObservation,
    min_confirmations: int,
) -> None:
    try:
        payload: AnchorPayload = decode_payload(anchor.op_return_data)
    except ValueError as exc:
        result.add("anchor_payload", False, str(exc))
        return
    result.add("anchor_payload", True,
               f"{payload.kind.name}, commitment {payload.commitment.hex()}, "
               f"{payload.leaf_count} leaf/leaves")

    if payload.kind == AnchorKind.SINGLE_RECORD:
        ok = payload.commitment == digest
        result.add("anchor_commitment", ok,
                   "record hash equals the anchored commitment" if ok
                   else "record hash does not match the anchored commitment")
    else:
        if proof is None:
            result.add("merkle_inclusion", False,
                       "batch anchor requires an inclusion proof, none supplied")
        elif proof.leaf_count != payload.leaf_count:
            result.add("merkle_inclusion", False,
                       f"proof declares {proof.leaf_count} leaves but the anchor "
                       f"declares {payload.leaf_count}")
        else:
            ok = verify_proof(digest, proof, payload.commitment)
            result.add("merkle_inclusion", ok,
                       f"record is leaf {proof.index} of {proof.leaf_count} under "
                       f"the anchored root" if ok
                       else "inclusion proof does not reproduce the anchored root")

    ok = anchor.confirmations >= min_confirmations
    result.add("confirmations", ok,
               f"{anchor.confirmations} confirmations at height "
               f"{anchor.block_height}, minimum required {min_confirmations}")


def verify_document(
    record: dict[str, Any],
    doc_type: str,
    salt: bytes,
    file_bytes: bytes,
) -> Check:
    """Check a presented file against the commitment in the record.

    A pass means the bytes are identical to the bytes committed when the record
    was issued. It says nothing about whether that original file was genuine,
    correctly issued or legally valid, which is a separate question answered by
    the issuer attestation and, ultimately, by law.
    """
    entries = [d for d in record.get("documents", []) if d.get("type") == doc_type]
    if not entries:
        return Check("document:" + doc_type, False,
                     "the record carries no commitment of this document type")
    expected = document_commitment(salt, sha256(file_bytes)).hex()
    for entry in entries:
        if entry["commitment"] == expected:
            return Check("document:" + doc_type, True,
                         "presented file matches the committed document")
    return Check("document:" + doc_type, False,
                 "presented file does not match any committed document of this type")
