"""X03 (HR-A-09, HR-C-17, HR-D-04(b), ISSUES E8): IS 800 7.4.2 stiffened (gusseted) column bases, embedded bases with
an EOR capacity, and the IS 800 9.3.1.2 Mpc of the section form for the 12.12.1 / IS 18168 9.3 capacity moment."""
import math
import os
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "steel_engine"))

import india_connections as C
import india_is800 as I8
import india_is800_s12 as S12
import sections as S

BOX = "BOX500X500X32"


@pytest.fixture(scope="module")
def box():
    return S.register_box(BOX, 500.0, 500.0, 32.0, 32.0)


# ---------------------------------------------------------------- unstiffened model unchanged (golden = pre-X03 code)
# AUD-2: a 45 mm plate is in the IS 2062 Table 3 >40-100 band (E250: 230 MPa); the golden values were computed at
# fy 240, which is within the band value of E275 (255 MPa) -- the plate grade is declared so the golden stays valid.
UNSTIFF_KW = dict(B_mm=700, L_mm=750, t_plate_mm=45, fy_plate_MPa=240, plate_grade="E275", fck_MPa=30, col_d_mm=300,
                  col_bf_mm=300,
                  col_tf_mm=19, anchors={"n_total": 8, "n_tension": 3, "d_mm": 30, "grade": "8.8", "f_mm": 290,
                                         "pitch_mm": 150, "edge_mm": 60, "n_per_row": 3})
GOLDEN = [  # (P, Mz, My, V) -> (dc, ok, plate key, plate value) from the code before X03 (fix/2026-09-review 98691c4)
    ((1500e3, 0, 0, 20e3), 0.6173555996472666, True, "plate_thickness_7_4_3_1", 1250.1450892857147),
    ((900e3, 60e6, 0, 50e3), 0.8040112433862435, True, "plate_thickness", 71045.35714285714),
    ((600e3, 250e6, 80e6, 90e3), 1.6969895338412264, None, "plate_thickness", 149952.1660812429),
    ((-150e3, 40e6, 0, 30e3), 0.3479589845729693, None, "plate_thickness", 30746.92118226601),
    ((2000e3, 30e6, 20e6, 10e3), 1.3050617283950618, None, "plate_thickness", 115320.0),
]


@pytest.mark.parametrize("case", GOLDEN)
def test_unstiffened_results_identical_to_before(case):
    (P, Mz, My, V), dc, ok, key, val = case
    for extra in ({}, {"stiffeners": None}):
        r = C.base_plate_design_biaxial(P_N=P, Mz_Nmm=Mz, My_Nmm=My, V_N=V, **UNSTIFF_KW, **extra)
        assert r["dc"] == pytest.approx(dc, rel=1e-12) and r["ok"] is ok
        assert r["checks"][key]["value"] == pytest.approx(val, rel=1e-12)
        assert not any(k.startswith(("gusset", "y:gusset")) for k in r["checks"]) and "stiffened" not in r


# ---------------------------------------------------------------- strip-method panels (closed-form hand checks)
def test_strip_method_panel_formulas():
    w, m = 20.0, 600.0
    p3 = C._panel_moments(w, 500.0, 500.0, m, [-100.0, 100.0], False)
    three = next(p for p in p3 if p["panel"].startswith("3-edge"))
    s = 200.0
    alpha = 4 * m ** 2 / (s ** 2 + 4 * m ** 2)                       # load share of the strips spanning the gussets
    assert three["M_per_mm"] == pytest.approx(alpha * w * s ** 2 / 8)               # x-strip, simply supported
    assert three["M_per_mm"] == pytest.approx((1 - alpha) * w * m ** 2 / 2)         # y-strip, cantilever: equal
    assert three["M_per_mm"] == pytest.approx(w * s * s * m * m / (2 * (s * s + 4 * m * m)))
    # overhang 150 beyond the outer gusset, column face 500 wide < plate 500? -> plate = face: 2-adjacent-edge panel
    over = [p for p in p3 if p["panel"].startswith("2-adjacent")]
    c = 150.0
    assert over and over[0]["M_per_mm"] == pytest.approx(w * c * c * m * m / (2 * (c * c + m * m)))
    # plate wider than the face, no corner gusset -> cantilever from the outer gusset w c^2/2
    p1 = C._panel_moments(w, 800.0, 500.0, m, [-100.0, 100.0], False)
    cant = [p for p in p1 if p["panel"].startswith("1-edge (outer gusset)")]
    assert cant[0]["M_per_mm"] == pytest.approx(w * 300.0 ** 2 / 2)
    # limits: s -> 0 the 3-edge panel vanishes; s >> m it tends to the cantilever w m^2/2
    big = C._panel_moments(w, 1e6, 1e6, m, [-4e5, 4e5], False)
    assert next(p for p in big if p["panel"].startswith("3-edge"))["M_per_mm"] == pytest.approx(w * m * m / 2, rel=1e-5)


def test_gusset_loads_hand_check_uniform_pressure():
    """Concentric P on a gusseted base: w = P/(BL) uniform; the gusset takes the x-strip share alpha of each 3-edge
    panel (half each side) -> V = alpha s w m_g, M = alpha s w m_g^2/2 (one interior gusset between two panels)."""
    B, L, d, bf = 600.0, 900.0, 400.0, 400.0
    P = 3.0e6
    st = {"n_per_side": 3, "t_mm": 20, "h_mm": 250, "fy_MPa": 250, "weld": {"size_mm": 10, "fu_MPa": 410}}
    r = C.base_plate_design(P_N=P, B_mm=B, L_mm=L, t_plate_mm=40, fy_plate_MPa=250, fck_MPa=30, col_d_mm=d,
                            col_bf_mm=bf, col_tf_mm=20, stiffeners=st)
    assert "plate_thickness_7_4_3_1" not in r["checks"] and r["stiffened"]["applied"] is True
    w = P / (B * L)
    m_pl, m_g = (L - 0.95 * d) / 2, (L - d) / 2
    s = (bf - 20) / 2                                               # gussets at -190, 0, +190
    al = 4 * m_pl ** 2 / (s ** 2 + 4 * m_pl ** 2)
    c = B / 2 - (bf - 20) / 2                                       # 110 overhang, cantilever (flange_extension)
    share_mid, share_out = al * s, al * s / 2 + c
    share = max(share_mid, share_out)
    assert r["checks"]["gusset_shear_8_4"]["value"] == pytest.approx(w * m_g * share, rel=1e-6)
    assert r["checks"]["gusset_bending"]["value"] == pytest.approx(w * m_g ** 2 / 2 * share, rel=1e-6)
    pt = r["checks"]["plate_thickness"]
    Mc = max(w * s * s * m_pl ** 2 / (2 * (s * s + 4 * m_pl ** 2)), w * c * c / 2)
    b_pl = (B - 0.8 * bf) / 2
    assert pt["M_comp_stiffened"] == pytest.approx(Mc, rel=1e-9)
    assert pt["M_side_zone"] == pytest.approx(w * b_pl ** 2 / 2, rel=1e-9)
    # AUD-2: the 20 mm gusset is in the IS 2062 Table 3 >16-40 band -> fy 240 (declared 250 reduced and recorded)
    Vd = 250 * 20 * 240 / (math.sqrt(3) * 1.10)
    assert r["checks"]["gusset_shear_8_4"]["limit"] == pytest.approx(Vd)
    assert r["checks"]["gusset_shear_8_4"]["plate_fy"][0]["reduced"] is True
    eps = math.sqrt(250.0 / 240.0)                                  # AUD-2: eps at the band fy 240
    assert r["checks"]["gusset_outstand_table2"]["limit"] == pytest.approx(13.6 * eps)
    assert r["checks"]["gusset_outstand_table2"]["dc"] is None                  # a gate, never the governing D/C


def test_stiffener_inputs_missing_is_not_evaluated_and_plate_stays_unstiffened():
    base = dict(P_N=900e3, M_Nmm=60e6, V_N=50e3, **UNSTIFF_KW)
    r0 = C.base_plate_design(**base)
    r = C.base_plate_design(**base, stiffeners={"n_per_side": 2, "t_mm": 20})
    assert r["checks"]["stiffeners_input"]["ok"] is None and r["ok"] is None
    assert r["checks"]["plate_thickness"]["value"] == pytest.approx(r0["checks"]["plate_thickness"]["value"])


# ---------------------------------------------------------------- Ex2 BOX500 SMF fixed base (HR-A-09)
def _ex2_md(stiffened, t_plate):
    main = C._gusset_positions(4, None, 500.0, 52.0)
    mids = [(a + b) / 2 for a, b in zip(main, main[1:])]            # tension anchors mid-panel between the gussets
    base = {"id": "b1", "column_member_id": "c1", "fixed": True, "B_mm": 650, "L_mm": 1900, "t_plate_mm": t_plate,
            "fy_plate_MPa": 230, "fck_MPa": 40, "shear_key_N": 3.0e6,
            "shear_key_source": "EOR shear-lug calc SK-01 (test record)", "shear_key_cite": "IS 456 34.4 bearing; IS 800 8.4.1",
            "anchors": {"n_total": 6, "n_tension": 3, "d_mm": 48, "grade": "8.8", "f_mm": 825, "Anb_mm2": 1473.0,
                        "x_mm": mids},
            "embedment": {"capacity_N": 700e3, "cite": "EOR anchorage calc AN-01 (test record)"},
            "load_cases": [{"combo": "1.2DL+0.5LL+1.2EQ_X", "P_N": 2.0e6, "Mz_Nmm": 100e6, "My_Nmm": 0.0,
                            "V_N": 300e3, "seismic": True}]}
    if stiffened:
        base["stiffeners"] = {"n_per_side": 4, "t_mm": 52, "h_mm": 700, "fy_MPa": 240, "layout": "cross",
                              "weld": {"size_mm": 20, "fu_MPa": 410}, "weld_column": {"type": "cjp"}}
    col = {"id": "c1", "section": BOX, "grade": "E250 B0", "role": "column", "sfrs": True, "L_mm": 3500.0}
    return {"members": [col], "bases": [base]}


def test_ex2_box500_stiffened_base_60mm_and_all_gusset_checks_evaluated(box):
    r = S12.base_checks("SMF", _ex2_md(True, 60), {"zone": "III"})[0]
    det = r["detail"]
    p = S.props(BOX)
    fy = I8.material_for_section(p, "E250 B0")["fy_MPa"]
    Mp = p["Zx"] * fy
    # 9.3.1.2(d) box: n = 0.139 -> Mp (1-n)/(1-0.5 aw) > Mp -> capped at Mp; 1.1 Ry = 1.54 -> ~3.9 MNm (HR-A-09)
    assert det["demands"]["M_Nmm"] == pytest.approx(1.54 * Mp, rel=1e-9)
    assert 3.8e9 < det["demands"]["M_Nmm"] < 4.0e9
    ck = det["checks"]
    pt = ck["plate_thickness"]
    assert pt["t_req_mm"] <= 60.0 and pt["ok"] is True and pt["verify"] is True and "EOR method" in pt["basis"]
    for k in ("gusset_outstand_table2", "gusset_shear_8_4", "gusset_bending", "gusset_weld_to_column_10_5_7",
              "gusset_weld_to_plate_10_5_7", "bearing", "anchor_tension_10_3_5", "anchor_combined_10_3_6"):
        assert ck[k]["ok"] is True, (k, ck[k])
        assert ck[k]["clause"] and ck[k]["cite"]
    assert "7.4.2" in pt["clause"] and "gusset" in C.CITE_7_4_2
    assert r["ok"] is True and r["base_type"] == "stiffened"
    # the same base without stiffeners needs a far thicker slab (the HR-A-09 150 mm artefact)
    r0 = S12.base_checks("SMF", _ex2_md(False, 60), {"zone": "III"})[0]
    assert r0["detail"]["checks"]["plate_thickness"]["t_req_mm"] > 150.0 and r0["ok"] is False
    assert r0["base_type"] == "slab"


def test_cross_layout_checks_minor_axis_gussets_flange_extension_does_not():
    main = C._gusset_positions(3, None, 300.0, 20.0)
    kw = dict(B_mm=600, L_mm=700, t_plate_mm=40, fy_plate_MPa=250, fck_MPa=30, col_d_mm=300, col_bf_mm=300,
              col_tf_mm=19, anchors={"n_total": 8, "n_tension": 2, "d_mm": 30, "grade": "8.8", "f_mm": 280, "f_y_mm": 240,
                                     "x_mm": [(a + b) / 2 for a, b in zip(main, main[1:])]})
    st = {"n_per_side": 3, "t_mm": 20, "h_mm": 250, "fy_MPa": 250, "weld": {"size_mm": 10, "fu_MPa": 410}}
    rc = C.base_plate_design_biaxial(P_N=800e3, Mz_Nmm=150e6, My_Nmm=60e6, V_N=50e3, stiffeners=dict(st, layout="cross"), **kw)
    rf = C.base_plate_design_biaxial(P_N=800e3, Mz_Nmm=150e6, My_Nmm=60e6, V_N=50e3,
                                     stiffeners=dict(st, layout="flange_extension"), **kw)
    assert "y:gusset_bending" in rc["checks"] and rc["stiffened_y"]["applied"] is True
    assert "y:gusset_bending" not in rf["checks"] and rf["stiffened_y"]["applied"] is False
    assert "gusset_bending" in rf["checks"]


# ---------------------------------------------------------------- embedded / socket base
def _emb_md(rec):
    base = dict({"id": "b1", "column_member_id": "c1", "fixed": True, "type": "embedded",
                 "load_cases": [{"combo": "1.2DL+0.5LL+1.2EQ_X", "P_N": 2.0e6, "Mz_Nmm": 100e6, "V_N": 300e3,
                                 "seismic": True}]}, **rec)
    return {"members": [{"id": "c1", "section": BOX, "grade": "E250 B0", "role": "column", "sfrs": True,
                         "L_mm": 3500.0}], "bases": [base]}


def test_embedded_base_without_source_is_found_false(box):
    r = S12.base_checks("SMF", _emb_md({"embedded": {"capacity_Nmm": 5.0e9, "capacity_N": 6.0e6}}), {"zone": "III"})[0]
    assert r["found"] is False and r["ok"] is None and r["base_type"] == "embedded"
    assert r["detail"]["checks"]["embedded_base_capacity"]["ok"] is None
    assert "source" in r["detail"]["checks"]["embedded_base_capacity"]["reason"]


def test_embedded_base_with_source_and_cite_checks_capacity_moment(box):
    rec = {"capacity_Nmm": 5.0e9, "capacity_N": 6.0e6, "source": "EOR socket design SB-2 rev 1",
           "cite": "EOR embedded-base calc (IS 456 socket), VERIFY"}
    r = S12.base_checks("SMF", _emb_md(rec), {"zone": "III"})[0]           # flat keys in the base spec also read
    ck = r["detail"]["checks"]
    M = r["detail"]["demands"]["M_Nmm"]
    assert r["found"] is True and ck["embedded_moment"]["dc"] == pytest.approx(M / 5.0e9)
    assert ck["embedded_moment"]["verify"] is True and ck["embedded_moment"]["clause"] == rec["cite"]
    assert ck["embedded_shear"]["value"] == pytest.approx(r["detail"]["demands"]["V_N"])
    assert r["ok"] is True
    rec_low = dict(rec, capacity_Nmm=3.0e9)
    assert S12.base_checks("SMF", _emb_md({"embedded": rec_low}), {"zone": "III"})[0]["ok"] is False


# ---------------------------------------------------------------- 9.3.1.2 Mpc by section form
def test_mpc_forms_9_3_1_2(box):
    fy = 240.0
    p = S.props(BOX)
    A = p["A"]
    P = 0.3 * A * fy
    aw = min((A - 2 * 500 * 32) / A, 0.5)
    Mpc, n, form = S12.mpc_9_3_1_2(p, fy, P, "z")
    assert n == pytest.approx(0.3) and "(d)" in form
    assert Mpc == pytest.approx(min(p["Zx"] * fy * 0.7 / (1 - 0.5 * aw), p["Zx"] * fy))
    old, _ = S12._mpc_reduced(p, fy, P, "z")                       # rolled-I form under-states the box capacity
    assert Mpc > old
    w = S.props("WPB300X300X117.03")
    assert S12.mpc_9_3_1_2(w, fy, 0.3 * w["A"] * fy, "z")[0] == pytest.approx(S12._mpc_reduced(w, fy, 0.3 * w["A"] * fy, "z")[0])
    assert S12.mpc_9_3_1_2(w, fy, 0.3 * w["A"] * fy, "y")[0] == pytest.approx(S12._mpc_reduced(w, fy, 0.3 * w["A"] * fy, "y")[0])
    # welded I (b): a = (A - 2 b tf)/A; minor axis unreduced for n <= a
    a = min((w["A"] - 2 * w["bf"] * w["tf"]) / w["A"], 0.5)
    Mz_b, _, fb = S12.mpc_9_3_1_2(w, fy, 0.3 * w["A"] * fy, "z", welded=True)
    assert "(b)" in fb and Mz_b == pytest.approx(min(w["Zx"] * fy * 0.7 / (1 - 0.5 * a), w["Zx"] * fy))
    chs = {"section_type": "CHS", "A": 5000.0, "Zx": 4.0e5, "Zy": 4.0e5}
    assert S12.mpc_9_3_1_2(chs, fy, 0.5 * 5000 * fy, "z")[0] == pytest.approx(min(1.04 * 4.0e5 * fy * (1 - 0.5 ** 1.7),
                                                                                  4.0e5 * fy))
