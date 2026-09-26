"""H07 (L-02, HR-B-03, NEW gusset): per-axis K (Kz L on rz, Ky L on ry) in the Section 12 brace compression, KL/r and
gusset-buckling demand; OCBF / SCBF brace compression from the Table 4 combinations only (12.2.3 rows are for columns
and connections; IS 18168 5.5(c) names braces of EBFs only)."""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "steel_engine"))

import india_is800 as I8
import india_is800_s12 as S12
import sections as S

SEC = "WPB250X250X73.15"


def _md(Kz=1.0, Ky=1.0):
    m = {"id": "e3", "section": SEC, "grade": "E250 B0", "role": "brace", "L_mm": 5600.0, "sfrs": True, "Kz": Kz,
         "Ky": Ky, "An_mm2": 9310.0}
    forces = {"e3": [{"combo": "1.5DL+1.5EQ_X", "family": "table4", "P_N": 700e3},
                     {"combo": "1.2DL+0.5LL+2.5EQ_X[col]", "family": "12.2.3", "P_N": 1050e3},
                     {"combo": "TS:+1.0EQ_X", "family": "tension_share", "P_N": 900e3}]}
    conn = {"id": "conn-e3", "member_id": "e3", "kind": "brace_end", "weld_type": "cjp",
            "welds_cjp": {"t_mm": 14.0, "length_mm": 650.0, "fy_MPa": 250.0, "n_sides": 4},
            "gusset": {"t_mm": 25.0, "fy_MPa": 250.0, "fu_MPa": 410.0, "w_start_mm": 250.0, "L_conn_mm": 650.0,
                       "L_unbraced_mm": 300.0, "K": 0.65}, "moment_capacity_Nmm": 1e12}
    return m, {"members": [m], "forces": forces, "connections": [conn]}


def test_scbf_brace_compression_from_table4_only():
    m, md = _md()
    out = S12.brace_member_checks("SCBF", m, md, {"zone": "IV", "I": 1.2})
    c = next(c for c in out if c["id"] == "brace_compression")
    assert c["value"] == 700e3 and c["demand_family"] == "table4"


def test_ebf_connection_force_keeps_5_5_row():
    m, md = _md()
    f = S12.brace_connection_force("EBF", m, md, cfg={"zone": "IV"})
    assert f["found"] and f["candidates"]["IS 18168 5.5 overstrength combination (Omega 2.5)"] == 1050e3


def test_per_axis_K_in_klr_compression_and_gusset():
    m, md = _md(Kz=1.0, Ky=0.5)
    p = S.props(SEC)
    out = S12.brace_member_checks("SCBF", m, md, {"zone": "IV", "I": 1.2})
    klr = next(c for c in out if c["id"] == "brace_KL_r")
    assert abs(klr["value"] - max(5600.0 / p["rx"], 0.5 * 5600.0 / p["ry"])) < 1e-9
    comp = next(c for c in out if c["id"] == "brace_compression")
    ref = I8.compression_capacity(p, 250.0 if p["tf"] <= 20 else 240.0, KLz_mm=5600.0, KLy_mm=2800.0)
    assert abs(comp["Pd_N"] - ref["Pd_N"]) / ref["Pd_N"] < 1e-9
    old = I8.compression_capacity(p, 250.0 if p["tf"] <= 20 else 240.0, KLz_mm=5600.0, KLy_mm=5600.0)
    assert comp["Pd_N"] > old["Pd_N"]
    # gusset buckling demand = the brace buckling strength with per-axis K (higher than the max-K value)
    conn = md["connections"][0]
    oc = S12.brace_connection_checks("SCBF", m, conn, md, {"zone": "IV", "I": 1.2})
    g = next(c for c in oc if c["id"] == "gusset_out_of_plane_buckling")
    assert abs(g["value"] - ref["Pd_N"]) / ref["Pd_N"] < 1e-9


def test_ebf_brace_klr_per_axis():
    m, md = _md(Kz=1.0, Ky=0.5)
    p = S.props(SEC)
    out = S12.ebf_brace_checks(m, md, {"zone": "IV"})
    klr = next(c for c in out if c["id"] == "brace_KL_r")
    assert abs(klr["value"] - max(5600.0 / p["rx"], 0.5 * 5600.0 / p["ry"])) < 1e-9
