"""WP1.4-1.9: importance factor, zone/system gate, seismic weight, Ta, irregularity, drift."""
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tests"))
sys.path.insert(0, str(ROOT / "steel_engine"))

import india_seismic as IS
import india_seismic_gates as G

FIX = json.load(open(ROOT / "tests" / "fixtures" / "zone_system_cfgs.json"))


# ---- WP1.4 ------------------------------------------------------------------------------------
def test_importance_factor_table8_amd2():
    assert IS.importance_factor({"use": "office", "persons": 300})["I"] == 1.2
    assert IS.importance_factor({"use": "office", "persons": 150})["I"] == 1.0
    assert IS.importance_factor({"use": "warehouse", "food_storage": True})["I"] == 1.5
    assert IS.importance_factor({"use": "warehouse"})["I"] == 1.0                      # D8 general storage
    assert IS.importance_factor({"use": "educational building (college)"})["I"] == 1.5  # Amd 2 wording
    assert IS.importance_factor({"use": "hospital"})["I"] == 1.5
    assert IS.importance_factor({"use": "clinic"})["I"] == 1.2                          # D8
    assert IS.importance_factor({"use": "office", "area_m2": 3600})["I"] == 1.2        # D8 > 2,000 m2
    assert IS.importance_factor([{"use": "retail", "persons": 50}, {"use": "cinema"}])["I"] == 1.5   # Note 4
    assert IS.importance_factor({})["found"] is False


def test_preflight_blocks_low_I():
    cfg = {"system": "SCBF", "R": 4.5, "zone": "IV", "I": 1.0, "occupancy": {"use": "office", "persons": 500}}
    assert any("Table 8" in m for m in G.occupancy_findings(cfg))


# ---- WP1.5 ------------------------------------------------------------------------------------
@pytest.mark.parametrize("ex", ["Ex3", "Ex15"])
def test_zone_system_errors_for_banned_systems(ex):
    errs = [m for s, m in G.system_zone_findings(FIX[ex]) if s == "ERROR"]
    assert any("not allowed in Seismic Zone" in m for m in errs), errs
    assert G.complete_allowed(FIX[ex])[0] is False


@pytest.mark.parametrize("ex", ["Ex5", "Ex13", "Ex14"])
def test_zone_ii_systems_pass_the_zone_gate(ex):
    errs = [m for s, m in G.system_zone_findings(FIX[ex]) if s == "ERROR"]
    assert not errs, errs


def test_table9_R_values_amd2():
    R = lambda s: G.resolve_system_R({"system": s})["R_table9"]
    assert (R("OMRF"), R("SMRF"), R("OCBF"), R("SCBF"), R("EBF")) == (3.0, 5.0, 4.0, 4.5, 5.0)
    assert G.resolve_system_R({"system": "SMF + SCBF"})["R_table9"] == 4.5


# ---- WP1.6 ------------------------------------------------------------------------------------
@pytest.fixture(scope="module")
def eng():
    pytest.importorskip("openseespy.opensees")
    import engine3d as E
    import india_units as IU
    IU.activate_si()
    return E


def test_ex1_engine_W_matches_design_W(eng):
    from _ex1_fixture import ex1_cfg
    E = eng
    cfg, seis = ex1_cfg()
    cfg["self_weight"] = False                    # the shipped W has no self-weight (spec 1.6 test)
    E.build(cfg, "Linear")
    w = [E.floor_w(cfg, k) / 1e3 for k in range(1, 6)]
    assert sum(w) == pytest.approx(14770.8, rel=0.02)
    assert w[0] == pytest.approx(3164.4, abs=0.5)
    cfg["self_weight"] = True
    cfg.pop("_sw_by_level", None)
    E.build(cfg, "Linear")
    comps = E.seismic_weight_components(cfg, 1)
    assert comps["self_weight"] > 3.0e5                           # ~372 kN steel per floor (HREX1-X-08)
    assert comps["imposed"] == pytest.approx(0.25 * 2.5 * 720.0 * 1000.0)   # Table 10: 25 % <= 3.0 kN/m2


def test_W_rules_partitions_snow_table10(eng):
    E = eng
    cfg = {"NX": 1, "NY": 1, "SX": 10000.0, "SY": 10000.0, "heights": [4000.0, 4000.0], "units": "N-mm",
           "D_floor": 3.0, "D_roof": 2.0, "L_floor": 5.0, "Lr": 1.5, "clad": 0.0, "snow": 2.0, "self_weight": False}
    c1 = E.seismic_weight_components(cfg, 1)
    c2 = E.seismic_weight_components(cfg, 2)
    assert c1["imposed"] == pytest.approx(0.5 * 5.0 * 100.0 * 1000.0)          # > 3.0 kN/m2 -> 50 %
    assert c1["partitions"] == pytest.approx(0.5 * 100.0 * 1000.0)            # 7.3.6 minimum
    assert c2["snow"] == pytest.approx(0.2 * 2.0 * 100.0 * 1000.0)            # 7.3.5 (> 1.5 kN/m2)
    assert "imposed" not in c2                                                 # 7.3.2 roof LL excluded
    with pytest.raises(ValueError):
        E.seismic_weight_components(dict(cfg, partition_seismic_kNm2=0.3), 1)


# ---- WP1.7 ------------------------------------------------------------------------------------
def test_Ta_labels_composite_infill_clamp():
    s = IS.approximate_Ta(31.5, 30.0, "SMF steel")
    assert s["clause"] == "7.6.2(a)" and s["Ta_s"] == pytest.approx(0.085 * 31.5 ** 0.75)
    c = IS.approximate_Ta(31.5, 30.0, "SMF", material="composite")
    assert c["Ta_s"] == pytest.approx(0.080 * 31.5 ** 0.75)
    inf = IS.approximate_Ta(31.5, 30.0, "SMF steel", infills=True)
    assert inf["clause"] == "7.6.2(c)" and inf["Ta_s"] == pytest.approx(0.09 * 31.5 / 30.0 ** 0.5)
    # 7.6.2.1: an MRF value below (c) is raised to (c)
    lo = IS.approximate_Ta(10.0, 1.0, "SMF steel")
    assert lo["Ta_s"] == pytest.approx(0.09 * 10 / 1.0) and lo["clamp_note"]
    with pytest.raises(IS.TaFormulaError):
        IS.approximate_Ta(18, 24, "SCBF", formula="0.085 h^0.75")


# ---- WP1.8 ------------------------------------------------------------------------------------
def test_torsion_ratio_bands_amd2():
    r = IS.torsion_ratio_from_edges(1.0, 2.5)
    assert r == pytest.approx(1.4286, abs=1e-4)
    assert "revise configuration" in IS.torsion_classification(r)["verdict"]
    assert IS.torsion_classification(IS.torsion_ratio_from_edges(10, 5 * 1.6667))["band"] in ("<= 1.2", "1.2-1.4")
    mid = IS.torsion_classification(1.29)
    assert mid["irregular"] and mid["requires_dynamic_analysis"]


def test_soft_storey_rule_and_exemption():
    s = IS.soft_storey_screen([0.57, 1.0, 1.0, 0.9])
    assert s["soft"][0] and s["drift_limit_by_storey"][0] == 0.002
    # split-level offset storey 2 exempt -> storey 1 compared with storey 3
    s2 = IS.soft_storey_screen([1.0, 0.01, 0.9, 0.8], exempt=[2])
    assert not any(s2["soft"])


def test_modes_rule_table6_vii():
    modes = [{"T": 1.037, "mass_x": 0.7, "mass_y": 0.0, "rot": 0.0},
             {"T": 1.032, "mass_x": 0.0, "mass_y": 0.7, "rot": 0.0},
             {"T": 0.8, "mass_x": 0.0, "mass_y": 0.0, "rot": 1.0}]
    r = IS.modes_screen(modes, "IV")
    assert r["irregular"] and "10 %" in r["verdict"]                         # Ex10: 0.5 % apart
    assert not IS.modes_screen(modes, "II")["irregular"]


def test_soft_storey_detected_in_model(eng):
    E = eng
    cfg = {"NX": 1, "NY": 1, "SX": 6000.0, "SY": 6000.0, "heights": [6600.0, 3300.0, 3300.0], "base": "fixed",
           "col": "WPB300X300X100.85", "beam": "NPB450X190X67.16", "units": "N-mm", "jurisdiction": "india",
           "D_floor": 4.0, "D_roof": 3.0, "L_floor": 3.0, "Lr": 0.75, "clad": 0.0, "self_weight": False,
           "load_plan": {"jurisdiction": "india", "story_forces_units": "N",
                         "story_forces": {"EQ_X": {"1": [1e4, 0, 0], "2": [2e4, 0, 0], "3": [3e4, 0, 0]},
                                          "EQ_Y": {"1": [0, 1e4, 0], "2": [0, 2e4, 0], "3": [0, 3e4, 0]}}}}
    dr = E.india_drift(cfg, {"X": {}, "Y": {}})
    K = dr["X"]["stiffness_N_per_mm"]
    s = IS.soft_storey_screen(K)
    assert s["soft"][0] and K[0] / K[1] < 0.7                                    # Ex12 pattern (0.57)


# ---- WP1.9 ------------------------------------------------------------------------------------
def test_drift_cap_and_soft_storey_limits():
    assert IS.drift_allowable({"drift_limit": 0.010})[0] == 0.004
    cfg = {"_soft_storey_flags": {"drift_limit_by_storey": [0.002, 0.004]}}
    assert IS.drift_allowable_for_storey(cfg, 0) == 0.002 and IS.drift_allowable_for_storey(cfg, 1) == 0.004


def test_separation_7_11_3_amd1():
    assert IS.separation_required(4.5, 10.0, 5.0, 8.0)["required_mm"] == pytest.approx(85.0)
    assert IS.separation_required(4.5, 10.0, 5.0, 8.0, same_floor_levels=True)["required_mm"] == pytest.approx(42.5)
