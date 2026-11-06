"""Engine checks follow-up (2026-11-06, branch fix/2026-11-engine-checks, on top of 711cc38): the lead's ruling on the
slender-section Pd basis and the three items flagged in CHANGES_2026-11-engine-checks.md, each with unit tests and an
end-to-end test on a real gold piece (fixtures in tests/fixtures/engine_checks_2026_11/).

R. Ruling: Pd of the 9.3.2.2 interaction is the design strength under axial compression alone (7.1.2); for a slender
   section its effective area takes the Table 2 'axial compression' web limit 42 eps; the 'generally' rows with r1 / r2
   decide the class and Md.  Stated in the check record (india_is800.PD_BASIS_3_7_2D) and pinned here.
1. Section 12 class gates (12.7.2.4, 12.8.2.5, 12.8.4.1, 12.11.3.1; IS 18168 Table 2 (ii) Ca) with the axial force of
   each combination, as fix B; the governing combination is reported.
2. The Section 12 panel-zone doubler at its own IS 2062:2025 fy (declared doubler_grade / doubler_fy_MPa, else E250),
   never the column's fy.
3. Member wind: a column piece under the roof is not on a wall (the gable posts above the eave split under the
   across-ridge wind took the long-wall pressure over an 18 m strip), and a piece above an eave split keeps its own
   wall's tributary width.
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


def _register(*labels):
    import peb_build as PB
    for lab in labels:
        if lab:
            PB.ensure(lab)


# ====================================================================================================== R (ruling)
def _in_ex1_check():
    import design_pipeline as DP
    fx = _fixture("IN_Ex1_main_column_WI862X225X12X8.json")
    _register(fx["member"]["section"], fx["member"].get("buckling_section"), *(fx.get("stations") or []))
    r = DP.member_checks_is800({}, {"member": fx["member"], "kind": fx["kind"], "records": fx["records"]})
    if fx.get("stations"):
        r = DP.peb_station_checks({}, fx["member"], fx["kind"], fx["records"], r, tuple(fx["stations"]))
    return fx, r


def test_R_slender_pd_takes_the_axial_compression_web_limit_IN_Ex1(monkeypatch):
    """Lead ruling 2026-11-06 on IN_Ex1 lateral_col-WI862X225X12X8: the engine's 3.7.2(d) reading is kept -- Ae (Pd, Nd)
    with the web at the 'axial compression' row 42 eps tw, Ze_eff with the combination's 126 eps / (1 + 2 r2) -- D/C
    1.063.  The review's reading (the r2 limit for the area too) would give about 1.03; it is not what the engine does."""
    import india_is800 as I8
    fx, r = _in_ex1_check()
    assert 1.060 <= r["dc"] <= 1.066, r["dc"]
    g = next(p for p in r["per_combo"] if p["combo"] == r.get("interaction_governing_combo", r["governing_combo"]))
    t2, e = g["table2"], g["effective_section_3_7_2d"]
    assert t2["section_class"] == "slender" and t2["web_row"].startswith("generally")
    p = I8._props(fx["member"]["section"])
    eps = math.sqrt(250.0 / r["fy_MPa"])
    assert e["web_dt_limit_axial_eps"] == 42.0
    assert e["web_d_eff_axial_mm"] == pytest.approx(42.0 * eps * p["tw"], rel=1e-9)            # Ae: 42 eps
    assert e["web_dt_limit_bending_eps"] == pytest.approx(126.0 / (1.0 + 2.0 * t2["r2"]), rel=1e-9)   # Md: r2 row
    basis = r["Pd_basis"]
    for k in ("9.3.2.2", "7.1.2", "7.3.2", "3.7.2(d)", "42 eps", "126 eps / (1 + 2 r2)", "keeps the gross area"):
        assert k in basis, k
    assert r["effective_section_3_7_2d"]["Pd_basis"] == basis
    # the other reading, for the record: the axial area with the r2 web limit as well -> about 1.03
    orig = I8.effective_section_3_7_2d

    def alt(sec, fy, *, welded=False, gamma_m0=I8.GAMMA_M0_DEFAULT, web_dt_limit=None):
        e_ = orig(sec, fy, welded=welded, gamma_m0=gamma_m0, web_dt_limit=web_dt_limit)
        if e_.get("found") and web_dt_limit not in (None, math.inf):
            tw = I8._props(sec)["tw"]
            d_ax = min(e_["web_d_mm"], web_dt_limit * tw)
            e_ = dict(e_, A_eff_mm2=e_["A_eff_mm2"] + (d_ax - e_["web_d_eff_axial_mm"]) * tw, web_d_eff_axial_mm=d_ax)
        return e_
    monkeypatch.setattr(I8, "effective_section_3_7_2d", alt)
    _, r_alt = _in_ex1_check()
    assert 1.02 <= r_alt["dc"] <= 1.04 and r_alt["dc"] < r["dc"] - 0.02


def test_R_semi_compact_by_the_generally_rows_keeps_the_gross_area_for_pd():
    """The same ruling, the other side: WI475X220X16X5 (E350, d/tw 88.6 > 42 eps = 35.5) is slender under axial
    compression alone but semi-compact under a combination with bending (the 'generally' rows decide the class), so Pd
    takes the gross area (7.3.2 'so long as the section is semi-compact or better'); with no bending at all the axial row
    classes it slender and Pd takes the 42 eps effective area."""
    import india_is800 as I8
    import sections as S
    lab = "WI475X220X16X5"
    S.register_welded_I(lab, 475, 220, 16, 5)
    mem = {"id": "c", "section": lab, "grade": "E350", "role": "column", "L_mm": 3000.0, "Kz": 1.0, "Ky": 1.0,
           "LLT_sag_mm": 1000.0, "LLT_hog_mm": 1000.0, "c1": 1.0}
    r = I8.member_check_is800(mem, [{"combo": "NC", "P_N": 155.1e3, "Mz_i_Nmm": 4.0e8, "Mz_j_Nmm": 4.0e8}])
    g = r["per_combo"][0]
    assert g["section_class"] == "semi-compact" and "effective_section_3_7_2d" not in g
    gross = I8.compression_capacity(I8._props(lab), r["fy_MPa"], KLz_mm=3000.0, KLy_mm=3000.0, welded=True,
                                    section_class="semi-compact")
    assert r["capacities"]["compression"]["Pd_N"] == pytest.approx(gross["Pd_N"], rel=1e-9)
    r2 = I8.member_check_is800(mem, [{"combo": "N", "P_N": 155.1e3}])
    t2 = r2["per_combo"][0]["table2"]
    assert t2["web_row"] == "axial compression" and t2["section_class"] == "slender"
    assert r2["capacities"]["compression"]["Pd_N"] < 0.9 * gross["Pd_N"]
    assert r2["Pd_basis"] == I8.PD_BASIS_3_7_2D


# ====================================================================================================== 1 (S12 classes)
def _column_md(sec="NPB600X220X107.57", ratios=((0.15, "table4", "1.5(DL+LL)"), (0.45, "12.2.3", "1.2DL+0.5LL+2.5EL"),
                                                 (-0.20, "12.2.3", "0.9DL-2.5EL"))):
    import sections as SS
    p = SS.props(sec)
    Py = p["A"] * 250.0 / 1.1
    m = {"id": "C1", "role": "column", "section": sec, "grade": "E250BR", "L_mm": 4000.0}
    fs = [{"combo": c, "family": fam, "P_N": r * Py, "Mz_i_Nmm": 200e6} for r, fam, c in ratios]
    return m, {"members": [m], "forces": {"C1": fs}}


def test_1_class_by_combination_takes_each_axial_force():
    """NPB600X220X107.57 (d/tw 52.4, E250): plastic with N = 0 (84 eps); under the 12.2.3 record with N = 0.45 Py the
    'generally' rows give r1 = 1.22 -> plastic / compact limits at the 42 eps floor, semi-compact 126 / (1 + 2 x 0.45) =
    66.3 eps: semi-compact, and that record governs."""
    import india_is800_s12 as S
    import sections as SS
    m, md = _column_md()
    sc, rec = S.table2_class_by_combination(m, SS.props(m["section"]), 250.0, md)
    assert sc["section_class"] == "semi-compact" and rec["class_without_axial_force"] == "plastic"
    assert rec["governing_combo"] == "1.2DL+0.5LL+2.5EL" and rec["governing_family"] == "12.2.3"
    assert rec["r2"] == pytest.approx(0.45) and rec["web_row"] == "generally, r1 positive"
    assert rec["web_limits"][2] == pytest.approx(126.0 / 1.9)
    assert rec["classes_by_combination"] == {"plastic": 2, "semi-compact": 1}


def test_1_smf_and_scbf_column_gates_with_the_axial_force():
    import india_is800_s12 as S
    m, md = _column_md()
    smf = next(c for c in S.column_checks("SMF", md, {}) if c["id"] == "smf_column_class")
    assert smf["ok"] is False and smf["value"] == "semi-compact"
    assert smf["governing_combo"] == "1.2DL+0.5LL+2.5EL" and smf["class_without_axial_force"] == "plastic"
    scbf = next(c for c in S.column_checks("SCBF", md, {}) if c["id"] == "scbf_column_plastic")
    assert scbf["ok"] is False and scbf["governing_combo"] == "1.2DL+0.5LL+2.5EL"
    # light axial force: the gate passes and still names the governing record
    m2, md2 = _column_md(ratios=((0.05, "table4", "1.5(DL+LL)"),))
    ok = next(c for c in S.column_checks("SMF", md2, {}) if c["id"] == "smf_column_class")
    assert ok["ok"] is True and ok["governing_combo"] == "1.5(DL+LL)"


def test_1_brace_gates_use_the_table4_records_and_the_axial_compression_row():
    """An I-section brace in compression with no bending takes the 'axial compression' web row (42 eps): NPB600's web
    (52.4 eps) is slender there (OCBF 12.7.2.4 fails), mid-depth semi-compact before; a CHS brace keeps its rows; the
    12.2.3 records are not brace demands (H07)."""
    import india_is800_s12 as S
    import sections as SS
    m = {"id": "B1", "role": "brace", "section": "NPB600X220X107.57", "grade": "E250BR", "L_mm": 5000.0}
    p = SS.props(m["section"])
    md = {"members": [m], "forces": {"B1": [{"combo": "1.5(DL+EL)", "family": "table4", "P_N": 500e3},
                                            {"combo": "1.2DL+0.5LL+2.5EL", "family": "12.2.3", "P_N": 2.0e6}]}}
    sc, rec = S.table2_class_by_combination(m, p, 250.0, md, families=("table4",))
    assert sc["section_class"] == "slender" and rec["web_row"] == "axial compression"
    assert rec["governing_combo"] == "1.5(DL+EL)" and rec["n_records"] == 1
    ocbf = next(c for c in S.brace_member_checks("OCBF", m, md, {}) if c["id"] == "brace_not_slender")
    assert ocbf["ok"] is False and ocbf["web_row"] == "axial compression"
    chs = {"id": "B2", "role": "brace", "section": "CHS168.3X4.8", "grade": "YSt 310", "process": "ERW", "L_mm": 5000.0}
    try:
        pc = SS.props(chs["section"], grade=chs["grade"], process="ERW")
    except KeyError:
        pytest.skip("CHS168.3X4.8 not in the IS 1161 table")
    sc2, rec2 = S.table2_class_by_combination(chs, pc, 310.0, {"forces": {"B2": md["forces"]["B1"]}}, loading="axial")
    assert "do not take the axial force" in rec2["class_basis"]


def test_1_is18168_column_ca_reports_the_governing_combination():
    import india_is800_s12 as S
    import sections as SS
    m, md = _column_md()
    p = SS.props(m["section"])
    Ca, rec = S._ca_governing(m, p, 250.0, md)
    assert Ca == pytest.approx(0.45) and rec["governing_combo"] == "1.2DL+0.5LL+2.5EL"


# ====================================================================================================== 2 (doubler)
_PZ = dict(d_col_mm=400.0, tw_mm=10.0, bf_mm=300.0, tf_mm=20.0, d_beam_mm=500.0, V_design_N=1.2e6, fy_MPa=350.0,
           continuity_plates=True)


def test_2_panel_zone_doubler_at_its_own_fy_never_the_columns():
    """Column web E350 (fy 350): a 12 mm doubler with no grade is E250 (250 MPa, stated); declared E350 -> 350; a 20 mm
    E350 doubler -> 330 (IS 2062:2025 Table 3 >16-40 mm); a declared 350 MPa on a 20 mm plate is capped at 330."""
    import india_is800 as I8
    r0 = I8.panel_zone_check(**_PZ, doubler_t_mm=12.0)
    dbl = next(p for p in r0["plates"] if p["plate"] == "doubler")
    web = next(p for p in r0["plates"] if p["plate"] == "column web")
    assert web["fy_MPa"] == 350.0 and dbl["fy_MPa"] == 250.0
    assert "E250 assumed" in r0["doubler_fy"]["grade_basis"] and "column's fy is not used" in r0["doubler_fy"]["grade_basis"]
    bp = 400.0 - 40.0
    assert r0["Vd_N"] == pytest.approx(bp * (10.0 * 350.0 + 12.0 * 250.0) / math.sqrt(3.0) / 1.1, rel=1e-9)
    r1 = I8.panel_zone_check(**_PZ, doubler_t_mm=12.0, doubler_grade="E350")
    assert next(p for p in r1["plates"] if p["plate"] == "doubler")["fy_MPa"] == 350.0
    r2 = I8.panel_zone_check(**_PZ, doubler_t_mm=20.0, doubler_grade="E350")
    assert next(p for p in r2["plates"] if p["plate"] == "doubler")["fy_MPa"] == 330.0
    r3 = I8.panel_zone_check(**_PZ, doubler_t_mm=20.0, doubler_fy_MPa=350.0)
    assert r3["doubler_fy"]["reduced"] and r3["doubler_fy"]["fy_used_MPa"] == 330.0


def test_2_doubler_required_at_the_doubler_fy():
    import india_is800 as I8
    r = I8.panel_zone_check(**_PZ)
    bp = 360.0
    t250 = (1.2e6 * 1.1 * math.sqrt(3.0) / bp - 10.0 * 350.0) / 250.0          # E250 doubler, <= 16 mm band
    assert r["doubler_required_mm"] == pytest.approx(max(t250, r["t_min_mm"]), rel=1e-6)
    assert r["doubler_required_mm"] > (1.2e6 * 1.1 * math.sqrt(3.0) / bp - 10.0 * 350.0) / 350.0   # not at 350


def test_2_smf_joint_passes_the_declared_doubler_grade():
    import india_is800_s12 as S
    col = {"id": "C1", "role": "column", "section": "NPB600X220X107.57", "grade": "E350BR", "L_mm": 4000.0}
    bm = {"id": "B1", "role": "beam", "section": "NPB500X200X79.36", "grade": "E350BR", "L_mm": 6000.0}
    md = {"members": [col, bm], "forces": {}}
    j = {"id": "J1", "frame_dir": "X", "columns": [{"member_id": "C1", "position": "below"}],
         "beams": [{"member_id": "B1", "L_clear_mm": 5400.0, "V_gravity_N": 50e3}], "continuity_plates": True,
         "doubler_t_mm": 12.0, "connection": {"type": "welded", "weld_type": "cjp"}}
    pz = lambda jj: next(c for c in S.smf_joint_checks(jj, md, {}) if c["id"] == "12.11.2.3_panel_zone")["detail"]
    d0 = pz(j)
    assert next(p for p in d0["plates"] if p["plate"] == "doubler")["fy_MPa"] == 250.0
    d1 = pz(dict(j, doubler_grade="E350"))
    assert next(p for p in d1["plates"] if p["plate"] == "doubler")["fy_MPa"] == 350.0
    assert d1["Vd_N"] > d0["Vd_N"]


# ====================================================================================================== 3 (member wind)
def _cols(spec):
    """[(c, c1, c2, xa, yo, z0, z1)] for wind along X (ax 0) from [(tag, x, y, z0, z1, rel)]."""
    out = []
    for tag, x, y, z0, z1, rel in spec:
        c1, c2 = (x, y, z0), (x, y, z1)
        out.append(({"tag": tag, "rel": rel}, c1, c2, x, round(y, 3), z0, z1))
    return out


_FACES = (("up", 1.0, 1.0), ("down", -0.5, -1.0))


def _scan(cols, env, ax=0):
    import static_model as SM
    r = SM.wall_wind_pieces(cols, env, ax, 1.0, _FACES, 6000.0)
    return {(c["tag"], face): w for (c, c1, c2, face, q, fs, w) in r["pieces"]}, r["record"]


def test_3_piece_under_the_roof_is_not_on_a_wall():
    """Frame plane y = 0 spanning x 0 - 18 m, eave 6.5 m, ridge 8.75 m at x = 9 m; a post at x = 6 m split at the eave.
    Wind along x: the upper piece (6.5 - 8.0 m) is the first column met at its height, but the rafter crosses that
    height at x = 3 m upwind of it -- under the roof, no wall pressure.  The corner pieces keep theirs."""
    cols = _cols([(1, 0.0, 0.0, 0.0, 6500.0, None), (2, 18000.0, 0.0, 0.0, 6500.0, None),
                  (3, 6000.0, 0.0, 0.0, 6500.0, None), (4, 6000.0, 0.0, 6500.0, 8000.0, "J"),
                  (5, 12000.0, 0.0, 0.0, 6500.0, None), (6, 12000.0, 0.0, 6500.0, 8000.0, "J")])
    env = [((0.0, 0.0, 6500.0), (9000.0, 0.0, 8750.0)), ((9000.0, 0.0, 8750.0), (18000.0, 0.0, 6500.0))]
    got, rec = _scan(cols, env)
    assert (1, "up") in got and (2, "down") in got
    assert not any(t in (3, 4, 5, 6) for t, _ in got)
    assert {s["tag"] for s in rec["sheltered"]} == {4, 6}
    got_old, _ = _scan(cols, [])                                  # without the envelope: the old artefact
    assert (4, "up") in got_old and (6, "down") in got_old


def test_3_own_wall_width_of_the_piece_above_the_eave_split():
    """Gable wall x = 0: corner lines y = 0 / 18 m (to the eave), posts y = 6 / 12 m split at the eave, gable rafter in the
    wall plane.  Wind along x: the upper post pieces keep the post's own width 6 m (half to the corner + half to the
    next post), not the 3 m of the pieces present at their height."""
    cols = _cols([(1, 0.0, 0.0, 0.0, 6500.0, None), (2, 0.0, 18000.0, 0.0, 6500.0, None),
                  (3, 0.0, 6000.0, 0.0, 6500.0, None), (4, 0.0, 6000.0, 6500.0, 8000.0, "J"),
                  (5, 0.0, 12000.0, 0.0, 6500.0, None), (6, 0.0, 12000.0, 6500.0, 8000.0, "J")])
    env = [((0.0, 0.0, 6500.0), (0.0, 9000.0, 8750.0)), ((0.0, 9000.0, 8750.0), (0.0, 18000.0, 6500.0))]
    got, rec = _scan(cols, env)
    assert got[(3, "up")] == pytest.approx(6000.0) and got[(4, "up")] == pytest.approx(6000.0)
    assert got[(6, "up")] == pytest.approx(6000.0) and got[(1, "up")] == pytest.approx(3000.0)
    assert {w["tag"] for w in rec["own_wall_width"]} == {4, 6}
    got_old, _ = _scan(cols, [])
    assert got_old[(4, "up")] == pytest.approx(3000.0)


def test_3_lean_to_main_wall_and_setback_tower_keep_their_scan():
    """A lean-to (x 0 - 6 m, flat roof at 4 m) before the main wall x = 6 m (eave 8 m): the main wall above the lean-to
    is still loaded.  A setback tower edge (no roof member in its wall plane above the podium) is not widened.  A
    canopy outside the columns' plan extent shelters nothing."""
    cols = _cols([(1, 0.0, 0.0, 0.0, 4000.0, None), (2, 6000.0, 0.0, 0.0, 4000.0, None),
                  (3, 6000.0, 0.0, 4000.0, 8000.0, None), (4, 24000.0, 0.0, 0.0, 8000.0, None)])
    env = [((-3000.0, 0.0, 3500.0), (0.0, 0.0, 4100.0))]                            # a canopy, outside the extent
    got, rec = _scan(cols, env)
    assert (1, "up") in got and (3, "up") in got and (4, "down") in got and not rec["sheltered"]
    tower = _cols([(1, 0.0, 0.0, 0.0, 4000.0, None), (2, 0.0, 6000.0, 0.0, 4000.0, None),
                   (3, 0.0, 6000.0, 4000.0, 8000.0, None), (4, 0.0, 12000.0, 0.0, 4000.0, None),
                   (5, 0.0, 12000.0, 4000.0, 8000.0, None)])
    got_t, rec_t = _scan(tower, [])
    assert got_t[(3, "up")] == pytest.approx(3000.0) and not rec_t["own_wall_width"]


def _in_ex21_scan(pattern, sign, envelope=True):
    import static_model as SM
    fx = _fixture("IN_Ex21_wall_wind_geometry.json")
    pat = next(p for p in fx["patterns"] if p["name"] == pattern)
    ax = 0 if pat["wind_axis"] == "X" else 1
    oth = 1 - ax
    cols = []
    for c in fx["cols"]:
        c1, c2 = c["c1"], c["c2"]
        cols.append((c, c1, c2, 0.5 * (c1[ax] + c2[ax]), round(0.5 * (c1[oth] + c2[oth]), 3), min(c1[2], c2[2]),
                     max(c1[2], c2[2])))
    faces = (("up", pat["wall_windward_kNm2"], sign), ("down", pat["wall_leeward_kNm2"], -sign))
    env = [tuple(map(tuple, e)) for e in fx["envelope"]] if envelope else []
    r = SM.wall_wind_pieces(cols, env, ax, sign, faces, fx["SY"] if ax == 0 else fx["SX"])
    return fx, pat, {c["tag"]: (face, q, w) for (c, c1, c2, face, q, fs, w) in r["pieces"]}, r["record"]


UPPER = (355, 357, 359, 361)            # IN_Ex21 gable-post pieces above the eave split (z 6.5 - 8.0 m)


@pytest.mark.parametrize("pattern", ["WM0+", "WM0-"])
@pytest.mark.parametrize("sign", [1.0, -1.0])
def test_3_e2e_IN_Ex21_gable_posts_above_the_eave_under_the_across_ridge_wind(pattern, sign):
    """IN_Ex21 (MSME angle-truss shed, span 18 m along Y, 36 m long): on origin/main the upper gable-post pieces e355 /
    e357 / e359 / e361 took the long-wall pressure over half the building length (an 18 m strip; up to 9.3 N/mm on a
    1.5 m piece under WM0-).  The end truss's top chord crosses their height upwind: no wall pressure now; the
    long-wall columns keep theirs."""
    fx, pat, got, rec = _in_ex21_scan(pattern, sign)
    assert not any(t in got for t in UPPER)
    assert {s["tag"] for s in rec["sheltered"]} >= set(UPPER)
    key = pattern + ("" if sign > 0 else "(rev)")
    assert max(fx["origin_main_upper_piece_w_Nmm"][key].values()) > 1.5           # the artefact on origin/main
    walls = [t for t, (face, q, w) in got.items()]
    assert len(walls) == 28                                    # the 14 long-wall column lines x 2 pieces
    _, _, got_old, _ = _in_ex21_scan(pattern, sign, envelope=False)
    assert all(got_old[t][2] == pytest.approx(18000.0) for t in UPPER)


@pytest.mark.parametrize("pattern", ["WM90+", "WM90-"])
def test_3_e2e_IN_Ex21_gable_posts_keep_their_own_width_under_the_along_ridge_wind(pattern):
    """Under the along-ridge wind the gable is the post's own wall: every piece of a post takes the gable pressure over
    the post's own tributary width 6 m (half to the corner column + half to the next post); origin/main gave the upper
    pieces 3 m (the posts are the only columns at their height)."""
    fx, pat, got, rec = _in_ex21_scan(pattern, 1.0)
    for t in UPPER + (354, 356, 358, 360):
        assert got[t][2] == pytest.approx(6000.0), (t, got[t])
    assert {w["tag"] for w in rec["own_wall_width"]} == set(UPPER)
    _, _, got_old, _ = _in_ex21_scan(pattern, 1.0, envelope=False)
    assert all(got_old[t][2] == pytest.approx(3000.0) for t in UPPER)
