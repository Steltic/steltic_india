"""H17 (CFS-C-09): IS 875-2 3.2.1 imposed-load reduction is never applied in combinations with earthquake
(IS 875 (Part 5):1987 8.1: "Reduced imposed load (IL) specified in Part 2 ... should not be applied in combination
with earthquake forces")."""
import pytest

from _ex1_fixture import ex1_cfg_is


def test_no_imposed_load_reduction_in_eq_cases():
    pytest.importorskip("openseespy.opensees")
    import engine3d as E
    import india_loads as IL
    import static_model as SM
    cfg, _ = ex1_cfg_is()
    plan = cfg["load_plan"]
    grav = {"label": "grav", "fD": 1.2, "fL": 1.2, "fLr": 0.0}
    eq = {"label": "eq", "fD": 1.2, "fL": 1.2, "fLr": 0.0, "fE": 1.0,
          "lateral": {"1": [0.0, 0.0, 0.0]}, "direction": "X"}
    cases = [IL.case_from_combination(grav, plan), IL.case_from_combination(eq, plan)]
    assert cases[1].meta["kind"] == "EQ"
    pc0, _, _ = SM.solve_cases_si(cfg, cases, nseg=2)
    cfg_r = dict(cfg, column_imposed_load_reduction=True)
    pc1, _, _ = SM.solve_cases_si(cfg_r, cases, nseg=2)
    col = frozenset((E.ntag(0, 0, 0), E.ntag(0, 0, 1)))       # ground-storey column carries 5 floors (40 %)
    # gravity-only case: reduced (less compression, tension-positive records)
    assert pc1["grav"][col][0] > pc0["grav"][col][0] + 1.0
    # earthquake case: unreduced
    assert pc1["eq"][col][0] == pytest.approx(pc0["eq"][col][0], rel=1e-9, abs=1e-6)
