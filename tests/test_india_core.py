"""HR-CORE acceptance: the spec section 4.2 hand values in the core scope (loads, combinations, seismic,
units, report) and an Ex1 end-to-end smoke through pipeline.design_and_report (ESM story forces +
RSA demands).  Assertions that depend on HR-MEMBERS capacity inputs are xfail with the reason."""
import json
import os
import re

import pytest

from _ex1_fixture import ex1_cfg, ex1_cfg_is, stage_ex1_rag

import engine3d as E
import india_seismic as IS
import india_seismic_gates as G
import static_model as SM


# ----------------------------------------------------------------------------------- hand values
def _sum_rx(cfg, label):
    import india_loads as IL
    import openseespy.opensees as ops
    plan = cfg["load_plan"]
    combo = next(c for c in plan["combinations"] if c["label"] == label)
    case = IL.case_from_combination(combo, plan)
    model = SM.build_static(cfg, "PDelta", 2)
    ops.timeSeries("Linear", 1); ops.pattern("Plain", 1, 1)
    SM.apply_lateral(case[4]); SM._solve(); ops.reactions()
    return -sum(ops.nodeReaction(E.ntag(i, j, 0), 1) for (i, j) in model["present"][0]) / 1000.0


def test_ex1_base_shear_with_load_factor():
    cfg, seis = ex1_cfg()
    assert _sum_rx(cfg, "1.5DL+1.5EQ_X") == pytest.approx(1477.1, abs=0.1)
    assert _sum_rx(cfg, "1.2DL+1.2LL+1.2EQ_X") == pytest.approx(1181.7, abs=0.1)


def test_si_one_way_beam():
    cfg = dict(units="N-mm", jurisdiction="india", heights=[3000.0, 3000.0], SX=6000.0, SY=6000.0,
               D_floor=8.25, L_floor=0.0, D_roof=8.25, Lr=0.0, NX=1, NY=1)
    M, V = SM.one_way_gravity(cfg, dict(k=1, L=6000.0, dir="X", _A=0.0), 1.0, 0.0, 0.0)
    assert M / 1e6 == pytest.approx(222.75, rel=1e-9)
    assert V / 1e3 == pytest.approx(148.5, rel=1e-9)


def test_rsa_sdof_Ah_and_esm_plateau():
    assert IS.design_Ah(0.24, 1.0, 5.0, 1.0, "II", "RSA") == pytest.approx(0.0326, abs=5e-5)
    assert IS.sa_over_g(0.09, "II", "ESM") == 2.5                    # not 1 + 15 T
    assert IS.sa_over_g(0.09, "II", "RSA") == pytest.approx(1 + 15 * 0.09)


def test_importance_resolver():
    assert IS.importance_factor({"use": "office", "persons": 300})["I"] == 1.2
    assert IS.importance_factor({"use": "warehouse", "food_storage": True})["I"] == 1.5


def test_system_zone_findings_examples():
    from pathlib import Path
    fx = json.load(open(Path(__file__).parent / "fixtures" / "zone_system_cfgs.json"))
    err = lambda c: [m for s, m in G.system_zone_findings(c) if s == "ERROR"]
    assert err(fx["Ex3"]) and err(fx["Ex15"])
    assert not err(fx["Ex5"])


def test_ex1_live_load_deflection():
    cfg, _ = ex1_cfg()
    worst, n, rows = E.beam_deflection_si(cfg)
    floor = next(r for r in rows if not r["roof"])
    assert n > 0
    assert floor["delta_mm"] == pytest.approx(4.26, abs=0.05)
    assert 0.2 <= floor["ratio"] <= 0.26


# ------------------------------------------------------------------------------ Ex1 end to end
@pytest.fixture(scope="module")
def ex1_job(tmp_path_factory):
    import pipeline as P
    jobs = tmp_path_factory.mktemp("jobs")
    os.environ["STELTIC_TEST_JOBS"] = str(jobs)
    os.environ["STEEL_BUILDER_JOBS"] = str(jobs)
    cfg, _ = ex1_cfg_is()
    stage_ex1_rag(os.path.join(str(jobs), "IN_Ex1_core"))              # H30: stored rag/ hits
    out = P.design_and_report("IN_Ex1_core", cfg, do_report=True)
    root = out.get("root")
    pkg = json.load(open(os.path.join(root, "design", "calc_package.json")))
    return out, root, pkg


def test_ex1_pipeline_runs_unblocked(ex1_job):
    out, root, pkg = ex1_job
    assert not out.get("blocked"), out.get("error")
    assert pkg["unit_system"] == "N-mm"
    assert pkg["design_status"]["status"] in ("partial", "complete")
    assert all(pkg["gates"].values()), pkg["gates"]


def test_ex1_generated_combinations_and_rsa(ex1_job):
    _, _, pkg = ex1_job
    labels = [c["label"] for c in pkg["load_combinations"]]
    assert "1.5DL+1.5LL" in labels
    assert any("[ea]" in l for l in labels) and any("[col]" in l for l in labels)
    assert any(l.startswith("SLS:") for l in labels)
    sa = pkg["seismic_analysis"]
    assert sa["method"] == "RSA" and sa["rsa_used_in_demands"]
    for d in ("X", "Y"):
        assert sa["scale"][d]["VB_scaled_kN"] == pytest.approx(sa["scale"][d]["VBbar_kN"], rel=0.01)
        assert sa["scale"][d]["mass_participation"] >= 0.9


def test_ex1_demands(ex1_job):
    _, _, pkg = ex1_job
    floor = next(m for m in pkg["members"] if m["inputs"]["role"] == "floor")
    assert floor["inputs"]["V_N"] / 1e3 >= 148.0                     # one-way girder shear (WP2.1)
    assert pkg["collectors"]["applied_to_member_checks"]
    assert floor["inputs"]["P_comp_N"] > 0                           # collector / chord axial (WP2.6)
    assert all(r["ok"] for r in pkg["drift_table"])
    assert pkg["seismic_calc"]["W_engine_kN"] == pytest.approx(pkg["seismic_calc"]["W_design_kN"], rel=0.02)


def test_ex1_report_is_india_only(ex1_job):
    _, root, pkg = ex1_job
    from india_contract_residue import residue_hits
    html = open(os.path.join(root, "report.html"), encoding="utf-8").read()
    assert residue_hits(html) == []
    for must in ("IS 1893", "IS 800", "kN", "Chapter 13", "Design status"):
        assert must in html
    assert not re.search(r"\bpsf\b|\bkips?\b|Risk Category|\bSDC\b", re.sub(r"<[^>]+>", " ", html))


EOR_EMBEDMENT = {"capacity_N": 900e3, "cite": "EOR anchorage design: IS 456:2000 cone / bond pull-out of the M48 "
                                            "anchors by the foundation engineer (outside the corpus; declared input)"}


@pytest.fixture(scope="module")
def ex1_complete_job(tmp_path_factory):
    """Ex1 with every wave-2 input declared, incl. the EOR anchorage embedment -> must reach COMPLETE."""
    import pipeline as P
    jobs = tmp_path_factory.mktemp("jobs2")
    os.environ["STELTIC_TEST_JOBS"] = str(jobs)
    os.environ["STEEL_BUILDER_JOBS"] = str(jobs)
    cfg, _ = ex1_cfg_is(design=True, embedment=EOR_EMBEDMENT)
    stage_ex1_rag(os.path.join(str(jobs), "IN_Ex1_complete"))              # H30: stored rag/ hits
    out = P.design_and_report("IN_Ex1_complete", cfg, do_report=True)
    root = out.get("root")
    pkg = json.load(open(os.path.join(root, "design", "calc_package.json")))
    return out, root, pkg


def test_ex1_all_member_dc_pass(ex1_job):
    """Every member has an IS 800 record with a numeric D/C <= 1 (LLT declared, plastic SCBF columns)."""
    _, _, pkg = ex1_job
    assert all(isinstance(m["DC"], (int, float)) and m["DC"] <= 1.0 for m in pkg["members"]), \
        [(m["id"], m["DC"]) for m in pkg["members"]]


def test_ex1_partial_only_for_the_eor_embedment(ex1_job):
    """Without the EOR anchorage capacity the ONLY open reasons are the anchorage embedment found:false rows."""
    _, _, pkg = ex1_job
    assert pkg["design_status"]["status"] == "partial"
    assert all("12.12_base" in r or "anchorage_embedment" in r for r in pkg["design_status"]["reasons"]), \
        pkg["design_status"]["reasons"]
    s12 = pkg["capacity_design"]["section12"]
    assert s12["n_fail"] == 0
    assert all(c["ok"] is True for c in s12["checks"] if c["id"] != "12.12_base")


def test_ex1_complete(ex1_complete_job):
    _, _, pkg = ex1_complete_job
    assert pkg["design_status"]["status"] == "complete", pkg["design_status"]["reasons"]


def test_ex1_section12_table_populated(ex1_job):
    _, _, pkg = ex1_job
    ids = {c["id"] for c in pkg["capacity_design"]["section12"]["checks"]}
    for need in ("brace_KL_r", "brace_compression", "brace_plastic", "brace_gross_yield_governs", "brace_conn_welds",
                 "brace_conn_block_shear", "gusset_whitmore_yield", "gusset_out_of_plane_buckling", "brace_conn_1p2Mp",
                 "12.4.2_weld_type", "brace_tension_share", "scbf_column_plastic", "12.5.1_trigger",
                 "12.12_base", "7.4_base", "is18168_1_3_system",
                 "is18168_5_5_combinations", "is18168_7_2_column_KL_r", "brace_configuration"):
        assert need in ids, need
    d = pkg["connections"]
    br = next(c for c in d if c["type"] == "brace-to-gusset")
    assert br["demand"]["Pu_capacity_design_N"] == pytest.approx(1.2 * 410 * 6480, rel=1e-6)   # IS 18168 10.4.1
    assert all(isinstance(c["DC"], (int, float)) for c in d), [(c["id"], c["DC"]) for c in d]


def test_ex1_roof_live_and_no_snow(ex1_job):
    """Roof beams get 0.75 kN/m2 (IS 875-2 Table 2) and zero snow in Delhi -- no 1.0 kN/m2 placeholder."""
    cfg, _ = ex1_cfg_is()
    D, L, Lr, Sn = SM.floor_pressures(cfg, len(cfg["heights"]))
    assert Lr == 0.75 and Sn == 0.0
    import openseespy.opensees as ops
    model = SM.build_static(cfg, "Linear", 2)
    ops.timeSeries("Linear", 1); ops.pattern("Plain", 1, 1)
    lev = SM.apply_gravity_state(cfg, model, 0.0, 0.0, 1.0, self_weight=False)      # roof imposed only
    assert lev[len(cfg["heights"])] / 1e3 == pytest.approx(0.75 * 30.0 * 24.0, rel=0.02)   # 540 kN on 720 m2
    # legacy SI gravity path uses the same Lr (no placeholder)
    model = SM.build_static(cfg, "Linear", 2)
    ops.timeSeries("Linear", 1); ops.pattern("Plain", 1, 1)
    tot = SM._apply_gravity_si(cfg, model, 0.0, 0.0, 1.0)
    assert tot / 1e3 == pytest.approx(0.75 * 30.0 * 24.0, rel=0.02)


def test_ex1_model_mass_equals_seismic_weight(ex1_job):
    """The linear engine mass equals the IS 1893 7.3/7.4 seismic weight W within 0.5 %."""
    _, _, pkg = ex1_job
    cfg, _ = ex1_cfg_is()
    import openseespy.opensees as ops
    E.build(cfg, "Linear")
    NF = len(cfg["heights"])
    m = sum(ops.nodeMass(E.mtag(k), 1) for k in range(1, NF + 1))
    W_eng = m * E.g / 1e3
    assert W_eng == pytest.approx(pkg["seismic_calc"]["W_design_kN"], rel=0.005)
    assert W_eng == pytest.approx(pkg["seismic_calc"]["W_engine_kN"], rel=0.005)
