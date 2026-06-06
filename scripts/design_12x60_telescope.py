"""
12x60 Terrestrial Telescope -- Automated Zemax OpticStudio Design
=================================================================
Objective: 420mm EFL, f/7, 60mm EPD, air-spaced Fraunhofer doublet
Porro Type-I prism erector: N-BK7 equivalent glass block (160mm)
Field corrector: cemented doublet (N-BK7 + N-F2) for off-axis correction

Connects via Interactive Extension -- Zemax OpticStudio must be open.
"""

from __future__ import annotations

import json
import os
import shutil
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any

# -- Paths ----------------------------------------------------
SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_DIR = SCRIPT_DIR.parent
TIMESTAMP = datetime.now().strftime("%Y%m%d_%H%M%S")
OUT_DIR = PROJECT_DIR / "designs" / f"telescope_12x60_{TIMESTAMP}"
OUT_DIR.mkdir(parents=True, exist_ok=True)

ZOS_ROOT = r"D:\Program Files\Ansys Zemax OpticStudio 2024 R1.00"

# -- Design parameters -----------------------------------------
EFL_TARGET      = 420.0   # mm
EPD             = 60.0    # mm
HALF_FOV_DEG    = 2.0     # half-field (4.0deg full true FOV)
MAGNIFICATION   = 12.0
EXIT_PUPIL_DIAM = 5.0     # mm
FIELD_STOP_DIAM = 29.3    # mm = 2*420*tan(2deg)
PRISM_MATERIAL  = "N-BK7"
PRISM_PATH_MM   = 160.0   # equivalent glass path through Porro prisms

WAVELENGTHS = [
    (0.48613270, 1.0, "F"),
    (0.58756180, 1.0, "d"),
    (0.65627250, 1.0, "C"),
]

FIELDS = [
    (0.0, 1.0, "on-axis"),
    (1.4, 1.0, "0.7-field"),
    (2.0, 1.0, "full-field"),
]


# -- Helpers ---------------------------------------------------

def log(msg: str) -> None:
    ts = datetime.now().strftime("%H:%M:%S")
    line = f"[{ts}] {msg}"
    print(line, flush=True)
    with (OUT_DIR / "design-log.txt").open("a", encoding="utf-8") as f:
        f.write(line + "\n")


def connect_interactive() -> tuple:
    """Connect to OpticStudio Interactive Extension. Returns (app, system, ZOSAPI, MFE)."""
    sys.path.insert(0, ZOS_ROOT)
    import clr

    root = Path(ZOS_ROOT)
    clr.AddReference(str(root / "ZOSAPI_NetHelper.dll"))
    clr.AddReference(str(root / "ZOSAPI_Interfaces.dll"))
    clr.AddReference(str(root / "ZOSAPI.dll"))

    import ZOSAPI_NetHelper
    ZOSAPI_NetHelper.ZOSAPI_Initializer.Initialize(ZOS_ROOT)

    import ZOSAPI

    conn = ZOSAPI.ZOSAPI_Connection()
    app = conn.ConnectAsExtension(0)
    if app is None:
        raise RuntimeError("Failed to connect. Make sure OpticStudio is open.")
    if not app.IsValidLicenseForAPI:
        raise RuntimeError("No valid ZOS-API license.")
    if app.PrimarySystem is None:
        raise RuntimeError("PrimarySystem is None.")

    system = app.PrimarySystem

    # Get MeritOperandType enum from the MFE via an existing row
    mfe = system.MFE
    op = mfe.GetOperandAt(1)
    MeritOpType = type(op.Type)

    return app, system, ZOSAPI, MeritOpType


# -- Build lens ------------------------------------------------

def build_telescope(system: Any, ZOSAPI: Any) -> None:
    """
    Surface layout (0-indexed in API, 1-based in Zemax UI):
      Surf 0: OBJECT at infinity
      Surf 1: STOP -- entrance pupil at objective front vertex
      Surf 2: Obj crown front    (N-BK7, convex R>0)
      Surf 3: Obj crown rear     (air gap, convex R<0)
      Surf 4: Obj flint front    (N-F2)
      Surf 5: Obj flint rear     (air -> prism)
      Surf 6: Prism entrance     (N-BK7, flat)
      Surf 7: Prism mid          (N-BK7, flat, dummy fold)
      Surf 8: Prism exit         (N-BK7, flat)
      Surf 9: Corrector crown    (N-BK7, convex R>0)
      Surf 10: Corrector cement  (N-F2 on N-BK7)
      Surf 11: Corrector rear    (air -> image)
      Surf 12: IMAGE plane
    """
    log("Building 13-surface telescope model...")
    lde = system.LDE

    # New sequential system
    system.New(False)

    # Add surfaces until we have 13 total (indices 0..12)
    while lde.NumberOfSurfaces < 13:
        lde.InsertNewSurfaceAt(lde.NumberOfSurfaces)

    # -- Aperture --
    apt = system.SystemData.Aperture
    apt.ApertureType = ZOSAPI.SystemData.ZemaxApertureType.EntrancePupilDiameter
    apt.ApertureValue = EPD
    log(f"  Aperture: EPD = {EPD} mm")

    # -- Wavelengths --
    wl = system.SystemData.Wavelengths
    while wl.NumberOfWavelengths > 1:
        wl.RemoveWavelength(wl.NumberOfWavelengths)
    wl.GetWavelength(1).Wavelength = WAVELENGTHS[0][0]
    wl.GetWavelength(1).Weight = WAVELENGTHS[0][1]
    for wv, wt, lb in WAVELENGTHS[1:]:
        wl.AddWavelength(wv, wt)
    log(f"  Wavelengths: F, d, C")

    # -- Fields --
    fld = system.SystemData.Fields
    while fld.NumberOfFields > 1:
        fld.RemoveField(fld.NumberOfFields)
    fld.GetField(1).Y = FIELDS[0][0]
    fld.GetField(1).Weight = FIELDS[0][1]
    for fy, fw, fl in FIELDS[1:]:
        fld.AddField(0.0, fy, fw)
    log(f"  Fields: 0deg, 1.4deg, 2.0deg (half-field)")

    # -- Glass catalog --
    try:
        system.SystemData.MaterialCatalogs.AddCatalog("SCHOTT")
    except Exception:
        pass

    # -- Define all surfaces --
    # fmt: off
    surf_data = [
        # idx  comment                       radius      thick     material    semi-dia
        (0, "Object at infinity",           float('inf'), 1e10,     "",         0.0  ),
        (1, "STOP (Entrance Pupil)",        float('inf'), 0.0,      "",         32.0 ),
        (2, "Obj Crown Front (N-BK7)",      240.0,        14.0,     "N-BK7",    32.0 ),
        (3, "Obj Crown Rear",               -190.0,       0.5,      "",         31.5 ),
        (4, "Obj Flint Front (N-F2)",       -195.0,       9.0,      "N-F2",     31.0 ),
        (5, "Obj Flint Rear",               -600.0,       60.0,     "",         30.5 ),
        (6, "Prism Entrance (N-BK7)",       float('inf'), 53.33,    "N-BK7",    34.0 ),
        (7, "Prism Mid (dummy fold)",       float('inf'), 53.33,    "N-BK7",    34.0 ),
        (8, "Prism Exit (N-BK7 -> air)",     float('inf'), 53.34,    "N-BK7",    34.0 ),
        (9, "Corrector Crown Front (N-BK7)",80.0,         6.0,      "N-BK7",    18.0 ),
        (10,"Corrector Cement (N-F2 on BK7)",-50.0,       4.0,      "N-F2",     17.5 ),
        (11,"Corrector Rear -> Image",       -120.0,       30.0,     "",         17.0 ),
        (12,"IMAGE (Field Stop)",           float('inf'), 0.0,      "",         14.65),
    ]
    # fmt: on

    for idx, comment, radius, thickness, material, semi_dia in surf_data:
        s = lde.GetSurfaceAt(idx)
        s.Comment = comment
        s.Radius = radius
        s.Thickness = thickness
        s.Material = material
        if semi_dia > 0:
            s.SemiDiameter = semi_dia

    # Make surface 1 the STOP
    lde.GetSurfaceAt(1).IsStop = True

    log(f"  Lens built: {len(surf_data)} surfaces")
    log(f"  Objective  : N-BK7 / N-F2 Fraunhofer doublet")
    log(f"  Prism      : {PRISM_MATERIAL} block, {PRISM_PATH_MM} mm glass path")
    log(f"  Corrector  : N-BK7 / N-F2 cemented doublet")
    log(f"  Field stop : dia.{FIELD_STOP_DIAM} mm")


# -- First-order metrics ---------------------------------------

def get_first_order(system: Any) -> dict:
    """Get first-order metrics by evaluating MFE operands."""
    try:
        mfe = system.MFE
        from ZOSAPI.Editors.MFE import MeritOperandType as MOT, MeritColumn

        # Save current MFE state
        saved_ops = mfe.NumberOfOperands

        # Add temporary operands and evaluate
        def eval_op(op_type, **params):
            """Add a singleton operand, calculate, return value, then remove."""
            mfe.InsertRowAt(mfe.NumberOfOperands + 1)
            op = mfe.GetOperandAt(mfe.NumberOfOperands)
            op.ChangeType(op_type)
            # Set parameters via Param columns
            for idx, (pname, pval) in enumerate(params.items(), 1):
                try:
                    col = getattr(MeritColumn, f'Param{idx}')
                    cell = op.GetOperandCell(col)
                    if cell is not None:
                        if isinstance(pval, int):
                            cell.IntegerValue = pval
                        else:
                            cell.DoubleValue = float(pval)
                except Exception:
                    pass
            mfe.CalculateMeritFunction()
            return op.Value

        efl = eval_op(MOT.EFFL, Wave=2)
        epdi = eval_op(MOT.EPDI, Wave=2)
        expd = eval_op(MOT.EXPD, Wave=2)
        isna = eval_op(MOT.ISNA, Wave=2)

        # Compute derived quantities
        efl_val = float(efl) if efl and str(efl) != 'nan' else 0.0
        epd_val = float(epdi) if epdi and str(epdi) != 'nan' else 0.0
        isna_val = float(isna) if isna and str(isna) != 'nan' else 0.0
        expd_val = float(expd) if expd and str(expd) != 'nan' else 0.0

        result = {
            "efl_mm": round(efl_val, 3),
            "epd_mm": round(epd_val, 3),
            "f_number": round(efl_val / epd_val, 3) if epd_val > 0 else None,
            "image_space_na": round(isna_val, 4),
            "exit_pupil_diameter_mm": round(expd_val, 3),
        }

        # Clean up temporary operands (remove all extras beyond saved count)
        while mfe.NumberOfOperands > saved_ops:
            mfe.RemoveOperandAt(mfe.NumberOfOperands)

        return result
    except Exception as e:
        return {"error": str(e)}


# -- Analyses --------------------------------------------------

def export_analyses(system: Any, stage: str) -> dict:
    analysis_dir = OUT_DIR / "analyses" / stage
    analysis_dir.mkdir(parents=True, exist_ok=True)
    exported = {}

    analyses = {
        "spot":            "New_StandardSpot",
        "mtf":             "New_FftMtf",
        "wavefront":       "New_WavefrontMap",
        "rayfan":          "New_RayFan",
        "field_curv_dist": "New_FieldCurvatureAndDistortion",
        "seidel":          "New_SeidelDiagram",
        "prescription":    "New_Prescription",
    }

    for key, factory_name in analyses.items():
        try:
            factory = getattr(system.Analyses, factory_name, None)
            if factory is None:
                continue
            analysis = factory()
            analysis.ApplyAndWaitForCompletion()
            path = str(analysis_dir / f"{key}.txt")
            analysis.GetResults().GetTextFile(path)
            exported[key] = path
            analysis.Close()
        except Exception as e:
            log(f"    {key} analysis: {e}")

    log(f"  Exported {len(exported)} analyses for stage '{stage}'")
    return exported


# -- Merit function --------------------------------------------

def build_merit_function(system: Any, stage: str, MOT: Any) -> None:
    """
    Build the merit function for each optimization stage.
    MOT = MeritOperandType enum from ZOSAPI.
    """
    from ZOSAPI.Editors.MFE import MeritColumn as MC

    mfe = system.MFE

    # Clear all existing operands
    mfe.DeleteAllRows()

    # Param name -> MeritColumn mapping for common operand parameters
    PARAM_MAP = {
        'Wave':  MC.Param1,  'Wave1': MC.Param1, 'Wave2': MC.Param2,
        'Field': MC.Param2,  'Surf':  MC.Param1,  'Surf1': MC.Param1, 'Surf2': MC.Param2,
        'Param3': MC.Param3, 'Param4': MC.Param4,
    }

    def add_op(op_type, target=0.0, weight=1.0, **kwargs):
        """Add one operand row via InsertRowAt + ChangeType + set Target/Weight/Params."""
        try:
            idx = mfe.NumberOfOperands + 1
            mfe.InsertRowAt(idx)
            op = mfe.GetOperandAt(idx)
            op.ChangeType(op_type)
            op.Target = float(target)
            op.Weight = float(weight)
            # Set parameters via MeritColumn
            for prop_name, prop_val in kwargs.items():
                col = PARAM_MAP.get(prop_name)
                if col is not None:
                    try:
                        cell = op.GetOperandCell(col)
                        if cell is not None:
                            if isinstance(prop_val, int):
                                cell.IntegerValue = prop_val
                            else:
                                cell.DoubleValue = float(prop_val)
                    except Exception:
                        pass
        except Exception as e:
            log(f"    MFE add_op({op_type}) failed: {e}")

    log(f"  Building merit function: {stage}")

    # --- Stage-specific operands ---
    if stage == "feasibility":
        add_op(MOT.EFFL, target=EFL_TARGET, weight=1.0, Wave=2)
        add_op(MOT.MNCG, target=1.0, weight=5.0, Surf=2)
        add_op(MOT.MNCG, target=0.8, weight=5.0, Surf=4)
        add_op(MOT.MNCG, target=1.0, weight=5.0, Surf=9)
        add_op(MOT.MNEG, target=0.8, weight=5.0, Surf=10)
        add_op(MOT.MNEA, target=0.2, weight=5.0, Surf=3)
        add_op(MOT.MXCA, target=20.0, weight=1.0, Surf=2)
        add_op(MOT.MXCA, target=10.0, weight=1.0, Surf=9)
        add_op(MOT.TOTR, target=350.0, weight=0.01, Surf1=1, Surf2=12)

    elif stage == "image-quality":
        add_op(MOT.EFFL, target=EFL_TARGET, weight=1.0, Wave=2)
        for fld_num in [1, 2, 3]:
            add_op(MOT.SPHA, target=0.0, weight=0.2, Wave=2, Field=fld_num)
            add_op(MOT.COMA, target=0.0, weight=0.2, Wave=2, Field=fld_num)
            add_op(MOT.ASTI, target=0.0, weight=0.2, Wave=2, Field=fld_num)
        add_op(MOT.AXCL, target=0.0, weight=1.0, Wave1=1, Wave2=3)
        add_op(MOT.LACL, target=0.0, weight=0.5, Wave1=1, Wave2=3, Param3=2)
        add_op(MOT.LACL, target=0.0, weight=0.5, Wave1=1, Wave2=3, Param3=3)
        add_op(MOT.FCUR, target=0.0, weight=0.3, Wave=2, Field=2)
        add_op(MOT.FCUR, target=0.0, weight=0.3, Wave=2, Field=3)
        add_op(MOT.DIST, target=0.0, weight=0.1, Wave=2, Field=3)

    elif stage == "field-balance":
        add_op(MOT.EFFL, target=EFL_TARGET, weight=1.0, Wave=2)
        add_op(MOT.DIST, target=0.0, weight=0.5, Wave=2, Field=2)
        add_op(MOT.DIST, target=0.0, weight=0.5, Wave=2, Field=3)
        for fld_num in [1, 2, 3]:
            add_op(MOT.FCUR, target=0.0, weight=0.4, Wave=2, Field=fld_num)
            add_op(MOT.ASTI, target=0.0, weight=0.3, Wave=2, Field=fld_num)
        add_op(MOT.AXCL, target=0.0, weight=0.5, Wave1=1, Wave2=3)

    elif stage == "manufacturability":
        add_op(MOT.EFFL, target=EFL_TARGET, weight=1.0, Wave=2)
        add_op(MOT.MNEG, target=2.0, weight=3.0, Surf=2)
        add_op(MOT.MNEG, target=1.5, weight=3.0, Surf=4)
        add_op(MOT.MNEG, target=1.5, weight=3.0, Surf=9)
        add_op(MOT.MNEG, target=1.0, weight=3.0, Surf=10)
        add_op(MOT.MNCG, target=1.0, weight=3.0, Surf=2)
        add_op(MOT.MNCG, target=0.8, weight=3.0, Surf=4)
        for si in [2, 3, 4, 5, 9, 10, 11]:
            add_op(MOT.MNSD, target=0.0, weight=0.1, Surf=si)
        for si in [2, 3, 4, 5]:
            add_op(MOT.RAID, target=0.0, weight=0.01, Surf=si)

    # --- Add default merit function (spot radius) via the optimization wizard ---
    try:
        wiz = mfe.SEQOptimizationWizard
        wiz.IsAssumeAxialSymmetryUsed = False
        wiz.IsIgnoreLateralColorUsed = False
        wiz.IsDeleteVignetteUsed = True
        wiz.Type = 0          # 0 = RMS spot radius
        wiz.OverallWeight = 1.0
        wiz.Ring = 3
        wiz.Grid = 0          # Gaussian quadrature
        wiz.Arm = 2
        wiz.Reference = 0     # Centroid
        wiz.StartAt = mfe.NumberOfOperands + 1
        wiz.OK()
        log("    Added default merit function (RMS spot, centroid ref)")
    except Exception as e:
        log(f"    Default merit function wizard: {e}")

    log(f"  Merit function '{stage}' ready ({mfe.NumberOfOperands} operands)")


# -- Variables -------------------------------------------------

def configure_variables(system: Any, stage: str) -> None:
    lde = system.LDE
    log(f"  Variables for: {stage}")

    # Always: image distance
    try:
        lde.GetSurfaceAt(11).ThicknessCell.MakeSolveVariable()
    except Exception:
        pass

    radius_surfs = [2, 3, 4, 5, 9, 10, 11]
    thick_surfs = [2, 3, 4, 5, 9, 10]

    for si in radius_surfs:
        try:
            lde.GetSurfaceAt(si).RadiusCell.MakeSolveVariable()
        except Exception:
            pass

    for si in thick_surfs:
        try:
            lde.GetSurfaceAt(si).ThicknessCell.MakeSolveVariable()
        except Exception:
            pass

    log(f"    {len(radius_surfs)} radii + {len(thick_surfs)} thicknesses variable")


# -- Optimization ----------------------------------------------

def optimize(system: Any, stage: str) -> float | None:
    log(f"  Running optimization ({stage})...")
    tool = system.Tools.OpenLocalOptimization()
    merit = None
    try:
        tool.NumberOfCycles = 0  # automatic
        tool.RunAndWaitForCompletion()
        try:
            merit = float(tool.FinalMeritFunctionValue)
        except Exception:
            pass
        log(f"  Merit function value: {merit}")
    except Exception as e:
        log(f"  Optimization error: {e}")
    finally:
        tool.Close()
    return merit


def save_lens(system: Any, stage: str) -> str:
    path = str(OUT_DIR / f"telescope_12x60_{stage}.zmx")
    system.SaveAs(path)
    log(f"  Lens saved: {path}")
    return path


def save_json(data: dict, name: str) -> Path:
    path = OUT_DIR / f"{name}.json"
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    return path


# -- Main ------------------------------------------------------

def main():
    log("=" * 70)
    log("12x60 Terrestrial Telescope -- Automated Zemax Optical Design")
    log("=" * 70)
    log(f"Output:      {OUT_DIR}")
    log(f"Target EFL:  {EFL_TARGET} mm")
    log(f"EPD:          {EPD} mm (f/{EFL_TARGET/EPD:.1f})")
    log(f"Half FOV:    {HALF_FOV_DEG}deg")
    log(f"Prism:       {PRISM_MATERIAL}, {PRISM_PATH_MM} mm glass path")
    log(f"Field stop:  dia {FIELD_STOP_DIAM} mm")
    log("")

    # -- 1. Connect --
    log("> Step 1: Connecting to OpticStudio...")
    app, system, ZOSAPI, MeritOpType = connect_interactive()
    log("  Connected (Interactive Extension).")
    log("")

    # -- 2. Build --
    log("> Step 2: Building telescope model...")
    build_telescope(system, ZOSAPI)
    log("")

    # -- 3. Baseline --
    log("> Step 3: Baseline evaluation...")
    baseline = get_first_order(system)
    log(f"  Baseline: {json.dumps(baseline, indent=2)}")
    save_json(baseline, "baseline_first_order")
    export_analyses(system, "baseline")
    save_lens(system, "baseline")
    log("")

    # -- 4. Staged optimization --
    stages = ["feasibility", "image-quality", "field-balance", "manufacturability"]
    stage_results = []

    for i, stage in enumerate(stages, 1):
        log(f"> Step 4.{i}: Stage '{stage}'")
        log("-" * 50)

        configure_variables(system, stage)
        build_merit_function(system, stage, MeritOpType)
        merit = optimize(system, stage)

        fo = get_first_order(system)
        log(f"  First-order after {stage}: {json.dumps(fo, indent=2)}")

        export_analyses(system, stage)
        lens_path = save_lens(system, stage)

        sr = {"stage": stage, "merit": merit, "first_order": fo, "lens": lens_path}
        stage_results.append(sr)
        save_json(sr, f"stage_{stage}")
        log("")

    # -- 5. Final --
    log("> Step 5: Final evaluation")
    log("=" * 50)
    final = get_first_order(system)
    efl_error = abs(final.get("efl_mm", 0) - EFL_TARGET)

    log(f"  EFL:      {final.get('efl_mm')} mm  (target {EFL_TARGET}, delta={efl_error:.3f})")
    log(f"  F/#:      {final.get('image_space_f_number')}")
    log(f"  BFL:      {final.get('bfl_mm')} mm")
    log(f"  EPD:      {final.get('epd_mm')} mm")
    log(f"  Exit PD:  {final.get('exit_pupil_diameter_mm')} mm")
    log(f"  Track:    {final.get('total_track_mm')} mm")

    export_analyses(system, "final")
    final_path = save_lens(system, "final")

    # Copy to convenient location
    convenience = PROJECT_DIR / "designs" / "telescope_12x60_final.zmx"
    convenience.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(final_path, convenience)
    log(f"\n  Convenience copy: {convenience}")

    # -- Summary --
    summary = {
        "design": "12x60 Terrestrial Telescope",
        "timestamp": TIMESTAMP,
        "targets": {
            "efl_mm": EFL_TARGET,
            "epd_mm": EPD,
            "f_number": round(EFL_TARGET / EPD, 1),
            "half_fov_deg": HALF_FOV_DEG,
            "true_fov_deg": 2 * HALF_FOV_DEG,
            "magnification": MAGNIFICATION,
            "exit_pupil_diameter_mm": EXIT_PUPIL_DIAM,
            "field_stop_diameter_mm": FIELD_STOP_DIAM,
        },
        "final_first_order": final,
        "efl_error_mm": round(efl_error, 3),
        "stages": stage_results,
        "final_lens": final_path,
        "optical_train": {
            "objective": "N-BK7 / N-F2 air-spaced Fraunhofer doublet, 60mm CA",
            "prism_erector": f"Porro Type-I, {PRISM_MATERIAL} equivalent block ({PRISM_PATH_MM}mm glass)",
            "field_corrector": "N-BK7 / N-F2 cemented doublet near image plane",
            "field_stop": f"D{FIELD_STOP_DIAM}mm intermediate image plane",
            "eyepiece": "Erfle 35mm EFL, f/7, 48deg apparent FOV (separate design)",
        },
    }
    save_json(summary, "design_summary")

    log("")
    log("=" * 70)
    log("DESIGN COMPLETE")
    log(f"  Final lens:    {final_path}")
    log(f"  All outputs:   {OUT_DIR}")
    log(f"  Quick access:  {convenience}")
    log("=" * 70)


if __name__ == "__main__":
    main()
