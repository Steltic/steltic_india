"""H39 (HR-B-19, HR-C-15): EBF links get their own role / member and connection group ('link'), are excluded from
the beam-to-column shear demand, rigid EBF beam-column joints get a moment-connection row, and
engine3d.add_link() builds the link as an ElasticTimoshenkoBeam."""
import inspect
import os
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "steel_engine"))

import design_pipeline as DP


def test_link_tags_from_info_or_cfg():
    assert DP.ebf_link_tags({}, {"links": [{"tag": 7}, {"tag": "9"}]}) == {7, 9}
    assert DP.ebf_link_tags({"ebf_links": [{"tag": 3}]}, {}) == {3}
    assert DP.ebf_link_tags({}, {}) == set()


def test_both_role_functions_know_links():
    for fn in (DP.design, DP.design_india):
        src = inspect.getsource(fn)
        assert "ebf_link_tags(cfg, info0)" in src and "return \"link\"" in src
        assert "_role(reg[t][0], reg[t][2], reg[t][3], t)" in src
    src = inspect.getsource(DP.design_india)
    assert 'kind == "beam" and role == "link"' in src                    # own connection group, no beam shear row
    assert "EBF rigid beam-column moment connection" in src               # 12.3.4.4 / 5.5(d) row


def test_add_link_timoshenko_shear_deformation():
    import engine3d as E
    import openseespy.opensees as ops
    import sections as S
    prev = E._UNIT_SYSTEM
    E.activate_si_units()
    sec = "WPB300X300X117.03"
    ops.wipe()
    ops.model("basic", "-ndm", 3, "-ndf", 6)
    ops.node(1, 0.0, 0.0, 0.0)
    ops.node(2, 900.0, 0.0, 0.0)
    ops.fix(1, 1, 1, 1, 1, 1, 1)
    E.add_link(10, 1, 2, sec)
    assert ops.getEleTags() == [10]
    ops.timeSeries("Linear", 1)
    ops.pattern("Plain", 1, 1)
    P = 100e3
    ops.load(2, 0.0, 0.0, -P, 0.0, 0.0, 0.0)
    ops.system("BandGeneral"); ops.numberer("Plain"); ops.constraints("Plain"); ops.integrator("LoadControl", 1.0)
    ops.algorithm("Linear"); ops.analysis("Static"); ops.analyze(1)
    d = -ops.nodeDisp(2, 3)
    A, Ix, Iy, J = E.Ipack(sec)
    p = S.props(sec)
    Av = (p["d"] - 2 * p["tf"]) * p["tw"]
    flex = P * 900.0 ** 3 / (3 * E.E * Ix)
    shear = P * 900.0 / (E.Gmod * Av)
    ops.wipe()
    if prev != "N-mm":
        E.activate_kip_in_units()
    assert d == pytest.approx(flex + shear, rel=0.02) and d > flex * 1.05
