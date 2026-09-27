"""H49 (HR-D-15, NEW-4): flexible-diaphragm line shears use each level's own footprint as the mass extent (no
half-bay padding, not level 1 for every level); collector rows keep the flexible 7.6.4 cite."""
import pytest

from _ex1_fixture import ex1_cfg_is


def test_flexible_extent_per_level_and_cite():
    pytest.importorskip("openseespy.opensees")
    import india_diaphragm as D
    cfg, _ = ex1_cfg_is()
    cfg["diaphragm"] = "flexible"
    ls = D.flexible_diaphragm_line_shears(cfg, "EQ")
    ext = ls["mass_extent_mm"][1]
    assert ext["X"] == [0.0, 24000.0] and ext["Y"] == [0.0, 30000.0]         # Ex1 30 x 24 m, no +/- half bay
    # 3-line check by hand: lines at 0 and 24 m, mass 0-24 m -> each line half; +0.05 b = 1.2 m shift
    shx = ls["ea"]["X"][1]
    f = sum(ls["e0"]["X"][1].values())
    assert shx[24000.0] == pytest.approx(f * (12000.0 + 1200.0) / 24000.0, rel=1e-9)
    rows = D.collector_demands(cfg)
    assert rows and all("flexible" in r["cite"] or "tributary" in r["cite"] for r in rows if r.get("kind") == "EQ")


def test_setback_level_uses_its_own_extent():
    pytest.importorskip("openseespy.opensees")
    import india_diaphragm as D
    import india_units as IU
    IU.activate_si()
    full = [(i, j) for i in range(3) for j in range(2)]
    top = [(i, j) for i in range(2) for j in range(2)]
    cfg = {"NX": 2, "NY": 1, "SX": 6000.0, "SY": 6000.0, "heights": [4000.0, 4000.0], "base": "fixed",
           "col": "WPB300X300X100.85", "beam": "NPB450X190X67.16", "units": "N-mm", "jurisdiction": "india",
           "D_floor": 3.0, "D_roof": 2.0, "L_floor": 2.5, "Lr": 0.75, "clad": 0.0, "self_weight": False,
           "diaphragm": "flexible", "present": {0: full, 1: full, 2: top},
           "lateral_lines": {"X": [0.0, 6000.0], "Y": [0.0, 6000.0, 12000.0]},
           "load_plan": {"jurisdiction": "india", "story_forces_units": "N",
                         "story_forces": {"EQ_X": {"1": [1e5, 0, 0], "2": [1e5, 0, 0]},
                                          "EQ_Y": {"1": [0, 1e5, 0], "2": [0, 1e5, 0]}}}}
    ls = D.flexible_diaphragm_line_shears(cfg, "EQ")
    assert ls["mass_extent_mm"][1]["Y"] == [0.0, 12000.0] and ls["mass_extent_mm"][2]["Y"] == [0.0, 6000.0]
    sh2 = ls["e0"]["Y"][2]
    # level 2 spans 0-6 m: lines at 0 and 6 m take half each, the 12 m line (outside the setback floor) nothing
    assert sh2[0.0] == pytest.approx(5e4) and sh2[6000.0] == pytest.approx(5e4) and sh2[12000.0] == pytest.approx(0.0)
