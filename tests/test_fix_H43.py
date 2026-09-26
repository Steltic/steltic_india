"""H43 package / provenance (L-03, HR-A-08, HR-C-08, HR-E-18): load_plan.json rewritten every run; calc_package
carries the whole load_plan (minus story-force arrays); the governing element result keeps the governing
combination's check record incl. LTB Md / chi_LT / lambda_LT; wind_serviceability for every job."""
import json
import os
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "steel_engine"))
sys.path.insert(0, str(ROOT / "tests"))

from _ex1_fixture import ex1_cfg_is, stage_ex1_rag


def test_load_plan_json_rewritten_every_run(tmp_path, monkeypatch):
    import pipeline as P
    import preflight as PF
    import engine3d as E
    import design_pipeline as DP
    monkeypatch.setenv("STEEL_BUILDER_JOBS", str(tmp_path))
    monkeypatch.setattr(PF, "check", lambda cfg: [])
    monkeypatch.setattr(E, "report", lambda name: {"allp": True})
    monkeypatch.setattr(E, "export_model", lambda *a, **k: None)
    monkeypatch.setattr(DP, "design", lambda name, outdir=None: True)
    import plot_model as PM
    monkeypatch.setattr(PM, "figures", lambda *a, **k: [])
    cfg = {"jurisdiction": "india", "heights": [3000.0], "load_plan": {"retrieval": [{"query": "a", "found": False}]}}
    P.design_and_report("H43_lp", cfg, do_report=False)
    p = tmp_path / "H43_lp" / "load_plan.json"
    assert json.load(open(p))["retrieval"][0]["query"] == "a"
    cfg["load_plan"]["retrieval"][0]["query"] = "b"
    P.design_and_report("H43_lp", cfg, do_report=False)
    assert json.load(open(p))["retrieval"][0]["query"] == "b"


def test_governing_result_keeps_ltb_record():
    import design_pipeline as DP
    res = {"dc": 0.8, "governing_combo": "C2", "capacities": {"Mdz_section": {"Md_Nmm": 1e8}},
           "per_combo": [{"combo": "C1", "dc": 0.5, "checks": []},
                         {"combo": "C2", "dc": 0.8, "checks": [
                             {"moment_sign": "sagging", "LLT_mm": 6000.0, "Mdz_LTB_Nmm": 7.5e7, "chi_LT": 0.61,
                              "lambda_LT": 1.1, "dc": 0.8}]}]}
    g = DP._governing_result(res)
    assert "per_combo" not in g
    assert g["governing_combo_record"]["combo"] == "C2"
    assert g["governing_ltb"]["Mdz_LTB_Nmm"] == 7.5e7 and g["governing_ltb"]["chi_LT"] == 0.61
    assert g["governing_ltb"]["lambda_LT"] == 1.1 and g["governing_ltb"]["combo"] == "C2"


@pytest.fixture(scope="module")
def ex1_pkg(tmp_path_factory):
    import pipeline as P
    jobs = tmp_path_factory.mktemp("jobsH43")
    os.environ["STELTIC_TEST_JOBS"] = str(jobs)
    os.environ["STEEL_BUILDER_JOBS"] = str(jobs)
    cfg, _ = ex1_cfg_is()
    stage_ex1_rag(os.path.join(str(jobs), "IN_Ex1_H43"))
    out = P.design_and_report("IN_Ex1_H43", cfg, do_report=False)
    return cfg, json.load(open(os.path.join(out["root"], "design", "calc_package.json")))


def test_package_carries_whole_load_plan(ex1_pkg):
    cfg, pkg = ex1_pkg
    lp = pkg["load_plan"]
    assert "story_forces" not in lp and sorted(lp["story_forces_keys"]) == sorted(cfg["load_plan"]["story_forces"])
    for k in ("wind_summary", "gravity_summary", "retrieval", "seismic_summary", "story_forces_units"):
        assert k in lp, k
    assert lp["wind_summary"].get("cyclone_belt") is False


def test_wind_serviceability_for_non_crane_job(ex1_pkg):
    cfg, pkg = ex1_pkg
    assert not (cfg.get("crane") or cfg.get("cranes"))
    assert "wind_serviceability" in pkg


def test_beam_package_shows_governing_ltb(ex1_pkg):
    _, pkg = ex1_pkg
    beams = [m for m in pkg["members"] if m["inputs"]["role"] in ("floor", "roof")]
    assert beams
    g = beams[0]["governing_element_result"]
    assert "per_combo" not in g and "governing_combo_record" in g
    assert g["governing_ltb"]["Mdz_LTB_Nmm"] > 0 and g["governing_ltb"]["lambda_LT"] is not None
