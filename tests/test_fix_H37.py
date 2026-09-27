"""H37 (HR-B-17, HR-C-16): a declared bolts.n_e (10.4.3 slip input) must not crash the bearing-bolt capacity calls,
and a connection-group build failure becomes a found:false row instead of aborting the package."""
import inspect
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "steel_engine"))

import india_connections as C
import india_connection_design as CD

BOLTS = {"n_bolts": 4, "d_mm": 20, "grade": "8.8", "t_mm": 10.0, "fu_plate_MPa": 410.0, "e_mm": 40.0, "p_mm": 60.0,
         "d0_mm": 22.0}


def test_fin_plate_accepts_n_e_and_slip_keys():
    b = dict(BOLTS, n_e=2, Kh=1.0, mu_f=0.33, slip_surface="clean_mill_scale")
    r = C.fin_plate_shear_checks(V_N=100e3, t_plate_mm=10.0, h_plate_mm=250.0, fy_plate_MPa=250.0,
                                 fu_plate_MPa=410.0, bolts=b)
    ref = C.fin_plate_shear_checks(V_N=100e3, t_plate_mm=10.0, h_plate_mm=250.0, fy_plate_MPa=250.0,
                                   fu_plate_MPa=410.0, bolts=dict(BOLTS))
    assert r["checks"]["bolts_10_3"]["limit"] == ref["checks"]["bolts_10_3"]["limit"]


def test_splice_bolts_accept_n_e():
    r = C.column_splice_checks(sfrs=False, Af_mm2=300 * 20.0, fy_MPa=250.0, P_N=100e3, M_Nmm=0.0, Zx_mm3=1e6,
                               A_mm2=15000.0, d_mm=300.0,
                               splice={"type": "flange_plates", "plate": {"A_mm2": 6000.0, "fy_MPa": 250.0},
                                       "bolts": dict(BOLTS, n_e=2)})
    assert r["checks"]["bolts_10_3"]["ok"] is not None


def test_hsfg_slip_n_e_doubles_capacity():
    b1 = CD.hsfg_slip_checks(dict(BOLTS, n_e=1), "HSFG", 50e3, mu_f=0.33)
    b2 = CD.hsfg_slip_checks(dict(BOLTS, n_e=2), "HSFG", 50e3, mu_f=0.33)
    assert abs(b2["slip_service_10_4_3"]["limit"] - 2 * b1["slip_service_10_4_3"]["limit"]) < 1e-6


def test_connection_rows_wrapped_in_try():
    import design_pipeline as DP
    src = inspect.getsource(DP.design_india)
    assert "def _conn_group(key, tags):" in src
    assert "_conn_group(key, tags)" in src and "\"found\": False, \"error\": err" in src
