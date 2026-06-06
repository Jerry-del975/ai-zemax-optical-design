"""
6-Element Double Gauss 50mm F/2.8 — Final Robust Design
==========================================================
Strategy: all curvatures variable from stage 1, very strong EFL constraint,
graduated release of thickness variables, wizard weight ramped up gradually.
"""

from __future__ import annotations
import json, os, shutil, sys
from datetime import datetime
from pathlib import Path
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_DIR = SCRIPT_DIR.parent
TS = datetime.now().strftime("%Y%m%d_%H%M%S")
OUT = PROJECT_DIR / "designs" / f"dg6_50mm_f28_{TS}"
OUT.mkdir(parents=True, exist_ok=True)

ZOS = r"D:\Program Files\Ansys Zemax OpticStudio 2024 R1.00"
EFL_T = 50.0; FNUM = 2.8; HFOV = 25.0
EPD_V = EFL_T / FNUM  # 17.857
TMAX = 70.0; MCT = 2.0; MET = 1.5; MAIR = 0.1
MTF_F = 30.0; MTF_T = 0.6

def log(m):
    t=datetime.now().strftime("%H:%M:%S"); print(f"[{t}] {m}",flush=True)
    with (OUT/"log.txt").open("a",encoding="utf-8") as f: f.write(f"[{t}] {m}\n")

def conn():
    sys.path.insert(0,ZOS)
    import clr; rr=Path(ZOS)
    clr.AddReference(str(rr/"ZOSAPI_NetHelper.dll"))
    clr.AddReference(str(rr/"ZOSAPI_Interfaces.dll"))
    clr.AddReference(str(rr/"ZOSAPI.dll"))
    import ZOSAPI_NetHelper; ZOSAPI_NetHelper.ZOSAPI_Initializer.Initialize(ZOS)
    import ZOSAPI
    a=ZOSAPI.ZOSAPI_Connection().ConnectAsExtension(0)
    if a is None or not a.IsValidLicenseForAPI or a.PrimarySystem is None:
        raise RuntimeError("Connect fail")
    s=a.PrimarySystem; op=s.MFE.GetOperandAt(1); MOT=type(op.Type)
    return a,s,ZOSAPI,MOT

def build(s,Z):
    l=s.LDE; s.New(False)
    while l.NumberOfSurfaces<13: l.InsertNewSurfaceAt(l.NumberOfSurfaces)
    s.SystemData.Aperture.ApertureType=Z.SystemData.ZemaxApertureType.EntrancePupilDiameter
    s.SystemData.Aperture.ApertureValue=EPD_V
    w=s.SystemData.Wavelengths
    while w.NumberOfWavelengths>1: w.RemoveWavelength(w.NumberOfWavelengths)
    w.GetWavelength(1).Wavelength=0.48613270
    w.AddWavelength(0.58756180,1.0); w.AddWavelength(0.65627250,1.0)
    f=s.SystemData.Fields
    while f.NumberOfFields>1: f.RemoveField(f.NumberOfFields)
    f.GetField(1).Y=0.0; f.AddField(0.0,17.5,1.0); f.AddField(0.0,25.0,1.0)
    try: s.SystemData.MaterialCatalogs.AddCatalog("SCHOTT")
    except: pass
    sd=[22,21,17,17,14,11,14,17,17,21,22,23.5]
    d=[(0,1e10,1e10,"",0),
       (1,12.0,6.0,"N-BK7",sd[0]),(2,48.0,3.5,"N-SF5",sd[1]),
       (3,18.0,0.3,"",sd[2]),(4,18.0,3.0,"N-SF5",sd[3]),
       (5,13.0,7.0,"",sd[4]),(6,1e10,7.0,"",sd[5]),
       (7,-15.0,3.0,"N-SF5",sd[6]),(8,-21.0,0.3,"",sd[7]),
       (9,-21.0,3.5,"N-SF5",sd[8]),(10,-48.0,6.0,"N-BK7",sd[9]),
       (11,-8.0,32.0,"",sd[10]),(12,1e10,0.0,"",sd[11])]
    for ix,rad,th,mat,sdi in d:
        ss=l.GetSurfaceAt(ix); ss.Radius=rad; ss.Thickness=th
        ss.Material=mat
        if sdi>0: ss.SemiDiameter=sdi
    l.GetSurfaceAt(6).IsStop=True
    tt=sum(l.GetSurfaceAt(i).Thickness for i in range(1,12))
    log(f"Build: 13surf, 6elem, track={tt:.1f}mm")

def fo(s,MOT):
    m=s.MFE; sv=m.NumberOfOperands
    from ZOSAPI.Editors.MFE import MeritColumn as MC
    def e(ot,**kw):
        m.InsertRowAt(m.NumberOfOperands+1); op=m.GetOperandAt(m.NumberOfOperands)
        op.ChangeType(ot)
        for ii,(_,v) in enumerate(kw.items(),1):
            try:
                c=op.GetOperandCell(getattr(MC,f'Param{ii}'))
                if c is not None:
                    if isinstance(v,int): c.IntegerValue=v
                    else: c.DoubleValue=float(v)
            except: pass
        m.CalculateMeritFunction(); return op.Value
    efl=e(MOT.EFFL,Wave=2); epd=e(MOT.EPDI,Wave=2)
    totr=e(MOT.TOTR,Surf1=2,Surf2=13)
    r={"efl":round(float(efl)if efl else 0,3),
       "epd":round(float(epd)if epd else 0,3),
       "fn":round(float(efl)/float(epd),3)if efl and epd and float(epd)>0 else None,
       "totr":round(float(totr),3)if totr else None}
    while m.NumberOfOperands>sv: m.RemoveOperandAt(m.NumberOfOperands)
    return r

def exp_anal(s,st):
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

def mf(s,stage,MOT):
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
                        if cl is not None:
                            if isinstance(pv,int): cl.IntegerValue=pv
                            else: cl.DoubleValue=float(pv)
                    except: pass
        except: pass

    glass=[1,2,4,7,9,10]   # 6 glass surfaces (center thickness = element CT)
    air_g=[3,5,6,8,11]      # air gap surfaces

    # ---- Stage-specific operands ----
    if stage=="feasibility":
        ao(MOT.EFFL,tg=EFL_T,wt=20.0,Wave=2)
        ao(MOT.TOTR,tg=TMAX,wt=3.0,Surf1=2,Surf2=13)
        # tight thickness minima
        for si in glass: ao(MOT.MNCG,tg=MCT,wt=15.0,Surf=si)
        for si in glass: ao(MOT.MNEG,tg=MET,wt=10.0,Surf=si)
        for si in air_g: ao(MOT.MNEA,tg=MAIR,wt=15.0,Surf=si)

    elif stage=="iq":  # image quality
        ao(MOT.EFFL,tg=EFL_T,wt=10.0,Wave=2)
        ao(MOT.TOTR,tg=TMAX,wt=3.0,Surf1=2,Surf2=13)
        for fl in[1,2,3]:
            ao(MOT.SPHA,tg=0.0,wt=0.3,Wave=2,Field=fl)
            ao(MOT.COMA,tg=0.0,wt=0.3,Wave=2,Field=fl)
            ao(MOT.ASTI,tg=0.0,wt=0.3,Wave=2,Field=fl)
        ao(MOT.AXCL,tg=0.0,wt=2.0,Wave1=1,Wave2=3)
        ao(MOT.LACL,tg=0.0,wt=1.0,Wave1=1,Wave2=3,Param3=2)
        ao(MOT.LACL,tg=0.0,wt=1.0,Wave1=1,Wave2=3,Param3=3)
        ao(MOT.FCUR,tg=0.0,wt=0.5,Wave=2,Field=2)
        ao(MOT.FCUR,tg=0.0,wt=0.5,Wave=2,Field=3)
        ao(MOT.DIST,tg=0.0,wt=0.5,Wave=2,Field=3)
        for si in glass: ao(MOT.MNCG,tg=MCT,wt=8.0,Surf=si)
        for si in glass: ao(MOT.MNEG,tg=MET,wt=5.0,Surf=si)
        for si in air_g: ao(MOT.MNEA,tg=MAIR,wt=8.0,Surf=si)

    elif stage=="balance":
        ao(MOT.EFFL,tg=EFL_T,wt=10.0,Wave=2)
        ao(MOT.TOTR,tg=TMAX,wt=3.0,Surf1=2,Surf2=13)
        ao(MOT.DIST,tg=0.0,wt=2.0,Wave=2,Field=2)
        ao(MOT.DIST,tg=0.0,wt=2.0,Wave=2,Field=3)
        for fl in[1,2,3]:
            ao(MOT.FCUR,tg=0.0,wt=0.8,Wave=2,Field=fl)
            ao(MOT.ASTI,tg=0.0,wt=0.8,Wave=2,Field=fl)
        ao(MOT.AXCL,tg=0.0,wt=1.5,Wave1=1,Wave2=3)
        ao(MOT.LACL,tg=0.0,wt=1.0,Wave1=1,Wave2=3,Param3=2)
        ao(MOT.LACL,tg=0.0,wt=1.0,Wave1=1,Wave2=3,Param3=3)
        # MTF targets (aggressive)
        for fl in[1,2,3]:
            ao(MOT.MTFT,tg=MTF_T,wt=1.0,Param1=MTF_F,Param2=2,Param3=fl)
            ao(MOT.MTFS,tg=MTF_T,wt=1.0,Param1=MTF_F,Param2=2,Param3=fl)
        for si in glass: ao(MOT.MNCG,tg=MCT,wt=8.0,Surf=si)
        for si in glass: ao(MOT.MNEG,tg=MET,wt=5.0,Surf=si)
        for si in air_g: ao(MOT.MNEA,tg=MAIR,wt=8.0,Surf=si)

    elif stage=="mfg":
        ao(MOT.EFFL,tg=EFL_T,wt=10.0,Wave=2)
        ao(MOT.TOTR,tg=TMAX,wt=5.0,Surf1=2,Surf2=13)
        for si in glass: ao(MOT.MNCG,tg=MCT,wt=15.0,Surf=si)
        for si in glass: ao(MOT.MNEG,tg=MET,wt=15.0,Surf=si)
        for si in air_g: ao(MOT.MNEA,tg=MAIR,wt=15.0,Surf=si)
        ao(MOT.DIST,tg=0.0,wt=0.5,Wave=2,Field=3)

    # Wizard: weight increases gradually
    wiz_wt = {"feasibility":0.03,"iq":0.08,"balance":0.15,"mfg":0.10}[stage]
    try:
        wz=m.SEQOptimizationWizard
        wz.IsAssumeAxialSymmetryUsed=False
        wz.IsIgnoreLateralColorUsed=False; wz.IsDeleteVignetteUsed=True
        wz.Type=0; wz.OverallWeight=wiz_wt; wz.Ring=3; wz.Grid=0; wz.Arm=2
        wz.Reference=0; wz.StartAt=m.NumberOfOperands+1; wz.OK()
    except Exception as e: log(f"  wiz err: {e}")
    log(f"  MF {stage}: {m.NumberOfOperands}ops, wizwt={wiz_wt}")


def vars(s,stage):
    l=s.LDE
    rad=[1,2,3,4,5,7,8,9,10,11]
    air=[3,5,6,8,11]
    thick=rad  # all thicknesses at powered surfaces + air gaps

    # BFD always
    try: l.GetSurfaceAt(11).ThicknessCell.MakeSolveVariable()
    except: pass

    if stage=="feasibility":
        # All radii + BFD only (keep thicknesses fixed to prevent collapse)
        for si in rad:
            try: l.GetSurfaceAt(si).RadiusCell.MakeSolveVariable()
            except: pass
        log(f"  vars: {len(rad)} radii + BFD")
    elif stage=="iq":
        for si in rad:
            try: l.GetSurfaceAt(si).RadiusCell.MakeSolveVariable()
            except: pass
        for si in air:
            try: l.GetSurfaceAt(si).ThicknessCell.MakeSolveVariable()
            except: pass
        log(f"  vars: {len(rad)} radii + {len(air)} air gaps + BFD")
    else:  # balance, mfg
        for si in rad:
            try: l.GetSurfaceAt(si).RadiusCell.MakeSolveVariable()
            except: pass
        for si in thick:
            try: l.GetSurfaceAt(si).ThicknessCell.MakeSolveVariable()
            except: pass
        log(f"  vars: {len(rad)} radii + {len(thick)} thick + BFD")


def opt(s,stage):
    log(f"  opt {stage}...")
    tool=s.Tools.OpenLocalOptimization()
    mv=None
    try:
        tool.NumberOfCycles=0; tool.RunAndWaitForCompletion()
        try: mv=float(tool.FinalMeritFunctionValue)
        except: pass
    except Exception as e: log(f"  opt err: {e}")
    finally: tool.Close()
    log(f"  merit={mv}")
    return mv


def save(s,st):
    p=str(OUT/f"dg6_{st}.zmx"); s.SaveAs(p); return p

def main():
    log("="*60)
    log(f"6-Elem Double Gauss: EFL={EFL_T} F/{FNUM} HFOV={HFOV}")
    log(f"T<=70 CT>={MCT} ET>={MET} MTF>={MTF_T}@{MTF_F}lp/mm")
    log("="*60)

    a,s,Z,MOT=conn(); log("connected")
    build(s,Z)
    b=fo(s,MOT)
    log(f"baseline FO: {json.dumps(b)}")
    (OUT/"baseline_fo.json").write_text(json.dumps(b,indent=2))
    exp_anal(s,"baseline"); save(s,"baseline")

    stages=["feasibility","iq","balance","mfg"]
    res=[]
    for i,st in enumerate(stages,1):
        log(f"\n{'='*40}\nStage {i}: {st}\n{'='*40}")
        vars(s,st); mf(s,st,MOT)
        mv=opt(s,st)
        ffo=fo(s,MOT)
        log(f"  FO: {json.dumps(ffo)}")
        exp_anal(s,st); lp=save(s,st)
        res.append({"stage":st,"merit":mv,"fo":ffo,"lens":lp})
        (OUT/f"stage_{st}.json").write_text(json.dumps(res[-1],indent=2))

    log("\n=== FINAL ===")
    ff=fo(s,MOT)
    err=abs(ff.get("efl",0)-EFL_T)
    log(f"EFL={ff['efl']}mm err={err:.3f}mm ({err/EFL_T*100:.2f}%)")
    log(f"F/#={ff['fn']} Track={ff['totr']}mm")
    exp_anal(s,"final"); fp=save(s,"final")
    conv=PROJECT_DIR/"designs"/"double_gauss_6elem_final.zmx"
    conv.parent.mkdir(parents=True,exist_ok=True); shutil.copy2(fp,conv)
    (OUT/"summary.json").write_text(json.dumps({
        "design":"6-Elem Double Gauss 50mm F/2.8",
        "timestamp":TS,"targets":{"efl":EFL_T,"fnum":FNUM,"hfov":HFOV,
        "tmax":TMAX,"mct":MCT,"met":MET,"mtf_t":MTF_T,"mtf_f":MTF_F},
        "final_fo":ff,"efl_err_mm":round(err,3),"efl_err_pct":round(err/EFL_T*100,2),
        "stages":res,"final_lens":fp},indent=2))
    log(f"\nDone! {fp}\nConv: {conv}")


if __name__=="__main__":
    main()
