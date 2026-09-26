"""H16 (HR-E-10, HR-B-13), H22 (HR-B-08, R1), H50 W part (HR-E-21): seismic weight completeness."""
import copy
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


def _cfg(**kw):
    c = {"NX": 2, "NY": 1, "SX": 6000.0, "SY": 6000.0, "heights": [4000.0, 4000.0], "base": "fixed",
         "col": "WPB300X300X100.85", "beam": "NPB450X190X67.16", "units": "N-mm", "jurisdiction": "india",
         "D_floor": 3.0, "D_roof": 2.0, "L_floor": 2.5, "Lr": 0.75, "clad": 0.0, "self_weight": False}
    c.update(kw)
    return c


# ---- H22 / R1 --------------------------------------------------------------------------------------------------
def test_partition_default_is_max_of_half_and_allowance(E):
    c = _cfg(partition_load_kNm2=1.0)
    comps = E.seismic_weight_components(c, 1)
    assert comps["partitions"] == pytest.approx(1.0 * 72.0 * 1000.0)            # 12 m x 6 m floor
    assert E.seismic_weight_components(_cfg(), 1)["partitions"] == pytest.approx(0.5 * 72.0 * 1000.0)
    assert E.seismic_weight_components(_cfg(partition_load_kNm2=1.0, partition_seismic_kNm2=0.5), 1)[
        "partitions"] == pytest.approx(0.5 * 72.0 * 1000.0)                        # declared value kept (+ WARN)


def test_preflight_warns_low_declared_partitions():
    from _ex1_fixture import ex1_cfg_is
    import preflight as PF
    cfg, _ = ex1_cfg_is()                         # partition_load 1.0, partition_seismic 0.5
    w = [m for s, m in PF.india_checks(cfg) if s == "WARN" and "partition_seismic_kNm2" in m]
    assert w and "7.3.6" in w[0]


# ---- H50 ------------------------------------------------------------------------------------------------------
def test_roof_levels_no_partitions_no_imposed(E):
    c = _cfg(roof_levels=[1], snow=2.0)
    assert E.roof_levels(c) == {1, 2}
    c1 = E.seismic_weight_components(c, 1)
    assert "partitions" not in c1 and "imposed" not in c1
    assert c1["dead"] == pytest.approx(2.0 * 72.0 * 1000.0)                       # D_roof on a roof level
    assert c1["snow"] == pytest.approx(0.2 * 2.0 * 72.0 * 1000.0)


# ---- H16 ------------------------------------------------------------------------------------------------------
def test_grid_base_returns_declared_present0(E):
    c = _cfg(present={0: [(0, 0), (1, 0), (2, 0), (0, 1), (1, 1), (2, 1)], 1: [(0, 0), (1, 0), (0, 1), (1, 1)],
                      2: [(0, 0), (1, 0), (2, 0), (0, 1), (1, 1), (2, 1)]})
    assert E.grid(c, 0) == {(0, 0), (1, 0), (2, 0), (0, 1), (1, 1), (2, 1)}
    assert E.grid(c, 1) == {(0, 0), (1, 0), (0, 1), (1, 1)}


def test_cladding_on_envelope_not_mezzanine_edge(E):
    full = [(i, j) for i in range(3) for j in range(2)]
    c = _cfg(clad=0.5, present={0: full, 1: [(0, 0), (1, 0), (0, 1), (1, 1)], 2: full})
    comps = E.seismic_weight_components(c, 1)
    # envelope 12 x 6 m -> perimeter 36 m (the mezzanine's own boundary is 24 m)
    assert E.envelope_perim_mm(c, 1) == pytest.approx(36000.0)
    assert comps["cladding"] == pytest.approx(0.5 * 36000.0 * 4000.0 / 1000.0)
    c2 = dict(c, envelope=[(0, 0), (1, 0), (0, 1), (1, 1)])
    assert E.envelope_perim_mm(c2, 1) == pytest.approx(24000.0)


def _stub_builder(z_stub):
    import example_build as EB
    import openseespy.opensees as ops

    def cb(cfg, transf):
        info = EB.example_build(cfg, transf)
        import engine3d as E
        x, y, _ = ops.nodeCoord(E.ntag(0, 0, 0))
        ops.node(900001, x - 500.0, y, z_stub)                    # crane-bracket-like node, tag level 9
        ops.fix(900001, 0, 0, 0, 1, 1, 1)
        E.add_column(99001, E.ntag(0, 0, 1), 900001, "WPB300X300X100.85", "X")
        info["ele"].append((99001, "col", "WPB300X300X100.85", E.ntag(0, 0, 1), 900001))
        return info
    return cb


def test_self_weight_binned_by_z(E):
    c = _cfg(self_weight=True, custom_build=_stub_builder(3700.0))
    E.build(c, "Linear")
    sw = c["_sw_by_level"]
    assert 9 not in sw                                              # old: binned to tag level 9 (never read)
    A = E.Ipack("WPB300X300X100.85")[0]
    import math
    Ls = math.hypot(500.0, 300.0)
    # both stub ends are nearest level 1 (z 4000 and 3700)
    c0 = _cfg(self_weight=True)
    E.build(c0, "Linear")
    assert sw[1] - c0["_sw_by_level"][1] == pytest.approx(A * E.STEEL_N_PER_MM3 * Ls, rel=1e-6)


def test_nodal_masses_nodal_dead_and_crane_in_W(E):
    c = _cfg(nodal_masses=[{"ijk": (1, 0, 2), "mass_kN": 50.0, "note": "tank"},
                           {"node": E.ntag(0, 0, 1), "mass_kN": 20.0}],
             nodal_dead_loads=[{"node": E.ntag(2, 1, 1), "Fz_N": -30e3, "level": 1, "note": "gantry"},
                               {"node": E.ntag(0, 0, 1), "Fz_N": -99e3}],          # same node as a nodal mass: skipped
             crane={"bridge_kN": 180.0, "crab_kN": 40.0, "capacity_kN": 200.0, "rail_height_mm": 3000.0})
    W0 = sum(E.seismic_weights(_cfg())[0])
    Wv, comps = E.seismic_weights(c)
    assert comps[2]["nodal_masses"] == pytest.approx(50e3)
    assert comps[1]["nodal_masses"] == pytest.approx(20e3)
    assert comps[1]["nodal_dead"] == pytest.approx(30e3)
    assert comps[1]["crane"] == pytest.approx(220e3)              # bridge + crab, not the lifted load
    assert sum(Wv) - W0 == pytest.approx(320e3)
    # modal mass follows W
    mp = E.modal_props(c)
    assert mp["m"][1] * E.g == pytest.approx(Wv[0], rel=1e-9)
