# SatDeed Design Rationale

Why the protocol is shaped the way it is, what was rejected, and where the
argument is weakest. The white paper states the proposal. The specification
states the rules. This document is the reasoning, including the parts that
cut against the proposal.

---

## 1. The question the white paper has to answer

If an issuer must be trusted to attest that a document is real, what does
Bitcoin add?

This is the first question any competent reviewer asks, and a standard that
cannot answer it in one paragraph does not deserve the reader's time.

The answer is that the two mechanisms defend against different parties.

An issuer signature defends against **forgery by outsiders**. Someone who did
not hold the key cannot produce a record that appears to come from the
registry.

A Bitcoin anchor defends against **revision by the issuer**. Once a commitment
is in a block, the registry cannot later produce a different version of
history and claim it was always so. The registry can still lie at the moment
of issuance, and SatDeed does nothing about that. What it removes is the
ability to lie **retroactively**: to backdate a lien, to insert a prior owner,
to quietly amend a boundary after a dispute arises, or to lose an inconvenient
record.

That is a narrower claim than tokenized ownership, and it is the one that
survives examination. A registry whose current state can be rewritten without
trace offers no more assurance than the institution that runs it. A registry
whose history is anchored can be caught, by anyone who kept a copy, which
changes the incentives of the people operating it.

Stated as compactly as it can be:

> SatDeed does not make a registry honest. It makes a registry's dishonesty
> detectable after the fact, by anyone, without the registry's cooperation.

Everything in the specification follows from taking that sentence literally.
The parts of the design that look conservative, no token, no new chain, no
smart contracts, no on chain documents, are conservative because nothing more
is needed to deliver it, and anything more weakens the claim by adding
dependencies.

---

## 2. Related work, and why SatDeed is not simply a renaming of it

An honest proposal has to say what already exists. Three bodies of work cover
most of what SatDeed does.

### 2.1 OpenTimestamps

OpenTimestamps has, for roughly a decade, done the core mechanic: aggregate
many hashes into a Merkle tree, commit the root to Bitcoin, and hand each
submitter an inclusion proof. If the question is only "prove this file existed
by this date", OpenTimestamps already answers it, it is deployed, and SatDeed
should not reimplement it.

What OpenTimestamps does not provide is a **subject**. A timestamp proves a
byte string existed. It does not say what the byte string is about, who
asserted it, what asset it describes, how that asset is identified across
documents and years, or what happens when the assertion is later withdrawn.

SatDeed is the layer above: a record format with a stable asset identifier, an
issuer, a verification class and a supersession chain. The anchoring mechanism
underneath it is deliberately unremarkable, and an implementation that used
OpenTimestamps calendars for the anchoring step rather than anchoring directly
would be a conformant and probably sensible choice.

### 2.2 W3C Verifiable Credentials

The Verifiable Credentials data model already covers signed assertions by an
identified issuer about a subject, with the surrounding machinery for issuer
identifiers, key material, revocation and selective disclosure. A great deal
of what section 10 of the specification defers to v0.2 is work the VC
community has already done.

The honest position is that SatDeed overlaps substantially with VCs, and that
the overlap is an argument for alignment rather than for reinvention. The
differences that remain are real but narrow:

- VCs are issuer centric. Revocation is typically published by the issuer, so
  a verifier depends on the issuer's infrastructure being available and
  truthful at verification time. A Bitcoin anchor does not.
- VCs have no native notion of a commitment that is cheap to publish and
  expensive to repudiate at a point in time.
- The VC ecosystem's identifier layer is considerably heavier than a registry
  anchoring vehicle titles needs.

A reasonable v0.2 direction is to express the SatDeed record as a VC with a
Bitcoin anchoring proof type, keeping the asset identifier derivation and the
anchoring rules and inheriting the rest. That would reduce the specification
rather than grow it, which is usually the sign of a correct decision.

### 2.3 RFC 3161 timestamping and existing registry practice

RFC 3161 trusted timestamping is widely deployed and legally recognised in
many jurisdictions. Its weakness, from the point of view of this proposal, is
that the timestamp authority is itself a trusted party whose records can be
revised, which is the exact failure mode SatDeed targets. Its strength is that
it already has legal standing, which SatDeed does not.

These are complements. A registry can do both, and in the medium term probably
should.

### 2.4 What is actually new here

Little, individually. The contribution, if there is one, is the combination:
a stable salted asset identifier, commitments rather than content, a
supersession chain rather than mutation, batch anchoring sized for an
institution, and an explicit refusal to conflate record control with legal
title.

A reader who concludes that SatDeed is OpenTimestamps plus Verifiable
Credentials plus an asset identifier namespace has understood it correctly.
Whether that combination deserves a name of its own is a fair question, and
the answer depends on whether registries adopt it.

---

## 3. Why the documents stay off chain

The white paper's slogan, that Bitcoin should store the proof and not the
paperwork, is a design constraint rather than an aesthetic.

A 32 byte commitment is the same size whether it commits to a one page
certificate or a 400 megabyte survey archive. Blockspace is a scarce shared
resource priced by auction, and a standard that puts documents on chain would
be both expensive for its users and antisocial toward everyone else. It would
also be permanently wrong about privacy: a document placed on a public chain
cannot be unplaced, and a registry that published personal data there would
find itself in direct conflict with every data protection regime that
recognises a right to erasure.

Keeping documents off chain means the commitment survives forever while the
document can be deleted, corrected or restricted. That is the correct
asymmetry, and section 13 of the specification states its cost: the commitment
does not keep the document in existence.

---

## 4. Issuer keys, the largest unresolved problem

The specification signs records and stops there. Key registration, rotation,
revocation and authorisation scopes are all deferred. This is the weakest part
of v0.1, and pretending otherwise would be the easiest way to make the whole
thing useless.

The difficulty is that the problem is institutional rather than cryptographic.
A key is only meaningful if a verifier knows which key belongs to which
authority, and that mapping is exactly the trusted directory the design is
otherwise trying to avoid.

Candidates, with the objection to each:

**DNS based.** Publish the key under the issuer's domain. Simple, uses
authority the issuer already has. Depends on DNS and the certificate
authority system, and a government registry's domain is not always under the
registry's own control.

**Anchored key statements.** The issuer anchors its own key rotations as
SatDeed records, so the key history is as tamper evident as the asset records.
Attractively self consistent. Does not solve bootstrapping: a verifier still
has to learn the first key from somewhere.

**Existing PKI.** Use whatever certificates the institution already has.
Pragmatic, legally recognised in many places. Reintroduces certificate
authorities as a dependency.

**Web of trust.** Historically unsuccessful at institutional scale and there
is no reason to expect a different outcome here.

The likely answer is anchored key statements bootstrapped by DNS, with the
first key fetched over the existing system and every subsequent rotation
anchored so that a silent key substitution becomes detectable. That is a v0.2
design problem and it should be settled before anyone builds a production
issuer.

---

## 5. Why Merkle promotion rather than duplication

Bitcoin's own block header tree duplicates the final node when a level has an
odd count. Copying that behaviour would have been the obvious choice and it
would have been a serious mistake.

Duplication means the leaf sets `[a, b, c]` and `[a, b, c, c]` produce the
same root. In a block header this is a nuisance, catalogued as CVE-2012-2459.
In an asset registry it is an attack: an issuer could produce a valid
inclusion proof for a record it never committed to, which removes the only
guarantee batch anchoring provides.

Promotion, carrying the odd node up unchanged, avoids it. The test suite
asserts the two roots differ, so the property cannot be lost in a refactor.

A related subtlety is documented in specification section 7.3 and was found by
the test suite rather than by design. For some index and size pairs the branch
shape above a leaf is identical across two tree sizes, so an inclusion proof
alone cannot distinguish them. The defence is the leaf count in the on chain
payload. The repository keeps a test for the indistinguishable case as well as
for the cross check that catches it, so that a later reader does not remove
the field as redundant.

---

## 6. The case against bearer control mode

The white paper describes two ownership models, registry anchored and bearer
control, and presents them as parallel options. On reflection they are not
parallel, and v0.1 implements only the first.

In bearer control mode, control of an inscription or output stands for control
of the asset record. The properties that follow are bad ones for a vehicle or
a parcel of land:

- Key loss means unrecoverable title. A seed phrase written on paper and lost
  in a house fire would mean a family cannot prove ownership of their home.
- Key theft means title theft, instantly and irreversibly, with no court able
  to reverse the transfer on chain.
- The meaning of the transfer depends on Ordinals indexing, which is a
  convention rather than a consensus rule. Two indexers can disagree about
  what happened.
- No jurisdiction currently recognises possession of a UTXO as title to a
  physical asset, so the on chain transfer and the legally effective transfer
  are separate events that can diverge.

Registry anchored mode has none of these properties. Ownership changes are
made by the party that already has legal authority to make them, and Bitcoin's
role is to make the resulting history unrewritable.

The recommendation is therefore to demote bearer control to an optional
extension and to stop presenting it as a peer of the registry model. A
standard that offers two modes of very different safety, and leaves the choice
to the integrator, will see the unsafe one chosen by whoever least understands
the trade off.

---

## 7. Why no token

A governance or utility token would add a speculative asset whose price
movements have nothing to do with whether a vehicle title is correctly
recorded. It would create a constituency whose interest is the token rather
than the standard, it would invite securities regulation into a project that
is otherwise a document verification format, and it would give every
integrating institution a reason to refuse.

The protocol needs BTC for fees and nothing else. Specification section 8.5
shows the fee is negligible at batch scale, so there is no economic problem
that a token solves.

---

## 8. Why the verifier returns a list rather than a boolean

A single boolean invites the integrator to read "the mathematics checked out"
as "the asset is fine". Those are very different statements, and the gap
between them is where every real loss will occur.

The pipeline therefore reports each check separately, and declines to report a
record as verified when the issuer directory was not supplied, rather than
quietly treating a valid self signature as a verified issuer. An integrator
who wants a boolean must decide for themselves which checks their use case
requires, which is the decision the design wants them to make consciously.

---

## 9. Known weaknesses

Collected in one place so that nobody has to assemble them from footnotes.

1. **Issuer key management is unspecified.** Section 4. The largest gap.
2. **Transfer semantics are absent.** A transfer is currently a new record
   superseding the old one, which does not capture its two party nature.
3. **Legal recognition is assumed nowhere and achieved nowhere.** SatDeed is
   an evidence layer. Whether a court gives that evidence weight is
   jurisdiction specific and currently untested.
4. **The status set problem.** A verifier can only check for revocation if it
   has the issuer's status records. Obtaining them reintroduces a dependency
   on the issuer, which is uncomfortable for a design whose premise is
   distrust of the issuer. Anchored status batches help but do not eliminate
   it, because a verifier must still know to look.
5. **Garbage in.** Anchoring a false statement makes the false statement
   permanent and tamper evident. The protocol improves integrity, never
   accuracy.
6. **Adoption is the real obstacle.** The engineering is modest and the costs
   are trivial. What is hard is persuading a registry to publish commitments
   that make its own future revisions detectable, which is a change many
   institutions will correctly understand as a reduction in their own
   discretion.

Point 6 deserves emphasis. The most likely reason this standard fails is not
that it is technically wrong. It is that the institutions best placed to adopt
it have the least to gain from being auditable.

---

## 10. Rejected alternatives

| Alternative | Why it was rejected |
|---|---|
| A dedicated sidechain or appchain | Reintroduces a consensus mechanism, a validator set and a bridge, which is the dependency the design exists to avoid |
| Smart contract platform with on chain title logic | No contract can adjudicate physical possession, and the legal layer remains decisive regardless |
| Full documents inscribed on chain | Expensive, antisocial toward other blockspace users, and permanently incompatible with data protection law |
| Unsalted hashes of identifiers | Low entropy identifiers are guessable, turning a public record into a confirmation oracle |
| Bitcoin style Merkle duplication | CVE-2012-2459, see section 5 |
| Mutable records with version fields | Defeats the purpose, since a revisable history is the problem being solved |
| A governance token | See section 7 |
| Shipping a chain client in the reference library | A verifier that trusts one endpoint has reintroduced a single point of dependence |
