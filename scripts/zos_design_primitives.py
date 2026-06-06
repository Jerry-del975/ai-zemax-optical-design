"""Zemax OpticStudio 2024 R1 primitives for automated optical design."""

from __future__ import annotations

import json
import os
import sys
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any


DEFAULT_ZOSAPI_ROOT_CANDIDATES = [
    r"D:\Program Files\Ansys Zemax OpticStudio 2024 R1.00",
    r"C:\Program Files\Ansys Zemax OpticStudio 2024 R1.00",
    r"C:\Program Files\ANSYS Inc\Zemax OpticStudio 2024 R1.00",
    r"C:\Program Files\ANSYS Zemax OpticStudio",
    r"C:\Program Files\Zemax OpticStudio",
]


@dataclass
class StageResult:
    name: str
    lens_path: str | None = None
    metrics_path: str | None = None
    analysis_dir: str | None = None
    merit_value: float | None = None
    accepted: bool = False
    notes: list[str] = field(default_factory=list)


def resolve_zosapi_root(explicit_root: str | None = None) -> Path:
    candidates: list[Path] = []
    if explicit_root:
        candidates.append(Path(explicit_root))
    env_root = os.environ.get("ZOSAPI_ROOT")
    if env_root:
        candidates.append(Path(env_root))
    candidates.extend(Path(item) for item in DEFAULT_ZOSAPI_ROOT_CANDIDATES)

    for candidate in candidates:
        if _has_nethelper(candidate):
            return candidate
        subdir = candidate / "ZOS-API"
        if _has_nethelper(subdir):
            return subdir

    checked = "\n".join(str(item) for item in candidates)
    raise FileNotFoundError(
        "Could not find ZOSAPI_NetHelper.dll for Ansys Zemax OpticStudio 2024 R1.\n"
        f"Checked:\n{checked}\n"
        "Set ZOSAPI_ROOT to the OpticStudio install directory if it is installed elsewhere."
    )


def _has_nethelper(path: Path) -> bool:
    return path.is_dir() and (path / "ZOSAPI_NetHelper.dll").is_file()


def connect_zemax(zos_root: str | None = None, standalone: bool = False):
    """Connect to OpticStudio 2024 R1 via ZOS-API and return the application."""
    root = resolve_zosapi_root(zos_root)
    if str(root) not in sys.path:
        sys.path.insert(0, str(root))

    try:
        import clr  # type: ignore
    except ImportError as exc:
        raise RuntimeError("pythonnet is required for ZOS-API automation. Install pythonnet in the Python used to run this script.") from exc

    nethelper = root / "ZOSAPI_NetHelper.dll"
    interfaces = root / "ZOSAPI_Interfaces.dll"
    zosapi = root / "ZOSAPI.dll"

    if nethelper.is_file():
        clr.AddReference(str(nethelper))
        try:
            import ZOSAPI_NetHelper  # type: ignore

            ZOSAPI_NetHelper.ZOSAPI_Initializer.Initialize(str(root))
        except Exception:
            pass

    clr.AddReference(str(interfaces))
    clr.AddReference(str(zosapi))
    import ZOSAPI  # type: ignore

    connection = ZOSAPI.ZOSAPI_Connection()
    app = connection.CreateNewApplication() if standalone else connection.ConnectAsExtension(0)
    if app is None:
        mode = "Standalone" if standalone else "Interactive Extension"
        raise RuntimeError(f"Failed to connect to OpticStudio in {mode} mode.")
    if hasattr(app, "IsValidLicenseForAPI") and not app.IsValidLicenseForAPI:
        mode = "Standalone" if standalone else "Interactive Extension"
        raise RuntimeError(f"Connected to OpticStudio in {mode} mode, but no valid ZOS-API license is available.")
    if getattr(app, "PrimarySystem", None) is None:
        mode = "Standalone" if standalone else "Interactive Extension"
        raise RuntimeError(f"Connected to OpticStudio in {mode} mode, but PrimarySystem is not available.")
    return app


def read_text_robust(path: Path) -> str:
    data = path.read_bytes()
    for encoding in ("utf-16", "utf-8-sig", "utf-8"):
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
    input_lens = requirements.get("input_lens")
    if input_lens:
        system.LoadFile(str(Path(input_lens).resolve()), False)
        return system
    create_minimal_sequential_system(system, requirements)
    return system


def create_minimal_sequential_system(system: Any, requirements: dict[str, Any]) -> None:
    """Create a simple starting sequential system from basic requirements."""
    system.New(False)
    set_wavelengths(system, requirements.get("wavelengths_um") or [])
    set_fields(system, requirements.get("fields") or [])
    set_aperture(system, requirements.get("aperture") or {})

    lde = system.LDE
    while lde.NumberOfSurfaces < 4:
        lde.InsertNewSurfaceAt(max(1, lde.NumberOfSurfaces))

    # A deliberately modest two-surface starter that optimization can reshape.
    s1 = lde.GetSurfaceAt(1)
    s1.Radius = 50.0
    s1.Thickness = 5.0
    s1.Material = "N-BK7"

    s2 = lde.GetSurfaceAt(2)
    s2.Radius = -50.0
    s2.Thickness = 40.0
    s2.Material = ""


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
    metrics: dict[str, Any] = {"analysis_files": analysis_files, "parser_notes": []}
    for file_name in analysis_files:
        text = read_text_robust(Path(file_name))
        metrics["parser_notes"].append({"file": file_name, "chars": len(text)})
    return metrics


def configure_variables_and_merit(system: Any, requirements: dict[str, Any], stage: str) -> None:
    """Set a conservative starter variable set for 2024 R1.

    Task-specific merit operands should be added by the agent using
    references/merit-function.md after inspecting the actual lens.
    """
    _ = requirements
    lde = system.LDE
    for surf_idx in (1, 2):
        try:
            surface = lde.GetSurfaceAt(surf_idx)
            surface.RadiusCell.MakeSolveVariable()
            if stage in {"feasibility", "image-quality", "field-balance"}:
                surface.ThicknessCell.MakeSolveVariable()
        except Exception:
            continue


def run_local_optimization(system: Any, seconds: int | None = None) -> None:
    _ = seconds
    tool = system.Tools.OpenLocalOptimization()
    try:
        tool.RunAndWaitForCompletion()
    finally:
        tool.Close()
