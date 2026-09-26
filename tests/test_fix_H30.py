"""H30: one completion authority (L-04, HR-E-04).  design_status also fails on consistency's retrieval-evidence
rule, the (fixed) literal-D/C rule, and on a found:false retrieval row without an EOR assumption record."""
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "steel_engine"))
sys.path.insert(0, str(ROOT / "tests"))

import india_seismic_gates as G
import consistency as C
from test_india_gates_wp0 import CFG_OK, _pkg


def _cfg(rows, **kw):
    c = dict(CFG_OK, load_plan={"retrieval": rows})
    c.update(kw)
    return c


def _reasons(cfg, pkg=None, job_dir=None):
    return " ".join(G.design_status(cfg, pkg or _pkg(), job_dir=job_dir)["reasons"])


SNOW = {"stem": "IS_875_Part_4_1987", "query": "snow Shimla", "found": False, "cite": None}


def test_found_false_without_eor_assumption_blocks():
    r = _reasons(_cfg([dict(SNOW)]))
    assert "found:false without EOR assumption" in r


def test_found_false_with_row_assumption_clears():
    row = dict(SNOW, value=1.5, source="EOR map reading (VERIFY)", cite="IS 875 (Part 4):1987 Fig. 1 (EOR reading)",
               verify=True)
    assert "found:false without EOR assumption" not in _reasons(_cfg([row]))


def test_found_false_with_cfg_eor_assumptions_clears():
    eor = [{"query": "snow shimla", "value": 1.5, "source": "EOR", "cite": "IS 875-4 Fig. 1 (EOR reading)",
            "verify": True}]
    assert "found:false without EOR assumption" not in _reasons(_cfg([dict(SNOW)], eor_assumptions=eor))
    # incomplete record (no verify flag) does not pair
    eor[0].pop("verify")
    assert "found:false without EOR assumption" in _reasons(_cfg([dict(SNOW)], eor_assumptions=eor))


def test_rag_evidence_rule_reaches_design_status(tmp_path):
    row = {"stem": "IS_1893_Part_1_2016", "query": "Delhi zone", "found": True, "cite": "Annex E Delhi IV 0.24",
           "hit_file": "rag/z.json", "quote": "Delhi IV 0.24"}
    (tmp_path / "rag").mkdir()
    (tmp_path / "rag" / "z.json").write_text(json.dumps({"query": "Delhi zone", "hits": [{"text": "Bareilly III 0.16"}]}))
    assert "no stored rag/ hit contains the cited" in _reasons(_cfg([row]), job_dir=str(tmp_path))
    (tmp_path / "rag" / "z.json").write_text(json.dumps({"query": "Delhi zone", "hits": [{"text": "x Delhi IV 0.24 y"}]}))
    assert "no stored rag/ hit contains the cited" not in _reasons(_cfg([row]), job_dir=str(tmp_path))


def test_literal_dc_reaches_design_status():
    pkg = _pkg(connections=[{"id": "conn-x", "DC": 0.9, "checks": [{"name": "c", "dc": 0.9, "ok": True}]}])
    assert "literal D/C 0.900" in _reasons(CFG_OK, pkg)


def test_script_grep_still_reported(tmp_path):
    (tmp_path / "x.py").write_text("DC = 0.8\n")
    assert "literal D/C constant 0.8" in _reasons(CFG_OK, job_dir=str(tmp_path))


def test_consistency_check_carries_the_same_found_false_rule():
    plan = {"retrieval": [dict(SNOW)]}
    assert C.retrieval_assumption_issues(plan, {})
    assert C.retrieval_assumption_issues(plan, {"eor_assumptions": {"retrieval_index": 0, "value": 0.0,
                                                                     "source": "EOR", "cite": "x", "verify": True}}) == []
