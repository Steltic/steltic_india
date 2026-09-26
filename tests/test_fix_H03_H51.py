"""H03 (CFS-B-10, CFS-C-08, CFS-D-02) and H51 (HR-E-20, HR-D-17), ruling R9: torsional / translational mode
identification, Table 5(i) ratio from lateral displacements only, drift for +F and -F, modes counted recorded."""
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "steel_engine"))

import india_seismic as IS

PROBE = [{"mode": 1, "T": 0.635, "mass_x": 0.02, "mass_y": 0.01, "rot": 0.957},
         {"mode": 2, "T": 0.602, "mass_x": 0.80, "mass_y": 0.00, "rot": 0.01},
         {"mode": 3, "T": 0.510, "mass_x": 0.00, "mass_y": 0.78, "rot": 0.02},
         {"mode": 4, "T": 0.093, "mass_x": 0.00, "mass_y": 0.00, "rot": 0.99}]


def test_torsional_mode_is_longest_period_rotation_dominant():
    r = IS.torsional_period_ok(PROBE)
    assert r["ok"] is False and r["T_torsion"] == pytest.approx(0.635)
    assert (r["mode_torsional"], r["mode_Tx"], r["mode_Ty"]) == (1, 2, 3)
    assert "R9" in r["rule"]


def test_tx_ty_from_distinct_modes():
    # a coupled mode with the largest X and Y mass is X-dominant only; Ty comes from another mode
    modes = [{"T": 1.0, "mass_x": 0.5, "mass_y": 0.4, "rot": 0.05},
             {"T": 0.9, "mass_x": 0.2, "mass_y": 0.3, "rot": 0.1},
             {"T": 0.5, "mass_x": 0.0, "mass_y": 0.0, "rot": 0.9}]
    r = IS.torsional_period_ok(modes)
    assert r["mode_Tx"] == 1 and r["mode_Ty"] == 2 and r["ok"] is True


def test_modes_screen_records_counted_modes():
    r = IS.modes_screen(PROBE, "IV")
    assert r["modes_counted"] == [2, 3]                  # modes 1 and 4 are rotation-dominant
    assert r["modes_excluded_rotation_dominant"] == [1, 4]
    assert (r["mode_Tx"], r["mode_Ty"]) == (2, 3) and "R9" in r["rule"]


def _leaning_cfg():
    import engine3d as E
    import example_build as EB

    class _P:
        def __init__(s, real):
            s.real = real

        def __getattr__(s, n):
            return getattr(s.real, n)

        def node(s, tag, x, y, z, *a):                 # corner column (0,0) leans 2 m in Y -> gravity sway + twist
            if tag == E.ntag(0, 0, 0):
                y -= 2000.0
            return s.real.node(tag, x, y, z, *a)

    def cb(cfg, transf):
        real = EB.ops
        EB.ops = _P(real)
        try:
            return EB.example_build(cfg, transf)
        finally:
            EB.ops = real
    return {"NX": 2, "NY": 2, "SX": 6000.0, "SY": 6000.0, "heights": [4000.0], "base": "pinned",
            "col": "WPB300X300X100.85", "beam": "NPB450X190X67.16", "units": "N-mm", "jurisdiction": "india",
            "D_floor": 6.0, "D_roof": 8.0, "L_floor": 5.0, "Lr": 1.5, "clad": 0.0, "self_weight": False,
            "custom_build": cb,
            "load_plan": {"jurisdiction": "india", "story_forces_units": "N",
                          "story_forces": {"EQ_X": {"1": [5e4, 0, 0]}, "EQ_Y": {"1": [0, 5e4, 0]}}}}


def test_torsion_ratio_from_lateral_displacement_and_two_signs():
    pytest.importorskip("openseespy.opensees")
    import engine3d as E
    import india_units as IU
    IU.activate_si()
    cfg = _leaning_cfg()
    a = E.india_drift(cfg, {"X": {}, "Y": {}})
    b = E.india_drift(cfg, {"X": {}, "Y": {}}, gravity=(0.0, 0.0))
    for d in ("X", "Y"):
        # old code: 1.72 (X) / 1.54 (Y) from total displacements; lateral-only ratio ~1.11
        assert a[d]["ratio"][0] == pytest.approx(b[d]["ratio"][0], rel=0.01)
        assert "lateral displacements only" in a[d]["ratio_basis"]
    # -F governs the X drift of this frame (gravity sway adds to it); +F alone gave 0.00346
    assert a["X"]["sign"] == "-F" and a["X"]["drift"][0] > 0.0037
