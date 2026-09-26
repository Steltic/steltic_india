"""RR-BUG-5 (H34 follow-up): when the IS 800 Table 3 slenderness ratio governs the member D/C, the member record names
the governing check 'IS 800 Table 3 slenderness' with its own value / limit / combination, and the 9.3 interaction
stays reported as the interaction (CFS Ex2 brace: the '9.3 interaction' row showed 0.845 = KL/r 152/180 for an
interaction of 0.068)."""
import json
import os
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "steel_engine"))

import india_is800 as I8  # noqa: E402
import sections as S  # noqa: E402
import design_pipeline as DP  # noqa: E402

SEC = "WPB220X220X71.47"


def _brace(klr=152.0):
    p = S.props(SEC)
    r = min(p.get("ry") or 1e9, p.get("rx") or 1e9, p.get("r_min") or 1e9)
    return {"id": "brace", "section": SEC, "grade": "E250 B0", "role": "brace", "L_mm": klr * r, "Kz": 1.0,
            "Ky": 1.0, "LLT_sag_mm": klr * r}


CF = [{"combo": "1.5DL+1.5LL", "P_N": 40e3, "Mz_i_Nmm": 0, "Mz_j_Nmm": 0, "My_i_Nmm": 0, "My_j_Nmm": 0, "Vy_N": 0},
      {"combo": "1.2DL+1.2LL+1.2EQ_X", "P_N": 60e3, "Mz_i_Nmm": 0, "Mz_j_Nmm": 0, "My_i_Nmm": 0, "My_j_Nmm": 0,
       "Vy_N": 0}]


def test_table3_governs_record_names_it():
    r = I8.member_check_is800(_brace(), CF)
    t3 = r["table3_slenderness"]
    assert "(i)" in t3["cite"] and t3["limit"] == 180
    assert t3["value"] == pytest.approx(152.0, rel=0.02)
    # the interaction is small and stays reported as the interaction
    assert r["interaction_dc"] < 0.3 < t3["dc"]
    assert r["interaction_governing_combo"] == "1.2DL+1.2LL+1.2EQ_X"
    # the governing check is Table 3, with its own value / limit / combination (largest compression)
    assert r["governing_check"] == "IS 800 Table 3 slenderness"
    assert r["dc"] == pytest.approx(t3["dc"]) and r["value"] == pytest.approx(t3["value"]) and r["limit"] == 180
    assert r["governing_combo"] == t3["governing_combo"] == "1.2DL+1.2LL+1.2EQ_X"
    assert "Table 3" in r["cite"] and "9.3 interaction" in r["cite"]
    json.dumps(r, allow_nan=False, default=str)

    rows = DP._check_rows(r)
    i93 = [x for x in rows if x["name"].startswith("IS 800 9.3 interaction")][0]
    t3r = [x for x in rows if x["name"].startswith("IS 800 Table 3")][0]
    assert i93["value"] == pytest.approx(r["interaction_dc"]) and i93["dc"] == pytest.approx(r["interaction_dc"])
    assert "governing" not in i93["name"] and i93["governing"] is False
    assert t3r["governing"] is True and "governing" in t3r["name"] and "1.2DL+1.2LL+1.2EQ_X" in t3r["name"]
    assert max(x["dc"] for x in rows) == pytest.approx(r["dc"])
    # the governing-combination record kept for the report is the 9.3 interaction's
    g = DP._governing_result(r)
    assert g["governing_combo_record"]["combo"] == "1.2DL+1.2LL+1.2EQ_X"


def test_interaction_governs_unchanged():
    m = _brace(klr=60.0)
    p = S.props(SEC)
    cf = [dict(CF[0], P_N=0.8 * p["A"] * 250 / 1.1)]
    r = I8.member_check_is800(m, cf)
    assert r["governing_check"] == "IS 800 9.3 interaction / member resistance"
    assert r["dc"] == pytest.approx(r["interaction_dc"]) and r["limit"] == 1.0 and r["value"] == r["dc"]
    assert r["cite"].startswith("IS 800:2007 9.3.2.2")
    rows = DP._check_rows(r)
    assert rows[0]["name"].startswith("IS 800 9.3 interaction / member resistance (governing combination")
    assert rows[0]["governing"] is True and rows[1]["governing"] is False
