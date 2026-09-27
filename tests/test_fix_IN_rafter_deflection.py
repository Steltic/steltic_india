"""IN-RAFTER-DEFL (gold issue IN_Ex15): IS 800:2007 Table 6 rafter deflection with cfg['roof_planes'].

IS 800 5.6.1: "Deflections are to be checked for the most adverse but realistic combination of service loads and their
arrangement, by elastic analysis, using a load factor of 1.0"; Table 6: "Rafter supporting | Profiled metal sheeting |
Span/180".  The old screen took each eave-to-apex piece (12 m plan) as a simply supported beam, 5wL^4/384EI against
12 m/180 -- 1/16 of the deflection against half the limit.  Now: the rafter line of the analysed true-slope frame,
Span = the plan distance between its supports (24 m eave to eave), deflection = the largest drop from the chord.

Reference: the X02 portal (24 m span, 8 m eave, 3 m rise, frames at 7.5 m, snow 1.2905 kN/m2 > Lr 0.75) and an
independent 2-D OpenSees portal (rafters split in 6 elements each, fixed bases, eaves free) under the middle frame's
service snow load w = 1.2905 x 7.5 = 9.68 N/mm of plan."""
import math
import os
import sys

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, "..", "steel_engine"))

pytest.importorskip("openseespy.opensees")

from test_fix_X02_pitched_roof_regions import COL, RAF, SNOW, _portal_cfg  # noqa: E402


def _ref_2d_drop(w_plan, rise=3000.0, L=24000.0, h=8000.0, nseg=6):
    """Largest downward displacement of the rafter nodes from the eave-to-eave chord (mm), 2-D portal."""
    import openseespy.opensees as ops
    import sections as S
    import engine3d as EN
    c, r = S.props(COL), S.props(RAF)
    ops.wipe(); ops.model("basic", "-ndm", 2, "-ndf", 3)
    ops.node(1, 0.0, 0.0); ops.node(2, 0.0, h); ops.node(5, L, 0.0); ops.node(4, L, h)
    ops.fix(1, 1, 1, 1); ops.fix(5, 1, 1, 1)
    ops.geomTransf("Linear", 1)
    ops.element("elasticBeamColumn", 1, 1, 2, c["A"], EN.E, c["Ix"], 1)
    ops.element("elasticBeamColumn", 2, 5, 4, c["A"], EN.E, c["Ix"], 1)
    pts = [(L * q / (2 * nseg), h + rise * q / nseg) for q in range(nseg + 1)]
    pts += [(L / 2 + L * q / (2 * nseg), h + rise - rise * q / nseg) for q in range(1, nseg + 1)]
    tags = [2] + [100 + q for q in range(1, 2 * nseg)] + [4]
    for t, (x, y) in zip(tags[1:-1], pts[1:-1]):
        ops.node(t, x, y)
    ops.timeSeries("Linear", 1); ops.pattern("Plain", 1, 1)
    Ls = math.hypot(L / 2, rise); co, si = (L / 2) / Ls, rise / Ls
    ws = w_plan * co
    for e, (a, b) in enumerate(zip(tags, tags[1:])):
        ops.element("elasticBeamColumn", 10 + e, a, b, r["A"], EN.E, r["Ix"], 1)
        up = e < nseg
        ops.eleLoad("-ele", 10 + e, "-type", "-beamUniform", -ws * co, (-ws * si) if up else (ws * si))
    ops.system("BandGeneral"); ops.numberer("Plain"); ops.constraints("Plain")
    ops.integrator("LoadControl", 1.0); ops.algorithm("Linear"); ops.analysis("Static")
    assert ops.analyze(1) == 0
    z2, z4 = ops.nodeDisp(2, 2), ops.nodeDisp(4, 2)
    drop = max((z2 + (z4 - z2) * x / L) - ops.nodeDisp(t, 2) for t, (x, _y) in zip(tags, pts))
    ops.wipe()
    return drop


def test_portal_rafter_uses_full_span_and_analysed_deflection():
    import engine3d as E
    cfg = _portal_cfg(deflection_key_roof="rafter_profiled_sheeting", building_type="industrial")
    worst, n, rows = E.beam_deflection_si(cfg)
    raf = [r for r in rows if r.get("member") == "rafter (roof_planes)"]
    assert n == len(rows) and len(raf) == 1
    r = raf[0]
    assert r["span_mm"] == 24000.0 and r["limit_mm"] == pytest.approx(24000.0 / 180.0, abs=0.01)   # Table 6 Span/180
    assert r["load_case"] == "snow" and r["line_coord_mm"] == 7500.0                    # middle frame, S > Lr
    w = SNOW * 7500.0 / 1000.0
    assert r["w_LL_N_per_mm"] == pytest.approx(w, rel=1e-3)
    ref = _ref_2d_drop(w)
    assert r["delta_frame_mm"] == pytest.approx(ref, rel=0.03)                         # independent 2-D frame
    assert r["delta_mm"] >= r["delta_frame_mm"]                                        # + sub-element sag (conservative)
    # the old half-rafter simply supported screen (12 m, 5wL^4/384EI, limit 12 m/180) is gone and was unconservative:
    import sections as S
    old = 5 * w * 12000.0 ** 4 / (384 * E.E * S.props(RAF)["Ix"])
    assert r["delta_mm"] > 2.5 * old and r["ratio"] == pytest.approx(r["delta_mm"] / r["limit_mm"], rel=1e-2)
    assert worst == pytest.approx(r["ratio"], rel=1e-9)


def test_partial_snow_and_soft_rafter_governs():
    """Declared IS 875-4 4.3 partial snow rows are service arrangements too; a soft rafter must fail the check."""
    import engine3d as E
    cfg = _portal_cfg(deflection_key_roof="rafter_profiled_sheeting", building_type="industrial",
                      snow_partial={"axis": "X"}, snow=7.0)
    worst, n, rows = E.beam_deflection_si(cfg)
    r = [x for x in rows if x.get("member") == "rafter (roof_planes)"][0]
    assert r["load_case"] in ("snow", "snow partial X-lo", "snow partial X-hi")
    ref = _ref_2d_drop(7.0 * 7.5)
    assert r["delta_frame_mm"] >= ref * 0.97
    assert worst > 1.0                                  # 7 kN/m2: ~155 mm > the 133 mm limit


def test_without_imposed_roof_load_no_rafter_row():
    import engine3d as E
    cfg = _portal_cfg(Lr=0.0, snow=0.0)
    worst, n, rows = E.beam_deflection_si(cfg)
    assert not [r for r in rows if r.get("member") == "rafter (roof_planes)"]
