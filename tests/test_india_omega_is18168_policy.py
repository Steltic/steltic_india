"""IS 1893 / IS 18168 India overstrength policy contract tests."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "steel_engine"))

import india_seismic_gates as ISG


def test_honest_is1893_omega0_miss_is_non_blocking_and_disclosed():
    cfg = {
        "system": "SCBF",
        "R": 4.5,
        "R_source": "eor_documented",
        "R_cite": "EOR example — IS 1893 Table 9 row review",
        "Omega0_found": False,
    }
    r = ISG.resolve_Omega0(cfg)
    assert r["found"] is False
    assert r["Omega0"] is None
    assert r["omega0_policy"]["blocks_complete"] is False
    assert r["omega0_policy"]["preferred_source_when_available"] == "is18168"
    d = ISG.complete_gate_disclosure(cfg)
    assert d["complete_allowed"] is True
    assert d["omega0_policy"]["blocks_complete"] is False
    assert d["disclosure"]["preferred_source_when_available"] == "is18168"


def test_is18168_corpus_hit_resolves_and_uses_hit_cite():
    cite = "IS 18168:2023, steel SFRS overstrength table, §7"
    r = ISG.resolve_Omega0(
        {},
        corpus_hit={"found": True, "source": "is18168", "Omega": 2.5, "cite": cite},
    )
    assert r["found"] is True
    assert r["Omega0"] == 2.5
    assert r["source"] == "is18168"
    assert r["resolved_via"] == "corpus"
    assert r["cite"] == cite
    assert "ELm=Ω·EL" in r["note"]


def test_is18168_alias_and_values_require_found_true_corpus_hit():
    hit = ISG.resolve_Omega0(
        {},
        corpus_hit={"found": True, "source": "is_18168", "Omega0": 3.0, "cite": "IS 18168 §7"},
    )
    assert hit["found"] is True and hit["Omega0"] == 3.0

    invented = ISG.resolve_Omega0(
        {"Omega0": 3.0, "Omega0_source": "is18168", "Omega0_cite": "IS 18168 §7"}
    )
    assert invented["found"] is False
    assert invented["Omega0"] is None
    assert "found:true corpus hit" in invented["note"]

    miss = ISG.resolve_Omega0(
        {},
        corpus_hit={"found": False, "source": "is18168", "Omega": 2.5, "cite": "IS 18168"},
    )
    assert miss["found"] is False and miss["Omega0"] is None


def test_asce_omega0_still_refused():
    r = ISG.resolve_Omega0(
        {"Omega0": 3.0, "Omega0_source": "asce7", "Omega0_cite": "ASCE 7-22 Table 12.2-1"}
    )
    assert r["found"] is False
    assert r["Omega0"] is None
    assert "ASCE" in r["cite"] or "asce" in r["note"].lower()

    corpus_asce = ISG.resolve_Omega0(
        {},
        corpus_hit={"found": True, "source": "asce7", "Omega0": 3.0, "cite": "ASCE 7-22"},
    )
    assert corpus_asce["found"] is False
    assert corpus_asce["Omega0"] is None
