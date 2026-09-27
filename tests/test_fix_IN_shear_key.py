"""IN-SHEAR-KEY (gold issue IN_Ex8): a declared column-base shear key / lug (shear_key_N subtracted from the anchor
shear) gets an explicit check row: the shear beyond friction (IS 800:2007 7.4.1, 0.45 x bearing compression; with
the 12.12.2 demand on SFRS bases) <= the declared capacity, with the EOR source and cite.  Without source or cite the
row is not evaluated (found:false) and the base is not a pass."""
import math
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "steel_engine"))

import india_connections as C  # noqa: E402

KW = dict(B_mm=550.0, L_mm=550.0, t_plate_mm=40.0, fy_plate_MPa=240.0, fck_MPa=25.0, col_d_mm=300.0, col_bf_mm=300.0,
          col_tf_mm=20.0, anchors={"n_total": 4, "n_tension": 2, "d_mm": 24, "grade": "8.8", "f_mm": 215.0})
KEY = {"capacity_N": 1.40e6, "source": "EOR shear-lug calc (test)", "cite": "IS 456:2000 34.4; IS 800:2007 8.4.1"}


def test_key_row_with_record_hand_values():
    # P 1,000 kN compression, V 800 kN: friction 0.45 x 1,000 = 450 kN -> key demand 350 kN vs 1,400 kN
    r = C.base_plate_design(P_N=1.0e6, V_N=800e3, shear_key=KEY, **KW)
    k = r["checks"]["shear_key"]
    assert k["value"] == pytest.approx(350e3) and k["limit"] == 1.40e6 and k["dc"] == pytest.approx(0.25)
    assert k["ok"] is True and k["capacity_source"] == KEY["source"] and KEY["cite"] in k["cite"]
    assert "7.4.1" in k["clause"] and k["verify"] is True
    assert r["checks"]["shear_path"]["anchors_N"] == 0.0                       # the anchors carry nothing
    # net uplift (no friction): 1,500 kN > 1,400 kN -> the key row fails (anchors are not added to the key)
    r2 = C.base_plate_design(P_N=-200e3, V_N=1.5e6, shear_key=KEY, **KW)
    assert r2["checks"]["shear_key"]["value"] == pytest.approx(1.5e6) and r2["checks"]["shear_key"]["ok"] is False
    assert r2["ok"] is not True                         # (anchorage embedment not declared: None)


def test_flat_keys_and_missing_source_or_cite_not_evaluated():
    r = C.base_plate_design(P_N=1.0e6, V_N=800e3, shear_key_N=1.4e6, shear_key_source=KEY["source"],
                            shear_key_cite=KEY["cite"], **KW)
    assert r["checks"]["shear_key"]["ok"] is True
    for kw in ({"shear_key_N": 1.4e6}, {"shear_key_N": 1.4e6, "shear_key_cite": "EOR detail"},
               {"shear_key": {"capacity_N": 1.4e6, "cite": "x"}}, {"shear_key": {"source": "s", "cite": "c"}}):
        r = C.base_plate_design(P_N=1.0e6, V_N=800e3, **KW, **kw)
        k = r["checks"]["shear_key"]
        assert k["ok"] is None and k["dc"] is None and k["found"] is False and "found:false" in k["reason"]
        assert r["ok"] is None                                                  # never a silent pass
    # the anchor shear is still reduced by the declared number (other rows unchanged)
    assert C.base_plate_design(P_N=-1e5, V_N=800e3, shear_key_N=1.4e6, **KW)["checks"]["shear_path"]["anchors_N"] == 0.0


def test_no_key_no_row_and_biaxial_single_row():
    assert "shear_key" not in C.base_plate_design(P_N=1.0e6, V_N=800e3, **KW)["checks"]
    kw = dict(KW, anchors=dict(KW["anchors"], f_y_mm=215.0))
    r = C.base_plate_design_biaxial(P_N=1.0e6, Mz_Nmm=50e6, My_Nmm=30e6, V_N=800e3, shear_key=KEY, **kw)
    assert "shear_key" in r["checks"] and "y:shear_key" not in r["checks"]


def test_sfrs_base_12_12_2_demand_reaches_the_key():
    """The IS 800 12.12.2 shear (1.2 Vd, owner ruling O1) is the key demand on an SFRS base."""
    r = C.base_plate_design(P_N=-100e3, V_N=10e3, sfrs_fixed_base=True, col_Zp_mm3=1.0e6, col_fy_MPa=250.0,
                            col_Vd_N=1.0e6, shear_key=KEY, **KW)
    fr = r["checks"]["shear_path"]["friction_N"]                    # 0.45 x the bearing-block compression
    assert r["checks"]["shear_path"]["value"] == pytest.approx(1.2e6)
    assert r["checks"]["shear_key"]["value"] == pytest.approx(1.2e6 - fr) and r["checks"]["shear_key"]["ok"] is True
