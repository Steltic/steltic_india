"""PEB-LEVERS (2026-10 variations study): the cfg['peb_rules'] switches (steel_engine/peb_levers.py and the delimited
'PEB-LEVERS' hooks in the engine) and the deterministic auto-sizer (steel_engine/peb_autosize.py).

* defaults change nothing (a cfg with the default switches runs exactly as one without them);
* each switch changes what it should, and only that, on the small tapered portal of tests/_peb_fixture.py;
* the auto-sizer reproduces the engine's member / knee checks with frozen forces and, on a small job, finds a lighter
  passing design deterministically."""
import copy
import json
import math
import os
import shutil

import pytest

from _peb_fixture import COL_T, RAF_P, RAF_T, mini_peb_cfg, stage_rag

import peb_levers as PL
import sections as S

HERE = os.path.dirname(os.path.abspath(__file__))
MINI = os.path.join(HERE, "fixtures", "peb_levers_mini")


@pytest.fixture(autouse=True)
def _si_units():
    import india_units as IU
    prev = IU.active_unit_system()
    IU.activate_si()
    yield
    if prev != "N-mm":
        IU.activate_kip_in()


# ------------------------------------------------------------------------------------------- the switch registry
def test_rules_defaults_and_validation():
    r = PL.rules({})
    assert r == PL.DEFAULTS and PL.is_default({}) and PL.is_default({"peb_rules": dict(PL.DEFAULTS)})
    with pytest.raises(PL.LeverError):
        PL.rules({"peb_rules": {"joint_demand": "0.8Mp"}})
    with pytest.raises(PL.LeverError):
        PL.rules({"peb_rules": {"no_such_switch": 1}})
    with pytest.raises(PL.LeverError):
        PL.rules({"peb_rules": {"sway_limit": "H150_with_dado_check"}})        # needs the dado height
    assert PL.rules({"peb_rules": {"sway_limit": "H150_with_dado_check", "dado_height_mm": 3000.0}})


def test_describe_marks_the_non_compliant_switches():
    d = {k: (v, st) for k, v, st, _b in PL.describe({"peb_rules": {"bracing": "tension_rods", "ltb_c1": "gradient"}})}
    assert d["bracing"][1] == "not compliant" and d["ltb_c1"][1] == "compliant"
    assert d["joint_demand"][1].startswith("default")


def test_seismic_route_status():
    assert PL.seismic_route_status("II")[0] is True
    ok, lab, note = PL.seismic_route_status("III", 1.0)
    assert ok and "conflict" in lab and "Note 1" in note and "12.10.1.1" in note
    assert PL.seismic_route_status("III", 1.2)[0] is False
    ok, lab, _n = PL.seismic_route_status("IV")
    assert not ok and "not compliant" in lab


def test_joint_demand_deliverable_reading():
    cfg = {"system": "OMRF+OCBF", "system_y": "OMRF", "peb_rules": {"joint_demand": "deliverable"}}
    M, basis, on = PL.joint_demand(cfg, 1000.0e6, 300.0e6)
    assert on and M == pytest.approx(min(1.2 * 1000e6, 1.2 * 300e6)) and "12.10.2.1" in basis
    cfg["peb_rules"]["deliverable_factor"] = 1.0
    assert PL.joint_demand(cfg, 1000.0e6, 300.0e6)[0] == pytest.approx(300e6)
    assert PL.joint_demand(cfg, 100.0e6, 300.0e6)[0] == pytest.approx(120e6)          # 1.2 Mp caps it
    # SMRF and IS 18168 joints are left unchanged
    smf = {"system": "SMF+SCBF", "system_y": "SMF", "peb_rules": {"joint_demand": "deliverable"}}
    M, note, on = PL.joint_demand(smf, 1000.0e6, 300.0e6)
    assert not on and M == pytest.approx(1200e6) and "unchanged" in note
    assert PL.joint_demand(cfg, 1000.0e6, 300.0e6, is18=True)[2] is False


def test_fold_collateral_old_treatment():
    cfg = {"D_roof": 0.20, "D_floor": 0.20, "D_roof_collateral": 0.15, "D_roof_pv": 0.10}
    c2, note = PL.fold_collateral(copy.deepcopy(cfg))
    assert c2 == cfg and note is None                                    # default: left to the engine (out of 0.9DL)
    cfg["peb_rules"] = {"collateral_in_uplift": True}
    c3, note = PL.fold_collateral(cfg)
    assert c3["D_roof"] == pytest.approx(0.45) and c3["D_floor"] == pytest.approx(0.45)
    assert c3["D_roof_collateral"] == 0.0 and c3["D_roof_pv"] == 0.0 and "0.9DL" in note


def test_c1_segment_from_end_moments():
    import india_is800 as I8
    chain = [(1, 0.0, 1000.0), (2, 1000.0, 2000.0)]
    recs = {1: {"c": [0, 0, 0, 0, 100.0e6, 50.0e6]}, 2: {"c": [0, 0, 0, 0, 50.0e6, 0.0]}}
    c1, note = PL._c1_segment(chain, lambda t: recs[t], "c", 0.0, 2000.0, {1: True, 2: True})
    assert c1 == pytest.approx(I8.c1_from_end_moments(0.0)) and c1 > 1.5
    # an interior moment larger than the end values keeps C1 = 1.0 (conservative)
    recs[1]["c"][5] = 150.0e6
    recs[2]["c"][4] = 150.0e6
    assert PL._c1_segment(chain, lambda t: recs[t], "c", 0.0, 2000.0, {1: True, 2: True})[0] == 1.0
    # a prismatic (long) element in the restrained length keeps C1 = 1.0
    assert PL._c1_segment(chain, lambda t: recs[t], "c", 0.0, 2000.0, {1: True, 2: False})[0] == 1.0


def test_rods_refused_outside_zone_II_ocbf():
    cfg = {"seis": {"zone": "III"}, "system_x": "OCBF", "peb_rules": {"bracing": "tension_rods"}}
    with pytest.raises(PL.LeverError):
        PL.rods_allowed(cfg)
    cfg["seis"]["zone"] = "II"
    ok, note = PL.rods_allowed(cfg)
    assert ok and "NOT compliant" in note
    r = PL.rod_tension_check(20, 50.0e3)
    assert r["An_mm2"] == 245.0 and r["Td_N"] == pytest.approx(min(314.16 * 250 / 1.1, 0.9 * 245 * 410 / 1.25), rel=1e-3)


# ------------------------------------------------------------------------------------------- pipeline runs
def _run(tmp_path_factory, name, cfg):
    import pipeline as P
    jobs = tmp_path_factory.mktemp("lev_" + name)
    os.environ["STELTIC_TEST_JOBS"] = str(jobs)
    os.environ["STEEL_BUILDER_JOBS"] = str(jobs)
    stage_rag(os.path.join(str(jobs), name))
    out = P.design_and_report(name, cfg, do_report=False)
    return out, json.load(open(os.path.join(out["root"], "design", "calc_package.json")))


def _mini_with_joints(name, brittle=False):
    import peb_build as PB
    import peb_autosize as A
    cfg = mini_peb_cfg(name)
    knee = PB.section_at(RAF_T, 0.0)
    ep = A.ep_dict(knee, t=25.0, d_bolt=20, n_out=1, n_in=3, pitch=90.0, b_plate=200.0)
    sp = A.ep_dict(RAF_P, t=25.0, d_bolt=20, n_out=1, n_in=2, pitch=90.0, b_plate=180.0)
    cfg["connections"] = {
        "beam_column": {knee: {"type": "end_plate", "end_plate": ep, "bolt_type": "HSFG", "weld_type": "cjp",
                               "symmetric": True, "plate_b_mm": 200.0, "gauge_mm": 110.0}},
        "knee_panel": {"diagonal_stiffener": {"n": 2, "b_mm": 60.0, "t_mm": 10.0, "fy_MPa": 250.0},
                       "flange_stiffener": {"n": 2, "b_mm": 60.0, "t_mm": 10.0, "fy_MPa": 250.0}},
        "rafter_splice": {"apex": {"end_plate": dict(sp), "symmetric": True, "plate_b_mm": 180.0},
                          "rafter_splice": {"end_plate": dict(sp), "symmetric": True, "plate_b_mm": 180.0}},
        "column_base": {"default": {"B_mm": 300.0, "L_mm": 350.0, "t_plate_mm": 20.0, "fy_plate_MPa": 250.0,
                                    "plate_grade": "E250", "fck_MPa": 30.0, "fixed": False,
                                    "anchors": {"n_total": 4, "n_tension": 2, "d_mm": 20, "grade": "8.8",
                                                "f_mm": 100.0, "pitch_mm": 120.0, "edge_mm": 50.0, "n_per_row": 2,
                                                "Anb_mm2": 245.0},
                                    "shear_key": A.shear_key(300.0, 32.0, 300.0, 240.0, 30.0)}}}
    if brittle:
        cfg["cladding_brittle"] = True
    return cfg


@pytest.fixture(scope="module")
def runs(tmp_path_factory):
    """The mini portal with joints under the defaults, the default switches written out, and each frame switch."""
    out = {}
    cases = {
        "none": {},
        "defaults": dict(PL.DEFAULTS),
        "deliverable": {"joint_demand": "deliverable"},
        "gradient": {"ltb_c1": "gradient"},
        "base": {"base_shear_key": "analysis"},
    }
    for k, rules in cases.items():
        cfg = _mini_with_joints("lev_" + k)
        if rules:
            cfg["peb_rules"] = rules
        out[k] = _run(tmp_path_factory, "lev_" + k, cfg)
    for k, rules in {"brittle": {}, "dado": {"sway_limit": "H150_with_dado_check", "dado_height_mm": 1500.0},
                     "nodado": {"sway_limit": "H150_no_dado_check"}}.items():
        cfg = _mini_with_joints("lev_" + k, brittle=True)
        if rules:
            cfg["peb_rules"] = rules
        out[k] = _run(tmp_path_factory, "lev_" + k, cfg)
    return out


def _core(pkg):
    return {"members": [(m["id"], m.get("DC")) for m in pkg["members"]],
            "connections": [(c["id"], c.get("DC")) for c in pkg["connections"]],
            "s12": [(c.get("id"), c.get("member"), c.get("dc"), c.get("ok"))
                    for c in pkg["capacity_design"]["section12"]["checks"]],
            "gates": pkg.get("gates"), "wind": pkg.get("wind_serviceability"), "tonnage": pkg["peb"]["tonnage"]["kg"]}


def test_default_switches_change_nothing(runs):
    assert _core(runs["none"][1]) == _core(runs["defaults"][1])


def _row(pkg, prefix, name_start):
    for c in pkg["connections"]:
        if c["id"].startswith(prefix):
            for r in c["checks"]:
                if r["name"].startswith(name_start):
                    return c, r
    raise KeyError((prefix, name_start))


def test_deliverable_lowers_the_knee_and_apex_demand(runs):
    p0, p1 = runs["none"][1], runs["deliverable"][1]
    c0, r0 = _row(p0, "conn-peb-knee-", "knee end plate, both signs")
    c1, r1 = _row(p1, "conn-peb-knee-", "knee end plate, both signs")
    Mk = c1["demand"]["M_knee_Nmm"]
    assert r1["value"] == pytest.approx(min(r0["value"], 1.2 * Mk), rel=1e-6) and r1["value"] < r0["value"]
    assert "deliverable" in r1["name"]
    a1 = [c for c in p1["connections"] if c["type"].startswith("PEB apex") and "deliverable" in c["demand"]["basis"]]
    assert a1
    a0 = [c for c in p0["connections"] if c["id"] == a1[0]["id"]]
    assert a0 and "owner ruling D-T7" in a0[0]["demand"]["basis"]
    assert a1[0]["demand"]["M_design_Nmm"] < a0[0]["demand"]["M_design_Nmm"]
    # the gravity (gable) apex is not a moment-frame joint: unchanged
    g0 = {c["id"]: c["demand"]["M_design_Nmm"] for c in p0["connections"] if "gravity" in str(c["demand"].get("basis"))}
    g1 = {c["id"]: c["demand"]["M_design_Nmm"] for c in p1["connections"] if "gravity" in str(c["demand"].get("basis"))}
    assert g0 and g0 == g1
    # the Section 12 12.10.2.1 row takes the deliverable moment too
    m0 = [c["value"] for c in p0["capacity_design"]["section12"]["checks"] if c.get("id") == "connection_moment"]
    m1 = [c["value"] for c in p1["capacity_design"]["section12"]["checks"] if c.get("id") == "connection_moment"]
    assert m0 and m1 and max(m1) < max(m0)


def test_gradient_c1_only_lowers_member_dc(runs):
    m0 = dict((m["id"], m["DC"]) for m in runs["none"][1]["members"])
    m1 = dict((m["id"], m["DC"]) for m in runs["gradient"][1]["members"])
    assert set(m0) == set(m1)
    assert all(m1[k] <= m0[k] + 1e-9 for k in m0)
    assert any(m1[k] < m0[k] - 1e-6 for k in m0)
    # the analysis is the same: only the LTB capacities change
    assert runs["none"][1]["wind_serviceability"] == runs["gradient"][1]["wind_serviceability"]


def test_sway_switch_and_dado_check(runs):
    wb, wd, wn = (runs[k][1]["wind_serviceability"]["Y"] for k in ("brittle", "dado", "nodado"))
    assert wb["basis"] == "column_no_crane_brittle" and wb["limit_top_mm"] == pytest.approx(wb["H_mm"] / 240.0)
    assert wd["basis"] == "column_no_crane_elastic" and wd["limit_top_mm"] == pytest.approx(wd["H_mm"] / 150.0)
    assert wd["top_mm"] == pytest.approx(wb["top_mm"])                          # same analysis
    assert 0.0 < wd["dado_top_mm"] < wd["top_mm"] and wd["dado_limit_mm"] == pytest.approx(1500.0 / 240.0)
    assert "ratio_dado" not in wn and wn["basis"] == "column_no_crane_elastic" and "market practice" in wn["cite"]


def test_base_shear_key_analysis_drops_the_1p2Vd_floor(runs):
    def base_v(pkg):
        return max([pc["V_N"] for c in pkg["capacity_design"]["section12"]["checks"] if c.get("id") == "12.12_base"
                    for pc in c.get("per_case") or []] or [0.0])
    v0, v1 = base_v(runs["none"][1]), base_v(runs["base"][1])
    assert v0 > 0 and v1 < v0
    rows = [c for c in runs["base"][1]["capacity_design"]["section12"]["checks"] if c.get("id") == "12.12_base"]
    assert rows and "base_shear_key 'analysis'" in rows[0]["cite"]


def test_rod_bracing_member_check_and_take_off(tmp_path_factory, monkeypatch):
    import _peb_fixture as F
    rod = PL.rod_label(20)
    PL.register_rod(rod)
    monkeypatch.setattr(F, "BRACE", rod)
    cfg = mini_peb_cfg("lev_rods")
    cfg["peb_rules"] = {"bracing": "tension_rods"}
    out, pkg = _run(tmp_path_factory, "lev_rods", cfg)
    br = [m for m in pkg["members"] if m["id"].startswith("brace-")]
    assert br and br[0]["governing_check"].startswith("tension rod")
    by_el = pkg["peb"]["tonnage"]["by_element"]
    import peb_checks as PC
    rods = [v["kg"] for v in by_el.values() if v["group"] == "bracing"]
    assert rods
    # the take-off counts the real rod (the analysis bar is half its area)
    p = S.props(rod)
    assert p["A"] == pytest.approx(math.pi * 20 ** 2 / 8.0)


# ------------------------------------------------------------------------------------------- the auto-sizer
@pytest.fixture(scope="module")
def mini_job(tmp_path_factory):
    root = tmp_path_factory.mktemp("lev_job")
    job = os.path.join(str(root), "peb_levers_mini")
    os.makedirs(job)
    shutil.copy(os.path.join(MINI, "cfg.py"), os.path.join(job, "cfg.py"))
    stage_rag(job)
    return job


SPEC = {"job": "peb_levers_mini",
        "members": {"COL_T": {"group": "column"}, "RAF_T": {"group": "rafter"}, "RAF_P": {"group": "rafter"}},
        "links": [["COL_T.D1", "RAF_T.D0"], ["RAF_T.D1", "RAF_P.D"]],
        "fab": {"D_min": 200.0, "D_max": 800.0, "bf_min": 120.0, "bf_max": 300.0, "tw_min": 4.0},
        "knee_column": "COL_T", "splice_faces": {"apex": ["RAF_P", 1.0], "rafter_splice": ["RAF_P", 0.0]},
        "base_consts": ["COL_T"], "frame_line": 1, "base": "pinned",
        "seismic": {"zone": "II", "I": 1.0, "R_consts": {"R_Y": "y", "R_X": "x"}, "route": "OMRF"}}


def test_cfg_constants_rewrite():
    import peb_autosize as A
    tree = A.override_source("A = 1\nB, C = 2, 3\nD = A + 1\n", {"A": 5, "C": "x"})
    ns = {}
    exec(compile(tree, "t", "exec"), ns)
    assert (ns["A"], ns["B"], ns["C"], ns["D"]) == (5, 2, "x", 6)
    with pytest.raises(KeyError):
        A.override_source("A = 1\n", {"Z": 1})


def test_ep_dict_matches_the_gold_helper():
    """The auto-sizer's end plate is the golds' bolted_end_plate (same rows, strip, lever arm, plate fy)."""
    import importlib.util
    import peb_autosize as A
    import peb_build as PB
    spec = importlib.util.spec_from_file_location("lev_mini_cfg", os.path.join(MINI, "cfg.py"))
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    knee = PB.section_at(RAF_T, 0.0)
    a = m.bolted_end_plate(knee, t=36.0, d_bolt=24, n_out=2, n_in=3, pitch=80.0, b_plate=220.0, web_doubler=6.0)
    b = A.ep_dict(knee, t=36.0, d_bolt=24, n_out=2, n_in=3, pitch=80.0, b_plate=220.0, web_doubler=6.0)
    assert a == b
    par = A.ep_params({"end_plate": b, "plate_b_mm": 220.0}, knee)
    assert (par["t"], par["d"], par["n_out"], par["n_in"], par["pitch_rule"]) == (36.0, 24, 2, 3, ("abs", 80.0))
    assert A.make_ep(par, knee) == dict(b, le_mm=b["le_mm"])


@pytest.fixture(scope="module")
def sized(mini_job, tmp_path_factory):
    import peb_autosize as A
    work = str(tmp_path_factory.mktemp("lev_work"))
    # the mini job is a test portal: its struts, brace ends, fly braces and anchorages are not declared, so their
    # rows stay 'not evaluated' whatever the sizes -- waived here (a gold job declares them)
    out = []
    for k in ("a", "b"):
        out.append(A.autosize(mini_job, SPEC, {}, work, name="sz_" + k, cfs_root=None, resize_secondary=False,
                              max_full_runs=4, waivers=(r"not evaluated",)))
    return None, out, work


def test_local_member_checks_match_the_engine(sized):
    import peb_autosize as A
    r0, out, work = sized
    run = os.path.join(work, "sz_a", "run")
    x = out[0]["history"][-1]["x"]
    lm = A.LocalModel(run, SPEC, {"members": x}, {})
    diffs = [abs(lm.element_dc(t, x)[0] - (lm.dump[t]["dc"] or 0.0)) for c in x for mid in lm.mem_of_const[c]
             for t in lm.el_of_mem[mid]]
    assert diffs and max(diffs) < 1e-9
    dem = A.knee_demand(lm, x)
    conn = lm.cfg["connections"]
    rows = A.knee_rows(lm, lm.cfg, dem, conn["beam_column"][A._knee_key(conn)], conn["knee_panel"])
    pk = [c for c in lm.pkg["connections"] if c["id"].startswith("conn-peb-knee")][0]
    assert [round(D / C, 6) for n, D, C in rows if C] == [round(r["dc"], 6) for r in pk["checks"]]


def test_autosize_passes_and_is_deterministic(sized):
    """The start design (the fixture's joints are undersized) fails; the sizer resizes members and joints to a design
    that passes, and a second run returns the same sizes, joints and mass."""
    _r0, (a, b), work = sized
    assert a["history"][0]["passed"] is False
    assert a["best"] and a["best"]["run"]["passed"] and a["best"]["it"] >= 1
    assert a["best"]["x"] != a["x_gold"]
    assert a["best"]["x"] == b["best"]["x"] and a["best"]["conn"] == b["best"]["conn"]
    assert a["best"]["total_kg"] == b["best"]["total_kg"]
    # the joints were re-designed for the new members (1.2 Mp of the new knee face, the apex, the shear keys)
    assert a["best"]["conn"] != a["history"][0]["conn"]


def test_floor_steps_never_go_below_the_floor():
    import peb_autosize as A
    x = {"COL_T": COL_T, "RAF_T": RAF_T, "RAF_P": RAF_P}
    sp = dict(SPEC, _floor=dict(x))
    g = [("RAF_P", "tf")]
    tf0 = A.dim(RAF_P, "tf")
    assert A.step_group(x, g, -1, sp) is None                   # at the floor: no lighter notch
    up = A.step_group(x, g, 1, sp)
    assert A.dim(up["RAF_P"], "tf") > tf0
    assert A.dim(A.step_group(up, g, -1, sp)["RAF_P"], "tf") == tf0
    assert A.dim(A.step_group(x, g, -1, SPEC)["RAF_P"], "tf") < tf0      # without a floor it may go lighter


def test_strengthen_only_keeps_the_gold_as_a_floor(mini_job, tmp_path_factory):
    """floor=True (the solar-ready strengthening of a published design): under an added roof load the sizer returns
    a passing design with no plate dimension, end-plate thickness or shear key below the gold's.  (The mini job
    declares its seismic weight, so the added load is roof imposed load, which IS 1893 7.3.2 leaves out of W.)"""
    import peb_autosize as A
    work = str(tmp_path_factory.mktemp("lev_floor"))
    r = A.autosize(mini_job, SPEC, {}, work, name="floor", cfs_root=None, resize_secondary=False, max_full_runs=4,
                   waivers=(r"not evaluated",), extra_overrides={"LR": 1.5}, floor=True)
    best = r["best"]
    assert best and best["run"]["passed"]
    for c, lab in best["x"].items():
        k, d = A.parse(lab)
        for dn in A.DIMS[k]:
            assert A.dim(lab, dn) >= A.dim(r["x_gold"][c], dn) - 1e-9, (c, dn)
    g, b = r["conn_gold"], best["conn"]
    for slot in g:
        if isinstance(g[slot], dict) and "t" in g[slot]:
            assert b[slot]["t"] >= g[slot]["t"], slot
        if isinstance(g[slot], dict) and g[slot].get("diag_t"):           # second wave: the knee diagonal too
            assert b[slot]["diag_t"] >= g[slot]["diag_t"], slot
        if isinstance(g[slot], dict) and g[slot].get("key"):
            ka, kb = g[slot]["key"], b[slot]["key"]
            assert kb == ka or 2 * kb[0] * kb[1] * (kb[2] + 50) >= 2 * ka[0] * ka[1] * (ka[2] + 50), slot


def test_study_variants_and_cumulative_ladder():
    """The study's variants: each lever alone from the strict design, the cumulative ladder in the waterfall order
    (compliant levers first, each step from the previous one), 'compliant' = the last compliant step, the market
    bundle last; levers that do not apply are n/a (rods outside a Zone II OCBF, deliverable joints on SMRF)."""
    import sys
    sys.path.insert(0, os.path.join(os.path.dirname(HERE), "scripts"))
    import peb_lever_jobs as J
    import peb_lever_study as L
    ex1 = {n: (kw, st) for n, kw, st, _ in L.variants_for(J.JOB_SPECS["IN_Ex1_PEB_factory_shed_tapered_Bengaluru"],
                                                         solar=True)}
    assert ex1["omrf_r3"][0] is None and ex1["rods"][0]["rods"]
    cum = [n for n in ex1 if n.startswith("cum:")]
    assert cum[0] == "cum:ltb_gradient" and ex1[cum[0]][0]["alias"] == "ltb_gradient"
    for a, b in zip(cum, cum[1:]):
        assert ex1[b][0]["start_from"] == a and set(ex1[a][0]["rules"]) <= set(ex1[b][0]["rules"])
    assert ex1["compliant"][0]["alias"] == "cum:thin_purlins"
    assert ex1["market"][0]["start_from"] == cum[-1] and ex1["market"][0]["market"] and ex1["market"][0]["rods"]
    assert ex1["market"][1].startswith("NOT") and ex1["cum:rods"][1] == "not compliant"
    assert ex1["solar_ready"][0]["solar_pv"] == 0.15
    ex4 = {n: (kw, st) for n, kw, st, _ in L.variants_for(J.JOB_SPECS["IN_Ex4_PEB_warehouse_SMRF_Zone4_NCR"])}
    assert ex4["joint_deliverable"][0] is None and ex4["rods"][0] is None and "solar_ready" not in ex4
    assert ex4["omrf_r3"][1] == "market practice, not compliant" and ex4["cum:omrf_r3"][1] == ex4["omrf_r3"][1]
    ex2 = {n: (kw, st) for n, kw, st, _ in L.variants_for(J.JOB_SPECS["IN_Ex2_PEB_GradeA_warehouse_multispan_Bhiwandi"])}
    assert ex2["cum:omrf_r3"][1].startswith("conflict")
