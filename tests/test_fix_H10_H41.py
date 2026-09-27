"""H10 (NEW): IS 18168 column-splice rules 7.5 / 12.2.4.6 / 12.3.4.7 with concurrent P, Mz, My.
H41 (HR-A-06, HR-B-04, HR-C-20, HR-D-12): bearing option (IS 800 7.3.4.1) with the 5.1.2 tie force; flange share
P Af/A + M/d; CJP basis per ruling R4; a clear error when a CJP is declared without its weld."""
import os
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "steel_engine"))

import india_connections as C
import india_connection_design as CD
import sections as S

SEC = "WPB300X300X117.03"
P = S.props(SEC)
KW = dict(Af_mm2=P["bf"] * P["tf"], fy_MPa=250.0, Zx_mm3=P["Zx"], A_mm2=P["A"], d_mm=P["d"], bf_mm=P["bf"],
          tf_mm=P["tf"], tw_mm=P["tw"])
PLATES = {"type": "flange_plates", "plate": {"A_mm2": 300.0 * 25.0, "fy_MPa": 250.0}}


def test_gravity_flange_share_with_web_plates_and_p_over_2_without():
    r = C.column_splice_checks(sfrs=False, P_N=2000e3, M_Nmm=0.0, splice=dict(PLATES, web_plate={"A_mm2": 3000.0,
                                                                                                "fy_MPa": 250.0}), **KW)
    assert r["demand_N"] == pytest.approx(2000e3 * KW["Af_mm2"] / KW["A_mm2"])
    r2 = C.column_splice_checks(sfrs=False, P_N=2000e3, M_Nmm=0.0, splice=dict(PLATES), **KW)
    assert r2["demand_N"] == pytest.approx(1000e3)                   # web not spliced: the flanges carry P/2 each


def test_bearing_option_and_tie_force():
    r = C.column_splice_checks(sfrs=False, P_N=7e6, M_Nmm=0.0, splice=dict(PLATES, bearing=True), tie_force_N=300e3,
                               **KW)
    assert r["bearing"] is True and r["demand_N"] == pytest.approx(150e3)       # T/2: compression by bearing
    assert "IS 800 5.1.2" in r["governing_demand"]
    r0 = C.column_splice_checks(sfrs=False, P_N=7e6, M_Nmm=0.0, splice=dict(PLATES, bearing=True), **KW)
    assert r0["dc"] == pytest.approx(0.0)


def test_concurrent_cases_not_enveloped():
    cases = [{"combo": "A", "P_N": 2000e3, "Mz_Nmm": 0.0, "My_Nmm": 0.0}, {"combo": "B", "P_N": 0.0, "Mz_Nmm": 150e6,
                                                                         "My_Nmm": 0.0}]
    r = C.column_splice_checks(sfrs=False, P_N=2000e3, M_Nmm=150e6, splice=dict(PLATES), cases=cases, **KW)
    assert r["demand_N"] == pytest.approx(max(1000e3, 150e6 / P["d"]))          # not P/2 + M/d from two cases
    r2 = C.column_splice_checks(sfrs=False, P_N=0, M_Nmm=0, splice=dict(PLATES),
                                cases=[{"combo": "C", "P_N": 0.0, "Mz_Nmm": 0.0, "My_Nmm": 20e6}], **KW)
    assert r2["demand_N"] == pytest.approx(3 * 20e6 / P["bf"])                 # minor-axis moment enters


def test_cjp_gate_r4_and_missing_weld_error():
    r = C.column_splice_checks(sfrs=True, P_N=0, M_Nmm=0, splice={"type": "cjp"}, **KW)
    assert r["ok"] is None and "without its weld record" in r["checks"]["cjp_parent_metal"]["reason"]
    r2 = C.column_splice_checks(sfrs=True, P_N=0, M_Nmm=0,
                                splice={"type": "cjp", "weld": {"matching_electrode": True, "electrode": "E7018"}}, **KW)
    g = r2["checks"]["cjp_parent_metal"]
    assert r2["ok"] is True and g["gate"] is True and "10.5.7.1.2" in g["clause"]
    r3 = C.column_splice_checks(sfrs=True, P_N=0, M_Nmm=0, splice={"type": "cjp", "weld": {"matching_electrode": False}},
                                **KW)
    assert r3["ok"] is False


def test_is18168_7_5_and_12_3_4_7():
    a18 = {"applies": True, "system": "EBF", "Ry": 1.4}
    cases = [{"combo": "1.2DL+0.5LL+2.5EQ_X[col]", "P_N": 1500e3, "Mz_Nmm": 80e6, "My_Nmm": 5e6, "family": "5.5"}]
    sp = dict(PLATES, web_plate={"A_mm2": 2 * 200.0 * 10.0, "fy_MPa": 250.0})
    r = C.column_splice_checks(sfrs=True, P_N=0, M_Nmm=0, splice=sp, cases=cases, is18168=a18, Hc_mm=3500.0, **KW)
    comps = r["demand_components"]
    assert comps["1.2 Ry fy Af (IS 18168 7.5)"] == pytest.approx(1.2 * 1.4 * 250.0 * KW["Af_mm2"])
    assert any("5.5 combination" in k for k in comps)
    assert any("12.3.4.7" in k for k in comps)
    assert r["demand_N"] >= 1.2 * 1.4 * 250.0 * KW["Af_mm2"]
    web = r["checks"]["web_plate_6_2"]
    Aw = (P["d"] - 2 * P["tf"]) * P["tw"]
    assert web["value"] == pytest.approx(1.2 * 1.4 * 250.0 * Aw)
    sh = r["checks"]["splice_shear_sumMp_Hc"]
    assert sh["value"] == pytest.approx(2 * P["Zx"] * 250.0 / 3500.0)
    # web plate missing under IS 18168 -> not evaluated
    r2 = C.column_splice_checks(sfrs=True, P_N=0, M_Nmm=0, splice=dict(PLATES), cases=cases, is18168=a18, **KW)
    assert r2["checks"]["web_plate_6_2"]["ok"] is None


def test_cd_column_splice_cases_per_element_and_family():
    import static_model as SM
    n = len(SM.REC_FIELDS)
    idx = {k: i for i, k in enumerate(SM.REC_FIELDS)}
    r1 = [0.0] * n; r1[idx["N"]] = -2000e3
    r2 = [0.0] * n; r2[idx["Mmaj"]] = 150e6
    cfg = {"connections": {"column_splice": {"default": dict(PLATES)}}}
    out = CD.column_splice(cfg, {"section": SEC, "grade": "E250 B0"}, P, 250.0,
                           {"1.5DL+1.5LL@e1": r1, "1.5DL+1.5LL@e2": r2}, sfrs=False)
    assert out["n_cases"] == 2 and out["demand_N"] == pytest.approx(max(1000e3, 150e6 / P["d"]))
