"""
pipeline.py  --  the design entry point the agent runs. ONE straight-through call (NO user-review
pause). Do NOT hand-write report.html or your own model/design scripts.

    import pipeline
    name = "<the building name the user gave you>"
    res = pipeline.design_and_report(name, cfg)    # sanity -> DEMAND envelope -> figures -> report.html
    print(res)                                     # {model_valid, demands_written, figures, report_html, design_dir, root}

You DETERMINE the joints / base fixity explicitly and STATE them in the report, but you do NOT pause
to ask the user to approve the model. (build_and_preview(name, cfg) remains available as an OPTIONAL
self-review that builds just the 3 figures -- it is not a required hold.)

The framework does the mechanics (contract/AGENT_START.md): it generates the IS 800 Table 4 / IS 1893
combinations from YOUR cfg['load_plan'] (every load and code value retrieved from the RAG), runs the second-order
analysis and the response-spectrum analysis, envelopes the member forces per combination, runs the IS 800 member
checks (india_is800.member_check_is800, Sections 7-9) and the Section 12 system checks
(india_is800_s12.section12_checks), designs the declared connections, and writes calc_package.json and the report.
YOU choose the system, the model, the sections and the connection geometry, and iterate.  All outputs go to the
building's job folder: <jobs root>/<name>/ (STEEL_BUILDER_JOBS; design/, figs/, report.html, STATUS.engine.md).

Unusual geometry / non-rigid joints: the parametric builder makes a rectangular grid of rigid
elasticBeamColumn members. To model anything else (custom nodes, sloped roofs, per-member moment
releases, etc.), set cfg["custom_build"] = a function custom_build(cfg, transf) that builds the
OpenSees model and returns the standard info dict {cm, present, z, NF, ele:[(tag,kind,sec,n1,n2)]}
using engine3d.ntag(i,j,k)/mtag(k); the whole pipeline then runs on your model unchanged.
"""
import os, json, sys, subprocess, copy

_HERE = os.path.dirname(os.path.abspath(__file__))     # .../engine
_REPO = os.path.dirname(_HERE)                          # repo root (steel_builder)
for _p in (_HERE, _REPO):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import engine3d as E


ENGINE_STATUS_MARK = "<!-- engine-generated: india_seismic_gates.design_status (pipeline.py) -->"


def _status_md_engine_owned(path):
    """STATUS.md may be (re)written by the engine only when absent or when its first line marks it engine-generated
    (the marker, or the pre-H44 engine header '# <name> -- design status: <STATUS>')."""
    import re as _re
    if not os.path.exists(path):
        return True
    try:
        with open(path, encoding="utf-8", errors="replace") as f:
            first = f.readline().strip()
    except Exception:
        return False
    return first == ENGINE_STATUS_MARK or bool(
        _re.match(r"^# .+ -- design status: (COMPLETE|PARTIAL|EXAMPLE_ONLY)$", first))


def _root(name):
    """Per-building solution folder -- ALL outputs (cfg, design, figs, report) land here.
    Routed to the removable jobs folder via STEEL_BUILDER_JOBS (set by the MCP server) so a fresh
    agent cannot see prior jobs; falls back to the repo root for standalone/dev use."""
    base = os.environ.get("STEEL_BUILDER_JOBS") or _REPO
    return os.path.join(base, name)


def build_and_preview(name, cfg=None):
    """OPTIONAL self-review: build the OpenSees model + the 3 reviewer figures and return the figure
    paths + modelling assumptions. NOT a required user hold -- you may inspect the figures yourself,
    but proceed straight to design_and_report (just STATE the joints explicitly in the report)."""
    if cfg is not None:
        E.CFG[name] = copy.deepcopy(cfg)   # freeze the analysed model: the report renders exactly this cfg
    if name not in E.CFG:
        raise SystemExit("cfg '%s' is not registered -- pass cfg=<your building dict>." % name)
    c = E.CFG[name]
    root = _root(name); os.makedirs(root, exist_ok=True)
    try:
        import plot_model as PM
        figs = PM.figures(name, os.path.join(root, "figs"))
    except Exception as ex:
        figs = "figures failed: %s" % ex
    base = c.get("base", "fixed")
    has_releases = bool(c.get("releases"))
    if c.get("custom_build"):
        joints = ("CUSTOM model -- you defined the nodes/elements and any joint releases yourself in "
                  "custom_build(cfg, transf).")
    elif has_releases:
        joints = ("Beam-to-column and brace joints are RIGID / continuous EXCEPT the per-member moment "
                  "releases you set in cfg['releases'] (pinned / simple-shear connections at those "
                  "members). Interior gravity framing leans only if cfg['lean_gravity'] is set.")
    else:
        joints = ("ALL beam-to-column and brace joints are RIGID / continuous (elasticBeamColumn) -- "
                  "there are NO per-member moment releases. Interior gravity framing leans only if "
                  "cfg['lean_gravity'] is set. (Use cfg['releases'] for pinned / simple-shear joints.)")
    return {"name": name, "root": root, "figures": figs,
            "base_fixity": base, "joint_assumption": joints, "joints_have_releases": has_releases,
            "NOTE": ("Joint fixity is a KEY modelling decision -- state it EXPLICITLY in the report. "
                     "Record exactly what you made the base joints (%s) and the internal member "
                     "connections (see joint_assumption) and whether each came from the user's information "
                     "or is a default you chose. You do NOT pause for the user -- set "
                     "cfg['releases'] / cfg['base'] / cfg['lean_gravity'] or a custom_build as needed and "
                     "call design_and_report." % base)}


def design_and_report(name, cfg=None, do_report=True):
    """Run the full design (no user-review pause): register cfg, run preflight -> analysis -> combinations ->
    IS 800 member + Section 12 checks -> figures -> HTML report, all in process, writing to the job folder
    <jobs root>/<name> (STEEL_BUILDER_JOBS)."""
    if cfg is not None:
        E.CFG[name] = copy.deepcopy(cfg)   # freeze the analysed model: the report renders exactly this cfg
    if name not in E.CFG:
        raise SystemExit("cfg '%s' is not registered -- pass cfg=<your building dict>." % name)

    root = _root(name); os.makedirs(root, exist_ok=True)
    out = {"name": name, "root": root}
    # R22 preflight: cheap cfg lint BEFORE any solve (units, factors vs system, drift limit vs Ie,
    # height limits, model/diaphragm declarations). Findings print and return; ERRORs mean the cfg
    # is mis-declared -- fix them first rather than debugging analysis output.
    try:
        import preflight as _PF
        _pf = _PF.check(E.CFG.get(name))
        out["preflight"] = _pf
        print(_PF.render(_pf))
        _pf_err = [m for s, m in (_pf or []) if s == "ERROR"]
        if _pf_err:
            out["blocked"] = True
            out["error"] = "preflight ERRORs — fix before design_and_report (wind gate / Ta / load_plan)"
            print("[pipeline] BLOCKED by preflight ERRORs:\n- " + "\n- ".join(_pf_err))
            return out
    except Exception as _pfe:
        out["preflight"] = [("WARN", "preflight failed: %s" % _pfe)]
    E.clear_caches()   # fresh per-run modal/elf memo so design + report share this run's solves

    # 1) engineering sanity-check suite
    r = E.report(name)
    out["model_valid"] = bool(r.get("allp"))
    import consistency as _CC                                   # early units/geometry heads-up (e.g. story heights in ft)
    out["geometry_warnings"] = _CC._geometry_issues(E.CFG.get(name))

    # 2) India load_plan combinations + per-member DEMAND envelope (NO capacities -- agent/RAG)
    import design_pipeline as DP
    if E._india_job(E.CFG.get(name)):
        try:     # the resolved load plan is part of the package (provenance hash); rewritten every run (H43, L-03)
            json.dump(DP._jsonable(E.CFG[name].get("load_plan") or {}), open(os.path.join(root, "load_plan.json"), "w"), indent=1)
        except Exception:
            pass
    out["demands_written"] = bool(DP.design(name, outdir=os.path.join(root, "design")))
    out["design_dir"] = os.path.join(root, "design")

    # 3) reviewer-grade figures (geometry / orientation / deformed)
    try:
        import plot_model as PM
        out["figures"] = PM.figures(name, os.path.join(root, "figs"))
    except Exception as ex:
        out["figures"] = "skipped (%s)" % ex

    # 3b) standalone OpenSees model files for the user to check independently:
    #     model_opensees.py (DYNAMIC -- mass/period/seismic) and model_static.py (STATIC -- gravity force diagrams)
    try:
        out["model_files"] = E.export_model(cfg, root, name=name)
    except Exception as ex:
        out["model_files"] = "skipped (%s)" % ex
    try:
        import static_model as SM
        out["model_static"] = SM.export_static_model(cfg, root, name=name)
    except Exception as ex:
        out["model_static"] = "skipped (%s)" % ex

    # 4) the HTML report (10-section + appendices) -> steel_builder/<name>/report.html
    if do_report:
        import report as RPT
        out["report_html"] = RPT.build_report(name, root=root)
        # 5) India: the COMPLETE authority is re-evaluated with the rendered report (grounding table, US residue);
        #    the package status is refreshed and the report re-rendered once when it changed.
        if E._india_job(cfg):
            try:
                import india_seismic_gates as G
                cp = os.path.join(root, "design", "calc_package.json")
                pkg = json.load(open(cp))
                st = G.design_status(cfg, pkg, job_dir=root)
                new_st = G.status_record(st)    # RR-BUG-4: ordered by class, element rows grouped, no class dropped
                if new_st != pkg.get("design_status"):
                    pkg["design_status"] = new_st
                    json.dump(pkg, open(cp, "w"), indent=1)
                    out["report_html"] = RPT.build_report(name, root=root)
                out["design_status"] = new_st
                # H44 (E9): the engine writes STATUS.engine.md; STATUS.md belongs to the package and is only
                # (re)written when absent or itself engine-generated
                # RR-BUG-4: the ordered / grouped summary first (every reason class), then every reason in class order
                sm = G.summarize_reasons(st["reasons"], limit=None)
                body = ("%s\n# %s -- design status: %s\n\nAuthority: %s\n\n" % (ENGINE_STATUS_MARK, name,
                                                                           st["status"].upper(), st["authority"])
                        + "Open reasons (%d; classes %s):\n" % (len(st["reasons"]), ", ".join(
                            "%s %d" % kv for kv in sm["classes_raw"].items()))
                        + "".join("- %s\n" % r for r in sm["reasons"]))
                if len(sm["reasons"]) < len(st["reasons"]):
                    body += "\nAll open reasons, ungrouped (%d):\n" % len(st["reasons"]) + "".join(
                        "- %s\n" % r for c in G.REASON_CLASSES for r in st["reasons"] if G.reason_class(r) == c)
                with open(os.path.join(root, "STATUS.engine.md"), "w") as f:
                    f.write(body)
                out["status_file"] = os.path.join(root, "STATUS.engine.md")
                if _status_md_engine_owned(os.path.join(root, "STATUS.md")):
                    with open(os.path.join(root, "STATUS.md"), "w") as f:
                        f.write(body)
            except Exception as ex:
                out["design_status_error"] = str(ex)

    # End-of-run reminder the agent sees in the tool output, right before it replies to the user.
    out["NEXT_STEP"] = ("MANDATORY before you finish: (a) the model must be COMPLETE (model_complete must PASS -- every "
                        "element modelled, no missing floor beams) and you must run consistency.check(name) and reconcile "
                        "every flag (including a missing cfg.py); ALSO CONFIRM report Figure 2 (member orientation, "
                        "web/depth ticks) rendered -- if it reads 'not available', run plot_model.figures(name) and "
                        "re-render report.build_report before finishing; then (b) END YOUR REPLY with this closing note "
                        "to the user, VERBATIM (do not reword it and do not add other offers):\n"
                        "\"Several figures are OFF-by-default, to reduce the time to render the report. Once the design "
                        "is completed, ask me to generate these items and add them to the report (may take several "
                        "minutes to render). Want to try different lateral restraint locations or systems? Want to do "
                        "an optimization run to reduce member sizes? Tell me what you would like to change in the "
                        "building and I'm on it.\"\n"
                        "(For your own reference, NOT to be listed to the user unless they ask: the OFF-by-default "
                        "figures are cfg['force_diagrams'] (~20-30 s), cfg['force_summary'] (~20-30 s), "
                        "cfg['mode_figures'] (~12 s), cfg['deformed_shape_figure'], cfg['section_color_figure'] and "
                        "cfg['appendix_case_figures'] -- set the flag(s) and re-render report.build_report.) "
                        "(c) The report is at jobs/<name>/report.html and the app serves it; give that path -- do "
                        "NOT copy it anywhere. (d) india_seismic_gates.design_status must report 'complete'; "
                        "otherwise list every open reason it returns (the run ends PARTIAL).")
    print("\n" + "=" * 72 + "\n>> NEXT STEP (do not skip): " + out["NEXT_STEP"] + "\n" + "=" * 72)
    return out


def design_units(name, cfg_units, joints=None, do_report=True):
    """X04 (HR-D-13): several seismically separated units in one job.  Each unit runs as its own sub-job
    <jobs root>/<name>/units/<unit>/ (design_and_report); the IS 1893 7.11.3 separation of every declared joint is
    computed from the two units' 7.11.1 displacements at the matching levels; one combined STATUS (worst unit status +
    joint checks), units_index.html and units_summary.json are written in <jobs root>/<name>/.
    joints = [{"units": [u1, u2], "direction": "X"|"Y", "gap_mm": ..., "same_floor_levels": None|True|False,
    "levels": {u: k}, "base_mm": {u: mm}, "level_tol_mm": 50}] -- see multi_unit.py."""
    import multi_unit as MU
    return MU.design_units(name, cfg_units, joints, do_report=do_report)


if __name__ == "__main__":
    for nm in (sys.argv[1:] or ["B02"]):
        print(design_and_report(nm))
