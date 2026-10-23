"""PEB-LEVERS test job: the small tapered portal of tests/_peb_fixture.py written as a job script (module-level section
constants, declared knee / apex / splice end plates, pinned bases with shear keys), so that the auto-sizer
(steel_engine/peb_autosize.py) can rewrite its constants.  Test inputs, not a design: kept small so a full pipeline
run takes seconds."""
import math
import os
import sys

import engine3d as E
import peb_build as PB
import sections as S

_REPO = os.path.dirname(os.path.dirname(os.path.abspath(PB.__file__)))
sys.path.insert(0, os.path.join(_REPO, "tests"))
import _peb_fixture as F          # noqa: E402

E.activate_si_units()

COL_T = "TI250-500X150X10X5"
RAF_T = "TI500-300X150X10X5"
RAF_P = "WI300X150X8X5"
BRACE = "CHS114.3X3.6"
LR = 0.75
R_Y, R_X = 3.0, 4.0
SOLAR_PV = 0.0

F.COL_T, F.RAF_T, F.RAF_P, F.BRACE = COL_T, RAF_T, RAF_P, BRACE
cfg = F.mini_peb_cfg(globals().get("JOB_NAME", "peb_levers_mini"))
cfg.update(Lr=LR, R_y=R_Y, R_x=R_X, D_roof_pv=SOLAR_PV)
cfg["custom_sections"].update({lab: ({"type": "tapered_I", "D_start_mm": PB.parse(lab)[1], "D_end_mm": PB.parse(lab)[2],
                                      "bf_mm": PB.parse(lab)[3], "tf_mm": PB.parse(lab)[4], "tw_mm": PB.parse(lab)[5],
                                      "n_seg": 4, "source": "test"} if PB.parse(lab)[0] == "tapered" else
                                     {"type": "welded_I", "D_mm": PB.parse(lab)[1], "bf_mm": PB.parse(lab)[2],
                                      "tf_mm": PB.parse(lab)[3], "tw_mm": PB.parse(lab)[4], "source": "test"})
                                  for lab in (COL_T, RAF_T, RAF_P)})
S.register_custom_sections(cfg)


def bolted_end_plate(sec, *, t, d_bolt, n_out, n_in, pitch, b_plate, grade="10.9", plate_grade="E250", ext=60.0,
                     weld=8.0, gauge=None, web_doubler=0.0, member_fy=350.0):
    p = S.props(sec)
    hf = p["d"] - p["tf"]
    g = gauge or (120.0 if d_bolt >= 30 else 110.0)
    lv = max(ext - p["tf"] / 2.0 - weld, g / 2.0 - p["tw"] / 2.0 - weld)
    rows = ([{"h_mm": round(hf + ext + k * pitch, 1), "n_pairs": 1} for k in range(n_out)] +
            [{"h_mm": round(hf - ext - k * pitch, 1), "n_pairs": 1} for k in range(n_in)
             if hf - ext - k * pitch >= hf / 2.0 - 1.0])
    fy = 250.0 if t <= 20 else 240.0 if t <= 40 else 230.0
    return {"rows": rows, "d_mm": d_bolt, "grade": grade, "t_plate_mm": t, "fy_plate_MPa": fy,
            "plate_grade": plate_grade, "be_mm": round(min(pitch, b_plate / 2.0), 1), "lv_mm": round(lv, 1),
            "le_mm": min(50.0, (b_plate - g) / 2.0), "pretensioned": True, "bolt_type": "HSFG",
            "web_t_mm": float(p["tw"]) + float(web_doubler), "web_fy_MPa": member_fy, "hf_mm": hf}


KNEE_FACE = PB.section_at(RAF_T, 0.0)
BASE_SEC = PB.section_at(COL_T, 1.0 / 8.0)
COL_TOP = PB.section_at(COL_T, 1.0)
KEY = {"capacity_N": 0.0}


def _key(b, t, h, fy=240.0, fck=30.0):
    gm0 = 1.1
    bear = 0.45 * fck * b * (h - 25.0)
    shear = b * t * fy / (math.sqrt(3.0) * gm0)
    lever = 50.0 + 25.0 + (h - 25.0) / 2.0
    bend = (t * b ** 2 / 4.0) * fy / gm0 / lever
    return {"capacity_N": round(min(bear, shear, bend), 0), "size": "cruciform 2 x %g x %g, %g deep" % (b, t, h),
            "mass_kg": round(2 * b * t * (h + 50.0) * 7.85e-6, 1), "source": "test key", "cite": "test key"}


cfg["connections"] = {
    "beam_column": {KNEE_FACE: {"type": "end_plate", "bolt_type": "HSFG", "weld_type": "cjp", "symmetric": True,
                                "end_plate": bolted_end_plate(KNEE_FACE, t=25.0, d_bolt=20, n_out=1, n_in=3, pitch=90.0,
                                                              b_plate=200.0),
                                "plate_b_mm": 200.0, "gauge_mm": 110.0, "column_flange_t_mm": 20.0,
                                "bom_plates": [{"item": "knee-zone column flange plates", "part": "plate",
                                                "size": "150 x 20 x 600", "qty_per_joint": 1,
                                                "kg_each": round(150 * 10 * 600 * 7.85e-6, 1)}]}},
    "knee_panel": {"diagonal_stiffener": {"n": 2, "b_mm": 60.0, "t_mm": 12.0, "fy_MPa": 250.0},
                   "flange_stiffener": {"n": 2, "b_mm": 60.0, "t_mm": 12.0, "fy_MPa": 250.0}},
    "rafter_splice": {
        "apex": {"end_plate": bolted_end_plate(RAF_P, t=25.0, d_bolt=20, n_out=1, n_in=2, pitch=90.0, b_plate=180.0),
                 "symmetric": True, "plate_b_mm": 180.0,
                 "shear_bolts": {"n_bolts": 2, "d_mm": 20, "grade": "10.9",
                                 "surface": "blasted_short_or_grit_loose_rust_removed"},
                 "bolt_type": "HSFG", "weld_type": "cjp"},
        "rafter_splice": {"end_plate": bolted_end_plate(RAF_P, t=20.0, d_bolt=20, n_out=1, n_in=1, pitch=90.0,
                                                        b_plate=180.0),
                          "symmetric": True, "plate_b_mm": 180.0,
                          "shear_bolts": {"n_bolts": 2, "d_mm": 20, "grade": "10.9",
                                          "surface": "blasted_short_or_grit_loose_rust_removed"},
                          "bolt_type": "HSFG", "weld_type": "cjp"}},
    "column_base": {BASE_SEC: {"B_mm": 300.0, "L_mm": 350.0, "t_plate_mm": 20.0, "fy_plate_MPa": 250.0,
                               "plate_grade": "E250", "fck_MPa": 30.0, "fixed": False,
                               "anchors": {"n_total": 4, "n_tension": 2, "d_mm": 20, "grade": "8.8", "f_mm": 100.0,
                                           "pitch_mm": 120.0, "edge_mm": 50.0, "n_per_row": 2, "Anb_mm2": 245.0},
                               "shear_key": _key(300.0, 32.0, 300.0)}},
}
cfg["peb_connection_mass_kg"] = 200.0
