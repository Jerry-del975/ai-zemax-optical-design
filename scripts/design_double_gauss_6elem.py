"""
6-Element Double Gauss 50mm F/2.8 -- Automated Zemax Optical Design
====================================================================
Classic 6-element symmetric double Gauss (Biogon/Planar type):
BK7(pos) + SF5(neg) + SF5(neg) + STOP + SF5(neg) + SF5(neg) + BK7(pos)

EFL: 50mm, F/2.8, +/-25deg field
Targets: MTF>=0.6@30lp/mm, distortion<=1.5%, total track<=70mm
Center thickness >=2mm, Edge thickness >=1.5mm
"""

from __future__ import annotations

import json, os, shutil, sys
from datetime import datetime
from pathlib import Path
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_DIR = SCRIPT_DIR.parent
TIMESTAMP = datetime.now().strftime("%Y%m%d_%H%M%S")
OUT_DIR = PROJECT_DIR / "designs" / f"double_gauss_6elem_{TIMESTAMP}"
OUT_DIR.mkdir(parents=True, exist_ok=True)

ZOS_ROOT = r"D:\Program Files\Ansys Zemax OpticStudio 2024 R1.00"

EFL_TARGET       = 50.0
F_NUMBER         = 2.8
HALF_FOV_DEG     = 25.0
EPD              = EFL_TARGET / F_NUMBER  # 17.857mm
TOTAL_TRACK_MAX  = 70.0
MIN_CT_MM        = 2.0
MIN_ET_MM        = 1.5
MTF_FREQ         = 30.0
MTF_MIN          = 0.6
DIST_MAX_PCT     = 1.5
GLASS_CATALOG    = "SCHOTT"

WAVELENGTHS = [
    (0.48613270, 1.0, "F"),
    (0.58756180, 1.0, "d"),
    (0.65627250, 1.0, "C"),
]
FIELDS = [
    (0.0,  1.0, "on-axis"),
    (17.5, 1.0, "0.7-field"),
    (25.0, 1.0, "full-field"),
]

# 15 surfaces (0..14): OBJ + 12 powered surfaces + STOP + IMAGE
# 0=OBJ, 1..6=front triplet, 7=STOP, 8..13=rear triplet, 14=IMAGE
NUM_SURFACES = 15

def log(msg: str) -> None:
    ts = datetime.now().strftime("%H:%M:%S")
    line = f"[{ts}] {msg}"
    print(line, flush=True)
    with (OUT_DIR / "design-log.txt").open("a", encoding="utf-8") as f:
        f.write(line + "\n")

def connect_interactive():
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
    if app is None or not app.IsValidLicenseForAPI or app.PrimarySystem is None:
        raise RuntimeError("Connection failed.")
    system = app.PrimarySystem
    mfe = system.MFE
    op = mfe.GetOperandAt(1)
    MeritOpType = type(op.Type)
    return app, system, ZOSAPI, MeritOpType


def build_6elem_double_gauss(system, ZOSAPI):
    """Build 6-element symmetric double Gauss.

    Surface layout (0-indexed):
      0: OBJ at infinity
      Front triplet (positive + negative + negative):
      1: BK7_1 front  -- positive meniscus, convex toward image (R>0, strong)
      2: BK7_1 rear = SF5_1 front (cemented)
      3: SF5_1 rear
      4: SF5_2 front
      5: SF5_2 rear (faces stop, concave)
      6: air gap to stop
      7: STOP (in air between triplets)
      Rear triplet (negative + negative + positive, symmetric):
      8: air gap from stop
      9: SF5_3 front (faces stop)
      10: SF5_3 rear
      11: SF5_4 front
      12: SF5_4 rear = BK7_2 front (cemented)
      13: BK7_2 rear -- positive meniscus, convex toward image (R<0)
      14: IMAGE
    """
    log("Building 6-element double Gauss 50mm F/2.8 lens model...")
    lde = system.LDE
    system.New(False)
    while lde.NumberOfSurfaces < NUM_SURFACES:
        lde.InsertNewSurfaceAt(lde.NumberOfSurfaces)

    # Aperture: EPD
    apt = system.SystemData.Aperture
    apt.ApertureType = ZOSAPI.SystemData.ZemaxApertureType.EntrancePupilDiameter
    apt.ApertureValue = EPD
    log(f"  Aperture: EPD = {EPD:.3f} mm")

    # Wavelengths
    wl = system.SystemData.Wavelengths
    while wl.NumberOfWavelengths > 1:
        wl.RemoveWavelength(wl.NumberOfWavelengths)
    wl.GetWavelength(1).Wavelength = WAVELENGTHS[0][0]
    wl.GetWavelength(1).Weight = WAVELENGTHS[0][1]
    for wv, wt, _ in WAVELENGTHS[1:]:
        wl.AddWavelength(wv, wt)
    log("  Wavelengths: F, d, C")

    # Fields
    fld = system.SystemData.Fields
    while fld.NumberOfFields > 1:
        fld.RemoveField(fld.NumberOfFields)
    fld.GetField(1).Y = FIELDS[0][0]
    fld.GetField(1).Weight = FIELDS[0][1]
    for fy, fw, _ in FIELDS[1:]:
        fld.AddField(0.0, fy, fw)
    log(f"  Fields: 0, {FIELDS[1][0]}, {FIELDS[2][0]} deg")

    # Glass catalog
    try:
        system.SystemData.MaterialCatalogs.AddCatalog(GLASS_CATALOG)
    except Exception:
        pass

    # -- Starting prescription (6-element double Gauss) --
    # Based on classic Double Gauss / Planar-type scaling
    # Front triplet: BK7(meniscus, convex→img) + SF5(meniscus) + SF5(meniscus)
    #   BK7: R1<R2 (R>0) → positive power
    #   SF5_1: R3<R4 (R>0) → negative power (concave toward stop)
    #   SF5_2: R5<R6 (R>0) → negative power (stronger concave toward stop)
    # Rear triplet: symmetric with signs flipped

    # Balanced prescription: strong BK7 + weak SF5 = positive net triplet
    # EFL should start around 80-90mm (positive!), optimizer tightens to 50mm
    Rf1 = 17.0   # BK7_1 front, strong positive
    Rf2 = 80.0   # BK7_1 = SF5_1 (cemented interface)
    Rf3 = 40.0   # SF5_1 rear (weak = small curvature diff from Rf2)
    Rf4 = 40.0   # SF5_2 front (match SF5_1 rear)
    Rf5 = 25.0   # SF5_2 rear (medium toward stop)

    Rr1 = -25.0  # SF5_3 front (symmetric)
    Rr2 = -40.0  # SF5_3 rear
    Rr3 = -40.0  # SF5_4 front
    Rr4 = -80.0  # SF5_4 = BK7_2 (cemented)
    Rr5 = -17.0  # BK7_2 rear, strong positive

    # Thicknesses (patent-style distribution)
    sd_big = 22.0
    sd_mid = 16.0
    sd_stp = 11.0

    surf_data = [
        (0,  "OBJ",                 1e10,        1e10,   "",        0.0),
        # Front triplet
        (1,  "BK7_1 front",         Rf1,         6.0,    "N-BK7",   sd_big),
        (2,  "BK7_1=SF5_1 (cem)",   Rf2,         3.5,    "N-SF5",   sd_big-1),
        (3,  "SF5_1 rear",          Rf3,         0.2,    "",        sd_mid),
        (4,  "SF5_2 front",         Rf4,         3.0,    "N-SF5",   sd_mid-1),
        (5,  "SF5_2 rear→stop",     Rf5,         6.8,    "",        sd_mid-2),
        (6,  "air pre-STOP",        1e10,        0.0,    "",        sd_stp),
        (7,  "STOP",                1e10,        6.8,    "",        sd_stp),
        (8,  "air post-STOP",       1e10,        0.0,    "",        sd_stp),
        # Rear triplet
        (9,  "SF5_3 front",         Rr1,         3.0,    "N-SF5",   sd_mid-2),
        (10, "SF5_3 rear",          Rr2,         0.2,    "",        sd_mid-1),
        (11, "SF5_4 front",         Rr3,         3.5,    "N-SF5",   sd_mid),
        (12, "SF5_4=BK7_2 (cem)",   Rr4,         6.0,    "N-BK7",   sd_big-1),
        (13, "BK7_2 rear→IMAGE",    Rr5,         33.0,   "",        sd_big),
        (14, "IMAGE",               1e10,        0.0,    "",        23.5),
    ]

    for idx, comment, radius, thickness, material, semi_dia in surf_data:
        s = lde.GetSurfaceAt(idx)
        s.Comment = comment
        s.Radius = radius
        s.Thickness = thickness
        s.Material = material
        if semi_dia > 0:
            s.SemiDiameter = semi_dia

    # STOP at surface 7
    lde.GetSurfaceAt(7).IsStop = True

    # Compute total track (surf1 → image)
    track = 0
    for si in range(1, 14):  # surfaces 1..13 thicknesses
        track += lde.GetSurfaceAt(si).Thickness
    log(f"  Lens built: 15 surfaces (6 elements + STOP)")
    log(f"  Front: N-BK7 / N-SF5 / N-SF5  (pos+neg+neg meniscus triplet)")
    log(f"  Rear:  N-SF5 / N-SF5 / N-BK7  (neg+neg+pos meniscus triplet)")
    log(f"  Total track: {track:.1f} mm (limit: {TOTAL_TRACK_MAX} mm)")


def get_first_order(system, MOT):
    try:
        mfe = system.MFE
        saved = mfe.NumberOfOperands
        def eval_op(op_type, **params):
            mfe.InsertRowAt(mfe.NumberOfOperands + 1)
            op = mfe.GetOperandAt(mfe.NumberOfOperands)
            op.ChangeType(op_type)
            for idx, (_, pval) in enumerate(params.items(), 1):
                try:
                    from ZOSAPI.Editors.MFE import MeritColumn
                    col = getattr(MeritColumn, f'Param{idx}')
                    cell = op.GetOperandCell(col)
                    if cell is not None:
                        if isinstance(pval, int): cell.IntegerValue = pval
                        else: cell.DoubleValue = float(pval)
                except Exception: pass
            mfe.CalculateMeritFunction()
            return op.Value

        efl = eval_op(MOT.EFFL, Wave=2)
        epdi = eval_op(MOT.EPDI, Wave=2)
        totr = eval_op(MOT.TOTR, Surf1=2, Surf2=15)
        isna = eval_op(MOT.ISNA, Wave=2)

        result = {
            "efl_mm": round(float(efl) if efl else 0, 3),
            "epd_mm": round(float(epdi) if epdi else 0, 3),
            "f_number": round(float(efl)/float(epdi), 3) if efl and epdi and float(epdi)>0 else None,
            "image_space_na": round(float(isna), 4) if isna else None,
            "total_track_mm": round(float(totr), 3) if totr else None,
        }
        while mfe.NumberOfOperands > saved:
            mfe.RemoveOperandAt(mfe.NumberOfOperands)
        return result
    except Exception as e:
        return {"error": str(e)}


def export_analyses(system, stage):
    ad = OUT_DIR / "analyses" / stage
    ad.mkdir(parents=True, exist_ok=True)
    exported = {}
    analyses = {
        "spot": "New_StandardSpot", "mtf": "New_FftMtf",
        "wavefront": "New_WavefrontMap", "rayfan": "New_RayFan",
        "field_curv_dist": "New_FieldCurvatureAndDistortion",
        "seidel": "New_SeidelDiagram", "prescription": "New_Prescription",
    }
    for key, fn in analyses.items():
        try:
            factory = getattr(system.Analyses, fn, None)
            if factory is None: continue
            a = factory()
            a.ApplyAndWaitForCompletion()
            path = str(ad / f"{key}.txt")
            a.GetResults().GetTextFile(path)
            exported[key] = path
            a.Close()
        except Exception as e:
            log(f"    {key}: {e}")
    log(f"  Exported {len(exported)} analyses for '{stage}'")
    return exported


def build_merit_function(system, stage, MOT):
    from ZOSAPI.Editors.MFE import MeritColumn as MC
    mfe = system.MFE
    mfe.DeleteAllRows()

    PM = {
        'Wave':MC.Param1, 'Wave1':MC.Param1, 'Wave2':MC.Param2,
        'Field':MC.Param2, 'Surf':MC.Param1, 'Surf1':MC.Param1,
        'Surf2':MC.Param2, 'Param1':MC.Param1, 'Param2':MC.Param2,
        'Param3':MC.Param3, 'Param4':MC.Param4,
    }
    def add_op(op_type, target=0.0, weight=1.0, **kw):
        try:
            idx = mfe.NumberOfOperands + 1
            mfe.InsertRowAt(idx)
            op = mfe.GetOperandAt(idx)
            op.ChangeType(op_type)
            op.Target = float(target)
            op.Weight = float(weight)
            for pn, pv in kw.items():
                col = PM.get(pn)
                if col:
                    try:
                        cell = op.GetOperandCell(col)
                        if cell is not None:
                            if isinstance(pv, int): cell.IntegerValue = pv
                            else: cell.DoubleValue = float(pv)
                    except Exception: pass
        except Exception as e:
            pass  # silently skip failed operands

    log(f"  Building merit function: {stage}")

    # Surfaces with glass: 1(BK7), 2-3(SF5), 4-5(SF5), 9-10(SF5), 11-12(SF5), 13(BK7)
    # STOP at surface 7
    glass_surfs = [1, 2, 4, 9, 11, 13]
    edge_surfs  = [2, 3, 5, 10, 12, 13]  # last surfaces of each element for edge thickness
    all_surfs   = list(range(1, 14))

    if stage == "feasibility":
        add_op(MOT.EFFL, target=EFL_TARGET, weight=10.0, Wave=2)
        add_op(MOT.TOTR, target=TOTAL_TRACK_MAX, weight=3.0, Surf1=2, Surf2=15)
        for si in glass_surfs:
            add_op(MOT.MNCG, target=MIN_CT_MM, weight=5.0, Surf=si)
        for si in edge_surfs:
            add_op(MOT.MNEG, target=MIN_ET_MM, weight=3.0, Surf=si)
        for si in [3, 5, 6, 8, 10]:  # air gaps
            add_op(MOT.MNEA, target=0.1, weight=10.0, Surf=si)

    elif stage == "image-quality":
        add_op(MOT.EFFL, target=EFL_TARGET, weight=5.0, Wave=2)
        add_op(MOT.TOTR, target=TOTAL_TRACK_MAX, weight=3.0, Surf1=2, Surf2=15)
        for fld in [1, 2, 3]:
            add_op(MOT.SPHA, target=0.0, weight=0.5, Wave=2, Field=fld)
            add_op(MOT.COMA, target=0.0, weight=0.5, Wave=2, Field=fld)
            add_op(MOT.ASTI, target=0.0, weight=0.5, Wave=2, Field=fld)
        add_op(MOT.AXCL, target=0.0, weight=2.0, Wave1=1, Wave2=3)
        add_op(MOT.LACL, target=0.0, weight=1.0, Wave1=1, Wave2=3, Param3=2)
        add_op(MOT.LACL, target=0.0, weight=1.0, Wave1=1, Wave2=3, Param3=3)
        add_op(MOT.FCUR, target=0.0, weight=0.5, Wave=2, Field=2)
        add_op(MOT.FCUR, target=0.0, weight=0.5, Wave=2, Field=3)
        add_op(MOT.DIST, target=0.0, weight=0.5, Wave=2, Field=3)
        for si in glass_surfs:
            add_op(MOT.MNCG, target=MIN_CT_MM, weight=3.0, Surf=si)

    elif stage == "field-balance":
        add_op(MOT.EFFL, target=EFL_TARGET, weight=5.0, Wave=2)
        add_op(MOT.TOTR, target=TOTAL_TRACK_MAX, weight=3.0, Surf1=2, Surf2=15)
        add_op(MOT.DIST, target=0.0, weight=2.0, Wave=2, Field=2)
        add_op(MOT.DIST, target=0.0, weight=2.0, Wave=2, Field=3)
        for fld in [1, 2, 3]:
            add_op(MOT.FCUR, target=0.0, weight=0.8, Wave=2, Field=fld)
            add_op(MOT.ASTI, target=0.0, weight=0.8, Wave=2, Field=fld)
        add_op(MOT.AXCL, target=0.0, weight=1.5, Wave1=1, Wave2=3)
        add_op(MOT.LACL, target=0.0, weight=1.0, Wave1=1, Wave2=3, Param3=2)
        add_op(MOT.LACL, target=0.0, weight=1.0, Wave1=1, Wave2=3, Param3=3)
        for fld in [1, 2, 3]:
            add_op(MOT.MTFT, target=MTF_MIN, weight=1.0, Param1=MTF_FREQ, Param2=2, Param3=fld)
            add_op(MOT.MTFS, target=MTF_MIN, weight=1.0, Param1=MTF_FREQ, Param2=2, Param3=fld)
        for si in glass_surfs:
            add_op(MOT.MNCG, target=MIN_CT_MM, weight=3.0, Surf=si)
        for si in edge_surfs:
            add_op(MOT.MNEG, target=MIN_ET_MM, weight=2.0, Surf=si)

    elif stage == "manufacturability":
        add_op(MOT.EFFL, target=EFL_TARGET, weight=5.0, Wave=2)
        add_op(MOT.TOTR, target=TOTAL_TRACK_MAX, weight=5.0, Surf1=2, Surf2=15)
        for si in edge_surfs:
            add_op(MOT.MNEG, target=MIN_ET_MM, weight=5.0, Surf=si)
        for si in glass_surfs:
            add_op(MOT.MNCG, target=MIN_CT_MM, weight=5.0, Surf=si)
        for si in [3, 5, 6, 8, 10]:
            add_op(MOT.MNEA, target=0.2, weight=5.0, Surf=si)
        add_op(MOT.DIST, target=0.0, weight=0.5, Wave=2, Field=3)

    # Default merit function
    wiz_wt = 0.05 if stage == "feasibility" else (0.3 if stage == "image-quality" else 0.1)
    try:
        wiz = mfe.SEQOptimizationWizard
        wiz.IsAssumeAxialSymmetryUsed = False
        wiz.IsIgnoreLateralColorUsed = False
        wiz.IsDeleteVignetteUsed = True
        wiz.Type = 0          # RMS spot
        wiz.OverallWeight = wiz_wt
        wiz.Ring = 3
        wiz.Grid = 0
        wiz.Arm = 2
        wiz.Reference = 0     # Centroid
        wiz.StartAt = mfe.NumberOfOperands + 1
        wiz.OK()
        log(f"    Default merit: RMS spot, wiz_wt={wiz_wt}")
    except Exception as e:
        log(f"    Wizard error: {e}")

    log(f"  Merit function '{stage}': {mfe.NumberOfOperands} operands")


def configure_variables(system, stage):
    lde = system.LDE
    log(f"  Variables: {stage}")

    # BFD (surface 13 → IMAGE, API index 13) always variable
    try: lde.GetSurfaceAt(13).ThicknessCell.MakeSolveVariable()
    except Exception: pass

    # Powered surfaces (1-5, 9-13) — 10 radii
    radius_surfs = [1, 2, 3, 4, 5, 9, 10, 11, 12, 13]
    # Air gap surfaces
    air_gaps = [3, 5, 6, 8, 10]
    # All lens thicknesses (glass element center thicknesses + air gaps)
    all_thicks = [1, 2, 3, 4, 5, 6, 8, 9, 10, 11, 12, 13]

    if stage == "feasibility":
        for si in air_gaps:
            try: lde.GetSurfaceAt(si).ThicknessCell.MakeSolveVariable()
            except Exception: pass
        log("    Air gaps only")

    elif stage == "image-quality":
        for si in radius_surfs:
            try: lde.GetSurfaceAt(si).RadiusCell.MakeSolveVariable()
            except Exception: pass
        for si in air_gaps:
            try: lde.GetSurfaceAt(si).ThicknessCell.MakeSolveVariable()
            except Exception: pass
        log(f"    {len(radius_surfs)} radii + air gaps")

    elif stage in ("field-balance", "manufacturability"):
        for si in radius_surfs:
            try: lde.GetSurfaceAt(si).RadiusCell.MakeSolveVariable()
            except Exception: pass
        for si in all_thicks:
            try: lde.GetSurfaceAt(si).ThicknessCell.MakeSolveVariable()
            except Exception: pass
        log(f"    {len(radius_surfs)} radii + {len(all_thicks)} thicknesses")


def optimize(system, stage):
    log(f"  Running optimization ({stage})...")
    merit = None

    # Use global optimization for image-quality to escape local minima
    if stage == "image-quality":
        try:
            tool = system.Tools.OpenGlobalOptimization()
            log("    Using Global Optimization (DLS with Hammer)...")
            tool.NumberOfCores = 4
            tool.RunAndWaitForCompletion()
            try: merit = float(tool.FinalMeritFunctionValue)
            except Exception: pass
            tool.Close()
        except Exception as e:
            log(f"    Global opt error: {e}, falling back to local")
            tool = system.Tools.OpenLocalOptimization()
            try:
                tool.NumberOfCycles = 0
                tool.RunAndWaitForCompletion()
                try: merit = float(tool.FinalMeritFunctionValue)
                except Exception: pass
            finally:
                tool.Close()
    else:
        tool = system.Tools.OpenLocalOptimization()
        try:
            tool.NumberOfCycles = 0  # automatic
            tool.RunAndWaitForCompletion()
            try: merit = float(tool.FinalMeritFunctionValue)
            except Exception: pass
        except Exception as e:
            log(f"  Optimization error: {e}")
        finally:
            tool.Close()

    log(f"  Merit value: {merit}")
    return merit


def save_lens(system, stage):
    path = str(OUT_DIR / f"dg6_{stage}.zmx")
    system.SaveAs(path)
    log(f"  Saved: {path}")
    return path


def save_json(data, name):
    path = OUT_DIR / f"{name}.json"
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    return path


def main():
    log("=" * 70)
    log("6-Element Double Gauss 50mm F/2.8 -- Automated Zemax Design")
    log("=" * 70)
    log(f"Output:      {OUT_DIR}")
    log(f"Target EFL:  {EFL_TARGET}mm, F/{F_NUMBER}, EPD={EPD:.3f}mm")
    log(f"FOV:         +/-{HALF_FOV_DEG}deg ({2*HALF_FOV_DEG}deg full)")
    log(f"Structure:   BK7/SF5/SF5 | STOP | SF5/SF5/BK7 (6-element)")
    log(f"MTF target:  >= {MTF_MIN} @ {MTF_FREQ}lp/mm")
    log(f"Distortion:  <= {DIST_MAX_PCT}%")
    log(f"Total track: <= {TOTAL_TRACK_MAX}mm")
    log("")

    # 1. Connect
    log("> Step 1: Connect...")
    app, system, ZOSAPI, MeritOpType = connect_interactive()
    log("  Connected (Interactive Extension).")
    log("")

    # 2. Build
    log("> Step 2: Build 6-element double Gauss...")
    build_6elem_double_gauss(system, ZOSAPI)
    log("")

    # 3. Baseline
    log("> Step 3: Baseline...")
    baseline = get_first_order(system, MeritOpType)
    log(f"  Baseline: {json.dumps(baseline, indent=2)}")
    save_json(baseline, "baseline_first_order")
    export_analyses(system, "baseline")
    save_lens(system, "baseline")
    log("")

    # 4. Staged optimization
    stages = ["feasibility", "image-quality", "field-balance", "manufacturability"]
    results = []
    for i, stage in enumerate(stages, 1):
        log(f"> Step 4.{i}: Stage '{stage}'")
        log("-" * 50)
        configure_variables(system, stage)
        build_merit_function(system, stage, MeritOpType)
        merit = optimize(system, stage)
        fo = get_first_order(system, MeritOpType)
        log(f"  First-order: {json.dumps(fo, indent=2)}")
        export_analyses(system, stage)
        lp = save_lens(system, stage)
        results.append({"stage": stage, "merit": merit, "first_order": fo, "lens": lp})
        save_json(results[-1], f"stage_{stage}")
        log("")

    # 5. Final
    log("> Step 5: Final evaluation")
    log("=" * 50)
    final = get_first_order(system, MeritOpType)
    efl_err = abs(final.get("efl_mm", 0) - EFL_TARGET)
    efl_err_pct = (efl_err / EFL_TARGET) * 100
    log(f"  EFL:       {final.get('efl_mm')} mm (target {EFL_TARGET}, err={efl_err:.3f}mm / {efl_err_pct:.2f}%)")
    log(f"  F/#:       {final.get('f_number')}")
    log(f"  EPD:       {final.get('epd_mm')} mm")
    log(f"  Track:     {final.get('total_track_mm')} mm")
    log(f"  NA:        {final.get('image_space_na')}")

    export_analyses(system, "final")
    final_path = save_lens(system, "final")
    convenience = PROJECT_DIR / "designs" / "double_gauss_6elem_final.zmx"
    convenience.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(final_path, convenience)

    summary = {
        "design": "6-Element Double Gauss 50mm F/2.8",
        "timestamp": TIMESTAMP,
        "targets": {
            "efl_mm": EFL_TARGET, "f_number": F_NUMBER,
            "epd_mm": round(EPD, 3), "half_fov_deg": HALF_FOV_DEG,
            "full_fov_deg": 2*HALF_FOV_DEG, "mtf_min": MTF_MIN,
            "mtf_freq_lp_per_mm": MTF_FREQ, "dist_max_pct": DIST_MAX_PCT,
            "total_track_max_mm": TOTAL_TRACK_MAX,
            "min_ct_mm": MIN_CT_MM, "min_et_mm": MIN_ET_MM,
        },
        "final_first_order": final,
        "efl_error_mm": round(efl_err, 3),
        "efl_error_pct": round(efl_err_pct, 2),
        "stages": results,
        "final_lens": final_path,
        "optical_train": {
            "structure": "Symmetric 6-Element Double Gauss",
            "front_triplet": "N-BK7 (pos meniscus) + N-SF5 (neg meniscus) + N-SF5 (neg meniscus)",
            "stop": "Central aperture in air gap",
            "rear_triplet": "N-SF5 (neg) + N-SF5 (neg) + N-BK7 (pos meniscus)",
            "catalog": "SCHOTT",
            "cemented_pairs": "BK7/SF5 in each triplet (surfaces 2 and 12)",
        },
    }
    save_json(summary, "design_summary")

    log("")
    log("=" * 70)
    log("DESIGN COMPLETE")
    log(f"  Final lens:   {final_path}")
    log(f"  All outputs:  {OUT_DIR}")
    log(f"  Quick access: {convenience}")
    log(f"  EFL error:    {efl_err:.3f}mm ({efl_err_pct:.2f}%)")
    log("=" * 70)


if __name__ == "__main__":
    main()
