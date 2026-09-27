"""WP1.11 -- IS 875 (Part 3):2015 wind rules (k4/Kd, pd >= 0.7pz, Ka basis, Vb source, Table 6 roof,
Cpi, 10.2 gust factor, 9.1 dynamic gate, member-level wind cases, IS 800 Table 6 wind serviceability)."""
import copy

import pytest

from _ex1_fixture import ex1_cfg_is

import india_wind_tables as W


def _cfg_ws(**ws):
    return {"load_plan": {"wind_summary": dict(ws), "member_wind": {"patterns": []}}}


def _errs(cfg):
    return [m for s, m in W.wind_findings(cfg) if s == "ERROR"]


def test_k4_by_class_and_kd_in_cyclone_belt():
    assert W.k4_required(False)["k4"] == 1.0
    r = W.k4_required(True, "industrial shed")
    assert r["k4"] == 1.15 and r["Kd"] == 1.0
    assert W.k4_required(True, "cyclone shelter")["k4"] == 1.30
    assert W.k4_required(True, "office")["k4"] == 1.0


def test_cyclone_belt_must_be_declared():
    assert any("cyclone_belt" in m for m in _errs(_cfg_ws(Kd=0.9)))


def test_kd_09_refused_in_cyclone_belt():
    e = _errs(_cfg_ws(cyclone_belt=True, Kd=0.9, k4=1.0))
    assert any("7.2.1" in m for m in e)


def test_k4_wrong_class_refused():
    e = _errs(_cfg_ws(cyclone_belt=True, Kd=1.0, k4=1.0, structure_class="industrial"))
    assert any("6.3.4 gives 1.15" in m for m in e)
    e = _errs(_cfg_ws(cyclone_belt=False, k4=1.15))
    assert any("cyclone_belt is false" in m for m in e)


def test_pd_not_less_than_070_pz():
    e = _errs(_cfg_ws(cyclone_belt=False, pz_kNm2=1.5, pd_kNm2=0.9))
    assert any("0.70 pz" in m for m in e)
    assert not any("0.70 pz" in m for m in _errs(_cfg_ws(cyclone_belt=False, pz_kNm2=1.5, pd_kNm2=1.05)))


def test_ka_basis_required_and_checked():
    e = _errs(_cfg_ws(cyclone_belt=False, Ka=0.9))
    assert any("Ka_basis" in m for m in e)
    e = _errs(_cfg_ws(cyclone_belt=False, Ka=0.95, Ka_basis="frame_tributary", Ka_area_m2=21.6))
    assert any("Table 4 gives" in m for m in e)


def test_proxy_vb_refused():
    e = _errs(_cfg_ws(cyclone_belt=False, Vb_source="nearest city proxy (Pune for Lonavala)"))
    assert any("proxy" in m for m in e)
    e = _errs(_cfg_ws(cyclone_belt=False, Vb_source="derived_from_map"))
    assert any("lat/long" in m for m in e)


def test_upwind_slope_needs_k3():
    cfg = _cfg_ws(cyclone_belt=False, upwind_slope_deg=8.0)
    assert any("k3" in m for m in _errs(cfg))


def test_lowrise_needs_member_wind():
    cfg = {"heights": [8000.0], "load_plan": {"wind_summary": {"cyclone_belt": False}}}
    assert any("member-level wind" in m for m in _errs(cfg))


def test_cpi_from_openings():
    assert W.cpi_from_openings(0.03)["Cpi"] == 0.2
    assert W.cpi_from_openings(0.10)["Cpi"] == 0.5
    assert W.cpi_from_openings(0.30)["Cpi"] == 0.7


def test_table6_roof_interpolates_on_pitch():
    r = W.roof_cpe_pitched(0.4, 15.0)
    lo, hi = W.TABLE_6_CPE_PITCHED["le_0.5"][10], W.TABLE_6_CPE_PITCHED["le_0.5"][20]
    assert r["found"] and r["EF"] == pytest.approx(0.5 * (lo[0] + hi[0]))
    assert not W.roof_cpe_pitched(7.0, 10.0)["found"]


def test_lowrise_member_wind_patterns_no_default_coefficients():
    r = W.lowrise_member_wind(1.0, 8.0, 24.0, 36.0, 10.0, 0.03)
    assert r["found"] and len(r["patterns"]) == 4
    wm = r["patterns"][0]
    walls = W.resolve_cpe_walls(8.0 / 24.0, 36.0 / 24.0, 0.0)["Cpe"]
    assert wm["wall_windward_kNm2"] == pytest.approx(walls["A"] - 0.2)
    assert wm["wall_leeward_kNm2"] == pytest.approx(walls["B"] - 0.2)
    # pressure difference across the roof with the opposite Cpi sign is 2 Cpi pd
    assert r["patterns"][0]["roof_windward_kNm2"] - r["patterns"][2]["roof_windward_kNm2"] == pytest.approx(-0.4)


def test_gust_factor_10_2_components():
    g = W.gust_factor_10_2(31.5, 30.0, 0.47, 3, 44.0)
    # hand check of the pieces (IS 875-3 6.4, 6.5, 10.2)
    assert g["gv"] == 4.0
    assert g["Ih"] == pytest.approx(0.2020, abs=5e-4)
    assert g["Lh"] == pytest.approx(85.0 * 3.15 ** 0.25, rel=1e-9)
    assert 2.5 < g["G"] < 3.6


def test_dynamic_wind_trigger():
    assert W.dynamic_wind_required(60.0, 10.0, 1.5)[0]            # h/b = 6
    assert W.dynamic_wind_required(30.0, 30.0, 0.8)[0]            # f1 < 1 Hz
    assert not W.dynamic_wind_required(18.0, 24.0, 2.6)[0]


def test_member_wind_combinations_generated():
    import india_combos as IC
    cfg, _ = ex1_cfg_is()
    plan = cfg["load_plan"]
    r = W.lowrise_member_wind(1.0, 18.0, 24.0, 36.0, 10.0, 0.03)
    plan["member_wind"] = {"patterns": [dict(p, wind_axis="X") for p in r["patterns"][:1]]}
    cs = [c for c in IC.expand_combinations(plan, cfg) if "member_wind" in c.get("tags", [])]
    fams = {c["family"] for c in cs}
    # H14: each pattern is applied from both sides of its axis (the reversed '<name>R' pattern, sign -1)
    assert any("0.9DL" in f for f in fams) and len(cs) == 8
    assert sum(1 for c in cs if c["member_wind"]["name"].endswith("R") and c["sign"] == -1) == 4
    assert all(c["fWM"] in (1.5, 1.2, 0.6) for c in cs)
    plan["member_wind"] = {"patterns": [dict(r["patterns"][0])]}           # no wind_axis
    with pytest.raises(IC.CombinationError):
        IC.expand_combinations(plan, cfg)


def test_member_wind_applied_in_analysis():
    import india_combos as IC
    import india_loads as IL
    import static_model as SM
    cfg, _ = ex1_cfg_is()
    plan = cfg["load_plan"]
    r = W.lowrise_member_wind(1.0, 18.0, 24.0, 36.0, 10.0, 0.03)
    plan["member_wind"] = {"patterns": [dict(r["patterns"][0], wind_axis="X")]}
    c = next(c for c in IC.expand_combinations(plan, cfg) if "member_wind" in c.get("tags", [])
             and c["fD"] == 1.5)
    base = IL.case_from_combination({"label": "1.5DL", "fD": 1.5, "fL": 0.0, "fLr": 0.0}, plan)
    case = IL.case_from_combination(c, plan)
    pc, kinds, _ = SM.solve_cases_si(cfg, [case, base], nseg=4)
    dM = max(abs(pc[case[0]][fs][1] - pc["1.5DL"][fs][1]) for fs in pc["1.5DL"])
    assert dM > 1e6                                                # wind changes member moments (N-mm)


def test_ex1_wind_serviceability_and_no_dynamic_trigger():
    import engine3d as E
    cfg, _ = ex1_cfg_is()
    assert not _errs(cfg)
    r = E.run_india(cfg, "Ex1")
    wsv = r["wind_serviceability"]
    assert set(wsv) == {"X", "Y"}
    for d in wsv.values():
        assert d["limit_top_mm"] == pytest.approx(18000.0 / 300.0)
        assert "IS 800:2007 Table 6" in d["cite"]
        assert 0 < d["ratio_top"] < 1
    assert r["chk"]["wind_defl_X"] and r["chk"]["wind_defl_Y"]
    assert r["dynamic_wind"]["required"] is False


def test_dynamic_gate_requires_gust_factor_and_across_wind():
    import engine3d as E
    cfg, _ = ex1_cfg_is()
    ok, why, req = E.india_dynamic_wind_gate(cfg, 0.8)
    assert req and not ok
    assert any("gust_factor" in w for w in why) and any("10.3" in w for w in why)
    ws = cfg["load_plan"]["wind_summary"]
    ws["gust_factor"] = {"G": 2.4, "VB_x_kN": 10000.0}
    ws["across_wind"] = {"method": "10.3", "result": "n/a", "cite": "IS 875-3 10.3"}
    ok, why, req = E.india_dynamic_wind_gate(cfg, 0.8)
    assert not ok and any("< 10.2 gust-factor" in w for w in why)
    ws["gust_factor"] = {"G": 2.4, "VB_x_kN": 100.0, "VB_y_kN": 100.0}
    # H12 / ruling R10: an across-wind record with result "n/a" is not an evaluation -> still not ok
    assert not E.india_dynamic_wind_gate(cfg, 0.8)[0]
    ws["across_wind"] = {"method": "10.3", "found": True, "Mc_kNm": 850.0, "cite": "IS 875-3 10.3"}
    assert E.india_dynamic_wind_gate(cfg, 0.8)[0]
