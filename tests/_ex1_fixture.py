"""Shared IN_Ex1 fixture (tests/fixtures/IN_Ex1 = the shipped build_and_run.py + load_plan.json).

`ex1_cfg(upgrade=True)` returns the Ex1 cfg upgraded to the WP1 schema the way an agent must now
write it: explicit story_forces_units, fE/fW on every lateral combination (read from the label),
occupancy, and no ASCE shims.  `upgrade=False` returns the cfg as shipped.
"""
import copy
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FIX = ROOT / "tests" / "fixtures" / "IN_Ex1"
for p in (str(ROOT / "steel_engine"), str(FIX)):
    if p not in sys.path:
        sys.path.insert(0, p)


def ex1_cfg(upgrade=True):
    os.environ.setdefault("STELTIC_TEST_JOBS", str(ROOT / "tests" / "_jobs"))
    import build_and_run as B
    cfg, seis = B.build_cfg()
    if not upgrade:
        return cfg, seis
    import india_loads as IL
    plan = cfg["load_plan"]
    plan["story_forces_units"] = "N"
    for c in plan["combinations"]:
        ref = c.get("lateral_ref")
        if ref:
            f = IL.label_lateral_terms(c["label"])[0][0]
            c["fE" if IL.lateral_kind(ref) == "EQ" else "fW"] = f
    for k in ("SDS", "SD1", "Cd", "Om0", "Ct", "x", "Cu", "Ie"):
        cfg["seis"].pop(k, None)
    cfg["occupancy"] = {"use": "office", "area_m2": 3600.0}
    return cfg, seis


def ex1_cfg_is(design=True, embedment=None):
    """Ex1 rebuilt the way the India contract now requires (spec WP6 row Ex1 + D8/D9):
    I = 1.2 (office > 2,000 m2, D8), office imposed load 4.0 kN/m2 (D9), IS 875-2 3.1.2 partition
    allowance 1.0 kN/m2 for design and 0.5 kN/m2 in W (7.3.6), member self-weight in DL and W,
    ESM summary recomputed from the engine seismic weights, generated combinations, RSA.
    design=True adds the wave-2 design inputs (apply_wave2_design)."""
    cfg, seis = ex1_cfg(upgrade=True)
    if design:
        return apply_wave2_design(cfg, embedment=embedment), None
    import engine3d as E
    cfg.update(L_floor=4.0, partition_load_kNm2=1.0, deck_span="X", steel_grade="E250BR",
               brace_grade="YSt 310", brace_process="HFS", analyses=["RSA"], brace_config="X")
    cfg["seis"].update(I=1.2)
    plan = cfg["load_plan"]
    ss = plan["seismic_summary"]
    ss.update(I=1.2, soil="II")
    for k in ("Cs", "V", "Tu", "Ta", "k", "W", "Fx"):
        ss.pop(k, None)
    r = E.esm_from_model(cfg, {"X": ss["Ta_x_s"], "Y": ss["Ta_y_s"]}, soil="II")
    ss.update(r["seismic_summary"])
    ss.update(system="SCBF", zone="IV", Z=0.24, R=4.5, Ta_formula="0.09 h/sqrt(d) (7.6.2(c) all other buildings)")
    sf = plan["story_forces"]
    for d in ("X", "Y"):
        sf["EQ_" + d] = r["story_forces"]["EQ_" + d]
    plan["story_forces_units"] = "N"
    plan["combinations"] = "auto"
    plan["wind_summary"].update(cyclone_belt=False, cyclone_belt_cite="New Delhi: inland, outside the 60 km "
                                "east-coast/Gujarat belt of IS 875-3 6.3.4", Ka_basis="frame_tributary")
    return cfg, r


# ---------------------------------------------------------------------------------------------------------------
# Wave-2 design inputs (HR-INTEGRATE) -- shared with scratch/HR-INTEGRATE/jobs/Ex1/build_and_run.py
# ---------------------------------------------------------------------------------------------------------------
import math


def col_sec(i, j, k, perim):
    if k <= 2:
        return "WPB300X300X117.03" if perim else "WPB300X300X88.34"
    if k <= 4:
        return "WPB300X300X100.85" if perim else "WPB300X300X69.8"
    return "WPB250X250X73.15" if perim else "MB300"


def releases(i, j, k, dirn):
    return ("both", "none")          # every beam pinned: gravity beams and braced-bay beams (gusset + shear tab)


def apply_wave2_design(cfg, *, embedment=None):
    """Wave-2 design inputs for IN_Ex1 (HR-INTEGRATE): I 1.2, office 4.0 kN/m2, partitions, RSA, plastic SCBF
    columns, IS 808 E250 B0 braces, declared connections / bases / splices, composite scope.  `embedment` =
    {capacity_N, cite} is the EOR anchorage input (None -> found:false, blocks COMPLETE)."""
    import engine3d as E
    import sections as S
    plan = cfg["load_plan"]
    cfg["occupancy"] = {"use": "office", "area_m2": 30.0 * 24.0 * 5, "persons": None,
                        "note": "office > 2,000 m2 -> I = 1.2 (D8, IS 1893 Table 8 (ii))"}
    # ---- loads (D9 / IS 875-2 3.1.2 / IS 1893 7.3.6) ----
    cfg.update(L_floor=4.0, partition_load_kNm2=1.0, partition_seismic_kNm2=0.5, deck_span="X",
               steel_grade="E250 B0", brace_grade="E250 B0", brace_process=None, analyses=["RSA"], brace_config="X",
               floor_system="one-way composite metal deck", composite_scope="bare_steel",
               construction_stage={"D_wet_kNm2": 3.0, "L_const_kNm2": 0.75, "LLT_mm": 6000.0,
                                   "cite": "unshored wet concrete + 0.75 kN/m2 construction imposed load; compression "
                                           "flange unrestrained until the deck is fixed (IS 800 8.2.2)"})
    plan["gravity_summary"].update(L_floor_kNm2=4.0, partition_kNm2=1.0,
                                   cite_LL="IS 875 (Part 2):1987 Table 1 office 4.0 kN/m2 (no separate storage, D9); "
                                           "3.1.2 partitions 1.0 kN/m2")
    cfg["seis"].update(I=1.2)
    ss = plan["seismic_summary"]
    ss.update(I=1.2, soil="II")
    for k in ("Cs", "V", "Tu", "Ta", "k", "W", "Fx"):
        ss.pop(k, None)
    # ---- sections / SFRS layout ----
    cfg.update(col="WPB300X300X100.85", brace="WPB200X200X50.92", col_sec=col_sec, releases=releases,
               brace_orientation="web perpendicular to the frame plane (minor-axis buckling in plane)")
    cfg["LLT_sag_mm"] = {"floor": 600.0, "roof": 600.0}       # deck fastener spacing (compression flange restrained)
    cfg["LLT_hog_mm"] = {"floor": 6000.0, "roof": 6000.0}     # no fly braces declared: full span
    cfg["K_factors"] = {"lateral_col": {"Kz": 1.0, "Ky": 1.0}, "gravity_col": {"Kz": 1.0, "Ky": 1.0},
                        "brace": {"Kz": 1.0, "Ky": 1.0}, "basis": "IS 800 Table 11 (braced frame, both ends restrained)"}
    cfg["sway_frame"] = False
    cfg["column_lateral_support_both_flanges"] = True
    # ---- seismic weight / ESM summary recomputed from the engine (same W as the model mass, WP1.6) ----
    r = E.esm_from_model(cfg, {"X": ss["Ta_x_s"], "Y": ss["Ta_y_s"]}, soil="II")
    ss.update(r["seismic_summary"])
    ss.update(system="SCBF", zone="IV", Z=0.24, R=4.5, Ta_formula="0.09 h/sqrt(d) (7.6.2(c) all other buildings)")
    for d in ("X", "Y"):
        plan["story_forces"]["EQ_" + d] = r["story_forces"]["EQ_" + d]
    plan["combinations"] = "auto"
    plan["wind_summary"].update(cyclone_belt=False, Ka_basis="frame_tributary",
                                cyclone_belt_cite="New Delhi: inland, outside the 60 km east-coast/Gujarat belt (IS 875-3 6.3.4)")
    # ---- connections (declared geometry -> IS 800 checks; never sized from demand) ----
    br = S.props("WPB200X200X50.92")
    Lw, tg, fyg, fug = 600.0, 20.0, 250.0, 410.0
    bw = br["bf"] + 2 * Lw * math.tan(math.radians(30))
    cfg["connections"] = {
        "brace_end": {"default": {
            "weld_type": "cjp", "welds": {"cjp": {"t_mm": br["tf"]}, "length_mm": Lw, "fy_MPa": 250.0, "n_sides": 4,
                                          "site": False},
            "gusset": {"t_mm": tg, "fy_MPa": fyg, "fu_MPa": fug, "w_start_mm": br["bf"], "L_conn_mm": Lw,
                       "L_unbraced_mm": 300.0, "K": 0.65,
                       "Avg_mm2": 2 * Lw * tg, "Avn_mm2": 2 * Lw * tg, "Atg_mm2": br["bf"] * tg, "Atn_mm2": br["bf"] * tg},
            "An_mm2": br["A"],
            "moment_capacity_Nmm": (tg * bw ** 2 / 4.0) * fyg / 1.1,
            "moment_capacity_cite": "gusset in-plane plastic moment on the Whitmore width (brace minor axis in the "
                                    "frame plane): t bw^2/4 fy/gamma_m0",
            "bolts_and_welds_share": False,
            "K_basis": "gusset K = 0.65 (compact corner gusset, engineering practice, EOR)"}},
        "beam_shear": {
            "default": {"t_plate_mm": 10.0, "h_plate_mm": 300.0, "fy_plate_MPa": 250.0, "fu_plate_MPa": 410.0,
                        "bolt_type": "HSFG", "slip_surface": "clean_mill_scale",
                        "bolts": {"n_bolts": 4, "d_mm": 20, "grade": "8.8", "t_mm": 7.6, "fu_plate_MPa": 410.0,
                                  "e_mm": 40.0, "p_mm": 70.0, "d0_mm": 22.0, "nn": 1, "ns": 0},
                        "block_shear_areas": {"Avg_mm2": (40 + 3 * 70) * 10.0, "Avn_mm2": (40 + 3 * 70 - 3.5 * 22) * 10.0,
                                              "Atg_mm2": 40.0 * 10.0, "Atn_mm2": (40 - 11) * 10.0},
                        "cjp": {"t_mm": 10.0, "length_mm": 300.0, "fy_MPa": 250.0, "n_sides": 1, "site": True},
                        "weld_type": "cjp"},
            "NPB400X180X57.38": {"t_plate_mm": 10.0, "h_plate_mm": 260.0, "fy_plate_MPa": 250.0, "fu_plate_MPa": 410.0,
                                 "bolt_type": "HSFG", "slip_surface": "clean_mill_scale",
                                 "bolts": {"n_bolts": 3, "d_mm": 20, "grade": "8.8", "t_mm": 7.0, "fu_plate_MPa": 410.0,
                                           "e_mm": 40.0, "p_mm": 70.0, "d0_mm": 22.0, "nn": 1, "ns": 0},
                                 "block_shear_areas": {"Avg_mm2": (40 + 2 * 70) * 10.0, "Avn_mm2": (40 + 2 * 70 - 2.5 * 22) * 10.0,
                                                       "Atg_mm2": 40.0 * 10.0, "Atn_mm2": (40 - 11) * 10.0},
                                 "cjp": {"t_mm": 10.0, "length_mm": 260.0, "fy_MPa": 250.0, "n_sides": 1, "site": True},
                                 "weld_type": "cjp"}},
        "column_base": {
            "default": {"B_mm": 750.0, "L_mm": 750.0, "t_plate_mm": 110.0, "fy_plate_MPa": 230.0, "fck_MPa": 30.0,
                        "fixed": True,
                        "anchors": {"n_total": 8, "n_tension": 4, "d_mm": 48, "grade": "8.8", "f_mm": 275.0,
                                    "pitch_mm": 150.0, "edge_mm": 100.0, "n_per_row": 4, "Anb_mm2": 1473.0},
                        "Ec_note": "Ec = 5000 sqrt(30) = 27386 MPa (IS 456:2000 6.2.3.1); plate fy 230 (E250, t > 40 mm, "
                                   "IS 2062 Table 3); M48 Anb 1473 mm2 (IS 4000 Table 2 not listing M48: thread stress "
                                   "area per IS 1367 = 0.7854 (d - 0.9382 p)^2, p = 5 mm)",
                        "detail_note": "SFRS fixed base for 1.1 Ry Mpc = 716 kN-m (IS 18168 9.3): unstiffened plate "
                                       "-> 110 mm; a stiffened base is the practical alternative (not modelled)",
                        "embedment": embedment},
            "WPB300X300X88.34": {"B_mm": 600.0, "L_mm": 600.0, "t_plate_mm": 45.0, "fy_plate_MPa": 240.0, "fck_MPa": 30.0,
                                 "fixed": False,
                                 "anchors": {"n_total": 4, "n_tension": 2, "d_mm": 24, "grade": "4.6", "f_mm": 240.0,
                                             "pitch_mm": 120.0, "edge_mm": 60.0, "n_per_row": 2}}},
        "column_splice": {
            "default": {"type": "flange_plates",
                        "plate": {"A_mm2": 300.0 * 25.0, "fy_MPa": 250.0},
                        "bolt_type": "HSFG",
                        "bolts": {"n_bolts": 12, "d_mm": 24, "grade": "8.8", "t_mm": 16.0, "fu_plate_MPa": 410.0,
                                  "e_mm": 45.0, "p_mm": 75.0, "d0_mm": 26.0, "nn": 0, "ns": 2}},
            "WPB300X300X117.03": {"none": True, "note": "ground-storey column length: no splice"},
            "WPB300X300X88.34": {"none": True, "note": "ground-storey gravity column: no splice"},
            "WPB300X300X69.8": {"type": "flange_plates", "plate": {"A_mm2": 300.0 * 12.0, "fy_MPa": 250.0},
                                "bolts": {"n_bolts": 6, "d_mm": 20, "grade": "8.8", "t_mm": 10.5, "fu_plate_MPa": 410.0,
                                          "e_mm": 40.0, "p_mm": 70.0, "d0_mm": 22.0, "nn": 0, "ns": 2}},
            "MB300": {"type": "flange_plates", "plate": {"A_mm2": 140.0 * 12.0, "fy_MPa": 250.0},
                      "bolts": {"n_bolts": 4, "d_mm": 20, "grade": "8.8", "t_mm": 13.1, "fu_plate_MPa": 410.0,
                                "e_mm": 40.0, "p_mm": 70.0, "d0_mm": 22.0, "nn": 0, "ns": 2}}},
    }
    cfg["notes"] = ("IN_Ex1 5-storey office perimeter SCBF (X-bracing), New Delhi Zone IV, I 1.2, RSA. IS 808 sections, "
                    "IS 2062 E250 B0. Composite metal deck: bare-steel scope (IS 11384 not in corpus) + construction stage. "
                    "Anchorage embedment: EOR input required (IS 456 not in corpus).")
    return cfg


