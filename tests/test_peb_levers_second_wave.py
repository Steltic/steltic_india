"""PEB-LEVERS, second wave (2026-10): the study runner's resumable time budget and the sizer's refusal of a proposal
that puts two resized constants on one section label."""
import argparse
import json
import os
import sys
import time
import types

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
for p in (os.path.join(ROOT, "steel_engine"), os.path.join(ROOT, "scripts")):
    if p not in sys.path:
        sys.path.insert(0, p)

import peb_autosize as A        # noqa: E402


def test_shared_label_reason():
    assert A._shared_label({"G_COL": "WI300X180X8X5", "W_COL": "WI400X180X8X5"}) is None
    why = A._shared_label({"G_COL": "WI200X120X6X4", "W_COL": "WI200X120X6X4", "COL_T": "TI300-1000X250X14X6"})
    assert why and "G_COL" in why and "W_COL" in why and "WI200X120X6X4" in why


def test_evaluator_refuses_two_constants_on_one_label():
    """The next full run maps members back to constants by label (LocalModel), so a proposal with two constants on
    one label must be infeasible before any check is evaluated (IN_Ex1 strict: the gable corner and wind columns both
    went to the lightest plates and the next LocalModel stopped the study)."""
    lm = types.SimpleNamespace(res={})
    x_gold = {"G_COL": "WI300X180X8X5", "W_COL": "WI400X180X8X5"}
    ev = A.Evaluator(lm, {"members": {}}, {}, {}, x_gold)
    e = ev({"G_COL": "WI200X120X6X4", "W_COL": "WI200X120X6X4"})
    assert e["feasible"] is False and "share the label" in e["why"] and e.get("viol") is None
    # the local optimiser skips such a proposal (no 'viol'): a repair or descent move to it is never taken
    assert ev.n_eval == 1


def _args(tmp, **kw):
    a = argparse.Namespace(jobs_root=str(tmp / "jobs"), work=str(tmp / "study"), cfs_root=str(tmp / "cfs"),
                           published_root=str(tmp / "pub"), variants="", max_runs=1, resume=True, solar=False,
                           render=False, stop_after_min=0.0)
    for k, v in kw.items():
        setattr(a, k, v)
    return a


def test_budget_spent():
    import peb_lever_study as L
    a = argparse.Namespace(stop_after_min=0.0)
    assert not L.budget_spent(a)
    a.stop_after_min = 30.0
    t0 = L.T_START
    try:
        L.T_START = time.time()
        assert not L.budget_spent(a)
        L.T_START = time.time() - 31 * 60.0
        assert L.budget_spent(a)
    finally:
        L.T_START = t0


def test_study_stops_between_variants_and_resumes(tmp_path):
    """With the budget spent the study starts no new variant: study.json records where it stopped and is not marked
    finished; the n/a levers before the stop are still recorded, so a resumed chunk continues from 'stopped_before'."""
    import peb_lever_study as L
    job = "IN_Ex1_PEB_factory_shed_tapered_Bengaluru"
    a = _args(tmp_path, stop_after_min=1.0)
    t0 = L.T_START
    try:
        L.T_START = time.time() - 120.0
        st = L.run_job(job, a, solar=True)
    finally:
        L.T_START = t0
    assert st["stopped_before"] == "strict" and "finished" not in st
    saved = json.load(open(os.path.join(a.work, job, "study.json")))
    assert saved["stopped_before"] == "strict" and "finished" not in saved
    assert os.path.exists(os.path.join(a.work, job, "study.html"))
    # resumed with every variant already done (here: marked done by hand), the chunk finishes and clears the stop
    for name, kw, status, note in L.variants_for(L.JOB_SPECS[job], solar=True):
        saved["rows"].setdefault(name, {"name": name, "label": L.label(name), "status": status, "note": note,
                                        "done": True})
    json.dump(saved, open(os.path.join(a.work, job, "study.json"), "w"))
    st2 = L.run_job(job, _args(tmp_path), solar=True)
    assert "stopped_before" not in st2 and st2.get("finished")


def test_short_ladder_variants():
    """--ladder short (a study that would take too long): strict, each lever alone, every compliant lever together
    (from the strict design), the market bundle (every lever + market loads, from the compliant design), solar-ready;
    no one-lever-at-a-time steps."""
    import peb_lever_jobs as J
    import peb_lever_study as L
    ex1 = {n: (kw, st) for n, kw, st, _ in L.variants_for(J.JOB_SPECS["IN_Ex1_PEB_factory_shed_tapered_Bengaluru"],
                                                         solar=True, ladder="short")}
    assert not [n for n in ex1 if n.startswith("cum:")]
    comp = ex1["compliant"][0]
    assert comp["start_from"] == "strict" and ex1["compliant"][1] == "compliant"
    assert comp["rules"] == {"ltb_c1": "gradient", "joint_demand": "deliverable", "sway_limit": "H150_with_dado_check",
                             "dado_height_mm": 3000.0, "purlins": "thin_G350"}
    mk, st = ex1["market"]
    assert mk["start_from"] == "compliant" and st.startswith("NOT") and mk["market"] and mk["rods"]
    assert mk["rules"]["sway_limit"] == "H150_no_dado_check" and "dado_height_mm" not in mk["rules"]
    assert mk["rules"]["base_shear_key"] == "analysis" and mk["rules"]["collateral_in_uplift"] is True
    assert ex1["solar_ready"][0]["solar_pv"] == 0.15
    for n in ("strict", "ltb_gradient", "joint_deliverable", "sway_H150_dado", "thin_purlins", "base_key_analysis",
              "collateral_in_uplift", "rods"):
        assert ex1[n][0] is not None, n
    ex4 = {n: (kw, st) for n, kw, st, _ in L.variants_for(J.JOB_SPECS["IN_Ex4_PEB_warehouse_SMRF_Zone4_NCR"],
                                                         ladder="short")}
    assert ex4["market"][0]["seismic_route"] == "OMRF_R3" and ex4["omrf_r3"][1] == "market practice, not compliant"
    assert "joint_demand" not in ex4["compliant"][0]["rules"]


def test_ladder_mode_cannot_change_on_resume(tmp_path):
    import pytest
    import peb_lever_study as L
    job = "IN_Ex1_PEB_factory_shed_tapered_Bengaluru"
    d = tmp_path / "study" / job
    d.mkdir(parents=True)
    json.dump({"job": job, "rows": {}, "ladder": "full"}, open(d / "study.json", "w"))
    with pytest.raises(SystemExit):
        L.run_job(job, _args(tmp_path, ladder="short"), solar=True)


def test_short_ladder_waterfall_and_tables():
    import peb_lever_study as L
    rows = {"strict": {"name": "strict", "label": "s", "status": "compliant", "kg_m2": {"total": 30.0}},
            "compliant": {"name": "compliant", "label": "c", "status": "compliant", "kg_m2": {"total": 27.5}},
            "market": {"name": "market", "label": "m", "status": "NOT COMPLIANT (market practice)",
                       "kg_m2": {"total": 24.0}}}
    st = {"job": "J", "rows": rows, "ladder": "short"}
    svg = L._waterfall(st)
    assert "-2.50" in svg and "-3.50" in svg
    md = L.markdown_tables([st])
    assert "(step -2.50)" in md and "(step -3.50)" in md


def _strut_cfg():
    return {"steel_grade": "E250 B0", "jurisdiction": "india", "units": "N-mm",
            "secondary_members": [
                {"kind": "strut", "id": "gable-rafter-as-girder-chord", "section": "WI350X160X8X5", "L_mm": 7500.0,
                 "Kz": 1.0, "Ky": 1.0, "LLT_mm": 3000.0,
                 "demands": [{"combo": "1.2DL+1.2LL+1.2WL", "P_N": 50706.1, "M_Nmm": 25649156.25},
                             {"combo": "1.5DL+1.5LL", "P_N": 0.0, "M_Nmm": 32061445.3}]},
                {"kind": "strut", "id": "roof-girder-strut", "section": "CHS139.7X4.5", "L_mm": 7500.0,
                 "demands": [{"combo": "1.5DL+1.5WL", "P_N": 47002.8}]}]}


def test_local_strut_check_follows_the_candidate_section():
    """A declared secondary strut on a resized section (the IN_Ex1 gable rafter is also the roof-girder chord) is
    checked locally with the candidate label exactly as the engine checks it (design_pipeline.secondary_strut_checks);
    a strut on a section the sizer does not resize is left to the full run."""
    import design_pipeline as DP
    import peb_build as PB
    lm = A.LocalModel.__new__(A.LocalModel)
    lm.cfg = _strut_cfg()
    lm.const_of_label = {"WI350X160X8X5": "G_RAF"}
    lm._strut_cache = {}
    lm.struts = [(lm.const_of_label[s_["section"]], s_) for s_ in lm.cfg["secondary_members"]
                 if s_["section"] in lm.const_of_label]
    assert [s_["id"] for _, s_ in lm.struts] == ["gable-rafter-as-girder-chord"]
    for lab in ("WI350X160X8X5", "WI250X125X8X4"):
        PB.ensure(lab)
        ref = DP.secondary_strut_checks(lm.cfg, dict(lm.cfg["secondary_members"][0], section=lab))["DC"]
        dc, gov = lm.strut_dc({"G_RAF": lab})
        assert abs(dc - ref) < 1e-12 and lab in gov
    assert lm.strut_dc({"G_RAF": "WI250X125X8X4"})[0] > lm.strut_dc({"G_RAF": "WI350X160X8X5"})[0]


def test_feedback_tightens_the_strut_margin():
    m = {"member": 0.99}
    A.feedback(m, {"fail_items": [(1.22, "secondary", "gable-rafter-as-girder-chord-WI250X125X8X4", "strut")]}, None,
               log_fn=lambda *a: None)
    assert abs(m["strut"] - 0.96) < 1e-9 and m["member"] == 0.99


def test_study_zone_ban_is_a_warning_only_for_a_declared_study_run():
    """cfg['study_allow_banned_system'] (cost-of-compliance runs) turns only the preflight zone-ban ERRORs into
    'STUDY ONLY' warnings; other ERRORs stay, and a job without the key is unchanged."""
    import india_seismic_gates as G
    import pipeline as P
    cfg = {"system": "OMF", "seis": {"zone": "IV", "Z": 0.24, "I": 1.0, "R": 3.0},
           "load_plan": {"seismic_summary": {"zone": "IV", "Z": 0.24, "I": 1.0, "R": 3.0, "system": "OMF"}}}
    f = G.system_zone_findings(cfg)
    ban = [m for s, m in f if s == "ERROR" and "is not allowed in Seismic Zone" in m]
    assert ban, f
    other = ("ERROR", "load_plan.seismic_summary.Ah missing")
    assert P.study_zone_ban_as_warning(cfg, f + [other]) == f + [other]
    cfg["study_allow_banned_system"] = "cost of compliance"
    g = P.study_zone_ban_as_warning(cfg, f + [other])
    assert other in g and not [m for s, m in g if s == "ERROR" and "is not allowed in Seismic Zone" in m]
    assert [m for s, m in g if s == "WARN" and m.startswith("STUDY ONLY (cost of compliance)")]
    # Zone III with I > 1 (IS 800 12.10.1.1 alone)
    msg = ("ERROR", "Steel OMRF with I = 1.5 in Zone III -- IS 800 12.10.1.1")
    assert P.study_zone_ban_as_warning(cfg, [msg])[0][0] == "WARN"
    # the design status still carries the ban (never COMPLETE)
    assert ban[0] in [m for s, m in G.system_zone_findings(cfg) if s == "ERROR"]


def test_omrf_patch_declares_the_study_run_outside_zone_II():
    import peb_lever_jobs as J
    import peb_lever_study as L
    _, p4 = L.omrf_patch(J.JOB_SPECS["IN_Ex4_PEB_warehouse_SMRF_Zone4_NCR"])
    assert "Zone IV" in p4["study_allow_banned_system"] and p4["apply_is18168"] is False
    _, p2 = L.omrf_patch(J.JOB_SPECS["IN_Ex2_PEB_GradeA_warehouse_multispan_Bhiwandi"])
    assert "Zone III" in p2["study_allow_banned_system"]
    _, p1 = L.omrf_patch(J.JOB_SPECS["IN_Ex1_PEB_factory_shed_tapered_Bengaluru"])
    assert "study_allow_banned_system" not in p1
