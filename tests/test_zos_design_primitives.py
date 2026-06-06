from __future__ import annotations

import importlib.util
import sys
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
    def test_module_loads_without_zosapi(self):
        """Module should import cleanly (ZOSPy handles DLL loading at connect time)."""
        primitives = load_primitives()
        self.assertTrue(hasattr(primitives, "connect_zemax"))
        self.assertTrue(hasattr(primitives, "export_common_analyses"))
        self.assertTrue(hasattr(primitives, "run_local_optimization"))

    def test_stage_result_dataclass(self):
        """StageResult dataclass should still work."""
        primitives = load_primitives()
        sr = primitives.StageResult(name="test", accepted=True, notes=["a", "b"])
        self.assertEqual(sr.name, "test")
        self.assertTrue(sr.accepted)
        self.assertEqual(len(sr.notes), 2)

    def test_write_stage_result_produces_json(self):
        import tempfile

        primitives = load_primitives()
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)
            result = primitives.StageResult(name="demo", notes=["one"])
            path = primitives.write_stage_result(out, result)
            self.assertTrue(path.is_file())
            import json

            data = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(data["name"], "demo")
            self.assertEqual(data["notes"], ["one"])


if __name__ == "__main__":
    unittest.main()
