"""WP6-fix (GOLD-HR-C, Ex13): edge-beam tributary in the Table 6 deflection screen, the IS 875-4 4.4 ponding
record / gate, the 7.6.4 declaration basis and the 7.4.3.1 plate-thickness D/C consistency."""
import os, sys
import pytest
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "steel_engine"))
sys.path.insert(0, os.path.dirname(__file__))
from _ex1_fixture import ex1_cfg_is


def test_beam_deflection_edge_beam_half_tributary():
    import engine3d as E
    cfg, _ = ex1_cfg_is()
    cfg["deck_span"] = "X"                                  # Y-direction beams carry the deck
    worst, n, rows = E.beam_deflection_si(cfg)
    assert n > 0
    ybeams = [r for r in rows if r["span_mm"] == pytest.approx(cfg["SY"], abs=1.0)]
    # the group record keeps the largest tributary of the section: interior lines exist in Ex1, so w = p x SX
    assert ybeams and max(r["w_LL_N_per_mm"] for r in ybeams) == pytest.approx(
        (cfg["L_floor"] + cfg.get("partition_load_kNm2", 0.0)) * cfg["SX"] / 1000.0, rel=1e-6)
    # a single-bay direction has edge beams only -> half the bay width
    assert E._bays_adjacent({(0, 0), (1, 0), (0, 1), (1, 1)}, 0, 0, "X") == 1
    assert E._bays_adjacent({(0, 0), (1, 0), (0, 1), (1, 1), (0, 2), (1, 2)}, 0, 1, "X") == 2


def test_ponding_record_and_gate():
    import india_loads as IL
    import india_seismic_gates as G
    r = IL.ponding_screen_4_4(span_mm=15000.0, delta_snow_mm=63.5, roof_slope=1 / 60.0)
    assert r["ok"] is True and r["limit"] == pytest.approx(125.0)
    bad = IL.ponding_screen_4_4(span_mm=15000.0, delta_snow_mm=140.0, roof_slope=1 / 60.0)
    assert bad["ok"] is False
    reasons = G.design_status({}, {"ponding": bad, "members": [], "connections": []})["reasons"]
    assert any("ponding screen fails" in x for x in reasons)
    ok_reasons = G.design_status({}, {"ponding": r, "members": [], "connections": []})["reasons"]
    assert not any("ponding" in x for x in ok_reasons)


def test_classify_7_6_4_records_basis():
    import india_diaphragm as D
    r = D.classify_7_6_4(declared="flexible", roof=True, basis="bare metal deck, 60 m span between braced walls")
    assert r["ok"] is True and r["flexible"] is True and "bare metal deck" in r["basis"]


def test_plate_thickness_dc_consistent_with_tf_floor():
    import india_connections as C
    th = C.base_plate_thickness_7_4_3_1(w_MPa=0.24, a_mm=250.0, b_mm=180.0, fy_MPa=230.0, tf_col_mm=20.5, t_prov_mm=70.0)
    c = th["check"]
    assert c["dc"] == pytest.approx(c["value"] / c["limit"], rel=1e-9)
    assert c["t_req_mm"] == pytest.approx(20.5)
