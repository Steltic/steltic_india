"""H38 (HR-A-14, HR-B-10, HR-E-13): IS 808 channel purlins / girts get LTB through the IS 800 Annex E-1.1 general
Mcr (load through the shear centre, It = J, Iw = Cw) instead of found:false."""
import math
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "steel_engine"))

import india_is800 as I8
import sections as S


def test_channel_mcr_hand_value():
    p = S.props("MC250")
    r = I8.ltb_moment_capacity(p, 4000.0, 250.0)
    assert r["found"] is True and r["lambda_LT"] > 0
    E, G, L = I8.E_DEFAULT_MPA, I8.G_DEFAULT_MPA, 4000.0
    a = math.pi ** 2 * E * p["Iy"] / L ** 2
    Mcr = a * math.sqrt(p["Cw"] / p["Iy"] + G * p["J"] * L ** 2 / (math.pi ** 2 * E * p["Iy"]))
    assert abs(r["Mcr_Nmm"] - Mcr) / Mcr < 1e-9
    assert "shear centre" in r["note"] and "E-1.1" in r["cite"]
    assert r["Md_Nmm"] < r["Md_8_2_1_Nmm"]


def test_channel_member_check_found():
    r = I8.member_check_is800({"id": "p", "section": "MC250", "grade": "E250", "role": "beam", "L_mm": 6000.0,
                               "Kz": 1.0, "Ky": 1.0, "LLT_sag_mm": 750.0},
                              [{"combo": "1.5DL+1.5LL", "P_N": 0.0, "Mz_i_Nmm": 0, "Mz_j_Nmm": 0, "Mz_mid_Nmm": 20e6,
                                "Vy_N": 10e3}])
    assert r["found"] is True and r["dc"] is not None


def test_angle_still_found_false():
    lab = next(k for k in S._load_csv() if k.startswith("ISA100X100"))
    r = I8.ltb_moment_capacity(S.props(lab), 2000.0, 250.0)
    assert r["found"] is False
