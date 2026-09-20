"""IS 875 (Part 4):2021 5.2.4 drift / 4.4 ponding (numbers from the PDF, pdf p. 7) and the IS 800 Table 2 web
limit floor decision (HR-INTEGRATE)."""
import math
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "steel_engine"))

import india_loads as IL  # noqa: E402
import india_is800 as I8  # noqa: E402


def test_snow_drift_5_2_4_shape_coefficients():
    r = IL.snow_drift_5_2_4(1.5, 3.0, 24.0, 12.0, beta_upper_deg=14.0)
    assert r["mu1"] == 0.80 and r["mus"] == 0.0
    assert r["muw"] == 4.0                       # (24+12)/(2*3) = 6 -> capped at 4.0 (and k h/s0 = 4.0)
    assert r["l3_m"] == 6.0                      # 2h, within 5-15 m
    assert r["s_wall_kNm2"] == pytest.approx(6.0) and r["s_uniform_kNm2"] == pytest.approx(1.2)
    assert r["load_at"](3.0) == pytest.approx(3.6)
    r2 = IL.snow_drift_5_2_4(2.0, 1.0, 6.0, 6.0)
    assert r2["muw"] == pytest.approx(1.0)       # k h/s0 = 1.0 governs; l3 floor 5 m
    assert r2["l3_m"] == 5.0
    assert IL.snow_drift_5_2_4(1.5, 3.0, 24.0, 12.0, beta_upper_deg=20.0)["found"] is False   # needs the upper load


def test_ponding_screen_4_4():
    assert IL.ponding_screen_4_4(span_mm=12000, delta_snow_mm=25, roof_slope=0.02)["ok"] is True
    assert IL.ponding_screen_4_4(span_mm=12000, delta_snow_mm=150, roof_slope=0.02)["ok"] is False
    assert IL.ponding_screen_4_4(span_mm=12000, delta_snow_mm=25, roof_slope=None)["ok"] is None


def test_table2_web_limit_floor_decision():
    """IS 800 Table 2 prints 'but <= 42 eps' under the 84/(1+r1), 105/(1+1.5 r1) and 126/(1+2 r2) web limits
    (pdf p. 24).  Applied as a FLOOR (>= 42 eps): with r1 = 1 (fully compressed web) the formulas give exactly
    42 eps, the 'axial compression' row gives 42 eps, and a cap would make every web with any compression 42 eps
    (discontinuous with the 84 eps 'neutral axis at mid-depth' row).  The floor is the BS 5950 Table 11 lineage."""
    p = I8._props("MB300")
    fy = 250.0
    d = p["d"] - 2 * p["tf"] - 2 * (p.get("R1") or 0.0)
    r0 = I8.section_class_table2("MB300", fy)
    web0 = next(e for e in r0["elements"] if e["element"].startswith("web"))
    assert web0["limits"][0] == pytest.approx(84.0)          # r1 = 0
    # r1 = 1: P = d tw fy/gamma_m0
    P1 = d * p["tw"] * fy / 1.1
    r1 = I8.section_class_table2("MB300", fy, P_N=P1)
    web1 = next(e for e in r1["elements"] if e["element"].startswith("web"))
    assert web1["limits"][0] == pytest.approx(42.0, rel=1e-6)
    # monotone between: the limit never drops below 42 eps and never exceeds 84 eps
    for f in (0.2, 0.5, 0.8, 1.5):
        rr = I8.section_class_table2("MB300", fy, P_N=f * P1)
        w = next(e for e in rr["elements"] if e["element"].startswith("web"))
        assert 42.0 - 1e-9 <= w["limits"][0] <= 84.0 + 1e-9
