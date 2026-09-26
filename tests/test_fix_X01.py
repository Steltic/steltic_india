"""X01: IS 1893 (Part 1):2016 Table 5(ii) (Amd 2) flexible-floor-diaphragm 3-D dynamic analysis for re-entrant plans,
run in addition to the rigid-diaphragm case and enveloped ('the worst effect considered').

(1) regular plan + very stiff deck reproduces the rigid run (periods, base shear, drift) within 2 %;
(2) hand check of the deck membrane: a long one-storey diaphragm between two braced end frames deflects as a
    shear + chord-bending beam (closed form);
(3) L-plan: the engine sets flexible_diaphragm_run / basis 'engine', the package records both runs and the envelope
    is >= each run;
(4) missing diaphragm_stiffness -> explicit ERROR reason, PARTIAL (never a silent pass); cfg['_flexible_diaphragm_run']
    alone does nothing."""
import json
import os
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tests"))
sys.path.insert(0, str(ROOT / "steel_engine"))

import india_flexible_diaphragm as FD
import india_seismic_gates as G

CORPUS_T5II = ("In a building with re-entrant corners, three-dimensional dynamic analysis method with flexible floor "
               "diaphragm shall be adopted")


def test_quotes_are_corpus_verbatim():
    rel = Path("documents") / "standards" / "IS_1893_Part_1_2016" / "markdown" / "IS_1893_Part_1_2016.search.md"
    here = Path(__file__).resolve()
    roots = [Path(os.environ["INDIA_CORPUS_ROOT"])] if os.environ.get("INDIA_CORPUS_ROOT") else []
    roots += [here.parents[i] / "engineering_rag_india" for i in (2, 3)]
    md = next((r / rel for r in roots if (r / rel).exists()), roots[-1] / rel)
    if not md.exists():
        pytest.skip("corpus checkout not beside the worktree")
    txt = " ".join(md.read_text(encoding="utf-8").split())
    q = FD.T5II_QUOTE.split(": '", 1)[1].rstrip("'")
    assert q in txt and CORPUS_T5II in q
    q764 = FD.Q_7_6_4.split(": '", 1)[1].rstrip("'")
    assert " ".join(q764.split()) in txt.replace("*", "")


def test_stiffness_record_rules():
    rec, err = FD.diaphragm_stiffness({})
    assert rec is None and err.startswith("ERROR") and "diaphragm_stiffness" in err
    rec, err = FD.diaphragm_stiffness({"diaphragm_stiffness": {"type": "metal_deck", "source": "EOR"}})
    assert rec is None and "topping" in err and "Gd_kN_per_m" in err            # bare deck: no default
    rec, err = FD.diaphragm_stiffness({"diaphragm_stiffness": {"type": "rc_slab", "t_mm": 150, "fck_MPa": 25}})
    assert rec is None and "source" in err
    rec, err = FD.diaphragm_stiffness({"diaphragm_stiffness": {"type": "rc_slab", "t_mm": 150, "fck_MPa": 25,
                                                               "source": "EOR"}})
    assert err is None and rec["E_eff_MPa"] == pytest.approx(25000.0)           # IS 456 6.2.3.1: 5000 sqrt(25)
    assert rec["Gt_N_per_mm"] == pytest.approx(25000.0 * 150 / 2.4) and rec["verify"] is True
    assert "IS 456" in rec["basis"]
    rec, err = FD.diaphragm_stiffness({"diaphragm_stiffness": {"type": "metal_deck", "topping_t_mm": 75, "fck_MPa": 25,
                                                               "source": "EOR", "cite": "deck catalogue"}})
    assert err is None and rec["h_mm"] == 75 and rec["Gt_N_per_mm"] == pytest.approx(25000.0 * 75 / 2.4)
    rec, err = FD.diaphragm_stiffness({"diaphragm_stiffness": {"type": "custom", "Gd_kN_per_m": 12000.0,
                                                               "source": "SDI test", "cite": "manufacturer G'"}})
    assert err is None and rec["Gt_N_per_mm"] == 12000.0 and rec["Et_N_per_mm"] == pytest.approx(2.4 * 12000.0)


def test_trigger_ignores_private_key():
    rect = {"NX": 3, "NY": 3, "SX": 6000.0, "SY": 6000.0, "heights": [3500.0], "_flexible_diaphragm_run": True}
    assert FD.trigger(rect)[0] is False
    import engine3d as E
    assert FD.trigger(dict(rect, NX=10, NY=10, plan=E.Lplan))[0] is True
    assert FD.trigger(dict(rect, flexible_diaphragm_analysis=True))[0] is True
    assert FD.trigger(dict(rect, NX=10, NY=10, plan=E.Lplan, flexible_diaphragm_analysis=False))[0] is False
    # the gate still refuses a package that only carries the private key
    an = {"seismic_analysis": {"reentrant_flexible_required": True, "flexible_diaphragm_run": True, "rsa_used_in_demands": True,
                               "scale": {d: {"VB_scaled_kN": 1.0, "VBbar_kN": 1.0, "mass_participation": 0.95} for d in "XY"}}}
    assert any("Table 5(ii)" in m for m in G.analysis_findings({"_flexible_diaphragm_run": True}, an))


def test_merge_records_keeps_larger_abs_per_component():
    rig = {"C1": {frozenset((1, 2)): (-100.0, 50.0, 0.0, 10.0, 0, 0, 0, 0, 20.0, 10.0, 0.0, 5.0, 1.0)}}
    flx = {"C1": {frozenset((1, 2)): (-80.0, -70.0, 3.0, 9.0, 0, 0, 0, 0, -30.0, 9.0, 1.0, 120.0, 0.5)}}
    n_f, n_r = FD.merge_records(rig, flx)
    r = rig["C1"][frozenset((1, 2))]
    assert r[0] == -100.0 and r[1] == -70.0 and r[2] == 3.0 and r[3] == 10.0
    assert r[8] == 20.0                                   # Mmaj_sag_max: the larger SIGNED value
    assert r[11] == 120.0 and n_r == 1


@pytest.fixture(scope="module")
def eng():
    pytest.importorskip("openseespy.opensees")
    import engine3d as E
    import india_units as IU
    IU.activate_si()
    return E


def test_regular_plan_stiff_deck_reproduces_rigid(eng):
    E = eng
    from _ex1_fixture import ex1_cfg_is
    cfg, _ = ex1_cfg_is(design=False)                     # 5 x 4 bays, 5 storeys, rectangular
    cfg["diaphragm_stiffness"] = {"type": "custom", "G_eff_MPa": 1.0e6, "t_mm": 150.0, "source": "test: very stiff deck"}
    assert FD.trigger(cfg)[0] is False                    # regular plan: no automatic run
    E.clear_caches()
    rig = E.rsa_analysis(cfg)
    flx = FD.rsa_flexible(cfg)
    assert flx["deck"][1]["panels"] == 20 and flx["deck"][1]["shells"] == 80
    Tr = [m["T"] for m in rig["modes"][:3]]
    Tf = [m["T"] for m in flx["modes"][:3]]
    for a, b in zip(Tr, Tf):
        assert b == pytest.approx(a, rel=0.02)
    for d in ("X", "Y"):
        assert flx[d]["VB_rsa_N"] == pytest.approx(rig[d]["VB_rsa_N"], rel=0.02)
        assert flx[d]["VB_scaled_N"] == pytest.approx(rig[d]["VB_scaled_N"], rel=1e-6)   # same 7.7.3.1 V-bar_B
        assert flx[d]["mass_participation"] >= 0.90
    # the same element responses (tags shared with the rigid static model): the largest brace axial force
    br = max(abs(v[0]) for t, v in rig["elements"]["X"].items() if len(v) == 1)
    bf = max(abs(v[0]) for t, v in flx["elements"]["X"].items() if len(v) == 1)
    assert bf == pytest.approx(br, rel=0.03)
    # drift of the flexible model with the stiff deck = the rigid india_drift; the deck stays 7.6.4-rigid
    ecc = E.design_eccentricities(cfg)
    dr = E.india_drift(cfg, ecc)
    fd = FD.drift_and_764(cfg, ecc)
    for d in ("X", "Y"):
        for a, b in zip(dr[d]["drift"], fd["drift"][d]):
            assert b == pytest.approx(a, rel=0.02)
        assert all(r["ratio"] < 0.05 and r["classification"] == "rigid" for r in fd["d764"][d])


def test_membrane_hand_check_long_diaphragm(eng):
    """One storey, 4 x 1 bays of 6 m (L 24 m, B 6 m), pinned base and pinned beams, stiff X-braces in the two end
    frames only.  A uniform lateral load along Y makes the deck a simply supported beam between the end frames:
    delta_mid = 5 w L^4 / (384 EI) + w L^2 / (8 Gd B), EI = Es A_chord 2 (B/2)^2 + Et B^3 / 12 (closed form)."""
    E = eng
    import openseespy.opensees as ops
    import sections as S
    cfg = {"NX": 4, "NY": 1, "SX": 6000.0, "SY": 6000.0, "heights": [4000.0], "base": "pinned",
           "col": "WPB300X300X100.85", "beam": "NPB450X190X67.16", "brace": "WPB300X300X100.85",
           "braces": lambda k, NX, NY: [("Y", 0, 0), ("Y", NX, 0)], "releases": lambda i, j, k, d: ("both", "none"),
           "units": "N-mm", "jurisdiction": "india", "D_floor": 4.0, "D_roof": 4.0, "L_floor": 0.0, "Lr": 0.0,
           "clad": 0.0, "self_weight": False,
           "diaphragm_stiffness": {"type": "custom", "Gd_kN_per_m": 10000.0, "t_mm": 100.0, "source": "hand check"}}
    m = FD.build_flexible(cfg, "Linear", 2)
    assert m["deck"][1]["panels"] == 4
    F = 1.0e5
    loads = FD._lateral_loads(FD._level_fields(m)[1], (0.0, F), 0.0)
    ops.timeSeries("Linear", 1); ops.pattern("Plain", 1, 1)
    for t, (fx, fy) in loads.items():
        ops.load(t, fx, fy, 0.0, 0.0, 0.0, 0.0)
    ops.constraints("Transformation"); ops.numberer("RCM"); ops.system("UmfPack")
    ops.test("NormDispIncr", 1e-9, 10); ops.algorithm("Linear"); ops.integrator("LoadControl", 1.0)
    ops.analysis("Static")
    assert ops.analyze(1) == 0
    uy = lambda i: 0.5 * (ops.nodeDisp(E.ntag(i, 0, 1), 2) + ops.nodeDisp(E.ntag(i, 1, 1), 2))
    rel = uy(2) - 0.5 * (uy(0) + uy(4))
    L, B, w = 24000.0, 6000.0, F / 24000.0
    Ab = S.props("NPB450X190X67.16")["A"]
    Et = 2.4 * 10000.0
    EI = E.E * Ab * 2 * (B / 2) ** 2 + Et * B ** 3 / 12.0
    hand = 5 * w * L ** 4 / (384 * EI) + w * L ** 2 / (8 * 10000.0 * B)
    assert rel == pytest.approx(hand, rel=0.06), (rel, hand)
    assert rel > 1.2 * 0.5 * (uy(0) + uy(4))              # 7.6.4: this deck is flexible


def _lplan_cfg(stiffness=True):
    from _ex1_fixture import ex1_cfg, apply_wave2_design
    cfg, _ = ex1_cfg(upgrade=True)
    cfg["plan"] = lambda k, NX, NY: {(i, j) for i in range(NX + 1) for j in range(NY + 1) if not (i >= 4 and j >= 3)}
    cfg = apply_wave2_design(cfg, embedment={"capacity_N": 900e3, "cite": "EOR anchorage design (declared input)"})
    if stiffness:
        cfg["diaphragm_stiffness"] = {"type": "metal_deck", "topping_t_mm": 75.0, "fck_MPa": 25.0,
                                      "source": "EOR: composite deck, 75 mm M25 topping above the ribs",
                                      "cite": "EOR deck schedule; Ec per IS 456 6.2.3.1"}
    return cfg


def _design(tmp_path_factory, name, cfg):
    import pipeline as P
    from _ex1_fixture import stage_ex1_rag
    jobs = tmp_path_factory.mktemp("jobsX01")
    os.environ["STELTIC_TEST_JOBS"] = str(jobs)
    os.environ["STEEL_BUILDER_JOBS"] = str(jobs)
    stage_ex1_rag(os.path.join(str(jobs), name))
    out = P.design_and_report(name, cfg, do_report=False)
    root = out["root"]
    pkg = json.load(open(os.path.join(root, "design", "calc_package.json")))
    forces = json.load(open(os.path.join(root, "design", "member_combo_forces.json")))
    return pkg, forces


@pytest.fixture(scope="module")
def lplan_job(tmp_path_factory, eng):
    eng.clear_caches()
    return _design(tmp_path_factory, "IN_X01_Lplan", _lplan_cfg(True))


def test_lplan_engine_run_sets_the_flag(lplan_job):
    pkg, _ = lplan_job
    sa = pkg["seismic_analysis"]
    assert pkg["irregularity"]["reentrant"]["irregular"] is True
    assert sa["reentrant_flexible_required"] is True
    assert sa["flexible_diaphragm_run"] is True and sa["flexible_diaphragm_basis"] == "engine"
    fd = sa["flexible_diaphragm"]
    assert fd["status"] == "run" and "Table 5(ii)" in fd["clause"] and CORPUS_T5II in fd["cite"]
    assert fd["deck"]["1"]["panels"] == 16                 # 20 bays less the 2 x 2 notch
    assert len(fd["periods_s"]) >= 3 and len(fd["periods_rigid_s"]) >= 3
    for d in ("X", "Y"):
        b = fd["base_shear"][d]
        assert b["VB_scaled_kN"] == pytest.approx(b["VBbar_kN"], rel=1e-3)
        assert b["rigid_VB_rsa_kN"] > 0 and b["mass_participation"] >= 0.9
    assert all(c["ok"] is True for c in fd["checks"])
    # IN-MIN-SENSE: the 7.7.5.2 / 7.7.3.1 rows are minimum-type (value >= limit, dc = limit / value)
    for c in fd["checks"]:
        if c["name"].startswith(("7.7.5.2", "7.7.3.1")):
            assert c["sense"] == ">=" and abs(c["dc"] - c["limit"] / c["value"]) <= 1e-3 * c["dc"] + 1e-4
    assert not [r for r in pkg["design_status"]["reasons"] if "Table 5(ii)" in r or "flexible" in r]
    assert pkg["diaphragm_7_6_4"]["flexible_run"]["levels"]["X"][0]["limit"] == 1.2


def test_lplan_envelope_not_below_either_run(lplan_job):
    pkg, forces = lplan_job
    env = pkg["seismic_analysis"]["flexible_diaphragm"]["envelope"]
    groups = env["ratio_flexible_over_rigid_by_group"]
    eq = {c["label"] for c in pkg["load_combinations"] if c.get("lateral_kind") == "EQ" and c.get("rsa")}
    assert env["n_cases"] == len(eq) > 0                  # every RSA combination (SLS rows use static forces)
    by_role = {}
    for t, e in forces["elements"].items():
        for lab, rec in e["records"].items():
            if lab in eq:
                g = by_role.setdefault(e["role"], [0.0] * 5)
                for q, f in enumerate((0, 11, 12, 1, 2)):          # N, N_LAT, V_LAT, Mmaj, Mmin
                    g[q] = max(g[q], abs(rec[f]) if f < len(rec) else 0.0)
    for role, rr in groups.items():
        for q, f in enumerate(("N", "N_LAT", "V_LAT", "Mmaj", "Mmin")):
            assert by_role[role][q] >= max(rr[f]["rigid"], rr[f]["flexible"]) * (1 - 1e-4) - 1.0, (role, f)
    # the flexible deck model loads the floor beams axially (collector / chord action of the deck)
    assert groups["floor"]["N_LAT"]["flexible"] > 1000.0
    for row in pkg["drift_table"]:
        assert row["value"] == pytest.approx(max(row["drift_rigid"], row["drift_flexible"]), abs=1e-6)


@pytest.fixture(scope="module")
def lplan_nostiff_job(tmp_path_factory, eng):
    eng.clear_caches()
    cfg = _lplan_cfg(False)
    cfg["_flexible_diaphragm_run"] = True                  # the private key is not evidence
    return _design(tmp_path_factory, "IN_X01_Lplan_nostiff", cfg)


def test_lplan_without_stiffness_is_partial_with_reason(lplan_nostiff_job):
    pkg, _ = lplan_nostiff_job
    sa = pkg["seismic_analysis"]
    assert sa["flexible_diaphragm_run"] is False and "flexible_diaphragm_basis" not in sa
    assert sa["flexible_diaphragm"]["status"] == "not run"
    assert "diaphragm_stiffness" in sa["flexible_diaphragm_engine_error"]
    assert pkg["design_status"]["status"] == "partial"
    msg = [r for r in pkg["design_status"]["reasons"] if "Table 5(ii)" in r]
    assert msg and "cfg['diaphragm_stiffness']" in msg[0] and "ERROR" in msg[0]
    assert "is ignored" in sa.get("flexible_diaphragm_note", "")


def test_report_shows_both_runs(lplan_job, lplan_nostiff_job):
    import report_india as RI
    pkg, _ = lplan_job
    h = RI._seismic_table({"load_plan": {}, "heights": [3600.0] * 5}, pkg, {})
    assert "Table 5(ii)" in h and "V_B RSA flexible" in h and "T rigid" in h and "flexible / rigid" in h
    h2 = RI._seismic_table({"load_plan": {}, "heights": [3600.0] * 5}, lplan_nostiff_job[0], {})
    assert "Not run" in h2 and "diaphragm_stiffness" in h2
