"""H20 (CFS-C-11, L-14, NEW-4; ruling R2): IS 1893 Table 8 importance factor -- word-boundary keywords,
residential precedence over institution names, explicit class flags, storage needs food_storage declared,
matched keyword returned, D8 area rule labelled as the owner ruling."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "steel_engine"))
import india_seismic as IS  # noqa: E402
import india_seismic_gates as G  # noqa: E402

I = lambda o: IS.importance_factor(o)["I"]  # noqa: E731


def test_word_boundaries():
    assert I({"use": "small office", "persons": 50}) == 1.0          # not 'mall'
    assert I({"use": "assembly line factory"}) == 1.0                # not an assembly hall
    assert IS.importance_factor({"use": "workshop", "area_m2": 3000})["row"] == "Table 8 (iii)"   # not 'shop'
    assert I({"use": "shopping mall", "persons": 50}) == 1.5
    assert I({"use": "motel", "persons": 300}) == I({"use": "hotel", "persons": 300}) == 1.2
    assert I({"use": "student residence", "persons": 250}) == 1.2


def test_residential_precedes_institution_unless_flag():
    r = IS.importance_factor({"use": "university dormitory", "persons": 300})
    assert r["I"] == 1.2 and r["matched_keyword"] == "dormitory" and r["warnings"]
    assert I({"use": "university dormitory", "persons": 300, "educational": True}) == 1.5
    assert I({"use": "university", "persons": 300}) == 1.5


def test_explicit_flags():
    for f in ("educational", "hospital", "food_storage", "assembly", "lifeline"):
        r = IS.importance_factor({"use": "building", f: True})
        assert r["I"] == 1.5 and r["basis"] == "flag" and f in r["matched_keyword"]
    assert I({"use": "hospital", "hospital": False}) == 1.0          # explicit flag overrides the keyword


def test_storage_without_food_storage_warns():
    r = IS.importance_factor({"use": "cold storage warehouse"})
    assert r["I"] == 1.0 and any("food_storage" in w for w in r["warnings"])
    assert I({"use": "cold storage warehouse", "food_storage": True}) == 1.5
    assert not IS.importance_factor({"use": "warehouse", "food_storage": False})["warnings"]
    cfg = {"occupancy": {"use": "cold storage warehouse"}}
    assert any("food_storage" in m for m in G.occupancy_warnings(cfg))


def test_d8_labelled_as_ruling():
    r = IS.importance_factor({"use": "office", "area_m2": 2500})
    assert r["I"] == 1.2 and "D8" in r["row"] and "ruling" in r["row"] and r["basis"] == "ruling"
    assert r["row"] != "Table 8 (ii)"
    assert "D8" in IS.importance_factor({"use": "clinic"})["row"]


def test_occupancy_findings_reports_keyword():
    cfg = {"occupancy": {"use": "hospital"}, "load_plan": {"seismic_summary": {"I": 1.2}}}
    msgs = G.occupancy_findings(cfg)
    assert msgs and "hospital" in msgs[0] and "Table 8 (i)" in msgs[0]
