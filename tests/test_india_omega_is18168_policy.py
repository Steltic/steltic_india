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


def test_refuse_concrete_is15988_is13920_corpus_even_if_found_true():
    """IS 15988 / IS 13920 are concrete — never steel Ω, even with a HIT value."""
    for src in ("is15988", "is13920", "is_15988", "is_13920",
                "is15988_2013", "is13920_2016"):
        r = ISG.resolve_Omega0(
            {},
            corpus_hit={
                "found": True,
                "source": src,
                "Omega": 2.5,
                "cite": "concrete code — must not resolve for steel",
            },
        )
        assert r["found"] is False, src
        assert r["Omega0"] is None, src
        note = (r.get("note") or "").lower()
        cite = (r.get("cite") or "").lower()
        assert "concrete" in note or "concrete" in cite, src
        assert "15988" in note or "13920" in note or "15988" in cite or "13920" in cite, src


def test_refuse_omega0_source_is15988_is13920_with_cite():
    """Literal Omega0_source pointing at concrete codes is refused."""
    for src in ("is15988", "is13920", "is_15988", "is_13920"):
        r = ISG.resolve_Omega0(
            {
                "Omega0": 2.5,
                "Omega0_source": src,
                "Omega0_cite": "IS %s — must not be steel overstrength" % src,
            }
        )
        assert r["found"] is False, src
        assert r["Omega0"] is None, src
        blob = ((r.get("note") or "") + " " + (r.get("cite") or "")).lower()
        assert "concrete" in blob, src
        assert src.replace("_", "") in blob.replace("_", "") or "15988" in blob or "13920" in blob, src


def test_policy_note_names_is18168_only_and_refuses_concrete():
    note = (ISG.OMEGA0_POLICY.get("note") or "").lower()
    assert "is 18168" in note or "18168" in note
    assert "15988" in note and "13920" in note
    assert "concrete" in note
    for key in ("is15988", "is_15988", "is13920", "is_13920",
                "is15988_2013", "is13920_2016"):
        assert key in ISG.OMEGA0_REFUSED, key
