"""Shared IN_Ex1 fixture (tests/fixtures/IN_Ex1 = the shipped build_and_run.py + load_plan.json).

`ex1_cfg(upgrade=True)` returns the Ex1 cfg upgraded to the WP1 schema the way an agent must now
write it: explicit story_forces_units, fE/fW on every lateral combination (read from the label),
occupancy, and no ASCE shims.  `upgrade=False` returns the cfg as shipped.
"""
import copy
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FIX = ROOT / "tests" / "fixtures" / "IN_Ex1"
for p in (str(ROOT / "steel_engine"), str(FIX)):
    if p not in sys.path:
        sys.path.insert(0, p)


def ex1_cfg(upgrade=True):
    os.environ.setdefault("STELTIC_TEST_JOBS", str(ROOT / "tests" / "_jobs"))
    import build_and_run as B
    cfg, seis = B.build_cfg()
    if not upgrade:
        return cfg, seis
    import india_loads as IL
    plan = cfg["load_plan"]
    plan["story_forces_units"] = "N"
    for c in plan["combinations"]:
        ref = c.get("lateral_ref")
        if ref:
            f = IL.label_lateral_terms(c["label"])[0][0]
            c["fE" if IL.lateral_kind(ref) == "EQ" else "fW"] = f
    for k in ("SDS", "SD1", "Cd", "Om0", "Ct", "x", "Cu", "Ie"):
        cfg["seis"].pop(k, None)
    cfg["occupancy"] = {"use": "office", "area_m2": 3600.0}
    return cfg, seis


def ex1_cfg_is():
    """Ex1 rebuilt the way the India contract now requires (spec WP6 row Ex1 + D8/D9):
    I = 1.2 (office > 2,000 m2, D8), office imposed load 4.0 kN/m2 (D9), IS 875-2 3.1.2 partition
    allowance 1.0 kN/m2 for design and 0.5 kN/m2 in W (7.3.6), member self-weight in DL and W,
    ESM summary recomputed from the engine seismic weights, generated combinations, RSA."""
    cfg, seis = ex1_cfg(upgrade=True)
    import engine3d as E
    cfg.update(L_floor=4.0, partition_load_kNm2=1.0, deck_span="X", steel_grade="E250BR",
               brace_grade="YSt 310", brace_process="HFS", analyses=["RSA"], brace_config="X")
    cfg["seis"].update(I=1.2)
    plan = cfg["load_plan"]
    ss = plan["seismic_summary"]
    ss.update(I=1.2, soil="II")
    for k in ("Cs", "V", "Tu", "Ta", "k", "W", "Fx"):
        ss.pop(k, None)
    r = E.esm_from_model(cfg, {"X": ss["Ta_x_s"], "Y": ss["Ta_y_s"]}, soil="II")
    ss.update(r["seismic_summary"])
    ss.update(system="SCBF", zone="IV", Z=0.24, R=4.5, Ta_formula="0.09 h/sqrt(d) (7.6.2(c) all other buildings)")
    sf = plan["story_forces"]
    for d in ("X", "Y"):
        sf["EQ_" + d] = r["story_forces"]["EQ_" + d]
    plan["story_forces_units"] = "N"
    plan["combinations"] = "auto"
    return cfg, r
