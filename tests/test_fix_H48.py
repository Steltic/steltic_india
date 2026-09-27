"""H48 (HR-E-09): crane sway on the single bracket frame (default when the roof is not a braced rigid diaphragm) or on
the whole building (cfg['crane']['sway_model'])."""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "steel_engine"))

CRANE = {"capacity_kN": 200.0, "crab_kN": 40.0, "bridge_kN": 180.0, "span_mm": 19500.0, "hook_approach_mm": 1000.0,
         "wheel_base_mm": 3500.0, "gantry_span_mm": 6000.0, "class": "III", "type": "electric",
         "span_axis": "X", "bracket_eccentricity_mm": 0.0, "operation": "pendant", "rail_height_mm": 6000.0}


def _cfg(E, **crane):
    cfg = {"NX": 1, "NY": 1, "SX": 20000.0, "SY": 6000.0, "heights": [6000.0], "base": "fixed",
           "col": "WPB300X300X100.85", "beam": "WPB900X300X291.46", "units": "N-mm", "jurisdiction": "india",
           "D_floor": 0.5, "D_roof": 0.5, "L_floor": 0.0, "Lr": 0.75, "clad": 0.0, "self_weight": False}
    cfg["crane"] = dict(CRANE, bracket_nodes={"L": E.ntag(0, 0, 1), "R": E.ntag(1, 0, 1)}, **crane)
    return cfg


def test_default_single_frame_matches_hand_portal():
    pytest.importorskip("openseespy.opensees")
    import engine3d as E
    import india_loads as IL
    import india_units as IU
    IU.activate_si()
    cfg = _cfg(E)
    assert E.crane_sway_model(cfg)[0] == "single_frame"
    r = E.india_crane_sway(cfg)
    assert r["sway_model"] == "single_frame"
    P = IL.crane_reactions(cfg["crane"])["col_surge_N"]
    A, Ic, _, _ = E.Ipack("WPB300X300X100.85")
    Ib = E.Ipack("WPB900X300X291.46")[1]
    h, L = 6000.0, 20000.0
    k = (Ib / L) / (Ic / h)
    hand = P * h ** 3 * (3 * k + 2) / (12 * E.E * Ic * (6 * k + 1))       # fixed-base portal, load at the eave
    assert r["sway_mm"] == pytest.approx(hand, rel=0.02)
    # building model (declared): the rigid roof shares the surge with the second frame (translation half, plus the
    # twist of the eccentric surge) -> between half and the single-frame value
    rb = E.india_crane_sway(_cfg(E, sway_model="building"))
    assert rb["sway_model"] == "building" and 0.5 * r["sway_mm"] < rb["sway_mm"] < 0.9 * r["sway_mm"]
    # rigid diaphragm + declared roof bracing -> building by default
    assert E.crane_sway_model(dict(cfg, roof_bracing=True))[0] == "building"
    assert E.crane_sway_model(dict(cfg, roof_bracing=True, diaphragm="flexible"))[0] == "single_frame"
