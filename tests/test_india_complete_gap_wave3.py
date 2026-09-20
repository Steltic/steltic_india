"""complete-gap wave3: base-plate bending, B5 SI, Whitmore/block shear, end-plate Rn,
column Pn, PZ doubler-in-model, multi-joint SCWB, Ex5 storage_height_m, Ch.1 India codes.
"""
from __future__ import annotations

import math
import sys
import types
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "steel_engine"))

import india_is800 as I8
import india_loads as IL
import preflight


# ---- base-plate bending -----------------------------------------------------

def test_base_plate_bending_found_false_without_rag_or_t():
    miss = I8.base_plate_bending_check(P_N=400e3)
    assert miss["found"] is False
    assert any("plate_t" in x for x in miss["required_inputs"])


def test_base_plate_bending_from_disclosed_t_and_m():
    r = I8.base_plate_bending_check(
        P_N=500e3,
        plate_B_mm=500,
        plate_L_mm=500,
        plate_t_mm=25,
        fy_plate_MPa=250,
        cantilever_m_mm=80,
    )
    assert r["found"] is True
    assert r["t_required_mm"] > 0
    assert r["DC"] is not None
    assert r["t_provided_mm"] == 25


def test_base_plate_bending_rag_capacity_path():
    r = I8.base_plate_bending_check(
        P_N=400e3, capacity_bending_N=800e3, cited="IS 800 Ch.11 RAG"
    )
    assert r["found"] is True and abs(r["DC"] - 0.5) < 1e-9


def test_base_plate_worksheet_wires_bending():
    bp = I8.base_plate_worksheet(
        P_N=500e3,
        plate_B_mm=500,
        plate_L_mm=500,
        plate_t_mm=20,
        fy_col_MPa=250,
        cantilever_m_mm=80,
        capacity_bearing_N=1.2e6,
        capacity_anchor_N=900e3,
    )
    bend = next(s for s in bp["slots"] if s["component"] == "base_plate_bending")
    assert bend["found"] is True
    assert bend["DC"] is not None


def test_base_plate_worksheet_bending_miss_stays_false():
    bp = I8.base_plate_worksheet(P_N=200e3, capacity_bearing_N=500e3)
    bend = next(s for s in bp["slots"] if s["component"] == "base_plate_bending")
    assert bend["found"] is False


# ---- B5 SI ------------------------------------------------------------------

def test_b5_si_short_plan_no_false_warn():
    cfg = {
        "units": "N-mm",
        "NX": 6, "SX": 6000, "NY": 4, "SY": 6000,
        "heights": [8000],
        "system": "OMRF portal",
    }
    res = preflight.check(cfg)
    assert not any("B5" in m for _, m in res), res


def test_b5_si_long_plan_warns_in_metres():
    cfg = {
        "units": "N-mm",
        "NX": 20, "SX": 6000, "NY": 4, "SY": 6000,
        "heights": [8000],
        "system": "OMRF",
    }
    res = preflight.check(cfg)
    b5 = [m for _, m in res if "B5" in m]
    assert b5 and "m >" in b5[0] and "ft >" not in b5[0]


def test_b5_usa_still_warns_in_feet():
    cfg = {
        "units": "kip-in",
        "NX": 40, "SX": 360, "NY": 10, "SY": 360,
        "heights": [156],
        "system": "smf",
    }
    res = preflight.check(cfg)
    b5 = [m for _, m in res if "B5" in m]
    assert b5 and "ft >" in b5[0]


# ---- Whitmore / block shear -------------------------------------------------

def test_whitmore_found_false_no_invent():
    miss = I8.gusset_whitmore_capacity_N()
    assert miss["found"] is False


def test_whitmore_from_width_t_fy():
    ok = I8.gusset_whitmore_capacity_N(
        whitmore_width_mm=200, t_gusset_mm=12, fy_MPa=250
    )
    assert ok["found"] is True
    assert abs(ok["capacity_N"] - (200 * 12 * 250 / 1.1)) < 1.0


def test_whitmore_30deg_construction():
    ok = I8.gusset_whitmore_capacity_N(
        L_wt_mm=150, w_brace_mm=100, t_gusset_mm=10, fy_MPa=250
    )
    assert ok["found"] is True
    bw = 100 + 2 * 150 * math.tan(math.radians(30))
    assert abs(ok["whitmore_width_mm"] - bw) < 1e-6


def test_block_shear_found_false_no_invent():
    miss = I8.gusset_block_shear_capacity_N()
    assert miss["found"] is False


def test_block_shear_from_areas():
    """WP0.5 / HR800-11: both 6.4.1 expressions; min governs; missing Avn/Atg -> found:false."""
    half = I8.gusset_block_shear_capacity_N(Avg_mm2=2000, Atn_mm2=800, fy_MPa=250, fu_MPa=410)
    assert half["found"] is False
    ok = I8.gusset_block_shear_capacity_N(
        Avg_mm2=1920, Avn_mm2=1260, Atg_mm2=480, Atn_mm2=348, fy_MPa=250, fu_MPa=410
    )
    assert ok["found"] is True
    assert abs(ok["Tdb1_N"] / 1e3 - 354.7) < 0.2 and abs(ok["Tdb2_N"] / 1e3 - 323.8) < 0.2
    assert ok["capacity_N"] == min(ok["Tdb1_N"], ok["Tdb2_N"])


# ---- end-plate / column Pn / PZ / SCWB --------------------------------------

def test_end_plate_rn_rag_passthrough():
    miss = I8.end_plate_or_continuity_capacity_N()
    assert miss["found"] is False
    ok = I8.end_plate_or_continuity_capacity_N(capacity_N=1.2e6, cite="IS 800 §10 RAG")
    assert ok["found"] and ok["capacity_N"] == 1.2e6


def test_column_base_splice_pn_not_beam_bolts():
    miss = I8.column_base_or_splice_Pn_capacity_N(demand_P_N=1e6)
    assert miss["found"] is False
    assert "bolt" in miss["note"].lower()
    ok = I8.column_base_or_splice_Pn_capacity_N(capacity_N=2e6, demand_P_N=1e6)
    assert ok["found"] and abs(ok["DC"] - 0.5) < 1e-9


def test_panel_zone_doubler_in_model_recompute():
    pz = I8.panel_zone_check(
        d_col_mm=400, tw_mm=10, bf_mm=400, tf_mm=20,
        d_beam_mm=450, V_design_N=800e3, fy_MPa=250,
    )
    assert pz["pass"] is False and pz["doubler_required_mm"] > 0
    pending = I8.panel_zone_apply_doubler_in_model(pz)
    assert pending["doubler_in_model"]["found"] is False
    filled = I8.panel_zone_apply_doubler_in_model(
        pz, doubler_t_mm_in_model=pz["doubler_required_mm"] + 2.0
    )
    assert filled["doubler_in_model"]["recomputed"] is True
    assert filled["pass"] is True


def test_scwb_multi_joint_optional():
    empty = I8.scwb_multi_joint()
    assert empty["found"] is False
    joints = [
        {
            "id": "J1",
            "columns": [{"Zx_mm3": 2.0e6, "fy_MPa": 250}],
            "beams": [{"Zx_mm3": 1.0e6, "fy_MPa": 250}],
        },
        {
            "id": "J2",
            "columns": [{"Zx_mm3": 2.5e6, "fy_MPa": 250}],
            "beams": [{"Zx_mm3": 1.2e6, "fy_MPa": 250}],
        },
    ]
    multi = I8.scwb_multi_joint(joints)
    assert multi["found"] is True
    assert multi["n_joints"] == 2
    assert multi["worst_ratio"] is not None


# ---- Ex5 storage_height_m ---------------------------------------------------

def test_storage_height_prefers_brief_field():
    r = IL.resolve_storage_height_m({
        "storage_height_m": 2.5,
        "storage_height_cite": "brief",
    })
    assert r["found"] and r["h_m"] == 2.5 and r["source"] == "cfg"
    assert r["key"] == "storage_height_m"


# ---- Ch.1 India codes scrub -------------------------------------------------

def test_design_basis_codes_india_no_asce_boilerplate():
    # Avoid heavy report.py imports (matplotlib); assert the wave3 India branch in source
    # and execute the function body via a minimal stub of dependencies.
    src = (ROOT / "steel_engine" / "report.py").read_text()
    assert "IS 875 (Parts 1" in src
    assert "National Building Code of India" in src
    assert "_india" in src[src.find("def _design_basis_codes"):src.find("def _design_basis_codes") + 1200]
    # Unit-level: SI cfg selects India rows (no IBC/ASCE)
    fake_is_si = types.ModuleType("india_units")
    fake_is_si.is_si = lambda cfg=None: True
    _saved_iu = sys.modules.get("india_units")          # WP0.5: never leak the stub into later tests
    sys.modules["india_units"] = fake_is_si
    try:
        _run_design_basis_codes_stub(src)
    finally:
        if _saved_iu is not None:
            sys.modules["india_units"] = _saved_iu
        else:
            sys.modules.pop("india_units", None)


def _run_design_basis_codes_stub(src):
    # Extract and exec just _design_basis_codes with a tiny harness
    start = src.find("def _design_basis_codes")
    # find next top-level def after it
    end = src.find("\ndef _", start + 10)
    if end < 0:
        end = src.find("\ndef ", start + 10)
    chunk = src[start:end]
    # stub helpers referenced inside
    g = {
        "bool": bool, "str": str, "Exception": Exception,
        "_table": lambda headers, rows: "<table>" + "".join("%s|%s" % (a,b) for a,b in rows) + "</table>",
        "_risk_category": lambda Ie: "II",
        "_sdc": lambda *a, **k: "B",
        "_design_of_record_rows": lambda root=None: [],
        "drift_relief": lambda cfg: None,
    }
    # Provide a local import hook for india_units inside the function
    exec(chunk, g)
    html_parts = g["_design_basis_codes"](
        {"units": "N-mm", "code_region": "india"},
        {"R": 5.0, "Ie": 1.0, "SDS": 0.2, "SD1": 0.1},
    )
    blob = "\n".join(html_parts) if isinstance(html_parts, list) else str(html_parts)
    assert "IS 875" in blob or "IS 1893" in blob
    assert "ASCE/SEI 7-22" not in blob
    assert "International Building Code" not in blob


def test_h6_h7_stubs_kept():
    src = (ROOT / "contract" / "AGENT_START.md").read_text()
    assert "H7" in src and "E250B" in src
    assert "H6" in src
