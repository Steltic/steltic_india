"""WP6 (GOLD-HR-B): EBF link support -- IS 18168 Table 2 width-thickness, off-grid beam pieces in the static model,
lateral-part record fields, links model_data and the EBF branch of section12_checks (links, capacity-protected
members, 12.3.4.5 braces, brace connection force, 12.3.4.4 joints)."""
import os, sys
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "steel_engine"))

import india_is18168 as I18
import india_is800_s12 as S12
import static_model as SM
import sections as S


def test_table2_limits_from_pdf():
    # Table 2 (pdf p. 8): link I-section 11.3 eps/sqrt(Ry) flange, 44.4 eps/sqrt(Ry) web; eps = sqrt(250/fy)
    lim = I18.table2_limits("link", 240.0, 1.4)
    eps = (250.0 / 240.0) ** 0.5
    assert abs(lim["flange_b_over_tf"] - 11.3 * eps / 1.4 ** 0.5) < 1e-9
    assert abs(lim["web_d_over_tw"] - 44.4 * eps / 1.4 ** 0.5) < 1e-9
    col = I18.table2_limits("column", 250.0, 1.4, Ca=0.5)
    assert abs(col["web_d_over_tw"] - max(24.9 * (2.68 - 0.5), 44.4) / 1.4 ** 0.5) < 1e-9
    # a rolled NPB (thin web) fails the link limit, a WPB passes
    assert I18.table2_check("link", S.props("NPB600X220X122.45"), 240.0, 1.4)["ok"] is False
    assert I18.table2_check("link", S.props("WPB300X300X117.03"), 240.0, 1.4)["ok"] is True


def test_grid_ijk_from_coords_for_link_pieces():
    cfg = {"NX": 7, "NY": 5, "SX": 9000.0, "SY": 9000.0, "heights": [4800.0] + [3900.0] * 7}
    # link piece of an X beam in bay i=1 at line j=0, level 1: x from 13050 to 13950
    assert SM.grid_ijk_from_coords(cfg, 13050.0, 0.0, 4800.0, "X") == (1, 0, 1)
    # Y beam piece in bay j=4 at line i=0, level 3
    assert SM.grid_ijk_from_coords(cfg, 0.0, 40050.0, 4800.0 + 2 * 3900.0, "Y") == (0, 4, 3)


def test_record_fields_carry_lateral_part():
    assert SM.REC_FIELDS[-2:] == ("N_LAT", "V_LAT")
    cf = SM.combo_forces_for_member_check({"1.5DL+1.5EQ_X": (-1000.0,) + (0.0,) * 10 + (-400.0, 30.0)}, "col")[0]
    assert cf["P_N"] == 1000.0 and cf["P_LAT_N"] == 400.0 and cf["V_LAT_N"] == 30.0
    # old 11-field records read as zero lateral part
    cf0 = SM.combo_forces_for_member_check({"1.5DL+1.5LL": (-1000.0,) + (0.0,) * 10}, "col")[0]
    assert cf0["P_LAT_N"] == 0.0


def _ebf_model_data():
    link_sec, beam_sec, brace_sec, col_sec = "WPB300X300X117.03", "WPB300X300X117.03", "WPB250X250X73.15", "WPB400X300X255.74"
    members = [
        {"id": "e1", "tag": 1, "section": link_sec, "grade": "E250 B0", "role": "beam", "L_mm": 900.0, "sfrs": True, "node_i": 101, "node_j": 102},
        {"id": "e2", "tag": 2, "section": beam_sec, "grade": "E250 B0", "role": "beam", "L_mm": 4050.0, "sfrs": True, "node_i": 100, "node_j": 101},
        {"id": "e3", "tag": 3, "section": brace_sec, "grade": "E250 B0", "role": "brace", "L_mm": 5600.0, "sfrs": True, "Kz": 1.0, "Ky": 1.0,
         "node_i": 1, "node_j": 101, "An_mm2": 9310.0},
        {"id": "e4", "tag": 4, "section": col_sec, "grade": "E250 B0", "role": "column", "L_mm": 3900.0, "sfrs": True, "Kz": 1.0, "Ky": 1.0,
         "node_i": 100, "node_j": 200, "major_axis_plane": "X"},
    ]
    forces = {
        "e1": [{"combo": "1.5DL+1.5EQ_X", "family": "table4", "P_N": 20e3, "P_EL_N": 15e3, "Vy_N": 300e3, "Mz_i_Nmm": 1e8, "Mz_j_Nmm": 1e8, "My_i_Nmm": 0, "My_j_Nmm": 0, "Vz_N": 0}],
        "e2": [{"combo": "1.5DL+1.5EQ_X", "family": "table4", "P_N": 400e3, "P_EL_N": 380e3, "Vy_N": 50e3, "Mz_i_Nmm": 1e8, "Mz_j_Nmm": 1e8, "My_i_Nmm": 0, "My_j_Nmm": 0, "Vz_N": 0}],
        "e3": [{"combo": "1.5DL+1.5EQ_X", "family": "table4", "P_N": 450e3, "P_EL_N": 430e3, "Vy_N": 0, "Mz_i_Nmm": 0, "Mz_j_Nmm": 0, "My_i_Nmm": 0, "My_j_Nmm": 0, "Vz_N": 0},
               {"combo": "1.2DL+0.5LL+2.5EQ_X[col]", "family": "12.2.3", "P_N": 740e3, "Vy_N": 0, "Mz_i_Nmm": 0, "Mz_j_Nmm": 0, "My_i_Nmm": 0, "My_j_Nmm": 0, "Vz_N": 0}],
        "e4": [{"combo": "1.5DL+1.5EQ_X", "family": "table4", "P_N": 2500e3, "P_EL_N": 800e3, "Vy_N": 0, "Mz_i_Nmm": 0, "Mz_j_Nmm": 0, "My_i_Nmm": 0, "My_j_Nmm": 0, "Vz_N": 0}],
    }
    links = [{"id": "link-e1", "member_id": "e1", "tag": 1, "section": link_sec, "grade": "E250 B0", "e_mm": 900.0, "bay_L_mm": 9000.0,
              "Vu_N": 300e3, "Pu_N": 20e3, "brace_ids": ["e3"], "column_ids": ["e4"], "beam_ids": ["e2"],
              "end_stiffeners": {"both_sides": True, "width_mm": 300.0, "t_mm": 12.0}, "intermediate_stiffener_spacing_mm": 250.0,
              "braced_both_flanges": True, "connected_to_column": False, "continuous_link_beam": True, "drift_ratio_inelastic": 0.004 * 5}]
    conns = [{"id": "conn-e3", "member_id": "e3", "kind": "brace_end", "weld_type": "cjp",
              "welds_cjp": {"t_mm": 13.6, "length_mm": 650.0, "fy_MPa": 250.0, "n_sides": 4, "site": False},
              "gusset": {"t_mm": 25.0, "fy_MPa": 250.0, "fu_MPa": 410.0, "w_start_mm": 250.0, "L_conn_mm": 650.0, "L_unbraced_mm": 300.0,
                         "K": 0.65, "Avg_mm2": 2 * 650 * 25.0, "Avn_mm2": 2 * 650 * 25.0, "Atg_mm2": 250 * 25.0, "Atn_mm2": 250 * 25.0},
              "An_mm2": 9310.0, "resists_link_end_moment": False, "bolts_and_welds_share": False}]
    joints = [{"id": "J100-X", "node": 100, "frame_dir": "X", "columns": [{"member_id": "e4", "position": "above"}],
               "beams": [{"member_id": "e2"}], "connection": {"type": "welded", "weld_type": "cjp"}}]
    return {"members": members, "forces": forces, "links": links, "connections": conns, "joints": joints,
            "combos_12_2_3_present": True, "combos_is18168_5_5_present": True, "bases": [], "brace_lines": []}


def test_section12_ebf_branch():
    md = _ebf_model_data()
    res = S12.section12_checks("EBF", md, {"zone": "III", "I": 1.2, "height_m": 32.1, "brace_config": "chevron"})
    ids = {c["id"] for c in res["checks"]}
    for k in ("11.2_link_design_shear", "11.3_link_length", "12.3.2.1_link_shear", "12.3.3.1_link_rotation", "11.4.1_end_stiffeners",
              "11.4.2_intermediate_stiffeners", "12.3.1_link_not_at_column", "12.3.2.2_link_overstrength", "is18168_table2_link",
              "12.3.2.2_brace_axial", "12.3.2.2_column_axial", "12.3.2.2_beam_axial", "is18168_table2_brace", "12.3.4.5_brace_tension",
              "brace_connection_force", "brace_conn_welds", "brace_conn_pinned_12.3.4.6", "is18168_table2_beam", "is18168_table2_column",
              "12.3.4.4_connection_moment", "12.3.4.4_column_strength"):
        assert k in ids, k
    by = {c["id"]: c for c in res["checks"]}
    # 11.2: WPB300X300X117.03 fy 240 (tf 19): VpL = 240 x (300 - 38) x 11 / sqrt3 = 399.3 kN -> Vd = 363.0 kN (< 2 MpL/e)
    assert abs(by["11.2_link_design_shear"]["value"] / 1e3 - 240.0 * 262 * 11 / 3 ** 0.5 / 1.1 / 1e3) < 0.5
    assert by["12.3.2.1_link_shear"]["ok"] is True and abs(by["12.3.2.1_link_shear"]["dc"] - 300e3 / by["11.2_link_design_shear"]["value"]) < 1e-6
    # rotation: (L/e) x inelastic drift = 10 x 0.02 = 0.2 > 0.08 -> fails (a real design must limit the drift)
    assert by["12.3.3.1_link_rotation"]["ok"] is False
    # capacity-protected amplification 1.1 x 1.4 x 1.25 x Vd / Vu
    over = by["12.3.2.2_link_overstrength"]
    assert abs(over["amplification_capacity_protected"] - 1.1 * 1.4 * 1.25 * by["11.2_link_design_shear"]["value"] / 300e3) < 1e-6
    # EBF brace connection: larger of the 5.5 force and the link-overstrength force, capped by 1.1 Ry fy Ag
    f = by["brace_connection_force"]
    assert f["ok"] is True and f["value"] > 740e3
    assert "12.3.2.2" in f["clause"]
    # a pinned brace connection satisfies 12.3.4.6; the beam-column joint develops the beam (CJP)
    assert by["brace_conn_pinned_12.3.4.6"]["ok"] is True
    assert by["12.3.4.4_connection_moment"]["ok"] is True


def test_is875_2_321_column_reduction_table():
    # IS 875 (Part 2):1987 3.2.1 (pdf p. 14): 1 floor 0 %, 2 10 %, 3 20 %, 4 30 %, 5-10 40 %, over 10 50 %
    assert [SM.imposed_load_reduction_321(n) for n in (1, 2, 3, 4, 5, 10, 11)] == [0.0, 0.10, 0.20, 0.30, 0.40, 0.40, 0.50]


def test_spec_for_role_group_key():
    import india_connection_design as CD
    cfg = {"connections": {"column_base": {"WPB800X300X317.36": {"fixed": True, "B_mm": 1},
                                           "gravity_col:WPB800X300X317.36": {"fixed": False, "B_mm": 2}}}}
    assert CD.spec_for(cfg, "column_base", "WPB800X300X317.36", "gravity_col")["B_mm"] == 2
    assert CD.spec_for(cfg, "column_base", "WPB800X300X317.36", "lateral_col")["B_mm"] == 1
    b = CD.base_entry(cfg, {"id": "e1", "section": "WPB800X300X317.36", "role_group": "gravity_col"}, {})
    assert b["fixed"] is False


def test_scbf_table2_live():
    """H05: IS 18168 Table 2 on SCBF members is live whenever IS 18168 applies (was opt-in via cfg['is18168_table2']);
    the opt-out False is ignored in Zones III-V."""
    md = {"members": [{"id": "e1", "tag": 1, "section": "NPB450X190X67.16", "grade": "E250 B0", "role": "beam", "L_mm": 6000.0,
                       "sfrs": True, "node_i": 1, "node_j": 2}], "forces": {"e1": []}, "connections": [], "bases": [],
          "brace_lines": [], "combos_12_2_3_present": True, "combos_is18168_5_5_present": True}
    for extra in ({}, {"is18168_table2": True}, {"is18168_table2": False}):
        r = S12.section12_checks("SCBF", dict(md), dict({"zone": "IV", "I": 1.2, "brace_config": "X"}, **extra))
        c = [c for c in r["checks"] if c["id"] == "is18168_table2_beam"][0]
        assert c["ok"] is False and c["value"]["d/tw"] > c["limit"]["d/tw"]
        assert not any(a.get("live") is False for a in r["advisories"])
