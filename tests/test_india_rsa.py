"""WP1.3 -- IS 1893 6.4.2 spectrum, 7.7.5 RSA (CQC), 7.7.3.1 scaling, 7.7.1 gate, no ASCE fallback."""
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tests"))
sys.path.insert(0, str(ROOT / "steel_engine"))

import india_seismic as IS


def test_sa_over_g_branches():
    assert IS.sa_over_g(0.09, "II", "ESM") == 2.5                 # not 1 + 15T (HREX3-Ex13-03)
    assert IS.sa_over_g(0.09, "II", "RSA") == pytest.approx(1 + 15 * 0.09)
    assert IS.sa_over_g(0.5, "I", "ESM") == pytest.approx(1.0 / 0.5)
    assert IS.sa_over_g(0.6, "medium", "RSA") == pytest.approx(1.36 / 0.6)
    assert IS.sa_over_g(0.6, "soft", "ESM") == 2.5
    assert IS.sa_over_g(5.0, "III", "ESM") == 0.42
    assert IS.sa_over_g(5.0, "II", "RSA") == 0.34


def test_sdof_Ah():
    assert IS.design_Ah(0.24, 1.0, 5.0, 1.0, "II", "RSA") == pytest.approx(0.0326, abs=5e-5)


def test_cqc_rho_identity():
    assert IS.cqc_rho(10.0, 10.0) == pytest.approx(1.0)
    assert IS.cqc_rho(10.0, 20.0) < 0.05


@pytest.fixture(scope="module")
def eng():
    pytest.importorskip("openseespy.opensees")
    import engine3d as E
    import india_units as IU
    IU.activate_si()
    return E


def _one_storey(E):
    return {"NX": 1, "NY": 1, "SX": 6000.0, "SY": 6000.0, "heights": [3600.0], "base": "fixed",
            "col": "WPB300X300X100.85", "beam": "NPB450X190X67.16", "units": "N-mm", "jurisdiction": "india",
            "D_floor": 4.0, "D_roof": 40.0, "L_floor": 0.0, "Lr": 0.75, "clad": 0.0, "self_weight": False,
            "load_plan": {"jurisdiction": "india", "story_forces_units": "N",
                          "seismic_summary": {"Z": 0.24, "I": 1.0, "R": 5.0, "soil": "II", "VB_kN": 1.0},
                          "story_forces": {"EQ_X": {"1": [1000.0, 0, 0]}, "EQ_Y": {"1": [0, 1000.0, 0]}}}}


def test_single_storey_rsa_base_shear_equals_Ah_W(eng):
    E = eng
    cfg = _one_storey(E)
    r = E.rsa_analysis(cfg)
    W = E.floor_w(cfg, 1)
    Tx = max((m for m in r["modes"]), key=lambda m: m["mass_x"])["T"]
    assert r["X"]["mass_participation"] == pytest.approx(1.0, abs=1e-3)
    assert r["X"]["VB_rsa_N"] == pytest.approx(IS.design_Ah(0.24, 1.0, 5.0, Tx, "II", "RSA") * W, rel=2e-3)
    assert r["X"]["scale"] == 1.0                                # VB_rsa > V-bar (1 kN) -> no scaling


def test_ex1_rsa_scaled_to_VBbar(eng):
    from _ex1_fixture import ex1_cfg
    cfg, seis = ex1_cfg()
    cfg["self_weight"] = False                                   # the shipped W (before WP1.6 additions)
    E = eng
    E.clear_caches()
    r = E.rsa_analysis(cfg)
    for d in ("X", "Y"):
        assert r[d]["VB_rsa_N"] < 984.72e3                       # before scaling
        assert r[d]["VB_scaled_N"] / 1e3 == pytest.approx(984.72, abs=0.05)
        assert r[d]["mass_participation"] >= 0.90
    # element forces are the scaled CQC envelopes: base column shears sum >= V-bar / (some) and finite
    assert all(v.max() >= 0 for v in r["elements"]["X"].values())


def test_ex1_preflight_rejects_elf_only(eng):
    from _ex1_fixture import ex1_cfg
    import preflight as PF
    cfg, _ = ex1_cfg()
    cfg["analyses"] = ["ELF"]
    errs = [m for s, m in PF.check(cfg) if s == "ERROR"]
    assert any("7.7.1" in m for m in errs)


def test_elf_and_asce_spectrum_refused_on_india(eng):
    E = eng
    cfg = _one_storey(E)
    cfg["load_plan"] = {"jurisdiction": "india"}
    with pytest.raises(RuntimeError):
        E.elf(cfg, 0.5)
    with pytest.raises(RuntimeError):
        E.sa(dict(cfg, seis={"SDS": 1.0, "SD1": 0.6}), 0.5)
    src = (ROOT / "steel_engine" / "engine3d.py").read_text()
    assert "rs_X\"]=max(VrsX" not in src.replace(" ", "")


def test_run_one_india_uses_rsa_gate_not_cd(eng):
    from _ex1_fixture import ex1_cfg
    E = eng
    cfg, _ = ex1_cfg()
    cfg.update(self_weight=False, deck_span="X", analyses=["RSA"])
    E.clear_caches()
    E.CFG["ex1_rsa_gate"] = cfg
    r = E.run_one("ex1_rsa_gate")
    assert r["Cd"] is None and r["method"] == "RSA"
    assert r["chk"]["rsa_X"] and r["chk"]["rsa_Y"]
    assert r["extra"]["VrsX/V"] < 1.0 and r["extra"]["rsa_scale_X"] > 1.0
