from __future__ import annotations

import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCHEMA_PATH = ROOT / "references" / "requirements-schema.md"
EXAMPLE_PATH = ROOT / "examples" / "seeded_complex_zoom_requirements.json"


def load_schema_example() -> dict:
    text = SCHEMA_PATH.read_text(encoding="utf-8")
    start = text.find("```json")
    if start == -1:
        raise AssertionError("Could not find JSON example block in requirements schema")
    start = text.find("{", start)
    if start == -1:
        raise AssertionError("Could not find JSON object in requirements schema example")

    depth = 0
    end = None
    for index, char in enumerate(text[start:], start=start):
        if char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                end = index + 1
                break

    if end is None:
        raise AssertionError("Unterminated JSON object in requirements schema example")
    return json.loads(text[start:end])


def load_json_example() -> dict:
    return json.loads(EXAMPLE_PATH.read_text(encoding="utf-8"))


class RequirementsSchemaTest(unittest.TestCase):
    def test_schema_example_includes_seed_design_metadata_shape(self):
        example = load_schema_example()
        self.assertIn("seed_design", example)

        seed_design = example["seed_design"]
        self.assertIsInstance(seed_design, dict)
        self.assertEqual(
            set(seed_design),
            {
                "preferred_source",
                "family_hint",
                "match_axes",
                "provenance",
                "structural_gaps",
                "selected_case",
                "selected_case_path",
                "selection_notes",
            },
        )
        self.assertIsInstance(seed_design["match_axes"], list)
        self.assertIsInstance(seed_design["selection_notes"], list)
        self.assertIsInstance(seed_design["structural_gaps"], list)

        provenance = seed_design["provenance"]
        self.assertIsInstance(provenance, dict)
        self.assertEqual(
            set(provenance),
            {
                "source_type",
                "source_name",
                "source_path",
                "source_version",
                "approval_status",
            },
        )

    def test_schema_example_keeps_top_level_design_contract_intact(self):
        example = load_schema_example()
        for key in (
            "system_type",
            "mode",
            "input_lens",
            "wavelengths_um",
            "fields",
            "aperture",
            "targets",
            "seed_design",
            "constraints",
            "automation",
            "assumptions",
        ):
            self.assertIn(key, example)

    def test_seeded_complex_example_includes_richer_seed_metadata_shape(self):
        example = load_json_example()
        self.assertIn("seed_design", example)

        seed_design = example["seed_design"]
        self.assertIsInstance(seed_design, dict)
        for key in (
            "preferred_source",
            "family_hint",
            "match_axes",
            "provenance",
            "structural_gaps",
            "selected_case",
            "selected_case_path",
            "selection_notes",
        ):
            self.assertIn(key, seed_design)

        provenance = seed_design["provenance"]
        self.assertIsInstance(provenance, dict)
        for key in ("source_type", "source_name", "source_version", "approval_status"):
            self.assertIn(key, provenance)

        structural_gaps = seed_design["structural_gaps"]
        self.assertIsInstance(structural_gaps, list)
        self.assertGreater(len(structural_gaps), 0)
        for gap in structural_gaps:
            self.assertIsInstance(gap, dict)
            for key in ("axis", "requested", "seed", "severity", "note"):
                self.assertIn(key, gap)


if __name__ == "__main__":
    unittest.main()
