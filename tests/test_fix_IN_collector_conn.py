"""IN-COLLECTOR-CONN (gold issue IN_CFS_Ex6): the beam-end connection of a collector / chord beam transfers the
collector axial force (IS 1893 (Part 1):2016 7.6.4 load path; IS 18168:2023 12.2.4.5 / 6.4: collector forces from the
overstrength earthquake load where IS 18168 applies) together with the shear: the bolt / plate / block-shear / weld
rows are checked for R = sqrt(V^2 + N^2) per combination (concurrent V and N of the same record).

Ex1 (SCBF, Delhi, IS 18168 applies): the braced-line floor / roof beams carry collector forces; the group demand is
the largest resultant over the element records -- hand check from member_combo_forces.json."""
import json
import math
import os
import sys

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, "..", "steel_engine"))

pytest.importorskip("openseespy.opensees")


@pytest.fixture(scope="module")
def ex1(tmp_path_factory):
    import pipeline as P
    from _ex1_fixture import ex1_cfg_is, stage_ex1_rag
    jobs = tmp_path_factory.mktemp("jobsColl")
    os.environ["STELTIC_TEST_JOBS"] = str(jobs)
    os.environ["STEEL_BUILDER_JOBS"] = str(jobs)
    cfg, _ = ex1_cfg_is(design=True, embedment={"capacity_N": 900e3, "cite": "EOR anchorage design (test)"})
    stage_ex1_rag(os.path.join(str(jobs), "IN_collconn"))
    out = P.design_and_report("IN_collconn", cfg, do_report=False)
    root = out["root"]
    pkg = json.load(open(os.path.join(root, "design", "calc_package.json")))
    forces = json.load(open(os.path.join(root, "design", "member_combo_forces.json")))
    return pkg, forces


def test_collector_connection_checked_for_the_resultant(ex1):
    pkg, forces = ex1
    assert pkg["collectors"]["applied_to_member_checks"]
    coll = [c for c in pkg["connections"] if "V_P_resultant_N" in (c.get("demand") or {})]
    assert coll, "no beam-end connection carries the collector axial"
    for c in coll:
        d = c["demand"]
        R = math.hypot(d["V_concurrent_N"], d["P_end_N"])
        assert d["V_P_resultant_N"] == pytest.approx(R, rel=1e-6)
        assert d["V_P_resultant_N"] > d["V_N"]                     # more than the shear alone
        assert "7.6.4" in d["resultant_basis"] and "12.2.4.5" in d["resultant_basis"]
        bolts = [x for x in c["checks"] if x["name"].endswith("bolts_10_3")]
        assert bolts and all(x["value"] == pytest.approx(R, rel=1e-6) for x in bolts)
        assert all("(V + N resultant)" in x["name"] for x in c["checks"] if x["name"].startswith("beam-end shear"))
        # hand check: the largest sqrt(V^2 + N^2) over the records of the group's elements (role, section)
        _, sec = c["id"].split("-", 2)[1:]
        role = c["id"].split("-")[1]
        best = 0.0
        for e in forces["elements"].values():
            if e.get("kind") == "beam" and e.get("section") == sec and e.get("role") == role:
                for lab, r in e["records"].items():
                    best = max(best, math.hypot(r[3], r[0]))
        assert d["V_P_resultant_N"] == pytest.approx(best, rel=1e-3)


def test_beams_without_axial_keep_the_shear_demand(ex1):
    pkg, _ = ex1
    plain = [c for c in pkg["connections"] if c["id"].startswith(("conn-floor", "conn-roof"))
             and "V_P_resultant_N" not in (c.get("demand") or {})]
    for c in plain:
        for x in c["checks"]:
            if x["name"].endswith("bolts_10_3"):
                assert x["value"] == pytest.approx(c["demand"]["V_N"], rel=1e-6)
