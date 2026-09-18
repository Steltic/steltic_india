"""SI wave 2: display helpers + report unit context (no OpenSees required)."""
import os, sys
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "steel_engine"))

import india_units as IU


def test_display_scale_si():
    IU.activate_si()
    sc = IU.display_scale({"units": "N-mm"})
    assert sc["si"] is True
    assert sc["force_lbl"] == "kN"
    assert sc["moment_lbl"] == "kN·m"
    assert sc["stress_lbl"] == "MPa"
    assert abs(sc["force_div"] - 1000.0) < 1e-9
    assert abs(sc["moment_div"] - 1e6) < 1e-6


def test_display_scale_legacy_kip():
    sc = IU.display_scale({"units": "kip-in", "force_kip_in": True})
    assert sc["si"] is False
    assert sc["force_lbl"] == "kip"
    assert sc["stress_lbl"] == "ksi"
    assert abs(sc["moment_div"] - 12.0) < 1e-9


def test_demand_field_names_si():
    fn = IU.demand_field_names({"units": "metric"})
    assert fn["P_comp"] == "P_comp_N"
    assert fn["Mx_display"] == "Mx_kNm"
    assert fn["V"] == "V_N"


def test_fmt_force_moment():
    IU.activate_si()
    assert "kN" in IU.fmt_force(5000.0, {"units": "N-mm"})
    assert "kN·m" in IU.fmt_moment(2.0e6, {"units": "N-mm"})


def test_report_helpers_import():
    import pytest
    pytest.importorskip("matplotlib")
    import report as R
    R._set_report_units({"units": "N-mm", "heights": [3600], "SX": 6000, "SY": 5000})
    assert R._sc()["si"] is True
    assert R._F(1000.0) == 1.0
    assert R._M(1.0e6) == 1.0
    assert R._ul("F") == "kN"
    assert R._ul("S") == "MPa"
    banner = R._si_unit_banner({"units": "N-mm"})
    assert "wave 2" in banner.lower() or "N-mm-sec" in banner
    assert "not kip" in banner.lower() or "kN" in banner
