"""H18 (HR-E-05, NEW-1): preflight ERROR for sloped beams (end levels differ > 1 mm) and for roof-level beams
with zero tributary under non-zero roof area loads -- no more silent zero roof load / roof weight."""
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "steel_engine"))
sys.path.insert(0, os.path.dirname(__file__))
from _ex1_fixture import ex1_cfg_is  # noqa: E402


def _portal(ridge_dz):
    """1 x 1 bay, eave level 1 at 8 m; rafters (i=0 -> ridge node) sloped by ridge_dz."""
    import openseespy.opensees as ops
    import engine3d as E
    ops.wipe(); ops.model("basic", "-ndm", 3, "-ndf", 6)
    for (i, j) in ((0, 0), (1, 0), (0, 1), (1, 1)):
        ops.node(E.ntag(i, j, 0), i * 12000.0, j * 6000.0, 0.0)
        ops.node(E.ntag(i, j, 1), i * 12000.0, j * 6000.0, 8000.0)
    ops.node(990001, 6000.0, 0.0, 8000.0 + ridge_dz)
    ele = [(1, "beam", "MB300", E.ntag(0, 0, 1), 990001), (2, "beam", "MB300", 990001, E.ntag(1, 0, 1)),
           (3, "beam", "MB300", E.ntag(0, 1, 1), E.ntag(1, 1, 1)), (4, "beam", "MB300", E.ntag(0, 0, 1), E.ntag(0, 1, 1))]
    pres = {0: {(0, 0), (1, 0), (0, 1), (1, 1)}, 1: {(0, 0), (1, 0), (0, 1), (1, 1)}}
    return {"NF": 1, "present": pres, "ele": ele}


CFG = {"heights": [8000.0], "NX": 1, "NY": 1, "SX": 12000.0, "SY": 6000.0, "D_roof": 0.5, "Lr": 0.75}


def test_sloped_beam_is_error():
    import static_model as SM
    f = SM.pitched_roof_findings(CFG, _portal(1500.0))
    assert any(s == "ERROR" and "end levels" in m for s, m in f)
    # X02: an invalid / non-matching roof_planes declaration no longer silences the guard; a plane that the sloped
    # rafters actually lie on does
    assert any(s == "ERROR" for s, m in SM.pitched_roof_findings(dict(CFG, roof_planes=[{}]), _portal(1500.0)))
    plane = {"axis": "X", "eave_coords_mm": [0.0, 12000.0], "ridge_coord_mm": 6000.0, "eave_z_mm": 8000.0,
             "ridge_z_mm": 9500.0, "lines": [0]}
    assert SM.pitched_roof_findings(dict(CFG, roof_planes=[plane]), _portal(1500.0)) == []
    assert not SM.pitched_roof_findings(CFG, _portal(0.0))


def test_zero_tributary_roof_beam_is_error():
    import static_model as SM
    info = _portal(0.0)
    info["present"][1] = {(0, 0), (0, 1), (1, 1)}              # the bay is not complete at the roof level
    f = SM.pitched_roof_findings(CFG, info)
    assert any(s == "ERROR" and "zero tributary" in m for s, m in f)
    assert not SM.pitched_roof_findings(dict(CFG, D_roof=0.0, Lr=0.0), info)


def test_flat_ex1_passes_preflight_guard():
    import static_model as SM
    import preflight as P
    cfg, _ = ex1_cfg_is()
    assert SM.pitched_roof_findings(cfg) == []
    assert not any("end levels" in m or "zero tributary" in m for s, m in P.india_checks(cfg))
