"""AUD-1 (independent gold audit, M5 / engine observation 1): a found:true retrieval row is backed only by ITS OWN
stored evidence -- (a) hit_file + quote verbatim (whitespace-normalised) in that file, or (b) a stored rag/ file whose
own query header ('# RAG query:' line / JSON 'query') equals the row's query and which contains the cited value.
An unrelated hit that happens to contain the digits (HR Ex1: roof LL '0.75' found in 'Ta = 0.075 h^0.75') no longer
passes, and the reason blocks COMPLETE."""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "steel_engine"))
sys.path.insert(0, str(ROOT / "tests"))

import consistency as C
import india_seismic_gates as G
from test_india_gates_wp0 import CFG_OK, _pkg

ROOF = {"query": "Table 2 roof imposed load", "found": True,
        "cite": "IS 875 (Part 2) Table 2 flat roof, access not provided except maintenance 0.75 kN/m2"}


def _hit(path, query, body):
    path.write_text("# RAG query: %s\n# collection: x  |  hits: 1\n\n## Hit 1\n%s\n" % (query, body)
                    if query is not None else "## Hit 1\n%s\n" % body)


def _job(tmp_path):
    (tmp_path / "rag").mkdir()
    return tmp_path


def test_unrelated_hit_with_same_digits_no_longer_backs_a_quote_less_row(tmp_path):
    j = _job(tmp_path)
    _hit(j / "rag" / "7-3-6.txt", "7.3.6 partition walls seismic weight", "Ta = 0.075 h^0.75 for RC frames")
    iss = C.rag_evidence_issues({"retrieval": [dict(ROOF)]}, str(j))
    assert len(iss) == 1 and "no stored rag/ file records this query" in iss[0] and "attach hit_file + quote" in iss[0]


def test_headerless_text_hit_is_not_evidence(tmp_path):
    j = _job(tmp_path)
    _hit(j / "rag" / "roof.txt", None, "Flat roof, access not provided except for maintenance: 0.75 kN/m2")
    assert len(C.rag_evidence_issues({"retrieval": [dict(ROOF)]}, str(j))) == 1


def test_own_query_header_with_the_value_passes(tmp_path):
    j = _job(tmp_path)
    _hit(j / "rag" / "roof.txt", "table 2  ROOF imposed load",
         "Flat roof, access not provided except for maintenance: 0.75 kN/m2")
    assert C.rag_evidence_issues({"retrieval": [dict(ROOF)]}, str(j)) == []


def test_own_query_header_without_the_value_blocks(tmp_path):
    j = _job(tmp_path)
    _hit(j / "rag" / "roof.txt", "Table 2 roof imposed load", "Access provided: 1.5 kN/m2")
    iss = C.rag_evidence_issues({"retrieval": [dict(ROOF)]}, str(j))
    assert len(iss) == 1 and "does not contain the cited value" in iss[0]


def test_own_json_query_field_passes(tmp_path):
    j = _job(tmp_path)
    (j / "rag" / "r.json").write_text(json.dumps({"query": "Table 2 roof imposed load",
                                                  "hits": [{"text": "maintenance 0.75 kN/m2"}]}))
    assert C.rag_evidence_issues({"retrieval": [dict(ROOF)]}, str(j)) == []


def test_hit_file_and_quote_whitespace_normalised(tmp_path):
    j = _job(tmp_path)
    _hit(j / "rag" / "any.txt", "something else", "access not provided\n   except for   maintenance 0.75")
    row = dict(ROOF, hit_file="rag/any.txt", quote="access not provided except for maintenance 0.75")
    assert C.rag_evidence_issues({"retrieval": [row]}, str(j)) == []
    row["quote"] = "access provided 1.5"
    iss = C.rag_evidence_issues({"retrieval": [row]}, str(j))
    assert len(iss) == 1 and "not verbatim" in iss[0]


def test_reason_blocks_complete(tmp_path):
    j = _job(tmp_path)
    _hit(j / "rag" / "7-3-6.txt", "7.3.6 partition walls seismic weight", "Ta = 0.075 h^0.75")
    cfg = dict(CFG_OK, load_plan={"retrieval": [dict(ROOF)]})
    st = G.design_status(cfg, _pkg(), job_dir=str(j))
    assert st["status"] != "complete" and st["complete_allowed"] is False
    assert any("evidence: load_plan.retrieval[0]" in r for r in st["reasons"])
