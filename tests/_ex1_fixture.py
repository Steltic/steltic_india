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
