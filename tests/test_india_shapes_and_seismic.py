"""Unit tests for IS 808/1161 shapes dual-path + IS 1893 drift/soft-storey helpers (no openseespy)."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "steel_engine"))
sys.path.insert(0, str(ROOT / "steltic"))

import sections as S
import india_seismic as IS
import india_collections as IC
import india_units as IU


def test_is808_mb200_props():
    IU.activate_si()
    p = S.props("MB200")
    assert abs(p["A"] - 3080.0) < 5.0  # A_si_mm2
    assert abs(p["d"] - 200.0) < 0.5   # mm
    assert p["Ix"] > p["Iy"] > 0
    # Legacy kip-in pack still available
    pin = S.props("MB200", unit_system="kip-in")
    assert abs(pin["A"] - 4.774) < 0.01


def test_is808_channel_and_angle():
    IU.activate_si()
    mc = S.props("MC200")
    assert mc["A"] > 2500 and mc["d"] > 190  # mm
    isa = S.props("ISA50X50X6")
    assert 400 < isa["A"] < 700  # mm^2
    assert "MC200" in S.list_is808("MC")


def test_is1161_chs():
    IU.activate_si()
    chs = S.props("CHS60.3X3.6")
    assert chs["A"] > 500  # mm^2
    assert abs(chs["Ix"] - chs["Iy"]) < 1e-3
    assert len(S.list_chs("CHS")) >= 50


def test_is808_spaced_and_npb():
    assert S.props("mb 300")["A"] > 0
    labs = S.list_is808("NPB")
    assert any(L.startswith("NPB100") for L in labs)


def test_drift_default_0004():
    dl, rho = IS.drift_allowable({})
    assert abs(dl - 0.004) < 1e-12
    assert rho is False
    assert IS.CLAUSES["storey_drift_limit"]["found"] is True


def test_soft_storey_stiffness_and_ax_false():
    r = IS.storey_stiffness_soft_flags([50.0, 100.0, 100.0])
    assert r["soft_storeys"][0] is True
    assert r["drift_limit_by_storey"][0] == 0.002
    assert r["requires_dynamic_analysis"] is True
    assert r["asce_Ax"]["found"] is False
    assert IS.CLAUSES["soft_storey"]["found"] is True
    assert IS.CLAUSES["soft_storey"]["soft_storey_drift_limit"] == 0.002
    todos = [t for t in IS.TODO if "ax" in t["id"].lower() or "Ax" in t.get("note", "")]
    assert any(t["found"] is False for t in IS.TODO if "ax" in t["id"].lower())


def test_no_cd_ie_amplification():
    drifts = [0.002, 0.003]
    out = IS.design_story_drifts(drifts, {"seis": {"Cd": 5.5, "Ie": 1.0}})
    assert out == drifts


def test_torsional_trigger_15():
    trig = IS.CLAUSES["torsional_irregularity_trigger"]["ratio_trigger"]
    assert abs(trig - 1.5) < 1e-12
    cls = IS.classify_plan_irregularities({"_tir_screen": 1.6}, {"reentrant": False})
    tors = [i for i in cls["items"] if i["type"].startswith("Torsional")][0]
    assert tors["triggered"] is True


def test_metric_units_conversion():
    cfg = {"units": "metric", "story_heights": [3.6], "bay_x": 6.0, "bay_y": 5.0}
    IU.apply_metric_geometry(cfg)  # wave 1 alias → SI mm
    assert abs(cfg["story_heights"][0] - 3600.0) < 1e-6
    assert abs(cfg["heights"][0] - 3600.0) < 1e-6
    assert abs(cfg["SX"] - 6000.0) < 1e-6
    assert abs(cfg["SY"] - 5000.0) < 1e-6
    assert cfg["_units_converted"]["to"] == "mm"
    assert cfg["units"] == "N-mm"
    assert IU.ENGINE_UNITS["force"] == "N"
    assert IU.ENGINE_UNITS["length"] == "mm"

def test_legacy_kip_in_opt_in():
    cfg = {"units": "kip-in", "force_kip_in": True, "metric": True,
           "story_heights": [3.6], "bay_x": 6.0, "bay_y": 5.0}
    IU.apply_metric_geometry(cfg)
    assert abs(cfg["SX"] - 6.0 * IU.M_TO_IN) < 1e-6
    assert cfg["_units_converted"]["to"] == "in"
    assert cfg["units"] == "kip-in"


def test_collection_stem_map():
    assert IC.stem_for_collection("engineering_standards_IS800") == "IS_800_2007"
    assert IC.stem_for_collection("engineering_standards_IS808") == "IS_808_2021"
    assert IC.stem_for_collection("IS875_P3") == "IS_875_Part_3_2015"
    assert IC.stem_for_collection("engineering_standards_IS1893") == "IS_1893_Part_1_2016"
    assert IC.stem_for_collection("engineering_standards_IS1161") == "IS_1161_2014"
    assert IC.normalize_collection("IS808") == "engineering_standards_IS808"
    assert IC.is_india_spec_collection("engineering_standards_IS875_P1")
    assert not IC.is_india_spec_collection("openseespy_documentation")


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print("OK", name)
    print("all passed")
