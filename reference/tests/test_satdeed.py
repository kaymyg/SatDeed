"""Test suite for the SatDeed v0.1 reference implementation.

Run with:  python3 -m pytest reference/tests -q
Or with:   python3 reference/tests/test_satdeed.py
"""

from __future__ import annotations

import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from satdeed import (  # noqa: E402
    AnchorKind,
    AnchorObservation,
    AnchorPayload,
    build_asset_record,
    build_status_record,
    canonicalize,
    decode_payload,
    derive_asset_uid,
    display_form,
    document_commitment,
    encode_payload,
    make_document_entry,
    merkle_root,
    parse_display_form,
    prove,
    record_hash,
    sha256,
    sign_record,
    verify_document,
    verify_proof,
    verify_record,
)
from satdeed import schnorr  # noqa: E402
from satdeed.canonical import CanonicalizationError  # noqa: E402
from satdeed.identifiers import InvalidIdentifier  # noqa: E402
from satdeed.merkle import build_tree, leaf_hash  # noqa: E402
from satdeed.record import StructuralError, validate_structure  # noqa: E402

SALT_A = bytes.fromhex(
    "a1" * 32
)
SALT_B = bytes.fromhex("b2" * 32)
SECKEY = bytes.fromhex(
    "0000000000000000000000000000000000000000000000000000000000000003"
)


class TestCanonicalization(unittest.TestCase):
    def test_object_members_are_sorted(self):
        self.assertEqual(canonicalize({"b": 1, "a": 2}), '{"a":2,"b":1}')

    def test_nested_ordering_and_arrays(self):
        self.assertEqual(
            canonicalize({"z": [3, {"y": 1, "x": 2}], "a": None}),
            '{"a":null,"z":[3,{"x":2,"y":1}]}',
        )

    def test_array_order_is_preserved(self):
        self.assertEqual(canonicalize([3, 1, 2]), "[3,1,2]")

    def test_unicode_is_not_escaped(self):
        self.assertEqual(canonicalize({"k": "Käthe"}), '{"k":"Käthe"}')

    def test_control_characters_are_escaped(self):
        self.assertEqual(canonicalize({"k": "a\nb"}), '{"k":"a\\nb"}')

    def test_floats_are_rejected(self):
        with self.assertRaises(CanonicalizationError):
            canonicalize({"amount": 1.5})

    def test_unsafe_integers_are_rejected(self):
        with self.assertRaises(CanonicalizationError):
            canonicalize({"n": 2**53})

    def test_utf16_ordering_differs_from_code_point_ordering(self):
        # U+1F600 is above U+FFFF, so its UTF-16 surrogate pair sorts before
        # U+FF00 even though its code point is larger. RFC 8785 requires the
        # UTF-16 order, and a naive implementation gets this backwards.
        text = canonicalize({"\U0001f600": 1, "＀": 2})
        self.assertTrue(text.index("\U0001f600") < text.index("＀"))


class TestIdentifiers(unittest.TestCase):
    def setUp(self):
        self.uid = derive_asset_uid(
            "ntsa.go.ke", {"chassis_number": "LC0ABC123DEF45678"}, SALT_A
        )

    def test_derivation_is_deterministic(self):
        again = derive_asset_uid(
            "ntsa.go.ke", {"chassis_number": "LC0ABC123DEF45678"}, SALT_A
        )
        self.assertEqual(self.uid, again)

    def test_attribute_order_does_not_change_the_uid(self):
        a = derive_asset_uid("x", {"one": "1", "two": "2"}, SALT_A)
        b = derive_asset_uid("x", {"two": "2", "one": "1"}, SALT_A)
        self.assertEqual(a, b)

    def test_different_salt_gives_a_different_uid(self):
        other = derive_asset_uid(
            "ntsa.go.ke", {"chassis_number": "LC0ABC123DEF45678"}, SALT_B
        )
        self.assertNotEqual(self.uid, other)

    def test_different_namespace_gives_a_different_uid(self):
        other = derive_asset_uid(
            "other.registry", {"chassis_number": "LC0ABC123DEF45678"}, SALT_A
        )
        self.assertNotEqual(self.uid, other)

    def test_display_form_round_trips(self):
        text = display_form(self.uid)
        self.assertEqual(parse_display_form(text), self.uid[:20])

    def test_checksum_catches_a_single_character_typo(self):
        text = display_form(self.uid)
        body_index = 5
        original = text[body_index]
        replacement = "0" if original != "0" else "1"
        mistyped = text[:body_index] + replacement + text[body_index + 1 :]
        with self.assertRaises(InvalidIdentifier):
            parse_display_form(mistyped)

    def test_confusable_characters_are_accepted_on_input(self):
        text = display_form(self.uid)
        if "0" in text[4:]:
            swapped = text[:4] + text[4:].replace("0", "O", 1)
            self.assertEqual(parse_display_form(swapped), self.uid[:20])


class TestSchnorr(unittest.TestCase):
    def test_sign_and_verify(self):
        msg = sha256(b"satdeed test vector")
        pub = schnorr.pubkey_from_seckey(SECKEY)
        sig = schnorr.sign(msg, SECKEY, aux_rand=bytes(32))
        self.assertTrue(schnorr.verify(msg, pub, sig))

    def test_signature_does_not_verify_for_another_message(self):
        pub = schnorr.pubkey_from_seckey(SECKEY)
        sig = schnorr.sign(sha256(b"one"), SECKEY, aux_rand=bytes(32))
        self.assertFalse(schnorr.verify(sha256(b"two"), pub, sig))

    def test_bip340_test_vector_0(self):
        # Vector 0 from the BIP-340 test vectors.
        seckey = bytes.fromhex(
            "0000000000000000000000000000000000000000000000000000000000000003"
        )
        expected_pub = bytes.fromhex(
            "F9308A019258C31049344F85F89D5229B531C845836F99B08601F113BCE036F9"
        )
        self.assertEqual(schnorr.pubkey_from_seckey(seckey).hex().upper(),
                         expected_pub.hex().upper())
        msg = bytes(32)
        sig = schnorr.sign(msg, seckey, aux_rand=bytes(32))
        self.assertTrue(schnorr.verify(msg, expected_pub, sig))

    def test_malformed_inputs_return_false_rather_than_raising(self):
        self.assertFalse(schnorr.verify(b"short", bytes(32), bytes(64)))
        self.assertFalse(schnorr.verify(bytes(32), bytes(32), bytes(64)))


class TestMerkle(unittest.TestCase):
    def hashes(self, n: int) -> list[bytes]:
        return [sha256(bytes([i])) for i in range(n)]

    def test_single_leaf_tree(self):
        h = self.hashes(1)
        self.assertEqual(merkle_root(h), leaf_hash(h[0]))
        self.assertTrue(verify_proof(h[0], prove(h, 0), merkle_root(h)))

    def test_every_index_proves_for_sizes_one_to_sixteen(self):
        for n in range(1, 17):
            hs = self.hashes(n)
            root = merkle_root(hs)
            for i in range(n):
                self.assertTrue(
                    verify_proof(hs[i], prove(hs, i), root),
                    f"inclusion failed for leaf {i} of {n}",
                )

    def test_proof_fails_for_a_record_not_in_the_batch(self):
        hs = self.hashes(7)
        root = merkle_root(hs)
        outsider = sha256(b"not in the batch")
        self.assertFalse(verify_proof(outsider, prove(hs, 3), root))

    def test_empty_batch_is_rejected(self):
        with self.assertRaises(ValueError):
            merkle_root([])

    def test_promotion_avoids_the_duplicate_node_collision(self):
        # CVE-2012-2459: with Bitcoin style duplication, the three leaf set
        # [a, b, c] and the four leaf set [a, b, c, c] produce the same root,
        # which lets a registry claim it committed to a record it never did.
        # Promotion must keep those roots distinct.
        a, b, c = self.hashes(3)
        self.assertNotEqual(merkle_root([a, b, c]), merkle_root([a, b, c, c]))

    def test_leaf_and_branch_domains_are_separated(self):
        # An internal node must never be a valid leaf hash, otherwise a two
        # record subtree could be presented as a single record.
        a, b = self.hashes(2)
        root = merkle_root([a, b])
        self.assertNotEqual(root, leaf_hash(root))
        self.assertFalse(verify_proof(root, prove([root], 0), root))

    def test_structurally_incompatible_leaf_count_is_rejected(self):
        # Leaf 4 of 5 is a promoted node and spends no step at the bottom
        # level. Claiming 6 leaves makes the bottom level even, so the same
        # path no longer lines up and verification must fail.
        hs = self.hashes(5)
        root = merkle_root(hs)
        proof = prove(hs, 4)
        tampered = type(proof)(index=4, leaf_count=6, path=proof.path)
        self.assertFalse(verify_proof(hs[4], tampered, root))

    def test_some_leaf_counts_are_indistinguishable_to_the_proof_alone(self):
        # Honest statement of a limit. For leaf 2, a 5 leaf tree and a 6 leaf
        # tree have the identical branch shape above that leaf, so the proof
        # by itself cannot tell them apart. This is not a weakness in the
        # tree, it is the reason the leaf count is carried in the on chain
        # anchor payload and cross checked there. See the companion test
        # TestEndToEndAnchoring.test_proof_leaf_count_must_match_the_anchor.
        hs = self.hashes(5)
        root = merkle_root(hs)
        proof = prove(hs, 2)
        tampered = type(proof)(index=2, leaf_count=6, path=proof.path)
        self.assertTrue(verify_proof(hs[2], tampered, root))

    def test_proof_with_a_flipped_side_is_rejected(self):
        hs = self.hashes(4)
        root = merkle_root(hs)
        proof = prove(hs, 1)
        flipped_path = tuple(
            ("left" if side == "right" else "right", h) for side, h in proof.path
        )
        tampered = type(proof)(index=proof.index, leaf_count=proof.leaf_count,
                               path=flipped_path)
        self.assertFalse(verify_proof(hs[1], tampered, root))

    def test_tree_levels_shrink_to_one_root(self):
        levels = build_tree(self.hashes(9))
        self.assertEqual(len(levels[-1]), 1)
        self.assertEqual(len(levels[0]), 9)


class TestAnchorPayload(unittest.TestCase):
    def test_round_trip(self):
        payload = AnchorPayload(AnchorKind.BATCH_ROOT, sha256(b"root"), 1024)
        self.assertEqual(decode_payload(encode_payload(payload)), payload)

    def test_payload_is_forty_bytes(self):
        payload = AnchorPayload(AnchorKind.BATCH_ROOT, sha256(b"root"), 1)
        self.assertEqual(len(encode_payload(payload)), 40)

    def test_foreign_op_return_data_is_rejected(self):
        with self.assertRaises(ValueError):
            decode_payload(b"\x00" * 40)

    def test_wrong_length_is_rejected(self):
        with self.assertRaises(ValueError):
            decode_payload(b"SD\x01\x02" + bytes(30))

    def test_single_record_anchor_must_declare_one_leaf(self):
        with self.assertRaises(ValueError):
            AnchorPayload(AnchorKind.SINGLE_RECORD, sha256(b"x"), 2)


class TestRecords(unittest.TestCase):
    def setUp(self):
        self.pub = schnorr.pubkey_from_seckey(SECKEY)
        self.uid = derive_asset_uid("ntsa.go.ke", {"chassis_number": "ABC"}, SALT_A)
        self.doc = b"REGISTRATION CERTIFICATE, serial 00912"
        self.record = build_asset_record(
            asset_uid=self.uid,
            asset_class="vehicle",
            issuer_id="ntsa.go.ke",
            issuer_pubkey=self.pub,
            issued_at="2026-11-07T09:00:00Z",
            verification_level=3,
            attributes={"manufacturer": "Example Motors", "year": 2026},
            documents=[
                make_document_entry("registration_certificate", SALT_B,
                                    sha256(self.doc))
            ],
        )

    def test_unsigned_record_is_structurally_valid(self):
        validate_structure(self.record)

    def test_signature_verifies(self):
        signed = sign_record(self.record, SECKEY)
        result = verify_record(signed)
        self.assertTrue(result.passed, result.report())

    def test_any_field_change_breaks_the_signature(self):
        signed = sign_record(self.record, SECKEY)
        signed["attributes"]["year"] = 2025
        result = verify_record(signed)
        self.assertFalse(result.passed)
        self.assertIn("issuer_signature", [c.name for c in result.failures])

    def test_adding_a_field_breaks_the_signature(self):
        signed = sign_record(self.record, SECKEY)
        signed["attributes"]["mileage"] = 12
        self.assertFalse(verify_record(signed).passed)

    def test_signing_with_a_mismatched_key_is_refused(self):
        other = bytes.fromhex("0" * 63 + "5")
        with self.assertRaises(StructuralError):
            sign_record(self.record, other)

    def test_asset_id_must_match_the_uid(self):
        broken = dict(self.record)
        broken["asset_id"] = display_form(
            derive_asset_uid("x", {"a": "b"}, SALT_B)
        )
        with self.assertRaises(StructuralError):
            validate_structure(broken)

    def test_document_commitment_check(self):
        check = verify_document(self.record, "registration_certificate",
                                SALT_B, self.doc)
        self.assertTrue(check.passed, check.detail)

    def test_document_check_fails_on_a_single_byte_change(self):
        altered = self.doc.replace(b"00912", b"00913")
        check = verify_document(self.record, "registration_certificate",
                                SALT_B, altered)
        self.assertFalse(check.passed)

    def test_document_check_fails_with_the_wrong_salt(self):
        check = verify_document(self.record, "registration_certificate",
                                SALT_A, self.doc)
        self.assertFalse(check.passed)

    def test_unsalted_digest_is_not_the_commitment(self):
        # Guards against an implementation that quietly drops the salt.
        self.assertNotEqual(
            document_commitment(SALT_B, sha256(self.doc)), sha256(self.doc)
        )

    def test_status_record_supersedes_the_asset_record(self):
        signed = sign_record(self.record, SECKEY)
        revocation = build_status_record(
            asset_uid=self.uid,
            issuer_id="ntsa.go.ke",
            issuer_pubkey=self.pub,
            issued_at="2026-11-20T09:00:00Z",
            status="revoked",
            supersedes=record_hash(signed).hex(),
            reason="registration cancelled following a court order",
        )
        signed_revocation = sign_record(revocation, SECKEY)
        self.assertTrue(verify_record(signed_revocation).passed)

    def test_issuer_directory_mismatch_is_reported(self):
        signed = sign_record(self.record, SECKEY)
        result = verify_record(signed, known_issuer_keys={"ntsa.go.ke": "ff" * 32})
        self.assertFalse(result.passed)
        self.assertIn("issuer_identity", [c.name for c in result.failures])

    def test_unknown_issuer_is_reported(self):
        signed = sign_record(self.record, SECKEY)
        result = verify_record(signed, known_issuer_keys={})
        self.assertFalse(result.passed)


class TestEndToEndAnchoring(unittest.TestCase):
    def setUp(self):
        self.pub = schnorr.pubkey_from_seckey(SECKEY)
        self.records = []
        for i in range(5):
            uid = derive_asset_uid("ntsa.go.ke", {"chassis_number": f"CH{i:05d}"},
                                   SALT_A)
            record = build_asset_record(
                asset_uid=uid,
                asset_class="vehicle",
                issuer_id="ntsa.go.ke",
                issuer_pubkey=self.pub,
                issued_at="2026-11-07T09:00:00Z",
                verification_level=3,
                attributes={"manufacturer": "Example Motors", "year": 2026},
            )
            self.records.append(sign_record(record, SECKEY))
        self.hashes = [record_hash(r) for r in self.records]
        self.root = merkle_root(self.hashes)
        self.payload = encode_payload(
            AnchorPayload(AnchorKind.BATCH_ROOT, self.root, len(self.hashes))
        )

    def observation(self, data: bytes | None = None, confirmations: int = 12):
        return AnchorObservation(
            txid="f" * 64,
            output_index=0,
            op_return_data=data if data is not None else self.payload,
            block_height=900_000,
            confirmations=confirmations,
        )

    def test_full_pipeline_passes(self):
        result = verify_record(
            self.records[2],
            proof=prove(self.hashes, 2),
            anchor=self.observation(),
        )
        self.assertTrue(result.passed, result.report())

    def test_record_outside_the_batch_fails_inclusion(self):
        uid = derive_asset_uid("ntsa.go.ke", {"chassis_number": "OUTSIDER"}, SALT_A)
        outsider = sign_record(
            build_asset_record(
                asset_uid=uid,
                asset_class="vehicle",
                issuer_id="ntsa.go.ke",
                issuer_pubkey=self.pub,
                issued_at="2026-11-07T09:00:00Z",
                verification_level=3,
            ),
            SECKEY,
        )
        result = verify_record(outsider, proof=prove(self.hashes, 2),
                               anchor=self.observation())
        self.assertFalse(result.passed)
        self.assertIn("merkle_inclusion", [c.name for c in result.failures])

    def test_proof_leaf_count_must_match_the_anchor(self):
        # The defence that the proof alone cannot provide: the anchor declares
        # the tree size on chain, so a proof claiming a different size is
        # rejected before its arithmetic is even attempted.
        proof = prove(self.hashes, 2)
        tampered = type(proof)(index=2, leaf_count=6, path=proof.path)
        result = verify_record(self.records[2], proof=tampered,
                               anchor=self.observation())
        self.assertFalse(result.passed)
        self.assertIn("merkle_inclusion", [c.name for c in result.failures])

    def test_batch_anchor_without_a_proof_fails(self):
        result = verify_record(self.records[0], anchor=self.observation())
        self.assertFalse(result.passed)

    def test_insufficient_confirmations_fails(self):
        result = verify_record(
            self.records[0],
            proof=prove(self.hashes, 0),
            anchor=self.observation(confirmations=2),
            min_confirmations=6,
        )
        self.assertFalse(result.passed)
        self.assertIn("confirmations", [c.name for c in result.failures])

    def test_single_record_anchor(self):
        digest = record_hash(self.records[1])
        payload = encode_payload(
            AnchorPayload(AnchorKind.SINGLE_RECORD, digest, 1)
        )
        result = verify_record(self.records[1], anchor=self.observation(payload))
        self.assertTrue(result.passed, result.report())

    def test_single_record_anchor_rejects_a_different_record(self):
        digest = record_hash(self.records[1])
        payload = encode_payload(AnchorPayload(AnchorKind.SINGLE_RECORD, digest, 1))
        result = verify_record(self.records[3], anchor=self.observation(payload))
        self.assertFalse(result.passed)

    def test_anchor_carrying_someone_elses_op_return_fails_cleanly(self):
        result = verify_record(
            self.records[0],
            proof=prove(self.hashes, 0),
            anchor=self.observation(data=b"\x6a" * 40),
        )
        self.assertFalse(result.passed)
        self.assertIn("anchor_payload", [c.name for c in result.failures])


if __name__ == "__main__":
    unittest.main(verbosity=2)
