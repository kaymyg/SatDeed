"""Validate the published examples against the JSON Schema.

Skipped when jsonschema is not installed, because the reference library must
stay usable with no third party dependencies.
"""

from __future__ import annotations

import glob
import json
import os
import unittest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
SCHEMA_PATH = os.path.join(ROOT, "spec", "schema", "satdeed-record-0.1.schema.json")

try:
    from jsonschema import Draft202012Validator
except ImportError:  # pragma: no cover
    Draft202012Validator = None


@unittest.skipIf(Draft202012Validator is None, "jsonschema is not installed")
class TestSchema(unittest.TestCase):
    def setUp(self):
        with open(SCHEMA_PATH, encoding="utf-8") as fh:
            self.schema = json.load(fh)
        Draft202012Validator.check_schema(self.schema)
        self.validator = Draft202012Validator(self.schema)

    def test_every_published_record_validates(self):
        paths = sorted(
            glob.glob(os.path.join(ROOT, "examples", "**", "*record*.json"),
                      recursive=True)
        )
        self.assertTrue(paths, "no example records were found")
        for path in paths:
            with self.subTest(path=os.path.relpath(path, ROOT)):
                with open(path, encoding="utf-8") as fh:
                    record = json.load(fh)
                errors = sorted(self.validator.iter_errors(record),
                                key=lambda e: list(e.path))
                self.assertEqual(
                    [], errors,
                    "; ".join(f"{list(e.path)}: {e.message}" for e in errors),
                )

    def test_schema_rejects_an_unknown_member(self):
        with open(os.path.join(ROOT, "examples", "vehicle-title",
                               "asset-record.json"), encoding="utf-8") as fh:
            record = json.load(fh)
        record["surprise"] = "unexpected"
        self.assertTrue(list(self.validator.iter_errors(record)))

    def test_schema_rejects_a_bad_verification_level(self):
        with open(os.path.join(ROOT, "examples", "vehicle-title",
                               "asset-record.json"), encoding="utf-8") as fh:
            record = json.load(fh)
        record["verification_level"] = 9
        self.assertTrue(list(self.validator.iter_errors(record)))


if __name__ == "__main__":
    unittest.main(verbosity=2)
