"""HR polish Wave D: Ω0 disclosure, Table 9 eor (BRBF/SPSW/EBF/IMF), Whitmore,
H6/H7 status objects, Annex town site_proxy. Never invent IS clauses.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "steel_engine"))

import india_seismic_gates as ISG
import india_loads as IL
import india_is800 as I8


# ---- Ω0 ---------------------------------------------------------------------

def test_omega0_never_invented_default_found_false():
    r = ISG.resolve_Omega0({"Omega0_found": False})
    assert r["found"] is False
    assert r["Omega0"] is None
    assert ISG.omega0_blocks_complete({}) is False


def test_omega0_complete_gate_disclosure_wired():
    cfg = {
        "system": "BRBF",
        "R": 4.5,
        "R_source": "eor_documented",
        "R_cite": "EXAMPLE EOR — Table 9 BRBF found:false",
        "R_steel_brbf_table9_found": False,
        "Omega0_found": False,
    }
    d = ISG.complete_gate_disclosure(cfg)
    assert d["complete_allowed"] is True
    assert d["Omega0"]["found"] is False
    assert d["Omega0"]["blocks_complete"] is False
    assert "steel_brbf_table9_found" in d["table9"]["misses"]
    assert "never invents" in d["policy"].lower() or "never invent" in d["policy"].lower()


def test_omega0_eor_documented_still_ok():
    r = ISG.resolve_Omega0(
        {},
        eor_Omega0=2.0,
        eor_cite="Project EOR overstrength (not IS 1893)",
        eor_source="eor_documented",
    )
    assert r["found"] is True and r["Omega0"] == 2.0


# ---- Table 9 eor / proxy refuse ---------------------------------------------

def test_brbf_table9_miss_eor_allows_complete():
    cfg = {
        "system": "BRBF midrise",
        "R": 4.5,
        "R_source": "eor_documented",
        "R_cite": "EXAMPLE labeled not-for-construction — BRBF Table 9 found:false",
        "R_steel_brbf_table9_found": False,
    }
    ok, reasons = ISG.complete_allowed(cfg)
    assert ok is True, reasons


def test_spsw_ebf_imf_table9_miss_silent_refuses_complete():
    for sysname, flag in (
        ("SPSW", "R_steel_spsw_table9_found"),
        ("EBF", "R_steel_ebf_table9_found"),
        ("IMF school", "R_steel_imf_table9_found"),
    ):
        cfg = {"system": sysname, "R": 4.0, flag: False}
        ok, _ = ISG.complete_allowed(cfg)
        assert ok is False, sysname
        assert ISG.R_is_proxy(cfg) is True


def test_is800_omrf_proxy_refuses_complete():
    cfg = {
        "system": "IMF",
        "R": 3.0,
        "R_source": "is800_omrf",
        "R_cite": "silent IS 800 OMRF invent",
        "R_steel_imf_table9_found": False,
    }
    assert "is800_omrf" in ISG.R_PROXY_SOURCES
    ok, reasons = ISG.complete_allowed(cfg)
    assert ok is False
    assert ISG.R_is_proxy(cfg) is True


def test_imf_disclosed_table9_smrf_map_allows_complete():
    """Ex11 pattern: IMF row found:false → disclosed SMRF Table 9 R=5 with cite."""
    cfg = {
        "system": "IMF school Chandigarh",
        "R": 5.0,
        "R_source": "is1893_table9",
        "R_cite": (
            "IMF Table 9 found:false; Zone IV → design as SMRF R=5.0 "
            "IS 1893 Table 9 (i)(d) found:true — disclosed mapping, not is800_omrf"
        ),
        "R_steel_imf_table9_found": False,
    }
    ok, reasons = ISG.complete_allowed(cfg)
    assert ok is True, reasons


def test_example_fixture_label_policy_flag():
    st = ISG.design_status({
        "system": "BRBF",
        "R": 4.5,
        "R_source": "eor_documented",
        "R_cite": "EXAMPLE",
        "R_steel_brbf_table9_found": False,
    })
    assert st["table9"]["example_fixtures_ok_when_labeled"] is True


# ---- Whitmore / block shear -------------------------------------------------

def test_whitmore_block_shear_status_found_false_on_miss():
    s = I8.gusset_whitmore_block_shear_status()
    assert s["found"] is False
    assert s["status"] == "found_false"
    assert s["blocks_complete"] is False
    assert s["whitmore"]["found"] is False
    assert s["block_shear"]["found"] is False


def test_whitmore_block_shear_status_rag_path():
    s = I8.gusset_whitmore_block_shear_status(
        rag_hit={
            "whitmore_capacity_N": 1.2e6,
            "block_shear_capacity_N": 9e5,
            "cite": "LIVE RAG gusset",
        }
    )
    assert s["found"] is True
    assert s["status"] == "ok"


def test_whitmore_disclosed_geometry_path():
    s = I8.gusset_whitmore_block_shear_status(
        disclosed={
            "whitmore_width_mm": 200,
            "t_gusset_mm": 12,
            "fy_MPa": 250,
            "Avg_mm2": 2400,
            "Atn_mm2": 1200,
            "fu_MPa": 410,
        }
    )
    assert s["whitmore"]["found"] is True
    assert s["block_shear"]["found"] is True


# ---- H6 / H7 ----------------------------------------------------------------

def test_h6_h7_residual_status_disclose_only_no_pe():
    r = I8.h6_h7_residual_status({"composite": True})
    assert r["blocking"] is False
    assert r["H6"]["pe_stamp"] is None
    assert r["H6"]["pe_stamp_invented"] is False
    assert r["H7"]["status"] == "process_open"
    assert r["H7"]["pe_stamp_invented"] is False
    assert "disclose" in r["status"] or "disclose" in r["policy"]


# ---- Site proxy -------------------------------------------------------------

def test_site_proxy_kochi_vb_refuses_silent():
    r = IL.resolve_site_annex_proxy(
        {"town": "Kochi", "Vb": 39},
        quantity="Vb",
        annex_hit={"found": False},
    )
    assert r["found"] is False
    assert r["site_proxy"] is False
    assert r["policy"] == "refuse_silent_wrong_city"


def test_site_proxy_kochi_vb_disclosed_ok():
    r = IL.resolve_site_annex_proxy(
        {
            "town": "Kochi",
            "site_proxy": True,
            "site_proxy_town": "Kozhikode/Trivandrum",
            "site_proxy_value": 39.0,
            "site_proxy_cite": (
                "Annex A Kochi/Cochin found:false — Kozhikode & Trivandrum Vb=39 "
                "Kerala coastal proxy disclosed"
            ),
            "site_proxy_source": "site_proxy",
        },
        quantity="Vb",
        annex_hit={"found": False},
    )
    assert r["found"] is True
    assert r["site_proxy"] is True
    assert r["value"] == 39.0
    assert r["town_found"] is False


def test_site_proxy_indore_bhopal_z():
    r = IL.resolve_site_annex_proxy(
        {
            "town": "Indore",
            "site_proxy": True,
            "site_proxy_town": "Bhopal",
            "site_proxy_value": 0.10,
            "site_proxy_cite": "Annex E Indore found:false — Bhopal Zone II Z=0.10 MP inland",
            "site_proxy_source": "site_proxy",
        },
        quantity="Z",
        annex_hit={"found": False},
    )
    assert r["found"] is True and r["site_proxy"] is True and r["value"] == 0.10


def test_site_proxy_noida_delhi_vb():
    r = IL.resolve_site_annex_proxy(
        {
            "town": "Noida",
            "site_proxy": True,
            "site_proxy_town": "Delhi",
            "site_proxy_value": 47.0,
            "site_proxy_cite": "Annex A Noida found:false — Delhi NCR Vb=47 disclosed",
            "site_proxy_source": "site_proxy",
        },
        quantity="Vb",
        annex_hit={"found": False},
    )
    assert r["found"] is True and r["value"] == 47.0


def test_annex_town_found_true_not_proxy():
    r = IL.resolve_site_annex_proxy(
        {"town": "Pune"},
        quantity="Vb",
        annex_hit={"found": True, "Vb": 39, "cite": "Annex A Pune"},
    )
    assert r["found"] is True
    assert r["site_proxy"] is False
    assert r["value"] == 39
