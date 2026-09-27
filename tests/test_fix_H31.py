"""H31: consistency false positives (HR-A-05, HR-D-11, HR-E-12, E8 part 1, HR-A-16, HR-D-16, HR-E-24).

- literal_dc_issues reads the governing child check (value + limit), not the parent record;
- geometry fits (anchor pitch / edge / fit, weld length) and boolean detailing gates carry dc None, gate True;
- the B8 delegated-design and A6 footfall rules use agent-authored text + structured records only.
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "steel_engine"))

import consistency as CC
import india_connections as IC
import india_is800_s12 as S12


def _base(**kw):
    a = dict(d_mm=24, grade="4.6", n_total=4, n_tension=2, pitch_mm=150.0, edge_mm=50.0, n_per_row=2, f_mm=200.0)
    a.update(kw)
    return IC.base_plate_design(B_mm=250.0, L_mm=500.0, t_plate_mm=25.0, fy_plate_MPa=250.0, fck_MPa=30.0,
                                P_N=300e3, M_Nmm=30e6, V_N=20e3, col_d_mm=300.0, col_bf_mm=150.0, col_tf_mm=12.0,
                                anchors=a)


def test_anchor_fit_exactly_at_plate_width_is_a_gate_not_the_governing_dc():
    # span = (2-1)*150 + 2*50 = 250 = B -> geometric fit value == limit
    r = _base()
    g = r["checks"]["geometry_anchor_fit"]
    assert g["value"] == g["limit"] == 250.0
    assert g["dc"] is None and g["gate"] is True and g["ok"] is True
    for k in ("geometry_anchor_pitch", "geometry_anchor_edge"):
        assert r["checks"][k]["dc"] is None and r["checks"][k]["gate"] is True
    strength = [c["dc"] for n, c in r["checks"].items() if isinstance(c, dict) and c.get("dc") is not None]
    assert r["dc"] == max(strength)
    assert not any(n.startswith("geometry_") for n, c in r["checks"].items() if c.get("dc") == r["dc"])


def test_geometry_gate_fails_on_ok_when_rows_do_not_fit():
    r = _base(pitch_mm=40.0)          # 2.5 d = 60 > 40
    assert r["checks"]["geometry_anchor_pitch"]["ok"] is False
    assert r["ok"] is False


def test_weld_length_is_a_gate():
    r = IC.base_plate_design(B_mm=400.0, L_mm=400.0, t_plate_mm=25.0, fy_plate_MPa=250.0, fck_MPa=30.0,
                             P_N=300e3, M_Nmm=0.0, V_N=0.0, col_d_mm=300.0, col_bf_mm=150.0, col_tf_mm=12.0,
                             weld_length_mm=900.0, col_perimeter_mm=900.0)
    w = r["checks"]["geometry_weld_length"]
    assert w["dc"] is None and w["gate"] is True and w["ok"] is True


def test_boolean_detailing_gate_has_no_dc():
    c = S12._chk("12.11.3.3_column_lateral_support", True, True, clause="IS 800:2007 12.11.3.3", cite="x",
                 dc=None, ok=True)
    assert c["dc"] is None and c["gate"] is True and c["ok"] is True
    c2 = S12._chk("x", True, True, clause="c", cite="x")     # boolean value/limit, no explicit dc
    assert c2["dc"] is None and c2["gate"] is True
    c3 = S12._chk("12.3.4.4_connection_moment", 5e6, 5e6, clause="IS 18168:2023 12.3.4.4", cite="x", ok=True,
                  dc=None)
    assert c3["dc"] is None                                   # explicit dc=None is honoured (was 1.000)
    c4 = S12._chk("num", 50.0, 100.0, clause="c", cite="x")
    assert abs(c4["dc"] - 0.5) < 1e-12 and "gate" not in c4


def test_literal_dc_reads_governing_child():
    pkg = {"connections": [{"id": "conn-base", "DC": 1.0, "demand": {"P_N": 1.0},
                            "checks": [{"name": "plate", "value": 1650.0, "limit": 1650.0, "dc": 1.0, "ok": True,
                                        "clause": "IS 800:2007 7.4.3.1"}]}]}
    assert CC.literal_dc_issues(pkg) == []
    # a parent 1.000 with no child carrying value + limit is still flagged
    pkg["connections"][0]["checks"] = [{"name": "plate", "dc": 1.0, "ok": True}]
    iss = CC.literal_dc_issues(pkg)
    assert iss and "literal D/C 1.000" in iss[0]


def test_literal_dc_skips_gates():
    pkg = {"connections": [{"id": "c", "checks": [{"name": "g", "value": True, "limit": True, "dc": 1.0,
                                                    "ok": True, "gate": True}]}]}
    assert CC.literal_dc_issues(pkg) == []


def _mem(role, L_mm):
    return {"id": "%s-X" % role, "inputs": {"role": role, "length_mm": L_mm}}


def test_engine_deck_text_does_not_trigger_delegated_register():
    cfg = {"heights": [4000.0], "arch": "shed"}
    pkg = {"members": [], "secondary_members": [{"note": "LLT_sag = deck restraint", "cite": "joist"}]}
    assert not any("delegated-design" in i for i in CC._consultancy_issues(cfg, pkg))


def test_delegated_register_requires_structured_record():
    cfg = {"heights": [4000.0], "notes": "roof on metal deck; purlins by the sheeting supplier"}
    pkg = {"members": [], "capacity_design": {"note": "delegated to supplier"}}
    iss = [i for i in CC._consultancy_issues(cfg, pkg) if "delegated-design" in i]
    assert iss, "a keyword 'delegated' alone must not clear B8"
    cfg["delegated_design"] = [{"item": "metal deck", "criteria": "IS 801 span tables"}]
    iss = [i for i in CC._consultancy_issues(cfg, pkg) if "delegated-design" in i]
    assert iss and "interface_forces" in iss[0]
    cfg["delegated_design"][0]["interface_forces"] = "1.2 kN/m2 gravity on purlins; diaphragm by X-bracing"
    assert not any("delegated-design" in i for i in CC._consultancy_issues(cfg, pkg))


def test_vibration_keyword_alone_does_not_clear_footfall():
    cfg = {"heights": [4000.0, 4000.0]}
    pkg = {"members": [_mem("floor", 13000.0)], "note": "vibration checked"}
    assert any("VIBRATION" in i for i in CC._consultancy_issues(cfg, pkg))
    cfg["vibration_screen"] = {"basis": "IS 800 5.6.4 / Annex screen: f1 = 6.1 Hz",
                               "result": "f1 > 5 Hz: ok for office", "cite": "IS 800:2007 5.6.4"}
    assert not any("VIBRATION" in i for i in CC._consultancy_issues(cfg, pkg))


def test_lean_to_roof_level_is_not_a_floor():
    cfg = {"heights": [4000.0, 4000.0], "roof_levels": [1]}
    pkg = {"members": [_mem("floor", 13000.0)]}
    assert not any("VIBRATION" in i for i in CC._consultancy_issues(cfg, pkg))
