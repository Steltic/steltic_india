"""H42 (L-05): esm_from_model / seismic_weights / build switch the engine to SI automatically for an N-mm / metre
cfg or an India job; unknown section labels get an India-worded error; US kip-in jobs are untouched."""
import copy
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "steel_engine"))
sys.path.insert(0, os.path.dirname(__file__))
from _ex1_fixture import ex1_cfg_is  # noqa: E402


@pytest.fixture
def eng():
    import engine3d as E
    was = E.unit_system()
    yield E
    (E.activate_si_units if was == "N-mm" else E.activate_kip_in_units)()


def test_seismic_weights_and_esm_switch_to_si(eng):
    cfg, _ = ex1_cfg_is()
    eng.activate_si_units()
    W_si = sum(eng.seismic_weights(copy.deepcopy(cfg))[0])
    eng.activate_kip_in_units()                                   # a fresh interpreter starts in kip-in
    c2 = copy.deepcopy(cfg)
    assert str(c2["brace"]).startswith("WPB")
    W = sum(eng.seismic_weights(c2)[0])
    assert eng.unit_system() == "N-mm" and W == pytest.approx(W_si, rel=1e-9)
    eng.activate_kip_in_units()
    ss = cfg["load_plan"]["seismic_summary"]
    r = eng.esm_from_model(copy.deepcopy(cfg), {"X": ss["Ta_x_s"], "Y": ss["Ta_y_s"]}, soil="II")
    assert eng.unit_system() == "N-mm"
    assert r["seismic_summary"]["W_kN"] == pytest.approx(W_si / 1000.0, rel=1e-6)


def test_us_kip_in_cfg_untouched(eng):
    eng.activate_kip_in_units()
    eng.ensure_units({"heights": [150.0], "SX": 360.0, "units": "kip-in"})
    eng.ensure_units({"heights": [150.0], "SX": 360.0})
    assert eng.unit_system() == "kip-in"


def test_india_worded_unknown_section(eng):
    eng.activate_kip_in_units()
    with pytest.raises(KeyError, match="IS section label .*IS 808 / IS 1161"):
        eng.HSS["WPB999X999X1"]
    with pytest.raises(KeyError, match="AISC HSS"):
        eng.HSS["HSS99X99X9"]
    eng.activate_si_units()
    with pytest.raises(KeyError, match="IS section label"):
        eng.Ipack("MB999")
