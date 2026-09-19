"""P1: India drift UI (S2), §12 connection stubs (H5), Ka/Cpe overrides (S6)."""
import ast
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "steel_engine"))

import india_loads as IL
import india_wind_tables as WT
import consistency as C
from design_pipeline import _section12_component_stubs


def test_ka_table4_breakpoints_and_interp():
    assert WT.ka_for_area_m2(5.0)["Ka"] == 1.0
    assert abs(WT.ka_for_area_m2(25.0)["Ka"] - 0.9) < 1e-9
    assert abs(WT.ka_for_area_m2(100.0)["Ka"] - 0.8) < 1e-9
    assert abs(WT.ka_for_area_m2(200.0)["Ka"] - 0.8) < 1e-9
    mid = WT.ka_for_area_m2(17.5)["Ka"]
    assert 0.9 < mid < 1.0
    assert WT.ka_for_area_m2(10.0)["found"] is True
    assert "Table 4" in WT.ka_for_area_m2(10.0)["cite"]


def test_ka_prefers_corpus_policy():
    pol = WT.override_policy()
    assert "exact_table 4" in pol["Ka_Table_4"]["prefer"]
    assert "Docling" in pol["Cpe_Table_5_walls"]["do_not_use"]
    # india_loads wrappers
    assert IL.ka_fallback(25.0)["Ka"] == 0.9
    assert "corpus" in IL.wind_table_override_policy()["Ka_Table_4"]["prefer"].lower() or \
           "exact_table" in IL.wind_table_override_policy()["Ka_Table_4"]["prefer"]


def test_cpe_walls_verified_override_common_band():
    r = WT.cpe_walls(0.4, 1.2, 0)  # h/w<=0.5, 1<l/w<=1.5, theta=0
    assert r["found"] is True
    assert r["Cpe"]["A"] == 0.7
    assert r["Cpe"]["B"] == -0.2
    assert r["Cpe_local"] == -0.8
    assert "OCR" in r["cite"] or "override" in r["cite"].lower()
    r90 = WT.cpe_walls(0.4, 1.2, 90)
    assert r90["Cpe"]["C"] == 0.7


def test_cpe_walls_refuses_outside_band_and_bad_angle():
    # h/w>=6 only ships discrete l/w = 1, 1.5, 2
    miss = WT.cpe_walls(7.0, 1.25, 0)
    assert miss["found"] is False
    assert miss["Cpe"] is None
    bad = WT.cpe_walls(0.4, 1.2, 45)
    assert bad["found"] is False


def test_cpe_ocr_not_authoritative_flag():
    assert WT.TABLE_5_CPE_WALLS["ocr_trust"] is False
    assert WT.TABLE_5_CPE_WALLS["source"] == "verified_pdf_override"
    assert WT.TABLE_4_KA["source"] == "corpus_preferred"


def test_section12_stubs_structure():
    ws = _section12_component_stubs("brace")
    assert ws["status"] == "stubs"
    comps = {s["component"] for s in ws["slots"]}
    assert comps == {"gusset", "bolts", "welds"}
    for s in ws["slots"]:
        assert s["found"] is False
        assert s["DC"] is None
        assert s["capacity"] == {}
        assert s["size"] is None
        assert s["limit_state"] is None


def test_report_chapter8_has_no_usa_drift_scaffold():
    """Static source gate: Chapter 8 body must not emit Table 12.12-1 / Cd/Ie / 0.025 defaults."""
    src = (ROOT / "steel_engine" / "report.py").read_text()
    # Chapter 8 seismic block (after our patch)
    assert "Seismic design storey drift (IS 1893)" in src
    assert "No</b> ASCE C<sub>d</sub>/I<sub>e</sub>" in src or "No ASCE" in src
    assert "0.025h" in src  # mentioned as stripped
    # The old USA amplification table headers must not remain in the Chapter 8 path
    assert "&delta;e X %" not in src or "design &delta; X %" in src
    # Checklist India text
    assert "0.004 h (IS 1893" in src
    assert "Table 12.12-1 / C<sub>d</sub>/I<sub>e</sub> rows" in src


def test_report_no_table_1212_label_on_limtxt():
    src = (ROOT / "steel_engine" / "report.py").read_text()
    # Old path labelled allowable as "(Table 12.12-1)" next to lim*100
    assert 'if limrho else " (Table 12.12-1)"' not in src
    assert "cfg.get('drift_limit',0.020)" not in src.split("Seismic design storey drift")[1][:800] \
        if "Seismic design storey drift" in src else True


def test_consistency_skips_asce_drift_for_india():
    cfg = {
        "units": "N-mm",
        "jurisdiction": "india",
        "seis": {"SDS": 0.2, "SD1": 0.1, "Ie": 1.5, "R": 4.5},
        "drift_limit": 0.004,
        "heights": [3600, 3600],
        "system": "SCBF",
    }
    # Call the design-basis helper if accessible; else check source
    src = (ROOT / "steel_engine" / "consistency.py").read_text()
    assert "S2: India" in src or "IS 1893 cl.7.11.1.1" in src
    assert "Table 12.12-1" in src  # still present for non-India branch
    # India path must not append Table 12.12-1 for Ie=1.5 with dl=0.004
    # Use _design_basis_issues when importable without full pkg
    issues = C._design_basis_issues(cfg, "Ex", {"members": [], "connections": [{"id": "x"}]})
    assert not any("Table 12.12-1" in m for m in issues)


def test_design_pipeline_source_wires_stubs():
    src = (ROOT / "steel_engine" / "design_pipeline.py").read_text()
    assert "section12_worksheet" in src
    assert "_section12_component_stubs" in src
    assert "component_checks" in src
