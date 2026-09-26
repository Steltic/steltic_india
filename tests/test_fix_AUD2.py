"""AUD-2 (gold audit H2 / M1, engine observation 2): plate yield stress by thickness.  Base plates, gussets, splice,
cover, end and fin plates, base stiffeners and shear-key plates take the IS 2062 (Part 1):2025 Table 3 ReH of their
grade for their thickness band (E250: 250 / 240 / 230 / 210 for <=16 / >16-40 / >40-100 / >100 mm, corpus
IS_2062_Part_1_2025 Table 3 row ii)); a declared fy above it is reduced and recorded (note + cite); a lower declared
fy is kept.  Hand values: 120 mm E250 -> 210; 25 mm -> 240."""
import math
import os
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "steel_engine"))
sys.path.insert(0, os.path.join(ROOT, "tests"))

import india_connection_design as CD
import india_connections as C
import india_is800_s12 as S12


def test_helper_hand_values():
    fy, r = C.plate_fy_is2062(250.0, 120.0, "E250 B0")
    assert fy == 210.0 and r["reduced"] and r["fy_table_MPa"] == 210.0 and r["thickness_band_mm"] == ">100"
    assert "IS 2062 (Part 1):2025 Table 3" in r["cite"] and "210" in r["note"]
    assert C.plate_fy_is2062(250.0, 25.0, "E250")[0] == 240.0
    assert C.plate_fy_is2062(250.0, 16.0, "E250")[0] == 250.0
    assert C.plate_fy_is2062(250.0, 45.0, "E250")[0] == 230.0
    # a lower declared fy is kept
    fy, r = C.plate_fy_is2062(200.0, 120.0, "E250")
    assert fy == 200.0 and r["reduced"] is False and r["fy_table_MPa"] == 210.0
    # declared E350 above 100 mm at 290 is correct (HR Ex6) -> kept
    assert C.plate_fy_is2062(290.0, 110.0, "E350 B0")[0] == 290.0


def test_grade_resolution_job_grade_and_inference():
    # plate grade not declared: job steel_grade when the declared fy does not exceed its designation
    fy, r = C.plate_fy_is2062(230.0, 120.0, None, job_grade="E250 B0")
    assert fy == 210.0 and "job steel_grade" in r["grade_basis"]
    # declared fy above the job grade designation: lowest grade whose designation >= fy (E300 for 290), flagged
    fy, r = C.plate_fy_is2062(290.0, 110.0, None, job_grade="E250 B0")
    assert r["grade"] == "E300" and fy == 250.0 and "inferred" in r["grade_basis"]
    # no job grade, fy <= 250 -> E250
    assert C.plate_fy_is2062(230.0, 120.0)[0] == 210.0
    # thickness unknown -> declared kept, band not verified (stated)
    fy, r = C.plate_fy_is2062(250.0, None, "E250")
    assert fy == 250.0 and r["band_checked"] is False


BASE = dict(P_N=900e3, M_Nmm=180e6, V_N=50e3, B_mm=700, L_mm=750, fck_MPa=30, col_d_mm=300, col_bf_mm=300,
            col_tf_mm=19, anchors={"n_total": 8, "n_tension": 3, "d_mm": 30, "grade": "8.8", "f_mm": 290,
                                   "pitch_mm": 150, "edge_mm": 60, "n_per_row": 3})


def test_base_plate_120mm_declared_230_uses_210():
    """HR Ex3 (audit H2): 120 mm E250 plate declared at 230 -> limit 0.2 t^2 x 210 / 1.10 = 549,818 N-mm/mm."""
    r = C.base_plate_design(t_plate_mm=120.0, fy_plate_MPa=230.0, job_steel_grade="E250 B0", **BASE)
    pt = r["checks"]["plate_thickness"]
    assert pt["limit"] == pytest.approx(0.2 * 120.0 ** 2 * 210.0 / 1.10) == pytest.approx(549818.18, rel=1e-6)
    assert pt["plate_fy"][0]["reduced"] and "210" in pt["note"] and "IS 2062 (Part 1):2025 Table 3" in pt["cite"]
    assert r["plate_fy"]["fy_used_MPa"] == 210.0
    # declared E250 at the band value -> nothing to record as a reduction, same capacity
    r2 = C.base_plate_design(t_plate_mm=120.0, fy_plate_MPa=210.0, job_steel_grade="E250 B0", **BASE)
    assert r2["checks"]["plate_thickness"]["limit"] == pytest.approx(pt["limit"])
    assert r2["plate_fy"]["reduced"] is False and "note" not in r2["checks"]["plate_thickness"]


def test_base_entry_carries_cfg_grades_to_s12():
    cfg = {"steel_grade": "E250 B0", "connections": {"column_base": {"default": {"t_plate_mm": 120.0}}}}
    b = CD.base_entry(cfg, {"id": "e1", "section": "ISMB300"}, [])
    assert b["job_steel_grade"] == "E250 B0"
    cfg["plate_grade"] = "E350 B0"
    assert CD.base_entry(cfg, {"id": "e1", "section": "ISMB300"}, [])["plate_grade"] == "E350 B0"


def test_fin_plate_25mm_declared_250_uses_240():
    sh = dict(t_plate_mm=25.0, h_plate_mm=300.0, fy_plate_MPa=250.0, fu_plate_MPa=410.0,
              bolts={"n_bolts": 4, "d_mm": 20, "grade": "8.8", "t_mm": 25.0, "fu_plate_MPa": 410.0})
    r = C.fin_plate_shear_checks(V_N=300e3, job_steel_grade="E250", **sh)
    c = r["checks"]["plate_shear_8_4_1"]
    assert c["limit"] == pytest.approx(300.0 * 25.0 * 240.0 / (math.sqrt(3) * 1.10))
    assert c["plate_fy"][0]["reduced"] and "240" in c["note"]
    # two 25 mm fin plates (t_plate_mm = 50 total, n_plates 2): band read per plate -> 240, not 230
    r2 = C.fin_plate_shear_checks(V_N=300e3, job_steel_grade="E250", n_plates=2,
                                  **dict(sh, t_plate_mm=50.0, fy_plate_MPa=240.0))
    assert r2["checks"]["plate_shear_8_4_1"]["limit"] == pytest.approx(300.0 * 50.0 * 240.0 / (math.sqrt(3) * 1.10))


def test_cover_and_end_plate_use_band_fy():
    r = C.cover_plate_moment_capacity(Zp_beam_mm3=1.0e6, fy_beam_MPa=250.0, plate_b_mm=200.0, plate_t_mm=20.0,
                                      d_beam_mm=400.0, fy_plate_MPa=250.0)
    Zp = 200.0 * 20.0 * 420.0
    assert r["capacity_Nmm"] == pytest.approx((1.0e6 * 250.0 + Zp * 240.0) / 1.10)
    assert r["plate_fy"]["reduced"] and "fy by thickness" in r["cite"]
    ep = C.end_plate_moment_capacity(rows=[{"h_mm": 400.0}], d_mm=24, t_plate_mm=45.0, fy_plate_MPa=250.0,
                                     be_mm=120.0, lv_mm=50.0, le_mm=50.0)
    assert ep["plate_fy"]["fy_used_MPa"] == 230.0
    assert ep["Mp_strip_Nmm"] == pytest.approx(1.2 * (120.0 * 45.0 ** 2 / 6.0) * 230.0 / 1.10)


def test_splice_plate_with_thickness():
    sp = {"type": "flange_plates", "plate": {"A_mm2": 300.0 * 25.0, "t_mm": 25.0, "fy_MPa": 250.0}}
    r = C.column_splice_checks(sfrs=False, Af_mm2=4000.0, fy_MPa=250.0, P_N=1.0e6, M_Nmm=50e6, Zx_mm3=1.5e6,
                               A_mm2=12000.0, d_mm=300.0, splice=sp, bf_mm=300.0, tf_mm=20.0, tw_mm=12.0,
                               job_steel_grade="E250 B0")
    c = r["checks"]["plate_yield_6_2"]
    assert c["limit"] == pytest.approx(300.0 * 25.0 * 240.0 / 1.10)
    assert c["plate_fy"][0]["reduced"]
    # A_mm2 + b_mm gives the thickness too
    sp2 = {"type": "flange_plates", "plate": {"A_mm2": 300.0 * 25.0, "b_mm": 300.0, "fy_MPa": 250.0}}
    r2 = C.column_splice_checks(sfrs=False, Af_mm2=4000.0, fy_MPa=250.0, P_N=1.0e6, M_Nmm=50e6, Zx_mm3=1.5e6,
                                A_mm2=12000.0, d_mm=300.0, splice=sp2, bf_mm=300.0, tf_mm=20.0, tw_mm=12.0)
    assert r2["checks"]["plate_yield_6_2"]["limit"] == pytest.approx(c["limit"])


def test_stiffener_and_shear_key_plates():
    st = {"n_per_side": 3, "t_mm": 20, "h_mm": 250, "fy_MPa": 250, "weld": {"size_mm": 10, "fu_MPa": 410}}
    r = C.base_plate_design(P_N=3.0e6, B_mm=600, L_mm=900, t_plate_mm=40, fy_plate_MPa=250, fck_MPa=30, col_d_mm=400,
                            col_bf_mm=400, col_tf_mm=20, stiffeners=st)
    assert r["checks"]["gusset_shear_8_4"]["limit"] == pytest.approx(250 * 20 * 240 / (math.sqrt(3) * 1.10))
    assert r["stiffener_fy"]["fy_used_MPa"] == 240.0
    # plate at 40 mm E250 = 240 (>16-40): declared 250 reduced
    assert r["plate_fy"]["fy_used_MPa"] == 240.0
    # shear key record that states its plate: 90 mm declared 250 -> 230; declared capacity scaled 230/250
    k = C.shear_key_check(1.0e6, {"capacity_N": 2.0e6, "source": "EOR", "cite": "IS 800 8.4.1", "t_mm": 90.0,
                                  "fy_MPa": 250.0, "grade": "E250"})
    assert k["limit"] == pytest.approx(2.0e6 * 230.0 / 250.0) and k["plate_fy"][0]["reduced"]
    # a key without a stated plate is unchanged
    k0 = C.shear_key_check(1.0e6, {"capacity_N": 2.0e6, "source": "EOR", "cite": "IS 800 8.4.1"})
    assert k0["limit"] == 2.0e6 and "plate_fy" not in k0


def test_s12_gusset_20mm_declared_250_uses_240():
    from test_fix_H07 import _md
    m, md = _md()
    conn = dict(md["connections"][0], job_steel_grade="E250 B0")
    conn["gusset"] = dict(conn["gusset"], t_mm=20.0, fy_MPa=250.0)
    oc = S12.brace_connection_checks("SCBF", m, conn, md, {"zone": "IV", "I": 1.2})
    wm = next(c for c in oc if c["id"] == "gusset_whitmore_yield")
    ww = 250.0 + 2 * 650.0 * math.tan(math.radians(30.0))
    assert wm["limit"] == pytest.approx(ww * 20.0 * 240.0 / 1.10, rel=1e-6)
    assert wm["plate_fy"][0]["reduced"] and "240" in wm["note"]
