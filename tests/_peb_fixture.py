"""PEB (2026-10) test fixture: a small web-tapered portal shed built the way the IN_Ex1 gold builds its frames
(peb_build stepped members, cfg['roof_planes'] rafters, cfg['flange_braces'] restraints), kept small so a full
pipeline run takes seconds.

Plan 12 m (X, 3 frame lines at 6.0 m) x 12 m (Y, single span, eaves at y = 0 and 12 m; a gable wind column at mid
span), eave 6.0 m, 1:10 (rise 0.6 m).  Main frame i = 1: tapered columns (pinned bases) and rafters tapered over
2.4 m, prismatic to the apex.  Gable frames i = 0, 2: post and beam.  X-bracing (CHS) in bay 0 of both long walls.
The load values are test inputs (not corpus evidence): this fixture exercises the PEB code paths, not a design.
"""
import math
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "steel_engine") not in sys.path:
    sys.path.insert(0, str(ROOT / "steel_engine"))

NX, NY = 2, 2
SX, SY = 6000.0, 6000.0
SPAN = NY * SY
H_EAVE, RISE = 6000.0, 600.0
COL_T = "TI250-500X150X10X5"
RAF_T = "TI500-300X150X10X5"
RAF_P = "WI300X150X8X5"
G_RAF = "WI250X125X8X5"
G_COL = "WI250X150X8X5"
W_COL = "WI300X150X8X5"
BRACE = "CHS114.3X3.6"
STRUT = "CHS114.3X3.6"
TAPER_LEN = 2400.0
GABLE = (0, NX)


def mini_peb_cfg(name="peb_mini"):
    import engine3d as E
    import peb_build as PB
    import sections as S
    import india_wind_tables as WT
    E.activate_si_units()
    custom = {}
    for lab in (COL_T, RAF_T, RAF_P, G_RAF, G_COL, W_COL):
        p_ = PB.parse(lab)
        if p_[0] == "tapered":
            custom[lab] = {"type": "tapered_I", "D_start_mm": p_[1], "D_end_mm": p_[2], "bf_mm": p_[3], "tf_mm": p_[4],
                           "tw_mm": p_[5], "n_seg": 4, "source": "test fixture"}
        else:
            custom[lab] = {"type": "welded_I", "D_mm": p_[1], "bf_mm": p_[2], "tf_mm": p_[3], "tw_mm": p_[4],
                           "source": "test fixture"}
    S.register_custom_sections({"custom_sections": custom})
    plane = {"axis": "Y", "eave_coords_mm": [0.0, SPAN], "ridge_coord_mm": SPAN / 2.0, "eave_z_mm": H_EAVE,
             "ridge_z_mm": H_EAVE + RISE, "lines": list(range(NX + 1)),
             "rafter_members": {"lo": [(TAPER_LEN, RAF_T), (SPAN / 2.0, RAF_P)]},
             "rafter_members_by_line": {0: {"lo": [(SPAN / 2.0, G_RAF)]}, NX: {"lo": [(SPAN / 2.0, G_RAF)]}},
             "gravity_lines": list(GABLE), "braced_lines": list(GABLE), "ridge_sec": STRUT}
    L_M, W_M = NX * SX / 1000.0, SPAN / 1000.0

    def build(cfg, transf="PDelta"):
        import openseespy.opensees as ops
        import roof_geometry as RG
        PB.reset()
        ops.wipe(); ops.model("basic", "-ndm", 3, "-ndf", 6)
        XY = lambda i, j: (i * SX, j * SY)
        present = {0: set(), 1: set()}
        for i in range(NX + 1):
            for j in (range(NY + 1) if i in GABLE else (0, NY)):
                x, y = XY(i, j)
                ops.node(E.ntag(i, j, 0), x, y, 0.0)
                ops.fix(E.ntag(i, j, 0), 1, 1, 1, 0, 0, 0)
                ops.node(E.ntag(i, j, 1), x, y, RG.lifted_z(cfg, 1, x, y) or H_EAVE)
                present[0].add((i, j)); present[1].add((i, j))
        ops.node(E.mtag(1), L_M * 500.0, W_M * 500.0, H_EAVE); ops.fix(E.mtag(1), 0, 0, 1, 1, 1, 0)
        et, eles = 1, []
        for (i, j) in sorted(present[0]):
            nb, nt = E.ntag(i, j, 0), E.ntag(i, j, 1)
            if i in GABLE:
                sec, sd = (G_COL, "Y") if j in (0, NY) else (W_COL, "X")
                et = PB.column(et, eles, nb, nt, [(None, sec)], sd, i=i, j=j, releases="J")
            else:
                et = PB.column(et, eles, nb, nt, [(None, COL_T)], "Y", i=i, j=j)
        et = RG.add_plane_members(cfg, 1, XY, present[1], et, eles)
        for j in (0, NY):
            for i in range(NX):
                E.add_beam(et, E.ntag(i, j, 1), E.ntag(i + 1, j, 1), STRUT, releases=("both", "none"))
                eles.append((et, "beam", STRUT, E.ntag(i, j, 1), E.ntag(i + 1, j, 1))); et += 1
        ops.uniaxialMaterial("Elastic", 1, E.E)
        A = E.Ipack(BRACE)[0]
        for j in (0, NY):
            for (a, b) in ((E.ntag(0, j, 0), E.ntag(1, j, 1)), (E.ntag(1, j, 0), E.ntag(0, j, 1))):
                ops.element("Truss", et, a, b, A, 1); eles.append((et, "brace", BRACE, a, b)); et += 1
        RG.tie_diaphragm(cfg, 1, E.mtag(1), [E.ntag(i, j, 1) for (i, j) in sorted(present[1])], H_EAVE)
        w = E.floor_w(cfg, 1); m = w / E.g
        ops.mass(E.mtag(1), m, m, 0.0, 0.0, 0.0, m * ((L_M * 1e3) ** 2 + (W_M * 1e3) ** 2) / 12.0)
        return PB.finish({"cm": {1: (L_M * 500.0, W_M * 500.0)}, "present": present, "z": [0.0, H_EAVE], "NF": 1,
                          "ele": eles})

    pitch = math.degrees(math.atan(RISE / (SPAN / 2.0)))
    pd = 0.40
    cpe0 = {"A": 0.7, "B": -0.25, "C": -0.6, "D": -0.6}
    cpe90 = {"A": -0.5, "B": -0.5, "C": 0.7, "D": -0.1}
    mw = WT.lowrise_member_wind(pd, H_EAVE / 1000.0, W_M, L_M, pitch, 0.05, ridge_axis="X",
                                walls={0: {"Cpe": cpe0, "resolved_via": "test"}, 90: {"Cpe": cpe90, "resolved_via": "test"}},
                                roof={"EF": -0.9, "GH": -0.4, "EG": -0.8, "FH": -0.4})
    F_Y = (cpe0["A"] - cpe0["B"]) * pd * L_M * H_EAVE / 2000.0
    F_X = (cpe90["C"] - cpe90["D"]) * pd * W_M * (H_EAVE + RISE) / 2000.0
    cfg = dict(
        name=name, jurisdiction="india", units="N-mm", system="OMRF+OCBF", system_y="OMRF", system_x="OCBF",
        R_x=4.0, R_y=3.0, NX=NX, NY=NY, SX=SX, SY=SY, heights=[H_EAVE],
        D_floor=0.30, D_roof=0.30, L_floor=0.0, Lr=0.75, clad=0.10, snow=0.0,
        partition_load_kNm2=0.0, partition_seismic_kNm2=0.0, partitions=False,
        base="pinned", diaphragm="rigid", diaphragm_type="braced_roof", building_type="industrial",
        deflection_key_roof="rafter_profiled_sheeting", cladding_brittle=False, roof_pitch_deg=round(pitch, 3),
        model={"bases": "pinned", "joints": "rigid end-plate knees and apex", "gravity": "portal frames"},
        occupancy={"use": "test shed (industrial)", "area_m2": L_M * W_M},
        steel_grade="E350", plate_grade="E250", tube_grade="YSt 310", tube_process="HFS",
        brace_grade="YSt 310", brace_process="HFS", brace_config="X",
        col=COL_T, beam=RAF_P, brace=BRACE, custom_build=build, custom_sections=custom, taper_nseg=4,
        roof_planes=[plane],
        flange_braces={"rafter": {"purlins_mm": [1200.0 * n for n in range(1, 5)] + [5800.0],
                                  "fly_braces_mm": [1200.0, 2400.0, 4800.0]},
                       "column": {"girts_mm": [1500.0, 3000.0, 4500.0], "fly_braces_mm": [3000.0, 4500.0]}},
        K_factors={"lateral_col": {"Kz": 1.0, "Ky": 1.0}, "gravity_col": {"Kz": 1.0, "Ky": 1.0},
                   "roof": {"Kz": 1.0, "Ky": 1.0}, "brace": {"Kz": 0.5, "Ky": 0.5}, "basis": "test fixture"},
        sway_frame=True, analyses=["ESM"], drift_limit=0.004,
        seis={"Z": 0.10, "zone": "II", "I": 1.0, "R": 3.0, "soil": "II"},
    )
    esm = E.esm_from_model(cfg, {"X": 0.09 * 6.3 / math.sqrt(L_M), "Y": 0.085 * 6.3 ** 0.75}, soil="II")
    ss = dict(esm["seismic_summary"])
    ss.update(system="OMRF+OCBF", zone="II", Z=0.10, R=3.0, R_x=4.0, R_y=3.0, I=1.0, soil="II")
    cfg["load_plan"] = {
        "jurisdiction": "india", "partial_factors_cite": "IS 800:2007 Table 4", "story_forces_units": "N",
        "seismic_summary": ss,
        "story_forces": {"EQ_X": esm["story_forces"]["EQ_X"], "EQ_Y": esm["story_forces"]["EQ_Y"],
                         "W_X": {"1": [F_X * 1000.0, 0.0, 0.0]}, "W_Y": {"1": [0.0, F_Y * 1000.0, 0.0]}},
        "wind_summary": {"code": "IS 875 (Part 3):2015", "Vb_mps": 33.0, "Vb_source": "test", "terrain_category": 3,
                         "k1": 1.0, "k2": 0.91, "k3": 1.0, "k4": 1.0, "Kd": 0.9, "pz_kNm2": 0.50, "pd_kNm2": pd,
                         "cyclone_belt": False, "structure_class": "industrial", "Cpi": 0.2},
        "member_wind": mw["patterns"], "retrieval": _retrieval(), "combinations": "auto",
    }
    ss["Ta_formula"] = "Y (OMRF): 0.085 h^0.75 (7.6.2(a)); X (OCBF): 0.09 h/sqrt(d) (7.6.2(c))"
    return cfg


# stored corpus hits of the shared IN_Ex13 fixture that do not depend on the site (formulae, tables, factors)
_ROWS = ("design wind speed Vz = Vb k1 k2 k3 k4", "Table 1 Risk Coefficient k1 general buildings 50 years",
         "imposed loads on roofs Table 2 access not provided", "importance factor I Table 8 / 6.4.2",
         "Table 4 partial safety factors for loads")


def _retrieval():
    import json
    fix = ROOT / "tests" / "fixtures" / "IN_Ex13"
    idx = json.load(open(fix / "rag_index.json", encoding="utf-8"))
    rows = [dict(r) for r in json.load(open(fix / "load_plan.json", encoding="utf-8"))["retrieval"]
            if r.get("query") in _ROWS]
    for r in rows:
        r.update(idx[r["query"]])
    return rows


def stage_rag(job_root):
    """Copy the stored IN_Ex13 rag/ hits into the job folder (the evidence gate reads them)."""
    import shutil
    dst = os.path.join(str(job_root), "rag")
    if os.path.isdir(dst):
        shutil.rmtree(dst)
    shutil.copytree(str(ROOT / "tests" / "fixtures" / "IN_Ex13" / "rag"), dst)
    return dst
