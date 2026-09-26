"""RR-BUG-1: the IS 1893 Table 8 importance-factor keywords must not match a negated phrase ('non-food storage',
'no food storage', 'non-hospital', 'not a hospital', 'without', 'excluding').  Explicit occupancy flags stay
authoritative; true positives are unchanged.  Repro strings from /home/claude/rerun/RERUN_REPORT.md (HR Ex5, CFS
Ex2/Ex5)."""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "steel_engine"))
import india_seismic as IS  # noqa: E402
import india_seismic_gates as G  # noqa: E402
import india_is18168 as M  # noqa: E402

IF = IS.importance_factor


@pytest.mark.parametrize("use", [
    "warehouse (general non-food storage)",           # HR Ex5
    "warehouse (general storage, no food storage)",   # CFS Ex2 / Ex5
    "general (non-food) storage",
    "warehouse without any food storage",
    "storage excluding food storage",
    "warehouse, not used for food storage",
])
def test_negated_food_storage_is_not_table8_i(use):
    r = IF({"use": use})
    assert r["found"] and r["I"] == 1.0 and r["row"] == "Table 8 (iii)"
    assert r["matched_keyword"] != "food storage"
    # the negation is reported (declare the flag to confirm) and the storage note still asks for food_storage
    assert any("negated keyword 'food storage'" in w for w in r["warnings"])


@pytest.mark.parametrize("use", ["non-hospital office", "office, not a hospital", "office (non hospital)"])
def test_negated_hospital_falls_to_office_rule(use):
    r = IF({"use": use, "persons": 50})
    assert r["I"] == 1.0 and r["row"] == "Table 8 (iii)" and r["matched_keyword"] == "office"
    r = IF({"use": use, "persons": 300})
    assert r["I"] == 1.2 and r["row"] == "Table 8 (ii)"
    # the report repro without a person count: office rule, not Table 8 (i)
    r = IF({"use": use})
    assert r["I"] != 1.5


@pytest.mark.parametrize("use,kw", [
    ("food storage warehouse", "food storage"),
    ("food-storage godown", "food storage"),
    ("grain storage godown", "grain storage"),
    ("hospital", "hospital"),
    ("non-residential hospital", "hospital"),
    ("hospital, not a school", "hospital"),
    ("secondary school", "school"),
])
def test_true_positives_unchanged(use, kw):
    r = IF({"use": use})
    assert r["I"] == 1.5 and r["row"] == "Table 8 (i)" and r["matched_keyword"] == kw


def test_explicit_flags_stay_authoritative():
    assert IF({"use": "general non-food storage", "food_storage": True})["I"] == 1.5
    assert IF({"use": "no food storage", "hospital": True})["I"] == 1.5
    r = IF({"use": "general non-food storage", "food_storage": False})
    assert r["I"] == 1.0 and not any("negated" in w for w in r["warnings"])
    assert IF({"use": "food storage", "food_storage": False})["I"] == 1.0


def test_negation_scope_is_the_phrase():
    # the negation does not leak across a phrase boundary or onto a non-adjacent keyword
    assert IF({"use": "warehouse", "uses": ["no hospital", "food storage"]})["I"] == 1.5
    assert IF({"use": "no parking, food storage"})["I"] == 1.5


def test_hr_ex5_preflight_not_blocked():
    """HR Ex5: I = 1.0 declared for 'general non-food storage' must not be an ERROR (I below Table 8 1.5)."""
    cfg = {"occupancy": {"use": "warehouse (general non-food storage)"}, "I": 1.0}
    assert G.occupancy_findings(cfg) == []
    cfg_food = {"occupancy": {"use": "food storage warehouse"}, "I": 1.0}
    assert any("below the Table 8 value 1.50" in m for m in G.occupancy_findings(cfg_food))


def test_is18168_scope_ignores_negated_uses():
    assert M.occupancy_in_scope({"use": "warehouse, no food storage"})["in_scope"] is False
    assert M.occupancy_in_scope({"use": "non-residential warehouse"})["in_scope"] is False
    assert M.occupancy_in_scope({"use": "food storage"})["in_scope"] is True
    assert M.occupancy_in_scope({"use": "office"})["in_scope"] is True
