"""Zemax OpticStudio primitives for automated optical design (multi-version via ZOSPy)."""

from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any


@dataclass
class StageResult:
    name: str
    lens_path: str | None = None
    metrics_path: str | None = None
    analysis_dir: str | None = None
    merit_value: float | None = None
    accepted: bool = False
    notes: list[str] = field(default_factory=list)
    metrics: dict[str, Any] | None = None


def connect_zemax(zos_root: str | None = None, standalone: bool = False):
    """Connect to OpticStudio via ZOSPy and return the ZOS-API application object.

    ZOSPy handles version discovery (v20.3+), DLL loading, and connection
    initialization.  The returned object is the raw ZOS-API application so
    existing analysis / optimisation / save code works unchanged.
    """
    import zospy as zp  # type: ignore

    zos = zp.ZOS(zosapi_root=zos_root) if zos_root else zp.ZOS()
    mode = "standalone" if standalone else "extension"
    zos.connect(mode)

    app: Any = zos.Application  # raw ZOS-API application

    # Keep the ZOS instance alive — .NET remoting breaks if it is garbage-collected.
    app._zos = zos

    if app is None:
        mode_name = "Standalone" if standalone else "Interactive Extension"
        raise RuntimeError(f"Failed to connect to OpticStudio in {mode_name} mode.")
    if hasattr(app, "IsValidLicenseForAPI") and not app.IsValidLicenseForAPI:
        mode_name = "Standalone" if standalone else "Interactive Extension"
        raise RuntimeError(
            f"Connected to OpticStudio in {mode_name} mode, "
            "but no valid ZOS-API license is available."
        )
    if getattr(app, "PrimarySystem", None) is None:
        mode_name = "Standalone" if standalone else "Interactive Extension"
        raise RuntimeError(
            f"Connected to OpticStudio in {mode_name} mode, "
            "but PrimarySystem is not available."
        )
    return app


def read_text_robust(path: Path) -> str:
    data = path.read_bytes()
    if data.startswith((b"\xff\xfe", b"\xfe\xff")):
        try:
            return data.decode("utf-16")
        except UnicodeDecodeError:
            pass
    for encoding in ("utf-8-sig", "utf-8", "utf-16"):
        try:
            return data.decode(encoding)
        except UnicodeDecodeError:
            pass
    return data.decode("utf-8", errors="replace")


def append_jsonl(path: Path, event: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {"time": datetime.now().isoformat(timespec="seconds"), **event}
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, ensure_ascii=True) + "\n")


def write_stage_result(out_dir: Path, result: StageResult) -> Path:
    path = out_dir / f"stage-{result.name}.json"
    path.write_text(json.dumps(asdict(result), indent=2), encoding="utf-8")
    return path


def load_or_create_system(app: Any, requirements: dict[str, Any]):
    system = app.PrimarySystem
    seed_context = build_seed_context(requirements)
    seed_path = resolve_seed_path(requirements, seed_context)
    if seed_path is not None:
        try:
            system.LoadFile(str(seed_path), False)
            seed_context["selection"]["loaded"] = True
        except Exception as exc:
            seed_context["selection"]["loaded"] = False
            seed_context["selection"]["load_error"] = str(exc)
            create_seeded_sequential_system(system, requirements, seed_context)
        attach_design_context(system, seed_context)
        return system
    create_seeded_sequential_system(system, requirements, seed_context)
    attach_design_context(system, seed_context)
    return system


def create_minimal_sequential_system(system: Any, requirements: dict[str, Any]) -> None:
    """Create a simple starting sequential system from basic requirements."""
    create_seeded_sequential_system(system, requirements, build_seed_context(requirements))


def build_seed_context(requirements: dict[str, Any]) -> dict[str, Any]:
    seed_design = dict(requirements.get("seed_design") or {})
    provenance = dict(seed_design.get("provenance") or {})
    structural_gaps = list(seed_design.get("structural_gaps") or [])
    selection_notes = list(seed_design.get("selection_notes") or [])
    match_axes = list(seed_design.get("match_axes") or [])
    return {
        "seed_design": {
            "preferred_source": seed_design.get("preferred_source"),
            "family_hint": seed_design.get("family_hint"),
            "match_axes": match_axes,
            "provenance": provenance,
            "structural_gaps": structural_gaps,
            "selected_case": seed_design.get("selected_case"),
            "selected_case_path": seed_design.get("selected_case_path"),
            "selection_notes": selection_notes,
        },
        "selection": {},
        "starter_profile": {},
    }


def resolve_seed_path(requirements: dict[str, Any], seed_context: dict[str, Any]) -> Path | None:
    seed_design = seed_context["seed_design"]
    candidates = [
        (requirements.get("input_lens"), "input_lens"),
        (seed_design.get("selected_case_path"), "seed_design.selected_case_path"),
        (seed_design.get("provenance", {}).get("source_path"), "seed_design.provenance.source_path"),
    ]
    for candidate, source_label in candidates:
        if not candidate:
            continue
        path = Path(candidate).expanduser().resolve()
        seed_context["selection"] = {
            "selected_case": seed_design.get("selected_case") or path.stem,
            "selected_case_path": str(path),
            "source_label": source_label,
            "source": "explicit_path",
            "family_match_score": score_seed_family(seed_design, path),
            "exists": path.is_file(),
        }
        return path
    return None


def score_seed_family(seed_design: dict[str, Any], path: Path | None = None) -> int:
    family_hint = str(seed_design.get("family_hint") or "").lower()
    selected_case = str(seed_design.get("selected_case") or "").lower()
    provenance = seed_design.get("provenance") or {}
    score = 0
    if "zoom" in family_hint or "zoom" in selected_case:
        score += 2
    if path is not None and "zoom" in path.stem.lower():
        score += 2
    if provenance.get("source_type") in {"catalog_reference", "official_example_or_catalog"}:
        score += 1
    if seed_design.get("match_axes"):
        score += len(seed_design["match_axes"])
    return score


def attach_design_context(system: Any, seed_context: dict[str, Any]) -> None:
    setattr(system, "_design_seed_context", seed_context)
    working_data = {
        "seed_source": _seed_source_label(seed_context),
        "provenance": dict(seed_context["seed_design"].get("provenance") or {}),
        "selection_notes": list(seed_context["seed_design"].get("selection_notes") or []),
        "structural_gaps": list(seed_context["seed_design"].get("structural_gaps") or []),
        "starter_profile": "seed-aware" if seed_context.get("starter_profile") else "loaded-seed",
    }
    working_data.update(seed_context.get("selection") or {})
    working_data.update(seed_context.get("starter_profile") or {})
    setattr(system, "design_working_data", working_data)


def _seed_source_label(seed_context: dict[str, Any]) -> str:
    selection = seed_context.get("selection") or {}
    if selection.get("source") == "explicit_path":
        if selection.get("source_label"):
            return str(selection["source_label"])
    if seed_context.get("starter_profile"):
        return "seed_design.metadata_only"
    return "seed_design.unknown"


def create_seeded_sequential_system(system: Any, requirements: dict[str, Any], seed_context: dict[str, Any]) -> None:
    """Create a starter system that reflects the requested seed family."""
    system.New(False)
    set_wavelengths(system, requirements.get("wavelengths_um") or [])
    set_fields(system, requirements.get("fields") or [])
    set_aperture(system, requirements.get("aperture") or {})

    lde = system.LDE
    seed_design = seed_context["seed_design"]
    structural_gaps = seed_design.get("structural_gaps") or []
    family_hint = str(seed_design.get("family_hint") or "").lower()
    max_elements = requirements.get("constraints", {}).get("max_elements")

    starter_surface_count = 4
    if "zoom" in family_hint or any(gap.get("axis") == "group_count" for gap in structural_gaps):
        starter_surface_count = 8
    if structural_gaps:
        starter_surface_count = max(starter_surface_count, 6)
    if isinstance(max_elements, int):
        starter_surface_count = min(starter_surface_count, max_elements)

    while lde.NumberOfSurfaces < starter_surface_count:
        lde.InsertNewSurfaceAt(max(1, lde.NumberOfSurfaces))

    powered_surfaces = _starter_powered_surfaces(lde.NumberOfSurfaces, family_hint, structural_gaps)
    _populate_starter_surfaces(lde, powered_surfaces, family_hint)
    seed_context["starter_profile"] = {
        "family_hint": seed_design.get("family_hint"),
        "surface_count": lde.NumberOfSurfaces,
        "powered_surfaces": powered_surfaces,
        "group_count_hint": _extract_gap_hint(structural_gaps, "group_count"),
        "air_gap_hint": _extract_gap_hint(structural_gaps, "air_gap"),
        "starter_profile": "seed-aware",
    }
    setattr(system, "_starter_profile", seed_context["starter_profile"])


def _extract_gap_hint(structural_gaps: list[dict[str, Any]], axis: str) -> str | None:
    for gap in structural_gaps:
        if gap.get("axis") == axis:
            return str(gap.get("requested"))
    return None


def _starter_powered_surfaces(surface_count: int, family_hint: str, structural_gaps: list[dict[str, Any]]) -> list[int]:
    if surface_count <= 4:
        return [1, 2]
    if "zoom" in family_hint:
        return [1, 2, max(2, surface_count // 2 - 1), max(3, surface_count // 2), surface_count - 2]
    if any(gap.get("severity") == "critical" for gap in structural_gaps):
        return [1, 2, surface_count - 2]
    return [1, 2, surface_count - 2]


def _populate_starter_surfaces(lde: Any, powered_surfaces: list[int], family_hint: str) -> None:
    # Keep the starter conservative but non-trivial so optimization has real structure to move.
    for index in powered_surfaces:
        try:
            surface = lde.GetSurfaceAt(index)
        except Exception:
            continue
        if index == powered_surfaces[0]:
            surface.Radius = 60.0
            surface.Thickness = 6.0
            surface.Material = "N-BK7"
        elif index == powered_surfaces[-1]:
            surface.Radius = -60.0
            surface.Thickness = 40.0
            surface.Material = ""
        else:
            surface.Radius = 120.0 if "zoom" not in family_hint else 90.0
            surface.Thickness = 8.0
            surface.Material = "N-LAK22" if "zoom" in family_hint else ""


def set_wavelengths(system: Any, wavelengths: list[dict[str, Any]]) -> None:
    if not wavelengths:
        wavelengths = [{"value": 0.486, "weight": 1}, {"value": 0.588, "weight": 1}, {"value": 0.656, "weight": 1}]
    editor = system.SystemData.Wavelengths
    while editor.NumberOfWavelengths > 1:
        editor.RemoveWavelength(editor.NumberOfWavelengths)
    first = wavelengths[0]
    editor.GetWavelength(1).Wavelength = float(first["value"])
    editor.GetWavelength(1).Weight = float(first.get("weight", 1))
    for item in wavelengths[1:]:
        editor.AddWavelength(float(item["value"]), float(item.get("weight", 1)))


def set_fields(system: Any, fields: list[dict[str, Any]]) -> None:
    if not fields:
        fields = [{"type": "angle_deg", "value": 0.0}, {"type": "angle_deg", "value": 5.0}]
    editor = system.SystemData.Fields
    while editor.NumberOfFields > 1:
        editor.RemoveField(editor.NumberOfFields)
    for index, item in enumerate(fields, start=1):
        if index > editor.NumberOfFields:
            editor.AddField(0.0, 0.0, 1.0)
        field = editor.GetField(index)
        field.X = 0.0
        field.Y = float(item.get("value", 0.0))
        field.Weight = float(item.get("weight", 1.0))


def set_aperture(system: Any, aperture: dict[str, Any]) -> None:
    value = float(aperture.get("value", 4.0))
    # Keep this conservative: many 2024 R1 installs expose ApertureValue.
    system.SystemData.Aperture.ApertureValue = value


def export_common_analyses(system: Any, analysis_dir: Path) -> list[str]:
    analysis_dir.mkdir(parents=True, exist_ok=True)
    exported: list[str] = []
    factories = {
        "spot": "New_StandardSpot",
        "mtf": "New_FftMtf",
        "wavefront": "New_WavefrontMap",
        "rayfan": "New_RayFan",
        "distortion": "New_FieldCurvatureAndDistortion",
    }
    for name, factory in factories.items():
        if not hasattr(system.Analyses, factory):
            continue
        analysis = getattr(system.Analyses, factory)()
        try:
            analysis.ApplyAndWaitForCompletion()
            out = analysis_dir / f"{name}.txt"
            analysis.GetResults().GetTextFile(str(out))
            exported.append(str(out))
        finally:
            analysis.Close()
    return exported


def parse_metrics(analysis_files: list[str]) -> dict[str, Any]:
    metrics: dict[str, Any] = {
        "analysis_files": analysis_files,
        "parser_notes": [],
        "summary": {
            "merit_value": None,
            "efl_mm": None,
            "bfl_mm": None,
            "total_track_mm": None,
            "f_number": None,
            "na": None,
            "rms_spot_um": None,
            "mtf": {},
            "distortion_percent": None,
            "wavefront_rms_waves": None,
            "constraint_violations": 0,
        },
    }
    for file_name in analysis_files:
        text = read_text_robust(Path(file_name))
        parsed = _parse_analysis_text(text)
        metrics["parser_notes"].append({"file": file_name, "chars": len(text), "signals": sorted(parsed)})
        _merge_summary(metrics["summary"], parsed)
    return metrics


def _parse_analysis_text(text: str) -> dict[str, Any]:
    parsed: dict[str, Any] = {}
    merit_match = re.search(r"(?im)^(?:merit(?: function)?(?: value)?)[^0-9+-]*([-+]?\d+(?:\.\d+)?)", text)
    if merit_match:
        parsed["merit_value"] = float(merit_match.group(1))
    rms_match = re.search(r"(?im)^(?:rms\s+spot)[^0-9+-]*([-+]?\d+(?:\.\d+)?)", text)
    if rms_match:
        parsed["rms_spot_um"] = float(rms_match.group(1))
    distortion_match = re.search(r"(?im)^(?:distortion)[^0-9+-]*([-+]?\d+(?:\.\d+)?)", text)
    if distortion_match:
        parsed["distortion_percent"] = float(distortion_match.group(1))
    wavefront_match = re.search(r"(?im)^(?:wavefront(?:\s+rms)?)[^0-9+-]*([-+]?\d+(?:\.\d+)?)", text)
    if wavefront_match:
        parsed["wavefront_rms_waves"] = float(wavefront_match.group(1))
    efl_match = re.search(r"(?im)^(?:efl)[^0-9+-]*([-+]?\d+(?:\.\d+)?)", text)
    if efl_match:
        parsed["efl_mm"] = float(efl_match.group(1))
    bfl_match = re.search(r"(?im)^(?:bfl)[^0-9+-]*([-+]?\d+(?:\.\d+)?)", text)
    if bfl_match:
        parsed["bfl_mm"] = float(bfl_match.group(1))
    track_match = re.search(r"(?im)^(?:total\s+track)[^0-9+-]*([-+]?\d+(?:\.\d+)?)", text)
    if track_match:
        parsed["total_track_mm"] = float(track_match.group(1))
    f_number_match = re.search(r"(?im)^(?:f/#|f-number|f number)[^0-9+-]*([-+]?\d+(?:\.\d+)?)", text)
    if f_number_match:
        parsed["f_number"] = float(f_number_match.group(1))
    na_match = re.search(r"(?im)^(?:na|numerical aperture)[^0-9+-]*([-+]?\d+(?:\.\d+)?)", text)
    if na_match:
        parsed["na"] = float(na_match.group(1))

    mtf_matches = re.finditer(r"(?im)mtf\s*([0-9]+(?:\.\d+)?)\s*lp/mm[^0-9+-]*([-+]?\d+(?:\.\d+)?)", text)
    mtf: dict[int | float, float] = {}
    for match in mtf_matches:
        frequency = float(match.group(1))
        frequency_key: int | float = int(frequency) if frequency.is_integer() else frequency
        mtf[frequency_key] = float(match.group(2))
    if mtf:
        parsed["mtf"] = mtf
    if re.search(r"(?im)\bviolation\b", text):
        parsed["constraint_violations"] = parsed.get("constraint_violations", 0) + 1
    return parsed


def _merge_summary(summary: dict[str, Any], parsed: dict[str, Any]) -> None:
    for key in ("merit_value", "efl_mm", "bfl_mm", "total_track_mm", "f_number", "na", "rms_spot_um", "distortion_percent", "wavefront_rms_waves"):
        if parsed.get(key) is not None:
            summary[key] = parsed[key]
    if parsed.get("constraint_violations"):
        summary["constraint_violations"] += int(parsed["constraint_violations"])
    if parsed.get("mtf"):
        summary["mtf"].update(parsed["mtf"])


def configure_variables_and_merit(system: Any, requirements: dict[str, Any], stage: str, recovery_level: int = 0) -> dict[str, Any]:
    """Build a stage-specific structural control plan and apply it conservatively."""
    seed_design = requirements.get("seed_design") or {}
    constraints = requirements.get("constraints") or {}
    lde = system.LDE
    plan = _build_variable_plan(system, requirements, stage, recovery_level)
    for surf_idx in plan["surface_release_order"]:
        try:
            surface = lde.GetSurfaceAt(surf_idx)
            surface.RadiusCell.MakeSolveVariable()
            if surf_idx in plan["thickness_surfaces"]:
                surface.ThicknessCell.MakeSolveVariable()
            if surf_idx in plan["material_surfaces"]:
                try:
                    surface.MaterialCell.MakeSolveVariable()
                except Exception:
                    pass
        except Exception:
            continue
    if constraints.get("zoom_configurations") or seed_design.get("family_hint") == "zoom_imaging":
        plan["zoom_control"] = {
            "strategy": "staged_configuration_release",
            "configurations": constraints.get("zoom_configurations") or [],
            "mce_ready": True,
        }
        plan["zoom_policy"] = _build_zoom_policy(seed_design, stage, recovery_level, plan)
    else:
        plan["zoom_policy"] = {
            "complex_zoom": False,
            "failure_intercept": "shrink_variable_set",
            "release_order": plan["surface_release_order"],
        }
    setattr(system, "_design_control_plan", plan)
    return plan


def _build_variable_plan(system: Any, requirements: dict[str, Any], stage: str, recovery_level: int) -> dict[str, Any]:
    lde = system.LDE
    surface_count = getattr(lde, "NumberOfSurfaces", 0)
    seed_design = requirements.get("seed_design") or {}
    structural_gaps = seed_design.get("structural_gaps") or []
    family_hint = str(seed_design.get("family_hint") or "").lower()
    stage_defaults = {
        "baseline": {"active": [1, 2], "thickness": [], "material": []},
        "feasibility": {"active": [1, 2, max(2, surface_count - 2)], "thickness": [2], "material": []},
        "image-quality": {"active": _active_window(surface_count, 4), "thickness": [2, max(2, surface_count - 2)], "material": _material_window(surface_count, family_hint)},
        "field-balance": {"active": _active_window(surface_count, 5), "thickness": [2, max(2, surface_count // 2)], "material": _material_window(surface_count, family_hint)},
        "manufacturability": {"active": [1, 2, max(2, surface_count - 2)], "thickness": [2], "material": _material_window(surface_count, family_hint, allow_more=False)},
    }
    stage_plan = stage_defaults.get(stage, stage_defaults["feasibility"])
    if recovery_level > 0:
        stage_plan = _shrink_variable_plan(stage_plan, recovery_level)
    stage_plan = {
        "stage": stage,
        "recovery_level": recovery_level,
        "family_hint": seed_design.get("family_hint"),
        "structural_gaps": structural_gaps,
        "active_surfaces": sorted({i for i in stage_plan["active"] if 0 <= i < surface_count}),
        "thickness_surfaces": sorted({i for i in stage_plan["thickness"] if 0 <= i < surface_count}),
        "material_surfaces": sorted({i for i in stage_plan["material"] if 0 <= i < surface_count}),
        "surface_release_order": _surface_release_order(surface_count, stage, family_hint, structural_gaps),
        "variable_groups": _describe_variable_groups(stage, seed_design, recovery_level),
        "locked_groups": _describe_locked_groups(stage, seed_design, recovery_level),
    }
    return stage_plan


def _active_window(surface_count: int, width: int) -> list[int]:
    if surface_count <= 0:
        return []
    upper = min(surface_count - 1, max(2, width))
    lower = 1
    return list(range(lower, upper + 1))


def _material_window(surface_count: int, family_hint: str, allow_more: bool = True) -> list[int]:
    if surface_count <= 0:
        return []
    if "zoom" in family_hint and allow_more:
        return [2, max(2, surface_count // 2), max(2, surface_count - 2)]
    return [max(2, surface_count // 2)]


def _surface_release_order(surface_count: int, stage: str, family_hint: str, structural_gaps: list[dict[str, Any]]) -> list[int]:
    if surface_count <= 0:
        return []
    if "zoom" not in family_hint and not structural_gaps:
        return list(range(1, min(surface_count, 5)))

    last_interior = max(1, surface_count - 2)
    mid = max(2, surface_count // 2)
    stage_orders = {
        "baseline": [1, 2, last_interior],
        "feasibility": [1, 2, last_interior],
        "image-quality": [1, 2, mid - 1, mid, last_interior],
        "field-balance": [1, 2, mid - 1, mid, last_interior],
        "manufacturability": [1, 2, last_interior],
    }
    order = stage_orders.get(stage, [1, 2, last_interior])
    filtered = [idx for idx in order if 1 <= idx < surface_count]
    return _dedupe_ints(filtered)


def _dedupe_ints(values: list[int]) -> list[int]:
    seen: set[int] = set()
    ordered: list[int] = []
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        ordered.append(value)
    return ordered


def _build_zoom_policy(seed_design: dict[str, Any], stage: str, recovery_level: int, plan: dict[str, Any]) -> dict[str, Any]:
    complex_zoom = seed_design.get("family_hint") == "zoom_imaging" or bool(seed_design.get("structural_gaps"))
    release_order = list(plan.get("surface_release_order") or [])
    if stage in {"image-quality", "field-balance", "manufacturability"} and release_order:
        failure_intercept = "rollback_then_shrink"
    else:
        failure_intercept = "shrink_variable_set"
    if recovery_level > 0 and release_order:
        trimmed = max(1, len(release_order) - recovery_level)
        release_order = release_order[:trimmed]
    return {
        "complex_zoom": bool(complex_zoom),
        "failure_intercept": failure_intercept,
        "release_order": release_order,
        "release_mode": "center-first-then-edges" if complex_zoom else "default",
    }


def _shrink_variable_plan(stage_plan: dict[str, list[int]], recovery_level: int) -> dict[str, list[int]]:
    shrink_amount = min(recovery_level, max(1, len(stage_plan["active"]) - 1))
    return {
        "active": stage_plan["active"][:-shrink_amount] or stage_plan["active"][:1],
        "thickness": stage_plan["thickness"][: max(1, len(stage_plan["thickness"]) - shrink_amount)],
        "material": stage_plan["material"][: max(1, len(stage_plan["material"]) - shrink_amount)],
    }


def _describe_variable_groups(stage: str, seed_design: dict[str, Any], recovery_level: int) -> list[str]:
    groups = ["powered_curvatures"]
    if stage in {"feasibility", "image-quality", "field-balance"}:
        groups.append("air_spacings")
    if stage in {"image-quality", "field-balance", "manufacturability"}:
        groups.append("selected_materials")
    if seed_design.get("family_hint") == "zoom_imaging":
        groups.append("zoom_configuration_controls")
    if recovery_level:
        groups.append("reduced_free_variables")
    return groups


def _describe_locked_groups(stage: str, seed_design: dict[str, Any], recovery_level: int) -> list[str]:
    locked = ["stop", "chief_ray_budget"]
    if stage == "baseline":
        locked.append("all_but_starter_geometry")
    if stage == "feasibility":
        locked.append("glass_catalog_flex")
    if recovery_level:
        locked.append("high_sensitivity_groups")
    if seed_design.get("structural_gaps"):
        locked.append("seed_gap_traceability")
    return locked


def run_local_optimization(system: Any, seconds: int | None = None) -> None:
    _ = seconds
    tool = system.Tools.OpenLocalOptimization()
    try:
        tool.RunAndWaitForCompletion()
    finally:
        tool.Close()
