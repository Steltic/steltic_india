"""WP1.1 -- lateral load factors (fE / fW) are applied; no silent 1.0."""
import copy
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tests"))
sys.path.insert(0, str(ROOT / "steel_engine"))
pytest.importorskip("openseespy.opensees")

import india_loads as IL


def _sum_rx(cfg, label):
    import openseespy.opensees as ops
    import engine3d as E
    import static_model as SM
    plan = cfg["load_plan"]
    combo = [c for c in plan["combinations"] if c["label"] == label][0]
    case = IL.case_from_combination(combo, plan)
    model = SM.build_static(cfg, "PDelta", 2)
    ops.timeSeries("Linear", 1); ops.pattern("Plain", 1, 1)
    SM.apply_lateral(case[4]); SM._solve(); ops.reactions()
    return -sum(ops.nodeReaction(E.ntag(i, j, 0), 1) for (i, j) in model["present"][0]) / 1000.0


def test_ex1_lateral_factor_applied():
    from _ex1_fixture import ex1_cfg
    cfg, seis = ex1_cfg()
    assert abs(seis["VB_kN"] - 984.72) < 0.05
    assert abs(_sum_rx(cfg, "1.5DL+1.5EQ_X") - 1477.1) < 0.1
    assert abs(_sum_rx(cfg, "1.2DL+1.2LL+1.2EQ_X") - 1181.7) < 0.1


def test_missing_factor_raises():
    from _ex1_fixture import ex1_cfg
    cfg, _ = ex1_cfg(upgrade=False)
    cfg["load_plan"]["story_forces_units"] = "N"
    errs = [m for s, m in IL.validate_load_plan(cfg) if s == "ERROR"]
    assert any("no lateral load factor" in m for m in errs)
    with pytest.raises(IL.LoadPlanError):
        IL.cases_from_load_plan(cfg)
    with pytest.raises(IL.LoadPlanError):
        IL.case_from_combination([c for c in cfg["load_plan"]["combinations"] if c.get("lateral_ref")][0],
                                 cfg["load_plan"])


def test_label_disagreement_and_units_required():
    from _ex1_fixture import ex1_cfg
    cfg, _ = ex1_cfg()
    c = [c for c in cfg["load_plan"]["combinations"] if c["label"] == "1.5DL+1.5EQ_X"][0]
    c["fE"] = 1.0
    assert any("disagrees with the label" in m for s, m in IL.validate_load_plan(cfg) if s == "ERROR")
    c["fE"] = 1.5
    cfg["load_plan"].pop("story_forces_units")
    assert any("story_forces_units" in m for s, m in IL.validate_load_plan(cfg) if s == "ERROR")


def test_kN_story_forces_converted():
    plan = {"story_forces_units": "kN", "story_forces": {"EQ_X": {"1": [10.0, 0, 0]}}}
    case = IL.case_from_combination({"label": "1.5DL+1.5EQ_X", "fD": 1.5, "fL": 0, "fLr": 0, "fE": 1.5,
                                     "lateral_ref": "EQ_X"}, plan)
    assert case[4][1][0] == pytest.approx(15000.0)
    assert case.meta["fLat"] == 1.5 and case.meta["kind"] == "EQ"


def test_not_table4_set_rejected():
    errs = IL.validate_table4([{"label": "1.2DL+1.2EQ_X", "fD": 1.2, "fL": 0.0, "fE": 1.2}])
    assert errs and "Table 4" in errs[0][1]
