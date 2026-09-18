"""Unit tests for IS 808 shapes dual-path + IS 1893 drift/irregularity helpers (no openseespy)."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "steel_engine"))
sys.path.insert(0, str(ROOT / "steltic"))

import sections as S
import india_seismic as IS
import india_collections as IC


def test_is808_mb200_props():
    p = S.props("MB200")
    assert abs(p["A"] - 4.774) < 0.01
    assert abs(p["d"] - 200 / 25.4) < 0.01
    assert p["Ix"] > p["Iy"] > 0


def test_is808_spaced_and_npb():
    assert S.props("mb 300")["A"] > 0
    labs = S.list_is808("NPB")
    assert any(L.startswith("NPB100") for L in labs)
    p = S.props(labs[0])
    assert p["A"] > 0 and p["d"] > 0


def test_channel_gap_raises():
    try:
        S.props("MC200")
        assert False, "expected KeyError for ungapped channel"
    except KeyError as e:
        assert "is808" in str(e).lower() or "GAPS" in str(e)


def test_drift_default_0004():
    dl, rho = IS.drift_allowable({})
    assert abs(dl - 0.004) < 1e-12
    assert rho is False
    assert IS.CLAUSES["storey_drift_limit"]["found"] is True
    assert IS.CLAUSES["storey_drift_limit"]["clause"] == "7.11.1.1"


def test_no_cd_ie_amplification():
    drifts = [0.002, 0.003]
    out = IS.design_story_drifts(drifts, {"seis": {"Cd": 5.5, "Ie": 1.0}})
    assert out == drifts  # factor 1.0 — ASCE Cd/Ie must NOT apply


def test_torsional_trigger_15():
    trig = IS.CLAUSES["torsional_irregularity_trigger"]["ratio_trigger"]
    assert abs(trig - 1.5) < 1e-12
    cls = IS.classify_plan_irregularities({"_tir_screen": 1.6}, {"reentrant": False})
    tors = [i for i in cls["items"] if i["type"].startswith("Torsional")][0]
    assert tors["triggered"] is True
    assert tors["found"] is True


def test_todo_asce_ax_found_false():
    todos = [t for t in IS.TODO if t["id"] == "tir_ax_amplification_asce_12_8_4_3"]
    assert todos and todos[0]["found"] is False


def test_collection_stem_map():
    assert IC.stem_for_collection("engineering_standards_IS800") == "IS_800_2007"
    assert IC.stem_for_collection("IS875_P3") == "IS_875_Part_3_2015"
    assert IC.stem_for_collection("engineering_standards_IS1893") == "IS_1893_Part_1_2016"
    assert IC.normalize_collection("IS808") == "engineering_standards_IS808"
    assert IC.is_india_spec_collection("engineering_standards_IS875_P1")
    assert not IC.is_india_spec_collection("openseespy_documentation")


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print("OK", name)
    print("all passed")
