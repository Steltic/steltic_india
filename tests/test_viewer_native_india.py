"""Regress the India native schedule, grouped strength, supports and immutable publication path."""
import copy
import csv
import hashlib
import json
from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "steel_engine"))
import viewer3d as viewer
import viewer_native as native


@pytest.fixture
def sample(tmp_path):
    job = tmp_path / "frozen job"
    design = job / "design"
    design.mkdir(parents=True)
    fields = ("ele_tag", "section", "role", "length_mm", "P_comp_kN", "P_tens_kN",
              "M_major_kNm", "M_minor_kNm", "V_kN", "governing_combo")
    with (design / "member_schedule.csv").open("w", encoding="utf-8", newline="") as f:
        out = csv.writer(f)
        out.writerow(fields)
        out.writerow((1, "MB450", "floor", 3600, 1849.69, 1059.85, 8.379, 2.965, 2.33, "force 1"))
        out.writerow((2, "MB450", "floor", 3600, 0, 0, 0, "", 0, "force 2"))
    group = {"id": "floor-MB450", "inputs": {"role": "floor", "section": "MB450"},
             "strength_worst": {"dc": .72, "element": "e2", "combination": "strength combo", "clause": "9.3"},
             "table3_worst": {"dc": .91, "element": "e1"}, "DC": .91,
             "governing_element_result": {"id": "e1", "found": True, "dc": .91,
                                          "governing_check": "IS 800 Table 3 slenderness", "interaction_dc": .42,
                                          "interaction_governing_combo": "strength combo 1"}}
    (design / "calc_package.json").write_text(json.dumps(
        {"code": "IS 800:2007 LSD", "unit_system": "N-mm", "members": [group]}), encoding="utf-8")
    grid = {"1": [0, 0, 0], "2": [0, 0, 3600], "3": [3600, 0, 3600], "4": [3600, 0, 0]}
    frame = {"nodes": grid, "modes": [{"T": .55, "shape": {"2": [.1, .3, .2]}}],
             "slabs": [], "fixed": [1, 4], "loads": {}, "meta": {"title": "Saved frame <A>", "levels": [0, 3600]},
             "elements": [{"tag": tag, "n": pair, "L": 3600, "sec": "MB450", "type": "beam",
                           "util": 0, "f": {"P": 0}} for tag, pair in ((1, [1, 2]), (2, [2, 3]), (3, [3, 4]))]}
    (job / "model_opensees.py").write_text(
        "raise RuntimeError('saved code must never be executed')\n"
        "ops.fix(1, 1, 1, 1, 1, 1, 1)\nops.fix(4, 1, 1, 1, 0, 0, 0)\n"
        "ops.fix(2, 0, 1, 0, 0, 0, 0) # elevated roller\n", encoding="utf-8")
    (job / "viewer_3d.html").write_text("<script>\nconst DATA = " + json.dumps(frame) + ";\n</script>", encoding="utf-8")
    return job, frame


def test_native_scope_units_and_per_node_supports(sample):
    job, raw = sample
    d = native.enrich(raw, job, True)
    a, b, missing = d["elements"]
    assert a["f"] == {"Pc": 1849.69, "Pt": 1059.85, "Mx": 8.379, "My": 2.965, "V": 2.33}
    assert b["f"] == {"Pc": 0, "Pt": 0, "Mx": 0, "My": None, "V": 0}
    assert not any(v is not None for v in missing["f"].values())
    assert (a["util"], a["util_scope"], b["util"], b["util_scope"], missing["util"]) == (.72, "group", .72, "element", None)
    assert a["combo"] == "force 1"
    assert a["element_result"]["dc"] == .42 and a["element_result"]["overall_dc"] == .91
    assert a["element_result"]["governing_check"] == "IS 800 Table 3 slenderness"
    assert a["element_result"]["combination"] == "strength combo 1"
    assert d["strength_groups"]["floor-MB450"] == {"id": "floor-MB450", "dc": .72, "element": 2,
                                                   "combination": "strength combo", "clause": "9.3"}
    assert d["meta"]["units"] == {"length": "mm", "force": "kN", "moment": "kN·m"}
    assert [(s["tag"], s["kind"]) for s in d["supports"]] == [(1, "fixed"), (2, "partial"), (4, "pinned")]
    assert d["supports"][1]["dofs"] == [0, 1, 0, 0, 0, 0]
    (job / "model_opensees.py").unlink()
    d = native.enrich(raw, job, True)
    assert all(s["kind"] == "unknown" and s["dofs"] is None for s in d["supports"])


def test_historical_force_units_and_unavailable_values():
    old = {"P_comp_N": "10300", "P_comp_kN": "0", "P_tens_N": "2425", "Mz_Nmm": "2385000",
           "My_kNm": "0.0502", "V_N": "2700"}
    assert native.member_forces(old, True) == pytest.approx({"Pc": 0, "Pt": 2.425, "Mx": 2.385, "My": .0502, "V": 2.7})
    assert native.member_forces({"P_comp_kN": "NaN", "V_N": "inf"}, True) == dict.fromkeys(("Pc", "Pt", "Mx", "My", "V"))
    assert native.member_forces({"P_tens_kip": 1.5, "Mx_kipft": 3}, False) == {
        "Pc": None, "Pt": 1.5, "Mx": 3, "My": None, "V": None}


def test_incompatible_groups_and_geometry_fail_closed(sample):
    job, frame = sample
    saved = job / "design/calc_package.json"
    package = json.loads(saved.read_bytes())
    for code, groups in (("Different design basis", package["members"]),
                         ("IS 800:2007", package["members"] * 2)):
        saved.write_text(json.dumps(dict(package, code=code, members=groups)), encoding="utf-8")
        assert all(e["util"] is None for e in native.enrich(copy.deepcopy(frame), job, True)["elements"])
    frame["elements"][0]["sec"] = "MB300"
    with pytest.raises(ValueError, match="section"):
        native.enrich(frame, job, True)
    frame["elements"][0].update(sec="MB450", L=1600)
    with pytest.raises(ValueError, match="length"):
        native.enrich(frame, job, True)


def test_rebuild_is_immutable_self_contained_and_preserves_geometry(sample, tmp_path):
    job, frame = sample
    digests = {p: hashlib.sha256(p.read_bytes()).hexdigest() for p in job.rglob("*") if p.is_file()}
    for invalid in (job / "viewer_3d.html", job / "report.html", job / "design/report.html"):
        with pytest.raises(ValueError, match="staging"):
            viewer.rebuild_saved(job, invalid)
    out = viewer.rebuild_saved(job, tmp_path / "publish/viewer_3d.html")
    payload = viewer._saved_geometry(out)
    assert payload["nodes"] == frame["nodes"] and payload["modes"] == frame["modes"] and payload["slabs"] == frame["slabs"]
    assert payload["meta"]["source_sha256"]["geometry_viewer"] == digests[job / "viewer_3d.html"]
    assert payload["meta"]["source_sha256"]["design/member_schedule.csv"] == digests[job / "design/member_schedule.csv"]
    assert all(hashlib.sha256(p.read_bytes()).hexdigest() == sha for p, sha in digests.items())
    first = out.read_bytes()
    assert viewer.rebuild_saved(job, out).read_bytes() == first
    html = first.decode("utf-8")
    assert "<script src=" not in html and "\n__THREE__\n" not in html and "Saved frame &lt;A&gt;" in html
    assert "Maximum across this role and section" in html and "U.length" in html


def test_directional_characteristic_story_loads():
    loads = {}
    plan = {"story_forces_units": "N", "story_forces": {
        "EQ_X": {"1": [70000, 0, 0]}, "EQ_Y": {"1": [0, 25000, 0]}, "W_X": {"1": [-15000, 0, 0]}}}
    viewer._india_lateral(loads, plan, [3600])
    assert loads["seis"] == {"z": [3600], "X": [70], "Y": [25]}
    assert loads["wind"] == {"z": [3600], "X": [-15]}
    legacy = {"seis": {"z": [3600], "F": [70], "V": 70, "Cs": .08}}
    viewer._india_lateral(legacy, {}, [])
    assert legacy["seis"] == {"z": [3600], "X": [70]}


def test_report_viewer_reads_actual_opensees_supports_and_metric_loads(tmp_path):
    pytest.importorskip("openseespy.opensees")
    import engine3d as engine
    previous = engine.unit_system()
    try:
        engine.activate_si_units()
        cfg = {"NX": 1, "NY": 1, "SX": 6000, "SY": 6000, "heights": [3600], "base": "fixed",
               "col": "WPB300X300X100.85", "beam": "NPB450X190X67.16", "units": "N-mm",
               "jurisdiction": "india", "D_floor": 4.0, "D_roof": 4.0, "L_floor": 0.0,
               "Lr": .75, "clad": 0.0, "self_weight": False}
        button = viewer.report_section(cfg, "One bay", tmp_path)
        d = viewer._saved_geometry(tmp_path / "viewer_3d.html")
        assert "viewer_3d.html" in button and d["modes"]
        assert len(d["supports"]) == 4 and all(s["dofs"] == [1]*6 for s in d["supports"])
        assert d["loads"]["DLdyn"]["total"] == 144.0 and d["loads"]["LLdyn"]["total"] == 27.0
        assert d["loads"]["stat"]["D"]["total"] == pytest.approx(144, rel=.02)
        assert all(not any(v is not None for v in e["f"].values()) and e["util"] is None for e in d["elements"])
    finally:
        if previous == "kip-in":
            engine.activate_kip_in_units()
