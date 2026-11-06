"""Engine checks follow-up 3 (2026-11-06, branch fix/2026-11-engine-checks): the lead's ruling on open point 1 and
the reviewer's gable-triangle note.

(a) Side walls: every member-wind pattern loads the columns and posts of the two walls parallel to the wind with
    their IS 875-3 Table 5 Cpe (C / D at theta = 0, A / B at theta = 90) and the pattern's Cpi, over the width of the
    member's own wall, a wind post with the Ka of its own side-wall area (static_model.side_wall_pressure,
    SIDE_WALL_CITE).  Table 5 gives one average Cpe per wall surface -- no zones by distance; the 0.25 w local strip
    is for cladding (7.3.1) -- so no tributary spans two zones.
(b) Every wall area reaches a member: in a wall plane with a sloping envelope member (gable rafter, end-truss top
    chord) each column line carries the wall area of its tributary strip up to that member, the part above or below
    its loaded height at its upper end (static_model.envelope_residuals, ENVELOPE_RESIDUAL_BASIS).
"""
import json
import math
import os
import sys

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
for p in (os.path.join(ROOT, "steel_engine"), HERE):
    if p not in sys.path:
        sys.path.insert(0, p)

DATA = os.path.join(HERE, "fixtures", "engine_checks_2026_11")


def _fixture(name):
    return json.load(open(os.path.join(DATA, name)))


# ====================================================================================================== Table 5 sides
def test_side_wall_pressure_from_the_generator_IN_Ex21():
    """IN_Ex21's own call (cfg.py: pd 0.4292, eave 6.5 m, 18 x 36 m, Cpi +-0.5): theta = 0 side walls C / D take
    -0.6, theta = 90 side walls A / B -0.5 (Table 5, h/w <= 1/2, 3/2 < l/w < 4); q = (Cpe - Cpi) pd."""
    import india_wind_tables as WT
    mw = WT.lowrise_member_wind(0.4292, 6.5, 18.0, 36.0, 14.0, 0.10, ridge_axis="X")
    by = {p["name"]: p for p in mw["patterns"]}
    for name, cpe, sfs in (("WM0+", -0.6, ["C", "D"]), ("WM0-", -0.6, ["C", "D"]), ("WM90+", -0.5, ["A", "B"]),
                           ("WM90-", -0.5, ["A", "B"])):
        p = by[name]
        assert p["wall_cpe"]["side"]["surfaces"] == sfs and p["wall_cpe"]["side"]["Cpe"] == cpe
        assert p["wall_side_kNm2"] == pytest.approx((cpe - p["Cpi"]) * 0.4292)
        assert p["pd_kNm2"] == 0.4292 and "0.25 w" in p["wall_cpe"]["cite"]
    assert by["WM0+"]["wall_cpe"]["windward"] == {"surface": "A", "Cpe": 0.7}
    assert by["WM90+"]["wall_cpe"]["leeward"] == {"surface": "D", "Cpe": -0.1}


def _box_cols(Lx, Ly, H, nx, ny):
    """A plain rectangle of wall columns (perimeter lines) as member_wind_loads' rows for wind along X."""
    out = []
    t = 0
    for i in range(nx + 1):
        for j in range(ny + 1):
            if 0 < i < nx and 0 < j < ny:
                continue
            t += 1
            x, y = Lx * i / nx, Ly * j / ny
            out.append(({"tag": t}, [x, y, 0.0], [x, y, H], x, round(y, 3), 0.0, H))
    return out


@pytest.mark.parametrize("axis,theta,cpe", [("X", 0, -0.6), ("Y", 90, -0.5)])
def test_side_wall_pressure_derived_for_a_pattern_without_it_IN_Ex6(axis, theta, cpe):
    """A hand-built pattern (IN_Ex6's form: pressures, Cpi +-0.5 and pd_kNm2, no wall_side_kNm2) on IN_Ex6's plan
    (32 m along Y x 18 m along X, h 9 m: h/w 0.5, l/w 1.78): wind along X is normal to the 32 m face (theta 0, its
    pressures imply A +0.7 / B -0.25) -> side walls C / D -0.6; wind along Y onto the 18 m gable (theta 90, C +0.7 /
    D -0.1) -> side walls A / B -0.5.  The record states the derivation and the check against the pattern."""
    import static_model as SM
    pd, cpi = 0.9256, 0.5
    ww, wl = (0.7, -0.25) if axis == "X" else (0.7, -0.1)
    pat = {"name": "WM%s+" % axis, "wind_axis": axis, "wall_windward_kNm2": (ww - cpi) * pd,
           "wall_leeward_kNm2": (wl - cpi) * pd, "Cpi": cpi, "pd_kNm2": pd}
    cols = _box_cols(18000.0, 32000.0, 9000.0, 3, 4)
    r = SM.side_wall_pressure({}, pat, cols, 0 if axis == "X" else 1)
    assert r["applied"] and r["theta_deg"] == theta and r["Cpe"] == cpe
    assert r["q_kNm2"] == pytest.approx((cpe - cpi) * pd)
    assert r["surfaces"] == (["C", "D"] if theta == 0 else ["A", "B"]) and r["source"].startswith("derived")
    assert r["check"]["table5_windward_Cpe"] == pytest.approx(r["check"]["pattern_windward_Cpe"])
    # the implied Cpe settles theta even when the plan would say otherwise (a square plan: both faces 'long')
    sq = SM.side_wall_pressure({}, pat, _box_cols(18000.0, 18000.0, 9000.0, 3, 3), 0 if axis == "X" else 1)
    assert sq["applied"] and sq["check"]["pattern_leeward_Cpe"] == pytest.approx(wl)


def test_side_walls_not_loadable_is_a_consistency_failure():
    """A pattern with no wall_side_kNm2, no Cpi: the side walls cannot be loaded -- the record says why and the
    package check fails (never silent)."""
    import static_model as SM
    import consistency as CS
    r = SM.side_wall_pressure({}, {"name": "W1", "wind_axis": "X", "wall_windward_kNm2": 1.0,
                                   "wall_leeward_kNm2": -0.5}, _box_cols(18000.0, 32000.0, 9000.0, 3, 4), 0)
    assert r["applied"] is False and "Cpi" in r["reason"]
    pkg = {"member_wind_wall_scan": {"patterns": {"W1": {"side_walls": r}}}}
    iss = CS.member_wind_side_wall_issues(pkg)
    assert len(iss) == 1 and "side walls are not loaded" in iss[0]
    ok = {"member_wind_wall_scan": {"patterns": {"W1": {"side_walls": {"applied": True}}}}}
    assert CS.member_wind_side_wall_issues(ok) == []


# ====================================================================================================== IN_Ex21 gable
def _in_ex21(pattern_axis):
    """The IN_Ex21 wall geometry (static model of its gold run), rows for a scan along pattern_axis."""
    fx = _fixture("IN_Ex21_wall_wind_geometry.json")
    a_ = 0 if pattern_axis == "X" else 1
    o_ = 1 - a_
    cols = []
    for c in fx["cols"]:
        c1, c2 = c["c1"], c["c2"]
        cols.append((c, c1, c2, 0.5 * (c1[a_] + c2[a_]), round(0.5 * (c1[o_] + c2[o_]), 3), min(c1[2], c2[2]),
                     max(c1[2], c2[2])))
    env = [tuple(map(tuple, e)) for e in fx["envelope"]]
    return fx, cols, env


GABLE_M2 = 18.0 * 6.5 + 18.0 * 2.25 / 2.0         # IN_Ex21 gable: 18 m span, eave 6.5 m, rise 2.25 m = 137.25 m2


def test_e2e_IN_Ex21_every_gable_area_reaches_a_member():
    """IN_Ex21's gables (x = 0, 36 m) are the windward / leeward walls of the along-ridge wind and the side walls of the
    across-ridge wind -- the same scan along X.  The corner columns (y = 0, 18) end at the eave and carry the strips
    0-3 / 15-18 m; the posts (y = 6, 12) end at 8.0 m under the end-truss top chord and carry 3-9 / 9-15 m.  Before,
    the loaded area was 135 m2 of 137.25: the corner triangles above the eave (1.125 m2 each) and the triangle over
    the posts' tops (2.25 m2, the review's note) carried nothing, and the posts' rectangles reached above the chord
    on their outer halves (1.125 m2 each).  Each line now carries its strip's wall up to the chord: the posts' strips
    balance exactly (48 m2 each), each corner column takes its 1.125 m2 triangle at its top node; the gable totals
    137.25 m2."""
    import static_model as SM
    fx, cols, env = _in_ex21("X")
    faces = (("up", 1.0, 1.0), ("down", 1.0, -1.0))
    scan = SM.wall_wind_pieces(cols, env, 0, 1.0, faces, fx["SY"])
    res = SM.envelope_residuals(scan["pieces"], scan["halves"], env, 0)
    for face in ("up", "down"):
        idx = [i for i, p in enumerate(scan["pieces"]) if p[3] == face]
        loaded = sum(scan["pieces"][i][6] * abs(scan["pieces"][i][2][2] - scan["pieces"][i][1][2]) for i in idx)
        assert loaded / 1e6 == pytest.approx(135.0, abs=1e-6)                       # the scan alone (origin/main)
        extra = sum(res.get(i, 0.0) for i in idx)
        assert (loaded + extra) / 1e6 == pytest.approx(GABLE_M2, abs=0.01)
        by_top = {}
        for i in idx:
            if abs(res.get(i, 0.0)) > 1e3:
                c, c1, c2 = scan["pieces"][i][:3]
                by_top[round(c1[1])] = round(res[i] / 1e6, 3)
        assert by_top == {0: 1.125, 18000: 1.125}                                   # the corner columns' tops


def test_e2e_IN_Ex21_long_walls_as_side_walls_under_the_along_ridge_wind():
    """Along the ridge (wind along X) the side walls are the long walls y = 0, 18 m: the side scan runs along Y in the
    frame strips -- every eave column takes the side-wall pressure over its frame spacing; the gable posts' pieces
    above the eave (inside the gable, the end truss's chord between them and the long wall) are not on a side wall;
    each long wall totals 36 x 6.5 = 234 m2 with no envelope residual (no sloping member in its plane)."""
    import static_model as SM
    fx, cols, env = _in_ex21("Y")
    scan = SM.wall_wind_pieces(cols, env, 1, 1.0, (("up", 1.0, 1.0), ("down", 1.0, -1.0)), fx["SX"])
    upper = {355, 357, 359, 361}
    assert not any(p[0]["tag"] in upper for p in scan["pieces"])
    assert {s["tag"] for s in scan["record"]["sheltered"]} >= upper
    for face in ("up", "down"):
        A = sum(p[6] * abs(p[2][2] - p[1][2]) for p in scan["pieces"] if p[3] == face)
        assert A / 1e6 == pytest.approx(234.0, abs=1e-6)
    assert SM.envelope_residuals(scan["pieces"], scan["halves"], env, 1) == {}


# ====================================================================================================== integration
def _mini_run(pattern_name, wind_summary=None):
    import openseespy.opensees as ops
    import static_model as SM
    from _peb_fixture import mini_peb_cfg
    cfg = mini_peb_cfg()
    if wind_summary is not None:
        cfg["load_plan"]["wind_summary"] = wind_summary
    pats = cfg["load_plan"]["member_wind"]
    pats = pats.get("patterns") if isinstance(pats, dict) else pats
    pat = next(p for p in pats if p["name"] == pattern_name)
    ops.wipe()
    model = SM.build_static(cfg, "Linear", 4)
    ops.timeSeries("Linear", 1)
    ops.pattern("Plain", 1, 1)
    ele, nod = [], []
    re_, rn_ = ops.eleLoad, ops.load

    def ce(*a):
        ele.append(a)
        return re_(*a)

    def cn(*a):
        nod.append(a)
        return rn_(*a)
    ops.eleLoad, ops.load = ce, cn
    try:
        tot = SM.member_wind_loads(cfg, model, dict(pat, sign=1), 1.0)
    finally:
        ops.eleLoad, ops.load = re_, rn_
    return cfg, pat, model, tot, ele, nod


def test_integration_mini_PEB_side_walls_and_gable_residual():
    """The mini PEB shed (12 x 12 m, eave 6 m, rise 0.6 m, gable post at mid-span): under WM0+ (wind along Y) the
    gables x = 0, 12 m are the side walls -- each 12 x 6 + 12 x 0.6 / 2 = 75.6 m2 at q = (Cpe_side - Cpi) pd, equal
    and opposite (side_N = 0); under WM90+ the long walls (72 m2 each) are.  The gable residual: each corner column
    +0.45 m2 at its top node, the post -0.9 m2 (its 6.6 m rectangle reaches above the rafter on both sides)."""
    cfg, pat, model, tot, ele, nod = _mini_run("WM0+")
    q = pat["wall_side_kNm2"]
    f = tot["faces"]
    assert f["side_lo"]["A_m2"] == pytest.approx(75.6, abs=0.01) and f["side_hi"]["A_m2"] == pytest.approx(75.6, abs=0.01)
    assert f["side_lo"]["N"] == pytest.approx(q * 75.6e3, rel=1e-3) and f["side_hi"]["N"] == pytest.approx(-q * 75.6e3, rel=1e-3)
    assert tot["side_N"] == pytest.approx(0.0, abs=1e-6) and tot["side_walls"]["source"] == "pattern (wall_side_kNm2)"
    assert f["windward"]["A_m2"] == pytest.approx(72.0) and f["leeward"]["A_m2"] == pytest.approx(72.0)
    rec = model["member_wind_wall"]["WM0+"]
    res = sorted((e["wall"], e["area_m2"]) for e in rec["envelope_residual"])
    assert res == [("side_hi", -0.9), ("side_hi", 0.45), ("side_hi", 0.45), ("side_lo", -0.9), ("side_lo", 0.45),
                   ("side_lo", 0.45)]
    # the residual is applied at the top nodes, along X (the gable's normal), and every side member is recorded
    tops = {e["node"] for e in rec["envelope_residual"]}
    assert {int(a[0]) for a in nod} >= tops and all(a[2] == 0.0 for a in nod if int(a[0]) in tops)
    sides = [m for m in rec["members"] if m["wall"].startswith("side")]
    assert sides and all(m["surface"] == "C/D" and m["Cpe"] == pat["wall_cpe"]["side"]["Cpe"] for m in sides)
    assert all(m["q_kNm2"] == pytest.approx(q, abs=1e-4) for m in sides)
    # a side-wall member is loaded across the wind: a uniform load along global X (transf 2: local y = +X; transf 1:
    # local z = +X), on every side member, the corner columns on top of their long-wall load along Y
    cols = {c["tag"]: c for c in model["cols"]}
    for t in {m["tag"] for m in sides}:
        xs = [a[4] if cols[t]["transf"] == 2 else a[5] for a in ele if a[1] == t]
        assert any(abs(x) > 0 for x in xs), t
    _, pat9, model9, tot9, _, _ = _mini_run("WM90+")
    f9 = tot9["faces"]
    assert f9["side_lo"]["A_m2"] == pytest.approx(72.0) and f9["windward"]["A_m2"] == pytest.approx(75.6, abs=0.01)
    assert f9["side_lo"]["N"] == pytest.approx(pat9["wall_side_kNm2"] * 72.0e3, rel=1e-6)
    assert all(m["surface"] == "A/B" for m in model9["member_wind_wall"]["WM90+"]["members"] if m["wall"].startswith("side"))


def test_integration_mini_PEB_side_wall_post_takes_the_Ka_of_its_own_side_area():
    """The gable wind column (pinned top) on the side wall of WM0+: IS 875-3 7.2.2.1 (b) Ka of its own side-wall area
    (38.7 m2 with the residual: strip 3-9 m up to the rafter) against the frame Ka the pattern carries (a wind summary
    stated with the frame basis): factor = Ka(38.7) / Ka_frame."""
    import india_wind_tables as WT
    ws = {"Kd": 1.0, "Kc": 1.0, "pz_kNm2": 1.0, "Ka": 0.8, "Ka_basis": "frame_tributary", "pd_kNm2": 0.8}
    cfg, pat, model, tot, ele, nod = _mini_run("WM0+", ws)
    side = {k: v for k, v in model["wind_post_Ka"].items() if len(k) == 3 and k[2] == "side"}
    post = [v for v in side.values() if v["A_m2"] == pytest.approx(38.7, abs=0.01)]
    assert len(post) == 2 and all(v["applied"] and v["wall"] == "side" for v in post)
    ka = WT.ka_for_area_m2(38.7)["Ka"]
    assert post[0]["factor"] == pytest.approx(max(ka, 0.7) / 0.8, rel=1e-3)
    f = tot["faces"]["side_lo"]
    assert f["N"] != pytest.approx(f["N_pattern_pd"])                   # the post's Ka moves the side-wall total


# ====================================================================================================== facade steps
def test_e2e_IN_Ex9_lean_to_facade_step():
    """IN_Ex9: a 24 x 60 m hall (x 12-36 m, eave 8 m, ridge 11 m along Y) with a flat lean-to x 0-12 m, y 0-30 m, 5 m
    high.  The +Y face is the hall's gable at y = 60 (x 12-36) and the lean-to's end wall at y = 30 (x 0-12, 5 m).
    Before, the hall's corner column (12, 60) took half the strip toward x = 0 over its 8 m (a wall that does not exist
    at y = 60) and the lean-to end wall's half next to wall B (x 6-12) had no member: 270 m2 against 252 below the
    eave line.  Now the corner's wall ends at its line and the re-entrant column (12, 30) carries that half: 252 m2,
    the same as the -Y face; with the gable triangle (residual) each face is 288 m2."""
    import static_model as SM
    fx = _fixture("IN_Ex9_wall_wind_geometry.json")
    cols = []
    for c in fx["cols"]:
        c1, c2 = c["c1"], c["c2"]
        cols.append((c, c1, c2, 0.5 * (c1[1] + c2[1]), round(0.5 * (c1[0] + c2[0]), 3), min(c1[2], c2[2]),
                     max(c1[2], c2[2])))
    env = [tuple(map(tuple, e)) for e in fx["envelope"]]
    scan = SM.wall_wind_pieces(cols, env, 1, 1.0, (("up", 1.0, 1.0), ("down", 1.0, -1.0)), fx["SX"])
    res = SM.envelope_residuals(scan["pieces"], scan["halves"], env, 1)
    tot = {}
    by = {}
    for i, p in enumerate(scan["pieces"]):
        c, c1, c2, face, q, fs, w = p
        tot[face] = tot.get(face, 0.0) + w * abs(c2[2] - c1[2]) + res.get(i, 0.0)
        by[(face, round(c1[0]), round(c1[1]), round(c1[2]))] = w
    assert tot["up"] / 1e6 == pytest.approx(288.0, abs=0.01) and tot["down"] / 1e6 == pytest.approx(288.0, abs=0.01)
    assert by[("down", 12000, 60000, 0)] == pytest.approx(12000.0)                 # the hall's corner: its own wall only
    assert by[("down", 12000, 30000, 0)] == pytest.approx(6000.0)                  # the re-entrant corner column
    assert by[("down", 0, 30000, 0)] == pytest.approx(6000.0)
    st = scan["record"]["stepped_facade"]
    assert any(s["width_mm"] == 0.0 for s in st) and any("re-entrant" in s["basis"] for s in st)
    # the -Y face (no step: the lean-to's end wall is in the gable's plane) is unchanged
    assert by[("up", 12000, 0, 0)] == pytest.approx(18000.0)


# ====================================================================================================== IS 18168 Ca
def _ca_md(rows):
    import sections as SS
    sec = "NPB600X220X107.57"
    p = SS.props(sec)
    Py = p["A"] * 250.0 / 1.1
    m = {"id": "C1", "role": "column", "section": sec, "grade": "E250BR", "L_mm": 4000.0}
    fs = [{"combo": c, "family": fam, "lateral_kind": lk, "P_N": r * Py} for r, fam, lk, c in rows]
    return m, p, {"members": [m], "forces": {"C1": fs}}


def test_Ca_from_the_earthquake_records_only():
    """Lead ruling (2026-11-06): IS 18168 Table 2 (ii) Ca = Pu / (Py / gamma_m0) is the axial ratio at the seismic
    ductility demand -- taken from the earthquake records only (the Table 4 EL rows and the 12.2.3 rows), as the
    Section 12 gates.  A member whose largest Pu (0.6 Py) is a wind record: Ca 0.3, from its Table 4 EL row; with
    wind and gravity records only, Ca is not formed (None, never 0: review R2-1)."""
    import india_is800_s12 as S12
    m, p, md = _ca_md([(0.6, "table4", "W", "1.5(DL+WL)"), (0.3, "table4", "EQ", "1.2(DL+LL+EL)"),
                       (0.2, "12.2.3", "EQ", "1.2DL+0.5LL+2.5EL"), (0.5, "table4", None, "1.5(DL+LL)")])
    Ca, rec = S12._ca_governing(m, p, 250.0, md)
    assert Ca == pytest.approx(0.3) and rec["governing_combo"] == "1.2(DL+LL+EL)"
    assert (rec["n_records"], rec["n_records_judged"], rec["n_records_not_judged"]) == (4, 2, 2)
    assert rec["Ca_basis"] == S12.CA_EQ_BASIS and "ductility" in rec["Ca_basis"]
    m2, p2, md2 = _ca_md([(0.6, "table4", "W", "1.5(DL+WL)"), (0.5, "table4", None, "1.5(DL+LL)")])
    Ca2, rec2 = S12._ca_governing(m2, p2, 250.0, md2)
    assert Ca2 is None and "no earthquake combination" in rec2["Ca_basis"] and rec2["not_applicable"] is False


def test_Ca_e2e_IN_Ex20_column_whose_largest_Pu_is_a_wind_record():
    """IN_Ex20 (SCBF, 18 levels) column e126, WPB320X300X126.66 E250 B0: its largest Pu is the wind record
    1.5DL-1.5W_Y+1.5W_Y_across (243.5 kN; at 0482f9a that gave Ca 0.0693 and the Table 2 (ii) web limit 58.19).  Ca
    now comes from its 104 earthquake records -- the 12.2.3 / EL row with the largest Pu (228 kN) -- so Ca is lower
    and the web limit (which falls with Ca) is higher; the row's dc stays on the flange b/tf (7.32 / 7.76)."""
    import india_is800_s12 as S12
    import india_is18168 as I18
    fx = _fixture("IN_Ex20_scbf_column_e126_s12.json")
    m = fx["member"]
    p = S12._props(m)
    fy, _ = S12._fy(m, p)
    Ca, rec = S12._ca_governing(m, p, fy, {"forces": fx["forces"]})
    old = fx["branch_0482f9a_row"]
    eq = [f for f in fx["forces"]["e126"] if S12.earthquake_record(f)]
    assert rec["n_records_judged"] == len(eq) == 104 and rec["n_records_not_judged"] == 53
    gov = next(f for f in eq if f["combo"] == rec["governing_combo"])
    assert gov["lateral_kind"] == "EQ" and abs(gov["P_N"]) == pytest.approx(max(abs(f["P_N"]) for f in eq))
    assert abs(rec["governing_P_N"]) < old["governing_P_N"] and Ca < old["Ca"]
    assert Ca == pytest.approx(abs(rec["governing_P_N"]) * 1.1 / (fy * p["A"]), rel=1e-9)
    ry = S12._ry(m, p)[0]
    new_row = I18.table2_check("column", p, fy, ry, Ca=Ca)
    old_row = I18.table2_check("column", p, fy, ry, Ca=old["Ca"])
    assert old_row["limit"]["d/tw"] == pytest.approx(old["limit_d_tw"], abs=0.01)
    assert new_row["limit"]["d/tw"] > old_row["limit"]["d/tw"] and new_row["dc"] == pytest.approx(old["dc"], rel=1e-9)


def test_Ca_sizer_screen_from_the_earthquake_records_only():
    """The sizer's IS 18168 Table 2 screen takes Ca as the full run does (earthquake labels of the run)."""
    import peb_autosize as PA
    import sections as S

    class _Stub:
        mem_of_const = {"c": ["m"]}
        el_of_mem = {"m": [1]}
        envt = {1: {"records": {"w": (-4.0e5,) + (0.0,) * 16, "e": (-5.0e4,) + (0.0,) * 16}}}
        pkg = {"load_combinations": [{"label": "w", "lateral_kind": "W"}, {"label": "e", "lateral_kind": "EQ"}]}
        _eq_labels = PA.LocalModel._eq_labels
    sec = "NPB600X220X107.57"
    A = float(S.props(sec)["A"])
    assert PA.LocalModel._Ca(_Stub(), "c", sec, 250.0) == pytest.approx(5.0e4 / (250.0 * A / 1.10))



# ====================================================================================================== review R2-1
def _noeq_md(kind, no_seismic=False):
    """The reviewer's noeq_probe.py member: NPB600X220X107.57, fy 250, P = 0.45 Py, Mz 200 kN-m, in one record."""
    import sections as SS
    p = SS.props("NPB600X220X107.57")
    Py = p["A"] * 250.0 / 1.10
    rec = {"EQ": dict(combo="1.2DL+1.2LL+1.2EQ_X", family="table4", lateral_kind="EQ"),
           "W": dict(combo="1.5DL+1.5W_X", family="table4", lateral_kind="W"),
           "G": dict(combo="1.5DL+1.5LL", family="table4", lateral_kind=None)}[kind]
    m = {"id": "c1", "role": "column", "section": "NPB600X220X107.57", "grade": "E250BR", "L_mm": 4000.0}
    md = {"members": [m], "forces": {"c1": [dict(rec, member="c1", P_N=0.45 * Py, Mz_i_Nmm=200e6, Mz_j_Nmm=200e6)]}}
    if no_seismic:
        md["no_seismic"] = True
    return m, p, md


def _status_reasons(rows):
    import design_pipeline as DP
    import india_seismic_gates as G
    pkg = {"capacity_design": {"checks": {"%s@%s" % (r["id"], r["member"]): DP.capacity_check_entry(r) for r in rows}}}
    return [x for x in G._screen_findings(pkg, {}) if x.startswith("capacity_design")]


@pytest.mark.parametrize("kind", ["W", "G"])
def test_R2_1_no_earthquake_record_in_a_seismic_job_is_not_evaluated_and_open(kind):
    """Review R2-1, the reviewer's noeq_probe.py: with an earthquake record the 12.11.3.1 gate judges it (semi-compact,
    fails) and Ca = 0.45; with only a wind or a gravity record, in a job with a Section 12 system, the gate is not judged
    (ok None) and Ca is not formed (never 0) -- both rows not evaluated, each an open reason with a plain message."""
    import india_is800_s12 as S12
    m, p, md = _noeq_md("EQ")
    sc, bas = S12.table2_class_by_combination(m, p, 250.0, md)
    assert sc["section_class"] == "semi-compact" and S12._ca_governing(m, p, 250.0, md)[0] == pytest.approx(0.45)
    m, p, md = _noeq_md(kind)
    sc, bas = S12.table2_class_by_combination(m, p, 250.0, md)
    assert sc["section_class"] is None and bas["not_applicable"] is False and bas["n_records_judged"] == 0
    Ca, rec = S12._ca_governing(m, p, 250.0, md)
    assert Ca is None and rec["not_applicable"] is False
    gate = next(c for c in S12.column_checks("SMF", md, {}) if c["id"] == "smf_column_class")
    t2 = S12._table2_column_row(m, p, 250.0, md, "IS 18168:2023 5.3")
    assert gate["ok"] is None and t2["ok"] is None and t2["id"] == "is18168_table2_column" and t2.get("Ca") is None
    reasons = _status_reasons([gate, t2])
    assert len(reasons) == 2 and all("not evaluated: no earthquake combination" in r for r in reasons)


def test_R2_1_no_seismic_job_marks_the_gates_not_applicable():
    """Review R2-1: a job declaring no_seismic (no earthquake family) has no seismic detailing -- the gate and the
    Table 2 (ii) row are not applicable (ok None, stated) and are not open reasons in the design status."""
    import india_is800_s12 as S12
    m, p, md = _noeq_md("W", no_seismic=True)
    gate = next(c for c in S12.column_checks("SMF", md, {}) if c["id"] == "smf_column_class")
    t2 = S12._table2_column_row(m, p, 250.0, md, "IS 18168:2023 5.3")
    assert gate["ok"] is None and gate["not_applicable"] is True and "no_seismic" in gate["reason"]
    assert t2["ok"] is None and t2["not_applicable"] is True
    assert _status_reasons([gate, t2]) == []
    # brace and beam gates take the same rule
    b = {"id": "b1", "role": "brace", "section": "NPB600X220X107.57", "grade": "E250BR", "L_mm": 5000.0}
    mdb = {"members": [b], "no_seismic": True, "forces": {"b1": [dict(md["forces"]["c1"][0], member="b1")]}}
    row = next(c for c in S12.brace_member_checks("OCBF", b, mdb, {}) if c["id"] == "brace_not_slender")
    assert row["ok"] is None and row["not_applicable"] is True


@pytest.mark.parametrize("variant", ["lean_to_column_split", "hall_column_one_piece"])
def test_R2_2_facade_step_with_offset_splits_loads_the_wall_once(variant):
    """Review R2-2 (the reviewer's step_probe.py on IN_Ex9's geometry): the re-entrant column's share is width x the
    height each piece of the stepped wall's line shares with it, spread over its own length.  Before, the lean-to
    corner column split at 2.5 m doubled the re-entrant width (+Y face 318 m2), and a hall column in one piece 0-8 m
    took the 6 m width over 8 m (306 m2).  Now both faces are 288 m2 in every variant."""
    import copy
    import static_model as SM
    fx = copy.deepcopy(_fixture("IN_Ex9_wall_wind_geometry.json"))
    if variant == "lean_to_column_split":
        c17 = next(c for c in fx["cols"] if c["tag"] == 17)
        fx["cols"] = [c for c in fx["cols"] if c["tag"] != 17] + [dict(c17, c2=[0.0, 30000.0, 2500.0]),
                                                                   dict(c17, tag=9017, c1=[0.0, 30000.0, 2500.0])]
    else:
        c18 = next(c for c in fx["cols"] if c["tag"] == 18)
        fx["cols"] = [c for c in fx["cols"] if c["tag"] not in (18, 19)] + [dict(c18, c2=[12000.0, 30000.0, 8000.0])]
    cols = []
    for c in fx["cols"]:
        c1, c2 = c["c1"], c["c2"]
        cols.append((c, c1, c2, 0.5 * (c1[1] + c2[1]), round(0.5 * (c1[0] + c2[0]), 3), min(c1[2], c2[2]),
                     max(c1[2], c2[2])))
    env = [tuple(map(tuple, e)) for e in fx["envelope"]]
    scan = SM.wall_wind_pieces(cols, env, 1, 1.0, (("up", 1.0, 1.0), ("down", 1.0, -1.0)), fx["SX"])
    res = SM.envelope_residuals(scan["pieces"], scan["halves"], env, 1)
    tot = {}
    for i, (c, c1, c2, face, q, fs, w) in enumerate(scan["pieces"]):
        tot[face] = tot.get(face, 0.0) + w * abs(c2[2] - c1[2]) + res.get(i, 0.0)
    assert tot["up"] / 1e6 == pytest.approx(288.0, abs=0.01) and tot["down"] / 1e6 == pytest.approx(288.0, abs=0.01)
    rc = [(w, abs(c2[2] - c1[2])) for (c, c1, c2, face, q, fs, w) in scan["pieces"]
          if face == "down" and abs(c1[0] - 12000.0) < 1.0 and abs(c1[1] - 30000.0) < 1.0]
    assert sum(w * L for w, L in rc) / 1e6 == pytest.approx(30.0, abs=1e-6)        # the lean-to end wall's 6 x 5 m


def test_R2_4_derived_side_wall_warns_when_the_pattern_matches_neither_angle():
    """Review R2-4: a hand-built pattern built on other coefficients (its own Cpe +0.9 / -0.6 imply neither Table 5
    angle on IN_Ex6's plan) gets the Table 5 side walls with a WARN in the record; IN_Ex6's own patterns do not."""
    import static_model as SM
    pd, cpi = 0.9256, 0.5
    cols = _box_cols(18000.0, 32000.0, 9000.0, 3, 4)
    odd = {"name": "W1", "wind_axis": "X", "wall_windward_kNm2": (0.9 - cpi) * pd, "wall_leeward_kNm2": (-0.6 - cpi) * pd,
           "Cpi": cpi, "pd_kNm2": pd}
    r = SM.side_wall_pressure({}, odd, cols, 0)
    assert r["applied"] and r["warning"].startswith("WARN") and "neither Table 5 wind angle" in r["warning"]
    ok = dict(odd, wall_windward_kNm2=(0.7 - cpi) * pd, wall_leeward_kNm2=(-0.25 - cpi) * pd)
    assert "warning" not in SM.side_wall_pressure({}, ok, cols, 0)


def test_R2_2_IN_Ex9_across_the_lean_to_each_wall_once():
    """IN_Ex9 scanned along X (the across-ridge wind): the -X face is the lean-to's outer wall (30 x 5 m), wall B above
    the lean-to roof (30 x 3 m) and wall B beyond the lean-to (30 x 8 m) = 480 m2; the +X face is wall D, 60 x 8 m.
    At the step (y = 30 m) the hall column (12, 37.5), one piece 0-8 m, gives the re-entrant column at (12, 30) its half
    only over the step band (0-5 m, where the lean-to's wall stands in front); above it the line's own piece carries
    the wall -- each wall once."""
    import static_model as SM
    fx = _fixture("IN_Ex9_wall_wind_geometry.json")
    cols = []
    for c in fx["cols"]:
        c1, c2 = c["c1"], c["c2"]
        cols.append((c, c1, c2, 0.5 * (c1[0] + c2[0]), round(0.5 * (c1[1] + c2[1]), 3), min(c1[2], c2[2]),
                     max(c1[2], c2[2])))
    env = [tuple(map(tuple, e)) for e in fx["envelope"]]
    scan = SM.wall_wind_pieces(cols, env, 0, 1.0, (("up", 1.0, 1.0), ("down", 1.0, -1.0)), fx["SY"])
    res = SM.envelope_residuals(scan["pieces"], scan["halves"], env, 0)
    tot = {}
    for i, (c, c1, c2, face, q, fs, w) in enumerate(scan["pieces"]):
        tot[face] = tot.get(face, 0.0) + w * abs(c2[2] - c1[2]) + res.get(i, 0.0)
    assert tot["up"] / 1e6 == pytest.approx(480.0, abs=0.01) and tot["down"] / 1e6 == pytest.approx(480.0, abs=0.01)
