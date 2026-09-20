"""WP2.7 -- crane loads reach the frame (IS 875-2 6.3 / 6.4), gantry demands, crane sway (IS 800 Table 6)."""
import pytest

from _ex1_fixture import ex1_cfg_is

import india_loads as IL

EX14 = {"capacity_kN": 200.0, "crab_kN": 40.0, "bridge_kN": 180.0, "span_mm": 19500.0,
        "hook_approach_mm": 1000.0, "wheel_base_mm": 3500.0, "gantry_span_mm": 9000.0, "class": "III",
        "type": "electric"}


def test_ex14_hook_approach_wheel_load():
    r = IL.crane_reactions(EX14)
    assert r["Rmax_N"] / 1e3 == pytest.approx(90.0 + 240.0 * 18.5 / 19.5, rel=1e-9)     # 317.7 kN
    assert r["wheel_max_N"] / 1e3 == pytest.approx(158.8, abs=0.1)                      # not 105 kN
    assert r["impact_column"] == 0.25 and r["impact_girder"] == 0.25
    assert r["surge_pct"] == 0.05
    assert IL.crane_reactions(dict(EX14, **{"class": "II"}))["impact_column"] == 0.10
    assert IL.crane_reactions(dict(EX14, type="hand"))["impact_column"] == 0.0
    assert IL.crane_reactions(dict(EX14, rigid_mast=True))["surge_pct"] == 0.10


def test_gantry_girder_demands_two_wheels():
    g = IL.gantry_girder_demands({"crane": EX14})
    P, L, c = 158.846e3, 9000.0, 3500.0
    M_abs = 2 * P / L * (L / 2 - c / 4) ** 2                                           # classic 2-wheel abs max
    assert g["M_static_Nmm"] == pytest.approx(M_abs, rel=2e-3)
    assert g["M_vertical_Nmm"] == pytest.approx(1.25 * g["M_static_Nmm"])
    assert g["defl_limit_vertical_mm"] == pytest.approx(9000.0 / 750.0)


def _crane_cfg():
    import engine3d as E
    cfg, _ = ex1_cfg_is()
    cfg["crane"] = dict(EX14, gantry_span_mm=6000.0, bracket_nodes={"L": E.ntag(0, 0, 1), "R": E.ntag(5, 0, 1)},
                        span_axis="X", bracket_eccentricity_mm=500.0, operation="cab", rail_height_mm=3000.0)
    return cfg


def test_crane_frame_loads_patterns():
    import engine3d as E
    cfg = _crane_cfg()
    r = IL.crane_reactions(cfg["crane"])
    L = IL.crane_frame_loads(cfg, ("L", "S+"))
    nl, nr = E.ntag(0, 0, 1), E.ntag(5, 0, 1)
    assert L[nl][2] == pytest.approx(-r["col_Rmax_N"] * 1.25)
    assert L[nr][2] == pytest.approx(-r["col_Rmin_N"] * 1.25)
    assert L[nl][0] == pytest.approx(r["col_surge_N"]) and L[nr][0] == 0.0
    assert L[nl][4] == pytest.approx(500.0 * r["col_Rmax_N"] * 1.25)
    T = IL.crane_frame_loads(cfg, ("R", "T-"))
    assert T[nr][1] == pytest.approx(-r["col_traction_N"]) and T[nr][0] == 0.0


def test_crane_combinations_and_analysis():
    import engine3d as E
    import india_combos as IC
    import static_model as SM
    cfg = _crane_cfg()
    plan = cfg["load_plan"]
    cs = IC.expand_combinations(plan, cfg)
    cr = [c for c in cs if c.get("crane_pattern")]
    assert len([c for c in cr if not c.get("lateral_kind")]) == 2 * len(IL.CRANE_PATTERNS)
    assert all(c.get("fC") in (1.05, 1.5, 0.53) for c in cr)
    c1 = next(c for c in cr if c["crane_pattern"] == ["L", "S+"] and c["fC"] == 1.5)
    c0 = {"label": "base", "fD": c1["fD"], "fL": c1["fL"], "fLr": c1["fLr"]}
    cases = [IL.case_from_combination(c1, plan), IL.case_from_combination(c0, plan)]
    pc, kinds, _ = SM.solve_cases_si(cfg, cases, nseg=4)
    r = IL.crane_reactions(cfg["crane"])
    col = frozenset((E.ntag(0, 0, 0), E.ntag(0, 0, 1)))
    dN = pc["base"][col][0] - pc[c1["label"]][col][0]                  # extra compression (N, tension +)
    assert dN > 0.5 * 1.5 * 1.25 * r["col_Rmax_N"]
    # vertical equilibrium: storey-1 columns + braces pick up the whole crane load
    info = E.build(cfg, "Linear")
    import math
    import openseespy.opensees as ops
    tot = 0.0
    for (t, kind, sec, n1, n2) in info["ele"]:
        if kind in ("col", "brace") and min(n1, n2) // 100000 == 0:
            fs = frozenset((n1, n2))
            c1_, c2_ = ops.nodeCoord(n1), ops.nodeCoord(n2)
            sin = abs(c2_[2] - c1_[2]) / math.dist(c1_, c2_)
            tot += (pc["base"][fs][0] - pc[c1["label"]][fs][0]) * sin
    assert tot == pytest.approx(1.5 * 1.25 * (r["col_Rmax_N"] + r["col_Rmin_N"]), rel=0.02)


def test_crane_preflight_and_sway():
    import engine3d as E
    cfg = _crane_cfg()
    assert IL.crane_findings(cfg) == []
    bad = dict(cfg); bad["crane"] = dict(cfg["crane"]); bad["crane"].pop("operation")
    assert any("operation" in m for s, m in IL.crane_findings(bad))
    sw = E.india_crane_sway(cfg)
    assert sw["limit_mm"] == pytest.approx(3000.0 / 400.0) and sw["sway_mm"] > 0
