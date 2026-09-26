"""H08 (HR-B-06, HR-B-15, HR-D-04, HR-C-07, HR-E-11, CFS-B-04 HR part, NEW x2): SFRS base demand per case."""
import os
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "steel_engine"))

import india_connections as C
import india_connection_design as CD
import india_is800 as I8
import india_is800_s12 as S12
import sections as S

SEC = "WPB300X300X117.03"


def _md(fixed, cases, **col):
    m = dict({"id": "c1", "section": SEC, "grade": "E250 B0", "role": "column", "sfrs": True, "L_mm": 4000.0}, **col)
    return {"members": [m],
            "bases": [{"id": "b1", "column_member_id": "c1", "fixed": fixed, "B_mm": 700, "L_mm": 700, "t_plate_mm": 60,
                       "fy_plate_MPa": 250, "fck_MPa": 30,
                       "anchors": {"n_total": 4, "n_tension": 2, "d_mm": 30, "grade": "8.8", "f_mm": 270},
                       "load_cases": cases}]}


def _fy(p):
    return I8.material_for_section(p, "E250 B0")["fy_MPa"]


def test_pinned_base_min_moment_in_each_case_and_1p2vd_checked():
    cases = [{"combo": "1.5DL+1.5EQ_X", "P_N": 800e3, "M_Nmm": 0.0, "V_N": 50e3},
             {"combo": "1.5DL+1.5LL", "P_N": 1500e3, "M_Nmm": 0.0, "V_N": 10e3}]
    r = S12.base_checks("SCBF", _md(False, cases), {"zone": "IV"})[0]
    p = S.props(SEC)
    fy = _fy(p)
    Mmin = 0.5 * 1.4 * p["Sx"] * fy
    Vd = I8.shear_capacity(p, fy, axis="z")["Vd_N"]
    assert len(r["per_case"]) == 2
    for c in r["per_case"]:
        assert c["M_Nmm"] == pytest.approx(Mmin, rel=1e-9)            # 9.4 minimum kept in every case
        assert c["V_N"] >= 1.2 * Vd - 1e-6                           # 12.12.2 checked, not only reported
    assert r["detail"]["checks"]["shear_path"]["value"] >= 1.2 * Vd - 1e-6


def test_fixed_base_capacity_moment_only_with_seismic_cases_and_mpc():
    cases = [{"combo": "1.2DL+0.5LL+2.5EQ_X[col]", "P_N": 900e3, "M_Nmm": 50e6, "V_N": 60e3},
             {"combo": "1.5DL+1.5LL", "P_N": 1800e3, "M_Nmm": 20e6, "V_N": 10e3}]
    r = S12.base_checks("SCBF", _md(True, cases), {"zone": "IV"})[0]
    p = S.props(SEC)
    fy = _fy(p)
    by = {c["combo"].split(" [")[0]: c for c in r["per_case"]}
    grav = by["1.5DL+1.5LL"]
    assert grav["M_Nmm"] == pytest.approx(20e6)                        # gravity case: its own moment only
    seis = by["1.2DL+0.5LL+2.5EQ_X[col]"]
    n = 900e3 / (p["A"] * fy)
    Mpc = min(1.11 * p["Zx"] * fy * (1 - n), p["Zx"] * fy)
    assert seis["M_Nmm"] == pytest.approx(1.54 * Mpc, rel=1e-9)       # 1.1 Ry Mpc (E250, Ry 1.4) with concurrent P
    assert "EQ" in r["governing_combo"]


def test_biaxial_corner_anchor_tension_and_minor_axis_capacity():
    cases = [{"combo": "1.2DL+1.2LL+1.2EQ_X", "P_N": 600e3, "Mz_Nmm": 200e6, "My_Nmm": 80e6, "V_N": 40e3,
              "seismic": True}]
    md = _md(True, cases, major_axis_plane="X", node_i=1, node_j=2)
    md["members"] += [{"id": "bx", "role": "brace", "sfrs": True, "frame_dir": "X", "node_i": 1, "node_j": 9},
                      {"id": "by", "role": "brace", "sfrs": True, "frame_dir": "Y", "node_i": 1, "node_j": 8}]
    r = S12.base_checks("SCBF", md, {"zone": "IV"})[0]
    assert r["frame_axes"] == ["y", "z"]
    axes = {c["axis"] for c in r["per_case"]}
    assert axes == {"y", "z"}
    p = S.props(SEC)
    fy = _fy(p)
    cy = next(c for c in r["per_case"] if c["axis"] == "y")
    Mpcy, _ = S12._mpc_reduced(p, fy, 600e3, "y")
    assert cy["My_Nmm"] == pytest.approx(1.54 * Mpcy, rel=1e-9) and cy["Mz_Nmm"] == pytest.approx(200e6)
    det = C.base_plate_design_biaxial(P_N=600e3, Mz_Nmm=200e6, My_Nmm=80e6, V_N=40e3, B_mm=700, L_mm=700,
                                      t_plate_mm=60, fy_plate_MPa=250, fck_MPa=30, col_d_mm=p["d"], col_bf_mm=p["bf"],
                                      col_tf_mm=p["tf"], anchors={"n_total": 4, "n_tension": 2, "d_mm": 30,
                                                                  "grade": "8.8", "f_mm": 270})
    z_only = det["checks"]["anchor_tension_10_3_5"]["value"]
    assert det["checks"]["anchor_tension_biaxial_10_3_5"]["value"] > z_only


def test_failing_case_ranks_above_unevaluated_and_zero_lever():
    # case A: net uplift with f_mm inside the column (zero lever) -> plate moment zero on the tension side, evaluated
    r0 = C.base_plate_design(P_N=-100e3, M_Nmm=0.0, B_mm=700, L_mm=700, t_plate_mm=40, fy_plate_MPa=250, fck_MPa=30,
                             col_d_mm=300, col_bf_mm=300, col_tf_mm=19,
                             anchors={"n_total": 4, "n_tension": 2, "d_mm": 30, "grade": "8.8", "f_mm": 100})
    assert r0["checks"]["plate_thickness"]["ok"] is not None
    assert r0["checks"]["plate_thickness"]["M_tension_side"] == 0.0
    # ordering: a failing case governs over a not-evaluated one
    cases = [{"combo": "1.5DL+1.5LL", "P_N": 50e3, "M_Nmm": 0.0, "V_N": 0.0},
             {"combo": "1.5DL+1.5LL+X", "P_N": 3e6, "M_Nmm": 400e6, "V_N": 0.0}]
    md = _md(False, cases)
    md["members"][0]["sfrs"] = False
    md["bases"][0]["anchors"] = {"n_total": 4, "n_tension": 2, "d_mm": 30, "grade": "8.8"}   # no f_mm: e > L/6 case -> None
    md["bases"][0]["t_plate_mm"] = 10
    r = S12.base_checks("SCBF", md, {"zone": "IV"})[0]
    oks = {c["combo"]: c["ok"] for c in r["per_case"]}
    assert oks == {"1.5DL+1.5LL": False, "1.5DL+1.5LL+X": None}
    assert r["ok"] is False and r["governing_combo"] == "1.5DL+1.5LL"
    assert r["not_evaluated_cases"] == ["1.5DL+1.5LL+X"]


def test_net_uplift_equilibrium_not_abs_p_plus_2m_over_l():
    kw = dict(B_mm=750, L_mm=750, t_plate_mm=60, fy_plate_MPa=250, fck_MPa=30, col_d_mm=300, col_bf_mm=300,
              col_tf_mm=19, anchors={"n_total": 8, "n_tension": 4, "d_mm": 36, "grade": "8.8", "f_mm": 275})
    r = C.base_plate_design(P_N=-200e3, M_Nmm=10e6, **kw)          # both rows in tension: T = P/2 + M/(2f)
    assert r["demands"]["T_anchor_N"] == pytest.approx(100e3 + 10e6 / 550.0)
    r2 = C.base_plate_design(P_N=-200e3, M_Nmm=100e6, **kw)         # bearing at the far edge
    T, Cb = r2["bearing"]["T_N"], r2["bearing"]["C_N"]
    assert T - Cb == pytest.approx(200e3, rel=1e-6)                  # vertical equilibrium
    assert r2["demands"]["T_anchor_N"] < 200e3 + 2 * 100e6 / 750.0  # below the old |P| + 2M/L


def test_base_load_cases_keep_both_moments():
    import static_model as SM
    rec = [0.0] * len(SM.REC_FIELDS)
    d = dict(zip(SM.REC_FIELDS, range(len(SM.REC_FIELDS))))
    rec[d["N"]] = -500e3; rec[d["Mmaj_i"]] = -30e6; rec[d["Mmin_i"]] = 12e6; rec[d["Vmaj"]] = 30e3; rec[d["Vmin"]] = 40e3
    lc = CD.base_load_cases({"1.5DL+1.5EQ_X": rec, "1.5DL+1.5LL": rec})
    a = lc[0]
    assert a["Mz_Nmm"] == 30e6 and a["My_Nmm"] == 12e6 and a["V_N"] == pytest.approx(50e3) and a["seismic"] is True
    assert lc[1]["seismic"] is False
