"""R01-R04 (+ L-08 part): the standards search tool's ladder, error semantics, evidence files, aliases.

R01  a server / transport error is never "genuinely absent"; not_tabulated and document_not_in_corpus
     pass through.
R02  an exact clause / table / equation hit is final regardless of count; rungs ranked by class;
     rung 5 only when rungs 1-4 are empty, with honest provenance; unit tokens are not clause ids.
R03  rag/ evidence files keyed on collection|clause|type|query + content hash, never overwritten.
R04  alias rewording on word boundaries, no symbol-only aliases.
L-08 INDIA_CORPUS_ROOT decides where the corpus is.
"""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from steltic import config                     # noqa: E402
from steltic.job_tools import JobWorkspace     # noqa: E402

COLL = "engineering_standards_IS1893"


class Wire(JobWorkspace):
    """No server: `reply(query, collection, clause, n)` returns the whole reply dict for each send."""

    def __init__(self, reply, jobs=None):
        if jobs is not None:
            JobWorkspace.__init__(self, jobs)
        else:
            self.building = False
        self.reply = reply
        self.sent = []
        self._aliases_cache = {}

    def log(self, tool, detail="", result=""):
        return {}

    def _corpus_status(self):
        return {}

    def _rag_post(self, query, collection, clause="", chapter=""):
        self.sent.append((query, collection, clause))
        return self.reply(query, collection, clause, len(self.sent)), None


def _hits(n, **kw):
    return [dict({"id": f"h{i}", "source": "IS_1893_Part_1_2016", "text": f"hit {i}"}, **kw) for i in range(n)]


def _run(reply, query, coll=COLL, **kw):
    config.RAG_API_URL = "http://stub"
    ws = Wire(reply)
    return ws, ws.search_engineering_standards(query, coll, **kw)


# ---------------------------------------------------------------- R02: exact hits are final ----
def test_a_single_exact_section_hit_is_the_answer():
    ws, out = _run(lambda q, c, cl, n: {"results": _hits(1, section="7.3.6") if cl else _hits(5)},
                   "7.3.6 weight of partition walls", clause="7.3.6")
    assert len(ws.sent) == 1, ws.sent
    assert "thin" not in out and out.get("exact_match") is True
    assert out["results"][0]["section"] == "7.3.6"


def test_matched_exact_reply_is_final_even_without_ids():
    ws, out = _run(lambda q, c, cl, n: {"results": _hits(1), "matched": "exact_table", "type": "exact_table"},
                   "Table 10", clause="Table 10")
    assert len(ws.sent) == 1 and "thin" not in out


def test_exact_table_recognised_by_table_id_when_section_is_the_citing_clause():
    # the old adapter maps a table hit's `section` to the clause that cites it (Table 10 -> 7.3.5)
    ws, out = _run(lambda q, c, cl, n: {"results": _hits(1, section="7.3.5", table_id="10") if cl else []},
                   "percentage of imposed load", clause="Table 10")
    assert len(ws.sent) == 1 and out.get("exact_match") is True


def test_rung3_exact_hit_beats_a_thin_fts_rung_and_stops_the_ladder():
    # IS 18168 5.6: rung 1 (sentence) finds 1 unrelated chunk, rung 3 exact-id 5.6 finds the clause
    def reply(q, c, cl, n):
        if cl == "5.6":
            return {"results": _hits(1, section="5.6")}
        return {"results": _hits(1, section="10.4.1")}
    ws, out = _run(reply, "maximum load effect analysis 5.6", coll="engineering_standards_IS18168")
    assert out["results"][0]["section"] == "5.6"
    assert "thin" not in out
    assert "rung3 exact-id 5.6" in out["escalated"] and "returned 1 hit" in out["escalated"]


# ---------------------------------------------------------------- R02: rung 5 ----
def test_rung5_does_not_run_when_the_asked_document_had_any_hit():
    ws, out = _run(lambda q, c, cl, n: {"results": _hits(1) if c else _hits(5, source="IS_875_Part_3_2015")},
                   "Delhi zone factor")
    assert all(c == COLL for _, c, _ in ws.sent), ws.sent
    assert "FOUND ONLY" not in str(out.get("note")) and "thin" in out


def test_rung5_hits_from_the_asked_document_lead_and_are_not_labelled_foreign():
    def reply(q, c, cl, n):
        if c:
            return {"results": []}
        return {"results": [{"id": "a", "source": "IS_875_Part_3_2015"}, {"id": "b", "source": "IS_1893_Part_1_2016"}]}
    ws, out = _run(reply, "Delhi")
    assert "FOUND ONLY" not in out["note"]
    assert out["results"][0]["source"] == "IS_1893_Part_1_2016"
    assert out["also_found_in"] == ["IS_875_Part_3_2015"]


def test_rung5_only_other_documents_says_found_only_without_filter():
    ws, out = _run(lambda q, c, cl, n: {"results": [] if c else [{"id": "a", "source": "IS_9595_1996"}]},
                   "Table 10")
    assert out["note"].startswith("FOUND ONLY WITHOUT THE DOCUMENT FILTER")
    assert out["found_in_documents"] == ["IS_9595_1996"]


def test_unit_tokens_and_grades_are_not_clause_ids():
    ws = Wire(lambda *a: {"results": []})
    assert ws._query_ids("Steel 78.5 kN/m3 unit weight") == []
    assert ws._query_ids("basic wind speed 44 m/s N/mm2") == []
    assert "E250" not in ws._query_ids("E250 yield stress 5.2.1")
    assert ws._query_ids("clause 7.3.6 kN/m2") == ["7.3.6"]


# ---------------------------------------------------------------- R01: errors ----
def test_server_error_is_retried_and_never_reported_absent():
    ws, out = _run(lambda q, c, cl, n: {"results": [], "note": "server error: SQLite objects created in a thread"},
                   "snow load", coll="engineering_standards_IS875_P4")
    assert out["not_found_kind"] == "server_error"
    assert out["found"] is None
    assert "RETRIEVAL ERROR" in out["note"] and "not evidence of absence" in out["note"]
    assert "genuinely absent" not in out["note"]
    firsts = [s for s in ws.sent if s == ws.sent[0]]
    assert len(firsts) == 2, "an errored rung is retried exactly once"


def test_server_error_then_success_on_retry_returns_the_hits():
    ws, out = _run(lambda q, c, cl, n: {"results": [], "note": "server error: x"} if n == 1 else {"results": _hits(4)},
                   "Shimla zone")
    assert len(out["results"]) == 4 and len(ws.sent) == 2
    assert "retrieval_errors" not in out


def test_not_tabulated_passes_through_verbatim_and_stops():
    note = ("Town not listed in IS 1893 (Part 1) Annex E or IS 875 (Part 3) Annex A: use the zone map "
            "(IS 1893 Fig. 1)")
    ws, out = _run(lambda q, c, cl, n: {"results": [], "found": False, "not_tabulated": True, "note": note}, "Noida")
    assert out["not_found_kind"] == "not_tabulated" and out["not_tabulated"] is True
    assert out["note"] == note
    assert len(ws.sent) == 1


def test_document_not_in_corpus_passes_through():
    ws, out = _run(lambda q, c, cl, n: {"results": [], "note": "IS_456_2000 is not in the corpus"},
                   "development length", coll="engineering_standards_IS456")
    assert out["not_found_kind"] == "document_not_in_corpus" and out["document"] == "IS_456_2000"
    assert len(ws.sent) == 1, "no further rungs once the corpus says the document is absent"


# ---------------------------------------------------------------- R03: evidence files ----
def test_same_query_on_two_collections_writes_two_files(tmp_path):
    config.RAG_API_URL = "http://stub"
    ws = Wire(lambda q, c, cl, n: {"results": [{"id": c, "source": c, "text": "Chennai " + c}] * 3}, jobs=tmp_path)
    ws.new_activity_log("b1")
    a = ws.search_engineering_standards("Chennai", "engineering_standards_IS1893")
    first = (tmp_path / "b1" / a["saved"]).read_text()
    b = ws.search_engineering_standards("Chennai", "engineering_standards_IS875_P3")
    assert a["saved"] != b["saved"]
    assert (tmp_path / "b1" / a["saved"]).read_text() == first
    assert (tmp_path / "b1" / b["saved"]).is_file()


def test_rerun_with_different_hits_keeps_both_files(tmp_path):
    config.RAG_API_URL = "http://stub"
    txt = {"v": "one"}
    ws = Wire(lambda q, c, cl, n: {"results": [{"id": "x", "text": txt["v"]}] * 3}, jobs=tmp_path)
    ws.new_activity_log("b2")
    a = ws.search_engineering_standards("Delhi", COLL)
    txt["v"] = "two"
    b = ws.search_engineering_standards("Delhi", COLL)
    assert a["saved"] != b["saved"]
    assert "one" in (tmp_path / "b2" / a["saved"]).read_text()
    assert "two" in (tmp_path / "b2" / b["saved"]).read_text()
    c = ws.search_engineering_standards("Delhi", COLL)      # identical evidence -> same file, no new copy
    assert c["saved"] == b["saved"]


# ---------------------------------------------------------------- R04: aliases ----
GROUPS = {"synonym_groups": [
    ["load combination", "combination of loads", "load combinations"],
    ["partial safety factor", "gamma_m0", "gamma_m1"],
    ["basic wind speed", "V b", "V_b", "Vb"],
    ["lateral torsional buckling", "LTB", "lateral-torsional buckling"],
]}


def test_reworded_uses_word_boundaries_and_skips_symbol_aliases():
    ws = Wire(lambda *a: {"results": []})
    ws._aliases_cache = GROUPS
    r = ws._reworded("load combinations IS 875 Part 5")
    assert not any("combinationss" in x for x in r), r
    assert ws._reworded("Table 4 partial safety factors for loads") == []
    r = ws._reworded("Indore basic wind speed Annex A")
    assert not any("V b" in x or "V_b" in x for x in r), r
    r = ws._reworded("design for lateral torsional buckling of beams")
    assert "design for lateral-torsional buckling of beams" in r and not any("LTB" in x for x in r)


# ---------------------------------------------------------------- L-08 ----
def test_india_corpus_root_env(monkeypatch, tmp_path):
    from steltic import india_collections as ic
    monkeypatch.setenv("INDIA_CORPUS_ROOT", str(tmp_path))
    assert ic.india_corpus_root() == str(tmp_path)
    assert ic.india_corpus_path("indexes", "aliases.json") == tmp_path / "indexes" / "aliases.json"
    monkeypatch.delenv("INDIA_CORPUS_ROOT")
    assert ic.india_corpus_root()                      # sibling checkout or /workspace fallback
