"""Third wave (2026-10), MSME angle-truss shed (IN_Ex21): the engine support for pin-jointed angle roof trusses.

Hand checks of every new path: double angles back to back on a gusset (sections), IS 800 Table 2 / Table 10 / 7.1.2 /
7.5.1.2 / 7.5.2.1 / 6.2-6.4 / Table 3 for truss members (india_is800), the purlin reactions at the top-chord panel
points (static_model), the truss element kind (engine3d / static_model) and the knee-braced portal checks of IS 800
12.10.2.1 / 12.10.2.4 (truss_design).
"""
import math
import os
import sys

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
for p in (os.path.join(ROOT, "steel_engine"), HERE):
    if p not in sys.path:
        sys.path.insert(0, p)

import engine3d as E                    # noqa: E402

E.activate_si_units()
import sections as S                    # noqa: E402
import india_is800 as I8                # noqa: E402
import truss_design as TD               # noqa: E402

GM0, GM1, EMOD = 1.10, 1.25, 2.0e5


def _fcd(fy, KL_r, alpha=0.49):
    """IS 800 7.1.2.1 by hand (class c unless alpha given)."""
    fcc = math.pi ** 2 * EMOD / KL_r ** 2
    lam = math.sqrt(fy / fcc)
    phi = 0.5 * (1 + alpha * (lam - 0.2) + lam ** 2)
    chi = min(1.0, 1.0 / (phi + math.sqrt(phi ** 2 - lam ** 2)))
    return chi * fy / GM0


@pytest.fixture(scope="module")
def da65():
    return S.register_double_angle("2ISA65X65X6", "ISA65X65X6", 8.0)


# ------------------------------------------------------------------------------------------------ sections
def test_double_angle_properties_by_hand(da65):
    p1 = S.props("ISA65X65X6")
    assert da65["section_type"] == "double_angle"
    assert da65["A"] == pytest.approx(2 * p1["A"])
    assert da65["Ix"] == pytest.approx(2 * p1["Ix"])                       # in-plane: no parallel-axis term
    a = p1["Cz"] + 4.0                                                       # centroid to the gap centre
    assert da65["Iy"] == pytest.approx(2 * (p1["Iy"] + p1["A"] * a * a))
    assert da65["ry"] == pytest.approx(math.sqrt(da65["Iy"] / da65["A"]))
    assert da65["rx"] == pytest.approx(p1["rx"], rel=1e-3)                 # IS 808 r is rounded to 0.1 mm
    assert da65["Zy"] == pytest.approx(2 * p1["A"] * a)
    assert da65["Sx"] == pytest.approx(da65["Ix"] / max(65.0 - p1["Cy"], p1["Cy"]))
    assert da65["Mass_kg_m"] == pytest.approx(2 * p1["Mass_kg_m"])
    assert E.Ipack("2ISA65X65X6")[0] == pytest.approx(da65["A"])


def test_double_angle_unequal_connected_leg_choice():
    pD = S.register_double_angle("2ISA75X50X6_D", "ISA75X50X6", 8.0, connected_leg="D")
    pB = S.register_double_angle("2ISA75X50X6_B", "ISA75X50X6", 8.0, connected_leg="B")
    p1 = S.props("ISA75X50X6")
    assert pD["Ix"] == pytest.approx(2 * p1["Ix"]) and pB["Ix"] == pytest.approx(2 * p1["Iy"])
    assert pD["leg_connected_mm"] == 75.0 and pB["leg_connected_mm"] == 50.0
    with pytest.raises(ValueError):
        S.register_double_angle("2MB200", "MB200", 8.0)


def test_custom_sections_type_double_angle():
    S.register_custom_sections({"custom_sections": {"2ISA60X60X6": {"type": "double_angle", "angle": "ISA60X60X6",
                                                                    "gap_mm": 10.0}}})
    assert S.props("2ISA60X60X6")["gap_mm"] == 10.0


# ------------------------------------------------------------------------------------------------ IS 800 checks
def test_table2_and_table10_double_angle(da65):
    eps = 1.0
    sc = I8.section_class_table2(da65, 250.0, P_N=1.0, loading="axial")
    # Table 2 'double angles with the components separated, axial': b/t, d/t <= 15.7 eps, (b + d)/t <= 25 eps
    assert sc["section_class"] == "semi-compact"
    assert {e["element"] for e in sc["elements"]} >= {"angle leg b/t (axial)", "angle (b+d)/t (axial)"}
    assert I8.buckling_class_for_section(da65, "z")["buckling_class"] == "c"
    sc_b = I8.section_class_table2(da65, 250.0)
    assert sc_b["section_class"] == "semi-compact"                         # 65/6 = 10.8 > 10.5 eps


def test_double_angle_compression_7_5_2_1_by_hand(da65):
    KLz, KLy = 0.85 * 1546.0, 1546.0
    c = I8.compression_capacity(da65, 250.0, KLz_mm=KLz, KLy_mm=KLy)
    assert c["found"]
    hand = min(_fcd(250.0, KLz / da65["rx"]), _fcd(250.0, KLy / da65["ry"])) * da65["A"]
    assert c["Pd_N"] == pytest.approx(hand, rel=2e-3)


def test_single_angle_7_5_1_2_by_hand():
    sec, l = "ISA65X65X6", 2000.0
    p = S.props(sec)
    r = I8.single_angle_7_5_1_2(sec, 250.0, l, n_bolts=2, fixity="hinged")
    den = 1.0 * math.sqrt(math.pi ** 2 * EMOD / 250.0)
    lvv = (l / p["rv"]) / den
    lph = ((65.0 + 65.0) / (2 * 6.0)) / den
    lam_e = math.sqrt(0.70 + 0.60 * lvv ** 2 + 5.0 * lph ** 2)               # Table 12: >= 2 bolts, hinged
    phi = 0.5 * (1 + 0.49 * (lam_e - 0.2) + lam_e ** 2)
    chi = 1.0 / (phi + math.sqrt(phi ** 2 - lam_e ** 2))
    assert r["lambda"] == pytest.approx(lam_e, rel=1e-6)
    assert r["Pd_N"] == pytest.approx(p["A"] * chi * 250.0 / GM0, rel=1e-6)


def test_angle_end_tension_6_3_3_and_6_4_1_by_hand():
    sec = "ISA65X65X6"
    ti, rec = I8.angle_end_connection_inputs(sec, n_bolts=3, d0_mm=18.0, pitch_mm=50.0, end_mm=30.0, gauge_mm=35.0)
    t = 6.0
    Anc, Ago = (65.0 - 3.0 - 18.0) * t, (65.0 - 3.0) * t
    assert ti["Anc_mm2"] == pytest.approx(Anc) and ti["Ago_mm2"] == pytest.approx(Ago)
    assert ti["bs_mm"] == pytest.approx(65.0 + 35.0 - 6.0) and ti["Lc_mm"] == pytest.approx(100.0)
    Td = I8.tension_capacity(S.props(sec)["A"], 250.0, 410.0, **ti)
    beta = 1.4 - 0.076 * (65.0 / 6.0) * (250.0 / 410.0) * (94.0 / 100.0)
    beta = max(0.7, min(beta, 410.0 * GM0 / (250.0 * GM1)))
    Tdn = 0.9 * Anc * 410.0 / GM1 + beta * Ago * 250.0 / GM0
    Avg, Avn = 130.0 * t, (130.0 - 2.5 * 18.0) * t
    Atg, Atn = 30.0 * t, (30.0 - 9.0) * t
    Tdb = min(Avg * 250.0 / (math.sqrt(3) * GM0) + 0.9 * Atn * 410.0 / GM1,
              0.9 * Avn * 410.0 / (math.sqrt(3) * GM1) + Atg * 250.0 / GM0)
    Tdg = S.props(sec)["A"] * 250.0 / GM0
    assert Td["complete"]
    assert Td["Td_N"] == pytest.approx(min(Tdg, Tdn, Tdb), rel=1e-6)
    ti2, _ = I8.angle_end_connection_inputs("2ISA65X65X6", n_bolts=3, d0_mm=18.0, pitch_mm=50.0, end_mm=30.0,
                                            gauge_mm=35.0)
    assert ti2["Anc_mm2"] == pytest.approx(2 * Anc) and ti2["block"]["Avg_mm2"] == pytest.approx(2 * Avg)
    assert ti2["member"] == "other"                                          # 6.3.4 double angles


def _axial(sec, forces, **kw):
    m = dict({"id": "e1", "section": sec, "grade": "E250", "L_mm": 2000.0, "axial_only": True}, **kw)
    if S.props(sec)["section_type"] == "angle":
        m.setdefault("angle_connection", {"n_bolts": 2, "fixity": "hinged"})
    ti, _ = I8.angle_end_connection_inputs(sec, n_bolts=2, d0_mm=18.0, pitch_mm=50.0, end_mm=30.0, gauge_mm=35.0)
    m["tension_inputs"] = ti
    return I8.member_check_is800(m, [{"combo": c, "P_N": P} for c, P in forces])


def test_axial_member_table3_rows():
    r = _axial("ISA65X65X6", [("1.5DL+1.5LL", 20e3), ("0.9DL+1.5W_Y", -30e3)])
    assert r["found"] and r["table3_slenderness"]["limit"] == 180           # (i) compression from DL + LL
    r = _axial("ISA65X65X6", [("1.5DL+1.5LL", -20e3), ("0.9DL+1.5W_Y", 10e3)])
    assert r["table3_slenderness"]["limit"] == 250                          # (iii) only from WL / EL
    r = _axial("ISA65X65X6", [("1.5DL+1.5LL", -20e3), ("1.2DL+1.2LL+1.2W_X", -5e3)])
    t3 = r["table3_slenderness"]
    assert t3["limit"] == 400 and t3["value"] == pytest.approx(2000.0 / S.props("ISA65X65X6")["r_min"])


def test_axial_member_dc_is_the_governing_axial_ratio():
    r = _axial("ISA65X65X6", [("1.5DL+1.5LL", 20e3), ("0.9DL+1.5W_Y", -60e3)])
    Pd = r["capacities"]["compression"]["Pd_N"]
    Td = r["capacities"]["tension"]["Td_N"]
    assert r["interaction_dc"] == pytest.approx(max(20e3 / Pd, 60e3 / Td))


def test_axial_single_angle_needs_its_end_condition():
    m = {"id": "e1", "section": "ISA65X65X6", "grade": "E250", "L_mm": 2000.0, "axial_only": True}
    r = I8.member_check_is800(m, [{"combo": "1.5DL+1.5LL", "P_N": 10e3}])
    assert r["found"] is False and "angle_connection" in r["reason"]


def test_axial_incomplete_tension_inputs_block():
    m = {"id": "e1", "section": "ISA65X65X6", "grade": "E250", "L_mm": 2000.0, "axial_only": True,
         "angle_connection": {"n_bolts": 2, "fixity": "hinged"}}
    r = I8.member_check_is800(m, [{"combo": "1.5DL+1.5LL", "P_N": -10e3}])
    assert r["found"] is False                                              # rupture / block shear inputs missing


def test_double_angle_chord_beam_column(da65):
    m = {"id": "e3", "section": "2ISA65X65X6", "grade": "E250", "L_mm": 1546.0, "Kz": 0.85, "Ky": 1.0,
         "role": "beam", "LLT_sag_mm": 1546.0, "LLT_hog_mm": 1546.0, "truss_chord": True}
    r = I8.member_check_is800(m, [{"combo": "1.5DL+1.5LL", "P_N": 100e3, "Mz_i_Nmm": -0.5e6, "Mz_j_Nmm": -0.2e6,
                                   "Mz_mid_Nmm": 0.2e6, "Vy_N": 1e3}])
    assert r["found"]
    ia = [c for c in r["per_combo"][0]["checks"] if c.get("section_9_3_1")][0]
    assert ia["section_9_3_1"]["method"].startswith("9.3.1.3")               # semi-compact: linear form
    ltb = I8.ltb_moment_capacity(da65, 1546.0, 250.0)
    assert ltb["found"] and "minor axis" in ltb["ltb"]                      # 8.2.2(a)
    assert ltb["Md_Nmm"] == pytest.approx(I8.design_moment_8_2_1(da65["Zx"], da65["Sx"], 250.0,
                                                                  "semi-compact")["Md_Nmm"])
    assert r["table3_slenderness"]["limit"] == 180                          # chord: a member carrying load


def test_truss_chord_always_in_tension_row_vi(da65):
    m = {"id": "e4", "section": "2ISA65X65X6", "grade": "E250", "L_mm": 1500.0, "Kz": 0.85, "Ky": 1.0,
         "role": "beam", "LLT_sag_mm": 1500.0, "LLT_hog_mm": 1500.0, "truss_chord": True}
    r = I8.member_check_is800(m, [{"combo": "1.5DL+1.5LL", "P_N": -100e3, "Mz_i_Nmm": 0.0, "Mz_j_Nmm": 0.0}])
    assert r["table3_slenderness"]["limit"] == 400


def test_compact_angle_section_uses_conservative_linear_9_3_1_1():
    r = I8.interaction_9_3(P_N=50e3, Mz_Nmm=1e6, My_Nmm=0.0, Nd_N=200e3, Pdz_N=150e3, Pdy_N=150e3, Mdz_Nmm=4e6,
                           Mdy_Nmm=4e6, lambda_z=0.5, lambda_y=0.5, section_class="compact", section_type="double_angle")
    assert r["section_9_3_1"]["dc"] == pytest.approx(50e3 / 200e3 + 1e6 / 4e6)


# ------------------------------------------------------------------------------------------------ truss_design
def _cfg_conn():
    sp = {"n_bolts": 3, "d_mm": 16, "grade": "8.8", "bolt_type": "HSFG", "slip_surface": "clean_mill_scale",
          "d0_mm": 18.0, "pitch_mm": 50.0, "end_mm": 30.0, "gauge_mm": 35.0, "gusset_t_mm": 8.0, "edge": "rolled"}
    return {"truss_connections": {"default": dict(sp, n_bolts=2), "truss_diagonal:ISA65X65X6": sp,
                                  "heel": {"n_bolts": 4, "d_mm": 20, "grade": "8.8", "d0_mm": 22.0, "pitch_mm": 60.0,
                                           "end_mm": 40.0, "t_plate_mm": 10.0, "fu_plate_MPa": 410.0}}}


def test_spec_for_most_specific_wins():
    cfg = _cfg_conn()
    assert TD.spec_for(cfg, "truss_diagonal", "ISA65X65X6")["n_bolts"] == 3
    assert TD.spec_for(cfg, "truss_vertical", "ISA60X60X6")["n_bolts"] == 2
    assert TD.spec_for({}, "truss_vertical", "ISA60X60X6") is None
    ac, ti, rec = TD.member_inputs(cfg, "truss_diagonal", "ISA65X65X6", 2000.0)
    assert ac == {"n_bolts": 3, "fixity": "hinged", "l_mm": 2000.0} and ti["Lc_mm"] == 100.0


def test_bolt_group_double_shear_by_hand(da65):
    import india_connections as C
    sp = dict(_cfg_conn()["truss_connections"]["truss_diagonal:ISA65X65X6"])
    bg = TD.bolt_group(sp, "2ISA65X65X6")
    one = C.bolt_capacity_is800(16, "8.8", nn=2, ns=0, t_mm=8.0, fu_plate_MPa=410.0, e_mm=30.0, p_mm=50.0,
                                d0_mm=18.0, lj_mm=100.0)
    assert bg["double_shear"] and bg["governs"] == "gusset"                 # 8 mm gusset < 2 x 6 mm angle legs
    assert bg["capacity_N"] == pytest.approx(3 * one["Vdb_N"])
    assert one["Vdsb_N"] == pytest.approx(800.0 / math.sqrt(3) * 2 * 157.0 / 1.25)


def test_detailing_and_stitches(da65):
    sp = _cfg_conn()["truss_connections"]["truss_diagonal:ISA65X65X6"]
    rows = dict(TD.detailing_rows(sp, "2ISA65X65X6", compression=True))
    assert all(r["ok"] for r in rows.values())
    bad = dict(TD.detailing_rows(dict(sp, gauge_mm=45.0), "ISA65X65X6", compression=True))
    assert any(r["ok"] is False for k, r in bad.items() if "edge distance" in k)        # 65 - 45 = 20 < 27
    st = TD.stitch_record("2ISA65X65X6", L_mm=1546.0, KL_over_r_member=60.0, compression=True)
    assert st["n_intermediate"] >= 2 and st["spacing_mm"] / da65["r1_min_mm"] <= 36.0 + 1e-9


def test_knee_geometry_and_12_10_2_1(da65):
    nodes = {1: (0.0, 0.0, 6500.0), 2: (0.0, 0.0, 5000.0), 3: (0.0, 1500.0, 6500.0)}
    knee = {"id": "K0-L", "heel_node": 1, "knee_node": 2, "chord_node": 3, "brace_section": "ISA65X65X6",
            "brace_role": "truss_diagonal", "span_mm": 18000.0, "V_gravity_N": 40e3}
    g = TD.knee_geometry(nodes, knee)
    assert g["lever_arm_mm"] == pytest.approx(1500.0 / math.sqrt(2)) and g["angle_deg"] == pytest.approx(45.0)
    Nd = 80e3
    rows = {r["id"]: r for r in TD.knee_checks(knee, {}, _cfg_conn(), nodes=nodes, member_capacity=Nd)}
    kb = rows["12.10.2.1_knee_brace_connection"]
    assert kb["value"] == pytest.approx(1.2 * Nd)
    hs = rows["12.10.2.4_heel_seat"]
    M = Nd * g["lever_arm_mm"]
    R = math.hypot(1.2 * Nd / math.sqrt(2), 40e3 + 2 * 1.2 * M / 18000.0)
    assert hs["value"] == pytest.approx(R)
    none = TD.knee_checks(knee, {}, _cfg_conn(), nodes=nodes, member_capacity=None)
    assert none[0]["ok"] is None


# ------------------------------------------------------------------------------------------------ engine / static model
def test_add_truss_element_and_kind_map():
    import openseespy.opensees as ops
    import static_model as SM
    E._TRUSS.clear()
    ops.wipe(); ops.model("basic", "-ndm", 3, "-ndf", 6)
    ops.node(1, 0.0, 0.0, 0.0); ops.node(2, 1000.0, 0.0, 1000.0)
    E.add_truss(5, 1, 2, "ISA65X65X6", group="diagonal", truss="T1")
    E.add_truss(6, 2, 1, "ISA65X65X6", group="diagonal", truss="T1")       # the material is defined once per domain
    assert 5 in ops.getEleTags() and E._TRUSS[5]["group"] == "diagonal"
    E.register_truss_member(7, group="top_chord", truss="T1", sec="2ISA65X65X6")
    assert E._TRUSS[7]["continuous"] is True
    kinds = SM._member_kinds({"braces": [{"n1": 1, "n2": 2, "sec": "ISA65X65X6", "kind": "truss"}],
                              "cols": [], "beams": []})
    assert kinds[frozenset((1, 2))] == ("truss", "ISA65X65X6")
    assert TD.role_of("knee_brace") == "truss_knee_brace" and TD.is_chord_role("truss_top_chord")


def _plane_cfg():
    return {"NX": 1, "NY": 3, "SX": 6000.0, "SY": 6000.0, "heights": [6500.0], "units": "N-mm", "D_roof": 0.10,
            "Lr": 0.669, "snow": 0.0, "clad": 0.0,
            "roof_planes": [{"axis": "Y", "eave_coords_mm": [0.0, 18000.0], "ridge_coord_mm": 9000.0,
                             "eave_z_mm": 6500.0, "ridge_z_mm": 8750.0, "lines": [0, 1], "purlins_at_nodes": True}]}


def test_purlins_at_nodes_gravity_and_wind_totals():
    import openseespy.opensees as ops
    import roof_geometry as RG
    import static_model as SM
    import staad_loads as SL
    cfg = _plane_cfg()
    pl = RG.planes(cfg)[0]
    ops.wipe(); ops.model("basic", "-ndm", 3, "-ndf", 6)
    ops.node(1, 0.0, 0.0, 6500.0); ops.node(2, 0.0, 1500.0, 6875.0)
    ops.geomTransf("Linear", 3, 0.0, 0.0, 1.0)
    ops.element("elasticBeamColumn", 9, 1, 2, 1506.0, 2e5, 8e4, 1e4, 6e5, 1.3e6, 3)
    ops.timeSeries("Linear", 1); ops.pattern("Plain", 1, 1)
    L = math.hypot(1500.0, 375.0)
    b = {"A": 1, "B": 2, "L": L, "segs": [9], "rp": (pl, "rafter"), "sec": "2ISA65X65X6", "_A": 1506.0}
    with SL._Recorder() as rec:
        tot = SM._plane_member_gravity(cfg, b, 1.0, 1.0, 0.0, 0.0, 1.0, False, (None, None, None))
    nodal = [c for c in rec.calls if c[0] == "node"]
    assert len(nodal) == 2 and not [c for c in rec.calls if c[0] == "ele"]  # no self-weight asked: nodes only
    Fz = sum(c[2][2] for c in nodal)
    trib = RG.rafter_trib_mm(pl, 0.0)
    assert trib == pytest.approx(3000.0)
    assert -Fz == pytest.approx((0.10 + 0.669) * 3.0 * 1.5 * 1e3, rel=1e-6)       # kN/m2 x m x m -> N
    assert tot == pytest.approx(-Fz)
    pat = {"wind_axis": "Y", "sign": 1, "roof_windward_kNm2": -0.6, "roof_leeward_kNm2": -0.4}
    with SL._Recorder() as rec2:
        W = SM._plane_member_wind(b, pat, 1.0, 1, 9000.0, "lo", -0.6, -0.4)
    F = [sum(c[2][k] for c in rec2.calls if c[0] == "node") for k in range(3)]
    n = (0.0, -375.0 / L, 1500.0 / L)                                        # upward normal of the slope
    assert W == pytest.approx(-0.6 * 3.0 * (L / 1000.0) * 1e3, rel=1e-6)
    assert F[2] == pytest.approx(-W * n[2], rel=1e-6) and F[1] == pytest.approx(-W * n[1], rel=1e-6)


def test_tonnage_counts_truss_members_as_primary():
    import peb_checks as PC
    info = {"ele": [(1, "beam", "2ISA65X65X6", 1, 2), (2, "truss", "ISA65X65X6", 2, 3), (3, "beam", "CHS114.3X3.6", 3, 4)],
            "truss": {1: {"group": "top_chord"}, 2: {"group": "diagonal"}}}
    t = PC.tonnage({}, info, {1: 1000.0, 2: 1000.0, 3: 1000.0}, {}, None)
    assert t["by_element"]["1"]["group"] == "primary" and t["by_element"]["2"]["group"] == "primary"
    assert t["by_element"]["3"]["group"] == "bracing"                        # an eave strut stays bracing


# ------------------------------------------------------------------------------------------------ outputs / report
def test_staad_labels_and_double_angle_property():
    import peb_outputs as PO
    assert PO.staad_label("MB300") == "ISMB300" and PO.staad_label("MC150") == "ISMC150"
    assert PO.staad_label("ISA65X65X6") == "ISA65X65X6" and PO.staad_label("WPB160X160X30.44") == "WPB160X160X30.44"


def test_member_input_record_truss_fields():
    import design_pipeline as DP
    S.register_double_angle("2ISA65X65X6", "ISA65X65X6", 8.0)
    cfg = dict(_cfg_conn(), steel_grade="E250", K_factors={"truss_diagonal": {"Kz": 1.0, "Ky": 1.0}})
    m = DP._member_input_record(cfg, 5, "truss", "ISA65X65X6", 1, 2, 2000.0, "truss_diagonal")
    assert m["axial_only"] and m["angle_connection"]["n_bolts"] == 3 and m["tension_inputs"]["Lc_mm"] == 100.0
    c = DP._member_input_record(cfg, 6, "beam", "2ISA65X65X6", 1, 2, 1500.0, "truss_bottom_chord")
    assert c["truss_chord"] and "axial_only" not in c and c["tension_inputs"]["member"] == "other"


def test_truss_report_section_rulings_and_public_text():
    import peb_report as PR
    import report_public as PUB
    cfg = dict(_cfg_conn(), flange_braces={"column": {"girts_mm": [3000.0], "fly_braces_mm": [3000.0]}})
    rows = PR.rulings_applied(cfg)
    assert [r[0] for r in rows] == ["D-T4", "D-T5", "D-T6", "D-T10"]
    assert PUB.ruling_meaning("D-T10").startswith("knee-braced truss portal")
    pkg = {"peb": {"tonnage": {"kg": {"primary": 1000.0}, "kg_per_m2": {"primary": 2.0, "total": 2.0},
                               "total_kg": 1000.0, "plan_area_m2": 500.0, "basis": "take-off"}},
           "members": [{"inputs": {"role": "truss_top_chord", "section": "2ISA65X65X6", "n_elements": 84,
                                   "P_comp_N": 90e3, "P_tens_N": 40e3}, "DC": 0.8, "governing_check": "IS 800 9.3"}],
           "connections": [{"id": "conn-truss_top_chord-2ISA65X65X6", "section": "2ISA65X65X6", "DC": 0.5,
                            "demand": {"axial_N": 90e3}, "bolt_group": {"capacity_N": 180e3},
                            "stitches": {"n_intermediate": 2, "spacing_mm": 515.0}}],
           "capacity_design": {"section12": {"checks": [
               {"id": "12.10.2.1_knee_brace_connection", "member": "K1-L", "value": 96e3, "limit": 150e3, "dc": 0.64,
                "knee": {"N_d_N": 80e3, "lever_arm_mm": 1061.0, "M_del_Nmm": 84.9e6}}]}}}
    html_ = PR.section(cfg, pkg, "/nonexistent")
    assert "Angle roof trusses and knee-braced portals" in html_ and "top chord" in html_
    assert "PEB &mdash; web-tapered" not in html_
    printed = PUB.public_html(html_)
    assert not PUB.leaks(printed)
    assert "Steltic design ruling D-T10" in printed
