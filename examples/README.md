# Worked examples

Every hash, identifier, signature, Merkle root and inclusion proof in this
directory is produced by the reference library. Nothing is hand written, and
nothing should be hand edited. Regenerate with:

```bash
python3 reference/tools/generate_examples.py
```

Regeneration is deterministic, so `git diff --exit-code examples/` after
running it is a check that the examples still match the code.

## Test vectors, not secrets

The keys and salts used here are fixed, published values so that anyone can
reproduce the examples byte for byte. They protect nothing. The transaction
ids are placeholders: no transaction has been broadcast, and the
`confirmations` fields are fabricated so the examples can exercise the full
pipeline offline.

| Vector | Value |
|---|---|
| Registry secret key | `0000…0003` |
| Warehouse secret key | `0000…0007` |
| Signing auxiliary randomness | 32 zero bytes |
| Asset salt | `11` repeated 32 times |
| Document salt, vehicle | `22` repeated 32 times |
| Attribute salt, chassis number | `33` repeated 32 times |
| Document salt, warehouse receipt | `44` repeated 32 times |

Real deployments generate a fresh 32 byte salt per asset and per document from
a cryptographically secure source. Reusing a salt across documents links them,
which is the thing the salts exist to prevent.

---

## `vehicle-title/`

A single vehicle record, anchored on its own, with a document commitment, a
hidden chassis number and a later revocation.

| File | What it is |
|---|---|
| `asset-record.json` | The signed public record |
| `registration-certificate.txt` | The specimen document, held off chain |
| `disclosure.json` | Salts and hidden values. The issuer holds this and releases it only to a party entitled to confirm the record. **Publishing this file would undo the privacy the commitments provide.** |
| `anchor.json` | What an independent observer reads off the chain |
| `issuers.json` | A minimal issuer key directory |
| `status-record-revocation.json` | A later signed statement revoking the record |
| `verification-transcript.txt` | Actual output of the verifier |

Note what the public record does and does not contain. The chassis number
appears only as a commitment, because a chassis number has far less entropy
than its seventeen characters suggest and an unsalted hash could be brute
forced. The registered keeper does not appear at all.

The revocation shows the correction model: nothing is deleted or rewritten. A
revoked record stays verifiable forever, and a reader who sees only the
original record without the revocation is reading an incomplete history. That
is why specification section 11 treats an unchecked status set as a check that
was not satisfied rather than one that passed.

## `warehouse-receipt/`

A commodity receipt at verification level 2, issuer attested rather than
registry recognised. Included to show the same format carrying a different
asset class with a different evidence level.

Note `"quantity_kg": 37800` rather than a weight in tonnes. Floating point
numbers are prohibited throughout, because their canonical form varies between
languages and would silently break signature interoperability. Quantities are
integers in a stated minor unit.

## `batch-anchor/`

Sixty four vehicle records under one Bitcoin anchor, which is the mode that
matters for an institution.

| File | What it is |
|---|---|
| `batch-manifest.json` | The registry's own index. **Not needed to verify anything.** |
| `anchor.json` | The single on chain commitment covering all 64 records |
| `record-000/`, `record-037/`, `record-063/` | Three records with their inclusion proofs and verifier output |
| `proof-sizes.json` | Proof length per leaf |

The point of this example is what a holder needs: their own record and a proof
of at most six sibling hashes, 192 bytes. They never need the manifest, the
registry's database, or the registry's cooperation.

`record-063` is the last leaf, deliberately included because an odd final node
is promoted rather than duplicated and therefore takes a shorter path. That
rule exists to avoid CVE-2012-2459, where duplication makes distinct leaf sets
produce the same root, which in a registry would let an issuer prove inclusion
of a record it never committed to.

---

## Checking them yourself

```bash
# Single anchor, with the issuer directory supplied
python3 reference/cli/satdeed_cli.py verify \
    examples/vehicle-title/asset-record.json \
    --anchor examples/vehicle-title/anchor.json \
    --issuers examples/vehicle-title/issuers.json

# A document against its commitment
python3 reference/cli/satdeed_cli.py check-document \
    examples/vehicle-title/asset-record.json \
    --type registration_certificate \
    --salt 2222222222222222222222222222222222222222222222222222222222222222 \
    --file examples/vehicle-title/registration-certificate.txt

# Batch inclusion, using only the record and its proof
python3 reference/cli/satdeed_cli.py verify \
    examples/batch-anchor/record-063/asset-record.json \
    --proof examples/batch-anchor/record-063/inclusion-proof.json \
    --anchor examples/batch-anchor/anchor.json

# Decode the 40 byte on chain payload by hand
python3 reference/cli/satdeed_cli.py decode-anchor \
    $(python3 -c "import json;print(json.load(open('examples/batch-anchor/anchor.json'))['op_return_data'])")
```

Things worth trying, all of which should fail:

- change one character in any record and verify again, the signature breaks
- change one byte of `registration-certificate.txt`, the document check fails
- use the wrong salt with the correct document, the check still fails
- verify `record-037` against `record-000`'s proof, inclusion fails
- edit `leaf_count` in an inclusion proof, the anchor cross check rejects it

If any of those passes, that is a finding worth an issue.
