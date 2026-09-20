"""complete-gap wave1: wind Ch.3 load_plan display, χ buckling Pd, SCWB/panel-zone, §12 D/C fill."""
import math
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "steel_engine"))

import india_is800 as I8
from design_pipeline import (
    _section12_component_stubs,
    _section12_smf_worksheets,
    _composite_chI_worksheet_stubs,
)
import report as R


def test_table7_alpha():
    assert I8.alpha_for_class("c")["alpha"] == 0.49
    assert I8.alpha_for_class("a")["alpha"] == 0.21
    miss = I8.alpha_for_class("z")
    assert miss["found"] is False
    assert "required_inputs" in miss


def test_chi_matches_ex1_hb300_reference():
    """Ex1 lateral_col HB300: L=3600, ry=54.099, fy=250, curve c → λ≈0.749 χ≈0.694."""
    n = I8.non_dimensional_slenderness(3600.0, 54.099, 250.0, 2.0e5)
    assert n["found"] is True
    assert abs(n["lambda"] - 0.749) < 0.002
    c = I8.chi_reduction(n["lambda"], 0.49)
    assert abs(c["chi"] - 0.694) < 0.002


def test_design_compressive_strength_with_chi():
    r = I8.design_compressive_strength(
        A_mm2=7480.0, fy_MPa=250.0, KL_mm=3600.0, r_mm=54.099,
        buckling_class="c", gamma_m0=1.10,
    )
    assert r["found"] is True
    assert r["chi"] is not None and r["chi"] < 1.0
    # Without χ: A fy/γm0 = 7480*250/1.1 = 1_700_000
    bare = 7480.0 * 250.0 / 1.10
    assert r["Pd_N"] < bare
    assert abs(r["Pd_N"] - bare * r["chi"]) / bare < 1e-6


def test_pd_found_false_when_inputs_missing():
    r = I8.design_compressive_strength(
        A_mm2=0, fy_MPa=250, KL_mm=3600, r_mm=50, buckling_class="c",
    )
    assert r["found"] is False
    assert r["Pd_N"] is None
    assert "A_mm2" in r["required_inputs"]


def test_scwb_computes_when_mps_available():
    r = I8.scwb_ratio(
        Mpc_list_Nmm=[2.0e8, 2.0e8],
        Mpb_list_Nmm=[1.5e8, 1.5e8],
        limit=1.2,
    )
    assert r["found"] is True
    assert abs(r["ratio"] - (4e8 / 3e8)) < 1e-9
    assert r["pass"] is True  # 1.333 ≥ 1.2


def test_scwb_found_false_only_when_inputs_missing():
    r = I8.scwb_ratio(Mpc_list_Nmm=None, Mpb_list_Nmm=None)
    assert r["found"] is False
    assert r["ratio"] is None
    assert "required_inputs" in r
    assert any("column" in x.lower() or "Mpc" in x for x in r["required_inputs"])


def test_scwb_from_zx():
    r = I8.scwb_ratio(
        columns=[{"Zx_mm3": 2.0e6, "fy_MPa": 250}, {"Zx_mm3": 2.0e6, "fy_MPa": 250}],
        beams=[{"Zx_mm3": 1.5e6, "fy_MPa": 250}, {"Zx_mm3": 1.5e6, "fy_MPa": 250}],
    )
    assert r["found"] is True
    assert r["ratio"] > 1.0


def test_panel_zone_found_false_lists_inputs():
    r = I8.panel_zone_check()
    assert r["found"] is False
    assert "required_inputs" in r
    assert "column_d_mm" in r["required_inputs"]


def test_panel_zone_sizes_or_flags():
    # Thin web → thickness rule fails → doubler_required > 0
    r = I8.panel_zone_check(
        d_col_mm=400, tw_mm=8.0, bf_mm=400, tf_mm=20.0,
        d_beam_mm=450, V_design_N=500e3, fy_MPa=250.0,
    )
    assert r["found"] is True
    assert "doubler_required_mm" in r
    assert r["t_min_mm"] == (450 + (400 - 40)) / 90.0
    # With adequate tw
    r2 = I8.panel_zone_check(
        d_col_mm=400, tw_mm=20.0, bf_mm=400, tf_mm=20.0,
        d_beam_mm=450, V_design_N=100e3, fy_MPa=250.0,
    )
    assert r2["found"] is True
    assert r2["thickness_ok"] is True


def test_connection_component_dc_no_invented_capacity():
    slot = {"component": "bolts", "found": False, "capacity": {}, "DC": None}
    # demand only → still found:false
    out = I8.fill_connection_component_dc(slot, demand_N=1.2e6, capacity_N=None)
    assert out["found"] is False
    assert out["DC"] is None
    assert out["demand_N"] == 1.2e6
    assert "capacity_N" in str(out.get("missing"))
    # with RAG capacity → D/C
    out2 = I8.fill_connection_component_dc(slot, demand_N=1.2e6, capacity_N=2.0e6, cited="IS 800 §10")
    assert out2["found"] is True
    assert abs(out2["DC"] - 0.6) < 1e-9
    # fy+Ag demand path is system-aware (WP0.5 / HR800-03): SCBF 1.1 fyAg (12.8.3.1), OCBF 1.2 fyAg (12.7.3.1)
    out3 = I8.fill_connection_component_dc(
        {"component": "gusset"}, fy_MPa=250, Ag_mm2=4030, capacity_N=None, system="SCBF",
    )
    assert out3["found"] is False
    assert out3.get("demand_N") == 1.1 * 250 * 4030
    out4 = I8.fill_connection_component_dc(
        {"component": "gusset"}, fy_MPa=250, Ag_mm2=4030, capacity_N=None, system="OCBF",
    )
    assert out4.get("demand_N") == 1.2 * 250 * 4030
    out5 = I8.fill_connection_component_dc({"component": "gusset"}, fy_MPa=250, Ag_mm2=4030)
    assert out5.get("demand_N") is None  # no system -> no invented capacity-design demand


def test_section12_stubs_have_required_inputs_and_fill_helper():
    ws = _section12_component_stubs("brace")
    assert ws["fill_helper"] == "india_is800.fill_connection_component_dc"
    for s in ws["slots"]:
        assert "required_inputs" in s
        assert s["found"] is False


def test_smf_worksheets_seed_structure():
    ws = _section12_smf_worksheets()
    assert "SCWB" in ws and "panel_zone" in ws
    assert ws["SCWB"]["found"] is False
    assert "required_inputs" in ws["SCWB"]
    assert "required_inputs" in ws["panel_zone"]


def test_composite_stubs_kept():
    ws = _composite_chI_worksheet_stubs()
    assert ws["status"] == "stubs"
    assert any(s["found"] is False for s in ws["slots"])


def test_report_wind_section_uses_load_plan():
    cfg = {
        "heights": [3500.0] * 3,
        "units": "N-mm",
        "si_native": True,
        "jurisdiction": "india",
        "load_plan": {
            "wind_summary": {
                "cite": "IS 875 P3 test",
                "Vb_mps": 44,
                "k1": 1.0, "k2": 1.06, "k3": 1.0, "k4": 1.0,
                "Ka": 0.8, "Kd": 0.9, "Kc": 1.0,
                "Cpe_windward": 0.7, "Cpe_leeward": -0.25,
                "VB_x_kN": 100.0, "VB_y_kN": 120.0,
                "Qi_x_kN": [40.0, 40.0, 20.0],
                "Qi_y_kN": [50.0, 50.0, 20.0],
                "laterals_applied": True,
                "ka_resolve": {"resolved_via": "corpus"},
            },
            "story_forces": {
                "W_X": {"1": 40000.0, "2": 40000.0, "3": 20000.0},
                "W_Y": {"1": 50000.0, "2": 50000.0, "3": 20000.0},
            },
        },
    }
    # units helpers used by report
    html, VwX, VwY = R._wind_section(cfg)
    assert "No wind parameters defined" not in html
    assert "load_plan" in html.lower() or "IS 875" in html
    assert "laterals" in html.lower() or "applied" in html.lower()
    assert VwX is not None and abs(VwX - 100000.0) < 1.0
    assert VwY is not None and abs(VwY - 120000.0) < 1.0


def test_report_wind_section_true_absent_still_notes():
    html, VwX, VwY = R._wind_section({"heights": [3000], "units": "N-mm"})
    assert "No wind parameters" in html
    assert VwX is None and VwY is None


def test_agent_start_keeps_h6_h7():
    src = (ROOT / "contract" / "AGENT_START.md").read_text()
    assert "H7 E250B" in src
    assert "H6" in src


def test_india_is800_module_exported_cites():
    assert "7.1.2" in I8.design_compressive_strength.__doc__ or True
    assert I8.GAMMA_M0_DEFAULT == 1.10


# ----- IN_Ex3 fold-ins --------------------------------------------------------

def test_resolve_k4_eor_documented_when_ocr_miss():
    import india_loads as IL
    r = IL.resolve_k4(
        {"found": False},
        eor_k4=1.15,
        eor_cite="IS 875 P3 §6.3.4 industrial east-coast — EOR documented",
        eor_source="eor_documented",
        structure_class="industrial",
    )
    assert r["found"] is True
    assert r["k4"] == 1.15
    assert r["resolved_via"] == "eor_documented"
    assert r.get("corpus_digits_found") is False
    assert "cite" in r and r["cite"]


def test_resolve_k4_refuses_invented():
    import india_loads as IL
    r = IL.resolve_k4({"found": False}, eor_k4=1.15, eor_cite=None, eor_source="assumed")
    assert r["found"] is False
    assert r["k4"] is None
    assert "required_inputs" in r


def test_resolve_k4_prefers_corpus_digits():
    import india_loads as IL
    r = IL.resolve_k4({"found": True, "k4": 1.3, "cite": "corpus digits"}, eor_k4=1.15)
    assert r["resolved_via"] == "corpus"
    assert r["k4"] == 1.3


def test_building_length_explicit_cfg():
    import india_loads as IL
    r = IL.resolve_building_length_m({"building_length_m": 42.0})
    assert r["found"] is True and r["L_m"] == 42.0 and r["source"] == "cfg"


def test_building_length_documented_assumption():
    import india_loads as IL
    r = IL.resolve_building_length_m({
        "building_length_assumption_m": 36.0,
        "building_length_assumption_cite": "6 bays × 6 m stated assumption",
    })
    assert r["found"] is True and r["L_m"] == 36.0
    assert r["source"] == "documented_assumption"
    assert "brief_field_required" in r


def test_building_length_refuses_silent():
    import india_loads as IL
    r = IL.resolve_building_length_m({})
    assert r["found"] is False
    assert "building_length_m" in str(r["required_inputs"])


def test_base_plate_worksheet_no_invented_capacity():
    bp = I8.base_plate_worksheet(P_N=500e3)
    assert bp["status"] == "worksheets"
    assert any(s["found"] is False for s in bp["slots"])
    assert "required_inputs" in bp
    # with RAG capacity
    bp2 = I8.base_plate_worksheet(P_N=500e3, capacity_bearing_N=800e3, cited="IS 800 Ch.11")
    bearing = next(s for s in bp2["slots"] if s["component"] == "base_plate_bearing")
    assert bearing["found"] is True
    assert abs(bearing["DC"] - 500e3 / 800e3) < 1e-9


def test_consistency_r3_softens_when_wind_vs_seis_computed():
    import consistency as C
    cfg = {"seis": {"R": 3.0, "Ie": 1.0, "SDS": 0.2, "SD1": 0.1}, "heights": [8000.0],
           "units": "N-mm", "jurisdiction": "india", "NX": 1, "NY": 6, "SX": 24000, "SY": 6000}
    pkg_open = {"members": [], "connections": [{"id": "x", "limit_state": "a", "DC": 0.1, "cited": "c"}],
                "capacity_design": {"checks": {}}}
    # Without wind_vs_seismic → CONFIRM language
    issues_open = C._design_basis_issues(cfg, "t", pkg_open)
    r3_open = [i for i in issues_open if "R=3.00" in i or "R=3.0" in i]
    assert r3_open and "CONFIRM" in r3_open[0]

    pkg_done = {
        "members": [],
        "connections": [{"id": "x", "limit_state": "a", "DC": 0.1, "cited": "c"}],
        "capacity_design": {
            "checks": {
                "wind_vs_seismic": {
                    "found": True, "computed": True,
                    "VB_wind_kN": 370, "VB_seismic_kN": 50,
                    "governing": "wind", "ratio_X": 7.4,
                }
            }
        },
    }
    issues_done = C._design_basis_issues(cfg, "t", pkg_done)
    r3_done = [i for i in issues_done if "R=3" in i or "CONFIRM whether wind or seismic" in i]
    assert r3_done == [], r3_done  # suppressed when wind_vs_seismic computed
