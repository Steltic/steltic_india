"""X04 (HR-D-13, HR-C-06): several seismically separated units in one job -- pipeline.design_units runs each unit as its
own sub-job <name>/units/<unit>/, computes the IS 1893 7.11.3 separation of every joint from the two units' 7.11.1
displacements at the matching level, and writes one combined STATUS, a units index and a summary json."""
import json
import os
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "steel_engine"))

A = {"disp_max_mm": [4.0, 9.0], "z_mm": [3600.0, 7200.0], "R": 5.0}
B = {"disp_max_mm": [3.0], "z_mm": [3600.0], "R": 4.0}


def test_joint_matching_level_amd1_form():
    import multi_unit as MU
    r = MU.joint_separation({"units": ["A", "B"], "direction": "X", "gap_mm": 20.0}, A, B)
    # B's only level (3.6 m) matches A's level 1: (R1 D1 + R2 D2)/2 at that level, not A's roof displacement
    assert r["same_floor_levels"] is True and r["governing_levels"] == {"A": 1, "B": 1}
    assert r["value"] == pytest.approx((5.0 * 4.0 + 4.0 * 3.0) / 2.0)
    assert r["dc"] == pytest.approx(16.0 / 20.0) and r["ok"] is True
    assert r["clause"] == "IS 1893 7.11.3" and "Amd 1" in r["cite"]
    r = MU.joint_separation({"units": ["A", "B"], "direction": "X", "gap_mm": 15.0}, A, B)
    assert r["ok"] is False


def test_joint_full_form_when_levels_differ():
    import multi_unit as MU
    # B founded 1.2 m higher: its level sits at 4.8 m, between A's levels -> R1 D1 + R2 D2; A's displacement is the
    # largest up to its first level at/above B's top (level 2 at 7.2 m)
    r = MU.joint_separation({"units": ["A", "B"], "direction": "X", "gap_mm": 100.0, "base_mm": {"B": 1200.0}}, A, B)
    assert r["same_floor_levels"] is False
    assert r["value"] == pytest.approx(5.0 * 9.0 + 4.0 * 3.0) and r["governing_levels"] == {"A": 2, "B": 1}
    # a declared same_floor_levels that the elevations contradict falls back to the full form (conservative)
    r2 = MU.joint_separation({"units": ["A", "B"], "direction": "X", "gap_mm": 100.0, "base_mm": {"B": 1200.0},
                              "same_floor_levels": True}, A, B)
    assert r2["value"] == pytest.approx(r["value"]) and "NOT the same levels" in r2["same_floor_levels_basis"]
    # declared False forces the full form even when the levels match; A contact height = its level 1
    r3 = MU.joint_separation({"units": ["A", "B"], "direction": "X", "gap_mm": 100.0, "same_floor_levels": False}, A, B)
    assert r3["value"] == pytest.approx(5.0 * 4.0 + 4.0 * 3.0)
    # no gap -> the joint check stays open; missing displacements -> not evaluated
    r4 = MU.joint_separation({"units": ["A", "B"], "direction": "X"}, A, B)
    assert r4["ok"] is None and r4["dc"] is None and "gap_mm" in r4["reason"] and r4["value"] == pytest.approx(16.0)
    r5 = MU.joint_separation({"units": ["A", "B"], "direction": "Y", "gap_mm": 50.0}, A, None)
    assert r5["ok"] is None and r5["value"] is None


def _fake_pipeline(monkeypatch, tmp_path, statuses, disp):
    import pipeline as P
    monkeypatch.setenv("STEEL_BUILDER_JOBS", str(tmp_path))

    def fake(name, cfg=None, do_report=True):
        root = P._root(name)
        os.makedirs(os.path.join(root, "design"), exist_ok=True)
        u = name.rsplit("/", 1)[-1]
        if statuses[u] == "blocked":
            return {"name": name, "root": root, "blocked": True, "error": "preflight ERRORs"}
        pkg = {"design_status": {"status": statuses[u], "reasons": [] if statuses[u] == "complete" else ["r-" + u]},
               "unit_displacements": {"X": disp[u]}}
        json.dump(pkg, open(os.path.join(root, "design", "calc_package.json"), "w"))
        open(os.path.join(root, "report.html"), "w").write("<html></html>")
        return {"name": name, "root": root, "design_status": pkg["design_status"]}
    monkeypatch.setattr(P, "design_and_report", fake)
    return P


def test_combined_status(tmp_path, monkeypatch):
    P = _fake_pipeline(monkeypatch, tmp_path, {"A": "complete", "B": "complete"}, {"A": A, "B": B})
    ok = P.design_units("J1", {"A": {}, "B": {}}, [{"units": ["A", "B"], "direction": "X", "gap_mm": 20.0}])
    assert ok["status"] == "complete" and ok["reasons"] == []
    bad = P.design_units("J2", {"A": {}, "B": {}}, [{"units": ["A", "B"], "direction": "X", "gap_mm": 10.0}])
    assert bad["status"] == "partial" and any("joint A-B" in r and "16.0 mm > provided gap 10.0 mm" in r for r in bad["reasons"])
    _fake_pipeline(monkeypatch, tmp_path, {"A": "partial", "B": "blocked"}, {"A": A, "B": B})
    r = P.design_units("J3", {"A": {}, "B": {}}, [{"units": ["A", "B"], "direction": "X", "gap_mm": 20.0}])
    assert r["status"] == "partial"
    assert "unit A: r-A" in r["reasons"] and any(x.startswith("unit B: unit blocked") for x in r["reasons"])
    assert any("not evaluated" in x for x in r["reasons"])        # B has no displacements
    _fake_pipeline(monkeypatch, tmp_path, {"A": "complete", "B": "complete"}, {"A": A, "B": B})
    r = P.design_units("J5", {"A": {}, "B": {}}, [{"units": ["A", "B"], "direction": "X"}])
    assert r["status"] == "partial" and any("gap_mm not declared" in x for x in r["reasons"])
    with pytest.raises(ValueError):
        P.design_units("J4", {"A/x": {}}, [])
    with pytest.raises(ValueError):
        P.design_units("J4", {"A": {}, "B": {}}, [{"units": ["A", "C"], "direction": "X"}])


def test_two_unit_driver_on_real_frames(tmp_path, monkeypatch):
    """Two small EBF frames (2 storeys and 1 storey, 3.6 m storeys) with an X joint: the separation uses both units'
    7.11.1 displacements at the matching level 1 (recomputed here independently with engine3d.india_drift)."""
    monkeypatch.setenv("STEEL_BUILDER_JOBS", str(tmp_path))
    import example_build_ebf as XE
    import engine3d as E
    import pipeline as P
    import package_finalize as PF
    cfgs = {"A": XE.ebf_example_cfg(name="A"), "B": XE.ebf_example_cfg(name="B", heights_m=(3.6,))}
    res = P.design_units("IN_X04", cfgs, [{"units": ["A", "B"], "direction": "X", "gap_mm": 25.0}], do_report=False)
    root = tmp_path / "IN_X04"
    for u in ("A", "B"):
        assert (root / "units" / u / "design" / "calc_package.json").exists()
    j = res["joints"][0]
    D = {}
    for u in ("A", "B"):
        c = E.CFG["IN_X04/units/%s" % u]
        dr = E.india_drift(c, E.design_eccentricities(c))
        D[u] = dr["X"]["disp_max"]
    assert len(D["A"]) == 2 and len(D["B"]) == 1 and D["A"][1] > D["A"][0]
    assert j["same_floor_levels"] is True and j["governing_levels"] == {"A": 1, "B": 1}
    assert j["D_mm"]["A"] == pytest.approx(D["A"][0], rel=1e-9) and j["D_mm"]["B"] == pytest.approx(D["B"][0], rel=1e-9)
    assert j["value"] == pytest.approx((5.0 * D["A"][0] + 5.0 * D["B"][0]) / 2.0, rel=1e-9)
    assert j["ok"] is True and j["dc"] == pytest.approx(j["value"] / 25.0)
    unit_st = [res["units"][u]["status"] for u in ("A", "B")]
    assert res["status"] == PF.worst_status(unit_st + ["complete"])
    st = (root / "STATUS.engine.md").read_text()
    assert "design status: %s" % res["status"].upper() in st and "A-B A-B dir X" in st
    assert (root / "STATUS.md").read_text() == st
    idx = (root / "units_index.html").read_text()
    assert "IS 1893 7.11.3" in idx and ">A<" in idx and ">B<" in idx
    summ = json.load(open(root / "units_summary.json"))
    assert summ["status"] == res["status"] and summ["joints"][0]["value"] == pytest.approx(j["value"])
    # figures of the nested unit jobs are written under sanitised names (H45)
    figs = list((root / "units" / "A" / "figs").glob("*.png"))
    assert figs and all("/" not in f.name and f.name.startswith("IN_X04__units__A_") for f in figs)
