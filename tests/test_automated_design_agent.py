from __future__ import annotations

import importlib.util
import json
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "scripts" / "automated_design_agent.py"


def load_agent():
    spec = importlib.util.spec_from_file_location("automated_design_agent_under_test", MODULE_PATH)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


class FakeSystem:
    def __init__(self):
        self.loaded_paths = []
        self.saved_paths = []
        self._design_seed_context = {}
        self.design_working_data = {}

    def LoadFile(self, path, flag):
        self.loaded_paths.append((path, flag))

    def SaveAs(self, path):
        self.saved_paths.append(path)


class FakeApp:
    def __init__(self, system: FakeSystem):
        self.PrimarySystem = system
        self.closed = False

    def CloseApplication(self):
        self.closed = True


class AutomatedDesignAgentTest(unittest.TestCase):
    def test_parse_metrics_extracts_numeric_signals(self):
        import tempfile

        agent = load_agent()
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "spot.txt"
            path.write_text(
                "Merit Value: 123.4\nRMS Spot = 5.6 um\nMTF 40 lp/mm: 0.27\nDistortion: 1.8 %\n",
                encoding="utf-8",
            )
            metrics = agent.parse_metrics([str(path)])

        self.assertEqual(metrics["analysis_files"], [str(path)])
        self.assertAlmostEqual(metrics["summary"]["merit_value"], 123.4)
        self.assertAlmostEqual(metrics["summary"]["rms_spot_um"], 5.6)
        self.assertAlmostEqual(metrics["summary"]["mtf"][40], 0.27)
        self.assertAlmostEqual(metrics["summary"]["distortion_percent"], 1.8)

    def test_decide_stage_acceptance_rejects_regression_and_requests_recovery(self):
        agent = load_agent()
        previous = {"summary": {"merit_value": 100.0, "rms_spot_um": 5.0, "mtf": {40: 0.35}, "constraint_violations": 0}}
        current = {"summary": {"merit_value": 110.0, "rms_spot_um": 6.0, "mtf": {40: 0.25}, "constraint_violations": 1}}

        decision = agent.decide_stage_acceptance(previous, current, "image-quality", {})

        self.assertFalse(decision["accepted"])
        self.assertEqual(decision["recovery_action"], "shrink_variable_set")
        self.assertIn("constraint", decision["reason"])

    def test_main_logs_seed_provenance_structural_gaps_before_optimization_and_uses_policy_metadata(self):
        import tempfile

        agent = load_agent()
        timeline: list[tuple[str, object]] = []
        system = FakeSystem()
        app = FakeApp(system)
        active_stage = {"name": None}
        requirements = {
            "seed_design": {
                "selected_case": "seeded zoom",
                "selected_case_path": "seeds/seeded_zoom.zmx",
                "family_hint": "zoom_imaging",
                "provenance": {
                    "source_type": "catalog_reference",
                    "source_name": "seeded zoom",
                    "source_path": "seeds/seeded_zoom.zmx",
                    "approval_status": "user_approved",
                },
                "selection_notes": ["controller should preserve provenance"],
                "structural_gaps": [
                    {"axis": "aperture", "requested": "f/2.8", "severity": "warning", "note": "starter lens is too slow"},
                    {"axis": "field", "requested": "6 deg", "severity": "critical", "note": "needs more field coverage"},
                ],
            },
            "automation": {"max_stage_retries": 2},
        }

        def fake_append_jsonl(_path, event):
            timeline.append(("log", event))

        def fake_connect_zemax(zos_root, standalone=False):
            timeline.append(("connect", {"zos_root": zos_root, "standalone": standalone}))
            return app

        def fake_load_or_create_system(connected_app, loaded_requirements):
            self.assertIs(connected_app, app)
            self.assertEqual(loaded_requirements["seed_design"]["selected_case"], "seeded zoom")
            system._design_seed_context = {
                "seed_design": loaded_requirements["seed_design"],
                "selection": {},
                "starter_profile": {"starter_profile": "seed-aware"},
            }
            system.design_working_data = {
                "seed_source": "seed_design.selected_case_path",
                "provenance": dict(loaded_requirements["seed_design"]["provenance"]),
                "selection_notes": list(loaded_requirements["seed_design"]["selection_notes"]),
            }
            timeline.append(("seed", system.design_working_data["provenance"]["source_name"]))
            return system

        def fake_configure_variables_and_merit(target_system, loaded_requirements, stage, recovery_level=0):
            active_stage["name"] = stage
            policy = {
                "stage": stage,
                "recovery_level": recovery_level,
                "policy_token": f"{stage}:{recovery_level}",
                "zoom_policy": {
                    "complex_zoom": True,
                    "failure_intercept": "rollback_then_shrink",
                    "release_order": [1, 2, 3],
                    "release_mode": "center-first-then-edges",
                },
            }
            timeline.append(("configure", policy))
            return policy

        def fake_run_local_optimization(target_system, seconds=None):
            timeline.append(("optimize", {"stage": active_stage["name"], "seconds": seconds}))

        def fake_evaluate_stage(target_system, out_dir, stage):
            timeline.append(("evaluate", stage))
            metrics_by_stage = {
                "baseline": {"summary": {"merit_value": 10.0, "rms_spot_um": 2.0, "mtf": {40: 0.4}, "constraint_violations": 0}},
                "feasibility": {"summary": {"merit_value": 20.0, "rms_spot_um": 3.0, "mtf": {40: 0.2}, "constraint_violations": 0}},
                "image-quality": {"summary": {"merit_value": 18.0, "rms_spot_um": 2.5, "mtf": {40: 0.25}, "constraint_violations": 0}},
                "field-balance": {"summary": {"merit_value": 16.0, "rms_spot_um": 2.3, "mtf": {40: 0.3}, "constraint_violations": 0}},
                "manufacturability": {"summary": {"merit_value": 15.0, "rms_spot_um": 2.2, "mtf": {40: 0.32}, "constraint_violations": 0}},
            }
            return agent.StageResult(name=stage, accepted=True, metrics=metrics_by_stage[stage], notes=["evaluated"])

        def fake_decide_stage_acceptance(previous_metrics, current_metrics, stage, loaded_requirements, control_plan=None):
            timeline.append(("decision-input", {"stage": stage, "control_plan": control_plan}))
            if stage == "baseline":
                return {
                    "accepted": True,
                    "score": 0,
                    "reason": "baseline accepted",
                    "recovery_action": "accept",
                    "current_violations": 0,
                    "previous_violations": 0,
                }
            self.assertIsNotNone(control_plan)
            self.assertEqual(control_plan["policy_token"], f"{stage}:0")
            return {
                "accepted": True,
                "score": 1,
                "reason": "policy honored",
                "recovery_action": control_plan["zoom_policy"]["failure_intercept"],
                "current_violations": 0,
                "previous_violations": 0,
            }

        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            requirements_path = tmp_path / "requirements.json"
            requirements_path.write_text(json.dumps(requirements), encoding="utf-8")
            out_dir = tmp_path / "out"

            with (
                mock.patch.object(agent, "parse_args", return_value=SimpleNamespace(requirements=str(requirements_path), out=str(out_dir), zos_root=None, standalone=False)),
                mock.patch.object(agent, "append_jsonl", side_effect=fake_append_jsonl),
                mock.patch.object(agent, "connect_zemax", side_effect=fake_connect_zemax),
                mock.patch.object(agent, "load_or_create_system", side_effect=fake_load_or_create_system),
                mock.patch.object(agent, "configure_variables_and_merit", side_effect=fake_configure_variables_and_merit),
                mock.patch.object(agent, "run_local_optimization", side_effect=fake_run_local_optimization),
                mock.patch.object(agent, "evaluate_stage", side_effect=fake_evaluate_stage),
                mock.patch.object(agent, "decide_stage_acceptance", side_effect=fake_decide_stage_acceptance),
            ):
                agent.main()

        seed_selected_index = next(index for index, item in enumerate(timeline) if item[0] == "log" and item[1]["event"] == "seed-selected")
        structural_gaps_index = next(index for index, item in enumerate(timeline) if item[0] == "log" and item[1]["event"] == "seed-structural-gaps")
        first_optimize_index = next(index for index, item in enumerate(timeline) if item[0] == "optimize")

        self.assertLess(seed_selected_index, structural_gaps_index)
        self.assertLess(structural_gaps_index, first_optimize_index)

        seed_event = next(item[1] for item in timeline if item[0] == "log" and item[1]["event"] == "seed-selected")
        structural_event = next(item[1] for item in timeline if item[0] == "log" and item[1]["event"] == "seed-structural-gaps")
        feasibility_policy_event = next(item[1] for item in timeline if item[0] == "log" and item[1]["event"] == "stage-policy" and item[1]["stage"] == "feasibility")
        feasibility_decision_input = next(item[1] for item in timeline if item[0] == "decision-input" and item[1]["stage"] == "feasibility")

        self.assertEqual(seed_event["seed_source"], "seed_design.selected_case_path")
        self.assertEqual(seed_event["provenance"]["source_name"], "seeded zoom")
        self.assertEqual(structural_event["count"], 2)
        self.assertEqual([gap["axis"] for gap in structural_event["structural_gaps"]], ["aperture", "field"])
        self.assertEqual(feasibility_policy_event["policy"]["policy_token"], "feasibility:0")
        self.assertEqual(feasibility_decision_input["control_plan"], feasibility_policy_event["policy"])

        optimize_stages = [item[1]["stage"] for item in timeline if item[0] == "optimize"]
        self.assertEqual(optimize_stages, ["feasibility", "image-quality", "field-balance", "manufacturability"])

    def test_main_clamps_zero_stage_retries_to_one(self):
        import tempfile

        agent = load_agent()
        timeline: list[tuple[str, object]] = []
        system = FakeSystem()
        app = FakeApp(system)
        requirements = {
            "seed_design": {
                "selected_case": "seeded zoom",
                "selected_case_path": "seeds/seeded_zoom.zmx",
                "family_hint": "zoom_imaging",
                "provenance": {"source_name": "seeded zoom", "source_path": "seeds/seeded_zoom.zmx"},
                "selection_notes": [],
                "structural_gaps": [],
            },
            "automation": {"max_stage_retries": 0, "max_stages": 2},
        }

        def fake_append_jsonl(_path, event):
            timeline.append(("log", event))

        def fake_connect_zemax(zos_root, standalone=False):
            return app

        def fake_load_or_create_system(connected_app, loaded_requirements):
            system._design_seed_context = {"seed_design": loaded_requirements["seed_design"], "selection": {}, "starter_profile": {}}
            system.design_working_data = {"seed_source": "seed_design.selected_case_path"}
            return system

        def fake_configure_variables_and_merit(target_system, loaded_requirements, stage, recovery_level=0):
            return {"stage": stage, "recovery_level": recovery_level, "surface_release_order": [1], "thickness_surfaces": [], "material_surfaces": [], "zoom_policy": {"complex_zoom": True, "failure_intercept": "shrink_variable_set", "release_order": [1]}}

        def fake_run_local_optimization(target_system, seconds=None):
            timeline.append(("optimize", seconds))

        def fake_evaluate_stage(target_system, out_dir, stage):
            metrics = {"summary": {"merit_value": 10.0 if stage == "baseline" else 9.0, "rms_spot_um": 2.0, "mtf": {40: 0.3}, "constraint_violations": 0}}
            return agent.StageResult(name=stage, accepted=True, metrics=metrics, notes=["evaluated"])

        def fake_decide_stage_acceptance(previous_metrics, current_metrics, stage, loaded_requirements, control_plan=None):
            return {
                "accepted": True,
                "score": 1,
                "reason": f"{stage} accepted",
                "recovery_action": "accept",
                "current_violations": 0,
                "previous_violations": 0,
            }

        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            requirements_path = tmp_path / "requirements.json"
            requirements_path.write_text(json.dumps(requirements), encoding="utf-8")

            with (
                mock.patch.object(agent, "parse_args", return_value=SimpleNamespace(requirements=str(requirements_path), out=str(tmp_path / "out"), zos_root=None, standalone=False)),
                mock.patch.object(agent, "append_jsonl", side_effect=fake_append_jsonl),
                mock.patch.object(agent, "connect_zemax", side_effect=fake_connect_zemax),
                mock.patch.object(agent, "load_or_create_system", side_effect=fake_load_or_create_system),
                mock.patch.object(agent, "configure_variables_and_merit", side_effect=fake_configure_variables_and_merit),
                mock.patch.object(agent, "run_local_optimization", side_effect=fake_run_local_optimization),
                mock.patch.object(agent, "evaluate_stage", side_effect=fake_evaluate_stage),
                mock.patch.object(agent, "decide_stage_acceptance", side_effect=fake_decide_stage_acceptance),
            ):
                agent.main()

        optimize_count = sum(1 for item in timeline if item[0] == "optimize")
        self.assertEqual(optimize_count, 1)
        stage_names = [item[1]["stage"] for item in timeline if item[0] == "log" and item[1]["event"] == "stage-start"]
        self.assertEqual(stage_names, ["baseline", "feasibility"])

    def test_main_rolls_back_to_last_accepted_lens_after_failed_stage(self):
        import tempfile

        agent = load_agent()
        system = FakeSystem()
        app = FakeApp(system)
        requirements = {
            "seed_design": {
                "selected_case": "seeded zoom",
                "selected_case_path": "seeds/seeded_zoom.zmx",
                "family_hint": "zoom_imaging",
                "provenance": {"source_name": "seeded zoom", "source_path": "seeds/seeded_zoom.zmx"},
                "selection_notes": [],
                "structural_gaps": [],
            },
            "automation": {"max_stage_retries": 1, "max_stages": 2},
        }

        def fake_append_jsonl(_path, event):
            pass

        def fake_connect_zemax(zos_root, standalone=False):
            return app

        def fake_load_or_create_system(connected_app, loaded_requirements):
            system._design_seed_context = {"seed_design": loaded_requirements["seed_design"], "selection": {}, "starter_profile": {}}
            system.design_working_data = {"seed_source": "seed_design.selected_case_path"}
            return system

        def fake_configure_variables_and_merit(target_system, loaded_requirements, stage, recovery_level=0):
            return {"stage": stage, "recovery_level": recovery_level, "surface_release_order": [1], "thickness_surfaces": [], "material_surfaces": [], "zoom_policy": {"complex_zoom": True, "failure_intercept": "rollback_then_shrink", "release_order": [1]}}

        def fake_run_local_optimization(target_system, seconds=None):
            pass

        def fake_evaluate_stage(target_system, out_dir, stage):
            metrics = {
                "baseline": {"summary": {"merit_value": 10.0, "rms_spot_um": 2.0, "mtf": {40: 0.3}, "constraint_violations": 0}},
                "feasibility": {"summary": {"merit_value": 12.0, "rms_spot_um": 2.4, "mtf": {40: 0.2}, "constraint_violations": 0}},
            }[stage]
            return agent.StageResult(name=stage, accepted=True, lens_path=str(Path(out_dir) / f"{stage}.zmx"), metrics=metrics, notes=["evaluated"])

        def fake_decide_stage_acceptance(previous_metrics, current_metrics, stage, loaded_requirements, control_plan=None):
            if stage == "baseline":
                return {
                    "accepted": True,
                    "score": 0,
                    "reason": "baseline accepted",
                    "recovery_action": "accept",
                    "current_violations": 0,
                    "previous_violations": 0,
                }
            return {
                "accepted": False,
                "score": -1,
                "reason": "feasibility regressed",
                "recovery_action": "rollback_then_shrink",
                "current_violations": 0,
                "previous_violations": 0,
            }

        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            requirements_path = tmp_path / "requirements.json"
            requirements_path.write_text(json.dumps(requirements), encoding="utf-8")

            with (
                mock.patch.object(agent, "parse_args", return_value=SimpleNamespace(requirements=str(requirements_path), out=str(tmp_path / "out"), zos_root=None, standalone=False)),
                mock.patch.object(agent, "append_jsonl", side_effect=fake_append_jsonl),
                mock.patch.object(agent, "connect_zemax", side_effect=fake_connect_zemax),
                mock.patch.object(agent, "load_or_create_system", side_effect=fake_load_or_create_system),
                mock.patch.object(agent, "configure_variables_and_merit", side_effect=fake_configure_variables_and_merit),
                mock.patch.object(agent, "run_local_optimization", side_effect=fake_run_local_optimization),
                mock.patch.object(agent, "evaluate_stage", side_effect=fake_evaluate_stage),
                mock.patch.object(agent, "decide_stage_acceptance", side_effect=fake_decide_stage_acceptance),
            ):
                agent.main()

        self.assertEqual(system.loaded_paths, [(str(tmp_path / "out" / "baseline.zmx"), False)])

    def test_stage_sequence_remains_baseline_through_manufacturability(self):
        agent = load_agent()

        self.assertEqual(
            agent.STAGES,
            ["baseline", "feasibility", "image-quality", "field-balance", "manufacturability"],
        )


if __name__ == "__main__":
    unittest.main()
