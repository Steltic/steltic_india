"""H09 (HR-A-04, HR-D-05): built-up box column panel zones count both web plates, and the panel in the second frame
direction is checked (flange plates acting as webs) instead of returning 'weak-axis joint, ok'."""
import math
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "steel_engine"))

import india_is800_s12 as S12
import sections as S


def test_box_panel_zone_two_webs_both_directions():
    S.register_box("BOX500X500X32", 500.0, 500.0, 32.0, 32.0)
    beam = "NPB450X190X67.16"
    members = [{"id": "c1", "section": "BOX500X500X32", "grade": "E250 B0", "role": "column", "L_mm": 3500.0,
                "sfrs": True, "major_axis_plane": "X"},
               {"id": "c2", "section": "BOX500X500X32", "grade": "E250 B0", "role": "column", "L_mm": 3500.0,
                "sfrs": True, "major_axis_plane": "X"},
               {"id": "bx", "section": beam, "grade": "E250 B0", "role": "beam", "L_mm": 6000.0, "sfrs": True},
               {"id": "by", "section": beam, "grade": "E250 B0", "role": "beam", "L_mm": 6000.0, "sfrs": True}]
    md = {"members": members, "forces": {}}
    cols = [{"member_id": "c1", "position": "below"}, {"member_id": "c2", "position": "above"}]
    rows = []
    for d, b in (("X", "bx"), ("Y", "by")):
        j = {"id": "J1-%s" % d, "frame_dir": d, "columns": cols, "beams": [{"member_id": b}], "continuity_plates": True,
             "connection": {"type": "welded", "weld_type": "cjp", "moment_capacity_Nmm": 1e12}}
        rows += [c for c in S12.smf_joint_checks(j, md, {"zone": "IV"}, system="SMF") if c["id"] == "12.11.2.3_panel_zone"]
    assert len(rows) == 2 and not any(r.get("note") == "weak-axis joint" for r in rows)
    fy = 240.0                                        # IS 2062 E250, 20 < t <= 40
    bp = 500.0 - 2 * 32.0
    for r in rows:
        det = r["detail"]
        assert det["n_webs"] == 2 and len([p for p in det["plates"] if p["plate"].startswith("column web")]) == 2
        tb = det["plates"][0]["tau_b_MPa"]
        assert abs(tb - fy / math.sqrt(3.0)) < 1e-6
        assert abs(det["Vd_N"] - 2 * bp * 32.0 * tb / 1.1) < 1e-3
    assert rows[1]["column_axis"] == "minor"


def test_i_column_weak_axis_unchanged():
    members = [{"id": "c1", "section": "WPB300X300X117.03", "grade": "E250 B0", "role": "column", "L_mm": 3500.0,
                "major_axis_plane": "X"},
               {"id": "by", "section": "NPB450X190X67.16", "grade": "E250 B0", "role": "beam", "L_mm": 6000.0}]
    j = {"id": "J1-Y", "frame_dir": "Y", "columns": [{"member_id": "c1", "position": "below"}],
         "beams": [{"member_id": "by"}], "connection": {"type": "welded", "weld_type": "cjp"}}
    r = [c for c in S12.smf_joint_checks(j, {"members": members, "forces": {}}, {"zone": "IV"}, system="SMF")
         if c["id"] == "12.11.2.3_panel_zone"]
    assert r and r[0]["note"] == "weak-axis joint"
