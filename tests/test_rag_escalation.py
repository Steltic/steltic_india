"""The escalation ladder in `search_engineering_standards`: when it climbs, and when it stops.

The ladder was written to fire on a zero-hit answer. On 2026-09-18 a design run showed the gap that
leaves: a nine-term query matched exactly ONE chunk -- a fragment straddling the
E7/F2 boundary -- and one hit is not zero, so the ladder never ran and the agent was handed a
fragment as though it were Chapter F. A thin rung now keeps the ladder climbing, and the best rung
seen is what comes back, labelled thin, rather than a claim that the provision is absent.

Engine-free and server-free: the RAG is a stub. Run with `python -m pytest tests -q` from the root.
"""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from steltic import config                     # noqa: E402
from steltic.job_tools import JobWorkspace     # noqa: E402

IS800 = "flexural strength compact I-shape lateral-torsional buckling F2"
NAV = "laterally unsupported beams elastic lateral torsional buckling moment"   # full text, no id


class Stub(JobWorkspace):
    """A workspace with no disk and no server: every rung's answer comes from `answers`."""

    def __init__(self, answers):
        self.answers = answers          # how -> number of hits it returns
        self.sent = []                  # every (query, collection, clause) that went out
        self.building = False
        self._aliases_cache = {}        # no alias rung: the stub must not depend on a corpus on disk

    def log(self, tool, detail="", result=""):
        return {}

    def _rag_post(self, query, collection, clause="", chapter="", type_="", want_commentary=False, neighbors=None):
        self.sent.append((query, collection, clause))
        n = self.answers(query, collection, clause, len(self.sent))
        return {"results": [{"id": f"hit{i}", "source": collection or "IS_360_22"} for i in range(n)]}, None


def _ws(answers):
    config.RAG_API_URL = "http://stub"
    return Stub(answers)


def test_one_fts_hit_is_not_an_answer_and_the_ladder_keeps_climbing():
    # R02: the ENOUGH rule still holds for FULL-TEXT rungs (the stub's hits carry no id and no
    # `matched`, so they are navigation-grade); an exact hit is exempt -- see test_fix_R01_R04_rag.py
    # (a navigation query narrowed to section 8: the thin answer sends the ladder on to drop the filter)
    ws = _ws(lambda q, c, cl, n: 1 if n == 1 else 5)
    out = ws.search_engineering_standards(NAV, "engineering_standards_IS800", type="fts", chapter="8")
    assert len(ws.sent) > 1, "a single thin full-text hit must not stop the ladder"
    assert len(out["results"]) == 5
    assert out.get("escalation") and len(out["escalation"]) > 1
    # the escalation note names the answering rung and what attempt 1 really returned (1 hit)
    assert "found nothing" not in out["escalated"] and "returned 1 hit" in out["escalated"]


def test_a_full_first_rung_still_stops_immediately():
    ws = _ws(lambda q, c, cl, n: 5)
    out = ws.search_engineering_standards(NAV, "engineering_standards_IS800", type="fts")
    assert len(ws.sent) == 1, "a good first answer must not cost four more queries"
    assert "escalation" not in out


def test_an_id_bearing_sentence_costs_the_exact_id_and_one_navigation_query():
    # under the retrieval policy: the exact id, then one navigation query in spec words -- and a good
    # navigation answer must not cost four more, nor be reported as an escalation
    ws = _ws(lambda q, c, cl, n: 5)
    out = ws.search_engineering_standards(IS800, "engineering_standards_IS800")
    assert len(ws.sent) == 2 and ws.sent[0] == ("", "engineering_standards_IS800", "F2"), ws.sent
    assert "escalation" not in out and "exact-id F2" in out["policy"]


def test_the_best_thin_rung_is_returned_rather_than_a_false_absence():
    # every rung thin: two hits on the second attempt (rung 2, filter dropped), one everywhere else.
    # (Before R02 this test let rung 5 -- another document -- win on count; rung 5 now runs only when
    # rungs 1-4 found nothing, so the thin rungs are all from the asked document.)
    ws = _ws(lambda q, c, cl, n: 2 if n == 2 else 1)
    out = ws.search_engineering_standards(IS800, "engineering_standards_IS800", clause="F2.2")
    assert out.get("results"), "a thin hit still beats reporting the provision absent"
    assert len(out["results"]) == 2
    assert "thin" in out
    assert out.get("not_found_kind") is None
    assert all(c == "engineering_standards_IS800" for _, c, _ in ws.sent), "rung 5 must not run"


def test_genuinely_nothing_still_reports_which_kind_of_nothing():
    ws = _ws(lambda q, c, cl, n: 0)
    out = ws.search_engineering_standards(IS800, "engineering_standards_IS800")
    assert out.get("found") is False
    assert out.get("not_found_kind") in (
        "no_specification_index", "document_not_in_corpus", "term_absent_from_document")


def test_an_unreachable_server_still_halts_the_run():
    ws = _ws(lambda q, c, cl, n: 0)
    ws._rag_post = lambda *a, **k: (None, "connection refused")
    out = ws.search_engineering_standards(IS800, "engineering_standards_IS800")
    assert out.get("rag_unavailable") is True


# --- the retrieval policy (contract/QUERYING_IS_CORPUS.md) -------------------------------------------
#
# The India design agent sent sentences ("laterally unsupported beams elastic lateral torsional buckling
# 8.2.2") because nothing between the instructions and the wire carried the policy: the tool had no
# `type`/`doc`, and the ladder tried the sentence first and an exact id only if the sentence failed. The
# policy now shapes every call: exact ids first, one navigation query in the standard's words.

class Exact(Stub):
    """A server that, like the real one, answers an exact id with that record and says so."""

    def _rag_post(self, query, collection, clause="", chapter="", type_="", want_commentary=False, neighbors=None):
        self.sent.append((query, collection, clause))
        self.wire = getattr(self, "wire", []) + [{"query": query, "collection": collection, "clause": clause,
                                                  "chapter": chapter, "type": type_, "neighbors": neighbors}]
        if clause:
            return {"results": [{"id": f"spec:{clause}", "section": clause, "source": "IS_800_2007"}],
                    "matched": "exact_section"}, None
        n = self.answers(query, collection, clause, len(self.sent))
        return {"results": [{"id": f"hit{i}", "source": collection or "IS_800_2007"} for i in range(n)],
                "matched": "fts" if n else ""}, None


SENTENCE = "laterally unsupported beams elastic lateral torsional buckling 8.2.2"
C800 = "engineering_standards_IS800"


def test_a_sentence_naming_an_id_goes_out_as_the_exact_id_first():
    config.RAG_API_URL = "http://stub"
    ws = Exact(lambda q, c, cl, n: 5)
    out = ws.search_engineering_standards(SENTENCE, C800)
    assert ws.wire[0]["clause"] == "8.2.2" and ws.wire[0]["query"] == "", ws.wire
    assert "exact-id 8.2.2" in out["policy"] and "fts «" in out["policy"]
    assert out["results"][0]["section"] == "8.2.2", "the exact record leads the answer"
    assert "8.2.2" not in ws.wire[1]["query"], "navigation is spec words without the id"
    assert out.get("exact_match") is True and out["exact_ids"] == ["8.2.2"]


def test_an_explicit_exact_type_sends_the_id_alone_with_its_kind():
    config.RAG_API_URL = "http://stub"
    ws = Exact(lambda q, c, cl, n: 0)
    out = ws.search_engineering_standards("8.2.2.1", C800, type="exact_section", doc="IS_800_2007",
                                          context_neighbors=1, purpose="Mcr")
    assert ws.wire == [{"query": "", "collection": C800, "clause": "8.2.2.1", "chapter": "", "type": "exact_section",
                        "neighbors": 1}]
    assert out["policy"] == "exact_section 8.2.2.1" and len(out["results"]) == 1


def test_an_exact_table_keeps_its_printed_sub_letter():
    config.RAG_API_URL = "http://stub"
    ws = Exact(lambda q, c, cl, n: 0)
    ws.search_engineering_standards("Table 9(c) design compressive stress buckling class c", C800, type="exact_table")
    assert ws.wire[0]["clause"] == "Table 9(c)", ws.wire


def test_a_bare_id_typed_into_query_is_an_exact_lookup():
    config.RAG_API_URL = "http://stub"
    ws = Exact(lambda q, c, cl, n: 0)
    out = ws.search_engineering_standards("7.1.2.1", C800)
    assert ws.wire[0]["clause"] == "7.1.2.1" and out["policy"] == "exact-id 7.1.2.1"
    ws = Exact(lambda q, c, cl, n: 0)
    out = ws.search_engineering_standards("Table 4", C800)
    assert ws.wire[0]["clause"] == "Table 4" and len(ws.wire) == 1


def test_doc_selects_the_collection_the_report_counts_by():
    config.RAG_API_URL = "http://stub"
    ws = Exact(lambda q, c, cl, n: 0)
    ws.search_engineering_standards("Table 9", "", type="exact_table", doc="IS_1893_Part_1_2016")
    assert ws.wire[0]["collection"] == "engineering_standards_IS1893"
    ws = Exact(lambda q, c, cl, n: 0)
    ws.search_engineering_standards("6.3.3", "", type="exact_section", doc="IS_875_Part_3_2015")
    assert ws.wire[0]["collection"] == "engineering_standards_IS875_P3"


def test_an_is_section_number_narrows_navigation_whole():
    """IS sections are numbers: chapter "12" is section 12, not "1"."""
    config.RAG_API_URL = "http://stub"
    ws = Exact(lambda q, c, cl, n: 5)
    ws.search_engineering_standards("special concentrically braced frames bracing members", C800, type="fts",
                                    chapter="12")
    assert ws.wire[0]["chapter"] == "12", ws.wire


def test_a_keyword_fallback_on_a_bogus_id_is_not_an_exact_answer():
    """HB 300 is a section designation, not a clause: the server's keyword fallback must not be returned as
    if an exact id had been found."""
    config.RAG_API_URL = "http://stub"
    ws = _ws(lambda q, c, cl, n: 1 if cl else 5)          # the Stub never claims a match
    out = ws.search_engineering_standards("HB 300 column buckling class 7.1.2.1", C800)
    assert not out.get("exact_ids") or "HB" not in " ".join(out["exact_ids"])
    assert len(out["results"]) >= 3
