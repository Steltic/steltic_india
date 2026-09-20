"""WP2.2 section database (review HR800-04/13/21; spec 4.2)."""
import os
import sys

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
SE = os.path.join(os.path.dirname(HERE), "steel_engine")
sys.path.insert(0, SE)
sys.path.insert(0, os.path.join(SE, "tools"))

import sections as S  # noqa: E402
import build_is808_shapes as B  # noqa: E402


def test_validator_zero_failures_on_shipped_csv():
    bad = B.validate_csv(os.path.join(SE, "is808_shapes.csv"))
    assert bad == [], bad[:5]


def test_wpb600_ry_corrected():
    assert S.props("WPB600X300X285.48")["ry"] == pytest.approx(72.2, abs=0.1)


def test_angle_r_min_is_rv():
    p = S.props("ISA100X100X10")
    assert p["rv"] == pytest.approx(19.6, abs=0.15)
    assert S.brace_r("ISA100X100X10") == pytest.approx(19.6, abs=0.15)
    assert p["Cw"] == 0.0


def test_wb_lb_rz_corrected_and_isa200x100_rz():
    assert S.props("WB600")["rx"] == pytest.approx(249.7, abs=0.2)
    assert S.props("LB400")["rx"] == pytest.approx(163.3, abs=0.2)
    assert S.props("ISA200X100X12")["rx"] == pytest.approx(64.4, abs=0.2)


def test_ze_rows_repaired():
    for lab in ("NPB750X270X145.29", "WPB500X300X187.34", "WPB650X300X224.78"):
        p = S.props(lab)
        assert p["Sx"] == pytest.approx(2 * p["Ix"] / p["d"], rel=0.04)


def test_quarantined_row_raises():
    with pytest.raises(KeyError, match="quarantined"):
        S.props("WPB280X280X284.13")


def test_brace_r_unknown_raises_no_invented_default():
    with pytest.raises(KeyError):
        S.brace_r("FOO123")


def test_aisc_label_raises_in_india_unless_allowed():
    with pytest.raises(KeyError, match="AISC"):
        S.props("W14X90")
    with pytest.raises(ValueError):
        S.allow_aisc_shapes(None)


def test_hss_regex_fixed():
    bt, t = S.hss_b_over_t("HSS8X8X1/2")
    assert t == 0.5 and bt == pytest.approx(13.0)


def test_chs_material_from_is1161_grade_no_default():
    p = S.props("CHS168.3X8")
    assert p["fy_MPa"] is None and p["material_found"] is False
    q = S.props("CHS168.3X8", grade="YSt 240", process="ERW")
    assert q["fy_MPa"] == 240.0 and q["fu_MPa"] == 410.0 and q["buckling_class"] == "b"
    assert S.props("CHS168.3X8", grade="YSt 310", process="HFS")["buckling_class"] == "a"
    assert S.brace_r("CHS168.3X8") == pytest.approx(56.74, abs=0.05)


def test_ipack_brace_area_for_is_chs():
    import engine3d as E
    E.set_unit_system("N-mm") if hasattr(E, "set_unit_system") else None
    assert S.brace_area("CHS219.1X8") == pytest.approx(5306.0)
