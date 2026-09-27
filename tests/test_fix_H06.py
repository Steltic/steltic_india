"""H06 (E2, HR-E-17): mixed systems -- the EBF link chain runs whenever EBF is any component; per-direction R
(cfg R_x / R_y) is validated against Table 9 per direction and used by ESM and RSA."""
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tests"))
sys.path.insert(0, str(ROOT / "steel_engine"))

import india_is800_s12 as S12
import india_seismic as IS
import india_seismic_gates as G
from test_wp6_ebf_links import _ebf_model_data


def test_ebf_links_checked_when_not_primary():
    res = S12.section12_checks("SMF+EBF", _ebf_model_data(), {"zone": "III", "I": 1.2, "height_m": 32.1,
                                                              "brace_config": "chevron"})
    ids = {c["id"] for c in res["checks"]}
    assert {"11.2_link_design_shear", "12.3.2.1_link_shear", "12.3.2.2_link_overstrength"} <= ids
    assert "IS 18168" in res["cite"]


def test_resolve_system_R_per_direction():
    base = {"system": "SMRF + SCBF"}
    r = G.resolve_system_R(base)
    assert r["R_table9"] == 4.5 and r["R_x"] == 4.5 and r["R_y"] == 4.5 and not r["errors"]
    r = G.resolve_system_R(dict(base, system_x="SMRF", system_y="SCBF", R_x=5.0, R_y=4.5))
    assert (r["R_x"], r["R_y"]) == (5.0, 4.5) and not r["errors"]
    # R_y = 5.0 for the braced direction exceeds Table 9 (ii)(b) 4.5 -> refused, Table 9 value used
    r = G.resolve_system_R(dict(base, system_x="SMRF", system_y="SCBF", R_x=5.0, R_y=5.0))
    assert r["R_y"] == 4.5 and any("R_y" in e for e in r["errors"])
    assert any(s == "ERROR" and "R_y" in m for s, m in G.validate_R(dict(base, R=4.5, system_x="SMRF", system_y="SCBF",
                                                                          R_x=5.0, R_y=5.0)))
    # without system_x the X value is checked against every component (min 4.5)
    r = G.resolve_system_R(dict(base, R_x=5.0))
    assert r["R_x"] == 4.5 and r["errors"]


def test_esm_summary_per_direction_R():
    out = IS.esm_summary([1000e3, 1000e3], [4000.0, 4000.0], 0.24, 1.0, {"X": 5.0, "Y": 4.5}, "II", "IV", 0.3)
    ss = out["seismic_summary"]
    assert ss["Ah_x"] == pytest.approx(0.12 / 5.0 * 2.5) and ss["Ah_y"] == pytest.approx(0.12 / 4.5 * 2.5, abs=1e-6)
    assert ss["R"] == 4.5 and ss["R_x"] == 5.0


def test_engine_params_and_rsa_use_per_direction_R():
    pytest.importorskip("openseespy.opensees")
    import engine3d as E
    from _ex1_fixture import ex1_cfg_is
    cfg, _ = ex1_cfg_is()
    cfg.update(system="SMRF + SCBF", system_x="SMRF", system_y="SCBF", R_x=5.0, R_y=4.5)
    prm = E.india_seismic_params(cfg)
    assert (prm["R_x"], prm["R_y"]) == (5.0, 4.5)
    E.clear_caches()
    r = E.rsa_analysis(cfg)
    m1 = r["modes"][0]
    assert m1["Ak_x"] / m1["Ak_y"] == pytest.approx(4.5 / 5.0)
    assert r["X"]["R"] == 5.0 and r["Y"]["R"] == 4.5
    E.clear_caches()
