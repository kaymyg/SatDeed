#!/usr/bin/env python3
"""Regenerate every worked example in examples/ from the reference library.

Run from the repository root:  python3 reference/tools/generate_examples.py

Every hash, identifier, signature and proof published in examples/ is produced
by this script, so the examples cannot drift away from the specification
without the test suite noticing. Keys and salts are fixed test vectors, never
real secrets.
"""

from __future__ import annotations

import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "reference"))

from satdeed import (  # noqa: E402
    AnchorKind,
    AnchorObservation,
    AnchorPayload,
    build_asset_record,
    build_status_record,
    derive_asset_uid,
    encode_payload,
    make_document_entry,
    merkle_root,
    prove,
    record_hash,
    sha256,
    sign_record,
    verify_document,
    verify_record,
)
from satdeed import schnorr  # noqa: E402

# Deterministic test vectors. These are published on purpose so that anyone
# can regenerate the examples byte for byte. They are not keys for anything.
REGISTRY_SECKEY = bytes.fromhex(
    "0000000000000000000000000000000000000000000000000000000000000003"
)
WAREHOUSE_SECKEY = bytes.fromhex(
    "0000000000000000000000000000000000000000000000000000000000000007"
)
AUX = bytes(32)
ASSET_SALT = bytes.fromhex("11" * 32)
DOC_SALT = bytes.fromhex("22" * 32)
VIN_SALT = bytes.fromhex("33" * 32)
RECEIPT_SALT = bytes.fromhex("44" * 32)


def deterministic_sign(record: dict, seckey: bytes) -> dict:
    """Sign with fixed auxiliary randomness so examples are reproducible."""
    pubkey = schnorr.pubkey_from_seckey(seckey)
    assert pubkey.hex() == record["issuer"]["public_key"]
    digest = record_hash(record)
    signed = dict(record)
    signed["issuer_signature"] = {
        "algorithm": "BIP340-schnorr-secp256k1",
        "signature": schnorr.sign(digest, seckey, aux_rand=AUX).hex(),
    }
    return signed


def write_json(path: str, data) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(data, fh, indent=2, ensure_ascii=False)
        fh.write("\n")
    print(f"wrote {os.path.relpath(path, ROOT)}")


def write_text(path: str, text: str) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(text)
    print(f"wrote {os.path.relpath(path, ROOT)}")


# ---------------------------------------------------------------- vehicle ---

CERTIFICATE = """REPUBLIC OF EXAMPLE
MOTOR VEHICLE REGISTRATION CERTIFICATE

Certificate number : MV-2026-0000912
Registration mark  : KDX 442T
Chassis number     : LC0ABC123DEF45678
Engine number      : EX4G15D0099112
Make and model     : Example Motors, Electric Motorcycle
Year of manufacture: 2026
Registered keeper  : (withheld from the public record)
Date of first entry: 2026-03-14

This certificate is a specimen used as a SatDeed worked example.
It does not describe a real vehicle and confers no rights.
"""


def build_vehicle(outdir: str) -> None:
    pub = schnorr.pubkey_from_seckey(REGISTRY_SECKEY)
    uid = derive_asset_uid(
        "registry.example",
        {
            "chassis_number": "LC0ABC123DEF45678",
            "engine_number": "EX4G15D0099112",
        },
        ASSET_SALT,
    )
    cert_bytes = CERTIFICATE.encode("utf-8")

    from satdeed import attribute_commitment

    record = build_asset_record(
        asset_uid=uid,
        asset_class="vehicle",
        issuer_id="registry.example",
        issuer_pubkey=pub,
        issued_at="2026-11-07T09:00:00Z",
        verification_level=3,
        attributes={
            "manufacturer": "Example Motors",
            "model": "Electric Motorcycle",
            "year_of_manufacture": 2026,
            "body_type": "motorcycle",
        },
        attribute_commitments=[
            {
                "name": "chassis_number",
                "commitment": attribute_commitment(
                    VIN_SALT, "chassis_number", "LC0ABC123DEF45678"
                ).hex(),
            }
        ],
        documents=[
            make_document_entry(
                "registration_certificate",
                DOC_SALT,
                sha256(cert_bytes),
                storage=[
                    "https://records.registry.example/v1/doc/{commitment}",
                    "ipfs://<cid placeholder, the commitment is what binds>",
                ],
            )
        ],
    )
    signed = deterministic_sign(record, REGISTRY_SECKEY)
    digest = record_hash(signed)
    payload = encode_payload(AnchorPayload(AnchorKind.SINGLE_RECORD, digest, 1))

    anchor = {
        "_comment": "What an independent observer reads off the chain. The txid "
                    "here is a placeholder: no transaction has been broadcast.",
        "txid": "00" * 32,
        "output_index": 0,
        "op_return_data": payload.hex(),
        "block_height": 900000,
        "confirmations": 144,
    }

    write_text(os.path.join(outdir, "registration-certificate.txt"), CERTIFICATE)
    write_json(os.path.join(outdir, "asset-record.json"), signed)
    write_json(os.path.join(outdir, "anchor.json"), anchor)
    write_json(
        os.path.join(outdir, "disclosure.json"),
        {
            "_comment": "Held by the issuer, released only to a party entitled to "
                        "confirm the record. Publishing this file would undo the "
                        "privacy the commitments provide.",
            "asset_salt": ASSET_SALT.hex(),
            "identifying_attributes": {
                "chassis_number": "LC0ABC123DEF45678",
                "engine_number": "EX4G15D0099112",
            },
            "attribute_salts": {"chassis_number": VIN_SALT.hex()},
            "document_salts": {"registration_certificate": DOC_SALT.hex()},
        },
    )

    obs = AnchorObservation(
        txid=anchor["txid"],
        output_index=0,
        op_return_data=payload,
        block_height=anchor["block_height"],
        confirmations=anchor["confirmations"],
    )
    result = verify_record(
        signed, anchor=obs,
        known_issuer_keys={"registry.example": pub.hex()},
    )
    doc_check = verify_document(signed, "registration_certificate",
                                DOC_SALT, cert_bytes)
    transcript = (
        "$ satdeed verify asset-record.json --anchor anchor.json "
        "--issuers issuers.json\n\n"
        + result.report()
        + "\n\n$ satdeed check-document asset-record.json "
        "--type registration_certificate \\\n"
        f"    --salt {DOC_SALT.hex()} --file registration-certificate.txt\n\n"
        f"{'PASS' if doc_check.passed else 'FAIL'}  {doc_check.name}: "
        f"{doc_check.detail}\n"
        f"      file sha256: {sha256(cert_bytes).hex()}\n"
    )
    write_text(os.path.join(outdir, "verification-transcript.txt"), transcript)
    write_json(os.path.join(outdir, "issuers.json"),
               {"registry.example": pub.hex()})
    assert result.passed and doc_check.passed, "vehicle example must verify"

    # A revocation, so the example shows how a record is corrected.
    revocation = build_status_record(
        asset_uid=uid,
        issuer_id="registry.example",
        issuer_pubkey=pub,
        issued_at="2027-02-02T11:30:00Z",
        status="revoked",
        supersedes=digest.hex(),
        reason="registration cancelled, vehicle written off after an accident",
    )
    signed_revocation = deterministic_sign(revocation, REGISTRY_SECKEY)
    write_json(os.path.join(outdir, "status-record-revocation.json"),
               signed_revocation)
    assert verify_record(signed_revocation).passed


# ------------------------------------------------------- warehouse receipt ---

RECEIPT = """EXAMPLE GRAIN HANDLERS LIMITED
WAREHOUSE RECEIPT

Receipt number   : WR-2026-004417
Warehouse        : Depot 3, Example Industrial Area
Commodity        : White maize, grade 1
Quantity         : 420 bags, 90 kg each, 37,800 kg gross
Moisture content : 13.1 percent
Date of deposit  : 2026-10-28
Depositor        : (withheld from the public record)

Specimen document for a SatDeed worked example. Not a receipt for any goods.
"""


def build_warehouse(outdir: str) -> None:
    pub = schnorr.pubkey_from_seckey(WAREHOUSE_SECKEY)
    uid = derive_asset_uid(
        "grain.example", {"receipt_number": "WR-2026-004417"}, ASSET_SALT
    )
    receipt_bytes = RECEIPT.encode("utf-8")
    record = build_asset_record(
        asset_uid=uid,
        asset_class="warehouse_receipt",
        issuer_id="grain.example",
        issuer_pubkey=pub,
        issued_at="2026-10-28T14:05:00Z",
        verification_level=2,
        attributes={
            "commodity": "white maize",
            "grade": "1",
            "quantity_kg": 37800,
            "warehouse": "Depot 3, Example Industrial Area",
            "deposit_date": "2026-10-28",
        },
        documents=[
            make_document_entry("warehouse_receipt", RECEIPT_SALT,
                                sha256(receipt_bytes),
                                storage=["https://records.grain.example/{commitment}"])
        ],
    )
    signed = deterministic_sign(record, WAREHOUSE_SECKEY)
    write_text(os.path.join(outdir, "warehouse-receipt.txt"), RECEIPT)
    write_json(os.path.join(outdir, "asset-record.json"), signed)
    write_json(os.path.join(outdir, "disclosure.json"), {
        "asset_salt": ASSET_SALT.hex(),
        "identifying_attributes": {"receipt_number": "WR-2026-004417"},
        "document_salts": {"warehouse_receipt": RECEIPT_SALT.hex()},
    })
    assert verify_record(signed).passed
    assert verify_document(signed, "warehouse_receipt", RECEIPT_SALT,
                           receipt_bytes).passed


# ----------------------------------------------------------- batch anchor ---


def build_batch(outdir: str, count: int = 64) -> None:
    pub = schnorr.pubkey_from_seckey(REGISTRY_SECKEY)
    records = []
    for i in range(count):
        uid = derive_asset_uid(
            "registry.example", {"chassis_number": f"LC0BATCH{i:09d}"}, ASSET_SALT
        )
        record = build_asset_record(
            asset_uid=uid,
            asset_class="vehicle",
            issuer_id="registry.example",
            issuer_pubkey=pub,
            issued_at="2026-11-07T23:59:00Z",
            verification_level=3,
            attributes={"manufacturer": "Example Motors", "year_of_manufacture": 2026},
        )
        records.append(deterministic_sign(record, REGISTRY_SECKEY))

    hashes = [record_hash(r) for r in records]
    root = merkle_root(hashes)
    payload = encode_payload(AnchorPayload(AnchorKind.BATCH_ROOT, root, count))

    write_json(os.path.join(outdir, "batch-manifest.json"), {
        "_comment": "The registry's own index of the batch. It is NOT needed to "
                    "verify any single record: a holder needs only their record "
                    "and their inclusion proof.",
        "issuer_id": "registry.example",
        "anchored_at": "2026-11-07T23:59:00Z",
        "leaf_count": count,
        "merkle_root": root.hex(),
        "op_return_data": payload.hex(),
        "record_hashes": [h.hex() for h in hashes],
    })
    write_json(os.path.join(outdir, "anchor.json"), {
        "txid": "11" * 32,
        "output_index": 0,
        "op_return_data": payload.hex(),
        "block_height": 900001,
        "confirmations": 143,
    })

    obs = AnchorObservation(txid="11" * 32, output_index=0,
                            op_return_data=payload, block_height=900001,
                            confirmations=143)
    # Publish three records with their proofs, including the awkward last leaf.
    for index in (0, 37, count - 1):
        sub = os.path.join(outdir, f"record-{index:03d}")
        proof = prove(hashes, index)
        write_json(os.path.join(sub, "asset-record.json"), records[index])
        write_json(os.path.join(sub, "inclusion-proof.json"), proof.to_json())
        result = verify_record(records[index], proof=proof, anchor=obs)
        write_text(os.path.join(sub, "verification-transcript.txt"),
                   f"$ satdeed verify asset-record.json "
                   f"--proof inclusion-proof.json --anchor ../anchor.json\n\n"
                   + result.report() + "\n")
        assert result.passed, f"batch record {index} must verify"

    proof_sizes = {i: len(prove(hashes, i).path) for i in range(count)}
    write_json(os.path.join(outdir, "proof-sizes.json"), {
        "_comment": "Number of sibling hashes a holder must keep, per leaf. Each "
                    "is 32 bytes, so a proof for this batch is at most "
                    f"{max(proof_sizes.values()) * 32} bytes.",
        "leaf_count": count,
        "max_path_length": max(proof_sizes.values()),
        "max_proof_bytes": max(proof_sizes.values()) * 32,
    })


# ------------------------------------------------------------------- main ---


def main() -> int:
    build_vehicle(os.path.join(ROOT, "examples", "vehicle-title"))
    build_warehouse(os.path.join(ROOT, "examples", "warehouse-receipt"))
    build_batch(os.path.join(ROOT, "examples", "batch-anchor"))
    print("\nall examples regenerated and verified")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
