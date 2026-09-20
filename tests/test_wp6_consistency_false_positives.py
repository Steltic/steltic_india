"""WP6-fix: consistency.check false positives seen on the gold-standard Ex1 SCBF package.

1. A capacity_design record that carries numeric value / limit / dc is a COMPUTED check even when its cite is the
   formula it evaluated ('(V/Vdb)^2+(T/Tdb)^2 <= 1'); only formula strings without a computed record are flagged.
2. 'gusset_out_of_plane_buckling' (IS 800 12.8.3.4, SCBF) is not a BRB component key.
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "steel_engine"))

import consistency as CC


def test_computed_record_with_formula_cite_is_not_symbolic():
    pkg = {"capacity_design": {"checks": {"anchor_combined_10_3_6": {
        "value": 0.061, "limit": 1.0, "dc": 0.061, "ok": True, "clause": "IS 800:2007 10.3.6",
        "cite": "(V/Vdb)^2+(T/Tdb)^2 <= 1"}}}}
    assert CC._named_not_computed_issues(pkg) == []


def test_bare_formula_without_numbers_is_still_flagged():
    pkg = {"capacity_design": {"checks": {"anchor_combined_10_3_6": {
        "ok": True, "clause": "IS 800:2007 10.3.6", "cite": "(V/Vdb)^2+(T/Tdb)^2 <= 1"}}}}
    iss = CC._named_not_computed_issues(pkg)
    assert len(iss) == 1 and "symbolic REQUIREMENT" in iss[0]


def test_gusset_buckling_key_is_not_a_brb_component():
    cfg = {"system": "SCBF", "seis": {"R": 4.5}}
    pkg = {"capacity_design": {"checks": {"gusset_out_of_plane_buckling@e12": {"dc": 0.5, "ok": True}}}}
    assert CC.absent_component_issues(cfg, pkg) == []
    pkg2 = {"capacity_design": {"checks": {"brb_core_strain@e12": {"dc": 0.5, "ok": True},
                                           "buckling_restrained_brace@e12": {"dc": 0.5, "ok": True}}}}
    assert len(CC.absent_component_issues(cfg, pkg2)) == 2


def test_base_plate_trapezoidal_bearing_label_is_not_symbolic():
    import india_connections as IC
    r = IC.base_plate_design(B_mm=500.0, L_mm=500.0, t_plate_mm=25.0, fy_plate_MPa=250.0, fck_MPa=30.0,
                             P_N=500e3, M_Nmm=10e6, V_N=0.0, col_d_mm=300.0, col_bf_mm=300.0, col_tf_mm=15.0)
    pkg = {"capacity_design": {"checks": {"base": {"ok": True, "detail": r}}}}
    assert CC._named_not_computed_issues(pkg) == []


def test_joints_skip_the_pinned_end_of_a_one_end_released_beam():
    """WP6-fix: a moment-frame beam pinned at the corner column (release 'I' at node_i) forms no joint there; the
    rigid end still forms the joint at the next column."""
    import india_is800_s12 as S12
    nodes = {1: (0.0, 0.0, 3500.0), 2: (7500.0, 0.0, 3500.0), 11: (0.0, 0.0, 0.0), 12: (7500.0, 0.0, 0.0)}
    els = [{"id": "c1", "role": "column", "node_i": 11, "node_j": 1, "section": "WPB600X300X285.48"},
           {"id": "c2", "role": "column", "node_i": 12, "node_j": 2, "section": "WPB600X300X285.48"},
           {"id": "b1", "role": "beam", "node_i": 1, "node_j": 2, "section": "NPB550X210X105.52", "release_major": "I"}]
    js = S12.joints_from_model(nodes, els)
    assert [j["node"] for j in js] == [2] and js[0]["beams"][0]["member_id"] == "b1"
    els[2]["release_major"] = "none"
    assert sorted(j["node"] for j in S12.joints_from_model(nodes, els)) == [1, 2]
    els[2]["release_major"] = "both"
    assert S12.joints_from_model(nodes, els) == []


def test_7112_gate_accepts_a_model_with_no_non_sfrs_columns():
    """WP6-fix: when every column is on a moment / braced line the 7.11.2 record says so and the gate does not
    demand a gravity-column check that has no member."""
    import india_seismic_gates as G
    cfg = {"system": "SMF", "seis": {"Z": 0.16, "I": 1.2, "R": 5.0, "zone": "III", "soil": "II"},
           "occupancy": {"use": "office", "persons": 300}}
    pkg = {"members": [{"id": "m", "DC": 0.5, "checks": [{"name": "x", "value": 0.5, "limit": 1.0, "dc": 0.5, "ok": True, "clause": "IS 800 9.3"}]}],
           "connections": [{"id": "c", "DC": 0.5, "checks": [{"name": "x", "value": 0.5, "limit": 1.0, "dc": 0.5, "ok": True, "clause": "IS 800 10"}]}],
           "deformation_compatibility": {"clause": "IS 1893 7.11.2", "zone": "III", "checks": [], "no_non_sfrs_columns": True}}
    r1 = G.design_status(cfg, pkg)["reasons"]
    assert not any("7.11.2" in x for x in r1)
    pkg["deformation_compatibility"].pop("no_non_sfrs_columns")
    r2 = G.design_status(cfg, pkg)["reasons"]
    assert any("7.11.2" in x for x in r2)


def test_roof_deflection_key_selects_the_table6_rafter_row():
    """WP6-fix: cfg['deflection_key_roof'] picks the IS 800 Table 6 row for the roof beams (portal rafter with profiled
    sheeting: span/180); floors keep the default row; an unknown key is refused."""
    import india_loads as IL
    import pytest
    cfg = {"deflection_key_roof": "rafter_profiled_sheeting"}
    assert IL.floor_deflection_limit(cfg, roof=True)[0] == 180.0
    assert IL.floor_deflection_limit(cfg)[0] == 360.0
    with pytest.raises(IL.LoadPlanError):
        IL.floor_deflection_limit({"deflection_key_roof": "no_such_row"}, roof=True)
