"""Span-moment fix (2026-11-01): the column in-span moment, used the way IS 800:2007 9.3.2.2 / Table 18 reads.

Independent review of 00336f6 / e7cc48b (briefs/SPAN_REVIEW.md): the mechanics were right, the use was not.
1. a column whose span moment governs (gable wind column) ran with Cm = 0.9 (sway note) and CmLT = 0.9;
2. a span moment of opposite sign smaller than the end moments was dropped (the other flange's LTB never checked);
3. columns with a span load whose end moments govern kept 0.6 + 0.4 psi (Table 18 has uniform-loading rows);
4. the column envelope Mz carried the span moment into the splice / base connection demand;
5. the PEB station checks kept My_mid_Nmm;
6. _top_records ranked the span combinations by |span| alone and could drop the governing concurrent pair;
7. weak tests; 8. the element length was read from the live OpenSees model; 9. the C1 gradient lever ignored the hump.
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

pytest.importorskip("openseespy.opensees")

L0 = 8000.0
W0 = 2.0                                     # N/mm


# ------------------------------------------------------------------------------ mechanics: one element vs 200
def _supports(case):
    """Nodal fixities (base, top) and the element release at the top for a support case ('spring': fixed base, top
    held laterally by a spring only)."""
    pin, fix = (1, 1, 1, 0, 0, 1), (1, 1, 1, 1, 1, 1)
    top_pin, top_fix = (1, 1, 0, 0, 0, 0), (1, 1, 0, 1, 1, 0)
    return {"pinned-pinned": (pin, top_pin, None), "fixed-fixed": (fix, top_fix, None),
            "propped": (fix, top_pin, None), "cantilever": (fix, None, None),
            "released": (pin, top_fix, "J"), "spring": (fix, None, None)}[case]


def _model(case, vecxz, Wy, Wz, *, n=1, L=L0, transf="Linear", P=0.0, H=0.0, k_spring=None):
    """A vertical column in n elements (the engine's local axes: transf 2 vecxz (0, 1, 0), transf 1 (1, 0, 0)), uniform
    span load (Wy, Wz) N/mm on every element; optional axial load P (compression, N) and lateral load H (N, global X)
    at the top, and a lateral spring (N/mm, both directions) holding the top.  Returns the element localForce list."""
    import openseespy.opensees as ops
    ops.wipe(); ops.model("basic", "-ndm", 3, "-ndf", 6)
    for k in range(n + 1):
        ops.node(k + 1, 0.0, 0.0, L * k / n)
    fb, ft, rel = _supports(case)
    ops.fix(1, *fb)
    if ft is not None:
        ops.fix(n + 1, *ft)
    if k_spring:
        ops.node(9001, 0.0, 0.0, L); ops.fix(9001, 1, 1, 1, 1, 1, 1)
        ops.uniaxialMaterial("Elastic", 77, float(k_spring))
        ops.element("zeroLength", 9001, 9001, n + 1, "-mat", 77, 77, "-dir", 1, 2)
    ops.geomTransf(transf, 1, *vecxz)
    for k in range(n):
        ra = []
        if rel == "J" and k == n - 1:
            ra = ["-releasez", 2, "-releasey", 2]
        ops.element("elasticBeamColumn", k + 1, k + 1, k + 2, 1e4, 2e5, 8e4, 1e6, 1e8, 1e8, 1, *ra)
    ops.timeSeries("Linear", 1); ops.pattern("Plain", 1, 1)
    for k in range(n):
        ops.eleLoad("-ele", k + 1, "-type", "-beamUniform", Wy, Wz)
    if P or H:
        ops.load(n + 1, H, 0.0, -P, 0.0, 0.0, 0.0)
    ops.system("BandGeneral"); ops.numberer("Plain"); ops.constraints("Plain")
    ops.integrator("LoadControl", 1.0)
    ops.algorithm("Newton" if transf == "PDelta" else "Linear"); ops.analysis("Static")
    ops.test("NormDispIncr", 1e-10, 50)
    assert ops.analyze(1) == 0
    return [ops.eleResponse(k + 1, "localForce") for k in range(n)]


def _stations(lfs):
    """Signed moments (record convention: M_i = -f_i, M_j = +f_j) at every element end of a split column."""
    mz, my, t = [], [], []
    n = len(lfs)
    for k, lf in enumerate(lfs):
        mz += [-lf[5], lf[11]]; my += [-lf[4], lf[10]]; t += [k / n, (k + 1) / n]
    return t, mz, my


CASES = ("pinned-pinned", "fixed-fixed", "propped", "cantilever", "released")


@pytest.mark.parametrize("case", CASES)
@pytest.mark.parametrize("vecxz", [(0, 1, 0), (1, 0, 0)])
@pytest.mark.parametrize("axis", ["y", "z"])
def test_one_element_rebuilds_the_200_element_moment_diagram(case, vecxz, axis):
    """From ONE element's end forces: the free moment of the span load is w L^2 / 8, the parabola through the end
    moments and that free moment equals the moment of the same column split into 200 elements at every station, and
    the in-span extreme is the fine model's interior extreme whatever its size or sign (0.0 when the vertex is at an
    end: the cantilever)."""
    import static_model as SM
    import india_is800 as I8
    Wy, Wz = (W0, 0.0) if axis == "y" else (0.0, W0)
    (lf,) = _model(case, vecxz, Wy, Wz)
    model = {"cols": [{"tag": 1, "n1": 1, "n2": 2, "L": L0}]}
    sz, sy, fz, fy = SM.column_span_moments(model, {1: lf})[frozenset((1, 2))]
    span, free, other_span, other_free = (sz, fz, sy, fy) if axis == "y" else (sy, fy, sz, fz)
    assert abs(free) == pytest.approx(W0 * L0 ** 2 / 8.0, rel=1e-9)
    assert other_span == 0.0 and other_free == 0.0
    Mi, Mj = (-lf[5], lf[11]) if axis == "y" else (-lf[4], lf[10])
    t, mz, my = _stations(_model(case, vecxz, Wy, Wz, n=200))
    ref = mz if axis == "y" else my
    scale = max(abs(v) for v in ref)
    for tt, mref in zip(t, ref):
        mfit = Mi * (1 - tt) + Mj * tt + 4.0 * free * tt * (1 - tt)
        assert mfit == pytest.approx(mref, abs=2e-6 * scale)
    dg = I8.span_moment_diagram(Mi, Mj, free)
    # the fine model's interior extreme: an interior node where the moment turns (one value per node)
    node = [ref[0]] + ref[1::2]
    inner = [node[k] for k in range(1, len(node) - 1) if (node[k] - node[k - 1]) * (node[k + 1] - node[k]) < 0.0]
    ext = max(inner, key=abs) if inner else None
    wl2 = W0 * L0 ** 2
    if case in ("pinned-pinned", "released"):
        assert abs(span) == pytest.approx(wl2 / 8.0, rel=1e-6) and dg["t_ext"] == pytest.approx(0.5)
    elif case == "fixed-fixed":
        # interior extreme w L^2 / 24, OPPOSITE in sign to the w L^2 / 12 end moments and smaller: still recorded
        assert abs(Mi) == pytest.approx(wl2 / 12.0, rel=1e-6) and abs(span) == pytest.approx(wl2 / 24.0, rel=1e-6)
        assert span * Mi < 0.0
    elif case == "propped":
        # fixed base w L^2 / 8, interior extreme 9 w L^2 / 128 at 5 L / 8, opposite sign
        assert abs(Mi) == pytest.approx(wl2 / 8.0, rel=1e-6) and abs(span) == pytest.approx(9.0 * wl2 / 128.0, rel=1e-6)
        assert dg["t_ext"] == pytest.approx(5.0 / 8.0, rel=1e-6) and span * Mi < 0.0
    else:                                        # cantilever: the vertex sits at the free tip
        assert span == 0.0 and dg["M_ext"] is None
    if ext is not None:
        assert span == pytest.approx(ext, rel=1e-4)
        assert dg["M_ext"] == pytest.approx(span, rel=1e-9)


@pytest.mark.parametrize("vecxz", [(0, 1, 0), (1, 0, 0)])
def test_p_delta_column_on_a_spring_with_axial_load(vecxz):
    """PDelta transformation, P = 300 kN, fixed base, the top held only by a lateral spring (it sways under the span
    load; P-Delta raises the base moments about 7 %), span load in both local directions: the span load recovered
    from v_i + v_j is exact, and the in-span extreme found from the shear v_i (static_model._span_extreme) equals the
    extreme of the parabola through the (second-order) end moments and the free moment -- localForce gives the
    chord shears, without the P-Delta shear, so the chord diagram is the element's diagram."""
    import static_model as SM
    import india_is800 as I8
    (lf,) = _model("spring", vecxz, 1.5, -1.0, transf="PDelta", P=3.0e5, k_spring=200.0)
    (lf1,) = _model("spring", vecxz, 1.5, -1.0, transf="Linear", P=3.0e5, k_spring=200.0)
    assert abs(lf[4]) + abs(lf[5]) > 1.05 * (abs(lf1[4]) + abs(lf1[5]))         # second-order end moments
    model = {"cols": [{"tag": 1, "n1": 1, "n2": 2, "L": L0}]}
    sz, sy, fz, fy = SM.column_span_moments(model, {1: lf})[frozenset((1, 2))]
    assert abs(fz) == pytest.approx(1.5 * L0 ** 2 / 8.0, rel=1e-9)
    assert abs(fy) == pytest.approx(1.0 * L0 ** 2 / 8.0, rel=1e-9)
    assert abs(lf[6]) == pytest.approx(3.0e5, rel=1e-6)                       # the axial load is there
    n_inside = 0
    for (Mi, Mj, f, s) in ((-lf[5], lf[11], fz, sz), (-lf[4], lf[10], fy, sy)):
        dg = I8.span_moment_diagram(Mi, Mj, f)
        if s:
            n_inside += 1
            assert dg["M_ext"] == pytest.approx(s, rel=1e-9)
        else:
            assert dg["M_ext"] is None
    assert n_inside >= 1


def test_element_length_is_passed_not_read_from_the_live_model():
    """column_span_moments takes L from the column dict: building another OpenSees model in between changes nothing;
    a column dict without L is refused (no silent read of whatever model is live)."""
    import static_model as SM
    (lf,) = _model("pinned-pinned", (0, 1, 0), W0, 0.0)
    m = {"cols": [{"tag": 1, "n1": 1, "n2": 2, "L": L0}]}
    before = SM.column_span_moments(m, {1: lf})
    _model("pinned-pinned", (0, 1, 0), 0.0, 0.0, L=40.0)                        # a different live model
    assert SM.column_span_moments(m, {1: lf}) == before
    with pytest.raises(ValueError):
        SM.column_span_moments({"cols": [{"tag": 1, "n1": 1, "n2": 2}]}, {1: lf})


def test_model_builders_set_the_column_length():
    """build_static (parametric) and _staticize_custom (the mini PEB shed) both put the element length on every
    column dict.  Parametric columns carry no 'transf', so member_wind_loads takes the nodal fallback: no column
    span load there (the wall wind reaches the frame as level forces)."""
    import engine3d as E
    import static_model as SM
    import openseespy.opensees as ops
    from _peb_fixture import mini_peb_cfg
    E.activate_si_units()
    cfg = dict(units="N-mm", jurisdiction="india", NX=1, NY=1, SX=6000.0, SY=5000.0, heights=[4000.0, 3500.0],
               D_floor=4.0, D_roof=3.0, L_floor=5.0, Lr=0.75, clad=0.0, self_weight=False, base="fixed",
               col="WPB200X200X61.3", beam="NPB300X150X36.53", brace="WPB200X200X61.3",
               braces=lambda k, NX, NY: [])
    m = SM.build_static(cfg, "Linear", 2)
    assert m["cols"] and all(c["L"] == pytest.approx(4000.0 if c["k"] == 0 else 3500.0) for c in m["cols"])
    assert all("transf" not in c for c in m["cols"])
    ops.timeSeries("Linear", 1); ops.pattern("Plain", 1, 1)
    seen = []
    real = ops.eleLoad
    ops.eleLoad = lambda *a: seen.append(a[1]) or real(*a)
    try:
        tot = SM.member_wind_loads(cfg, m, {"wind_axis": "X", "wall_windward_kNm2": 1.0, "wall_leeward_kNm2": -0.5}, 1.0)
    finally:
        ops.eleLoad = real
    assert tot["wall_N"] != 0.0 and not ({c["tag"] for c in m["cols"]} & set(seen))
    pc = mini_peb_cfg("peb_len")
    mc = SM.build_static(pc, "Linear", 2)
    for c in mc["cols"]:
        a, b = ops.nodeCoord(c["n1"]), ops.nodeCoord(c["n2"])
        assert c["L"] == pytest.approx(math.dist(a, b), rel=1e-12)
    ops.wipe()


# ------------------------------------------------------------------------------ records
def _rec(**kw):
    import static_model as SM
    d = dict.fromkeys(SM.REC_FIELDS, 0.0)
    d.update(kw)
    return tuple(d[f] for f in SM.REC_FIELDS)


def test_record_layout_and_combo_forces():
    import static_model as SM
    assert SM.REC_FIELDS[11:13] == ("N_LAT", "V_LAT")
    assert SM.REC_FIELDS[13:] == ("Mmaj_span", "Mmin_span", "Mmaj_free", "Mmin_free")
    wl2 = W0 * L0 ** 2
    recs = {"wind": _rec(N=-1e4, Mmaj_span=wl2 / 8, Mmaj_free=wl2 / 8, Mmin_free=-3e6, Mmin_span=-3e6),
            "ff": _rec(N=-1e4, Mmaj_i=-wl2 / 12, Mmaj_j=-wl2 / 12, Mmaj_span=wl2 / 24, Mmaj_free=wl2 / 8),
            "grav": _rec(N=-5e4, Mmaj_i=1e6, Mmaj_j=-2e6)}
    cf = {c["combo"]: c for c in SM.combo_forces_for_member_check(recs, "col")}
    assert cf["wind"]["Mz_free_Nmm"] == wl2 / 8 and cf["wind"]["My_free_Nmm"] == -3e6
    assert cf["ff"]["Mz_free_Nmm"] == wl2 / 8 and "My_free_Nmm" not in cf["ff"]
    assert not {"Mz_free_Nmm", "My_free_Nmm", "Mz_mid_Nmm", "My_mid_Nmm"} & set(cf["grav"])
    # beams: unchanged (Mz_mid = the sagging maximum, no free moments)
    cb = SM.combo_forces_for_member_check({"b": _rec(Mmaj_sag_max=5e6)}, "beam")[0]
    assert cb["Mz_mid_Nmm"] == 5e6 and "Mz_free_Nmm" not in cb
    # 13-field records: no span load; 15-field records of 00336f6: the free moment recovered from the extreme
    old13 = SM.combo_forces_for_member_check({"o": recs["wind"][:13]}, "col")[0]
    assert "Mz_free_Nmm" not in old13
    old15 = {c["combo"]: c for c in SM.combo_forces_for_member_check({k: r[:15] for k, r in recs.items()}, "col")}
    assert old15["wind"]["Mz_free_Nmm"] == pytest.approx(wl2 / 8, rel=1e-12)
    assert old15["ff"]["Mz_free_Nmm"] == pytest.approx(wl2 / 8, rel=1e-12)


@pytest.mark.parametrize("Mi,Mj,f", [(0.0, 0.0, 5e6), (-3e6, 1e6, 4e6), (2e6, 2.5e6, -7e6), (1e6, -1e6, -2e6)])
def test_free_moment_from_an_interior_extreme_round_trip(Mi, Mj, f):
    import static_model as SM
    import india_is800 as I8
    dg = I8.span_moment_diagram(Mi, Mj, f)
    assert dg["M_ext"] is not None
    assert SM.free_from_span_extreme(Mi, Mj, dg["M_ext"]) == pytest.approx(f, rel=1e-9)


def test_envelope_keeps_end_moments_apart_from_the_span_moment():
    """envelope_from_records: Mz / My are end-moment envelopes (connection demands); the span extremes are
    Mz_span / My_span."""
    import static_model as SM
    recs = {"W": {frozenset((1, 2)): _rec(N=-1e4, Mmaj=2e6, Mmaj_i=2e6, Mmaj_span=-9e6, Mmaj_free=-1e7,
                                          Mmin_span=4e6, Mmin_free=4e6)}}
    env = SM.envelope_from_records(recs, {frozenset((1, 2)): ("col", None)}, [("W", 1, 0, 0, {}, False)])
    e = env[frozenset((1, 2))]
    assert e["Mz"] == 2e6 and e["My"] == 0.0
    assert e["Mz_span"] == 9e6 and e["My_span"] == 4e6
    import design_pipeline as DP
    assert DP._member_moment(e, "Mz") == 9e6 and DP._member_moment(e, "My") == 4e6


# ------------------------------------------------------------------------------ IS 800 Table 18 (uniform loading)
WL2 = W0 * L0 ** 2


@pytest.mark.parametrize("name,Mi,Mj,f,cm", [
    ("pinned-pinned (Ms > Mh, alpha_h = 0)", 0.0, 0.0, WL2 / 8, 0.95),
    ("fixed-fixed (alpha_s = -0.5, psi = 1)", -WL2 / 12, -WL2 / 12, WL2 / 8, 0.1 + 0.8 * 0.5),
    ("propped (extreme 9/128 at 5L/8 read as Ms)", -WL2 / 8, 0.0, WL2 / 8, 0.1 + 0.8 * 9.0 / 16.0),
    ("portal, knee -120, mid -78 (review case)", 0.0, -120e6, -18e6, 0.2 + 0.8 * 0.65),
    ("alpha_s < 0, psi = -1", -100e6, 100e6, 40e6, 0.1 * 2.0 + 0.8 * 0.4),
    ("cantilever (alpha_s = 0.25)", -WL2 / 2, 0.0, WL2 / 8, 0.4),
])
def test_table18_uniform_loading_rows(name, Mi, Mj, f, cm):
    import india_is800 as I8
    r = I8.cm_factor_span_load(Mi, Mj, f)
    assert r["Cm"] == pytest.approx(cm, rel=1e-9), (name, r)
    assert r["Cm_table18"] == r["Cm"] and r["psi"] is None and "Table 18" in r["cite"]


def test_table18_span_moment_larger_with_reversed_ends():
    """Ms > Mh, alpha_h < 0, psi < 0: 0.95 + 0.05 alpha_h (1 + 2 psi); the larger of the mid-length and extreme
    readings of Ms is used."""
    import india_is800 as I8
    Mi, Mj, f = 20e6, -5e6, -100e6
    r = I8.cm_factor_span_load(Mi, Mj, f)
    dg = I8.span_moment_diagram(Mi, Mj, f)
    psi = Mj / Mi
    exp = max(0.95 + 0.05 * (Mi / Ms) * (1 + 2 * psi) for Ms in (dg["M_mid"], dg["M_ext"]))
    assert r["Cm"] == pytest.approx(exp, rel=1e-12) and 0.9 < r["Cm"] < 0.95
    assert "1 + 2 psi" in r["row"]


@pytest.mark.parametrize("Mi,Mj", [(100e6, 100e6), (100e6, 30e6), (100e6, -40e6), (-60e6, 100e6), (100e6, -100e6)])
def test_table18_rows_meet_the_linear_row_without_span_load(Mi, Mj):
    """With (almost) no span load Ms(mid) = Mh (1 + psi) / 2 and the Mh >= Ms rows give 0.6 + 0.4 psi: the reading
    of Ms is consistent with the linear-gradient row."""
    import india_is800 as I8
    assert I8.cm_factor_span_load(Mi, Mj, 1e-3)["Cm"] == pytest.approx(I8.cm_factor(Mi, Mj)["Cm"], abs=1e-6)


def test_table18_sway_note():
    """Sway buckling mode: the Table 18 note's 0.9 is a floor (a row above 0.9 stands); Cm_table18 (CmLT) never
    takes the sway value."""
    import india_is800 as I8
    pp = I8.cm_factor_span_load(0.0, 0.0, WL2 / 8, sway=True)
    ff = I8.cm_factor_span_load(-WL2 / 12, -WL2 / 12, WL2 / 8, sway=True)
    assert pp["Cm"] == pytest.approx(0.95) and pp["Cm_table18"] == pytest.approx(0.95)
    assert ff["Cm"] == pytest.approx(0.9) and ff["Cm_table18"] == pytest.approx(0.5) and "sway" in ff["note"]


# ------------------------------------------------------------------------------ member check
def _sec():
    import engine3d as E
    import sections as S
    E.activate_si_units()
    S.register_custom_sections({"custom_sections": {"WI300X150X8X5": {
        "type": "welded_I", "D_mm": 300.0, "bf_mm": 150.0, "tf_mm": 8.0, "tw_mm": 5.0, "source": "test"}}})
    return "WI300X150X8X5"


def _mem(**kw):
    m = {"id": "c", "section": _sec(), "grade": "E350", "role": "column", "L_mm": L0, "Kz": 1.0, "Ky": 1.0,
         "LLT_sag_mm": L0, "LLT_hog_mm": L0}
    m.update(kw)
    return m


def _cf(**kw):
    c = {"combo": "W", "P_N": 5.0e4, "Mz_i_Nmm": 0.0, "Mz_j_Nmm": 0.0, "My_i_Nmm": 0.0, "My_j_Nmm": 0.0,
         "Vy_N": 0.0, "Vz_N": 0.0}
    c.update(kw)
    return c


def _checks(res):
    pc = res["per_combo"][0]
    return pc, {c["moment_sign"]: c for c in pc["checks"] if "moment_sign" in c}


def test_smaller_span_moment_of_opposite_sign_is_checked_on_its_own_flange():
    """Review case 3: ends +10.67 kN-m (fixed-fixed), span -5.33 kN-m, LLT_sag 1.5 m, LLT_hog 8 m.  The hogging
    check (the other flange, over 8 m) is made and governs; Cmz from Table 18 (alpha_s ~ -0.5, psi = 1: 0.1 - 0.8
    alpha_s ~ 0.5)."""
    import india_is800 as I8
    mem = _mem(LLT_sag_mm=1500.0, LLT_hog_mm=8000.0)
    Me = 10.67e6
    c0 = _cf(Mz_i_Nmm=Me, Mz_j_Nmm=Me)
    c1 = dict(c0, Mz_free_Nmm=-16.0e6)                      # mid-length -5.33 kN-m
    r0, r1 = I8.member_check_is800(mem, [c0]), I8.member_check_is800(mem, [c1])
    pc0, ch0 = _checks(r0)
    pc1, ch1 = _checks(r1)
    assert "hogging" not in ch0 and "hogging" in ch1
    assert pc1["Mz_hog_Nmm"] == pytest.approx(16.0e6 - Me, rel=1e-9) and pc1["Mz_sag_Nmm"] == Me
    assert ch1["hogging"]["LLT_mm"] == 8000.0
    assert ch1["hogging"]["dc"] > ch1["sagging"]["dc"]
    assert r1["interaction_dc"] > r0["interaction_dc"] + 0.05
    assert pc1["Cmz"] == pytest.approx(0.1 + 0.8 * (16.0e6 - Me) / Me, rel=1e-9) and "Table 18" in pc1["Cmz_basis"]


def test_span_governing_column_in_a_sway_frame_job():
    """sway True (a job with moment lines): a pinned-pinned column under its span load gets Cmz = 0.95 (the Table 18
    Ms > Mh row), not the 0.9 of the sway note; CmLT = the row value where the compression flange is free over the
    member, 1.0 (Table 18 upper bound) where lateral supports sit inside it; C1 = 1.0 under a span load."""
    import india_is800 as I8
    mem = _mem(sway=True, LLT_sag_mm=L0, LLT_hog_mm=2000.0)
    c_s = _cf(Mz_free_Nmm=12.0e6)                           # sagging span moment
    c_h = _cf(Mz_free_Nmm=-12.0e6)                          # hogging span moment
    pc, ch = _checks(I8.member_check_is800(mem, [c_s]))
    assert pc["Cmz"] == pytest.approx(0.95) and pc["Mz_sag_Nmm"] == pytest.approx(12.0e6)
    assert ch["sagging"]["CmLT"] == pytest.approx(0.95)
    m22 = ch["sagging"]["member_9_3_2_2"]
    assert m22["CmLT"] == pytest.approx(0.95) and m22["Cmz"] == pytest.approx(0.95)
    lam, ny = ch["sagging"]["lambda_LT"], m22["ny"]
    assert m22["KLT"] == pytest.approx(max(1 - 0.1 * lam * ny / 0.70, 1 - 0.1 * ny / 0.70), rel=1e-9)
    pch, chh = _checks(I8.member_check_is800(mem, [c_h]))
    assert pch["Cmz"] == pytest.approx(0.95) and chh["hogging"]["CmLT"] == 1.0
    # C1 = 1.0 under a span load: the Md of a declared C1 = 1.0, below the Md that psi = 0 would give (C1 > 1)
    cfe = _cf(Mz_i_Nmm=2e6, Mz_free_Nmm=12.0e6)
    md_span = _checks(I8.member_check_is800(mem, [cfe]))[1]["sagging"]["Mdz_LTB_Nmm"]
    md_c1 = _checks(I8.member_check_is800(dict(mem, c1=1.0), [cfe]))[1]["sagging"]["Mdz_LTB_Nmm"]
    md_psi = _checks(I8.member_check_is800(dict(mem, sway=False), [_cf(Mz_i_Nmm=2e6)]))[1]["sagging"]["Mdz_LTB_Nmm"]
    md_span_ns = _checks(I8.member_check_is800(dict(mem, sway=False), [cfe]))[1]["sagging"]["Mdz_LTB_Nmm"]
    assert md_span_ns == pytest.approx(md_span, rel=1e-12)
    assert md_span == pytest.approx(md_c1, rel=1e-12) and md_psi > md_span * 1.05
    # without a span load the sway note stands (unchanged behaviour)
    assert I8.member_check_is800(mem, [_cf(Mz_i_Nmm=5e6, Mz_j_Nmm=1e6)])["per_combo"][0]["Cmz"] == 0.9


def test_end_moments_governing_with_a_span_load_take_the_uniform_loading_row():
    """Review case (finding 3): pinned base, knee -120 kN-m, wall wind making mid-height -78 kN-m: Cmz = 0.72
    (0.2 + 0.8 alpha_s), not 0.6 + 0.4 psi = 0.6; with a sway buckling mode the 0.9 of the note stands."""
    import india_is800 as I8
    c = _cf(Mz_i_Nmm=0.0, Mz_j_Nmm=-120e6, Mz_free_Nmm=-18e6)
    assert I8.member_check_is800(_mem(), [c])["per_combo"][0]["Cmz"] == pytest.approx(0.72)
    assert I8.member_check_is800(_mem(), [dict(c, Mz_free_Nmm=None)])["per_combo"][0]["Cmz"] == pytest.approx(0.6)
    assert I8.member_check_is800(_mem(sway=True), [c])["per_combo"][0]["Cmz"] == pytest.approx(0.9)


def test_minor_axis_span_moment():
    import india_is800 as I8
    r0 = I8.member_check_is800(_mem(L_mm=6000.0), [_cf(P_N=1e4)])
    r1 = I8.member_check_is800(_mem(L_mm=6000.0), [_cf(P_N=1e4, My_free_Nmm=8.0e6)])
    pc = r1["per_combo"][0]
    assert pc["My_Nmm"] == pytest.approx(8.0e6) and pc["Cmy"] == pytest.approx(0.95)
    assert r1["per_combo"][0]["dc"] > r0["per_combo"][0]["dc"] + 0.2


def test_gravity_columns_have_no_sway_buckling_mode_under_a_span_load():
    """A gravity column of a sway-frame job takes the Table 18 rows under a span load (no sway mode of its own); its
    end-moment-only checks keep the job's sway flag (scope of this fix)."""
    import design_pipeline as DP
    import india_is800 as I8
    cfg = {"sway_frame": True}
    g = DP._member_input_record(cfg, 1, "col", "WI300X150X8X5", 1, 2, L0, "gravity_col")
    lat = DP._member_input_record(cfg, 1, "col", "WI300X150X8X5", 1, 2, L0, "lateral_col")
    assert g["sway"] is True and g["sway_span_load"] is False
    assert lat["sway"] is True and "sway_span_load" not in lat
    assert "sway_span_load" not in DP._member_input_record({}, 1, "col", "WI300X150X8X5", 1, 2, L0, "gravity_col")
    m = dict(_mem(), sway=True, sway_span_load=False)
    ff = _cf(Mz_i_Nmm=-WL2 / 12, Mz_j_Nmm=-WL2 / 12, Mz_free_Nmm=WL2 / 8)
    assert I8.member_check_is800(m, [ff])["per_combo"][0]["Cmz"] == pytest.approx(0.5)
    assert I8.member_check_is800(dict(m, sway_span_load=True), [ff])["per_combo"][0]["Cmz"] == pytest.approx(0.9)
    assert I8.member_check_is800(m, [_cf(Mz_i_Nmm=5e6, Mz_j_Nmm=-5e6)])["per_combo"][0]["Cmz"] == 0.9


# ------------------------------------------------------------------------------ _top_records, stations, C1 lever
def test_top_records_keep_every_span_load_combination():
    """40 combinations: the span-load combination that governs (largest compression with its span moment) ranks
    only 5th by |span| (the tension-side wind cases have more span moment), so ranking by |span| would drop it."""
    import design_pipeline as DP
    import india_is800 as I8
    import static_model as SM
    recs = {}
    for k in range(32):                                      # gravity / storey-force cases: more axial, no span load
        recs["G%02d" % k] = _rec(N=-(1.6e5 + 1e3 * k), Mmaj=1e3 * k, Mmaj_i=1e3 * k, V=10.0 * k)
    for k in range(4):                                       # suction cases: big span, tension
        recs["WT%d" % k] = _rec(N=4e4, Mmaj_span=-2.0e7 - 1e5 * k, Mmaj_free=-2.0e7 - 1e5 * k)
    recs["WC"] = _rec(N=-1.5e5, Mmaj_span=-1.8e7, Mmaj_free=-1.8e7)          # governing: compression + span
    for k in range(3):
        recs["WS%d" % k] = _rec(N=-1e4, Mmaj_span=-1.0e7, Mmaj_free=-1.0e7)
    by_span = sorted(recs, key=lambda l: -abs(recs[l][13]))[:3]
    assert "WC" not in by_span
    mem = _mem(L_mm=3000.0, LLT_sag_mm=3000.0, LLT_hog_mm=3000.0)
    top = DP._top_records(recs)
    assert {l for l in recs if recs[l][15]} <= set(top)
    full = I8.member_check_is800(mem, SM.combo_forces_for_member_check(recs, "col"))
    got = DP.member_checks_is800({}, {"member": mem, "kind": "col", "records": recs})
    assert full["interaction_governing_combo"] == "WC"
    assert got["interaction_governing_combo"] == "WC" and got["interaction_dc"] == pytest.approx(full["interaction_dc"])


def test_station_checks_carry_no_span_moment():
    """peb_station_checks: a station is checked with its end forces only -- the minor-axis span moment (and any span
    load's free moment) is cleared, so a station with zero end moments is not penalised (review case 4)."""
    import design_pipeline as DP
    import india_is800 as I8
    import static_model as SM
    mem = _mem(L_mm=1500.0, LLT_sag_mm=1500.0, LLT_hog_mm=1500.0)
    sec = mem["section"]
    with_span = {"W": _rec(N=-2e5, Mmaj=30e6, Mmaj_i=30e6, Mmaj_j=24e6, Mmin_span=6.0e6, Mmin_free=6.0e6)}
    no_span = {"W": _rec(N=-2e5, Mmaj=30e6, Mmaj_i=30e6, Mmaj_j=24e6)}
    res_el = {"dc": 0.01, "found": True}
    a = DP.peb_station_checks({}, mem, "col", with_span, dict(res_el), (sec, sec))
    b = DP.peb_station_checks({}, mem, "col", no_span, dict(res_el), (sec, sec))
    sa = {s["where"]: s["dc"] for s in a["stations"] if s["where"].startswith("station")}
    sb = {s["where"]: s["dc"] for s in b["stations"] if s["where"].startswith("station")}
    assert sa and sa == pytest.approx(sb, rel=1e-12)
    # the element check (mid-depth section) does take the minor-axis span moment: the case is not masked
    el_a = I8.member_check_is800(mem, SM.combo_forces_for_member_check(with_span, "col"))
    el_b = I8.member_check_is800(mem, SM.combo_forces_for_member_check(no_span, "col"))
    assert el_a["interaction_dc"] > el_b["interaction_dc"] + 0.1 and el_b["interaction_dc"] > 0.3


def test_c1_gradient_lever_returns_unity_under_a_span_load():
    import peb_levers as PL
    chain = [(1, 0.0, 3000.0)]
    flat = {"W": [-1e4, 5e6, 0.0, 0.0, 5e6, 1e6] + [0.0] * 11}
    hump = {"W": [-1e4, 5e6, 0.0, 0.0, 5e6, 1e6] + [0.0] * 7 + [9e6, 0.0, 1.2e7, 0.0]}
    c_flat, _ = PL._c1_segment(chain, lambda t: flat, "W", 0.0, 3000.0, {1: True})
    c_hump, why = PL._c1_segment(chain, lambda t: hump, "W", 0.0, 3000.0, {1: True})
    assert c_flat > 1.0 and c_hump == 1.0 and "span load" in why


# ------------------------------------------------------------------------------ end to end on the mini PEB shed
@pytest.fixture(scope="module")
def shed(tmp_path_factory):
    import pipeline as P
    from _peb_fixture import mini_peb_cfg, stage_rag
    jobs = tmp_path_factory.mktemp("peb_spanfix")
    os.environ["STELTIC_TEST_JOBS"] = str(jobs)
    os.environ["STEEL_BUILDER_JOBS"] = str(jobs)
    cfg = mini_peb_cfg("peb_spanfix")
    assert cfg["sway_frame"] is True                         # the job has moment lines: the sway path is live
    stage_rag(os.path.join(str(jobs), "peb_spanfix"))
    out = P.design_and_report("peb_spanfix", cfg, do_report=False)
    d = os.path.join(out["root"], "design")
    return out, cfg, json.load(open(os.path.join(d, "calc_package.json"))), \
        json.load(open(os.path.join(d, "member_combo_forces.json")))


def _wind_column(pkg):
    from _peb_fixture import W_COL
    return next(m for m in pkg["members"] if m["inputs"]["section"] == W_COL and m["inputs"]["kind"] == "col")


def test_e2e_gable_wind_column_is_governed_by_its_span_moment(shed):
    """The gable wind column (pinned base, top released at the end rafter, 6.6 m, along-ridge member wind): its
    governing 9.3 record carries the span moment q x tributary x L^2 / 8 with the Table 18 Cm (0.95, not the sway
    0.9), and its interaction D/C is several times the D/C of the same records without the span moment -- this
    assertion fails if the span moment is not used."""
    import design_pipeline as DP
    import static_model as SM
    from _peb_fixture import SY
    out, cfg, pkg, recs = shed
    assert not out.get("blocked"), out.get("error")
    m = _wind_column(pkg)
    inp = m["inputs"]
    L = float(inp["length_mm"])
    q = max(abs(p["wall_windward_kNm2"]) for p in cfg["load_plan"]["member_wind"] if p.get("wind_axis") == "X")
    M_ref = 1.5 * q * SY / 1000.0 * L ** 2 / 8.0
    g = m["governing_element_result"]
    gr = g["governing_combo_record"]
    assert gr["combo"] == g["interaction_governing_combo"] and "WM" in gr["combo"]
    assert max(gr["Mz_sag_Nmm"], gr["Mz_hog_Nmm"], gr["My_Nmm"]) == pytest.approx(M_ref, rel=0.02)
    assert gr["Cmz"] == pytest.approx(0.95) and "Table 18" in gr["Cmz_basis"]
    t = inp["governing_element"]
    el = recs["elements"][str(t)]
    assert recs["fields"][13:] == list(SM.REC_FIELDS[13:])
    mem = DP._member_input_record(cfg, t, "col", inp["section"], 0, 0, el["L_mm"], inp["role"])
    assert mem["sway"] is True and mem["sway_span_load"] is False and inp["role"] == "gravity_col"
    nospan = {l: r[:13] + [0.0] * 4 for l, r in el["records"].items()}
    r_ns = DP.member_checks_is800(cfg, {"member": mem, "kind": "col", "records": nospan})
    assert g["interaction_dc"] > 2.0 * r_ns["interaction_dc"]
    rows = [c for c in m["checks"] if "9.3" in str(c.get("name"))]
    assert rows and rows[0]["dc"] == pytest.approx(g["interaction_dc"]) and rows[0]["combo"] == gr["combo"]
    assert inp["Mz_span_Nmm"] == pytest.approx(M_ref, rel=0.02)


def test_e2e_top_records_never_drop_the_governing_combination(shed):
    """For every column of the shed, the reported 9.3 interaction equals the check over ALL its combinations."""
    import design_pipeline as DP
    import india_is800 as I8
    import static_model as SM
    out, cfg, pkg, recs = shed
    n = 0
    for m in pkg["members"]:
        inp = m["inputs"]
        if inp["kind"] != "col":
            continue
        t = inp["governing_element"]
        el = recs["elements"][str(t)]
        mem = DP._member_input_record(cfg, t, "col", inp["section"], 0, 0, el["L_mm"], inp["role"])
        full = I8.member_check_is800(mem, SM.combo_forces_for_member_check(el["records"], "col"))
        top = DP.member_checks_is800(cfg, {"member": mem, "kind": "col", "records": el["records"]})
        assert top["interaction_dc"] == pytest.approx(full["interaction_dc"], rel=1e-12), m["id"]
        assert top["interaction_governing_combo"] == full["interaction_governing_combo"]
        n += any(r[15] or r[16] for r in el["records"].values())
    assert n >= 2                                            # span-load columns are among them


def test_e2e_connection_demands_take_no_span_moment(shed):
    """The pinned gable wind column: member moment = its span moment, column splice / base demand moment = 0."""
    out, cfg, pkg, recs = shed
    m = _wind_column(pkg)
    assert m["inputs"]["Mz_Nmm"] > 1e6
    c = next(c for c in pkg["connections"] if c["id"] == "conn-" + m["id"])
    assert c["demand"]["M_Nmm"] == 0.0


def test_e2e_station_checks_unchanged_by_span_fields(shed):
    """Tapered portal columns (station checks) under the wall wind: the station D/Cs equal those of the same
    records with the span fields removed."""
    import design_pipeline as DP
    out, cfg, pkg, recs = shed
    seen = 0
    for m in pkg["members"]:
        g = m["governing_element_result"]
        if m["inputs"]["kind"] != "col" or not g.get("stations"):
            continue
        t = m["inputs"]["governing_element"]
        el = recs["elements"][str(t)]
        if not any(r[13] or r[15] for r in el["records"].values()):
            continue
        st = [s["section"] for s in g["stations"] if s["where"].startswith("station")]
        mem = DP._member_input_record(cfg, t, "col", m["inputs"]["section"], 0, 0, el["L_mm"], m["inputs"]["role"])
        nospan = {l: r[:13] + [0.0] * 4 for l, r in el["records"].items()}
        a = DP.peb_station_checks(cfg, mem, "col", el["records"], {"dc": 0.0}, tuple(st))
        b = DP.peb_station_checks(cfg, mem, "col", nospan, {"dc": 0.0}, tuple(st))
        assert [s["dc"] for s in a["stations"]] == pytest.approx([s["dc"] for s in b["stations"]], rel=1e-12)
        seen += 1
    assert seen >= 1
