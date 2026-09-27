"""IS 18168 live Ω corpus HIT → resolve_Omega0 (no invent / no hardcoded defaults)."""
from __future__ import annotations

import ast
import inspect
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "steel_engine"))

import india_seismic_gates as ISG
import india_omega_is18168 as IO


# Fixture text for the §5.5 HIT. Digits VERIFIED against the IS 18168:2023 PDF cl. 5.5 (pdf p. 7) in WP2.4:
# 'Ω = Overstrength factor = 2.5 for SCBFs and EBFs = 3.0 for SMRFs'.
_FIXTURE_SEC55_TEXT = """## 5.5 Loads and Load Combinations

Design earthquake loads ( EL ) shall be estimated and combined as per IS 1893 (Part 1).
| EL m  | = | Estimated maximum equivalent earthquake force = Ω EL ; |
| Ω     | = | Overstrength factor = 2.5 for SCBFs and EBFs = 3.0 for SMRFs; and |
| EL    | = | Earthquake load as per IS 1893 (Part 1). |
"""


def _fixture_section_hit():
    parsed = IO.parse_omega_table_from_hit_text(_FIXTURE_SEC55_TEXT)
    assert parsed is not None
    return {
        "found": True,
        "source": "is18168",
        "cite": IO.IS18168_CITE,
        "Elm_rule": IO.IS18168_ELM_RULE,
        "section_id": "5.5",
        "hit_id": "spec:IS_18168_2023:standard:5.5:7",
        "pdf_page": 7,
        "doc": IO.IS18168_DOC,
        "text": _FIXTURE_SEC55_TEXT,
        "omega_by_sfrs": {
            "SCBF": parsed["SCBF"],
            "EBF": parsed["EBF"],
            "SMRF": parsed["SMRF"],
        },
        "raw_match": parsed.get("raw_match"),
        "note": "fixture §5.5 HIT",
    }


@pytest.mark.parametrize(
    "sfrs,expected",
    [
        ("SCBF", 2.5),
        ("scbf", 2.5),
        ("EBF", 2.5),
        ("ebf", 2.5),
        ("SMRF", 3.0),
        ("SMF", 3.0),
        ("smrf", 3.0),
    ],
)
def test_fixture_corpus_hit_maps_sfrs_omega(sfrs, expected):
    hit = IO.fetch_is18168_omega(sfrs, section_hit=_fixture_section_hit())
    assert hit["found"] is True
    assert hit["source"] == "is18168"
    assert hit["Omega"] == expected
    assert hit["cite"] == "IS 18168:2023 §5.5"
    assert hit["Elm_rule"] == "ELm=Ω·EL"
    assert hit["section_id"] == "5.5"
    r = ISG.resolve_Omega0({}, corpus_hit=hit)
    assert r["found"] is True
    assert r["Omega0"] == expected
    assert r["source"] == "is18168"
    assert r["resolved_via"] == "corpus"
    assert "§5.5" in r["cite"]
    assert "ELm=Ω·EL" in r["note"]


def test_resolve_with_helper_fixture_scbf():
    r = IO.resolve_Omega0_with_is18168(
        {"system": "SCBF", "Omega0_found": False},
        section_hit=_fixture_section_hit(),
    )
    assert r["found"] is True and r["Omega0"] == 2.5
    assert r["cite"] == IO.IS18168_CITE


def test_dual_and_unmapped_sfrs_honest_miss():
    sec = _fixture_section_hit()
    for sfrs in (
        "dual SMF + SCBF",
        "BRBF",
        "SPSW",
        "OCBF",
        "OCBF / steel OBF concentric perimeter",
        "IMF",
        "OMRF",
    ):
        hit = IO.fetch_is18168_omega(sfrs, section_hit=sec)
        assert hit["found"] is False, sfrs
        assert hit["Omega"] is None, sfrs
        r = ISG.resolve_Omega0({"Omega0_found": False, "system": sfrs}, corpus_hit=hit)
        assert r["found"] is False and r["Omega0"] is None, sfrs


def test_section_miss_returns_found_false():
    hit = IO.fetch_is18168_omega("SCBF", section_hit={"found": False, "note": "miss"})
    assert hit["found"] is False
    assert hit["Omega"] is None


def test_still_refuse_invent_literal_is18168_without_hit():
    invented = ISG.resolve_Omega0(
        {"Omega0": 2.5, "Omega0_source": "is18168", "Omega0_cite": "IS 18168 §5.5"}
    )
    assert invented["found"] is False
    assert invented["Omega0"] is None


def test_still_refuse_asce_and_concrete():
    asce = ISG.resolve_Omega0(
        {"Omega0": 3.0, "Omega0_source": "asce7", "Omega0_cite": "ASCE 7-22"}
    )
    assert asce["found"] is False and asce["Omega0"] is None
    concrete = ISG.resolve_Omega0(
        {},
        corpus_hit={
            "found": True,
            "source": "is15988",
            "Omega": 2.5,
            "cite": "concrete",
        },
    )
    assert concrete["found"] is False and concrete["Omega0"] is None


def test_no_magic_omega_constants_as_resolve_defaults():
    """resolve_Omega0 must not assign bare 2.5/3.0 as default Ω values."""
    src = inspect.getsource(ISG.resolve_Omega0)
    tree = ast.parse(src)
    # Walk Assign / AnnAssign / Return for bare numeric 2.5 / 3.0 used as Omega defaults
    forbidden = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and node.value in (2.5, 3.0):
            forbidden.append(node.value)
    assert not forbidden, (
        "resolve_Omega0 contains bare 2.5/3.0 literals — Ω must come only from "
        "corpus_hit found:true (got %r)" % (forbidden,)
    )
    # Also scan module-level defaults in india_seismic_gates for Omega invent tables
    mod_src = Path(ISG.__file__).read_text()
    # Allow the numbers only inside comments / docstrings / refuse-test notes —
    # enforce no assignment like Omega0 = 2.5 or "SCBF": 2.5 invent maps.
    for bad in (
        "Omega0 = 2.5",
        "Omega0 = 3.0",
        '"SCBF": 2.5',
        "'SCBF': 2.5",
        '"SMRF": 3.0',
        "'SMRF': 3.0",
        "DEFAULT_OMEGA",
        "OMEGA_DEFAULT",
    ):
        assert bad not in mod_src, bad


def test_parse_requires_hit_text_pattern():
    assert IO.parse_omega_table_from_hit_text("") is None
    assert IO.parse_omega_table_from_hit_text("no omega here") is None
    parsed = IO.parse_omega_table_from_hit_text(_FIXTURE_SEC55_TEXT)
    assert parsed["SCBF"] == parsed["EBF"] == 2.5
    assert parsed["SMRF"] == 3.0


@pytest.mark.skipif(
    not IO.corpus_available(),
    reason="no IS corpus (set INDIA_CORPUS_ROOT)",
)
def test_live_corpus_probe_is18168_section_55():
    """Optional integration: live exact_section 5.5 → SCBF/EBF/SMRF Ω."""
    sec = IO.fetch_is18168_section_55()
    assert sec["found"] is True, sec
    assert sec["section_id"] == "5.5"
    assert "omega_by_sfrs" in sec
    for sfrs, expected in (("SCBF", 2.5), ("EBF", 2.5), ("SMRF", 3.0)):
        hit = IO.fetch_is18168_omega(sfrs, section_hit=sec)
        assert hit["found"] is True
        assert hit["Omega"] == expected
        assert "§5.5" in hit["cite"]
        r = ISG.resolve_Omega0({"system": sfrs}, corpus_hit=hit)
        assert r["found"] is True and r["Omega0"] == expected
        assert r["resolved_via"] == "corpus"
