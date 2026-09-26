"""H05 (E4, HR-C-14, NEW): IS 18168 Table 2 width-to-thickness checks are live whenever IS 18168 applies, and built-up
boxes are checked with the closed-box rows (flange (B - 2tw)/tf, web (D - 2tf)/tw) instead of being skipped."""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "steel_engine"))

import india_is18168 as I18
import india_is800_s12 as S12
import sections as S


def _md(members):
    return {"members": members, "forces": {m["id"]: [] for m in members}, "connections": [], "bases": [],
            "brace_lines": [], "combos_12_2_3_present": True, "combos_is18168_5_5_present": True}


def test_box_column_smrf_zone_iv_checked_with_box_row():
    S.register_box("BOX450X450X16", 450.0, 450.0, 16.0, 16.0)
    md = _md([{"id": "c1", "section": "BOX450X450X16", "grade": "E250 B0", "role": "column", "L_mm": 3500.0,
               "sfrs": True, "Kz": 1.0, "Ky": 1.0}])
    r = S12.section12_checks("SMF", md, {"zone": "IV", "I": 1.2, "height_m": 12.0})
    c = [c for c in r["checks"] if c["id"] == "is18168_table2_column" and c["member"] == "c1"]
    assert c, "box SFRS column must get a Table 2 record"
    c = c[0]
    assert abs(c["value"]["b/tf"] - (450 - 32) / 16.0) < 0.01          # (B - 2 tw)/tf = 26.1
    assert abs(c["value"]["d/tw"] - (450 - 32) / 16.0) < 0.01
    fy = 250.0 if 16.0 <= 20 else 240.0
    lim = 21.4 * (250.0 / fy) ** 0.5 / 1.4 ** 0.5                       # closed-box row (iii), flagged basis
    assert abs(c["limit"]["b/tf"] - round(lim, 2)) < 0.02
    assert c["ok"] is False and "no explicit row" in c["basis"]


def test_box_brace_uses_closed_box_row():
    S.register_box("BOX200X200X12", 200.0, 200.0, 12.0, 12.0)
    p = S.props("BOX200X200X12")
    r = I18.table2_check("brace", p, 250.0, 1.4)
    assert r["table2_row"] == "brace_box" and abs(r["value"]["b/tf"] - (200 - 24) / 12.0) < 0.01
    assert "basis" not in r
    assert I18.table2_check("brace", S.props("CHS193.7X6.3", grade="YSt 310", process="HFS"), 310.0, 1.4)["ok"] is None


def test_table2_live_without_opt_in_and_opt_out_only_outside_iii_v():
    md = _md([{"id": "b1", "section": "NPB450X190X67.16", "grade": "E250 B0", "role": "beam", "L_mm": 6000.0,
               "sfrs": True}])
    r = S12.section12_checks("SMF", md, {"zone": "III", "I": 1.2, "height_m": 12.0, "is18168_table2": False})
    assert [c for c in r["checks"] if c["id"] == "is18168_table2_beam"]
    assert any("ignored" in (a.get("note") or "") for a in r["advisories"])
    r2 = S12.section12_checks("SMF", md, {"zone": "II", "I": 1.0, "apply_is18168": True, "is18168_table2": False})
    assert not [c for c in r2["checks"] if c["id"] == "is18168_table2_beam"]
    r3 = S12.section12_checks("SMF", md, {"zone": "II", "I": 1.0, "apply_is18168": True})
    assert [c for c in r3["checks"] if c["id"] == "is18168_table2_beam"]
