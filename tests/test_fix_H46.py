"""H46 (HR-E-22, HR-A-07, HR-D-07; ruling R3): IS 18168 5.5(1) rows use gamma_LL = 0.25 when the imposed load is at
most 3 kN/m2; the IS 18168 8.2 SCWB check states its Pu basis, with cfg['scwb_pu_basis'] in {'all', 'seismic'}."""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "steel_engine"))

import india_combos as IC
import india_is800_s12 as S12


def _plan_cfg(system, **kw):
    plan = {"story_forces": {"EQ_X": {"1": [1000.0, 0, 0]}, "EQ_Y": {"1": [0, 1000.0, 0]}},
            "seismic_summary": {"zone": "IV", "Z": 0.24, "R": 5.0, "I": 1.2, "system": system}}
    cfg = {"system": system, "seis": {"R": 5.0, "zone": "IV"}, "heights": [3500.0], "SX": 7500.0, "SY": 7500.0,
           "NX": 1, "NY": 1, "load_plan": plan, "notional_loads": False}
    cfg.update(kw)
    return plan, cfg


def test_smrf_5_5_1_gamma_ll_025():
    plan, cfg = _plan_cfg("SMF", L_floor=2.5)
    cs = IC.expand_combinations(plan, cfg, method="ESM")
    r = [c for c in cs if c["family"] == "IS 18168 5.5(1)"]
    assert r and all(c["fL"] == 0.25 for c in r) and "gamma_LL = 0.25" in r[0]["cite"]
    # the IS 800 12.2.3(a) row keeps 0.5 LL
    assert all(c["fL"] == 0.5 for c in cs if c["family"] == "IS 800 12.2.3(a)")


def test_smrf_heavy_live_load_keeps_050():
    plan, cfg = _plan_cfg("SMF", L_floor=5.0)
    cs = IC.expand_combinations(plan, cfg, method="ESM")
    assert all(c["fL"] == 0.5 for c in cs if c["family"] == "IS 18168 5.5(1)")


def test_scbf_omega_25_gets_own_5_5_1_row():
    plan, cfg = _plan_cfg("SCBF", L_floor=2.5)
    plan["seismic_summary"].update(system="SCBF", R=4.5)
    cs = IC.expand_combinations(plan, cfg, method="ESM")
    r55 = [c for c in cs if c["family"] == "IS 18168 5.5(1)"]
    assert r55 and all(c["fL"] == 0.25 and "is18168_5_5" in c["tags"] and "sfrs_beam" in c["tags"] for c in r55)
    a = [c for c in cs if c["family"] == "IS 800 12.2.3(a)"]
    assert a and all("is18168_5_5" not in c["tags"] and c["fL"] == 0.5 for c in a)
    b = [c for c in cs if c["family"] == "IS 800 12.2.3(b)"]
    assert b and all("is18168_5_5" in c["tags"] for c in b)
    assert not IC.validate_combinations(cs, cfg, plan)


def _joint_md():
    col = "WPB400X400X191.11"
    members = [{"id": "c1", "section": col, "grade": "E250 B0", "role": "column", "L_mm": 3500.0, "Kz": 1.0, "Ky": 1.0},
               {"id": "c2", "section": col, "grade": "E250 B0", "role": "column", "L_mm": 3500.0, "Kz": 1.0, "Ky": 1.0},
               {"id": "b1", "section": "NPB450X190X67.16", "grade": "E250 B0", "role": "beam", "L_mm": 6000.0}]
    fs = [{"combo": "1.5DL+1.5LL", "family": "table4", "P_N": 3000e3},
          {"combo": "1.2DL+1.2LL+1.2EQ_X", "family": "table4", "P_N": 1500e3},
          {"combo": "1.2DL+0.5LL+3EQ_X[col]", "family": "12.2.3", "P_N": 2500e3}]
    j = {"id": "J1", "frame_dir": "X", "columns": [{"member_id": "c1", "position": "below"},
                                                    {"member_id": "c2", "position": "above"}],
         "beams": [{"member_id": "b1"}]}
    return j, {"members": members, "forces": {"c1": fs, "c2": fs}}


def test_scwb_pu_basis_all_default_and_seismic_option():
    j, md = _joint_md()
    r_all = S12.scwb_joint_is18168(j, md, {})
    assert r_all["Pu_basis"] == "all" and "ruling R3" in r_all["cite"]
    assert r_all["columns"][0]["Pu_N"] == 3000e3
    r_s = S12.scwb_joint_is18168(j, md, {"scwb_pu_basis": "seismic"})
    assert r_s["columns"][0]["Pu_N"] == 1500e3 and r_s["value"] > r_all["value"]
    assert S12.scwb_joint_is18168(j, md, {"scwb_pu_basis": "bogus"})["ok"] is None
