from __future__ import annotations

import importlib.util
import json
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace


ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "scripts" / "zos_design_primitives.py"


def load_primitives():
    spec = importlib.util.spec_from_file_location("zos_design_primitives_under_test", MODULE_PATH)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


class FakeWavelength:
    def __init__(self):
        self.Wavelength = None
        self.Weight = None


class FakeWavelengthsEditor:
    def __init__(self):
        self.NumberOfWavelengths = 1
        self.first = FakeWavelength()
        self.added = []
        self.removed = []

    def RemoveWavelength(self, index):
        self.removed.append(index)
        self.NumberOfWavelengths -= 1

    def GetWavelength(self, index):
        return self.first

    def AddWavelength(self, wavelength, weight):
        self.added.append((wavelength, weight))
        self.NumberOfWavelengths += 1


class FakeField:
    def __init__(self):
        self.X = None
        self.Y = None
        self.Weight = None


class FakeFieldsEditor:
    def __init__(self):
        self.NumberOfFields = 1
        self.first = FakeField()
        self.added = []
        self.removed = []

    def RemoveField(self, index):
        self.removed.append(index)
        self.NumberOfFields -= 1

    def AddField(self, x, y, weight):
        self.added.append((x, y, weight))
        self.NumberOfFields += 1

    def GetField(self, index):
        return self.first


class FakeAperture:
    def __init__(self):
        self.ApertureValue = None


class FakeSystemData:
    def __init__(self):
        self.Wavelengths = FakeWavelengthsEditor()
        self.Fields = FakeFieldsEditor()
        self.Aperture = FakeAperture()


class FakeSurface:
    def __init__(self):
        self.Radius = None
        self.Thickness = None
        self.Material = None
        self.RadiusCell = SimpleNamespace(MakeSolveVariable=lambda: None)
        self.ThicknessCell = SimpleNamespace(MakeSolveVariable=lambda: None)


class FakeLDE:
    def __init__(self, initial_surfaces: int = 1):
        self.NumberOfSurfaces = initial_surfaces
        self.surfaces = {index: FakeSurface() for index in range(1, initial_surfaces + 1)}
        self.insert_calls = []

    def InsertNewSurfaceAt(self, index):
        self.insert_calls.append(index)
        self.NumberOfSurfaces += 1
        self.surfaces[self.NumberOfSurfaces] = FakeSurface()

    def GetSurfaceAt(self, index):
        if index not in self.surfaces:
            self.surfaces[index] = FakeSurface()
            self.NumberOfSurfaces = max(self.NumberOfSurfaces, index)
        return self.surfaces[index]


class FakeSystem:
    def __init__(self, initial_surfaces: int = 1):
        self.loaded_paths = []
        self.new_called = False
        self.saved_paths = []
        self.LDE = FakeLDE(initial_surfaces=initial_surfaces)
        self.SystemData = FakeSystemData()

    def LoadFile(self, path, flag):
        self.loaded_paths.append((path, flag))

    def New(self, flag):
        self.new_called = True

    def SaveAs(self, path):
        self.saved_paths.append(path)


class FakeApp:
    def __init__(self, system: FakeSystem | None = None):
        self.PrimarySystem = system or FakeSystem()


class ZosDesignPrimitivesTest(unittest.TestCase):
    def test_module_loads_without_zosapi(self):
        primitives = load_primitives()
        for name in (
            "connect_zemax",
            "load_or_create_system",
            "create_minimal_sequential_system",
            "set_wavelengths",
            "set_fields",
            "set_aperture",
            "export_common_analyses",
            "parse_metrics",
            "configure_variables_and_merit",
            "run_local_optimization",
        ):
            self.assertTrue(hasattr(primitives, name), name)

    def test_stage_result_dataclass(self):
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
            data = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(data["name"], "demo")
            self.assertEqual(data["notes"], ["one"])

    def test_load_or_create_system_uses_explicit_input_lens_before_seed_metadata(self):
        primitives = load_primitives()
        system = FakeSystem()
        app = FakeApp(system)
        requirements = {
            "input_lens": "lens/input.zmx",
            "seed_design": {
                "selected_case_path": "seeds/selected_case.zmx",
                "provenance": {
                    "source_path": "seeds/provenance_seed.zmx",
                    "approval_status": "system_selected",
                },
                "selection_notes": ["seed metadata is still recorded"],
            },
        }

        selected = primitives.load_or_create_system(app, requirements)

        self.assertIs(selected, system)
        self.assertEqual(system.loaded_paths, [(str(Path("lens/input.zmx").resolve()), False)])
        self.assertEqual(system.new_called, False)
        self.assertTrue(hasattr(system, "design_working_data"))
        self.assertEqual(system.design_working_data["seed_source"], "input_lens")
        self.assertEqual(system.design_working_data["selection_notes"], ["seed metadata is still recorded"])

    def test_load_or_create_system_prefers_selected_case_path_and_records_working_data(self):
        primitives = load_primitives()
        system = FakeSystem()
        app = FakeApp(system)
        requirements = {
            "seed_design": {
                "selected_case": "catalog seed name",
                "selected_case_path": "seeds/selected_case.zmx",
                "provenance": {
                    "source_type": "catalog_reference",
                    "source_name": "catalog seed name",
                    "source_path": "seeds/provenance_seed.zmx",
                    "source_version": "v1",
                    "approval_status": "user_approved",
                },
                "selection_notes": ["selected_case_path should win"],
                "structural_gaps": [{"axis": "aperture", "severity": "warning"}],
            },
        }

        selected = primitives.load_or_create_system(app, requirements)

        self.assertIs(selected, system)
        self.assertEqual(system.loaded_paths, [(str(Path("seeds/selected_case.zmx").resolve()), False)])
        self.assertEqual(system.design_working_data["seed_source"], "seed_design.selected_case_path")
        self.assertEqual(system.design_working_data["selection_notes"], ["selected_case_path should win"])
        self.assertEqual(system.design_working_data["provenance"]["source_name"], "catalog seed name")

    def test_load_or_create_system_falls_back_to_provenance_source_path(self):
        primitives = load_primitives()
        system = FakeSystem()
        app = FakeApp(system)
        requirements = {
            "seed_design": {
                "selected_case": "catalog seed name",
                "provenance": {
                    "source_type": "catalog_reference",
                    "source_name": "catalog seed name",
                    "source_path": "seeds/provenance_seed.zmx",
                    "source_version": "v1",
                    "approval_status": "system_selected",
                },
                "selection_notes": ["provenance path should be used"],
                "structural_gaps": [],
            },
        }

        selected = primitives.load_or_create_system(app, requirements)

        self.assertIs(selected, system)
        self.assertEqual(system.loaded_paths, [(str(Path("seeds/provenance_seed.zmx").resolve()), False)])
        self.assertEqual(system.design_working_data["seed_source"], "seed_design.provenance.source_path")
        self.assertIn("provenance path should be used", system.design_working_data["selection_notes"])

    def test_load_or_create_system_creates_seed_aware_starter_without_input_lens(self):
        primitives = load_primitives()
        system = FakeSystem()
        app = FakeApp(system)
        requirements = {
            "wavelengths_um": [{"value": 0.486, "weight": 1}, {"value": 0.588, "weight": 1}],
            "fields": [{"type": "angle_deg", "value": 0.0}, {"type": "angle_deg", "value": 5.0}],
            "aperture": {"type": "f_number", "value": 2.8},
            "seed_design": {
                "selected_case": "zoom family seed",
                "provenance": {
                    "source_type": "reference_catalog",
                    "source_name": "zoom family seed",
                    "source_path": None,
                    "source_version": "reference-only",
                    "approval_status": "system_selected",
                },
                "selection_notes": ["metadata-only seed should still enrich the starter"],
                "structural_gaps": [
                    {"axis": "focal_length_span", "severity": "warning"},
                    {"axis": "group_count", "severity": "warning"},
                ],
                "match_axes": ["focal_length_span", "group_count", "field_of_view"],
            },
        }

        selected = primitives.load_or_create_system(app, requirements)

        self.assertIs(selected, system)
        self.assertTrue(system.new_called)
        self.assertGreater(system.LDE.NumberOfSurfaces, 4)
        self.assertEqual(system.SystemData.Aperture.ApertureValue, 2.8)
        self.assertEqual(system.design_working_data["seed_source"], "seed_design.metadata_only")
        self.assertIn("metadata-only seed should still enrich the starter", system.design_working_data["selection_notes"])
        self.assertEqual(system.design_working_data["starter_profile"], "seed-aware")

    def test_configure_variables_and_merit_builds_zoom_specific_policy(self):
        primitives = load_primitives()
        system = FakeSystem(initial_surfaces=8)
        requirements = {
            "seed_design": {
                "family_hint": "zoom_imaging",
                "structural_gaps": [
                    {"axis": "group_count", "severity": "warning"},
                    {"axis": "package_length", "severity": "warning"},
                ],
                "provenance": {"source_type": "catalog_reference", "approval_status": "user_approved"},
            },
            "constraints": {"zoom_configurations": [{"name": "wide", "efl_mm": 18.0}]},
        }

        plan = primitives.configure_variables_and_merit(system, requirements, "image-quality")

        self.assertEqual(plan["stage"], "image-quality")
        self.assertTrue(plan["zoom_policy"]["complex_zoom"])
        self.assertEqual(plan["zoom_policy"]["failure_intercept"], "rollback_then_shrink")
        self.assertEqual(plan["surface_release_order"], system._design_control_plan["surface_release_order"])
        self.assertIn("zoom_configuration_controls", plan["variable_groups"])
        self.assertIn("seed_gap_traceability", plan["locked_groups"])
        self.assertEqual(system._design_control_plan["zoom_policy"]["release_mode"], "center-first-then-edges")


if __name__ == "__main__":
    unittest.main()
