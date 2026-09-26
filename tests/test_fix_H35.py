"""H35 (CFS-D-03): stepped supports are foundations -- floating_columns skips columns whose bottom node is a support;
floor_beam_gaps honours omit_beams_at / stepped_bases (the documented split-level schema)."""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "steel_engine"))


def _split_level_build(cfg, transf="Linear"):
    """2 x 1 bays, 2 storeys; the i = 2 column line is founded on the uphill grade at level 1 (stepped base) and no
    level-1 beams frame into it (split-level CFS schema)."""
    import openseespy.opensees as ops
    import engine3d as E
    ops.wipe(); ops.model("basic", "-ndm", 3, "-ndf", 6)
    z = E.zlevels(cfg)
    full = {(i, j) for i in range(3) for j in range(2)}
    low = {(i, j) for i in range(2) for j in range(2)}
    pres = {0: low, 1: low, 2: full}
    node_sets = {0: low, 1: full, 2: full}
    for k, P in node_sets.items():
        for (i, j) in P:
            ops.node(E.ntag(i, j, k), i * cfg["SX"], j * cfg["SY"], z[k])
    for (i, j) in low:
        ops.fix(E.ntag(i, j, 0), 1, 1, 1, 1, 1, 1)
    for j in range(2):
        ops.fix(E.ntag(2, j, 1), 1, 1, 1, 1, 1, 1)                     # stepped base on the grade at level 1
    cm = {}
    for k in (1, 2):
        pts = pres[k]
        cx = sum(i * cfg["SX"] for i, j in pts) / len(pts); cy = sum(j * cfg["SY"] for i, j in pts) / len(pts)
        cm[k] = (cx, cy); ops.node(E.mtag(k), cx, cy, z[k]); ops.fix(E.mtag(k), 0, 0, 1, 1, 1, 0)
    et, eles = 1, []
    for (i, j) in full:
        for k in (0, 1):
            if (i, j) in node_sets[k] and (i, j) in node_sets[k + 1]:
                E.add_column(et, E.ntag(i, j, k), E.ntag(i, j, k + 1), cfg["col"], "X")
                eles.append((et, "col", cfg["col"], E.ntag(i, j, k), E.ntag(i, j, k + 1))); et += 1
    omit = {1: {(2, 0), (2, 1)}}
    for k in (1, 2):
        P = node_sets[k]
        for (i, j) in sorted(P):
            for b in ((i + 1, j), (i, j + 1)):
                if b in P and (i, j) not in omit.get(k, set()) and b not in omit.get(k, set()):
                    E.add_beam(et, E.ntag(i, j, k), E.ntag(*b, k), cfg["beam"])
                    eles.append((et, "beam", cfg["beam"], E.ntag(i, j, k), E.ntag(*b, k))); et += 1
    for k in (1, 2):
        ops.rigidDiaphragm(3, E.mtag(k), *[E.ntag(i, j, k) for (i, j) in pres[k]])
        m = E.floor_w(cfg, k) / E.g
        ops.mass(E.mtag(k), m, m, 0.0, 0.0, 0.0, E.floor_plan_inertia(cfg, k, m, pres[k])[0])
    return {"cm": cm, "present": pres, "z": z, "NF": 2, "ele": eles,
            "stepped_bases": {1: {(2, 0), (2, 1)}}, "omit_beams_at": omit}


def test_split_level_stepped_bases_not_floating_and_no_gaps():
    pytest.importorskip("openseespy.opensees")
    import engine3d as E
    import india_seismic as IS
    import india_units as IU
    IU.activate_si()
    cfg = {"NX": 2, "NY": 1, "SX": 6000.0, "SY": 6000.0, "heights": [3500.0, 3500.0], "units": "N-mm",
           "jurisdiction": "india", "col": "WPB300X300X100.85", "beam": "NPB450X190X67.16",
           "D_floor": 3.0, "D_roof": 2.0, "L_floor": 2.5, "Lr": 0.75, "clad": 0.0, "self_weight": False,
           "custom_build": _split_level_build}
    fl = IS.floating_columns(cfg)
    assert fl["irregular"] is False and fl["columns"] == []
    assert E.floor_beam_gaps(cfg) == []


def test_undeclared_missing_beam_still_a_gap():
    pytest.importorskip("openseespy.opensees")
    import engine3d as E

    def cb(cfg, transf="Linear"):
        info = _split_level_build(cfg, transf)
        info.pop("omit_beams_at")
        return info
    cfg = {"NX": 2, "NY": 1, "SX": 6000.0, "SY": 6000.0, "heights": [3500.0, 3500.0], "units": "N-mm",
           "jurisdiction": "india", "col": "WPB300X300X100.85", "beam": "NPB450X190X67.16",
           "D_floor": 3.0, "D_roof": 2.0, "L_floor": 2.5, "Lr": 0.75, "clad": 0.0, "self_weight": False,
           "custom_build": cb}
    gaps = E.floor_beam_gaps(cfg)
    # the two level-1 beams from the floor into the grade nodes are missing and not declared; the grade-to-grade
    # pair (both supports) is not a gap
    assert len(gaps) == 2
