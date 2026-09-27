"""GOLD-COLL (IN_CFS_Ex9, lead decision 2): flexible-diaphragm collector forces follow the load path -- the deck
shear accumulates along each braced / frame line from the free end (or the previous vertical element) and is
delivered to each braced / frame bay by tributary length of the line (IS 1893 (Part 1):2016 7.6.4 flexible
diaphragm, tributary distribution); the whole-line-shear upper bound is kept only when the vertical-element
positions on the line cannot be determined; per-level diaphragm labels (cfg['diaphragm_by_level']); the X01-enveloped
EQ combinations take the X01 deck-model beam axial as their flexible case."""
import os
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "steel_engine"))

import india_diaphragm as D

kN = 1e3


def test_hand_accumulation_two_braced_bays_among_five():
    """Line 0-30 m, five 6 m bays, braced bays 2 and 4 ([6, 12] and [18, 24], X-braces: both bay ends deliver),
    line shear V = 300 kN -> q = 10 kN/m.  Tributary lengths: bay 2 = 0..15 m (mid-gap 15 m), bay 4 = 15..30 m
    -> R = 150 kN each, 75 kN at each bay end.  N(x) = q x - deliveries before x (+ = compression):
      beam 0-6   : 0 .. 60                        -> +60
      beam 6-12  : 60 - 75 = -15 .. 120 - 75 = 45 -> +45
      beam 12-18 : 120 - 150 = -30 .. 180 - 150 = 30 -> 30 (either sign)
      beam 18-24 : 180 - 225 = -45 .. 240 - 225 = 15 -> -45
      beam 24-30 : 240 - 300 = -60 .. 0            -> -60
    The old upper bound gave 300 kN to every beam."""
    segs = [(6000.0 * i, 6000.0 * (i + 1), "b%d" % (i + 1)) for i in range(5)]
    els = [{"span": (6000.0, 12000.0), "nodes": [(6000.0, 1.0), (12000.0, 1.0)]},
           {"span": (18000.0, 24000.0), "nodes": [(18000.0, 1.0), (24000.0, 1.0)]}]
    acc = D.accumulate_line_collector(segs, els, 300 * kN)
    assert acc["q"] == pytest.approx(10.0)                       # N/mm = kN/m
    assert [e["R"] for e in acc["elements"]] == [pytest.approx(150 * kN), pytest.approx(150 * kN)]
    N = acc["N"]
    assert N["b1"] == pytest.approx(60 * kN) and N["b2"] == pytest.approx(45 * kN)
    assert abs(N["b3"]) == pytest.approx(30 * kN)
    assert N["b4"] == pytest.approx(-45 * kN) and N["b5"] == pytest.approx(-60 * kN)
    assert sum(r for _x, r in acc["deliveries"]) == pytest.approx(300 * kN)
    # a single diagonal delivering at the far end of bay 2 only: the bay beam carries the drag up to x = 12 m
    acc1 = D.accumulate_line_collector(segs, [{"span": (6000.0, 12000.0), "nodes": [(12000.0, 1.0)]}, els[1]],
                                       300 * kN)
    assert acc1["N"]["b2"] == pytest.approx(120 * kN) and acc1["N"]["b3"] == pytest.approx(-30 * kN)


def _line_cfg(braced=True, NF=1):
    import india_units as IU
    IU.activate_si()
    cfg = {"NX": 5, "NY": 1, "SX": 6000.0, "SY": 6000.0, "heights": [4000.0] * NF, "base": "pinned",
           "col": "WPB300X300X100.85", "beam": "NPB450X190X67.16", "units": "N-mm", "jurisdiction": "india",
           "D_floor": 3.0, "D_roof": 2.0, "L_floor": 2.5, "Lr": 0.75, "clad": 0.0, "self_weight": False,
           "diaphragm": "flexible", "releases": lambda i, j, k, d: ("both", "none"),
           "load_plan": {"jurisdiction": "india", "story_forces_units": "N",
                         "story_forces": {"EQ_X": {str(k): [6.0e5, 0, 0] for k in range(1, NF + 1)}}}}
    if braced:
        cfg.update(brace="WPB300X300X100.85",
                   braces=lambda k, NX, NY: [("X", 1, 0), ("X", 3, 0), ("X", 1, 1), ("X", 3, 1)])
    else:
        cfg["lateral_lines"] = {"X": [0.0, 6000.0]}
    return cfg


def _rows(cf, d="X", k=1, line=0.0):
    return sorted((r for r in cf["rows"] if r["role"] == "collector" and r["dir"] == d and r["level"] == k
                   and abs(r["line"] - line) < 1.0), key=lambda r: r["x_mm"][0] if "x_mm" in r else r["beam"])


def test_model_line_two_braced_bays_among_five():
    """Built model: 5 x 1 bays of 6 m, X-braced bays i = 1 and 3 on both X lines; F_X = 600 kN at the level ->
    each line 300 kN by tributary width (lines at y = 0 and 6 m) -> the hand numbers of the test above."""
    pytest.importorskip("openseespy.opensees")
    cfg = _line_cfg()
    cf = D.collector_forces(cfg, "EQ")
    assert cf["diaphragm"] == "flexible" and not cf["upper_bound_lines"]
    for line in (0.0, 6000.0):
        rows = _rows(cf, line=line)
        assert [r["x_mm"] for r in rows] == [[6000.0 * i, 6000.0 * (i + 1)] for i in range(5)]
        got = [r["N_N"] / kN for r in rows]
        assert got[0] == pytest.approx(60, abs=0.1) and got[1] == pytest.approx(45, abs=0.1)
        assert abs(got[2]) == pytest.approx(30, abs=0.1)
        assert got[3] == pytest.approx(-45, abs=0.1) and got[4] == pytest.approx(-60, abs=0.1)
        assert all(r["R_line_N"] == pytest.approx(300 * kN) for r in rows)
        assert [e["R_N"] for e in rows[0]["vertical_elements"]] == [pytest.approx(150 * kN)] * 2
        assert all("accumulated along the line" in r["basis"] and "7.6.4" in r["cite"] for r in rows)
    assert max(abs(v) for v in cf["X"].values() if v) < 300 * kN      # no beam carries the whole line shear


def test_unknown_bay_positions_fall_back_to_the_upper_bound():
    """Lines declared by cfg['lateral_lines'] with neither braces nor moment-connected beams on them: the vertical
    element positions are unknown -> every beam on the line gets the whole line shear, and the record says so."""
    pytest.importorskip("openseespy.opensees")
    cfg = _line_cfg(braced=False)
    cf = D.collector_forces(cfg, "EQ")
    rows = _rows(cf)
    assert len(rows) == 5 and all(r["N_N"] == pytest.approx(300 * kN) and r["upper_bound"] for r in rows)
    assert all("could not be determined" in r["basis"] for r in rows)
    ub = cf["upper_bound_lines"]
    assert {(u["dir"], u["level"], u["line"]) for u in ub} == {("X", 1, 0.0), ("X", 1, 6000.0)}
    dem = D.collector_demands(cfg)
    assert any(r.get("upper_bound") for r in dem)


def test_moment_frame_line_is_a_vertical_element():
    """No braces, the beams of line y = 0 moment-connected in bays 1-3 (x 0-18 m), pinned elsewhere: the frame
    (span 0-18 m) takes the whole line; only the free-end bays 18-30 m drag: N = q x distance from the free end."""
    pytest.importorskip("openseespy.opensees")
    cfg = _line_cfg(braced=False)
    cfg["lateral_lines"] = {"X": [0.0]}
    cfg["releases"] = lambda i, j, k, d: ("none", "none") if (d == "X" and j == 0 and i < 3) else ("both", "none")
    cf = D.collector_forces(cfg, "EQ")
    rows = _rows(cf)
    assert not cf["upper_bound_lines"]
    V = rows[0]["R_line_N"]                                       # the single line takes the whole 600 kN
    assert V == pytest.approx(600 * kN)
    q = V / 30000.0
    N = {tuple(r["x_mm"]): r["N_N"] for r in rows}
    assert N[(24000.0, 30000.0)] == pytest.approx(-q * 6000.0, rel=1e-4)
    assert N[(18000.0, 24000.0)] == pytest.approx(-q * 12000.0, rel=1e-4)
    assert "moment-frame" in rows[0]["basis"]


def test_diaphragm_by_level_labels():
    labels, errs = D.diaphragm_labels({"heights": [1, 1, 1, 1], "diaphragm": "flexible",
                                       "diaphragm_by_level": {"1-2": "rigid"}})
    assert labels == {1: "rigid", 2: "rigid", 3: "flexible", 4: "flexible"} and errs == []
    labels, errs = D.diaphragm_labels({"heights": [1, 1, 1], "diaphragm_by_level": {"default": "flexible", 1: "rigid"}})
    assert labels == {1: "rigid", 2: "flexible", 3: "flexible"} and not errs
    _, errs = D.diaphragm_labels({"heights": [1, 1], "diaphragm_by_level": {"3": "rigid", "1": "stiff", "2": "rigid",
                                                                              "1-2": "rigid"}})
    assert len(errs) == 3                                          # level 3 > NF, 'stiff', level 2 twice
    with pytest.raises(D.DiaphragmError):
        D.collector_forces({"heights": [1], "diaphragm_by_level": {"1": "semi-rigid"}}, "EQ")


def test_podium_rigid_under_flexible_floor_and_x01_case():
    """Two levels: level 1 rigid (composite podium), level 2 flexible.  Level 1 collectors come from the rigid load
    path (analysed model), level 2 from the line accumulation.  x01_flexible (the combination is enveloped with the
    X01 deck model): level 2 takes the rigid-case collectors and the rows say why."""
    pytest.importorskip("openseespy.opensees")
    cfg = _line_cfg(NF=2)
    cfg["diaphragm_by_level"] = {"1": "rigid", "default": "flexible"}
    cf = D.collector_forces(cfg, "EQ")
    assert cf["diaphragm"] == "by_level" and cf["diaphragm_by_level"] == {"1": "rigid", "2": "flexible"}
    r1 = [r for r in cf["rows"] if r["level"] == 1 and r["role"] == "collector"]
    r2 = [r for r in cf["rows"] if r["level"] == 2 and r["role"] == "collector"]
    assert r1 and all("q_N_per_mm" in r and "basis" not in r for r in r1)           # rigid load-path rows
    assert r2 and all("accumulated along the line" in r["basis"] for r in r2)
    got = sorted(round(r["N_N"] / kN, 1) for r in r2 if abs(r["line"]) < 1.0)
    assert got[0] == pytest.approx(-60, abs=0.1) and got[-1] == pytest.approx(60, abs=0.1)
    cx = D.collector_forces(cfg, "EQ", x01_flexible=True)
    assert cx["x01_flexible"] and "X01" in cx["x01_note"]
    rx2 = [r for r in cx["rows"] if r["level"] == 2 and r["role"] == "collector"]
    assert rx2 and all("basis" not in r and "rigid half" in r["case"] for r in rx2)
    dem = D.collector_demands(cfg, x01_flexible=True)
    assert any(r.get("role") == "note" and r["levels"] == [2] for r in dem)
    assert any(r.get("case") and r["level"] == 2 for r in dem if r.get("role") == "collector")


def test_add_to_records_uses_rigid_collectors_for_x01_enveloped_combinations():
    pytest.importorskip("openseespy.opensees")
    import engine3d as E

    class C(tuple):
        pass

    def case(label):
        c = C((label,))
        c.meta = {"kind": "EQ", "direction": "X", "fLat": 1.0}
        return c
    cfg = _line_cfg()
    info = E.build(cfg, "PDelta")
    reg = {t: (k, s, a, b) for (t, k, s, a, b) in info["ele"]}
    beams = [frozenset((a, b)) for t, (k, s, a, b) in reg.items() if k == "beam"]
    per = {"A": {fs: (0.0,) * 11 for fs in beams}, "B": {fs: (0.0,) * 11 for fs in beams}}
    D.add_to_records(per, [case("A"), case("B")], reg, cfg, x01_labels=["B"])
    fl = D.collector_forces(cfg, "EQ")["X"]
    rg = D.collector_forces(cfg, "EQ", x01_flexible=True)["X"]
    tag_of = {frozenset((a, b)): t for t, (k, s, a, b) in reg.items() if k == "beam"}
    for fs, rec in per["A"].items():
        assert rec[0] == pytest.approx(-fl.get(tag_of[fs], 0.0))
    for fs, rec in per["B"].items():
        assert rec[0] == pytest.approx(-rg.get(tag_of[fs], 0.0))
    assert per["A"] != per["B"]


def test_reconcile_per_level_labels():
    lv = {"X": [{"level": 1, "ratio": 0.05, "ratio_basis": D.RATIO_BASIS_7_6_4},
                {"level": 2, "ratio": 0.30, "ratio_basis": D.RATIO_BASIS_7_6_4}]}
    rec = D.reconcile_7_6_4(D.classify_7_6_4(declared="flexible"), lv, declared="flexible",
                            declared_by_level={1: "rigid", 2: "flexible"})
    assert rec["computed_by_level"]["2"]["classification"] == "rigid"
    assert rec["contradicted_levels"] == [{"level": 2, "declared": "flexible", "computed": "rigid", "ratio": 0.30,
                                           "dir": "X"}]
    assert rec["declared_contradicted"] is True and "level 2" in rec["warning"]
    ok = D.reconcile_7_6_4(D.classify_7_6_4(declared="rigid"), lv, declared="rigid",
                           declared_by_level={1: "rigid", 2: "rigid"})
    assert not ok.get("declared_contradicted")
