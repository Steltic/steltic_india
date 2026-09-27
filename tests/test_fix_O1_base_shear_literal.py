"""O1 (owner ruling 2026-09-26): IS 800 12.12.2 stays code-literal on pinned braced-frame bases -- the base shear
demand is max(case shear, 1.2 x the column's Vd); no reduction for a pinned base of a braced frame.  The ruling is
named in the check cite and in contract/AGENT_START.md."""
import os
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "steel_engine"))
sys.path.insert(0, os.path.join(ROOT, "tests"))

import india_is800 as I8
import india_is800_s12 as S12
import sections as S
from test_fix_H08 import _md, SEC


@pytest.mark.parametrize("system,zone", [("OCBF", "II"), ("SCBF", "IV")])
def test_pinned_braced_frame_base_shear_is_1p2_vd(system, zone):
    cases = [{"combo": "1.5DL+1.5EQ_X", "P_N": 400e3, "M_Nmm": 0.0, "V_N": 20e3}]     # case shear << 1.2 Vd
    r = S12.base_checks(system, _md(False, cases), {"zone": zone})[0]
    p = S.props(SEC)
    fy = I8.material_for_section(p, "E250 B0")["fy_MPa"]
    Vd = I8.shear_capacity(p, fy, axis="z")["Vd_N"]
    rec = r["detail"]["checks"]["12.12.2_shear_demand"]
    assert rec["value"] == pytest.approx(1.2 * Vd, rel=1e-9)                     # literal: 1.2 x column Vd
    assert r["per_case"][0]["V_N"] == pytest.approx(1.2 * Vd, rel=1e-9)         # and it is the shear checked
    assert rec["clause"] == "IS 800:2007 12.12.2"
    assert "owner ruling O1: literal" in rec["cite"] and "owner ruling O1: literal" in r["cite"]


def test_connection_base_plate_cite_names_ruling():
    import india_connections as C                   # the connection-level SFRS base record (fixed base path)
    r = C.base_plate_design(P_N=400e3, M_Nmm=0.0, V_N=20e3, B_mm=700, L_mm=700, t_plate_mm=60, fy_plate_MPa=250,
                            fck_MPa=30, col_d_mm=300, col_bf_mm=300, col_tf_mm=20,
                            anchors={"n_total": 4, "n_tension": 2, "d_mm": 30, "grade": "8.8", "f_mm": 270},
                            sfrs_fixed_base=True, col_Zp_mm3=1.5e6, col_fy_MPa=250.0, col_Vd_N=400e3)
    rec = r["checks"]["12.12.2_shear_demand"] if "checks" in r else r["detail"]["checks"]["12.12.2_shear_demand"]
    assert rec["value"] == pytest.approx(480e3)
    assert "owner ruling O1: literal" in rec["cite"]


def test_contract_documents_ruling_o1():
    txt = open(os.path.join(ROOT, "contract", "AGENT_START.md"), encoding="utf-8").read()
    assert "Owner ruling O1 (2026-09-26)" in txt and "12.12.2" in txt
