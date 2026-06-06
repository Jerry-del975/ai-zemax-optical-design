from __future__ import annotations

import importlib.util
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "scripts" / "zos_design_primitives.py"


def load_primitives():
    spec = importlib.util.spec_from_file_location("zos_design_primitives_under_test", MODULE_PATH)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


class ZosDesignPrimitivesTest(unittest.TestCase):
    def test_2024r1_default_candidate_is_included(self):
        primitives = load_primitives()

        self.assertIn(
            r"D:\Program Files\Ansys Zemax OpticStudio 2024 R1.00",
            primitives.DEFAULT_ZOSAPI_ROOT_CANDIDATES,
        )

    def test_resolve_zosapi_root_accepts_explicit_2024r1_root(self):
        primitives = load_primitives()

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "ZOSAPI_NetHelper.dll").write_text("", encoding="utf-8")

            self.assertEqual(primitives.resolve_zosapi_root(str(root)), root)

    def test_resolve_zosapi_root_accepts_zos_api_subdirectory(self):
        primitives = load_primitives()

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            sub = root / "ZOS-API"
            sub.mkdir()
            (sub / "ZOSAPI_NetHelper.dll").write_text("", encoding="utf-8")

            self.assertEqual(primitives.resolve_zosapi_root(str(root)), sub)

    def test_resolve_zosapi_root_reports_2024r1_when_missing(self):
        primitives = load_primitives()

        with tempfile.TemporaryDirectory() as tmp:
            original = primitives.DEFAULT_ZOSAPI_ROOT_CANDIDATES
            primitives.DEFAULT_ZOSAPI_ROOT_CANDIDATES = []
            try:
                with self.assertRaises(FileNotFoundError) as ctx:
                    primitives.resolve_zosapi_root(str(Path(tmp) / "missing"))
            finally:
                primitives.DEFAULT_ZOSAPI_ROOT_CANDIDATES = original

        self.assertIn("2024 R1", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
