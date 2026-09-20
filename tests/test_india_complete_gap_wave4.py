"""complete-gap wave4: end-plate EOR Rn, cfg base/splice geometry + RAG formulas,
H6/H7 stubs kept, multi-joint SCWB optional.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "steel_engine"))

import india_is800 as I8


# ---- end-plate Rn: RAG preferred + eor_documented parallel to CFS R ----------

def test_end_plate_rn_found_false_no_invent():
    miss = I8.end_plate_or_continuity_capacity_N()
    assert miss["found"] is False
    assert any("IS 800" in x for x in miss["required_inputs"])


def test_end_plate_rn_rag_preferred():
    ok = I8.end_plate_or_continuity_capacity_N(
        capacity_N=1.5e6, cite="IS 800 §10 QFM", source="rag",
    )
    assert ok["found"] is True
    assert ok["capacity_N"] == 1.5e6
    assert ok["resolved_via"] == "rag"
    assert ok.get("Rn") == 1.5e6


def test_end_plate_rn_eor_documented_refused_d3():
    """D3 ruling: no eor_documented capacity bypass."""
    bad = I8.end_plate_or_continuity_capacity_N(
        Rn=900e3, cite="EOR calc package §EP-3", source="eor_documented", demand_N=450e3,
    )
    assert bad["found"] is False and bad["DC"] is None


def test_end_plate_rn_refuses_thin_air():
    bad = I8.end_plate_or_continuity_capacity_N(
        Rn=1e6, source="assumed", cite="guess",
    )
    assert bad["found"] is False


def test_end_plate_rn_from_cfg():
    cfg = {"end_plate_Rn": 1.1e6, "end_plate_Rn_cite": "IS 800 10.3.5 bolt tension x lever arm (computed)",
           "end_plate_Rn_source": "computed"}
    ok = I8.end_plate_or_continuity_capacity_N(cfg=cfg)
    assert ok["found"] and ok["Rn"] == 1.1e6
    cfg["end_plate_Rn_source"] = "eor_documented"
    assert I8.end_plate_or_continuity_capacity_N(cfg=cfg)["found"] is False


# ---- cfg geometry + RAG formulas for base/splice -----------------------------

def test_resolve_geometry_found_false_empty():
    miss = I8.resolve_base_or_splice_geometry({})
    assert miss["found"] is False


def test_resolve_geometry_from_cfg_block():
    cfg = {
        "base_plate_geometry": {
            "plate_B_mm": 500, "plate_L_mm": 500, "plate_t_mm": 40,
            "anchor_n": 4, "anchor_dia_mm": 24, "anchor_grade": "4.6",
            "fck_MPa": 25, "cantilever_m_mm": 80, "fy_plate_MPa": 250,
        }
    }
    g = I8.resolve_base_or_splice_geometry(cfg)
    assert g["found"] is True
    assert g["geometry"]["plate_t_mm"] == 40
    assert g["geometry"]["anchor_n"] == 4


def test_bearing_capacity_geometry_x_rag_stress():
    miss = I8.base_plate_bearing_capacity_N(plate_B_mm=400, plate_L_mm=400)
    assert miss["found"] is False  # no invent 0.45 fck

    ok = I8.base_plate_bearing_capacity_N(
        plate_B_mm=400, plate_L_mm=400, bearing_stress_MPa=11.25,  # e.g. 0.45*25 from RAG
        cite="IS 456 bearing RAG",
    )
    assert ok["found"] is True
    assert abs(ok["capacity_N"] - 400 * 400 * 11.25) < 1.0


def test_bearing_capacity_is800_0p6_fck():
    """WP0.5: IS 800 7.4.1 bearing strength 0.6 fck (not 0.45 fck 'IS 456')."""
    ok = I8.base_plate_bearing_capacity_N(plate_B_mm=500, plate_L_mm=500, fck_MPa=25)
    assert ok["found"] and abs(ok["capacity_N"] - 500 * 500 * 0.6 * 25) < 1.0
    assert abs(ok["capacity_N"] - 3750e3) < 1.0
    assert "7.4.1" in ok["cite"]


def test_anchor_group_needs_rag_one():
    miss = I8.anchor_group_capacity_N(n_anchors=4, dia_mm=24, grade="4.6")
    assert miss["found"] is False  # never invent from dia alone
    ok = I8.anchor_group_capacity_N(
        n_anchors=4, capacity_one_N=150e3, dia_mm=24, grade="4.6",
    )
    assert ok["found"] and abs(ok["capacity_N"] - 600e3) < 1.0


def test_worksheet_wires_cfg_geometry_and_rag_formulas():
    cfg = {
        "base_plate_geometry": {
            "plate_B_mm": 500, "plate_L_mm": 500, "plate_t_mm": 30,
            "cantilever_m_mm": 80, "fy_plate_MPa": 250,
            "anchor_n": 4, "anchor_dia_mm": 20,
            "fck_MPa": 25,
        }
    }
    bp = I8.base_plate_worksheet(
        P_N=800e3,
        cfg=cfg,
        capacity_one_anchor_N=250e3,
        cited="IS 800:2007 7.4",
    )
    assert bp["geometry"]["cfg_geometry_found"] is True
    bend = next(s for s in bp["slots"] if s["component"] == "base_plate_bending")
    assert bend["found"] is True  # t + m + fy from cfg
    bearing = next(s for s in bp["slots"] if s["component"] == "base_plate_bearing")
    assert bearing["found"] is True
    anchors = next(s for s in bp["slots"] if s["component"] == "anchor_bolts")
    assert anchors["found"] is True


def test_worksheet_found_false_without_geometry_or_rag():
    bp = I8.base_plate_worksheet(P_N=200e3)
    assert bp["found"] is False
    bend = next(s for s in bp["slots"] if s["component"] == "base_plate_bending")
    assert bend["found"] is False


def test_column_base_splice_pn_from_geometry_rag():
    miss = I8.column_base_or_splice_Pn_capacity_N(demand_P_N=1e6)
    assert miss["found"] is False
    assert "bolt" in miss["note"].lower()

    ok = I8.column_base_or_splice_Pn_capacity_N(
        demand_P_N=500e3,
        plate_B_mm=400, plate_L_mm=400,
        bearing_stress_MPa=12.0,
        anchor_n=4, capacity_one_anchor_N=200e3,
        cite="IS 800:2007 7.4",
    )
    assert ok["found"] is True
    # bearing = 400*400*12 = 1.92e6; anchors = 800e3 → gov = anchors
    assert ok["governing"] == "anchors"
    assert abs(ok["capacity_N"] - 800e3) < 1.0
    assert abs(ok["DC"] - 500e3 / 800e3) < 1e-9


def test_column_base_splice_pn_cfg_geometry():
    cfg = {
        "splice_geometry": {
            "plate_B_mm": 450, "plate_L_mm": 450, "plate_t_mm": 25,
            "anchor_n": 6, "anchor_dia_mm": 22,
        }
    }
    ok = I8.column_base_or_splice_Pn_capacity_N(
        cfg=cfg, demand_P_N=600e3,
        fck_MPa=30,
        capacity_one_anchor_N=180e3,
    )
    assert ok["found"] is True
    assert ok["geometry"]["cfg_geometry_found"] is True


# ---- H6/H7 stubs + multi-joint SCWB optional ---------------------------------

def test_h6_h7_stubs_kept_wave4():
    src = (ROOT / "contract" / "AGENT_START.md").read_text()
    assert "H7" in src and "E250B" in src
    assert "H6" in src
    assert "wave4" in src.lower() or "complete-gap wave4" in src or "INDIA_COMPLETE_GAP_WAVE4" in src


def test_scwb_multi_joint_still_optional():
    empty = I8.scwb_multi_joint()
    assert empty["found"] is False
    multi = I8.scwb_multi_joint([
        {"id": "J1", "columns": [{"Zx_mm3": 2e6, "fy_MPa": 250}],
         "beams": [{"Zx_mm3": 1e6, "fy_MPa": 250}]},
    ])
    assert multi["found"] is True


def test_end_plate_rag_passthrough_still_works():
    """wave3 contract: bare capacity_N + cite still found:true (RAG path)."""
    ok = I8.end_plate_or_continuity_capacity_N(
        capacity_N=1.2e6, cite="IS 800 §10 RAG",
    )
    assert ok["found"] and ok["capacity_N"] == 1.2e6
