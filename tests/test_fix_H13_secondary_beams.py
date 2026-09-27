"""H13 (HR-B-07, HR-C-04, HR-C-03, HR-D-08): one-way decks on secondary beams -- cfg['secondary_spacing_mm'];
grid beams parallel to the deck span carry their strip, girders perpendicular to it carry the rest (panel load
conserved); one_way_gravity uses the actual bounding bays (edge girder: half bay) and feeds a non-zero 12.11.2.2
V_gravity for beams parallel to the span when secondaries are declared."""
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "steel_engine"))
sys.path.insert(0, os.path.dirname(__file__))
from _ex1_fixture import ex1_cfg_is  # noqa: E402

FULL = {(i, j) for i in range(6) for j in range(5)}          # Ex1: 5 x 4 bays at 6 m, deck_span X


def test_one_way_trib_with_and_without_secondaries():
    import static_model as SM
    cfg = {"NX": 5, "NY": 4, "SX": 6000.0, "SY": 6000.0, "deck_span": "X"}
    assert SM.one_way_trib_mm(cfg, FULL, 1, 2, "X") == 0.0                 # parallel to the span: nothing
    assert SM.one_way_trib_mm(cfg, FULL, 2, 1, "Y") == pytest.approx(6000.0)
    assert SM.one_way_trib_mm(cfg, FULL, 0, 1, "Y") == pytest.approx(3000.0)   # edge girder: half bay
    cfg["secondary_spacing_mm"] = 2000.0
    assert SM.one_way_trib_mm(cfg, FULL, 1, 2, "X") == pytest.approx(2000.0)   # interior: s
    assert SM.one_way_trib_mm(cfg, FULL, 1, 0, "X") == pytest.approx(1000.0)   # edge: s/2
    assert SM.one_way_trib_mm(cfg, FULL, 2, 1, "Y") == pytest.approx(2 * 3000.0 * (1 - 2000.0 / 6000.0))
    cfg["secondary_spacing_mm"] = 9000.0                                    # capped at the bay
    assert SM.one_way_trib_mm(cfg, FULL, 1, 2, "X") == pytest.approx(6000.0)
    assert SM.one_way_trib_mm(cfg, FULL, 2, 1, "Y") == pytest.approx(0.0)
    # actual xcoords / ycoords
    cfg2 = {"NX": 2, "NY": 1, "SX": 6000.0, "SY": 6000.0, "deck_span": "X", "xcoords": [0.0, 4000.0, 12000.0],
            "ycoords": [0.0, 6000.0]}
    pres = {(i, j) for i in range(3) for j in range(2)}
    assert SM.one_way_trib_mm(cfg2, pres, 1, 0, "Y") == pytest.approx(2000.0 + 4000.0)


def test_gravity_total_conserved_and_parallel_beams_loaded():
    import static_model as SM
    import openseespy.opensees as ops
    cfg, _ = ex1_cfg_is()
    cfg["clad"] = 0.0

    def run(c):
        ops.wipe()
        model = SM.build_static(c, "Linear", 2)
        ops.timeSeries("Linear", 1); ops.pattern("Plain", 1, 1)
        loads = {}
        real = ops.eleLoad

        def cap(*a):
            loads[a[1]] = a[-2]
            return real(*a)
        ops.eleLoad = cap
        try:
            lev = SM.apply_gravity_state(c, model, 1.0, 0.0, 0.0, self_weight=False)
        finally:
            ops.eleLoad = real
        return model, lev, loads
    m0, lev0, ld0 = run(cfg)
    cfg2 = dict(cfg, secondary_spacing_mm=2000.0)
    m1, lev1, ld1 = run(cfg2)
    for k in lev0:
        assert lev1[k] == pytest.approx(lev0[k], rel=1e-9)                  # panel load conserved
    xb = next(b for b in m1["beams"] if b["dir"] == "X" and b["k"] == 2 and b["j"] == 2 and b["i"] == 1)
    assert -ld1[xb["segs"][0]] == pytest.approx(cfg["D_floor"] * 2000.0 / 1000.0)     # w = p x s (N/mm)
    xb0 = next(b for b in m0["beams"] if b["dir"] == "X" and b["k"] == 2 and b["j"] == 2 and b["i"] == 1)
    assert ld0[xb0["segs"][0]] == 0.0


def test_one_way_gravity_edge_half_and_v_gravity_parallel_beam():
    import static_model as SM
    cfg, _ = ex1_cfg_is()
    cfg["clad"] = 0.0
    edge = {"k": 2, "L": 6000.0, "dir": "Y", "i": 0, "j": 1, "present_k": FULL}
    inner = dict(edge, i=2)
    Ve = SM.one_way_gravity(cfg, edge, 1.2, 0.5, 0.5)[1]
    Vi = SM.one_way_gravity(cfg, inner, 1.2, 0.5, 0.5)[1]
    assert Ve == pytest.approx(0.5 * Vi)
    xpar = {"k": 2, "L": 6000.0, "dir": "X", "i": 1, "j": 2, "present_k": FULL}
    assert SM.one_way_gravity(cfg, xpar, 1.2, 0.5, 0.5)[1] == 0.0
    cfg["secondary_spacing_mm"] = 2000.0
    V = SM.one_way_gravity(cfg, xpar, 1.2, 0.5, 0.5)[1]
    D, Lf, Lr, S = SM.floor_pressures(cfg, 2)
    assert V == pytest.approx((1.2 * D + 0.5 * Lf) * 2000.0 / 1000.0 * 6000.0 / 2.0)
    # legacy call without the grid position keeps the full-bay bound
    assert SM.one_way_gravity(cfg, {"k": 2, "L": 6000.0, "dir": "Y"}, 1.2, 0.5, 0.5)[1] > Vi * 0.99


def test_deflection_screen_uses_secondary_strip():
    import engine3d as E
    cfg, _ = ex1_cfg_is()
    cfg["secondary_spacing_mm"] = 2000.0
    worst, n, rows = E.beam_deflection_si(cfg)
    xrows = [r for r in rows if not r["roof"] and r["span_mm"] == pytest.approx(cfg["SX"], abs=1.0)]
    p = cfg["L_floor"] + cfg["partition_load_kNm2"]
    assert any(r["w_LL_N_per_mm"] == pytest.approx(p * 2000.0 / 1000.0, rel=1e-6) for r in xrows)
