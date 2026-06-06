"""Controller scaffold for an automated Zemax optical design loop."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

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
    )
    write_stage_result(out_dir, result)
    return result


def main() -> None:
    args = parse_args()
    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    log_path = out_dir / "design-log.jsonl"
    requirements = load_requirements(Path(args.requirements))

    app = None
    try:
        app = connect_zemax(args.zos_root, standalone=args.standalone)
        system = load_or_create_system(app, requirements)
        for stage in STAGES:
            append_jsonl(log_path, {"event": "stage-start", "stage": stage})
            if stage != "baseline":
                configure_variables_and_merit(system, requirements, stage)
                seconds = requirements.get("automation", {}).get("max_optimization_seconds_per_stage")
                run_local_optimization(system, seconds=seconds)
            result = evaluate_stage(system, out_dir, stage)
            append_jsonl(log_path, {"event": "stage-finish", "stage": stage, "result": result.__dict__})
    finally:
        if app is not None and args.standalone:
            app.CloseApplication()


if __name__ == "__main__":
    main()
