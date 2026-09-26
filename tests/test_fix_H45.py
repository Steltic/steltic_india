"""H45 multi-unit jobs (HR-C-06, HR-D-13): figure names for units/<unit> job names; 7.11.3 D1 at the matching
level when same_floor_levels."""
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "steel_engine"))
sys.path.insert(0, str(ROOT / "tests"))


def test_fig_stem_and_title():
    import plot_model as PM
    assert PM.fig_stem("job/units/workshop") == "job__units__workshop"
    assert PM.fig_stem("B02") == "B02"
    assert PM.title_name("job/units/workshop") == "workshop"


def test_unit_figures_written(tmp_path):
    import engine3d as E
    import plot_model as PM
    from _ex1_fixture import ex1_cfg
    cfg, _ = ex1_cfg()
    name = "IN_H45/units/workshop"
    E.CFG[name] = cfg
    out = tmp_path / "figs"
    paths = PM.figures(name, str(out), deformed_fig=False)
    assert len(paths) == 2
    for p in paths:
        assert os.path.dirname(p) == str(out) and os.path.exists(p)
        assert os.path.basename(p).startswith("IN_H45__units__workshop_")


def test_separation_D1_matching_level():
    import design_pipeline as DP
    dm = [5.0, 11.0, 18.0, 24.0]
    D1, basis, lev = DP._separation_D1({"same_floor_levels": True, "level": 2}, dm)
    assert D1 == 11.0 and lev == 2 and "level 2" in basis
    D1, _, lev = DP._separation_D1({"same_floor_levels": True, "n_levels": 3}, dm)
    assert D1 == 18.0 and lev == 3
    D1, basis, lev = DP._separation_D1({"same_floor_levels": True}, dm)
    assert D1 == 24.0 and lev is None and "declare" in basis
    assert DP._separation_D1({"level": 2}, dm)[0] == 24.0          # R x (D1 + D2): max displacement


def test_separation_record_uses_matching_level():
    import design_pipeline as DP
    run = {"drift": {"X": {"disp_max": [5.0, 11.0, 18.0, 24.0]}}}
    cfg = {"adjacent_units": [{"id": "B", "direction": "X", "same_floor_levels": True, "level": 2,
                               "delta2_mm": 9.0, "R2": 4.5, "gap_mm": 100.0}]}
    out = {}
    DP._separation_7_11_3(cfg, run, 4.5, out)
    r = out["separation"][0]
    assert r["D1_mm"] == 11.0 and r["level"] == 2
    assert abs(r["value"] - (4.5 * 11.0 + 4.5 * 9.0) / 2.0) < 1e-9
