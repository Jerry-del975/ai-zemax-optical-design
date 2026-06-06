"""
6-Element Double Gauss 50mm F/2.8 -- V2 (robust constraints)
================================================================
Simplified 13-surface layout (no dummy air surfaces).
Strong thickness constraints to prevent surface crossover.
Conservative graduated variable release.
"""

from __future__ import annotations
import json, os, shutil, sys
from datetime import datetime
from pathlib import Path
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_DIR = SCRIPT_DIR.parent
TIMESTAMP = datetime.now().strftime("%Y%m%d_%H%M%S")
OUT_DIR = PROJECT_DIR / "designs" / f"dg6_v2_{TIMESTAMP}"
OUT_DIR.mkdir(parents=True, exist_ok=True)

ZOS_ROOT = r"D:\Program Files\Ansys Zemax OpticStudio 2024 R1.00"
EFL_TARGET = 50.0; F_NUMBER = 2.8; HALF_FOV = 25.0
EPD = EFL_TARGET / F_NUMBER
TRACK_MAX = 70.0; MIN_CT = 2.0; MIN_ET = 1.5; MIN_AIR = 0.1
MTF_FREQ = 30.0; MTF_MIN = 0.6

WAVELENGTHS = [(0.48613270,1.0),(0.58756180,1.0),(0.65627250,1.0)]
FIELDS = [(0.0,1.0),(17.5,1.0),(25.0,1.0)]

def log(msg):
    ts=datetime.now().strftime("%H:%M:%S")
    print(f"[{ts}] {msg}", flush=True)
    with (OUT_DIR/"design-log.txt").open("a",encoding="utf-8") as f:
        f.write(f"[{ts}] {msg}\n")

def connect():
    sys.path.insert(0,ZOS_ROOT)
    import clr
    r=Path(ZOS_ROOT)
    clr.AddReference(str(r/"ZOSAPI_NetHelper.dll"))
    clr.AddReference(str(r/"ZOSAPI_Interfaces.dll"))
    clr.AddReference(str(r/"ZOSAPI.dll"))
    import ZOSAPI_NetHelper
    ZOSAPI_NetHelper.ZOSAPI_Initializer.Initialize(ZOS_ROOT)
    import ZOSAPI
    conn=ZOSAPI.ZOSAPI_Connection()
    app=conn.ConnectAsExtension(0)
    if app is None or not app.IsValidLicenseForAPI or app.PrimarySystem is None:
        raise RuntimeError("Connection failed")
    system=app.PrimarySystem
    op=system.MFE.GetOperandAt(1)
    MOT=type(op.Type)
    return app,system,ZOSAPI,MOT

def build(system,ZOSAPI):
    """13-surface 6-element double Gauss.
    0:OBJ 1:BK7_f 2:BK7_r=SF5_f 3:SF5_r 4:SF5_f 5:SF5_r
    6:STOP 7:SF5_f 8:SF5_r 9:SF5_f 10:SF5_r=BK7_f 11:BK7_r 12:IMAGE
    """
    log("Building 13-surface 6-element double Gauss...")
    lde=system.LDE
    system.New(False)
    while lde.NumberOfSurfaces<13:
        lde.InsertNewSurfaceAt(lde.NumberOfSurfaces)

    apt=system.SystemData.Aperture
    apt.ApertureType=ZOSAPI.SystemData.ZemaxApertureType.EntrancePupilDiameter
    apt.ApertureValue=EPD

    wl=system.SystemData.Wavelengths
    while wl.NumberOfWavelengths>1: wl.RemoveWavelength(wl.NumberOfWavelengths)
    wl.GetWavelength(1).Wavelength=WAVELENGTHS[0][0]
    wl.GetWavelength(1).Weight=WAVELENGTHS[0][1]
    for wv,wt in WAVELENGTHS[1:]: wl.AddWavelength(wv,wt)

    fld=system.SystemData.Fields
    while fld.NumberOfFields>1: fld.RemoveField(fld.NumberOfFields)
    fld.GetField(1).Y=FIELDS[0][0]; fld.GetField(1).Weight=FIELDS[0][1]
    for fy,fw in FIELDS[1:]: fld.AddField(0.0,fy,fw)

    try: system.SystemData.MaterialCatalogs.AddCatalog("SCHOTT")
    except: pass

    # ASYMMETRIC prescription to ensure net positive system power:
    # Front triplet: moderate positive BK7 + weak negative SF5s → near-afocal
    # Rear triplet: very strong positive BK7 + moderate negative SF5s → net positive
    # System power = P_front + P_rear - d*P_front*P_rear → positive ~60mm EFL
    sd=[22,21,17,17,14,11,14,17,17,21,22,23.5]

    surf=[
        (0,"OBJ",           1e10, 1e10, "",      0),
        (1,"BK7_1 front",   12.0, 6.0,  "N-BK7", sd[0]),
        (2,"BK7_1=SF5_1",   48.0, 3.5,  "N-SF5", sd[1]),
        (3,"SF5_1 rear",    18.0, 0.3,  "",      sd[2]),
        (4,"SF5_2 front",   18.0, 3.0,  "N-SF5", sd[3]),
        (5,"SF5_2 rear",    13.0, 7.0,  "",      sd[4]),
        (6,"STOP",          1e10, 7.0,  "",      sd[5]),
        (7,"SF5_3 front",  -15.0, 3.0,  "N-SF5", sd[6]),
        (8,"SF5_3 rear",   -21.0, 0.3,  "",      sd[7]),
        (9,"SF5_4 front",  -21.0, 3.5,  "N-SF5", sd[8]),
        (10,"SF5_4=BK7_2", -48.0, 6.0,  "N-BK7", sd[9]),
        (11,"BK7_2 rear",   -8.0, 32.0, "",      sd[10]),
        (12,"IMAGE",        1e10, 0.0,  "",      sd[11]),
    ]

    for idx,comment,radius,thick,mat,sdiam in surf:
        s=lde.GetSurfaceAt(idx)
        s.Comment=comment; s.Radius=radius; s.Thickness=thick
        s.Material=mat
        if sdiam>0: s.SemiDiameter=sdiam

    lde.GetSurfaceAt(6).IsStop=True

    track=sum(lde.GetSurfaceAt(i).Thickness for i in range(1,12))
    log(f"  13 surfaces, 6 elements, track={track:.1f}mm")
    log(f"  Front: N-BK7/N-SF5/N-SF5 | STOP | N-SF5/N-SF5/N-BK7")


def get_fo(system,MOT):
    try:
        mfe=system.MFE; saved=mfe.NumberOfOperands
        def eop(ot,**kw):
            mfe.InsertRowAt(mfe.NumberOfOperands+1)
            op=mfe.GetOperandAt(mfe.NumberOfOperands)
            op.ChangeType(ot)
            from ZOSAPI.Editors.MFE import MeritColumn
            for i,(_,v) in enumerate(kw.items(),1):
                try:
                    c=op.GetOperandCell(getattr(MeritColumn,f'Param{i}'))
                    if c is not None:
                        if isinstance(v,int): c.IntegerValue=v
                        else: c.DoubleValue=float(v)
                except: pass
            mfe.CalculateMeritFunction()
            return op.Value
        efl=eop(MOT.EFFL,Wave=2)
        epd=eop(MOT.EPDI,Wave=2)
        totr=eop(MOT.TOTR,Surf1=2,Surf2=13)
        r={"efl_mm":round(float(efl)if efl else 0,3),
           "epd_mm":round(float(epd)if epd else 0,3),
           "f_number":round(float(efl)/float(epd),3)if efl and epd and float(epd)>0 else None,
           "total_track_mm":round(float(totr),3)if totr else None}
        while mfe.NumberOfOperands>saved: mfe.RemoveOperandAt(mfe.NumberOfOperands)
        return r
    except Exception as e: return {"error":str(e)}


def export(system,stage):
    ad=OUT_DIR/"analyses"/stage; ad.mkdir(parents=True,exist_ok=True)
    exp={}
    for k,fn in [("spot","New_StandardSpot"),("mtf","New_FftMtf"),
                 ("wavefront","New_WavefrontMap"),("rayfan","New_RayFan"),
                 ("field_curv_dist","New_FieldCurvatureAndDistortion"),
                 ("seidel","New_SeidelDiagram"),("prescription","New_Prescription")]:
        try:
            f=getattr(system.Analyses,fn,None)
            if f is None: continue
            a=f(); a.ApplyAndWaitForCompletion()
            a.GetResults().GetTextFile(str(ad/f"{k}.txt"))
            exp[k]=str(ad/f"{k}.txt"); a.Close()
        except Exception as e: log(f"  {k}: {e}")
    log(f"  {len(exp)} analyses exported for '{stage}'")
    return exp


def build_mf(system,stage,MOT):
    from ZOSAPI.Editors.MFE import MeritColumn as MC
    mfe=system.MFE; mfe.DeleteAllRows()
    PM={'Wave':MC.Param1,'Wave1':MC.Param1,'Wave2':MC.Param2,
        'Field':MC.Param2,'Surf':MC.Param1,'Surf1':MC.Param1,
        'Surf2':MC.Param2,'Param1':MC.Param1,'Param2':MC.Param2,
        'Param3':MC.Param3,'Param4':MC.Param4}

    def aop(ot,target=0.0,weight=1.0,**kw):
        try:
            idx=mfe.NumberOfOperands+1; mfe.InsertRowAt(idx)
            op=mfe.GetOperandAt(idx); op.ChangeType(ot)
            op.Target=float(target); op.Weight=float(weight)
            for pn,pv in kw.items():
                col=PM.get(pn)
                if col:
                    try:
                        c=op.GetOperandCell(col)
                        if c is not None:
                            if isinstance(pv,int): c.IntegerValue=pv
                            else: c.DoubleValue=float(pv)
                    except: pass
        except: pass

    log(f"  MF: {stage}")
    # Glass surfaces (1-indexed): 1(BK7), 2(SF5), 4(SF5), 7(SF5), 9(SF5), 10(BK7)
    glass=[1,2,4,7,9,10]
    # Surfaces needing edge thickness: surfaces where glass ends or significant air gaps
    all_s=[1,2,3,4,5,7,8,9,10,11]
    # Air gaps
    air=[3,5,6,8,11]  # surface indices whose thickness is air gap

    # === Thickness positivity constraints ===
    for si in all_s:
        if si in glass:
            aop(MOT.MNCG, target=MIN_CT, weight=20.0, Surf=si)
            aop(MOT.MNEG, target=MIN_ET, weight=10.0, Surf=si)
        else:
            aop(MOT.MNEA, target=MIN_AIR, weight=20.0, Surf=si)

    if stage=="feasibility":
        aop(MOT.EFFL,target=EFL_TARGET,weight=10.0,Wave=2)
        aop(MOT.TOTR,target=TRACK_MAX,weight=2.0,Surf1=2,Surf2=13)

    elif stage=="image-quality":
        aop(MOT.EFFL,target=EFL_TARGET,weight=5.0,Wave=2)
        aop(MOT.TOTR,target=TRACK_MAX,weight=3.0,Surf1=2,Surf2=13)
        for fld in[1,2,3]:
            aop(MOT.SPHA,target=0.0,weight=0.5,Wave=2,Field=fld)
            aop(MOT.COMA,target=0.0,weight=0.5,Wave=2,Field=fld)
            aop(MOT.ASTI,target=0.0,weight=0.5,Wave=2,Field=fld)
        aop(MOT.AXCL,target=0.0,weight=2.0,Wave1=1,Wave2=3)
        aop(MOT.LACL,target=0.0,weight=1.0,Wave1=1,Wave2=3,Param3=2)
        aop(MOT.LACL,target=0.0,weight=1.0,Wave1=1,Wave2=3,Param3=3)
        aop(MOT.FCUR,target=0.0,weight=0.5,Wave=2,Field=2)
        aop(MOT.FCUR,target=0.0,weight=0.5,Wave=2,Field=3)
        aop(MOT.DIST,target=0.0,weight=0.5,Wave=2,Field=3)

    elif stage=="field-balance":
        aop(MOT.EFFL,target=EFL_TARGET,weight=5.0,Wave=2)
        aop(MOT.TOTR,target=TRACK_MAX,weight=3.0,Surf1=2,Surf2=13)
        aop(MOT.DIST,target=0.0,weight=2.0,Wave=2,Field=2)
        aop(MOT.DIST,target=0.0,weight=2.0,Wave=2,Field=3)
        for fld in[1,2,3]:
            aop(MOT.FCUR,target=0.0,weight=0.8,Wave=2,Field=fld)
            aop(MOT.ASTI,target=0.0,weight=0.8,Wave=2,Field=fld)
        aop(MOT.AXCL,target=0.0,weight=1.5,Wave1=1,Wave2=3)
        aop(MOT.LACL,target=0.0,weight=1.0,Wave1=1,Wave2=3,Param3=2)
        aop(MOT.LACL,target=0.0,weight=1.0,Wave1=1,Wave2=3,Param3=3)
        for fld in[1,2,3]:
            aop(MOT.MTFT,target=MTF_MIN,weight=1.0,Param1=MTF_FREQ,Param2=2,Param3=fld)
            aop(MOT.MTFS,target=MTF_MIN,weight=1.0,Param1=MTF_FREQ,Param2=2,Param3=fld)

    elif stage=="manufacturability":
        aop(MOT.EFFL,target=EFL_TARGET,weight=5.0,Wave=2)
        aop(MOT.TOTR,target=TRACK_MAX,weight=5.0,Surf1=2,Surf2=13)
        aop(MOT.DIST,target=0.0,weight=0.5,Wave=2,Field=3)

    # Default merit function (very low weight to prioritize constraints)
    wt=0.02 if stage=="feasibility" else 0.05
    try:
        wiz=mfe.SEQOptimizationWizard
        wiz.IsAssumeAxialSymmetryUsed=False
        wiz.IsIgnoreLateralColorUsed=False
        wiz.IsDeleteVignetteUsed=True
        wiz.Type=0; wiz.OverallWeight=wt; wiz.Ring=3; wiz.Grid=0; wiz.Arm=2
        wiz.Reference=0; wiz.StartAt=mfe.NumberOfOperands+1; wiz.OK()
        log(f"    Wizard: RMS spot, wt={wt}")
    except Exception as e: log(f"    Wizard err: {e}")
    log(f"  MF '{stage}': {mfe.NumberOfOperands} ops")


def set_vars(system,stage):
    lde=system.LDE
    # Radii: surfaces 1-5, 7-11 (10 powered surfaces, skip STOP at 6, IMAGE at 12)
    rad=[1,2,3,4,5,7,8,9,10,11]
    air_gaps=[3,5,6,8,11]  # SF5_1 rear→SF5_2, SF5_2→STOP, STOP→SF5_3, SF5_3→SF5_4, BK7→IMAGE
    glass_th=[1,2,4,7,9,10]  # center thicknesses

    # Always: BFD (surface 11 thickness)
    try: lde.GetSurfaceAt(11).ThicknessCell.MakeSolveVariable()
    except: pass

    if stage=="feasibility":
        for si in air_gaps:
            try: lde.GetSurfaceAt(si).ThicknessCell.MakeSolveVariable()
            except: pass
        log(f"    Air gaps only ({len(air_gaps)} vars)")

    elif stage=="image-quality":
        for si in rad:
            try: lde.GetSurfaceAt(si).RadiusCell.MakeSolveVariable()
            except: pass
        for si in air_gaps:
            try: lde.GetSurfaceAt(si).ThicknessCell.MakeSolveVariable()
            except: pass
        log(f"    {len(rad)} radii + {len(air_gaps)} air gaps")

    else:  # field-balance, manufacturability
        for si in rad:
            try: lde.GetSurfaceAt(si).RadiusCell.MakeSolveVariable()
            except: pass
        for si in glass_th+air_gaps:
            try: lde.GetSurfaceAt(si).ThicknessCell.MakeSolveVariable()
            except: pass
        log(f"    {len(rad)} radii + {len(glass_th)+len(air_gaps)} thicknesses")


def optimize(system,stage):
    log(f"  Optimizing ({stage})...")
    m=None
    tool=system.Tools.OpenLocalOptimization()
    try:
        tool.NumberOfCycles=0
        tool.RunAndWaitForCompletion()
        try: m=float(tool.FinalMeritFunctionValue)
        except: pass
    except Exception as e: log(f"  Opt err: {e}")
    finally: tool.Close()
    log(f"  Merit={m}")
    return m


def save_lens(system,stage):
    p=str(OUT_DIR/f"dg6_{stage}.zmx"); system.SaveAs(p); return p

def save_json(data,name):
    (OUT_DIR/f"{name}.json").write_text(json.dumps(data,indent=2,ensure_ascii=False),encoding="utf-8")

def main():
    log("="*60)
    log("6-Element Double Gauss 50mm F/2.8 (V2)")
    log(f"EFL={EFL_TARGET}mm F/{F_NUMBER} FOV=+/-{HALF_FOV}deg")
    log(f"Track<={TRACK_MAX}mm CT>={MIN_CT}mm ET>={MIN_ET}mm")
    log("="*60)

    app,system,ZOSAPI,MOT=connect()
    log("Connected.")
    build(system,ZOSAPI)
    fo=get_fo(system,MOT)
    log(f"Baseline: {json.dumps(fo,indent=2)}")
    save_json(fo,"baseline_fo")
    export(system,"baseline")
    save_lens(system,"baseline")

    stages=["feasibility","image-quality","field-balance","manufacturability"]
    results=[]
    for i,stage in enumerate(stages,1):
        log(f"\n--- Stage {i}: {stage} ---")
        set_vars(system,stage)
        build_mf(system,stage,MOT)
        merit=optimize(system,stage)
        fo=get_fo(system,MOT)
        log(f"  FO: {json.dumps(fo,indent=2)}")
        export(system,stage)
        lp=save_lens(system,stage)
        results.append({"stage":stage,"merit":merit,"fo":fo,"lens":lp})
        save_json(results[-1],f"stage_{stage}")

    log("\n=== FINAL ===")
    fo=get_fo(system,MOT)
    err=abs(fo.get("efl_mm",0)-EFL_TARGET)
    log(f"EFL={fo.get('efl_mm')}mm (err={err:.3f}mm/{err/EFL_TARGET*100:.2f}%)")
    log(f"F/#={fo.get('f_number')} Track={fo.get('total_track_mm')}mm")
    export(system,"final")
    fp=save_lens(system,"final")
    conv=PROJECT_DIR/"designs"/"double_gauss_6elem_final.zmx"
    conv.parent.mkdir(parents=True,exist_ok=True)
    shutil.copy2(fp,conv)
    log(f"\nFinal: {fp}\nQuick: {conv}")
    log("DONE")

if __name__=="__main__":
    main()
