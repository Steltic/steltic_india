"""peb_autosize.py -- PEB-LEVERS (2026-10): a deterministic auto-sizer for a PEB job, used by the lever study.

Given a PEB job folder (cfg.py written the way the PEB golds are: module-level section-label constants such as
COL_T = "TI300-1000X250X14X6", the declared connections in cfg['connections'], the CFS secondary design in
secondary/secondary_is801.py) and a set of cfg['peb_rules'] switches, find the lightest member plates, purlins / girts
and connection plates for which the whole pipeline passes: every member and station check, every joint, the Section 12
checks, the analysis gates (sway, drift, beam deflection), lambda_cr >= 5 and the design_status authority.

How it works (all steps deterministic; no random numbers, sorted iteration, PYTHONHASHSEED 0 in every child run):

 1. secondary   -- purlins and girts: the job's own secondary script (the CFS engine, IS 801) is re-run with candidate
                   sections in a child process; the lightest section of the switch's family ('IS811_Fy240': IS 811
                   lipped zeds at Fy 240 MPa; 'thin_G350': generic thin lipped zeds at Fy 350 MPa) that passes every
                   IS 801 check is kept, for the purlins and the girts separately.  Spacing is not changed (the frame
                   restraints and fly braces depend on it).
 2. full run    -- the job's cfg.py is executed with its section constants replaced (an AST rewrite of the top-level
                   assignments, so every quantity cfg.py derives from them follows), the connection plates patched, the
                   switches set; the HR pipeline runs without the report (pipeline.design_and_report(do_report=False))
                   in a child process, then india_seismic_gates.design_status is evaluated on the package.
 3. local sizing -- with the forces of the last full run frozen, each member group is resized by coordinate descent
                   over its plates (depth at each end, flange width and thickness, web thickness, from standard plate
                   sizes, within the fabrication limits) re-running the exact IS 800 member and station checks of
                   every element (design_pipeline.member_checks_is800 / peb_station_checks with the element inputs the
                   run dumped); the frame sway and lambda_cr are predicted from a virtual-work flexibility index of a
                   typical frame; the knee, apex and splice end plates, the column flange plate at the knee, the knee
                   stiffeners and the base shear keys are sized for the demand of the switch (1.2 Mp or the
                   deliverable moment; 1.2 Vd or the analysis base shear) with the same capacity functions the engine
                   uses (peb_checks / india_connections).  The objective is the steel mass (members + connections).
 4. verify      -- a full run of the proposal; a failure tightens the local margin of the group it belongs to and the
                   loop repeats from the last passing design.  Stops when a passing proposal no longer changes, or at
                   the iteration cap.

Mass: the take-off of the engine (peb_checks.tonnage).  The connection group of a resized job is the gold's declared
plate take-off corrected by the change of the itemised connection plates (end plates, knee flange plates, rib
stiffeners, knee stiffeners, base shear keys) computed here on one basis for the gold and the variant
(connection_items), so the plates the gold itemises by hand (gussets, cleats) keep their gold mass.

Limitations (stated in every study): base plates, anchors and base gussets keep the gold sizes (only shear keys are
resized); member depths keep the gold's taper layout (taper length, splice positions); the purlin / girt spacing and
the fly-brace layout are not changed; the brace section is resized only where the job spec names it.

CLI (the worker entry points, used by the driver):
    python peb_autosize.py frame <run_dir>        # one full pipeline run of <run_dir>/variant.json
    python peb_autosize.py secondary <run_dir>    # the secondary design candidates of <run_dir>/secondary_job.json
"""
from __future__ import annotations

import ast
import contextlib
import copy
import io
import json
import math
import os
import re
import shutil
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ENGINE_ROOT = os.path.dirname(HERE)
STEEL = 7.85e-6                     # kg/mm3
PY = sys.executable

# commercial plate thicknesses (assumption: IS 1730 is not in the corpus; the golds' own thicknesses are added)
PLATES_MM = (4.0, 5.0, 6.0, 8.0, 10.0, 12.0, 14.0, 16.0, 18.0, 20.0, 22.0, 25.0, 28.0, 32.0, 36.0, 40.0, 45.0, 50.0,
             56.0, 63.0)
FLANGE_W_MM = tuple(sorted(set(list(range(120, 401, 10)) + list(range(125, 401, 25)))))
DEPTH_STEP_MM = 25.0
BOLT_D_MM = (20, 24, 30, 36)
KEY_B_MM = (150.0, 200.0, 250.0, 300.0, 400.0, 500.0, 600.0, 800.0)
KEY_H_MM = (150.0, 200.0, 250.0, 300.0, 340.0, 400.0, 450.0)
LOG = []
# design_status reasons that need the report (not built in a sizing run): never a reason to reject a design
REPORT_ONLY_WAIVERS = (r"grounding record not available \(report not built\)",)


def log(*a):
    s = " ".join(str(x) for x in a)
    LOG.append(s)
    print(s, flush=True)


# =================================================================================================== labels
def _fmt(v):
    v = float(v)
    return ("%d" % round(v)) if abs(v - round(v)) < 1e-6 else ("%g" % v)


def label(kind, dims):
    """dims: tapered (D0, D1, bf, tf, tw); welded (D, bf, tf, tw)."""
    if kind == "tapered":
        D0, D1, bf, tf, tw = dims
        return "TI%s-%sX%sX%sX%s" % tuple(_fmt(v) for v in (D0, D1, bf, tf, tw))
    D, bf, tf, tw = dims
    return "WI%sX%sX%sX%s" % tuple(_fmt(v) for v in (D, bf, tf, tw))


def parse(lab):
    import peb_build as PB
    p = PB.parse(lab)
    if p[0] == "tapered":
        return "tapered", list(p[1:])
    if p[0] == "welded":
        return "welded", list(p[1:])
    return "rolled", [lab]


DIMS = {"tapered": ("D0", "D1", "bf", "tf", "tw"), "welded": ("D", "bf", "tf", "tw")}


def dim(lab, name):
    k, d = parse(lab)
    return d[DIMS[k].index(name)]


def with_dim(lab, name, v):
    k, d = parse(lab)
    d = list(d)
    d[DIMS[k].index(name)] = float(v)
    return label(k, d)


def mass_kg_m(lab):
    """Mass per metre of a welded / tapered label (tapered: the mean web)."""
    k, d = parse(lab)
    if k == "tapered":
        D0, D1, bf, tf, tw = d
        return (2 * bf * tf + 0.5 * ((D0 - 2 * tf) + (D1 - 2 * tf)) * tw) * STEEL * 1000.0
    if k == "welded":
        D, bf, tf, tw = d
        return (2 * bf * tf + (D - 2 * tf) * tw) * STEEL * 1000.0
    import sections as S
    p = S.props(lab)
    return float(p.get("Mass_kg_m") or p["A"] * 7850e-6)


# =================================================================================================== cfg.py rewrite
def _literal(v):
    return ast.parse(repr(v), mode="eval").body


def override_source(src, overrides, path="cfg.py"):
    """Replace the values of top-level assignments NAME = ... (and NAME in a tuple assignment A, B = x, y) by the
    literals of `overrides`.  Every override must be found (KeyError otherwise)."""
    tree = ast.parse(src, filename=path)
    done = set()
    for node in tree.body:
        if not isinstance(node, ast.Assign) or len(node.targets) != 1:
            continue
        tg = node.targets[0]
        if isinstance(tg, ast.Name) and tg.id in overrides:
            node.value = _literal(overrides[tg.id])
            done.add(tg.id)
        elif isinstance(tg, ast.Tuple) and isinstance(node.value, ast.Tuple) and len(tg.elts) == len(node.value.elts):
            for k, el in enumerate(tg.elts):
                if isinstance(el, ast.Name) and el.id in overrides:
                    node.value.elts[k] = _literal(overrides[el.id])
                    done.add(el.id)
    miss = sorted(set(overrides) - done)
    if miss:
        raise KeyError("%s: no top-level assignment for %s" % (path, miss))
    ast.fix_missing_locations(tree)
    return tree


def exec_with_overrides(path, overrides, name="cfg_mod", inject=None):
    """Execute a job script with constant overrides; returns the module namespace (dict)."""
    import types
    src = open(path, encoding="utf-8").read()
    tree = override_source(src, overrides or {}, path)
    mod = types.ModuleType(name)
    mod.__file__ = os.path.abspath(path)
    mod.__dict__.update(inject or {})
    exec(compile(tree, os.path.abspath(path), "exec"), mod.__dict__)
    return mod


# =================================================================================================== run folders
_SKIP_FILES = {"report.html", "viewer_3d.html", "model_opensees.py", "model_static.py", "model.std", "run_stdout.txt",
               "run_summary.json", "STATUS.md", "STATUS.engine.md", "activity_log.jsonl", "load_plan.json",
               "cfg.pass1.py"}
_SKIP_DIRS = {"design", "figs", "units"}


def prepare_run_dir(job_dir, run_dir):
    """A clean copy of the job's inputs: scripts and data files copied, rag/ linked, secondary/ copied."""
    os.makedirs(run_dir, exist_ok=True)
    for f in sorted(os.listdir(job_dir)):
        src, dst = os.path.join(job_dir, f), os.path.join(run_dir, f)
        if os.path.isdir(src):
            if f in _SKIP_DIRS:
                continue
            if f == "rag":
                if not os.path.lexists(dst):
                    os.symlink(os.path.abspath(src), dst)
                continue
            if f == "secondary":
                shutil.copytree(src, dst, dirs_exist_ok=True)
            continue
        if f in _SKIP_FILES:
            continue
        shutil.copy2(src, dst)
    for f in ("load_plan.json",):
        p = os.path.join(run_dir, f)
        if os.path.exists(p):
            os.remove(p)
    return run_dir


def _child_env(extra=None):
    env = dict(os.environ)
    env["PYTHONHASHSEED"] = "0"
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    env["MPLBACKEND"] = "Agg"
    env.update(extra or {})
    return env


def run_child(args, cwd, timeout, env=None, log_path=None):
    t0 = time.time()
    with open(log_path or os.devnull, "w") as fo:
        r = subprocess.run(args, cwd=cwd, env=_child_env(env), stdout=fo, stderr=subprocess.STDOUT, timeout=timeout)
    return r.returncode, round(time.time() - t0, 1)


# =================================================================================================== connections
def plate_fy(t, grade):
    """IS 2062 Table 3 yield stress by thickness, as the golds' helpers use it (E250: 250 / 240 / 230; E350: 350 /
    330 / 320 for t <= 20 / <= 40 / > 40 mm)."""
    if str(grade).upper().startswith("E350"):
        return 350.0 if t <= 20 else 330.0 if t <= 40 else 320.0
    return 250.0 if t <= 20 else 240.0 if t <= 40 else 230.0


def ep_dict(sec, *, t, d_bolt, n_out, n_in, pitch, b_plate, grade="10.9", plate_grade="E250", ext=60.0, weld=8.0,
            gauge=None, web_doubler=0.0, member_fy=350.0):
    """The extended end plate of the PEB golds (their bolted_end_plate helper, identical arithmetic): n_out rows
    beyond the tension flange, n_in rows inside it (only rows in the tension half), be = min(pitch, b/2), lv to the
    weld toe, le = min(50, (b - g)/2), plate fy by thickness."""
    import sections as S
    p = S.props(sec)
    hf = p["d"] - p["tf"]
    g = gauge or (120.0 if d_bolt >= 30 else 110.0)
    lv = max(ext - p["tf"] / 2.0 - weld, g / 2.0 - p["tw"] / 2.0 - weld)
    rows = ([{"h_mm": round(hf + ext + k * pitch, 1), "n_pairs": 1} for k in range(n_out)] +
            [{"h_mm": round(hf - ext - k * pitch, 1), "n_pairs": 1} for k in range(n_in)
             if hf - ext - k * pitch >= hf / 2.0 - 1.0])
    return {"rows": rows, "d_mm": d_bolt, "grade": grade, "t_plate_mm": t, "fy_plate_MPa": plate_fy(t, plate_grade),
            "plate_grade": plate_grade, "be_mm": round(min(pitch, b_plate / 2.0), 1), "lv_mm": round(lv, 1),
            "le_mm": min(50.0, (b_plate - g) / 2.0), "pretensioned": True, "bolt_type": "HSFG",
            "web_t_mm": float(p["tw"]) + float(web_doubler), "web_fy_MPa": member_fy, "hf_mm": hf}


def ep_height(sec, n_out, pitch, ext=60.0, edge=60.0):
    import sections as S
    p = S.props(sec)
    return p["d"] + 2.0 * (ext + (n_out - 1) * pitch + edge - p["tf"] / 2.0)


def shear_key(b, t, h, fy, fck, grout=50.0):
    """The cruciform shear key of the PEB golds (their shear_key_record helper, identical arithmetic)."""
    gm0 = 1.1
    bear = 0.45 * fck * b * (h - 25.0)
    shear = b * t * fy / (math.sqrt(3.0) * gm0)
    lever = grout + 25.0 + (h - 25.0) / 2.0
    bend = (t * b ** 2 / 4.0) * fy / gm0 / lever
    cap = min(bear, shear, bend)
    return {"capacity_N": round(cap, 0), "size": "cruciform 2 x %g x %g, %g deep" % (b, t, h),
            "mass_kg": round(2 * b * t * (h + grout) * STEEL, 1),
            "source": ("PEB-LEVERS auto-sized shear key: cruciform key of two IS 2062 E250 plates %g x %g mm (fy %g "
                       "MPa), %g mm into a grouted pocket under %g mm grout, fck %g MPa: min(bearing 0.45 fck b (h - 25) "
                       "= %.0f kN, plate shear b t fy/(sqrt3 gamma_m0) = %.0f kN, plate bending (t b^2/4) fy/gamma_m0 / "
                       "lever %.0f mm = %.0f kN) = %.0f kN" % (b, t, fy, h, grout, fck, bear / 1e3, shear / 1e3, lever,
                                                               bend / 1e3, cap / 1e3)),
            "cite": "IS 800:2007 7.4.1 (base shear transfer), 8.4.1, 8.2.1.2, 10.5.7.1.2 (CJP); IS 456:2000 34.4 bearing "
                    "0.45 fck (EOR assumption, outside the corpus); the key takes all base shear beyond friction",
            "_dims": [b, t, h]}


def _rows_split(ep):
    hf = float(ep.get("hf_mm") or 0.0)
    out = sorted(float(r["h_mm"]) for r in ep.get("rows") or [] if float(r["h_mm"]) > hf)
    inn = sorted((float(r["h_mm"]) for r in ep.get("rows") or [] if float(r["h_mm"]) < hf), reverse=True)
    return out, inn, hf


def ep_params(spec, sec):
    """Read the design parameters of a declared end-plate joint spec (the inverse of ep_dict)."""
    import sections as S
    ep = spec.get("end_plate") or {}
    p = S.props(sec)
    out, inn, hf = _rows_split(dict(ep, hf_mm=ep.get("hf_mm") or (p["d"] - p["tf"])))
    pitch = None
    if len(out) >= 2:
        pitch = out[1] - out[0]
    elif len(inn) >= 2:
        pitch = inn[0] - inn[1]
    pitch = pitch or 100.0
    rule = ("abs", round(pitch, 1))
    for k in range(2, 10):
        if abs((hf - 120.0) / k - pitch) < 0.6:
            rule = ("ratio", k)
            break
    g = spec.get("gauge_mm")
    b_plate = float(spec.get("plate_b_mm") or (p["bf"] + 50.0))
    return {"t": float(ep.get("t_plate_mm")), "d": int(ep.get("d_mm")), "grade": ep.get("grade", "10.9"),
            "plate_grade": ep.get("plate_grade") or "E250", "n_out": len(out), "n_in": len(inn), "pitch_rule": rule,
            "b_plate": b_plate, "web_doubler": round(float(ep.get("web_t_mm") or p["tw"]) - float(p["tw"]), 3),
            "member_fy": float(ep.get("web_fy_MPa") or 350.0), "gauge": float(g) if g else None}


def pitch_of(par, sec):
    import sections as S
    if par["pitch_rule"][0] == "ratio":
        p = S.props(sec)
        return (p["d"] - p["tf"] - 120.0) / par["pitch_rule"][1]
    return float(par["pitch_rule"][1])


def make_ep(par, sec):
    gauge = par.get("gauge") if (par.get("gauge") and par["d"] < 30) or par.get("gauge_fixed") else None
    return ep_dict(sec, t=par["t"], d_bolt=par["d"], n_out=par["n_out"], n_in=par["n_in"], pitch=pitch_of(par, sec),
                   b_plate=par["b_plate"], grade=par["grade"], plate_grade=par["plate_grade"],
                   web_doubler=par["web_doubler"], member_fy=par["member_fy"],
                   gauge=par.get("gauge") if par.get("gauge_fixed") else None)


def _bom_item(items, name):
    for x in items or []:
        if str(x.get("item") or "") == name:
            return x
    return None


def _parse_txhxl(size):
    m = re.match(r"\s*([\d.]+)\s*x\s*([\d.]+)\s*x\s*([\d.]+)", str(size or ""))
    return [float(v) for v in m.groups()] if m else None


def regen_bom_plates(items, *, ep_h, sec_face, col_face=None, t_cf=None):
    """The gold's itemised extra plates of a joint, regenerated for the new joint height / plates: rib stiffeners
    (height from the new extension), the knee-zone column flange plate (the new thickness and height); other items
    (web plates, gussets) are kept as cfg.py computed them."""
    import sections as S
    out = []
    pf = S.props(sec_face)
    for x in items or []:
        it = str(x.get("item") or "")
        if it == "extension rib stiffeners":
            t_, _h, _L = _parse_txhxl(x.get("size")) or (10.0, 0.0, 0.0)
            ext = ep_h / 2.0 - pf["d"] / 2.0
            L = 1.7 * ext
            out.append(dict(x, size="%.0f x %.0f x %.0f (t x h x L)" % (t_, ext, L),
                            kg_each=round(0.5 * ext * L * t_ * STEEL, 1)))
        elif it == "knee-zone column flange plates" and col_face:
            pc = S.props(col_face)
            if t_cf is None or t_cf <= pc["tf"] + 1e-9:
                continue                                  # no plate: the column's own flange
            h = ep_h + 100.0
            out.append(dict(x, part="column flange plate, replaces the %.0f mm flange (mass: the extra steel)" % pc["tf"],
                            size="%.0f x %.0f x %.0f" % (pc["bf"], t_cf, h),
                            kg_each=round(pc["bf"] * (t_cf - pc["tf"]) * h * STEEL, 1)))
        else:
            out.append(dict(x))
    return out


def _bom_kg(items):
    return sum(float(x.get("kg_each") or 0.0) * int(x.get("qty_per_joint") or 1) for x in items or [])


# ------------------------------------------------------------------------------- the connection design of a run
def _knee_key(conn):
    for key, spec in (conn.get("beam_column") or {}).items():
        if key != "default" and ((spec or {}).get("end_plate") or {}).get("rows"):
            return key
    return None


def base_slots(conn):
    """[(slot, key)] of the column_base specs in declaration order ('base#0', ...): cfg.py builds them in a fixed
    order, so the slot of a base keeps its name when its section key changes with the members."""
    return [("base#%d" % i, k) for i, k in enumerate((conn.get("column_base") or {}).keys())]


def read_conn_design(cfg, knee_col_face):
    """The connection design variables of a cfg (gold or patched): {slot: params}.  Slots: 'knee' (the beam_column
    spec with an end plate), 'knee_panel', 'splice:<key>' for the rafter_splice specs with an end plate (filled by
    read_conn_design_full, which knows the faces), 'base#<i>' for the column_base specs with a shear key."""
    import sections as S
    conn = cfg.get("connections") or {}
    out = {}
    kk = _knee_key(conn)
    if kk:
        spec = conn["beam_column"][kk]
        par = ep_params(spec, kk)
        par["t_cf"] = float(spec.get("column_flange_t_mm") or S.props(knee_col_face)["tf"]) if knee_col_face else None
        out["knee"] = par
    kp = conn.get("knee_panel") or {}
    if kp:
        out["knee_panel"] = {"diag_t": float((kp.get("diagonal_stiffener") or {}).get("t_mm") or 0.0),
                             "flange_t": float((kp.get("flange_stiffener") or {}).get("t_mm") or 0.0)}
    for key, spec in (conn.get("rafter_splice") or {}).items():
        if not isinstance(spec, dict) or not (spec.get("end_plate") or {}).get("rows"):
            continue
        out["splice:" + key] = None                        # filled per joint section by the caller (needs the face)
    for slot, key in base_slots(conn):
        spec = conn["column_base"][key]
        if isinstance(spec, dict) and spec.get("shear_key"):
            sk = spec["shear_key"]
            dims = sk.get("_dims") or _key_dims_from_size(sk.get("size"))
            out[slot] = {"key": dims, "fck": float(spec.get("fck_MPa") or 30.0),
                         "b_max": min(float(spec.get("B_mm") or 1e9), float(spec.get("L_mm") or 1e9))}
    return out


def _key_dims_from_size(size):
    m = re.match(r"cruciform 2 x ([\d.]+) x ([\d.]+), ([\d.]+) deep", str(size or ""))
    return [float(v) for v in m.groups()] if m else None


def patch_connections(cfg, design, sections):
    """Apply a connection design {slot: params} to cfg['connections'] in place.  sections = {'knee_col_face':
    <column section at the knee>, 'splice_face': {key: section}} (the joint faces of THIS cfg)."""
    import sections as S
    conn = cfg.get("connections") or {}
    for slot, par in (design or {}).items():
        if par is None:
            continue
        if slot == "knee":
            face = _knee_key(conn)
            if not face:
                raise KeyError("patch_connections: no beam_column spec with an end plate (the knee)")
            spec = conn["beam_column"][face]
            t_old = float(spec["end_plate"]["t_plate_mm"])
            ep = make_ep(par, face)
            spec["end_plate"] = ep
            h = ep_height(face, par["n_out"], pitch_of(par, face))
            if par.get("t_cf") is not None:
                spec["column_flange_t_mm"] = par["t_cf"]
            sh = spec.get("shear")
            if isinstance(sh, dict):
                r = par["t"] / t_old
                sh["t_plate_mm"] = par["t"]
                sh["h_plate_mm"] = h
                sh["fy_plate_MPa"] = plate_fy(par["t"], sh.get("plate_grade") or par["plate_grade"])
                if isinstance(sh.get("block_shear_areas"), dict):
                    sh["block_shear_areas"] = {k: v * r for k, v in sh["block_shear_areas"].items()}
            spec["bom_plates"] = regen_bom_plates(spec.get("bom_plates"), ep_h=h, sec_face=face,
                                                  col_face=sections.get("knee_col_face"), t_cf=par.get("t_cf"))
            spec["peb_levers_design"] = dict(par, height_mm=round(h, 1))
        elif slot == "knee_panel":
            kp = conn.setdefault("knee_panel", {})
            if par.get("diag_t") and kp.get("diagonal_stiffener"):
                kp["diagonal_stiffener"]["t_mm"] = par["diag_t"]
                kp["diagonal_stiffener"]["fy_MPa"] = plate_fy(par["diag_t"], "E250")
            if par.get("flange_t") and kp.get("flange_stiffener"):
                kp["flange_stiffener"]["t_mm"] = par["flange_t"]
                kp["flange_stiffener"]["fy_MPa"] = plate_fy(par["flange_t"], "E250")
        elif slot.startswith("splice:"):
            key = slot.split(":", 1)[1]
            spec = (conn.get("rafter_splice") or {}).get(key)
            face = (sections.get("splice_face") or {}).get(key)
            if not spec or not face:
                continue
            ep = make_ep(par, face)
            spec["end_plate"] = ep
            h = ep_height(face, par["n_out"], pitch_of(par, face))
            spec["bom_plates"] = regen_bom_plates(spec.get("bom_plates"), ep_h=h, sec_face=face)
            spec["peb_levers_design"] = dict(par, height_mm=round(h, 1))
        elif slot.startswith("base#"):
            key = dict(base_slots(conn)).get(slot)
            spec = (conn.get("column_base") or {}).get(key) if key else None
            if not spec:
                continue
            if par.get("key"):
                b, t, h = par["key"]
                spec["shear_key"] = shear_key(b, t, h, plate_fy(t, "E250"), par.get("fck", 30.0))
            else:
                spec.pop("shear_key", None)
    return cfg


# ------------------------------------------------------------------------------- itemised connection mass
def connection_items(cfg, counts, faces):
    """{item: kg} of the connection plates this module resizes, for the take-off correction (one basis for the gold
    and every variant).  counts = {'knee': n, 'splice:<key>': n, 'base#<i>': n}; faces = {'knee_col_face',
    'splice_face': {key: sec}}."""
    import sections as S
    conn = cfg.get("connections") or {}
    out = {}
    for key, spec in (conn.get("beam_column") or {}).items():
        ep = (spec or {}).get("end_plate") or {}
        if key == "default" or not ep.get("rows"):
            continue
        n = counts.get("knee", 0)
        par = ep_params(spec, key)
        h = ep_height(key, par["n_out"], pitch_of(par, key))
        b = float(spec.get("plate_b_mm") or (S.props(key)["bf"] + 50.0))
        out["knee end plates"] = n * b * float(ep["t_plate_mm"]) * h * STEEL
        out["knee extra plates"] = n * sum(float(x.get("kg_each") or 0) * int(x.get("qty_per_joint") or 1)
                                           for x in spec.get("bom_plates") or []
                                           if x.get("item") in ("extension rib stiffeners",
                                                                "knee-zone column flange plates"))
        kp = conn.get("knee_panel") or {}
        cf = faces.get("knee_col_face")
        if cf and kp:
            pc, pb = S.props(cf), S.props(key)
            fs, ds = kp.get("flange_stiffener") or {}, kp.get("diagonal_stiffener") or {}
            Lst = pc["d"] - 2 * pc["tf"]
            out["knee stiffeners"] = n * (2 * float(fs.get("n", 2)) * float(fs.get("b_mm", 0)) * float(fs.get("t_mm", 0))
                                          * Lst + float(ds.get("n", 2)) * float(ds.get("b_mm", 0)) *
                                          float(ds.get("t_mm", 0)) * math.hypot(pc["d"], pb["d"])) * STEEL
    for key, spec in (conn.get("rafter_splice") or {}).items():
        ep = (spec or {}).get("end_plate") or {}
        face = (faces.get("splice_face") or {}).get(key)
        if not ep.get("rows") or not face:
            continue
        n = counts.get("splice:" + key, 0)
        par = ep_params(spec, face)
        h = ep_height(face, par["n_out"], pitch_of(par, face))
        npl = 1 if key == "canopy_root" else 2
        b = float(spec.get("plate_b_mm") or (S.props(face)["bf"] + 50.0))
        out["%s end plates" % key] = n * npl * b * float(ep["t_plate_mm"]) * h * STEEL
        out["%s extra plates" % key] = n * sum(float(x.get("kg_each") or 0) * int(x.get("qty_per_joint") or 1)
                                               for x in spec.get("bom_plates") or []
                                               if x.get("item") == "extension rib stiffeners")
    for slot, key in base_slots(conn):
        spec = conn["column_base"][key]
        if not isinstance(spec, dict):
            continue
        n = counts.get(slot, 0)
        sk = spec.get("shear_key")
        if n:
            out["shear keys %s" % slot] = n * float((sk or {}).get("mass_kg") or 0.0)
    return {k: round(v, 2) for k, v in out.items()}


# =================================================================================================== frame worker
def _install_run_paths(run_dir):
    for p in (HERE, ENGINE_ROOT, run_dir):
        if p not in sys.path:
            sys.path.insert(0, p)


def frame_worker(run_dir):
    """Child process: one full pipeline run of run_dir/variant.json; writes run_dir/result.json."""
    v = json.load(open(os.path.join(run_dir, "variant.json")))
    _install_run_paths(run_dir)
    os.chdir(run_dir)
    jobs_root, name = os.path.dirname(os.path.abspath(run_dir)), os.path.basename(os.path.abspath(run_dir))
    os.environ["STEEL_BUILDER_JOBS"] = jobs_root
    os.environ["STELTIC_HR_ROOT"] = ENGINE_ROOT
    t0 = time.time()
    res = {"run_dir": run_dir, "ok": False}
    buf = io.StringIO()
    try:
        with contextlib.redirect_stdout(buf):
            import engine3d as E
            E.activate_si_units()
            import peb_levers as PL
            for rl in v.get("rods") or []:
                PL.register_rod(rl)
            mod = exec_with_overrides(os.path.join(run_dir, "cfg.py"), v.get("overrides") or {})
            cfg = mod.cfg
            for k, val in (v.get("cfg_patch") or {}).items():
                _set_path(cfg, k, val)
            rules = dict(v.get("rules") or {})
            rules["_dump_element_inputs"] = True
            cfg["peb_rules"] = rules
            faces = joint_faces(mod.__dict__, cfg, v.get("job_spec") or {})
            if v.get("connections"):
                patch_connections(cfg, v["connections"], faces)
            cb = v.get("conn_mass_basis")
            if cb:
                # the gold's declared plate take-off, corrected by the change of the itemised (resized) plates
                items = connection_items(cfg, cb["counts"], faces)
                cfg["peb_connection_mass_kg"] = round(float(cb["gold_kg"]) + sum(items.values()) - float(cb["items_kg"]), 1)
                cfg["peb_connection_mass_basis"] = (
                    "PEB-LEVERS: the gold's declared plate take-off %.0f kg corrected by the auto-sized connection plates "
                    "(peb_autosize.connection_items: %.0f kg now against %.0f kg in the gold)"
                    % (float(cb["gold_kg"]), sum(items.values()), float(cb["items_kg"])))
            import pipeline as P
            import plot_model as PM
            import static_model as SM
            PM.figures = lambda *a, **k: "skipped (peb_autosize)"
            E.export_model = lambda *a, **k: "skipped (peb_autosize)"
            SM.export_static_model = lambda *a, **k: "skipped (peb_autosize)"
            out = P.design_and_report(name, cfg, do_report=False)
            res["pipeline"] = {k: out.get(k) for k in ("blocked", "error", "model_valid", "peb_rules_note")}
            pkg_path = os.path.join(run_dir, "design", "calc_package.json")
            pkg = json.load(open(pkg_path))
            import india_seismic_gates as G
            st = G.design_status(E.CFG[name], pkg, job_dir=run_dir)
            res["design_status"] = {"status": st["status"], "reasons": st["reasons"]}
            import peb_build as PB
            snap = PB.snapshot()
            counts = joint_counts(cfg, snap)
            res["counts"] = counts
            res["faces"] = faces
            res["connection_items"] = connection_items(cfg, counts, faces)
            res["connection_design"] = read_conn_design_full(cfg, faces)
            res["rafter_lines"] = {"%s,%s" % k: v for k, v in (snap.get("rafter_lines") or {}).items()}
            res["gravity_elements"] = sorted(int(t) for t in snap.get("gravity") or [])
            res["cfg_values"] = {"D_roof": cfg.get("D_roof"), "Lr": cfg.get("Lr"), "system": cfg.get("system"),
                                 "R_x": cfg.get("R_x"), "R_y": cfg.get("R_y"),
                                 "peb_connection_mass_kg": cfg.get("peb_connection_mass_kg"),
                                 "apply_is18168": cfg.get("apply_is18168")}
            res["ok"] = True
    except Exception:
        import traceback
        res["exception"] = traceback.format_exc()[-6000:]
    res["elapsed_s"] = round(time.time() - t0, 1)
    open(os.path.join(run_dir, "worker_stdout.txt"), "w").write(buf.getvalue()[-200000:])
    json.dump(res, open(os.path.join(run_dir, "result.json"), "w"), indent=1, default=str)
    return res


def _set_path(d, path, val):
    """cfg_patch key 'a/b/c' sets d['a']['b']['c']."""
    ks = path.split("/")
    for k in ks[:-1]:
        d = d.setdefault(k, {})
    d[ks[-1]] = val


def joint_faces(ns, cfg, spec):
    """The joint face sections of THIS cfg: the column section at the knee (job spec 'knee_column' names the
    column constant; its top section) and, per rafter_splice key, the face section of the joint it designs."""
    import peb_build as PB
    out = {"knee_col_face": None, "splice_face": {}}
    kc = spec.get("knee_column")
    if kc and kc in ns:
        out["knee_col_face"] = PB.section_at(ns[kc], 1.0)
    for key, const in (spec.get("splice_faces") or {}).items():
        lab = ns.get(const[0]) if isinstance(const, (list, tuple)) else ns.get(const)
        f = const[1] if isinstance(const, (list, tuple)) else 1.0
        if lab:
            out["splice_face"][key] = PB.section_at(lab, f)
    return out


def joint_counts(cfg, snap):
    """Joint counts of the built model (fixed geometry): knees (moment-connected column tops), splice nodes per
    rafter_splice spec key, bases per column_base spec key (the BOM assignment: role-keyed, then section, then
    'default')."""
    import peb_checks as PC
    counts = {}
    knees = [ch for ch in (snap.get("chains") or {}).values() if ch.get("kind") == "column" and not ch.get("releases")]
    counts["knee"] = len(knees)
    for nd, spl in (snap.get("splices") or {}).items():
        kind = spl.get("kind")
        if kind not in ("apex", "rafter_splice", "canopy_root"):
            continue
        sp, key = PC._spec(cfg, kind, [spl.get("sec_left"), spl.get("sec_right")])
        if sp:
            counts["splice:" + key] = counts.get("splice:" + key, 0) + 1
    conn = cfg.get("connections") or {}
    bases = []
    for t, e in (snap.get("elements") or {}).items():
        m = (snap.get("members") or {}).get(e["member"]) or {}
        if m.get("kind") == "column" and int(e["n1"]) // 100000 == 0:
            bases.append((t, e["section"], m))
    assigned = set()
    slot_of = {k: sl for sl, k in base_slots(conn)}
    specs = sorted((conn.get("column_base") or {}).items(),
                   key=lambda kv: (0 if ":" in kv[0] else (2 if kv[0] == "default" else 1)))
    for key, spec in specs:
        sec_k = key.split(":", 1)[1] if ":" in key else key
        hit = [b for b in bases if b[0] not in assigned and (key == "default" or b[1] == sec_k or
                                                              (":" in key and b[2].get("section") == sec_k))]
        assigned.update(b[0] for b in hit)
        if hit:
            counts[slot_of[key]] = len(hit)
    return counts


def read_conn_design_full(cfg, faces):
    """read_conn_design with the splice slots filled (needs the joint faces)."""
    d = read_conn_design(cfg, faces.get("knee_col_face"))
    conn = cfg.get("connections") or {}
    for slot in list(d):
        if slot.startswith("splice:"):
            key = slot.split(":", 1)[1]
            face = (faces.get("splice_face") or {}).get(key)
            if face:
                d[slot] = ep_params(conn["rafter_splice"][key], face)
            else:
                d.pop(slot)
    return d


# =================================================================================================== secondary design
# The secondary worker runs in its own interpreter (python -I) with the CFS engine first on the path: the CFS and HR
# engines share module names (india_wind_tables, pipeline, consistency), so the two never share a process.
SECONDARY_WORKER = r'''
import ast, copy, json, os, sys, types, traceback


def _literal(v):
    return ast.parse(repr(v), mode="eval").body


def override_source(src, overrides, path):
    tree = ast.parse(src, filename=path)
    done = set()
    for node in tree.body:
        if isinstance(node, ast.Assign) and len(node.targets) == 1:
            tg = node.targets[0]
            if isinstance(tg, ast.Name) and tg.id in overrides:
                node.value = _literal(overrides[tg.id]); done.add(tg.id)
            elif isinstance(tg, ast.Tuple) and isinstance(node.value, ast.Tuple):
                for k, el in enumerate(tg.elts):
                    if isinstance(el, ast.Name) and el.id in overrides:
                        node.value.elts[k] = _literal(overrides[el.id]); done.add(el.id)
    miss = sorted(set(overrides) - done)
    if miss:
        raise KeyError("%s: no top-level assignment for %s" % (path, miss))
    ast.fix_missing_locations(tree)
    return tree


def load(job, purlin, girt):
    c = job["consts"]
    ov = {c["purlin"]: dict(job["purlin0"], section=purlin), c["girt"]: dict(job["girt0"], section=girt),
          c["fy"]: job["fy"]}
    path = job["script"]
    mod = types.ModuleType("secondary_mod")
    mod.__file__ = path
    exec(compile(override_source(open(path).read(), ov, path), path, "exec"), mod.__dict__)
    base = mod.cfs_cfg

    def cfs_cfg():
        cc = base()
        L = cc["loads"]
        if job.get("Lr") is not None:
            L["Lr"] = job["Lr"]
        npd = job.get("nonpermanent_kNm2") or {}
        extra = float(job.get("extra_pv_kNm2") or 0.0)
        if (npd or extra) and not job.get("collateral_in_uplift"):
            # PEB-LEVERS collateral_in_uplift False: collateral / PV are non-permanent dead (CFS engine
            # nonpermanent_dead): in the gravity combinations, out of the rows where the dead load resists uplift.
            # npd: inside the script's D_roof (taken out of it); extra: a PV load the script does not carry
            L["D_roof"] = round(float(L["D_roof"]) - sum(npd.values()), 6)
            L["collateral_kNm2"] = float(npd.get("collateral", 0.0))
            L["pv_kNm2"] = float(npd.get("pv", 0.0)) + extra
        elif extra:
            L["D_roof"] = round(float(L["D_roof"]) + extra, 6)
        return cc
    mod.cfs_cfg = cfs_cfg
    if job.get("free_flange_braced"):
        CM = mod.CM
        if not getattr(CM, "_peb_levers_patched", False):
            orig = CM.bracing_basis

            def bb(spec, span, role="purlin"):
                rec = orig(spec, span, role)
                if role == "purlin":
                    rec.update(declared=True, spacing_mm=0.0, type="sheeting", type_text="the sheeting (MARKET "
                               "PRACTICE assumption, not compliant: IS 801 6.3 needs the unbraced length of the free "
                               "flange)", note="PEB-LEVERS market practice: free flange taken as braced by the sheeting")
                return rec
            CM.bracing_basis = bb
            CM._peb_levers_patched = True
    return mod


def main():
    job = json.load(open(sys.argv[1]))
    os.environ["STELTIC_CFS_ROOT"] = job["cfs_root"]
    out = {"results": []}
    for cand in job.get("candidates") or []:
        try:
            mod = load(job, cand["purlin"], cand["girt"])
            recs = mod.CM.design_all(mod.cfs_cfg())
            row = {"purlin": cand["purlin"], "girt": cand["girt"]}
            for r in recs:
                if r.get("role") in ("purlin", "girt"):
                    bad = [c for c in r.get("checks") or [] if c.get("ok") is False]
                    row[r["role"]] = {"section": r.get("section"), "ok": r.get("ok"), "DC": r.get("DC"),
                                      "governing": r.get("governing_check") or (max(
                                          [c for c in r.get("checks") or [] if isinstance(c.get("dc"), (int, float))],
                                          key=lambda c: c["dc"], default={}) or {}).get("check"),
                                      "fails": [c.get("check") for c in bad][:6],
                                      "mass_kg_m": (mod.S811.props(r["section"]) or {}).get("mass_kg_m")}
            out["results"].append(row)
        except Exception:
            out["results"].append({"purlin": cand["purlin"], "girt": cand["girt"],
                                   "error": traceback.format_exc()[-2000:]})
    fin = job.get("write_final")
    if fin:
        mod = load(job, fin["purlin"], fin["girt"])
        mod.main()
        out["final"] = json.load(open(os.path.join(os.path.dirname(job["script"]), "secondary_result.json"))).get("mass_kg")
    json.dump(out, open(job["out"], "w"), indent=1, default=str)


main()
'''


def secondary_candidates(family, cfs_root, gold_section, span_mm):
    """Candidate zed sections of a family, lightest first: 'IS811_Fy240' -- the IS 811 lipped zeds (LZ) with a depth
    >= span / 45 (and not deeper than 300 mm); 'thin_G350' -- the generic thin zeds of cfs_generic_sections."""
    code = ("import sys, json; sys.path.insert(0, %r); import is811_sections as S811\n"
            "out = []\n"
            "fam = %r\n"
            "if fam == 'thin_G350':\n"
            "    import cfs_generic_sections as G\n"
            "    labs = G.family_labels('thin_Z_G350')\n"
            "else:\n"
            "    labs = S811.list_labels('LZ')\n"
            "for l in labs:\n"
            "    try:\n"
            "        p = S811.props(l)\n"
            "    except Exception:\n"
            "        continue\n"
            "    out.append([l, p.get('h'), p.get('t'), p.get('mass_kg_m')])\n"
            "print(json.dumps(out))\n" % (os.path.join(cfs_root, "steel_engine"), family))
    r = subprocess.run([PY, "-I", "-c", code], capture_output=True, text=True, env=_child_env(), timeout=300)
    if r.returncode:
        raise RuntimeError("secondary_candidates: %s" % r.stderr[-2000:])
    rows = json.loads(r.stdout.strip().splitlines()[-1])
    rows = [x for x in rows if x[1] and x[3] and float(x[1]) >= span_mm / 45.0 and float(x[1]) <= 300.0]
    rows.sort(key=lambda x: (float(x[3]), float(x[1]), x[0]))
    return rows


def design_secondary(run_dir, spec, rules, *, cfs_root, Lr=None, free_flange_braced=False, log_fn=log,
                     start=None, extra_pv=0.0):
    """Lightest passing purlin and girt of the switch's family for this job (the job's secondary script with the
    CFS engine); writes the final secondary/*.json into run_dir.  Returns {'purlin', 'girt', 'evaluated', ...}."""
    sec = spec["secondary"]
    script = os.path.join(run_dir, sec["script"])
    fam = rules.get("purlins", "IS811_Fy240")
    fy = 350.0 if fam == "thin_G350" else float(sec.get("fy_IS811", 240.0))
    gold = sec["gold"]
    npd = {}
    for k, nm in (sec.get("nonpermanent") or {}).items():
        npd[k] = float(nm)
    job = {"script": script, "cfs_root": cfs_root, "consts": sec["consts"], "purlin0": gold["purlin"],
           "girt0": gold["girt"], "fy": fy, "Lr": Lr, "nonpermanent_kNm2": npd,
           "collateral_in_uplift": bool(rules.get("collateral_in_uplift")),
           "free_flange_braced": bool(free_flange_braced), "extra_pv_kNm2": float(extra_pv or 0.0),
           "out": os.path.join(run_dir, "secondary_eval.json")}
    worker = os.path.join(run_dir, "_secondary_worker.py")
    open(worker, "w").write(SECONDARY_WORKER)
    cands = secondary_candidates(fam, cfs_root, gold["purlin"]["section"], float(sec["span_mm"]))

    def evaluate(pairs):
        job["candidates"] = [{"purlin": p, "girt": g} for p, g in pairs]
        job.pop("write_final", None)
        jp = os.path.join(run_dir, "secondary_job.json")
        json.dump(job, open(jp, "w"), indent=1)
        rc, el = run_child([PY, "-I", worker, jp], cwd=os.path.dirname(script), timeout=1800,
                           env={"STELTIC_CFS_ROOT": cfs_root}, log_path=os.path.join(run_dir, "secondary_worker.log"))
        if rc:
            raise RuntimeError("secondary worker failed (rc %d): see %s" % (rc, os.path.join(run_dir, "secondary_worker.log")))
        return json.load(open(job["out"]))["results"]

    gp, gg = gold["purlin"]["section"], gold["girt"]["section"]
    chosen, evaluated = {}, 0
    for role, other in (("purlin", gg), ("girt", gp)):
        # lightest first, in batches of 8 (one child process per batch)
        found = None
        for i in range(0, len(cands), 8):
            batch = cands[i:i + 8]
            pairs = [(c[0], other) if role == "purlin" else (other, c[0]) for c in batch]
            res = evaluate(pairs)
            evaluated += len(res)
            for c, r in zip(batch, res):
                rr = r.get(role) or {}
                if rr.get("ok") is True:
                    found = {"section": c[0], "mass_kg_m": c[3], "DC": rr.get("DC"), "governing": rr.get("governing")}
                    break
            if found:
                break
        if not found:
            raise RuntimeError("design_secondary: no %s of family %s passes for %s" % (role, fam, spec["job"]))
        chosen[role] = found
        log_fn("    secondary %s: %s (%.2f kg/m, DC %.3f, %s)" % (role, found["section"], found["mass_kg_m"],
                                                                  found["DC"] or -1, found["governing"]))
    job["candidates"] = []
    job["write_final"] = {"purlin": chosen["purlin"]["section"], "girt": chosen["girt"]["section"]}
    jp = os.path.join(run_dir, "secondary_job.json")
    json.dump(job, open(jp, "w"), indent=1)
    rc, el = run_child([PY, "-I", worker, jp], cwd=os.path.dirname(script), timeout=1800,
                       env={"STELTIC_CFS_ROOT": cfs_root}, log_path=os.path.join(run_dir, "secondary_worker.log"))
    if rc:
        raise RuntimeError("secondary final write failed: see secondary_worker.log")
    return {"purlin": chosen["purlin"], "girt": chosen["girt"], "evaluated": evaluated, "family": fam, "Fy_MPa": fy,
            "mass_kg": json.load(open(job["out"])).get("final")}


# =================================================================================================== local model
def _eps(fy):
    return math.sqrt(250.0 / float(fy))


def fy_of(sec, grade):
    import india_is800 as I8
    import sections as S
    m = I8.material_for_section(S.props(sec), grade)
    return float(m.get("fy_MPa") or 250.0)


class LocalModel:
    """The frozen-force model of one full run: exact member / station checks, the PEB knee and splice checks and the
    base shear keys for candidate sections, and the predicted sway / lambda_cr of a typical frame."""

    def __init__(self, run_dir, spec, x, rules):
        import peb_build as PB
        import sections as S
        import engine3d as E
        E.activate_si_units()
        self.run_dir, self.spec, self.x0, self.rules = run_dir, spec, dict(x["members"]), dict(rules)
        d = os.path.join(run_dir, "design")
        self.pkg = json.load(open(os.path.join(d, "calc_package.json")))
        self.dump = {int(k): v for k, v in json.load(open(os.path.join(d, "peb_element_inputs.json"))).items()}
        mcf = json.load(open(os.path.join(d, "member_combo_forces.json")))["elements"]
        self.res = json.load(open(os.path.join(run_dir, "result.json")))
        snap = json.load(open(os.path.join(d, "cfg_snapshot.json")))
        self.cfg = snap.get("cfg") if isinstance(snap.get("cfg"), dict) else snap
        self.cfg["peb_rules"] = {k: v for k, v in rules.items() if not k.startswith("_")}
        for lab in set(self.x0.values()):
            PB.ensure(lab)
        peb = self.pkg["peb"]
        self.members, self.chains = peb["members"], peb["chains"]
        for m in self.members.values():
            PB.ensure(m["section"]) if m.get("parse") in ("welded", "tapered") else None
        self.reg, self.envt = {}, {}
        for t, e in self.dump.items():
            mm = e["member"]
            self.reg[t] = (e["kind"], mm["section"], int(mm["node_i"]), int(mm["node_j"]))
        for k, e in mcf.items():
            t = int(k)
            self.envt[t] = {"records": e.get("records") or {}, "conn": e.get("conn_only_records") or {}}
            if t not in self.reg:
                self.reg[t] = (e["kind"], e["section"], None, None)
        self.recs = {}
        for t, e in self.dump.items():
            allr = self.envt.get(t, {}).get("records") or {}
            self.recs[t] = {l: allr[l] for l in e["records"] if l in allr}
        # const -> members / elements; clusters (consts that share a chain)
        self.const_of_label = {}
        for c, lab in self.x0.items():
            if lab in self.const_of_label:
                raise ValueError("constants %s and %s share the label %s: tie them in the job spec"
                                 % (self.const_of_label[lab], c, lab))
            self.const_of_label[lab] = c
        self.mem_of_const = {c: sorted(mid for mid, m in self.members.items() if m["section"] == lab)
                             for c, lab in self.x0.items()}
        self.el_of_mem = {mid: [int(t) for t in m["elements"] if int(t) in self.dump] for mid, m in self.members.items()}
        self.cluster = {}
        for c in self.x0:
            chains = {self.members[mid]["chain"] for mid in self.mem_of_const[c]}
            cl = set()
            for ch in chains:
                for mid in (self.chains.get(ch) or {}).get("members") or []:
                    lab = self.members[mid]["section"]
                    if lab in self.const_of_label:
                        cl.add(self.const_of_label[lab])
            self.cluster[c] = tuple(sorted(cl | {c}))
        self._dc_cache = {}
        self._t2_cache = {}
        self.is18 = self._is18()
        self.knees = self._knee_joints()
        self.knee_shear0 = self._knee_shear0()
        self.base_info = self._bases()
        self.global0 = self._globals()
        self.F0 = self.flexibility(self.x0)

    # ------------------------------------------------------------------ helpers
    def lab_of_member(self, mid, x):
        lab = self.members[mid]["section"]
        c = self.const_of_label.get(lab)
        return x[c] if c else lab

    def _is18(self):
        import peb_checks as PC
        s12 = self.s12_cfg()
        return PC._is18_smf(self.cfg, s12, self.cfg.get("system"))

    def s12_cfg(self):
        import india_seismic_gates as G
        cfg = self.cfg
        s = dict(cfg.get("section12_inputs") or {}, zone=G.zone_of(cfg), I=G.importance_of(cfg),
                 height_m=G.building_height_m(cfg), brace_config=cfg.get("brace_config"),
                 apply_is18168=cfg.get("apply_is18168"), eor_weld_exception=cfg.get("eor_weld_exception"),
                 is18168_table2=cfg.get("is18168_table2"))
        s.update({k: cfg[k] for k in ("occupancy", "scwb_pu_basis") if k in cfg})
        if cfg.get("peb_rules"):
            s["peb_rules"] = cfg["peb_rules"]
        return s

    # ------------------------------------------------------------------ members
    def buckling_section(self, chain_id, x):
        import peb_build as PB
        import sections as S
        ch = self.chains.get(chain_id) or {}
        cands = []
        for mid in ch.get("members") or []:
            lab = self.lab_of_member(mid, x)
            p = PB.parse(lab)
            if p[0] == "tapered":
                cands.append(PB.section_at(lab, 0.0 if p[1] <= p[2] else 1.0))
            else:
                cands.append(lab)
        return min(cands, key=lambda s_: float(S.props(s_)["Ix"])) if cands else None

    def element_dc(self, t, x):
        import peb_build as PB
        import design_pipeline as DP
        e = self.dump[t]
        pe = e.get("peb") or {}
        mid = pe.get("member")
        lab = self.lab_of_member(mid, x)
        f0, f1 = pe.get("f") or (0.0, 1.0)
        mem = copy.deepcopy(e["member"])
        mem["section"] = PB.section_at(lab, 0.5 * (f0 + f1))
        m = self.members[mid]
        if m["kind"] in ("column", "rafter"):
            mem["buckling_section"] = self.buckling_section(m["chain"], x)
        else:
            p = PB.parse(lab)
            mem["buckling_section"] = PB.section_at(lab, 1.0 if (p[0] == "tapered" and p[1] > p[2]) else 0.0)
        recs = self.recs[t]
        res = DP.member_checks_is800(self.cfg, {"member": mem, "kind": e["kind"], "records": recs})
        si, sj = PB.section_at(lab, f0), PB.section_at(lab, f1)
        if PB.parse(lab)[0] == "tapered" and si != sj:
            res = DP.peb_station_checks(self.cfg, mem, e["kind"], recs, res, (si, sj))
        dc = res.get("dc")
        return 9.99 if dc is None else float(dc), res.get("governing_check")

    def cluster_dc(self, c, x):
        """Max member / station D/C over the elements of the cluster of constant c with the labels of x."""
        cl = self.cluster[c]
        key = (cl, tuple(x[k] for k in cl))
        if key in self._dc_cache:
            return self._dc_cache[key]
        best = (0.0, None)
        for k in cl:
            for mid in self.mem_of_const[k]:
                for t in self.el_of_mem[mid]:
                    dc, gov = self.element_dc(t, x)
                    if dc > best[0]:
                        best = (dc, "e%d %s" % (t, gov))
        self._dc_cache[key] = best
        return best

    def member_mass(self, x):
        out = 0.0
        for c, lab in x.items():
            for mid in self.mem_of_const.get(c) or []:
                out += mass_kg_m(lab) * float(self.members[mid]["L_mm"]) / 1000.0
        return out

    # ------------------------------------------------------------------ geometric rules (fabrication, route B)
    def geometry_ok(self, c, lab):
        """Fabrication limits and the section rules that are not member checks: flange outstand semi-compact (no
        slender flange: design choice), IS 800 8.6.1.1 (a) unstiffened web d/tw <= 200 eps, minimum web 4 mm,
        tf >= tw; under IS 18168 (route B, SMRF) the Table 2 limits (5.3) and 12.11.3.1 compact or plastic."""
        key = (c, lab)
        if key in self._t2_cache:
            return self._t2_cache[key]
        import peb_build as PB
        import sections as S
        import india_is800 as I8
        k, d = parse(lab)
        fab = self.spec.get("fab") or {}
        out = (True, None)
        if k in ("tapered", "welded"):
            bf, tf, tw = d[-3], d[-2], d[-1]
            Ds = d[:2] if k == "tapered" else d[:1]
            grade = self.cfg.get("steel_grade") or "E350"
            fyf = 350.0 if str(grade).startswith("E350") and tf <= 20 else (330.0 if str(grade).startswith("E350") and tf <= 40 else (320.0 if str(grade).startswith("E350") else 250.0))
            fyw = 350.0 if str(grade).startswith("E350") and tw <= 20 else (330.0 if str(grade).startswith("E350") else 250.0)
            if tw < float(fab.get("tw_min", 4.0)) - 1e-9:
                out = (False, "web below the minimum")
            elif tf < tw:
                out = (False, "tf < tw")
            elif (bf / 2.0) / tf > 13.6 * _eps(fyf) + 1e-9:
                out = (False, "slender flange (b/tf > 13.6 eps)")
            elif any((D - 2 * tf) / tw > 200.0 * _eps(fyw) + 1e-9 for D in Ds):
                out = (False, "IS 800 8.6.1.1(a) d/tw > 200 eps")
            elif any(D > float(fab.get("D_max", 1500.0)) + 1e-9 or D < float(fab.get("D_min", 200.0)) - 1e-9 for D in Ds):
                out = (False, "depth outside the fabrication range")
            elif bf > float(fab.get("bf_max", 400.0)) + 1e-9 or bf < float(fab.get("bf_min", 120.0)) - 1e-9:
                out = (False, "flange width outside the fabrication range")
            if out[0] and self.is18 and self.spec["members"][c].get("sfrs", True):
                import india_is18168 as I18
                import india_is800_s12 as S12
                comp = "column" if self.spec["members"][c].get("group") == "column" else "beam"
                secs = [PB.section_at(lab, f) for f in ((0.0, 1.0) if k == "tapered" else (0.0,))]
                for s_ in secs:
                    PB.ensure(s_)
                    p = S.props(s_)
                    fy = fy_of(s_, grade)
                    ry = S12._ry({"grade": grade}, p)[0]
                    Ca = self._Ca(c, s_, fy) if comp == "column" else None
                    r = I18.table2_check(comp, p, fy, ry, Ca=Ca)
                    if r.get("ok") is False:
                        out = (False, "IS 18168 Table 2 (%s %s)" % (comp, r.get("value")))
                        break
                    sc = I8.section_class_table2(p, fy, welded=True)["section_class"]
                    if sc not in ("plastic", "compact"):
                        out = (False, "IS 800 12.11.3.1 %s not compact" % s_)
                        break
        self._t2_cache[key] = out
        return out

    def _Ca(self, c, sec, fy):
        import sections as S
        P = 0.0
        for mid in self.mem_of_const.get(c) or []:
            for t in self.el_of_mem[mid]:
                for r in (self.envt.get(t, {}).get("records") or {}).values():
                    P = max(P, abs(float(r[0])))
        return P / (fy * float(S.props(sec)["A"]) / 1.10)

    # ------------------------------------------------------------------ global predictors
    def _globals(self):
        pkg = self.pkg
        ws = pkg.get("wind_serviceability") or {}
        g = {}
        for dname in ("X", "Y"):
            r = ws.get(dname) or {}
            g["wind_" + dname] = max(float(r.get("ratio_top") or 0.0), float(r.get("ratio_storey") or 0.0),
                                     float(r.get("ratio_dado") or 0.0))
        for row in pkg.get("drift_table") or []:
            k = "drift_" + str(row.get("dir"))
            g[k] = max(g.get(k, 0.0), float(row.get("dc") or 0.0))
        fs = (pkg.get("peb") or {}).get("frame_stability") or {}
        for dname in ("X", "Y"):
            r = fs.get(dname) or {}
            if r.get("lambda_cr"):
                g["lambda_" + dname] = float(r["lambda_cr"])
        bd = [float(r.get("ratio") or 0.0) for r in pkg.get("beam_deflection") or [] if isinstance(r, dict)]
        g["beam_defl"] = max(bd) if bd else 0.0
        cs = pkg.get("crane_sway") or {}
        if isinstance(cs, dict) and cs.get("ratio") is not None:
            g["crane_sway"] = float(cs["ratio"])
        return g

    def flexibility(self, x):
        """Virtual-work flexibility index of the typical frame (spec 'frame_line'): sum of int m^2 / Ix ds over its
        columns (m = z/H, pinned bases; z/H - 1/2, fixed) and rafters (m = 1 at the eaves, 0 at mid-width).  Used as a
        ratio only (sway, drift, lambda_cr)."""
        import peb_build as PB
        import sections as S
        q = int(self.spec.get("frame_line", 1))
        fixed = str(self.spec.get("base", "pinned")) == "fixed"
        F = 0.0
        width = None
        for mid, m in sorted(self.members.items()):
            if m["kind"] == "rafter" and int(m.get("line", -1)) == q:
                width = max(width or 0.0, float(m.get("a1") or 0.0))
        for mid, m in sorted(self.members.items()):
            lab = self.lab_of_member(mid, x)
            if m["kind"] == "column" and list(m.get("line") or [])[:1] == [q]:
                ch = self.chains.get(m["chain"]) or {}
                if ch.get("releases") in ("J", "both"):
                    continue
                H = float(ch.get("L_mm") or 1.0)
                s0, s1 = float(m.get("s0") or 0.0), float(m.get("s1") or H)
                for k in range(8):
                    f = (k + 0.5) / 8.0
                    z = s0 + (s1 - s0) * f
                    mm = (z / H - 0.5) if fixed else z / H
                    F += mm * mm / float(S.props(PB.section_at(lab, f))["Ix"]) * (s1 - s0) / 8.0
            elif m["kind"] == "rafter" and int(m.get("line", -1)) == q and width:
                a0, a1 = float(m.get("a0") or 0.0), float(m.get("a1") or 0.0)
                start_is_eave = m.get("eave_end") == "start"
                for k in range(8):
                    f = (k + 0.5) / 8.0
                    a = a0 + (a1 - a0) * f
                    dist = min(a, width - a)
                    mm = max(0.0, 1.0 - dist / (width / 2.0))
                    ff = f if start_is_eave else 1.0 - f
                    F += mm * mm / float(S.props(PB.section_at(lab, ff))["Ix"]) * abs(a1 - a0) / 8.0
        return F

    def predicted(self, x):
        r = self.flexibility(x) / self.F0 if self.F0 else 1.0
        g = self.global0
        out = {}
        for k, v in g.items():
            if k.startswith(("wind_", "drift_", "beam_defl", "crane_sway")):
                out[k] = v * (r if k.endswith("Y") or k in ("beam_defl", "crane_sway") else 1.0)
            elif k.startswith("lambda_"):
                out[k] = v / (r if k.endswith("Y") else 1.0)
        return out

    # ------------------------------------------------------------------ joints
    def _knee_joints(self):
        """The knees of the run: node, the rafter element and the column element at it (from the registry dump)."""
        out = []
        for c in self.pkg.get("connections") or []:
            if not str(c.get("id", "")).startswith("conn-peb-knee-"):
                continue
        tops = {}
        for t, e in self.dump.items():
            pe = e.get("peb") or {}
            if e["kind"] == "col" and pe:
                m = self.members.get(pe.get("member")) or {}
                ch = self.chains.get(m.get("chain")) or {}
                if not ch.get("releases") and int(e["member"]["node_j"]) == int(ch.get("top") or -1):
                    tops[int(ch["top"])] = t
        for nd, tc in sorted(tops.items()):
            tb = None
            for t, e in self.dump.items():
                pe = e.get("peb") or {}
                if e["kind"] == "beam" and pe and nd in (int(e["member"]["node_i"]), int(e["member"]["node_j"])):
                    m = self.members.get(pe.get("member")) or {}
                    if m.get("kind") == "rafter":
                        tb = t
                        break
            if tb is not None:
                out.append({"node": nd, "tc": tc, "tb": tb})
        return out

    def _knee_shear0(self):
        """(V, Mdem) of the run's 12.10.2.4 / 12.11.2.2 knee connection-shear rows (largest V) and the
        connection-moment demand of the same member."""
        ch = (self.pkg.get("capacity_design") or {}).get("section12", {}).get("checks") or []
        knee_beams = {"e%d" % k["tb"] for k in self.knees}
        V = [(c.get("value") or 0.0, c.get("member")) for c in ch if c.get("id") == "connection_shear"
             and c.get("member") in knee_beams and isinstance(c.get("value"), (int, float))]
        if not V:
            return None
        v, mem = max(V)
        M = [c.get("value") for c in ch if c.get("id") == "connection_moment" and c.get("member") == mem
             and isinstance(c.get("value"), (int, float))]
        return (float(v), float(M[0]) if M else None)

    def is18168_6_2_dc(self, x):
        """IS 18168 6.2 (route B rafters) for the labels x: peb_checks.is18168_6_2_records on a registry rebuilt from
        the run with the candidate sections at the element ends (the check reads only geometry and sections)."""
        if not self.is18:
            return 0.0, None
        key = tuple(sorted((c, x[c]) for c in x))
        if key in self._t2_cache:
            return self._t2_cache[key]
        import peb_build as PB
        import peb_checks as PC
        saved = dict(PB._REG)
        try:
            els = {}
            for t, e in self.dump.items():
                pe = e.get("peb")
                if not pe:
                    continue
                lab = self.lab_of_member(pe["member"], x)
                f0, f1 = pe["f"]
                els[int(t)] = dict(pe, sec_i=PB.section_at(lab, f0), sec_j=PB.section_at(lab, f1),
                                   section=PB.section_at(lab, 0.5 * (f0 + f1)))
            rl = {}
            for k, v in (self.res.get("rafter_lines") or {}).items():
                a, b = k.split(",")
                rl[(int(a), int(b))] = v
            PB._REG.clear()
            PB._REG.update(elements=els, members=self.members, chains=self.chains, splices={}, continuous=set(),
                           frame_nodes=set(), gravity=set(self.res.get("gravity_elements") or []), rafter_lines=rl)
            recs = PC.is18168_6_2_records(self.cfg, self.cfg.get("system"), self.s12_cfg())
        finally:
            PB._REG.clear()
            PB._REG.update(saved)
        out = (max([r.get("DC") or 0.0 for r in recs] or [0.0]), recs[0].get("governing_check") if recs else None)
        self._t2_cache[key] = out
        return out

    def face_sections(self, x):
        """(knee column face, knee rafter face) of the labels x (the first knee: all knees share the sections)."""
        import peb_build as PB
        if not self.knees:
            return None, None
        k = self.knees[0]
        ec, eb = self.dump[k["tc"]]["peb"], self.dump[k["tb"]]["peb"]
        labc, labb = self.lab_of_member(ec["member"], x), self.lab_of_member(eb["member"], x)
        fb = eb["f"][0] if int(self.dump[k["tb"]]["member"]["node_i"]) == k["node"] else eb["f"][1]
        return PB.section_at(labc, ec["f"][1]), PB.section_at(labb, fb)

    def _bases(self):
        out = []
        for t, e in self.dump.items():
            if e["kind"] == "col" and int(e["member"]["node_i"]) // 100000 == 0:
                out.append(t)
        return sorted(out)


def _section_rename(conn, old, new):
    """Rename a section-keyed connection spec (beam_column / column_base / rafter_splice) after a section change."""
    for grp in ("beam_column", "column_base", "rafter_splice"):
        g = conn.get(grp) or {}
        for k in list(g):
            base = k.split(":", 1)[1] if ":" in k else k
            if base == old:
                nk = (k.split(":", 1)[0] + ":" + new) if ":" in k else new
                g[nk] = g.pop(k)


# =================================================================================================== local joints
def _rec(r):
    return list(r) + [0.0] * 13


def knee_demand(lm, x):
    """The worst knee of the run (knee_records scan): Mk = the largest moment at the rafter end over every
    combination (12.2.3 rows included), Vc the concurrent column shear, with the face sections of x."""
    csec, bsec = lm.face_sections(x)
    best = None
    for k in lm.knees:
        nd, tb, tc = k["node"], k["tb"], k["tc"]
        endb = "i" if lm.reg[tb][2] == nd else "j"
        Mk, lab_k, Vc = 0.0, None, 0.0
        for lab, r in (lm.envt[tb].get("records") or {}).items():
            r = _rec(r)
            M = abs(r[4] if endb == "i" else r[5])
            if M > Mk:
                Mk, lab_k = M, lab
                rc = _rec((lm.envt[tc].get("records") or {}).get(lab) or [])
                Vc = abs(rc[9] or rc[3])
        if best is None or Mk > best["Mk"]:
            best = {"Mk": Mk, "Vc": Vc, "combo": lab_k, "node": nd}
    if best:
        best.update(csec=csec, bsec=bsec)
    return best


def knee_rows(lm, cfg_c, dem, kspec, kp):
    """The four rows of peb_checks.knee_records for one knee (the same arithmetic): panel shear, column stiffeners,
    the end plate in both signs at the connection demand, the column flange T-stub.  Returns [(name, D, C)]."""
    import india_is800 as I8
    import peb_checks as PC
    import peb_levers as PL
    import sections as S
    csec, bsec = dem["csec"], dem["bsec"]
    pc, pb = S.props(csec), S.props(bsec)
    Mk, Vc = dem["Mk"], dem["Vc"]
    fyc = PC._fy_plate(csec, cfg_c)
    lever = pb["d"] - pb["tf"]
    kep = kspec.get("end_plate") or {}
    Mp_f = PC._mp(bsec, cfg_c)
    if lm.is18:
        import india_is800_s12 as S12
        ry = S12._ry({"grade": (cfg_c.get("grade_by_section") or {}).get(bsec) or cfg_c.get("steel_grade")}, pb)[0]
        fac = 1.1 * ry
    else:
        fac = 1.2
    Mconn = fac * Mp_f if kep.get("rows") else 0.0
    _Mc, _b, _on = PL.joint_demand(cfg_c, Mp_f, Mk, is18=lm.is18, system=cfg_c.get("system"), fac_default=fac)
    if _on and kep.get("rows"):
        Mconn = _Mc
    F = Mk / lever
    Vp = F - Vc
    Vweb = I8.shear_capacity(csec, fyc, axis="z", welded=True, stiffener_spacing_mm=pb["d"]).get("Vd_N") or 0.0
    ds = kp.get("diagonal_stiffener") or {}
    theta = math.atan2(pb["d"], pc["d"])
    A_d = float(ds.get("n", 2)) * float(ds.get("b_mm", 0.0)) * float(ds.get("t_mm", 0.0))
    V_d = A_d * float(ds.get("fy_MPa", 250.0)) / 1.10 * math.cos(theta)
    dbl = float(kp.get("doubler_t_mm") or 0.0)
    V_dbl = (pc["d"] - 2 * pc["tf"]) * dbl * 250.0 / (math.sqrt(3.0) * 1.10)
    rows = [("knee panel shear", Vp, Vweb + V_d + V_dbl)]
    fs_ = kp.get("flange_stiffener") or {}
    A_f = float(fs_.get("n", 2)) * float(fs_.get("b_mm", 0.0)) * float(fs_.get("t_mm", 0.0))
    t_cfl = float(kspec.get("column_flange_t_mm") or pc["tf"])
    tw_c = float(pc["tw"]) + dbl
    b_web = pb["tf"] + 5.0 * (t_cfl + float(kp.get("weld_mm", 6.0)))
    cap_f = (A_f * float(fs_.get("fy_MPa", 250.0)) + tw_c * b_web * fyc) / 1.10
    rows.append(("knee column stiffeners", max(Mk, Mconn) / lever, cap_f))
    if kep.get("rows"):
        sym = bool(kspec.get("symmetric"))
        lay = PC.end_plate_layout(kep, bsec, symmetric=sym)
        cap_p = (PC.end_plate_capacity(kep, cfg_c) or {}).get("capacity_Nmm")
        if sym:
            cap_r = cap_p
        else:
            cap_r = (PC.end_plate_capacity(kep, cfg_c, rows=lay["reverse_rows"]) or {}).get("capacity_Nmm") \
                if lay["reverse_rows"] else None
        cap_ep = min(c_ for c_ in (cap_p, cap_r) if c_) if (cap_p and cap_r) else 0.0
        rows.append(("knee end plate, both signs", Mconn, cap_ep))
        g_cf = kspec.get("gauge_mm")
        lv_cf = float(kspec.get("column_flange_lv_mm")
                      or ((float(g_cf) / 2.0 - pc["tw"] / 2.0 - float(kspec.get("column_weld_mm", 8.0)))
                          if g_cf else kep.get("lv_mm")))
        grade_c = (kspec.get("column_flange_grade") or (cfg_c.get("grade_by_section") or {}).get(csec)
                   or cfg_c.get("steel_grade"))
        cf = dict(kep, t_plate_mm=t_cfl, fy_plate_MPa=fyc, lv_mm=lv_cf, plate_grade=grade_c, web_t_mm=tw_c,
                  web_fy_MPa=fyc, hf_mm=lay["hf_mm"])
        caps = [(PC.end_plate_capacity(cf, cfg_c) or {}).get("capacity_Nmm")]
        if not sym and lay["reverse_rows"]:
            caps.append((PC.end_plate_capacity(cf, cfg_c, rows=lay["reverse_rows"]) or {}).get("capacity_Nmm"))
        caps = [c_ for c_ in caps if c_]
        rows.append(("knee column flange T-stub", Mconn, min(caps) if caps else 0.0))
        rows.append(("_Mconn", Mconn, None))
    return rows


def _ok(rows, margin):
    return all((C or 0.0) > 0 and D <= margin * C + 1e-6 for n, D, C in rows if C is not None and not n.startswith("_"))


def _knee_mass(par, kp_par, kspec, kp, bsec, csec):
    """kg per knee: end plate + knee-zone column flange plate (extra over the column flange) + rib stiffeners (if the
    gold has them) + column flange stiffeners + diagonal stiffener pair (connection_items basis)."""
    import sections as S
    pc, pb = S.props(csec), S.props(bsec)
    h = ep_height(bsec, par["n_out"], pitch_of(par, bsec))
    kg = par["b_plate"] * par["t"] * h * STEEL
    if par.get("t_cf") and par["t_cf"] > pc["tf"] + 1e-9 and _bom_item(kspec.get("bom_plates"), "knee-zone column flange plates"):
        kg += pc["bf"] * (par["t_cf"] - pc["tf"]) * (h + 100.0) * STEEL
    rib = _bom_item(kspec.get("bom_plates"), "extension rib stiffeners")
    if rib:
        t_ = (_parse_txhxl(rib.get("size")) or (10.0,))[0]
        ext = h / 2.0 - pb["d"] / 2.0
        kg += int(rib.get("qty_per_joint") or 1) * 0.5 * ext * 1.7 * ext * t_ * STEEL
    fs, ds = kp.get("flange_stiffener") or {}, kp.get("diagonal_stiffener") or {}
    kg += 2 * float(fs.get("n", 2)) * float(fs.get("b_mm", 0)) * float(kp_par.get("flange_t") or fs.get("t_mm", 0)) * \
        (pc["d"] - 2 * pc["tf"]) * STEEL
    kg += float(ds.get("n", 2)) * float(ds.get("b_mm", 0)) * float(kp_par.get("diag_t") or ds.get("t_mm", 0)) * \
        math.hypot(pc["d"], pb["d"]) * STEEL
    return kg


def size_knee(lm, x, par0, kp0, margin=1.0, t_min=None):
    """Lightest knee (end plate t, bolt d, rows beyond the flange, knee-zone column flange plate, column flange
    stiffeners, diagonal stiffener) for the members x.  par0 / kp0: the current design (its b_plate, n_in, pitch rule,
    grades kept).  Returns (par, kp_par, kg_per_knee, rows) or None when nothing in the catalogue passes."""
    import sections as S
    dem = knee_demand(lm, x)
    if not dem:
        return None
    csec, bsec = dem["csec"], dem["bsec"]
    cfg_c = lm.cfg
    old_face = next((k for k, v in (cfg_c.get("connections") or {}).get("beam_column", {}).items()
                     if k != "default" and (v or {}).get("end_plate", {}).get("rows")), None)
    kspec0 = copy.deepcopy(cfg_c["connections"]["beam_column"][old_face])
    kp = copy.deepcopy((cfg_c.get("connections") or {}).get("knee_panel") or {})
    pc = S.props(csec)
    plates = [t for t in PLATES_MM if t >= 10.0]
    t_lo = max(10.0, float(t_min or 0.0))
    # 1) diagonal stiffener: the panel shear row only
    best_d = None
    for td in [t for t in PLATES_MM if t >= 6.0]:
        kp_t = copy.deepcopy(kp)
        if kp_t.get("diagonal_stiffener"):
            kp_t["diagonal_stiffener"]["t_mm"] = td
            kp_t["diagonal_stiffener"]["fy_MPa"] = plate_fy(td, "E250")
        r = knee_rows(lm, cfg_c, dem, dict(kspec0, end_plate={}), kp_t)
        if _ok([r[0]], margin):
            best_d = td
            break
        if not kp.get("diagonal_stiffener"):
            break
    if best_d is None and kp.get("diagonal_stiffener"):
        return None
    best = None
    tcf_list = [None] + [t for t in PLATES_MM if t > pc["tf"] + 1e-9]
    for d in BOLT_D_MM:
        for n_out in sorted({1, 2, int(par0["n_out"])}):
            par = dict(par0, d=d, n_out=n_out)
            # end plate: thinnest t that passes the end-plate row
            t_ok = None
            for t in plates:
                if t < t_lo:
                    continue
                par["t"] = t
                ks = dict(kspec0, end_plate=make_ep(par, bsec))
                r = knee_rows(lm, cfg_c, dem, ks, kp)
                if _ok([r[2]], margin):
                    t_ok = t
                    break
            if t_ok is None:
                continue
            par["t"] = t_ok
            ep = make_ep(par, bsec)
            # column flange plate and stiffeners
            for tcf in tcf_list:
                par["t_cf"] = tcf if tcf else float(pc["tf"])
                ks = dict(kspec0, end_plate=ep, column_flange_t_mm=par["t_cf"])
                r = knee_rows(lm, cfg_c, dem, ks, kp)
                if not _ok([r[3]], margin):
                    continue
                fl_ok = None
                for tf_ in [t for t in PLATES_MM if t >= 6.0]:
                    kp_t = copy.deepcopy(kp)
                    if kp_t.get("flange_stiffener"):
                        kp_t["flange_stiffener"]["t_mm"] = tf_
                        kp_t["flange_stiffener"]["fy_MPa"] = plate_fy(tf_, "E250")
                    if kp_t.get("diagonal_stiffener"):
                        kp_t["diagonal_stiffener"]["t_mm"] = best_d
                        kp_t["diagonal_stiffener"]["fy_MPa"] = plate_fy(best_d, "E250")
                    r2 = knee_rows(lm, cfg_c, dem, ks, kp_t)
                    if _ok(r2, margin) and _knee_shear_ok(lm, cfg_c, ks, bsec, r2, margin):
                        fl_ok = (tf_, r2, kp_t)
                        break
                    if not kp.get("flange_stiffener"):
                        break
                if fl_ok is None:
                    continue
                kp_par = {"diag_t": best_d, "flange_t": fl_ok[0]}
                kg = _knee_mass(par, kp_par, ks, kp, bsec, csec)
                key = (round(kg, 3), d, n_out, par["t"])
                if best is None or key < best[0]:
                    best = (key, dict(par), kp_par, kg, fl_ok[1])
                break                                          # thinner column flange plates were tried first
    if not best:
        return None
    return best[1], best[2], best[3], best[4]


def _knee_shear_ok(lm, cfg_c, kspec, bsec, rows, margin):
    """IS 800 12.10.2.4 / 12.11.2.2 connection shear of the knee: the run's demand scaled with the connection moment
    (never down: V = Vg + 2 Mdem / L', Vg unknown here), against the declared shear plate / bolts (t, h follow the end
    plate)."""
    import india_connections as C
    sh = copy.deepcopy(kspec.get("shear") or {})
    if not sh or not lm.knee_shear0:
        return True
    ep = kspec["end_plate"]
    t_old = float(sh.get("t_plate_mm") or ep["t_plate_mm"])
    r_ = float(ep["t_plate_mm"]) / t_old
    sh["t_plate_mm"] = float(ep["t_plate_mm"])
    sh["fy_plate_MPa"] = plate_fy(sh["t_plate_mm"], sh.get("plate_grade") or "E250")
    if isinstance(sh.get("block_shear_areas"), dict):
        sh["block_shear_areas"] = {k: v * r_ for k, v in sh["block_shear_areas"].items()}
    sh.pop("V_N", None)
    sh.setdefault("plate_grade", (kspec.get("plate_grade") or lm.cfg.get("plate_grade")))
    sh.setdefault("job_steel_grade", lm.cfg.get("steel_grade"))
    try:
        cap = C.fin_plate_shear_checks(V_N=1.0, **sh).get("capacity_N")
    except Exception:
        return True
    V0, M0 = lm.knee_shear0
    Mc = next((D for n, D, C_ in rows if n == "_Mconn"), M0)
    V = V0 * max(1.0, Mc / M0) if M0 else V0
    return bool(cap) and V <= margin * cap


def splice_demands(lm, x):
    """{spec key: demand record} for the rafter_splice specs with an end plate: the largest Mdem / Mdem_r of
    peb_checks.splice_records over the joints the spec designs, with the faces of x."""
    import peb_build as PB
    import peb_checks as PC
    import peb_levers as PL
    out = {}
    cfg = lm.cfg
    for nd_s, spl in sorted((lm.pkg["peb"].get("splices") or {}).items()):
        kind = spl.get("kind")
        if kind not in ("apex", "rafter_splice", "canopy_root"):
            continue
        nd = int(nd_s)
        secs = []
        for side, mid in zip(("sec_left", "sec_right"), (spl.get("members") or []) + [None]):
            old = spl.get(side)
            if mid is None or mid not in lm.members:
                secs.append(old)
                continue
            lab_old = lm.members[mid]["section"]
            lab_new = lm.lab_of_member(mid, x)
            f = 1.0 if PB.section_at(lab_old, 1.0) == old else 0.0
            secs.append(PB.section_at(lab_new, f))
        if len(secs) == 1:
            secs = [secs[0], secs[0]]
        sp, key = PC._spec(cfg, kind, [s_ for s_ in [spl.get("sec_left"), spl.get("sec_right")]])
        if not sp or not (sp.get("end_plate") or {}).get("rows"):
            continue
        sec_min = min(secs, key=lambda s_: PC._mp(s_, cfg))
        Mp = PC._mp(sec_min, cfg)
        f = PC._node_forces(lm.reg, lm.envt, nd)
        M_an = max([abs(v[0]) for v in f.values()] or [0.0])
        M_rev = PC.reverse_demand(lm.reg, lm.envt, nd)[0]
        is18 = lm.is18
        if kind == "canopy_root" or spl.get("gravity"):
            Md, Mr = M_an, M_rev
        elif kind == "apex":
            Md = max(1.2 * Mp, (1.8 if is18 else 1.0) * M_an)
            Mr = max(1.2 * Mp, (1.8 if is18 else 1.0) * M_rev)
            a, _b, on = PL.joint_demand(cfg, Mp, M_an, is18=is18, system=cfg.get("system"))
            if on:
                Md = max(a, M_an)
                Mr = max(PL.joint_demand(cfg, Mp, M_rev, is18=is18, system=cfg.get("system"))[0], M_rev)
        elif is18:
            Md, Mr = 1.8 * M_an, 1.8 * M_rev
        else:
            Md, Mr = M_an, M_rev
        r = out.setdefault(key, {"Md": 0.0, "Mr": 0.0, "sec_min": sec_min, "kind": kind, "spec": sp, "n": 0})
        r["n"] += 1
        if Md >= r["Md"]:
            r["Md"], r["sec_min"] = Md, sec_min
        r["Mr"] = max(r["Mr"], Mr)
    return out


def size_splice(lm, key, dem, face, par0, margin=1.0, t_min=None):
    """Lightest end plate (t, bolt d, rows beyond the flange) of a rafter_splice spec for its demand."""
    import peb_checks as PC
    sp = dem["spec"]
    sym = bool(sp.get("symmetric"))
    best = None
    t_lo = max(10.0, float(t_min or 0.0))
    for d in BOLT_D_MM:
        for n_out in sorted({1, 2, int(par0["n_out"])}):
            par = dict(par0, d=d, n_out=n_out)
            for t in [t for t in PLATES_MM if t >= t_lo]:
                par["t"] = t
                ep = make_ep(par, face)
                cap = (PC.end_plate_capacity(ep, lm.cfg) or {}).get("capacity_Nmm") or 0.0
                lay = PC.end_plate_layout(ep, dem["sec_min"], symmetric=sym)
                if sym:
                    cap_r = cap
                else:
                    cap_r = (PC.end_plate_capacity(ep, lm.cfg, rows=lay["reverse_rows"]) or {}).get("capacity_Nmm") \
                        if lay["reverse_rows"] else 0.0
                if dem["Md"] <= margin * cap + 1e-6 and (dem["Mr"] <= 1.0 or dem["Mr"] <= margin * (cap_r or 0.0) + 1e-6):
                    h = ep_height(face, n_out, pitch_of(par, face))
                    npl = 1 if key == "canopy_root" else 2
                    kg = npl * par["b_plate"] * t * h * STEEL
                    rib = _bom_item(sp.get("bom_plates"), "extension rib stiffeners")
                    if rib:
                        import sections as S
                        tr = (_parse_txhxl(rib.get("size")) or (10.0,))[0]
                        ext = h / 2.0 - S.props(face)["d"] / 2.0
                        kg += int(rib.get("qty_per_joint") or 1) * 0.5 * ext * 1.7 * ext * tr * STEEL
                    k_ = (round(kg, 3), d, n_out, t)
                    if best is None or k_ < best[0]:
                        best = (k_, dict(par), kg, (dem["Md"], cap, dem["Mr"], cap_r))
                    break
    if not best:
        return None
    return best[1], best[2], best[3]


def base_demands(lm, x, base_counts):
    """{column_base key: required shear-key capacity (N)} -- per case the base shear (the switch: max(case, 1.2 Vd
    of the base section about its frame axes) or the case alone; IS 18168 9.3 2.2 Ry Mpc / Hc on fixed SFRS bases in
    the seismic cases) less friction 0.45 P (compression), the largest over the bases of the key."""
    import india_is800 as I8
    import india_is800_s12 as S12
    import india_connection_design as CD
    import peb_build as PB
    import peb_levers as PL
    import sections as S
    cfg = lm.cfg
    rule_an = bool(PL.base_shear_note(cfg))
    conn = cfg.get("connections") or {}
    s12 = {}
    for c in (lm.pkg.get("capacity_design") or {}).get("section12", {}).get("checks") or []:
        if c.get("id") in ("12.12_base", "7.4_base"):
            s12[str(c.get("member"))] = c
    specs = sorted((conn.get("column_base") or {}).items(),
                   key=lambda kv: (0 if ":" in kv[0] else (2 if kv[0] == "default" else 1)))
    slot_of = {k: sl for sl, k in base_slots(conn)}
    out = {}
    assigned = set()
    for key, spec in specs:
        sec_k = key.split(":", 1)[1] if ":" in key else key
        for t in lm.base_info:
            if t in assigned:
                continue
            sec_old = lm.reg[t][1]
            pe = lm.dump[t].get("peb") or {}
            mlab_old = (lm.members.get(pe.get("member")) or {}).get("section")
            if not (key == "default" or sec_old == sec_k or (":" in key and mlab_old == sec_k)):
                continue
            assigned.add(t)
            if not (isinstance(spec, dict) and spec.get("shear_key")):
                continue
            row = s12.get("base-e%d" % t) or {}
            sfrs = bool(row.get("sfrs", row.get("id") == "12.12_base"))
            axes = row.get("frame_axes") or ["z"]
            lab_new = lm.lab_of_member(pe.get("member"), x) if pe else sec_old
            sec_new = PB.section_at(lab_new, pe["f"][0] * 0.5 + pe["f"][1] * 0.5) if pe else sec_old
            p = S.props(sec_new)
            fy = fy_of(sec_new, cfg.get("steel_grade"))
            vmin = 0.0
            if sfrs and not rule_an:
                vmin = max([1.2 * (I8.shear_capacity(p, fy, axis=ax).get("Vd_N") or 0.0) for ax in axes] or [0.0])
            fixed = bool(spec.get("fixed")) and sfrs
            use18 = sfrs and lm.is18
            Hc = float(lm.dump[t]["member"].get("Lz_mm") or lm.dump[t]["member"].get("L_mm") or 0.0)
            need = 0.0
            for lc in CD.base_load_cases(lm.envt[t].get("records") or {}):
                V0 = float(lc["V_N"])
                P = float(lc["P_N"])
                V = max(V0, vmin)
                if fixed and use18 and lc.get("seismic") and Hc:
                    ry = S12._ry({"grade": cfg.get("steel_grade")}, p)[0]
                    for ax in axes:
                        Mpc = S12.mpc_9_3_1_2(p, fy, P, ax)[0]
                        V = max(V, 2.2 * ry * Mpc / Hc)
                need = max(need, V - 0.45 * max(P, 0.0))
            out[slot_of[key]] = max(out.get(slot_of[key], 0.0), need)
    return out


def key_catalogue():
    cat = []
    for b in KEY_B_MM:
        for t in [tt for tt in PLATES_MM if 12.0 <= tt <= 63.0]:
            if t > b / 4.0:
                continue
            for h in KEY_H_MM:
                cat.append((round(2 * b * t * (h + 50.0) * STEEL, 3), b, t, h))
    cat.sort()
    return cat


_KEYCAT = None


def size_key(need_N, fck, margin=1.0, b_max=None):
    """Lightest cruciform key with capacity >= need (None: no key needed); the key plates fit under the base plate
    (b <= the smaller plan dimension of the base plate)."""
    global _KEYCAT
    if need_N <= 0.0:
        return None, 0.0
    _KEYCAT = _KEYCAT or key_catalogue()
    for kg, b, t, h in _KEYCAT:
        if b_max and b > b_max + 1e-9:
            continue
        if shear_key(b, t, h, plate_fy(t, "E250"), fck)["capacity_N"] * margin >= need_N:
            return [b, t, h], kg
    return "none_fits", None


# =================================================================================================== the search
def dim_groups(spec, x):
    """Design dimensions as tied groups [[(const, dim), ...], ...]: the spec 'links' tie dimensions that must stay
    equal (the knee depth of column and rafter, the matching depths at an end-plate splice); 'fixed' dims are left out."""
    fixed = set(spec.get("fixed") or [])
    links = [[tuple(a.split(".")) for a in L] for L in spec.get("links") or []]
    seen, groups = set(), []
    for c in sorted(spec["members"]):
        k, _d = parse(x[c])
        for dn in DIMS.get(k, ()):
            cd = (c, dn)
            if cd in seen or "%s.%s" % cd in fixed:
                continue
            g = [cd]
            for L in links:
                if cd in L:
                    g = sorted(set(g) | set(L))
            seen.update(g)
            groups.append(g)
    return groups


def dim_values(dn, current, spec):
    fab = spec.get("fab") or {}
    if dn in ("D", "D0", "D1"):
        lo, hi = float(fab.get("D_min", 200.0)), float(fab.get("D_max", 1500.0))
        vals = set(float(v) for v in range(int(lo), int(hi) + 1, int(DEPTH_STEP_MM)))
    elif dn == "bf":
        vals = set(float(v) for v in FLANGE_W_MM)
    else:
        vals = set(PLATES_MM)
        if dn == "tw":
            vals = {v for v in vals if v >= float(fab.get("tw_min", 4.0))}
        else:
            vals = {v for v in vals if v >= 6.0}
    vals.add(float(current))
    return sorted(vals)


def step_group(x, g, n, spec):
    """x with the dims of group g moved n notches (negative: lighter); None when out of range or unchanged."""
    c0, d0 = g[0]
    cur = dim(x[c0], d0)
    vals = dim_values(d0, cur, spec)
    i = vals.index(cur) + n
    if i < 0 or i >= len(vals):
        return None
    v = vals[i]
    x2 = dict(x)
    for c, dn in g:
        x2[c] = with_dim(x2[c], dn, v)
    return x2


def _orientation_ok(x, x_gold):
    """A tapered member keeps the gold's taper direction (shallow at the pinned base, deep at the knee)."""
    for c, lab in x.items():
        k, d = parse(lab)
        kg, dg = parse(x_gold.get(c, lab))
        if k == "tapered" and kg == "tapered":
            if (dg[0] < dg[1]) != (d[0] < d[1]) or abs(d[0] - d[1]) < 1e-9:
                return False
    return True


class Evaluator:
    """Local (frozen-force) feasibility and mass of member labels x, with the joints sized for them."""

    def __init__(self, lm, spec, conn_prev, margins, x_gold):
        self.lm, self.spec, self.conn_prev, self.m, self.x_gold = lm, spec, conn_prev or {}, margins, x_gold
        self.counts = lm.res.get("counts") or {}
        self.cache, self.conn_cache = {}, {}
        self.n_eval = 0

    def margin(self, key, default=1.0):
        return float(self.m.get(key, default))

    def connections(self, x):
        lm = self.lm
        csec, bsec = lm.face_sections(x)
        faces = self.spec.get("splice_faces") or {}
        import peb_build as PB
        fkey = tuple(sorted((k, PB.section_at(x[v[0]], v[1]) if isinstance(v, (list, tuple)) else x[v])
                            for k, v in faces.items() if (v[0] if isinstance(v, (list, tuple)) else v) in x))
        bkey = tuple(sorted((c, x[c]) for c in self.spec.get("base_consts") or []))
        key = (csec, bsec, fkey, bkey)
        if key in self.conn_cache:
            return self.conn_cache[key]
        design, kg, info = {}, 0.0, {}
        cp = self.conn_prev
        if cp.get("knee") and lm.knees:
            r = size_knee(lm, x, cp["knee"], cp.get("knee_panel") or {}, margin=self.margin("conn:knee"),
                          t_min=self.m.get("tmin:knee"))
            if r is None:
                self.conn_cache[key] = (None, None, {"fail": "knee"})
                return self.conn_cache[key]
            design["knee"], design["knee_panel"] = r[0], r[1]
            kg += self.counts.get("knee", 0) * r[2]
            info["knee"] = {"kg_each": round(r[2], 1), "rows": [(n, round(D / 1e6 if "stiff" not in n and "panel" not in n
                                                                           else D / 1e3, 1),
                                                                 round((C or 0) / 1e6 if "stiff" not in n and "panel" not in n
                                                                       else (C or 0) / 1e3, 1)) for n, D, C in r[3]]}
        sd = splice_demands(lm, x)
        for skey, dem in sd.items():
            slot = "splice:" + skey
            if not cp.get(slot) or skey not in faces:
                continue
            v = faces[skey]
            face = PB.section_at(x[v[0]], v[1]) if isinstance(v, (list, tuple)) else x[v]
            r = size_splice(lm, skey, dem, face, cp[slot], margin=self.margin("conn:" + slot),
                            t_min=self.m.get("tmin:" + slot))
            if r is None:
                self.conn_cache[key] = (None, None, {"fail": slot})
                return self.conn_cache[key]
            design[slot] = r[0]
            kg += self.counts.get(slot, 0) * r[1]
            info[slot] = {"kg_each": round(r[1], 1), "Md_kNm": round(dem["Md"] / 1e6, 1), "cap_kNm": round(r[2][1] / 1e6, 1)}
        bd = base_demands(lm, x, self.counts)
        for slot, need in bd.items():
            if slot not in cp:
                continue
            dims, kgk = size_key(need, cp[slot].get("fck", 30.0), margin=self.margin("conn:base"),
                                 b_max=cp[slot].get("b_max"))
            if dims == "none_fits":
                self.conn_cache[key] = (None, None, {"fail": slot})
                return self.conn_cache[key]
            design[slot] = {"key": dims, "fck": cp[slot].get("fck", 30.0), "b_max": cp[slot].get("b_max")}
            kg += self.counts.get(slot, 0) * (kgk or 0.0)
            info[slot] = {"need_kN": round(need / 1e3, 1), "key": dims}
        self.conn_cache[key] = (design, kg, info)
        return self.conn_cache[key]

    def __call__(self, x):
        key = tuple(sorted(x.items()))
        if key in self.cache:
            return self.cache[key]
        self.n_eval += 1
        lm = self.lm
        out = {"x": dict(x), "feasible": False, "mass": None, "why": None}
        if not _orientation_ok(x, self.x_gold):
            out["why"] = "taper orientation"
            self.cache[key] = out
            return out
        for c in sorted(x):
            ok, why = lm.geometry_ok(c, x[c])
            if not ok:
                out["why"] = "%s: %s" % (c, why)
                self.cache[key] = out
                return out
        viol = 0.0
        dcs = {}
        for c in sorted(x):
            cl = lm.cluster[c]
            if cl in dcs:
                continue
            dc, gov = lm.cluster_dc(c, x)
            dcs[cl] = (dc, gov)
            mg = self.margin("member:" + "+".join(cl), self.margin("member", 0.99))
            if dc > mg:
                viol += dc - mg
                out["why"] = out["why"] or "member %s D/C %.3f > %.3f (%s)" % ("+".join(cl), dc, mg, gov)
        if lm.is18:
            dc62, gov62 = lm.is18168_6_2_dc(x)
            mg = self.margin("is18168_6_2", 1.0)
            if dc62 > mg:
                viol += dc62 - mg
                out["why"] = out["why"] or "IS 18168 6.2 %.3f > %.3f (%s)" % (dc62, mg, gov62)
            dcs[("IS18168_6.2",)] = (dc62, gov62)
        pr = lm.predicted(x)
        for k, v in pr.items():
            if k.startswith("lambda_"):
                need = 5.0 / self.margin("lambda", 0.97)
                if v < need:
                    viol += (need - v) / need
                    out["why"] = out["why"] or "%s %.2f < %.2f (predicted)" % (k, v, need)
            else:
                mg = self.margin("sway" if k.startswith(("wind", "drift", "crane")) else "defl", 0.98)
                if v > mg:
                    viol += v - mg
                    out["why"] = out["why"] or "%s %.3f > %.3f (predicted)" % (k, v, mg)
        design, ckg, cinfo = self.connections(x)
        if design is None:
            viol += 1.0
            out["why"] = out["why"] or "joint %s: nothing in the catalogue passes" % cinfo.get("fail")
        mm = lm.member_mass(x)
        out.update(viol=viol, member_kg=mm, conn_kg=ckg, conn=design, conn_info=cinfo, dcs={"+".join(k): v for k, v in dcs.items()},
                   predicted=pr)
        out["mass"] = mm + (ckg or 0.0)
        out["feasible"] = viol <= 0.0
        self.cache[key] = out
        return out


def local_optimize(ev, x0, groups, spec, *, max_passes=8, log_fn=log, time_cap_s=900.0):
    """Deterministic coordinate descent on the tied dimension groups with the local evaluator: first a repair of an
    infeasible start (the move that cuts the violation most per kg), then lighter moves of 1, 2, 4 or 8 notches per
    group, then pair moves (one group lighter, another heavier) when no single move helps."""
    t0 = time.time()
    x = dict(x0)
    e = ev(x)
    it = 0
    while not e["feasible"] and it < 60 and time.time() - t0 < time_cap_s:
        it += 1
        best = None
        for g in groups:
            for n in (1, 2, 4):
                x2 = step_group(x, g, n, spec)
                if not x2:
                    continue
                e2 = ev(x2)
                if e2.get("viol") is None:
                    continue
                gain = e["viol"] - e2["viol"] if e.get("viol") is not None else 1.0
                if gain <= 1e-9 and not e2["feasible"]:
                    continue
                dm = max((e2["mass"] or 0.0) - (e["mass"] or 0.0), 1e-3)
                k_ = (0 if e2["feasible"] else 1, -(gain / dm) if not e2["feasible"] else e2["mass"])
                if best is None or k_ < best[0]:
                    best = (k_, x2, e2)
        if best is None:
            log_fn("    local repair: no move reduces the violation (%s)" % e.get("why"))
            return x, e
        x, e = best[1], best[2]
    if not e["feasible"]:
        return x, e
    for p in range(max_passes):
        if time.time() - t0 > time_cap_s:
            log_fn("    local descent: time cap reached")
            break
        improved = False
        for g in groups:
            best = None
            for n in (-8, -4, -2, -1):
                x2 = step_group(x, g, n, spec)
                if not x2:
                    continue
                e2 = ev(x2)
                if e2["feasible"] and e2["mass"] < e["mass"] - 0.05 and (best is None or e2["mass"] < best[1]["mass"]):
                    best = (x2, e2)
            if best:
                x, e = best
                improved = True
        if not improved:
            # pair moves: one group a notch lighter (infeasible alone), another a notch heavier
            for g1 in groups:
                x1 = step_group(x, g1, -1, spec)
                if not x1 or ev(x1)["feasible"]:
                    continue
                for g2 in groups:
                    if g2 == g1:
                        continue
                    x12 = step_group(x1, g2, 1, spec)
                    if not x12:
                        continue
                    e12 = ev(x12)
                    if e12["feasible"] and e12["mass"] < e["mass"] - 0.05:
                        x, e = x12, e12
                        improved = True
                        break
                if improved:
                    break
        if not improved:
            break
    return x, e


# =================================================================================================== full runs
def evaluate_run(run_dir, waivers=()):
    """Pass / fail of a full run (india_seismic_gates.design_status, with the variant's accepted non-compliance
    patterns waived), the take-off and the governing check."""
    res = json.load(open(os.path.join(run_dir, "result.json")))
    out = {"ok_run": bool(res.get("ok")), "exception": res.get("exception"), "elapsed_s": res.get("elapsed_s")}
    if not res.get("ok"):
        out["passed"] = False
        return out
    pkg = json.load(open(os.path.join(run_dir, "design", "calc_package.json")))
    st = res.get("design_status") or {}
    reasons = st.get("reasons") or []
    waived = [r for r in reasons if any(re.search(w, r) for w in waivers)]
    blocking = [r for r in reasons if r not in waived]
    out.update(status=st.get("status"), reasons=reasons, waived=waived, blocking=blocking, passed=not blocking)
    ton = (pkg.get("peb") or {}).get("tonnage") or {}
    out["tonnage_kg"] = ton.get("kg")
    out["plan_area_m2"] = ton.get("plan_area_m2")
    # governing check: the largest D/C over members, connections, Section 12 rows and the analysis ratios
    cands = []
    for m in pkg.get("members") or []:
        if isinstance(m.get("DC"), (int, float)):
            cands.append((m["DC"], "member", m["id"], m.get("governing_check")))
    for c in pkg.get("connections") or []:
        if isinstance(c.get("DC"), (int, float)):
            cands.append((c["DC"], "connection", c["id"], c.get("governing_check")))
    for c in (pkg.get("capacity_design") or {}).get("section12", {}).get("checks") or []:
        if isinstance(c.get("dc"), (int, float)) and c.get("ok") is not None:
            cands.append((c["dc"], "section12", "%s@%s" % (c.get("id"), c.get("member")), c.get("clause")))
    for dname, r in (pkg.get("wind_serviceability") or {}).items():
        if isinstance(r, dict):
            cands.append((r.get("ratio_top", 0.0), "sway", "wind %s eave" % dname, r.get("cite", "")[:80]))
            if r.get("ratio_dado") is not None:
                cands.append((r["ratio_dado"], "sway", "wind %s dado top" % dname, "IS 800 Table 6 H/240 at the dado"))
    for row in pkg.get("drift_table") or []:
        cands.append((row.get("dc") or 0.0, "drift", "storey drift %s" % row.get("dir"), row.get("clause")))
    for r in pkg.get("beam_deflection") or []:
        if isinstance(r, dict):
            cands.append((r.get("ratio") or 0.0, "deflection", "rafter %s" % r.get("section"), "IS 800 Table 6"))
    fs = (pkg.get("peb") or {}).get("frame_stability") or {}
    for dname in ("X", "Y"):
        lam = (fs.get(dname) or {}).get("lambda_cr")
        if lam:
            cands.append((5.0 / lam, "stability", "lambda_cr %s = %.2f" % (dname, lam), "IS 800 4.6.2(b) B-2.1"))
    cands.sort(key=lambda r: -r[0])
    out["governing"] = cands[0] if cands else None
    out["top_checks"] = cands[:8]
    out["fail_items"] = [c for c in cands if c[0] > 1.0 + 1e-9][:40]
    s12 = (pkg.get("capacity_design") or {}).get("section12", {}).get("checks") or []
    out["s12_fail"] = [(c.get("id"), c.get("member"), c.get("dc")) for c in s12 if c.get("ok") is False][:40]
    out["gates_fail"] = [g for g, v in (pkg.get("gates") or {}).items() if v is False]
    out["design_connections"] = res.get("connection_design")
    out["connection_items"] = res.get("connection_items")
    out["counts"] = res.get("counts")
    out["cfg_values"] = res.get("cfg_values")
    return out


def feedback(margins, ev_run, lm, log_fn=log, x_run=None):
    """Tighten the local margins of what a failed full run says failed (each margin at most once per run)."""
    hit = False
    done = set()

    def tighten(key, by=0.03, default=1.0):
        if key in done:
            return
        done.add(key)
        margins[key] = round(float(margins.get(key, default)) - by, 4)
        log_fn("    feedback: margin %s -> %.3f" % (key, margins[key]))

    sec2cl = {}
    if lm is not None:
        import peb_build as PB
        for c in lm.x0:
            for mid in lm.mem_of_const[c]:
                for t in lm.el_of_mem[mid]:
                    sec2cl[lm.dump[t]["member"]["section"]] = lm.cluster[c]
                    pe = lm.dump[t].get("peb") or {}
                    if x_run and c in x_run and pe.get("f"):
                        sec2cl[PB.section_at(x_run[c], 0.5 * (pe["f"][0] + pe["f"][1]))] = lm.cluster[c]
    for dc, kind, ident, _gov in ev_run.get("fail_items") or []:
        if kind == "member":
            sec = ident.split("-", 1)[1] if "-" in ident else ident
            cl = sec2cl.get(sec)
            if cl:
                tighten("member:" + "+".join(cl), default=float(margins.get("member", 0.99)))
                hit = True
        elif kind == "connection" and "6.2" in ident:
            tighten("is18168_6_2"); hit = True
        elif kind == "connection":
            if "knee" in ident:
                tighten("conn:knee"); hit = True
            elif "splice" in ident:
                for k in ("conn:splice:apex", "conn:splice:rafter_splice", "conn:splice:canopy_root"):
                    tighten(k, 0.02)
                hit = True
        elif kind == "section12":
            sid = ident.split("@")[0]
            if sid in ("connection_moment", "connection_shear", "12.11.2.3_panel_zone"):
                tighten("conn:knee"); hit = True
            elif sid.startswith("12.12") or sid.startswith("7.4"):
                tighten("conn:base"); hit = True
            elif sid in ("12.11.3.2_SCWB", "is18168_8_2_SCWB", "is18168_7_2_column_KL_r", "smf_column_class",
                         "is18168_table2_column"):
                for k in list(margins):
                    pass
                tighten("member", 0.02, 0.99); hit = True
        elif kind in ("sway", "drift"):
            tighten("sway", 0.03, 0.98); hit = True
        elif kind == "deflection":
            tighten("defl", 0.03, 0.98); hit = True
        elif kind == "stability":
            tighten("lambda", 0.03, 0.97); hit = True
    for g in ev_run.get("gates_fail") or []:
        if g.startswith(("wind_defl", "drift")):
            tighten("sway", 0.03, 0.98); hit = True
        elif g.startswith("beam_deflection"):
            tighten("defl", 0.03, 0.98); hit = True
        elif g.startswith("stability"):
            tighten("lambda", 0.03, 0.97); hit = True
    if not hit:
        tighten("member", 0.02, 0.99)
        tighten("sway", 0.02, 0.98)
    return margins


def read_constants(path, names):
    """Literal values of top-level assignments NAME = <literal> (and tuple assignments) in a job script."""
    tree = ast.parse(open(path, encoding="utf-8").read(), filename=path)
    out = {}
    for node in tree.body:
        if not isinstance(node, ast.Assign) or len(node.targets) != 1:
            continue
        tg = node.targets[0]
        try:
            if isinstance(tg, ast.Name) and tg.id in names:
                out[tg.id] = ast.literal_eval(node.value)
            elif isinstance(tg, ast.Tuple) and isinstance(node.value, ast.Tuple):
                for el, val in zip(tg.elts, node.value.elts):
                    if isinstance(el, ast.Name) and el.id in names:
                        out[el.id] = ast.literal_eval(val)
        except ValueError:
            pass
    miss = [n for n in names if n not in out]
    if miss:
        raise KeyError("%s: no literal top-level assignment for %s" % (path, miss))
    return out


def full_run(run_dir, spec, members, rules, *, conn=None, extra_overrides=None, cfg_patch=None, rods=None,
             conn_mass_basis=None, waivers=(), timeout=3600, log_fn=log, tag=""):
    """One full pipeline run (child process) of the members / connections / switches; returns evaluate_run()."""
    v = {"overrides": dict(members, **(extra_overrides or {})), "rules": dict(rules), "connections": conn,
         "conn_mass_basis": conn_mass_basis, "cfg_patch": cfg_patch or {}, "rods": rods or [],
         "job_spec": {"knee_column": spec.get("knee_column"), "splice_faces": spec.get("splice_faces") or {}}}
    json.dump(v, open(os.path.join(run_dir, "variant.json"), "w"), indent=1, default=str)
    for f in ("result.json",):
        p = os.path.join(run_dir, f)
        if os.path.exists(p):
            os.remove(p)
    if os.path.isdir(os.path.join(run_dir, "design")):
        shutil.rmtree(os.path.join(run_dir, "design"))
    rc, el = run_child([PY, os.path.abspath(__file__), "frame", run_dir], cwd=run_dir, timeout=timeout,
                       log_path=os.path.join(run_dir, "frame_child.log"))
    if not os.path.exists(os.path.join(run_dir, "result.json")):
        return {"ok_run": False, "passed": False, "exception": "child rc %s, no result.json (see frame_child.log)" % rc,
                "elapsed_s": el}
    r = evaluate_run(run_dir, waivers)
    r["elapsed_s"] = el
    g = r.get("governing")
    log_fn("    full run %s: %s in %.0f s; total %s kg; governing %s%s" % (
        tag, "PASS" if r.get("passed") else "FAIL", el, round(sum((r.get("tonnage_kg") or {}).values()), 0),
        ("%.3f %s %s" % (g[0], g[1], g[2])) if g else "-",
        "" if r.get("passed") else "; open: %s" % ("; ".join((r.get("blocking") or [str(r.get("exception"))[-300:]])[:3]))))
    return r


def _total(r):
    return round(sum((r.get("tonnage_kg") or {}).values()), 1)


def save_best(run_dir, dst):
    os.makedirs(dst, exist_ok=True)
    for f in ("variant.json", "result.json"):
        shutil.copy2(os.path.join(run_dir, f), os.path.join(dst, f))
    for f in ("calc_package.json", "bom.csv", "member_schedule.csv"):
        p = os.path.join(run_dir, "design", f)
        if os.path.exists(p):
            shutil.copy2(p, os.path.join(dst, f))
    for f in ("secondary_result.json", "peb_secondary.json"):
        p = os.path.join(run_dir, "secondary", f)
        if os.path.exists(p):
            shutil.copy2(p, os.path.join(dst, f))


def autosize(job_dir, spec, rules, work_dir, *, name, cfs_root, extra_overrides=None, cfg_patch=None, rods=None,
             Lr=None, free_flange=False, waivers=(), start=None, start_conn=None, calib=None, max_full_runs=8,
             resize_secondary=True, extra_pv=0.0, secondary_cache=None, log_fn=log):
    """Auto-size one variant of a PEB job.  Returns a record with the passing design of least mass ('best'), the
    history of full runs and the calibration of the connection take-off ('calib', reused by later variants)."""
    t0 = time.time()
    waivers = tuple(waivers or ()) + REPORT_ONLY_WAIVERS
    vdir = os.path.join(work_dir, name)
    run_dir = os.path.join(vdir, "run")
    if os.path.isdir(run_dir):
        shutil.rmtree(run_dir)
    prepare_run_dir(job_dir, run_dir)
    consts = sorted(spec["members"])
    x_gold = read_constants(os.path.join(job_dir, "cfg.py"), consts)
    out = {"variant": name, "rules": rules, "extra_overrides": extra_overrides, "cfg_patch": cfg_patch, "history": [],
           "x_gold": x_gold}
    log_fn("== %s / %s" % (spec["job"], name))
    if resize_secondary:
        skey = json.dumps([rules.get("purlins", "IS811_Fy240"), bool(rules.get("collateral_in_uplift")), Lr,
                           bool(free_flange), float(extra_pv or 0.0)])
        hit = (secondary_cache or {}).get(skey)
        if hit:
            for f, txt in hit["files"].items():
                open(os.path.join(run_dir, "secondary", f), "w").write(txt)
            out["secondary"] = hit["record"]
            log_fn("    secondary: reused (%s / %s)" % (hit["record"]["purlin"]["section"], hit["record"]["girt"]["section"]))
        else:
            out["secondary"] = design_secondary(run_dir, spec, rules, cfs_root=cfs_root, Lr=Lr,
                                                free_flange_braced=free_flange, extra_pv=extra_pv, log_fn=log_fn)
            if secondary_cache is not None:
                secondary_cache[skey] = {"record": out["secondary"], "files": {
                    f: open(os.path.join(run_dir, "secondary", f)).read()
                    for f in ("secondary_result.json", "peb_secondary.json")}}
    x_last = dict(start or x_gold)
    conn_run = start_conn
    margins = {"member": 1.0, "sway": 0.98, "defl": 0.98, "lambda": 0.98}
    best, lm = None, None
    groups = dim_groups(spec, x_last)
    for it in range(max_full_runs):
        if it > 0:
            lm = LocalModel(run_dir, spec, {"members": x_last}, rules)
            conn_prev = (json.load(open(os.path.join(run_dir, "result.json"))).get("connection_design") or {})
            ev = Evaluator(lm, spec, conn_prev, margins, x_gold)
            x_from = best["x"] if best else x_last
            tl = time.time()
            x_new, e = local_optimize(ev, x_from, groups, spec, log_fn=log_fn)
            log_fn("    local sizing: %d evaluations in %.0f s; %s; predicted mass %.0f kg (members %.0f + joints %.0f)%s"
                   % (ev.n_eval, time.time() - tl, "feasible" if e["feasible"] else "NOT feasible (%s)" % e.get("why"),
                      e.get("mass") or 0.0, e.get("member_kg") or 0.0, e.get("conn_kg") or 0.0,
                      "" if not e.get("conn_info") else "; joints %s" % json.dumps(e["conn_info"], default=str)[:400]))
            if not e["feasible"] and best is not None:
                log_fn("    stop: no feasible local proposal from the best design")
                break
            conn_new = e.get("conn") or conn_prev
            if best is not None and x_new == best["x"] and conn_new == best["conn"]:
                log_fn("    converged: the proposal is the best design")
                break
            x_run, conn_run = x_new, conn_new
        else:
            x_run = x_last
        R = full_run(run_dir, spec, x_run, rules, conn=conn_run, extra_overrides=extra_overrides, cfg_patch=cfg_patch,
                     rods=rods, conn_mass_basis=calib, waivers=waivers, log_fn=log_fn, tag="%s#%d" % (name, it))
        if not R.get("ok_run"):
            out["history"].append({"it": it, "x": x_run, "passed": False, "exception": R.get("exception")})
            log_fn("    run failed: %s" % str(R.get("exception"))[-1500:])
            break
        if it == 0 and calib is None:
            calib = {"gold_kg": float((R.get("cfg_values") or {}).get("peb_connection_mass_kg") or 0.0),
                     "items_kg": round(sum((R.get("connection_items") or {}).values()), 2),
                     "items": R.get("connection_items"), "counts": R.get("counts")}
        tot = _total(R)
        out["history"].append({"it": it, "x": x_run, "conn": R.get("design_connections"), "passed": R["passed"],
                               "total_kg": tot, "tonnage_kg": R.get("tonnage_kg"), "governing": R.get("governing"),
                               "blocking": (R.get("blocking") or [])[:12], "elapsed_s": R.get("elapsed_s"),
                               "margins": dict(margins)})
        if R["passed"]:
            if best is None or tot < best["total_kg"] - 0.5:
                best = {"x": dict(x_run), "conn": R.get("design_connections"), "total_kg": tot, "run": R, "it": it}
                save_best(run_dir, os.path.join(vdir, "best"))
            elif it > 0:
                log_fn("    passing but not lighter (%.0f >= %.0f kg): stop" % (tot, best["total_kg"]))
                break
        elif it > 0:
            feedback(margins, R, lm, log_fn=log_fn, x_run=x_run)   # the start design was not proposed by the sizer
        x_last = x_run
    out.update(best=best, calib=calib, elapsed_s=round(time.time() - t0, 1), n_full_runs=len(out["history"]))
    json.dump(out, open(os.path.join(vdir, "autosize.json"), "w"), indent=1, default=str)
    return out


if __name__ == "__main__":
    if len(sys.argv) >= 3 and sys.argv[1] == "frame":
        r = frame_worker(os.path.abspath(sys.argv[2]))
        sys.exit(0 if r.get("ok") else 1)
    print(__doc__)
