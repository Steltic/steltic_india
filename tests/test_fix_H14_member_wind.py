"""H14 (HR-A-15, HR-B-12, HR-E-16, L-15): member-level wind -- reversed patterns, wall load by tributary width,
first exposed facade per strip, gable walls in WM90, roof pressure on every roof level, roof zones split at the
declared ridge per sub-segment, retrieved Table 5 passed through lowrise_member_wind."""
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "steel_engine"))
sys.path.insert(0, os.path.dirname(__file__))
from _ex1_fixture import ex1_cfg_is  # noqa: E402

FULL = {(i, j) for i in range(6) for j in range(5)}


def _run(cfg, pat, f=1.0, nseg=4):
    import static_model as SM
    import openseespy.opensees as ops
    ops.wipe()
    model = SM.build_static(cfg, "Linear", nseg)
    ops.timeSeries("Linear", 1); ops.pattern("Plain", 1, 1)
    loads = {}
    real = ops.eleLoad

    def cap(*a):
        loads[a[1]] = a[4:]
        return real(*a)
    ops.eleLoad = cap
    try:
        tot = SM.member_wind_loads(cfg, model, pat, f)
    finally:
        ops.eleLoad = real
    return model, tot, loads


def test_strip_widths_tributary():
    import static_model as SM
    w = SM._strip_widths([0.0, 8000.0, 16000.0, 24000.0, 32000.0])
    assert [w[x] for x in sorted(w)] == [4000.0, 8000.0, 8000.0, 8000.0, 4000.0]
    assert sum(w.values()) == 32000.0


def test_wall_load_by_tributary_and_reversed():
    cfg, _ = ex1_cfg_is()
    pat = {"wind_axis": "X", "wall_windward_kNm2": 1.0, "wall_leeward_kNm2": -0.5}
    model, tot, loads = _run(cfg, pat)
    H = sum(cfg["heights"]); Ly = cfg["NY"] * cfg["SY"]
    assert tot["wall_N"] == pytest.approx(1.5 * Ly * H / 1000.0, rel=1e-6)
    # corner column line (j = 0) gets half the interior line load
    wl = {}
    for c in model["cols"]:
        if c["tag"] in loads and c["i"] == 0 and c["k"] == 0:
            wl[c["j"]] = max(abs(x) for x in loads[c["tag"]])
    assert wl[0] == pytest.approx(0.5 * wl[2]) and wl[2] == pytest.approx(1.0 * cfg["SY"] / 1000.0)
    # reversed: windward face is the high-coordinate edge, total along -X
    model, totR, loadsR = _run(cfg, dict(pat, sign=-1))
    assert totR["wall_N"] == pytest.approx(-tot["wall_N"], rel=1e-9)
    hi = {c["tag"] for c in model["cols"] if c["i"] == cfg["NX"]}
    assert hi & set(loadsR)


def test_first_exposed_facade_on_setback():
    cfg, _ = ex1_cfg_is()
    cfg["present"] = {0: FULL, 1: FULL, 2: FULL, 3: FULL, 4: {p for p in FULL if p[0] >= 1},
                      5: {p for p in FULL if p[0] >= 1}}
    model, tot, loads = _run(cfg, {"wind_axis": "X", "wall_windward_kNm2": 1.0, "wall_leeward_kNm2": 0.0})
    upper_i1 = [c for c in model["cols"] if c["i"] == 1 and c["k"] >= 3]
    lower_i1 = [c for c in model["cols"] if c["i"] == 1 and c["k"] < 3]
    assert upper_i1 and all(c["tag"] in loads for c in upper_i1)          # exposed above the setback
    assert not any(c["tag"] in loads and any(loads[c["tag"]]) for c in lower_i1)


def test_roof_every_roof_level_and_ridge_split_per_segment():
    import static_model as SM
    cfg, _ = ex1_cfg_is()
    cfg["deck_span"] = None                                   # two-way roof tributary
    cfg["roof_levels"] = [2]
    cfg["ridge"] = {"axis": "X", "coord_mm": 3000.0}          # ridge line normal to X at x = 3 m
    pat = {"wind_axis": "X", "roof_windward_kNm2": -1.0, "roof_leeward_kNm2": -0.5}
    model, tot, loads = _run(cfg, pat)
    b = next(b for b in model["beams"] if b["k"] == 5 and b["dir"] == "X" and b["i"] == 0 and b["j"] == 2)
    w = [loads[t][1] for t in b["segs"]]                     # -w (downward positive pressure)
    # segments at 750 / 2250 mm windward (EF), 3750 / 5250 mm leeward (GH); two-way widths 2 x min(s, L-s, 3000)
    assert w[0] == pytest.approx(1.0 * 2 * 750.0 / 1000.0) and w[1] == pytest.approx(1.0 * 2 * 2250.0 / 1000.0)
    assert w[2] == pytest.approx(0.5 * 2 * 2250.0 / 1000.0) and w[3] == pytest.approx(0.5 * 2 * 750.0 / 1000.0)
    lower = [t for bb in model["beams"] if bb["k"] == 2 for t in bb["segs"]]
    assert any(t in loads for t in lower)                     # declared lower roof level gets uplift
    assert not any(t in loads for bb in model["beams"] if bb["k"] == 3 for t in bb["segs"])
    # reversed pattern: the high side becomes windward
    _, _, loadsR = _run(cfg, dict(pat, sign=-1))
    wR = [loadsR[t][1] for t in b["segs"]]
    assert wR[0] == pytest.approx(0.5 * 2 * 750.0 / 1000.0)


def test_lowrise_member_wind_gable_walls_and_corpus_passthrough():
    import india_wind_tables as W
    r = W.lowrise_member_wind(1.0, 8.0, 24.0, 36.0, 10.0, 0.03)
    wm90 = [p for p in r["patterns"] if p["name"].startswith("WM90")]
    c90 = W.resolve_cpe_walls(8.0 / 24.0, 1.5, 90.0)["Cpe"]
    assert wm90[0]["wall_windward_kNm2"] == pytest.approx(c90["C"] - 0.2)
    assert wm90[0]["wall_leeward_kNm2"] == pytest.approx(c90["D"] - 0.2)
    hit = {"found": True, "Cpe": {"A": 0.8, "B": -0.3, "C": -0.6, "D": -0.6}, "cite": "exact_table 5"}
    r2 = W.lowrise_member_wind(1.0, 8.0, 24.0, 36.0, 10.0, 0.03, corpus_hit={0: hit})
    wm0 = r2["patterns"][0]
    assert wm0["walls_source"] == "corpus" and wm0["wall_windward_kNm2"] == pytest.approx(0.8 - 0.2)
    r3 = W.lowrise_member_wind(1.0, 8.0, 24.0, 36.0, 10.0, 0.03, roof={"EF": -1.0, "GH": -0.5, "EG": -0.9, "FH": -0.4})
    assert r3["patterns"][0]["roof_windward_kNm2"] == pytest.approx(-1.0 - 0.2)
    # l/w >= 4: EOR record accepted instead of reshaping the building
    assert W.lowrise_member_wind(1.0, 8.0, 10.0, 45.0, 10.0, 0.03)["found"] is False
    eor = {"Cpe": {"A": 0.7, "B": -0.3, "C": -0.7, "D": -0.7}, "source": "eor_documented", "cite": "EOR", "verify": True}
    assert W.lowrise_member_wind(1.0, 8.0, 10.0, 45.0, 10.0, 0.03, eor_cpe={0: eor, 90: eor})["found"] is True
