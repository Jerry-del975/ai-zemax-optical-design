"""
6-Element Double Gauss 50mm F/2.8 — Working Version
=====================================================
Based on proven 4-element script pattern.
EPD aperture, graduated variables, low wizard weight.
13 surfaces: 0=OBJ, 1-12=optical, 12=IMAGE
"""

from __future__ import annotations
import json, os, shutil, sys, time
from datetime import datetime
from pathlib import Path
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_DIR = SCRIPT_DIR.parent
TIMESTAMP = datetime.now().strftime("%Y%m%d_%H%M%S")
OUT_DIR = PROJECT_DIR / "designs" / f"dg6_w_{TIMESTAMP}"
OUT_DIR.mkdir(parents=True, exist_ok=True)

ZOS_ROOT = r"D:\Program Files\Ansys Zemax OpticStudio 2024 R1.00"
EFL_T = 50.0; FNUM = 2.8; HFOV = 25.0; EPD_V = EFL_T / FNUM  # 17.857
TMAX = 70.0; MCT = 2.0; MET = 1.5; MAIR = 0.1
MTF_FREQ = 30.0; MTF_TGT = 0.6

WVL = [(0.48613270,1.0),(0.58756180,1.0),(0.65627250,1.0)]
FLD = [(0.0,1.0),(17.5,1.0),(25.0,1.0)]

def log(msg):
    ts=datetime.now().strftime("%H:%M:%S"); print(f"[{ts}] {msg}",flush=True)
    with (OUT_DIR/"design-log.txt").open("a",encoding="utf-8")as f: f.write(f"[{ts}] {msg}\n")

def connect():
    sys.path.insert(0,ZOS_ROOT)
    import clr; r=Path(ZOS_ROOT)
    clr.AddReference(str(r/"ZOSAPI_NetHelper.dll"))
    clr.AddReference(str(r/"ZOSAPI_Interfaces.dll"))
    clr.AddReference(str(r/"ZOSAPI.dll"))
    import ZOSAPI_NetHelper; ZOSAPI_NetHelper.ZOSAPI_Initializer.Initialize(ZOS_ROOT)
    import ZOSAPI
    a=ZOSAPI.ZOSAPI_Connection().ConnectAsExtension(0)
    if a is None or not a.IsValidLicenseForAPI or a.PrimarySystem is None:
        raise RuntimeError("Connection failed")
    s=a.PrimarySystem; op=s.MFE.GetOperandAt(1); MOT=type(op.Type)
    return a,s,ZOSAPI,MOT

def build(system,ZOSAPI):
    """13-surface 6-element double Gauss.
    s0=OBJ s1-12 optical s12=IMAGE. STOP at s6.
    """
    log("Building 6-element double Gauss...")
    lde=system.LDE; system.New(False)
    while lde.NumberOfSurfaces<13: lde.InsertNewSurfaceAt(lde.NumberOfSurfaces)

    apt=system.SystemData.Aperture
    apt.ApertureType=ZOSAPI.SystemData.ZemaxApertureType.EntrancePupilDiameter
    apt.ApertureValue=EPD_V

    wl=system.SystemData.Wavelengths
    while wl.NumberOfWavelengths>1: wl.RemoveWavelength(wl.NumberOfWavelengths)
    wl.GetWavelength(1).Wavelength=WVL[0][0]; wl.GetWavelength(1).Weight=WVL[0][1]
    for wv,wt in WVL[1:]: wl.AddWavelength(wv,wt)

    fld=system.SystemData.Fields
    while fld.NumberOfFields>1: fld.RemoveField(fld.NumberOfFields)
    fld.GetField(1).Y=FLD[0][0]; fld.GetField(1).Weight=FLD[0][1]
    for fy,fw in FLD[1:]: fld.AddField(0.0,fy,fw)

    try: system.SystemData.MaterialCatalogs.AddCatalog("SCHOTT")
    except: pass

    # Prescription — 12 optical surfaces (S0-S11) + IMAGE at distance
    # S6 = STOP with rear air gap thickness
    sd=[22,21,17,17,14,    # front
        11,                 # STOP
        14,17,17,21,22,     # rear
        23.7]               # IMAGE

    surf=[
        #(ix, Radius, Thickness, Material, SemiDia, Comment)
        (0,  1e10,  1e10,    "",      0,      "OBJ"),
        # Stronger starting prescription (EFL ~55mm, close to 50mm target)
        (1,  10.0,  5.5,     "N-BK7", sd[0],  "BK7_1 front"),
        (2,  40.0,  3.0,     "N-SF5", sd[1],  "BK7_1=SF5_1 (cem)"),
        (3,  20.0,  0.3,     "",      sd[2],  "SF5_1 rear"),
        (4,  20.0,  2.5,     "N-SF5", sd[3],  "SF5_2 front"),
        (5,  12.0,  6.5,     "",      sd[4],  "SF5_2 rear→STOP"),
        (6,  1e10,  6.5,     "",      sd[5],  "STOP→SF5_3"),  # STOP + rear gap
        (7, -12.0,  2.5,     "N-SF5", sd[6],  "SF5_3 front"),
        (8, -20.0,  0.3,     "",      sd[7],  "SF5_3 rear"),
        (9, -20.0,  3.0,     "N-SF5", sd[8],  "SF5_4 front"),
        (10,-40.0,  5.5,     "N-BK7", sd[9],  "SF5_4=BK7_2 (cem)"),
        (11,-10.0,  30.0,    "",      sd[10], "BK7_2 rear→IMAGE"),
        (12, 1e10,  0.0,     "",      sd[11], "IMAGE"),
    ]

    for ix,rad,th,mat,sdia,comment in surf:
        s=lde.GetSurfaceAt(ix)
        s.Comment=comment; s.Radius=rad; s.Thickness=th; s.Material=mat
        if sdia>0: s.SemiDiameter=sdia

    lde.GetSurfaceAt(6).IsStop=True

    track=sum(lde.GetSurfaceAt(i).Thickness for i in range(1,12))
    log(f"  13 surfaces, STOP@6, track={track:.1f}mm")
    log(f"  Front: BK7/SF5/SF5 | STOP | SF5/SF5/BK7")


def get_fo(system,MOT):
    mfe=system.MFE; saved=mfe.NumberOfOperands
    from ZOSAPI.Editors.MFE import MeritColumn as MC
    def eop(ot,**kw):
        mfe.InsertRowAt(mfe.NumberOfOperands+1)
        op=mfe.GetOperandAt(mfe.NumberOfOperands); op.ChangeType(ot)
        for i,(_,v) in enumerate(kw.items(),1):
            try:
                c=op.GetOperandCell(getattr(MC,f'Param{i}'))
                if c is not None:
                    if isinstance(v,int): c.IntegerValue=v
                    else: c.DoubleValue=float(v)
            except: pass
        mfe.CalculateMeritFunction(); return op.Value
    efl=eop(MOT.EFFL,Wave=2); epd=eop(MOT.EPDI,Wave=2)
    totr=eop(MOT.TOTR,Surf1=2,Surf2=13)
    r={"efl":round(float(efl)if efl else 0,3),
       "epd":round(float(epd)if epd else 0,3),
       "fn":round(float(efl)/float(epd),3)if efl and epd and float(epd)>0 else None,
       "totr":round(float(totr),3)if totr else None}
    while mfe.NumberOfOperands>saved: mfe.RemoveOperandAt(mfe.NumberOfOperands)
    return r

def export_analyses(system,stage):
    ad=OUT_DIR/"analyses"/stage; ad.mkdir(parents=True,exist_ok=True)
    exports={}
    for k,fn in [("spot","New_StandardSpot"),("mtf","New_FftMtf"),
                 ("wavefront","New_WavefrontMap"),("rayfan","New_RayFan"),
                 ("fcd","New_FieldCurvatureAndDistortion"),
                 ("seidel","New_SeidelDiagram"),("rx","New_Prescription")]:
        try:
            fa=getattr(system.Analyses,fn,None)
            if fa is None: continue
            a=fa(); a.ApplyAndWaitForCompletion()
            a.GetResults().GetTextFile(str(ad/f"{k}.txt"))
            exports[k]=str(ad/f"{k}.txt"); a.Close()
        except Exception as e: log(f"    {k}: {e}")
    log(f"  Exported {len(exports)} analyses for '{stage}'")
    return exports

def build_mf(system,stage,MOT):
    from ZOSAPI.Editors.MFE import MeritColumn as MC
    mfe=system.MFE; mfe.DeleteAllRows()
    pm={'Wave':MC.Param1,'Wave1':MC.Param1,'Wave2':MC.Param2,
        'Field':MC.Param2,'Surf':MC.Param1,'Surf1':MC.Param1,
        'Surf2':MC.Param2,'Param1':MC.Param1,'Param2':MC.Param2,
        'Param3':MC.Param3,'Param4':MC.Param4}
    def ao(ot,tg=0.0,wt=1.0,**kw):
        try:
            ix=mfe.NumberOfOperands+1; mfe.InsertRowAt(ix)
            op=mfe.GetOperandAt(ix); op.ChangeType(ot)
            op.Target=float(tg); op.Weight=float(wt)
            for pn,pv in kw.items():
                col=pm.get(pn)
                if col:
                    try:
                        cl=op.GetOperandCell(col)
                        if cl is not None:
                            if isinstance(pv,int): cl.IntegerValue=pv
                            else: cl.DoubleValue=float(pv)
                    except: pass
        except Exception as e: pass

    log(f"  Building MF: {stage}")

    glass=[1,2,4,7,9,10]  # 6 glass center thicknesses
    air_g=[3,5,6,8]         # 4 air gaps
    bfd_surf=11              # BFD = thickness at S11 (last powered surface)

    # === CRITICAL: curvature sign (prevents surface reversal) ===
    front_R = [1,2,3,4,5]     # must stay R>0 (positive curvature)
    rear_R  = [7,8,9,10,11]   # must stay R<0 (negative curvature)
    for si in front_R: ao(MOT.CVGT,tg=0.001,wt=10.0,Surf=si)
    for si in rear_R:  ao(MOT.CVLT,tg=-0.001,wt=10.0,Surf=si)

    # Shared constraints: TTHI minimum on ALL variable surfaces
    all_th=[1,2,3,4,5,6,7,8,9,10,11]
    for si in all_th:
        tmin = float(MCT) if si in glass else float(MAIR)
        ao(MOT.TTHI,tg=tmin,wt=30.0,Surf=si)

    if stage=="feasibility":
        ao(MOT.EFFL,tg=EFL_T,wt=10.0,Wave=2)
        ao(MOT.TOTR,tg=TMAX,wt=2.0,Surf1=2,Surf2=13)
        ao(MOT.TTHI,tg=30.0,wt=1.0,Surf=bfd_surf)  # BFD ~30mm target

    elif stage=="image-quality":
        ao(MOT.EFFL,tg=EFL_T,wt=5.0,Wave=2)
        ao(MOT.TOTR,tg=TMAX,wt=2.0,Surf1=2,Surf2=13)
        ao(MOT.TTHI,tg=30.0,wt=0.5,Surf=bfd_surf)
        for fl in[1,2,3]:
            ao(MOT.SPHA,tg=0.0,wt=0.5,Wave=2,Field=fl)
            ao(MOT.COMA,tg=0.0,wt=0.5,Wave=2,Field=fl)
            ao(MOT.ASTI,tg=0.0,wt=0.5,Wave=2,Field=fl)
        ao(MOT.AXCL,tg=0.0,wt=2.0,Wave1=1,Wave2=3)
        ao(MOT.LACL,tg=0.0,wt=1.0,Wave1=1,Wave2=3,Param3=2)
        ao(MOT.LACL,tg=0.0,wt=1.0,Wave1=1,Wave2=3,Param3=3)
        ao(MOT.FCUR,tg=0.0,wt=0.5,Wave=2,Field=2)
        ao(MOT.FCUR,tg=0.0,wt=0.5,Wave=2,Field=3)
        ao(MOT.DIST,tg=0.0,wt=0.5,Wave=2,Field=3)

    elif stage=="field-balance":
        ao(MOT.EFFL,tg=EFL_T,wt=5.0,Wave=2)
        ao(MOT.TOTR,tg=TMAX,wt=2.0,Surf1=2,Surf2=13)
        ao(MOT.TTHI,tg=30.0,wt=0.5,Surf=bfd_surf)
        ao(MOT.DIST,tg=0.0,wt=2.0,Wave=2,Field=2)
        ao(MOT.DIST,tg=0.0,wt=2.0,Wave=2,Field=3)
        for fl in[1,2,3]:
            ao(MOT.FCUR,tg=0.0,wt=0.8,Wave=2,Field=fl)
            ao(MOT.ASTI,tg=0.0,wt=0.8,Wave=2,Field=fl)
        ao(MOT.AXCL,tg=0.0,wt=1.5,Wave1=1,Wave2=3)
        ao(MOT.LACL,tg=0.0,wt=1.0,Wave1=1,Wave2=3,Param3=2)
        ao(MOT.LACL,tg=0.0,wt=1.0,Wave1=1,Wave2=3,Param3=3)
        for fl in[1,2,3]:
            ao(MOT.MTFT,tg=MTF_TGT,wt=1.0,Param1=MTF_FREQ,Param2=2,Param3=fl)
            ao(MOT.MTFS,tg=MTF_TGT,wt=1.0,Param1=MTF_FREQ,Param2=2,Param3=fl)

    elif stage=="manufacturability":
        ao(MOT.EFFL,tg=EFL_T,wt=5.0,Wave=2)
        ao(MOT.TOTR,tg=TMAX,wt=5.0,Surf1=2,Surf2=13)
        ao(MOT.TTHI,tg=30.0,wt=1.0,Surf=bfd_surf)
        for si in glass:
            ao(MOT.MNCG,tg=MCT,wt=10.0,Surf=si)
            ao(MOT.MNEG,tg=MET,wt=10.0,Surf=si)
        for si in air_g: ao(MOT.MNEA,tg=MAIR,wt=10.0,Surf=si)
        ao(MOT.DIST,tg=0.0,wt=0.5,Wave=2,Field=3)

    # Default merit function
    wiz_wt = 0.03 if stage=="feasibility" else 0.06
    try:
        wiz=mfe.SEQOptimizationWizard
        wiz.IsAssumeAxialSymmetryUsed=False; wiz.IsIgnoreLateralColorUsed=False
        wiz.IsDeleteVignetteUsed=True; wiz.Type=0; wiz.OverallWeight=wiz_wt
        wiz.Ring=3; wiz.Grid=0; wiz.Arm=2; wiz.Reference=0
        wiz.StartAt=mfe.NumberOfOperands+1; wiz.OK()
        log(f"    Added default MF (RMS spot, weight={wiz_wt})")
    except Exception as e: log(f"    Wizard error: {e}")

    log(f"  MF '{stage}': {mfe.NumberOfOperands} operands")


def configure_vars(system,stage):
    lde=system.LDE; log(f"  Variables: {stage}")
    rad=[1,2,3,4,5,7,8,9,10,11]  # 10 powered surfaces (S6=STOP, S12=IMAGE)
    air=[3,5,6,8]                   # 4 air gaps
    glass_th=[1,2,4,7,9,10]        # 6 glass center thicknesses
    bfd_surf=11                      # BFD surface (S11 thickness = BK7_2→IMAGE)

    # BFD always variable
    try: lde.GetSurfaceAt(bfd_surf).ThicknessCell.MakeSolveVariable()
    except: pass

    if stage=="feasibility":
        for si in air:
            try: lde.GetSurfaceAt(si).ThicknessCell.MakeSolveVariable()
            except: pass
        log(f"    Air gaps only ({len(air)} vars)")

    elif stage=="image-quality":
        for si in rad:
            try: lde.GetSurfaceAt(si).RadiusCell.MakeSolveVariable()
            except: pass
        for si in air:
            try: lde.GetSurfaceAt(si).ThicknessCell.MakeSolveVariable()
            except: pass
        log(f"    {len(rad)} radii + {len(air)} air gaps")

    else:  # field-balance, manufacturability
        for si in rad:
            try: lde.GetSurfaceAt(si).RadiusCell.MakeSolveVariable()
            except: pass
        for si in glass_th+air:
            try: lde.GetSurfaceAt(si).ThicknessCell.MakeSolveVariable()
            except: pass
        log(f"    {len(rad)} radii + {len(glass_th)+len(air)} thicknesses")


def optimize(system,stage):
    log(f"  Running optimization ({stage})...")
    tool=system.Tools.OpenLocalOptimization(); merit=None
    try:
        tool.NumberOfCycles=0
        tool.RunAndWaitForCompletion()
        try: merit=float(tool.FinalMeritFunctionValue)
        except: pass
    except Exception as e: log(f"  Opt error: {e}")
    finally: tool.Close()
    log(f"  Merit: {merit}")
    return merit


def save_lens(system,stage):
    p=str(OUT_DIR/f"dg6_{stage}.zmx"); system.SaveAs(p); log(f"  Saved: {p}"); return p

def save_json(data,name):
    (OUT_DIR/f"{name}.json").write_text(json.dumps(data,indent=2,ensure_ascii=False),encoding="utf-8")


def main():
    log("="*60)
    log(f"6-Element Double Gauss 50mm F/2.8 (Working)")
    log(f"EFL={EFL_T}mm F/{FNUM} HFOV={HFOV}deg EPD={EPD_V:.3f}mm")
    log(f"Track<={TMAX}mm CT>={MCT} ET>={MET} MTF>={MTF_TGT}@{MTF_FREQ}lp/mm")
    log("="*60)

    app,system,ZOSAPI,MOT=connect(); log("Connected.")
    build(system,ZOSAPI)

    baseline=get_fo(system,MOT)
    log(f"Baseline: {json.dumps(baseline)}")
    save_json(baseline,"baseline_fo")
    export_analyses(system,"baseline")
    save_lens(system,"baseline")

    stages=["feasibility","image-quality","field-balance","manufacturability"]
    results=[]
    for i,stage in enumerate(stages,1):
        log(f"\n--- Stage {i}: {stage} ---")
        configure_vars(system,stage)
        build_mf(system,stage,MOT)
        merit=optimize(system,stage)
        fo=get_fo(system,MOT)
        log(f"  FO: {json.dumps(fo)}")
        export_analyses(system,stage)
        lp=save_lens(system,stage)
        results.append({"stage":stage,"merit":merit,"fo":fo,"lens":lp})
        save_json(results[-1],f"stage_{stage}")

    log("\n=== FINAL ===")
    final=get_fo(system,MOT)
    err=abs(final.get("efl",0)-EFL_T)
    log(f"EFL={final['efl']}mm (err={err:.3f}mm/{err/EFL_T*100:.2f}%)")
    log(f"F/#={final['fn']} Track={final['totr']}mm")
    export_analyses(system,"final")
    fp=save_lens(system,"final")
    conv=PROJECT_DIR/"designs"/"double_gauss_6elem_final.zmx"
    conv.parent.mkdir(parents=True,exist_ok=True); shutil.copy2(fp,conv)

    summary={"design":"6-Elem Double Gauss 50mm F/2.8","ts":TIMESTAMP,
        "targets":{"efl":EFL_T,"fnum":FNUM,"hfov":HFOV,"tmax":TMAX},
        "final_fo":final,"efl_err_mm":round(err,3),"stages":results,"final_lens":fp}
    save_json(summary,"summary")
    log(f"\nDONE! {fp}\nQuick: {conv}")


if __name__=="__main__":
    main()
