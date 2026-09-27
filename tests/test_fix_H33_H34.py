"""H33 (HR-A-10, HR-C-13, CFS-B-11, CFS-C-16): finite D/C when P >= Nd.  H34 (HR-D-10): Table 3 ratio always in the
member D/C; a beam with negligible axial (<= 0.05 Pd) stays on Table 3 row (iv)."""
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "steel_engine"))

import india_is800 as I8
import sections as S


def test_interaction_finite_when_P_exceeds_Nd():
    Nd = 1000e3
    r = I8.interaction_9_3(P_N=1.2 * Nd, Mz_Nmm=10e6, My_Nmm=0.0, Nd_N=Nd, Pdz_N=900e3, Pdy_N=800e3, Mdz_Nmm=100e6,
                           Mdy_Nmm=40e6, lambda_z=0.5, lambda_y=0.8, section_class="plastic")
    assert r["found"] and r["dc"] >= 1.2 and r["dc"] != float("inf")
    assert abs(r["section_9_3_1"]["dc"] - (1.2 + 10e6 / 100e6)) < 1e-9
    assert r["P_over_Nd"] == 1.2 and "P >= Nd" in r["note"]
    json.dumps(r, allow_nan=False)                       # strict JSON: no Infinity


def test_member_check_json_strict_when_overloaded():
    m = {"id": "c", "section": "WPB300X300X117.03", "grade": "E250 B0", "role": "column", "L_mm": 3500.0,
         "Kz": 1.0, "Ky": 1.0, "LLT_sag_mm": 3500.0}
    p = S.props("WPB300X300X117.03")
    r = I8.member_check_is800(m, [{"combo": "c", "P_N": 1.5 * p["A"] * 240 / 1.1, "Mz_i_Nmm": 5e6, "Mz_j_Nmm": -5e6,
                                   "My_i_Nmm": 0, "My_j_Nmm": 0, "Vy_N": 0}])
    assert r["dc"] > 1.5 and r["ok"] is False
    json.dumps(r, allow_nan=False, default=str)


def test_table3_always_in_member_dc():
    # beam with no axial, LLT/ry = 280 (< 300): dc >= 280/300 even though the moment ratio is small
    p = S.props("NPB300X150X36.53")
    L = 280.0 * p["ry"]
    m = {"id": "b", "section": "NPB300X150X36.53", "grade": "E250 B0", "role": "beam", "L_mm": L, "Kz": 1.0, "Ky": 1.0,
         "LLT_sag_mm": 300.0}
    r = I8.member_check_is800(m, [{"combo": "1.5DL+1.5LL", "P_N": 0.0, "Mz_i_Nmm": 0, "Mz_j_Nmm": 0, "Mz_mid_Nmm": 1e6,
                                   "Vy_N": 1e3}])
    t3 = r["table3_slenderness"]
    assert "(iv)" in t3["cite"] and t3["ok"]
    r2 = I8.member_check_is800(dict(m, LLT_sag_mm=None, LLT_hog_mm=None), [{"combo": "1.5DL+1.5LL", "P_N": 0.0,
                               "Mz_i_Nmm": 0, "Mz_j_Nmm": 0, "Mz_mid_Nmm": 1e6, "Vy_N": 1e3}])
    assert r2["dc"] >= r2["table3_slenderness"]["dc"] - 1e-12


def test_beam_negligible_axial_stays_on_row_iv():
    # 1 kN collector axial on a beam with LLT/ry = 280: row (iv) (<= 0.05 Pd), not KL/r <= 180/250
    p = S.props("NPB300X150X36.53")
    L = 280.0 * p["ry"]
    m = {"id": "b", "section": "NPB300X150X36.53", "grade": "E250 B0", "role": "beam", "L_mm": L, "Kz": 1.0, "Ky": 1.0,
         "LLT_sag_mm": L}
    r = I8.member_check_is800(m, [{"combo": "1.2DL+1.2LL+1.2EQ_X", "P_N": 1e3, "Mz_i_Nmm": 0, "Mz_j_Nmm": 0,
                                   "Mz_mid_Nmm": 5e6, "Vy_N": 1e3}])
    t3 = r["table3_slenderness"]
    assert "(iv)" in t3["cite"] and t3["limit"] == 300 and t3["ok"] is True
    assert r["dc"] >= t3["dc"]
    # a real axial (> 0.05 Pd) moves it to the KL/r rows
    Pd = r["capacities"]["compression"]["Pd_N"]
    r3 = I8.member_check_is800(m, [{"combo": "1.5DL+1.5LL", "P_N": 0.2 * Pd, "Mz_i_Nmm": 0, "Mz_j_Nmm": 0,
                                    "Mz_mid_Nmm": 5e6, "Vy_N": 1e3}])
    assert "(i)" in r3["table3_slenderness"]["cite"]
