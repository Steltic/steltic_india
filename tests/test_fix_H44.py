"""H44 hygiene (E9, E10, L-06, HR-B-14, HR-E-19, L-07)."""
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "steel_engine"))


def test_contract_residue_word_boundaries():
    from india_contract_residue import contract_hits
    assert contract_hits("the preflight skipped the check; kipper; psfx") == []
    assert contract_hits("load 2 kips") and contract_hits("50 psf live") and contract_hits("1 kip")


def _grounding(monkeypatch, pkg, R=4.5, braced=True):
    import report as RPT
    monkeypatch.setattr(RPT, "_load_activity", lambda name: ([], None))
    monkeypatch.setattr(RPT.E, "is_braced", lambda cfg: braced)
    return RPT._grounding_check({"seis": {"R": R}}, "x", pkg)


def test_grounding_does_not_credit_span_360(monkeypatch):
    html = _grounding(monkeypatch, {"members": [{"cite": "deflection span/360"}], "connections": [{"cite": "A341 358"}]})
    assert "MISSING" in html
    assert "Ch. J" not in html and "seismic-22" not in html and "prequalified" not in html
    assert "Section 10" in html and "Section 12" in html


def test_grounding_credits_is800_cites(monkeypatch):
    pkg = {"members": [{"cited": "IS 800:2007 7-9 (member_check_is800)"}],
           "connections": [{"checks": [{"clause": "IS 800:2007 10.3.3"}]}],
           "capacity_design": {"checks": {"a": {"clause": "IS 800:2007 12.8.3"}}}}
    assert "MISSING" not in _grounding(monkeypatch, pkg)
    # moment frame: the 12.10.2 / 12.11.2 row needs an IS 800 moment-connection cite (or IS 800 queries)
    assert "MISSING" in _grounding(monkeypatch, pkg, braced=False)
    pkg["connections"][0]["checks"].append({"clause": "IS 800:2007 12.10.2.1"})
    assert "MISSING" not in _grounding(monkeypatch, pkg, braced=False)


def test_omf_connection_rows_cite_12_10_2():
    import design_pipeline as DP
    import india_is800_s12 as S12
    assert DP._mf_conn_clause({"system": "OMF"}) == "12.10.2"
    assert DP._mf_conn_clause({"system": "SMF"}) == "12.11.2"
    lab = DP._mf_conn_label({"system": "OMF"}, "connection_moment", {"clause": "IS 800:2007 12.10.2.1", "member": "e1"})
    assert "12.10.2" in lab and "12.11.2" not in lab
    assert "12.10.2" in DP._mf_conn_label({"system": "OMF"}, "x", {"member": "e1"})
    src = open(ROOT / "steel_engine" / "design_pipeline.py").read()
    assert '"IS 800 12.11.2 %s (joint %s)"' not in src


def test_pipeline_docstring_matches_agent_start():
    import pipeline as P
    d = P.__doc__
    assert "computes NO IS 800" not in d and "It computes NO" not in d
    assert "member_check_is800" in d and "section12_checks" in d and "jobs root" in d
    assert "steel_builder/<name>" not in d


def test_status_md_left_alone_when_not_engine_owned(tmp_path):
    import pipeline as P
    p = tmp_path / "STATUS.md"
    assert P._status_md_engine_owned(str(p))                      # absent -> engine may write
    p.write_text("# Package status (agent)\n\nCOMPLETE per the checker\n")
    assert not P._status_md_engine_owned(str(p))
    p.write_text(P.ENGINE_STATUS_MARK + "\n# x -- design status: PARTIAL\n")
    assert P._status_md_engine_owned(str(p))
    p.write_text("# IN_Ex1 -- design status: PARTIAL\n\nAuthority: x\n")  # pre-H44 engine file
    assert P._status_md_engine_owned(str(p))


def test_pipeline_writes_status_engine_md(tmp_path, monkeypatch):
    import pipeline as P
    import preflight as PF
    import engine3d as E
    import design_pipeline as DP
    import plot_model as PM
    import report as RPT
    import india_seismic_gates as G
    monkeypatch.setenv("STEEL_BUILDER_JOBS", str(tmp_path))
    monkeypatch.setattr(PF, "check", lambda cfg: [])
    monkeypatch.setattr(E, "report", lambda name: {"allp": True})
    monkeypatch.setattr(E, "export_model", lambda *a, **k: None)
    monkeypatch.setattr(PM, "figures", lambda *a, **k: [])
    monkeypatch.setattr(RPT, "build_report", lambda name, root=None: os.path.join(root, "report.html"))
    monkeypatch.setattr(G, "design_status", lambda cfg, pkg, job_dir=None: {"status": "partial", "reasons": ["r1"],
                                                                            "authority": "a"})

    def _design(name, outdir=None):
        os.makedirs(outdir, exist_ok=True)
        json.dump({"members": []}, open(os.path.join(outdir, "calc_package.json"), "w"))
        return True
    monkeypatch.setattr(DP, "design", _design)
    root = tmp_path / "H44"
    root.mkdir()
    (root / "STATUS.md").write_text("# agent package status\nCOMPLETE\n")
    P.design_and_report("H44", {"jurisdiction": "india", "heights": [3000.0], "load_plan": {}}, do_report=True)
    assert (root / "STATUS.md").read_text() == "# agent package status\nCOMPLETE\n"
    assert "design status: PARTIAL" in (root / "STATUS.engine.md").read_text()
