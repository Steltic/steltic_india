"""RR-BUG-6: a declared corpus Ka (site.Ka_corpus_hit) was returned unchanged for every tributary area, so the C02
per-direction Ka was defeated and the direction with the smaller area took a Ka below Table 4 (unconservative;
report repro: Ka 0.9467 declared for A = 18 m2 applied at A = 15.75 m2 where Table 4 gives 0.9617).  A declared Ka is
now per direction or an {area: Ka} table, or is checked against Table 4 at each direction's tributary area."""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "steel_engine"))
import india_wind_tables as WT  # noqa: E402
import india_loads as IL  # noqa: E402


def test_report_repro_single_ka_is_area_checked():
    hit = {"found": True, "Ka": 0.9467, "cite": "x"}
    r = WT.resolve_ka(15.75, hit)
    # Table 4: 1.0 + (0.9 - 1.0)(15.75 - 10)/(25 - 10) = 0.961667
    assert r["Ka"] == pytest.approx(0.961667, abs=1e-6) == WT.ka_for_area_m2(15.75)["Ka"]
    assert r["resolved_via"] == "table4_area_check" and r["area_check"]["ok"] is False
    assert r["Ka_declared"] == 0.9467 and "unconservative" in r["note"]
    # at the area it was declared for, the declared value stands
    r18 = WT.resolve_ka(18.0, hit)
    assert r18["Ka"] == 0.9467 and r18["resolved_via"] == "corpus" and r18["area_check"]["ok"] is True
    # a conservative (higher) declared value is kept
    assert WT.resolve_ka(60.0, {"found": True, "Ka": 1.0})["Ka"] == 1.0
    assert IL.resolve_ka(15.75, hit)["Ka"] == pytest.approx(0.961667, abs=1e-6)


def test_per_direction_and_area_table_forms():
    hit = {"found": True, "Ka_x": 0.95, "Ka_y": 0.90, "cite": "EOR"}
    assert WT.resolve_ka(18.0, hit, direction="X")["Ka"] == 0.95
    # Y declared 0.90 but Table 4 at 18 m2 = 0.9467 -> Table 4 value
    ry = WT.resolve_ka(18.0, hit, direction="Y")
    assert ry["Ka"] == pytest.approx(0.946667, abs=1e-6) and ry["direction"] == "Y"
    assert WT.resolve_ka(40.0, hit, direction="Y")["Ka"] == 0.90          # 0.90 >= 0.88 at 40 m2
    assert WT.resolve_ka(40.0, {"found": True, "Ka": {"X": 0.95, "Y": 0.9}}, direction="X")["Ka"] == 0.95
    tab = {"found": True, "table": {"10": 1.0, "25": 0.9, "100": 0.8}, "cite": "Table 4 rows"}
    assert WT.resolve_ka(15.75, tab)["Ka"] == pytest.approx(0.961667, abs=1e-6)
    assert WT.resolve_ka(62.5, {"found": True, "Ka": {10: 1.0, 25: 0.9, 100: 0.8}})["Ka"] == pytest.approx(0.85)


def test_preflight_checks_each_direction():
    cfg = {"load_plan": {"wind_summary": {"Ka": 0.9467, "Ka_area_m2": 18.0, "Ka_basis": "frame_tributary",
                                          "Ka_X": 0.9467, "Ka_area_X_m2": 18.0, "Ka_Y": 0.9467,
                                          "Ka_area_Y_m2": 15.75}}}
    msgs = [m for s, m in WT.wind_findings(cfg) if s == "ERROR"]
    assert any("Ka_Y = 0.9467" in m and "15.75" in m for m in msgs)
    assert not any(m.startswith("Ka_X") for m in msgs)
