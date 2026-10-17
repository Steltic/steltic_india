"""First wave (2026-10) fixes from the industry-alignment review of the published India examples.

Item 2  crane bracket at the column face (crane_bracket.bracket_record)
Item 5  collateral + solar PV are non-permanent dead loads: dead-load factor where they add, none in the 0.9 DL rows
Item 6  honest status: IS 18168 6.2 beam bracing, D-T9 disclosure, rulings shown only where they apply, flexible deck
        over a rigid model compared line by line
Item 7  report clean-up: failed look-ups collapsed in Appendix C, no build-machine paths, no literal '&mdash;'
Item 8  STAAD export: every engine load case recorded from the engine's own load application
"""
import json
import math
import os

import pytest

from _ex1_fixture import ex1_cfg_is


# ------------------------------------------------------------------------------------------------ item 5
def test_nonpermanent_factor_rule():
    import engine3d as E
    assert E.nonpermanent_factor(0.9) == 0.0
    assert E.nonpermanent_factor(1.0) == 1.0
    assert E.nonpermanent_factor(1.2) == 1.2
    assert E.nonpermanent_factor(1.5) == 1.5
    assert E.roof_nonpermanent_kNm2({"D_roof_collateral": 0.15, "D_roof_pv": 0.12}) == pytest.approx(0.27)
    assert E.roof_nonpermanent_kNm2({}) == 0.0


def test_collateral_left_out_of_the_0_9_dead_load_rows():
    """The roof gravity of a 0.9 DL state is the same with or without collateral + PV; a 1.5 DL state carries
    1.5 x (collateral + PV) x roof area more."""
    import static_model as SM
    import openseespy.opensees as ops
    cfg, _ = ex1_cfg_is()
    base = dict(cfg, D_roof_collateral=0.0, D_roof_pv=0.0)
    extra = dict(cfg, D_roof_collateral=0.15, D_roof_pv=0.10)

    def lev(c, fD):
        m = SM.build_static(c, "Linear", 4)
        ops.timeSeries("Linear", 1)
        ops.pattern("Plain", 1, 1)
        out = SM.apply_gravity_state(c, m, fD, 0.0, 0.0, self_weight=False)
        ops.wipe()
        return sum(out.values())
    NF = len(cfg["heights"])
    roof_area_mm2 = cfg["NX"] * cfg["SX"] * cfg["NY"] * cfg["SY"]
    assert lev(extra, 0.9) == pytest.approx(lev(base, 0.9), rel=1e-9)
    d15 = lev(extra, 1.5) - lev(base, 1.5)
    assert d15 == pytest.approx(1.5 * 0.25e-3 * roof_area_mm2, rel=0.02), (d15, NF)


def test_collateral_counts_in_the_seismic_weight():
    import engine3d as E
    cfg, _ = ex1_cfg_is()
    NF = len(cfg["heights"])
    w0 = E.floor_w(dict(cfg, D_roof_collateral=0.0, D_roof_pv=0.0), NF)
    w1 = E.floor_w(dict(cfg, D_roof_collateral=0.15, D_roof_pv=0.10), NF)
    assert w1 > w0


# ------------------------------------------------------------------------------------------------ item 2
CRANE = {"capacity_kN": 100.0, "crab_kN": 15.0, "bridge_kN": 60.0, "span_mm": 22500.0, "hook_approach_mm": 900.0,
         "wheels_per_side": 2, "wheel_base_mm": 3000.0, "gantry_span_mm": 7500.0, "class": "II", "type": "electric",
         "operation": "pendant", "rail_height_mm": 7500.0, "span_axis": "Y"}


def _bracket_cfg(sec="WI600X250X16X10", col="WI550X250X16X8"):
    import sections as S
    for lab, (D, bf, tf, tw) in ((sec, (600, 250, 16, 10)), (col, (550, 250, 16, 8))):
        S.register_welded_I(lab, D, bf, tf, tw, source="test")
    return {"crane": dict(CRANE, bracket={"section": sec, "projection_mm": 475.0, "rail_height_mm": 600.0,
                                          "dead_N": 9500.0, "weld_leg_mm": 8.0, "column_section": col,
                                          "column_fy_MPa": 350.0, "fy_MPa": 250.0,
                                          "column_stiffeners": {"b_mm": 115, "t_mm": 12, "n": 2, "fy_MPa": 250}})}


def test_crane_bracket_record():
    import crane_bracket as CB
    import india_loads as IL
    assert CB.bracket_record({"crane": dict(CRANE)}) is None
    cfg = _bracket_cfg()
    r = CB.bracket_record(cfg)
    names = " | ".join(c["name"] for c in r["checks"])
    for w in ("N/Nd", "shear", "weld", "column web"):
        assert w in names, w
    assert r["id"] == "conn-crane-bracket" and 0.0 < r["DC"] < 1.0
    R = IL.crane_reactions(cfg["crane"])
    # the vertical seat force of the crane-leading row: 1.5 x girder dead + 1.5 x (1 + girder impact) x Rmax
    assert r["demand"]["V_crane_N"] == pytest.approx((1.0 + R["impact_girder"]) * R["col_Rmax_N"], rel=1e-6)
    shear = next(c for c in r["checks"] if c["name"].startswith("bracket web shear"))
    V = 1.5 * 9500.0 + 1.5 * r["demand"]["V_crane_N"]
    assert shear["value"] == pytest.approx(V / (600.0 * 10.0), rel=1e-6)


def test_crane_bracket_weld_grows_with_projection():
    import crane_bracket as CB
    a = _bracket_cfg()
    b = _bracket_cfg()
    b["crane"]["bracket"]["projection_mm"] = 950.0
    wa = next(c for c in CB.bracket_record(a)["checks"] if "weld" in c["name"])
    wb = next(c for c in CB.bracket_record(b)["checks"] if "weld" in c["name"])
    assert wb["value"] > wa["value"]


# ------------------------------------------------------------------------------------------------ item 6
def _smf_model():
    return {"members": [{"id": "b1", "kind": "beam", "role": "floor", "section": "NPB450X190X67.16",
                         "grade": "E250 B0"}],
            "joints": [{"id": "j1", "beams": [{"member_id": "b1"}], "columns": []}]}


def test_is18168_6_2_undeclared_blocks():
    import india_is800_s12 as S12
    rows = S12.is18168_6_2_beam_checks(_smf_model(), {})
    assert rows and all(r.get("ok") is None for r in rows)
    assert "beam_lateral_bracing" in rows[0]["reason"]


def test_is18168_6_2_provide_at_required():
    import india_is800_s12 as S12
    import sections as S
    ry = S.props("NPB450X190X67.16")["ry"]
    rows = S12.is18168_6_2_beam_checks(_smf_model(), {"beam_lateral_bracing": {"default": {"provide_at_required": True,
                                                                                         "basis": "stays"}}})
    near = next(r for r in rows if r["id"].endswith("_2db"))
    assert near["ok"] and near["Lb_mm"] <= 25.0 * ry and near["Lb_mm"] % 50.0 == 0.0
    assert "drawing requirement" in near["basis"]


def test_is18168_6_2_declared_spacing_fails_when_too_long():
    import india_is800_s12 as S12
    rows = S12.is18168_6_2_beam_checks(_smf_model(), {"beam_lateral_bracing": {"floor": {"near_end_mm": 3000.0,
                                                                                       "elsewhere_mm": 3000.0}}})
    near = next(r for r in rows if r["id"].endswith("_2db"))
    assert near["ok"] is False


def test_rulings_shown_only_where_they_apply():
    import peb_report as PR
    plain = [k for k, _ in PR.rulings_applied({})]
    assert "D-T2" not in plain and not any(k.startswith("D-T9") for k in plain)
    ductile = [k for k, _ in PR.rulings_applied({"apply_is18168": True})]
    assert "D-T2" in ductile and any(k.startswith("D-T9") for k in ductile)
    assert PR._f(None) == "—"                       # a plain dash: _tab escapes text


def test_dt9_disclosed_as_a_point_for_the_checker():
    import consistency as CC
    w = CC.package_warnings({"apply_is18168": True}, {"peb": {"members": {}}})
    assert any("D-T9" in x for x in w)
    assert not any("D-T9" in x for x in CC.package_warnings({}, {"peb": {}}))


def test_flexible_deck_compared_with_the_rigid_model():
    import india_diaphragm as D
    cfg, _ = ex1_cfg_is()
    cfg["diaphragm"] = "flexible"
    rec = D.rigid_vs_tributary(cfg, "EQ")
    assert rec["rows"] and rec["max_ratio"] is not None
    for r in rec["rows"]:
        assert r["V_rigid_kN"] > 0 and r["V_tributary_kN"] > 0
    # sum over the lines of one direction: the rigid model carries the whole storey shear (+ torsion pair)
    for d in ("X", "Y"):
        rows = [r for r in rec["rows"] if r["dir"] == d]
        assert sum(r["V_rigid_kN"] for r in rows) >= 0.99 * sum(r["V_tributary_kN"] for r in rows) / 1.1


# ------------------------------------------------------------------------------------------------ item 7
def test_appendix_c_collapses_failed_lookups(tmp_path, monkeypatch):
    import report as R
    job = tmp_path / "jobA"
    job.mkdir()
    recs = [{"step": 1, "ts": "2026-09-25T10:00:00", "tool": "search_engineering_standards", "detail": "q1",
             "result": "0 hits -- server error: SQLite objects created in a thread can only be used in that same thread"},
            {"step": 2, "ts": "2026-09-25T10:00:01", "tool": "search_engineering_standards", "detail": "q2",
             "result": "3 hits"}]
    (job / "activity_log.jsonl").write_text("\n".join(json.dumps(r) for r in recs))
    monkeypatch.setenv("STEEL_BUILDER_JOBS", str(tmp_path))
    h = R._activity_section("jobA")
    assert "SQLite" not in h and "server error" not in h
    assert "1 standards look-ups" in h
    assert str(tmp_path) not in h and "../" not in h


# ------------------------------------------------------------------------------------------------ item 8
def test_staad_vector_mapping():
    import staad_loads as SL
    assert SL._vec_staad((1.0, 2.0, 3.0)) == (1.0, 3.0, -2.0)


def test_staad_recorder_converts_local_uniform_loads():
    """A local -z uniform load on a horizontal beam with vecxz (0, 0, 1) is a global -Z load (the engine's gravity)."""
    import openseespy.opensees as ops
    import staad_loads as SL
    ops.wipe()
    ops.model("basic", "-ndm", 3, "-ndf", 6)
    ops.node(1, 0.0, 0.0, 0.0)
    ops.node(2, 4000.0, 0.0, 0.0)
    ops.geomTransf("Linear", 3, 0.0, 0.0, 1.0)
    ops.element("elasticBeamColumn", 7, 1, 2, 1e4, 2e5, 8e4, 1e6, 1e8, 1e8, 3)
    ops.timeSeries("Linear", 1)
    ops.pattern("Plain", 1, 1)
    with SL._Recorder() as r:
        ops.eleLoad("-ele", 7, "-type", "-beamUniform", 0.0, -2.0, 0.0)      # local z = global Z here
        ops.load(2, 0.0, 0.0, -100.0, 0.0, 0.0, 0.0)
    rec, bad = SL._convert(r.calls, {7: (7, 0.0, 4000.0)}, {})
    ops.wipe()
    assert bad == 0
    g = rec[("m", 7, 0.0, 4000.0)]
    assert g[0] == pytest.approx(0.0, abs=1e-9) and g[1] == pytest.approx(0.0, abs=1e-9)
    assert g[2] == pytest.approx(-2.0)
    assert SL._totals(rec) == pytest.approx([0.0, 0.0, -8100.0])


# ------------------------------------------------------------------------------------------------ items 3, 4 (report)
def test_report_sections_dead_loads_occupancy_takeoff():
    import report_first_wave as FW
    cfg, _ = ex1_cfg_is()
    cfg = dict(cfg, D_roof_collateral=0.15, D_roof_pv=0.12,
               occupancy={"use": "warehouse", "area_m2": 2400.0, "note": "IS 1893 Table 8 (iii)"})
    rows = FW.dead_load_rows(cfg)
    txt = " ".join(str(c) for r in rows for c in r)
    assert "0.150" in txt and "0.120" in txt and "0.9" in txt
    occ = FW.occupancy_text(cfg)
    assert "{" not in occ and "warehouse" in occ
    tk = FW.takeoff_section(cfg, {"members": []})
    assert "kg/m" in tk


def test_pv_section_reads_the_capacity_record(tmp_path):
    import report_first_wave as FW
    d = tmp_path / "design"
    d.mkdir()
    (d / "pv_capacity.json").write_text(json.dumps({"capacity_kNm2": 0.02, "first_failure_kNm2": 0.03,
                                                    "limiting_gate": "wind_defl_Y",
                                                    "capacity_H150_kNm2": 0.08, "capacity_strength_kNm2": 0.04}))
    h = FW.pv_check_section({"name": "x"}, str(tmp_path))
    assert "0.02" in h and "H/150" in h
