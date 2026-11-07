"""Merkle tree construction and inclusion proofs for batch anchoring.

Construction rules, all of which exist to close a known attack:

1. Leaves are ``tagged_hash(TAG_LEAF, record_hash)`` and internal nodes are
   ``tagged_hash(TAG_BRANCH, left || right)``. Distinct tags mean no leaf
   value can ever be reinterpreted as an internal node, so nobody can present
   a two record subtree as if it were a single record.

2. A level with an odd number of nodes promotes its last node unchanged to the
   next level. It is NOT duplicated. Duplicating the final node is the Bitcoin
   block tree behaviour and it causes distinct leaf sets to produce the same
   root, which was CVE-2012-2459. A registry whose batches collide can publish
   a record it never committed to.

3. The leaf count is carried in the on chain anchor payload and bound into
   verification. This matters more than it first appears. For many index and
   size pairs the branch shape above a leaf is identical across two different
   tree sizes, for example leaf 2 of a five leaf tree and leaf 2 of a six leaf
   tree, so an inclusion proof on its own cannot tell those sizes apart. A
   verifier that accepted a self declared tree size would therefore accept a
   proof against a batch of a size the registry never committed to. Putting
   the count on chain removes the ambiguity, and ``verify.py`` rejects any
   proof whose declared size differs from the anchored one.

4. A batch with zero records has no root and cannot be anchored.
"""

from __future__ import annotations

from dataclasses import dataclass

from .hashing import TAG_BRANCH, TAG_LEAF, tagged_hash

__all__ = ["MerkleProof", "leaf_hash", "build_tree", "merkle_root", "prove", "verify_proof"]


@dataclass(frozen=True)
class MerkleProof:
    """An inclusion proof for one leaf.

    ``path`` is ordered from the bottom of the tree upward. Each element is the
    sibling hash together with the side that sibling sits on.
    """

    index: int
    leaf_count: int
    path: tuple[tuple[str, bytes], ...]

    def to_json(self) -> dict:
        return {
            "index": self.index,
            "leaf_count": self.leaf_count,
            "path": [{"side": side, "hash": h.hex()} for side, h in self.path],
        }

    @staticmethod
    def from_json(data: dict) -> "MerkleProof":
        return MerkleProof(
            index=data["index"],
            leaf_count=data["leaf_count"],
            path=tuple(
                (step["side"], bytes.fromhex(step["hash"])) for step in data["path"]
            ),
        )


def leaf_hash(record_hash: bytes) -> bytes:
    if len(record_hash) != 32:
        raise ValueError("record hash must be exactly 32 bytes")
    return tagged_hash(TAG_LEAF, record_hash)


def build_tree(record_hashes: list[bytes]) -> list[list[bytes]]:
    """Return every level of the tree, leaves first, root last."""
    if not record_hashes:
        raise ValueError("cannot build a Merkle tree over an empty batch")
    level = [leaf_hash(h) for h in record_hashes]
    levels = [level]
    while len(level) > 1:
        nxt: list[bytes] = []
        for i in range(0, len(level) - 1, 2):
            nxt.append(tagged_hash(TAG_BRANCH, level[i], level[i + 1]))
        if len(level) % 2 == 1:
            nxt.append(level[-1])  # promote, never duplicate
        level = nxt
        levels.append(level)
    return levels


def merkle_root(record_hashes: list[bytes]) -> bytes:
    return build_tree(record_hashes)[-1][0]


def prove(record_hashes: list[bytes], index: int) -> MerkleProof:
    if not 0 <= index < len(record_hashes):
        raise IndexError("leaf index is outside the batch")
    levels = build_tree(record_hashes)
    path: list[tuple[str, bytes]] = []
    position = index
    for level in levels[:-1]:
        if position == len(level) - 1 and len(level) % 2 == 1:
            # Promoted node: it has no sibling at this level.
            position //= 2
            continue
        if position % 2 == 0:
            path.append(("right", level[position + 1]))
        else:
            path.append(("left", level[position - 1]))
        position //= 2
    return MerkleProof(index=index, leaf_count=len(record_hashes), path=tuple(path))


def verify_proof(record_hash: bytes, proof: MerkleProof, root: bytes) -> bool:
    """Recompute the root from a record hash and its proof."""
    if proof.leaf_count < 1 or not 0 <= proof.index < proof.leaf_count:
        return False
    node = leaf_hash(record_hash)
    position = proof.index
    width = proof.leaf_count
    step = 0
    while width > 1:
        if position == width - 1 and width % 2 == 1:
            # This node was promoted, so the proof must not spend a step here.
            pass
        else:
            if step >= len(proof.path):
                return False
            side, sibling = proof.path[step]
            step += 1
            if side == "right":
                if position % 2 != 0:
                    return False
                node = tagged_hash(TAG_BRANCH, node, sibling)
            elif side == "left":
                if position % 2 != 1:
                    return False
                node = tagged_hash(TAG_BRANCH, sibling, node)
            else:
                return False
        position //= 2
        width = (width + 1) // 2
    if step != len(proof.path):
        return False  # reject proofs carrying unused steps
    return node == root
