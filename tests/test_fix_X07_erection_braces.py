"""X07 (HR-C-19): optional erection sequence -- braces connected after the dead load.

Two-storey, one-bay X-braced frame (braces on grid line j = 0, rigid diaphragms).  Hand check for the default model
(braces present for the dead load): under symmetric gravity the storeys do not sway, so a diagonal of storey s
shortens by (h / Ld) x the column shortening delta_s = N_col h / (E A_c) and carries
    N_brace = E A_b (h / Ld) delta_s / Ld  =>  N_brace / N_col = (A_b / A_c) (h / Ld)^2 .
With cfg['braces_after_dead_load'] the 1.5DL part of that brace force disappears (the dead load is carried by the
columns alone, braces removed), the 1.5LL part is unchanged, and every lateral increment is unchanged."""
import math
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(__file__))
import _ex1_fixture  # noqa: E402,F401  (engine path)

H = 3500.0


@pytest.fixture(autouse=True)
def _units():
    import engine3d as E
    was = E.unit_system()
    yield
    (E.activate_si_units if was == "N-mm" else E.activate_kip_in_units)()
S = 6000.0


def _cfg(**kw):
    import engine3d as E
    E.activate_si_units()
    c = {"jurisdiction": "india", "NX": 1, "NY": 1, "SX": S, "SY": S, "heights": [H, H], "col": "HB250",
         "beam": "HB300", "brace": "HB150", "braces": lambda k, NX, NY: [("X", 0, 0)], "base": "fixed",
         "D_floor": 4.0, "D_roof": 3.0, "L_floor": 3.0, "Lr": 1.5, "snow": 0.0, "clad": 0.0,
         "self_weight": False}
    c.update(kw)
    return c


def _cases():
    import india_loads as IL
    plan = {"story_forces_units": "N"}
    lat = {"1": [60e3, 0.0, 0.0], "2": [90e3, 0.0, 0.0]}
    rows = [{"label": "1.5DL+1.5LL", "fD": 1.5, "fL": 1.5, "fLr": 1.5},
            {"label": "1.5DL", "fD": 1.5, "fL": 0.0, "fLr": 0.0},
            {"label": "1.5DL+1.5W_X", "fD": 1.5, "fL": 0.0, "fLr": 0.0, "fW": 1.5, "lateral": lat,
             "direction": "X"}]
    return [IL.case_from_combination(r, plan) for r in rows]


def _solve(cfg):
    pytest.importorskip("openseespy.opensees")
    import static_model as SM
    return SM.solve_cases_si(cfg, _cases(), nseg=4)


def _members(cfg):
    import engine3d as E
    br = {s: [] for s in (1, 2)}
    for k in (1, 2):
        br[k] = [frozenset((E.ntag(0, 0, k - 1), E.ntag(1, 0, k))), frozenset((E.ntag(0, 0, k), E.ntag(1, 0, k - 1)))]
    col = {k: frozenset((E.ntag(0, 0, k - 1), E.ntag(0, 0, k))) for k in (1, 2)}
    return br, col


def test_default_brace_gravity_share_hand_check():
    import engine3d as E
    cfg = _cfg()
    pc, _, info = _solve(cfg)
    assert "erection" not in info
    br, col = _members(cfg)
    Ab, Ac = E.Ipack("HB150")[0], E.Ipack("HB250")[0]
    Ld = math.hypot(S, H)
    ratio = (Ab / Ac) * (H / Ld) ** 2
    for k in (1, 2):
        Nb = pc["1.5DL"][br[k][0]][0]
        Nc = pc["1.5DL"][col[k]][0]
        assert Nb < 0 and Nc < 0                                   # compression (tension-positive records)
        assert Nb == pytest.approx(pc["1.5DL"][br[k][1]][0], rel=1e-6)
        assert Nb / Nc == pytest.approx(ratio, rel=0.02)


def test_braces_after_dead_load():
    cfg0, cfg1 = _cfg(), _cfg(braces_after_dead_load=True)
    pc0, _, _ = _solve(cfg0)
    pc1, _, info = _solve(cfg1)
    br, col = _members(cfg0)
    er = info["erection"]
    assert er["braces_after_dead_load"] is True and er["verify"] is True and "3.3" in er["cite"]
    assert {s["fD"] for s in er["states"]} == {1.5} and len(er["states"][0]["braces_released"]) == 4
    Ld = math.hypot(S, H)
    for k in (1, 2):
        for b in br[k]:
            # dead load alone: no brace force
            assert abs(pc1["1.5DL"][b][0]) < 1e-6 * abs(pc0["1.5DL"][b][0])
            # 1.5DL+1.5LL: the brace force drops by exactly the 1.5DL share (the LL part is unchanged)
            assert pc1["1.5DL+1.5LL"][b][0] == pytest.approx(pc0["1.5DL+1.5LL"][b][0] - pc0["1.5DL"][b][0], rel=1e-4)
            assert abs(pc1["1.5DL+1.5LL"][b][0]) < abs(pc0["1.5DL+1.5LL"][b][0])
        # the column takes the brace's vertical component back (vertical equilibrium of the storey)
        Nb0 = pc0["1.5DL"][br[k][0]][0]
        assert pc1["1.5DL"][col[k]][0] == pytest.approx(pc0["1.5DL"][col[k]][0] + Nb0 * H / Ld, rel=1e-3)
    # lateral results unchanged: the lateral increment of every member and the N_LAT field
    lab = "1.5DL+1.5W_X"
    for fs in pc0[lab]:
        r0, r1 = pc0[lab][fs], pc1[lab][fs]
        g0, g1 = pc0["1.5DL"][fs], pc1["1.5DL"][fs]
        assert r1[11] == pytest.approx(r0[11], rel=1e-9, abs=1e-6)                  # N_LAT
        assert r1[0] - g1[0] == pytest.approx(r0[0] - g0[0], rel=1e-6, abs=1e-3)   # lateral axial increment
    assert abs(pc0[lab][br[1][0]][11]) > 1e3                                        # braces do carry the wind


def test_flag_false_and_unmatched_selector_unchanged():
    pc0, _, _ = _solve(_cfg())
    pcF, _, infoF = _solve(_cfg(braces_after_dead_load=False))
    pcS, _, infoS = _solve(_cfg(braces_after_dead_load=["Y"]))      # no Y-direction braces in this frame
    assert "erection" not in infoF and infoS["erection"]["states"][0]["braces_released"] == []
    for lab in pc0:
        for fs in pc0[lab]:
            assert pcF[lab][fs] == pc0[lab][fs]
            assert pcS[lab][fs] == pc0[lab][fs]
    pcV, _, infoV = _solve(_cfg(braces_after_dead_load=["vertical"]))
    assert len(infoV["erection"]["states"][0]["braces_released"]) == 4


def test_superimposed_dead_after_braces():
    """With 1.0 of the 4.0 / 3.0 kN/m2 dead declared superimposed, only 3.0 / 2.0 go in before the braces: the brace keeps
    the superimposed share; braces_after_superimposed_dead puts it back before the braces."""
    import static_model as SM
    sdl = {"floor": 1.0, "roof": 1.0}
    c_all = _cfg(braces_after_dead_load=True)
    c_sdl = _cfg(braces_after_dead_load=True, superimposed_dead_kNm2=sdl)
    c_sdl2 = _cfg(braces_after_dead_load=True, superimposed_dead_kNm2=sdl, braces_after_superimposed_dead=True)
    pcA, _, _ = _solve(c_all)
    pcB, _, iB = _solve(c_sdl)
    pcC, _, _ = _solve(c_sdl2)
    pc0, _, _ = _solve(_cfg())
    br, _ = _members(c_all)
    b = br[1][0]
    assert abs(pcA["1.5DL"][b][0]) < 1e-3
    assert pcC["1.5DL"][b][0] == pytest.approx(pcA["1.5DL"][b][0], abs=1e-3)
    # superimposed share: floor 1.0 of 4.0, roof 1.0 of 3.0 -> between 1/4 and 1/3 of the default dead-load brace force
    share = pcB["1.5DL"][b][0] / pc0["1.5DL"][b][0]
    assert 0.25 - 1e-3 < share < 1.0 / 3.0 + 1e-3
    assert "superimposed" in iB["erection"]["pre_brace_loads"]
    with pytest.raises(ValueError):
        SM.erection_pre_brace_cfg(_cfg(superimposed_dead_kNm2=5.0))


def test_unstable_frame_without_braces_is_held_laterally(monkeypatch):
    """When the frame without the released braces cannot carry the dead load on its own (the unrestrained solve fails),
    the pre-brace dead state is solved with the storeys held at the diaphragm masters (temporary erection bracing,
    IS 800 3.3); the brace force result is the same for this symmetric frame (no sway either way)."""
    import static_model as SM
    pc0, _, _ = _solve(_cfg())
    real = SM._solve_newton
    calls = {"n": 0}

    def fake():
        calls["n"] += 1
        return -3 if calls["n"] == 2 else real()        # call 1: full model; call 2: first no-brace attempt
    monkeypatch.setattr(SM, "_solve_newton", fake)
    pc1, _, info = SM.solve_cases_si(_cfg(braces_after_dead_load=True), _cases(), nseg=4)
    st = info["erection"]["states"][0]
    assert st["temporary_lateral_restraint"] is True and "3.3" in st["note"]
    assert st["temporary_restraint_max_N"] < 1.0
    br, col = _members(_cfg())
    for k in (1, 2):
        b = br[k][0]
        assert abs(pc1["1.5DL"][b][0]) < 1e-6 * abs(pc0["1.5DL"][b][0])
        assert pc1["1.5DL+1.5LL"][b][0] == pytest.approx(pc0["1.5DL+1.5LL"][b][0] - pc0["1.5DL"][b][0], rel=1e-4)
