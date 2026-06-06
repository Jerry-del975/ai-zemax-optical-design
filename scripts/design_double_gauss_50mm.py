"""
Double Gauss 50mm F/2.8 -- Automated Zemax Optical Design
=========================================================
Structure: BK7(positive) + SF5(negative) + STOP + SF5(negative) + BK7(positive)
Symmetric double Gauss for high-end photography
EFL: 50mm, F/2.8, +/-25deg field
Targets: MTF>=0.6@30lp/mm, distortion<=1.5%, total track<=70mm

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
OUT_DIR = PROJECT_DIR / "designs" / f"double_gauss_50mm_{TIMESTAMP}"
OUT_DIR.mkdir(parents=True, exist_ok=True)

ZOS_ROOT = r"D:\Program Files\Ansys Zemax OpticStudio 2024 R1.00"

# -- Design parameters -----------------------------------------
EFL_TARGET       = 50.0    # mm
F_NUMBER         = 2.8
HALF_FOV_DEG     = 25.0    # half-field (+/-25deg full field)
EPD              = EFL_TARGET / F_NUMBER  # 17.857 mm
TOTAL_TRACK_MAX  = 70.0    # mm
MIN_CT_MM        = 2.0     # min center thickness
MIN_ET_MM        = 1.5     # min edge thickness
MTF_FREQ         = 30.0    # lp/mm
MTF_MIN          = 0.6
DIST_MAX_PCT     = 1.5

# Glass catalog
GLASS_CATALOG = "SCHOTT"

WAVELENGTHS = [
    (0.48613270, 1.0, "F"),
    (0.58756180, 1.0, "d"),
    (0.65627250, 1.0, "C"),
]

FIELDS = [
    (0.0,  1.0, "on-axis"),
    (17.5, 1.0, "0.7-field"),   # 0.7 * 25deg
    (25.0, 1.0, "full-field"),
]

# Surface indices (0-based in API, 1-based in UI)
# 0=OBJ, 1=BK7_front, 2=BK7_rear, 3=SF5_rear, 4=STOP,
# 5=SF5_front, 6=SF5_rear, 7=BK7_front, 8=BK7_rear, 9=IMAGE
NUM_SURFACES = 10  # indices 0..9

# -- Helpers ---------------------------------------------------

def log(msg: str) -> None:
    ts = datetime.now().strftime("%H:%M:%S")
    line = f"[{ts}] {msg}"
    print(line, flush=True)
    with (OUT_DIR / "design-log.txt").open("a", encoding="utf-8") as f:
        f.write(line + "\n")


def connect_interactive() -> tuple:
    """Connect to OpticStudio Interactive Extension. Returns (app, system, ZOSAPI, MFE, MOT)."""
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

    # Get MeritOperandType enum from the MFE
    mfe = system.MFE
    op = mfe.GetOperandAt(1)
    MeritOpType = type(op.Type)

    return app, system, ZOSAPI, MeritOpType


# -- Build lens ------------------------------------------------

def build_double_gauss(system: Any, ZOSAPI: Any) -> None:
    """
    Build a symmetric double Gauss lens.

    Surface layout (0-indexed in API):
      Surf 0: OBJECT at infinity
      Surf 1: BK7 front  -- positive meniscus, convex toward object (R>0)
      Surf 2: BK7 rear   -- cemented/air-gap to SF5 (R>0, larger)
      Surf 3: SF5 rear   -- negative meniscus, concave toward stop (R>0, smaller)
      Surf 4: STOP       -- aperture stop, symmetric center
      Surf 5: SF5 front  -- negative meniscus, concave toward stop (R<0)
      Surf 6: SF5 rear   -- cemented/air-gap to BK7 (R<0, larger)
      Surf 7: BK7 front  -- (same surface as SF5 rear in cemented)
      Surf 8: BK7 rear   -- positive meniscus, convex toward image (R<0)
      Surf 9: IMAGE plane

    Wait, 4-element means 8 powered surfaces + OBJ + STOP + IMAGE = more surfaces.
    Let me recount: 4 elements = 8 glass surfaces.

    Layout (1-based UI numbering):
      0 (OBJ): Object at infinity
      1: BK7 front face (R>0, convex toward object)
      2: BK7 rear face  (R>0, ~interface to SF5)
      3: SF5 front face  (R>0 or small, ~interface from BK7)
      4: SF5 rear face   (R>0, concave toward stop)
      5: STOP
      6: SF5 front face   (R<0, concave toward stop)
      7: SF5 rear face    (R<0 or small, ~interface to BK7)
      8: BK7 front face   (R<0, ~interface from SF5)
      9: BK7 rear face    (R<0, convex toward image)
      10: IMAGE

    Wait, I'm confusing myself. Each element has 2 surfaces. 4 elements = 8 surfaces.
    Plus OBJ, STOP, IMAGE.

    Let me use 11 surfaces (0..10):
    0: OBJ
    1: BK7_1 front
    2: BK7_1 rear
    3: SF5_1 front
    4: SF5_1 rear (faces stop)
    5: STOP
    6: SF5_2 front (faces stop)
    7: SF5_2 rear
    8: BK7_2 front
    9: BK7_2 rear
    10: IMAGE

    This accounts for air gaps between crown and flint in each half-group.
    If cemented, surfaces 2==3 and 7==8 share the same radius.
    """
    log("Building double Gauss 50mm F/2.8 lens model...")
    lde = system.LDE

    # New sequential system
    system.New(False)

    # Add surfaces until we have 11 total (indices 0..10)
    while lde.NumberOfSurfaces < 11:
        lde.InsertNewSurfaceAt(lde.NumberOfSurfaces)

    # -- Aperture: Entrance Pupil Diameter (more stable than FloatByStop) --
    apt = system.SystemData.Aperture
    apt.ApertureType = ZOSAPI.SystemData.ZemaxApertureType.EntrancePupilDiameter
    apt.ApertureValue = EPD
    log(f"  Aperture: EPD = {EPD:.3f} mm (target F/{F_NUMBER})")

    # -- Wavelengths: F, d, C --
    wl = system.SystemData.Wavelengths
    while wl.NumberOfWavelengths > 1:
        wl.RemoveWavelength(wl.NumberOfWavelengths)
    wl.GetWavelength(1).Wavelength = WAVELENGTHS[0][0]
    wl.GetWavelength(1).Weight = WAVELENGTHS[0][1]
    for wv, wt, lb in WAVELENGTHS[1:]:
        wl.AddWavelength(wv, wt)
    log("  Wavelengths: F (0.486), d (0.588), C (0.656) um")

    # -- Fields: 0deg, 17.5deg, 25deg --
    fld = system.SystemData.Fields
    while fld.NumberOfFields > 1:
        fld.RemoveField(fld.NumberOfFields)
    fld.GetField(1).Y = FIELDS[0][0]
    fld.GetField(1).Weight = FIELDS[0][1]
    for fy, fw, fl in FIELDS[1:]:
        fld.AddField(0.0, fy, fw)
    log("  Fields: 0deg, 17.5deg, 25deg (half-field)")

    # -- Glass catalog --
    try:
        system.SystemData.MaterialCatalogs.AddCatalog(GLASS_CATALOG)
    except Exception:
        pass

    # -- Starting prescription (symmetric double Gauss) --
    # Based on classic double Gauss / Planar-type scaling for 50mm F/2.8
    # Front group: positive meniscus (crown) + negative meniscus (flint)
    #   Both elements have surfaces curving toward image (R>0)
    #   Crown: R1 < R2 → positive power (stronger front surface)
    #   Flint: R3 > R4 → negative power (stronger rear surface, concave toward stop)
    # Rear group: symmetric about stop, surfaces curve toward object (R<0)
    #
    # Zemax sign convention: R>0 = center of curvature to right of vertex
    #   = surface bulges toward image (right)
    semi_front = 21.0
    semi_stop  = 9.0

    # Starting prescription: each half-group must have NET POSITIVE power
    # to ensure the overall system converges.
    # Front BK7: strong positive meniscus (R1 << R2, both R>0)
    #   f1 ≈ 1/(0.5168*(1/15-1/60)) = 38.7mm → strong positive
    # Front SF5: weak negative meniscus (R3 < R4, both R>0, R4 close to R3)
    #   f2 ≈ 1/(0.6727*(1/60-1/28)) = -1/0.0128 ≈ -78mm → mild negative
    # Net front group: slightly positive
    # Rear group: symmetric → same net positive → overall system converges
    R1  =  15.0   # BK7_1 front:  strong convex toward image
    R2  =  60.0   # BK7_1 rear:   weak convex toward image
    R3  =  60.0   # SF5_1 front:  near-match BK7 rear
    R4  =  28.0   # SF5_1 rear:   mild convex toward stop (weak negative power)
    # STOP at surface 5
    R6  = -28.0   # SF5_2 front:  symmetric to R4
    R7  = -60.0   # SF5_2 rear:   symmetric to R3
    R8  = -60.0   # BK7_2 front:  symmetric to R2
    R9  = -15.0   # BK7_2 rear:   symmetric to R1

    # Thicknesses: each surface's thickness = distance to the NEXT surface.
    # Layout: OBJ | BK7_1 | air | SF5_1 | air | STOP | air | SF5_2 | air | BK7_2 | air->IMAGE
    #
    # Surf 0 → 1:  OBJ to BK7_1 front
    # Surf 1 → 2:  BK7_1 center (glass)
    # Surf 2 → 3:  air gap BK7 → SF5
    # Surf 3 → 4:  SF5_1 center (glass)
    # Surf 4 → 5:  air gap to STOP
    # Surf 5 → 6:  air gap STOP → SF5_2  (must be >0 for stop in air!)
    # Surf 6 → 7:  SF5_2 center (glass)
    # Surf 7 → 8:  air gap SF5 → BK7
    # Surf 8 → 9:  BK7_2 center (glass)
    # Surf 9 → 10: BFD (air to image)
    t0  = 1e10     # 0: OBJ distance
    t1  = 5.5      # 1: BK7_1 center thickness
    t2  = 0.3      # 2: air gap BK7_1 → SF5_1
    t3  = 3.0      # 3: SF5_1 center thickness
    t4  = 6.5      # 4: air SF5_1 rear → STOP
    t5  = 6.5      # 5: STOP → SF5_2 front (air, symmetric)
    t6  = 3.0      # 6: SF5_2 center thickness
    t7  = 0.3      # 7: air gap SF5_2 rear → BK7_2 front
    t8  = 5.5      # 8: BK7_2 center thickness
    t9  = 35.0     # 9: BFD — BK7_2 rear → IMAGE
    t10 = 0.0      # 10: IMAGE (terminal)

    # Total track (surf 1→image) = 5.5+0.3+3+6.5+6.5+3+0.3+5.5+35 = 65.6mm
    # Expected EFL ≈ 53mm

    surf_data = [
        # idx  comment                     radius           thick   material   semi-dia
        (0,  "Object at infinity",         float('inf'),    t0,     "",        0.0),
        (1,  "BK7_1 front (crown)",        R1,              t1,     "N-BK7",   semi_front),
        (2,  "BK7_1 rear",                 R2,              t2,     "",        semi_front - 1),
        (3,  "SF5_1 front (flint)",        R3,              t3,     "N-SF5",   semi_front - 2),
        (4,  "SF5_1 rear (faces stop)",    R4,              t4,     "",        semi_stop + 4),
        (5,  "STOP",                       float('inf'),    t5,     "",        semi_stop),
        (6,  "SF5_2 front (faces stop)",   R6,              t6,     "N-SF5",   semi_stop + 4),
        (7,  "SF5_2 rear",                 R7,              t7,     "",        semi_front - 2),
        (8,  "BK7_2 front (crown)",        R8,              t8,     "N-BK7",   semi_front - 1),
        (9,  "BK7_2 rear",                 R9,              t9,     "",        semi_front),
        (10, "IMAGE",                      float('inf'),    0.0,    "",        23.5),
    ]

    total_track = t1 + t2 + t3 + t4 + t5 + t6 + t7 + t8 + t9 + t10

    for idx, comment, radius, thickness, material, semi_dia in surf_data:
        s = lde.GetSurfaceAt(idx)
        s.Comment = comment
        s.Radius = radius
        s.Thickness = thickness
        s.Material = material
        if semi_dia > 0:
            s.SemiDiameter = semi_dia

    # Set surface 5 as STOP
    lde.GetSurfaceAt(5).IsStop = True

    # Set apertures on all surfaces to float by stop
    for si in range(1, 10):
        try:
            lde.GetSurfaceAt(si).SurfaceApertureData.ApertureType = 0  # 0 = None/Float
        except Exception:
            pass

    total_track = t1 + t2 + t3 + t4 + t5 + t6 + t7 + t8 + t9 + t10
    log(f"  Lens built: 11 surfaces (4 elements + STOP)")
    log(f"  Front group : N-BK7 / N-SF5  (positive + negative meniscus)")
    log(f"  Rear group  : N-SF5 / N-BK7  (negative + positive meniscus)")
    log(f"  Total track : {total_track:.1f} mm (limit: {TOTAL_TRACK_MAX} mm)")
    log(f"  Starting EFL target: {EFL_TARGET} mm @ F/{F_NUMBER}")


# -- First-order metrics ---------------------------------------

def get_first_order(system: Any, MOT: Any) -> dict:
    """Get first-order metrics by evaluating MFE operands."""
    try:
        mfe = system.MFE
        saved_ops = mfe.NumberOfOperands

        def eval_op(op_type, **params):
            mfe.InsertRowAt(mfe.NumberOfOperands + 1)
            op = mfe.GetOperandAt(mfe.NumberOfOperands)
            op.ChangeType(op_type)
            for idx, (pname, pval) in enumerate(params.items(), 1):
                try:
                    from ZOSAPI.Editors.MFE import MeritColumn
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
        isna = eval_op(MOT.ISNA, Wave=2)
        totr = eval_op(MOT.TOTR, Surf1=2, Surf2=11)
        bfl_val = None
        try:
            # Back focal length: distance from last surface to paraxial image
            from ZOSAPI.Editors.MFE import MeritColumn
        except Exception:
            pass

        result = {
            "efl_mm": round(float(efl) if efl else 0, 3),
            "epd_mm": round(float(epdi) if epdi else 0, 3),
            "f_number": round(float(efl)/float(epdi), 3) if efl and epdi and float(epdi) > 0 else None,
            "image_space_na": round(float(isna), 4) if isna else None,
            "total_track_mm": round(float(totr), 3) if totr else None,
        }

        # Clean up temporary operands
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
    Double Gauss specific: heavy emphasis on symmetry, color correction,
    field flatness, and low distortion.
    """
    from ZOSAPI.Editors.MFE import MeritColumn as MC

    mfe = system.MFE
    mfe.DeleteAllRows()

    # Parameter column mapping
    PARAM_MAP = {
        'Wave':   MC.Param1, 'Wave1':  MC.Param1, 'Wave2':  MC.Param2,
        'Field':  MC.Param2, 'Surf':   MC.Param1, 'Surf1':  MC.Param1,
        'Surf2':  MC.Param2, 'Param1': MC.Param1, 'Param2': MC.Param2,
        'Param3': MC.Param3, 'Param4': MC.Param4,
        'Px':     MC.Param1, 'Py':     MC.Param2,
    }

    def add_op(op_type, target=0.0, weight=1.0, **kwargs):
        try:
            idx = mfe.NumberOfOperands + 1
            mfe.InsertRowAt(idx)
            op = mfe.GetOperandAt(idx)
            op.ChangeType(op_type)
            op.Target = float(target)
            op.Weight = float(weight)
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

    # === Stage 1: Feasibility ===
    if stage == "feasibility":
        # EFL constraint (primary — very strong weight)
        add_op(MOT.EFFL, target=EFL_TARGET, weight=10.0, Wave=2)

        # Total track constraint (strong — hard limit)
        add_op(MOT.TOTR, target=TOTAL_TRACK_MAX, weight=3.0, Surf1=2, Surf2=11)

        # Center thickness constraints (min 2mm for all elements)
        for si in [1, 3, 6, 8]:
            add_op(MOT.MNCG, target=MIN_CT_MM, weight=5.0, Surf=si)
        # Edge thickness for each element
        for si in [2, 4, 7, 9]:
            add_op(MOT.MNEG, target=MIN_ET_MM, weight=3.0, Surf=si)

        # Minimum air gaps
        for si in [2, 4, 6, 8]:
            add_op(MOT.MNEA, target=0.1, weight=10.0, Surf=si)

    # === Stage 2: Image Quality ===
    elif stage == "image-quality":
        # EFL strongly constrained
        add_op(MOT.EFFL, target=EFL_TARGET, weight=5.0, Wave=2)

        # Total track (strong constraint)
        add_op(MOT.TOTR, target=TOTAL_TRACK_MAX, weight=3.0, Surf1=2, Surf2=11)

        # Seidel aberrations for all 3 fields (d wavelength = wave 2)
        for fld_num in [1, 2, 3]:
            add_op(MOT.SPHA, target=0.0, weight=0.5, Wave=2, Field=fld_num)
            add_op(MOT.COMA, target=0.0, weight=0.5, Wave=2, Field=fld_num)
            add_op(MOT.ASTI, target=0.0, weight=0.5, Wave=2, Field=fld_num)

        # Axial color (F-C, waves 1 and 3)
        add_op(MOT.AXCL, target=0.0, weight=2.0, Wave1=1, Wave2=3)

        # Lateral color at 0.7 and full field
        add_op(MOT.LACL, target=0.0, weight=1.0, Wave1=1, Wave2=3, Param3=2)
        add_op(MOT.LACL, target=0.0, weight=1.0, Wave1=1, Wave2=3, Param3=3)

        # Field curvature at mid and full field
        add_op(MOT.FCUR, target=0.0, weight=0.5, Wave=2, Field=2)
        add_op(MOT.FCUR, target=0.0, weight=0.5, Wave=2, Field=3)

        # Distortion at full field
        add_op(MOT.DIST, target=0.0, weight=0.5, Wave=2, Field=3)

        # Center/edge thickness
        for si in [1, 3, 6, 8]:
            add_op(MOT.MNCG, target=MIN_CT_MM, weight=3.0, Surf=si)

    # === Stage 3: Field Balance ===
    elif stage == "field-balance":
        add_op(MOT.EFFL, target=EFL_TARGET, weight=5.0, Wave=2)
        add_op(MOT.TOTR, target=TOTAL_TRACK_MAX, weight=3.0, Surf1=2, Surf2=11)

        # Strong distortion control (target ≤ 1.5%)
        add_op(MOT.DIST, target=0.0, weight=2.0, Wave=2, Field=2)
        add_op(MOT.DIST, target=0.0, weight=2.0, Wave=2, Field=3)

        # Field curvature balanced across all fields
        for fld_num in [1, 2, 3]:
            add_op(MOT.FCUR, target=0.0, weight=0.8, Wave=2, Field=fld_num)

        # Astigmatism balanced
        for fld_num in [1, 2, 3]:
            add_op(MOT.ASTI, target=0.0, weight=0.8, Wave=2, Field=fld_num)

        # Color balance
        add_op(MOT.AXCL, target=0.0, weight=1.5, Wave1=1, Wave2=3)
        add_op(MOT.LACL, target=0.0, weight=1.0, Wave1=1, Wave2=3, Param3=2)
        add_op(MOT.LACL, target=0.0, weight=1.0, Wave1=1, Wave2=3, Param3=3)

        # MTF at 30lp/mm for all fields
        for fld_num in [1, 2, 3]:
            add_op(MOT.MTFT, target=MTF_MIN, weight=1.0,
                   Param1=MTF_FREQ, Param2=2, Param3=fld_num)
            add_op(MOT.MTFS, target=MTF_MIN, weight=1.0,
                   Param1=MTF_FREQ, Param2=2, Param3=fld_num)

        # Keep thickness constraints
        for si in [1, 3, 6, 8]:
            add_op(MOT.MNCG, target=MIN_CT_MM, weight=3.0, Surf=si)
        for si in [2, 4, 7, 9]:
            add_op(MOT.MNEG, target=MIN_ET_MM, weight=2.0, Surf=si)

    # === Stage 4: Manufacturability ===
    elif stage == "manufacturability":
        add_op(MOT.EFFL, target=EFL_TARGET, weight=5.0, Wave=2)
        add_op(MOT.TOTR, target=TOTAL_TRACK_MAX, weight=5.0, Surf1=2, Surf2=11)

        # Edge thickness constraints (strong)
        for si in [2, 4, 7, 9]:
            add_op(MOT.MNEG, target=MIN_ET_MM, weight=5.0, Surf=si)

        # Center thickness constraints
        for si in [1, 3, 6, 8]:
            add_op(MOT.MNCG, target=MIN_CT_MM, weight=5.0, Surf=si)

        # Minimum edge thickness for air gaps
        for si in [2, 4, 6, 8]:
            add_op(MOT.MNEA, target=0.2, weight=5.0, Surf=si)

        # Maintain image quality
        add_op(MOT.DIST, target=0.0, weight=0.5, Wave=2, Field=3)
        for fld_num in [1, 2, 3]:
            add_op(MOT.FCUR, target=0.0, weight=0.3, Wave=2, Field=fld_num)

    # --- Add default merit function (RMS spot radius) via optimization wizard ---
    # CRITICAL: keep wizard weight LOW so constraint operands dominate.
    wizard_overall_weight = 0.05 if stage in ("feasibility",) else 0.1
    try:
        wiz = mfe.SEQOptimizationWizard
        wiz.IsAssumeAxialSymmetryUsed = False
        wiz.IsIgnoreLateralColorUsed = False
        wiz.IsDeleteVignetteUsed = True
        wiz.Type = 0          # 0 = RMS spot radius
        wiz.OverallWeight = wizard_overall_weight
        wiz.Ring = 3
        wiz.Grid = 0          # Gaussian quadrature
        wiz.Arm = 2
        wiz.Reference = 0     # Centroid
        wiz.StartAt = mfe.NumberOfOperands + 1
        wiz.OK()
        log(f"    Added default merit function (RMS spot, weight={wizard_overall_weight})")
    except Exception as e:
        log(f"    Default merit function wizard: {e}")

    log(f"  Merit function '{stage}' ready ({mfe.NumberOfOperands} operands)")


# -- Variables -------------------------------------------------

def configure_variables(system: Any, stage: str) -> None:
    """Configure variable surfaces for optimization — graduated by stage."""
    lde = system.LDE
    log(f"  Variables for: {stage}")

    # Image distance (BFD) is ALWAYS variable
    try:
        lde.GetSurfaceAt(10).ThicknessCell.MakeSolveVariable()
    except Exception:
        pass

    if stage == "feasibility":
        # Stage 1: ONLY air gaps + BFD (prevent collapse)
        air_gap_surfs = [2, 4, 6, 8]  # gaps between elements and to stop
        for si in air_gap_surfs:
            try:
                lde.GetSurfaceAt(si).ThicknessCell.MakeSolveVariable()
            except Exception:
                pass
        log("    Air gaps only (stage 1)")

    elif stage == "image-quality":
        # Stage 2: All curvatures + air gaps + BFD
        radius_surfs = [1, 2, 3, 4, 6, 7, 8, 9]
        thick_surfs = [2, 4, 6, 8]  # air gaps
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
        log(f"    {len(radius_surfs)} radii + {len(thick_surfs)} air gaps")

    elif stage in ("field-balance", "manufacturability"):
        # Stage 3+: All curvatures + all thicknesses
        radius_surfs = [1, 2, 3, 4, 6, 7, 8, 9]
        thick_surfs = [1, 2, 3, 4, 6, 7, 8, 9]  # all element thicknesses + air gaps
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
        log(f"    {len(radius_surfs)} radii + {len(thick_surfs)} thicknesses (all)")


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
    path = str(OUT_DIR / f"double_gauss_50mm_{stage}.zmx")
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
    log("Double Gauss 50mm F/2.8 -- Automated Zemax Optical Design")
    log("=" * 70)
    log(f"Output:       {OUT_DIR}")
    log(f"Target EFL:   {EFL_TARGET} mm")
    log(f"F/#:          {F_NUMBER}")
    log(f"EPD:          {EPD:.3f} mm")
    log(f"Half FOV:     {HALF_FOV_DEG} deg (full FOV: {2*HALF_FOV_DEG} deg)")
    log(f"Structure:    N-BK7 / N-SF5 / STOP / N-SF5 / N-BK7")
    log(f"MTF target:   >= {MTF_MIN} @ {MTF_FREQ} lp/mm")
    log(f"Distortion:   <= {DIST_MAX_PCT}%")
    log(f"Total track:  <= {TOTAL_TRACK_MAX} mm")
    log(f"Min CT:       >= {MIN_CT_MM} mm")
    log(f"Min ET:       >= {MIN_ET_MM} mm")
    log("")

    # -- 1. Connect --
    log("> Step 1: Connecting to OpticStudio...")
    app, system, ZOSAPI, MeritOpType = connect_interactive()
    log("  Connected (Interactive Extension).")
    log("")

    # -- 2. Build --
    log("> Step 2: Building double Gauss model...")
    build_double_gauss(system, ZOSAPI)
    log("")

    # -- 3. Baseline --
    log("> Step 3: Baseline evaluation...")
    baseline = get_first_order(system, MeritOpType)
    log(f"  Baseline first-order: {json.dumps(baseline, indent=2)}")
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

        fo = get_first_order(system, MeritOpType)
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
    final = get_first_order(system, MeritOpType)
    efl_error = abs(final.get("efl_mm", 0) - EFL_TARGET)
    efl_error_pct = (efl_error / EFL_TARGET) * 100

    log(f"  EFL:       {final.get('efl_mm')} mm  (target {EFL_TARGET}, err={efl_error:.3f}mm / {efl_error_pct:.2f}%)")
    log(f"  F/#:       {final.get('f_number')}")
    log(f"  EPD:       {final.get('epd_mm')} mm")
    log(f"  Track:     {final.get('total_track_mm')} mm")
    log(f"  NA:        {final.get('image_space_na')}")

    export_analyses(system, "final")
    final_path = save_lens(system, "final")

    # Convenience copy
    convenience = PROJECT_DIR / "designs" / "double_gauss_50mm_final.zmx"
    convenience.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(final_path, convenience)
    log(f"\n  Convenience copy: {convenience}")

    # -- Summary --
    summary = {
        "design": "Double Gauss 50mm F/2.8",
        "timestamp": TIMESTAMP,
        "targets": {
            "efl_mm": EFL_TARGET,
            "f_number": F_NUMBER,
            "epd_mm": round(EPD, 3),
            "half_fov_deg": HALF_FOV_DEG,
            "full_fov_deg": 2 * HALF_FOV_DEG,
            "mtf_min": MTF_MIN,
            "mtf_frequency_lp_per_mm": MTF_FREQ,
            "distortion_percent_max": DIST_MAX_PCT,
            "total_track_max_mm": TOTAL_TRACK_MAX,
            "min_center_thickness_mm": MIN_CT_MM,
            "min_edge_thickness_mm": MIN_ET_MM,
        },
        "final_first_order": final,
        "efl_error_mm": round(efl_error, 3),
        "efl_error_percent": round(efl_error_pct, 2),
        "stages": stage_results,
        "final_lens": final_path,
        "optical_train": {
            "structure": "Symmetric Double Gauss",
            "front_group": "N-BK7 (positive meniscus) + N-SF5 (negative meniscus)",
            "stop": "Central aperture stop",
            "rear_group": "N-SF5 (negative meniscus) + N-BK7 (positive meniscus)",
            "catalog": "SCHOTT",
        },
    }
    save_json(summary, "design_summary")

    log("")
    log("=" * 70)
    log("DESIGN COMPLETE")
    log(f"  Final lens:    {final_path}")
    log(f"  All outputs:   {OUT_DIR}")
    log(f"  Quick access:  {convenience}")
    log(f"  EFL error:     {efl_error:.3f}mm ({efl_error_pct:.2f}%)")
    log("=" * 70)


if __name__ == "__main__":
    main()
