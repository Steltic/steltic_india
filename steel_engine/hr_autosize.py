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
BUILT_UP_BY_ROLE = {"beam": "welded_I", "link": "welded_I", "column": "box", "brace": "welded_I_brace",
                    "strut": "welded_I_brace", "gantry": "welded_I"}
# braces: CHS families (OCBF) have no built-up fallback; IS 808 rolled braces (SCBF / EBF, E250 B0) fall back to a
# welded I from IS 2062 E250 B0 plates when no rolled section passes (IN_Ex10: 17.8 m X-braces -- the rolled sections
# with the radius of gyration fail the IS 18168 Table 2 brace flange limit, the compact ones the KL/r limit)
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
        brace = kind == "welded_I_brace"         # compact, nearly square welded I braces, D 150-500 mm in 25 mm steps
        for D in (range(150, 501, 25) if brace else range(300, 1201, 50)):
            if min_depth and D < min_depth - 1e-6 or max_depth and D > max_depth + 1e-6:
                continue
            for bf in range(150, 501, 25):
                if bf > D or (brace and bf < 0.75 * D):
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


_CAND_CACHE = {}


MASS_SPAN_MAX, MAX_EVALS = 2.5, 400     # size_groups: candidate mass cap (no stiffness asked) and full evaluations
SHORT_CF_FROM, SHORT_CF = 48, 24      # Local._short_cf: elements with more combinations are predicted on a short list


def candidates(spec, current=None):
    """[(label, grade, tier)] for a group, in the order of preference: rolled E250 (families in order, each family
    lightest first; merged by mass), then rolled E350 (columns), then the built-up fallback (box or welded I, each
    plate set in the group's grades, lightest first)."""
    key = json.dumps(spec, sort_keys=True, default=str)
    if key in _CAND_CACHE:
        return _CAND_CACHE[key]
    role = spec.get("role", "beam")
    fams = spec.get("families") or FAMILIES_BY_ROLE.get(role, ["MB", "WB"])
    grades = spec.get("grades") or (["E250 B0", "E350 B0"] if role == "column" else [None])
    bu = spec.get("built_up", BUILT_UP_BY_ROLE.get(role))
    if "CHS" in fams and "built_up" not in spec:
        bu = None                               # OCBF tube braces: no built-up fallback
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
        # built-up fallback: every plate set in each grade of the group (E250 first at equal mass: the E350 Table 2
        # width-thickness limits are stricter), lightest first
        labs = built_up_catalogue(bu, min_depth=spec.get("min_depth_mm"), max_depth=spec.get("max_depth_mm"))
        out += [(l, g, tier) for l in labs if _limits_ok(spec, l) for g in grades]
    _CAND_CACHE[key] = out
    return out


def _dims(lab):
    """(d, bf) of a label without registering it (built-up labels are parsed)."""
    pb = parse_built_up(lab)
    if pb:
        k, d = pb
        return (d[1], d[0]) if k == "box" else (d[0], d[1])
    p = _S().props(lab)
    return float(p.get("d") or 0.0), float(p.get("bf") or 0.0)


def _limits_ok(spec, lab):
    try:
        d, bf = _dims(lab)
    except Exception:
        return False
    if spec.get("min_depth_mm") and d < spec["min_depth_mm"] - 1e-6:
        return False
    if spec.get("max_depth_mm") and d > spec["max_depth_mm"] + 1e-6:
        return False
    if spec.get("min_bf_mm") and bf < spec["min_bf_mm"] - 1e-6:
        return False
    if spec.get("max_mass_kg_m") and mass_kg_m(lab) > spec["max_mass_kg_m"] + 1e-9:
        return False
    if spec.get("allow") and not any(re.match(a, lab) for a in spec["allow"]):
        return False
    return True


def plastic_props(lab):
    """(A, Zx, Zy) without registering a built-up label (plates; rolled from the table)."""
    pb = parse_built_up(lab)
    if pb:
        k, d = pb
        if k == "box":
            B, D, tf, tw = d
            dw = D - 2 * tf
            return 2 * B * tf + 2 * dw * tw, B * tf * (D - tf) + 2 * tw * (dw / 2.0) ** 2, \
                dw * tw * (B - tw) + 2 * tf * (B / 2.0) ** 2
        D, bf, tf, tw = d
        hw = D - 2 * tf
        return 2 * bf * tf + hw * tw, bf * tf * (D - tf) + tw * hw ** 2 / 4.0, tf * bf ** 2 / 2.0 + hw * tw ** 2 / 4.0
    p = _S().props(lab)
    return float(p["A"]), float(p.get("Zx") or 0.0), float(p.get("Zy") or 0.0)


def eligible(x, specs, skip=()):
    """A design counts as a re-sized design only when every sized group is in its own families (or the built-up
    fallback): the gold's own (NPB / WPB) sections never count as the best design.  skip: groups no member of the
    model takes (dead branches of the cfg's section functions, e.g. IN_Ex11 corner columns that are all braced)."""
    for g, (lab, grade) in x.items():
        sp = specs.get(g) or {}
        if sp.get("role") == "fixed" or sp.get("same_as") or g in skip:
            continue
        fams = sp.get("families") or FAMILIES_BY_ROLE.get(sp.get("role", "beam"), [])
        bu = sp.get("built_up", BUILT_UP_BY_ROLE.get(sp.get("role")))
        f = family_of(lab)
        if f in fams:
            continue
        if bu == "box" and f == "BOX" or bu in ("welded_I", "welded_I_brace") and f == "WI":
            continue
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
    d = os.path.dirname(os.path.abspath(path))
    sys.path.insert(0, d)               # job-local modules (IN_Ex15 / IN_Ex17: hrb_build.py next to cfg.py)
    try:
        exec(compile(src, os.path.abspath(path), "exec"), mod.__dict__)
    finally:
        if sys.path and sys.path[0] == d:
            sys.path.pop(0)
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


def probe_secondary(job_dir, sections):
    """cfg['secondary_members'] index -> group: the declared secondary members (lean-to beams, purlins, struts)
    whose section is one of the sized groups, found by executing the cfg with the probe labels."""
    S = _S()
    plabs = {}
    for k, (g, lab) in enumerate(sorted(sections.items())):
        register(lab)
        pl = "%s#P%d" % (lab, k)
        S.CUSTOM[S.normalize_label(pl)] = dict(S.props(lab))
        plabs[g] = pl
    with contextlib.redirect_stdout(io.StringIO()):
        mod = exec_cfg(os.path.join(job_dir, "cfg.py"), {"SECTIONS": plabs})
    back = {S.normalize_label(v): g for g, v in plabs.items()}
    out = {}
    for i, s_ in enumerate(mod.cfg.get("secondary_members") or []):
        g = back.get(S.normalize_label(str(s_.get("section") or "")))
        if g is not None:
            out[i] = g
    return out


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
    cap = {"elems": {}, "s12": None, "calls": {}}
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
                # every call is kept: the IS 1893 7.11.2 gravity-column check calls the member check again for the
                # same element with its own (R x displacement) records, after the strength check
                rec = {"member": copy.deepcopy(elem["member"]), "kind": elem["kind"],
                       "records": getattr(DP, "member_check_records", DP._top_records)(elem["records"])}
                t_ = int(elem["member"]["tag"])
                if t_ in cap["elems"]:
                    cap["elems"][t_].setdefault("more", []).append(rec)
                else:
                    cap["elems"][t_] = rec
                return _mc(cfg, elem)

            def s12(system, md, s12cfg):
                cap["s12"] = (system, copy.deepcopy(md), copy.deepcopy(s12cfg))
                return _s12(system, md, s12cfg)
            DP.member_checks_is800 = mc
            S12.section12_checks = s12
            # the exact (member, combination forces) of every member check the engine makes for a model element --
            # whatever combination filter the pipeline applies, the local check sees the same list
            import india_is800 as I8m
            _mci = I8m.member_check_is800

            def mci(member, combo_forces, *, cfg=None):
                if isinstance(member, dict) and member.get("tag") is not None:
                    cap["calls"].setdefault(int(member["tag"]), []).append(
                        {"member": copy.deepcopy(member), "cf": copy.deepcopy(combo_forces)})
                return _mci(member, combo_forces, cfg=cfg)
            I8m.member_check_is800 = mci
            import india_seismic as ISM
            _irr = ISM.irregularity_screens

            def irr(cfg_, run_):
                out_ = _irr(cfg_, run_)
                try:          # Delta_max / Delta_ave per loading direction (the package keeps only the largest)
                    res["torsion_by_dir"] = {d: max(v["ratio"]) for d, v in (run_.get("drift") or {}).items()}
                except Exception:
                    pass
                return out_
            ISM.irregularity_screens = irr
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
            import report_first_wave as RF               # the take-off the report prints (design/takeoff.json)
            RF.takeoff_section(E.CFG.get(name, cfg), pkg, root=run_dir)
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
    out["torsion"] = {d: float(v) for d, v in (res.get("torsion_by_dir") or {}).items()}
    out["torsion_fail"] = any(r.startswith("irregularity.torsion") for r in blocking)
    md_ = (pkg.get("irregularity") or {}).get("modes") or {}
    out["modes_mass"] = {d: float(md_["first3_mass_" + d.lower()]) for d in ("X", "Y")
                         if isinstance(md_.get("first3_mass_" + d.lower()), (int, float))}
    out["modes_fail"] = any(r.startswith("irregularity.modes") for r in blocking)
    out["periods"] = {d: float(md_["T" + d.lower()]) for d in ("X", "Y") if isinstance(md_.get("T" + d.lower()), (int, float))}
    ss_ = ((pkg.get("irregularity") or {}).get("soft_storey") or {}).get("by_direction") or {}
    out["soft"] = {d: [(int(i), float((v.get("ratio_to_above") or [None] * (i + 1))[i] or 1.0))
                       for i in (v.get("soft_storey_indices") or [])] for d, v in ss_.items() if isinstance(v, dict)}
    out["dynamic_wind_fail"] = (pkg.get("gates") or {}).get("dynamic_wind") is False
    return out


TORSION_TARGET = 1.2 * 0.97         # Table 5(i) (Amd 2) regular band <= 1.2, with a margin


def torsion_groups(lm, d):
    """The lateral groups that resist the torsion of a d-direction loading with their lever arm: the members of the
    frames in the other plan direction (beams / braces whose frame direction is the other one) and the lateral
    columns sized for bending stiffness (moment-frame columns; the columns of braced bays, sized for axial stiffness,
    are left out)."""
    other = "X" if d == "Y" else "Y"
    if lm.s12 is None:
        return []
    out = set()
    for m in lm.s12[1].get("members") or []:
        t = int(m.get("tag") or str(m["id"]).lstrip("e"))
        g = lm.groups_of.get(t)
        if g is None or (lm.specs.get(g) or {}).get("role") in ("fixed", "link"):
            continue
        sp = lm.specs.get(g) or {}
        if m.get("frame_dir") == other and (sp.get("lateral") or m.get("role") == "brace"):
            out.add(g)
        elif m.get("role") == "column" and sp.get("lateral") and \
                sp.get("stiff", STIFF_BY_ROLE.get(sp.get("role"))) == "I":
            out.add(g)            # moment-frame columns (bending stiffness); braced-bay columns (axial) are left out
    return sorted(out)


def torsion_requirements(lm, ev, x, st):
    """IS 1893 Table 5(i): when the run is torsionally irregular (Delta_max / Delta_ave > 1.2 in a direction d), the
    groups that give the torsional stiffness for that direction (torsion_groups) keep at least their stiffness x
    (ratio - 1) / (TORSION_TARGET - 1) from now on (ratio - 1 is proportional to K_d / K_theta)."""
    req = st.setdefault("tor_req", {})
    if ev.get("torsion_fail"):
        for d, r in sorted((ev.get("torsion") or {}).items()):
            if r <= 1.2:
                continue
            f = min(max((r - 1.0) / (TORSION_TARGET - 1.0), 1.05), 1.6)
            for g in torsion_groups(lm, d):
                kind = lm.specs[g].get("stiff", STIFF_BY_ROLE.get(lm.specs[g].get("role")))
                if not kind:
                    continue
                need = stiffness(x[g][0], kind) * f
                if need > req.get(g, 0.0):
                    req[g] = round(need, 1)
                    log("    torsion %s (Delta_max / Delta_ave %.3f): %s keeps %s >= %.4g" % (d, r, g, kind, need))
    if ev.get("dynamic_wind_fail"):
        # IS 875-3 9.1(b): a first-mode frequency below 1 Hz calls for the 10.2 / 10.3 dynamic wind response, which
        # the job does not declare: keep T <= 0.97 s in that direction (K ~ 1 / T^2) with the frames of that direction
        for d, T in sorted((ev.get("periods") or {}).items()):
            if T <= 1.0:
                continue
            f = min(max((T / 0.97) ** 2, 1.05), 1.6)
            for g in torsion_groups(lm, "X" if d == "Y" else "Y"):
                kind = lm.specs[g].get("stiff", STIFF_BY_ROLE.get(lm.specs[g].get("role")))
                if not kind:
                    continue
                need = stiffness(x[g][0], kind) * f
                if need > req.get(g, 0.0):
                    req[g] = round(need, 1)
                    log("    period T%s %.3f s > 1 s (IS 875-3 9.1(b)): %s keeps %s >= %.4g" % (d.lower(), T, g, kind, need))
    for d, lst in sorted((ev.get("soft") or {}).items()):
        # IS 1893 Table 6(i): storey i softer than the storey above (K_i < K_i+1) -- the drift limit of that storey
        # and below drops to 0.2 %: the braces (else the columns) of storey i keep their stiffness x (K_i+1 / K_i) / 0.97
        for i, ratio in lst:
            gs = set()
            mems = (lm.s12[1].get("members") or []) if lm.s12 is not None else []
            lv = i + 1 if any(m.get("role") == "column" and m.get("level") == i + 1 for m in mems) else i   # storeys 1-based
            # a braced storey is stiffened through its braces (brace levels count from 0), a moment-frame storey
            # through its columns
            br = [m for m in mems if m.get("role") == "brace" and m.get("level") == i]
            for m in (br or [m for m in mems if m.get("role") == "column" and m.get("level") == lv]):
                g = lm.groups_of.get(int(m.get("tag") or str(m["id"]).lstrip("e")))
                if g is not None and lm.specs.get(g, {}).get("role") not in (None, "fixed"):
                    gs.add(g)
            f = min(max(1.0 / max(ratio, 0.3) / 0.97, 1.05), 1.6)
            for g in sorted(gs):
                kind = lm.specs[g].get("stiff", STIFF_BY_ROLE.get(lm.specs[g].get("role")))
                if not kind:
                    continue
                need = stiffness(x[g][0], kind) * f
                if need > req.get(g, 0.0):
                    req[g] = round(need, 1)
                    log("    soft storey %d (%s, K / K above %.2f): %s keeps %s >= %.4g" % (i + 1, d, ratio, g, kind, need))
    kl = [r for r in ev.get("s12_fail") or [] if "7_2_column_KL_r" in str(r.get("id")) and
          isinstance(r.get("dc"), (int, float)) and r["dc"] > 1.0]
    if kl:
        # IS 18168 7.2 column KL/r with K from the beam / column stiffness ratio (IS 800 Annex D, e.g. the IN_Ex12 gym):
        # the column's own step-up raises its stiffness share and K with it, so the moment-frame beams are stiffened
        st["kl_fail"] = int(st.get("kl_fail") or 0) + 1
        f = min(max(max(r["dc"] for r in kl) ** 2, 1.1), 1.6)
        for g, sp in sorted(lm.specs.items()):
            if sp.get("role") == "beam" and sp.get("lateral") and lm.by_group.get(g):
                need = stiffness(x[g][0], "I") * f
                if need > req.get(g, 0.0):
                    req[g] = round(need, 1)
                    log("    IS 18168 7.2 column KL/r %.2f: %s keeps I >= %.4g (K follows the beam stiffness)"
                        % (max(r["dc"] for r in kl), g, need))
    per = ev.get("periods") or {}
    if ev.get("modes_fail") and all(v >= 0.65 for v in (ev.get("modes_mass") or {}).values()) and \
            len(per) == 2 and abs(per["X"] - per["Y"]) / max(per.values()) < 0.10:
        # IS 1893 Table 6(vii), Zones IV / V: the fundamental Tx and Ty at least 10 % apart -- the frames of the stiffer
        # direction (beams / braces of that frame direction; the columns stiffen both) are made stiffer still
        d = "X" if per["X"] < per["Y"] else "Y"
        f = min(max((min(per.values()) * 1.12 / max(per.values())) ** 2, 1.05), 1.5)
        gs = set()
        for m in (lm.s12[1].get("members") or []) if lm.s12 is not None else []:
            g = lm.groups_of.get(int(m.get("tag") or str(m["id"]).lstrip("e")))
            if g is not None and m.get("frame_dir") == d and lm.specs.get(g, {}).get("role") in ("beam", "brace") \
                    and lm.specs[g].get("lateral"):
                gs.add(g)
        for g in sorted(gs):
            kind = lm.specs[g].get("stiff", STIFF_BY_ROLE.get(lm.specs[g].get("role")))
            need = max(stiffness(x[g][0], kind), req.get(g, 0.0)) * f
            req[g] = round(need, 1)
            log("    modes: Tx %.3f / Ty %.3f s less than 10 %% apart: %s (frame %s) keeps %s >= %.4g"
                % (per["X"], per["Y"], g, d, kind, need))
    if ev.get("modes_fail"):
        # IS 1893 Table 6(vii): the d-direction mass sits in rotation-dominant modes (translation coupled with
        # torsion): a stiffer torsional system for that direction separates them -- the same groups, 25 % up
        for d, mass in sorted((ev.get("modes_mass") or {}).items()):
            if mass >= 0.65:
                continue
            for g in torsion_groups(lm, d):
                kind = lm.specs[g].get("stiff", STIFF_BY_ROLE.get(lm.specs[g].get("role")))
                if not kind:
                    continue
                need = max(stiffness(x[g][0], kind), req.get(g, 0.0)) * 1.25
                req[g] = round(need, 1)
                log("    modes %s (first three translational modes %.0f %% of the mass): %s keeps %s >= %.4g"
                    % (d, 100.0 * mass, g, kind, need))
    # IS 18168 12.3.3.1 link rotation: the plastic rotation follows the storey drift (theta_p L / e), which no link
    # section changes much -- the braces of those links keep A x ratio^2 x 1.03 from now on (stiffer storey)
    links = {str(ln.get("id")): ln for ln in ((lm.s12[1].get("links") or []) if lm.s12 is not None else [])}
    for r_ in ev.get("s12_fail") or []:
        if "link_rotation" not in str(r_.get("id")) or not isinstance(r_.get("dc"), (int, float)) or r_["dc"] <= 1.0:
            continue
        ln = links.get(str(r_.get("member")))
        if not ln:
            continue
        f = min(max(float(r_["dc"]) ** 2 * 1.03, 1.05), 1.35)
        for bid in ln.get("brace_ids") or []:
            g = lm.groups_of.get(int(str(bid).lstrip("e"))) if str(bid).lstrip("e").isdigit() else None
            if g is None or g not in x or (lm.specs.get(g) or {}).get("role") == "fixed":
                continue
            need = stiffness(x[g][0], "A") * f
            if need > req.get(g, 0.0) * 1.0001:
                req[g] = round(need, 1)
                log("    link rotation %s (%.3f): %s keeps A >= %.4g" % (r_.get("member"), r_["dc"], g, need))
    return {g: v for g, v in req.items()}


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
        self._more = {t: [(x["member"], SM.combo_forces_for_member_check(x["records"], x["kind"]))
                          for x in e.get("more") or []] for t, e in self.elems.items() if e.get("more")}
        # captures from 2026-11-06: the engine's own calls (member, combination forces) per element
        self._calls = {t: [(c["member"], c["cf"]) for c in v] for t, v in (cap.get("calls") or {}).items() if v}
        self.by_group = {}
        self._dem = {}
        self._md_cache = {}
        self._t2 = {}
        self.secondary = {}
        for t in sorted(self.elems):
            g = groups_of.get(t)
            if g is not None:
                self.by_group.setdefault(g, []).append(t)

    def member_dc(self, t, label, grade):
        """Strength and Table 3 ratios of element t with a candidate section: the governing of every member check the
        run made for it (the strength check and, for a gravity column, the IS 1893 7.11.2 check).  Memoised per
        (element, label, grade) for the run."""
        memo = self.__dict__.setdefault("_dc_memo", {})
        key = (t, label, grade)
        if key not in memo:
            memo[key] = self._member_dc0(t, label, grade)
        return memo[key]

    def _group_order(self, g):
        """The group's elements, the most loaded first (strength ratio with the run's own section), so that a candidate
        that fails is rejected after its first elements."""
        cache = self.__dict__.setdefault("_order", {})
        if g not in cache:
            tags = list(self.by_group.get(g, []))
            lab = (self.sections or {}).get(g)

            def cur(t):
                sec = lab or ((self.elems.get(t) or {}).get("member") or {}).get("section")
                if not sec:
                    return 0.0
                try:
                    return self.member_dc(t, sec, None)[0]
                except Exception:
                    return 0.0
            cache[g] = sorted(tags, key=lambda t: (-cur(t), tags.index(t)))
        return cache[g]

    def _member_dc0(self, t, label, grade):
        calls = self._calls.get(t)
        if calls:
            st = t3 = 0.0
            for i, (mem, cf) in enumerate(calls):
                st2, t32, err = self._member_dc1(t, mem, self._short_cf(t, i, mem, cf), label, grade)
                if err:
                    return st2, t32, err
                st, t3 = max(st, st2), max(t3, t32)
            return st, t3, None
        st, t3, err = self._member_dc1(t, self.elems[t]["member"], self._cf[t], label, grade)
        for mem, cf in self._more.get(t, ()):
            if err:
                break
            st2, t32, err = self._member_dc1(t, mem, cf, label, grade)
            st, t3 = max(st, st2), max(t3, t32)
        return st, t3, err

    def _short_cf(self, t, i, mem, cf):
        """The combinations a candidate section is checked with (the local prediction only; the full run checks every
        one).  Since the engine checks every combination with both signs (2026-11), a tall job's element carries 100+
        of them, and each candidate of each group re-checks them all.  An element with more than SHORT_CF_FROM keeps,
        in the run's order: the SHORT_CF combinations with the largest linear stress index at its current section,
        |P|/A + |Mz|/Zz + |My|/Zy (plastic properties, the largest end or mid moment), and for each force the two
        largest of each sign.  Computed once per element and run."""
        if len(cf) <= SHORT_CF_FROM:
            return cf
        cache = self.__dict__.setdefault("_short_cache", {})
        key = (t, i)
        if key in cache:
            return cache[key]
        try:
            A, Zz, Zy = plastic_props(mem["section"])
        except Exception:
            cache[key] = cf
            return cf

        def f(c, k):
            return float(c.get(k) or 0.0)

        def idx(c):
            mz = max(abs(f(c, "Mz_i_Nmm")), abs(f(c, "Mz_j_Nmm")), abs(f(c, "Mz_mid_Nmm")))
            my = max(abs(f(c, "My_i_Nmm")), abs(f(c, "My_j_Nmm")))
            return abs(f(c, "P_N")) / max(A, 1.0) + mz / max(Zz, 1.0) + my / max(Zy, 1.0)
        ks = range(len(cf))
        keep = set(sorted(ks, key=lambda k: (-idx(cf[k]), k))[:SHORT_CF])
        for fld in sorted({k for c in cf for k, v in c.items() if isinstance(v, (int, float))}):
            keep |= set(sorted(ks, key=lambda k: (-f(cf[k], fld), k))[:2])
            keep |= set(sorted(ks, key=lambda k: (f(cf[k], fld), k))[:2])
        out = [c for k, c in enumerate(cf) if k in keep]
        cache[key] = out
        return out

    def set_secondary(self, sec_map):
        """sec_map: cfg['secondary_members'] index -> group (probe_secondary)."""
        lst = self.cfg.get("secondary_members") or []
        self.secondary = {}
        for i, g in sorted(sec_map.items()):
            if int(i) < len(lst):
                self.secondary.setdefault(g, []).append(lst[int(i)])

    def secondary_dc(self, s_, label, grade):
        """The engine's own check of a declared secondary member (design_pipeline.secondary_member_checks /
        secondary_strut_checks) with a candidate section: its governing D/C, None when it cannot be formed."""
        import design_pipeline as DP
        register(label)
        s2 = dict(s_, section=label)
        if grade:
            s2["grade"] = grade
        try:
            with contextlib.redirect_stdout(io.StringIO()):
                if str(s2.get("kind") or "").lower() == "strut":
                    r = DP.secondary_strut_checks(self.cfg, s2)
                else:
                    r = DP.secondary_member_checks(self.cfg, s2, DP.secondary_member_demand(self.cfg, s2))
        except Exception:
            return None
        if any(c.get("ok") is False for c in r.get("checks") or []):
            return max(1.01, float(r.get("DC") or 0.0))
        return r.get("DC")

    def _member_dc1(self, t, member, cf, label, grade):
        import india_is800 as I8
        register(label)
        e = {"member": member}
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
            r = I8.member_check_is800(m, cf, cfg=self.cfg)
        except Exception as ex:
            return 99.0, 99.0, "error %s" % ex
        if r.get("dc") is None:
            return 99.0, 99.0, r.get("reason")
        st = r.get("interaction_dc", r["dc"])
        t3 = (r.get("table3_slenderness") or {}).get("dc") or 0.0
        return float(st), float(t3), None

    def group_ok(self, g, label, grade, margin):
        worst = (0.0, 0.0)
        for t in self._group_order(g):
            st, t3, err = self.member_dc(t, label, grade)
            if err or st > margin + 1e-9 or t3 > 1.0 + 1e-9:
                return False, (st, t3)
            worst = (max(worst[0], st), max(worst[1], t3))
        for s_ in self.secondary.get(g, ()):
            dc = self.secondary_dc(s_, label, grade)
            if dc is None or dc > margin + 1e-9:
                return False, (dc if dc is not None else 99.0, worst[1])
            worst = (max(worst[0], dc), worst[1])
        bad = self.self_rows(g, label, grade)
        if bad:
            return False, (worst[0], 99.0)
        if (self.specs.get(g) or {}).get("role") == "gantry":
            dc = self.gantry_dc(label, grade)
            if dc is None or dc > margin + 1e-9:
                return False, (dc if dc is not None else 99.0, worst[1])
            worst = (max(worst[0], dc), worst[1])
        return True, worst

    def _sub_md(self, g):
        """The Section 12 model data reduced to one group's members (their forces and links): the base of the group's
        own Section 12 rows (Table 2, brace / column / link proportioning rules) for a candidate section."""
        if g in self._md_cache:
            return self._md_cache[g]
        if self.s12 is None:
            self._md_cache[g] = None
            return None
        system, md, sc = self.s12
        tags = set(self.by_group.get(g) or [])
        mems = [m for m in md.get("members") or [] if int(m.get("tag") or str(m["id"]).lstrip("e")) in tags]
        ids = {m["id"] for m in mems}
        sub = {k: v for k, v in md.items() if k not in ("members", "forces", "links", "joints", "connections", "bases",
                                                         "brace_lines")}
        sub["members"] = mems
        sub["forces"] = {i: md.get("forces", {}).get(i, []) for i in ids}
        sub["links"] = [ln for ln in md.get("links") or [] if ln.get("member_id") in ids]
        sub["joints"], sub["connections"], sub["bases"], sub["brace_lines"] = [], [], [], []
        self._md_cache[g] = (system, sub, sc)
        return self._md_cache[g]

    def self_rows(self, g, label, grade):
        """The failing Section 12 rows that depend on the group's own section only (SELF_S12_ROWS), for a
        candidate: [row id, ...]."""
        import india_is800_s12 as S12
        base = self._sub_md(g)
        if not base or not base[1]["members"]:
            return []
        system, sub, sc = base
        bad = self._table2_screen(g, label, grade)
        if bad:
            return bad
        md = md_copy(sub)
        register(label)
        for m in md["members"]:
            _substitute(m, label, grade, self.cfg)
        for ln in md["links"]:
            ln["section"] = label
            if grade:
                ln["grade"] = grade
        try:
            r = S12.section12_checks(system, md, sc)
        except Exception:
            return []
        return [c.get("id") for c in r.get("checks") or []
                if c.get("ok") is False and SELF_S12_ROWS.search(str(c.get("id")))]

    def _table2_screen(self, g, label, grade):
        """Quick IS 18168 Table 2 width-thickness screen of a candidate (india_is18168.table2_check), live only for a
        group whose current section gets a Table 2 row in the Section 12 checks (that row's component)."""
        import india_is18168 as I18
        import india_is800 as I8
        if g not in self._t2:
            self._t2[g] = None
            base = self._sub_md(g)
            if base and base[1]["members"]:
                import india_is800_s12 as S12
                try:
                    r = S12.section12_checks(base[0], copy.deepcopy(base[1]), base[2])
                    ids = [str(c.get("id")) for c in r.get("checks") or [] if str(c.get("id")).startswith("is18168_table2_")]
                    if ids:
                        self._t2[g] = ids[0].replace("is18168_table2_", "")
                except Exception:
                    pass
        comp = self._t2[g]
        if not comp:
            return []
        try:
            p = props(label)
        except Exception:
            return ["props"]
        if p.get("section_type") not in I18.TABLE2_SECTION_TYPES:
            return []
        gr = grade or self.cfg.get("steel_grade")
        fy = I8.material_for_section(p, gr).get("fy_MPa") or 250.0
        key = I8.parse_is2062_grade(str(gr))[0]
        Ry = I18.ry_for_grade(key) or 1.4
        Ca = None
        if comp == "column":
            Ca = self.group_demand(g)["N"] / (fy * float(p["A"]) / 1.1)
        r = I18.table2_check(comp, p, fy, Ry, Ca=Ca)
        return [] if r.get("ok") is not False else ["is18168_table2_%s (screen)" % comp]

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
        register(label)
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
        # the vertical deflection under the static wheel loads scales exactly with 1 / Ix: the Ix it asks for screens
        # the remaining candidates (gantry_ix_req)
        dv = [c["dc"] for c in r.get("checks") or [] if isinstance(c.get("dc"), (int, float)) and
              "vertical deflection" in str(c.get("name") or c.get("id") or "")]
        if dv:
            self._gantry_ix = max(getattr(self, "_gantry_ix", 0.0), float(props(label)["Ix"]) * max(dv))
        if any(c.get("ok") is None for c in r.get("checks") or []):
            return None
        return max(dcs) if dcs else None

    def gantry_ix_req(self, margin):
        return getattr(self, "_gantry_ix", 0.0) / max(margin, 1e-6)

    def _gantry_group(self):
        return next((g for g, sp in self.specs.items() if sp.get("role") == "gantry"), None)

    def group_demand(self, g):
        """Largest |N|, |Mz|, |My| over the group's elements and combinations (frozen forces), for the screen."""
        if g in self._dem:
            return self._dem[g]
        N = Mz = My = 0.0
        for t in self.by_group.get(g, []):
            for c in self._cf[t]:
                N = max(N, abs(c.get("P_N") or 0.0))
                Mz = max(Mz, abs(c.get("Mz_i_Nmm") or 0.0), abs(c.get("Mz_j_Nmm") or 0.0), abs(c.get("Mz_mid_Nmm") or 0.0))
                My = max(My, abs(c.get("My_i_Nmm") or 0.0), abs(c.get("My_j_Nmm") or 0.0), abs(c.get("My_mid_Nmm") or 0.0))
        self._dem[g] = {"N": N, "Mz": Mz, "My": My}
        return self._dem[g]

    def group_length_mm(self, g):
        return sum(float(self.elems[t]["member"].get("L_mm") or 0.0) for t in self.by_group.get(g, []))


def _capacity_screen(lab, grade, dem, tube=False):
    """Cheap necessary conditions before the exact checks: squash load A fy / gamma_m0 >= the largest compression or
    tension, plastic moments Zp fy / gamma_m0 >= 0.9 x the largest end / span moments (the exact checks decide)."""
    try:
        A, Zx, Zy = plastic_props(lab)
    except Exception:
        return False
    fy = 310.0 if tube else (350.0 if "350" in str(grade or "") else 250.0)
    cap = fy / 1.1
    if A * cap < dem["N"] * 0.98:
        return False
    if Zx * cap < 0.9 * dem["Mz"] or Zy * cap < 0.9 * dem["My"]:
        return False
    return True


def stiffness(label, kind):
    p = props(label)
    if kind == "A":
        return float(p["A"])
    return float(p["Ix"])


def size_groups(lm, x, margins, stiff_req, *, log_fn=log, fixed=(), barred=None, conn_req=None):
    """Lightest candidate per group under the frozen forces.  x: {group: (label, grade)}; stiff_req: {group:
    minimum stiffness (I or A)}.  Returns the new x and a per-group note."""
    new, notes = {}, {}
    for g in sorted(lm.specs):
        spec = lm.specs[g]
        if spec.get("role") == "fixed" or g in fixed or spec.get("same_as"):
            new[g] = x[g]
            continue
        if not lm.by_group.get(g) and spec.get("role") != "gantry" and not lm.secondary.get(g):
            new[g] = x[g]                   # a gantry girder or a secondary member is sized from its own checks
            notes[g] = "no elements"
            continue
        kind = spec.get("stiff", STIFF_BY_ROLE.get(spec.get("role")))
        need = stiff_req.get(g)
        chosen = None
        dem = lm.group_demand(g)
        bar = set((barred or {}).get(g) or ())
        try:
            m_cap = MASS_SPAN_MAX * mass_kg_m(x[g][0])
        except Exception:
            m_cap = None
        # the caps are for a group whose own section passes (a lighter one is looked for); a group that must change
        # searches on
        try:
            cur_ok = lm.group_ok(g, x[g][0], x[g][1], margins.get(g, spec.get("margin", 0.95)))[0]
        except Exception:
            cur_ok = False
        if not cur_ok:
            m_cap = None
        max_evals = MAX_EVALS if cur_ok else 10 * MAX_EVALS
        n_eval = 0
        for lab, grade, tier in candidates(spec):
            if lab in bar:
                continue
            if m_cap is not None and need is None and mass_kg_m(lab) > m_cap:
                continue              # no stiffness asked: a candidate more than MASS_SPAN_MAX x the current mass
            if not _capacity_screen(lab, grade, dem, family_of(lab) == "CHS"):
                continue
            if spec.get("role") == "gantry":
                register(lab)
                if float(props(lab)["Ix"]) < lm.gantry_ix_req(margins.get(g, spec.get("margin", 0.95))) * 0.999:
                    continue
            if need and kind and stiffness(lab, kind) < need - 1e-6:
                continue
            n_eval += 1               # full evaluations only
            if n_eval > max_evals:
                break                 # a row no candidate answers (e.g. a drift-driven link rotation): keep the section
            ok, worst = lm.group_ok(g, lab, grade, margins.get(g, spec.get("margin", 0.95)))
            if ok and (conn_req or {}).get(g) and design_fin_plate(lab, conn_req[g][0], conn_req[g][1],
                                                                          n_frac=(conn_req[g][2:3] or [0.0])[0]) is None:
                ok = False                    # the beam-end connection (V + N) of an earlier run does not fit
            if ok:
                chosen = (lab, grade)
                notes[g] = "%s %s tier %d: strength %.3f slender %.3f" % (lab, grade or "", tier, worst[0], worst[1])
                break
        if chosen is not None and spec.get("role") == "link":
            chosen, note = _least_overstrength_link(lm, g, spec, chosen, dem, margins, bar, conn_req)
            if note:
                notes[g] = note
        if chosen is None:
            chosen = x[g]
            notes[g] = "no candidate passes: kept %s" % (x[g],)
        new[g] = chosen
    for g in sorted(lm.specs):
        if lm.specs[g].get("same_as"):
            new[g] = new[lm.specs[g]["same_as"]]
    return new, notes


def link_vp(label, grade=None):
    """Plastic shear strength of a link web, 0.6 fy (d - 2 tf) tw (N; IS 18168 / IS 800 12.11 Vp), fy from the
    IS 2062 band of the web."""
    register(label)
    p = props(label)
    tw = float(p["tw"])
    return 0.6 * plate_fy(tw, grade or "E250") * (float(p["d"]) - 2.0 * float(p["tf"])) * tw


def _least_overstrength_link(lm, g, spec, first, dem, margins, bar, conn_req, *, mass_span=1.3, max_evals=60):
    """EBF links: every brace, beam outside the link and column (and its base) is designed for the link overstrength
    1.1 Ry Vp, so among the candidates of the first passing one's tier (rolled stays rolled) that pass within
    mass_span x its mass, the one with the least web shear strength Vp is taken.  Returns (choice, note)."""
    lab0, gr0 = first
    cands = candidates(spec)
    tier0 = next((t for (l, gr, t) in cands if l == lab0 and gr == gr0), None)
    m0, vp0 = mass_kg_m(lab0), link_vp(lab0, gr0)
    best, best_vp, n = first, vp0, 0
    for lab, grade, tier in cands:
        if tier != tier0 or lab in bar or (lab, grade) == first:
            continue
        if mass_kg_m(lab) > mass_span * m0:
            continue
        vp = link_vp(lab, grade)
        if vp >= 0.97 * best_vp:
            continue
        if not _capacity_screen(lab, grade, dem, False):
            continue
        n += 1
        if n > max_evals:
            break
        ok, worst = lm.group_ok(g, lab, grade, margins.get(g, spec.get("margin", 0.95)))
        if ok and (conn_req or {}).get(g) and design_fin_plate(lab, conn_req[g][0], conn_req[g][1],
                                                                          n_frac=(conn_req[g][2:3] or [0.0])[0]) is None:
            ok = False
        if ok:
            best, best_vp = (lab, grade), vp
    if best == first:
        return first, None
    return best, ("%s %s tier %d: least link overstrength, Vp %.0f kN (lightest passing %s, Vp %.0f kN)"
                  % (best[0], best[1] or "", tier0, best_vp / 1e3, lab0, vp0 / 1e3))


_STACK_RX = re.compile(r"^(?P<base>.+?)_(?:(?P<a>\d+)(?:_(?P<b>\d+))?|(?P<w>lo|hi|roof))$")


def column_stacks(specs):
    """Lateral column groups that are the same frame columns over storey ranges, bottom first, from the group names:
    '<base>_<i>_<j>' / '<base>_<i>' (storeys from i), '<base>_lo' / '<base>_hi'.  {base: [group, ...]}."""
    st = {}
    for g, sp in specs.items():
        if sp.get("role") != "column" or not sp.get("lateral"):
            continue
        m = _STACK_RX.match(g)
        if not m:
            continue
        key = int(m.group("a")) if m.group("a") is not None else {"lo": 0, "hi": 1000, "roof": 2000}[m.group("w")]
        st.setdefault(m.group("base"), []).append((key, g))
    return {b: [g for _, g in sorted(v)] for b, v in st.items() if len(v) > 1}


def monotone_columns(x, specs, log_fn=log, lm=None, margins=None, barred=None):
    """IS 1893 Table 6(i) soft storey (K_i < K_i+1): a lateral column group is never less stiff (Ix) than the same
    columns in the storeys above it.  Where the sizing made it so, the lower group is sized again with the upper
    group's Ix as its minimum stiffness (lightest passing candidate, frozen forces); without a local model, or when
    nothing passes, it takes the upper group's section and grade."""
    x = dict(x)
    for base, gs in sorted(column_stacks(specs).items()):
        for k in range(len(gs) - 2, -1, -1):
            lo, up = gs[k], gs[k + 1]
            # the group's own stiffness measure: Ix for moment-frame columns, A for braced-frame columns (stiff 'A')
            kind = specs[lo].get("stiff", STIFF_BY_ROLE.get("column")) or "I"
            Iup = stiffness(x[up][0], kind)
            if Iup <= stiffness(x[lo][0], kind) * 1.0001:
                continue
            new = None
            if lm is not None:
                xx, notes = size_groups(lm, x, margins or {}, {lo: Iup}, log_fn=lambda *a: None,
                                        fixed=[g for g in x if g != lo], barred=barred)
                if "no candidate" not in str(notes.get(lo, "")):
                    new = xx[lo]
                elif lm.group_ok(lo, x[up][0], x[up][1], (margins or {}).get(lo, specs[lo].get("margin", 0.95)))[0]:
                    new = x[up]
                else:
                    continue          # nothing stiffer passes the lower storeys' own checks: keep their section
            new = new or x[up]
            log_fn("    stack %s: %s %s is stiffer than %s %s below it -> %s %s"
                   % (base, up, x[up][0], lo, x[lo][0], lo, "%s %s" % (new[0], new[1] or "")))
            x[lo] = tuple(new)
    return x


def next_up(spec, current, lm=None, g=None, margin=None, min_area=None):
    """The next candidate after `current` (label, grade) in the group's order of preference that is not weaker than
    it (A, Ix, Zx; the same section in a higher grade counts) and passes the frozen member checks (when lm is
    given).  Used to step a group up for a failing Section 12 row that the member checks cannot see (SCWB ...)."""
    cands = candidates(spec)
    cur = (current[0], current[1])
    idx = next((k for k, (l, gr, tr) in enumerate(cands) if (l, gr) == cur), None)
    if idx is None:
        idx = next((k for k, (l, gr, tr) in enumerate(cands) if l == cur[0]), -1)
    cur_fy = 350.0 if "350" in str(cur[1] or "") else 250.0
    for lab, grade, tier in cands[idx + 1:]:
        if (lab, grade) == cur:
            continue
        fy = 350.0 if "350" in str(grade or "") else 250.0
        if lab == cur[0] and fy <= cur_fy:
            continue
        if lab != cur[0] and not (_stronger(lab, cur[0]) and fy >= cur_fy - 1e-9 or
                                  _stronger(lab, cur[0]) and mass_kg_m(lab) > mass_kg_m(cur[0])):
            continue
        if min_area and stiffness(lab, "A") * fy < min_area * cur_fy * (1.0 - 1e-9):
            continue                      # an axial row asks for that much more A fy at once
        if lm is not None:
            ok, _ = lm.group_ok(g, lab, grade, margin)
            if not ok:
                continue
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


# Section 12 rows decided by a member's own section and forces (checked for every candidate in the local sizing)
SELF_S12_ROWS = re.compile(r"(table2|smf_beam_class|smf_column_class|brace_KL_r|brace_plastic|brace_not_slender|"
                           r"brace_compression|brace_gross_yield|7_2_column_KL_r|material_E250B|scbf_column_plastic|"
                           r"link_section|link_length|link_shear|link_rotation)")


def md_copy(md):
    """A copy of Section 12 model data that a candidate may change: the member records (the sizer sets section and
    grade on them) and the links (section12_checks writes into them) are copied; the forces and the other records,
    which neither changes, are shared.  A deep copy of IN_Ex19's model data took 2.8 s, more than the checks."""
    out = dict(md)
    out["members"] = [dict(m) for m in md.get("members") or []]
    out["links"] = copy.deepcopy(md.get("links") or [])
    return out


def _substitute(m, lab, grade, cfg):
    """Put a candidate section (and grade) into a Section 12 member record."""
    if lab == m.get("section") and grade is None:
        return
    m["section"] = lab
    if family_of(lab) == "CHS":
        m["grade"] = cfg.get("tube_grade") or cfg.get("brace_grade")
        m["process"] = cfg.get("tube_process") or cfg.get("brace_process")
        p = props(lab)
        m["An_mm2"] = float(p["A"]) - 2.0 * float(p["tw"]) * 22.0          # slot for a 20 mm gusset (estimate)
    else:
        if grade is not None:
            m["grade"] = grade
        elif str(m.get("grade") or "").upper().replace(" ", "").startswith("YST"):
            m["grade"] = cfg.get("steel_grade")
        if m.get("role") == "brace":
            m["An_mm2"] = float(props(lab)["A"])                         # flanges welded to the gusset, no holes
            m.pop("process", None)


def s12_local(lm, x, *, tags_changed=None, margins=None):
    """Section 12 checks of the model with the proposed sections (frozen forces).  Returns the failing member-level
    rows [(row, group)]; margins {"group::row id": m}: a row of that kind and group with a ratio above m also counts (a row the full run
    failed although the frozen forces passed it -- IS 18168 12.3.2.2 brace axial at the link overstrength)."""
    import india_is800_s12 as S12
    if lm.s12 is None:
        return []
    system, md0, sc = lm.s12
    md = md_copy(md0)
    for m in md.get("members") or []:
        t = int(m.get("tag") or str(m["id"]).lstrip("e"))
        g = lm.groups_of.get(t)
        if g is None or g not in x:
            continue
        lab, grade = x[g]
        register(lab)
        _substitute(m, lab, grade, lm.cfg)
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
        if S12_CONNECTION_ROWS.search(str(c.get("id"))):
            continue
        mid = c.get("member")
        g = lm.groups_of.get(mem_tag.get(mid)) if mid in mem_tag else None
        dc = c.get("dc")
        mk = "%s::%s" % (g, re.sub(r"@.*$", "", str(c.get("id"))))
        if c.get("ok") is False or (mk in (margins or {}) and isinstance(dc, (int, float)) and dc > margins[mk] + 1e-9):
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
    """IS 2062 Table 3 yield stress of a plate of thickness t: the engine's own band function
    (india_is800.fy_is2062, IS 2062:2025 bands <= 16 / > 16-40 / > 40-100 / > 100 mm), so the sizer and the checks
    use one rule.  grade: an IS 2062 designation; anything else is read as E250 (E350 when it says 350)."""
    import india_is800 as I8
    key, _q = I8.parse_is2062_grade(str(grade or ""))
    g = key if key in I8.IS2062_TABLE3 else ("E350" if "350" in str(grade) else "E250")
    return float(I8.fy_is2062(g, float(t)))


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


def design_fin_plate(sec, V_N, template=None, *, V_service_N=None, margin=0.9, n_frac=0.0):
    """Lightest fin plate whose IS 800 checks (bolts 10.3, plate 8.4.1, block shear 6.4.1, CJP weld, HSFG slip 10.4.3
    at the service shear) pass at V_N within the margin, in this order: one fin plate with one bolt line, then two
    lines; then two fin plates (double shear); each with the template's faying surface, then sand-blasted (IS 800
    Table 20, mu 0.48).  Within a tier: fewest bolts, then the thinnest plate.  When none passes, the same search
    with three or four bolt lines.  The service shear is the run's (V_service_N), else V_N / 1.5.  n_frac = the
    axial share N / R of a V + N resultant demand (the eccentric check of a multi-line group takes V and N apart)."""
    Vs = V_service_N if V_service_N is not None else V_N / 1.5
    surf0 = (template or {}).get("slip_surface", "clean_mill_scale")
    for lines in ((1, 2), (3, 4)):
        # three or four bolt lines (the IN_Ex19 collector fins of the published gold: 4 lines x 3 rows of M24 in
        # double shear) only when no one- or two-line plate takes the demand
        sp = _fin_plate_tier(sec, V_N, Vs, template, surf0, lines, margin, n_frac=n_frac)
        if sp is not None:
            return sp
    return None


def _fin_plate_tier(sec, V_N, Vs, template, surf0, lines, margin, n_frac=0.0):
    """design_fin_plate over the given bolt-line counts."""
    nf = min(max(float(n_frac or 0.0), 0.0), 1.0)
    comp = {"V_shear_N": max(float(V_N), 1.0) * math.sqrt(1.0 - nf * nf), "N_axial_N": max(float(V_N), 1.0) * nf}
    import india_connections as C
    import india_connection_design as CD
    trials = []
    for n_lines in lines:
        for d in (20, 24, 30):
            for n in range(2, 13):
                if not fin_plate_fits(sec, n, d):
                    break
                trials.append((n * n_lines * d * d, n_lines, d, n))
    for surface in [surf0] + (["sand_blasted"] if surf0 != "sand_blasted" else []):
        for plates in (1, 2):
            for _, n_lines, d, n in sorted(trials):
                for t in (8.0, 10.0, 12.0, 14.0, 16.0, 20.0, 25.0, 32.0, 40.0, 50.0):   # IN_Ex19 links: 2 x 50 mm
                    sp = fin_plate_spec(sec, n, d, t, dict(template or {}, slip_surface=surface), n_lines=n_lines)
                    if plates == 2:
                        sp = double_fin(sp, sec)
                    kw = {k: v for k, v in sp.items() if k in ("t_plate_mm", "h_plate_mm", "fy_plate_MPa",
                                                                "fu_plate_MPa", "block_shear_areas", "cjp",
                                                                "n_plates", "bolt_lines", "gauge_mm")}
                    kw["bolts"] = dict(sp["bolts"])
                    r = C.fin_plate_shear_checks(V_N=max(float(V_N), 1.0), **kw, **comp)
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
            # CJP = parent metal of the weaker part joined: the brace wall / flange (IS 1161 tube: 250 taken, below
            # YSt 310) or the gusset, each at its IS 2062 thickness band
            "welds": {"cjp": {"t_mm": tw_}, "length_mm": float(Lw),
                      "fy_MPa": min(250.0 if chs else plate_fy(tw_), fyg), "n_sides": 4, "site": False},
            "gusset": {"t_mm": float(tg), "fy_MPa": fyg, "fu_MPa": 410.0, "w_start_mm": w0, "L_conn_mm": float(Lw),
                       "L_unbraced_mm": float(tpl.get("L_unbraced_mm", 250.0)), "K": 0.65,
                       "Avg_mm2": 2.0 * Lw * tg, "Avn_mm2": 2.0 * Lw * tg, "Atg_mm2": w0 * tg, "Atn_mm2": w0 * tg},
            "An_mm2": An,
            "moment_capacity_Nmm": tg * bw ** 2 / 4.0 * fyg / 1.1,
            "moment_capacity_cite": "gusset in-plane plastic moment on the Whitmore width: t bw^2/4 fy/gamma_m0",
            "bolts_and_welds_share": False,
            "K_basis": "gusset K = 0.65 (compact corner gusset; L_unbraced = the free gusset length at the brace end)",
            "detail": detail}


def brace_system(system):
    """The brace branch of a (possibly combined, 'SMRF+SCBF') system string, as section12_checks picks it: the first
    OCBF / SCBF component (EBF braces are checked under 'EBF'); the system itself when it has no braced component."""
    import india_is800_s12 as S12
    comps = S12.system_components(system)
    return next((c for c in comps if c in ("OCBF", "SCBF")), None) or ("EBF" if "EBF" in comps else system)


def design_brace_end(lm, g, sec, grade, template=None, margin=0.95):
    """Lightest gusset (thinnest, then shortest weld length) for which the engine's brace connection checks
    (india_is800_s12.brace_connection_checks, the brace member rules' net-section row) pass for one brace group with
    its proposed section (frozen forces)."""
    import india_is800_s12 as S12
    import india_connection_design as CD
    system, md, sc = lm.s12
    system = brace_system(system)
    tags = lm.by_group.get(g) or []
    mems = [m for m in md.get("members") or [] if int(m.get("tag") or str(m["id"]).lstrip("e")) in tags]
    if not mems:
        return None
    if family_of(sec) not in ("CHS", "HB", "WB", "MB", "NPB", "WPB", "WI"):
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
                # EBF: the connection force follows the link overstrength of the run, which moves with the link
                # sections; the brace's own expected strength 1.1 Ry fy Ag (IS 18168 10.4.1a, the cap) is designed for
                cap_ = None
                if S12.normalize_system(system) == "EBF":
                    dem_ = S12.brace_connection_force(system, m, md, conn=conn, cfg=sc)
                    cap_ = next((v for k, v in (dem_.get("candidates") or {}).items() if "cap" in k), None)
                for r in rows:
                    if r.get("ok") is False or (isinstance(r.get("dc"), (int, float)) and r["dc"] > margin and
                                                r.get("id") != "brace_gross_yield_governs"):
                        ok = False
                        break
                    if cap_ and r.get("id") in ("brace_conn_welds", "brace_conn_block_shear", "gusset_whitmore_yield",
                                                "brace_conn_bolts", "brace_conn_net_rupture") and \
                            isinstance(r.get("limit"), (int, float)) and float(r["limit"]) * margin < float(cap_):
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
    fy = plate_fy(max(float(p["tf"]), float(p["tw"])), "E250")         # the beam's governing thickness band
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


BASE_T_MM = (20.0, 25.0, 28.0, 32.0, 36.0, 40.0, 45.0, 50.0, 56.0, 63.0, 70.0, 80.0, 90.0, 100.0, 110.0, 120.0,
             130.0, 140.0, 150.0)


def _base_t_up(t, factor):
    need = float(t) * factor
    for v in BASE_T_MM:
        if v >= need - 1e-9 and v > float(t) + 1e-9:
            return v
    return BASE_T_MM[-1]


def ring_base(col, template, *, d=None, n=None, t=None, proj=None):
    """A fixed column base with a perimeter ring of anchors (the IN_Ex8 detail) laid out for the column section:
    plate B x L = column footprint + 2 x projection, n anchors on each face (corners shared, 4(n - 1) in all),
    edge 1.7 d0 (IS 800 10.2.4.2 with the rough-edge factor), pitch >= 2.5 d (10.2.2); the embedment record,
    concrete grade, plate grade and other declared items of the template are kept."""
    sp = copy.deepcopy(template)
    p = props(col)
    an = dict(sp.get("anchors") or {})
    d = int(d or an.get("d_mm") or 36)
    d0 = d + (2 if d <= 24 else 3)
    edge = float(math.ceil(1.7 * d0 / 5.0) * 5.0)
    proj = float(proj or max(2.0 * edge + 20.0, 150.0))
    B = float(math.ceil((float(p["bf"]) + 2.0 * proj) / 50.0) * 50.0)
    L = float(math.ceil((float(p["d"]) + 2.0 * proj) / 50.0) * 50.0)
    nmax = int((min(B, L) - 2.0 * edge) // (2.5 * d)) + 1
    n = max(2, min(int(n or an.get("n_per_row") or 3), nmax))
    pitch = (min(B, L) - 2.0 * edge) / (n - 1)
    an.update({"n_total": 4 * n - 4, "n_tension": n, "d_mm": d, "Anb_mm2": ANCHOR_ANB.get(d, an.get("Anb_mm2")),
               "f_mm": L / 2.0 - edge, "pitch_mm": round(pitch, 1), "edge_mm": edge, "n_per_row": n,
               "f_y_mm": B / 2.0 - edge, "n_tension_y": n,
               "note": "perimeter ring: %d anchors on each face (corners shared), %d in total" % (n, 4 * n - 4)})
    an.pop("x_mm", None)
    an.pop("y_mm", None)
    sp["anchors"] = an
    sp["B_mm"], sp["L_mm"] = B, L
    sp["t_plate_mm"] = float(t or sp.get("t_plate_mm") or 50.0)
    sp["fy_plate_MPa"] = plate_fy(sp["t_plate_mm"], sp.get("plate_grade") or "E250")
    sp["fixed"] = True
    sp["layout"] = "ring"
    sp.pop("stiffeners", None)
    return sp


def _adapt_base(template, old_col, new_col):
    """A column base for a new column section from the base of the old one: the plate keeps its projections beyond
    the column (B and L grow or shrink with the column, never below the old anchor layout's fit), the anchors and
    every other declared item (embedment, stiffeners, shear key) are kept; the plate fy follows its thickness."""
    sp = copy.deepcopy(template)
    if old_col == new_col or not isinstance(sp, dict) or sp.get("type") == "embedded":
        return sp
    if sp.get("fixed") and not sp.get("stiffeners") and isinstance(sp.get("anchors"), dict):
        return ring_base(new_col, sp)
    po, pn = props(old_col), props(new_col)
    dB = float(pn["bf"]) - float(po["bf"])
    dL = float(pn["d"]) - float(po["d"])
    for k, dk in (("B_mm", dB), ("L_mm", dL)):
        if k in sp and dk > 0:
            sp[k] = float(math.ceil((float(sp[k]) + dk) / 50.0) * 50.0)
    if sp.get("t_plate_mm"):
        sp["fy_plate_MPa"] = plate_fy(sp["t_plate_mm"], sp.get("plate_grade") or "E250")
    return sp


_GEOM_NOTE = re.compile(r"plate\s+\d+(\.\d+)?\s*x\s*\d+(\.\d+)?\s*x\s*\d+|\b\d+\s*M\d\d\b")


def base_note(sp, note):
    """A base note that states the plate and anchors (IN_Ex14: 'plate 800 x 1400 x 90 (E250, fy 230), 12 M48 8.8
    anchors; grout ...') is re-stated from the base's own geometry; the rest of the note (after the first ';') is
    kept.  Other notes are returned unchanged."""
    if not isinstance(note, str) or not _GEOM_NOTE.search(note):
        return note
    an = sp.get("anchors") or {}
    head = "plate %s x %s x %s (%s, fy %s), %s M%s %s anchors" % (
        _fmt(sp.get("B_mm")), _fmt(sp.get("L_mm")), _fmt(sp.get("t_plate_mm")), sp.get("plate_grade") or "E250",
        _fmt(sp.get("fy_plate_MPa")), an.get("n_total"), an.get("d_mm"), an.get("grade") or "8.8")
    return head + (";" + note.split(";", 1)[1] if ";" in note else "")


_BOND_TEXT = re.compile(r"bond length [0-9.]+ mm into the pedestal / pile cap -> pi d L tau_bd = [0-9.]+ kN per M\d+ "
                        r"anchor")


def _base_stiffeners(st, sp, col):
    """Gusset stiffeners for a fixed base whose plate is at its largest thickness and still fails in bending (IS 800
    7.4.2 gusseted base, the IN_Ex12 detail): a cross of gussets, 3 on each face, CJP to the column and the plate,
    25 mm thick and 0.4 x the plate's projection beyond the column high (at least 300 mm); a declared set is
    stepped one plate up instead."""
    if isinstance(st, dict) and st:
        # the plate still fails between the gussets: one more gusset on each face (shorter plate spans), up to 6
        st = dict(st)
        n = int(st.get("n_per_side") or 2)
        if n < 6:
            st["n_per_side"] = n + 1
            st["n_per_side_y"] = int(st.get("n_per_side_y") or n) + 1
        else:
            st["t_mm"] = min(_plate_up(float(st.get("t_mm") or 20.0), 1.0001), 63.0)
        st["fy_MPa"] = plate_fy(st["t_mm"], st.get("grade") or "E250")
        if isinstance(st.get("note"), str):
            st["note"] = re.sub(r"^\d+ gussets", "%d gussets" % (2 * (int(st["n_per_side"]) + int(st.get("n_per_side_y") or st["n_per_side"]))),
                                st["note"])
        return st
    proj = 200.0
    try:
        p = props(col)
        proj = max((float(sp["L_mm"]) - float(p["d"])) / 2.0, (float(sp["B_mm"]) - float(p["bf"])) / 2.0)
    except Exception:
        pass
    h = float(max(300.0, math.ceil(0.4 * proj * 2.0 / 50.0) * 50.0))
    return {"layout": "cross", "n_per_side": 3, "n_per_side_y": 3, "t_mm": 25.0, "h_mm": h,
            "fy_MPa": plate_fy(25.0, "E250"), "weld_column": {"type": "cjp"}, "weld_plate": {"type": "cjp"},
            "note": "12 gussets %s x 25 (IS 2062 E250, fy %s), CJP with matching electrode" % (_fmt(h), _fmt(plate_fy(25.0, "E250")))}


def _minor_axis_anchors(sp):
    """A rectangular plate (B != L) needs the minor-axis anchor pattern for My (india_connections.
    base_plate_design_biaxial: anchors.f_y_mm / n_tension_y): rows of n_per_row anchors at the pitch, so about the
    minor axis the tension side holds one anchor of each row (n_total / n_per_row) at the outermost position,
    f_y = min(B / 2 - edge, (n_per_row - 1) pitch / 2).  A declared pattern is kept."""
    an = sp.get("anchors") if isinstance(sp, dict) else None
    if not isinstance(an, dict) or an.get("f_y_mm") is not None or "B_mm" not in sp or "L_mm" not in sp:
        return sp
    if abs(float(sp["B_mm"]) - float(sp["L_mm"])) < 1e-6:
        return sp
    n_row = int(an.get("n_per_row") or 2)
    rows = max(1, int(an.get("n_total") or 2 * n_row) // max(n_row, 1))
    d = float(an.get("d_mm") or 24.0)
    edge = float(an.get("edge_mm") or math.ceil(1.7 * (d + 3.0) / 5.0) * 5.0)
    fy_ = float(sp["B_mm"]) / 2.0 - edge
    if an.get("pitch_mm") and n_row > 1:
        fy_ = min(fy_, (n_row - 1) * float(an["pitch_mm"]) / 2.0)
    an["f_y_mm"] = round(fy_, 1)
    an["n_tension_y"] = rows
    return sp


def _restate_base_texts(sp):
    """The base's note (base_note) and the embedment record's bond sentence ('bond length 600 mm into the pedestal /
    pile cap -> pi d L tau_bd = 79 kN per M30 anchor') re-stated from the base's own geometry."""
    if not isinstance(sp, dict):
        return sp
    if sp.get("note"):
        sp["note"] = base_note(sp, sp["note"])
    an = sp.get("anchors") or {}
    emb = an.get("embedment") if isinstance(an, dict) else None
    if isinstance(emb, dict) and isinstance(emb.get("source"), str) and emb.get("L_mm") and emb.get("tau_bd_MPa"):
        d, L = float(an.get("d_mm") or 0.0), float(emb["L_mm"])
        kn = math.pi * d * L * float(emb["tau_bd_MPa"]) / 1000.0
        emb["source"] = _BOND_TEXT.sub("bond length %s mm into the pedestal / pile cap -> pi d L tau_bd = %.0f kN per "
                                       "M%d anchor" % (_fmt(L), kn, int(d)), emb["source"])
    return sp


def adapt_base(template, old_col, new_col):
    """_adapt_base, with the minor-axis anchor pattern of a rectangular plate (_minor_axis_anchors) and the
    geometry-stating texts re-stated (_restate_base_texts)."""
    sp = _adapt_base(template, old_col, new_col)
    return _restate_base_texts(_minor_axis_anchors(sp)) if sp != template else sp


def bump_base(sp, failing, col=None):
    """_bump_base, with _minor_axis_anchors and _restate_base_texts."""
    return _restate_base_texts(_minor_axis_anchors(_bump_base(sp, failing, col=col)))


def _col_pieces(lm):
    """{tag: (section in x, node_i, node_j, role_group)} of the column elements of the run (captured member records)."""
    out = {}
    for t, e in (lm.elems or {}).items():
        m = e.get("member") or {}
        if e.get("kind") not in ("col", "column") and m.get("role") not in ("column", "lateral_col", "gravity_col"):
            continue
        if m.get("node_i") is None or m.get("node_j") is None:
            continue
        out[t] = (m.get("section"), int(m["node_i"]), int(m["node_j"]), m.get("role_group"))
    return out


def splice_section_changes(lm, x, lab, role):
    """The sections (in the proposal x) that pieces of label `lab` (role group `role`) sit on where they change
    section, or [] when every piece sits on the same label or on the base: where a 'none' splice is not allowed."""
    pcs = _col_pieces(lm)
    if not pcs:
        return []
    cur = {t: (x[lm.groups_of[t]][0] if lm.groups_of.get(t) in x else v[0]) for t, v in pcs.items()}
    below = {}
    for t, v in pcs.items():
        below.setdefault(v[2], []).append(t)
    lows = set()
    for t, v in pcs.items():
        if cur[t] != lab or (role and v[3] and v[3] != role):
            continue
        if v[1] // 100000 == 0:
            continue                                   # on the base
        bl = below.get(v[1]) or []
        if not bl:
            lows.add("no column")
        for tb in bl:
            if cur[tb] != lab:
                lows.add(cur[tb])
    return sorted(lows)


ELECTRODE = {"E250": "IS 814 low-hydrogen E4918 (matching IS 2062 E250)",
             "E350": "IS 814 low-hydrogen E5518 (matching IS 2062 E350)"}
DIVISION_PLATE_T = (20.0, 25.0, 32.0, 40.0, 50.0, 56.0, 63.0, 75.0, 80.0, 90.0, 100.0)


def designed_splice(lm, x, g, lab, grade, lows):
    """A column splice at a section change (the upper label `lab` on the sections `lows`): a site CJP butt splice
    with matching electrode when the outer sizes agree (the thicker wall / flange tapered 1 in 4 to the thinner, IS 800
    10.5), else both shafts CJP-welded to a division plate (bearing), its thickness from the upper wall's line force
    q = (N/A + Mz/Zz + My/Zy) t_wall (the group's largest forces) carried over the offset between the walls."""
    register(lab)
    pu = props(lab)
    gkey = "E350" if "350" in str(grade or "") else "E250"
    elec = ELECTRODE[gkey]
    dims = []
    for lw in lows:
        if lw == "no column":
            continue
        register(lw)
        pl_ = props(lw)
        dims.append((lw, float(pl_["d"]), float(pl_["bf"]), max(float(pl_["tf"]), float(pl_["tw"]))))
    tu = max(float(pu["tf"]), float(pu["tw"]))
    same = all(abs(d - float(pu["d"])) < 1.0 and abs(b - float(pu["bf"])) < 1.0 for _, d, b, _t in dims)
    if same:
        tmax = max([t_ for *_, t_ in dims] + [tu])
        return {"type": "cjp", "weld": {"matching_electrode": True, "electrode": elec, "t_mm": tu},
                "note": "site CJP butt splice of %s on %s, matching electrode, 100 %% UT; the thicker wall (%s mm) "
                        "tapered 1 in 4 on its inner face to %s mm (equal outer faces)"
                        % (lab, " / ".join(d[0] for d in dims) or "the column below", _fmt(tmax), _fmt(tu))}
    a = max([max(d - float(pu["d"]), b - float(pu["bf"])) / 2.0 for _, d, b, _t in dims] + [0.0])
    dem = lm.group_demand(g) if g is not None else {"N": 0.0, "Mz": 0.0, "My": 0.0}
    A, Zz, Zy = plastic_props(lab)
    p_ = props(lab)
    Zz, Zy = float(p_.get("Zx") or Zz), float(p_.get("Zy") or Zy)
    q = (float(dem.get("N") or 0.0) / float(p_["A"]) + float(dem.get("Mz") or 0.0) / Zz
         + float(dem.get("My") or 0.0) / Zy) * min(float(pu["tf"]), float(pu["tw"]))
    import india_is800 as I8
    tp = DIVISION_PLATE_T[-1]
    for t_ in DIVISION_PLATE_T:
        fy = float(I8.fy_is2062("E250", t_))
        if q * a <= 0.95 * fy * t_ * t_ / 4.0 / 1.1 and q <= 0.95 * fy * t_ / (math.sqrt(3.0) * 1.1):
            tp = t_
            break
    return {"type": "cjp", "bearing": True,
            "weld": {"matching_electrode": True, "electrode": elec, "t_mm": tu},
            "transition": {"type": "division_plate", "t_mm": tp, "grade": "E250 B0", "offset_mm": round(a, 1)},
            "note": "%s on %s: both shafts CJP-welded (matching electrode, 100 %% UT) to a %s mm E250 B0 division plate, "
                    "UT-tested for laminations; ends bearing on the plate; the walls %s mm apart"
                    % (lab, " / ".join(d[0] for d in dims), _fmt(tp), _fmt(a))}


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


def _rows(failing):
    """[(name, dc)] from row names or (name, dc, ok) tuples."""
    out = []
    for f in failing:
        if isinstance(f, (list, tuple)):
            out.append((str(f[0]), float(f[1]) if isinstance(f[1], (int, float)) else 1.1))
        else:
            out.append((str(f), 1.1))
    return out


def _dc_of(rows, pattern):
    v = [dc for nm, dc in rows if re.search(pattern, nm)]
    return max(v) if v else None


def _bump_base(sp, failing, col=None):
    """Step up a column base for its failing rows (the run's 'column base' rows, with their ratios): plate t by
    sqrt(ratio) (bending), plan by sqrt(ratio) (bearing), anchor area by the ratio (a bigger diameter, then more
    anchors), embedment length by the ratio (bond), stiffeners one plate up."""
    sp = copy.deepcopy(sp)
    rows = _rows(failing)
    if sp.get("layout") == "ring" and col is not None:
        an = sp.get("anchors") or {}
        d, n, t = int(an.get("d_mm") or 36), int(an.get("n_per_row") or 3), float(sp.get("t_plate_mm") or 50.0)
        d0 = d + 3
        proj = (float(sp["L_mm"]) - float(props(col)["d"])) / 2.0
        dc = _dc_of(rows, r"plate_thickness")
        if dc:
            t = _base_t_up(t, max(1.05, math.sqrt(dc) * 1.03))
        dc = _dc_of(rows, r"bearing")
        if dc:
            proj = proj * max(1.1, math.sqrt(dc))
        dc = _dc_of(rows, r"anchor_(tension|combined|shear)|geometry_anchor")
        if dc:
            nmax = int((min(float(sp["B_mm"]), float(sp["L_mm"])) - 2.0 * math.ceil(1.7 * d0 / 5.0) * 5.0) // (2.5 * d)) + 1
            need_n = int(math.ceil(n * dc * 1.05))
            if need_n <= nmax:
                n = need_n
            else:
                up = [x for x in ANCHOR_D if x > d and x <= 64]
                d = up[0] if up else d
                if not up:
                    proj += 50.0
        emb_dc = _dc_of(rows, r"anchorage_embedment")
        out = ring_base(col, sp, d=d, n=n, t=t, proj=proj)
        if sp.get("stiffeners"):
            out["stiffeners"] = copy.deepcopy(sp["stiffeners"])        # a stiffened ring base stays stiffened
            if _dc_of(rows, r"gusset"):
                out["stiffeners"] = _step_stiffeners(out["stiffeners"], rows)
            else:
                out["stiffeners"] = _step_stiffeners(out["stiffeners"], [])      # height within the outstand limit
        dcp = _dc_of(rows, r"plate_thickness")
        if dcp and float(sp.get("t_plate_mm") or 0.0) >= BASE_T_MM[-1] - 1e-9:
            out["stiffeners"] = _base_stiffeners(out.get("stiffeners"), out, col)
            out["layout"] = "ring"
        emb = (out.get("anchors") or {}).get("embedment")
        if emb_dc and isinstance(emb, dict) and emb.get("L_mm"):
            emb["L_mm"] = float(math.ceil(float(emb["L_mm"]) * emb_dc * 1.05 / 50.0) * 50.0)
        return out
    dc = _dc_of(rows, r"plate_thickness")
    if dc:
        if float(sp.get("t_plate_mm") or 0.0) >= BASE_T_MM[-1] - 1e-9 and sp.get("fixed"):
            sp["stiffeners"] = _base_stiffeners(sp.get("stiffeners"), sp, col)    # the plate is at its largest
        sp["t_plate_mm"] = _base_t_up(float(sp.get("t_plate_mm") or 20.0), max(1.05, math.sqrt(dc) * 1.03))
        sp["fy_plate_MPa"] = plate_fy(sp["t_plate_mm"], sp.get("plate_grade") or "E250")
    dc = _dc_of(rows, r"bearing|geometry_anchor_fit")
    if dc:
        f = max(1.1, math.sqrt(dc) * 1.03)
        for k in ("B_mm", "L_mm"):
            if k in sp:
                sp[k] = float(math.ceil(float(sp[k]) * f / 50.0) * 50.0)
    an = sp.get("anchors")
    dc = _dc_of(rows, r"anchor_(tension|combined|shear)")
    if isinstance(an, dict) and dc:
        d = int(an.get("d_mm") or 24)
        need = ANCHOR_ANB.get(d, 353.0) * dc * 1.05
        up = [x for x in ANCHOR_D if x > d and x <= 56 and ANCHOR_ANB[x] >= need]
        if up:
            an["d_mm"] = up[0]
            an["Anb_mm2"] = ANCHOR_ANB[up[0]]
        else:
            npr = int(an.get("n_per_row") or 2)
            add = max(1, int(math.ceil(npr * (dc * 1.05 - 1.0))))
            an["n_per_row"] = npr + add
            an["n_tension"] = int(an.get("n_tension") or 2) + add
            an["n_total"] = int(an.get("n_total") or 4) + 2 * add
    dc = _dc_of(rows, r"anchorage_embedment")
    if isinstance(an, dict) and dc:
        emb = an.get("embedment") or sp.get("embedment")
        if isinstance(emb, dict) and emb.get("L_mm"):
            emb["L_mm"] = float(math.ceil(float(emb["L_mm"]) * dc * 1.05 / 50.0) * 50.0)
        elif isinstance(emb, dict) and emb.get("capacity_N"):
            pass                                  # an asserted capacity is not the sizer's to raise
    st = sp.get("stiffeners")
    if isinstance(st, dict) and st:
        sp["stiffeners"] = _step_stiffeners(st, rows if _dc_of(rows, r"gusset") else [])
    return sp


def _gusset_h_max(t, fy):
    """The semi-compact limit of a gusset as an outstanding welded element, h / t <= 13.6 eps (IS 800 Table 2, the
    engine's gusset_outstand_table2 row), with a small margin, to 50 mm."""
    return float(math.floor(13.0 * math.sqrt(250.0 / float(fy)) * float(t) / 50.0) * 50.0)


def _step_stiffeners(st, rows):
    """Base gussets stepped up from their failing rows: the thickness first (stresses ~ 1 / t; IS 2062 fy falls with t,
    so one more step); at the thickest plate (63 mm) the height (bending and the CJP weld to the column ~ 1 / h^2), but
    never above the outstand limit (_gusset_h_max), and past it one more gusset on each face.  The height is always
    brought within the outstand limit.  rows: [(name, dc)] or a bare ratio.  The note is re-stated."""
    st = dict(st)
    rows = [("gusset", float(rows))] if isinstance(rows, (int, float)) else _rows(rows)
    dc = max([d for n, d in rows if "gusset" in n and "outstand" not in n] + [0.0])
    t0 = float(st.get("t_mm") or 12.0)
    if dc > 1.0:
        if t0 < 63.0 - 1e-9:
            st["t_mm"] = min(_plate_up(max(t0 * dc * 1.05, t0 + 1.0), 1.0), 63.0)
        else:
            h_new = float(math.ceil(float(st.get("h_mm") or 300.0) * max(math.sqrt(dc) * 1.05, 1.1) / 50.0) * 50.0)
            hmax = _gusset_h_max(st["t_mm"], plate_fy(st["t_mm"], st.get("grade") or "E250"))
            if h_new > hmax:
                h_new = hmax
                if int(st.get("n_per_side") or 2) < 6:
                    st["n_per_side"] = int(st.get("n_per_side") or 2) + 1
                    st["n_per_side_y"] = int(st.get("n_per_side_y") or st["n_per_side"] - 1) + 1
            st["h_mm"] = h_new
    st["fy_MPa"] = plate_fy(st["t_mm"], st.get("grade") or "E250")
    hmax = _gusset_h_max(st["t_mm"], st["fy_MPa"])
    if float(st.get("h_mm") or 0.0) > hmax:
        st["h_mm"] = hmax
    if isinstance(st.get("note"), str):
        st["note"] = re.sub(r"^\d+ gussets", "%d gussets" % (2 * (int(st.get("n_per_side") or 3) +
                                                                  int(st.get("n_per_side_y") or st.get("n_per_side") or 3))),
                            st["note"])
    if isinstance(st.get("note"), str):
        st["note"] = re.sub(r"\b(\d+) gussets [0-9.]+ x [0-9.]+ \(IS 2062 E250, fy [0-9.]+\)",
                            lambda m_: "%s gussets %s x %s (IS 2062 E250, fy %s)" % (
                                m_.group(1), _fmt(st.get("h_mm")), _fmt(st["t_mm"]), _fmt(st["fy_MPa"])), st["note"])
    return st


def bump_splice(sp, failing):
    sp = copy.deepcopy(sp)
    names = " ".join(nm for nm, _ in _rows(failing))
    if isinstance(sp.get("bolts"), dict) and re.search(r"bolts_10_3", names):
        sp["bolts"]["n_bolts"] = int(sp["bolts"].get("n_bolts") or 4) + 2
    pl = sp.get("plate")
    if isinstance(pl, dict) and re.search(r"plate_yield|plate_weld", names):
        # the flange plate's area by the row ratio (a thicker plate, to 63 mm); past 63 mm inner plates are added
        # on the inside of the flange (double shear, the IN_Ex14 detail): the area grows at the same thickness
        dc = max([d for n, d in _rows(failing) if re.search(r"plate_yield|plate_weld", n)] + [1.05])
        t0 = float(pl.get("t_mm") or 12.0)
        A0 = float(pl.get("A_mm2") or 0.0)
        need = A0 * dc * 1.03 * (plate_fy(t0) / plate_fy(min(t0 * dc * 1.03, 63.0)))
        if t0 < 63.0 - 1e-9:
            t1 = min(_plate_up(max(t0 * dc * 1.03, t0 + 1.0), 1.0), 63.0)
            pl["A_mm2"] = round(A0 * t1 / t0, 1)
            pl["t_mm"] = t1
        if float(pl["A_mm2"]) < need - 1e-6:
            pl["A_mm2"] = round(need, 1)
            pl["inner_plates"] = True
            pl["note"] = "outer + inner flange plates (double shear)"
        pl["fy_MPa"] = plate_fy(pl["t_mm"], pl.get("grade") or sp.get("plate_grade") or "E250")
    w = sp.get("weld")
    if isinstance(w, dict) and re.search(r"plate_weld", names):
        dcw = max([d for n, d in _rows(failing) if "plate_weld" in n] + [1.05])
        w["length_mm"] = float(math.ceil(float(w.get("length_mm") or 300.0) * dcw * 1.05 / 10.0) * 10.0)
    wp = sp.get("web_plate")
    if isinstance(wp, dict) and re.search(r"web_plate|sumMp", names):
        t0 = float(wp.get("t_mm") or 10.0)
        t1 = _plate_up(t0, 1.0001)
        for k in ("A_mm2", "Av_mm2"):
            if wp.get(k):
                wp[k] = round(float(wp[k]) * t1 / t0, 1)
        wp["t_mm"] = t1
        wp["fy_MPa"] = plate_fy(t1, wp.get("grade") or sp.get("plate_grade") or "E250")
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


def _group_conn_demand(ev, roles, label, with_frac=False):
    """The run's beam-end shear demand of a beam group: the largest V (or V + N resultant) of its connection
    records ('conn-<role>-<label>').  with_frac: also the axial share N / R of that demand (0 for a shear)."""
    best, frac = 0.0, 0.0
    for c in ev.get("connections") or []:
        cid = str(c.get("id"))
        if not any(cid == "conn-%s-%s" % (r, label) for r in roles):
            continue
        d = c.get("demand") or {}
        for k in ("V_P_resultant_N", "V_N"):
            if isinstance(d.get(k), (int, float)) and float(d[k]) > best:
                best = float(d[k])
                frac = (float(d.get("P_end_N") or 0.0) / best) if (k == "V_P_resultant_N" and best > 0) else 0.0
    return (best, min(frac, 1.0)) if with_frac else best


def design_connections(lm, ev, x, x_run, conn_run, roles, specs, *, bumps=None, infeasible=None, cache=None):
    """CONNECTIONS for design x: every kind keyed by the new labels (bases / splices by '<role>:<label>').
    infeasible (a list): gets (group, demand, template) for every beam whose end shear connection cannot be designed
    in its section (no fin plate fits the V + N demand): the driver steps that beam group up."""
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
    shear_done = {}                     # label -> demand designed for (groups that share a label: the largest wins)
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
            V, nfr = _group_conn_demand(ev, rl, lab0, with_frac=True)
            if (V > 0 or lab != lab0) and max(1.2 * V, 30.0e3) > shear_done.get(lab, 0.0):
                Vd = max(1.2 * V, 30.0e3)
                sp = design_fin_plate(lab, Vd, tpl, n_frac=nfr)
                if sp is not None:
                    out["beam_shear"][lab] = sp
                    shear_done[lab] = Vd
                elif infeasible is not None:
                    infeasible.append((g, Vd, tpl, nfr))
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
            # the web plate for the joint shear (12.11.2.2: 1.2DL + 0.5LL + 2 x 1.2 Mp / L') of the new beam
            jsp = out["beam_column"][lab]
            if isinstance(jsp.get("shear"), dict):
                Vj = max(joint_shear_demand(lm, g, lab, grade),
                         float((bumps.get("beam_column", {}).get(g, {}) or {}).get("V_shear") or 0.0))
                if Vj > 0:
                    sh = _joint_shear_spec(lab, 1.05 * Vj)
                    if sh is not None:
                        jsp["shear"] = sh
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
            cb = (cache or {}).setdefault("column_base", {}) if cache is not None else {}
            cs = (cache or {}).setdefault("column_splice", {}) if cache is not None else {}
            tb = CD.spec_for(conn_cfg, "column_base", lab0, r)
            if tb is not None:
                # a column label that comes back gets the base designed (and stepped up) for it before
                sp = copy.deepcopy(cb[key]) if (lab != lab0 and key in cb) else adapt_base(tb, lab0, lab)
                fb = (bumps.get("column_base") or {}).get(key) or (bumps.get("column_base") or {}).get("%s:%s" % (r, lab0))
                if fb:
                    sp = bump_base(sp, fb, col=lab)
                out["column_base"][key] = sp
                if cache is not None:
                    cb[key] = copy.deepcopy(sp)
            ts = CD.spec_for(conn_cfg, "column_splice", lab0, r)
            if ts is not None:
                sp = copy.deepcopy(cs[key]) if (lab != lab0 and key in cs) else adapt_splice(ts, lab0, lab)
                # SECT review (2026-11-07): 'none' (continuous column) only where every piece of this label sits on
                # the same label or on the base; at a section change the splice is designed (CJP, or CJP to a
                # division plate between boxes of different outer size)
                if isinstance(sp, dict) and sp.get("none"):
                    lows = splice_section_changes(lm, x, lab, r)
                    if lows:
                        sp = designed_splice(lm, x, g, lab, grade, lows)
                fs = (bumps.get("column_splice") or {}).get(key) or (bumps.get("column_splice") or {}).get("%s:%s" % (r, lab0))
                if fs:
                    sp = bump_splice(sp, fs)
                out["column_splice"][key] = sp
                if cache is not None:
                    cs[key] = copy.deepcopy(sp)
    doubler_grades(lm, x, out)
    return out


def doubler_grades(lm, x, conns):
    """The IS 2062 grade of the panel-zone doubler on every beam_column spec that has one (the engine checks a doubler
    at its own grade, E250 when none is declared): E350 B0 when every column that the label's beams frame into is
    E350 (the doubler is the same plate grade as the column web it is welded to), else E250 B0.  Columns outside the
    sized groups count as E250."""
    if lm.s12 is None:
        return
    mems = {m["id"]: m for m in lm.s12[1].get("members") or []}

    def grp(m):
        return lm.groups_of.get(int(str(m["id"]).lstrip("e"))) if m else None
    at = {}
    for j in lm.s12[1].get("joints") or []:
        gr = set()
        for c in j.get("columns") or []:
            g = grp(mems.get(c.get("member_id")))
            gr.add("E350" if g is not None and g in x and "350" in str(x[g][1]) else "E250")
        for bb in j.get("beams") or []:
            g = grp(mems.get(bb.get("member_id")))
            if g is not None and g in x and gr:
                at.setdefault(x[g][0], set()).update(gr)
    for lab, sp in (conns.get("beam_column") or {}).items():
        if lab == "default" or not isinstance(sp, dict) or float(sp.get("doubler_t_mm") or 0.0) <= 0.0:
            continue
        sp["doubler_grade"] = "E350 B0" if at.get(lab.split(":", 1)[-1]) == {"E350"} else "E250 B0"


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
                    out["column_base"].setdefault(key, []).append((nm, dc, ok))
                elif nm.startswith("column splice"):
                    out["column_splice"].setdefault(key, []).append((nm, dc, ok))
    return out


def joint_shear_demand(lm, g, lab, grade):
    """IS 800:2007 12.11.2.2 / 12.10.2.4 shear of the moment joints of beam group g with section lab: the largest
    |V_gravity| + 2 x 1.2 Mp / L' over the group's beams in the Section 12 model data (fy 350 for an E350 grade,
    else 250 -- the thickness reduction of IS 2062 is left out, which is conservative here)."""
    if lm.s12 is None:
        return 0.0
    tags = set(lm.by_group.get(g) or [])
    fy = 350.0 if "350" in str(grade or "") else 250.0
    Mp = float(props(lab)["Zx"]) * fy
    V = 0.0
    for m in lm.s12[1].get("members") or []:
        t = int(m.get("tag") or str(m["id"]).lstrip("e"))
        if t in tags and m.get("L_clear_mm") and m.get("V_gravity_N") is not None:
            V = max(V, abs(float(m["V_gravity_N"])) + 2.0 * 1.2 * Mp / float(m["L_clear_mm"]))
    return V


def _joint_shear_spec(lab, V):
    """The bolted web plate of a moment joint for the joint shear V (design_fin_plate), in the joint spec's keys."""
    sh = design_fin_plate(lab, V, {}, margin=0.95)
    if sh is None:
        return None
    return {k: v for k, v in sh.items() if k in ("t_plate_mm", "h_plate_mm", "fy_plate_MPa", "fu_plate_MPa", "bolts",
                                                 "block_shear_areas", "cjp", "n_plates", "bolt_lines", "gauge_mm")}


def joint_bumps(lm, ev, x, conns):
    """Moment-joint step-ups from the failing Section 12 rows of a run: a panel zone (12.11.2.3 / IS 18168) -> a
    thicker doubler on the joint's spec (the beam group whose beam_column spec the joint uses), sized from the row's
    ratio on the column web plus doubler; a connection moment -> a thicker cover plate."""
    import india_connection_design as CD
    out = {}
    if lm.s12 is None:
        return out
    joints = {str(j.get("id")): j for j in (lm.s12[1].get("joints") or [])}
    mems = {m["id"]: m for m in lm.s12[1].get("members") or []}
    cc = {"connections": conns or {}}
    for r in ev.get("s12_fail") or []:
        rid = str(r.get("id"))
        if not re.search(r"panel_zone|connection_moment|connection_shear", rid):
            continue
        if "connection_shear" in rid:
            m = mems.get(r.get("member"))
            g_beam = lm.groups_of.get(int(str(m["id"]).lstrip("e"))) if m else None
            if g_beam is None:
                continue
            try:
                vdem = float(str(r.get("value")).split()[0])
            except (TypeError, ValueError):
                vdem = 0.0
            cur = out.setdefault(g_beam, {})
            cur["V_shear"] = max(cur.get("V_shear", 0.0), 1.05 * vdem)
            continue
        g_beam = None
        if "panel_zone" in rid:
            j = joints.get(str(r.get("member")))
            if not j:
                continue
            for bb in j.get("beams") or []:
                m = mems.get(bb.get("member_id"))
                if m and CD.spec_for(cc, "beam_column", m["section"], "beam"):
                    g_beam = lm.groups_of.get(int(str(m["id"]).lstrip("e")))
                    break
            col = next((mems.get(c.get("member_id")) for c in j.get("columns") or [] if mems.get(c.get("member_id"))), None)
            if g_beam is None or col is None:
                continue
            sp = CD.spec_for(cc, "beam_column", x[g_beam][0], "beam") or {}
            t0 = float(sp.get("doubler_t_mm") or 0.0)
            twc = float(props(col["section"])["tw"])
            dc = float(r.get("dc") or 1.1)
            need = max(t0 + 6.0, (twc + t0) * dc * 1.05 - twc)
            cur = out.setdefault(g_beam, {})
            cur["doubler_t_mm"] = max(cur.get("doubler_t_mm", 0.0), _plate_up(need, 1.0))
        else:
            m = mems.get(r.get("member"))
            if not m:
                continue
            g_beam = lm.groups_of.get(int(str(m["id"]).lstrip("e")))
            if g_beam is None:
                continue
            sp = CD.spec_for(cc, "beam_column", x[g_beam][0], "beam") or {}
            t0 = float(((sp.get("cover_plate") or {}).get("plate_t_mm")) or 10.0)
            cur = out.setdefault(g_beam, {})
            cur["cp_t"] = max(cur.get("cp_t", 0.0), _plate_up(t0, 1.0001))
    return out


def stiffness_requirements(lm, ev, x_run, specs, target=0.95, floor=0.5):
    """Minimum stiffness per group from the run's drift / sway / deflection ratios: a group of the lateral system
    keeps I (or A) >= its current value x ratio / target (the run's worst lateral ratio; a ratio below target lets the
    stiffness fall, but never below floor x the current); a beam with a deflection row keeps I >= I x ratio /
    target."""
    lat = max(list((ev.get("drift") or {}).values()) + list((ev.get("wind") or {}).values()) + [0.0])
    # at most 1.35 per pass: a drift limit that changes in steps (a soft storey's 0.2 %) is answered where it arises
    f_lat = min(max(lat / target, floor), 1.35)
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
            lateral = any(r in ("lateral_col", "brace") for r in roles.get(g, []))
        if spec.get("role") == "link":
            # EBF links are sized for their shear and the IS 18168 link rules only: a link made stiffer than its
            # demand raises the link overstrength (1.1 Ry Vp / V) that every brace and column must then carry
            # (12.3.2.2 / 12.3.4.5) -- the stiffness comes from the braces and columns
            lateral = False
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
        if st.get("sec_groups") is None:
            st["sec_groups"] = {str(i): g for i, g in sorted(probe_secondary(run_dir, {g: v[0] for g, v in x.items()}).items())}
        groups_of = {int(t): g for t, g in st["groups_of"].items()}
        mod = exec_cfg(os.path.join(run_dir, "cfg.py"))
        lm = Local(run_dir, groups_of, specs, {g: v[0] for g, v in x.items()}, st["gbs"], mod.cfg)
        lm.set_secondary({int(i): g for i, g in st["sec_groups"].items()})
        roles = roles_of_groups(lm)
        mass_est = sum(lm.group_length_mm(g) / 1000.0 * mass_kg_m(x[g][0]) for g in x)
        rec = {"it": it, "x": {g: list(v) for g, v in x.items()}, "passed": ev["passed"], "kg_m2": ev.get("kg_m2"),
               "blocking": ev.get("blocking")[:12], "drift": ev.get("drift"), "wind": ev.get("wind"),
               "headline": ev.get("headline"), "elapsed_s": el, "mass_est_kg": round(mass_est, 1)}
        log_fn("it%02d %s kg/m2 %s  (%.0f s)  blocking %d: %s" % (it, "PASS" if ev["passed"] else "FAIL", ev.get("kg_m2"),
                                                           el, len(ev.get("blocking") or []),
                                                           "; ".join((ev.get("blocking") or [])[:4])[:600]))
        st["unused"] = sorted(g for g in specs if not lm.by_group.get(g) and not lm.secondary.get(g) and
                              specs[g].get("role") not in ("gantry", "fixed") and not specs[g].get("same_as"))
        if ev["passed"] and eligible(x, specs, st["unused"]) and \
                (st["best"] is None or ev["kg_m2"] < st["best"]["kg_m2"] - 1e-9):
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
                        if (m.get("strength") or 0.0) > 1.0 + 1e-9:
                            st["margins"][g] = round(min(st["margins"].get(g, specs[g].get("margin", 0.95)), 0.95) - 0.04, 3)
                            log_fn("    margin %s -> %.2f (%s strength %s)" % (g, st["margins"][g], mid, m.get("strength")))
                        if (m.get("slender") or 0.0) > 1.0 + 1e-9:
                            # the Table 3 limit depends on the forces of the run (a beam that picks up compression
                            # in its own run, IN_Ex12 gym): the frozen forces cannot see it, so the label is barred
                            bl = st.setdefault("barred", {}).setdefault(g, [])
                            if x[g][0] not in bl:
                                bl.append(x[g][0])
                                log_fn("    barred %s for %s (%s slenderness %s in its own run)" % (x[g][0], g, mid,
                                                                                               m.get("slender")))
        # ---- local sizing under the frozen forces
        req, info = stiffness_requirements(lm, ev, x, specs)
        for g, f in (st.get("stiff_boost") or {}).items():
            if g in req:
                req[g] *= float(f)
        for g, v in torsion_requirements(lm, ev, x, st).items():
            req[g] = max(req.get(g, 0.0), v)
        lat_fail = [k for k, v in list((ev.get("drift") or {}).items()) + list((ev.get("wind") or {}).items()) if v > 1.0]
        if lat_fail and ev["passed"] is False:
            for g in req:
                st.setdefault("stiff_boost", {})[g] = round(float(st["stiff_boost"].get(g, 1.0)) * 1.05, 3)
        # EBF: the links are sized in the first two passes and then held (only their own Section 12 link rows step
        # them up): every brace and column force follows the link overstrength 1.1 Ry Vp / V, so links that keep
        # moving keep the braces and columns from converging (IN_Ex15 / IN_Ex19)
        links = [g for g, sp in specs.items() if sp.get("role") == "link"]
        failing_labels = {m.get("section") for m in (ev.get("members") or {}).values()
                          if (m.get("strength") or 0.0) > 1.0 + 1e-9 or (m.get("slender") or 0.0) > 1.0 + 1e-9}
        # a held link group whose own members fail in the run (the beam outside the link), or whose end connection
        # the last pass found too small (conn_req), is sized again
        hold = list(fixed) + ([g for g in links if x[g][0] not in failing_labels and
                               g not in (st.get("conn_req") or {})] if links and it >= 2 else [])
        _t0 = time.time()
        x1, notes = size_groups(lm, x, st["margins"], req, log_fn=log_fn, fixed=hold, barred=st.get("barred"),
                                conn_req=st.get("conn_req"))
        _t1 = time.time()
        # Section 12 rows the full run failed although the frozen forces passed them: that group's rows get a margin
        mem_tag_ = {m["id"]: int(m.get("tag") or str(m["id"]).lstrip("e")) for m in (lm.s12[1].get("members") or [])} \
            if lm.s12 is not None else {}
        for r_ in ev.get("s12_fail") or []:
            g_ = lm.groups_of.get(mem_tag_.get(r_.get("member")))
            if g_ is not None and isinstance(r_.get("dc"), (int, float)) and r_["dc"] > 1.0 and \
                    not S12_CONNECTION_ROWS.search(str(r_.get("id"))):
                mk = "%s::%s" % (g_, re.sub(r"@.*$", "", str(r_.get("id"))))      # per group and row kind
                m0 = st.setdefault("s12_margin", {}).get(mk, 1.0)
                st["s12_margin"][mk] = round(max(0.8, min(m0, 1.0) - 0.04), 3)
        for k in range(12):
            rows = s12_local(lm, x1, margins=st.get("s12_margin"))
            bumped = set()
            for row, g in rows:
                if "7_2_column_KL_r" in str(row.get("id")) and int(st.get("kl_fail") or 0) < 3:
                    continue          # answered through the beams first (torsion_requirements), see above
                gs = [g] if g else []
                if re.search(r"SCWB|column_strength|8_2", str(row.get("id"))) or g is None:
                    gs += scwb_columns(lm, row)
                for gg in gs:
                    if gg in bumped or gg not in specs or specs[gg].get("role") == "fixed":
                        continue
                    # an axial capacity-design row (brace / column axial at the link or system overstrength, brace
                    # tension) asks for A fy x its ratio in one step, not one catalogue entry at a time
                    ma = None
                    if gg == g and re.search(r"axial|tension", str(row.get("id"))) and isinstance(row.get("dc"), (int, float)):
                        ma = stiffness(x1[gg][0], "A") * max(float(row["dc"]), 1.0) * 1.02
                    nu = next_up(specs[gg], x1[gg], lm, gg, st["margins"].get(gg, specs[gg].get("margin", 0.95)),
                                 min_area=ma)
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
        _t2 = time.time()
        x1 = monotone_columns(x1, specs, log_fn=log_fn, lm=lm, margins=st["margins"], barred=st.get("barred"))
        _t3 = time.time()
        gbs1 = grade_map(x1, roles, mod.cfg.get("steel_grade"), base={k: v for k, v in (st["gbs"] or {}).items()
                                                                       if ":" not in k and k not in _labels_in_use(x)})
        bumps = connection_bumps(ev, x, roles)
        bumps["beam_column"].update(joint_bumps(lm, ev, x, st["conns"]))
        for g_, b_ in bumps["beam_column"].items():
            log_fn("    joint step-up %s: %s" % (g_, b_))
        infeas = []
        conns1 = design_connections(lm, ev, x1, x, st["conns"], roles, specs, bumps=bumps, infeasible=infeas,
                                    cache=st.setdefault("conn_cache", {})) if st["conns"] is not None else None
        if infeas:
            # a beam whose end shear connection (V + N) does not fit its section: the next section up in the group's
            # order that passes the frozen member checks and takes a fin plate for that demand
            for g, Vd, tpl, nfr in infeas:
                # an EBF link too is stepped up for its end connection (the smallest that takes it): without it the
                # design cannot pass; its stiffness is not asked for (stiffness_requirements), which kept the link
                # overstrength low enough in the IN_Ex15 / IN_Ex19 first passes
                prev = (st.setdefault("conn_req", {}).get(g) or [0.0, None])[0]
                st["conn_req"][g] = [max(float(Vd), float(prev)), tpl, nfr]  # kept: size_groups honours it from now on
                cur = x1[g]
                for _ in range(80):
                    nu = next_up(specs[g], cur, lm, g, st["margins"].get(g, specs[g].get("margin", 0.95)))
                    if not nu:
                        break
                    if design_fin_plate(nu[0], Vd, tpl, n_frac=nfr) is not None:
                        log_fn("    %s: no fin plate fits %s for %.0f kN -> %s" % (g, x1[g][0], Vd / 1e3, nu[0]))
                        x1[g] = nu
                        break
                    cur = nu
            gbs1 = grade_map(x1, roles, mod.cfg.get("steel_grade"), base={k: v for k, v in (st["gbs"] or {}).items()
                                                                           if ":" not in k and k not in _labels_in_use(x)})
            conns1 = design_connections(lm, ev, x1, x, st["conns"], roles, specs, bumps=bumps,
                                        cache=st.setdefault("conn_cache", {}))
        log_fn("    local step: sizing %.0f s, Section 12 loop %.0f s, stacks %.0f s, connections %.0f s"
               % (_t1 - _t0, _t2 - _t1, _t3 - _t2, time.time() - _t3))
        rec["proposal"] = {g: list(v) for g, v in x1.items()}
        rec["notes"] = notes
        rec["stiffness"] = info
        st["history"].append(rec)
        changed = _x_key(x1) != _x_key(x) or json.dumps(conns1, sort_keys=True, default=str) != \
            json.dumps(st["conns"], sort_keys=True, default=str)
        seen = st.setdefault("seen", [])
        cycle = _x_key(x1) in seen and _x_key(x1) != _x_key(x)
        seen.append(_x_key(x))
        for g in sorted(x1):
            if tuple(x1[g]) != tuple(x[g]):
                log_fn("    %-18s %-22s -> %-22s %s" % (g, "%s %s" % (x[g][0], x[g][1] or ""),
                                                     "%s %s" % (x1[g][0], x1[g][1] or ""), notes.get(g, "")))
        st["x"] = {g: list(v) for g, v in x1.items()}
        st["gbs"] = gbs1
        st["conns"] = conns1
        st["it"] = it + 1
        # it00 is kept too: the starting design's run is the baseline that each later move is compared with
        _cleanup(work, keep={"it00", "it%02d" % it, "it%02d" % (it - 1), "it%02d" % (st["best"] or {}).get("it", -1)})
        save_state(work, st)
        if cycle and st.get("best"):
            log_fn("the proposal repeats an earlier design (a cycle of the frozen-force sizing): stop at it%02d, best "
                   "it%02d" % (it, st["best"]["it"]))
            st["converged"] = "cycle"
            save_state(work, st)
            break
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
    unused = st.get("unused") or []
    if unused:                 # groups no member of the model takes: say so in SIZING_GROUPS (their label is kept)
        sg = read_literals(src, ("SIZING_GROUPS",)).get("SIZING_GROUPS") or {}
        for g in unused:
            if g in sg:
                sg[g] = dict(sg[g], unused=True)
                note = str(sg[g].get("note") or g)
                if "not used by this model" not in note:
                    sg[g]["note"] = note + " (not used by this model: no member takes this group)"
        vals["SIZING_GROUPS"] = sg
    if "GRADE_BY_SECTION" in lit:
        vals["GRADE_BY_SECTION"] = b["gbs"]
    if "CONNECTIONS" in lit and b.get("conns") is not None:
        conns = copy.deepcopy(b["conns"])
        for sp in (conns.get("beam_column") or {}).values():
            # a panel-zone doubler states its grade: the one the verified run checked it at (none declared -> E250)
            if isinstance(sp, dict) and float(sp.get("doubler_t_mm") or 0.0) > 0.0 and not sp.get("doubler_grade"):
                sp["doubler_grade"] = "E250 B0"
        vals["CONNECTIONS"] = conns
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
