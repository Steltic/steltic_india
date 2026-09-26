"""H50 (HR-E-06, HR-E-21, HR-E-26, HR-B-16 part): cfg['roof_levels'] treated as roofs by the static loads,
partial snow split at a declared ridge, snow on every roof level, cfg['nodal_imposed_loads'] factored by fL / fLr."""
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "steel_engine"))
sys.path.insert(0, os.path.dirname(__file__))
from _ex1_fixture import ex1_cfg_is  # noqa: E402


def _state(cfg, *a, **kw):
    import static_model as SM
    import openseespy.opensees as ops
    ops.wipe()
    model = SM.build_static(cfg, "Linear", 2)
    ops.timeSeries("Linear", 1); ops.pattern("Plain", 1, 1)
    return SM.apply_gravity_state(cfg, model, *a, self_weight=False, **kw)


def test_roof_levels_are_roofs():
    import static_model as SM
    import india_loads as IL
    cfg, _ = ex1_cfg_is()
    cfg["snow"] = 1.2
    assert SM.floor_pressures(cfg, 2) == (cfg["D_floor"], cfg["L_floor"] + cfg["partition_load_kNm2"], 0.0, 0.0)
    cfg["roof_levels"] = [2]
    assert IL.roof_level_set(cfg) == {2, 5}
    assert SM.floor_pressures(cfg, 2) == (cfg["D_roof"], 0.0, cfg["Lr"], 1.2)      # no partitions, snow on it
    lev = _state(cfg, 0.0, 0.0, 0.0, fS=1.0)
    assert lev[2] == pytest.approx(lev[5], rel=1e-9) and lev[2] > 0 and lev[3] == 0.0


def test_partial_snow_split_at_declared_ridge():
    cfg, _ = ex1_cfg_is()
    cfg["clad"] = 0.0
    cfg["snow"] = 1.0
    cfg["deck_span"] = None                        # two-way: tributary follows the plan exactly
    NF = len(cfg["heights"])
    full = _state(cfg, 0.0, 0.0, 0.0, fS=1.0)[NF]
    cfg["snow_partial"] = {"axis": "X", "ridge_mm": 9000.0}          # mid-bay: no grid line on the ridge
    lo = _state(cfg, 0.0, 0.0, 0.0, fS=1.0, snow_pattern=("X", "lo"))[NF]
    hi = _state(cfg, 0.0, 0.0, 0.0, fS=1.0, snow_pattern=("X", "hi"))[NF]
    Lx = cfg["NX"] * cfg["SX"]
    assert lo + hi == pytest.approx(full, rel=1e-9)
    assert lo == pytest.approx(full * 9000.0 / Lx, rel=0.10)          # sub-segment resolution (nseg 2)
    cfg["snow_partial"] = {"axis": "X"}                               # default: plan mid-line
    assert _state(cfg, 0.0, 0.0, 0.0, fS=1.0, snow_pattern=("X", "lo"))[NF] == pytest.approx(0.5 * full, rel=0.02)


def test_nodal_imposed_loads_factored_by_fL_or_fLr():
    import engine3d as E
    cfg, _ = ex1_cfg_is()
    cfg["nodal_imposed_loads"] = [{"node": E.ntag(0, 0, 2), "Fz_N": -10000.0, "kind": "floor"},
                                  {"node": E.ntag(0, 0, 5), "Fz_N": -10000.0, "kind": "roof", "level": 5}]
    lev = _state(cfg, 0.0, 1.5, 1.5)
    base = _state(dict(cfg, nodal_imposed_loads=[]), 0.0, 1.5, 1.5)
    assert lev[2] - base[2] == pytest.approx(15000.0) and lev[5] - base[5] == pytest.approx(15000.0)
    snow_row = _state(cfg, 0.0, 1.5, 0.0, fS=1.5)            # 1.5DL+1.5LL+1.5SL: roof imposed replaced by snow
    base_s = _state(dict(cfg, nodal_imposed_loads=[]), 0.0, 1.5, 0.0, fS=1.5)
    assert snow_row[5] - base_s[5] == pytest.approx(0.0) and snow_row[2] - base_s[2] == pytest.approx(15000.0)
