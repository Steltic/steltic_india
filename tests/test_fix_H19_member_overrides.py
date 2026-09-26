"""H19 (HR-E-15, CFS-A-16, CFS-D-11, HR-B-05, HR-E-14): per-member overrides (K, LLT incl. columns, Lz / Ly,
grade, process); grade_by_section no longer overrides the brace grade; CHS / NB members of any kind take the
IS 1161 tube grade and process."""
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "steel_engine"))
import design_pipeline as DP  # noqa: E402

BASE = {"steel_grade": "E250 B0", "brace_grade": "E250 B0", "brace_process": None,
        "K_factors": {"roof": {"Kz": 0.083, "Ky": 0.083}, "gravity_col": {"Kz": 1.0, "Ky": 1.0}}}


def rec(cfg, t=101, kind="beam", sec="MB300", role="roof", L=9000.0):
    return DP._member_input_record(cfg, t, kind, sec, 1, 2, L, role)


def test_eave_strut_override_K_and_column_LLT():
    cfg = dict(BASE, member_overrides={"roof:MB200": {"Kz": 1.0, "Ky": 1.0}, "e7": {"LLT_sag_mm": 2000.0,
                                                                                       "LLT_hog_mm": 2000.0}})
    r = rec(cfg)
    assert r["Kz"] == pytest.approx(0.083)                       # rafters keep the roof K
    s = rec(cfg, sec="MB200")
    assert s["Kz"] == 1.0 and s["Ky"] == 1.0 and s["Kz"] * s["L_mm"] == pytest.approx(9000.0)
    c = rec(cfg, t=7, kind="col", sec="WPB300X300X117.03", role="gravity_col", L=6000.0)
    assert c["LLT_sag_mm"] == 2000.0 and c["overrides"] == ["e7"]


def test_column_LLT_used_in_ltb():
    import india_is800 as I8
    m = {"id": "c", "section": "MB300", "grade": "E250 B0", "role": "column", "L_mm": 6000.0, "Kz": 1.0, "Ky": 1.0}
    cf = [{"combo": "x", "P_N": 1e4, "Mz_i_Nmm": 40e6, "Mz_j_Nmm": 40e6}]
    full = I8.member_check_is800(dict(m), cf)
    short = I8.member_check_is800(dict(m, LLT_sag_mm=2000.0, LLT_hog_mm=2000.0), cf)
    assert short["per_combo"][0]["dc"] < 0.6 * full["per_combo"][0]["dc"]      # LTB over 2 m, not 6 m


def test_lz_ly_and_tag_beats_section():
    cfg = dict(BASE, member_overrides={"MB300": {"Ly_mm": 3000.0, "Kz": 0.9}, "e5": {"Kz": 0.7}})
    r = rec(cfg, t=5)
    assert r["Ly_mm"] == 3000.0 and r["Kz"] == 0.7 and r["overrides"] == ["MB300", "e5"]


def test_brace_grade_not_overridden_by_grade_by_section():
    cfg = dict(BASE, grade_by_section={"WPB300X300X117.03": "E350 B0"})
    b = rec(cfg, kind="brace", sec="WPB300X300X117.03", role="brace")
    assert b["grade"] == "E250 B0"
    assert rec(cfg, kind="col", sec="WPB300X300X117.03", role="lateral_col")["grade"] == "E350 B0"
    cfg["grade_by_section"]["brace:WPB300X300X117.03"] = "E350 B0"
    assert rec(cfg, kind="brace", sec="WPB300X300X117.03", role="brace")["grade"] == "E350 B0"


def test_chs_any_kind_takes_tube_grade_and_process():
    import india_is800 as I8
    cfg = dict(BASE, tube_grade="YSt 310", tube_process="HFS")
    s = rec(cfg, kind="beam", sec="CHS193.7X6.3", role="roof")
    assert s["grade"] == "YSt 310" and s["process"] == "HFS"
    chk = I8.member_check_is800(dict(s, Kz=1.0, Ky=1.0), [{"combo": "x", "P_N": 1e5}])
    assert chk.get("found", True) is not False and chk.get("fy_MPa")
    cfg2 = dict(BASE, brace_grade="YSt 240", brace_process="CDS")      # fallback to the brace tube grade
    s2 = rec(cfg2, kind="beam", sec="CHS193.7X6.3", role="roof")
    assert s2["grade"] == "YSt 240" and s2["process"] == "CDS"
