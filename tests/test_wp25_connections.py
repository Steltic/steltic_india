"""WP2.5 IS 800 connections and bases - hand values from spec 4.2 / HR800-09..12 / HREX1-X-06."""
import os
import sys

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "steel_engine"))

import india_connections as C  # noqa: E402


def test_bolt_m20_88_shear_thread_and_shank():
    assert C.bolt_capacity_is800(20, "8.8", nn=1)["Vdsb_N"] / 1e3 == pytest.approx(90.5, abs=0.05)
    assert C.bolt_capacity_is800(20, "8.8", nn=0, ns=1)["Vdsb_N"] / 1e3 == pytest.approx(116.1, abs=0.05)
    assert C.bolt_capacity_is800(24, "8.8", nn=1)["Vdsb_N"] / 1e3 == pytest.approx(130.4, abs=0.1)


def test_bolt_bearing_kb():
    b = C.bolt_capacity_is800(20, "8.8", nn=1, t_mm=10, fu_plate_MPa=410, e_mm=35, p_mm=60, d0_mm=22)
    assert b["Vdpb_N"] / 1e3 == pytest.approx(87.0, abs=0.05)
    assert b["kb"] == pytest.approx(35 / 66, abs=1e-6)
    assert b["Vdb_N"] == b["Vdpb_N"]
    # bearing inputs missing -> found:false, not the shear value
    assert C.bolt_capacity_is800(20, "8.8", nn=1)["found"] is False


def test_bolt_long_joint_and_combined():
    b = C.bolt_capacity_is800(20, "8.8", nn=1, lj_mm=400)
    assert b["reductions"]["beta_lj"] == pytest.approx(1.075 - 400 / 4000)
    c = C.bolt_capacity_is800(20, "8.8", nn=1, t_mm=10, fu_plate_MPa=410, e_mm=40, p_mm=60, d0_mm=22,
                              V_N=50e3, T_N=80e3)
    assert c["combined_check"]["clause"] == "IS 800:2007 10.3.6"


def test_hsfg_slip():
    s = C.hsfg_slip_capacity(20, "8.8", mu_f=0.5, n_e=1)
    assert s["Vdsf_N"] == pytest.approx(0.5 * 245 * 0.7 * 800 / 1.25)
    assert C.hsfg_slip_capacity(20, "8.8")["found"] is False


def test_fillet_weld_shop_site():
    assert C.fillet_weld_capacity_is800_N(size_mm=6, length_mm=300, fu_MPa=410, n_sides=2)["capacity_N"] / 1e3 == \
        pytest.approx(477.2, abs=0.05)
    assert C.fillet_weld_capacity_is800_N(size_mm=6, length_mm=300, fu_MPa=410, n_sides=2, site=True)["capacity_N"] \
        / 1e3 == pytest.approx(397.7, abs=0.05)
    lw = C.fillet_weld_capacity_is800_N(size_mm=6, length_mm=800, fu_MPa=410, lj_mm=800)
    assert lw["beta_lw"] == pytest.approx(1.2 - 0.2 * 800 / (150 * 4.2))


def test_cjp_gate_12_4_2():
    assert C.cjp_weld_gate("fillet")["ok"] is False
    assert C.cjp_weld_gate("CJP")["ok"] is True
    assert C.cjp_weld_gate("PJP", location="column splice")["ok"] is True
    assert C.cjp_weld_gate(None)["ok"] is None


def test_block_shear_both_expressions_hand_value():
    ar = C.block_shear_bolted_areas(t_mm=12, n_rows=3, pitch_mm=60, end_mm=40, d0_mm=22, edge_mm=40)
    bs = C.block_shear(fy_MPa=250, fu_MPa=410, **{k: v for k, v in ar.items() if k.endswith("mm2")})
    assert bs["Tdb1_N"] / 1e3 == pytest.approx(354.7, abs=0.1)
    assert bs["Tdb_N"] / 1e3 == pytest.approx(323.8, abs=0.1)
    assert C.block_shear(Avg_mm2=1920, Atn_mm2=348, fy_MPa=250, fu_MPa=410)["found"] is False


def test_whitmore_labelled_practice_and_buckling_needs_K():
    w = C.whitmore_section(t_gusset_mm=12, fy_MPa=250, w_start_mm=168.3, L_conn_mm=250)
    assert w["whitmore_width_mm"] == pytest.approx(457.0, abs=0.1)
    assert w["capacity_N"] / 1e3 == pytest.approx(1246.3, abs=0.5)
    assert "ENGINEERING PRACTICE" in w["cite"]
    assert C.whitmore_buckling(whitmore_width_mm=457, t_gusset_mm=12, fy_MPa=250, L_unbraced_mm=200)["found"] is False
    b = C.whitmore_buckling(whitmore_width_mm=457, t_gusset_mm=12, fy_MPa=250, L_unbraced_mm=200, K=0.65)
    assert b["found"] and b["buckling_class"] == "c"


def test_base_plate_7_4_3_1_thickness():
    t = C.base_plate_thickness_7_4_3_1(w_MPa=500e3 / 250000.0, a_mm=80, b_mm=80, fy_MPa=250)
    assert t["ts_mm"] == pytest.approx(9.93, abs=0.01)
    r = C.base_plate_design(P_N=500e3, B_mm=500, L_mm=500, t_plate_mm=12, fy_plate_MPa=250, fck_MPa=25,
                            col_d_mm=(500 - 160) / 0.95, col_bf_mm=(500 - 160) / 0.8, col_tf_mm=10)
    assert r["checks"]["bearing"]["limit"] == pytest.approx(0.6 * 25)
    assert r["checks"]["plate_thickness_7_4_3_1"]["dc"] == pytest.approx((9.93 / 12) ** 2, abs=0.01)


def test_ex3_base_anchor_tension_from_moment():
    r = C.base_plate_design(P_N=183.6e3, M_Nmm=538.6e6, B_mm=500, L_mm=500, t_plate_mm=25, fy_plate_MPa=250,
                            fck_MPa=25, col_d_mm=400, col_bf_mm=400, col_tf_mm=20,
                            anchors={"n_total": 4, "n_tension": 2, "d_mm": 24, "grade": "4.6", "f_mm": 200},
                            Ec_MPa=25000)
    assert r["demands"]["T_anchor_N"] / 1e6 == pytest.approx(1.2, abs=0.05)
    assert r["ok"] is not True
    assert r["checks"]["anchor_tension_10_3_5"]["ok"] is False
    assert r["checks"]["anchorage_embedment"]["ok"] is None   # outside IS 800 -> found:false, blocks


def test_base_12_12_demands_and_geometry_gate():
    r = C.base_plate_design(P_N=2000e3, M_Nmm=100e6, V_N=50e3, B_mm=650, L_mm=650, t_plate_mm=40,
                            fy_plate_MPa=250, fck_MPa=30, col_d_mm=400, col_bf_mm=400, col_tf_mm=24,
                            sfrs_fixed_base=True, col_Zp_mm3=4.32e6, col_fy_MPa=250, col_Vd_N=900e3,
                            anchors={"n_total": 64, "n_tension": 16, "d_mm": 24, "grade": "8.8", "f_mm": 275,
                                     "pitch_mm": 35, "edge_mm": 40, "n_per_row": 16}, Ec_MPa=27000,
                            weld_length_mm=4370, col_perimeter_mm=2300)
    assert r["demands"]["M_Nmm"] == pytest.approx(1.2 * 4.32e6 * 250)
    assert r["demands"]["V_N"] == pytest.approx(1.2 * 900e3)
    assert r["checks"]["geometry_anchor_pitch"]["ok"] is False
    assert r["checks"]["geometry_weld_length"]["ok"] is False
