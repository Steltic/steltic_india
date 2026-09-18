"""Minimal India OpenSees smoke: metric brief → kip-in + IS 808 MB + example_build + eigen.

Requires project venv with openseespy (CPython <3.13). Skip cleanly if unavailable.
Does NOT invent load values — uses placeholder D_floor/D_roof only so mass path runs;
load_plan RAG gate is not exercised here (see test_india_load_plan).
"""
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "steel_engine"))
sys.path.insert(0, str(ROOT / "steltic"))

openseespy = pytest.importorskip("openseespy.opensees", reason="openseespy not installed in this interpreter")


def test_india_metric_is808_build_and_eigen():
    import openseespy.opensees as ops
    import india_units as IU
    import sections as S
    import example_build as EB
    import engine3d as eng

    p = S.props("MB300")
    assert p["A"] > 0 and p["d"] > 0

    cfg = {
        "name": "IN_smoke_2storey",
        "units": "metric",
        "NX": 1,
        "NY": 1,
        "bay_x": 6.0,
        "bay_y": 6.0,
        "story_heights": [3.6, 3.6],
        "col": "MB300",
        "beam": "MB250",
        "base": "fixed",
        "jurisdiction": "india",
        # Placeholder gravity/clad for mass only — not design values from RAG.
        "D_floor": 80.0,
        "D_roof": 60.0,
        "clad": 15.0,
        "L_floor": 50.0,
        "Lr": 20.0,
    }
    IU.apply_metric_geometry(cfg)
    assert cfg.get("SX") and cfg.get("heights")
    assert abs(cfg["SX"] - 6.0 * IU.M_TO_IN) < 1e-6

    info = EB.example_build(cfg, transf="Linear")
    assert info["NF"] == 2
    assert len(info["ele"]) >= 4  # cols + beams both ways

    for k in range(1, info["NF"] + 1):
        ops.mass(eng.mtag(k), 1.0, 1.0, 0.0, 0.0, 0.0, 0.0)

    ops.wipeAnalysis()
    lam = ops.eigen("-fullGenLapack", 2)
    assert len(lam) >= 1 and all(float(x) > 0 for x in lam[:1])
    T1 = 2 * 3.141592653589793 / (float(lam[0]) ** 0.5)
    assert 0.01 < T1 < 10.0
