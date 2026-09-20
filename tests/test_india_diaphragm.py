"""WP2.6 -- collector / chord axial from the diaphragm load path (rigid diaphragm gives beams P = 0)."""
import inspect

import pytest

from _ex1_fixture import ex1_cfg_is

import india_diaphragm as D


@pytest.fixture(scope="module")
def ex1():
    cfg, _ = ex1_cfg_is()
    return cfg, D.collector_forces(cfg, "EQ")


def test_chord_force_matches_simple_span_diaphragm(ex1):
    cfg, cf = ex1
    import engine3d as E
    F4 = E.india_story_forces(cfg, "Y")[4][1]
    L = 5 * 6000.0                                    # diaphragm span along X between the Y-braced end lines
    B = 4 * 6000.0
    ch = [r for r in cf["rows"] if r["role"] == "chord" and r["dir"] == "Y" and r["level"] == 4]
    Mmax = max(abs(r["M_diaphragm_Nmm"]) for r in ch)
    assert Mmax == pytest.approx(F4 * L / 8.0, rel=0.10)
    assert max(abs(r["N_N"]) for r in ch) == pytest.approx(Mmax / B, rel=1e-6)


def test_collector_rows_exist_on_braced_lines(ex1):
    _, cf = ex1
    col = [r for r in cf["rows"] if r["role"] == "collector"]
    assert col and max(abs(r["N_N"]) for r in col) > 1e3
    # line shares at a level add up to the level force (rigid diaphragm equilibrium)
    import engine3d as E
    cfg = ex1[0]
    F = E.india_story_forces(cfg, "X")
    shares = {}
    for r in col:
        if r["dir"] == "X":
            shares.setdefault(r["level"], {})[r["line"]] = r["R_line_N"]
    for k, s in shares.items():
        assert sum(s.values()) <= F[k][0] * 1.01


def test_records_get_axial_only_in_lateral_cases(ex1):
    cfg, _ = ex1
    import engine3d as E
    import india_loads as IL
    plan = cfg["load_plan"]
    grav = IL.case_from_combination({"label": "G", "fD": 1.5, "fL": 1.5, "fLr": 1.5}, plan)
    lat = IL.case_from_combination({"label": "L", "fD": 1.2, "fL": 1.2, "fLr": 1.2, "lateral_ref": "EQ_Y",
                                    "fE": 1.2}, plan)
    info = E.build(cfg, "PDelta")
    reg = {t: (k, s, a, b) for (t, k, s, a, b) in info["ele"]}
    beams = [frozenset((a, b)) for t, (k, s, a, b) in reg.items() if k == "beam"]
    per_case = {"G": {fs: (0.0,) * 11 for fs in beams}, "L": {fs: (0.0,) * 11 for fs in beams}}
    added = D.add_to_records(per_case, [grav, lat], reg, cfg)
    assert added
    assert all(r[0] == 0.0 for r in per_case["G"].values())
    assert max(abs(r[0]) for r in per_case["L"].values()) == pytest.approx(1.2 * max(added.values()) / 1.2, rel=1e-9)


def test_flexible_diaphragm_tributary_path():
    """IS 1893 7.6.4: a flexible diaphragm is no longer refused -- the storey shear goes to the braced lines by
    tributary width and the collectors carry the line shear; semi-rigid shells are still an EOR input."""
    cfg, _ = ex1_cfg_is()
    cfg["diaphragm"] = "flexible"
    cf = D.collector_forces(cfg, "EQ")
    assert cf.get("diaphragm") == "flexible" and cf["rows"]
    ls = D.flexible_diaphragm_line_shears(cfg, "EQ")
    for d in ("X", "Y"):
        assert len(ls["lines"][d]) == 2                     # perimeter braced lines of Ex1
        for k, sh in ls["e0"][d].items():
            assert abs(sum(sh.values())) > 0
            assert sh[min(sh)] == pytest.approx(sh[max(sh)], rel=1e-6)   # symmetric plan: equal shares
        ea = ls["ea"][d][1]
        assert ea[max(ea)] > ea[min(ea)]                      # +0.05 b mass shift loads the far line more
    assert not any("error" in r for r in D.collector_demands(cfg))
    cfg["diaphragm"] = "semi-rigid"
    with pytest.raises(D.DiaphragmError):
        D.collector_forces(cfg, "EQ")
