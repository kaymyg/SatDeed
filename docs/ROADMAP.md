# SatDeed Implementation Roadmap

Six phases. Each one has an exit criterion that can be checked by someone who
did not do the work, because a phase that ends when its author feels it is
finished never ends.

Dates are deliberately absent. Phase 3 onward depends on finding institutional
partners, and committing to dates for work that depends on other people's
decisions produces a roadmap that is wrong within a month.

Current position: **Phase 1 in progress, Phase 2 partially delivered.** The
reference library, test suite and worked examples in this repository are
Phase 2 deliverables that were built early because specifying a format without
implementing it tends to produce a format that cannot be implemented.

---

## Phase 1, specification

**Objective.** A specification precise enough that two independent
implementations agree byte for byte.

**Delivered.**

- Record format and JSON Schema
- Canonical serialization rules, RFC 8785 subset
- Asset identifier derivation with salted commitments
- Document and attribute commitment schemes
- Merkle construction with promotion, and inclusion proofs
- Bitcoin anchor payload, 40 bytes
- Verification algorithm
- Explicit statement of what verification does not establish

**Outstanding.**

- Issuer key registration, rotation and revocation, the largest gap
- Transfer semantics
- Signature agility
- A decision on whether to express records as W3C Verifiable Credentials

**Exit criterion.** A second implementation, written in another language by
someone who did not write the first, reproduces every record hash, identifier
and Merkle root in `examples/` without consulting the Python source. Until
that has happened, the specification is ambiguous in ways its author cannot
see.

---

## Phase 2, reference implementation

**Objective.** Make the specification falsifiable.

**Delivered.**

- Dependency free Python library
- Canonical serialization, identifiers, commitments, Merkle trees, BIP-340
  signatures, verification pipeline
- Command line tool for hashing, verifying, document checking and fee
  estimation
- 55 tests, including adversarial cases for the Merkle construction
- Worked examples generated and self verified by the library

**Outstanding.**

- A second implementation in TypeScript or Rust, which is also the Phase 1
  exit criterion
- A verifier that reads anchors from a Bitcoin node rather than taking them as
  input, shipped separately from the core library so the core stays free of
  chain dependencies
- Testnet anchoring, with real transactions and real confirmations

**Exit criterion.** A batch of at least 1,000 records anchored on testnet, and
an inclusion proof for one of them verified by an implementation that was not
involved in producing the batch.

---

## Phase 3, vehicle title demonstration

**Objective.** Find out what breaks when the protocol meets an actual asset
and an actual institution.

**Scope.** One vehicle. Registration document committed, issuer attested
record, anchored on mainnet, independently verified, a transfer workflow
exercised, and a revocation issued and verified.

The demonstration must show the gap between record control and legal
ownership rather than paper over it. If the demonstration leaves a viewer
believing that holding the record means owning the vehicle, it has failed
regardless of whether the software worked.

**Exit criterion.** An independent party, given only the public record and the
disclosures they are entitled to, verifies the asset and correctly states what
the verification does and does not prove. A written account of what went
wrong, published whether or not it is flattering.

---

## Phase 4, institutional pilot

**Objective.** Test whether an institution will actually run this.

**Candidates.** Vehicle dealers, asset financiers, insurers, equipment
lessors, warehouse operators, commercial registries.

**What the pilot must measure.** Not whether the cryptography works, which
Phase 2 settles. It must measure whether staff can operate it, whether
verification costs less than the manual process it replaces, whether
disclosure handling survives contact with real privacy requirements, and
whether the institution's lawyers will sign off on publishing commitments that
make its own future revisions detectable.

That last point is the pilot's real subject. Everything else is engineering.

**Exit criterion.** One institution anchors its records on a schedule for
three consecutive months without the project team operating the system for
them, and a third party verifies a record the institution issued.

---

## Phase 5, multi asset expansion

**Objective.** Extend beyond vehicles once the format has survived one asset
class.

**Candidates.** Real property, agricultural commodities, commercial equipment,
warehouse receipts, trade invoices, intellectual property.

Each class needs its own identifying attribute set and its own analysis of
which attributes must be committed rather than published. Land in particular
needs care, since boundary data is both sensitive and frequently revised.

**Exit criterion.** Two asset classes beyond vehicles, each with a published
attribute profile and at least one issuer anchoring in production.

---

## Phase 6, financial extensions

**Objective.** Only once the record layer is boring and reliable.

**Candidates.** Collateral verification, asset backed financing, productive
asset leasing, performance bonds, insurance integration.

Every one of these is a regulated activity in most jurisdictions. They are
listed as possibilities rather than plans, and each would need its own legal
analysis before any code is written.

**The discipline this phase requires.** Financial extensions must not become
prerequisites for the base protocol. The moment a registry has to interact
with a lending market to anchor a title, the standard has lost the property
that made it adoptable.

**Exit criterion.** Not defined. Defining it now would be guessing, and this
phase should not begin until Phase 4 has produced evidence about what
institutions actually want.

---

## Sequencing risks

**The temptation to skip to Phase 6.** Financial applications are where the
revenue is, and every incentive points at building them before the record
layer is trustworthy. Doing so would produce a financial product resting on an
unproven format, which is the standard way these projects fail.

**The second implementation keeps getting deferred.** It is the exit criterion
for both Phase 1 and Phase 2 because it is the only test that catches
ambiguity in the specification, and it is exactly the kind of work that is
easy to postpone indefinitely.

**Phase 4 may simply fail.** Institutions may decline to make their own
records auditable. That is a real possibility rather than a risk to be
mitigated, and it should be discovered in a pilot rather than after years of
building.
