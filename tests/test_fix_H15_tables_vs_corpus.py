"""H15 (HR-E-25, L-15, C3): the in-repo IS 875-3 Table 5 / Table 6 transcriptions equal the corpus recovered
files cell by cell; Table 5 band edges follow the printed inequalities; an EOR Cpe path exists outside the table."""
import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "steel_engine"))
import india_wind_tables as W  # noqa: E402

_STEM = "IS_875_Part_3_2015"
_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from steltic.india_collections import india_corpus_root  # noqa: E402

# The corpus is the user's own (built in the Steltic hub from licensed BIS PDFs): $INDIA_CORPUS_ROOT, else the
# sibling-folder fallback of india_corpus_root(). The published default has none, and these tests skip.
_CANDIDATES = [
    os.environ.get("INDIA_CORPUS_ROOT") or "",
    os.environ.get("ENGINEERING_RAG_INDIA") or "",
    india_corpus_root(),
]


def _std_dir():
    for c in _CANDIDATES:
        d = os.path.join(c, "documents", "standards", _STEM) if c else ""
        if d and os.path.isdir(d):
            return d
    return None


STD = _std_dir()
needs_corpus = pytest.mark.skipif(STD is None, reason="no IS corpus (set INDIA_CORPUS_ROOT)")


def _num(s):
    s = s.strip().replace("−", "-").replace("+", "")
    return float(s)


def _ratio_key(s):
    """'l/w = 3/2' -> 1.5 ; 'l/w = 1.0' -> 1.0 (h/w >= 6 rows)."""
    v = s.split("=")[1].strip()
    if "/" in v:
        a, b = v.split("/")
        return float(a) / float(b)
    return float(v)


@needs_corpus
def test_table5_every_cell_equals_corpus():
    import csv
    rows = list(csv.reader(open(os.path.join(STD, "tables", "Table_5_recovered.csv"), encoding="utf-8")))[1:]
    assert len(rows) == 18
    hw_mid = {"h/w ≤ 1/2": 0.3, "1/2 < h/w ≤ 3/2": 1.0, "3/2 < h/w < 6": 3.0, "h/w ≥ 6": 8.0}
    lw_mid = {"1 < l/w ≤ 3/2": 1.25, "3/2 < l/w < 4": 2.5, "1 ≤ l/w ≤ 3/2": 1.25, "3/2 ≤ l/w < 4": 2.5}
    for hw_s, lw_s, th, A, B, C, D, loc in rows:
        hw = hw_mid[hw_s]
        lw = lw_mid.get(lw_s) if lw_s in lw_mid else _ratio_key(lw_s)
        r = W.cpe_walls(hw, lw, float(th))
        assert r["found"], (hw_s, lw_s, th)
        assert r["Cpe"] == {"A": _num(A), "B": _num(B), "C": _num(C), "D": _num(D)}, (hw_s, lw_s, th)
        assert r["Cpe_local"] == _num(loc), (hw_s, lw_s, th)
    assert len(W.TABLE_5_CPE_WALLS["rows"]) == 18


@needs_corpus
def test_table6_every_cell_equals_corpus():
    txt = open(os.path.join(STD, "markdown", "pages_recovered", "page_016.md"), encoding="utf-8").read()
    band = {"h/w ≤ 1/2": "le_0.5", "1/2 < h/w ≤ 3/2": "0.5_1.5", "3/2 < h/w < 6": "1.5_6"}
    n = 0
    for line in txt.splitlines():
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if len(cells) < 6 or cells[0] not in band:
            continue
        b, a = band[cells[0]], int(cells[1])
        want = tuple(_num(c) for c in cells[2:6])
        assert W.TABLE_6_CPE_PITCHED[b][a] == want, (cells[0], a, W.TABLE_6_CPE_PITCHED[b][a], want)
        n += 1
    assert n == sum(len(v) for v in W.TABLE_6_CPE_PITCHED.values()) == 22


def test_table6_fh_mid_band_is_minus_08():
    assert W.roof_cpe_pitched(1.0, 30)["FH"] == -0.8
    assert W.roof_cpe_pitched(1.0, 60)["FH"] == -0.8
    assert abs(W.roof_cpe_pitched(1.0, 25)["FH"] - (-0.7)) < 1e-12   # interpolated 20 -> 30


def test_table5_band_edges_as_printed():
    # 3/2 < h/w < 6 and h/w >= 6: h/w = 6.0 goes to the h/w >= 6 rows
    assert W.cpe_walls(6.0, 1.0, 0)["band"]["h_over_w"] == ">=6"
    assert W.cpe_walls(5.99, 1.0, 0)["band"]["h_over_w"] == "1.5<h/w<6"
    # l/w < 4 in every band: l/w = 4.0 has no row
    for hw in (0.3, 1.0, 3.0):
        assert W.cpe_walls(hw, 3.99, 0)["found"]
        assert W.cpe_walls(hw, 4.0, 0)["found"] is False


def test_eor_cpe_path_outside_table():
    r = W.resolve_cpe_walls(0.3, 5.0, 0.0)
    assert r["found"] is False and r["source"] == "refused_band"
    bad = W.resolve_cpe_walls(0.3, 5.0, 0.0, eor_cpe={"Cpe": {"A": 0.7, "B": -0.3, "C": -0.7, "D": -0.7}})
    assert bad["found"] is False and any("verify" in m for m in bad["required_inputs"])
    ok = W.resolve_cpe_walls(0.3, 5.0, 0.0, eor_cpe={"Cpe": {"A": 0.7, "B": -0.3, "C": -0.7, "D": -0.7},
                                                     "source": "eor_documented", "cite": "EOR memo W-3",
                                                     "verify": True})
    assert ok["found"] is True and ok["resolved_via"] == "eor" and ok["verify"] is True
    # inside the table the EOR record is not used (table governs)
    t = W.resolve_cpe_walls(0.3, 2.0, 0.0, eor_cpe={"Cpe": {"A": 9, "B": 9, "C": 9, "D": 9},
                                                    "source": "eor", "cite": "x", "verify": True})
    assert t["resolved_via"] == "fallback" and t["Cpe"]["A"] == 0.7
