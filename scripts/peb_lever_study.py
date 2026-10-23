#!/usr/bin/env python3
"""peb_lever_study.py -- PEB-LEVERS (2026-10): how each Indian PEB practice / code reading changes the steel of a shed.

For a PEB gold (or an engineer's own PEB job with a job spec, scripts/peb_lever_jobs.py) this runs, all with the
deterministic auto-sizer steel_engine/peb_autosize.py:

  gold        the gold as published (its own take-off; no run)
  rerun       the gold sizes re-run on this engine with the strict rules (the first run of 'strict')
  strict      the auto-sized strict baseline: owner rulings D-T1 C1 = 1.0, D-T4 no rods, D-T7 1.2 Mp joints, O1
              1.2 Vd shear keys, H/240 with a brick dado, IS 811 purlins at Fy 240, collateral / PV out of 0.9DL
  each lever alone (auto-sized from the strict design):
              joint_deliverable, ltb_gradient, sway_H150_dado, base_key_analysis, rods, thin_purlins,
              collateral_in_uplift, omrf_r3 (seismic route) -- a lever that does not apply to the job is reported 'n/a'
  compliant   every lever marked compliant, together
  market      the market-practice bundle -- NOT COMPLIANT: MBMA roof live load 0.57 kN/m2, ordinary frames R 3 in any
              zone, the sheeting taken as bracing the purlin free flange, H/150 sway without the dado check, plus the
              lighter readings (deliverable joints, gradient C1, thin purlins, analysis base shear, rods in Zone II)
  solar_ready (IN_Ex1 only, --solar) the Ex1 shed auto-sized for 0.15 kN/m2 of rooftop PV, strict rules

and writes <work>/<job>/study.json, study.csv and study.html (kg/m2 of plan by group, governing check, change from
the strict baseline), and <work>/index.html over the jobs.

usage:
  python scripts/peb_lever_study.py --job IN_Ex1_PEB_factory_shed_tapered_Bengaluru [--job ...] \\
      --jobs-root /home/claude/gold_var/jobs_hr --work /home/claude/gold_var/study \\
      --cfs-root /home/claude/gold_var/cfs_fw [--published-root /home/claude/gold_var/jobs_hr] \\
      [--variants strict,joint_deliverable,...] [--max-runs 8] [--resume] [--solar]
  python scripts/peb_lever_study.py --render --work <dir>       # re-write the CSV / HTML from study.json files
One heavy analysis at a time: every full run is one child process, run sequentially.
"""
import argparse
import copy
import csv
import html
import json
import math
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path[:0] = [os.path.join(ROOT, "steel_engine"), HERE]

import peb_autosize as A          # noqa: E402
import peb_levers as PL           # noqa: E402
from peb_lever_jobs import JOB_SPECS   # noqa: E402

GROUPS = ("primary", "bracing", "crane", "canopy", "secondary", "connections")
COLORS = {"primary": "#ff8a3d", "bracing": "#e6b65c", "crane": "#8fb996", "canopy": "#7aa6c2",
          "secondary": "#9c9286", "connections": "#c97c5d"}
# design_status reasons that do not depend on the design (the report is not built during the study)
BASE_WAIVERS = (r"grounding record not available \(report not built\)",)

# the levers alone (run order) and the cumulative ladder (waterfall order: the compliant levers first, then the
# readings, then the not-compliant ones, the market-practice loads last)
LEVER_ORDER = ("ltb_gradient", "joint_deliverable", "sway_H150_dado", "thin_purlins", "base_key_analysis",
               "collateral_in_uplift", "omrf_r3", "rods")
CUM_ORDER = LEVER_ORDER + ("market",)
VARIANT_ORDER = (("gold", "rerun", "strict", "control") + LEVER_ORDER + tuple("cum:" + n for n in LEVER_ORDER) +
                 ("compliant", "market", "solar_ready"))
LABELS = {
    "gold": "Gold as published",
    "rerun": "Gold sizes, this engine (strict rules)",
    "strict": "Auto-sized strict baseline",
    "control": "Control: strict rules again, from the strict design (sizer resolution)",
    "joint_deliverable": "Joints for the deliverable moment (12.10.2.1)",
    "ltb_gradient": "LTB with the moment-gradient C1",
    "sway_H150_dado": "Sway H/150 + dado-top H/240",
    "base_key_analysis": "Shear keys for the analysis base shear",
    "rods": "Tension-rod X-bracing",
    "thin_purlins": "Thin G350 purlins / girts",
    "collateral_in_uplift": "Collateral / PV counted in 0.9DL rows",
    "omrf_r3": "Seismic route: OMRF R 3, no IS 18168",
    "compliant": "All compliant levers together",
    "market": "Market practice bundle (every lever + market loads)",
    "solar_ready": "Solar-ready: gold strengthened for 0.15 kN/m2 PV",
}


def label(name):
    if name.startswith("cum:"):
        return "+ " + LABELS[name[4:]]
    return LABELS[name]


def log(*a):
    print(*a, flush=True)


# ------------------------------------------------------------------------------------------- variants of a job
def omrf_patch(spec):
    """Brief-level seismic route OMRF_R3: ordinary moment frames R 3 (transverse) and ordinary braced frames R 4
    (longitudinal), no IS 18168."""
    ov = {}
    for c, d in (spec["seismic"].get("R_consts") or {}).items():
        ov[c] = 3.0 if d == "y" else 4.0
    patch = {"system": "OMRF+OCBF", "system_y": "OMRF", "system_x": "OCBF", "apply_is18168": False,
             "load_plan/seismic_summary/system": "OMRF+OCBF"}
    if str(spec["seismic"].get("zone")).upper() != "II":
        # second wave: let the comparison run past the preflight zone ban (pipeline.study_zone_ban_as_warning); the
        # design status keeps the ban, which the study waives (ZONE_WAIVERS) and reports as the code status
        patch["study_allow_banned_system"] = ("PEB lever study, seismic route OMRF_R3 in Zone %s: cost of compliance"
                                              % spec["seismic"]["zone"])
    return ov, patch


def _worst_status(sts):
    """The least compliant of a set of statuses (the status of a cumulative step)."""
    for key in ("NOT", "not compliant", "conflict", "unconservative", "reading"):
        for st in sts:
            if key in str(st):
                return st
    return "compliant"


def variants_for(spec, solar=False, ladder="full", control=False):
    """[(name, kwargs for autosize, status, note)] of a job; status: compliant / reading / not compliant / n/a.
    The levers alone start from the strict design; the cumulative steps ('cum:<lever>', the waterfall) add one lever
    at a time to the previous step, in CUM_ORDER (the compliant levers first, then the readings, then the not-compliant
    ones, the market-practice loads last), each starting from the previous step's design.  The last compliant step is
    'all compliant levers'; the last step is the market-practice bundle."""
    sz = spec["seismic"]
    zone, I = sz["zone"], float(sz.get("I") or 1.0)
    omrf = sz.get("route") == "OMRF"
    dado = spec.get("dado_height_mm")
    out = []
    levers = {}          # name -> (rules, status, note, flags) of the levers that apply

    def add(name, rules=None, status="compliant", note="", **kw):
        out.append((name, dict(rules=dict(rules or {}), **kw), status, note))

    add("strict", {}, "compliant", "owner rulings D-T1, D-T4, D-T7, O1; H/240 with the dado; IS 811 purlins Fy 240")
    if control:
        # second wave: the same rules again from the strict design -- what the sizer still finds with no lever is its
        # resolution (a lever's change smaller than this is within the sizer's noise)
        add("control", {}, "compliant", "strict rules again, from the strict design: the change is the sizer's "
                                        "resolution, not a lever", start_from="strict")
    if omrf:
        levers["joint_deliverable"] = ({"joint_demand": "deliverable"}, "compliant",
                                       PL.STATUS[("joint_demand", "deliverable")][1], {})
    else:
        out.append(("joint_deliverable", None, "n/a", "SMRF joints (IS 800 12.11.2.1 1.2 Mp, IS 18168 8.4 1.1 Ry Mp): no "
                                                        "deliverable-moment option; unchanged"))
    levers["ltb_gradient"] = ({"ltb_c1": "gradient"}, "compliant", PL.STATUS[("ltb_c1", "gradient")][1], {})
    if dado:
        levers["sway_H150_dado"] = ({"sway_limit": "H150_with_dado_check", "dado_height_mm": dado}, "compliant",
                                    PL.STATUS[("sway_limit", "H150_with_dado_check")][1], {})
    else:
        out.append(("sway_H150_dado", None, "n/a", "no brick dado: the column sway row is not the masonry row "
                                                   "(crane frame H/200 governs)"))
    levers["base_key_analysis"] = ({"base_shear_key": "analysis"}, "reading rejected by ruling O1",
                                   PL.STATUS[("base_shear_key", "analysis")][1], {})
    if zone == "II" and omrf:
        levers["rods"] = ({"bracing": "tension_rods"}, "not compliant", PL.STATUS[("bracing", "tension_rods")][1],
                          {"rods": True})
    else:
        out.append(("rods", None, "n/a", "refused: tension rods are offered on a Zone II OCBF only (zone %s)" % zone))
    levers["thin_purlins"] = ({"purlins": "thin_G350"}, "compliant", PL.STATUS[("purlins", "thin_G350")][1], {})
    levers["collateral_in_uplift"] = ({"collateral_in_uplift": True}, "old treatment (unconservative)",
                                      "collateral / PV also resist uplift in the 0.9DL rows (the treatment before the "
                                      "2026-10 first wave; the engine now leaves them out)", {})
    if omrf:
        out.append(("omrf_r3", None, "n/a", "the job is already an ordinary moment frame (route as briefed)"))
    else:
        ok_, lab_, note_ = PL.seismic_route_status(zone, I)
        levers["omrf_r3"] = ({}, lab_, note_, {"seismic_route": "OMRF_R3"})
    for name in LEVER_ORDER:
        if name in levers:
            r, st, nt, fl = levers[name]
            add(name, r, st, nt, **fl)
    if ladder == "short":
        # the short ladder (a study that would take too long): strict -> every compliant lever together (run from the
        # strict design) -> the market-practice bundle (every lever + the market loads, run from the compliant design)
        comp = [n for n in LEVER_ORDER if n in levers and levers[n][1] == "compliant"]
        rules, flags = {}, {}
        for n in comp:
            rules.update(levers[n][0])
            flags.update(levers[n][3])
        if len(comp) == 1:
            out.append(("compliant", {"alias": comp[0]}, "compliant", "every lever marked compliant (= %s)" % comp[0]))
        elif comp:
            add("compliant", rules, "compliant", "every lever marked compliant, together: " + " + ".join(comp),
                start_from="strict", **flags)
        sts = ["compliant"]
        for n in LEVER_ORDER:
            if n in levers and n not in comp:
                rules = dict(rules, **levers[n][0])
                flags = dict(flags, **levers[n][3])
                sts.append(levers[n][1])
        mk = dict(sway_limit="H150_no_dado_check", purlin_free_flange="sheeting_braced")
        if not dado:
            mk.pop("sway_limit")
        rules = dict(rules, **mk)
        rules.pop("dado_height_mm", None)
        flags = dict(flags, market=True, seismic_route="OMRF_R3" if not omrf else flags.get("seismic_route"))
        flags = {k: v for k, v in flags.items() if v}
        add("market", rules, "NOT COMPLIANT (market practice)",
            "every lever plus the market-practice loads: MBMA roof live 0.57 kN/m2 (IS 875-2: 0.75), ordinary frames "
            "R 3 / R 4 in any zone, the sheeting taken as bracing the purlin free flange, H/150 without the dado check "
            "(short ladder: run from the all-compliant design)", start_from="compliant" if comp else "strict", **flags)
        if solar:
            add("solar_ready", {}, "compliant", "the Ex1 gold strengthened for 0.15 kN/m2 rooftop PV (cfg D_roof_pv), "
                                                "strict rules: nothing lighter than the gold, a gold joint or purlin "
                                                "kept while it passes", solar_pv=0.15)
        return out
    # the cumulative ladder
    rules, flags, sts, prev, last_comp = {}, {}, [], "strict", None
    for name in CUM_ORDER:
        if name == "market":
            mk = dict(sway_limit="H150_no_dado_check", purlin_free_flange="sheeting_braced")
            if not dado:
                mk.pop("sway_limit")
            rules = dict(rules, **mk)
            rules.pop("dado_height_mm", None)
            flags = dict(flags, market=True, seismic_route="OMRF_R3" if not omrf else flags.get("seismic_route"))
            flags = {k: v for k, v in flags.items() if v}
            sts = sts + ["NOT COMPLIANT (market practice)"]
            note = ("all the levers above plus the market-practice loads: MBMA roof live 0.57 kN/m2 (IS 875-2: 0.75), "
                    "ordinary frames R 3 / R 4 in any zone, the sheeting taken as bracing the purlin free flange, "
                    "H/150 without the dado check")
            add("market", rules, sts[-1], note, start_from=prev, **flags)
            break
        if name not in levers:
            continue
        r, st, nt, fl = levers[name]
        rules = dict(rules, **r)
        flags = dict(flags, **fl)
        sts = sts + [st]
        cname = "cum:" + name
        add(cname, rules, _worst_status(sts), "cumulative: " + " + ".join(
            n for n in CUM_ORDER if n in levers and CUM_ORDER.index(n) <= CUM_ORDER.index(name)),
            start_from=prev, alias=name if prev == "strict" else None, **flags)
        prev = cname
        if _worst_status(sts) == "compliant":
            last_comp = cname
    if last_comp:
        out.append(("compliant", {"alias": last_comp}, "compliant", "every lever marked compliant, together (= %s)"
                    % last_comp))
    if solar:
        add("solar_ready", {}, "compliant", "the Ex1 gold strengthened for 0.15 kN/m2 rooftop PV (cfg D_roof_pv), strict "
                                            "rules: nothing lighter than the gold, a gold joint or purlin kept while it "
                                            "passes", solar_pv=0.15)
    return out


# ------------------------------------------------------------------------------------------- braces
def size_rods(strict_run_dir):
    """Rod diameter for the X-bracing: T = 2 max |N| of the strict design's braces (the X pair as two half-area bars,
    the real tension rod carries the panel force alone), the smallest IS 4000 size with Td >= T / 0.95."""
    pkg = json.load(open(os.path.join(strict_run_dir, "calc_package.json")))
    N = 0.0
    for m in pkg.get("members") or []:
        if (m.get("inputs") or {}).get("kind") == "brace":
            N = max(N, float(m["inputs"].get("P_comp_N") or 0.0), float(m["inputs"].get("P_tens_N") or 0.0))
    for d in PL.ROD_SIZES_MM:
        if PL.rod_tension_check(d, 2.0 * N)["dc"] <= 0.95:
            return PL.rod_label(d), 2.0 * N
    return PL.rod_label(PL.ROD_SIZES_MM[-1]), 2.0 * N


def size_ocbf_braces(strict_run_dir, gold_brace, R_old_x, R_new_x=4.0, K=0.5):
    """Brace section for the OMRF_R3 route (OCBF): the lightest section of the gold's family with KL/r <= 120 (IS 800
    12.7.2.1), not slender (12.7.2.4) and 0.8 Pd >= the strict design's brace compression x R_old / R_new
    (12.7.2.2).  Returns (label, note)."""
    import sections as S
    import india_is800 as I8
    pkg = json.load(open(os.path.join(strict_run_dir, "calc_package.json")))
    P, L = 0.0, 0.0
    for m in pkg.get("members") or []:
        inp = m.get("inputs") or {}
        if inp.get("kind") == "brace":
            P = max(P, float(inp.get("P_comp_N") or 0.0))
            L = max(L, float(inp.get("length_mm") or 0.0))
    P *= float(R_old_x) / float(R_new_x)
    fam = "".join(ch for ch in gold_brace.split("X")[0] if ch.isalpha())
    tube = fam in ("CHS", "NB")
    labels = S.list_chs() if tube else S.list_is808(fam)
    cands = []
    for lab in labels:
        if not str(lab).startswith(fam):
            continue
        try:
            p = S.props(lab, grade="YSt 310", process="HFS") if tube else S.props(lab)
        except Exception:
            continue
        cands.append((float(p.get("Mass_kg_m") or p["A"] * 7.85e-3), lab, p))
    cands.sort()
    for kg, lab, p in cands:
        r = min(p.get("rx") or 1e9, p.get("ry") or 1e9)
        if K * L / r > 120.0:
            continue
        fy = float(p.get("fy_MPa") or 250.0)
        if I8.section_class_table2(p, fy, loading="axial" if p.get("section_type") in ("CHS", "angle") else "bending")[
                "section_class"] == "slender":
            continue
        c = I8.compression_capacity(p, fy, KLz_mm=K * L, KLy_mm=K * L, process="HFS" if tube else None)
        if c.get("found") and 0.8 * c["Pd_N"] >= P:
            return lab, "KL/r %.0f <= 120, 0.8 Pd %.0f kN >= %.0f kN (strict brace force x %.2f / %.1f)" % (
                K * L / r, 0.8 * c["Pd_N"] / 1e3, P / 1e3, R_old_x, R_new_x)
    return gold_brace, "no lighter section found: gold brace kept"


# ------------------------------------------------------------------------------------------- one job
def design_changes(res):
    """What a strengthen-only variant changed from the gold: member constants, joints, purlins / girts."""
    best = res.get("best") or {}
    out = []
    for c, lab in sorted((best.get("x") or {}).items()):
        g = (res.get("x_gold") or {}).get(c)
        if g and g != lab:
            out.append("%s %s -> %s" % (c, g, lab))
    cg, cb = res.get("conn_gold") or {}, best.get("conn") or {}
    for slot in sorted(set(cg) | set(cb)):
        a, b = cg.get(slot), cb.get(slot)
        if a == b or not isinstance(a, dict) or not isinstance(b, dict):
            continue
        keys = [k for k in sorted(set(a) | set(b)) if a.get(k) != b.get(k) and not str(k).startswith("_")]
        if keys:
            out.append("joint %s: %s" % (slot, ", ".join("%s %s -> %s" % (k, a.get(k), b.get(k)) for k in keys)))
    sec = res.get("secondary") or {}
    for role in ("purlin", "girt"):
        r = sec.get(role) or {}
        g0 = (sec.get("gold") or {}).get(role)
        if r.get("section") and g0 and r["section"] != g0:
            out.append("%s %s -> %s (DC %.3f)" % (role, g0, r["section"], r.get("DC") or 0.0))
    return out


def solar_job(job_dir, spec, jobs_root, work):
    """The job the solar-ready variant is sized on (second wave): a copy of the job with spec['solar']['cfg_append']
    appended to its cfg.py (IN_Ex1: the IN_Ex5 gust-factor wind once the PV mass takes f1 below 1.0 Hz) and the
    evidence (retrieval_evidence.json, rag/) of spec['solar']['evidence_job'] laid over the job's own.  Without a
    'solar' entry the job itself is used."""
    import shutil
    so = spec.get("solar") or {}
    if not so.get("cfg_append"):
        return job_dir
    d = os.path.join(work, "_solar_job", os.path.basename(job_dir))
    if os.path.isdir(d):
        shutil.rmtree(d)
    shutil.copytree(job_dir, d, ignore=shutil.ignore_patterns("design", "figs", "report.html", "viewer_3d.html",
                                                              "model.std", "model_*.py", "__pycache__"))
    ev = os.path.join(jobs_root, so.get("evidence_job") or "", "")
    if so.get("evidence_job") and os.path.isdir(ev):
        shutil.copy2(os.path.join(ev, "retrieval_evidence.json"), os.path.join(d, "retrieval_evidence.json"))
        if os.path.isdir(os.path.join(ev, "rag")):
            shutil.copytree(os.path.join(ev, "rag"), os.path.join(d, "rag"), dirs_exist_ok=True)
    with open(os.path.join(d, "cfg.py"), "a", encoding="utf-8") as f:
        f.write(so["cfg_append"])
    return d


def kgm2(ton, area):
    out = {g: round(float((ton or {}).get(g) or 0.0) / area, 2) for g in GROUPS}
    out["total"] = round(sum(float((ton or {}).get(g) or 0.0) for g in GROUPS) / area, 2)
    return out


class _PersistentDict(dict):
    """The secondary-design cache of a job, kept on disk so that a resumed study does not redo the CFS runs."""

    def __init__(self, path):
        super().__init__()
        self.path = path
        try:
            self.update(json.load(open(path)))
        except (OSError, ValueError):
            pass

    def __setitem__(self, k, v):
        super().__setitem__(k, v)
        json.dump(dict(self), open(self.path, "w"), default=str)


def run_job(job, a, solar=False):
    spec = JOB_SPECS[job]
    job_dir = os.path.join(a.jobs_root, job)
    work = os.path.join(a.work, job)
    os.makedirs(work, exist_ok=True)
    study_p = os.path.join(work, "study.json")
    study = json.load(open(study_p)) if (a.resume and os.path.exists(study_p)) else {"job": job, "rows": {}}
    study.update(job=job, engine=os.path.join(ROOT, "steel_engine"), cfs_root=a.cfs_root,
                 started=study.get("started") or time.strftime("%Y-%m-%d %H:%M"))
    rows = study["rows"]
    # gold as published
    pub = os.path.join(a.published_root, job, "design", "calc_package.json")
    if os.path.exists(pub):
        ton = json.load(open(pub))["peb"]["tonnage"]
        rows["gold"] = {"name": "gold", "label": LABELS["gold"], "status": "published (owner rulings)",
                        "kg": ton["kg"], "area_m2": ton["plan_area_m2"], "kg_m2": kgm2(ton["kg"], ton["plan_area_m2"]),
                        "note": "the published gold package (%s)" % os.path.dirname(os.path.dirname(pub))}
    sec_p = os.path.join(work, "secondary_cache.json")
    sec_cache = _PersistentDict(sec_p)
    ladder = getattr(a, "ladder", "full") or "full"
    if study.get("ladder") and study["ladder"] != ladder:
        raise SystemExit("%s: the study in %s was run with --ladder %s" % (job, work, study["ladder"]))
    study["ladder"] = ladder
    vlist = variants_for(spec, solar=solar, ladder=ladder, control=bool(getattr(a, "control", False)))
    want = set(a.variants.split(",")) if a.variants else None
    strict = rows.get("strict")
    stopped = None
    for name, kw, status, note in vlist:
        if want and name not in want and not (name == "strict" and not strict):
            continue
        if a.resume and name in rows and rows[name].get("done"):
            log("== %s / %s: done (resume)" % (job, name))
            continue
        if kw is None:
            rows[name] = {"name": name, "label": label(name), "status": "n/a", "note": note, "done": True}
            continue
        if kw.get("alias"):
            # the first cumulative step is its lever alone; 'compliant' is the last compliant cumulative step
            src = rows.get(kw["alias"])
            if src and src.get("done"):
                rows[name] = dict(copy.deepcopy(src), name=name, label=label(name), status=status, note=note,
                                  alias_of=kw["alias"])
                study["rows"] = rows
                json.dump(study, open(study_p, "w"), indent=1, default=str)
            continue
        if budget_spent(a):
            # a resumable chunk: no new variant after --stop-after-min minutes (the run in hand is never cut)
            log("== %s: time budget of %s min reached before '%s'; re-run with --resume to continue"
                % (job, a.stop_after_min, name))
            stopped = name
            break
        t0 = time.time()
        rules = dict(kw["rules"])
        args = dict(cfs_root=a.cfs_root, waivers=BASE_WAIVERS, max_full_runs=a.max_runs, secondary_cache=sec_cache)
        extra_ov, patch, rods, Lr, free = {}, {}, None, None, False
        if kw.get("seismic_route") == "OMRF_R3" or kw.get("market"):
            if spec["seismic"].get("route") != "OMRF":
                ov, pt = omrf_patch(spec)
                extra_ov.update(ov)
                patch.update(pt)
        if kw.get("market"):
            extra_ov[spec["Lr_const"]] = PL.MARKET_PRACTICE["Lr_kNm2"]
            Lr = PL.MARKET_PRACTICE["Lr_kNm2"]
            free = True
        vjob_dir = job_dir
        if kw.get("solar_pv"):
            extra_ov["SOLAR_PV"] = float(kw["solar_pv"])
            args["extra_pv"] = float(kw["solar_pv"])
            args["floor"] = True                       # strengthening of the published gold: nothing lighter
            vjob_dir = solar_job(job_dir, spec, a.jobs_root, work)
        if name != "strict":
            if not strict or not strict.get("best_x"):
                rows[name] = {"name": name, "label": label(name), "status": status, "note": note,
                              "error": "no strict baseline to start from", "done": False}
                continue
            src = rows.get(kw.get("start_from") or "strict") or {}
            if not src.get("best_x"):
                src = strict                           # the previous step found no passing design
            args.update(start=src["best_x"], start_conn=src.get("best_conn"), calib=strict.get("calib"))
        if kw.get("rods"):
            rod, T = size_rods(os.path.join(a.work, job, "strict", "best"))
            PL.register_rod(rod)
            brace_c = spec["brace"]["const"]
            extra_ov[brace_c] = rod
            rods = [rod]
            note = note + "; rods %s (T = 2 max|N| = %.0f kN)" % (rod, T / 1e3)
        if patch.get("system_x") == "OCBF":
            gold_brace = A.read_constants(os.path.join(job_dir, "cfg.py"), [spec["brace"]["const"]])[spec["brace"]["const"]]
            Rx_old = A.read_constants(os.path.join(job_dir, "cfg.py"),
                                      [c for c, d in spec["seismic"]["R_consts"].items() if d == "x"])
            br, bnote = size_ocbf_braces(os.path.join(a.work, job, "strict", "best"), gold_brace,
                                         list(Rx_old.values())[0])
            if br != gold_brace and not rods:
                extra_ov[spec["brace"]["const"]] = br
            note = note + "; OCBF braces %s (%s)" % (br, bnote)
        if kw.get("market"):
            waivers = list(BASE_WAIVERS) + MARKET_WAIVERS
            args["waivers"] = tuple(waivers)
        elif kw.get("seismic_route") == "OMRF_R3" and spec["seismic"]["zone"] != "II":
            args["waivers"] = tuple(list(BASE_WAIVERS) + ZONE_WAIVERS)
        if kw.get("rods"):
            args["waivers"] = tuple(list(args["waivers"]) + ROD_WAIVERS)
        res = A.autosize(vjob_dir, spec, rules, work, name=name, extra_overrides=extra_ov or None,
                         cfg_patch=patch or None, rods=rods, Lr=Lr, free_flange=free, **args)
        best = res.get("best")
        row = {"name": name, "label": label(name), "status": status, "note": note, "rules": rules,
               "start_from": kw.get("start_from") or ("gold" if name in ("strict", "solar_ready") else "strict"),
               "extra_overrides": extra_ov, "cfg_patch": patch, "n_full_runs": res.get("n_full_runs"),
               "elapsed_s": round(time.time() - t0, 1), "secondary": res.get("secondary"), "done": True,
               "history": [{k: h.get(k) for k in ("it", "passed", "total_kg", "governing", "blocking", "elapsed_s")}
                           for h in res.get("history") or []]}
        if best:
            R = best["run"]
            area = R.get("plan_area_m2") or 1.0
            row.update(kg=R.get("tonnage_kg"), area_m2=area, kg_m2=kgm2(R.get("tonnage_kg"), area),
                       governing=R.get("governing"), waived=R.get("waived"), best_x=best["x"], best_conn=best["conn"],
                       members=best["x"])
        else:
            row["error"] = "no passing design within %d full runs" % a.max_runs
            last = (res.get("history") or [{}])[-1]
            row["last_blocking"] = last.get("blocking")
        if kw.get("solar_pv"):
            row["changed"] = design_changes(res)
            g = rows.get("gold") or {}
            if best and g.get("kg_m2"):
                row["extra_over_gold_kg_m2"] = round(row["kg_m2"]["total"] - g["kg_m2"]["total"], 2)
        if name == "strict":
            row["calib"] = res.get("calib")
            h0 = (res.get("history") or [None])[0]
            if h0:
                rows["rerun"] = {"name": "rerun", "label": LABELS["rerun"], "status": "strict rules",
                                 "kg": h0.get("tonnage_kg"), "kg_m2": kgm2(h0.get("tonnage_kg"), row.get("area_m2") or
                                                                           (rows.get("gold") or {}).get("area_m2") or 1.0),
                                 "governing": h0.get("governing"), "passed": h0.get("passed"),
                                 "blocking": h0.get("blocking"), "done": True,
                                 "note": "the gold's sizes and joints run on this engine with the strict rules"}
            strict = row
        rows[name] = row
        study["rows"] = rows
        json.dump(study, open(study_p, "w"), indent=1, default=str)
        render_job(study, work)
    st = rows.get("strict") or {}
    for r in rows.values():
        if r.get("kg_m2") and st.get("kg_m2"):
            r["delta_vs_strict_kg_m2"] = round(r["kg_m2"]["total"] - st["kg_m2"]["total"], 2)
            r["delta_vs_strict_pct"] = round(100.0 * r["delta_vs_strict_kg_m2"] / st["kg_m2"]["total"], 1)
    if stopped:
        study["stopped_before"] = stopped
        study.pop("finished", None)
    else:
        study.pop("stopped_before", None)
        study["finished"] = time.strftime("%Y-%m-%d %H:%M")
    json.dump(study, open(study_p, "w"), indent=1, default=str)
    render_job(study, work)
    return study


T_START = time.time()


def budget_spent(a):
    """True once the study has run for --stop-after-min minutes (0: no budget).  Used to cut a long study into
    resumable chunks that finish between variants."""
    lim = float(getattr(a, "stop_after_min", 0) or 0)
    return lim > 0 and (time.time() - T_START) > 60.0 * lim


# accepted non-compliances of the not-compliant variants (design_status reasons that the variant is about)
ZONE_WAIVERS = [r"(?i)table 9", r"(?i)not permitted in zone", r"(?i)zone_gate", r"(?i)12\.10\.1\.1", r"(?i)12\.7\.1\.1",
                r"(?i)ordinary .*zone"]
ROD_WAIVERS = [r"(?i)brace_KL_r", r"(?i)brace_compression", r"(?i)brace_tension_share", r"(?i)brace_conn",
               r"(?i)gusset_", r"(?i)brace_gross_yield", r"(?i)brace_not_slender", r"(?i)conn-brace-ROD",
               r"(?i)brace-ROD"]
MARKET_WAIVERS = ZONE_WAIVERS + ROD_WAIVERS


# ------------------------------------------------------------------------------------------- outputs
def _rows_sorted(study):
    return [study["rows"][k] for k in VARIANT_ORDER if k in study["rows"]]


def render_job(study, work):
    rows = _rows_sorted(study)
    st = study["rows"].get("strict") or {}
    for r in rows:
        if r.get("kg_m2") and st.get("kg_m2"):
            r["delta_vs_strict_kg_m2"] = round(r["kg_m2"]["total"] - st["kg_m2"]["total"], 2)
    with open(os.path.join(work, "study.csv"), "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["variant", "label", "status"] + ["%s_kg_m2" % g for g in GROUPS] +
                   ["total_kg_m2", "delta_vs_strict_kg_m2", "governing_check", "governing_dc", "full_runs", "note"])
        for r in rows:
            k = r.get("kg_m2") or {}
            g = r.get("governing") or [None, None, None, None]
            w.writerow([r["name"], r.get("label"), r.get("status")] + [k.get(x, "") for x in GROUPS] +
                       [k.get("total", ""), r.get("delta_vs_strict_kg_m2", ""),
                        ("%s %s %s" % (g[1], g[2], g[3] or "")).strip() if g[0] is not None else "",
                        round(g[0], 3) if g[0] is not None else "", r.get("n_full_runs", ""),
                        r.get("note") or r.get("error") or ""])
    open(os.path.join(work, "study.html"), "w").write(html_page([study]))


CSS = """
:root{--bg:#12100d;--panel:#181511;--panel-2:#1b1813;--bg3:#0c0a07;--line:#2e2820;--line-2:#3a3328;
--ink:#f0ebe4;--muted:#9c9286;--body:#c6beb2;--faint:#665e50;--accent:#ff8a3d;--accent-bright:#ffa15c;
--accent-dim:rgba(255,138,61,.15);--err:#ff6b6b;--ok:#46c993;--tool:#e6b65c;
--sans:system-ui,-apple-system,"Segoe UI",Roboto,sans-serif;--mono:"DM Mono","SFMono-Regular",Consolas,Menlo,monospace;
--r:10px;--r-sm:6px}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--ink);font:15px/1.55 var(--sans);-webkit-font-smoothing:antialiased}
main{max-width:1180px;margin:0 auto;padding:28px 16px 64px}
h1{font-size:1.45rem;font-weight:600;margin:.2rem 0 .3rem;letter-spacing:-.01em}
h2{font-size:1.1rem;font-weight:600;margin:2.2rem 0 .6rem}
.kicker{font:500 11px/1 var(--mono);letter-spacing:.16em;color:var(--accent);text-transform:uppercase}
p,li{color:var(--body)}
.muted{color:var(--muted);font-size:.86em}
.card{background:linear-gradient(180deg,var(--panel),var(--panel-2));border:1px solid var(--line);border-radius:12px;
padding:18px 18px 14px;margin:14px 0}
table{border-collapse:collapse;width:100%;font-size:.86rem}
th,td{border-bottom:1px solid var(--line);padding:6px 8px;text-align:right;vertical-align:top}
th{color:var(--muted);font-weight:500;font:500 11px/1.3 var(--mono);letter-spacing:.06em;text-transform:uppercase}
td.l,th.l{text-align:left}
tr.nc td{background:rgba(255,107,107,.06)}
tr.na td{color:var(--faint)}
.tag{display:inline-block;font:500 10.5px/1.6 var(--mono);padding:0 6px;border-radius:4px;border:1px solid var(--line-2);
color:var(--muted);white-space:nowrap}
.tag.ok{color:var(--ok);border-color:rgba(70,201,147,.35)}
.tag.nc{color:var(--err);border-color:rgba(255,107,107,.45)}
.tag.rd{color:var(--tool);border-color:rgba(230,182,92,.45)}
.legend{display:flex;flex-wrap:wrap;gap:14px;margin:6px 0 10px;font-size:.82rem;color:var(--body)}
.legend i{display:inline-block;width:11px;height:11px;border-radius:2px;margin-right:6px;vertical-align:-1px}
.wrap{overflow-x:auto}
svg text{font-family:var(--sans)}
.neg{color:var(--ok)}.pos{color:var(--err)}
"""


def _tag(status):
    s = str(status or "")
    cls = "nc" if ("NOT" in s or "not compliant" in s) else ("ok" if s.startswith(("compliant", "published", "strict",
                                                                                     "permitted")) else
                                                                ("" if s == "n/a" else "rd"))
    return '<span class="tag %s">%s</span>' % (cls, html.escape(s))


def _bars(rows):
    rows = [r for r in rows if r.get("kg_m2")]
    if not rows:
        return "<p class='muted'>No results yet.</p>"
    vmax = max(r["kg_m2"]["total"] for r in rows) * 1.08
    W, lw, rh = 1100, 330, 26
    H = 18 + rh * len(rows)
    bw = W - lw - 70
    out = ['<svg viewBox="0 0 %d %d" width="100%%" role="img" aria-label="kg per m2 of plan by variant">' % (W, H)]
    step = 10 if vmax > 40 else 5
    for v in range(0, int(vmax) + 1, step):
        x = lw + bw * v / vmax
        out.append('<line x1="%.1f" y1="4" x2="%.1f" y2="%d" stroke="#2e2820"/>' % (x, x, H - 2))
        out.append('<text x="%.1f" y="%d" fill="#665e50" font-size="10" text-anchor="middle">%d</text>' % (x, H, v))
    for i, r in enumerate(rows):
        y = 6 + i * rh
        nc = "NOT" in str(r.get("status")) or "not compliant" in str(r.get("status"))
        out.append('<text x="%d" y="%.1f" fill="%s" font-size="12" text-anchor="end">%s</text>'
                   % (lw - 10, y + rh * 0.62, "#ff6b6b" if nc else "#c6beb2", html.escape(r.get("label") or r["name"])))
        x = lw
        for g in GROUPS:
            v = r["kg_m2"].get(g) or 0.0
            w = bw * v / vmax
            if w > 0:
                out.append('<rect x="%.1f" y="%.1f" width="%.1f" height="%d" fill="%s"><title>%s %.2f kg/m2</title></rect>'
                           % (x, y + 3, w, rh - 8, COLORS[g], g, v))
            x += w
        out.append('<text x="%.1f" y="%.1f" fill="#f0ebe4" font-size="12">%.1f</text>' % (x + 6, y + rh * 0.62,
                                                                                        r["kg_m2"]["total"]))
    out.append("</svg>")
    return "".join(out)


def _waterfall(study):
    """The cumulative ladder as a waterfall: the strict total, then the change of each added lever."""
    R = study["rows"]
    steps = [("strict", R.get("strict"))] + [(n, R.get("cum:" + n) if n != "market" else R.get("market"))
                                             for n in CUM_ORDER]
    if study.get("ladder") == "short":
        steps = [("strict", R.get("strict")), ("all compliant", R.get("compliant")), ("market", R.get("market"))]
    steps = [(n, r) for n, r in steps if r and r.get("kg_m2")]
    if len(steps) < 2:
        return ""
    W, H, top, bot, lw = 1100, 300, 16, 92, 46
    vmax = max(r["kg_m2"]["total"] for n, r in steps) * 1.1
    bw = (W - lw - 10) / len(steps)
    y = lambda v: top + (H - top - bot) * (1.0 - v / vmax)
    out = ['<svg viewBox="0 0 %d %d" width="100%%" role="img" aria-label="cumulative change of kg per m2">' % (W, H)]
    step = 10 if vmax > 40 else 5
    for v in range(0, int(vmax) + 1, step):
        out.append('<line x1="%d" y1="%.1f" x2="%d" y2="%.1f" stroke="#2e2820"/>' % (lw, y(v), W - 10, y(v)))
        out.append('<text x="%d" y="%.1f" fill="#665e50" font-size="10" text-anchor="end">%d</text>' % (lw - 6, y(v) + 3, v))
    prev = None
    for i, (n, r) in enumerate(steps):
        v = r["kg_m2"]["total"]
        x = lw + i * bw + bw * 0.18
        w = bw * 0.64
        nc = "NOT" in str(r.get("status")) or "not compliant" in str(r.get("status"))
        if prev is None:
            y0, y1, col = y(v), y(0), "#ff8a3d"
            txt = "%.1f" % v
        else:
            y0, y1 = y(max(prev, v)), y(min(prev, v))
            col = "#46c993" if v <= prev else "#ff6b6b"
            txt = "%+.2f" % (v - prev)
        out.append('<rect x="%.1f" y="%.1f" width="%.1f" height="%.1f" fill="%s"%s><title>%s: %.2f kg/m2</title></rect>'
                   % (x, y0, w, max(y1 - y0, 1.0), col, ' fill-opacity="0.55"' if nc else "",
                      html.escape(r.get("label") or n), v))
        out.append('<text x="%.1f" y="%.1f" fill="#f0ebe4" font-size="11" text-anchor="middle">%s</text>'
                   % (x + w / 2, y0 - 5, txt))
        lab = "strict" if n == "strict" else ("market" if n == "market" else n.replace("_", " "))
        out.append('<text x="%.1f" y="%d" fill="%s" font-size="10.5" text-anchor="end" transform="rotate(-35 %.1f %d)">%s'
                   '</text>' % (x + w / 2, H - bot + 14, "#ff6b6b" if nc else "#c6beb2", x + w / 2, H - bot + 14,
                                html.escape(lab)))
        if prev is not None:
            px = lw + (i - 1) * bw + bw * 0.82
            out.append('<line x1="%.1f" y1="%.1f" x2="%.1f" y2="%.1f" stroke="#665e50" stroke-dasharray="3 3"/>'
                       % (px, y(prev), x, y(prev)))
        prev = v
    out.append("</svg>")
    return "".join(out)


def _table(rows):
    h = ['<div class="wrap"><table><tr><th class="l">variant</th><th class="l">status</th>'] + \
        ["<th>%s</th>" % g for g in GROUPS] + ["<th>total kg/m²</th><th>vs strict</th><th class='l'>governing check</th></tr>"]
    for r in rows:
        k = r.get("kg_m2") or {}
        s = str(r.get("status") or "")
        cls = "nc" if ("NOT" in s or "not compliant" in s) else ("na" if s == "n/a" else "")
        g = r.get("governing")
        gov = ("%.3f &middot; %s %s" % (g[0], html.escape(str(g[2])), html.escape(str(g[3] or "")[:70]))) if g else \
            html.escape(r.get("note") if s == "n/a" else (r.get("error") or ""))
        d = r.get("delta_vs_strict_kg_m2")
        ds = "" if d is None or r["name"] == "strict" else '<span class="%s">%+.2f</span>' % ("neg" if d < 0 else "pos", d)
        h.append('<tr class="%s"><td class="l">%s<div class="muted">%s</div></td><td class="l">%s</td>%s<td><b>%s</b></td>'
                 '<td>%s</td><td class="l muted">%s</td></tr>'
                 % (cls, html.escape(r.get("label") or r["name"]),
                    html.escape((r.get("note") or "")[:220]) if s != "n/a" else "", _tag(s),
                    "".join("<td>%s</td>" % (("%.2f" % k[g_]) if k.get(g_) else "&ndash;") for g_ in GROUPS),
                    ("%.2f" % k["total"]) if k.get("total") else "&ndash;", ds, gov))
    h.append("</table></div>")
    return "".join(h)


def _members(study):
    rows = [r for r in _rows_sorted(study) if r.get("members")]
    if not rows:
        return ""
    consts = sorted({c for r in rows for c in r["members"]})
    h = ['<div class="wrap"><table><tr><th class="l">variant</th>'] + ["<th class='l'>%s</th>" % c for c in consts] + \
        ["<th class='l'>purlin / girt</th></tr>"]
    for r in rows:
        sec = r.get("secondary") or {}
        pg = "%s / %s" % ((sec.get("purlin") or {}).get("section", ""), (sec.get("girt") or {}).get("section", ""))
        h.append("<tr><td class='l'>%s</td>%s<td class='l'>%s</td></tr>" % (
            html.escape(r["label"]), "".join("<td class='l' style='font-family:var(--mono);font-size:.8rem'>%s</td>"
                                             % html.escape(r["members"].get(c, "")) for c in consts), html.escape(pg)))
    h.append("</table></div>")
    for r in rows:
        if r.get("changed") is not None:
            h.append("<p class='muted'>%s: changed from the gold%s</p><ul>%s</ul>" % (
                html.escape(r["label"]), "" if r.get("extra_over_gold_kg_m2") is None else
                " (%+.2f kg/m²)" % r["extra_over_gold_kg_m2"],
                "".join("<li class='muted'>%s</li>" % html.escape(c) for c in r["changed"]) or "<li>nothing</li>"))
    return "".join(h)


def html_page(studies):
    parts = ["<!doctype html><html lang='en'><head><meta charset='utf-8'><meta name='viewport' "
             "content='width=device-width,initial-scale=1'><title>PEB lever study</title><style>%s</style></head><body><main>"
             % CSS,
             "<div class='kicker'>Steltic India &middot; PEB variations study</div>",
             "<h1>How each Indian PEB practice changes the steel of a shed</h1>",
             "<p>Each variant is auto-sized by the same deterministic sizer (steel_engine/peb_autosize.py): every member, "
             "station, joint, Section 12 check, analysis gate, sway limit and &lambda;<sub>cr</sub> &ge; 5 must pass "
             "(india_seismic_gates.design_status), and the lightest plates found are kept. kg/m² of plan area. "
             "Rows in red are <b>not compliant</b> with the Indian Standards as written; they are shown because they "
             "are common practice, so a design engineer can see what each shortcut buys.</p>",
             "<div class='legend'>%s</div>" % "".join("<span><i style='background:%s'></i>%s</span>" % (COLORS[g], g)
                                                      for g in GROUPS)]
    for st in studies:
        rows = _rows_sorted(st)
        parts.append("<h2>%s</h2>" % html.escape(st["job"]))
        parts.append("<div class='card'>%s</div>" % _bars(rows))
        wf = _waterfall(st)
        if wf:
            parts.append("<div class='card'><div class='muted'>Cumulative: each lever added to the previous step "
                         "(compliant levers first; faded bars are not compliant), kg/m²</div>%s</div>" % wf)
        parts.append("<div class='card'>%s</div>" % _table(rows))
        parts.append("<details class='card'><summary class='muted'>member sizes and purlins of each variant</summary>%s"
                     "</details>" % _members(st))
    parts.append("<p class='muted'>Basis and limits: base plates, anchors and base gussets keep the gold sizes (only "
                 "shear keys are resized); member taper layout, splice positions, purlin spacing and fly-brace layout "
                 "are the gold's; plate thicknesses from a commercial list (IS 1730 is not in the corpus); bolts and "
                 "welds are not weighed (as in the gold take-off). Generated by scripts/peb_lever_study.py.</p>")
    parts.append("</main></body></html>")
    return "".join(parts)


def markdown_tables(studies):
    """Markdown summary: per job kg/m2 (total) of the strict design, each lever alone and each cumulative step, with
    the change from the strict design / the previous step, the governing check, the full runs and the run time."""
    out = []
    for st in studies:
        R = st["rows"]
        s0 = (R.get("strict") or {}).get("kg_m2", {}).get("total")
        out.append("### %s\n" % st["job"])
        out.append("| variant | status | kg/m² | vs strict | governing check | runs | time |")
        out.append("|---|---|---|---|---|---|---|")
        prev = s0
        for r in _rows_sorted(st):
            k = (r.get("kg_m2") or {}).get("total")
            g = r.get("governing")
            gov = ("%.3f %s" % (g[0], str(g[2])[:48])) if g else (r.get("error") or ("" if r.get("status") != "n/a"
                                                                                       else str(r.get("note"))[:60]))
            dv = "" if (k is None or s0 is None or r["name"] in ("strict",)) else "%+.2f" % (k - s0)
            if r["name"].startswith("cum:") or r["name"] == "market" or (
                    st.get("ladder") == "short" and r["name"] == "compliant"):
                dv += "" if (k is None or prev is None) else " (step %+.2f)" % (k - prev)
                prev = k if k is not None else prev
            tm = ("%.0f min" % (r["elapsed_s"] / 60.0)) if r.get("elapsed_s") and not r.get("alias_of") else \
                ("= %s" % r["alias_of"] if r.get("alias_of") else "")
            out.append("| %s | %s | %s | %s | %s | %s | %s |" % (
                r.get("label") or r["name"], r.get("status") or "", "%.2f" % k if k is not None else "-", dv, gov,
                r.get("n_full_runs") or "", tm))
            if r.get("changed") is not None:
                out.append("| ↳ changed from the gold (%s kg/m²) | | | | %s | | |" % (
                    "%+.2f" % r["extra_over_gold_kg_m2"] if r.get("extra_over_gold_kg_m2") is not None else "?",
                    "; ".join(r["changed"]) or "nothing"))
        out.append("")
    return "\n".join(out)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--job", action="append", default=[])
    ap.add_argument("--jobs-root", default="/home/claude/gold_var/jobs_hr")
    ap.add_argument("--work", default="/home/claude/gold_var/study")
    ap.add_argument("--cfs-root", default="/home/claude/gold_var/cfs_fw")
    ap.add_argument("--published-root", default="/home/claude/gold_var/jobs_hr")
    ap.add_argument("--variants", default="")
    ap.add_argument("--max-runs", type=int, default=8)
    ap.add_argument("--resume", action="store_true")
    ap.add_argument("--solar", action="store_true", help="IN_Ex1: add the solar-ready variant (0.15 kN/m2 PV)")
    ap.add_argument("--control", action="store_true",
                    help="add the control variant: strict rules again from the strict design (the sizer's resolution)")
    ap.add_argument("--ladder", choices=("full", "short"), default="full",
                    help="full: the cumulative ladder one lever at a time; short: strict -> all compliant levers -> "
                         "market bundle (for a study that would otherwise take too long)")
    ap.add_argument("--render", action="store_true")
    ap.add_argument("--stop-after-min", type=float, default=0.0,
                    help="start no new variant after this many minutes (a resumable chunk; continue with --resume)")
    a = ap.parse_args()
    os.makedirs(a.work, exist_ok=True)
    if not a.render:
        for job in a.job:
            if budget_spent(a):
                log("== %s: not started (time budget reached); re-run with --resume" % job)
                continue
            run_job(job, a, solar=a.solar and job.startswith("IN_Ex1_"))
    studies = []
    for job in sorted(os.listdir(a.work)):
        p = os.path.join(a.work, job, "study.json")
        if os.path.exists(p):
            st = json.load(open(p))
            render_job(st, os.path.join(a.work, job))
            studies.append(st)
    open(os.path.join(a.work, "index.html"), "w").write(html_page(studies))
    json.dump({s["job"]: {k: {kk: r.get(kk) for kk in ("label", "status", "kg_m2", "governing", "delta_vs_strict_kg_m2",
                                                        "note", "n_full_runs", "elapsed_s", "error", "start_from", "alias_of",
                                                        "extra_over_gold_kg_m2", "changed", "members")}
                          for k, r in s["rows"].items()} for s in studies},
              open(os.path.join(a.work, "study_all.json"), "w"), indent=1, default=str)
    open(os.path.join(a.work, "study_tables.md"), "w").write(markdown_tables(studies))
    log("wrote %s" % os.path.join(a.work, "index.html"))


if __name__ == "__main__":
    main()
