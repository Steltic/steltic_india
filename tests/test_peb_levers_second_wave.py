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
import sections as S           # noqa: E402


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


FAKE_SECONDARY = '''
import types
calls = []


def bracing_basis(spec, span, role="purlin"):
    return {"declared": True, "type": "sag_rods", "lines": 2, "spacing_mm": span / 3.0}


def bracing_rows(cfg, pu, sec, role, span, s, br, *a, **k):
    calls.append((role, br["spacing_mm"]))
    return [{"check": "8.2.1 brace spacing", "dc": br["spacing_mm"] / (span / 4.0)}]


CM = types.SimpleNamespace(bracing_basis=bracing_basis, bracing_rows=bracing_rows)
PURLIN = {"section": "LZ230X75X20X2", "sag_rods": 2}
GIRT = {"section": "LZ210X60X20X2"}
FY = 240.0


def cfs_cfg():
    return {"loads": {"D_roof": 0.2, "Lr": 0.75}}
'''


def test_market_free_flange_patch_drops_the_brace_rows(tmp_path):
    """Market bundle (sheeting taken as the purlin brace): the patched bracing basis has no brace interval, so the
    IS 801 8.2 brace rows are not produced for the purlin (the first-wave CFS engine divided by the interval: the
    IN_Ex1 market variant stopped on a ZeroDivisionError); girts keep their rows."""
    src = A.SECONDARY_WORKER.replace("\nmain()\n", "\n")
    ns = {}
    exec(compile(src, "secondary_worker", "exec"), ns)
    script = tmp_path / "secondary_is801.py"
    script.write_text(FAKE_SECONDARY)
    job = {"script": str(script), "consts": {"purlin": "PURLIN", "girt": "GIRT", "fy": "FY"},
           "purlin0": {"section": "LZ230X75X20X2", "sag_rods": 2}, "girt0": {"section": "LZ210X60X20X2"}, "fy": 240.0,
           "free_flange_braced": True}
    mod = ns["load"](job, "LZ200X60X20X2", "LZ210X60X20X2")
    br = mod.CM.bracing_basis({}, 7500.0, "purlin")
    assert br["spacing_mm"] == 0.0 and br["type"] == "sheeting" and "MARKET PRACTICE" in br["type_text"]
    assert mod.CM.bracing_rows({}, {}, {}, "purlin", 7500.0, 1500.0, br) == []
    gb = mod.CM.bracing_basis({}, 7500.0, "girt")
    rows = mod.CM.bracing_rows({}, {}, {}, "girt", 7500.0, 1800.0, gb)
    assert rows and abs(rows[0]["dc"] - (2500.0 / 1875.0)) < 1e-9


def test_secondary_error_rows_are_not_read_as_results():
    """A CFS error row carries the section label under the role key: it must read as 'no result', not crash."""
    r = {"purlin": "Z200X65X20X1.0-G350", "girt": "LZ230X75X20X2", "error": "Traceback ...\nZeroDivisionError: x"}
    rr = r.get("purlin") if isinstance(r.get("purlin"), dict) else {}
    assert rr == {}
    import inspect
    assert 'isinstance(r.get(role), dict)' in inspect.getsource(A.design_secondary)


def _fake_lm(Ty, Tx=0.2, gust=False):
    lm = A.LocalModel.__new__(A.LocalModel)
    lm.pkg = {"irregularity": {"modes": {"Ty": Ty, "Tx": Tx}}, "wind_serviceability": {}, "drift_table": []}
    ws = {"pd_kNm2": 1.0}
    if gust:
        ws["gust_factor"] = {"G": 2.1}
    lm.cfg = {"load_plan": {"wind_summary": ws}}
    lm.spec = {}
    return lm


def test_first_mode_frequency_is_kept_at_or_above_1Hz():
    """IS 875-3 9.1(b): below 1.0 Hz the engine requires the 10.2 gust-factor wind.  Without a gust factor the
    predicted f1 = f1_run / sqrt(flexibility ratio) must reach 1.0 Hz (a run below it -- the solar-ready variant with
    the PV mass -- is stiffened); a job with a gust factor is not constrained; a failed dynamic_wind gate tightens the
    frequency margin."""
    lm = _fake_lm(0.974)
    g = lm._globals()
    assert abs(g["freq_Y"] - 1.0 / 0.974) < 1e-12
    lm.global0, lm.F0 = g, 100.0
    lm.flexibility = lambda x: 121.0                   # 21 % more flexible -> f / 1.1
    assert abs(lm.predicted({})["freq_Y"] - (1.0 / 0.974) / 1.1) < 1e-12
    assert abs(_fake_lm(1.07)._globals()["freq_Y"] - 1.0 / 1.07) < 1e-12   # below 1 Hz: constrained (stiffen)
    assert "freq_Y" not in _fake_lm(0.2, Tx=0.5)._globals()          # the first mode is not the transverse one
    assert "freq_Y" not in _fake_lm(0.9, gust=True)._globals()     # the job declares the gust factor
    m = {}
    A.feedback(m, {"fail_items": [], "gates_fail": ["dynamic_wind"]}, None, log_fn=lambda *a: None)
    assert abs(m["freq"] - 0.95) < 1e-9 and "sway" not in m


def test_waived_checks_do_not_govern(tmp_path):
    """The rods / market variants waive the brace compression of tension-only rods: such a row (D/C ~ 134) must not be
    reported as the governing check nor be fed back as a failure."""
    import json as _j
    rd = tmp_path / "run"
    (rd / "design").mkdir(parents=True)
    _j.dump({"ok": True, "design_status": {"status": "complete", "reasons": []}}, open(rd / "result.json", "w"))
    pkg = {"peb": {"tonnage": {"kg": {"primary": 1.0}, "plan_area_m2": 1.0}},
           "members": [{"id": "roof-WI500X200X10X6", "DC": 0.93, "governing_check": "9.3"}],
           "capacity_design": {"section12": {"checks": [
               {"id": "brace_compression", "member": "e355", "dc": 134.3, "ok": False, "clause": "IS 800 7.1.2"}]}}}
    _j.dump(pkg, open(rd / "design" / "calc_package.json", "w"))
    r = A.evaluate_run(str(rd), waivers=(r"(?i)brace_compression",))
    assert r["governing"][2] == "roof-WI500X200X10X6" and not r["fail_items"]
    assert r["waived_checks"][0][2] == "brace_compression@e355"
    r0 = A.evaluate_run(str(rd))
    assert r0["governing"][1] == "section12" and r0["fail_items"]


def test_control_variant_is_optional():
    """--control: the strict rules again from the strict design (the sizer's resolution), right after 'strict'."""
    import peb_lever_jobs as J
    import peb_lever_study as L
    spec = J.JOB_SPECS["IN_Ex3_PEB_crane_shed_10t_Nagpur"]
    names = [n for n, kw, st, _ in L.variants_for(spec, ladder="short")]
    assert "control" not in names
    v = L.variants_for(spec, ladder="short", control=True)
    names = [n for n, kw, st, _ in v]
    assert names[:2] == ["strict", "control"]
    kw = v[1][1]
    assert kw["rules"] == {} and kw["start_from"] == "strict" and v[1][2] == "compliant"
    assert L.VARIANT_ORDER.index("control") == L.VARIANT_ORDER.index("strict") + 1


def test_strengthen_only_floors_the_knee_diagonal_stiffener():
    """IN_Ex1 solar-ready: the gold knee failed, the knee was re-sized and its diagonal stiffener came out 6 mm
    against the gold's 16 mm.  In strengthen-only mode the diagonal stiffener is not thinner than the gold's."""
    import inspect
    sig = inspect.signature(A.size_knee)
    assert "diag_min" in sig.parameters and sig.parameters["diag_min"].default is None
    src = inspect.getsource(A.Evaluator.connections)
    assert 'diag_min=float((fl.get("knee_panel") or {}).get("diag_t") or 0.0)' in src


def test_solar_job_uses_the_IN_Ex5_wind_basis(tmp_path):
    """The solar-ready variant is sized on a copy of the job with spec['solar']['cfg_append'] appended (IN_Ex1: the
    IN_Ex5 gust-factor wind once the PV mass takes f1 below 1.0 Hz) and the evidence of the PV job laid over."""
    import peb_lever_jobs as J
    import peb_lever_study as L
    jobs = tmp_path / "jobs"
    j1, j5 = jobs / "JOB1", jobs / "JOB5"
    for d in (j1 / "rag", j1 / "design", j1 / "secondary", j5 / "rag"):
        d.mkdir(parents=True)
    (j1 / "cfg.py").write_text("SOLAR_PV = 0.0\ncfg = {}\n")
    (j1 / "retrieval_evidence.json").write_text('[{"item": "a"}]')
    (j1 / "rag" / "a.txt").write_text("a")
    (j1 / "design" / "calc_package.json").write_text("{}")
    (j5 / "retrieval_evidence.json").write_text('[{"item": "a"}, {"item": "dyn_9_1"}]')
    (j5 / "rag" / "dyn.txt").write_text("9.1")
    spec = {"solar": {"pv_kNm2": 0.15, "evidence_job": "JOB5", "cfg_append": "\n# APPENDED\n"}}
    d = L.solar_job(str(j1), spec, str(jobs), str(tmp_path / "work"))
    assert d != str(j1) and open(os.path.join(d, "cfg.py")).read().endswith("# APPENDED\n")
    assert "dyn_9_1" in open(os.path.join(d, "retrieval_evidence.json")).read()
    assert sorted(os.listdir(os.path.join(d, "rag"))) == ["a.txt", "dyn.txt"]
    assert not os.path.exists(os.path.join(d, "design"))            # no stale outputs in the variant job
    assert open(j1 / "cfg.py").read() == "SOLAR_PV = 0.0\ncfg = {}\n"  # the job itself is not touched
    assert L.solar_job(str(j1), {}, str(jobs), str(tmp_path / "work")) == str(j1)
    ap = J.JOB_SPECS["IN_Ex1_PEB_factory_shed_tapered_Bengaluru"]["solar"]["cfg_append"]
    compile(ap, "append", "exec")
    for name in ("SOLAR_PV", "E.modal", "WT.along_wind_story_forces", "CPE_W0", "F_Y", "gust_factor", "9.1 (b)"):
        assert name in ap, name


def test_local_scwb_matches_the_engine_joint_check():
    """IN_Ex2 / IN_Ex4 (SMRF): the local IS 800 12.11.3.2 check of a run's SCWB rows with candidate sections equals the
    engine's scwb_joint for the same sections and column axial load."""
    import india_is800_s12 as S12
    import peb_build as PB
    col0, col1, raf = "WI600X270X20X14", "WI700X300X22X14", "WI625X250X20X17"
    for s_ in (col0, col1, raf):
        PB.ensure(s_)
    P = 222000.0
    lm = A.LocalModel.__new__(A.LocalModel)
    lm.dump = {16: {"member": {"section": col0, "node_i": 1000, "node_j": 100100, "grade": "E350 B0"},
                    "peb": {"member": "m16", "f": [0.0, 1.0]}},
               122: {"member": {"section": raf, "node_i": 100100, "node_j": 100101, "grade": "E350 B0"},
                     "peb": {"member": "m122", "f": [0.0, 0.25]}}}
    lm.members = {"m16": {"section": col0}, "m122": {"section": raf}}
    lm.const_of_label = {col0: "COL", raf: "RAF_K"}
    lm.pkg = {"capacity_design": {"section12": {"checks": [
        {"id": "12.11.3.2_SCWB", "member": "J100100-Y", "value": 0.94, "dc": 1.27, "ok": False,
         "columns": [{"member": "e16", "section": col0, "axis": "z", "P_N": P}],
         "beams": [{"member": "e122", "section": raf}]}]}}}
    lm._scwb_cache = {}
    lm.scwb = lm._scwb_rows()
    assert len(lm.scwb) == 1 and lm.scwb[0][1] == 100100
    for col in (col0, col1):
        dc, gov = lm.scwb_dc({"COL": col, "RAF_K": raf})
        md = {"members": [{"id": "c", "section": col, "grade": "E350 B0"}, {"id": "b", "section": raf, "grade": "E350 B0"}],
              "forces": {}}
        ref = S12.scwb_joint({"id": "J100100-Y", "columns": [{"member_id": "c", "P_N": P}], "beams": [{"member_id": "b"}],
                              "frame_dir": None}, md)
        assert abs(dc - ref["dc"]) < 1e-9 and "J100100-Y" in gov, (col, dc, ref)
    assert lm.scwb_dc({"COL": col1, "RAF_K": raf})[0] < lm.scwb_dc({"COL": col0, "RAF_K": raf})[0]
    m = {}
    A.feedback(m, {"fail_items": [(1.17, "section12", "12.11.3.2_SCWB@J100100-Y", "IS 800")]}, None,
               log_fn=lambda *a: None)
    assert abs(m["scwb"] - 0.98) < 1e-9 and "member" not in m


def test_local_panel_zone_matches_the_engine():
    """SMRF knees: the local 12.11.2.3 / 12.11.2.4 panel-zone ratio with candidate face sections equals the engine's
    panel_zone_check at the 12.11.2.2 shear of those sections (column shear and doubler of the run)."""
    import india_is800 as I8
    import india_is800_s12 as S12
    import peb_build as PB
    col0, col1, raf = "WI700X280X22X14", "WI700X300X22X16", "WI625X310X22X17"
    for s_ in (col0, col1, raf):
        PB.ensure(s_)
    lm = A.LocalModel.__new__(A.LocalModel)
    lm.dump = {16: {"member": {"section": col0, "node_i": 1000, "node_j": 100100, "grade": "E350 B0"},
                    "peb": {"member": "m16", "f": [0.0, 1.0]}},
               122: {"member": {"section": raf, "node_i": 100100, "node_j": 100101, "grade": "E350 B0"},
                     "peb": {"member": "m122", "f": [0.0, 0.25]}}}
    lm.members = {"m16": {"section": col0}, "m122": {"section": raf}}
    lm.const_of_label = {col0: "COL", raf: "RAF_K"}
    lm.x0 = {"COL": col0, "RAF_K": raf}
    praf = S.props(raf)
    fyb = S12._fy({"section": raf, "grade": "E350 B0"}, praf)[0]
    vcol = 50000.0
    V0 = S12.panel_zone_design_shear([praf["Zx"] * fyb], praf["d"], praf["tf"], vcol)
    lm.pkg = {"capacity_design": {"section12": {"checks": [
        {"id": "12.11.3.2_SCWB", "member": "J100100-Y", "value": 1.0, "dc": 1.2,
         "columns": [{"member": "e16", "section": col0, "axis": "z", "P_N": 2.0e5}],
         "beams": [{"member": "e122", "section": raf}]},
        {"id": "12.11.2.3_panel_zone", "member": "J100100-Y", "dc": 1.05, "column_axis": "major",
         "detail": {"found": True, "inputs": {"V_design_N": V0, "d_beam_mm": praf["d"], "doubler_t_mm": 16.0}}}]}}}
    lm._scwb_cache, lm._pz_cache = {}, {}
    lm.scwb = lm._scwb_rows()
    lm.pz = lm._pz_rows()
    assert len(lm.pz) == 1 and abs(lm.pz[0][4] - vcol) < 1e-6
    for col in (col0, col1):
        pc = S.props(col)
        fyc = S12._fy({"section": col, "grade": "E350 B0"}, pc)[0]
        ref = I8.panel_zone_check(d_beam_mm=praf["d"], V_design_N=V0, fy_MPa=fyc, doubler_t_mm=16.0,
                                  continuity_plates=True, n_webs=1, d_col_mm=pc["d"], tw_mm=pc["tw"], bf_mm=pc["bf"],
                                  tf_mm=pc["tf"])
        want = max([ref["dc"]] + [p["t_min_mm"] / p["t_mm"] for p in ref["plates"]])
        dc, gov = lm.pz_dc({"COL": col, "RAF_K": raf})
        assert abs(dc - want) < 1e-9 and "panel zone" in gov, (col, dc, want)
    m = {}
    A.feedback(m, {"fail_items": [(1.07, "section12", "12.11.2.3_panel_zone@J100100-Y", "IS 800")]}, None,
               log_fn=lambda *a: None)
    assert abs(m["panel"] - 0.98) < 1e-9 and "conn:knee" not in m


def test_ocbf_brace_sizing_skips_sections_without_Cw(tmp_path):
    """IN_Ex2 OMRF_R3: the OCBF brace came out WPB200X200X37.34, whose IS 808 record has no warping constant, so the
    engine could not evaluate the brace (found:false) and every run stayed open.  Such a section is skipped."""
    import peb_lever_study as L
    assert not S.props("WPB200X200X37.34").get("Cw")
    rd = tmp_path / "best"
    rd.mkdir()
    pkg = {"members": [{"inputs": {"kind": "brace", "P_comp_N": 150000.0, "length_mm": 10817.0}}]}
    json.dump(pkg, open(rd / "calc_package.json", "w"))
    lab, note = L.size_ocbf_braces(str(rd), "WPB160X160X30.44", 4.5)
    assert lab != "WPB200X200X37.34" and S.props(lab).get("Cw"), (lab, note)


def test_buckling_section_registers_taper_station_labels():
    """A candidate taper's end-station label (e.g. WI325X290X22X12) must be registered before its properties are read
    (IN_Ex2 OMRF_R3 stopped on a KeyError)."""
    import peb_build as PB
    lm = A.LocalModel.__new__(A.LocalModel)
    lm.chains = {"ch": {"members": ["m1"]}}
    lm.members = {"m1": {"section": "TI450-200X190X12X5"}}
    lm.const_of_label = {"TI450-200X190X12X5": "CAN_T"}
    lab = "TI453-219X291X22X12"
    PB.ensure(lab)
    sec = lm.buckling_section("ch", {"CAN_T": lab})
    assert sec == PB.section_at(lab, 1.0) and S.props(sec)["d"] > 0


def test_canopy_root_checks_the_candidate_column_flange():
    """IN_Ex2 OMRF_R3: the canopy-beam root is bolted to the column flange; the column flange (the other T-stub
    flange) follows the candidate column, so a column too light for the canopy bolts fails locally instead of in
    every full run.  The row is peb_checks.splice_records' own column-flange row."""
    import peb_build as PB
    face = "WI450X190X12X5"
    for s_ in (face, "WI675X200X20X8", "WI725X230X22X14", "WI675X200X12X8"):
        PB.ensure(s_)
    lm = A.LocalModel.__new__(A.LocalModel)
    lm.cfg = {"steel_grade": "E350 B0", "units": "N-mm", "jurisdiction": "india"}
    par = {"t": 32.0, "d": 20, "grade": "10.9", "plate_grade": "E250 B0", "n_out": 2, "n_in": 3,
           "pitch_rule": ["ratio", 4], "b_plate": 220.0, "web_doubler": 0.0, "member_fy": 350.0, "gauge": 110.0}
    sp = {"symmetric": True, "gauge_mm": 110.0, "column_flange_grade": "E350 B0", "column_section": "WI675X200X20X8"}
    dem = {"Md": 2.0e8, "Mr": 1.5e8, "sec_min": face, "kind": "canopy_root", "spec": sp, "n": 1}
    assert A.splice_fixed(lm, "canopy_root", dem, face, par, 1.0) is not None           # no column: plate only
    ok = A.splice_fixed(lm, "canopy_root", dict(dem, col_sec="WI725X230X22X14"), face, par, 1.0)
    thin = A.splice_fixed(lm, "canopy_root", dict(dem, col_sec="WI675X200X12X8"), face, par, 1.0)
    assert ok is not None and thin is None


def test_market_bundle_drops_rods_that_cannot_pass():
    """IN_Ex3: with rod X-bracing the shed is torsionally irregular (IS 1893 Table 5(i), Amd 2) and no design passes;
    the market bundle then keeps the compression bracing and says so.  With a passing rods row nothing changes."""
    import peb_lever_study as L
    kw = {"rules": {"bracing": "tension_rods", "ltb_c1": "gradient"}, "rods": True, "market": True}
    failed = {"rods": {"done": True, "error": "no passing design within 8 full runs",
                       "last_blocking": ["irregularity.torsion.verdict: revise configuration"]}}
    k2 = L.drop_failed_rods(kw, "market", failed)
    assert k2["rods"] is False and "bracing" not in k2["rules"] and k2["rules"]["ltb_c1"] == "gradient"
    assert "rods left out" in k2["rods_dropped"] and "torsion" in k2["rods_dropped"]
    assert kw["rods"] is True and "bracing" in kw["rules"]                       # the variant list is not mutated
    assert L.drop_failed_rods(kw, "market", {"rods": {"done": True, "best_x": {"COL": "x"}}}) is kw
    assert L.drop_failed_rods(kw, "compliant", failed) is kw
