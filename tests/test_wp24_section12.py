"""WP2.4 / WP2.8 IS 800 Section 12 system checks and IS 18168 EBF links (spec 4.2, HR800-03/05/17, HREX1-Ex2-01)."""
import os
import sys

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "steel_engine"))

import india_is800 as I8  # noqa: E402
import india_is800_s12 as S12  # noqa: E402


def _brace(mid, sec, L, **kw):
    m = {"id": mid, "role": "brace", "section": sec, "L_mm": L, "Kz": 1.0, "Ky": 1.0, "sfrs": True}
    m.update(kw)
    return m


def test_scbf_connection_demand_1p1_fy_ag():
    m = _brace("B1", "CHS219.1X8", 6000, fy_MPa=250, fu_MPa=410)
    md = {"members": [m], "forces": {"B1": [{"combo": "1.5DL+1.5EQ", "P_N": 395.7e3}]}}
    d = S12.brace_connection_force("SCBF", m, md)
    assert d["demand_N"] / 1e3 == pytest.approx(1459.2, abs=0.2)   # regardless of the 395.7 kN analysis force


def test_ocbf_connection_demand_min_of_three():
    m = _brace("B1", "CHS219.1X8", 6000, fy_MPa=250, fu_MPa=410)
    md = {"members": [m], "forces": {"B1": [{"combo": "0.9DL+2.5EQ", "family": "12.2.3", "P_N": -600e3}]}}
    d = S12.brace_connection_force("OCBF", m, md)
    assert d["demand_N"] == pytest.approx(600e3)
    assert "12.2.3" in d["basis"]


def test_ocbf_klr_131_fails_and_ex1_104p8_passes():
    ocbf = _brace("B8", "CHS219.1X8", 131 * 74.69, grade="E250 B0", fy_MPa=250, fu_MPa=410)
    r = S12.brace_member_checks("OCBF", ocbf, {"forces": {}}, {})
    k = next(c for c in r if c["id"] == "brace_KL_r")
    assert k["value"] == pytest.approx(131, abs=0.2) and k["limit"] == 120 and k["ok"] is False
    ex1 = _brace("B1", "CHS168.3X8", 104.8 * 56.74, grade="YSt 240", process="ERW")
    r = S12.brace_member_checks("SCBF", ex1, {"forces": {}}, {})
    k = next(c for c in r if c["id"] == "brace_KL_r")
    assert k["value"] == pytest.approx(104.8, abs=0.1) and k["ok"] is True
    mat = next(c for c in r if c["id"] == "material_E250B")
    assert mat["ok"] is False          # IS 1161 YSt tube is not E250B (12.8.2.1)


def test_panel_zone_individual_thickness_fails():
    pz = I8.panel_zone_check(d_col_mm=400, tw_mm=6, bf_mm=400, tf_mm=20, d_beam_mm=600, V_design_N=1e5,
                             fy_MPa=250, doubler_t_mm=6)
    assert pz["t_min_mm"] == pytest.approx(10.67, abs=0.01)
    assert pz["thickness_ok"] is False and pz["pass"] is False


def _ex2_model(fy=None):
    """Ex2 SMF: 2 bays in X, 9 storeys, WPB400 (1-3) / WPB360X370 (4-6) / WPB340 (7-9) columns, NPB550 beams."""
    col_sec = {1: "WPB400X400X191.11", 2: "WPB400X400X191.11", 3: "WPB400X400X191.11",
               4: "WPB360X370X150.87", 5: "WPB360X370X150.87", 6: "WPB360X370X150.87",
               7: "WPB340X300X104.78", 8: "WPB340X300X104.78", 9: "WPB340X300X104.78"}
    nodes, members = {}, []
    for k in range(10):
        for i in range(3):
            nodes["n%d_%d" % (i, k)] = (i * 8000.0, 0.0, k * 3500.0)
    for k in range(1, 10):
        for i in range(3):
            members.append({"id": "c%d_%d" % (i, k), "role": "column", "section": col_sec[k], "grade": "E250",
                            "node_i": "n%d_%d" % (i, k - 1), "node_j": "n%d_%d" % (i, k), "L_mm": 3500.0,
                            "major_axis_plane": "X", **({"fy_MPa": fy} if fy else {})})
        for i in range(2):
            members.append({"id": "b%d_%d" % (i, k), "role": "beam", "section": "NPB550X210X105.52", "grade": "E250",
                            "node_i": "n%d_%d" % (i, k), "node_j": "n%d_%d" % (i + 1, k), "L_mm": 8000.0,
                            **({"fy_MPa": fy} if fy else {})})
    return nodes, members


def test_scwb_per_joint_from_connectivity_ex2():
    nodes, members = _ex2_model(fy=250)
    joints = S12.joints_from_model(nodes, members)
    md = {"members": members, "forces": {}, "joints": joints}
    res = {j["id"]: S12.scwb_joint(j, md) for j in joints}
    interior_l7 = res["Jn1_7-X"]
    assert interior_l7["value"] == pytest.approx(0.67, abs=0.01) and interior_l7["ok"] is False
    assert res["Jn1_2-X"]["value"] == pytest.approx(1.34, abs=0.01)
    assert res["Jn1_3-X"]["value"] == pytest.approx(1.19, abs=0.01)
    # thickness-dependent fy (IS 2062 Table 3) lowers it further
    nodes, members = _ex2_model()
    md = {"members": members, "forces": {}, "joints": S12.joints_from_model(nodes, members)}
    assert S12.scwb_joint(next(j for j in md["joints"] if j["id"] == "Jn1_7-X"), md)["value"] < 0.67


def test_scwb_axial_reduction():
    nodes, members = _ex2_model(fy=250)
    joints = S12.joints_from_model(nodes, members)
    md = {"members": members, "joints": joints,
          "forces": {"c1_2": [{"combo": "12.2.3a", "family": "12.2.3", "P_N": 3.0e6}],
                     "c1_3": [{"combo": "12.2.3a", "family": "12.2.3", "P_N": 2.5e6}]}}
    r = S12.scwb_joint(next(j for j in joints if j["id"] == "Jn1_2-X"), md)
    assert r["value"] < 1.34 and all(t["n"] > 0 for t in r["columns"])


def test_unsupported_systems_no_indian_basis():
    for s in ("BRBF", "SPSW", "dual SMF+BRBF", "IMF"):
        r = S12.section12_checks(s, {}, {})
        assert r["ok"] is None and r["reason"] == "no Indian basis" and r["supported"] is False


def test_zone_gate_ocbf_zone_iii_blocked():
    r = S12.section12_checks("OCBF", {"members": []}, {"zone": "III", "I": 1.0})
    z = next(c for c in r["checks"] if c["id"] == "zone_gate")
    assert z["ok"] is False
    assert S12.zone_gate("OCBF", {"zone": "II"})["ok"] is True


def test_scbf_full_run_blocks_on_missing_and_failing():
    m = _brace("B1", "CHS219.1X8", 6000, grade="YSt 310", process="HFS", sfrs=True, cos_h=0.8)
    md = {"members": [m], "forces": {"B1": [{"combo": "EQX+", "P_N": 395.7e3}]}, "combos_12_2_3_present": True,
          "connections": [{"member_id": "B1", "kind": "brace_end", "weld_type": "fillet",
                           "bolts": {"n_bolts": 10, "d_mm": 20, "grade": "8.8", "t_mm": 12, "fu_plate_MPa": 410,
                                     "e_mm": 40, "p_mm": 60, "d0_mm": 22}}]}
    # Zone II: IS 18168 optional -> IS 800 12.8.3.1 alone: 1.1 fy Ag
    r = S12.section12_checks("SCBF", md, {"zone": "II", "brace_config": "X"})
    ids = {c["id"]: c for c in r["checks"]}
    assert ids["material_E250B"]["ok"] is False
    assert ids["brace_conn_bolts"]["value"] == pytest.approx(1.1 * 310 * 5306)
    assert ids["brace_conn_bolts"]["dc"] > 1.0      # 10 x M20 vs 1.1 fy Ag
    assert ids["12.4.2_weld_type"]["ok"] is False
    assert r["ok"] is False and r["blocks_complete"] is True
    # Zone IV: IS 18168 10.4.1(a) governs (stricter): max(1.1 Ry fy Ag, Ru fu An) with Ry 1.4 / Ru 1.2 (5.2.1)
    r = S12.section12_checks("SCBF", md, {"zone": "IV", "brace_config": "X"})
    ids = {c["id"]: c for c in r["checks"]}
    assert ids["brace_conn_bolts"]["value"] == pytest.approx(max(1.1 * 1.4 * 310 * 5306, 1.2 * 450 * 5306))
    assert "IS 18168:2023 10.4.1" in ids["brace_connection_force"]["clause"]
    assert ids["is18168_1_3_system"]["ok"] is True and ids["is18168_5_5_combinations"]["ok"] is None


def test_ebf_link_checks_is18168():
    link = {"id": "L1", "section": "NPB400X180X57.38", "grade": "E250 B0", "e_mm": 800.0, "Vu_N": 250e3,
            "Pu_N": 0.0, "bay_L_mm": 8000.0, "drift_ratio_inelastic": 0.006,
            "end_stiffeners": {"both_sides": True, "width_mm": 170, "t_mm": 10}, "intermediate_stiffener_spacing_mm": 120,
            "braced_both_flanges": True, "connected_to_column": False}
    r = {c["id"]: c for c in S12.ebf_link_checks(link)}
    fy = 250.0
    VpL = fy * (397 - 2 * 12) * 7.0 / 3 ** 0.5
    MpL = fy * 1.14e6
    assert r["11.2_link_design_shear"]["VpL_N"] == pytest.approx(VpL, rel=1e-3)
    assert r["11.2_link_design_shear"]["value"] == pytest.approx(min(VpL / 1.1, 2 * MpL / (800 * 1.1)), rel=1e-3)
    assert r["11.3_link_length"]["limit"] == pytest.approx(1.6 * MpL / VpL, rel=1e-3)
    assert r["12.3.3.1_link_rotation"]["value"] == pytest.approx(8000 / 800 * 0.006)
    assert r["12.3.3.1_link_rotation"]["limit"] == 0.08
    assert r["11.4.2_intermediate_stiffeners"]["limit"] == pytest.approx(30 * 7 - 0.2 * 397)
    assert r["12.3.2.2_link_overstrength"]["Ry"] == 1.4 and r["12.3.2.2_link_overstrength"]["Sh"] == 1.25
    hss = S12.ebf_link_checks({"id": "L2", "section": "CHS219.1X8", "grade": "YSt 310", "e_mm": 500})
    assert next(c for c in hss if c["id"] == "11.1_link_section")["ok"] is False


def test_ebf_without_links_blocks():
    r = S12.section12_checks("EBF", {"members": []}, {"zone": "V"})
    assert r["ok"] is None and any(c["id"] == "ebf_links" for c in r["checks"])


def test_smf_joint_connection_1p2mp_and_panel_zone():
    nodes, members = _ex2_model(fy=250)
    joints = S12.joints_from_model(nodes, members)
    j = next(x for x in joints if x["id"] == "Jn1_2-X")
    j["connection"] = {"type": "end_plate", "moment_capacity_Nmm": 813.3e3 * 495, "shear_capacity_N": 600e3,
                       "weld_type": "CJP", "bolt_type": "HSFG", "cite": "end plate, IS 800 10.3.5 x lever arm"}
    for b in j["beams"]:
        b.update(L_clear_mm=7600.0, V_gravity_N=120e3)
    md = {"members": members, "forces": {}, "joints": [j]}
    out = {c["id"] + ":" + str(c["member"]): c for c in S12.smf_joint_checks(j, md, {})}
    cm = out["connection_moment:b0_2"]
    assert cm["value"] / 1e6 == pytest.approx(834.0, abs=0.5) and cm["dc"] == pytest.approx(2.07, abs=0.01)
    cs = out["connection_shear:b0_2"]
    assert cs["value"] == pytest.approx(120e3 + 2 * 834e6 / 7600, rel=1e-3)
    pz = out["12.11.2.3_panel_zone:Jn1_2-X"]
    assert pz["detail"]["V_design_N"] > 0 and pz["ok"] in (True, False)
    assert out["12.11.3.2_SCWB:Jn1_2-X"]["value"] == pytest.approx(1.34, abs=0.01)


def test_is18168_omega_from_pdf_clause():
    import india_omega_is18168 as IO
    r = IO.resolve_omega("SCBF", LL_class_kNm2=2.5)
    assert r["found"] and r["Omega"] == 2.5 and r["gamma_LL"] == 0.25 and "5.5" in r["clause"]
    assert IO.resolve_omega("SMRF", LL_class_kNm2=4.0)["Omega"] == 3.0
    assert IO.resolve_omega("EBF")["Omega"] == 2.5
    assert IO.resolve_omega("OCBF")["found"] is False
    assert IO.resolve_omega("BRBF")["found"] is False
    sec = IO.fetch_is18168_section_55(root="/nonexistent")
    assert sec["found"] and sec["resolved_via"] == "pdf_clause"
