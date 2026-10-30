"""Third wave (2026-10-30), PEB golds: the in-span moment of a column under a span load.

Before this fix a column's member check used its end moments only.  A gable wind column (pinned at the base and at the
end rafter) carries the wall wind as a span load: its end moments are zero and the w L^2 / 8 at mid-height was never
checked -- the auto-sizer then took the IN_Ex1..4 wind columns down to 200 x 120 plates.  static_model now records the
signed span extreme of every column (Mmaj_span / Mmin_span) from the static part of each combination, and the member
check uses it (Cm = 1.0) wherever it exceeds both end moments.
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


def _column(vecxz, Wy, Wz, Mbase=(0.0, 0.0), L=10000.0):
    """One pinned-pinned vertical column (the engine's local axes: transf 2 vecxz (0, 1, 0), transf 1 (1, 0, 0)) with a
    uniform span load (Wy, Wz) N/mm and base moments (about X, about Y) N-mm; returns (localForce, model dict)."""
    import openseespy.opensees as ops
    ops.wipe(); ops.model("basic", "-ndm", 3, "-ndf", 6)
    ops.node(1, 0.0, 0.0, 0.0); ops.node(2, 0.0, 0.0, L)
    ops.fix(1, 1, 1, 1, 0, 0, 1); ops.fix(2, 1, 1, 0, 0, 0, 0)
    ops.geomTransf("Linear", 1, *vecxz)
    ops.element("elasticBeamColumn", 1, 1, 2, 1e4, 2e5, 8e4, 1e6, 1e8, 1e8, 1)
    ops.timeSeries("Linear", 1); ops.pattern("Plain", 1, 1)
    ops.eleLoad("-ele", 1, "-type", "-beamUniform", Wy, Wz)
    ops.load(1, 0.0, 0.0, 0.0, Mbase[0], Mbase[1], 0.0)
    ops.system("BandGeneral"); ops.numberer("Plain"); ops.constraints("Plain")
    ops.integrator("LoadControl", 1.0); ops.algorithm("Linear"); ops.analysis("Static")
    assert ops.analyze(1) == 0
    return ops.eleResponse(1, "localForce"), {"cols": [{"tag": 1, "n1": 1, "n2": 2}]}


@pytest.mark.parametrize("vecxz", [(0, 1, 0), (1, 0, 0)])
@pytest.mark.parametrize("axis", ["y", "z"])
def test_span_moment_of_a_pinned_column_is_wL2_over_8(vecxz, axis):
    import static_model as SM
    w, L = 1.5, 10000.0
    lf, model = _column(vecxz, w if axis == "y" else 0.0, w if axis == "z" else 0.0, L=L)
    mz, my = SM.column_span_moments(model, {1: lf})[frozenset((1, 2))]
    got = mz if axis == "y" else my                      # a local-y load bends about local z (major), z about y
    other = my if axis == "y" else mz
    assert abs(got) == pytest.approx(w * L * L / 8.0, rel=1e-6)
    assert other == pytest.approx(0.0, abs=1.0)
    # the end moments of the record are zero: the old check saw nothing
    assert abs(lf[5]) < 1.0 and abs(lf[11]) < 1.0 and abs(lf[4]) < 1.0 and abs(lf[10]) < 1.0


def _split_column_moments(vecxz, Wy, Wz, Mbase, L=10000.0, n=200):
    """The same column in n elements: the signed bending moments (record convention) at every station."""
    import openseespy.opensees as ops
    ops.wipe(); ops.model("basic", "-ndm", 3, "-ndf", 6)
    for k in range(n + 1):
        ops.node(k + 1, 0.0, 0.0, L * k / n)
    ops.fix(1, 1, 1, 1, 0, 0, 1); ops.fix(n + 1, 1, 1, 0, 0, 0, 0)
    ops.geomTransf("Linear", 1, *vecxz)
    for k in range(n):
        ops.element("elasticBeamColumn", k + 1, k + 1, k + 2, 1e4, 2e5, 8e4, 1e6, 1e8, 1e8, 1)
    ops.timeSeries("Linear", 1); ops.pattern("Plain", 1, 1)
    for k in range(n):
        ops.eleLoad("-ele", k + 1, "-type", "-beamUniform", Wy, Wz)
    ops.load(1, 0.0, 0.0, 0.0, Mbase[0], Mbase[1], 0.0)
    ops.system("BandGeneral"); ops.numberer("Plain"); ops.constraints("Plain")
    ops.integrator("LoadControl", 1.0); ops.algorithm("Linear"); ops.analysis("Static")
    assert ops.analyze(1) == 0
    mz, my = [], []
    for k in range(n):
        lf = ops.eleResponse(k + 1, "localForce")
        mz += [-lf[5], lf[11]]
        my += [-lf[4], lf[10]]
    return mz, my


@pytest.mark.parametrize("vecxz", [(0, 1, 0), (1, 0, 0)])
@pytest.mark.parametrize("load", [(1.0, 0.0), (0.0, 1.0), (1.0, -0.7)])
def test_span_moment_with_end_moments_matches_a_finely_split_column(vecxz, load):
    """Base moments plus a uniform load in either local direction: the signed span extreme found from the end forces
    of ONE element equals the extreme of the same column split into 200 elements (an independent model)."""
    import static_model as SM
    Mb = (3.0e6, -2.0e6)
    lf, model = _column(vecxz, load[0], load[1], Mbase=Mb)
    mz, my = SM.column_span_moments(model, {1: lf})[frozenset((1, 2))]
    fz, fy = _split_column_moments(vecxz, load[0], load[1], Mb)
    for got, ref in ((mz, fz), (my, fy)):
        ext = max(ref, key=abs)
        ends = max(abs(ref[0]), abs(ref[-1]))
        if abs(ext) > ends + 1.0:                            # an interior extreme: found, with its sign
            assert got == pytest.approx(ext, rel=1e-3)
        else:
            assert abs(got) <= ends + 1.0


def test_no_span_load_no_span_moment():
    import static_model as SM
    lf, model = _column((0, 1, 0), 0.0, 0.0, Mbase=(2.0e6, 1.0e6))
    assert SM.column_span_moments(model, {1: lf})[frozenset((1, 2))] == (0.0, 0.0)


def test_combo_forces_use_the_span_moment_only_where_it_governs():
    import static_model as SM
    n = len(SM.REC_FIELDS)
    assert SM.REC_FIELDS[13:] == ("Mmaj_span", "Mmin_span")
    base = dict.fromkeys(SM.REC_FIELDS, 0.0)
    pin = dict(base, N=-1e4, Mmaj_span=-2.0e7, Mmin_span=5.0e6)               # wind column: zero end moments
    knee = dict(base, N=-1e5, Mmaj_i=0.0, Mmaj_j=-9.0e8, Mmaj_span=-1.0e8)   # portal column: the knee moment governs
    recs = {"pin": tuple(pin[f] for f in SM.REC_FIELDS), "knee": tuple(knee[f] for f in SM.REC_FIELDS)}
    cf = {c["combo"]: c for c in SM.combo_forces_for_member_check(recs, "col")}
    assert cf["pin"]["Mz_mid_Nmm"] == -2.0e7 and cf["pin"]["My_mid_Nmm"] == 5.0e6
    assert "Mz_mid_Nmm" not in cf["knee"] and "My_mid_Nmm" not in cf["knee"]
    # an old 13-field record (no span fields) reads as no span moment
    old = {"o": tuple(pin[f] for f in SM.REC_FIELDS[:13])}
    assert "Mz_mid_Nmm" not in SM.combo_forces_for_member_check(old, "col")[0]
    assert n == 15


def test_member_check_counts_the_minor_axis_span_moment():
    import engine3d as E
    import india_is800 as I8
    import sections as S
    E.activate_si_units()
    S.register_custom_sections({"custom_sections": {"WI300X150X8X5": {
        "type": "welded_I", "D_mm": 300.0, "bf_mm": 150.0, "tf_mm": 8.0, "tw_mm": 5.0, "source": "test"}}})
    mem = {"id": "c", "section": "WI300X150X8X5", "grade": "E350", "role": "column", "L_mm": 6000.0, "Kz": 1.0,
           "Ky": 1.0, "LLT_sag_mm": 1500.0, "LLT_hog_mm": 1500.0}
    cf0 = {"combo": "W", "P_N": 1e4, "Mz_i_Nmm": 0.0, "Mz_j_Nmm": 0.0, "My_i_Nmm": 0.0, "My_j_Nmm": 0.0,
           "Vy_N": 0.0, "Vz_N": 0.0}
    r0 = I8.member_check_is800(mem, [cf0])
    r1 = I8.member_check_is800(mem, [dict(cf0, My_mid_Nmm=8.0e6)])
    assert r1["per_combo"][0]["dc"] > r0["per_combo"][0]["dc"] + 0.2      # the 9.3 interaction, not Table 3 KL/r
    pc = r1["per_combo"][0]
    assert pc["My_Nmm"] == 8.0e6 and pc["Cmy"] == 1.0


# ------------------------------------------------------------------------------ end to end on the mini PEB shed
@pytest.fixture(scope="module")
def mini_job(tmp_path_factory):
    import pipeline as P
    from _peb_fixture import mini_peb_cfg, stage_rag
    jobs = tmp_path_factory.mktemp("peb_third")
    os.environ["STELTIC_TEST_JOBS"] = str(jobs)
    os.environ["STEEL_BUILDER_JOBS"] = str(jobs)
    cfg = mini_peb_cfg("peb_span")
    stage_rag(os.path.join(str(jobs), "peb_span"))
    out = P.design_and_report("peb_span", cfg, do_report=False)
    pkg = json.load(open(os.path.join(out["root"], "design", "calc_package.json")))
    return out, pkg, cfg


def test_gable_wind_column_is_checked_for_the_wall_wind(mini_job):
    """The mini shed's gable wind column (W_COL, pinned top and base, 6.3 m) under the along-ridge member wind: its
    member demand carries the span moment q x tributary x L^2 / 8 and the check uses it."""
    from _peb_fixture import W_COL, SY, H_EAVE, RISE
    out, pkg, cfg = mini_job
    assert not out.get("blocked"), out.get("error")
    m = next(x for x in pkg["members"] if (x.get("inputs") or {}).get("section") == W_COL
             and (x.get("inputs") or {}).get("kind") == "col")
    inp = m["inputs"]
    L = float(inp["length_mm"])
    assert L == pytest.approx(H_EAVE + RISE, rel=1e-6)
    q = max(abs(p["wall_windward_kNm2"]) for p in cfg["load_plan"]["member_wind"] if p.get("wind_axis") == "X")
    M_ref = 1.5 * q * SY / 1000.0 * L ** 2 / 8.0             # 1.5 WL: kN/m2 x m = N/mm
    M_rec = max(float(inp.get("Mz_Nmm") or 0.0), float(inp.get("My_Nmm") or 0.0))
    assert M_rec == pytest.approx(M_ref, rel=0.05)
    recs = json.load(open(os.path.join(out["root"], "design", "member_combo_forces.json")))
    assert recs["fields"][13:] == ["Mmaj_span", "Mmin_span"]
    el = recs["elements"][str(inp["governing_element"])]
    assert max(max(abs(r[13]), abs(r[14])) for r in el["records"].values() if len(r) > 14) == pytest.approx(M_ref, rel=0.05)
    rows = [c for c in m["checks"] if "9.3" in str(c.get("name"))]
    assert rows and max(c["dc"] for c in rows) > 0.05


def test_base_plate_inside_the_column_outline_is_a_geometry_failure_not_a_crash():
    """IN_Ex1 (sizing the gable wind column for its wall wind): a 425 mm deep column on the declared 400 x 260 plate
    made base_plate_design divide by a zero bearing length and the whole Section 12 block went unevaluated."""
    import india_connections as C
    kw = dict(B_mm=260.0, L_mm=400.0, t_plate_mm=20.0, fy_plate_MPa=250.0, fck_MPa=30.0, col_d_mm=425.0,
              col_bf_mm=150.0, col_tf_mm=8.0,
              anchors={"n_total": 4, "n_tension": 2, "d_mm": 24, "grade": "8.8", "f_mm": 100.0, "pitch_mm": 160.0,
                       "edge_mm": 50.0, "n_per_row": 2, "Anb_mm2": 353.0})
    r = C.base_plate_design_biaxial(P_N=50e3, Mz_Nmm=5e6, My_Nmm=0.0, V_N=10e3, **kw)
    assert r["checks"]["geometry_plate_outline"]["ok"] is False
    assert r["ok"] is False
    r2 = C.base_plate_design_biaxial(P_N=50e3, Mz_Nmm=5e6, My_Nmm=0.0, V_N=10e3, **dict(kw, col_d_mm=350.0))
    assert "geometry_plate_outline" not in r2["checks"]


# ------------------------------------------------------------------------------ the PEB sizer (handoff P12)
def _lm_stub(members, chains, x, spec, res=None):
    import peb_autosize as A
    lm = object.__new__(A.LocalModel)
    lm.members, lm.chains, lm.spec, lm.res = members, chains, spec, res or {}
    lm.x0 = dict(x)
    lm.const_of_label = {lab: c for c, lab in x.items()}
    return lm


def _frame(col_lab, raf_lab, H=13000.0, W=24000.0):
    """One portal line q = 1: two fixed-base columns and two rafters (eave to ridge), labels as constants COL / RAF."""
    members = {
        "C-0": {"kind": "column", "section": col_lab, "line": [1, 0], "chain": "c0", "s0": 0.0, "s1": H},
        "C-1": {"kind": "column", "section": col_lab, "line": [1, 4], "chain": "c1", "s0": 0.0, "s1": H},
        "R-0": {"kind": "rafter", "section": raf_lab, "line": 1, "a0": 0.0, "a1": W / 2, "eave_end": "start",
                "plane": 0},
        "R-1": {"kind": "rafter", "section": raf_lab, "line": 1, "a0": W / 2, "a1": W, "eave_end": "end", "plane": 0},
    }
    chains = {"c0": {"kind": "column", "L_mm": H, "top": 100100}, "c1": {"kind": "column", "L_mm": H, "top": 100104}}
    return members, chains


def test_rafter_sway_weight_single_span_and_props():
    import peb_autosize as A
    w = A.LocalModel.rafter_sway_weight
    # single portal span 0..24 m: 1 at the eaves, 0 at mid-span (the previous index)
    assert w(0.0, [0.0, 24000.0], []) == pytest.approx(1.0)
    assert w(6000.0, [0.0, 24000.0], []) == pytest.approx(0.5)
    assert w(12000.0, [0.0, 24000.0], []) == pytest.approx(0.0)
    # IN_Ex2: 96 m continuous over pinned props at 24 / 48 / 72 m -- the knee moment dies out at the first prop
    mom, pin = [0.0, 96000.0], [24000.0, 48000.0, 72000.0]
    assert w(12000.0, mom, pin) == pytest.approx(0.5)
    assert w(24000.0, mom, pin) == pytest.approx(0.0)
    assert w(40000.0, mom, pin) == 0.0 and w(60000.0, mom, pin) == 0.0
    assert w(90000.0, mom, pin) == pytest.approx(0.75)
    # interior moment columns: each span is a portal of its own
    assert w(36000.0, [0.0, 24000.0, 48000.0], []) == pytest.approx(0.0)
    assert w(30000.0, [0.0, 24000.0, 48000.0], []) == pytest.approx(0.5)


def test_dado_index_follows_the_lower_column_not_the_rafter():
    """A fixed-base frame: the dado-top index changes with the column, not with the rafter; the eave index changes
    with both (IN_Ex2 H/150 + dado: the eave index sent the sizer to the rafters, which did not move the dado top)."""
    import peb_autosize as A
    import peb_build as PB
    for lab in ("WI700X300X22X14", "WI700X300X32X14", "WI600X250X20X14", "WI600X250X32X14"):
        PB.ensure(lab)
    x = {"COL": "WI700X300X22X14", "RAF": "WI600X250X20X14"}
    members, chains = _frame(x["COL"], x["RAF"])
    spec = {"frame_line": 1, "base": "fixed", "dado_height_mm": 3000.0}
    lm = _lm_stub(members, chains, x, spec)
    Fd0, F0 = lm.flexibility_dado(x), lm.flexibility(x)
    x_raf = dict(x, RAF="WI600X250X32X14")
    x_col = dict(x, COL="WI700X300X32X14")
    assert lm.flexibility_dado(x_raf) == pytest.approx(Fd0)
    assert lm.flexibility(x_raf) < F0
    assert lm.flexibility_dado(x_col) < 0.85 * Fd0
    # pinned bases: the dado top follows the eave index
    lm_p = _lm_stub(members, chains, x, dict(spec, base="pinned"))
    assert lm_p.flexibility_dado(x_raf) == pytest.approx(lm_p.flexibility(x_raf))
    # the prediction: dado by its own index, the eave sway by the frame index
    lm.global0, lm.F0, lm.Fd0 = {"wind_Y": 0.9, "dado_Y": 1.08}, F0, None
    pr = lm.predicted(x_col)
    assert pr["dado_Y"] == pytest.approx(1.08 * lm.flexibility_dado(x_col) / Fd0)
    assert pr["wind_Y"] == pytest.approx(0.9 * lm.flexibility(x_col) / F0)


def test_feedback_tightens_the_dado_margin_alone():
    import peb_autosize as A
    m = {"sway": 0.98}
    run = {"fail_items": [(1.08, "sway", "wind Y dado top", "IS 800 Table 6 H/240 at the dado")],
           "gates_fail": ["wind_defl_Y"]}
    A.feedback(m, run, None, log_fn=lambda *a: None)
    assert m["dado"] == pytest.approx(0.98 - 0.08) and m["sway"] == 0.98
    m2 = {"sway": 0.98}
    run2 = {"fail_items": [(1.05, "sway", "wind Y eave", "")], "gates_fail": ["wind_defl_Y"]}
    A.feedback(m2, run2, None, log_fn=lambda *a: None)
    assert m2["sway"] == pytest.approx(0.93) and "dado" not in m2


def _slab_spec(L=450.0, B=400.0, t=25.0, d=24):
    return {"B_mm": B, "L_mm": L, "t_plate_mm": t, "fy_plate_MPa": 240.0, "plate_grade": "E250", "fck_MPa": 30.0,
            "fixed": False, "anchors": {"n_total": 4, "n_tension": 2, "d_mm": d, "grade": "8.8", "f_mm": 100.0,
                                        "pitch_mm": 160.0, "edge_mm": 50.0, "n_per_row": 2, "Anb_mm2": 353.0,
                                        "embedment": {"method": "bond", "tau_bd_MPa": 1.5, "bar": "plain",
                                                      "L_mm": 900.0, "source": "test input (as the IN_Ex1 gold)",
                                                      "cite": "IS 456:2000 26.2.1.1"}}}


def test_base_plate_sizing_picks_the_thinnest_passing_plate():
    import peb_autosize as A
    import peb_build as PB
    PB.ensure("WI412X225X12X8")
    cfg = {"plate_grade": "E250", "steel_grade": "E350"}
    spec = _slab_spec()
    entries = [{"el": 1, "sec": "WI412X225X12X8", "cases": [(250e3, 0.0, 0.0, 60e3), (-80e3, 0.0, 0.0, 40e3)]}]
    pl = A.size_base_plate(cfg, spec, entries)
    assert pl and pl["t"] in A.BASE_PLATE_T_MM and pl["d"] in A.ANCHOR_D_MM
    assert A.base_plate_ok(cfg, spec, entries, pl)
    i = A.BASE_PLATE_T_MM.index(pl["t"])
    if i > 0:
        assert not any(A.base_plate_ok(cfg, spec, entries, {"t": A.BASE_PLATE_T_MM[i - 1], "d": d})
                       for d in A.ANCHOR_D_MM)
    # strengthen-only floor
    assert A.size_base_plate(cfg, spec, entries, floor={"t": 32.0, "d": 30})["t"] >= 32.0
    # the plate and anchor values are applied with their IS 2062 fy and IS 4000 stress area
    sp = A.apply_plate(dict(spec, anchors=dict(spec["anchors"])), {"t": 16.0, "d": 30})
    assert sp["t_plate_mm"] == 16.0 and sp["fy_plate_MPa"] == 250.0 and sp["anchors"]["Anb_mm2"] == 561.0


def test_base_plate_is_a_design_variable_and_itemised():
    import peb_autosize as A
    cfg = {"connections": {"column_base": {"WI412X225X12X8": dict(_slab_spec(), shear_key={
        "capacity_N": 1e6, "size": "cruciform 2 x 400 x 28, 250 deep", "mass_kg": 52.8}),
        "default": _slab_spec(400.0, 260.0, 20.0)}}}
    d = A.read_conn_design(cfg, None)
    assert d["base#0"]["key"] == [400.0, 28.0, 250.0] and d["base#0"]["plate"] == {"t": 25.0, "d": 24}
    assert d["base#1"]["key"] is None and d["base#1"]["plate"] == {"t": 20.0, "d": 24}
    items = A.connection_items(cfg, {"base#0": 18, "base#1": 6}, {})
    assert items["base plates base#0"] == pytest.approx(18 * 450 * 400 * 25 * A.STEEL, abs=0.01)
    assert items["base plates base#1"] == pytest.approx(6 * 400 * 260 * 20 * A.STEEL, abs=0.01)
    # an older calibration (no base plates itemised) keeps its basis
    old = {"items": {"shear keys base#0": 950.4}}
    assert set(A.calib_items(old, items)) == {"shear keys base#0"}
    assert A.calib_items({}, items) == items
    # patching a slot with a plate changes thickness and anchors, keeps the key
    A.patch_connections(cfg, {"base#0": {"key": [400.0, 28.0, 250.0], "fck": 30.0, "plate": {"t": 20.0, "d": 30}}},
                        {})
    sp = cfg["connections"]["column_base"]["WI412X225X12X8"]
    assert sp["t_plate_mm"] == 20.0 and sp["anchors"]["d_mm"] == 30 and sp["shear_key"]
