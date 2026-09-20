"""WP1.2 -- IS 800 Table 4 / IS 1893 combination generator and validators."""
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tests"))
sys.path.insert(0, str(ROOT / "steel_engine"))

import india_combos as IC
import india_loads as IL


def _plan(zone="IV", Z=0.24, R=4.5, I=1.2, wind=True):
    sf = {"EQ_X": {str(k): [100.0 * k, 0, 0] for k in range(1, 4)},
          "EQ_Y": {str(k): [0, 100.0 * k, 0] for k in range(1, 4)}}
    if wind:
        sf["W_X"] = {str(k): [50.0, 0, 0] for k in range(1, 4)}
        sf["W_Y"] = {str(k): [0, 50.0, 0] for k in range(1, 4)}
    return {"story_forces_units": "kN", "story_forces": sf,
            "seismic_summary": {"zone": zone, "Z": Z, "R": R, "I": I, "soil": "II"}}


CFG = {"system": "SCBF", "NX": 2, "NY": 2, "SX": 6000.0, "SY": 6000.0, "heights": [3600.0] * 3,
       "snow": 0.0, "units": "N-mm"}


def test_families_signs_torsion_vertical_12_2_3():
    plan = _plan()
    ecc = {"X": {1: 300.0, 2: 300.0, 3: 300.0}, "Y": {1: 0.0, 2: 0.0, 3: 0.0}}
    cs = IC.expand_combinations(plan, CFG, eccentricity=ecc, method="ESM")
    assert not [m for s, m in IC.validate_combinations(cs, CFG, plan) if s == "ERROR"]
    labs = [c["label"] for c in cs]
    assert any(l.startswith("1.2DL+0.5LL+2.5EQ_X") and "[col]" in l for l in labs)
    assert any(l.startswith("0.9DL-2.5EQ_Y") and "[col]" in l for l in labs)
    eqx = [c for c in cs if c.get("lateral_kind") == "EQ" and c.get("direction") == "X" and not c.get("service")]
    assert {c["sign"] for c in eqx} == {1, -1}
    assert all(c.get("torsion") in ("a", "b") for c in eqx if not c["family"].endswith("(ELZ leading)"))
    assert len([c for c in eqx if any(abs(v) > 0 for v in (c.get("torsion_mz") or {}).values())]) >= 8
    # 7.8.2 moments: esi 300, b 12000 -> variant a adds F(0.5*300 + 600), variant b F(-600) (X force: Mz = -F d)
    a = [c for c in eqx if c.get("torsion") == "a"][0]["torsion_mz"]
    b = [c for c in eqx if c.get("torsion") == "b"][0]["torsion_mz"]
    assert a["1"] == pytest.approx(-100.0 * 750.0) and b["1"] == pytest.approx(+100.0 * 600.0)
    # vertical per Amd 2 6.3.3.1 (Zone IV), Av = (2/3)(0.24/2)(2.5)/(4.5/1.2)
    Av = (2 / 3) * 0.12 * 2.5 / (4.5 / 1.2)
    v = [c for c in cs if c.get("fEv")]
    assert v and any(c["fEv"] == pytest.approx(1.5 * 0.3 * Av) for c in v)
    assert any(c["family"].endswith("(ELZ leading)") and c["fEv"] == pytest.approx(1.5 * Av) for c in v)
    # wind rows incl. 0.6WL, notional loads, serviceability
    assert any(c.get("fW") == pytest.approx(0.6) for c in cs)
    assert any(c.get("notional") for c in cs)
    assert any(c.get("service") and c.get("fW") == pytest.approx(0.8) for c in cs)


def test_zone_ii_no_vertical_and_12_2_3_for_ocbf():
    plan = _plan(zone="II", Z=0.10, R=4.0, I=1.0, wind=False)
    cfg = dict(CFG, system="OCBF")
    cs = IC.expand_combinations(plan, cfg, method="ESM")
    assert not any(c.get("fEv") for c in cs)
    assert any("is800_12_2_3" in c["tags"] for c in cs)       # OBF is a Section 12 system (12.1)


def test_seismic_plan_without_2p5_raises():
    plan = _plan(wind=False)
    plan["combinations"] = [c for c in IC.expand_combinations(plan, CFG, method="ESM")
                            if "is800_12_2_3" not in c["tags"]]
    cfg = dict(CFG, load_plan=plan)
    errs = [m for s, m in IC.validate_combinations(plan["combinations"], cfg, plan) if s == "ERROR"]
    assert any("12.2.3" in m for m in errs)
    plan.update({"jurisdiction": "india", "no_wind": "test: no wind",
                 "retrieval": [{"stem": "IS_875_Part_2_1987", "query": "q", "found": True, "cite": "c"},
                               {"stem": "IS_1893_Part_1_2016", "query": "q", "found": True, "cite": "c"}]})
    cfg["seis"] = {"Z": 0.24}
    with pytest.raises(IL.LoadPlanError):
        IL.cases_from_load_plan(cfg)


def test_nonparallel_adds_orthogonal_30pct():
    plan = _plan(wind=False)
    cs = IC.expand_combinations(plan, dict(CFG, nonparallel=True), method="ESM")
    c = [c for c in cs if c.get("direction") == "X" and c.get("terms")][0]
    assert c["terms"][0]["ref"] == "EQ_Y" and c["terms"][0]["f"] == pytest.approx(0.3 * c["fE"])
    case = IL.case_from_combination(c, plan)
    fx, fy, _ = case[4][1]
    assert fy == pytest.approx(0.3 * fx)


def test_rsa_cases_carry_rsa_and_static_torsion():
    plan = _plan(wind=False)
    cs = IC.expand_combinations(plan, CFG, eccentricity={"X": {1: 0.0, 2: 0.0, 3: 0.0}}, method="RSA")
    c = [c for c in cs if c.get("rsa") == "X" and c.get("torsion") == "a"][0]
    case = IL.case_from_combination(c, plan)
    assert case.meta["rsa"] == {"X": c["fE"]}
    assert all(fx == 0.0 and abs(mz) > 0 for (fx, fy, mz) in case[4].values())


def test_lplan_eccentricity_from_centre_of_rigidity():
    pytest.importorskip("openseespy.opensees")
    import engine3d as E
    import india_units as IU
    IU.activate_si()
    cfg = {"NX": 4, "NY": 4, "SX": 6000.0, "SY": 6000.0, "heights": [3600.0] * 3, "base": "fixed",
           "col": "WPB300X300X100.85", "beam": "NPB450X190X67.16", "plan": E.Lplan, "units": "N-mm",
           "D_floor": 3.0, "D_roof": 2.5, "L_floor": 3.0, "Lr": 0.75, "clad": 0.0}
    ecc = E.design_eccentricities(cfg)
    assert any(abs(v) > 100.0 for v in ecc["X"].values()) and any(abs(v) > 100.0 for v in ecc["Y"].values())
    plan = _plan(wind=False)
    cs = IC.expand_combinations(plan, dict(cfg, system="SMRF"), eccentricity=ecc, method="ESM")
    for d in ("X", "Y"):
        eq = [c for c in cs if c.get("direction") == d and c.get("lateral_kind") == "EQ" and not c.get("service")
              and any(abs(v) > 0 for v in (c.get("torsion_mz") or {}).values())]
        assert len(eq) >= 8
