"""H02: V-bar_B is computed by the engine per direction (IS 1893 6.4.2, 7.6.1, 7.6.2, Table 7) and the larger of
the engine and agent values is used; preflight ERROR when the agent value is more than 2 % below the engine value."""
import copy

import pytest

from _ex1_fixture import ex1_cfg_is


@pytest.fixture(scope="module")
def base():
    pytest.importorskip("openseespy.opensees")
    import engine3d as E
    cfg, _ = ex1_cfg_is()
    E.build(cfg, "Linear")
    return cfg


def _errs(cfg):
    import preflight as PF
    return [m for s, m in PF.india_checks(cfg) if s == "ERROR"]


def test_engine_VBbar_matches_ESM_hand_value(base):
    import engine3d as E
    import india_seismic as IS
    ss = base["load_plan"]["seismic_summary"]
    for d in ("X", "Y"):
        r = E.VBbar_record(base, d)
        Ah = max(0.24 / 2 * 1.2 / 4.5 * IS.sa_over_g(ss["Ta_%s_s" % d.lower()], "II", "ESM"), 0.016)
        assert r["Ah"] == pytest.approx(Ah, rel=1e-9)
        assert r["engine_N"] == pytest.approx(Ah * r["W_used_N"], rel=1e-9)
        assert r["engine_N"] / 1e3 == pytest.approx(ss["VB_%s_kN" % d.lower()], rel=0.005)
    assert not [m for m in _errs(base) if "V-bar" in m or "7.7.3" in m]


def test_low_agent_VB_is_raised_and_flagged(base):
    import engine3d as E
    cfg = copy.deepcopy(base)
    ss = cfg["load_plan"]["seismic_summary"]
    eng = E.VBbar_record(cfg, "X")["engine_N"]
    ss["VB_x_kN"] = 0.79 * eng / 1e3                          # Model 3 Ex9: X designed 21 % low
    assert E.VBbar(cfg, "X") == pytest.approx(eng)            # max(engine, agent)
    assert E.VBbar_record(cfg, "X")["basis"] == "engine"
    assert any("VB_x_kN" in m and "7.7.3" in m for m in _errs(cfg))


def test_single_VB_checked_against_both_directions(base):
    import engine3d as E
    cfg = copy.deepcopy(base)
    ss = cfg["load_plan"]["seismic_summary"]
    ss["Ta_x_s"], ss["Ta_y_s"] = 0.9, 0.5                     # Sa/g differs by direction
    vx, vy = (E.VBbar_record(cfg, d)["engine_N"] for d in ("X", "Y"))
    assert vy > vx * 1.05
    ss.pop("VB_x_kN"); ss.pop("VB_y_kN")
    ss["VB_kN"] = vx / 1e3                                    # right for X, low for Y
    msgs = [m for m in _errs(cfg) if "7.7.3" in m]
    assert any("VB_y" in m for m in msgs) and not any("VB_x" in m for m in msgs)
