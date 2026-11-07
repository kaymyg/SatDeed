# SatDeed Technical Specification

**Version 0.1 (draft)** · November 2026

Status: draft for discussion. Nothing in this document is stable. Version 0.1
exists to be implemented, attacked and revised, not to be relied on.

The key words MUST, MUST NOT, REQUIRED, SHALL, SHALL NOT, SHOULD, SHOULD NOT,
RECOMMENDED, MAY and OPTIONAL are to be interpreted as described in RFC 2119
and RFC 8174 when, and only when, they appear in capitals.

---

## 1. Scope

This document specifies the SatDeed record format, its canonical
serialization, the derivation of asset identifiers, the commitment schemes for
documents and sensitive attributes, the Merkle construction used for batch
anchoring, the Bitcoin anchor payload, and the verification algorithm.

It does not specify user interfaces, storage services, legal instruments,
issuer accreditation, or any financial product. Those are out of scope by
design, and section 12 states plainly what a passing verification does and
does not establish.

### 1.1 Conformance

An implementation is conformant if it produces and accepts exactly the byte
sequences this document requires. Two conformant implementations given the
same record MUST compute the same record hash. This is the only
interoperability property that matters, and it is the one the test vectors in
`examples/` exist to check.

---

## 2. Notation and primitives

| Symbol | Meaning |
|---|---|
| `SHA256(x)` | FIPS 180-4 SHA-256 of the byte string `x` |
| `a \|\| b` | concatenation |
| `utf8(s)` | UTF-8 encoding of the string `s`, no byte order mark |
| `hex(x)` | lowercase hexadecimal, no prefix, no separators |

### 2.1 Tagged hashes

All SatDeed hashes are tagged hashes in the style of BIP-340:

```
tagged_hash(tag, m) = SHA256( SHA256(utf8(tag)) || SHA256(utf8(tag)) || m )
```

Implementations MUST use the following tags, exactly as written:

| Tag | Used for |
|---|---|
| `SatDeed/v0.1/record` | record hash |
| `SatDeed/v0.1/leaf` | Merkle leaf |
| `SatDeed/v0.1/branch` | Merkle internal node |
| `SatDeed/v0.1/document` | document commitment |
| `SatDeed/v0.1/attribute` | attribute commitment |
| `SatDeed/v0.1/asset-id` | asset identifier derivation |
| `SatDeed/v0.1/asset-id-checksum` | display form checksum |

Domain separation is not decoration here. Without distinct tags, a 32 byte
value produced as a document commitment is indistinguishable from one produced
as a Merkle internal node, and an issuer could be induced to commit to a value
that is simultaneously valid in two roles. The tag is carried in the preimage
of every hash so that no such substitution is possible.

The tag string embeds the specification version. A v0.2 record will therefore
hash to a different value than a byte identical v0.1 record, and no cross
version confusion is possible.

---

## 3. Canonical serialization

A SatDeed record is a JSON value. Hashing and signing operate on its canonical
serialization, which MUST be produced as specified in RFC 8785 (JSON
Canonicalization Scheme), subject to the restrictions below.

### 3.1 Restrictions on permitted values

1. Floating point numbers MUST NOT appear anywhere in a record. Their RFC 8785
   canonical form depends on the ECMAScript number to string algorithm, which
   is a recurring source of cross language disagreement and would silently
   break signature interoperability. Quantities that would otherwise be
   fractional MUST be expressed as integers in a stated minor unit, for
   example `"quantity_kg": 37800` or `"area_cm2": 48500`.
2. Integers MUST lie within the range `[-(2^53 - 1), 2^53 - 1]`.
3. Strings MUST be valid Unicode with no unpaired surrogate code points.
4. Object member names MUST be unique within an object.

A serializer MUST reject any record violating these rules rather than attempt
to coerce it.

### 3.2 Member ordering

Object members MUST be ordered by the code unit sequence of their UTF-16
representation, as RFC 8785 requires. For member names drawn from the Basic
Multilingual Plane this is identical to code point order. It differs for names
containing characters above U+FFFF, and an implementation that sorts by code
point will disagree with a conformant one on such names. Implementations
SHOULD restrict member names to ASCII, which makes the distinction moot.

### 3.3 Example

Input:

```json
{"b": 1, "a": {"z": null, "y": [3, 1, 2]}}
```

Canonical form, with no whitespace, members sorted, array order preserved:

```
{"a":{"y":[3,1,2],"z":null},"b":1}
```

---

## 4. The record

### 4.1 Common members

Every record, of any `record_type`, MUST contain:

| Member | Type | Notes |
|---|---|---|
| `satdeed` | string | MUST be `"0.1"` |
| `record_type` | string | `"asset"` or `"status"` |
| `asset_uid` | string | `hex` of the 32 byte asset uid, section 5 |
| `issuer` | object | `issuer_id` and `public_key` |
| `issued_at` | string | `YYYY-MM-DDTHH:MM:SSZ`, UTC, whole seconds |
| `status` | string | `active`, `superseded`, `revoked` or `disputed` |

`issued_at` is the issuer's own assertion and carries no independent
evidentiary weight. A verifier MUST NOT treat it as proof of time. The block
containing the anchor is what establishes a time the record cannot predate.

`issuer.issuer_id` is a stable lowercase label. A DNS name under the issuer's
control is RECOMMENDED, because it is already globally unique and already has
an accountable owner, which a self chosen string is not.

`issuer.public_key` is a 32 byte x only secp256k1 public key as defined by
BIP-340.

### 4.2 Asset records

A record with `record_type` of `"asset"` MUST additionally contain `asset_id`,
`asset_class` and `verification_level`, and MAY contain `attributes`,
`attribute_commitments`, `documents` and `supersedes`.

`attributes` carries public descriptive data. Anything that identifies a
person, and anything with low enough entropy to be guessed, MUST NOT appear
here. It belongs in `attribute_commitments`.

`documents` carries commitments, never content. Each entry has a `type`, a
`digest_algorithm` of `"SHA-256"`, a 32 byte `commitment` computed per section
6, and a `storage` array of retrieval hints. The `storage` array MAY be empty,
which means the holder keeps the document. A verifier MUST NOT treat a storage
reference as authoritative: the commitment is what binds, and a document
fetched from a listed URL is worth exactly as much as one handed over on a
memory stick, which is to say it is worth whatever its hash says it is worth.

`asset_class` is an open vocabulary. Values registered in v0.1: `vehicle`,
`real_property`, `warehouse_receipt`, `equipment`, `commodity`, `invoice`,
`intellectual_property`.

### 4.3 Status records

A record with `record_type` of `"status"` MUST contain `supersedes`, naming the
record hash it replaces, and `reason`, a human readable explanation.

Status records are the only correction mechanism. Nothing is ever deleted or
rewritten, because a record whose history can be quietly revised provides no
more assurance than the database it was meant to improve on. A revocation is a
new signed statement; both it and the record it supersedes remain verifiable
forever.

### 4.4 Signature

`issuer_signature` is an object with `algorithm` of
`"BIP340-schnorr-secp256k1"` and a 64 byte `signature` in lowercase hex.

### 4.5 Record hash

```
record_hash = tagged_hash("SatDeed/v0.1/record", canonical(R))
```

where `R` is the record with the `issuer_signature` member removed. The
signature commits to the hash, so it cannot be part of its own preimage.

The signature is computed as `BIP340_Sign(record_hash, seckey)` and verified as
`BIP340_Verify(record_hash, public_key, signature)`.

Because the hash covers the canonical serialization of every other member,
adding, removing, reordering or altering any field invalidates the signature.

---

## 5. Asset identifiers

### 5.1 Derivation

```
asset_uid = tagged_hash("SatDeed/v0.1/asset-id",
                        utf8(namespace) || 0x00 || salt || canonical(attrs))
```

`namespace` is the issuer's `issuer_id`. `salt` is 32 bytes from a
cryptographically secure source, generated once per asset. `attrs` is a JSON
object of the attributes that identify the physical thing and that will never
change.

The identifier MUST NOT be derived from anything mutable. Not an inscription
number, not a wallet address, not a storage URL, not a database row id, not
the owner. An identifier that changes when the asset changes hands is not an
identifier for the asset; it is an identifier for the transaction.

The `0x00` separator prevents a namespace and salt boundary ambiguity: without
it, a namespace ending in bytes that the salt could begin with would admit two
distinct inputs with the same concatenation.

### 5.2 Why the salt is mandatory

A chassis number looks like seventeen characters of entropy and is nothing of
the sort. Once make, model and year are known, the plausible space collapses
to something a laptop enumerates in seconds. An unsalted derivation would
therefore turn a public identifier into a confirmation oracle: anyone could
test a guess and learn which vehicle a record describes. The salt closes this.
The issuer holds it and discloses it only to a party already entitled to know
which asset is in question.

The same reasoning applies to title numbers, invoice numbers, serial numbers
and national identifiers, which is to say to almost every attribute that
usefully identifies anything.

### 5.3 Display form

```
SD0-XXXXXXXX-XXXXXXXX-XXXXXXXX-XXXXXXXX-CCCC
```

The body is the first 20 bytes of `asset_uid` in Crockford base32, grouped in
eights. `CCCC` is the first four characters of
`base32(tagged_hash("SatDeed/v0.1/asset-id-checksum", body))`.

Crockford base32 excludes I, L, O and U, so the characters most often confused
in handwriting and speech cannot occur. Decoders MUST accept I and L as 1, O
as 0, and U as V on input, and MUST be case insensitive. The checksum catches
single character transcription errors, which matters because these strings
will be read down telephones and copied off printed documents.

Truncation to 20 bytes gives 160 bits, which is ample for collision resistance
against any party able to grind identifiers. The full 32 byte `asset_uid`
remains the canonical form and is what appears in the record.

---

## 6. Commitments

### 6.1 Documents

```
document_commitment = tagged_hash("SatDeed/v0.1/document", salt || SHA256(file))
```

`salt` is 32 fresh random bytes per document. The salt and the file are held
off chain and disclosed together to a verifier.

A matching commitment establishes one thing and one thing only: the presented
bytes are identical to the bytes committed at issuance. It does not establish
that the original document was genuine, correctly issued, or legally valid.
Those are separate questions, answered by the issuer attestation and
ultimately by law.

### 6.2 Attributes

```
attribute_commitment = tagged_hash("SatDeed/v0.1/attribute",
                                   salt || canonical({"name": n, "value": v}))
```

Used for identifying attributes that MUST NOT be published in the clear.

### 6.3 Selective disclosure

A holder discloses an attribute by revealing its salt and value. A verifier
recomputes the commitment and compares. Attributes not disclosed stay hidden,
and the record reveals nothing about them beyond their count and names.

Member names are visible in the record. An implementation that considers the
name itself sensitive, for example `"outstanding_charge_holder"`, SHOULD place
the whole object in a single commitment rather than enumerate the members.

---

## 7. Merkle batch anchoring

### 7.1 Construction

```
leaf(i)        = tagged_hash("SatDeed/v0.1/leaf", record_hash(i))
branch(l, r)   = tagged_hash("SatDeed/v0.1/branch", l || r)
```

Leaves are ordered as the issuer chooses and that order is fixed for the life
of the batch. Each level is reduced pairwise, left to right. When a level has
an odd number of nodes, the final node is **promoted unchanged** to the next
level.

The final node MUST NOT be duplicated. Duplication is the Bitcoin block header
behaviour and it causes distinct leaf sets to produce identical roots, the
defect catalogued as CVE-2012-2459. For a registry this is not a theoretical
nuisance: it would let an issuer produce an inclusion proof for a record it
never committed to, which destroys the only property batch anchoring is
supposed to provide.

An empty batch has no root and MUST NOT be anchored.

### 7.2 Inclusion proofs

A proof is the leaf index, the leaf count, and the ordered list of sibling
hashes from the bottom upward, each tagged with the side the sibling sits on.
A promoted node has no sibling at its level and consumes no step.

Verification recomputes the root and MUST additionally:

- reject a proof whose `index` is outside `[0, leaf_count)`
- reject a proof with unused trailing steps
- reject a proof whose declared side contradicts the parity of the position

### 7.3 Why the leaf count is anchored on chain

For many index and size pairs the branch shape above a leaf is identical
across two different tree sizes. Leaf 2 of a five leaf tree and leaf 2 of a
six leaf tree are one such pair: the same proof verifies against the same root
under either claimed size. A verifier that accepted a self declared tree size
would therefore accept a proof against a batch size the issuer never committed
to.

Carrying the count in the on chain payload removes the ambiguity. A verifier
MUST reject a proof whose `leaf_count` differs from the anchored one. The test
suite contains both halves of this, the indistinguishable case and the
cross check that catches it, so that the reason this field exists is not lost.

### 7.4 Proof size

A batch of `n` records yields proofs of at most `ceil(log2(n))` siblings, each
32 bytes. A batch of one million records gives proofs of at most 640 bytes. A
holder needs their record and their proof, never the batch.

---

## 8. Bitcoin anchoring

### 8.1 Payload

A SatDeed anchor is a fixed 40 byte payload:

| Offset | Size | Field | Value |
|---|---|---|---|
| 0 | 2 | magic | `0x53 0x44`, the ASCII `SD` |
| 2 | 1 | version | `0x01` |
| 3 | 1 | kind | `0x01` single record, `0x02` batch root, `0x03` status batch |
| 4 | 32 | commitment | record hash or Merkle root |
| 36 | 4 | leaf count | big endian, MUST be 1 when kind is `0x01` |

### 8.2 OP_RETURN

The payload MAY be carried in an `OP_RETURN` output. Forty bytes of data gives
a 42 byte script, which leaves ample room inside the 80 byte standardness
limit that Bitcoin Core has applied to `OP_RETURN` relay for most of its
history.

That limit has been contested and its default has moved. SatDeed deliberately
sits far enough below any value under discussion that policy changes do not
affect it. Implementers MUST check the relay policy of the node they broadcast
through rather than assume a figure from this document, which is a statement
about a moving target.

### 8.3 Taproot script path

The payload MAY instead be committed in a Taproot script path leaf. This keeps
it out of the UTXO set and off chain entirely until the output is spent, which
is cheaper and more private.

Taproot is the RECOMMENDED construction for issuers anchoring on a schedule.
`OP_RETURN` is specified first because it is trivially indexable by any
explorer with no cooperation from the issuer, and the point of the standard is
that verification does not depend on the issuer's continued goodwill.

### 8.4 Ordinals inscriptions

An inscription MAY be associated with a record. This is OPTIONAL and v0.1
treats it as a strictly additive convenience.

It is not the default, and implementers should understand why. Ordinals
numbering is an indexer convention rather than a consensus rule, so two
indexers can disagree about what a given inscription is, and a record whose
meaning depends on which indexer you ask has not achieved independent
verification. Nothing in sections 1 to 8.3 requires an inscription or an
indexer.

### 8.5 Cost

A minimal anchoring transaction with one Taproot key path input, one 40 byte
`OP_RETURN` output and one Taproot change output is approximately 162 vbytes.

| Records per batch | 1 sat/vB | 5 sat/vB | 20 sat/vB | 100 sat/vB |
|---|---|---|---|---|
| 1 | 162 sat | 810 sat | 3,240 sat | 16,200 sat |
| 100 | 1.62 sat | 8.10 sat | 32.4 sat | 162 sat |
| 10,000 | 0.016 sat | 0.081 sat | 0.324 sat | 1.62 sat |
| 1,000,000 | 0.00016 sat | 0.0008 sat | 0.0032 sat | 0.0162 sat |

Figures are satoshis per record, total fee divided by batch size. Reproduce
them with `python3 reference/cli/satdeed_cli.py fees`.

The practical reading: a national vehicle registry anchoring its entire
database daily spends a few thousand satoshis a day at ordinary fee rates.
Cost is not the obstacle to adoption. Issuer accountability and legal
recognition are, and no amount of engineering addresses those.

---

## 9. Verification levels

| Level | Name | What it means |
|---|---|---|
| 0 | Self declared | The subject asserted it. Nobody checked. |
| 1 | Document verified | Supporting documents were examined and committed. |
| 2 | Issuer attested | A recognised issuer authenticated the information. |
| 3 | Registry recognised | The asset is linked to a legal or institutional registry. |
| 4 | Independently audited | The record and the issuing process were examined by a third party. |

These describe the evidence available. They are not a legal ranking, they do
not travel between jurisdictions, and a level 4 record can still describe an
asset that is stolen, double financed or encumbered. The level tells a reader
how much checking happened, not whether the answer was right.

Levels are asserted by the issuer. A level 3 claim from an issuer with no
registry relationship is a false statement in a signed document, which is a
problem for law rather than for cryptography, and SatDeed does not pretend
otherwise.

---

## 10. Issuer keys

v0.1 specifies record signing and nothing more. Key registration, rotation,
revocation and authorisation scopes are deferred to v0.2, and this is the
largest known gap in the specification.

Until then, a verifier obtains issuer keys out of band and supplies them as a
directory. The reference verifier reports `issuer_identity` as failed when no
directory is supplied, rather than quietly passing, so that an integrator
cannot mistake a valid self signature for a verified issuer.

Implementers should not build a production issuer directory on v0.1. The
shape of that mechanism is the main open design question, and section 4 of
`docs/DESIGN-RATIONALE.md` discusses the candidates.

---

## 11. Verification algorithm

Given a record, and optionally an inclusion proof, an anchor observation and
an issuer directory, a verifier MUST perform these steps and report each
outcome separately:

1. **Structure.** Validate against the schema and the rules in sections 3 and
   4. On failure, stop: nothing downstream is meaningful.
2. **Record hash.** Compute per section 4.5.
3. **Signature.** Verify per BIP-340 against `issuer.public_key`. A record
   with no signature MUST NOT be reported as verified.
4. **Issuer identity.** If a directory was supplied, confirm the key matches
   the entry for `issuer_id`. If none was supplied, report this check as not
   satisfied rather than skipping it silently.
5. **Anchor payload.** Decode per section 8.1. Reject anything lacking the
   magic bytes.
6. **Commitment.** For kind `0x01`, the commitment MUST equal the record hash.
   For `0x02` or `0x03`, verify the inclusion proof against the commitment and
   confirm the proof's leaf count equals the anchored one.
7. **Confirmations.** Compare against the caller's threshold. Six is a
   reasonable default. A high value asset SHOULD use more.
8. **Status.** If the issuer's status set was supplied, confirm no later
   record supersedes or revokes this one. Where two status records conflict,
   the later anchor wins, ordered by block height, then transaction index
   within the block, then output index.

A verifier MUST return the per check outcome rather than a single boolean. A
single boolean invites an integrator to treat "the maths checked out" as "the
asset is fine", and those are very different statements.

### 11.1 The verifier obtains its own chain data

The reference implementation deliberately ships no chain client. A verifier
that trusts one API endpoint for its anchor observations has reintroduced
precisely the single point of dependence that SatDeed exists to remove. The
anchor observation is an input to the pipeline, supplied by whatever node,
explorer or indexer the verifier actually trusts.

---

## 12. What a passing verification does not mean

Stated plainly, because a standard that is vague here is worse than no
standard at all.

A passing verification establishes that a well formed record was signed by a
stated key and committed to Bitcoin at a stated depth, and that a presented
document matches its commitment.

It does **not** establish:

- that the issuer had authority to make the statement
- that the physical asset exists, or matches the description
- that the asset is unencumbered, undisputed or not already financed elsewhere
- that the holder of the signing key is the legal owner
- that controlling any inscription or UTXO conveys legal title
- that no later record revokes this one, unless the status set was supplied
- that the committed document was genuine when it was committed

The protocol binds records to time and to a signer. Everything else is law,
institutions and physical inspection, and SatDeed is useful precisely to the
extent that it does not pretend otherwise.

---

## 13. Security considerations

**Tampering with a record** is detected by the signature. **Tampering with
history** is detected by the anchor: a registry that rewrites a record cannot
rewrite the commitment already in a block. This is the single property that
distinguishes SatDeed from a well run database, and it is worth stating
exactly: SatDeed does not make a registry honest, it makes a registry's
dishonesty detectable after the fact by anyone who kept a copy.

**Key compromise.** An attacker holding an issuer key can sign arbitrary
records. v0.1 has no revocation mechanism for keys, only for records, which is
the gap named in section 10. Issuers SHOULD keep signing keys in hardware and
SHOULD anchor from a separate key.

**Fraudulent issuance.** Nothing prevents anyone from creating a record for an
asset they do not own. Verification levels and issuer identity are the only
defences, and both reduce to knowing who the issuer is.

**Document availability.** A commitment proves a match when a document is
presented. It does not keep the document in existence. Issuers SHOULD maintain
redundant storage, and holders SHOULD keep their own copy, because the party
with the most to lose is the one who should hold the evidence.

**Privacy.** Commitments are hiding only if salts are unpredictable and kept
secret. A salt reused across documents links them. A salt derived from the
document defeats the whole mechanism.

**Chain reorganisation.** An anchor in a reorganised block is not an anchor.
Confirmation thresholds are the defence, and high value assets warrant more
than six.

**Quantum considerations.** SHA-256 commitments are comparatively robust.
BIP-340 signatures are not, against a sufficiently capable adversary. Records
anchored today remain evidence of what existed at a point in time even if the
signature scheme is later broken, which is an argument for anchoring early and
for treating signature agility as a v1.0 requirement.

---

## 14. Open questions for v0.2

1. Issuer key registration, rotation and revocation, section 10.
2. Transfer semantics, which v0.1 omits entirely. A transfer is currently just
   a new record superseding the old one, which does not capture the two party
   nature of a transfer.
3. Whether bearer control mode belongs in the standard at all. Key loss
   equalling unrecoverable title, and key theft equalling title theft, are
   poor properties for a vehicle, and `docs/DESIGN-RATIONALE.md` section 6
   argues for demoting it.
4. Signature agility, so that the scheme can change without a new record
   format.
5. Whether `asset_class` should remain an open vocabulary or move to a
   registry.
6. Selective disclosure that hides member names as well as values.
