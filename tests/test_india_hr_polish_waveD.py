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
    cfg = {"system": "BRBF", "R": 4.5, "R_source": "eor_documented",
           "R_cite": "EXAMPLE EOR — Table 9 BRBF found:false", "R_steel_brbf_table9_found": False,
           "Omega0_found": False}
    d = ISG.complete_gate_disclosure(cfg)
    assert d["complete_allowed"] is False                 # D3: BRBF has no IS basis
    assert d["status"] == "example_only"                  # EXAMPLE label in the R cite
    assert d["Omega0"]["found"] is False
    assert "never invent" in d["policy"].lower()


def test_omega0_eor_literal_refused():
    r = ISG.resolve_Omega0({}, eor_Omega0=2.0, eor_cite="Project EOR overstrength (not IS 1893)",
                           eor_source="eor_documented")
    assert r["found"] is False and r["Omega0"] is None


# ---- Table 9 / D3 -----------------------------------------------------------

def test_brbf_spsw_dual_have_no_is_basis():
    for sysname in ("BRBF midrise", "SPSW core", "dual SMF+BRBF"):
        cfg = {"system": sysname, "R": 4.5, "zone": "IV"}
        errs = [m for s, m in ISG.system_zone_findings(cfg) if s == "ERROR"]
        assert any("no Indian design basis" in m for m in errs), sysname
        assert ISG.complete_allowed(cfg)[0] is False


def test_ebf_is_table9_row_R5():
    r = ISG.resolve_system_R({"system": "EBF"})
    assert r["R_table9"] == 5.0 and r["components"] == ["sbf_eccentric"]
    assert not any("ebf" in k for k in ISG.table9_system_flags({"system": "EBF"}))


def test_is800_omrf_proxy_refuses_complete():
    cfg = {"system": "OMRF", "R": 4.0, "R_source": "is800_omrf", "R_cite": "IS 800 Table 23 OMF 4",
           "zone": "II"}
    assert "is800_omrf" in ISG.R_PROXY_SOURCES
    errs = [m for s, m in ISG.validate_R(cfg) if s == "ERROR"]
    assert any("proxy" in m for m in errs) and any("exceeds" in m for m in errs)
    assert ISG.complete_allowed(cfg)[0] is False


def test_imf_maps_to_omrf_unless_declared_smrf():
    assert ISG.resolve_system_R({"system": "IMF school"})["R_table9"] == 3.0
    assert ISG.resolve_system_R({"system": "IMF school", "imf_as_smrf": True})["R_table9"] == 5.0
    errs = [m for s, m in ISG.system_zone_findings({"system": "IMF school", "R": 3.0, "zone": "IV"}) if s == "ERROR"]
    assert any("not allowed in Seismic Zone IV" in m for m in errs)


def test_example_label_gives_example_only():
    st = ISG.design_status({"system": "SCBF", "R": 4.5, "zone": "IV",
                            "R_cite": "EXAMPLE / not-for-construction memo"})
    assert st["status"] == "example_only"


# ---- Whitmore / block shear -------------------------------------------------

def test_whitmore_block_shear_status_found_false_on_miss():
    s = I8.gusset_whitmore_block_shear_status()
    assert s["found"] is False
    assert s["status"] == "found_false"
    assert s["blocks_complete"] is True  # WP2.5: 12.7.3.2/12.8.3.2 make block shear mandatory
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
            "Avn_mm2": 1800,
            "Atg_mm2": 1400,
            "Atn_mm2": 1200,
            "fu_MPa": 410,
        }
    )
    assert s["whitmore"]["found"] is True
    assert s["block_shear"]["found"] is True


# ---- H6 / H7 ----------------------------------------------------------------

def test_h6_h7_residual_status_wp29():
    """WP2.9: composite = IS 11384 (found:false, blocking unless bare-steel/delegated); E250B is a design check."""
    r = I8.h6_h7_residual_status({"composite": True})
    assert r["blocking"] is True
    assert r["H6"]["found"] is False and "11384" in r["H6"]["cite"]
    assert r["H6"]["pe_stamp"] is None and r["H6"]["pe_stamp_invented"] is False
    assert r["H7"]["status"] == "design_requirement" and r["H7"]["blocking"] is True
    ok = I8.h6_h7_residual_status({"composite": True, "composite_scope": "bare_steel"})
    assert ok["H6"]["blocking"] is False


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
            "site_proxy_distance_km": 30.0,  # ruling R5 record (H47)
            "site_proxy_verify": True,
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
            "site_proxy_distance_km": 30.0,  # ruling R5 record (H47)
            "site_proxy_verify": True,
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
            "site_proxy_distance_km": 30.0,  # ruling R5 record (H47)
            "site_proxy_verify": True,
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
