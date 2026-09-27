"""AUD-1 evidence check must match hit_file on Windows, where os.path.relpath yields 'rag\\z.json'."""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "steel_engine"))
import consistency as C  # noqa: E402


def _job(tmp_path):
    rag = tmp_path / "rag"
    rag.mkdir()
    (rag / "z.json").write_text('{"query": "zone Delhi", "text": "Delhi IV 0.24"}', encoding="utf-8")
    return {"retrieval": [{"query": "zone Delhi", "found": True, "cite": "IS 1893 Annex E: Delhi IV 0.24",
                           "hit_file": "rag/z.json", "quote": "Delhi IV 0.24"}]}


def test_windows_relpath_separator(tmp_path, monkeypatch):
    plan = _job(tmp_path)
    real = os.path.relpath
    monkeypatch.setattr(C.os.path, "relpath", lambda p, start=None: real(p, start).replace("/", "\\"))
    monkeypatch.setattr(C.os, "sep", "\\")
    assert C.rag_evidence_issues(plan, str(tmp_path)) == []


def test_backslash_hit_file(tmp_path):
    plan = _job(tmp_path)
    plan["retrieval"][0]["hit_file"] = "rag\\z.json"
    assert C.rag_evidence_issues(plan, str(tmp_path)) == []


def test_wrong_quote_still_fails(tmp_path):
    plan = _job(tmp_path)
    plan["retrieval"][0]["quote"] = "Delhi V 0.36"
    assert C.rag_evidence_issues(plan, str(tmp_path))
