"""India load_plan: refuse ASCE hardcoding; require RAG-backed combinations."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "steel_engine"))

import india_loads as IL
import pytest


def test_missing_load_plan_errors():
    findings = IL.validate_load_plan({})
    assert any(s == "ERROR" for s, _ in findings)


def test_rag_backed_plan_builds_cases():
    cfg = {
        "seis": {"SDS": 0.1},
        "load_plan": {
            "jurisdiction": "india",
            "no_wind": "unit-test fixture — wind not in scope for this gate test",
            "retrieval": [
                {"stem": "IS_875_Part_2_1987", "query": "imposed loads residential",
                 "found": True, "cite": "Table 1"},
                {"stem": "IS_1893_Part_1_2016", "query": "seismic zone factor",
                 "found": True, "cite": "Table 3"},
                {"stem": "IS_800_2007", "query": "partial safety factors combinations",
                 "found": True, "cite": "Table 4"},
            ],
            "combinations": [
                {"label": "1.5DL+1.5LL", "fD": 1.5, "fL": 1.5, "fLr": 0.0,
                 "lateral": {}, "cite": "IS 800:2007 Table 4"},
                {"label": "1.2DL+1.2EQ_X", "fD": 1.2, "fL": 0.0, "fLr": 0.0,
                 "lateral": {"1": [10.0, 0.0, 0.0]}, "cite": "IS 800 + IS 1893"},
            ],
        },
    }
    findings = IL.validate_load_plan(cfg)
    assert not any(s == "ERROR" for s, _ in findings)
    cases = IL.cases_from_load_plan(cfg)
    assert len(cases) == 2
    assert cases[0][0] == "1.5DL+1.5LL"
    assert cases[1][4][1][0] == 10.0


def test_asce_flag_forbidden():
    cfg = {
        "use_asce7_engine_loads": True,
        "load_plan": {
            "jurisdiction": "india",
            "no_wind": "unit-test fixture — wind not in scope for this gate test",
            "retrieval": [
                {"stem": "IS_875_Part_1_2026", "query": "dead", "found": True, "cite": "1"},
                {"stem": "IS_1893_Part_1_2016", "query": "Z", "found": True, "cite": "3"},
            ],
            "combinations": [
                {"label": "1.5D", "fD": 1.5, "fL": 0, "fLr": 0, "cite": "x"},
            ],
        },
    }
    findings = IL.validate_load_plan(cfg)
    assert any("use_asce7_engine_loads" in m for s, m in findings if s == "ERROR")


def test_wind_forces_disabled():
    pytest.importorskip("openseespy.opensees", reason="openseespy not installed in this interpreter")
    import engine3d as E
    with pytest.raises(RuntimeError, match="wind_forces"):
        E.wind_forces({"wind": {"V": 100, "exposure": "C"}, "heights": [120], "NX": 1, "NY": 1, "SX": 300, "SY": 300}, "X")
