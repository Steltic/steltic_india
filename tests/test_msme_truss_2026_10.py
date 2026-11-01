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
          "d0_mm": 18.0, "pitch_mm": 50.0, "end_mm": 30.0, "gauge_mm": 35.0, "gusset_t_mm": 8.0, "edge": "rolled",
          "end_cut": "sawn", "gusset_end_mm": 35.0, "gusset_edge_mm": 40.0, "gusset_K": 0.65, "gusset_free_mm": 150.0}
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
    sp.pop("gusset_end_mm")                       # the gusset end distance defaults to the member end distance
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
    assert "HSFG 8.8" in PUB.ruling_meaning("D-T10") and "complete-penetration welds" in PUB.ruling_meaning("D-T10")
    bare = PUB.public_html("<p>The knees follow D-T10.</p>")
    assert "Steltic design ruling D-T10 (knee-braced truss portal" in bare and "HSFG 8.8 bolts" in bare
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


# ------------------------------------------------------------------------------------------------ pipeline plumbing
def test_section12_cfg_carries_the_truss_connections_to_the_knee_checks():
    """First IN_Ex21 gold run: every knee was 'not evaluated' because the Section 12 cfg did not carry
    cfg['truss_connections'].  design_india now builds it with section12_cfg, which does."""
    import design_pipeline as DP
    cfg = dict(_cfg_conn(), zone="II", I=1.0, heights=[6500.0])
    s12 = DP.section12_cfg(cfg)
    assert s12["truss_connections"] is cfg["truss_connections"] and s12["zone"] == "II"
    assert "truss_connections" not in DP.section12_cfg({"zone": "II"})
    nodes = {1: (0.0, 0.0, 6500.0), 2: (0.0, 0.0, 5000.0), 3: (0.0, 1500.0, 6500.0)}
    knee = {"id": "K0-L", "heel_node": 1, "knee_node": 2, "chord_node": 3, "brace_section": "ISA65X65X6",
            "brace_role": "truss_diagonal", "span_mm": 18000.0, "V_gravity_N": 40e3, "Pd_N": 80e3, "Tdg_N": 169.1e3,
            "Tdn_N": 180e3, "Tdb_N": 175e3}
    rows = TD.knee_checks(knee, {}, s12, nodes=nodes, member_capacity=169.1e3)
    assert rows and all(r["dc"] is not None for r in rows)
    bare = TD.knee_checks(knee, {}, DP.section12_cfg({"zone": "II"}), nodes=nodes, member_capacity=80e3)
    assert all(r["dc"] is None for r in bare)


def test_column_line_read_from_the_grid_end():
    """First IN_Ex21 gold run: the upper piece of a gable post runs from the truss bottom-chord node (off the grid,
    tag 182400 decodes to the truss-node line (824, 0)) to the post top on the grid (0, 1).  Its column line is now
    read from the grid end, so it is a gravity column of line (0, 1), not a frame column of a truss-node line."""
    import design_pipeline as DP
    grid = {(0, 0), (0, 1), (0, 2), (0, 3)}
    assert DP.column_line(182400, 100001, grid) == (0, 1)
    assert DP.column_line(1, 100001, grid) == (0, 1)                # an ordinary column: its first node
    assert DP.column_line(182400, 100001, None) == (824, 0)        # no grid information: as before


def test_activity_appendix_without_a_log_is_plain_text(monkeypatch):
    """A job designed without a tool-call log (IN_Ex21) printed the developer note '[no activity_log.jsonl found --
    call new_activity_log() ...]' in Appendix C.  It now says so in plain words."""
    import report as R
    import report_public as PUB
    monkeypatch.setattr(R, "_load_activity", lambda name: ([], None))
    h = R._activity_section("IN_Ex21_MSME_angle_truss_shed_Hosur")
    assert "Appendix C" in h and "No tool-call log was recorded" in h
    assert "activity_log" not in h and "new_activity_log" not in h and "MCP" not in h
    assert not PUB.leaks(PUB.public_html(h))


def test_take_off_prints_the_sourced_typical_range():
    import peb_report as PR
    import report_public as PUB
    bm = {"lo_kg_m2": 27.7, "hi_kg_m2": 35.8, "basis": "conventional hot-rolled sheds of 15 m and 20 m span",
          "source": "Kumar and Grover, IJRASET 2022, Table 4"}
    cfg = dict(_cfg_conn(), tonnage_benchmark=bm)
    pkg = {"peb": {"tonnage": {"kg": {"primary": 15000.0}, "kg_per_m2": {"primary": 23.1, "total": 31.0},
                               "total_kg": 20000.0, "plan_area_m2": 648.0, "basis": "take-off"}},
           "members": [], "connections": []}
    html_ = PR.section(cfg, pkg, "/nonexistent")
    assert "27.7 to 35.8 kg/m2" in html_ and "IJRASET 2022" in html_ and "31.0 kg/m2 (within the range)" in html_
    assert not PUB.leaks(PUB.public_html(html_))
    assert "Typical steel" not in PR.section(_cfg_conn(), pkg, "/nonexistent")       # nothing without a source


def test_d_t10_recorded_with_its_meaning_in_the_rulings_register():
    """D-T10 is listed with the other owner decisions (docs/PEB_LIMITATIONS.md) with its full meaning."""
    from pathlib import Path
    doc = (Path(ROOT) / "docs" / "PEB_LIMITATIONS.md").read_text(encoding="utf-8")
    row = [ln for ln in doc.splitlines() if ln.startswith("| D-T10")]
    assert len(row) == 1
    for must in ("12.10.2.1", "1.2 times", "knee brace", "HSFG 8.8", "complete-penetration", "2026-11-01"):
        assert must in row[0], must


# ------------------------------------------------------------------------------------------------ review 2026-11
def test_d_t10_knee_uses_the_force_the_brace_delivers_in_either_direction():
    """HIGH finding: the knee brace works both ways under reversing wind.  N_del = max(Pd, Tdg = Ag fy / gamma_m0);
    every knee-brace connection takes 1.2 N_del, the gusset buckling 1.2 Pd, the heel the matching horizontal force;
    the brace's bolted end must not be weaker than its gross yield (the brace yields first)."""
    sec = "ISA90X90X8"
    A = S.props(sec)["A"]
    Pd, Tdg = 114.7e3, A * 250.0 / GM0
    assert Tdg == pytest.approx(315.9e3, rel=1e-3) and Tdg > Pd          # tension governs the deliverable force
    sp = {"n_bolts": 8, "d_mm": 16, "grade": "8.8", "bolt_type": "HSFG", "d0_mm": 18.0, "pitch_mm": 50.0,
          "end_mm": 35.0, "gauge_mm": 50.0, "gusset_t_mm": 8.0, "edge": "rolled", "end_cut": "sheared",
          "gusset_end_mm": 35.0, "gusset_edge_mm": 40.0, "gusset_K": 0.65, "gusset_free_mm": 150.0}
    cfg = {"truss_connections": {"truss_knee_brace:%s" % sec: sp, "heel": _cfg_conn()["truss_connections"]["heel"]}}
    nodes = {1: (0.0, 0.0, 6500.0), 2: (0.0, 0.0, 5000.0), 3: (0.0, 1500.0, 6500.0)}
    knee = {"id": "K1-L", "heel_node": 1, "knee_node": 2, "chord_node": 3, "brace_section": sec,
            "brace_role": "truss_knee_brace", "span_mm": 18000.0, "V_gravity_N": 40e3, "Pd_N": Pd, "Tdg_N": Tdg,
            "Tdn_N": 348.8e3, "Tdb_N": 413.6e3}
    Nd = max(Pd, Tdg)
    rows = {r["id"]: r for r in TD.knee_checks(knee, {}, cfg, nodes=nodes, member_capacity=Nd)}
    assert rows["12.10.2.1_knee_brace_connection"]["value"] == pytest.approx(1.2 * Tdg)         # not 1.2 min(Pd, Td)
    assert rows["12.10.2.1_knee_gusset_whitmore_yield"]["value"] == pytest.approx(1.2 * Tdg)
    assert rows["12.10.2.1_knee_gusset_block_shear"]["value"] == pytest.approx(1.2 * Tdg)
    assert rows["12.10.2.1_knee_gusset_buckling"]["value"] == pytest.approx(1.2 * Pd)           # compression only
    yf = rows["12.10.2.1_knee_brace_yields_first"]
    assert yf["value"] == pytest.approx(Tdg) and yf["limit"] == pytest.approx(348.8e3) and yf["ok"]
    e = 1500.0 / math.sqrt(2.0)
    R = math.hypot(1.2 * Tdg / math.sqrt(2.0), 40e3 + 2 * 1.2 * Tdg * e / 18000.0)
    assert rows["12.10.2.4_heel_seat"]["value"] == pytest.approx(R)
    assert all(r["ok"] for r in rows.values()), {k: r.get("dc") for k, r in rows.items()}
    # a weak bolted end (rupture below gross yield) is flagged: the brace would not yield first
    weak = dict(knee, Tdn_N=0.9 * Tdg)
    w = {r["id"]: r for r in TD.knee_checks(weak, {}, cfg, nodes=nodes, member_capacity=Nd)}
    assert w["12.10.2.1_knee_brace_yields_first"]["ok"] is False
    # 3 bolts (the first gold) cannot develop 1.2 Tdg
    few = {"truss_connections": dict(cfg["truss_connections"], **{"truss_knee_brace:%s" % sec: dict(sp, n_bolts=3)})}
    f = {r["id"]: r for r in TD.knee_checks(knee, {}, few, nodes=nodes, member_capacity=Nd)}
    assert f["12.10.2.1_knee_brace_connection"]["dc"] > 1.0


def test_member_wind_combinations_count_as_wind_in_table3():
    """Member-wind labels (WM0+, WM90-R, ...) are wind combinations: compression that arises only in them is Table 3
    row (iii) 250, in both the axial check and the general member check; row (i) names a gravity combination."""
    for lab in ("1.5DL+1.5WM0+", "0.9DL+1.5WM90-R", "1.2DL+1.2LL+1.2WM0-", "1.2DL+1.2LL-1.2W_X", "1.5DL+1.5EQ_Y"):
        assert I8.is_lateral_combo(lab), lab
    for lab in ("1.5DL+1.5LL", "1.5DL+1.5LL+N_X", "1.2DL+1.2LL+0.5S"):
        assert not I8.is_lateral_combo(lab), lab
    m = {"id": "d", "section": "ISA70X70X6", "grade": "E250", "L_mm": 2401.0, "Kz": 1.0, "Ky": 1.0,
         "role": "truss_diagonal", "angle_connection": {"n_bolts": 2, "fixity": "hinged"},
         "tension_inputs": {"member": "angle", "Anc_mm2": 300.0, "Ago_mm2": 400.0, "w_mm": 70.0, "t_mm": 6.0,
                            "bs_mm": 104.0, "Lc_mm": 50.0,
                            "block": {"Avg_mm2": 510.0, "Avn_mm2": 348.0, "Atg_mm2": 180.0, "Atn_mm2": 126.0}}}
    rec = lambda c, P: {"combo": c, "P_N": P}
    wind_only = I8.axial_member_check_is800(m, [rec("1.5DL+1.5LL", -20e3), rec("0.9DL+1.5WM0-R", 25e3),
                                                rec("1.5DL+0.3", 0.3)])           # 0.3 N of noise is not compression
    assert wind_only["table3_slenderness"]["limit"] == 250
    grav = I8.axial_member_check_is800(m, [rec("1.5DL+1.5LL", 5e3), rec("0.9DL+1.5WM0-R", 25e3)])
    t3 = grav["table3_slenderness"]
    assert t3["limit"] == 180 and t3["governing_combo"] == "1.5DL+1.5LL"          # row (i) names the gravity case
    beam = {"id": "s", "section": "CHS114.3X3.6", "grade": "YSt 310", "process": "ERW", "role": "beam", "L_mm": 6000.0,
            "Kz": 1.0, "Ky": 1.0, "LLT_sag_mm": 6000.0, "LLT_hog_mm": 6000.0, "beam_axial_negligible_ratio": 0.0}
    z = dict(Mz_i_Nmm=0.0, Mz_j_Nmm=0.0, Mz_mid_Nmm=0.0, My_i_Nmm=0.0, My_j_Nmm=0.0, Vy_N=0.0, Vz_N=0.0)
    r = I8.member_check_is800(dict(beam, role="column"), [dict(z, combo="1.5DL+1.5WM90-", P_N=20e3),
                                                          dict(z, combo="1.5DL+1.5LL", P_N=0.3)])
    assert r["table3_slenderness"]["limit"] == 250


def test_non_angle_truss_member_takes_the_general_member_check():
    """A CHS knee brace / web with a declared spec does not crash: the general member check, no angle inputs, and the
    end connection reported as not covered."""
    import design_pipeline as DP
    cfg = dict(_cfg_conn(), steel_grade="E250", K_factors={"truss_knee_brace": {"Kz": 1.0, "Ky": 1.0}})
    ac, ti, rec = TD.member_inputs(cfg, "truss_knee_brace", "CHS76.1X3.6", 2121.0)
    assert ac is None and ti is None and rec.get("general_member_check")
    m = DP._member_input_record(cfg, 9, "truss", "CHS76.1X3.6", 1, 2, 2121.0, "truss_knee_brace")
    assert "axial_only" not in m
    envt = {9: {"comp": 50e3, "tens": 40e3}}
    cr = TD.end_connection_record(cfg, "truss_knee_brace", "CHS76.1X3.6", [9], envt, {}, {9: 2121.0})
    assert cr["DC"] is None and cr["checks"][0]["ok"] is None
    nodes = {1: (0.0, 0.0, 6500.0), 2: (0.0, 0.0, 5000.0), 3: (0.0, 1500.0, 6500.0)}
    knee = {"id": "K0-L", "heel_node": 1, "knee_node": 2, "chord_node": 3, "brace_section": "CHS76.1X3.6",
            "brace_role": "truss_knee_brace", "span_mm": 18000.0, "V_gravity_N": 40e3}
    rows = {r["id"]: r for r in TD.knee_checks(knee, {}, cfg, nodes=nodes, member_capacity=90e3)}
    assert rows["12.10.2.1_knee_brace_connection"]["ok"] is None


def test_brief_asks_for_hsfg_8_8_truss_bolts():
    from pathlib import Path
    t = (Path(ROOT) / "test_buildings" / "IN_Ex21_MSME_angle_truss_shed_Hosur.txt").read_text(encoding="utf-8")
    flat = " ".join(t.split())
    assert "HSFG property class 8.8" in flat and "12.4.1" in flat and "D-T10" in flat
    assert "4.6 bolts" not in flat


def test_double_angle_7_5_2_1_conditions():
    """>= 2 bolts at each end for 7.5.2.1 (one bolt: 7.5.2.2 -> 7.5.1, each angle through one leg); KL in the gusset
    plane >= 0.7 L, normal to it = L."""
    S.register_double_angle("2ISA65X65X6", "ISA65X65X6", 8.0)
    base = {"id": "w", "section": "2ISA65X65X6", "grade": "E250", "L_mm": 2000.0, "role": "truss_diagonal",
            "tension_inputs": {"T_N": 1e6}}
    f = [{"combo": "1.5DL+1.5LL", "P_N": 10e3}]
    r = I8.axial_member_check_is800(dict(base, Kz=0.5, Ky=0.5, angle_connection={"n_bolts": 2, "fixity": "hinged"}), f)
    c = r["capacities"]["compression"]
    assert c["rule"] == "7.5.2.1" and "raised" in c["note"]
    ref = I8.compression_capacity(S.props("2ISA65X65X6"), 250.0, KLz_mm=0.7 * 2000.0, KLy_mm=2000.0)
    assert c["Pd_N"] == pytest.approx(ref["Pd_N"])
    one = I8.axial_member_check_is800(dict(base, Kz=1.0, Ky=1.0, angle_connection={"n_bolts": 1, "fixity": "hinged"}), f)
    c1 = one["capacities"]["compression"]
    sa = I8.single_angle_7_5_1_2("ISA65X65X6", 250.0, 2000.0, n_bolts=1, fixity="hinged")
    assert c1["rule"] == "7.5.2.2" and c1["Pd_N"] == pytest.approx(2.0 * sa["Pd_N"])
    none = I8.axial_member_check_is800(dict(base, Kz=1.0, Ky=1.0), f)
    assert none["ok"] is None and "7.5.2.1" in none["reason"]


def test_stitches_600_mm_and_7_8_4_bolt_size():
    S.register_double_angle("2ISA100X100X10", "ISA100X100X10", 10.0)
    st = TD.stitch_record("2ISA100X100X10", L_mm=3000.0, KL_over_r_member=120.0, compression=True)
    assert st["spacing_mm"] <= 600.0                       # 10.2.5.5 (40 r1 alone would give about 780 mm)
    assert TD.stitch_bolt_check("2ISA100X100X10", 16)["ok"] is True          # t 10 mm: >= 16 mm
    S.register_double_angle("2ISA100X100X12", "ISA100X100X12", 10.0)
    assert TD.stitch_bolt_check("2ISA100X100X12", 16)["ok"] is False         # t 12 mm: >= 20 mm
    assert TD.stitch_bolt_check("2ISA100X100X12", 20)["ok"] is True


def test_gusset_block_shear_buckling_and_cut_end_by_hand():
    sp = dict(_cfg_conn()["truss_connections"]["truss_diagonal:ISA65X65X6"])
    rows = dict(TD.gusset_rows(sp, 100e3, 60e3))
    bs = rows["gusset block shear (6.4.1)"]
    Ls, t, d0, edge = 35.0 + 100.0, 8.0, 18.0, 40.0
    Avg, Avn, Atg, Atn = Ls * t, (Ls - 2.5 * d0) * t, edge * t, (edge - 0.5 * d0) * t
    fy, fu = 250.0, 410.0
    Tdb = min(Avg * fy / (math.sqrt(3) * GM0) + 0.9 * Atn * fu / GM1, 0.9 * Avn * fu / (math.sqrt(3) * GM1) + Atg * fy / GM0)
    assert bs["limit"] == pytest.approx(Tdb)
    gb = rows["gusset buckling on the Whitmore width (compression)"]
    bw = 2 * 100.0 * math.tan(math.radians(30))
    assert gb["value"] == pytest.approx(60e3) and gb["limit"] == pytest.approx(
        bw * t * _fcd(fy, 0.65 * 150.0 / (t / math.sqrt(12.0))))
    # undeclared gusset geometry -> not evaluated, never assumed
    bare = dict(TD.gusset_rows({k: v for k, v in sp.items() if not k.startswith(("gusset_edge", "gusset_K",
                                                                                 "gusset_free"))}, 100e3, 60e3))
    assert bare["gusset block shear (6.4.1)"]["ok"] is None
    assert bare["gusset buckling on the Whitmore width"]["ok"] is None
    # sheared angle ends need 1.7 d0 (30.6 mm for M16): 30 mm fails, sawn ends 1.5 d0 pass
    she = dict(TD.detailing_rows(dict(sp, end_cut="sheared"), "ISA65X65X6", compression=True))
    saw = dict(TD.detailing_rows(sp, "ISA65X65X6", compression=True))
    assert any(r["ok"] is False for k, r in she.items() if k.startswith("end distance"))
    assert all(r["ok"] for k, r in saw.items() if k.startswith("end distance"))


def test_chord_connection_checks_the_gusset_for_the_full_chord_force():
    """The heel / apex gusset takes the full chord force (review 2026-11): the chord record carries the gusset rows."""
    S.register_double_angle("2ISA70X70X6-G8", "ISA70X70X6", 8.0)
    cfg = {"truss_connections": {"truss_top_chord": dict(_cfg_conn()["truss_connections"]["truss_diagonal:ISA65X65X6"],
                                                         n_bolts=4, gauge_mm=40.0)}}
    envt = {1: {"comp": 166e3, "tens": 80e3}}
    cr = TD.end_connection_record(cfg, "truss_top_chord", "2ISA70X70X6-G8", [1], envt, {}, {1: 1546.0})
    names = [c["name"] for c in cr["checks"]]
    assert any("Whitmore" in n and "full chord force" in n for n in names)
    assert any("block shear" in n and "full chord force" in n for n in names)
    wm = [c for c in cr["checks"] if "Whitmore" in c["name"] and "yield" in c["name"]][0]
    assert wm["value"] == pytest.approx(166e3)
    assert any(n.startswith("back-to-back interconnection bolts M16 (7.8.4)") for n in names)


def test_single_angle_bending_uses_the_9_3_1_1_linear_form():
    """member_check_is800 passes section_type 'angle' for a single angle (review 2026-11, a behaviour change outside
    the new truss paths): 9.3.1 then uses the conservative linear form of 9.3.1.1, not the 9.3.1.2 reduced moments
    (those are for I / H, box and tube sections).  No earlier gold has an angle in this check."""
    kw = dict(P_N=20e3, Mz_Nmm=1.0e6, My_Nmm=0.2e6, Nd_N=300e3, Pdz_N=250e3, Pdy_N=200e3, Mdz_Nmm=4.0e6, Mdy_Nmm=2.0e6,
              lambda_z=0.5, lambda_y=0.6, lambda_LT=0.3, section_class="compact")
    ang = I8.interaction_9_3(section_type="angle", **kw)
    i_h = I8.interaction_9_3(section_type="I", **kw)
    lin = 20e3 / 300e3 + 1.0e6 / 4.0e6 + 0.2e6 / 2.0e6
    assert ang["section_9_3_1"]["dc"] == pytest.approx(lin) and "9.3.1.1" in ang["section_9_3_1"]["method"]
    assert i_h["section_9_3_1"]["dc"] < lin                       # the I / H form would have been unconservative
    import inspect
    assert '"angle", "double_angle")' in inspect.getsource(I8.member_check_is800)    # the check passes the type


def test_double_angle_label_carries_the_gusset_and_guards_overwrites():
    assert S.double_angle_label("ISA70X70X6", 8.0) == "2ISA70X70X6-G8"
    assert S.double_angle_label("ISA70X70X6") == "2ISA70X70X6"
    S.register_double_angle("2ISA75X75X6-G10", "ISA75X75X6", 10.0)
    with pytest.raises(ValueError):
        S.register_double_angle("2ISA75X75X6-G10", "ISA75X75X6", 8.0)
    import peb_outputs as PO
    assert S.props("2ISA75X75X6-G10")["gap_mm"] == 10.0 and PO.staad_label("2ISA75X75X6-G10") == "2ISA75X75X6-G10"
