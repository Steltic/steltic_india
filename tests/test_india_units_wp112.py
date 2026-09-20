"""WP1.12 -- units contract: explicit units, kip laterals / psf gravity refused, no *_kip aliases."""
import copy

import pytest

from _ex1_fixture import ex1_cfg_is

import india_units as U
import preflight as PF


def _errors(cfg):
    return [m for s, m in PF.check(cfg) if s == "ERROR"]


def test_india_unset_units_not_guessed():
    cfg = {"jurisdiction": "india", "heights": [3.6, 3.6], "SX": 6.0}
    with pytest.raises(U.UnitsError):
        U.is_si(cfg)
    with pytest.raises(U.UnitsError):
        U.apply_si_geometry(dict(cfg))
    # legacy USA archetype (no India marker) keeps the old behaviour
    assert U.is_si({"heights": [156.0]}) is False


def test_india_units_missing_is_preflight_error():
    cfg, _ = ex1_cfg_is()
    cfg.pop("units", None)
    assert any("units" in m for m in _errors(cfg))


def test_kip_laterals_refused():
    cfg, _ = ex1_cfg_is()
    cfg["load_plan"]["story_forces_units"] = "kip"
    assert any("story_forces_units" in m for m in _errors(cfg))


def test_psf_gravity_refused():
    cfg, _ = ex1_cfg_is()
    cfg["D_floor"] = 90.0                   # 90 psf typed into the kN/m2 field
    assert any("> 25" in m for m in _errors(cfg))


def test_ex1_is_clean():
    cfg, _ = ex1_cfg_is()
    assert _errors(cfg) == []


def test_metre_xcoords_converted_or_flagged():
    cfg = {"units": "m", "jurisdiction": "india", "heights": [3.6], "SX": 6.0, "SY": 6.0,
           "xcoords": [0.0, 6.0, 12.0]}
    U.apply_si_geometry(cfg)
    assert cfg["xcoords"] == [0.0, 6000.0, 12000.0]
    cfg2, _ = ex1_cfg_is()
    cfg2["xcoords"] = [0.0, 6.0, 12.0]
    assert any("xcoords" in m for m in _errors(cfg2))


def test_plf_helper_renamed():
    assert not hasattr(U, "kn_per_m_to_plf")
    assert U.kn_per_m_to_kip_per_ft(14.5939) == pytest.approx(1.0, rel=1e-3)


def test_si_conversion_record_has_no_imperial_factor():
    """WP6: the cfg['_units_converted'] record (written into design/cfg_snapshot.json) carries SI factors only --
    no 'ksi' / 'in' legacy factor, so the package residue grep (ASCE|AISC|...|ksi|kip|...) is clean."""
    import json, re
    import india_units as IU
    cfg = {"units": "m", "jurisdiction": "india", "heights": [3.6], "bay_x": 6.0, "bay_y": 6.0, "NX": 1, "NY": 1}
    IU.apply_si_geometry(cfg)
    rec = cfg["_units_converted"]
    assert rec["to"] == "mm" and rec["factors"]["m_to_mm"] == 1000.0
    assert not re.search(r"ksi|kip|psf|\bin\b", json.dumps(rec))
