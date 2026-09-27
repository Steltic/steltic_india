"""D02 (HR-D-18, brief defects B12 / B13): the retired Ex12 EOR EXAMPLE memo lives under test_buildings/usa_reference/
and is no longer listed in README_INDIA; the stale 'Ex13' OCBF Zone II fixture is renamed to a legacy key, and the
current Ex13 brief (SCBF, Zone III map reading, R 4.5 Table 9 (ii)(b)) has its own fixture entry."""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "steel_engine"))

import india_seismic_gates as G

FIX = json.load(open(ROOT / "tests" / "fixtures" / "zone_system_cfgs.json"))


def test_ex12_example_memo_retired():
    tb = ROOT / "test_buildings"
    assert not (tb / "IN_Ex12_EOR_inputs_EXAMPLE.json").exists()
    assert (tb / "usa_reference" / "IN_Ex12_EOR_inputs_EXAMPLE.json").exists()
    readme = (tb / "README_INDIA.md").read_text(encoding="utf-8")
    assert "`IN_Ex12_EOR_inputs_EXAMPLE.json`" not in readme


def test_legacy_key_and_current_ex13():
    leg = FIX["legacy_Ex13_OCBF_ZoneII"]
    assert "LEGACY" in leg["_source"] and "not the current brief".lower() in leg["_source"].lower()
    ex13 = FIX["Ex13"]
    ss = ex13["load_plan"]["seismic_summary"]
    assert (ss["zone"], ss["R"]) == ("III", 4.5)
    assert "IN_Ex13_SCBF_bigbox_flexdiaphragm_Indore.txt" in ex13["_source"]
    # the current brief's SCBF passes the zone gate in Zone III with its Table 9 R
    assert not [m for s, m in G.system_zone_findings(ex13) if s == "ERROR"]
    assert G.resolve_system_R(ex13)["R_table9"] == 4.5


def test_legacy_obf_is_refused_in_zone_iii():
    """The legacy OBF case is meaningful only in Zone II: moved to Zone III it is banned (Table 9 Note 1)."""
    import copy
    leg = copy.deepcopy(FIX["legacy_Ex13_OCBF_ZoneII"])
    leg["load_plan"]["seismic_summary"].update(zone="III", Z=0.16)
    errs = [m for s, m in G.system_zone_findings(leg) if s == "ERROR"]
    assert errs, "OBF must be refused in Zone III"
