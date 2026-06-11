"""Controller scaffold for an automated Zemax optical design loop."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

if __package__ in {None, ""}:
    script_dir = Path(__file__).resolve().parent
    if str(script_dir) not in sys.path:
        sys.path.insert(0, str(script_dir))

from zos_design_primitives import (
    StageResult,
    append_jsonl,
    configure_variables_and_merit,
    connect_zemax,
    export_common_analyses,
    load_or_create_system,
    parse_metrics,
    run_local_optimization,
    write_stage_result,
)


STAGES = ["baseline", "feasibility", "image-quality", "field-balance", "manufacturability"]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run an automated Zemax optical design loop.")
    parser.add_argument("--requirements", required=True, help="Path to normalized requirements JSON.")
    parser.add_argument("--out", default="automated-zemax-design", help="Output directory.")
    parser.add_argument("--zos-root", help="OpticStudio install directory.")
    parser.add_argument("--standalone", action="store_true", help="Create a new OpticStudio instance instead of attaching to Interactive Extension.")
    return parser.parse_args()


def load_requirements(path: Path) -> dict:
    requirements = json.loads(path.read_text(encoding="utf-8"))
    requirements.setdefault("assumptions", [])
    requirements.setdefault("automation", {})
    return requirements


def evaluate_stage(system, out_dir: Path, stage: str) -> StageResult:
    analysis_dir = out_dir / "analyses" / stage
    analysis_files = export_common_analyses(system, analysis_dir)
    metrics = parse_metrics(analysis_files)
    metrics_path = out_dir / f"metrics-{stage}.json"
    metrics_path.write_text(json.dumps(metrics, indent=2), encoding="utf-8")

    lens_path = out_dir / f"{stage}.zmx"
    system.SaveAs(str(lens_path))

    result = StageResult(
        name=stage,
        lens_path=str(lens_path),
        metrics_path=str(metrics_path),
        analysis_dir=str(analysis_dir),
        accepted=True,
        notes=["Stage evaluated and saved."],
        metrics=metrics,
    )
    write_stage_result(out_dir, result)
    return result


def _summarize_structural_gaps(seed_context: dict) -> list[dict]:
    seed_design = (seed_context or {}).get("seed_design") or {}
    gaps = []
    for gap in seed_design.get("structural_gaps") or []:
        if not isinstance(gap, dict):
            continue
        gaps.append(
            {
                "axis": gap.get("axis"),
                "requested": gap.get("requested"),
                "seed": gap.get("seed"),
                "severity": gap.get("severity"),
                "note": gap.get("note"),
            }
        )
    return gaps


def _seed_log_payload(system) -> dict:
    seed_context = getattr(system, "_design_seed_context", {}) or {}
    seed_design = seed_context.get("seed_design") or {}
    working_data = getattr(system, "design_working_data", {}) or {}
    provenance = dict(seed_design.get("provenance") or {})
    return {
        "selected_case": seed_design.get("selected_case"),
        "selected_case_path": seed_design.get("selected_case_path"),
        "family_hint": seed_design.get("family_hint"),
        "seed_source": working_data.get("seed_source"),
        "provenance": provenance,
        "selection_notes": list(seed_design.get("selection_notes") or []),
    }


def _is_complex_zoom(requirements: dict, control_plan: dict | None = None) -> bool:
    seed_design = requirements.get("seed_design") or {}
    if seed_design.get("family_hint") == "zoom_imaging":
        return True
    if requirements.get("constraints", {}).get("zoom_configurations"):
        return True
    if control_plan and control_plan.get("zoom_policy", {}).get("complex_zoom"):
        return True
    return False


def decide_stage_acceptance(
    previous_metrics: dict | None,
    current_metrics: dict,
    stage: str,
    requirements: dict,
    control_plan: dict | None = None,
) -> dict:
    previous_summary = (previous_metrics or {}).get("summary") or {}
    current_summary = current_metrics.get("summary") or {}
    reasons: list[str] = []

    previous_violations = int(previous_summary.get("constraint_violations") or 0)
    current_violations = int(current_summary.get("constraint_violations") or 0)
    if current_violations > previous_violations:
        reasons.append("constraint regression")

    score = 0
    score += _compare_lower_is_better(previous_summary, current_summary, "merit_value")
    score += _compare_lower_is_better(previous_summary, current_summary, "rms_spot_um")
    score += _compare_lower_is_better(previous_summary, current_summary, "distortion_percent")
    score += _compare_lower_is_better(previous_summary, current_summary, "wavefront_rms_waves")
    score += _compare_lower_is_better(previous_summary, current_summary, "total_track_mm")
    score += _compare_higher_is_better(previous_summary, current_summary, "mtf")

    if stage == "baseline" or not previous_metrics:
        accepted = True
        recovery_action = "accept"
        reasons.append("baseline accepted")
    else:
        accepted = current_violations <= previous_violations and score > 0 and not reasons
        recovery_action = "accept" if accepted else "shrink_variable_set"
        if score > 0:
            reasons.append("metrics improved")
        elif score < 0:
            reasons.append("metrics regressed")
        else:
            reasons.append("metrics unchanged")

    if current_violations > previous_violations:
        recovery_action = "shrink_variable_set"

    if stage != "baseline" and _is_complex_zoom(requirements, control_plan) and not accepted:
        recovery_action = "rollback_then_shrink"

    if requirements.get("automation", {}).get("prefer_rollback_on_regression") and not accepted:
        recovery_action = "rollback_then_shrink"

    return {
        "accepted": accepted,
        "score": score,
        "reason": "; ".join(reasons) if reasons else "no decision",
        "recovery_action": recovery_action,
        "current_violations": current_violations,
        "previous_violations": previous_violations,
    }


def _compare_lower_is_better(previous_summary: dict, current_summary: dict, key: str) -> int:
    previous = previous_summary.get(key)
    current = current_summary.get(key)
    if previous is None or current is None:
        return 0
    if current < previous:
        return 1
    if current > previous:
        return -1
    return 0


def _compare_higher_is_better(previous_summary: dict, current_summary: dict, key: str) -> int:
    previous = (previous_summary.get(key) or {}) if key == "mtf" else previous_summary.get(key)
    current = (current_summary.get(key) or {}) if key == "mtf" else current_summary.get(key)
    if not previous or not current:
        return 0
    if key == "mtf":
        shared_frequencies = sorted(set(previous) & set(current))
        if not shared_frequencies:
            return 0
        deltas = []
        for frequency in shared_frequencies:
            if current[frequency] > previous[frequency]:
                deltas.append(1)
            elif current[frequency] < previous[frequency]:
                deltas.append(-1)
            else:
                deltas.append(0)
        return 1 if sum(deltas) > 0 else -1 if sum(deltas) < 0 else 0
    if current > previous:
        return 1
    if current < previous:
        return -1
    return 0


def main() -> None:
    args = parse_args()
    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    log_path = out_dir / "design-log.jsonl"
    requirements = load_requirements(Path(args.requirements))
    stage_limit = requirements.get("automation", {}).get("max_stages", len(STAGES))
    try:
        stage_limit = int(stage_limit)
    except (TypeError, ValueError):
        stage_limit = len(STAGES)
    stage_limit = max(1, min(len(STAGES), stage_limit))
    stage_sequence = STAGES[:stage_limit]

    app = None
    try:
        app = connect_zemax(args.zos_root, standalone=args.standalone)
        system = load_or_create_system(app, requirements)
        seed_payload = _seed_log_payload(system)
        append_jsonl(log_path, {"event": "seed-selected", **seed_payload})
        seed_context = getattr(system, "_design_seed_context", {}) or {}
        structural_gaps = _summarize_structural_gaps(seed_context)
        if structural_gaps:
            append_jsonl(
                log_path,
                {
                    "event": "seed-structural-gaps",
                    "count": len(structural_gaps),
                    "family_hint": seed_payload.get("family_hint"),
                    "structural_gaps": structural_gaps,
                },
        )
        last_accepted_metrics = None
        last_accepted_lens = None
        for stage in stage_sequence:
            append_jsonl(log_path, {"event": "stage-start", "stage": stage})
            attempts = 1 if stage == "baseline" else int(requirements.get("automation", {}).get("max_stage_retries", 2))
            attempts = max(1, attempts)
            result = None
            decision = None
            rolled_back_to_last_accepted = False
            for attempt in range(attempts):
                if stage != "baseline":
                    if attempt > 0 and last_accepted_lens:
                        system.LoadFile(last_accepted_lens, False)
                    control_plan = configure_variables_and_merit(system, requirements, stage, recovery_level=attempt)
                    append_jsonl(
                        log_path,
                        {
                            "event": "stage-policy",
                            "stage": stage,
                            "attempt": attempt + 1,
                            "policy": control_plan,
                        },
                    )
                    seconds = requirements.get("automation", {}).get("max_optimization_seconds_per_stage")
                    run_local_optimization(system, seconds=seconds)
                result = evaluate_stage(system, out_dir, stage)
                decision = decide_stage_acceptance(
                    last_accepted_metrics,
                    result.metrics or {},
                    stage,
                    requirements,
                    control_plan=control_plan if stage != "baseline" else None,
                )
                result.accepted = bool(decision["accepted"])
                result.notes.append(decision["reason"])
                write_stage_result(out_dir, result)
                append_jsonl(
                    log_path,
                    {
                        "event": "stage-decision",
                        "stage": stage,
                        "attempt": attempt + 1,
                        "decision": decision,
                        "result": result.__dict__,
                    },
                )
                if result.accepted:
                    last_accepted_metrics = result.metrics
                    last_accepted_lens = result.lens_path
                    break
                if decision["recovery_action"].startswith("rollback") and last_accepted_lens:
                    system.LoadFile(last_accepted_lens, False)
                    rolled_back_to_last_accepted = True
            if result is None:
                result = StageResult(
                    name=stage,
                    accepted=False,
                    notes=["Stage did not complete."],
                    metrics={"summary": {}},
                )
            if not result.accepted and last_accepted_lens and not rolled_back_to_last_accepted:
                system.LoadFile(last_accepted_lens, False)
            append_jsonl(log_path, {"event": "stage-finish", "stage": stage, "result": result.__dict__, "decision": decision})
    finally:
        if app is not None and args.standalone:
            app.CloseApplication()


if __name__ == "__main__":
    main()
