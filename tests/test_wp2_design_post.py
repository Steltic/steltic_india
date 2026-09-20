"""HR800-22 / WP2.1.5: design_post SI roof live from cfg['Lr'] (not 1.0); snow separate; missing Lr raises."""
import os
import sys

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "steel_engine"))

import openseespy.opensees as ops  # noqa: E402
import design_post as DP  # noqa: E402


def _nodes():
    ops.wipe()
    ops.model("basic", "-ndm", 3, "-ndf", 6)
    ops.node(100001, 0.0, 0.0, 3500.0)
    ops.node(100002, 6000.0, 0.0, 3500.0)


def test_roof_live_from_cfg():
    _nodes()
    cfg = {"heights": [3500.0], "SX": 6000.0, "SY": 6000.0, "D_roof": 2.0, "D_floor": 4.0, "L_floor": 4.0,
           "Lr": 1.5, "units": "N-mm"}
    M, V = DP._beam_grav(cfg, 100001, 100002, 1.5, 0.0, 1.5)
    w = (1.5 * 2.0 + 1.5 * 1.5) * 6000.0 / 1000.0
    assert M == pytest.approx(w * 6000.0 ** 2 / 8.0)
    assert V == pytest.approx(w * 6000.0 / 2.0)


def test_roof_live_missing_raises_and_snow_separate():
    _nodes()
    cfg = {"heights": [3500.0], "SX": 6000.0, "SY": 6000.0, "D_roof": 2.0, "D_floor": 4.0, "L_floor": 4.0,
           "units": "N-mm"}
    with pytest.raises(ValueError):
        DP._beam_grav(cfg, 100001, 100002, 1.5, 0.0, 1.5)
    cfg["snow"] = 2.0
    M, _ = DP._beam_grav(cfg, 100001, 100002, 1.0, 0.0, 1.0)
    assert M == pytest.approx((2.0 + 2.0) * 6.0 * 6000.0 ** 2 / 8.0)
