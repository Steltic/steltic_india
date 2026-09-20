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


def test_section12_mixed_system_runs_both_branches():
    import india_is800_s12 as S12
    assert S12.normalize_system("OMF+OCBF") == "OMF"
    assert S12.system_components("SMF + SCBF") == ["SMF", "SCBF"]
    r = S12.section12_checks("OMF+OCBF", {"members": [], "forces": {}, "combos_12_2_3_present": True}, {"zone": "II", "I": 1.0})
    ids = {c["id"].split("@")[0] for c in r["checks"]}
    assert "braces" in ids and "moment_frame_joints" in ids          # both branches ran (na rows: nothing modelled)
    assert any("mixed per-direction system" in (a.get("note") or "") for a in r.get("advisories") or [])
    r1 = S12.section12_checks("OCBF", {"members": [], "forces": {}, "combos_12_2_3_present": True}, {"zone": "II", "I": 1.0})
    ids1 = {c["id"].split("@")[0] for c in r1["checks"]}
    assert "braces" in ids1 and "moment_frame_joints" not in ids1


def test_validate_table4_accepts_generator_crane_rows():
    import india_loads as IL
    rows = [{"label": "1.5DL+1.05LL+1.5CL[CL:LS+]", "fD": 1.5, "fL": 1.05, "fLr": 1.05, "fC": 1.5, "crane": True},
            {"label": "1.2DL+1.2LL+0.53CL+1.2WL", "fD": 1.2, "fL": 1.2, "fLr": 1.2, "fC": 0.53, "fW": 1.2, "lateral_ref": "W_X"}]
    assert IL.validate_table4(rows) == []
    bad = [{"label": "x", "fD": 1.5, "fL": 1.5, "fLr": 1.5, "fC": 1.5}]
    assert any(s == "ERROR" for s, _ in IL.validate_table4(bad))


def test_nodal_dead_loads_and_column_wall_wind():
    """cfg['nodal_dead_loads'] reach the static model (factored with DL); wall wind is a distributed column load."""
    import engine3d as E
    import static_model as SM
    import india_loads as IL
    import openseespy.opensees as ops
    cfg, _ = ex1_cfg_is()
    nd = E.ntag(0, 0, 1)
    cfg["nodal_dead_loads"] = [{"node": nd, "Fz_N": -50000.0, "My_Nmm": 30.0e6, "level": 1}]
    model = SM.build_static(cfg, "Linear", 2)
    ops.timeSeries("Linear", 1); ops.pattern("Plain", 1, 1)
    lev = SM.apply_gravity_state(cfg, model, 1.5, 0.0, 0.0, self_weight=False)
    assert lev[1] > 0
    # a member-wind pattern with wall pressure loads the edge columns as element loads (no exception, total recorded)
    pat = {"wind_axis": "X", "wall_windward_kNm2": 1.0, "wall_leeward_kNm2": -0.5, "roof_windward_kNm2": None, "roof_leeward_kNm2": None}
    tot = SM.member_wind_loads(cfg, model, pat, 1.0)
    H = sum(cfg["heights"]); Ly = cfg["NY"] * cfg["SY"]
    assert tot["wall_N"] == pytest.approx((1.0 + 0.5) * Ly * H / 1000.0, rel=1e-6)
