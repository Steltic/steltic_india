"""WP6-fix: numeric IS 800 checks for declared secondary members (purlins / joists / filler beams) and the gantry
girder -- the demand-only records blocked COMPLETE for every job that declared them (Ex13/14/15 gold runs)."""
import os, sys
import pytest
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "steel_engine"))
import design_pipeline as DP
import india_loads as IL
import sections as S


def _cfg():
    import engine3d as E
    E.activate_si_units()
    return {"units": "N-mm", "steel_grade": "E250 B0", "D_roof": 0.85, "D_floor": 3.0, "Lr": 0.75, "L_floor": 4.0,
            "partition_load_kNm2": 1.0, "snow": 0.0}


def test_secondary_member_purlin_checks_numeric():
    cfg = _cfg()
    s_ = {"id": "roof purlin", "section": "MB200", "span_mm": 7500.0, "spacing_mm": 1500.0, "level": "roof",
          "wind_uplift_kNm2": 1.2, "LLT_sag_mm": 1500.0, "LLT_hog_mm": 2500.0}
    rec = DP.secondary_member_demand(cfg, s_)
    labs = [r["combo"] for r in rec["demands"]]
    assert "1.5DL+1.5LL" in labs and "0.9DL+1.5WL(uplift)" in labs
    w = 1.5 * (0.85 + 0.75) * 1.5                                     # kN/m -> N/mm without self-weight
    assert rec["demands"][0]["w_N_per_mm"] == pytest.approx(w + 1.5 * rec["self_weight_N_per_mm"], abs=2e-3)
    assert rec["demands"][0]["M_Nmm"] == pytest.approx(rec["demands"][0]["w_N_per_mm"] * 7500.0 ** 2 / 8.0, rel=1e-3)
    up = rec["demands"][-1]
    assert up["sign"] == "hogging" and up["w_N_per_mm"] < 0
    chk = DP.secondary_member_checks(cfg, s_, rec)
    assert isinstance(chk["DC"], float) and chk["DC"] > 0
    names = [c["name"] for c in chk["checks"]]
    assert any("Table 6 deflection" in n for n in names)
    assert all(isinstance(c.get("dc"), float) and c.get("ok") is not None for c in chk["checks"])
    # a member too small for the span fails, a bigger one passes
    rec2 = DP.secondary_member_demand(cfg, dict(s_, section="MB100"))
    assert DP.secondary_member_checks(cfg, dict(s_, section="MB100"), rec2)["DC"] > 1.0


def test_secondary_member_extra_case_drift_snow():
    cfg = _cfg()
    s_ = {"id": "lean-to beam", "section": "NPB300X150X36.53", "span_mm": 6000.0, "spacing_mm": 1500.0, "level": "roof",
          "LLT_sag_mm": 1500.0, "extra_cases": [{"label": "1.5DL+1.5SL(drift)", "w_kNm2": 1.5 * (0.85 + 5.44),
                                                 "service_w_kNm2": 5.44, "cite": "IS 875-4 5.2.4"}]}
    rec = DP.secondary_member_demand(cfg, s_)
    assert rec["demands"][-1]["combo"] == "1.5DL+1.5SL(drift)"
    assert rec["demands"][-1]["w_N_per_mm"] == pytest.approx(1.5 * (0.85 + 5.44) * 1.5 + 1.5 * rec["self_weight_N_per_mm"], abs=2e-3)
    chk = DP.secondary_member_checks(cfg, s_, rec)
    assert chk["DC"] is not None


EX14 = {"capacity_kN": 200.0, "crab_kN": 40.0, "bridge_kN": 180.0, "span_mm": 19500.0, "hook_approach_mm": 1000.0,
        "wheel_base_mm": 3500.0, "gantry_span_mm": 9000.0, "class": "III", "type": "electric",
        "gantry_section": "NPB700X250X171.48", "gantry_LLT_mm": 4500.0, "rail_foot_mm": 100.0,
        "fatigue": {"detail_category_MPa": 112.0, "cycles": 2.0e6, "gamma_mft": 1.35, "cite": "EOR: Table 26 detail category 112 (rolled section), 2e6 cycles"}}


def test_gantry_girder_checks_numeric():
    cfg = dict(_cfg(), crane=EX14)
    gd = IL.gantry_girder_demands(cfg)
    g = DP.gantry_girder_checks(cfg, gd)
    names = [c["name"] for c in g["checks"]]
    assert any("biaxial" in n for n in names) and any("web bearing" in n for n in names)
    assert any("vertical deflection" in n for n in names) and any("fatigue" in n for n in names)
    assert all(isinstance(c.get("dc"), float) for c in g["checks"]), [c for c in g["checks"] if c.get("dc") is None]
    assert isinstance(g["DC"], float)
    # factored vertical moment = 1.5 x (M_vertical with impact) + 1.5 x self-weight moment
    p = S.props("NPB700X250X171.48")
    from static_model import STEEL_UNIT_WEIGHT_N_PER_MM3 as SW
    Msw = p["A"] * SW * 9000.0 ** 2 / 8.0
    assert g["factored"]["Mz_Nmm"] == pytest.approx(1.5 * gd["M_vertical_Nmm"] + 1.5 * Msw, rel=1e-6)
    # unrestrained over 9 m the same section is over-stressed (HREX3-Ex14-01 recheck: D/C 1.54 unrestrained)
    g2 = DP.gantry_girder_checks(dict(cfg, crane=dict(EX14, gantry_LLT_mm=9000.0)), gd)
    bi = lambda gg: next(c["dc"] for c in gg["checks"] if "biaxial" in c["name"])
    assert bi(g2) > bi(g) > 1.0
    # top-flange cap (surge channel, EOR data) raises the lateral stiffness and the surge capacity
    cap = dict(EX14, top_flange_cap={"Iy_mm4": 4.0e8, "Zpy_mm3": 1.8e6, "cite": "EOR: MC300 cap on the top flange"})
    g4 = DP.gantry_girder_checks(dict(cfg, crane=cap), gd)
    lat = lambda gg: next(c["dc"] for c in gg["checks"] if "lateral deflection" in c["name"])
    assert lat(g4) < lat(g) and bi(g4) < bi(g)
    # no fatigue declaration -> that row is not evaluated and DC is None (blocks COMPLETE)
    g3 = DP.gantry_girder_checks(dict(cfg, crane={k: v for k, v in EX14.items() if k != "fatigue"}), gd)
    assert g3["DC"] is None
