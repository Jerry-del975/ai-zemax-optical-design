"""
6-Element Double Gauss 50mm F/2.8 — Production Design
=======================================================
Key insight: start with minimal MF (no wizard), gradually add complexity.
Stage 1: EFL + TOTR + TTHI only (NO wizard)
Stage 2: Add Seidel + color + light wizard
Stage 3: Add MTF + distortion + wizard
Stage 4: Strong thickness + wizard
"""

from __future__ import annotations
import json, os, shutil, sys, time
from datetime import datetime
from pathlib import Path
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_DIR = SCRIPT_DIR.parent
TS = datetime.now().strftime("%Y%m%d_%H%M%S")
OUT = PROJECT_DIR / "designs" / f"dg6_prod_{TS}"
OUT.mkdir(parents=True, exist_ok=True)

ZOS_ROOT = r"D:\Program Files\Ansys Zemax OpticStudio 2024 R1.00"
EFL_T = 50.0; FNUM = 2.8; HFOV = 25.0; EPD_V = 17.857
TMAX = 70.0; MCT = 2.0; MET = 1.5; MAIR = 0.1
MTF_F = 30.0; MTF_TGT = 0.6

def log(m):
    t=datetime.now().strftime("%H:%M:%S"); print(f"[{t}] {m}",flush=True)
    with (OUT/"log.txt").open("a",encoding="utf-8")as fh: fh.write(f"[{t}] {m}\n")

def connect():
    sys.path.insert(0,ZOS_ROOT)
    import clr; rr=Path(ZOS_ROOT)
    clr.AddReference(str(rr/"ZOSAPI_NetHelper.dll"))
    clr.AddReference(str(rr/"ZOSAPI_Interfaces.dll"))
    clr.AddReference(str(rr/"ZOSAPI.dll"))
    import ZOSAPI_NetHelper; ZOSAPI_NetHelper.ZOSAPI_Initializer.Initialize(ZOS_ROOT)
    import ZOSAPI
    a=ZOSAPI.ZOSAPI_Connection().ConnectAsExtension(0)
    if a is None or not a.IsValidLicenseForAPI or a.PrimarySystem is None:
        raise RuntimeError("connect fail")
    s=a.PrimarySystem; op=s.MFE.GetOperandAt(1); MOT=type(op.Type)
    return a,s,ZOSAPI,MOT

def build(s,Z):
    l=s.LDE; s.New(False)
    while l.NumberOfSurfaces<13: l.InsertNewSurfaceAt(l.NumberOfSurfaces)
    s.SystemData.Aperture.ApertureType=Z.SystemData.ZemaxApertureType.EntrancePupilDiameter
    s.SystemData.Aperture.ApertureValue=EPD_V
    w=s.SystemData.Wavelengths
    while w.NumberOfWavelengths>1: w.RemoveWavelength(w.NumberOfWavelengths)
    w.GetWavelength(1).Wavelength=0.48613270; w.AddWavelength(0.58756180,1.0); w.AddWavelength(0.65627250,1.0)
    f=s.SystemData.Fields
    while f.NumberOfFields>1: f.RemoveField(f.NumberOfFields)
    f.GetField(1).Y=0.0; f.AddField(0.0,17.5,1.0); f.AddField(0.0,25.0,1.0)
    try: s.SystemData.MaterialCatalogs.AddCatalog("SCHOTT")
    except: pass
    sd=[22,21,17,17,14,11,14,17,17,21,22,23.7]
    sf=[(0,1e10,1e10,'',0),(1,10.0,5.5,'N-BK7',sd[0]),(2,40.0,3.0,'N-SF5',sd[1]),
        (3,20.0,0.3,'',sd[2]),(4,20.0,2.5,'N-SF5',sd[3]),(5,12.0,6.5,'',sd[4]),
        (6,1e10,6.5,'',sd[5]),(7,-12.0,2.5,'N-SF5',sd[6]),(8,-20.0,0.3,'',sd[7]),
        (9,-20.0,3.0,'N-SF5',sd[8]),(10,-40.0,5.5,'N-BK7',sd[9]),(11,-10.0,30.0,'',sd[10]),
        (12,1e10,0.0,'',sd[11])]
    for ix,rad,th,mat,sdia in sf:
        ss=l.GetSurfaceAt(ix); ss.Radius=rad; ss.Thickness=th; ss.Material=mat
        if sdia>0: ss.SemiDiameter=sdia
    l.GetSurfaceAt(6).IsStop=True
    track=sum(l.GetSurfaceAt(i).Thickness for i in range(1,12))
    log(f"Built 13-surf 6-elem, trk={track:.1f}mm")

def fo(s,MOT):
    m=s.MFE; sv=m.NumberOfOperands
    from ZOSAPI.Editors.MFE import MeritColumn as MC
    def e(ot,**kw):
        m.InsertRowAt(m.NumberOfOperands+1); op=m.GetOperandAt(m.NumberOfOperands)
        op.ChangeType(ot)
        for i,(_,v) in enumerate(kw.items(),1):
            try:
                c=op.GetOperandCell(getattr(MC,f'Param{i}'))
                if c:
                    if isinstance(v,int): c.IntegerValue=v
                    else: c.DoubleValue=float(v)
            except: pass
        m.CalculateMeritFunction(); return op.Value
    efl=e(MOT.EFFL,Wave=2); epd=e(MOT.EPDI,Wave=2); totr=e(MOT.TOTR,Surf1=2,Surf2=13)
    r={"efl":round(float(efl)if efl else 0,3),
       "epd":round(float(epd)if epd else 0,3),
       "fn":round(float(efl)/float(epd),3)if efl and epd and float(epd)>0 else None,
       "totr":round(float(totr),3)if totr else None}
    while m.NumberOfOperands>sv: m.RemoveOperandAt(m.NumberOfOperands)
    return r

def exports(s,st):
    ad=OUT/"analyses"/st; ad.mkdir(parents=True,exist_ok=True)
    ex={}
    for k,fn in [("spot","New_StandardSpot"),("mtf","New_FftMtf"),
                 ("wavefront","New_WavefrontMap"),("rayfan","New_RayFan"),
                 ("fcd","New_FieldCurvatureAndDistortion"),
                 ("seidel","New_SeidelDiagram"),("rx","New_Prescription")]:
        try:
            fa=getattr(s.Analyses,fn,None)
            if fa is None: continue
            a=fa(); a.ApplyAndWaitForCompletion()
            a.GetResults().GetTextFile(str(ad/f"{k}.txt"))
            ex[k]=str(ad/f"{k}.txt"); a.Close()
        except Exception as e: log(f"  {k}: {e}")
    log(f"  {len(ex)} analyses: {st}")
    return ex

def build_mf(s,st,MOT):
    from ZOSAPI.Editors.MFE import MeritColumn as MC
    m=s.MFE; m.DeleteAllRows()
    pm={'Wave':MC.Param1,'Wave1':MC.Param1,'Wave2':MC.Param2,
        'Field':MC.Param2,'Surf':MC.Param1,'Surf1':MC.Param1,
        'Surf2':MC.Param2,'Param1':MC.Param1,'Param2':MC.Param2,
        'Param3':MC.Param3,'Param4':MC.Param4}
    def ao(ot,tg=0.0,wt=1.0,**kw):
        try:
            ix=m.NumberOfOperands+1; m.InsertRowAt(ix)
            op=m.GetOperandAt(ix); op.ChangeType(ot)
            op.Target=float(tg); op.Weight=float(wt)
            for pn,pv in kw.items():
                col=pm.get(pn)
                if col:
                    try:
                        cl=op.GetOperandCell(col)
                        if cl:
                            if isinstance(pv,int): cl.IntegerValue=pv
                            else: cl.DoubleValue=float(pv)
                    except: pass
        except: pass

    glass=[1,2,4,7,9,10]; air=[3,5,6,8]

    # --- ALWAYS: EFL + TOTR + thickness floor ---
    ao(MOT.EFFL,tg=EFL_T,wt=5.0,Wave=2)
    ao(MOT.TOTR,tg=TMAX,wt=1.0,Surf1=2,Surf2=13)
    for si in glass: ao(MOT.TTHI,tg=MCT,wt=5.0,Surf=si)
    for si in air: ao(MOT.TTHI,tg=MAIR,wt=5.0,Surf=si)
    ao(MOT.TTHI,tg=25.0,wt=1.0,Surf=11)  # BFD ~25-35mm

    # --- Stage-specific additions ---
    if st=="feasibility":
        # NO wizard — pure constraint-driven
        pass

    elif st=="iq":
        # Add Seidel + color
        for fl in[1,2,3]:
            ao(MOT.SPHA,tg=0.0,wt=0.3,Wave=2,Field=fl)
            ao(MOT.COMA,tg=0.0,wt=0.3,Wave=2,Field=fl)
            ao(MOT.ASTI,tg=0.0,wt=0.3,Wave=2,Field=fl)
        ao(MOT.AXCL,tg=0.0,wt=1.0,Wave1=1,Wave2=3)
        ao(MOT.LACL,tg=0.0,wt=0.5,Wave1=1,Wave2=3,Param3=2)
        ao(MOT.LACL,tg=0.0,wt=0.5,Wave1=1,Wave2=3,Param3=3)
        ao(MOT.FCUR,tg=0.0,wt=0.3,Wave=2,Field=2)
        ao(MOT.FCUR,tg=0.0,wt=0.3,Wave=2,Field=3)
        ao(MOT.DIST,tg=0.0,wt=0.3,Wave=2,Field=3)

    elif st=="balance":
        # Distortion + field balance + MTF
        ao(MOT.DIST,tg=0.0,wt=2.0,Wave=2,Field=2)
        ao(MOT.DIST,tg=0.0,wt=2.0,Wave=2,Field=3)
        for fl in[1,2,3]:
            ao(MOT.FCUR,tg=0.0,wt=0.5,Wave=2,Field=fl)
            ao(MOT.ASTI,tg=0.0,wt=0.5,Wave=2,Field=fl)
        ao(MOT.AXCL,tg=0.0,wt=1.0,Wave1=1,Wave2=3)
        for fl in[1,2,3]:
            ao(MOT.MTFT,tg=MTF_TGT,wt=0.5,Param1=MTF_F,Param2=2,Param3=fl)
            ao(MOT.MTFS,tg=MTF_TGT,wt=0.5,Param1=MTF_F,Param2=2,Param3=fl)

    elif st=="mfg":
        ao(MOT.TOTR,tg=TMAX,wt=3.0,Surf1=2,Surf2=13)  # stronger
        for si in glass:
            ao(MOT.MNCG,tg=MCT,wt=5.0,Surf=si)
            ao(MOT.MNEG,tg=MET,wt=5.0,Surf=si)

    # --- Wizard (only for non-feasibility stages) ---
    wiz_wt = 0.0 if st=="feasibility" else 0.05
    if wiz_wt>0:
        try:
            wz=m.SEQOptimizationWizard
            wz.IsAssumeAxialSymmetryUsed=False; wz.IsIgnoreLateralColorUsed=False
            wz.IsDeleteVignetteUsed=True; wz.Type=0; wz.OverallWeight=wiz_wt
            wz.Ring=3; wz.Grid=0; wz.Arm=2; wz.Reference=0
            wz.StartAt=m.NumberOfOperands+1; wz.OK()
        except Exception as e: log(f"  wiz err: {e}")

    log(f"  MF {st}: {m.NumberOfOperands} ops wizwt={wiz_wt}")


def set_vars(s,st):
    l=s.LDE
    rad=[1,2,3,4,5,7,8,9,10,11]  # 10 powered
    air=[3,5,6,8]; gl=[1,2,4,7,9,10]
    try: l.GetSurfaceAt(11).ThicknessCell.MakeSolveVariable()  # BFD
    except: pass

    if st=="feasibility":
        for si in rad:
            try: l.GetSurfaceAt(si).RadiusCell.MakeSolveVariable()
            except: pass
        log(f"  vars: {len(rad)} radii + BFD")
    elif st=="iq":
        for si in rad:
            try: l.GetSurfaceAt(si).RadiusCell.MakeSolveVariable()
            except: pass
        for si in air:
            try: l.GetSurfaceAt(si).ThicknessCell.MakeSolveVariable()
            except: pass
        log(f"  vars: {len(rad)} radii + {len(air)} air + BFD")
    else:
        for si in rad:
            try: l.GetSurfaceAt(si).RadiusCell.MakeSolveVariable()
            except: pass
        for si in gl+air:
            try: l.GetSurfaceAt(si).ThicknessCell.MakeSolveVariable()
            except: pass
        log(f"  vars: {len(rad)} radii + {len(gl)+len(air)} thick + BFD")


def optimize(s,st):
    log(f"  opt {st}...")
    tool=s.Tools.OpenLocalOptimization(); mv=None
    try:
        tool.NumberOfCycles=0
        tool.RunAndWaitForCompletion()
        try: mv=float(tool.CurrentMeritFunction)
        except: pass
    except Exception as e: log(f"  opt err: {e}")
    finally: tool.Close()
    log(f"  merit={mv}")
    return mv


def save_lens(s,st):
    p=str(OUT/f"dg6_{st}.zmx"); s.SaveAs(p); return p


def main():
    log("="*60)
    log(f"6-Elem Double Gauss 50mm F/2.8 — Production")
    log("="*60)

    a,s,Z,MOT=connect(); log("Connected")
    build(s,Z)
    b=fo(s,MOT); log(f"Baseline: {json.dumps(b)}")
    (OUT/"baseline.json").write_text(json.dumps(b,indent=2))
    exports(s,"baseline"); save_lens(s,"baseline")

    stages=["feasibility","iq","balance","mfg"]
    rs=[]
    for i,st in enumerate(stages,1):
        log(f"\n{'='*40}\nStage {i}: {st}\n{'='*40}")
        set_vars(s,st); build_mf(s,st,MOT)
        mv=optimize(s,st)
        ffo=fo(s,MOT); log(f"  FO: {json.dumps(ffo)}")
        exports(s,st); lp=save_lens(s,st)
        rs.append({"stage":st,"merit":mv,"fo":ffo,"lens":lp})
        (OUT/f"stage_{st}.json").write_text(json.dumps(rs[-1],indent=2))

    log("\n=== FINAL ===")
    ff=fo(s,MOT); err=abs(ff["efl"]-EFL_T)
    log(f"EFL={ff['efl']}mm err={err:.3f}mm ({err/EFL_T*100:.2f}%)")
    log(f"F/#={ff['fn']} Track={ff['totr']}mm")
    exports(s,"final"); fp=save_lens(s,"final")
    conv=PROJECT_DIR/"designs"/"double_gauss_6elem_final.zmx"
    conv.parent.mkdir(parents=True,exist_ok=True); shutil.copy2(fp,conv)
    (OUT/"summary.json").write_text(json.dumps({
        "design":"6-Elem Double Gauss 50mm F/2.8","ts":TS,
        "targets":{"efl":EFL_T,"fnum":FNUM,"hfov":HFOV,"tmax":TMAX,"mtf_t":MTF_TGT,"mtf_f":MTF_F},
        "final_fo":ff,"efl_err_mm":round(err,3),"efl_err_pct":round(err/EFL_T*100,2),
        "stages":rs,"final_lens":fp},indent=2))
    log(f"\nDONE: {fp}\nConv: {conv}")


if __name__=="__main__":
    main()
