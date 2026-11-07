#!/usr/bin/env python3
"""Command line tool for inspecting and verifying SatDeed records.

Usage:
  satdeed_cli.py hash RECORD.json
  satdeed_cli.py canonical RECORD.json
  satdeed_cli.py verify RECORD.json [--proof PROOF.json] [--anchor ANCHOR.json]
                                    [--min-confirmations N]
  satdeed_cli.py check-document RECORD.json --type TYPE --salt HEX --file PATH
  satdeed_cli.py decode-anchor HEXDATA
  satdeed_cli.py fees [--batch-size N ...] [--fee-rate R ...]

The anchor file is a small JSON object describing what an independent observer
read off the chain:

  {"txid": "...", "output_index": 0, "op_return_data": "<hex>",
   "block_height": 900000, "confirmations": 12}
"""

from __future__ import annotations

import argparse
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

from satdeed import (  # noqa: E402
    AnchorObservation,
    MerkleProof,
    canonicalize,
    decode_payload,
    record_hash,
    sha256,
    verify_document,
    verify_record,
)
from satdeed.anchor import estimate_fee_sats, estimate_vbytes  # noqa: E402


def _load(path: str) -> dict:
    with open(path, "r", encoding="utf-8") as fh:
        return json.load(fh)


def cmd_hash(args) -> int:
    print(record_hash(_load(args.record)).hex())
    return 0


def cmd_canonical(args) -> int:
    record = _load(args.record)
    payload = {k: v for k, v in record.items() if k != "issuer_signature"}
    sys.stdout.write(canonicalize(payload))
    sys.stdout.write("\n")
    return 0


def cmd_verify(args) -> int:
    record = _load(args.record)
    proof = MerkleProof.from_json(_load(args.proof)) if args.proof else None
    anchor = None
    if args.anchor:
        data = _load(args.anchor)
        anchor = AnchorObservation(
            txid=data["txid"],
            output_index=data.get("output_index", 0),
            op_return_data=bytes.fromhex(data["op_return_data"]),
            block_height=data.get("block_height"),
            confirmations=data.get("confirmations", 0),
        )
    directory = _load(args.issuers) if args.issuers else None
    result = verify_record(
        record,
        proof=proof,
        anchor=anchor,
        min_confirmations=args.min_confirmations,
        known_issuer_keys=directory,
    )
    print(result.report())
    return 0 if result.passed else 1


def cmd_check_document(args) -> int:
    record = _load(args.record)
    with open(args.file, "rb") as fh:
        blob = fh.read()
    check = verify_document(record, args.type, bytes.fromhex(args.salt), blob)
    print(f"{'PASS' if check.passed else 'FAIL'}  {check.name}: {check.detail}")
    print(f"      file sha256: {sha256(blob).hex()}")
    return 0 if check.passed else 1


def cmd_decode_anchor(args) -> int:
    payload = decode_payload(bytes.fromhex(args.hexdata))
    print(f"kind:        {payload.kind.name}")
    print(f"commitment:  {payload.commitment.hex()}")
    print(f"leaf_count:  {payload.leaf_count}")
    return 0


def cmd_fees(args) -> int:
    vbytes = estimate_vbytes()
    print(f"Anchoring transaction size: {vbytes:.1f} vbytes")
    print("(one Taproot key path input, one 40 byte OP_RETURN output, one change output)")
    print()
    header = "records/batch | " + " | ".join(f"{r:>8.0f} sat/vB" for r in args.fee_rate)
    print(header)
    print("-" * len(header))
    for n in args.batch_size:
        cells = []
        for rate in args.fee_rate:
            total = estimate_fee_sats(rate)
            cells.append(f"{total / n:>8.2f} sat")
        print(f"{n:>13} | " + " | ".join(cells))
    print()
    print("Figures are satoshis per anchored record, total fee divided by batch size.")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="satdeed", description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("hash", help="print the record hash")
    p.add_argument("record")
    p.set_defaults(func=cmd_hash)

    p = sub.add_parser("canonical", help="print the canonical serialization")
    p.add_argument("record")
    p.set_defaults(func=cmd_canonical)

    p = sub.add_parser("verify", help="run the verification pipeline")
    p.add_argument("record")
    p.add_argument("--proof")
    p.add_argument("--anchor")
    p.add_argument("--issuers", help="JSON map of issuer_id to public key")
    p.add_argument("--min-confirmations", type=int, default=6)
    p.set_defaults(func=cmd_verify)

    p = sub.add_parser("check-document", help="check a file against a commitment")
    p.add_argument("record")
    p.add_argument("--type", required=True)
    p.add_argument("--salt", required=True)
    p.add_argument("--file", required=True)
    p.set_defaults(func=cmd_check_document)

    p = sub.add_parser("decode-anchor", help="decode an OP_RETURN payload")
    p.add_argument("hexdata")
    p.set_defaults(func=cmd_decode_anchor)

    p = sub.add_parser("fees", help="estimate anchoring cost per record")
    p.add_argument("--batch-size", type=int, nargs="+",
                   default=[1, 10, 100, 1_000, 10_000, 100_000])
    p.add_argument("--fee-rate", type=float, nargs="+", default=[1, 5, 20, 100])
    p.set_defaults(func=cmd_fees)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
