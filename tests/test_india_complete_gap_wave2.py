"""complete-gap wave2: dual R eor_documented, Ω0 hook, RAG connection D/C, doubler detail."""
import math
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "steel_engine"))

import india_is800 as I8
import india_seismic_gates as ISG
import india_loads as IL


# ---- Dual / steel R provenance ----------------------------------------------

# WP0.5 / D3: the EOR-adopted R path is removed; a steel "dual" has no IS 1893 Table 9 row.
def test_dual_R_eor_documented_refused_no_is_basis():
    cfg = {
        "system": "dual SMF + SCBF", "R": 4.5, "R_source": "eor_documented",
        "R_cite": "IS 1893 Table 9 steel dual row found:false; EOR uses SBF R=4.5",
        "R_steel_dual_table9_found": False, "Z": 0.16, "zone": "III",
    }
    assert "eor_documented" not in ISG.R_OK_SOURCES
    assert any(s == "ERROR" and "D3" in m for s, m in ISG.validate_R(cfg))
    assert any(s == "ERROR" and "no Indian design basis" in m for s, m in ISG.system_zone_findings(cfg))
    ok, reasons = ISG.complete_allowed(cfg)
    assert ok is False and reasons
    assert ISG.design_status(cfg)["status"] == "partial"


def test_dual_R_silent_sbf_without_source_errors():
    cfg = {"system": "dual SMF + SCBF hospital", "R": 4.5, "R_steel_dual_table9_found": False}
    assert any(s == "ERROR" for s, _ in ISG.system_zone_findings(cfg))
    ok, reasons = ISG.complete_allowed(cfg)
    assert ok is False
    assert ISG.R_is_proxy(cfg) is True


def test_dual_R_proxy_source_refuses_complete():
    cfg = {"system": "dual SMF+SCBF", "R": 4.5, "R_source": "sbf_proxy", "R_cite": "silent proxy",
           "R_steel_dual_table9_found": False}
    assert ISG.R_is_proxy(cfg) is True
    ok, _ = ISG.complete_allowed(cfg)
    assert ok is False


def test_scbf_table9_R_no_R_errors():
    cfg = {"system": "SCBF", "R": 4.5, "R_source": "is1893_table9", "zone": "IV"}
    assert not [m for s, m in ISG.validate_R(cfg) if s == "ERROR"]
    cfg["R"] = 6.0          # ASCE R for SCBF -> refused (> Table 9 4.5)
    assert any(s == "ERROR" and "exceeds" in m for s, m in ISG.validate_R(cfg))


# ---- Ω0 ---------------------------------------------------------------------

def test_omega0_default_found_false_no_invent():
    r = ISG.resolve_Omega0({"Omega0_found": False})
    assert r["found"] is False
    assert r["Omega0"] is None
    assert "IS 1893" in r["cite"] or "§12" in r["note"]
    assert ISG.omega0_blocks_complete({}) is False  # honest gap does not block


def test_omega0_eor_literal_refused_D3():
    r = ISG.resolve_Omega0({}, eor_Omega0=2.0, eor_cite="Project EOR overstrength (not IS 1893)",
                           eor_source="eor_documented")
    assert r["found"] is False and r["Omega0"] is None
    assert "12.2.3" in r["cite"] or "12.2.3" in r["note"]


def test_omega0_refuses_silent_asce():
    r = ISG.resolve_Omega0(
        {"Omega0": 3.0, "Omega0_source": "asce7", "Omega0_cite": "ASCE 7-22"},
    )
    assert r["found"] is False
    assert r["Omega0"] is None


# ---- k4 hospital / Ex4 path -------------------------------------------------

def test_resolve_k4_hospital_eor_when_ocr_miss():
    r = IL.resolve_k4(
        {"found": False},
        eor_k4=1.30,
        eor_cite="IS 875 P3 §6.3.4 important building east-coast — EOR documented",
        eor_source="eor_documented",
        structure_class="important",
    )
    assert r["found"] is True
    assert r["k4"] == 1.30
    assert r["resolved_via"] == "eor_documented"
    assert r.get("corpus_digits_found") is False


# ---- RAG connection capacities ----------------------------------------------

def test_is4000_bolt_table2_is_permissible_not_capacity():
    """WP0.5: IS 4000 Table 2 is a working-stress permissible force, never an LSD capacity_N."""
    r = I8.is4000_bolt_shear_capacity_N(
        n_bolts=4, diameter_mm=20, property_class="8.8", plane="thread",
    )
    assert r["found"] is True
    assert r["capacity_N"] is None
    assert abs(r["permissible_N"] - 4 * 50.8 * 1000.0) < 1.0
    assert "IS 4000" in r["cite"]
    m30 = I8.is4000_bolt_shear_capacity_N(n_bolts=1, diameter_mm=30, property_class="10.9", plane="shank")
    assert abs(m30["permissible_N"] - 183.6e3) < 1.0


def test_is4000_bolt_unknown_size_found_false():
    r = I8.is4000_bolt_shear_capacity_N(n_bolts=2, diameter_mm=22)
    assert r["found"] is False
    assert r["capacity_N"] is None


def test_fillet_weld_is800_lsd():
    """WP0.5: throat = K s with K = 0.70 (IS 800 Table 22), not s/sqrt2."""
    r = I8.fillet_weld_capacity_is800_N(
        size_mm=6.0, length_mm=300.0, fu_MPa=410.0, gamma_mw=1.25, n_sides=2,
    )
    assert r["found"] is True
    a = 0.70 * 6.0
    fwd = 410.0 / (math.sqrt(3.0) * 1.25)
    expect = fwd * a * 300.0 * 2
    assert abs(r["capacity_N"] - expect) / expect < 1e-9
    assert abs(r["capacity_N"] / 1e3 - 477.2) < 0.1
    site = I8.fillet_weld_capacity_is800_N(size_mm=6.0, length_mm=300.0, fu_MPa=410.0, n_sides=2, site=True)
    assert abs(site["capacity_N"] / 1e3 - 397.7) < 0.1


def test_fillet_weld_is816_only_explicit_wsm_and_permissible():
    r = I8.fillet_weld_capacity_N(
        size_mm=6.0, length_mm=200.0,
        permissible_stress_kgf_cm2=1100.0,  # IS 816 §7.1.2
        n_sides=1,
    )
    assert r["found"] is False  # IS 816 needs method="WSM"
    r = I8.fillet_weld_capacity_N(size_mm=6.0, length_mm=200.0, permissible_stress_kgf_cm2=1100.0, method="WSM")
    assert r["found"] is True and r["capacity_N"] is None and r["permissible_N"] > 0


def test_apply_rag_capacities_fills_weld_and_bolts():
    conn = {
        "type": "beam-to-column",
        "demand": {"V_N": 150e3},
        "section12_worksheet": {
            "status": "stubs",
            "slots": [
                {"component": "bolts", "found": False, "capacity": {}, "DC": None},
                {"component": "welds", "found": False, "capacity": {}, "DC": None},
                {"component": "gusset", "found": False, "capacity": {}, "DC": None},
            ],
        },
    }
    out = I8.apply_rag_capacities_to_connection(
        conn,
        rag_capacities={
            # IS 800 10.3 from geometry (not IS 4000 working values)
            "bolts": {"n_bolts": 6, "d_mm": 20, "grade": "8.8", "t_mm": 10, "fu_plate_MPa": 410, "e_mm": 35,
                      "p_mm": 60, "d0_mm": 22},
            "welds": {"size_mm": 6, "length_mm": 400, "fu_MPa": 410, "n_sides": 2},
            # gusset intentionally missing → stays found:false
        },
    )
    checks = out["component_checks"]
    assert checks["bolts"]["found"] is True
    assert checks["welds"]["found"] is True
    assert checks["gusset"]["found"] is False
    assert out["DC"] == max(checks["bolts"]["DC"], checks["welds"]["DC"])
    assert abs(checks["bolts"]["DC"] - 150e3 / (6 * 86.97e3)) < 1e-3  # Vdb = min(90.5, 87.0) kN per bolt


def test_apply_rag_miss_stays_found_false():
    conn = {
        "demand": {"P_N": 200e3},
        "base_plate_worksheet": I8.base_plate_worksheet(P_N=200e3),
    }
    out = I8.apply_rag_capacities_to_connection(conn, rag_capacities={})
    assert all(not s.get("found") for s in out["base_plate_worksheet"]["slots"])


def test_base_plate_with_rag_bearing_and_anchor():
    bp = I8.base_plate_worksheet(
        P_N=184e3,
        capacity_bearing_N=500e3,
        capacity_anchor_N=400e3,
        cited="IS 800:2007 7.4.1 / 10.3",
    )
    assert bp["found"] is True
    bearing = next(s for s in bp["slots"] if s["component"] == "base_plate_bearing")
    assert bearing["found"] is True and bearing["DC"] < 1.0


# ---- Panel-zone doubler grade/electrode -------------------------------------

def test_panel_zone_doubler_detail_requires_grade_electrode():
    pz = I8.panel_zone_check(
        d_col_mm=400, tw_mm=8.0, bf_mm=400, tf_mm=20.0,
        d_beam_mm=450, V_design_N=500e3, fy_MPa=250.0,
    )
    assert pz["found"] is True
    # 12.11.2.4 individual thickness: tw 8 < (450+360)/90 = 9 -> no doubler can cure the web (WP2.4)
    assert pz["web_thickness_ok"] is False and pz["doubler_required_mm"] is None
    pz = I8.panel_zone_check(
        d_col_mm=400, tw_mm=10.0, bf_mm=400, tf_mm=20.0,
        d_beam_mm=450, V_design_N=800e3, fy_MPa=250.0,
    )
    assert pz["doubler_required_mm"] >= pz["t_min_mm"]
    bare = I8.panel_zone_doubler_detail(pz)
    assert bare["doubler_detail"]["found"] is False
    assert "electrode" in str(bare["doubler_detail"]["required_inputs"])

    filled = I8.panel_zone_doubler_detail(
        pz,
        plate_fy_MPa=250.0,
        plate_grade="IS 2062 E250",
        plate_cite="IS 2062 E250 fy=250 (RAG) — H7 mill confirm open",
        electrode="IS 814 Exx (shop)",
        electrode_cite="IS 814 / IS 800 §10.5.6 electrodes (RAG)",
    )
    assert filled["doubler_detail"]["found"] is True
    assert filled["doubler_detail"]["doubler_required_mm"] == pz["doubler_required_mm"]


# ---- SCWB representative vs multi-joint scope --------------------------------

def test_scwb_and_panel_from_schedule():
    out = I8.scwb_and_panel_from_schedule(
        column_props=[
            {"Zx_mm3": 2.0e6, "fy_MPa": 250, "d_mm": 400, "tw_mm": 12, "bf_mm": 400, "tf_mm": 20},
            {"Zx_mm3": 2.0e6, "fy_MPa": 250},
        ],
        beam_props=[
            {"Zx_mm3": 1.2e6, "fy_MPa": 250, "d_mm": 450},
            {"Zx_mm3": 1.2e6, "fy_MPa": 250},
        ],
        V_design_N=200e3,
    )
    assert out["SCWB"]["found"] is True
    assert out["panel_zone"]["found"] is True


def test_h6_h7_stubs_kept_in_agent_start():
    src = (ROOT / "contract" / "AGENT_START.md").read_text()
    assert "H7 E250B" in src
    assert "H6" in src


def test_end_plate_capacity_passthrough_no_invent():
    miss = I8.end_plate_or_continuity_capacity_N()
    assert miss["found"] is False
    ok = I8.end_plate_or_continuity_capacity_N(capacity_N=900e3, cite="IS 800 §10 RAG")
    assert ok["found"] is True and ok["capacity_N"] == 900e3


# ---- Ex5 storage height + mass irregularity ---------------------------------

def test_resolve_storage_height_documented():
    import india_loads as IL
    r = IL.resolve_storage_height_m({
        "storage_height_assumption_m": 2.5,
        "storage_height_assumption_cite": "IS 875 P2 Table 1 — documented 2.5 m stack",
        "storage_height_source": "eor_documented",
    })
    assert r["found"] is True
    assert r["h_m"] == 2.5
    assert abs(r["L_kNpm2"] - 7.5) < 1e-9          # 2.4 x 2.5 = 6.0 < the 7.5 kN/m2 minimum (Table 1 viii)(a), WP6-fix)


def test_resolve_storage_height_refuses_silent():
    import india_loads as IL
    r = IL.resolve_storage_height_m({})
    assert r["found"] is False
    assert "storage_height_m" in str(r["required_inputs"])


def test_resolve_storage_height_cfg_explicit():
    import india_loads as IL
    r = IL.resolve_storage_height_m({"storage_height_m": 3.0, "storage_height_cite": "brief"})
    assert r["found"] and r["h_m"] == 3.0 and abs(r["L_kNpm2"] - 7.5) < 1e-9     # 2.4 x 3.0 = 7.2 -> minimum 7.5
    r4 = IL.resolve_storage_height_m({"storage_height_m": 4.0, "storage_height_cite": "brief"})
    assert abs(r4["L_kNpm2"] - 9.6) < 1e-9                                        # 2.4 x 4.0 above the minimum


def test_mass_irregularity_screen_mezzanine():
    import india_seismic as IS
    # roof light, mezz heavy relative to... actually ratio floor_i / floor_below
    # W = [open bay lower?]; use [100, 200, 80] → floor2/floor1 = 2.0 > 1.5
    r = IS.mass_irregularity_screen_note([100.0, 200.0, 80.0], zone="II")
    assert r["found"] is True
    assert r["irregular"] is True
    assert any(f["ratio"] > 1.5 for f in r["flagged"])
    assert "Table 6" in r["cite"]


def test_mass_irregularity_regular():
    import india_seismic as IS
    r = IS.mass_irregularity_screen_note([100.0, 110.0, 105.0], zone="III")
    assert r["irregular"] is False
