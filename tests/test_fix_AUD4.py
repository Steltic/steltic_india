"""AUD-4 (gold audit M3, engine observation 4): anchorage transparency.  column_base.anchors.embedment may be derived
({method: 'bond', tau_bd_MPa, bar, L_mm, source, cite} -> pi d L tau_bd, x1.6 only for bar 'deformed'; IS 456:2000
26.2.1.1 is outside the corpus so tau_bd is an EOR input); the asserted {capacity_N, source, cite} form is kept
but needs source + cite and draws a WARN; concrete breakout is an explicit record, satisfied only by a delegated
anchor-breakout / pedestal item (otherwise WARN, never a blocker)."""
import math
import os
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "steel_engine"))
sys.path.insert(0, os.path.join(ROOT, "tests"))

import consistency as CC
import india_connection_design as CD
import india_connections as C
import india_seismic_gates as G
from test_india_gates_wp0 import CFG_OK, _pkg

BOND = {"method": "bond", "tau_bd_MPa": 1.2, "bar": "plain", "L_mm": 1500.0, "source": "EOR: M30 pedestal",
        "cite": "IS 456:2000 26.2.1.1 tau_bd 1.2 MPa (M30), EOR input"}


def test_bond_capacity_hand_values():
    r = C.anchorage_embedment_capacity(BOND, 30.0, anchor_grade="8.8")
    assert r["found"] and r["method"] == "bond" and r["deformed_factor"] == 1.0
    assert r["capacity_N"] == pytest.approx(math.pi * 30 * 1500 * 1.2) == pytest.approx(169646.0, abs=1.0)
    assert "warn" not in r and "26.2.1.1" in r["clause"]
    d = C.anchorage_embedment_capacity(dict(BOND, bar="deformed"), 30.0, anchor_grade="4.6")
    assert d["capacity_N"] == pytest.approx(math.pi * 30 * 1500 * 1.2 * 1.6) == pytest.approx(271434.0, abs=1.0)
    assert "x1.6" in d["warn"] and "property-class 4.6" in d["warn"]          # threaded rod declared deformed
    # a deformed bar anchor (no property class) carries no warning
    assert "warn" not in C.anchorage_embedment_capacity(dict(BOND, bar="deformed"), 32.0, anchor_grade="Fe500")


def test_bond_and_asserted_missing_inputs_not_evaluated():
    r = C.anchorage_embedment_capacity(dict(BOND, tau_bd_MPa=None, bar="threaded"), 30.0)
    assert r["found"] is False and "tau_bd_MPa" in r["missing"] and any("bar" in m for m in r["missing"])
    a = C.anchorage_embedment_capacity({"capacity_N": 900e3, "cite": "EOR"}, 48.0)
    assert a["found"] is False and a["missing"] == ["source"]
    ok = C.anchorage_embedment_capacity({"capacity_N": 900e3, "source": "EOR_input", "cite": "EOR calc"}, 48.0)
    assert ok["found"] and ok["method"] == "asserted" and "without a derivation" in ok["warn"]


BASE = dict(P_N=300e3, M_Nmm=250e6, V_N=50e3, B_mm=700, L_mm=750, t_plate_mm=60.0, fy_plate_MPa=230.0, fck_MPa=30,
            col_d_mm=300, col_bf_mm=300, col_tf_mm=19)


def _anchors(**kw):
    return dict({"n_total": 8, "n_tension": 3, "d_mm": 30, "grade": "8.8", "f_mm": 290, "pitch_mm": 150,
                 "edge_mm": 60, "n_per_row": 3}, **kw)


def test_base_row_uses_the_derived_capacity_and_breakout_record():
    r = C.base_plate_design(anchors=_anchors(embedment=BOND), **BASE)
    row = r["checks"]["anchorage_embedment"]
    assert row["limit"] == pytest.approx(math.pi * 30 * 1500 * 1.2) and row["embedment"]["method"] == "bond"
    assert "pi d L tau_bd" in row["cite"] and row["ok"] is (row["value"] <= row["limit"])
    cb = r["concrete_breakout"]
    assert cb["satisfied"] is False and "foundation EOR (delegated design)" in cb["note"] and cb["warn"]
    assert "concrete_breakout" not in r["checks"]                           # a record, never a blocking row
    # asserted without source: not evaluated (blocks, as before without a cite)
    r2 = C.base_plate_design(anchors=_anchors(), embedment={"capacity_N": 900e3, "cite": "EOR"}, **BASE)
    assert r2["checks"]["anchorage_embedment"]["ok"] is None and "source" in r2["checks"]["anchorage_embedment"]["reason"]
    # biaxial path uses the same record
    rb = C.base_plate_design_biaxial(P_N=300e3, Mz_Nmm=250e6, My_Nmm=60e6, V_N=50e3, B_mm=700, L_mm=700,
                                     t_plate_mm=60.0, fy_plate_MPa=230.0, fck_MPa=30, col_d_mm=300, col_bf_mm=300,
                                     col_tf_mm=19, anchors=_anchors(embedment=BOND))
    assert rb["checks"]["anchorage_embedment"]["embedment"]["method"] == "bond" and "concrete_breakout" in rb


DELEG = [{"item": "column pedestals and anchor breakout (foundation EOR)",
          "criteria": "anchor tension / shear per base from the package; IS 456 pedestal; cone / group breakout",
          "interface_forces": "base reactions"}]


def test_breakout_satisfied_only_by_delegation_with_criteria():
    cfg = {"steel_grade": "E250 B0", "connections": {"column_base": {"default": {"anchors": _anchors()}}}}
    assert CD.breakout_delegation(cfg) is None
    assert CD.breakout_delegation(dict(cfg, delegated_design=[dict(DELEG[0], criteria="")])) is None
    cfg["delegated_design"] = DELEG
    b = CD.base_entry(cfg, {"id": "e1", "section": "ISMB300"}, [])
    assert b["breakout_delegation"]["item"].startswith("column pedestals")
    r = C.base_plate_design(anchors=_anchors(), breakout_delegation=b["breakout_delegation"], **BASE)
    assert r["concrete_breakout"]["satisfied"] is True and r["concrete_breakout"]["warn"] is None


def test_findings_are_warnings_not_reasons():
    cfg = dict(CFG_OK, connections={"column_base": {"default": {
        "anchors": _anchors(), "embedment": {"capacity_N": 900e3, "source": "EOR_input", "cite": "EOR calc"}}}})
    w = CD.anchorage_findings(cfg)
    assert [s for s, _ in w] == ["WARN", "WARN"]
    assert "asserted per-anchor" in w[0][1] and "default (900 kN)" in w[0][1] and "delegated_design" in w[1][1]
    st = G.design_status(cfg, _pkg())
    assert any("asserted per-anchor" in x for x in st["warnings"])
    assert not any("asserted per-anchor" in x or "breakout" in x for x in st["reasons"])
    cfg2 = dict(cfg, delegated_design=DELEG)
    cfg2["connections"] = {"column_base": {"default": {"anchors": _anchors(embedment=BOND)}}}
    assert CD.anchorage_findings(cfg2) == [] and CC.package_warnings(cfg2, {}) == []
