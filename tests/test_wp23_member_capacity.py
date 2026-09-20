"""WP2.3 IS 800 member-capacity layer - hand values from spec 4.2 / HR800-08 / HREX2-X-01 / HREX3-Ex12-01."""
import os
import sys

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "steel_engine"))

import india_is800 as I  # noqa: E402
import sections as S  # noqa: E402


def test_fy_is2062_thickness_bands():
    assert I.fy_is2062("E250", 40) == 240
    assert I.fy_is2062("E250", 16) == 250
    assert I.fy_is2062("E250 BR", 41) == 230
    assert I.fy_is2062("E350", 20) == 330
    with pytest.raises(ValueError):
        I.fy_is2062("S275", 10)
    # governing thickness max(tf, tw): WPB800X300X317.36 tf = 40 -> 240
    assert I.material_for_section("WPB800X300X317.36", "E250")["fy_MPa"] == 240


def test_mb400_compression_hand_values():
    c = I.compression_capacity("MB400", 250, KLz_mm=3600, KLy_mm=3600)
    assert c["Pdz_N"] / 1e3 == pytest.approx(1761.4, abs=0.5)
    assert c["Pdy_N"] / 1e3 == pytest.approx(649.5, abs=0.5)
    assert c["axes"]["z"]["buckling_class"] == "a" and c["axes"]["y"]["buckling_class"] == "b"
    assert c["axes"]["y"]["chi"] == pytest.approx(0.3645, abs=5e-4)


def test_wpb800_pdy_fy240():
    c = I.compression_capacity("WPB800X300X317.36", 240, KLz_mm=5400, KLy_mm=5400)
    assert c["Pdy_N"] / 1e3 == pytest.approx(5955, rel=0.002)


def test_ltb_hand_values():
    r = I.ltb_moment_capacity("MB450", 3000, 250)
    assert r["Md_Nmm"] / 1e6 == pytest.approx(271.3, abs=0.2)
    assert r["Mcr_Nmm"] / 1e6 == pytest.approx(545.2, abs=0.5)
    r = I.ltb_moment_capacity("NPB400X180X57.38", 3040, 250)
    assert r["Md_Nmm"] / 1e6 == pytest.approx(217.0, abs=0.2)
    # lambda_LT <= 0.4 needs LLT <= ~1611 mm
    assert I.ltb_moment_capacity("NPB400X180X57.38", 1600, 250)["lambda_LT"] <= 0.4
    assert I.ltb_moment_capacity("NPB400X180X57.38", 1650, 250)["lambda_LT"] > 0.4


def test_ltb_found_false_without_length_or_iw():
    assert I.ltb_moment_capacity("MB450", None, 250)["found"] is False
    assert I.ltb_moment_capacity("WPB200X200X37.34", 3000, 250)["found"] is False  # Iw blank in IS 808


def test_chs_md_cap_and_mp_uncapped():
    p = S.props("CHS168.3X8")
    sc = I.section_class_table2(p, 250)
    md = I.design_moment_8_2_1(p["Zx"], p["Sx"], 250, sc["section_class"])
    assert md["Md_Nmm"] / 1e6 == pytest.approx(42.04, abs=0.01) and md["cap_governs"]
    assert I.plastic_moment_Mp(p["Zx"], 250)["Mp_Nmm"] == pytest.approx(205739.6 * 250, rel=1e-4)


def test_buckling_class_table10_full():
    assert I.buckling_class("I", 600, 300, 45, "y")["buckling_class"] == "c"
    assert I.buckling_class("I", 600, 300, 45, "z")["buckling_class"] == "b"
    assert I.buckling_class("I", 400, 400, 120, "z")["buckling_class"] == "d"
    assert I.buckling_class("CHS", process="ERW")["buckling_class"] == "b"
    assert I.buckling_class("CHS", process="HFS")["buckling_class"] == "a"
    assert I.buckling_class("angle")["buckling_class"] == "c"
    assert I.buckling_class("welded_I", tf=50, axis="y", welded=True)["buckling_class"] == "d"
    assert I.buckling_class("CHS")["found"] is False           # no silent default
    assert I.design_compressive_strength(5000, 250, 3000, 50)["found"] is False


def test_section_class_hb300_semicompact():
    sc = I.section_class_table2("HB300", 250)
    assert sc["section_class"] == "semi-compact"
    assert I.section_class_table2("WPB300X300X100.85", 250)["section_class"] in ("plastic",)


def test_shear_capacity_and_block_shear_both_expressions():
    v = I.shear_capacity("MB400", 250)
    assert v["Vd_N"] == pytest.approx(400 * 8.9 * 250 / (3 ** 0.5) / 1.1, rel=1e-6)
    b = I.block_shear_6_4_1(Avg_mm2=160 * 12, Avn_mm2=(160 - 2.5 * 22) * 12, Atg_mm2=40 * 12,
                            Atn_mm2=(40 - 11) * 12, fy_MPa=250, fu_MPa=410)
    assert b["Tdb1_N"] / 1e3 == pytest.approx(354.7, abs=0.2)
    assert b["Tdb2_N"] / 1e3 == pytest.approx(323.8, abs=0.2)
    assert b["Tdb_N"] == min(b["Tdb1_N"], b["Tdb2_N"])
    t = I.tension_capacity(5306, 250, 410)
    assert t["complete"] is False  # rupture / block shear inputs missing are reported, not skipped


def test_member_check_ex10_ele73_per_combination():
    m = {"id": "ele73", "section": "WPB800X300X317.36", "grade": "E250", "role": "column", "L_mm": 5400,
         "Kz": 1.0, "Ky": 1.0, "LLT_sag_mm": 5400, "LLT_hog_mm": 5400}
    cf = [{"combo": "1.2DL+1.2LL+1.2EQ_X", "P_N": 7213e3, "Mz_i_Nmm": 159e6, "Mz_j_Nmm": 159e6,
           "My_i_Nmm": 15.5e6, "My_j_Nmm": 15.5e6},
          {"combo": "1.5DL+1.5LL", "P_N": 5000e3, "Mz_i_Nmm": 50e6, "Mz_j_Nmm": -20e6}]
    r = I.member_check_is800(m, cf)
    assert r["fy_MPa"] == 240
    assert r["governing_combo"] == "1.2DL+1.2LL+1.2EQ_X"
    mm = r["per_combo"][0]["checks"][0]["member_9_3_2_2"]
    assert mm["ny"] == pytest.approx(1.21, abs=0.01)
    assert r["dc"] == pytest.approx(1.35, abs=0.03) and r["ok"] is False


def test_member_check_ex12_soft_storey_sway():
    m = {"id": "ex12", "section": "WPB800X300X317.36", "fy_MPa": 250, "grade": "E250", "role": "column",
         "L_mm": 6600, "Kz": 1.0, "Ky": 1.0, "LLT_sag_mm": 6600, "LLT_hog_mm": 6600, "sway": True}
    cf = [{"combo": "c", "P_N": 3854.5e3, "Mz_i_Nmm": 586e6, "Mz_j_Nmm": 586e6, "My_i_Nmm": 113.1e6,
           "My_j_Nmm": 113.1e6}]
    r = I.member_check_is800(m, cf)
    assert r["dc"] == pytest.approx(1.52, abs=0.02)


def test_member_check_llt_by_moment_sign():
    m = {"id": "b1", "section": "NPB400X180X57.38", "grade": "E250", "role": "beam", "L_mm": 6000,
         "LLT_sag_mm": 1500, "LLT_hog_mm": 6000, "Kz": 1.0, "Ky": 1.0}
    sag = I.member_check_is800(m, [{"combo": "g", "P_N": 0, "Mz_i_Nmm": 0, "Mz_j_Nmm": 0, "Mz_mid_Nmm": 150e6}])
    hog = I.member_check_is800(m, [{"combo": "u", "P_N": 0, "Mz_i_Nmm": 0, "Mz_j_Nmm": 0, "Mz_mid_Nmm": -150e6}])
    assert hog["dc"] > sag["dc"]
    assert hog["per_combo"][0]["checks"][0]["moment_sign"] == "hogging"


def test_member_check_no_grade_is_not_evaluated():
    r = I.member_check_is800({"section": "CHS168.3X8", "L_mm": 4000}, [{"combo": "c", "P_N": 1e5}])
    assert r["ok"] is None and r["found"] is False
