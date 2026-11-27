# SatDeed

**A Bitcoin anchored standard for real world asset identity, provenance and
ownership records.**

> Bitcoin should store the proof, not the paperwork.

**Status: draft, version 0.1.** Nothing here is stable. This repository exists
to be implemented, attacked and revised.

> ### Open call for independent review
>
> **[Issue #1: Independent Implementation and Technical Review of SatDeed](https://github.com/kaymyg/SatDeed/issues/1)**
>
> There is one implementation of this specification and the same people wrote
> both, which means every ambiguity in the text has been resolved the same way
> twice. The project is asking developers to build a second implementation from
> the specification alone, to attack the construction, and to challenge the
> reason SatDeed should exist at all, including the case for deleting most of
> it in favour of existing work.
>
> SatDeed should earn its place through independent verification, not through
> the strength of its claims. No new features are being accepted until that
> review has had a chance to happen.

---

## What this is

A registry holds records: vehicle titles, warehouse receipts, land parcels,
equipment registers. Those records are only as trustworthy as the institution
holding them, because an institution that can rewrite its own history leaves
no trace when it does.

SatDeed publishes a 32 byte cryptographic commitment to those records on
Bitcoin. The records themselves, and every supporting document, stay off chain
where they belong.

In one sentence:

> SatDeed does not make a registry honest. It makes a registry's dishonesty
> detectable after the fact, by anyone, without the registry's cooperation.

That is a narrower claim than most tokenization proposals make, and it is the
one that survives examination. See
[`docs/DESIGN-RATIONALE.md`](docs/DESIGN-RATIONALE.md) section 1 for the full
argument, and section 9 for the known weaknesses.

## What it explicitly is not

- Not a new blockchain, and not a bridge to one
- Not a token, governance or otherwise
- Not a claim that holding an inscription means owning a vehicle
- Not a replacement for land registries, courts or physical inspection
- Not a document store

A passing verification proves that a well formed record was signed by a stated
key and committed to Bitcoin at a stated depth. It proves nothing about
whether the asset exists, whether the issuer had authority, or who owns
anything. [Specification section 12](spec/SPECIFICATION.md) sets this out in
full, because a standard that is vague about its own limits is worse than no
standard at all.

---

## Repository contents

| Path | What it holds |
|---|---|
| [`WHITEPAPER.md`](WHITEPAPER.md) | The proposal, its motivation and long term vision |
| [`spec/SPECIFICATION.md`](spec/SPECIFICATION.md) | Normative technical specification, v0.1 |
| [`spec/schema/`](spec/schema/) | JSON Schema for the record format |
| [`docs/DESIGN-RATIONALE.md`](docs/DESIGN-RATIONALE.md) | Why it is built this way, related work, rejected alternatives, known weaknesses |
| [`docs/ROADMAP.md`](docs/ROADMAP.md) | Six phases, each with a checkable exit criterion |
| [`reference/`](reference/) | Dependency free Python implementation, CLI and tests |
| [`examples/`](examples/) | Worked examples, every value generated and verified by the library |

---

## Quick start

No dependencies beyond Python 3.10 or later.

```bash
git clone https://github.com/kaymyg/SatDeed.git
cd SatDeed

# Run the test suite
python3 -m pytest reference/tests -q

# Verify the vehicle title example end to end
python3 reference/cli/satdeed_cli.py verify \
    examples/vehicle-title/asset-record.json \
    --anchor examples/vehicle-title/anchor.json \
    --issuers examples/vehicle-title/issuers.json

# Check a document against its commitment
python3 reference/cli/satdeed_cli.py check-document \
    examples/vehicle-title/asset-record.json \
    --type registration_certificate \
    --salt 2222222222222222222222222222222222222222222222222222222222222222 \
    --file examples/vehicle-title/registration-certificate.txt

# Verify a record inside a 64 record batch, using only that record and its proof
python3 reference/cli/satdeed_cli.py verify \
    examples/batch-anchor/record-063/asset-record.json \
    --proof examples/batch-anchor/record-063/inclusion-proof.json \
    --anchor examples/batch-anchor/anchor.json

# Anchoring cost per record at various batch sizes and fee rates
python3 reference/cli/satdeed_cli.py fees

# Regenerate every example from scratch
python3 reference/tools/generate_examples.py
```

---

## How it works, briefly

**1. Derive a stable identifier.** From the issuer namespace plus the
attributes that identify the physical thing, under a per asset salt. The salt
matters: a chassis number has far less entropy than its seventeen characters
suggest, so an unsalted identifier would let anyone confirm a guess.

**2. Commit to documents, do not publish them.** Each document is committed as
`tagged_hash(salt || SHA256(file))`. The commitment goes in the public record.
The salt and the file go to whoever is entitled to see them.

**3. Sign the record.** BIP-340 Schnorr over the tagged hash of the canonical
serialization, so any change to any field invalidates the signature.

**4. Anchor to Bitcoin.** A fixed 40 byte payload carrying a Merkle root and
the leaf count. One transaction covers the whole batch.

**5. Verify independently.** A holder needs their record and their inclusion
proof, never the registry's database. A proof for a batch of a million
records is at most 640 bytes.

### What it costs

One anchoring transaction is roughly 162 vbytes.

| Records per batch | 1 sat/vB | 5 sat/vB | 20 sat/vB | 100 sat/vB |
|---|---|---|---|---|
| 1 | 162 sat | 810 sat | 3,240 sat | 16,200 sat |
| 100 | 1.62 sat | 8.10 sat | 32.4 sat | 162 sat |
| 10,000 | 0.016 sat | 0.081 sat | 0.324 sat | 1.62 sat |
| 1,000,000 | 0.00016 sat | 0.0008 sat | 0.0032 sat | 0.0162 sat |

Per record, total fee divided by batch size. A national registry anchoring its
whole database daily spends a few thousand satoshis a day. Cost is not the
obstacle to adoption, and the roadmap says plainly what is.

---

## Design decisions worth knowing about

**Tagged hashes everywhere.** Every hash carries a domain separating tag, so a
value produced for one purpose can never be substituted into another.

**Merkle promotion, not duplication.** Bitcoin's block tree duplicates the odd
final node, which makes distinct leaf sets collide. That is CVE-2012-2459, and
in a registry it would let an issuer prove inclusion of a record it never
committed to. SatDeed promotes the odd node instead, and the test suite
asserts the roots differ.

**The leaf count is on chain.** For some index and size pairs an inclusion
proof cannot distinguish two tree sizes. This was found by the test suite, not
by design. The anchored leaf count is what resolves it, and the repository
keeps tests for both the ambiguity and the cross check that catches it.

**No chain client in the library.** A verifier that trusts one API endpoint
has reintroduced the single point of dependence the whole design exists to
remove. Anchor observations are an input, supplied by whatever node the
verifier actually trusts.

**Ordinals are optional and not the default.** Ordinals numbering is an
indexer convention rather than a consensus rule, so a record whose meaning
depends on which indexer you ask has not achieved independent verification.

**Bearer control mode is not implemented.** Key loss meaning unrecoverable
title, and key theft meaning title theft, are poor properties for a vehicle.
The argument for demoting it is in
[`docs/DESIGN-RATIONALE.md`](docs/DESIGN-RATIONALE.md) section 6.

---

## Known gaps

Stated here rather than buried, because the gaps determine whether this is
worth anyone's time.

1. **Issuer key management is unspecified.** Registration, rotation and
   revocation are all deferred to v0.2. Do not build a production issuer
   directory on v0.1.
2. **Transfer semantics are absent.** A transfer is currently just a new
   record superseding the old one.
3. **Legal recognition is untested.** SatDeed is an evidence layer. Whether a
   court gives that evidence weight is jurisdiction specific.
4. **Substantial overlap with existing work.** OpenTimestamps already does
   Merkle batch anchoring to Bitcoin, and W3C Verifiable Credentials already
   cover signed issuer assertions with revocation. Section 2 of the design
   rationale argues for alignment rather than reinvention, and a reader who
   concludes SatDeed is those two plus an asset identifier namespace has
   understood it correctly.
5. **Adoption is the real obstacle, not engineering.** The institutions best
   placed to adopt this have the least to gain from being auditable.

---

## Contributing

Looking for something to work on? See [HELP_WANTED.md](HELP_WANTED.md).

Review of the specification is more valuable than code right now. The most
useful contribution available is a second implementation in another language,
written without reading the Python, that reproduces every value in
`examples/`. That is the exit criterion for Phase 1 and the only reliable test
for ambiguity in the specification.

See [`CONTRIBUTING.md`](CONTRIBUTING.md).

## Security

The reference implementation's pure Python BIP-340 is for examples and tests.
It is not constant time and must not handle production keys. Use libsecp256k1
or a hardware signer.

For anything sensitive, open a private security advisory rather than a public
issue.

## Licence

Specification and documents: [CC BY 4.0](LICENSE-DOCS).
Code: [MIT](LICENSE-CODE).

The specification is permissively licensed on purpose. A standard that one
party controls is not a standard.
