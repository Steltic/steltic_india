"""AUD-3 (gold audit M2, engine observation 3): the IS 1893 7.6.4 record reports the classification the analysis
computed -- 'flexible (IS 1893 7.6.4, from the analysis)' with the ratio when any level exceeds 1.2, even when rigid is
declared; the design stays enveloped; a declared label that contradicts the computed one is a non-blocking warning;
a board / CFS or bare metal-deck diaphragm declared rigid with no stiffness basis and no 7.6.4 evaluation is a
preflight WARN."""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "steel_engine"))
sys.path.insert(0, os.path.join(ROOT, "tests"))

import consistency as C
import india_diaphragm as D
import india_seismic_gates as G
from test_india_gates_wp0 import CFG_OK, _pkg

LV = {"X": [{"level": 1, "ratio": 0.8, "limit": 1.2, "flexible": False},
            {"level": 2, "ratio": 4.26, "limit": 1.2, "flexible": True}],
      "Y": [{"level": 1, "ratio": 0.5, "limit": 1.2, "flexible": False}]}


def _declared_rigid():
    return D.classify_7_6_4(declared="rigid", plan_aspect_ratio=2.9)


def test_flexible_run_overrides_declared_rigid_label():
    rec = D.reconcile_7_6_4(_declared_rigid(), LV, declared="rigid")
    assert rec["classification"] == "flexible (IS 1893 7.6.4, from the analysis)"
    assert rec["flexible"] is True and rec["ratio"] == 4.26 and rec["limit"] == 1.2 and rec["ok"] is True
    assert rec["declared_classification"] == "rigid" and rec["declared_contradicted"] is True
    assert rec["computed_at"] == {"dir": "X", "level": 2, "source": "X01 flexible-diaphragm run (Table 5(ii))"}
    assert "enveloped" in rec["model"] and "4.26" in rec["warning"]
    assert "IS 1893 (Part 1):2016 7.6.4" in rec["clause"]


def test_rigid_run_keeps_rigid_and_declared_flexible_is_warned():
    lv = {"X": [{"level": 1, "ratio": 0.9, "flexible": False}]}
    rec = D.reconcile_7_6_4(_declared_rigid(), lv, declared="rigid")
    assert rec["classification"] == "rigid" and rec["computed_classification"] == "rigid"
    assert not rec.get("declared_contradicted")
    fl = D.reconcile_7_6_4(D.classify_7_6_4(declared="flexible"), lv, declared="flexible")
    assert fl["classification"] == "flexible" and fl["declared_contradicted"] is True   # conservative label kept


def test_declared_deflections_ratio_above_limit():
    rec = D.classify_7_6_4(delta_max_from_chord_mm=13.0, delta_avg_mm=10.0, declared="rigid")
    D.reconcile_7_6_4(rec, None, declared="rigid")
    assert rec["classification"] == "flexible (IS 1893 7.6.4, from the analysis)" and abs(rec["ratio"] - 1.3) < 1e-12
    assert rec["declared_contradicted"] is True


def test_contradiction_is_a_warning_not_a_reason():
    rec = D.reconcile_7_6_4(_declared_rigid(), LV, declared="rigid")
    pkg = _pkg(diaphragm_7_6_4=rec)
    assert C.package_warnings(CFG_OK, pkg) == [rec["warning"]]
    st = G.design_status(CFG_OK, pkg)
    assert rec["warning"] in st["warnings"] and not [r for r in st["reasons"] if "declared rigid" in r]
    assert G.status_record(st)["warnings"] == st["warnings"]


def test_light_diaphragm_declared_rigid_without_basis_warns():
    cfs = {"diaphragm": "rigid", "floor_system": "one-way: CFS joists (IS 801) span between the hot-rolled grid beams",
           "diaphragm_7_6_4": {"declared": "rigid", "plan_aspect_ratio": 1.5}}
    w = D.light_diaphragm_rigid_findings(cfs)
    assert len(w) == 1 and w[0][0] == "WARN" and "diaphragm_stiffness" in w[0][1]
    assert D.light_diaphragm_rigid_findings({"diaphragm_type": "metal_deck"})[0][0] == "WARN"
    assert D.light_diaphragm_rigid_findings({"floor_system": "purlins + profiled metal sheeting"})[0][0] == "WARN"
    # a stiffness basis, a flexible declaration, RC / composite decks: no warning
    assert D.light_diaphragm_rigid_findings(dict(cfs, diaphragm_stiffness={"type": "custom", "Gd_kN_per_m": 2500})) == []
    assert D.light_diaphragm_rigid_findings(dict(cfs, diaphragm="flexible")) == []
    assert D.light_diaphragm_rigid_findings(dict(cfs, flexible_diaphragm_analysis=True)) == []
    assert D.light_diaphragm_rigid_findings({"floor_system": "one-way composite metal deck"}) == []
    assert D.light_diaphragm_rigid_findings({"diaphragm_7_6_4": {"rc_slab": True}, "diaphragm_type": "board"}) == []


def test_preflight_carries_the_warning():
    from _ex1_fixture import ex1_cfg_is
    import preflight as PF
    cfg, _ = ex1_cfg_is()
    base = [m for s_, m in PF.india_checks(dict(cfg)) if "7.6.4" in m and "board" in m]
    assert base == []                                          # composite deck (Ex1): no warning
    cfg2, _ = ex1_cfg_is()
    cfg2.update(floor_system="CFS joists with 20 mm particle board", diaphragm="rigid")
    cfg2.pop("diaphragm_stiffness", None)
    w = [(s_, m) for s_, m in PF.india_checks(cfg2) if "7.6.4" in m and "board" in m]
    assert len(w) == 1 and w[0][0] == "WARN"
