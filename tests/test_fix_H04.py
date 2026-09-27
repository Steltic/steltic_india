"""H04 (HR-B-11, E3, NEW-5): one floor mass-moment-of-inertia helper with the TRUE plan extent; a builder-declared
J (info['Jm']) and cfg['Jm_by_level'] are kept by modal_props."""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "steel_engine"))


@pytest.fixture(scope="module")
def E():
    pytest.importorskip("openseespy.opensees")
    import engine3d as E
    import india_units as IU
    IU.activate_si()
    return E


def _portal():
    return {"NX": 1, "NY": 1, "SX": 6000.0, "SY": 6000.0, "heights": [3600.0], "base": "fixed",
            "col": "WPB300X300X100.85", "beam": "NPB450X190X67.16", "units": "N-mm", "jurisdiction": "india",
            "D_floor": 4.0, "D_roof": 4.0, "L_floor": 0.0, "Lr": 0.75, "clad": 0.0, "self_weight": False}


def test_one_bay_portal_true_extent(E):
    cfg = _portal()
    mp = E.modal_props(cfg)
    m = mp["m"][1]
    assert mp["J"][1] == pytest.approx(m * (6000.0 ** 2 + 6000.0 ** 2) / 12.0, rel=1e-9)   # not x 4 (E3)
    assert "true plan extent" in mp["J_basis"][1]
    # the builder (example_build) assigns the same J to the master node
    import openseespy.opensees as ops
    E.build(cfg, "Linear")
    assert ops.nodeMass(E.mtag(1), 6) == pytest.approx(mp["J"][1], rel=1e-9)


def test_plan_extent_uses_xcoords(E):
    cfg = dict(_portal(), NX=2, xcoords=[0.0, 4000.0, 11000.0])
    assert E.plan_extent(cfg, 1) == (pytest.approx(11000.0), pytest.approx(6000.0))


def test_builder_J_and_override_kept(E):
    import example_build as EB

    def cb(cfg, transf):
        info = EB.example_build(cfg, transf)
        info["Jm"] = {1: 1.234e9}
        return info
    cfg = dict(_portal(), custom_build=cb)
    mp = E.modal_props(cfg)
    assert mp["J"][1] == pytest.approx(1.234e9) and mp["J_basis"][1] == "builder info['Jm']"
    cfg2 = dict(_portal(), Jm_by_level={1: 2.0e9})
    mp2 = E.modal_props(cfg2)
    assert mp2["J"][1] == pytest.approx(2.0e9) and mp2["J_basis"][1] == "cfg['Jm_by_level']"
