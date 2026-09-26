"""H36 (CFS-D-05): IS 18168 12.3.4.4 applies only where a brace or gusset frames into the beam-to-column connection;
a pinned centre-link EBF returns 'not applicable' (ok True) instead of 'not evaluated'."""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "steel_engine"))

import india_is800_s12 as S12


def _md(brace_node_i=1, joints=None):
    members = [{"id": "e2", "section": "WPB300X300X117.03", "grade": "E250 B0", "role": "beam", "L_mm": 4050.0,
                "sfrs": True, "node_i": 100, "node_j": 101},
               {"id": "e3", "section": "WPB250X250X73.15", "grade": "E250 B0", "role": "brace", "L_mm": 5600.0,
                "sfrs": True, "node_i": brace_node_i, "node_j": 101},
               {"id": "e4", "section": "WPB400X300X255.74", "grade": "E250 B0", "role": "column", "L_mm": 3900.0,
                "sfrs": True, "node_i": 100, "node_j": 200}]
    return {"members": members, "forces": {}, "joints": joints or []}


LINKS = [{"id": "link-e1", "member_id": "e1", "beam_ids": ["e2"], "brace_ids": ["e3"], "column_ids": ["e4"]}]


def test_pinned_centre_link_not_applicable():
    r = S12.ebf_beam_column_checks(LINKS, _md(), {})
    assert len(r) == 1 and r[0]["id"] == "12.3.4.4_beam_column"
    assert r[0]["ok"] is True and r[0]["applies"] is False and "12.3.4.4" in r[0]["clause"]


def test_brace_at_pinned_beam_column_node_not_evaluated():
    r = S12.ebf_beam_column_checks(LINKS, _md(brace_node_i=100), {})
    assert r[0]["ok"] is None and "100" in r[0]["reason"]


def test_brace_at_rigid_joint_checked():
    j = [{"id": "J100-X", "node": 100, "frame_dir": "X", "columns": [{"member_id": "e4", "position": "above"}],
          "beams": [{"member_id": "e2"}], "connection": {"type": "welded", "weld_type": "cjp"}}]
    r = S12.ebf_beam_column_checks(LINKS, _md(brace_node_i=100, joints=j), {})
    ids = {c["id"] for c in r}
    assert {"12.3.4.4_connection_moment", "12.3.4.4_column_strength"} <= ids
    # the same rigid joint without a brace there: not applicable
    r2 = S12.ebf_beam_column_checks(LINKS, _md(brace_node_i=1, joints=j), {})
    assert r2[0]["applies"] is False
