"""IN-CJP-GATE (gold issue HR_consistency_cjp_splice_no_dc): a connection record whose only checks are passing
deemed-to-comply gates (CJP column splice with matching electrode, IS 800:2007 10.5.7.1.2 -- ruling R4) is not
flagged "no D/C reported"; a failing / unevaluated gate or a non-gate row without a D/C still is."""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "steel_engine"))

import consistency as HC  # noqa: E402

GATE = {"name": "splice: cjp_parent_metal", "value": None, "limit": None, "dc": None, "ok": True, "gate": True,
        "limit_state": "column splice", "clause": "IS 800:2007 10.5.7.1.2 / 12.5.2.2",
        "cite": "CJP butt weld with matching electrode develops the parent metal (ruling R4)"}


def _entry(*checks):
    return {"id": "conn-lateral_col-BOX550X550X28", "DC": None, "limit_state": "column splice",
            "checks": list(checks)}


def _nodc(iss):
    return [x for x in iss if "no D/C reported" in x]


def test_cjp_gate_only_splice_is_accepted():
    assert not _nodc(HC._entry_issues("connection", _entry(GATE)))


def test_failing_or_unevaluated_gate_or_plain_row_still_flagged():
    assert _nodc(HC._entry_issues("connection", _entry(dict(GATE, ok=None))))
    assert _nodc(HC._entry_issues("connection", _entry(dict(GATE, ok=False))))
    assert _nodc(HC._entry_issues("connection", _entry(GATE, {"name": "x", "ok": True, "clause": "c"})))
    assert _nodc(HC._entry_issues("connection", _entry()))
