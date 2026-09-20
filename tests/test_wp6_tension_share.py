"""WP6-fix: IS 800 12.8.2.4 / 12.7.2.3 tension share is taken on the LATERAL load only (EQ-only static case),
never on DL+EQ where gravity compression can swamp the split (CFS Ex1 read 2 %)."""
import re, sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "steel_engine"))
import india_is800_s12 as S12


def _md(pA, pB):
    return {"members": [{"id": "A", "role": "brace", "cos_h": 0.8}, {"id": "B", "role": "brace", "cos_h": 0.8}],
            "forces": {"A": [{"combo": "TS:+1.0EQ_X", "P_N": pA}], "B": [{"combo": "TS:+1.0EQ_X", "P_N": pB}]},
            "brace_lines": [{"id": ("X", 1), "braces": ["A", "B"], "combos": {"+": "TS:+1.0EQ_X"}}]}


def test_x_brace_eq_only_split_is_half():
    r = S12.tension_share_checks("SCBF", _md(-100e3, +100e3))
    assert len(r) == 1 and r[0]["ok"] is True and abs(r[0]["value"] - 0.5) < 1e-9
    assert r[0]["clause"].startswith("IS 800:2007 12.8.2.4")


def test_pipeline_ts_case_has_no_gravity():
    src = open(os.path.join(os.path.dirname(__file__), "..", "steel_engine", "design_pipeline.py")).read()
    m = re.search(r'lab = "TS:%s1\.0EQ_%s".*?"fD": (\d\.\d)', src, re.S)
    assert m and m.group(1) == "0.0"
