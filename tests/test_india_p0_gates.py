"""P0 gates: Ta fail-closed (H1), wind evidence (S5/H2), SI geometry (S4), CuTa off (S3)."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "steel_engine"))

import india_loads as IL
import india_seismic as IS
import consistency as C
import pytest


def _base_plan(**extra):
    plan = {
        "jurisdiction": "india",
        "retrieval": [
            {"stem": "IS_875_Part_2_1987", "query": "imposed loads", "found": True, "cite": "Table 1"},
            {"stem": "IS_1893_Part_1_2016", "query": "zone factor", "found": True, "cite": "Table 3"},
            {"stem": "IS_875_Part_3_2015", "query": "basic wind speed Delhi", "found": True, "cite": "Annex A"},
            {"stem": "IS_800_2007", "query": "partial factors", "found": True, "cite": "Table 4"},
        ],
        "wind_summary": {"VB_x_kN": 100.0, "VB_y_kN": 120.0},
        "combinations": [
            {"label": "1.5DL+1.5LL", "fD": 1.5, "fL": 1.5, "fLr": 0.0,
             "lateral": {}, "cite": "IS 800:2007 Table 4"},
            {"label": "1.5DL+1.5WL_X", "fD": 1.5, "fL": 0.0, "fLr": 0.0, "fW": 1.5, "units": "N",
             "lateral": {"1": [50.0, 0.0, 0.0]}, "cite": "IS 800 + IS 875 P3"},
        ],
    }
    plan.update(extra)
    return plan


def test_approximate_Ta_scbf_all_other():
    r = IS.approximate_Ta(h_m=18.0, d_m=24.0, system="SCBF")
    assert r["kind"] == "all_other"
    assert abs(r["Ta_s"] - 0.09 * 18.0 / (24.0 ** 0.5)) < 1e-9
    assert "0.09" in r["formula"]


def test_approximate_Ta_steel_mrf():
    r = IS.approximate_Ta(h_m=18.0, system="SMRF", material="steel")
    assert r["kind"] == "steel_mrf"
    assert abs(r["Ta_s"] - 0.085 * (18.0 ** 0.75)) < 1e-9


def test_Ta_fail_closed_non_mrf_with_mrf_formula():
    with pytest.raises(IS.TaFormulaError):
        IS.approximate_Ta(h_m=18.0, d_m=24.0, system="SCBF", formula="0.085 h^0.75")
    cfg = {
        "system": "SCBF",
        "seis": {"SDS": 0.1},
        "load_plan": _base_plan(seismic_summary={
            "system": "SCBF",
            "Ta_s": 0.74,
            "Ta_formula": "0.085 h^0.75 steel MRF",
        }),
    }
    findings = IL.validate_load_plan(cfg)
    assert any(("fail-closed" in m) or ("7.6.2" in m and "MRF" in m) for s, m in findings if s == "ERROR")


def test_Ta_ok_for_scbf_009():
    cfg = {
        "system": "SCBF",
        "seis": {"SDS": 0.1},
        "load_plan": _base_plan(seismic_summary={
            "system": "SCBF",
            "Ta_s": 0.331,
            "Ta_formula": "0.09 h/√d (§7.6.2(c) all other buildings)",
        }),
    }
    findings = IL.validate_load_plan(cfg)
    assert not any("7.6.2" in m and s == "ERROR" for s, m in findings)


def test_wind_gate_requires_part3_or_no_wind():
    cfg = {
        "seis": {"SDS": 0.1},
        "load_plan": {
            "jurisdiction": "india",
            "retrieval": [
                {"stem": "IS_875_Part_2_1987", "query": "ll", "found": True, "cite": "T1"},
                {"stem": "IS_1893_Part_1_2016", "query": "Z", "found": True, "cite": "T3"},
            ],
            "combinations": [
                {"label": "1.5D", "fD": 1.5, "fL": 0, "fLr": 0, "cite": "x"},
            ],
        },
    }
    findings = IL.validate_load_plan(cfg)
    assert any("Wind gate" in m for s, m in findings if s == "ERROR")


def test_wind_gate_found_false_needs_no_wind_reason():
    cfg = {
        "seis": {"SDS": 0.1},
        "load_plan": {
            "jurisdiction": "india",
            "retrieval": [
                {"stem": "IS_875_Part_2_1987", "query": "ll", "found": True, "cite": "T1"},
                {"stem": "IS_1893_Part_1_2016", "query": "Z", "found": True, "cite": "T3"},
                {"stem": "IS_875_Part_3_2015", "query": "Cp", "found": False, "cite": "OCR gap"},
            ],
            "combinations": [
                {"label": "1.5D", "fD": 1.5, "fL": 0, "fLr": 0, "cite": "x"},
            ],
        },
    }
    findings = IL.validate_load_plan(cfg)
    assert any("found:false" in m and "no_wind" in m for s, m in findings if s == "ERROR")
    cfg["load_plan"]["no_wind"] = "enclosed underground plant room — no wind exposure"
    findings2 = IL.validate_load_plan(cfg)
    assert not any("Wind gate" in m for s, m in findings2 if s == "ERROR")


def test_wind_gate_found_true_requires_laterals():
    cfg = {
        "seis": {"SDS": 0.1},
        "load_plan": {
            "jurisdiction": "india",
            "retrieval": [
                {"stem": "IS_875_Part_2_1987", "query": "ll", "found": True, "cite": "T1"},
                {"stem": "IS_1893_Part_1_2016", "query": "Z", "found": True, "cite": "T3"},
                {"stem": "IS_875_Part_3_2015", "query": "Vb", "found": True, "cite": "Annex A"},
            ],
            "combinations": [
                {"label": "1.5DL+1.5LL", "fD": 1.5, "fL": 1.5, "fLr": 0, "cite": "T4"},
            ],
        },
    }
    findings = IL.validate_load_plan(cfg)
    assert any(s == "ERROR" and ("laterals" in m.lower() or "silently omit" in m) for s, m in findings)
    cfg["load_plan"]["wind_summary"] = {"VB_x_kN": 10.0, "VB_y_kN": 12.0}
    cfg["load_plan"]["combinations"].append(
        {"label": "1.5DL+1.5WL", "fD": 1.5, "fL": 0, "fLr": 0,
         "lateral": {"1": [1.0, 0, 0]}, "cite": "P3"}
    )
    findings2 = IL.validate_load_plan(cfg)
    assert not any("Wind gate" in m for s, m in findings2 if s == "ERROR")


def test_si_geometry_accepts_mm_storeys():
    cfg = {"units": "N-mm", "jurisdiction": "india", "heights": [3600, 3600, 3600], "SX": 6000, "SY": 6000}
    assert C._geometry_issues(cfg) == []


def test_si_geometry_flags_metre_slip():
    cfg = {"units": "N-mm", "jurisdiction": "india", "heights": [3.6, 3.6], "SX": 6, "SY": 6}
    msgs = C._geometry_issues(cfg)
    assert any("millimetre" in m.lower() or "METRES" in m for m in msgs)


def test_viewer_si_helper():
    import viewer3d as V
    assert V._viewer_si({"units": "N-mm", "jurisdiction": "india"}) is True
    assert V._viewer_si({"units": "kip-in", "force_kip_in": True}) is False


def test_period_gate_disabled_for_india():
    src = (ROOT / "steel_engine" / "engine3d.py").read_text()
    start = src.find("def _india_job")
    assert start > 0
    rest = src[start:]
    cut = rest.find("\ndef ", 5)
    cut2 = rest.find("\ndef ", cut + 5)
    ns = {}
    exec(rest[:cut2], ns)
    assert ns["_period_check_ok"]({"units": "N-mm", "jurisdiction": "india"}, 0.05, 0.33) is True
    assert ns["_period_check_ok"]({"units": "kip-in"}, 5.0, 0.5) is False
    assert ns["_period_check_ok"]({"units": "kip-in"}, 1.0, 0.5) is True
