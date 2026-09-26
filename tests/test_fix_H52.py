"""H52 (CFS-A-17, ruling R8): IS 18168 applies by the 1.2 occupancy list in Zones III-V, with an explicit
cfg['apply_is18168'] True / False override."""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "steel_engine"))

import india_is18168 as I18
import india_is800_s12 as S12
import india_combos as IC


def test_occupancy_list():
    assert I18.applies("SCBF", "IV", occupancy={"use": "office"})["applies"] is True
    assert I18.applies("SCBF", "IV", occupancy={"use": "student residence"})["applies"] is True
    wh = I18.applies("SCBF", "III", occupancy={"use": "warehouse"})
    assert wh["applies"] is False and wh["mandatory"] is False and "1.2" in wh["note"]
    assert I18.applies("SCBF", "III", occupancy=[{"use": "warehouse"}, {"use": "office"}])["applies"] is True
    # undeclared / unrecognised occupancy: applied (conservative)
    assert I18.applies("SCBF", "IV")["applies"] is True
    assert I18.applies("SCBF", "IV", occupancy={"use": "parking deck"})["applies"] is True


def test_override():
    assert I18.applies("SCBF", "IV", occupancy={"use": "warehouse"}, override=True)["applies"] is True
    assert I18.applies("SCBF", "II", override=True)["applies"] is True
    assert I18.applies("SCBF", "II", opt_in=True)["applies"] is True
    assert I18.applies("SCBF", "IV", occupancy={"use": "parking deck"}, override=False)["applies"] is False
    r = I18.applies("SCBF", "IV", occupancy={"use": "office"}, override=False)
    assert r["applies"] is True and "ignored" in r["note"]


def test_s12_status_reads_cfg_occupancy():
    assert S12.is18168_status("SCBF", {"zone": "IV", "occupancy": {"use": "industrial shed"}})["applies"] is False
    assert S12.is18168_status("SCBF", {"zone": "IV", "occupancy": {"use": "school"}})["applies"] is True


def _plan_cfg(**kw):
    plan = {"story_forces": {"EQ_X": {"1": [1000.0, 0, 0]}, "EQ_Y": {"1": [0, 1000.0, 0]}},
            "seismic_summary": {"zone": "IV", "Z": 0.24, "R": 5.0, "I": 1.2, "system": "SMF"}}
    cfg = {"system": "SMF", "seis": {"R": 5.0, "zone": "IV"}, "heights": [3500.0], "SX": 7500.0, "SY": 7500.0,
           "NX": 1, "NY": 1, "load_plan": plan, "notional_loads": False}
    cfg.update(kw)
    return plan, cfg


def test_combos_follow_occupancy():
    plan, cfg = _plan_cfg(occupancy={"use": "office"})
    c1 = IC.expand_combinations(plan, cfg, method="ESM")
    plan, cfg = _plan_cfg(occupancy={"use": "warehouse"})
    c2 = IC.expand_combinations(plan, cfg, method="ESM")
    assert any("is18168_5_5" in (c.get("tags") or []) for c in c1)
    assert not any("is18168_5_5" in (c.get("tags") or []) for c in c2)
