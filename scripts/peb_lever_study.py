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
      --cfs-root /home/claude/gold_var/cfs_head [--published-root /home/claude/gold_ref/jobs_hr] \\
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

VARIANT_ORDER = ("gold", "rerun", "strict", "joint_deliverable", "ltb_gradient", "sway_H150_dado", "base_key_analysis",
                 "rods", "thin_purlins", "collateral_in_uplift", "omrf_r3", "compliant", "market", "solar_ready")
LABELS = {
    "gold": "Gold as published",
    "rerun": "Gold sizes, this engine (strict rules)",
    "strict": "Auto-sized strict baseline",
    "joint_deliverable": "Joints for the deliverable moment (12.10.2.1)",
    "ltb_gradient": "LTB with the moment-gradient C1",
    "sway_H150_dado": "Sway H/150 + dado-top H/240",
    "base_key_analysis": "Shear keys for the analysis base shear",
    "rods": "Tension-rod X-bracing",
    "thin_purlins": "Thin G350 purlins / girts",
    "collateral_in_uplift": "Collateral / PV counted in 0.9DL rows",
    "omrf_r3": "Seismic route: OMRF R 3, no IS 18168",
    "compliant": "All compliant levers together",
    "market": "Market practice bundle",
    "solar_ready": "Solar-ready: auto-sized for 0.15 kN/m2 PV",
}


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
    return ov, patch


def variants_for(spec, solar=False):
    """[(name, kwargs for autosize, status, note)] of a job; status: compliant / reading / not compliant / n/a."""
    sz = spec["seismic"]
    zone, I = sz["zone"], float(sz.get("I") or 1.0)
    omrf = sz.get("route") == "OMRF"
    dado = spec.get("dado_height_mm")
    out = []

    def add(name, rules=None, status="compliant", note="", **kw):
        out.append((name, dict(rules=dict(rules or {}), **kw), status, note))

    add("strict", {}, "compliant", "owner rulings D-T1, D-T4, D-T7, O1; H/240 with the dado; IS 811 purlins Fy 240")
    if omrf:
        add("joint_deliverable", {"joint_demand": "deliverable"}, "compliant", PL.STATUS[("joint_demand", "deliverable")][1])
    else:
        out.append(("joint_deliverable", None, "n/a", "SMRF joints (IS 800 12.11.2.1 1.2 Mp, IS 18168 8.4 1.1 Ry Mp): no "
                                                        "deliverable-moment option; unchanged"))
    add("ltb_gradient", {"ltb_c1": "gradient"}, "compliant", PL.STATUS[("ltb_c1", "gradient")][1])
    if dado:
        add("sway_H150_dado", {"sway_limit": "H150_with_dado_check", "dado_height_mm": dado}, "compliant",
            PL.STATUS[("sway_limit", "H150_with_dado_check")][1])
    else:
        out.append(("sway_H150_dado", None, "n/a", "no brick dado: the column sway row is not the masonry row "
                                                   "(crane frame H/200 governs)"))
    add("base_key_analysis", {"base_shear_key": "analysis"}, "reading rejected by ruling O1",
        PL.STATUS[("base_shear_key", "analysis")][1])
    if zone == "II" and omrf:
        add("rods", {"bracing": "tension_rods"}, "not compliant", PL.STATUS[("bracing", "tension_rods")][1],
            rods=True)
    else:
        out.append(("rods", None, "n/a", "refused: tension rods are offered on a Zone II OCBF only (zone %s)" % zone))
    add("thin_purlins", {"purlins": "thin_G350"}, "compliant", PL.STATUS[("purlins", "thin_G350")][1])
    add("collateral_in_uplift", {"collateral_in_uplift": True}, "old treatment (unconservative)",
        "collateral / PV also resist uplift in the 0.9DL rows (the treatment before the 2026-10 first wave; the "
        "engine now leaves them out)")
    if omrf:
        out.append(("omrf_r3", None, "n/a", "the job is already an ordinary moment frame (route as briefed)"))
    else:
        ok_, lab_, note_ = PL.seismic_route_status(zone, I)
        add("omrf_r3", {}, lab_, note_, seismic_route="OMRF_R3")
    comp_rules = {"ltb_c1": "gradient", "purlins": "thin_G350"}
    if omrf:
        comp_rules["joint_demand"] = "deliverable"
    if dado:
        comp_rules.update(sway_limit="H150_with_dado_check", dado_height_mm=dado)
    add("compliant", comp_rules, "compliant", "every lever marked compliant: %s" % ", ".join(sorted(comp_rules)))
    mk = dict(comp_rules, joint_demand="deliverable", base_shear_key="analysis", sway_limit="H150_no_dado_check",
              purlin_free_flange="sheeting_braced")
    mk.pop("dado_height_mm", None)
    if not dado:
        mk.pop("sway_limit")
    kw = {"market": True, "rods": bool(zone == "II" and omrf)}
    if kw["rods"]:
        mk["bracing"] = "tension_rods"
    add("market", mk, "NOT COMPLIANT (market practice)",
        "MBMA roof live 0.57 kN/m2 (IS 875-2: 0.75); ordinary frames R 3 / R 4 in any zone; sheeting taken as bracing "
        "the purlin free flange; H/150 without the dado check; deliverable joints, gradient C1, thin purlins, "
        "analysis base shear%s" % (", rods" if kw["rods"] else ""), **kw)
    if solar:
        add("solar_ready", {}, "compliant", "the Ex1 shed with 0.15 kN/m2 rooftop PV (cfg D_roof_pv), strict rules",
            solar_pv=0.15)
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
def kgm2(ton, area):
    out = {g: round(float((ton or {}).get(g) or 0.0) / area, 2) for g in GROUPS}
    out["total"] = round(sum(float((ton or {}).get(g) or 0.0) for g in GROUPS) / area, 2)
    return out


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
    sec_cache = {}
    vlist = variants_for(spec, solar=solar)
    want = set(a.variants.split(",")) if a.variants else None
    strict = rows.get("strict")
    for name, kw, status, note in vlist:
        if want and name not in want and not (name == "strict" and not strict):
            continue
        if a.resume and name in rows and rows[name].get("done"):
            log("== %s / %s: done (resume)" % (job, name))
            continue
        if kw is None:
            rows[name] = {"name": name, "label": LABELS[name], "status": "n/a", "note": note, "done": True}
            continue
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
        if kw.get("solar_pv"):
            extra_ov["SOLAR_PV"] = float(kw["solar_pv"])
            args["extra_pv"] = float(kw["solar_pv"])
        if name != "strict":
            if not strict or not strict.get("best_x"):
                rows[name] = {"name": name, "label": LABELS[name], "status": status, "note": note,
                              "error": "no strict baseline to start from", "done": False}
                continue
            args.update(start=strict["best_x"], start_conn=strict.get("best_conn"), calib=strict.get("calib"))
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
        res = A.autosize(job_dir, spec, rules, work, name=name, extra_overrides=extra_ov or None,
                         cfg_patch=patch or None, rods=rods, Lr=Lr, free_flange=free, **args)
        best = res.get("best")
        row = {"name": name, "label": LABELS[name], "status": status, "note": note, "rules": rules,
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
    study["finished"] = time.strftime("%Y-%m-%d %H:%M")
    json.dump(study, open(study_p, "w"), indent=1, default=str)
    render_job(study, work)
    return study


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
        parts.append("<div class='card'>%s</div>" % _table(rows))
        parts.append("<details class='card'><summary class='muted'>member sizes and purlins of each variant</summary>%s"
                     "</details>" % _members(st))
    parts.append("<p class='muted'>Basis and limits: base plates, anchors and base gussets keep the gold sizes (only "
                 "shear keys are resized); member taper layout, splice positions, purlin spacing and fly-brace layout "
                 "are the gold's; plate thicknesses from a commercial list (IS 1730 is not in the corpus); bolts and "
                 "welds are not weighed (as in the gold take-off). Generated by scripts/peb_lever_study.py.</p>")
    parts.append("</main></body></html>")
    return "".join(parts)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--job", action="append", default=[])
    ap.add_argument("--jobs-root", default="/home/claude/gold_var/jobs_hr")
    ap.add_argument("--work", default="/home/claude/gold_var/study")
    ap.add_argument("--cfs-root", default="/home/claude/gold_var/cfs_head")
    ap.add_argument("--published-root", default="/home/claude/gold_ref/jobs_hr")
    ap.add_argument("--variants", default="")
    ap.add_argument("--max-runs", type=int, default=8)
    ap.add_argument("--resume", action="store_true")
    ap.add_argument("--solar", action="store_true", help="IN_Ex1: add the solar-ready variant (0.15 kN/m2 PV)")
    ap.add_argument("--render", action="store_true")
    a = ap.parse_args()
    os.makedirs(a.work, exist_ok=True)
    if not a.render:
        for job in a.job:
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
                                                        "note", "n_full_runs", "elapsed_s", "error")}
                          for k, r in s["rows"].items()} for s in studies},
              open(os.path.join(a.work, "study_all.json"), "w"), indent=1, default=str)
    log("wrote %s" % os.path.join(a.work, "index.html"))


if __name__ == "__main__":
    main()
