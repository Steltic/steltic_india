"""H11 (HR-E-07, HR-E-08, NEW-7): IS 875 (Part 5) 8.1 Note 1 -- snow replaces the roof imposed load in the
lateral and member-wind combinations when snow > Lr; the Table 6 deflection screen uses max(Lr, snow) on roofs
and the per-level imposed load on floors."""
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "steel_engine"))
sys.path.insert(0, os.path.dirname(__file__))
from _ex1_fixture import ex1_cfg_is  # noqa: E402


def _combos(cfg):
    import india_combos as IC
    return IC.expand_combinations(cfg["load_plan"], cfg)


def test_lateral_rows_carry_snow_when_snow_exceeds_lr():
    cfg, _ = ex1_cfg_is()
    cfg["Lr"], cfg["snow"] = 0.67, 1.09
    cs = _combos(cfg)
    lat = [c for c in cs if c.get("lateral_kind") in ("W", "EQ") and not c.get("service")
           and c["family"].startswith("T4 DL+LL+") and c["fL"] == 1.2 and "ELZ" not in c["family"]]
    assert lat
    for c in lat:
        assert c["fS"] == pytest.approx(1.2) and c["fLr"] == 0.0, c["label"]
        assert "SL" in c["label"] and "8.1 Note 1" in c["cite"]
    # snow below Lr: the roof imposed load stays
    cfg["snow"] = 0.5
    for c in _combos(cfg):
        if c.get("lateral_kind") == "W" and c["fL"] == 1.2 and not c.get("service"):
            assert c["fLr"] == pytest.approx(1.2) and not c.get("fS")


def test_member_wind_rows_carry_snow():
    import india_wind_tables as W
    cfg, _ = ex1_cfg_is()
    cfg["Lr"], cfg["snow"] = 0.75, 1.5
    r = W.lowrise_member_wind(1.0, 18.0, 24.0, 36.0, 10.0, 0.03)
    cfg["load_plan"]["member_wind"] = {"patterns": [dict(r["patterns"][0], wind_axis="X")]}
    mw = [c for c in _combos(cfg) if "member_wind" in c.get("tags", [])]
    withL = [c for c in mw if c["fL"]]
    assert withL and all(c["fS"] == c["fL"] and c["fLr"] == 0.0 for c in withL)
    assert all(not c.get("fS") for c in mw if not c["fL"])


def test_deflection_roof_uses_snow_and_levels_use_L_by_level():
    import engine3d as E
    cfg, _ = ex1_cfg_is()
    cfg["Lr"], cfg["snow"] = 0.0, 1.5
    worst, n, rows = E.beam_deflection_si(cfg)
    roof = [r for r in rows if r["roof"]]
    assert roof, "a roof with Lr = 0 but snow must still be checked"
    assert max(r["w_LL_N_per_mm"] for r in roof) == pytest.approx(1.5 * cfg["SX"] / 1000.0, rel=1e-6)
    cfg["L_by_level"] = {2: 7.5}
    _, _, rows2 = E.beam_deflection_si(cfg)
    fl = [r for r in rows2 if not r["roof"]]
    assert max(r["w_LL_N_per_mm"] for r in fl) == pytest.approx(
        (7.5 + cfg["partition_load_kNm2"]) * cfg["SX"] / 1000.0, rel=1e-6)


def test_vertical_eq_rows_keep_roof_imposed():
    import india_combos as IC
    cfg, _ = ex1_cfg_is()
    plan = cfg["load_plan"]
    rows = [c for c in IC.expand_combinations(plan, cfg, method="ESM") if "ELZ leading" in c["family"]]
    if not rows:
        pytest.skip("vertical earthquake not required for this fixture")
    assert all(c["fLr"] == c["fL"] for c in rows)
