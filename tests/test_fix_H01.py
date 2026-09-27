"""H01 (HR-B-18, CFS-B-01, CFS-C-02, CFS-D-01, E1): the Table 5(ii) flexible-diaphragm gate cannot be satisfied by
the private cfg key; an EOR record needs all four fields; the re-entrant screen applies the 15 % projection test."""
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "steel_engine"))

import engine3d as E
import india_seismic_gates as G


def _pkg(sa):
    return {"seismic_analysis": dict(sa, rsa_used_in_demands=True,
                                     scale={d: {"VB_scaled_kN": 1.0, "VBbar_kN": 1.0, "mass_participation": 0.95}
                                            for d in ("X", "Y")})}


def _flex_msgs(cfg, sa):
    return [m for m in G.analysis_findings(cfg, _pkg(sa)) if "Table 5(ii)" in m]


def test_private_cfg_key_alone_does_not_pass():
    cfg = {"_flexible_diaphragm_run": True}
    rec, miss = G.flexible_diaphragm_eor(cfg)
    assert rec is None
    # a package claiming the run without an engine basis or an EOR record still fails the gate
    assert _flex_msgs(cfg, {"reentrant_flexible_required": True, "flexible_diaphragm_run": True})


def test_eor_record_needs_all_four_fields():
    part = {"flexible_diaphragm_eor": {"analysis_ref": "ETABS run 12", "results": "", "source": "EOR", "cite": "T5(ii)"}}
    rec, miss = G.flexible_diaphragm_eor(part)
    assert rec is None and miss == ["results"]
    full = {"flexible_diaphragm_eor": {"analysis_ref": "ETABS run 12", "results": "chord forces +18 %",
                                       "source": "EOR", "cite": "IS 1893 Table 5(ii) (Amd 2)"}}
    rec, miss = G.flexible_diaphragm_eor(full)
    assert rec["basis"] == "EOR-documented" and not miss
    sa = {"reentrant_flexible_required": True, "flexible_diaphragm_run": True,
          "flexible_diaphragm_basis": "EOR-documented", "flexible_diaphragm_eor": rec}
    assert not _flex_msgs(full, sa)
    # engine hook
    assert not _flex_msgs({}, {"reentrant_flexible_required": True, "flexible_diaphragm_run": True,
                               "flexible_diaphragm_basis": "engine"})


def _cfg(plan):
    return {"NX": 10, "NY": 10, "SX": 6000.0, "SY": 6000.0, "heights": [4000.0], "plan": plan}


def test_one_bay_notch_in_ten_bay_plan_is_not_reentrant():
    notch = lambda k, NX, NY: {(i, j) for i in range(NX + 1) for j in range(NY + 1) if not (i == NX and j == NY)}
    r = E.plan_irregularities(_cfg(notch))
    assert r["reentrant"] is False
    assert r["reentrant_projection"]["max_ratio"] == pytest.approx(0.10)
    assert "15 percent" in r["reentrant_projection"]["cite"]


def test_L_plan_is_reentrant():
    r = E.plan_irregularities(_cfg(E.Lplan))            # nodes i, j > 5 removed: 5 x 5 bays of 10 x 10
    assert r["reentrant"] is True
    assert r["reentrant_projection"]["max_ratio"] == pytest.approx(0.5)


def test_projection_uses_xcoords_and_any_direction():
    # corner notch 1 bay in X (10 % of the width) x 3 bays in Y (30 %): re-entrant in Y ("in any plan direction")
    notch = lambda k, NX, NY: {(i, j) for i in range(NX + 1) for j in range(NY + 1) if not (i == NX and j >= NY - 2)}
    r = E.plan_irregularities(_cfg(notch))
    n = r["reentrant_projection"]["levels"][1]["notches"][0]
    assert n["ratio_x"] == pytest.approx(0.1) and n["ratio_y"] == pytest.approx(0.3)
    assert r["reentrant"] is True
    # non-uniform grid: last bay 1 m of a 55 m plan -> 1/55 < 15 %
    cfg = dict(_cfg(lambda k, NX, NY: {(i, j) for i in range(NX + 1) for j in range(NY + 1)
                                       if not (i == NX and j == NY)}),
               xcoords=[6000.0 * i for i in range(10)] + [55000.0])
    cfg["xcoords"][-1] = 54000.0 + 1000.0
    r2 = E.plan_irregularities(cfg)
    assert r2["reentrant"] is False


def test_interior_opening_is_not_a_reentrant_corner():
    hole = lambda k, NX, NY: {(i, j) for i in range(NX + 1) for j in range(NY + 1) if not (i == 5 and j == 5)}
    r = E.plan_irregularities(_cfg(hole))
    assert r["reentrant"] is False and r["openings"] is True
