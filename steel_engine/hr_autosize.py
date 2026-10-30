"""hr_autosize.py -- third wave (2026-10): a deterministic auto-sizer for the hot-rolled (non-PEB) jobs, used to
re-size the IN_Ex7 ... IN_Ex20 golds to the Indian section families.

A job is sizable when its cfg.py declares, at the top level:

    SECTIONS = {group: label}               member groups -> section label (the sizer rewrites this literal)
    SIZING_GROUPS = {group: spec}           how each group is sized (role, families, built-up fallback, ...)
    GRADE_BY_SECTION = {key: grade}         optional: per-section IS 2062 grade (rewritten: E350 heavy columns)
    CONNECTIONS = {kind: {key: spec}}       optional: declared connection geometry (rewritten by the designers)

and uses SECTIONS[...] wherever a member section is chosen (cfg['custom_sections'] from custom_sections(SECTIONS),
cfg['grade_by_section'] from GRADE_BY_SECTION, cfg['connections'] from CONNECTIONS).  SIZING_GROUPS[group]:

    role       'beam' | 'column' | 'brace' | 'strut' | 'link' (EBF link beam) | 'fixed' (never resized)
    families   rolled families tried in this order of preference, e.g. ['MB', 'WB'] (IS 808), ['CHS'] (IS 1161),
               ['HB', 'WB', 'MB'] (columns), ['ISA'], ['MC'] -- default by role (FAMILIES_BY_ROLE)
    grades     IS 2062 grades tried in order (columns: ['E250 B0', 'E350 B0']); rolled E250 is preferred, then
               rolled E350, then the built-up fallback ('E350 for heavy columns')
    built_up   None | 'box' | 'welded_I': the fallback when no rolled section of the families passes
    stiff      'I' | 'A' | None: the stiffness the drift / sway predictor keeps (moment frames 'I', braces 'A')
    min_depth_mm / max_depth_mm / min_bf_mm / max_mass_kg_m: optional limits (fabrication, detailing)
    same_as    another group: always takes that group's section (e.g. a gantry strut line)

How it works (deterministic: sorted iteration, PYTHONHASHSEED 0 in every child run):

 1. probe       -- the cfg is executed once with a distinct probe label per group (a registered clone of the
                   group's section) and its model builder is called: element tag -> group.
 2. full run    -- the cfg is executed with SECTIONS / GRADE_BY_SECTION / CONNECTIONS replaced (AST rewrite of the
                   top-level literals) and the HR pipeline runs without the report in a child process.  The run
                   captures, for every element, the exact member-check inputs (india_is800.member_check_is800) and the
                   Section 12 model data (india_is800_s12.section12_checks); the design status authority
                   (india_seismic_gates.design_status) decides pass / fail.
 3. local sizing -- with the forces of that run frozen, each group takes the lightest candidate of its families
                   for which every element passes the exact IS 800 member checks within the group's margin, and the
                   section stiffness the drift / sway / deflection ratios of the run require (a proportional
                   predictor); the whole proposal is then put through the engine's Section 12 checks (SCWB, panel
                   zones, IS 18168 Table 2, brace and link rules ...) and every group a member-level Section 12 row
                   fails is stepped up until they pass.
 4. connections -- the declared connection geometry of every group is re-designed for the new sections
                   (fin plates and brace ends against the engine's own capacity functions; bases, splices and moment
                   joints by first-guess rules, then stepped up from the failing rows of the verification run).
 5. verify      -- a full run of the proposal.  A failure tightens the margin of the groups it names (members,
                   stiffness) or steps up the connection that failed; the loop repeats.  Stops when a passing design
                   no longer changes, or at the iteration cap; the lightest passing design is kept.

Mass: the engine's take-off of the modelled members (design/takeoff.json, kg/m2 of floor area); connections are not
in that figure (as in every hot-rolled gold).

CLI:
    python hr_autosize.py worker <run_dir>              one full run of <run_dir>/variant.json (child process)
    python hr_autosize.py size <job_dir> --work <dir>   the sizing loop (resumable; state in <dir>/state.json)
    python hr_autosize.py write <job_dir> --work <dir>  write the best passing design into <job_dir>/cfg.py
"""
from __future__ import annotations

import ast
import contextlib
import copy
import io
import json
import math
import os
import pickle
import pprint
import re
import shutil
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ENGINE_ROOT = os.path.dirname(HERE)
PY = sys.executable
STEEL_KG_MM3 = 7.85e-6

# commercial plate thicknesses (IS 1730 is not in the corpus: the thicknesses the golds already use)
PLATES_MM = (8.0, 10.0, 12.0, 14.0, 16.0, 18.0, 20.0, 22.0, 25.0, 28.0, 32.0, 36.0, 40.0, 45.0, 50.0, 56.0, 63.0)

FAMILIES_BY_ROLE = {
    "beam": ["MB", "WB"],                   # IS 808 medium / wide flange beams
    "link": ["MB", "WB", "HB"],             # EBF link beams: compact rolled I (IS 18168 11.1)
    "column": ["HB", "WB", "MB"],           # IS 808 column (H) sections first
    "brace": ["CHS"],                       # IS 1161 tubes: OCBF only (SCBF / EBF braces must be IS 2062
                                            # E250B, IS 800 12.8.2.1 / IS 18168 5.2: their jobs declare HB / WB / MB)
    "strut": ["MB", "WB", "HB"],
    "gantry": ["MB", "WB"],
    "channel": ["MC"],
    "angle": ["ISA"],
}
BUILT_UP_BY_ROLE = {"beam": "welded_I", "link": "welded_I", "column": "box", "brace": None, "strut": None}
STIFF_BY_ROLE = {"beam": "I", "link": "I", "column": "I", "brace": "A", "strut": "A", "gantry": None}
LOG = []


def log(*a):
    s = " ".join(str(x) for x in a)
    LOG.append(s)
    print(s, flush=True)


# =================================================================================================== catalogue
def _S():
    import sections as S
    return S


def rolled(family):
    """Labels of a rolled family from the engine's tables, lightest first: IS 808 (MB, WB, HB, MC, ISA, NPB, WPB,
    ...) or IS 1161 (CHS)."""
    S = _S()
    fam = family.upper()
    if fam == "CHS":
        labs = [l for l in S.list_chs() if l.upper().startswith("CHS")]
    else:
        labs = [l for l in S.list_is808(fam) if _family_of(l) == fam]
    out = []
    for l in labs:
        try:
            out.append((mass_kg_m(l), l))
        except Exception:
            continue
    return [l for _, l in sorted(out)]


def _family_of(label):
    m = re.match(r"^(ISA|CHS|BOX|WI|MB|WB|HB|MC|NPB|WPB|PBP|LB|JB|SC|LC|JC|MPC)", str(label).upper())
    return m.group(1) if m else None


def family_of(label):
    return _family_of(label)


_BOX = re.compile(r"^BOX(\d+(?:\.\d+)?)X(\d+(?:\.\d+)?)X(\d+(?:\.\d+)?)(?:X(\d+(?:\.\d+)?))?$")
_WI = re.compile(r"^WI(\d+(?:\.\d+)?)X(\d+(?:\.\d+)?)X(\d+(?:\.\d+)?)X(\d+(?:\.\d+)?)$")


def _fmt(v):
    v = float(v)
    return ("%d" % round(v)) if abs(v - round(v)) < 1e-6 else ("%g" % v)


def box_label(B, D, tf, tw=None):
    """BOX<D>X<B>X<t> (tf = tw) or BOX<D>X<B>X<tf>X<tw>: welded box from IS 2062 plates, depth D (in the plane of
    the major axis) first, as the golds' labels (BOX450X400X25: 450 deep, 400 wide) and the rolled I labels."""
    if tw is None or abs(float(tw) - float(tf)) < 1e-9:
        return "BOX%sX%sX%s" % (_fmt(D), _fmt(B), _fmt(tf))
    return "BOX%sX%sX%sX%s" % (_fmt(D), _fmt(B), _fmt(tf), _fmt(tw))


def wi_label(D, bf, tf, tw):
    return "WI%sX%sX%sX%s" % tuple(_fmt(v) for v in (D, bf, tf, tw))


def parse_built_up(label):
    """('box', (B, D, tf, tw)) for BOX<D>X<B>X<tf>[X<tw>] | ('welded_I', (D, bf, tf, tw)) | None."""
    u = str(label).upper()
    m = _BOX.match(u)
    if m:
        D, B, tf = (float(x) for x in m.groups()[:3])
        tw = float(m.group(4)) if m.group(4) else tf
        return "box", (B, D, tf, tw)
    m = _WI.match(u)
    if m:
        return "welded_I", tuple(float(x) for x in m.groups())
    return None


def register(label, source=None):
    """Register a built-up label (BOX / WI) in sections.CUSTOM when it is not there; rolled labels are left alone."""
    S = _S()
    if S.normalize_label(label) in S.CUSTOM:
        return
    pb = parse_built_up(label)
    if not pb:
        return
    kind, d = pb
    if kind == "box":
        S.register_box(label, d[0], d[1], d[2], d[3], source=source or (
            "built-up welded box from IS 2062 plates: flanges %s x %s, webs %s x %s (third wave sizer)"
            % (_fmt(d[0]), _fmt(d[2]), _fmt(d[1] - 2 * d[2]), _fmt(d[3]))))
    else:
        S.register_welded_I(label, d[0], d[1], d[2], d[3], source=source or (
            "welded plate I from IS 2062 plates: flanges %s x %s, web %s x %s (third wave sizer)"
            % (_fmt(d[1]), _fmt(d[2]), _fmt(d[0] - 2 * d[2]), _fmt(d[3]))))


def custom_sections(sections):
    """cfg['custom_sections'] entries for every built-up label in SECTIONS (dict or list of labels)."""
    labs = sections.values() if isinstance(sections, dict) else sections
    out = {}
    for lab in sorted(set(labs)):
        pb = parse_built_up(lab)
        if not pb:
            continue
        kind, d = pb
        if kind == "box":
            out[lab] = {"type": "box", "B_mm": d[0], "D_mm": d[1], "tf_mm": d[2], "tw_mm": d[3],
                        "source": "built-up welded box, IS 2062 plates: flanges %s x %s, webs %s x %s"
                                  % (_fmt(d[0]), _fmt(d[2]), _fmt(d[1] - 2 * d[2]), _fmt(d[3]))}
        else:
            out[lab] = {"type": "welded_I", "D_mm": d[0], "bf_mm": d[1], "tf_mm": d[2], "tw_mm": d[3],
                        "source": "welded plate I, IS 2062 plates: flanges %s x %s, web %s x %s"
                                  % (_fmt(d[1]), _fmt(d[2]), _fmt(d[0] - 2 * d[2]), _fmt(d[3]))}
    return out


def cap_channel(girder):
    """The lightest IS 808 MC channel whose depth is at least the girder's flange width (web horizontal on the top
    flange of a gantry girder: the usual Indian capped gantry)."""
    bf = float(props(girder)["bf"])
    for lab in rolled("MC"):
        if float(props(lab)["d"]) >= bf - 1e-6:
            return lab
    return rolled("MC")[-1]


def capped_flange(girder, channel):
    """Top-flange surge system of a capped gantry girder (cfg['crane']['top_flange_cap']): the top flange (tf b^3/12,
    tf b^2/4) plus the channel about its own major axis (web horizontal): Iy = tf b^3/12 + Ixx,channel and
    Zpy = tf b^2/4 + Zp,channel (IS 808 properties of both)."""
    p, c = props(girder), props(channel)
    tf, b = float(p["tf"]), float(p["bf"])
    Iy = tf * b ** 3 / 12.0 + float(c["Ix"])
    Zpy = tf * b ** 2 / 4.0 + float(c["Zx"])
    return {"Iy_mm4": Iy, "Zpy_mm3": Zpy,
            "cite": "%s cap (web horizontal) on the %s top flange: Iy = tf b^3/12 + Ixx,%s = %.1f x %.0f^3/12 + %.3g = "
                    "%.3g mm4; Zpy = tf b^2/4 + Zp,%s = %.3g mm3 (IS 808 properties)"
                    % (channel, girder, channel, tf, b, float(c["Ix"]), Iy, channel, Zpy)}


def props(label):
    register(label)
    return _S().props(label)


def mass_kg_m(label):
    pb = parse_built_up(label)
    if pb:
        kind, d = pb
        if kind == "box":
            B, D, tf, tw = d
            A = 2 * B * tf + 2 * (D - 2 * tf) * tw
        else:
            D, bf, tf, tw = d
            A = 2 * bf * tf + (D - 2 * tf) * tw
        return A * STEEL_KG_MM3 * 1000.0
    p = _S().props(label)
    m = p.get("Mass_kg_m")
    return float(m) if m else float(p["A"]) * STEEL_KG_MM3 * 1000.0


def built_up_catalogue(kind, *, min_depth=None, max_depth=None, square=True):
    """Generated built-up candidates (lightest first).  Boxes: B = D from 250 to 800 mm in 50 mm steps (square, the
    golds' practice), plate t with (B - 2t)/t >= 6; welded I: D 300-1200 mm (50 mm steps), bf 150-500 mm, tf / tw
    from PLATES_MM with tw <= tf, bf/tf <= 2 x 13.6 (no slender outstand), d/tw <= 100."""
    out = []
    if kind == "box":
        for B in range(250, 801, 50):
            if min_depth and B < min_depth - 1e-6 or max_depth and B > max_depth + 1e-6:
                continue
            for t in PLATES_MM:
                if t > 63 or (B - 2 * t) / t < 6.0:
                    continue
                lab = box_label(B, B, t)
                out.append((mass_kg_m(lab), lab))
    else:
        for D in range(300, 1201, 50):
            if min_depth and D < min_depth - 1e-6 or max_depth and D > max_depth + 1e-6:
                continue
            for bf in range(150, 501, 25):
                if bf > D:
                    continue
                for tf in PLATES_MM:
                    if tf > 40 or bf / tf > 27.2 or bf / tf < 6:
                        continue
                    for tw in PLATES_MM:
                        if tw > tf or (D - 2 * tf) / tw > 100 or tw > 25:
                            continue
                        lab = wi_label(D, bf, tf, tw)
                        out.append((mass_kg_m(lab), lab))
    return [l for _, l in sorted(out)]


def candidates(spec, current=None):
    """[(label, grade, tier)] for a group, in the order of preference: rolled E250 (families in order, each family
    lightest first; merged by mass), then rolled E350 (columns), then the built-up fallback (E350 for columns)."""
    role = spec.get("role", "beam")
    fams = spec.get("families") or FAMILIES_BY_ROLE.get(role, ["MB", "WB"])
    grades = spec.get("grades") or (["E250 B0", "E350 B0"] if role == "column" else [None])
    bu = spec.get("built_up", BUILT_UP_BY_ROLE.get(role))
    rolled_labs = []
    for f in fams:
        rolled_labs += rolled(f)
    rolled_labs = sorted(set(rolled_labs), key=lambda l: (mass_kg_m(l), l))
    rolled_labs = [l for l in rolled_labs if _limits_ok(spec, l)]
    out = []
    tier = 0
    for g in grades:
        if g is not None and family_of(rolled_labs[0] if rolled_labs else "") == "CHS":
            g = None
        out += [(l, g, tier) for l in rolled_labs]
        tier += 1
    if bu:
        g = grades[-1]
        labs = built_up_catalogue(bu, min_depth=spec.get("min_depth_mm"), max_depth=spec.get("max_depth_mm"))
        out += [(l, g, tier) for l in labs if _limits_ok(spec, l)]
    return out


def _limits_ok(spec, lab):
    try:
        p = props(lab)
    except Exception:
        return False
    if spec.get("min_depth_mm") and float(p.get("d") or 0) < spec["min_depth_mm"] - 1e-6:
        return False
    if spec.get("max_depth_mm") and float(p.get("d") or 1e9) > spec["max_depth_mm"] + 1e-6:
        return False
    if spec.get("min_bf_mm") and float(p.get("bf") or 0) < spec["min_bf_mm"] - 1e-6:
        return False
    if spec.get("max_mass_kg_m") and mass_kg_m(lab) > spec["max_mass_kg_m"] + 1e-9:
        return False
    if spec.get("allow") and not any(re.match(a, lab) for a in spec["allow"]):
        return False
    return True


# =================================================================================================== cfg rewrite
def literal_text(name, value, width=118):
    return "%s = %s\n" % (name, pprint.pformat(value, width=width - len(name) - 3, sort_dicts=False))


def read_literals(path_or_src, names):
    """The values of top-level literal assignments NAME = <literal> (ast.literal_eval)."""
    src = path_or_src
    if os.path.exists(str(path_or_src)):
        src = open(path_or_src, encoding="utf-8").read()
    tree = ast.parse(src)
    out = {}
    for node in tree.body:
        if isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name) \
                and node.targets[0].id in names:
            out[node.targets[0].id] = ast.literal_eval(node.value)
    return out


def rewrite_source(src, values):
    """Replace the text of top-level assignments NAME = <literal> by the pretty-printed literals of `values` (comments
    elsewhere kept).  Every name must be found."""
    tree = ast.parse(src)
    spans = {}
    for node in tree.body:
        if isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name) \
                and node.targets[0].id in values:
            spans[node.targets[0].id] = (node.lineno, node.end_lineno)
    miss = sorted(set(values) - set(spans))
    if miss:
        raise KeyError("cfg.py: no top-level assignment for %s" % miss)
    lines = src.splitlines(keepends=True)
    for name, (a, b) in sorted(spans.items(), key=lambda kv: -kv[1][0]):
        lines[a - 1:b] = [literal_text(name, values[name])]
    return "".join(lines)


# =================================================================================================== run folders
_SKIP_FILES = {"report.html", "viewer_3d.html", "model_opensees.py", "model_static.py", "model.std", "run_stdout.txt",
               "run_summary.json", "STATUS.md", "STATUS.engine.md", "load_plan.json", "cfg.pass1.py", "SOLUTION.md",
               "compliance_comparison.json", "strengthening_option.json"}
_SKIP_DIRS = {"design", "figs", "units", "unitB_link", "unitC_gym", "__pycache__", "secondary"}


def prepare_run_dir(job_dir, run_dir, cfg_text=None):
    os.makedirs(run_dir, exist_ok=True)
    for f in sorted(os.listdir(job_dir)):
        src, dst = os.path.join(job_dir, f), os.path.join(run_dir, f)
        if os.path.isdir(src):
            if f == "rag" and not os.path.lexists(dst):
                os.symlink(os.path.abspath(src), dst)
            continue
        if f in _SKIP_FILES:
            continue
        shutil.copy2(src, dst)
    if cfg_text is not None:
        open(os.path.join(run_dir, "cfg.py"), "w", encoding="utf-8").write(cfg_text)
    return run_dir


def _child_env():
    env = dict(os.environ)
    env.update(PYTHONHASHSEED="0", PYTHONDONTWRITEBYTECODE="1", MPLBACKEND="Agg")
    return env


def run_child(args, cwd, timeout, log_path=None):
    t0 = time.time()
    with open(log_path or os.devnull, "w") as fo:
        r = subprocess.run(args, cwd=cwd, env=_child_env(), stdout=fo, stderr=subprocess.STDOUT, timeout=timeout)
    return r.returncode, round(time.time() - t0, 1)


def _install_paths(run_dir):
    for p in (HERE, ENGINE_ROOT, run_dir):
        if p not in sys.path:
            sys.path.insert(0, p)


def exec_cfg(path, overrides=None, name="cfg_mod"):
    """Execute a cfg.py with its top-level literals replaced (AST), returning the module."""
    import types
    src = open(path, encoding="utf-8").read()
    if overrides:
        src = rewrite_source(src, overrides)
    mod = types.ModuleType(name)
    mod.__file__ = os.path.abspath(path)
    exec(compile(src, os.path.abspath(path), "exec"), mod.__dict__)
    return mod


# =================================================================================================== probe
def probe(job_dir, sections):
    """element tag -> group: the cfg is executed with a distinct probe label per group (a registered clone of the
    group's section, label '<section>#P<n>') and its model builder is called."""
    S = _S()
    import engine3d as E
    E.activate_si_units()
    plabs = {}
    for k, (g, lab) in enumerate(sorted(sections.items())):
        register(lab)
        pl = "%s#P%d" % (lab, k)
        S.CUSTOM[S.normalize_label(pl)] = dict(S.props(lab))
        plabs[g] = pl
    with contextlib.redirect_stdout(io.StringIO()):
        mod = exec_cfg(os.path.join(job_dir, "cfg.py"), {"SECTIONS": plabs})
        cfg = mod.cfg
        info = cfg["custom_build"](cfg, "Linear")
    back = {S.normalize_label(v): g for g, v in plabs.items()}
    out, kinds = {}, {}
    for (t, kind, sec, n1, n2) in info["ele"]:
        g = back.get(S.normalize_label(sec))
        if g is not None:
            out[int(t)] = g
            kinds[int(t)] = kind
    return out, kinds


# =================================================================================================== worker
def worker(run_dir):
    """Child process: one full pipeline run of run_dir/cfg.py (already rewritten); captures the member-check inputs
    and the Section 12 model data; writes result.json and capture.pkl."""
    _install_paths(run_dir)
    os.chdir(run_dir)
    v = json.load(open(os.path.join(run_dir, "variant.json")))
    jobs_root, name = os.path.dirname(os.path.abspath(run_dir)), os.path.basename(os.path.abspath(run_dir))
    os.environ["STEEL_BUILDER_JOBS"] = jobs_root
    os.environ["STELTIC_HR_ROOT"] = ENGINE_ROOT
    if os.path.exists("load_plan.json"):
        os.remove("load_plan.json")
    t0 = time.time()
    res = {"run_dir": run_dir, "ok": False}
    buf = io.StringIO()
    cap = {"elems": {}, "s12": None}
    try:
        with contextlib.redirect_stdout(buf):
            import engine3d as E
            E.activate_si_units()
            for lab in v.get("register") or []:
                register(lab)
            import design_pipeline as DP
            import india_is800_s12 as S12
            _mc, _s12 = DP.member_checks_is800, S12.section12_checks

            def mc(cfg, elem):
                cap["elems"][int(elem["member"]["tag"])] = {"member": copy.deepcopy(elem["member"]),
                                                            "kind": elem["kind"],
                                                            "records": DP._top_records(elem["records"])}
                return _mc(cfg, elem)

            def s12(system, md, s12cfg):
                cap["s12"] = (system, copy.deepcopy(md), copy.deepcopy(s12cfg))
                return _s12(system, md, s12cfg)
            DP.member_checks_is800 = mc
            S12.section12_checks = s12
            import importlib.util
            spec = importlib.util.spec_from_file_location("cfg_mod", os.path.join(run_dir, "cfg.py"))
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)
            cfg = mod.cfg
            import pipeline as P
            import plot_model as PM
            import static_model as SM
            PM.figures = lambda *a, **k: "skipped (hr_autosize)"
            E.export_model = lambda *a, **k: "skipped (hr_autosize)"
            SM.export_static_model = lambda *a, **k: "skipped (hr_autosize)"
            out = P.design_and_report(name, cfg, do_report=False)
            res["pipeline"] = {k: out.get(k) for k in ("blocked", "error", "model_valid")}
            pkg = json.load(open(os.path.join(run_dir, "design", "calc_package.json")))
            import india_seismic_gates as G
            st = G.design_status(E.CFG[name], pkg, job_dir=run_dir)
            res["design_status"] = {"status": st["status"], "reasons": st["reasons"]}
            res["ok"] = True
    except Exception:
        import traceback
        res["exception"] = traceback.format_exc()[-6000:]
    res["elapsed_s"] = round(time.time() - t0, 1)
    open(os.path.join(run_dir, "worker_stdout.txt"), "w").write(buf.getvalue()[-100000:])
    if cap["s12"] is not None or cap["elems"]:
        with open(os.path.join(run_dir, "capture.pkl"), "wb") as f:
            pickle.dump(cap, f, protocol=pickle.HIGHEST_PROTOCOL)
    json.dump(res, open(os.path.join(run_dir, "result.json"), "w"), indent=1, default=str)
    return res


# =================================================================================================== evaluation
REPORT_ONLY_WAIVERS = (r"grounding record not available \(report not built\)",)


def evaluate_run(run_dir, waivers=()):
    """Pass / fail (design_status with the waivers), kg/m2, and every failing item of the run."""
    res = json.load(open(os.path.join(run_dir, "result.json")))
    out = {"ok_run": bool(res.get("ok")), "exception": res.get("exception"), "elapsed_s": res.get("elapsed_s")}
    if not res.get("ok"):
        out["passed"] = False
        return out
    pkg = json.load(open(os.path.join(run_dir, "design", "calc_package.json")))
    tk = json.load(open(os.path.join(run_dir, "design", "takeoff.json")))
    st = res.get("design_status") or {}
    reasons = st.get("reasons") or []
    wv = tuple(waivers) + REPORT_ONLY_WAIVERS
    waived = [r for r in reasons if any(re.search(w, r) for w in wv)]
    blocking = [r for r in reasons if r not in waived]
    out.update(status=st.get("status"), reasons=reasons, waived=waived, blocking=blocking, passed=not blocking,
               kg_m2=tk.get("kg_per_m2"), total_kg=tk.get("total_kg"), floor_area_m2=tk.get("floor_area_m2"))
    out["members"] = {}
    for m in pkg.get("members") or []:
        rows = m.get("checks") or []
        st_ = [c.get("dc") for c in rows if str(c.get("name", "")).startswith("IS 800 9.3") and
               isinstance(c.get("dc"), (int, float))]
        sl_ = [c.get("dc") for c in rows if str(c.get("name", "")).startswith("IS 800 Table 3") and
               isinstance(c.get("dc"), (int, float))]
        out["members"][m["id"]] = {"section": (m.get("inputs") or {}).get("section"),
                                   "role": (m.get("inputs") or {}).get("role"),
                                   "strength": max(st_) if st_ else None, "slender": max(sl_) if sl_ else None,
                                   "DC": m.get("DC")}
    out["connections"] = []
    for c in pkg.get("connections") or []:
        bad = [ch for ch in c.get("checks") or [] if ch.get("ok") is not True]
        out["connections"].append({"id": c.get("id"), "type": c.get("type"), "section": c.get("section"),
                                   "DC": c.get("DC"), "demand": c.get("demand"),
                                   "fail": [(ch.get("name"), ch.get("dc"), ch.get("ok")) for ch in bad][:20]})
    s12 = ((pkg.get("capacity_design") or {}).get("section12") or {}).get("checks") or []
    out["s12_fail"] = [{"id": c.get("id"), "member": c.get("member"), "dc": c.get("dc"), "ok": c.get("ok"),
                        "value": str(c.get("value"))[:80], "limit": str(c.get("limit"))[:80]}
                       for c in s12 if c.get("ok") is not True][:200]
    out["drift"] = {}
    for r in pkg.get("drift_table") or []:
        d = r.get("dir")
        out["drift"][d] = max(out["drift"].get(d, 0.0), float(r.get("dc") or 0.0))
    out["wind"] = {}
    for d, r in (pkg.get("wind_serviceability") or {}).items():
        if isinstance(r, dict):
            out["wind"][d] = max([float(r.get(k) or 0.0) for k in ("ratio_top", "ratio_storey", "ratio_dado")])
    out["deflection"] = [(r.get("section"), r.get("ratio"), r.get("roof")) for r in pkg.get("beam_deflection") or []
                         if isinstance(r, dict)]
    out["gates_false"] = [g for g, v in (pkg.get("gates") or {}).items() if v is False]
    out["headline"] = _headline(pkg)
    return out


def _headline(pkg):
    try:
        import report_second_wave as RS2
        h = RS2.headline(pkg)
        return {"strength": (h.get("strength") or {}).get("dc"), "member": (h.get("strength") or {}).get("member"),
                "check": (h.get("strength") or {}).get("check")}
    except Exception as ex:
        return {"error": str(ex)}


# =================================================================================================== local sizing
class Local:
    """The frozen-force model of one run: element member-check inputs, the Section 12 model data, the cfg."""

    def __init__(self, run_dir, groups_of, specs, sections, grades, cfg):
        cap = pickle.load(open(os.path.join(run_dir, "capture.pkl"), "rb"))
        self.elems = cap["elems"]
        self.s12 = cap["s12"]
        self.groups_of = groups_of           # tag -> group
        self.specs = specs
        self.sections = dict(sections)
        self.grades = grades                 # GRADE_BY_SECTION of the run
        self.cfg = cfg
        import static_model as SM
        self._cf = {t: SM.combo_forces_for_member_check(e["records"], e["kind"]) for t, e in self.elems.items()}
        self.by_group = {}
        for t in sorted(self.elems):
            g = groups_of.get(t)
            if g is not None:
                self.by_group.setdefault(g, []).append(t)

    def member_dc(self, t, label, grade):
        import india_is800 as I8
        e = self.elems[t]
        m = dict(e["member"], section=label)
        if grade is not None or family_of(label) != "CHS":
            if grade is not None:
                m["grade"] = grade
            elif family_of(e["member"]["section"]) == "CHS" and family_of(label) != "CHS":
                m["grade"] = self.cfg.get("steel_grade")
        if family_of(label) == "CHS":
            m["grade"] = self.cfg.get("tube_grade") or self.cfg.get("brace_grade") or m.get("grade")
            m["process"] = self.cfg.get("tube_process") or self.cfg.get("brace_process") or m.get("process")
        try:
            r = I8.member_check_is800(m, self._cf[t], cfg=self.cfg)
        except Exception as ex:
            return 99.0, 99.0, "error %s" % ex
        if r.get("dc") is None:
            return 99.0, 99.0, r.get("reason")
        st = r.get("interaction_dc", r["dc"])
        t3 = (r.get("table3_slenderness") or {}).get("dc") or 0.0
        return float(st), float(t3), None

    def group_ok(self, g, label, grade, margin):
        worst = (0.0, 0.0)
        for t in self.by_group.get(g, []):
            st, t3, err = self.member_dc(t, label, grade)
            if err or st > margin + 1e-9 or t3 > 1.0 + 1e-9:
                return False, (st, t3)
            worst = (max(worst[0], st), max(worst[1], t3))
        if (self.specs.get(g) or {}).get("role") == "gantry":
            dc = self.gantry_dc(label, grade)
            if dc is None or dc > margin + 1e-9:
                return False, (dc if dc is not None else 99.0, worst[1])
            worst = (max(worst[0], dc), worst[1])
        return True, worst

    def gantry_dc(self, label, grade):
        """The engine's gantry girder checks (design_pipeline.gantry_girder_checks: LTB + surge on the capped top
        flange, web bearing / buckling under the wheel, Table 6 deflections, Section 13 fatigue) for a candidate
        girder with its channel cap (cap_channel / capped_flange)."""
        import design_pipeline as DP
        import india_loads as IL
        cfg = dict(self.cfg)
        cr = copy.deepcopy(cfg.get("crane") or {})
        if not cr:
            return None
        cr["gantry_section"] = label
        if grade:
            cr["gantry_grade"] = grade
        if (self.specs.get(self._gantry_group()) or {}).get("cap"):
            cr["top_flange_cap"] = capped_flange(label, cap_channel(label))
        cfg["crane"] = cr
        try:
            gd = IL.gantry_girder_demands(cfg)
            r = DP.gantry_girder_checks(cfg, gd)
        except Exception as ex:
            log("    gantry check failed for %s: %s" % (label, ex))
            return None
        dcs = [c.get("dc") for c in r.get("checks") or [] if isinstance(c.get("dc"), (int, float))]
        if any(c.get("ok") is None for c in r.get("checks") or []):
            return None
        return max(dcs) if dcs else None

    def _gantry_group(self):
        return next((g for g, sp in self.specs.items() if sp.get("role") == "gantry"), None)

    def group_length_mm(self, g):
        return sum(float(self.elems[t]["member"].get("L_mm") or 0.0) for t in self.by_group.get(g, []))


def stiffness(label, kind):
    p = props(label)
    if kind == "A":
        return float(p["A"])
    return float(p["Ix"])


def size_groups(lm, x, margins, stiff_req, *, log_fn=log, fixed=()):
    """Lightest candidate per group under the frozen forces.  x: {group: (label, grade)}; stiff_req: {group:
    minimum stiffness (I or A)}.  Returns the new x and a per-group note."""
    new, notes = {}, {}
    for g in sorted(lm.specs):
        spec = lm.specs[g]
        if spec.get("role") == "fixed" or g in fixed or spec.get("same_as"):
            new[g] = x[g]
            continue
        if not lm.by_group.get(g):
            new[g] = x[g]
            notes[g] = "no elements"
            continue
        kind = spec.get("stiff", STIFF_BY_ROLE.get(spec.get("role")))
        need = stiff_req.get(g)
        chosen = None
        for lab, grade, tier in candidates(spec):
            if need and kind and stiffness(lab, kind) < need - 1e-6:
                continue
            ok, worst = lm.group_ok(g, lab, grade, margins.get(g, spec.get("margin", 0.95)))
            if ok:
                chosen = (lab, grade)
                notes[g] = "%s %s tier %d: strength %.3f slender %.3f" % (lab, grade or "", tier, worst[0], worst[1])
                break
        if chosen is None:
            chosen = x[g]
            notes[g] = "no candidate passes: kept %s" % (x[g],)
        new[g] = chosen
    for g in sorted(lm.specs):
        if lm.specs[g].get("same_as"):
            new[g] = new[lm.specs[g]["same_as"]]
    return new, notes


def next_up(spec, current, lm=None, g=None, margin=None):
    """The next candidate after `current` (label, grade) in the group's order that is heavier than it (or a later
    tier) and passes the frozen member checks (when lm is given)."""
    cands = candidates(spec)
    cur_m = mass_kg_m(current[0])
    cur_tier = next((tr for (l, gr, tr) in cands if l == current[0] and gr == current[1]), None)
    for lab, grade, tier in cands:
        if (lab, grade) == tuple(current):
            continue
        heavier = mass_kg_m(lab) > cur_m + 1e-9
        later_tier = cur_tier is not None and tier > cur_tier and mass_kg_m(lab) >= cur_m * 0.999
        if not (heavier or later_tier):
            continue
        if cur_tier is not None and tier < cur_tier:
            continue
        if lm is not None:
            ok, _ = lm.group_ok(g, lab, grade, margin)
            if not ok:
                continue
        if _stronger(lab, current[0]):
            return (lab, grade)
    return None


def _stronger(a, b):
    """a is not weaker than b in every basic property (A, Ix, Iy, Zx): avoids stepping 'up' to a heavier but less
    capable section."""
    pa, pb = props(a), props(b)
    return all(float(pa.get(k) or 0) >= 0.98 * float(pb.get(k) or 0) for k in ("A", "Ix", "Zx")) or \
        float(pa["A"]) > 1.05 * float(pb["A"])


# ---------------------------------------------------------------------------------------- Section 12, frozen forces
# rows that belong to connection geometry (designed in the connection step, not by the member sizes)
S12_CONNECTION_ROWS = re.compile(r"(brace_conn|gusset|connection_moment|connection_shear|_base$|7\.4_base|12\.12|"
                                 r"bolt_type|weld_type|end_stiffeners|intermediate_stiffeners|continuity_plates|"
                                 r"panel_zone|splice|12\.3\.4\.4_connection)")


def s12_local(lm, x, *, tags_changed=None):
    """Section 12 checks of the model with the proposed sections (frozen forces).  Returns the failing member-level
    rows [(row, group)]."""
    import india_is800_s12 as S12
    if lm.s12 is None:
        return []
    system, md0, sc = lm.s12
    md = copy.deepcopy(md0)
    for m in md.get("members") or []:
        t = int(m.get("tag") or str(m["id"]).lstrip("e"))
        g = lm.groups_of.get(t)
        if g is None or g not in x:
            continue
        lab, grade = x[g]
        if lab != m.get("section"):
            m["section"] = lab
            register(lab)
            if family_of(lab) == "CHS":
                m["grade"] = lm.cfg.get("tube_grade") or lm.cfg.get("brace_grade")
                m["process"] = lm.cfg.get("tube_process") or lm.cfg.get("brace_process")
                p = props(lab)
                m["An_mm2"] = float(p["A"]) - 2.0 * float(p["tw"]) * 22.0     # slot for a 20 mm gusset (estimate)
            elif grade is not None:
                m["grade"] = grade
        elif grade is not None:
            m["grade"] = grade
    for ln in md.get("links") or []:
        t = int(str(ln.get("member_id")).lstrip("e")) if str(ln.get("member_id", "")).lstrip("e").isdigit() else None
        g = lm.groups_of.get(t) if t is not None else None
        if g is not None and g in x:
            ln["section"] = x[g][0]
            if x[g][1]:
                ln["grade"] = x[g][1]
    try:
        r = S12.section12_checks(system, md, sc)
    except Exception as ex:
        log("    s12 local failed: %s" % ex)
        return []
    out = []
    mem_tag = {m["id"]: int(m.get("tag") or str(m["id"]).lstrip("e")) for m in md.get("members") or []}
    for c in r.get("checks") or []:
        if c.get("ok") is not False:
            continue
        if S12_CONNECTION_ROWS.search(str(c.get("id"))):
            continue
        mid = c.get("member")
        g = lm.groups_of.get(mem_tag.get(mid)) if mid in mem_tag else None
        out.append((c, g))
    return out


def scwb_columns(lm, row):
    """Groups of the columns at the joint of a failing SCWB / column-strength row."""
    system, md, sc = lm.s12
    jid = row.get("member") or row.get("joint")
    out = set()
    for j in md.get("joints") or []:
        if str(j.get("id")) == str(jid) or str(j.get("node")) == str(jid):
            for c in j.get("columns") or []:
                t = int(str(c.get("member_id")).lstrip("e"))
                if lm.groups_of.get(t):
                    out.add(lm.groups_of[t])
    return sorted(out)


# =================================================================================================== driver
def _state_path(work):
    return os.path.join(work, "state.json")


def load_state(work):
    p = _state_path(work)
    return json.load(open(p)) if os.path.exists(p) else {}


def save_state(work, st):
    p = _state_path(work)
    tmp = p + ".tmp"
    json.dump(st, open(tmp, "w"), indent=1, default=str)
    os.replace(tmp, p)


def job_literals(job_dir):
    lit = read_literals(os.path.join(job_dir, "cfg.py"), ("SECTIONS", "SIZING_GROUPS", "GRADE_BY_SECTION",
                                                          "CONNECTIONS"))
    if "SECTIONS" not in lit or "SIZING_GROUPS" not in lit:
        raise KeyError("%s/cfg.py: SECTIONS and SIZING_GROUPS are required at the top level" % job_dir)
    return lit


# =================================================================================================== connections
# Declared connection geometry (india_connection_design formats), re-designed for the new sections.  Every designer
# returns a complete spec; its capacity is checked by the engine's own functions (india_connections /
# india_is800_s12) where the demand is known locally, and the verification run checks everything.
CONN_KINDS = ("beam_shear", "brace_end", "beam_column", "column_base", "column_splice")
BOLT_GEOM = {20: (40.0, 70.0, 22.0), 24: (45.0, 75.0, 26.0), 30: (55.0, 90.0, 33.0)}   # d -> (e, p, d0) mm


def plate_fy(t, grade="E250"):
    """IS 2062 Table 3 yield stress by thickness (the values the golds' helpers use): E250 250 / 240 / 230 (<= 20,
    20-40, 40-100 mm) and 210 above 100 mm; E350 350 / 330 / 320 / 290."""
    t = float(t)
    if "350" in str(grade):
        return 350.0 if t <= 20 else (330.0 if t <= 40 else (320.0 if t <= 100 else 290.0))
    return 250.0 if t <= 20 else (240.0 if t <= 40 else (230.0 if t <= 100 else 210.0))


def _plate_up(t, factor=1.0):
    need = float(t) * factor
    for p in PLATES_MM:
        if p >= need - 1e-9 and p > float(t) - 1e-9 + (0.0 if factor > 1.0 else 1e-3):
            return p
    return PLATES_MM[-1]


def fin_plate_spec(sec, n, d, t, template=None, n_lines=1, gauge=70.0):
    """Fin plate (shear tab) on a beam web: n_lines vertical lines of n bolts (diameter d, end / edge e, pitch p,
    gauge between lines), plate t; block shear on the L-shaped path (vertical shear plane along the bolt line(s),
    tension plane from the outer line to the plate edge across every line)."""
    p = props(sec)
    e, pitch, d0 = BOLT_GEOM[int(d)]
    h = 2.0 * e + (n - 1) * pitch
    tpl = dict(template or {})
    Ls = e + (n - 1) * pitch
    wt = e + (n_lines - 1) * gauge
    bs = {"Avg_mm2": Ls * t, "Avn_mm2": (Ls - (n - 0.5) * d0) * t,
          "Atg_mm2": wt * t, "Atn_mm2": (wt - (n_lines - 0.5) * d0) * t}
    out = {"t_plate_mm": float(t), "h_plate_mm": h, "fy_plate_MPa": plate_fy(t), "fu_plate_MPa": 410.0,
           "bolt_type": tpl.get("bolt_type", "HSFG"), "slip_surface": tpl.get("slip_surface", "clean_mill_scale"),
           "bolts": {"n_bolts": int(n) * int(n_lines), "d_mm": int(d), "grade": "8.8",
                     "t_mm": round(min(float(t), float(p["tw"])), 2),
                     "fu_plate_MPa": 410.0, "e_mm": e, "p_mm": pitch, "d0_mm": d0, "nn": 1, "ns": 0},
           "block_shear_areas": bs,
           "cjp": {"t_mm": float(t), "length_mm": h, "fy_MPa": plate_fy(t), "n_sides": 1, "site": True},
           "weld_type": "cjp"}
    if n_lines > 1:
        out["bolt_lines"] = int(n_lines)            # the bolt dict carries only the IS 800 10.3 inputs
        out["gauge_mm"] = float(gauge)
        out["detail"] = "%d lines x %d M%d 8.8 at %s mm pitch, %s mm gauge" % (n_lines, n, d, _fmt(pitch), _fmt(gauge))
    return out


def fin_plate_fits(sec, n, d):
    p = props(sec)
    e, pitch, _ = BOLT_GEOM[int(d)]
    h = 2.0 * e + (n - 1) * pitch
    clear = float(p["d"]) - 2.0 * (float(p["tf"]) + float(p.get("R1") or 0.0)) - 10.0
    return h <= clear


def double_fin(sp, sec):
    """Two fin plates, one each side of the beam web (the IN_Ex15 EBF detail): plate shear on 2 t, bolts in double
    shear (nn 2), block shear on both plates, CJP of both plates to the column."""
    p = props(sec)
    t = float(sp["t_plate_mm"])
    out = copy.deepcopy(sp)
    out["t_plate_mm"] = 2.0 * t
    out["n_plates"] = 2
    out["t_plate_note"] = "two fins of %s mm (one each side of the web): plate shear on 2 t" % _fmt(t)
    out["bolts"]["nn"] = 2
    out["bolts"]["t_mm"] = round(float(p["tw"]), 2)
    out["block_shear_areas"] = {k: 2.0 * v for k, v in sp["block_shear_areas"].items()}
    out["cjp"] = dict(sp["cjp"], n_sides=2)
    return out


def design_fin_plate(sec, V_N, template=None, *, V_service_N=None, margin=0.9):
    """Lightest fin plate whose IS 800 checks (bolts 10.3, plate 8.4.1, block shear 6.4.1, CJP weld, HSFG slip 10.4.3
    at the service shear) pass at V_N within the margin, in this order: one fin plate with one bolt line, then two
    lines; then two fin plates (double shear); each with the template's faying surface, then sand-blasted (IS 800
    Table 20, mu 0.48).  Within a tier: fewest bolts, then the thinnest plate.  The service shear is the run's
    (V_service_N), else V_N / 1.5."""
    import india_connections as C
    import india_connection_design as CD
    Vs = V_service_N if V_service_N is not None else V_N / 1.5
    trials = []
    for n_lines in (1, 2):
        for d in (20, 24):
            for n in range(2, 13):
                if not fin_plate_fits(sec, n, d):
                    break
                trials.append((n * n_lines * d * d, n_lines, d, n))
    surf0 = (template or {}).get("slip_surface", "clean_mill_scale")
    for surface in [surf0] + (["sand_blasted"] if surf0 != "sand_blasted" else []):
        for plates in (1, 2):
            for _, n_lines, d, n in sorted(trials):
                for t in (8.0, 10.0, 12.0, 14.0, 16.0, 20.0, 25.0):
                    sp = fin_plate_spec(sec, n, d, t, dict(template or {}, slip_surface=surface), n_lines=n_lines)
                    if plates == 2:
                        sp = double_fin(sp, sec)
                    kw = {k: v for k, v in sp.items() if k in ("t_plate_mm", "h_plate_mm", "fy_plate_MPa",
                                                                "fu_plate_MPa", "block_shear_areas", "cjp",
                                                                "n_plates")}
                    kw["bolts"] = dict(sp["bolts"])
                    r = C.fin_plate_shear_checks(V_N=max(float(V_N), 1.0), **kw)
                    if r.get("dc") is None or r["dc"] > margin:
                        continue
                    sl = CD.hsfg_slip_checks(kw["bolts"], sp["bolt_type"], Vs, V_N, slip_surface=sp.get("slip_surface"))
                    if any((c.get("dc") or 0.0) > margin for c in (sl or {}).values()):
                        continue
                    return sp
    return None


def brace_end_chs_spec(sec, tg, Lw, *, grade_plate="E250", template=None):
    """Brace end on a gusset.  CHS (the IN_Ex7 detail): the gusset passes through slots in the tube and the tube wall
    is welded to it along Lw on both slot edges, both faces (4 weld lines, CJP to the tube wall); net section at the
    slot An = A - 2 t (tg + 2).  Rolled I brace (the IN_Ex13 detail): the flanges are CJP-welded to the gusset over Lw
    (4 weld lines at the flange thickness), no holes (An = A); Whitmore start width bf + 2 mm."""
    p = props(sec)
    tpl = dict(template or {})
    fyg = plate_fy(tg, grade_plate)
    chs = family_of(sec) == "CHS"
    if chs:
        w0, tw_ = float(p["d"]), float(p["tw"])
        An = round(float(p["A"]) - 2.0 * tw_ * (tg + 2.0), 1)
        detail = "slotted CHS %s on a %s mm gusset, 4 welds x %s mm (tube wall to gusset)" % (sec, _fmt(tg), _fmt(Lw))
    else:
        w0, tw_ = float(p["bf"]) + 2.0, float(p["tf"])
        An = float(p["A"])
        detail = "%s flanges CJP-welded to a %s mm gusset over %s mm" % (sec, _fmt(tg), _fmt(Lw))
    bw = w0 + 2.0 * Lw * math.tan(math.radians(30.0))
    return {"weld_type": "cjp",
            "welds": {"cjp": {"t_mm": tw_}, "length_mm": float(Lw), "fy_MPa": 250.0, "n_sides": 4, "site": False},
            "gusset": {"t_mm": float(tg), "fy_MPa": fyg, "fu_MPa": 410.0, "w_start_mm": w0, "L_conn_mm": float(Lw),
                       "L_unbraced_mm": float(tpl.get("L_unbraced_mm", 250.0)), "K": 0.65,
                       "Avg_mm2": 2.0 * Lw * tg, "Avn_mm2": 2.0 * Lw * tg, "Atg_mm2": w0 * tg, "Atn_mm2": w0 * tg},
            "An_mm2": An,
            "moment_capacity_Nmm": tg * bw ** 2 / 4.0 * fyg / 1.1,
            "moment_capacity_cite": "gusset in-plane plastic moment on the Whitmore width: t bw^2/4 fy/gamma_m0",
            "bolts_and_welds_share": False,
            "K_basis": "gusset K = 0.65 (compact corner gusset; L_unbraced = the free gusset length at the brace end)",
            "detail": detail}


def design_brace_end(lm, g, sec, grade, template=None, margin=0.95):
    """Lightest gusset (thinnest, then shortest weld length) for which the engine's brace connection checks
    (india_is800_s12.brace_connection_checks, the brace member rules' net-section row) pass for one brace group with
    its proposed section (frozen forces)."""
    import india_is800_s12 as S12
    import india_connection_design as CD
    system, md, sc = lm.s12
    tags = lm.by_group.get(g) or []
    mems = [m for m in md.get("members") or [] if int(m.get("tag") or str(m["id"]).lstrip("e")) in tags]
    if not mems:
        return None
    if family_of(sec) not in ("CHS", "HB", "WB", "MB", "NPB", "WPB"):
        return None
    for tg in (10.0, 12.0, 14.0, 16.0, 18.0, 20.0, 22.0, 25.0, 28.0, 32.0, 36.0, 40.0):
        for Lw in range(150, 1201, 50):
            sp = brace_end_chs_spec(sec, tg, Lw, template=template)
            cfg_l = {"connections": {"brace_end": {sec: sp}}, "plate_grade": lm.cfg.get("plate_grade"),
                     "steel_grade": lm.cfg.get("steel_grade")}
            ok = True
            for m0 in mems[:4]:
                m = dict(m0, section=sec, An_mm2=sp["An_mm2"])
                if family_of(sec) == "CHS":
                    m["grade"] = lm.cfg.get("tube_grade") or lm.cfg.get("brace_grade") or m.get("grade")
                    m["process"] = lm.cfg.get("tube_process") or lm.cfg.get("brace_process") or m.get("process")
                else:
                    m["grade"] = grade or lm.cfg.get("brace_grade") or lm.cfg.get("steel_grade")
                    m.pop("process", None)
                conn = CD.brace_end_connection(cfg_l, m)
                rows = S12.brace_connection_checks(system, m, conn, md, sc)
                rows += [r for r in S12.brace_member_checks(system, m, md, sc) if r.get("id") == "brace_gross_yield_governs"] \
                    if S12.normalize_system(system) in ("OCBF", "SCBF") else []
                for r in rows:
                    if r.get("ok") is False or (isinstance(r.get("dc"), (int, float)) and r["dc"] > margin and
                                                r.get("id") != "brace_gross_yield_governs"):
                        ok = False
                        break
                if not ok:
                    break
            if ok:
                return sp
    return None


def welded_joint_spec(beam, template):
    """A CJP-welded (or other declared) moment joint for a new beam section: the template's type and notes kept, the
    bolted web plate re-sized to the new beam's depth and web, the continuity plates at least the beam flange."""
    sp = copy.deepcopy(template)
    p = props(beam)
    if isinstance(sp.get("shear"), dict):
        nb = 6 if p["d"] >= 450 else (4 if p["d"] >= 300 else 3)
        while not fin_plate_fits(beam, nb, 20) and nb > 2:
            nb -= 1
        sh = fin_plate_spec(beam, nb, 20, 12.0 if nb >= 6 else 10.0)
        sp["shear"] = {k: v for k, v in sh.items() if k in ("t_plate_mm", "h_plate_mm", "fy_plate_MPa", "fu_plate_MPa",
                                                            "bolts", "block_shear_areas", "cjp")}
    if sp.get("continuity_plate_t_mm"):
        sp["continuity_plate_t_mm"] = max(_plate_up(float(p["tf"]), 1.0), 10.0)
    return sp


def cover_plate_joint_spec(beam, col=None, *, doubler_t=0.0, template=None, factor=1.32, cp_t=None,
                           continuity_t=None):
    """Welded cover-plate moment joint (the IN_Ex8 detail): CJP flanges with one cover plate per flange sized so that
    (Zp fy + b t (d + t) fyp)/gamma_m0 >= factor x Zp fy (1.32 = 1.2 Mp x 1.1, with margin), fillet welds for the plate
    force, and a bolted HSFG fin plate for the shear; continuity plates; doubler (panel zone) as given."""
    p = props(beam)
    fy = 250.0 if max(float(p["tf"]), float(p["tw"])) <= 20 else 240.0
    b = float(p["bf"])
    t = 10.0 if cp_t is None else float(cp_t)
    while cp_t is None and (p["Zx"] * fy + b * t * (p["d"] + t) * plate_fy(t)) / 1.1 < factor * p["Zx"] * fy and t < 50:
        t = _plate_up(t, 1.0001)
    fyp = plate_fy(t)
    Fpl = b * t * fyp / 1.1
    s = 12.0 if t > 16 else 10.0
    per_mm = 0.7 * s * 410.0 / (math.sqrt(3.0) * 1.25)
    L = math.ceil(1.15 * Fpl / per_mm / 10.0) * 10.0
    nb = 6 if p["d"] >= 450 else (4 if p["d"] >= 300 else 3)
    while not fin_plate_fits(beam, nb, 20) and nb > 2:
        nb -= 1
    t_sh = 12.0 if nb >= 6 else 10.0
    sh = fin_plate_spec(beam, nb, 20, t_sh)
    sh = {k: v for k, v in sh.items() if k in ("t_plate_mm", "h_plate_mm", "fy_plate_MPa", "fu_plate_MPa", "bolts",
                                               "block_shear_areas", "cjp")}
    ct = continuity_t if continuity_t is not None else _plate_up(float(p["tf"]), 1.0)
    out = {"type": "welded_cover_plate",
           "cover_plate": {"plate_b_mm": b, "plate_t_mm": t, "fy_plate_MPa": fyp,
                           "weld": {"size_mm": s, "length_mm": L, "fu_MPa": 410.0, "n_sides": 1, "site": False}},
           "weld_type": "cjp", "bolt_type": "HSFG", "shear": sh,
           "continuity_plates": True, "continuity_plate_t_mm": ct, "doubler_t_mm": float(doubler_t),
           "cite": "CJP-welded flanges + %s x %s cover plates (fillet %s mm x %s mm) + bolted HSFG fin plate; "
                   "continuity plates %s mm%s (IS 800 12.10 / 12.11)"
                   % (_fmt(b), _fmt(t), _fmt(s), _fmt(L), _fmt(ct),
                      ("; panel-zone doubler %s mm" % _fmt(doubler_t)) if doubler_t else "")}
    return out


ANCHOR_D = (20, 24, 30, 36, 42, 48, 56, 64)
ANCHOR_ANB = {20: 245.0, 24: 353.0, 30: 561.0, 36: 817.0, 42: 1120.0, 48: 1473.0, 56: 2030.0, 64: 2676.0}


def adapt_base(template, old_col, new_col):
    """A column base for a new column section from the base of the old one: the plate keeps its projections beyond
    the column (B and L grow or shrink with the column, never below the old anchor layout's fit), the anchors and
    every other declared item (embedment, stiffeners, shear key) are kept; the plate fy follows its thickness."""
    sp = copy.deepcopy(template)
    if old_col == new_col or not isinstance(sp, dict) or sp.get("type") == "embedded":
        return sp
    po, pn = props(old_col), props(new_col)
    dB = float(pn["bf"]) - float(po["bf"])
    dL = float(pn["d"]) - float(po["d"])
    for k, dk in (("B_mm", dB), ("L_mm", dL)):
        if k in sp and dk > 0:
            sp[k] = float(math.ceil((float(sp[k]) + dk) / 50.0) * 50.0)
    if sp.get("t_plate_mm"):
        sp["fy_plate_MPa"] = plate_fy(sp["t_plate_mm"], sp.get("plate_grade") or "E250")
    return sp


def adapt_splice(template, old_col, new_col):
    """A column splice for a new upper column: flange plates resized to the new flange width (area b t, the bolts'
    bearing thickness the thinner of the flange and the plate), web plates kept; a 'none' or CJP splice is kept."""
    sp = copy.deepcopy(template)
    if not isinstance(sp, dict) or sp.get("none") or old_col == new_col:
        return sp
    pn = props(new_col)
    pl = sp.get("plate")
    if isinstance(pl, dict) and pl.get("t_mm"):
        t = float(pl["t_mm"])
        pl["A_mm2"] = round(float(pn["bf"]) * t, 1)
        if "b_mm" in pl:
            pl["b_mm"] = float(pn["bf"])
        pl.pop("note", None)
    b = sp.get("bolts")
    if isinstance(b, dict) and pl:
        b["t_mm"] = round(min(float(pn["tf"]), float((pl or {}).get("t_mm") or pn["tf"])), 2)
        b.pop("note", None)
    sp.pop("note", None)
    return sp


def bump_base(sp, failing):
    """Step up a column base for its failing rows (names of the run's 'column base' rows)."""
    sp = copy.deepcopy(sp)
    names = " ".join(failing)
    if re.search(r"plate_thickness", names):
        sp["t_plate_mm"] = _plate_up(float(sp.get("t_plate_mm") or 20.0), 1.1)
        if float(sp["t_plate_mm"]) > 63:
            sp["t_plate_mm"] = float(math.ceil(float(sp["t_plate_mm"]) / 10.0) * 10.0)
        sp["fy_plate_MPa"] = plate_fy(sp["t_plate_mm"], sp.get("plate_grade") or "E250")
    if re.search(r"bearing|geometry_anchor_fit", names):
        for k in ("B_mm", "L_mm"):
            if k in sp:
                sp[k] = float(math.ceil(float(sp[k]) * 1.1 / 50.0) * 50.0)
    an = sp.get("anchors")
    if isinstance(an, dict) and re.search(r"anchor_(tension|combined|shear)", names):
        d = int(an.get("d_mm") or 24)
        up = [x for x in ANCHOR_D if x > d]
        if up and up[0] <= 56:
            an["d_mm"] = up[0]
            an["Anb_mm2"] = ANCHOR_ANB[up[0]]
        else:
            npr = int(an.get("n_per_row") or 2) + 1
            an["n_per_row"] = npr
            an["n_tension"] = int(an.get("n_tension") or 2) + 1
            an["n_total"] = int(an.get("n_total") or 4) + 2
    if isinstance(an, dict) and re.search(r"anchorage_embedment", names):
        emb = an.get("embedment") or sp.get("embedment")
        if isinstance(emb, dict) and emb.get("L_mm"):
            emb["L_mm"] = float(emb["L_mm"]) + 250.0
    st = sp.get("stiffeners")
    if isinstance(st, dict) and re.search(r"gusset", names):
        st["t_mm"] = _plate_up(float(st.get("t_mm") or 12.0), 1.0001)
    return sp


def bump_splice(sp, failing):
    sp = copy.deepcopy(sp)
    names = " ".join(failing)
    if isinstance(sp.get("bolts"), dict) and re.search(r"bolts_10_3", names):
        sp["bolts"]["n_bolts"] = int(sp["bolts"].get("n_bolts") or 4) + 2
    pl = sp.get("plate")
    if isinstance(pl, dict) and re.search(r"plate_yield|plate_weld", names):
        t0 = float(pl.get("t_mm") or 12.0)
        t1 = _plate_up(t0, 1.0001)
        pl["A_mm2"] = round(float(pl.get("A_mm2") or 0.0) * t1 / t0, 1)
        pl["t_mm"] = t1
        pl["fy_MPa"] = plate_fy(t1)
    wp = sp.get("web_plate")
    if isinstance(wp, dict) and re.search(r"web_plate|sumMp", names):
        t0 = float(wp.get("t_mm") or 10.0)
        t1 = _plate_up(t0, 1.0001)
        for k in ("A_mm2", "Av_mm2"):
            if wp.get(k):
                wp[k] = round(float(wp[k]) * t1 / t0, 1)
        wp["t_mm"] = t1
        if isinstance(sp.get("web_bolts"), dict):
            sp["web_bolts"]["n_bolts"] = int(sp["web_bolts"].get("n_bolts") or 2) + 2
    return sp


# =================================================================================================== driver
def _x_key(x):
    return json.dumps({g: list(v) for g, v in sorted(x.items())}, sort_keys=True)


def roles_of_groups(lm):
    out = {}
    for g, tags in lm.by_group.items():
        out[g] = sorted({str(lm.elems[t]["member"].get("role_group") or lm.elems[t]["member"].get("role"))
                         for t in tags})
    return out


def grade_map(x, roles, steel_grade, base=None):
    """GRADE_BY_SECTION for a design: '<role>:<label>' (or 'brace:<label>') for every group whose grade differs from
    the job steel grade; the job's own non-group entries (base) are kept."""
    out = dict(base or {})
    for g in sorted(x):
        lab, grade = x[g]
        if grade is None or str(grade) == str(steel_grade):
            continue
        for r in roles.get(g) or []:
            out["%s:%s" % (r, lab)] = grade
    return out


def _labels_in_use(x):
    return {v[0] for v in x.values()}


def _group_conn_demand(ev, roles, label):
    """The run's beam-end shear demand of a beam group: the largest V (or V + N resultant) of its connection
    records ('conn-<role>-<label>')."""
    best = 0.0
    for c in ev.get("connections") or []:
        cid = str(c.get("id"))
        if not any(cid == "conn-%s-%s" % (r, label) for r in roles):
            continue
        d = c.get("demand") or {}
        for k in ("V_P_resultant_N", "V_N"):
            if isinstance(d.get(k), (int, float)):
                best = max(best, float(d[k]))
    return best


def design_connections(lm, ev, x, x_run, conn_run, roles, specs, *, bumps=None):
    """CONNECTIONS for design x: every kind keyed by the new labels (bases / splices by '<role>:<label>')."""
    bumps = bumps or {}
    used = _labels_in_use(x)
    out = {}
    for kind in CONN_KINDS:
        old = copy.deepcopy((conn_run or {}).get(kind) or {})
        new = {}
        for k, v in old.items():                                  # keep defaults and labels still in use
            lab = k.split(":", 1)[1] if ":" in k else k
            if k == "default" or lab in used:
                new[k] = v
        out[kind] = new
    import india_connection_design as CD
    for g in sorted(x):
        spec = specs[g]
        lab, grade = x[g]
        lab0 = x_run[g][0]
        rl = roles.get(g) or []
        role = spec.get("role")
        conn_cfg = {"connections": conn_run or {}}
        # beam-end shear connection (gravity beams, braced-bay beams, struts)
        if any(r in ("floor", "roof") for r in rl) and family_of(lab) not in ("CHS", "ISA"):
            tpl = CD.spec_for(conn_cfg, "beam_shear", lab0, "beam") or {}
            V = _group_conn_demand(ev, rl, lab0)
            if V > 0 or lab != lab0:
                Vd = max(1.2 * V, 30.0e3)
                sp = design_fin_plate(lab, Vd, tpl)
                if sp is not None:
                    out["beam_shear"][lab] = sp
        # moment joints
        tplj = CD.spec_for(conn_cfg, "beam_column", lab0, "beam")
        if tplj and (lab != lab0 or g in bumps.get("beam_column", {})):
            typ = str(tplj.get("type") or "").lower()
            if typ in ("welded_cover_plate", "cover_plate"):
                b = bumps.get("beam_column", {}).get(g, {})
                out["beam_column"][lab] = cover_plate_joint_spec(
                    lab, doubler_t=float(b.get("doubler_t_mm", tplj.get("doubler_t_mm") or 0.0)),
                    cp_t=b.get("cp_t"), continuity_t=b.get("continuity_t"))
            else:
                out["beam_column"][lab] = welded_joint_spec(lab, tplj)
        # brace ends
        if role == "brace" or any(r == "brace" for r in rl):
            tplb = CD.spec_for(conn_cfg, "brace_end", lab0, "brace") or {}
            sp = design_brace_end(lm, g, lab, grade, (tplb.get("gusset") or {}))
            if sp is not None:
                out["brace_end"][lab] = sp
            elif lab != lab0 and tplb:
                out["brace_end"][lab] = copy.deepcopy(tplb)
        # bases and splices (columns)
        for r in rl:
            if r not in ("lateral_col", "gravity_col"):
                continue
            key = "%s:%s" % (r, lab)
            tb = CD.spec_for(conn_cfg, "column_base", lab0, r)
            if tb is not None:
                sp = adapt_base(tb, lab0, lab)
                fb = (bumps.get("column_base") or {}).get(key) or (bumps.get("column_base") or {}).get("%s:%s" % (r, lab0))
                if fb:
                    sp = bump_base(sp, fb)
                out["column_base"][key] = sp
            ts = CD.spec_for(conn_cfg, "column_splice", lab0, r)
            if ts is not None:
                sp = adapt_splice(ts, lab0, lab)
                fs = (bumps.get("column_splice") or {}).get(key) or (bumps.get("column_splice") or {}).get("%s:%s" % (r, lab0))
                if fs:
                    sp = bump_splice(sp, fs)
                out["column_splice"][key] = sp
    return out


def connection_bumps(ev, x, roles):
    """Failing connection rows of a run, by kind and key: {'column_base': {'<role>:<label>': [row names]}, ...}."""
    out = {"column_base": {}, "column_splice": {}, "beam_column": {}}
    for c in ev.get("connections") or []:
        if not c.get("fail"):
            continue
        cid = str(c.get("id"))
        m = re.match(r"conn-(lateral_col|gravity_col)-(.+)$", cid)
        if m:
            key = "%s:%s" % (m.group(1), m.group(2))
            for (nm, dc, ok) in c["fail"]:
                nm = str(nm)
                if nm.startswith("column base"):
                    out["column_base"].setdefault(key, []).append(nm)
                elif nm.startswith("column splice"):
                    out["column_splice"].setdefault(key, []).append(nm)
    return out


def stiffness_requirements(lm, ev, x_run, specs, target=0.95, floor=0.5):
    """Minimum stiffness per group from the run's drift / sway / deflection ratios: a group of the lateral system
    keeps I (or A) >= its current value x ratio / target (the run's worst lateral ratio; a ratio below target lets the
    stiffness fall, but never below floor x the current); a beam with a deflection row keeps I >= I x ratio /
    target."""
    lat = max(list((ev.get("drift") or {}).values()) + list((ev.get("wind") or {}).values()) + [0.0])
    f_lat = max(lat / target, floor)
    defl = {}
    for sec, ratio, roof in ev.get("deflection") or []:
        if isinstance(ratio, (int, float)):
            defl[sec] = max(defl.get(sec, 0.0), float(ratio))
    req = {}
    roles = roles_of_groups(lm)
    for g, (lab, grade) in x_run.items():
        spec = specs[g]
        kind = spec.get("stiff", STIFF_BY_ROLE.get(spec.get("role")))
        if not kind or not lm.by_group.get(g):
            continue
        lateral = spec.get("lateral")
        if lateral is None:
            lateral = any(r in ("lateral_col", "brace") for r in roles.get(g, [])) or spec.get("role") == "link"
        need = 0.0
        if lateral:
            need = stiffness(lab, kind) * f_lat
        if lab in defl and kind == "I":
            need = max(need, stiffness(lab, "I") * max(defl[lab] / target, floor))
        if need > 0:
            req[g] = need
    return req, {"lateral_ratio": lat, "factor": f_lat}


def _run_variant(job_dir, work, it, x, gbs, conns, *, probe_sections=None, timeout=5400):
    run_dir = os.path.join(work, "it%02d" % it)
    if os.path.isdir(run_dir):
        shutil.rmtree(run_dir)
    src = open(os.path.join(job_dir, "cfg.py"), encoding="utf-8").read()
    vals = {"SECTIONS": {g: v[0] for g, v in sorted(x.items())}}
    lit = read_literals(src, ("GRADE_BY_SECTION", "CONNECTIONS"))
    if "GRADE_BY_SECTION" in lit:
        vals["GRADE_BY_SECTION"] = gbs
    if "CONNECTIONS" in lit and conns is not None:
        vals["CONNECTIONS"] = conns
    prepare_run_dir(job_dir, run_dir, rewrite_source(src, vals))
    json.dump({"register": sorted(l for l in _labels_in_use(x) if parse_built_up(l))},
              open(os.path.join(run_dir, "variant.json"), "w"), indent=1)
    rc, el = run_child([PY, os.path.abspath(__file__), "worker", run_dir], run_dir, timeout,
                       log_path=os.path.join(run_dir, "child.log"))
    return run_dir, rc, el


def _cleanup(work, keep):
    for d in sorted(os.listdir(work)):
        p = os.path.join(work, d)
        if not (d.startswith("it") and os.path.isdir(p)) or d in keep:
            continue
        for f in ("capture.pkl", os.path.join("design", "member_combo_forces.json"),
                  os.path.join("design", "calc_package.json")):
            fp = os.path.join(p, f)
            if os.path.exists(fp):
                os.remove(fp)


def size_job(job_dir, work, *, max_iter=14, waivers=(), time_cap_s=6600, log_fn=log, fixed=()):
    """The sizing loop (resumable from work/state.json).  Returns the state."""
    import engine3d as E
    E.activate_si_units()
    os.makedirs(work, exist_ok=True)
    t_start = time.time()
    lit = job_literals(job_dir)
    specs = lit["SIZING_GROUPS"]
    st = load_state(work)
    if not st:
        gb0 = lit.get("GRADE_BY_SECTION") or {}

        def _g0(lab):
            for k, v in gb0.items():
                if k == lab or k.endswith(":" + lab):
                    return v
            return None
        x0 = {g: (lab, _g0(lab)) for g, lab in lit["SECTIONS"].items()}
        st = {"job": job_dir, "x": {g: list(v) for g, v in x0.items()}, "gbs": gb0,
              "conns": lit.get("CONNECTIONS"), "margins": {}, "it": 0, "history": [], "best": None, "groups_of": None,
              "stiff_boost": {}, "bumps": {}}
        save_state(work, st)
    while st["it"] < max_iter:
        if time.time() - t_start > time_cap_s:
            log_fn("time cap reached: stop (resumable)")
            break
        it = st["it"]
        x = {g: tuple(v) for g, v in st["x"].items()}
        run_dir, rc, el = _run_variant(job_dir, work, it, x, st["gbs"], st["conns"])
        ev = evaluate_run(run_dir, waivers)
        if not ev.get("ok_run"):
            log_fn("it%02d run failed (rc %s): %s" % (it, rc, (ev.get("exception") or "")[-1500:]))
            st["history"].append({"it": it, "x": st["x"], "failed": True, "exception": (ev.get("exception") or "")[-800:]})
            save_state(work, st)
            raise RuntimeError("full run failed at it%02d" % it)
        if st.get("groups_of") is None:
            gmap, _kinds = probe(run_dir, {g: v[0] for g, v in x.items()})
            st["groups_of"] = {str(t): g for t, g in sorted(gmap.items())}
        groups_of = {int(t): g for t, g in st["groups_of"].items()}
        mod = exec_cfg(os.path.join(run_dir, "cfg.py"))
        lm = Local(run_dir, groups_of, specs, {g: v[0] for g, v in x.items()}, st["gbs"], mod.cfg)
        roles = roles_of_groups(lm)
        mass_est = sum(lm.group_length_mm(g) / 1000.0 * mass_kg_m(x[g][0]) for g in x)
        rec = {"it": it, "x": {g: list(v) for g, v in x.items()}, "passed": ev["passed"], "kg_m2": ev.get("kg_m2"),
               "blocking": ev.get("blocking")[:12], "drift": ev.get("drift"), "wind": ev.get("wind"),
               "headline": ev.get("headline"), "elapsed_s": el, "mass_est_kg": round(mass_est, 1)}
        log_fn("it%02d %s kg/m2 %s  (%.0f s)  blocking %d: %s" % (it, "PASS" if ev["passed"] else "FAIL", ev.get("kg_m2"),
                                                           el, len(ev.get("blocking") or []),
                                                           "; ".join((ev.get("blocking") or [])[:4])[:600]))
        if ev["passed"] and (st["best"] is None or ev["kg_m2"] < st["best"]["kg_m2"] - 1e-9):
            st["best"] = {"it": it, "kg_m2": ev["kg_m2"], "x": st["x"], "gbs": st["gbs"], "conns": st["conns"],
                          "headline": ev.get("headline")}
            log_fn("    best so far: it%02d %.2f kg/m2" % (it, ev["kg_m2"]))
        # ---- feedback from the full run: members that fail although the local check passed -> tighter margin
        for mid, m in (ev.get("members") or {}).items():
            if (m.get("strength") or 0.0) > 1.0 + 1e-9 or (m.get("slender") or 0.0) > 1.0 + 1e-9:
                for g in sorted(lm.by_group):
                    if x[g][0] == m.get("section") and any(
                            str(lm.elems[t]["member"].get("role_group")) == m.get("role") or
                            str(lm.elems[t]["member"].get("role")) == m.get("role") for t in lm.by_group[g]):
                        st["margins"][g] = round(min(st["margins"].get(g, specs[g].get("margin", 0.95)), 0.95) - 0.04, 3)
                        log_fn("    margin %s -> %.2f (%s strength %s)" % (g, st["margins"][g], mid, m.get("strength")))
        # ---- local sizing under the frozen forces
        req, info = stiffness_requirements(lm, ev, x, specs)
        for g, f in (st.get("stiff_boost") or {}).items():
            if g in req:
                req[g] *= float(f)
        lat_fail = [k for k, v in list((ev.get("drift") or {}).items()) + list((ev.get("wind") or {}).items()) if v > 1.0]
        if lat_fail and ev["passed"] is False:
            for g in req:
                st.setdefault("stiff_boost", {})[g] = round(float(st["stiff_boost"].get(g, 1.0)) * 1.05, 3)
        x1, notes = size_groups(lm, x, st["margins"], req, log_fn=log_fn, fixed=fixed)
        for k in range(8):
            rows = s12_local(lm, x1)
            bumped = set()
            for row, g in rows:
                gs = [g] if g else []
                if re.search(r"SCWB|column_strength|8_2", str(row.get("id"))) or g is None:
                    gs += scwb_columns(lm, row)
                for gg in gs:
                    if gg in bumped or gg not in specs or specs[gg].get("role") == "fixed":
                        continue
                    nu = next_up(specs[gg], x1[gg], lm, gg, st["margins"].get(gg, specs[gg].get("margin", 0.95)))
                    if nu:
                        log_fn("    s12 %s (%s dc %s) -> %s %s" % (gg, row.get("id"), _r3(row.get("dc")), nu[0], nu[1] or ""))
                        x1[gg] = nu
                        bumped.add(gg)
            if not bumped:
                if rows:
                    log_fn("    s12 rows left unresolved: %s" % "; ".join("%s@%s" % (r.get("id"), r.get("member"))
                                                                         for r, _ in rows[:8]))
                break
        for g in sorted(lm.specs):
            if lm.specs[g].get("same_as"):
                x1[g] = x1[lm.specs[g]["same_as"]]
        gbs1 = grade_map(x1, roles, mod.cfg.get("steel_grade"), base={k: v for k, v in (st["gbs"] or {}).items()
                                                                       if ":" not in k and k not in _labels_in_use(x)})
        bumps = connection_bumps(ev, x, roles)
        conns1 = design_connections(lm, ev, x1, x, st["conns"], roles, specs, bumps=bumps) \
            if st["conns"] is not None else None
        rec["proposal"] = {g: list(v) for g, v in x1.items()}
        rec["notes"] = notes
        rec["stiffness"] = info
        st["history"].append(rec)
        changed = _x_key(x1) != _x_key(x) or json.dumps(conns1, sort_keys=True, default=str) != \
            json.dumps(st["conns"], sort_keys=True, default=str)
        for g in sorted(x1):
            if tuple(x1[g]) != tuple(x[g]):
                log_fn("    %-18s %-22s -> %-22s %s" % (g, "%s %s" % (x[g][0], x[g][1] or ""),
                                                     "%s %s" % (x1[g][0], x1[g][1] or ""), notes.get(g, "")))
        st["x"] = {g: list(v) for g, v in x1.items()}
        st["gbs"] = gbs1
        st["conns"] = conns1
        st["it"] = it + 1
        _cleanup(work, keep={"it%02d" % it, "it%02d" % (it - 1), "it%02d" % (st["best"] or {}).get("it", -1)})
        save_state(work, st)
        if not changed and ev["passed"]:
            log_fn("converged at it%02d" % it)
            st["converged"] = True
            save_state(work, st)
            break
        if not changed and not ev["passed"]:
            log_fn("no change proposed but the run fails: margins tightened for the next pass")
            for g in specs:
                st["margins"][g] = round(st["margins"].get(g, specs[g].get("margin", 0.95)) - 0.03, 3)
            save_state(work, st)
    return st


def _r3(v):
    return ("%.3f" % v) if isinstance(v, (int, float)) else str(v)


def write_best(job_dir, work, dst=None):
    """Write the best passing design of a sizing run into cfg.py (SECTIONS, GRADE_BY_SECTION, CONNECTIONS)."""
    st = load_state(work)
    b = st.get("best")
    if not b:
        raise RuntimeError("no passing design in %s" % work)
    path = os.path.join(job_dir, "cfg.py")
    src = open(path, encoding="utf-8").read()
    lit = read_literals(src, ("GRADE_BY_SECTION", "CONNECTIONS"))
    vals = {"SECTIONS": {g: v[0] for g, v in sorted(b["x"].items())}}
    if "GRADE_BY_SECTION" in lit:
        vals["GRADE_BY_SECTION"] = b["gbs"]
    if "CONNECTIONS" in lit and b.get("conns") is not None:
        vals["CONNECTIONS"] = b["conns"]
    out = rewrite_source(src, vals)
    open(dst or path, "w", encoding="utf-8").write(out)
    return b


def main(argv=None):
    import argparse
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    w = sub.add_parser("worker")
    w.add_argument("run_dir")
    s = sub.add_parser("size")
    s.add_argument("job_dir")
    s.add_argument("--work", required=True)
    s.add_argument("--max-iter", type=int, default=14)
    s.add_argument("--time-cap", type=float, default=6600.0)
    s.add_argument("--waive", action="append", default=[])
    s.add_argument("--fixed", action="append", default=[])
    wb = sub.add_parser("write")
    wb.add_argument("job_dir")
    wb.add_argument("--work", required=True)
    wb.add_argument("--dst")
    a = ap.parse_args(argv)
    if a.cmd == "worker":
        r = worker(a.run_dir)
        return 0 if r.get("ok") else 1
    _install_paths(HERE)
    if a.cmd == "size":
        st = size_job(os.path.abspath(a.job_dir), os.path.abspath(a.work), max_iter=a.max_iter, waivers=a.waive,
                      time_cap_s=a.time_cap, fixed=tuple(a.fixed))
        b = st.get("best")
        log("best: %s" % (json.dumps({"it": b["it"], "kg_m2": b["kg_m2"]}) if b else "none"))
        return 0
    if a.cmd == "write":
        b = write_best(os.path.abspath(a.job_dir), os.path.abspath(a.work), a.dst)
        log("written: it%02d %.2f kg/m2" % (b["it"], b["kg_m2"]))
        return 0


if __name__ == "__main__":
    sys.exit(main())
