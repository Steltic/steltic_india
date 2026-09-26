"""IN-X01-LEVEL (gold issue IN_CFS_Ex9): cfg['diaphragm_stiffness'] per level for the IS 1893 Table 5(ii) (Amd 2)
flexible-floor-diaphragm run -- each floor diaphragm with its own flexibility (e.g. a composite podium under light CFS
floors).  Forms: {'by_level': {k | 'a-b': rec}, 'default': rec}, top-level record + by_level, or a list per level.

Hand check (closed form, as test_fix_X01.test_membrane_hand_check_long_diaphragm): two storeys, 4 x 1 bays of 6 m,
pinned beams, light pinned-base columns, stiff Y braces in the two end frames only; a uniform Y load on ONE level makes
that deck a simply supported beam between the end frames:
    delta_mid = 5 w L^4 / (384 EI) + w L^2 / (8 Gd B),  EI = Es A_chord 2 (B/2)^2 + Et B^3 / 12,
with Gd of THAT level.  Level 1 stiff (Gd 200,000 N/mm), level 2 soft (5,000 N/mm)."""
import os
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "steel_engine"))

import india_flexible_diaphragm as FD  # noqa: E402

SOFT = {"type": "custom", "Gd_kN_per_m": 5000.0, "source": "EOR: screwed sheet + board deck (test value)"}
STIFF = {"type": "custom", "Gd_kN_per_m": 200000.0, "source": "EOR: composite podium slab (test value)"}


def _cfg(ds, NF=2):
    return {"NX": 4, "NY": 1, "SX": 6000.0, "SY": 6000.0, "heights": [4000.0] * NF, "base": "pinned",
            "col": "MB100", "beam": "NPB450X190X67.16", "brace": "WPB300X300X100.85",
            "braces": lambda k, NX, NY: [("Y", 0, 0), ("Y", NX, 0)], "releases": lambda i, j, k, d: ("both", "none"),
            "units": "N-mm", "jurisdiction": "india", "D_floor": 4.0, "D_roof": 4.0, "L_floor": 0.0, "Lr": 0.0,
            "clad": 0.0, "self_weight": False, "diaphragm_stiffness": ds}


def test_forms_and_errors():
    one, err = FD.diaphragm_stiffness(_cfg(SOFT))
    assert err is None and "by_level" not in one and one["Gt_N_per_mm"] == 5000.0          # original form unchanged
    for ds in ({"by_level": {1: STIFF, 2: SOFT}}, [STIFF, SOFT], {"by_level": {"2": SOFT}, "default": STIFF},
               dict(STIFF, by_level={"2-2": SOFT})):
        rec, err = FD.diaphragm_stiffness(_cfg(ds))
        assert err is None, err
        assert rec["per_level"] is True and rec["mesh"] == 2
        assert FD.level_stiffness(rec, 1)["Gt_N_per_mm"] == 200000.0
        assert FD.level_stiffness(rec, 2)["Gt_N_per_mm"] == 5000.0
        assert "1: " in rec["basis"] and "2: " in rec["basis"]
    rec, _ = FD.diaphragm_stiffness(_cfg({"by_level": {"1-3": SOFT}, "default": STIFF}, NF=4))
    assert [FD.level_stiffness(rec, k)["Gt_N_per_mm"] for k in (1, 2, 3, 4)] == [5000.0] * 3 + [200000.0]
    # never a silent value: uncovered level, bad key, wrong list length, per-level source missing, mesh clash
    for ds, frag in (({"by_level": {2: SOFT}}, "does not cover level(s) [1]"),
                     ({"by_level": {3: SOFT}, "default": SOFT}, "key 3"),
                     ([SOFT], "1 records for 2"),
                     ({"by_level": {1: dict(SOFT, source=""), 2: SOFT}}, "by_level[1].source missing"),
                     ({"by_level": {1: dict(SOFT, mesh=1), 2: SOFT}}, "global mesh"),
                     ({"by_level": {1: SOFT, 2: SOFT, "1-2": SOFT}}, "twice")):
        rec, err = FD.diaphragm_stiffness(_cfg(ds))
        assert rec is None and err.startswith("ERROR") and frag in err, (ds, err)


@pytest.fixture(scope="module")
def eng():
    pytest.importorskip("openseespy.opensees")
    import engine3d as E
    import india_units as IU
    IU.activate_si()
    return E


def _mid_deflection(E, ds, lev):
    import openseespy.opensees as ops
    m = FD.build_flexible(_cfg(ds), "Linear", 2)
    F = 1.0e5
    loads = FD._lateral_loads(FD._level_fields(m)[lev], (0.0, F), 0.0)
    ops.timeSeries("Linear", 1); ops.pattern("Plain", 1, 1)
    for t, (fx, fy) in loads.items():
        ops.load(t, fx, fy, 0.0, 0.0, 0.0, 0.0)
    ops.constraints("Transformation"); ops.numberer("RCM"); ops.system("UmfPack")
    ops.test("NormDispIncr", 1e-9, 10); ops.algorithm("Linear"); ops.integrator("LoadControl", 1.0)
    ops.analysis("Static")
    assert ops.analyze(1) == 0
    out = {}
    for k in (1, 2):
        uy = lambda i: 0.5 * (ops.nodeDisp(E.ntag(i, 0, k), 2) + ops.nodeDisp(E.ntag(i, 1, k), 2))
        out[k] = uy(2) - 0.5 * (uy(0) + uy(4))
    return out, m["deck"]


def _hand(Gd):
    import engine3d as E
    import sections as S
    L, B, w = 24000.0, 6000.0, 1.0e5 / 24000.0
    EI = E.E * S.props("NPB450X190X67.16")["A"] * 2 * (B / 2) ** 2 + 2.4 * Gd * B ** 3 / 12.0
    return 5 * w * L ** 4 / (384 * EI) + w * L ** 2 / (8 * Gd * B)


def test_two_level_membrane_hand_check_per_level(eng):
    mixed = {"by_level": {1: STIFF, 2: SOFT}}
    d2, deck = _mid_deflection(eng, mixed, 2)
    d1, _ = _mid_deflection(eng, mixed, 1)
    assert deck[1]["section"] != deck[2]["section"]                     # one membrane section per distinct record
    assert deck[1]["Gt_N_per_mm"] == 200000.0 and deck[2]["Gt_N_per_mm"] == 5000.0
    assert d2[2] == pytest.approx(_hand(5000.0), rel=0.10)             # soft upper deck: its own Gd
    assert d1[1] == pytest.approx(_hand(200000.0), rel=0.10)           # stiff podium deck: its own Gd
    assert d2[2] > 10 * d1[1]
    # the same as the uniform model of each level's own record (per-level decks do not leak into each other)
    s2, _ = _mid_deflection(eng, SOFT, 2)
    k1, _ = _mid_deflection(eng, STIFF, 1)
    assert d2[2] == pytest.approx(s2[2], rel=0.01) and d1[1] == pytest.approx(k1[1], rel=0.01)
    # a single soft value on both levels makes the podium ~14x too flexible -- the defect the per-level form removes
    s1, _ = _mid_deflection(eng, SOFT, 1)
    assert s1[1] > 10 * d1[1]


def test_flexible_modes_lie_between_the_uniform_decks(eng):
    """Y-dominant fundamental period: all-stiff < stiff podium + soft upper deck < all-soft."""
    def ty(ds):
        md = FD.modal_flexible(_cfg(ds), nseg=2)
        return max(m["T"] for m in md["modes"] if m["mass_y"] > m["mass_x"])
    t_soft, t_stiff, t_mix = ty(SOFT), ty(STIFF), ty({"by_level": {1: STIFF, 2: SOFT}})
    assert t_stiff < t_mix < t_soft
    assert t_mix > 1.5 * t_stiff


def test_report_lists_the_deck_stiffness_per_level():
    import report_india as RI
    fd = {"status": "run", "cite": "Table 5(ii)", "model": "m", "base_shear": {}, "periods_s": [], "periods_rigid_s": [],
          "deck": {"1": {"panels": 4, "Gt_N_per_mm": 200000.0, "stiffness_basis": "podium composite"},
                   "2": {"panels": 4, "Gt_N_per_mm": 5000.0, "stiffness_basis": "CFS board deck"}}}
    h = RI._seismic_table({"load_plan": {}, "heights": [3600.0] * 2}, {"seismic_analysis": {"flexible_diaphragm": fd}}, {})
    assert "deck G t (N/mm)" in h and "podium composite" in h and "CFS board deck" in h
