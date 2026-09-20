"""WP0 guardrails: the single COMPLETE authority, consistency extensions, agent loop."""
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "steel_engine"))
sys.path.insert(0, str(ROOT))

import india_seismic_gates as G
import consistency as C

CFG_OK = {"system": "SCBF", "R": 4.5, "zone": "IV", "Z": 0.24, "I": 1.2,
          "occupancy": {"use": "office", "persons": 400}, "heights": [3600.0] * 5, "units": "N-mm"}


def _chk(v, l, **kw):
    d = {"value": v, "limit": l, "dc": v / l, "ok": v <= l, "clause": "IS 800 7.1.2", "cite": "IS 800:2007 7.1.2",
         "source": "india_is800"}
    d.update(kw)
    return d


def _pkg(**kw):
    p = {"members": [{"id": "col-1", "checks": [_chk(900.0, 1000.0)]}],
         "connections": [{"id": "conn-1", "checks": [_chk(10.0, 20.0)]}],
         "load_combinations": [
             {"label": "1.5DL+1.5EQ_X", "lateral_kind": "EQ", "direction": "X", "fE": 1.5, "sign": 1, "torsion": "+"},
             {"label": "1.5DL-1.5EQ_X", "lateral_kind": "EQ", "direction": "X", "fE": 1.5, "sign": -1, "torsion": "-"},
             {"label": "1.5DL+1.5EQ_Y", "lateral_kind": "EQ", "direction": "Y", "fE": 1.5, "sign": 1, "torsion": "+"},
             {"label": "1.5DL-1.5EQ_Y", "lateral_kind": "EQ", "direction": "Y", "fE": 1.5, "sign": -1, "torsion": "-"},
             {"label": "1.2DL+0.5LL+2.5EQ_X[col]", "lateral_kind": "EQ", "direction": "X", "fE": 2.5, "sign": 1,
              "tags": ["col_only"]}],
         "seismic_analysis": {"method": "RSA", "rsa_used_in_demands": True,
                              "scale": {"X": {"VB_scaled_kN": 100.0, "VBbar_kN": 100.0, "mass_participation": 0.95},
                                        "Y": {"VB_scaled_kN": 100.0, "VBbar_kN": 100.0, "mass_participation": 0.95}}},
         "grounding": {"rows": [{"topic": "IS 800", "status": "OK"}]}}
    p.update(kw)
    return p


def test_status_partial_without_package():
    st = G.design_status(CFG_OK, None)
    assert st["status"] == "partial" and "no calc_package" in " ".join(st["reasons"])


def test_numeric_dc_recomputed_and_bound():
    pkg = _pkg(members=[{"id": "col-1", "checks": [_chk(1100.0, 1000.0)]}])
    r = " ".join(G.design_status(CFG_OK, pkg)["reasons"])
    assert "D/C = 1.100" in r
    pkg = _pkg(members=[{"id": "col-1", "checks": [dict(_chk(900.0, 1000.0), dc=0.5)]}])
    assert "stored D/C 0.500 != recomputed" in " ".join(G.design_status(CFG_OK, pkg)["reasons"])


def test_capacity_none_with_ok_true_and_dc_none_block():
    pkg = _pkg(members=[{"id": "g", "checks": [{"value": 5.0, "limit": None, "ok": True}]},
                        {"id": "h", "checks": [{"value": None, "limit": None, "dc": None, "found": False}]}])
    r = " ".join(G.design_status(CFG_OK, pkg)["reasons"])
    assert "without numeric demand AND capacity" in r and "not evaluated" in r


def test_waiver_needs_numeric_check_and_approver():
    pkg = _pkg(connections=[{"id": "c", "waived": "n/a by judgement"}])
    assert "waived without a numeric replacement" in " ".join(G.design_status(CFG_OK, pkg)["reasons"])
    pkg = _pkg(connections=[{"id": "c", "waived": "replaced", "waiver_approved_by": "EOR X",
                             "checks": [_chk(1.0, 2.0)]}])
    assert "waived" not in " ".join(G.design_status(CFG_OK, pkg)["reasons"])


def test_capacity_design_fail_drift_fail_and_revise_block():
    pkg = _pkg(capacity_design={"system": "SCBF", "checks": {"panel_zone": {"pass": False, "DC": 3.63}}},
               drift_table=[{"storey": 1, "ok": False}],
               irregularity={"torsion": {"ratio": 1.58, "verdict": "revise configuration (Amd 2 Table 5(i))"}})
    r = " ".join(G.design_status(CFG_OK, pkg)["reasons"])
    assert "panel_zone fails" in r and "drift_table storey 1 fails" in r and "revise configuration" in r


def test_rsa_and_12_2_3_required():
    pkg = _pkg(seismic_analysis={"method": "ESM"}, load_combinations=[
        {"label": "1.5DL+1.5EQ_X", "lateral_kind": "EQ", "direction": "X", "fE": 1.5, "sign": 1}])
    r = " ".join(G.design_status(CFG_OK, pkg)["reasons"])
    assert "7.7.1" in r and "12.2.3" in r and "+/-" in r and "7.8.2" in r


def test_zone_bans_ex3_ex15_and_zone_ii_ok():
    ex3 = {"system": "OMRF", "R": 3.0, "zone": "III", "I": 1.0}
    ex15 = {"system": "OMRF + OBF", "R": 3.0, "zone": "IV", "I": 1.0}
    for c in (ex3, ex15):
        errs = [m for s, m in G.system_zone_findings(c) if s == "ERROR"]
        assert any("not allowed in Seismic Zone" in m and "Note 1" in m for m in errs)
        assert G.complete_allowed(c)[0] is False
    for c in ({"system": "OMRF", "R": 3.0, "zone": "II"}, {"system": "OCBF", "R": 4.0, "Z": 0.10}):
        assert not [m for s, m in G.system_zone_findings(c) if s == "ERROR"], c


def test_R_system_mismatch_detected():
    pkg = _pkg(capacity_design={"system": "Dual SMF+BRBF", "R": 4.5, "checks": {}})
    r = " ".join(G.design_status(dict(CFG_OK, system="SMRF", R=5.0), pkg)["reasons"])
    assert "R disagrees" in r and "does not match cfg system" in r


def test_importance_resolver_blocks_low_I():
    cfg = dict(CFG_OK, I=1.0)
    assert "below the Table 8 value 1.20" in " ".join(G.design_status(cfg, _pkg())["reasons"])


def test_consistency_grep_bak_and_literal_dc(tmp_path):
    job = tmp_path / "J"
    (job / "design").mkdir(parents=True)
    (job / "design" / "calc_package.json.wave1bak").write_text("{}")
    (job / "pipeline_error.txt").write_text("x")
    (job / "wave1_fill.py").write_text("cap = max(1.25*T, 10)\nc['DC'] = 0.8\n# seeded D/C=0.90\n")
    iss = C.script_grep_issues(str(job)) + C.bak_issues(str(job))
    blob = " ".join(iss)
    assert "own demand" in blob and "0.8" in blob and "seeded" in blob
    assert ".wave1bak" in blob and "pipeline_error.txt" in blob
    lit = C.literal_dc_issues({"connections": [{"id": "coll", "DC": 0.9}]})
    assert lit and "literal D/C 0.900" in lit[0]


def test_consistency_absent_components_and_zero_demand():
    cfg = {"system": "SMRF school", "zone": "IV"}
    pkg = {"capacity_design": {"checks": {"BRB_core": {}, "crane_runway": {}}},
           "members": [{"id": "gym", "inputs": {"P_comp_N": 0, "P_tens_N": 0, "Mz_Nmm": 0, "My_Nmm": 0, "V_N": 0}}]}
    blob = " ".join(C.absent_component_issues(cfg, pkg) + C.zero_demand_issues(pkg))
    assert "BRB_core" in blob and "crane_runway" in blob and "zero demand" in blob


def test_rag_evidence_rule(tmp_path):
    job = tmp_path / "J"
    (job / "rag").mkdir(parents=True)
    (job / "rag" / "t1.json").write_text(json.dumps({"query": "office imposed", "found": True,
                                                     "hits": [{"text": "Office rooms 2.5 and 4.0 kN/m2"}]}))
    plan = {"retrieval": [{"query": "office imposed", "found": True, "cite": "IS 875-2 Table 1 office 4.0"},
                          {"query": "zone", "found": True, "cite": "Annex E Delhi Z = 0.24"}]}
    iss = C.rag_evidence_issues(plan, str(job))
    assert len(iss) == 1 and "retrieval[1]" in iss[0]


def test_agent_gate_ends_partial_not_finish():
    src = (ROOT / "steltic" / "agent.py").read_text()
    assert "finishing with %d unresolved" not in src
    assert "run ends PARTIAL" in src and "design_status" in src
