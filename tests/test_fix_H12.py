"""H12 (HR-A-03, HR-B-09, HR-C-12), ruling R10: the IS 875-3 10.3 across-wind gate passes only with an evaluated
result -- found:true and a numeric Mc_kNm, or an EOR record {value, source, cite}."""
import pytest

from _ex1_fixture import ex1_cfg_is


@pytest.mark.parametrize("aw,ok", [
    (None, False),
    ({"found": False, "result": None}, False),
    ({"method": "10.3", "result": "n/a", "cite": "IS 875-3 10.3"}, False),
    ({"found": True, "Mc_kNm": "TBD"}, False),
    ({"found": True, "Mc_kNm": 1250.0, "cite": "IS 875-3 10.3"}, True),
    ({"eor": {"value": 1250.0, "source": "", "cite": "wind tunnel"}}, False),
    ({"eor": {"value": 1250.0, "source": "EOR calc 7", "cite": "IS 875-3 10.3 Fig 10"}}, True),
])
def test_across_wind_record(aw, ok):
    import engine3d as E
    assert E.across_wind_evaluated(aw)[0] is ok


def test_gate_partial_without_evaluated_across_wind():
    import engine3d as E
    cfg, _ = ex1_cfg_is()
    ws = cfg["load_plan"]["wind_summary"]
    ws["gust_factor"] = {"G": 2.4, "VB_x_kN": 1.0, "VB_y_kN": 1.0}
    ws["across_wind"] = {"found": False, "result": None}
    ok, why, req = E.india_dynamic_wind_gate(cfg, 0.8)                 # f1 < 1 Hz -> dynamic wind required
    assert req and not ok and any("R10" in w for w in why)
    ws["across_wind"] = {"found": True, "Mc_kNm": 900.0, "cite": "IS 875-3 10.3"}
    assert E.india_dynamic_wind_gate(cfg, 0.8)[0]
