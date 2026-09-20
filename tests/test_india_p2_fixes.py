"""P2 leftovers: corpus-prefer Ka/Cpe, H6 composite Ch.I stubs, H7 E250B process note."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "steel_engine"))

import india_loads as IL
import india_wind_tables as WT
from design_pipeline import _section12_component_stubs, _composite_chI_worksheet_stubs


def test_corpus_prefer_ka_uses_hit_not_fallback():
    hit = {"found": True, "Ka": 0.85, "cite": "corpus exact_table 4"}
    r = WT.resolve_ka(40.0, hit)
    assert r["resolved_via"] == "corpus"
    assert r["Ka"] == 0.85
    assert r["found"] is True
    # india_loads wrapper
    r2 = IL.resolve_ka(40.0, hit)
    assert r2["resolved_via"] == "corpus"


def test_corpus_prefer_ka_falls_back_when_found_false():
    r = WT.resolve_ka(25.0, {"found": False})
    assert r["resolved_via"] == "fallback"
    assert r["Ka"] == 0.9
    assert r["corpus_found"] is False


def test_corpus_prefer_cpe_walls_uses_hit():
    hit = {"found": True, "Cpe": {"A": 0.7, "B": -0.2, "C": -0.5, "D": -0.5},
           "cite": "corpus exact_table 5"}
    r = WT.resolve_cpe_walls(0.4, 1.2, 0, hit)
    assert r["resolved_via"] == "corpus"
    assert r["Cpe"]["A"] == 0.7
    r2 = IL.resolve_cpe_walls(0.4, 1.2, 0, hit)
    assert r2["resolved_via"] == "corpus"


def test_corpus_prefer_cpe_walls_falls_back_when_found_false():
    r = WT.resolve_cpe_walls(0.4, 1.2, 0, {"found": False})
    assert r["resolved_via"] == "fallback"
    assert r["found"] is True
    assert r["Cpe"]["A"] == 0.7
    assert "fallback" in r["cite"].lower() or "exact_table 5" in r["cite"]


def test_override_policy_table5_prefers_corpus():
    pol = WT.override_policy()
    assert "exact_table 5" in pol["Cpe_Table_5_walls"]["prefer"]
    assert "found:false" in pol["Cpe_Table_5_walls"]["fallback"]
    assert 5 in WT.CORPUS_LIVE_WIND_TABLES
    assert 4 in WT.CORPUS_LIVE_WIND_TABLES
    assert "IS875_P3_OCR_reingest" in pol["qfm_note"]
    # india_loads mirrors
    assert "exact_table 5" in IL.wind_table_override_policy()["Cpe_Table_5_walls"]["prefer"]


def test_table5_meta_is_corpus_preferred_fallback_ok():
    assert WT.TABLE_5_CPE_WALLS["source"] == "corpus_preferred"
    assert WT.TABLE_5_CPE_WALLS.get("fallback_ok") is True
    assert WT.TABLE_5_CPE_WALLS["ocr_trust"] is False
    assert WT.TABLE_4_KA["source"] == "corpus_preferred"


def test_composite_is11384_stubs_structure():
    """WP2.9: composite floors are IS 11384 (not in the corpus): found:false slots + the bare-steel / construction
    stage scope (no 'IS 800 Ch. I' -- that chapter does not exist)."""
    ws = _composite_chI_worksheet_stubs()
    assert ws["status"] == "stubs"
    comps = {s["component"] for s in ws["slots"]}
    assert {"is11384_composite_strength", "is11384_shear_connectors", "bare_steel_8_2", "construction_stage"} == comps
    assert "IS 11384" in ws["cite"] and "Ch. I" not in ws["cite"]
    for s in ws["slots"]:
        assert s["found"] is False
        assert s["DC"] is None
        assert s["capacity"] == {}


def test_section12_stubs_still_present():
    ws = _section12_component_stubs("brace")
    assert {s["component"] for s in ws["slots"]} == {"gusset", "bolts", "welds"}


def test_design_pipeline_seeds_composite_and_wires_stubs():
    src = (ROOT / "steel_engine" / "design_pipeline.py").read_text()
    assert "_composite_chI_worksheet_stubs" in src
    assert 'pkg["composite_design"]' in src
    assert "chI_worksheet" in src
    assert "section12_worksheet" in src


def test_agent_start_has_h6_h7_process_notes():
    src = (ROOT / "contract" / "AGENT_START.md").read_text()
    assert "H7 E250B procurement" in src
    assert "open procurement process" in src.lower() or "procurement process item" in src.lower()
    assert "H6 Composite" in src or "composite_design.chI_worksheet" in src
    assert "Do not invent" in src or "do not invent" in src


def test_composite_india_note_is11384_found_false():
    """WP2.9: composite = IS 11384 (not in corpus) -> found:false; no 'IS 800 Ch. I', no AISC I3/I8."""
    src = (ROOT / "steel_engine" / "COMPOSITE_INDIA.md").read_text()
    assert "found:false" in src and "IS 11384" in src and "bare steel" in src.lower()
    assert "invent" in src.lower()
    import re
    body = src.split("## Never")[0]
    assert not re.search(r"I3\.1a|I8\.2a|Qn|psf|IS 800 Ch\. I\b", body)
