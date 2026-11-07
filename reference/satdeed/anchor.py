"""Bitcoin anchor payload encoding and cost estimation.

SatDeed puts a fixed 40 byte payload on chain and nothing else:

    magic       2 bytes   "SD" (0x53 0x44)
    version     1 byte    0x01
    kind        1 byte    see AnchorKind
    commitment 32 bytes   Merkle root, or a single record hash
    leaf_count  4 bytes   big endian, number of records under the commitment

Forty bytes fits inside a single standard OP_RETURN output with room to spare,
so an anchor needs no inscription, no witness data trick and no non standard
relay policy. The leaf count is on chain rather than off chain because it
fixes the shape of the tree: without it, a registry could present the same
root with a different claimed tree size and change which inclusion proofs
verify.

The same payload can instead be committed in a Taproot script path leaf, which
keeps it out of the UTXO set and off the chain entirely until spent. That is
cheaper and more private, and it is the recommended construction for issuers
anchoring on a schedule. OP_RETURN is specified first because it is trivially
indexable by any explorer, which matters for a standard whose whole point is
independent verification.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import IntEnum

__all__ = [
    "MAGIC",
    "ANCHOR_VERSION",
    "PAYLOAD_SIZE",
    "AnchorKind",
    "AnchorPayload",
    "encode_payload",
    "decode_payload",
    "estimate_vbytes",
    "estimate_fee_sats",
]

MAGIC = b"SD"
ANCHOR_VERSION = 1
PAYLOAD_SIZE = 40


class AnchorKind(IntEnum):
    SINGLE_RECORD = 0x01
    BATCH_ROOT = 0x02
    STATUS_BATCH = 0x03


@dataclass(frozen=True)
class AnchorPayload:
    kind: AnchorKind
    commitment: bytes
    leaf_count: int

    def __post_init__(self) -> None:
        if len(self.commitment) != 32:
            raise ValueError("commitment must be exactly 32 bytes")
        if not 1 <= self.leaf_count <= 0xFFFFFFFF:
            raise ValueError("leaf count must be between 1 and 2**32 - 1")
        if self.kind == AnchorKind.SINGLE_RECORD and self.leaf_count != 1:
            raise ValueError("a single record anchor must declare a leaf count of 1")


def encode_payload(payload: AnchorPayload) -> bytes:
    data = (
        MAGIC
        + bytes([ANCHOR_VERSION, int(payload.kind)])
        + payload.commitment
        + payload.leaf_count.to_bytes(4, "big")
    )
    assert len(data) == PAYLOAD_SIZE
    return data


def decode_payload(data: bytes) -> AnchorPayload:
    """Decode a candidate payload, raising ValueError if it is not SatDeed.

    An indexer scanning OP_RETURN outputs will meet far more non SatDeed data
    than SatDeed data, so this is written to reject quickly and never to guess.
    """
    if len(data) != PAYLOAD_SIZE:
        raise ValueError(f"payload must be {PAYLOAD_SIZE} bytes, got {len(data)}")
    if data[:2] != MAGIC:
        raise ValueError("payload does not carry the SatDeed magic bytes")
    version = data[2]
    if version != ANCHOR_VERSION:
        raise ValueError(f"unsupported anchor version {version}")
    try:
        kind = AnchorKind(data[3])
    except ValueError as exc:
        raise ValueError(f"unknown anchor kind 0x{data[3]:02x}") from exc
    return AnchorPayload(
        kind=kind,
        commitment=data[4:36],
        leaf_count=int.from_bytes(data[36:40], "big"),
    )


# Virtual size components for a minimal anchoring transaction, one Taproot key
# path input, one OP_RETURN output and one Taproot change output.
_VB_OVERHEAD = 10.5  # version, counts, locktime, segwit marker and flag
_VB_P2TR_INPUT = 57.5  # outpoint, sequence, and a 64 byte witness signature
_VB_P2TR_OUTPUT = 43.0
_VB_OP_RETURN_OUTPUT = 8 + 1 + 2 + PAYLOAD_SIZE  # value, script length, opcodes, data


def estimate_vbytes(inputs: int = 1, change_outputs: int = 1) -> float:
    """Virtual size of an anchoring transaction, in vbytes."""
    return (
        _VB_OVERHEAD
        + inputs * _VB_P2TR_INPUT
        + change_outputs * _VB_P2TR_OUTPUT
        + _VB_OP_RETURN_OUTPUT
    )


def estimate_fee_sats(fee_rate_sat_vb: float, inputs: int = 1, change_outputs: int = 1) -> int:
    """Fee for one anchor at a given fee rate, rounded up to whole satoshis."""
    import math

    return math.ceil(estimate_vbytes(inputs, change_outputs) * fee_rate_sat_vb)
