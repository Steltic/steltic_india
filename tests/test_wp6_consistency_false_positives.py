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
