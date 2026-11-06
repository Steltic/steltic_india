"""Engine checks fix (2026-11, branch fix/2026-11-engine-checks): the three gaps of the PEB golds review
(/home/claude/briefs/PEB_REVIEW.md A, B, C) and two small items, each with unit tests and an end-to-end test on a real
gold piece (fixtures in tests/fixtures/engine_checks_2026_11/, captured from the gold runs on the origin/main engine).

A. Member checks saw a ranked subset of the combinations (top 3 by |N|, |Mmaj|, |Mmin|, |V| and the 3 most
   compressive) that ignored the sign of the moment, so the governing combination of the other sign (another
   compression flange, another LTB length) could be dropped.  Every combination is checked now.
B. The Table 2 web class was found with P = 0 (and P = 1 N for the axial terms): the 'generally' web rows with the
   actual r1 / r2 were never used.  The class is found per combination with its axial force, and the capacities follow
   the class (plastic / compact Zp, semi-compact Ze, slender: 3.7.2(d) effective section with the web limit of the
   combination).
C. One IS 2062 (Part 1):2025 Table 3 band function (india_is800.fy_is2062) for every fy taken from a thickness: the
   PEB sizer's plate_fy (250 / 350 MPa up to 20 mm before), the knee stiffeners / doubler, the fly braces, the crane
   bracket.
Small: a gable wind column (wind post) takes Ka of its own tributary area (IS 875-3 7.2.2.1 (b)); the minor-axis
base-plate call keeps the plate-outline gate.
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


def _old_top_records(recs, k=12):
    """The member-check filter of origin/main 41fb2f7 (design_pipeline._top_records), kept here to show what it drops."""
    import static_model as SM
    if len(recs) <= k:
        return recs
    keep = set()
    for idx in range(4):
        keep |= set(sorted(recs, key=lambda l: -abs(recs[l][idx]))[: max(3, k // 4)])
    span_idx = [SM.REC_FIELDS.index(f) for f in ("Mmaj_span", "Mmin_span", "Mmaj_free", "Mmin_free")]
    keep |= {l for l, r in recs.items() if any(len(r) > i and r[i] for i in span_idx)}
    keep |= set(sorted(recs, key=lambda l: recs[l][0])[:3])
    return {l: recs[l] for l in sorted(keep, key=list(recs).index)}


def _rec(**kw):
    import static_model as SM
    r = [0.0] * len(SM.REC_FIELDS)
    for k, v in kw.items():
        r[SM.REC_FIELDS.index(k)] = float(v)
    return r


def _register(*labels):
    """Register the welded / tapered PEB labels of a fixture (peb_build.ensure, as the sizer does)."""
    import peb_build as PB
    for lab in labels:
        if lab:
            PB.ensure(lab)


# ====================================================================================================== A
def test_A_member_check_records_keep_every_combination_in_order():
    import design_pipeline as DP
    recs = {"c%02d" % k: _rec(N=-1e3 * k, Mmaj=1e4 * k, Mmaj_i=1e4 * k) for k in range(40)}
    got = DP.member_check_records(recs)
    assert list(got) == list(recs) and got == recs
    assert DP._top_records(recs) == recs                     # the old name keeps working, with every combination


def test_A_hogging_combination_ranked_out_by_sagging_cases_governs():
    """A canopy-like beam: three uplift (sagging) cases with the largest |M| and a gravity hogging set.  The flange
    held by the purlins (sagging, LLT 1.5 m) is not the one in compression under hogging (fly braces at 6 m): the
    largest hogging case must be checked with LLT_hog even though it is only 4th by |M|."""
    import design_pipeline as DP
    recs = {}
    for k, M in enumerate((3.3e8, 3.2e8, 3.1e8)):                       # uplift: sagging, larger |M|
        recs["UPL%d" % k] = _rec(Mmaj=M, Mmaj_i=M, Mmaj_j=0.4 * M, V=1e5)
    recs["1.5DL+1.5LL"] = _rec(N=-1.0, Mmaj=2.35e8, Mmaj_i=-2.35e8, Mmaj_j=-0.5e8, V=2.2e5)   # most 'compressive'
    recs["1.2DL+1.2LL+1.2WM0+"] = _rec(Mmaj=2.85e8, Mmaj_i=-2.85e8, Mmaj_j=-0.6e8, V=0.9e5)  # the largest hogging
    for k in range(12):                                                  # other cases: small, tension
        recs["G%02d" % k] = _rec(N=1e3 * (k + 1), Mmaj=1e7, Mmaj_i=-1e7, V=1e4)
    old = _old_top_records(recs)
    assert "1.2DL+1.2LL+1.2WM0+" not in old                              # what origin/main dropped
    mem = {"id": "e1", "section": "MB450", "grade": "E250", "role": "beam", "L_mm": 4000.0, "Kz": 1.0, "Ky": 1.0,
           "LLT_sag_mm": 1500.0, "LLT_hog_mm": 6000.0}
    r = DP.member_checks_is800({}, {"member": mem, "kind": "beam", "records": recs})
    assert r["interaction_governing_combo"] == "1.2DL+1.2LL+1.2WM0+"
    gov = next(p for p in r["per_combo"] if p["combo"] == r["interaction_governing_combo"])
    ia = max((c for c in gov["checks"] if c.get("moment_sign")), key=lambda c: c["dc"])
    assert ia["moment_sign"] == "hogging" and ia["LLT_mm"] == 6000.0      # the fly-brace length, not the purlins'
    import india_is800 as I8
    import static_model as SM
    r_old = I8.member_check_is800(mem, SM.combo_forces_for_member_check(old, "beam"))
    assert r["interaction_dc"] > 1.1 * r_old["interaction_dc"]


def test_A_free_span_moment_of_either_sign_and_both_LTB_lengths():
    """A column with a uniform span load whose free moment changes sign between combinations (pressure / suction):
    each sign is checked with its own LTB length, and both combinations are seen."""
    import design_pipeline as DP
    recs = {"WP": _rec(N=-5e4, Mmaj_free=4e7, Mmaj_span=4e7), "WS": _rec(N=-5e4, Mmaj_free=-4e7, Mmaj_span=-4e7)}
    for k in range(20):
        recs["G%02d" % k] = _rec(N=-(2e4 + 1e3 * k), Mmaj=5e6, Mmaj_i=5e6, Mmaj_j=-5e6)
    mem = {"id": "e2", "section": "MB300", "grade": "E250", "role": "column", "L_mm": 6000.0, "Kz": 1.0, "Ky": 1.0,
           "LLT_sag_mm": 1500.0, "LLT_hog_mm": 6000.0, "sway": False}
    r = DP.member_checks_is800({}, {"member": mem, "kind": "col", "records": recs})
    by = {p["combo"]: p for p in r["per_combo"]}
    assert set(by) == set(recs)
    sw = [c for c in by["WS"]["checks"] if c.get("moment_sign")]
    assert [c["moment_sign"] for c in sw] == ["hogging"] and sw[0]["LLT_mm"] == 6000.0
    assert r["interaction_governing_combo"] == "WS"


def test_A_e2e_IN_Ex2_canopy_root_hogging_case_governs_at_1_21():
    """IN_Ex2 (PEB sandbox gold, cdfc027 inputs, origin/main analysis): the canopy root element e483
    (roof-WI408X190X12X5).  origin/main checked 6 of its 141 combinations and reported 1.000 (1.5DL+1.5LL, hogging
    -235 kN-m); every combination gives about 1.21 under 1.2DL+1.2LL+1.2WM0 (hogging -285 kN-m), as the review's
    diagnostic run found (PEB_REVIEW.md A)."""
    import design_pipeline as DP
    fx = _fixture("IN_Ex2_canopy_root_e483.json")
    _register(fx["member"]["section"], fx["member"].get("buckling_section"), *fx["stations"])
    mem, recs = fx["member"], fx["records"]
    r = DP.member_checks_is800({}, {"member": mem, "kind": fx["kind"], "records": recs})
    r = DP.peb_station_checks({}, mem, fx["kind"], recs, r, tuple(fx["stations"]))
    assert r["dc"] == pytest.approx(1.211, abs=0.01)
    assert r["governing_combo"].startswith("1.2DL+1.2LL+1.2WM0")
    old = _old_top_records(recs)
    assert len(old) < len(recs) and not any(l.startswith("1.2DL+1.2LL+1.2WM0") for l in old)


# ====================================================================================================== B
def _wi(D, B, tf, tw):
    import sections as S
    lab = "WI%dX%dX%dX%d" % (D, B, tf, tw)
    S.register_welded_I(lab, D, B, tf, tw)
    return lab


def test_B_table2_web_rows_with_the_actual_axial_force():
    """WI475X220X16X5, fy 350 (IN_Ex3 column): d/tw = 443/5 = 88.6.  N = 155.1 kN gives r1 = (N/(d tw))/(fy/1.1) =
    0.220 and the compact limit 105 eps/(1 + 1.5 r1) = 66.7 (review); the web is semi-compact (126 eps/(1 + 2 r2) =
    95.5 > 88.6), compact with N = 0 (105 eps = 88.74)."""
    import india_is800 as I8
    lab = _wi(475, 220, 16, 5)
    s0 = I8.section_class_table2(lab, 350.0)
    assert s0["web_row"] == "neutral axis at mid-depth" and s0["web_class"] == "compact"
    s1 = I8.section_class_table2(lab, 350.0, P_N=155.1e3)
    eps = math.sqrt(250.0 / 350.0)
    assert s1["r1"] == pytest.approx(155.1e3 / (443.0 * 5.0) / (350.0 / 1.1), rel=1e-9)
    assert s1["r1"] == pytest.approx(0.220, abs=0.001)
    assert s1["web_limits"][1] == pytest.approx(105.0 * eps / (1 + 1.5 * s1["r1"]), rel=1e-9)
    assert s1["web_limits"][1] == pytest.approx(66.7, abs=0.1)
    assert s1["web_class"] == "semi-compact" and s1["section_class"] == "semi-compact"
    assert s1["web_row"] == "generally, r1 positive"


def test_B_table2_tension_rows_and_no_limit_beyond_the_denominator():
    """Tension: r1 negative ('generally, if r1 is negative': 84e/(1+r1), 105e/(1+r1), 126e/(1+2r2)) -- the limits
    rise; with r1 <= -1 (or r2 <= -1/2) the row sets no limit (the web is not a compression element)."""
    import india_is800 as I8
    lab = _wi(600, 200, 12, 4)                                # d/tw = 144: slender at N = 0
    assert I8.section_class_table2(lab, 250.0)["section_class"] == "slender"
    A = 2 * 200 * 12 + 576 * 4
    T = 0.4 * A * 250.0 / 1.1                                 # r2 = -0.4
    st = I8.section_class_table2(lab, 250.0, P_N=-T)
    assert st["r1"] < 0 and st["web_row"] == "generally, r1 negative"
    assert st["web_limits"][2] == pytest.approx(126.0 / (1 - 0.8), rel=1e-6)      # 630 eps: semi-compact web
    assert st["web_class"] in ("plastic", "compact", "semi-compact")
    big = I8.section_class_table2(lab, 250.0, P_N=-1.2 * 576 * 4 * 250.0 / 1.1)   # r1 = -1.2
    web = next(e for e in big["elements"] if e.get("web_row"))
    assert "plastic" in web["no_limit"] and web["limits"][0] is None and web["class"] == "plastic"
    json.dumps(big)                                           # JSON-safe (no Infinity)


def test_B_axial_compression_row_without_major_axis_moment():
    """The 'axial compression' row (semi-compact 42 eps; plastic / compact 'Not applicable') applies to a combination
    with axial compression and no major-axis moment: d/tw above 42 eps is slender; below it the web does not limit
    the class (the flanges do)."""
    import india_is800 as I8
    lab = _wi(300, 200, 12, 5)                                # d/tw = 55.2 > 42 (E250)
    r = I8.section_class_table2(lab, 250.0, P_N=1e5, axial_only=True)
    assert r["web_row"] == "axial compression" and r["web_class"] == "slender"
    assert I8.section_class_table2(lab, 250.0, P_N=1e5)["section_class"] != "slender"   # with a moment: generally
    lab2 = _wi(300, 200, 12, 8)                               # d/tw = 34.5 <= 42
    r2 = I8.section_class_table2(lab2, 250.0, P_N=1e5, axial_only=True)
    assert r2["web_class"] == "plastic" and r2["section_class"] == "plastic"           # not downgraded


def test_B_member_check_classifies_each_combination_and_capacity_follows():
    """Same moment, two axial forces: the compression combination is semi-compact (Ze, 9.3.1.3), the zero-axial one
    compact (Zp) -- the capacities follow each combination's class."""
    import india_is800 as I8
    lab = _wi(475, 220, 16, 5)
    mem = {"id": "c", "section": lab, "grade": "E350", "role": "column", "L_mm": 3000.0, "Kz": 1.0, "Ky": 1.0,
           "LLT_sag_mm": 1000.0, "LLT_hog_mm": 1000.0, "c1": 1.0}
    cf = [{"combo": "N0", "P_N": 0.0, "Mz_i_Nmm": 4.0e8, "Mz_j_Nmm": 4.0e8},
          {"combo": "NC", "P_N": 155.1e3, "Mz_i_Nmm": 4.0e8, "Mz_j_Nmm": 4.0e8}]
    r = I8.member_check_is800(mem, cf)
    by = {p["combo"]: p for p in r["per_combo"]}
    assert by["N0"]["section_class"] == "compact" and by["NC"]["section_class"] == "semi-compact"
    ia = {k: next(c for c in by[k]["checks"] if c.get("moment_sign")) for k in by}
    p = I8._props(lab)
    Mdz_N0 = ia["N0"]["Mdz_LTB_Nmm"]
    Mdz_NC = ia["NC"]["Mdz_LTB_Nmm"]
    assert Mdz_NC / Mdz_N0 == pytest.approx(p["Sx"] / p["Zx"], rel=0.02)            # Ze against Zp (chi_LT ~ 1)
    assert r["section_class_by_combination"] == {"compact": 1, "semi-compact": 1}
    assert r["capacities"]["section_class"]["section_class"] == "semi-compact"       # the governing combination's


def test_B_slender_web_effective_section_takes_the_web_limit_of_the_combination():
    """3.7.2(d): the bending effective section keeps 126 eps / (1 + 2 r2) tw of the web for the combination's N
    (126 eps tw before), so the effective modulus falls with the axial force."""
    import india_is800 as I8
    lab = _wi(862, 225, 12, 8)                                # d/tw = 104.75 (IN_Ex1 column)
    fy = 350.0
    eps = math.sqrt(250.0 / fy)
    e0 = I8.effective_section_3_7_2d(lab, fy, welded=True)
    lim = 126.0 * eps / (1 + 2 * 0.0515)
    e1 = I8.effective_section_3_7_2d(lab, fy, welded=True, web_dt_limit=lim)
    assert e0["web_d_eff_bending_mm"] == pytest.approx(min(838.0, 126.0 * eps * 8.0))
    assert e1["web_d_eff_bending_mm"] == pytest.approx(lim * 8.0) and e1["Ze_eff_mm3"] < e0["Ze_eff_mm3"]
    assert e1["A_eff_mm2"] == pytest.approx(e0["A_eff_mm2"])                           # axial: 42 eps either way
    assert I8.section_class_table2(lab, fy, P_N=0.0515 * I8._props(lab)["A"] * fy / 1.1)["section_class"] == "slender"


@pytest.mark.parametrize("fixture,low,high,combo_prefix", [
    ("IN_Ex3_column_WI475X220X16X5.json", 1.06, 1.09, None),
    ("IN_Ex2_wind_column_WI400X220X20X4.json", 1.03, 1.07, None),
    ("IN_Ex1_main_column_WI862X225X12X8.json", 1.05, 1.08, None),
])
def test_B_e2e_gold_columns_with_the_actual_axial_force(fixture, low, high, combo_prefix):
    """The three gold columns of the review (PEB_REVIEW.md B), on their captured origin/main demands and every
    combination: IN_Ex3 lateral_col-WI475X220X16X5 0.994 -> 1.075 (semi-compact web: Ze; review 1.074); IN_Ex2 wind
    column WI400X220X20X4 0.993 -> 1.050 (review about 1.05); IN_Ex1 lateral_col-WI862X225X12X8 0.996 -> 1.063
    (slender web: the engine's 3.7.2(d) section -- axial area with the 42 eps web, bending modulus with the r2 web
    limit; the review's 'about 1.03' is one effective section with the r2 limit for both terms, see CHANGES).
    origin/main's own D/C on the same records is stored in the fixture."""
    import design_pipeline as DP
    fx = _fixture(fixture)
    _register(fx["member"]["section"], fx["member"].get("buckling_section"), *(fx.get("stations") or []))
    mem, recs = fx["member"], fx["records"]
    r = DP.member_checks_is800({}, {"member": mem, "kind": fx["kind"], "records": recs})
    if fx.get("stations"):
        r = DP.peb_station_checks({}, mem, fx["kind"], recs, r, tuple(fx["stations"]))
    assert fx["dc_origin_main"] < 1.0
    assert low <= r["dc"] <= high, (r["dc"], r.get("governing_combo"))
    g = next(p for p in r["per_combo"] if p["combo"] == r.get("interaction_governing_combo", r["governing_combo"])) \
        if r.get("per_combo") else None
    if g is not None:
        assert g["table2"]["web_row"].startswith("generally")


# ====================================================================================================== C
def test_C_one_band_function_IS2062_2025_Table3():
    import india_is800 as I8
    assert [I8.fy_is2062("E250", t) for t in (10, 16, 16.5, 18, 20, 40, 41, 100, 101)] == \
        [250, 250, 240, 240, 240, 240, 230, 230, 210]
    assert [I8.fy_is2062("E350", t) for t in (16, 18, 20, 40, 63, 120)] == [350, 330, 330, 330, 320, 290]
    assert I8.fy_is2062("IS 2062 E250 B0", 18.0) == 240.0
    with pytest.raises(ValueError):
        I8.fy_is2062(None, 10.0)


def test_C_sizer_plate_fy_follows_the_band():
    """peb_autosize.plate_fy (it writes fy_plate_MPa into the cfgs the full runs judge) gave 250 / 350 MPa up to
    20 mm; IS 2062 Table 3 gives 240 / 330 above 16 mm."""
    import peb_autosize as PA
    import india_is800 as I8
    for g in ("E250", "E350", "E250 B0"):
        for t in (8, 16, 18, 20, 25, 40, 45, 65):
            assert PA.plate_fy(t, g) == I8.fy_is2062(g, t)
    assert PA.plate_fy(18, "E250") == 240.0 and PA.plate_fy(20, "E350") == 330.0
    assert PA.plate_fy(20, None) == 240.0


def test_C_plate_fy_band_declared_capped_and_undeclared_from_the_table():
    import india_connections as C
    assert C.plate_fy_band(18.0, "E250")[0] == 240.0                     # undeclared: the table, not 250
    assert C.plate_fy_band(12.0, None)[0] == 250.0                       # no grade: E250 (the old default's grade)
    fy, rec = C.plate_fy_band(18.0, "E250", fy_MPa=250.0)
    assert fy == 240.0 and rec["reduced"]
    assert C.plate_fy_band(18.0, "E250", fy_MPa=230.0)[0] == 230.0       # a lower declared value is kept
    assert C.plate_fy_band(None, "E250", fy_MPa=250.0)[0] == 250.0       # no thickness: the declared value


def test_C_knee_stiffener_and_doubler_fy_from_the_band():
    import peb_checks as PC
    cfg = {"plate_grade": "E250", "steel_grade": "E350"}
    assert PC._stiffener_fy({"t_mm": 18.0, "fy_MPa": 250.0}, cfg, "s") == 240.0
    assert PC._stiffener_fy({"t_mm": 18.0}, cfg, "s") == 240.0
    assert PC._stiffener_fy({"t_mm": 12.0}, cfg, "s") == 250.0
    assert PC._stiffener_fy({"doubler_t_mm": 6.0}, cfg, "d", t_key="doubler_t_mm", fy_key="doubler_fy_MPa",
                            grade_key="doubler_grade") == 250.0


def test_C_crane_bracket_fy_from_the_band():
    """crane_bracket: a 20 mm-flange E250 bracket declared at 250 MPa is checked at 240 MPa (IS 2062 Table 3, > 16 mm),
    its 18 mm stiffeners too; undeclared, the band value (was 250 MPa whatever the thickness)."""
    import crane_bracket as CB
    import sections as S
    from test_first_wave_2026_10 import CRANE
    S.register_welded_I("WI600X250X20X10", 600, 250, 20, 10, source="test")
    S.register_welded_I("WI550X250X16X8", 550, 250, 16, 8, source="test")
    br = {"section": "WI600X250X20X10", "projection_mm": 475.0, "rail_height_mm": 600.0, "dead_N": 9500.0,
          "weld_leg_mm": 8.0, "column_section": "WI550X250X16X8", "column_fy_MPa": 350.0, "fy_MPa": 250.0,
          "column_stiffeners": {"b_mm": 115, "t_mm": 18, "n": 2, "fy_MPa": 250}}
    for fy_decl in (250.0, None):
        b = dict(br, fy_MPa=fy_decl)
        r = CB.bracket_record({"crane": dict(CRANE, bracket=b), "plate_grade": "E250", "steel_grade": "E350"})
        sh = next(c for c in r["checks"] if c["name"].startswith("bracket web shear"))
        assert sh["limit"] == pytest.approx(240.0 / (math.sqrt(3.0) * 1.10), rel=1e-9)
        cw = next(c for c in r["checks"] if c["name"].startswith("column web opposite"))
        assert "%.0f kN" % (2 * 115 * 18 * 240.0 / 1.10 / 1e3) in cw["cite"]


def _knee(fx, cfg):
    import peb_checks as PC
    import peb_build as PB
    reg = {int(k): tuple(v) for k, v in fx["reg"].items()}
    envt = {int(k): v for k, v in fx["envt"].items()}
    _register(*[v[1] for v in reg.values()])
    for j in fx["joints"]:
        for c in (j.get("columns") or []) + (j.get("beams") or []):
            if c.get("face_section"):
                _register(c["face_section"])
    orig = PB.element
    PB.element = lambda t: True if int(t) in reg else orig(t)
    try:
        recs = PC.knee_records(cfg, None, fx["joints"], reg, envt, fx["system"], fx["s12_cfg"])
    finally:
        PB.element = orig
    r = max(recs, key=lambda x: x.get("DC") or 0)
    st = next(c for c in r["checks"] if c["name"].startswith("column stiffeners at the rafter flange levels"))
    return r, st


def test_C_e2e_IN_Ex3_knee_stiffeners_and_doubler_at_their_plate_fy():
    """IN_Ex3 (PEB sandbox gold) knee, captured inputs and demand.  The column stiffeners at the rafter flange levels
    (IS 800 8.7.4) carry the flange force with the 18 mm E250 stiffener pair and the column web + 6 mm E250 web doubler
    over the bearing length b = t_fb + 5 (t_fc + s).  origin/main: 1.024 with the cfg's 240 MPa stiffeners (the
    doubler at the column's 350 MPa); with the 250 MPa the cfg declared at cdfc027 (old helper) origin/main gave
    1.000 (review C).  Now the doubler is at its own 250 MPa and a declared 250 MPa stiffener is capped at 240."""
    import copy
    fx = _fixture("IN_Ex3_knee.json")
    r, st = _knee(fx, fx["cfg"])
    old = fx["result"][0]
    assert old["DC"] == pytest.approx(1.024, abs=0.003)
    assert "doubler 6 mm x 250" in st["cite"] and r["DC"] == pytest.approx(st["dc"])
    assert r["DC"] > 1.08
    cfg250 = copy.deepcopy(fx["cfg"])
    cfg250["connections"]["knee_panel"]["flange_stiffener"]["fy_MPa"] = 250.0      # the cdfc027 declaration
    r2, st2 = _knee(fx, cfg250)
    assert st2["limit"] == pytest.approx(st["limit"], rel=1e-9)                       # capped at the 240 MPa band


# ====================================================================================================== small items
def test_wind_post_ka_factor_own_tributary_area():
    """IS 875-3 7.2.2.1 (b): a wind post (gable wind column) is a beam-type element -- Ka of span x spacing.  IN_Ex3:
    frame 7.5 x 10 = 75 m2 (Ka 0.833), wind column 6.0 m x 11.2 m = 67.2 m2 (Ka 0.844): +1.3 %."""
    import static_model as SM
    import india_wind_tables as WT
    ka_f = WT.ka_for_area_m2(75.0)["Ka"]
    pz = 1.0
    ws = {"Kd": 0.9, "Kc": 1.0, "pz_kNm2": pz, "Ka": round(ka_f, 4), "Ka_basis": "frame_tributary", "Ka_area_m2": 75.0,
          "pd_kNm2": round(0.9 * ka_f * pz, 4)}
    k = SM.wind_post_ka_factor(ws, 6.0 * 11.2)
    ka_c = WT.ka_for_area_m2(67.2)["Ka"]
    assert k["applied"] and k["factor"] == pytest.approx(ka_c / round(ka_f, 4), rel=1e-6)
    assert k["factor"] == pytest.approx(1.013, abs=0.002)
    assert SM.wind_post_ka_factor(ws, 150.0)["factor"] == pytest.approx(0.8 / round(ka_f, 4), rel=1e-6)  # larger area
    low = dict(ws, pz_kNm2=1.0, Kd=0.75)                       # 0.7 pz floor: both pd at the floor -> factor 1
    low["pd_kNm2"] = round(max(0.75 * ka_f, 0.7), 4)
    assert SM.wind_post_ka_factor(low, 20.0)["factor"] == pytest.approx(max(0.75 * 0.9333, 0.7) / 0.7, rel=1e-3)
    assert not SM.wind_post_ka_factor({"pd_kNm2": 0.4}, 20.0)["applied"]
    assert not SM.wind_post_ka_factor(dict(ws, Ka_basis="element_tributary"), 20.0)["applied"]


def test_wind_post_columns_are_the_pinned_top_lines():
    import static_model as SM
    mk = lambda t, rel, z0, z1, x=0.0, y=0.0: ({"tag": t, "rel": rel}, None, None, x, y, z0, z1)
    cols = [mk(1, None, 0, 5000, 0, 0), mk(2, "J", 5000, 11000, 0, 0),         # a wind post in two pieces
            mk(3, None, 0, 10000, 0, 6000)]                                   # a frame column
    p = SM._wind_post_columns(cols)
    assert set(p) == {1, 2} and p[1]["H_mm"] == 11000


def test_base_plate_minor_axis_outline_gate_fails_loudly():
    """A plate narrower than 0.95 bf about the minor axis (B < 0.95 bf, the swapped outline of the y call) is a
    failing gate 'y:geometry_plate_outline', not a zero compression-side plate moment."""
    import india_connections as C
    kw = dict(P_N=300e3, Mz_Nmm=20e6, My_Nmm=15e6, V_N=10e3, B_mm=230.0, L_mm=600.0, t_plate_mm=25.0, fy_plate_MPa=240.0,
              fck_MPa=25.0, col_d_mm=400.0, col_bf_mm=250.0, col_tf_mm=12.0, plate_grade="E250",
              anchors={"n_total": 4, "n_tension": 2, "d_mm": 24, "grade": "4.6", "f_mm": 225.0, "f_y_mm": 80.0,
                       "n_tension_y": 2})
    r = C.base_plate_design_biaxial(**kw)
    g = r["checks"].get("y:geometry_plate_outline")
    assert g is not None and g["ok"] is False and g["gate"] is True
    assert r["ok"] is not True                                # failing (or not evaluable), never passing
    ok = C.base_plate_design_biaxial(**dict(kw, B_mm=300.0))
    assert "y:geometry_plate_outline" not in ok["checks"]


def test_wind_post_e2e_gable_wind_column_carries_its_own_Ka(tmp_path):
    """Pipeline run of the small PEB shed (tests/_peb_fixture.py) with a wind summary on the frame basis (Ka 1.0 at
    10 m2, so pd = Kd Ka Kc pz = 0.40): the gable wind column (6.0 m tributary x 6.6 m span = 39.6 m2, Ka 0.880) carries
    q x 0.880 / 1.0 -- its span moment is 1.5 q Ka_post SY L^2 / 8, and the package records the factor."""
    pytest.importorskip("openseespy.opensees")
    import pipeline as P
    import india_wind_tables as WT
    from _peb_fixture import mini_peb_cfg, stage_rag, SY, W_COL
    os.environ["STELTIC_TEST_JOBS"] = str(tmp_path)
    os.environ["STEEL_BUILDER_JOBS"] = str(tmp_path)
    cfg = mini_peb_cfg("peb_windpost")
    ws = cfg["load_plan"]["wind_summary"]
    ws.update(Kc=1.0, Ka=1.0, Ka_basis="frame_tributary", Ka_area_m2=10.0, pz_kNm2=round(0.40 / 0.9, 6))
    stage_rag(os.path.join(str(tmp_path), "peb_windpost"))
    out = P.design_and_report("peb_windpost", cfg, do_report=False)
    assert not out.get("blocked"), out.get("error")
    pkg = json.load(open(os.path.join(out["root"], "design", "calc_package.json")))
    m = next(m for m in pkg["members"] if m["inputs"]["section"] == W_COL and m["inputs"]["kind"] == "col")
    L = float(m["inputs"]["length_mm"])
    rec = [k for k in pkg.get("wind_post_Ka") or [] if k.get("applied")]
    assert rec, pkg.get("wind_post_Ka")
    ka_post = WT.ka_for_area_m2(SY / 1000.0 * L / 1000.0)["Ka"]
    assert any(k["factor"] == pytest.approx(ka_post, rel=0.01) for k in rec)
    q = max(abs(p["wall_windward_kNm2"]) for p in cfg["load_plan"]["member_wind"] if p.get("wind_axis") == "X")
    M_ref = 1.5 * q * ka_post * SY / 1000.0 * L ** 2 / 8.0
    assert m["inputs"]["Mz_span_Nmm"] == pytest.approx(M_ref, rel=0.02)
    assert m["inputs"]["Mz_span_Nmm"] < 0.95 * M_ref / ka_post             # the frame's Ka (1.0) is not used
