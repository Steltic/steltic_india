"""WP2.10 -- the assembled India system prompt carries no US-code residue; UI lists the IN briefs only."""
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


def _prompt():
    import sys
    for q in (str(ROOT), str(ROOT / "steel_engine")):
        if q not in sys.path:
            sys.path.insert(0, q)
    from steltic import contract
    return contract


def test_system_prompt_has_no_us_residue():
    c = _prompt()
    from india_contract_residue import contract_hits
    for imgs in (False, True):
        hits = contract_hits(c.system_prompt(has_images=imgs))
        assert hits == [], hits[:5]


def test_contract_files_loaded_and_present():
    c = _prompt()
    t = c.system_contract()
    assert "[missing" not in t
    assert "IS 800:2007 CLAUSE MAP" in t and "WORKED METHOD" in t
    for f in c.CONTRACT_FILES:
        assert (ROOT / "contract" / f).exists()
    for f in ("III1_REFERENCE.md", "DESIGN_EG_INDEX.md", "AISC360_TOC.md"):
        assert not (ROOT / "contract" / f).exists()
        assert (ROOT / "contract" / "usa_reference" / f).exists()


@pytest.mark.parametrize("phrase", [
    r"computed, not retrieved", r"\bCd\b", r"R\s*(<=|≤)\s*3", r"Ω0|Omega0|Ω", r"RyFy", r"A992", r"\bIEBC\b",
    r"ASCE\s*41", r"0\.85\s*(·|x)?\s*ELF", r"\bELF\b", r"\bLRFD\b", r"\bAISC\b", r"feet|inches"])
def test_hrload17_items_deleted(phrase):
    t = _prompt().system_prompt()
    assert not re.search(phrase, t), phrase


def test_prompt_states_india_basis():
    t = _prompt().system_prompt()
    for must in ("Table 4", "7.8.2", "12.2.3", "7.7.1", "0.004 h", "R x", "kN/m2", "story_forces_units"):
        assert must in t, must


def test_frontend_lists_only_india_briefs():
    html = (ROOT / "frontend" / "index.html").read_text(encoding="utf-8")
    i0 = html.index('id="exampleSelect"')
    sel = html[i0:html.index("</select>", i0)]
    vals = re.findall(r'<option value="([^"]*)"', sel)
    assert [v for v in vals if v] == ["in%d" % i for i in range(1, 16)]
    assert not re.search(r"\bpsf\b|\bmph\b|\bSDC\b", html)
    tb = ROOT / "test_buildings"
    assert not list(tb.glob("Ex*.txt"))
    assert len(list((tb / "usa_reference").glob("Ex*.txt"))) >= 35
    main = (ROOT / "steltic" / "main.py").read_text(encoding="utf-8")
    for i in range(1, 16):
        m = re.search(r'"in%d": "([^"]+)"' % i, main)
        assert m and (tb / m.group(1)).exists()
