"""IN-MIN-SENSE (gold issue IN_CFS_Ex13 / IN_CFS_Ex7): minimum-type check rows (value >= limit) carry
`sense: '>='` (or '>' for a strict inequality) so that a consumer recomputing the stored D/C uses limit / value.

Rows: IS 1893 7.7.5.2 modal mass ("at least 90 percent") and 7.7.3.1 scaled base shear of the flexible run
(design_pipeline, asserted in test_fix_X01), IS 800 12.11.3.2 SCWB (sum Mpc / sum Mpb >= 1.2), IS 18168 8.2 SCWB
(> 1.4, strict), IS 800 12.10.2.5 continuity plate t >= beam flange t.  Maximum-type rows carry no sense."""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "steel_engine"))

import india_is800_s12 as S12  # noqa: E402

MD = {"members": [
    {"id": "c1", "role": "column", "section": "WPB400X400X191.11", "grade": "E250 B0", "L_mm": 3500.0,
     "node_i": 1, "node_j": 2, "major_axis_plane": "X"},
    {"id": "c2", "role": "column", "section": "WPB400X400X191.11", "grade": "E250 B0", "L_mm": 3500.0,
     "node_i": 2, "node_j": 3, "major_axis_plane": "X"},
    {"id": "b1", "role": "beam", "section": "NPB550X210X92.08", "grade": "E250 B0", "L_mm": 7500.0}],
    "forces": {"c1": [{"combo": "x", "P_N": 1.0e6}], "c2": [{"combo": "x", "P_N": 0.5e6}]}}
JOINT = {"id": "J2-X", "frame_dir": "X", "columns": [{"member_id": "c1", "position": "below"},
                                                      {"member_id": "c2", "position": "above"}],
         "beams": [{"member_id": "b1"}]}


def test_scwb_rows_are_minimum_type_with_limit_over_value():
    r800 = S12.scwb_joint(JOINT, MD)
    r18 = S12.scwb_joint_is18168(JOINT, MD, {"zone": "IV"})
    assert r800["sense"] == ">=" and r18["sense"] == ">"
    for r in (r800, r18):
        assert r["value"] > 0 and abs(r["dc"] - r["limit"] / r["value"]) < 1e-12
        assert r["ok"] is (r["dc"] < 1.0 if r["sense"] == ">" else r["dc"] <= 1.0)


def test_maximum_type_rows_carry_no_sense():
    r = S12._chk("x", 50.0, 100.0, clause="c", cite="c")
    assert "sense" not in r and r["dc"] == 0.5


def test_capacity_design_flattening_keeps_sense():
    """design_pipeline copies section12 rows into capacity_design.checks: the sense must survive the copy."""
    src = open(os.path.join(os.path.dirname(S12.__file__), "design_pipeline.py")).read()
    i = src.index('pkg["capacity_design"] = {"system": cfg.get("system"), "R": G.declared_R(cfg), "section12"')
    assert '"sense": c["sense"]' in src[i:i + 900]


def test_hr_consistency_does_not_flag_minimum_rows():
    """The HR consistency recomputes demand / capacity fields only (never value / limit), so a '>=' row with
    dc = limit / value is accepted -- same verdict as before, now also explicit."""
    import consistency as HC
    ent = {"id": "J2-X", "limit_state": "SCWB", "cited": "IS 800 12.11.3.2",
           "checks": [dict(S12.scwb_joint(JOINT, MD), DC=S12.scwb_joint(JOINT, MD)["dc"])]}
    assert not [x for x in HC._entry_issues("connection", ent) if "D/C" in x and "!=" in x]
