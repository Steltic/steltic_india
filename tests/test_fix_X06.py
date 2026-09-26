"""X06 (E11, HR-B-20): the JSON-declared frame builder promoted from the CFS engine (steel_engine/frame_build.py), the
EBF reference example (example_build_ebf.py) and the shared package-finalize helpers (package_finalize.py)."""
import json
import math
import os
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "steel_engine"))


def test_attach_gold_converts_units_once():
    import frame_build as FB
    cfg = {"name": "t", "units": "m", "jurisdiction": "india", "NX": 2, "NY": 1, "bay_x": 6.0, "bay_y": 5.0,
           "heights": [3.0, 3.0], "col": "WPB200X200X50.92", "beam": "NPB300X165X39.88", "base": "fixed",
           "D_floor": 3.0, "D_roof": 2.0, "L_floor": 3.0, "Lr": 0.75, "clad": 0.0}
    gold = {"xcoords_m": [0.0, 5.0, 12.0], "xbays": {"1-2": [["X", 0, 0]]}, "brace_sec": {"1-2": "WPB200X200X50.92"}}
    FB.attach_gold(cfg, gold)
    assert cfg["xcoords"] == [0.0, 5000.0, 12000.0] and cfg["heights"] == [3000.0, 3000.0]
    assert cfg["custom_build"] is FB.frame_build and cfg["braces"] is None and cfg["gold"] is gold
    import india_units as IU
    IU.apply_si_geometry(cfg)                                   # idempotent: no second x1000
    assert cfg["xcoords"] == [0.0, 5000.0, 12000.0]
    import engine3d as E
    import openseespy.opensees as ops
    info = E.build(cfg, "Linear")
    assert ops.nodeCoord(E.ntag(2, 1, 2)) == pytest.approx([12000.0, 5000.0, 6000.0])
    assert len([e for e in info["ele"] if e[1] == "brace"]) == 4 and info["bases"][(0, 0)] == "fixed"


def test_ebf_example_model_complete_and_link_geometry():
    import example_build_ebf as XE
    import engine3d as E
    import openseespy.opensees as ops
    cfg = XE.ebf_example_cfg()
    info = E.build(cfg, "Linear")
    assert len(info["links"]) == 4 * 2                          # four EBF bays x two storeys
    for ln in info["links"]:
        assert ln["e_mm"] == 900.0 and ln["bay_L_mm"] == 6000.0 and len(ln["brace_tags"]) == 2
        link = [e for e in info["ele"] if e[0] == ln["tag"]][0]
        a, b = ops.nodeCoord(link[3]), ops.nodeCoord(link[4])
        ax = 0 if ln["dir"] == "X" else 1
        assert abs(b[ax] - a[ax]) == pytest.approx(900.0)
        assert ((a[ax] + b[ax]) / 2.0) % 6000.0 == pytest.approx(3000.0)   # centre link: (L - e)/2 from each column
        assert ops.eleType(ln["tag"]).startswith("ElasticTimoshenkoBeam")
    assert E.floor_beam_gaps(cfg) == []                         # model_complete (engine3d.report gate)
    import static_model as SM
    assert SM.pitched_roof_findings(cfg) == []                  # EBF beam pieces at the far end of an edge bay are not zero-tributary
    import preflight as PF
    assert not [m for s, m in PF.check(cfg) if s == "ERROR"]


def test_ebf_example_passes_ebf_link_checks(tmp_path, monkeypatch):
    monkeypatch.setenv("STEEL_BUILDER_JOBS", str(tmp_path))
    import example_build_ebf as XE
    import engine3d as E
    import design_pipeline as DP
    import sections as S
    import india_is800 as I8
    cfg = XE.ebf_example_cfg()
    E.CFG[XE.NAME] = cfg
    DP.design(XE.NAME, outdir=str(tmp_path / "design"))
    pkg = json.load(open(tmp_path / "design" / "calc_package.json"))
    rows = pkg["capacity_design"]["section12"]["checks"]
    link_ids = ("11.1_link_section", "is18168_table2_link", "11.2_link_design_shear", "11.3_link_length",
                "12.3.2.1_link_shear", "12.3.3.1_link_rotation", "11.4.1_end_stiffeners", "11.4.2_intermediate_stiffeners",
                "12.3.1_link_not_at_column", "12.3.3.2_link_bracing", "12.3.2.2_link_overstrength")
    links = sorted({c["member"] for c in rows if c["id"] == "11.2_link_design_shear"})
    assert len(links) == 8
    for lid in links:
        got = {c["id"]: c for c in rows if c.get("member") == lid}
        for k in link_ids:
            assert got[k]["ok"] is True, (lid, k, got.get(k))
    # capacity-protected braces / columns / beams of the links, member checks: nothing fails
    assert not [c for c in rows if c.get("ok") is False]
    assert all((m.get("DC") or 0.0) <= 1.0 for m in pkg["members"])
    # hand values (IS 18168 11.2 / 11.3 / 12.3.3.1) for one link
    p = S.props("NPB350X170X66.05")
    fy = I8.fy_is2062("E250 B0", I8.governing_thickness_mm(p))
    VpL = fy * (p["d"] - 2 * p["tf"]) * p["tw"] / math.sqrt(3.0)
    MpL = fy * p["Zx"]
    c = {r["id"]: r for r in rows if r.get("member") == links[0]}
    assert c["11.2_link_design_shear"]["value"] == pytest.approx(min(VpL / 1.1, 2 * MpL / (900.0 * 1.1)), rel=1e-6)
    assert c["11.3_link_length"]["limit"] == pytest.approx(1.6 * MpL / VpL, rel=1e-6)
    rot = c["12.3.3.1_link_rotation"]["value"]
    drifts = {(d["dir"], d["storey"]): d["value"] for d in pkg["drift_table"]}
    cands = [6000.0 / 900.0 * 5.0 * v for v in drifts.values()]
    assert any(abs(rot - x) < 1e-9 for x in cands) and rot <= 0.08       # (L/e) x R x elastic storey drift


def test_package_finalize_status_writer(tmp_path):
    import package_finalize as PF
    import pipeline as P
    assert PF.worst_status(["complete", "complete"]) == "complete"
    assert PF.worst_status(["complete", "partial"]) == "partial"
    assert PF.worst_status(["partial", "example_only", "complete"]) == "example_only"
    assert PF.worst_status(["complete", None]) == "partial"
    r = PF.write_status(str(tmp_path), "J", "partial", "auth", ["a", "b"], sections=[("Units", ["U1: COMPLETE"])])
    body = open(r["engine"]).read()
    assert body.startswith(P.ENGINE_STATUS_MARK) and "design status: PARTIAL" in body and "- U1: COMPLETE" in body
    assert r["status_md"] and open(r["status_md"]).read() == body
    (tmp_path / "STATUS.md").write_text("# Package status (agent)\nCOMPLETE\n")
    r = PF.write_status(str(tmp_path), "J", "complete", "auth", [])
    assert r["status_md"] is None and (tmp_path / "STATUS.md").read_text().startswith("# Package status (agent)")
    assert "COMPLETE" in (tmp_path / "STATUS.engine.md").read_text()
