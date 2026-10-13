"""Loop guard: IS-corpus searches pause at REPEAT_LIMIT_SEARCH (50), every other tool at REPEAT_LIMIT (10).

An India design looks up many related IS clauses, and the loop guard's coarse search signature groups reworded
lookups together, so 10 grouped searches paused runs that were working normally (2026-10). The model, the tools
and the workspace are stubs: no LLM, no RAG server, no sandbox.
"""
import json
import os
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from steltic import agent, config     # noqa: E402


class _WS:
    def __init__(self, root):
        self.jobs = root
        self.building = None

    def log(self, *a, **k):
        return {}


def _run(monkeypatch, tmp_path, tool, args, result):
    """Drive run_design with a model that makes the same tool call every turn; return (calls made, paused event)."""
    calls = {"n": 0}

    def fake_chat(*a, **k):
        calls["n"] += 1
        tc = {"id": "c%d" % calls["n"], "type": "function",
              "function": {"name": tool, "arguments": json.dumps(args)}}
        return {"content": "", "tool_calls": [tc], "finish_reason": "tool_calls", "usage": {}}
        yield  # noqa: unreachable -- makes this a generator, as _chat_with_retry is

    monkeypatch.setattr(agent, "_chat_with_retry", fake_chat)
    monkeypatch.setattr(agent, "dispatch", lambda nm, a, ws, ex: dict(result))
    (tmp_path / "B").mkdir()
    ws = _WS(tmp_path)
    paused = None
    for ev in agent.run_design(ws, type("Ex", (), {"name": "stub"})(), "http://x", "k", "stub-model", "B",
                               "brief"):
        if ev.get("type") in ("paused", "error", "done"):
            paused = ev
            break
    return calls["n"], paused


def test_default_limits():
    assert config.REPEAT_LIMIT == 10
    assert config.REPEAT_LIMIT_SEARCH == 50


def test_repeated_search_pauses_at_50(monkeypatch, tmp_path):
    n, ev = _run(monkeypatch, tmp_path, "search_engineering_standards",
                 {"query": "IS 800 lateral torsional buckling of laterally unsupported beams", "collection": "IS800"},
                 {"results": [{"id": "hit0", "text": "8.2.2"}]})
    assert ev["type"] == "paused"
    assert "search_engineering_standards" in ev["reason"] and "50x" in ev["reason"]
    assert n == 50


def test_repeated_run_python_still_pauses_at_10(monkeypatch, tmp_path):
    n, ev = _run(monkeypatch, tmp_path, "run_python", {"code": "print(1/0)"},
                 {"returncode": 1, "stderr": "ZeroDivisionError"})
    assert ev["type"] == "paused"
    assert "run_python" in ev["reason"] and "10x" in ev["reason"]
    assert n == 10
