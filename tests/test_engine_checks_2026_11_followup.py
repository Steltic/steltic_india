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


def test_R_slender_pd_takes_the_axial_compression_web_limit_IN_Ex1():
    """Lead ruling 1 (2026-11-06) on IN_Ex1 lateral_col-WI862X225X12X8: Pd is the design strength under axial
    compression alone -- the 3.7.2(d) effective area with the 42 eps web -- one value for every combination; the
    'generally' rows decide the combination's class and Md (Ze_eff with 126 eps / (1 + 2 r2)).  D/C 1.063 (the
    review's 'about 1.03' took the r2 web limit for the area as well)."""
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
    pe = r["Pd_effective_section"]
    assert pe["A_eff_mm2"] == pytest.approx(e["A_eff_mm2"], rel=1e-9)                          # Pd: the same Ae
    basis = r["Pd_basis"]
    for k in ("9.3.2.2", "7.1.2", "7.3.2", "3.7.2", "42 eps", "axial compression alone", "one Pd per member",
              "126 eps / (1 + 2 r2)"):
        assert k in basis, k
    assert "not adopted" not in basis and "keeps the gross area" not in basis


def test_R_one_pd_per_member_from_the_class_under_axial_compression_alone():
    """Lead ruling 1, the jump the review found: WI475X220X16X5 (E350, d/tw 88.6 > 42 eps = 35.5) at N = 155 kN had
    P/Pdz 0.0750 with no moment and 0.0643 with a 2 N-m moment (gross area once the combination had a moment).  Now
    Pd is the 42 eps effective-area value in all three combinations (no moment, 2 N-m, a real bending moment), while
    the bending combination keeps its own semi-compact class for Md."""
    import india_is800 as I8
    import sections as S
    lab = "WI475X220X16X5"
    S.register_welded_I(lab, 475, 220, 16, 5)
    mem = {"id": "c", "section": lab, "grade": "E350", "role": "column", "L_mm": 3000.0, "Kz": 1.0, "Ky": 1.0,
           "LLT_sag_mm": 1000.0, "LLT_hog_mm": 1000.0, "c1": 1.0}
    pds, ratios = [], []
    for cf in ({"combo": "N", "P_N": 155.1e3}, {"combo": "N2", "P_N": 155.1e3, "Mz_i_Nmm": 2.0e3, "Mz_j_Nmm": 2.0e3},
               {"combo": "NC", "P_N": 155.1e3, "Mz_i_Nmm": 4.0e8, "Mz_j_Nmm": 4.0e8}):
        r = I8.member_check_is800(mem, [cf])
        pds.append(r["capacities"]["compression"]["Pdz_N"])
        if cf["combo"] == "NC":
            assert r["per_combo"][0]["section_class"] == "semi-compact"          # Md on the combination's class
            assert r["per_combo"][0]["table2"]["web_row"].startswith("generally")
    pe = I8.effective_props_3_7_2d(I8._props(lab), 350.0, welded=True)
    ref = I8.compression_capacity(pe, 350.0, KLz_mm=3000.0, KLy_mm=3000.0, welded=True, section_class="slender")
    assert pds[0] == pytest.approx(pds[1], rel=1e-12) == pytest.approx(pds[2], rel=1e-12)
    assert pds[0] == pytest.approx(ref["Pdz_N"], rel=1e-9)
    gross = I8.compression_capacity(I8._props(lab), 350.0, KLz_mm=3000.0, KLy_mm=3000.0, welded=True,
                                    section_class="semi-compact")
    assert pds[0] < 0.9 * gross["Pdz_N"]                                         # Ae / Ag = 0.857


def test_R_axial_only_checks_take_the_axial_compression_row_too():
    """Finding 8 with ruling 1: compression_capacity's own classification (the truss route, the Section 12 axial
    checks) puts an I web on the 'axial compression' row -- WI475X220X16X5 is slender there (Ae) -- and a welded box
    with plates beyond 42 eps gets its 3.7.2(d) effective area instead of 'not coded'."""
    import india_is800 as I8
    import sections as S
    lab = "WI475X220X16X5"
    S.register_welded_I(lab, 475, 220, 16, 5)
    c = I8.compression_capacity(lab, 350.0, KLz_mm=3000.0, KLy_mm=3000.0, welded=True)
    assert c["section_class_axial"] == "slender" and c["effective_section"]["web_d_eff_axial_mm"] == pytest.approx(
        42.0 * math.sqrt(250.0 / 350.0) * 5.0)
    box = "BOX600X400X10"
    S.register_box(box, 400, 600, 10, 10)                       # B 400, D 600: web 580 / 10, flange 380 / 10
    try:
        pb = I8._props(box)
    except Exception:
        pytest.skip("box registration not available")
    cb = I8.compression_capacity(box, 250.0, KLz_mm=4000.0, KLy_mm=4000.0)
    assert cb["found"] and cb["section_class_axial"] == "slender"
    eb = cb["effective_section"]
    assert eb["web_d_eff_mm"] == pytest.approx(420.0) and eb["flange_b_eff_mm"] == pytest.approx(380.0)
    assert eb["A_eff_mm2"] == pytest.approx(pb["A"] - 2 * (580 - 420) * 10, rel=1e-6)


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


# ====================================================================================================== D-T11 (ruling 2)
def _corner(P=5.0e4, Mz=0.0, My=5.0e6):
    import sections as S
    lab = "WI200X190X12X4"                                    # IN_Ex3 corner column: d/tw 44 > 42 eps = 35.5 (E350)
    S.register_welded_I(lab, 200, 190, 12, 4)
    mem = {"id": "c", "section": lab, "grade": "E350", "role": "column", "L_mm": 3000.0, "Kz": 1.0, "Ky": 1.0,
           "LLT_sag_mm": 3000.0, "LLT_hog_mm": 3000.0}
    return lab, mem, {"combo": "c", "P_N": P, "Mz_i_Nmm": Mz, "Mz_j_Nmm": Mz, "My_i_Nmm": My, "My_j_Nmm": My}


@pytest.mark.parametrize("mz_ratio,row", [(0.0, "axial compression"), (0.04, "axial compression"),
                                          (0.06, "generally")])
def test_DT11_web_row_by_the_major_axis_moment(mz_ratio, row):
    """Steltic ruling D-T11: with axial compression the web takes the 'axial compression' row when |Mz| <= 0.05 Mdz
    (Mdz: the section's 8.2.1.2 strength without axial force), whatever My -- N + My only, N + My + Mz = 0.04 Mdz;
    N + My + Mz = 0.06 Mdz takes the 'generally' rows."""
    import india_is800 as I8
    lab, mem, cf = _corner()
    Mdz = I8.mdz_without_axial_force(lab, 350.0, welded=True)
    cf.update(Mz_i_Nmm=mz_ratio * Mdz, Mz_j_Nmm=mz_ratio * Mdz)
    r = I8.member_check_is800(mem, [cf])
    t2 = r["per_combo"][0]["table2"]
    assert t2["web_row"].startswith(row), t2
    assert ("D-T11" in r["web_class_basis"]) and ("3.7.1" in r["web_class_basis"])
    if row == "axial compression":
        assert t2["section_class"] == "slender" and t2["web_row_basis"].startswith("D-T11")


def test_DT11_tiny_compression_is_not_axial_compression():
    """The 'axial compression' row needs compression above the Table 3 tolerance (p_comp_tol): 0.5 N with My is not."""
    import india_is800 as I8
    lab, mem, cf = _corner(P=0.5)
    assert I8.member_check_is800(mem, [cf])["per_combo"][0]["table2"]["web_row"].startswith("generally")


def test_DT11_section12_gate_and_sizer_screen_use_the_same_rule():
    import india_is800_s12 as S12
    import sections as S
    lab, mem, cf = _corner()
    m = {"id": "C1", "role": "column", "section": lab, "grade": "E350BR", "L_mm": 3000.0}
    md = {"members": [m], "forces": {"C1": [dict(cf, combo="1.2DL+0.5LL+2.5EL", family="12.2.3")]}}
    sc, rec = S12.table2_class_by_combination(m, S.props(lab), 350.0, md)
    assert rec["web_row"] == "axial compression" and sc["section_class"] == "slender"
    assert "D-T11" in rec["web_class_basis"]
    import peb_autosize as PA

    class _Stub:                                            # the sizer's record access, two records of one element
        mem_of_const = {"c": ["m"]}
        el_of_mem = {"m": [1]}
        envt = {1: {"records": {"g": (-5.0e4, 0.0) + (0.0,) * 15, "b": (-5.0e4, 2.0e8) + (0.0,) * 15}}}
    import india_is800 as I8
    cls = PA.LocalModel._class_with_N(_Stub(), "c", S.props(lab), 350.0)
    assert cls == "slender"                                   # the axial-only record (N, no Mz) governs


# ====================================================================================================== review findings
def test_F4_beam_in_span_hogging_reaches_the_member_check():
    """Finding 4: a pinned roof beam under uplift -- ends 0, a sagging peak of 10 kN-m, an in-span hogging peak of
    -80 kN-m: the record carries Mmaj_hog_min and the check takes the hogging sign with LLT_hog (fly braces)."""
    import static_model as SM
    import india_is800 as I8
    import sections as S
    r = [0.0] * len(SM.REC_FIELDS)
    for k, v in (("Mmaj", 80e6), ("Mmaj_sag_max", 10e6), ("Mmaj_hog_min", -80e6), ("Vmaj", 30e3)):
        r[SM.REC_FIELDS.index(k)] = v
    cf = SM.combo_forces_for_member_check({"0.9DL+1.5WM0+": tuple(r)}, "beam")
    assert cf[0]["Mz_mid_hog_Nmm"] == -80e6 and cf[0]["Mz_mid_Nmm"] == 10e6
    lab = "WI450X200X10X6"
    S.register_welded_I(lab, 450, 200, 10, 6)
    mem = {"id": "b", "section": lab, "grade": "E350", "role": "beam", "L_mm": 9000.0, "Kz": 1.0, "Ky": 1.0,
           "LLT_sag_mm": 1500.0, "LLT_hog_mm": 4500.0}
    res = I8.member_check_is800(mem, cf)
    chk = {c["moment_sign"]: c for c in res["per_combo"][0]["checks"] if c.get("moment_sign")}
    assert res["per_combo"][0]["Mz_hog_Nmm"] == pytest.approx(80e6) and chk["hogging"]["LLT_mm"] == 4500.0
    assert chk["hogging"]["dc"] > chk["sagging"]["dc"]


def test_F5_web_strip_with_a_doubler_at_its_own_fy():
    import peb_checks as PC
    f = PC.column_web_strip_fy({"tw": 8.0}, 350.0, 6.0, {})
    assert f == pytest.approx((8.0 * 350.0 + 6.0 * 250.0) / 14.0)
    assert PC.column_web_strip_fy({"tw": 8.0}, 350.0, 0.0, {}) == 350.0


def test_F6_rod_and_sizer_web_fy_from_the_band():
    import peb_levers as PL
    import peb_autosize as PA
    import sections as S
    assert PL.rod_fy(16) == 250.0 and PL.rod_fy(20) == 240.0 and PL.rod_fy(36) == 240.0
    assert PL.rod_tension_check(24, 1.0)["Tdg_N"] == pytest.approx(math.pi * 24 ** 2 / 4 * 240.0 / 1.1, rel=1e-9)
    S.register_welded_I("WI600X250X20X8", 600, 250, 20, 8)
    assert PA.member_web_fy("WI600X250X20X8") == 330.0           # E350, 20 mm flange: the > 16 - 40 mm band
    assert PA.member_web_fy("WI600X250X20X8", "E250") == 240.0


def test_F12_different_column_LLT_sag_and_hog_are_rejected():
    import design_pipeline as DP
    cfg = {"member_overrides": {"col:WI400X200X12X6": {"LLT_sag_mm": 1500.0, "LLT_hog_mm": 3000.0}}}
    with pytest.raises(ValueError, match="not a flange"):
        DP.member_override(cfg, 7, "col", "WI400X200X12X6", "lateral_col")
    ok, _ = DP.member_override({"member_overrides": {"col:WI400X200X12X6": {"LLT_sag_mm": 2000.0,
                                                                            "LLT_hog_mm": 2000.0}}},
                               7, "col", "WI400X200X12X6", "lateral_col")
    assert ok["LLT_sag_mm"] == 2000.0
    beam, _ = DP.member_override({"member_overrides": {"beam:WI400X200X12X6": {"LLT_sag_mm": 1500.0,
                                                                              "LLT_hog_mm": 3000.0}}},
                                 7, "beam", "WI400X200X12X6", "roof")
    assert beam["LLT_hog_mm"] == 3000.0                          # beams keep their two flanges


# ====================================================================================================== 1, 2 on gold pieces
def _s12_fixture(name):
    import re
    import sections as S
    fx = _fixture(name)
    for m in fx.get("members") or [fx.get("member")]:
        g = re.match(r"BOX(\d+)X(\d+)X(\d+)$", m["section"])
        if g:                                                   # the gold cfgs register their square boxes
            S.register_box(m["section"], float(g.group(2)), float(g.group(1)), float(g.group(3)), float(g.group(3)))
    return fx


def test_1_e2e_IN_Ex13_scbf_column_gate_with_the_12_2_3_axial_force():
    """IN_Ex13 SCBF column e1 (WPB260X260X114.4, E250 B0), its 125 captured force records: the 12.8.4.1 gate is now
    classified with each record's N; the governing record is the 12.2.3 row 1.2DL+0.5LL-2.5EQ_Y[eb]+0.3EQ_Z[col]
    (N = 1,020 kN, small Mz: D-T11 puts the web on the 'axial compression' row, 42 eps); d/tw 14.2 is well inside,
    so the column stays plastic -- on origin/main the gate read the N = 0 class only."""
    import india_is800_s12 as S12
    fx = _s12_fixture("IN_Ex13_scbf_column_e1_s12.json")
    md = {"members": [fx["member"]], "forces": fx["forces"]}
    r = next(c for c in S12.column_checks(fx["system"], md, fx["cfg"]) if c["id"] == "scbf_column_plastic")
    assert r["ok"] is True and r["value"] == "plastic" and r["n_records"] == 125
    assert r["governing_family"] == "12.2.3" and r["governing_combo"] == "1.2DL+0.5LL-2.5EQ_Y[eb]+0.3EQ_Z[col]"
    assert r["governing_P_N"] == pytest.approx(1020268.0, rel=1e-6) and r["web_row"] == "axial compression"
    assert r["web_limits"][2] == pytest.approx(42.0 * math.sqrt(250.0 / 240.0))          # E250, flange > 16 mm: 240


@pytest.mark.parametrize("name,t_dbl,fy_dbl,fy_col", [("IN_Ex12_smf_joint_J100000-X.json", 48.0, 230.0, 240.0),
                                                      ("IN_Ex18_smf_joint_J100000-X.json", 15.0, 250.0, 230.0)])
def test_2_e2e_gold_panel_zone_doubler_at_its_own_band(name, t_dbl, fy_dbl, fy_col):
    """Two gold SMF joints with a declared doubler and no doubler grade: IN_Ex12 J100000-X (BOX450X450X25 column at
    240 MPa, a 48 mm doubler -> E250 > 40 mm band 230 MPa) and IN_Ex18 J100000-X (BOX800X800X45 at 230 MPa, a 15 mm
    doubler -> 250 MPa).  origin/main took the column's fy for the doubler: the panel resistance now differs by
    bp t_dbl (fy_col - fy_dbl) / (sqrt3 gamma_m0), down for IN_Ex12, up for IN_Ex18."""
    import india_is800_s12 as S12
    fx = _s12_fixture(name)
    md = {"members": fx["members"], "forces": fx["forces"]}
    pz = next(c for c in S12.smf_joint_checks(fx["joint"], md, fx["cfg"], system="SMF") if c["id"] == "12.11.2.3_panel_zone")
    d = pz["detail"]
    dbl = next(p for p in d["plates"] if p["plate"] == "doubler")
    assert dbl["t_mm"] == t_dbl and dbl["fy_MPa"] == fy_dbl
    assert all(p["fy_MPa"] == fy_col for p in d["plates"] if p["plate"].startswith("column web"))
    assert "E250 assumed" in d["doubler_fy"]["grade_basis"]
    bp = d["bp_mm"]
    Vd_main = d["Vd_N"] + bp * t_dbl * (fy_col - fy_dbl) / math.sqrt(3.0) / 1.1      # the doubler at the column fy
    assert (d["Vd_N"] < Vd_main) == (fy_dbl < fy_col)
    assert pz["dc"] == pytest.approx(max(d["DC_shear"], d["t_min_mm"] / float(d["inputs"]["tw_mm"])), rel=1e-9)
