#!/usr/bin/env python3
"""peb_lever_infer.py -- PEB-LEVERS, third wave (2026-10): the lever study's job spec read from a PEB job's own cfg.py.

The study runner (scripts/peb_lever_study.py) needs a job spec for every job it sizes (scripts/peb_lever_jobs.py says
what each field means).  The four PEB golds have hand-written specs; any other PEB job written the way the golds are
(a Hub project, an engineer's own shed) gets one inferred here, so that it needs no hand-written spec:

  members         every top-level constant of cfg.py whose literal value is a welded (WI) or web-tapered (TI) label
                  and which the model uses; 'group' from the members the job's own build makes of it (column /
                  rafter; a canopy is a rafter), 'sfrs': False when every member of it is a gravity member (gable
                  posts and rafters, canopies)
  links           dimensions that meet at a joint of the main frame and are equal in cfg.py: the knee (the knee
                  column's top depth and the knee rafter's start depth) and every rafter splice (the depths of the
                  two sides)
  fab             the briefs' fabrication limits (D 200-1500, bf 120-400, tw >= 4 mm), widened to the job's own sizes
  knee_column     the main-frame column constant whose members carry the knee joint (the beam_column end plate)
  splice_faces    each named rafter_splice joint with an end plate ('apex', 'rafter_splice', 'canopy_root', ...): the
                  constant (and end) its end plate is designed from, matched by the plate's lever arm and web
  base_consts     the column constants whose column_base entry has a shear key
  frame_line      the middle main frame (NX // 2), else the middle line of the main-frame rafters
  base            the typical frame's column base: cfg['base'] when 'pinned' / 'fixed', else the knee column's
                  column_base entry ('fixed')
  dado_height_mm  DADO_H (m) when cfg['cladding_brittle']; else the lowest girt (girts start above the dado); none
                  without a brittle dado
  seismic         zone and I from cfg['seis'], the R constants (R_Y / R_X), the route from the transverse system
  Lr_const        the roof imposed-load constant (the literal whose value is cfg['Lr'])
  secondary       the job's secondary/*.py script with PURLIN / GIRT / FY, the collateral / PV loads, the purlin span
                  (the frame spacing SX)
  brace           the brace constant (BRACE), when the job has one

The job's model is built once (cfg['custom_build'], no analysis), as the engine builds it: the member roles come from
it.  When the build fails the stored package (design/calc_package.json) is read instead, and the reason is noted.
Anything not inferred is a reason the spec is refused (InferError), never a guess the study would run on silently;
every derived value is listed in the spec's '_notes'.

usage:  python scripts/peb_lever_infer.py <job folder> [--json]
        (in-process: infer_spec(job_dir) runs in a child process; _infer_here(job_dir) in this one)
"""
import ast
import json
import os
import re
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
ENGINE = os.path.join(ROOT, "steel_engine")

FAB_DEFAULT = {"D_min": 200.0, "D_max": 1500.0, "bf_min": 120.0, "bf_max": 400.0, "tw_min": 4.0}
_TI = re.compile(r"^TI(\d+(?:\.\d+)?)-(\d+(?:\.\d+)?)X(\d+(?:\.\d+)?)X(\d+(?:\.\d+)?)X(\d+(?:\.\d+)?)$")
_WI = re.compile(r"^WI(\d+(?:\.\d+)?)X(\d+(?:\.\d+)?)X(\d+(?:\.\d+)?)X(\d+(?:\.\d+)?)$")
INFER_TIMEOUT_S = 300


class InferError(ValueError):
    """The spec could not be inferred; .reasons lists why (plain text, for the engineer)."""

    def __init__(self, reasons):
        self.reasons = list(reasons)
        super().__init__("; ".join(self.reasons))


# ------------------------------------------------------------------------------------------------ labels
def parse(lab):
    """('tapered', D0, D1, bf, tf, tw) | ('welded', D, bf, tf, tw) | None."""
    s = str(lab or "")
    m = _TI.match(s)
    if m:
        return ("tapered",) + tuple(float(x) for x in m.groups())
    m = _WI.match(s)
    if m:
        return ("welded",) + tuple(float(x) for x in m.groups())
    return None


def depths(lab):
    """{'D0': .., 'D1': ..} of a tapered label, {'D': ..} of a welded one."""
    p = parse(lab)
    if not p:
        return {}
    return {"D0": p[1], "D1": p[2]} if p[0] == "tapered" else {"D": p[1]}


def end_depth(lab, end):
    """Depth at end 0 (start) or 1 (end) of a member label."""
    d = depths(lab)
    if "D" in d:
        return d["D"], "D"
    return (d["D0"], "D0") if end == 0 else (d["D1"], "D1")


def face_dims(lab, f):
    """(d, tf, tw, bf) of the section at fraction f of a tapered label (welded: its own)."""
    p = parse(lab)
    if not p:
        return None
    if p[0] == "tapered":
        D = p[1] + (p[2] - p[1]) * float(f)
        return D, p[4], p[5], p[3]
    return p[1], p[3], p[4], p[2]


def belongs(seg_label, const_label):
    """True when seg_label is the label itself or a stepped segment of the tapered const_label (same flanges and web,
    depth within the taper)."""
    if seg_label == const_label:
        return True
    a, b = parse(seg_label), parse(const_label)
    if not a or not b or a[0] != "welded" or b[0] != "tapered":
        return False
    D, bf, tf, tw = a[1:]
    D0, D1, bf2, tf2, tw2 = b[1:]
    return (abs(bf - bf2) < 1e-6 and abs(tf - tf2) < 1e-6 and abs(tw - tw2) < 1e-6
            and min(D0, D1) - 1e-6 <= D <= max(D0, D1) + 1e-6)


# ------------------------------------------------------------------------------------------------ cfg.py source
def literal_constants(path):
    """{NAME: literal value} of the top-level assignments NAME = <literal> (and NAME in A, B = x, y) of a script,
    in source order (a later assignment of the same name wins)."""
    tree = ast.parse(open(path, encoding="utf-8").read(), filename=path)
    out = {}
    for node in tree.body:
        if not isinstance(node, ast.Assign) or len(node.targets) != 1:
            continue
        tg = node.targets[0]
        pairs = []
        if isinstance(tg, ast.Name):
            pairs = [(tg.id, node.value)]
        elif isinstance(tg, ast.Tuple) and isinstance(node.value, ast.Tuple) and len(tg.elts) == len(node.value.elts):
            pairs = [(el.id, v) for el, v in zip(tg.elts, node.value.elts) if isinstance(el, ast.Name)]
        for name, val in pairs:
            try:
                out[name] = ast.literal_eval(val)
            except (ValueError, TypeError, SyntaxError, MemoryError, RecursionError):
                out.pop(name, None)            # re-assigned to an expression: not a literal any more
    return out


# ------------------------------------------------------------------------------------------------ the model
def _model(job_dir, notes):
    """(ns, cfg, peb) of the job: cfg.py executed, its model built once (cfg['custom_build'], no analysis) for the
    PEB registry (members, chains, splices, gravity elements); the stored package when the build fails."""
    sys.path[:0] = [p for p in (ENGINE,) if p not in sys.path]
    import peb_autosize as A
    cwd = os.getcwd()
    os.chdir(job_dir)
    try:
        mod = A.exec_with_overrides(os.path.join(job_dir, "cfg.py"), {})
    finally:
        os.chdir(cwd)
    ns = mod.__dict__
    cfg = ns.get("cfg")
    if not isinstance(cfg, dict):
        raise InferError(["cfg.py defines no cfg dict"])
    peb = None
    if callable(cfg.get("custom_build")):
        try:
            os.chdir(job_dir)
            info = cfg["custom_build"](cfg)
            if isinstance(info, (tuple, list)):
                info = info[-1]
            peb = (info or {}).get("peb") if isinstance(info, dict) else None
        except Exception as e:                       # noqa: BLE001 -- reported, then the stored package is read
            notes.append("the model could not be built (%s: %s); member roles read from the stored package"
                         % (type(e).__name__, str(e)[:160]))
        finally:
            os.chdir(cwd)
    if not peb:
        p = os.path.join(job_dir, "design", "calc_package.json")
        if os.path.exists(p):
            peb = (json.load(open(p, encoding="utf-8")).get("peb") or {}) or None
            if peb:
                peb = dict(peb, gravity=None)
    if not peb or not peb.get("members"):
        raise InferError(["no PEB members: cfg.py builds no PEB model (peb_build) and there is no stored package -- "
                          "the lever study re-sizes PEB sheds with welded / tapered portal frames"])
    return ns, cfg, peb


def _in_moment_frame(m, peb, gable_lines):
    """True when member m is part of a moment frame: a column rigid at its top (its chain not released 'J' / 'both'),
    a rafter that is not a gravity member (gable lines, canopies)."""
    ch = (peb.get("chains") or {}).get(m.get("chain")) or {}
    if m.get("kind") == "column":
        return ch.get("releases") not in ("J", "both")
    if m.get("kind") == "canopy":
        return False
    grav = peb.get("gravity")
    els = [int(t) for t in m.get("elements") or []]
    if grav is not None and els:
        return not all(t in grav for t in els)
    line = m.get("line")                              # stored package (no gravity set): a gable line is gravity
    q = line[0] if isinstance(line, (list, tuple)) else line
    return q not in gable_lines


# ------------------------------------------------------------------------------------------------ the spec
def _infer_here(job_dir):
    """The job spec of a PEB job folder, inferred in this process (see the module docstring).  Returns the spec with
    '_notes' (what was derived and how) and '_source' = 'inferred from cfg.py'.  Raises InferError."""
    job_dir = os.path.abspath(job_dir)
    cfg_path = os.path.join(job_dir, "cfg.py")
    if not os.path.isfile(cfg_path):
        raise InferError(["no cfg.py in the job folder"])
    notes, why = [], []
    lit = literal_constants(cfg_path)
    ns, cfg, peb = _model(job_dir, notes)
    members = peb.get("members") or {}
    gable_lines = set(ns.get("GABLE") or ()) if isinstance(ns.get("GABLE"), (tuple, list, set, range)) else set()

    # -- members: literal WI / TI constants the model uses
    by_label = {}
    for mid, m in members.items():
        by_label.setdefault(m.get("section"), []).append(m)
    consts = {}
    lat_bases = [k for k in ((cfg.get("connections") or {}).get("column_base") or {})]
    for name, val in lit.items():
        if not (isinstance(val, str) and parse(val)) or not name.isupper() or ns.get(name) != val:
            continue
        ms = by_label.get(val) or []
        if not ms:
            continue
        mf = [m for m in ms if _in_moment_frame(m, peb, gable_lines)]
        kinds = {m.get("kind") for m in (mf or ms)}
        if mf and {m.get("kind") for m in ms} != kinds:
            notes.append("%s (%s): its role taken from the main-frame members (the label is also used by %s members)"
                         % (name, val, " / ".join(sorted({str(m.get("kind")) for m in ms} - kinds))))
        if kinds <= {"column"}:
            group = "column"
        elif kinds <= {"rafter", "canopy"}:
            group = "rafter"
        else:
            why.append("%s (%s) is used as %s: a constant must be one member role" % (name, val, " and ".join(sorted(
                str(k) for k in kinds))))
            continue
        sfrs = any(_in_moment_frame(m, peb, gable_lines) for m in ms)
        if group == "column" and not sfrs and any(str(k).split(":", 1)[0] == "lateral_col" and
                                                  belongs(str(k).split(":", 1)[-1], val) for k in lat_bases):
            notes.append("%s (%s) is a braced-frame column (pinned at its top, a lateral column base): kept at its size "
                         "-- the sizer has no brace capacity-design forces for it" % (name, val))
            continue
        consts[name] = {"label": val, "group": group, "sfrs": sfrs, "members": ms}
    labs = {}
    for c, d in consts.items():
        if d["label"] in labs:
            why.append("constants %s and %s are both %s: the sizer maps members back to constants by their label, so "
                       "give them different sizes or one constant" % (labs[d["label"]], c, d["label"]))
        labs[d["label"]] = c
    if not any(d["sfrs"] and d["group"] == "column" for d in consts.values()) or \
            not any(d["sfrs"] and d["group"] == "rafter" for d in consts.values()):
        why.append("no welded / tapered main-frame column and rafter given as top-level constants of cfg.py (e.g. "
                   "COL = \"WI600X250X14X8\"): the sizer resizes those constants")
    spec_members = {}
    for c in sorted(consts):
        d = consts[c]
        spec_members[c] = {"group": d["group"]} if d["sfrs"] else {"group": d["group"], "sfrs": False}
    conn = cfg.get("connections") or {}

    # -- the knee: the main-frame column under the beam_column end plate, and the rafter at its face
    main_cols = [c for c, d in consts.items() if d["sfrs"] and d["group"] == "column"]
    main_rafs = [c for c, d in consts.items() if d["sfrs"] and d["group"] == "rafter"]
    raf_nodes = {}
    for c in main_rafs:
        for m in consts[c]["members"]:
            for n in (m.get("node_start"), m.get("node_end")):
                raf_nodes.setdefault(n, set()).add(c)
    knee_col, knee_raf = None, None
    cand = []
    for c in main_cols:
        top = [m.get("node_end") for m in consts[c]["members"]]
        hits = [n for n in top if n in raf_nodes]
        if hits:
            cand.append((len(hits), c, sorted({r for n in hits for r in raf_nodes[n]})))
    if cand:
        cand.sort(key=lambda t: (-t[0], t[1]))
        knee_col = cand[0][1]
        # the knee rafter: the one whose start depth matches the beam_column face (the knee end plate's section)
        bc = conn.get("beam_column") or {}
        face = next((k for k, v in bc.items() if isinstance(v, dict) and v.get("end_plate")), None)
        rafs = cand[0][2]
        knee_raf = next((r for r in rafs if face and belongs(face, consts[r]["label"])), rafs[0] if len(rafs) == 1 else None)
    elif main_cols:
        knee_col = sorted(main_cols, key=lambda c: (-len(consts[c]["members"]), c))[0]
        notes.append("knee column %s: the main-frame column with most members (no column top met a rafter)" % knee_col)
    if not knee_col:
        why.append("no main-frame column constant found for the knee")

    # -- links: equal depths that meet at the knee and at the rafter splices of the main frame
    links = []

    def tie(a, b):
        for L in links:
            if a in L or b in L:
                for x in (a, b):
                    if x not in L:
                        L.append(x)
                return
        links.append([a, b])

    if knee_col and knee_raf:
        dc, nc = end_depth(consts[knee_col]["label"], 1)
        dr, nr = end_depth(consts[knee_raf]["label"], 0)
        if abs(dc - dr) < 1e-6:
            tie("%s.%s" % (knee_col, nc), "%s.%s" % (knee_raf, nr))
    for nd, sp in sorted((peb.get("splices") or {}).items(), key=lambda kv: str(kv[0])):
        if sp.get("gravity"):
            continue
        sl, sr = sp.get("sec_left"), sp.get("sec_right")
        cl = next((c for c in main_rafs if belongs(sl, consts[c]["label"])), None)
        cr = next((c for c in main_rafs if belongs(sr, consts[c]["label"])), None)
        if not cl or not cr or cl == cr:
            continue
        a, b = parse(sl), parse(sr)
        if a and b and abs(a[1] - b[1]) < 1e-6:
            # the end of each side at the joint: a tapered member's end whose depth is the face depth
            ends = []
            for c, face in ((cl, a), (cr, b)):
                d = depths(consts[c]["label"])
                ends.append(next(("%s.%s" % (c, k) for k in ("D", "D1", "D0") if k in d and abs(d[k] - face[1]) < 1e-6),
                                 None))
            if all(ends):
                tie(*ends)
    links = [sorted(L, key=lambda s: (s.split(".")[0] not in (knee_col,), s)) for L in links]
    links = [L for L in links if len(L) > 1]

    # -- fabrication limits: the briefs', widened to the job's own sizes
    fab = dict(FAB_DEFAULT)
    for c, d in consts.items():
        p = parse(d["label"])
        Ds = [p[1], p[2]] if p[0] == "tapered" else [p[1]]
        bf, tw = (p[3], p[5]) if p[0] == "tapered" else (p[2], p[4])
        if min(Ds) < fab["D_min"] or max(Ds) > fab["D_max"] or bf < fab["bf_min"] or bf > fab["bf_max"] or \
                tw < fab["tw_min"]:
            fab.update(D_min=min(fab["D_min"], min(Ds)), D_max=max(fab["D_max"], max(Ds)),
                       bf_min=min(fab["bf_min"], bf), bf_max=max(fab["bf_max"], bf), tw_min=min(fab["tw_min"], tw))
            notes.append("fabrication limits widened to %s's own size %s" % (c, d["label"]))

    # -- splice faces: each named rafter_splice joint with an end plate, by the plate's lever arm and web
    faces = {}
    for key, js in (conn.get("rafter_splice") or {}).items():
        ep = (js or {}).get("end_plate") if isinstance(js, dict) else None
        if not isinstance(ep, dict) or not ep.get("rows") or parse(key) or key in labs:
            continue                                 # a joint keyed by its section label follows the label itself
        hf, tw = float(ep.get("hf_mm") or 0.0), float(ep.get("web_t_mm") or 0.0)
        hit = []
        for c in sorted(consts, key=lambda c: (not consts[c]["sfrs"], c)):
            for f in ((0.0, 1.0) if parse(consts[c]["label"])[0] == "tapered" else (None,)):
                d, tf, tw_, bf = face_dims(consts[c]["label"], f or 0.0)
                # the plate's lever arm is the face's d - tf; its web may carry a doubler (web_t >= the member's)
                if abs((d - tf) - hf) < 0.51 and tw >= tw_ - 1e-6:
                    hit.append((abs(tw - tw_) > 1e-6, c, f))
        hit = [(c, f) for _x, c, f in sorted(hit, key=lambda h: h[0])]
        if not hit:
            why.append("rafter_splice '%s': no member constant matches its end plate (lever arm %.0f mm, web %.0f mm)"
                       % (key, hf, tw))
            continue
        c, f = hit[0]
        faces[key] = [c, (1.0 if key == "apex" else 0.0) if f is None else f]
        if len({h[0] for h in hit}) > 1:
            notes.append("rafter_splice '%s': end plate matches %s; %s taken" % (key, ", ".join(sorted({h[0] for h in hit})), c))

    # -- shear-keyed bases
    base_consts, base_fixed = [], {}
    for key, b in (conn.get("column_base") or {}).items():
        if not isinstance(b, dict):
            continue
        lab = str(key).split(":", 1)[-1]
        c = next((c for c in sorted(consts) if consts[c]["group"] == "column" and belongs(lab, consts[c]["label"])), None)
        if c:
            base_fixed.setdefault(c, bool(b.get("fixed")))
            if b.get("shear_key") and c not in base_consts:
                base_consts.append(c)

    # -- the typical frame, its base
    main_lines = sorted({(m.get("line")[0] if isinstance(m.get("line"), (list, tuple)) else m.get("line"))
                         for c in main_rafs for m in consts[c]["members"]} - {None})
    NX = ns.get("NX") if isinstance(ns.get("NX"), int) else None
    frame_line = NX // 2 if NX and (NX // 2) in main_lines else (main_lines[len(main_lines) // 2] if main_lines else 1)
    if not (NX and (NX // 2) in main_lines):
        notes.append("typical frame line %s: the middle main-frame line" % frame_line)
    base = str(cfg.get("base") or "")
    if base not in ("pinned", "fixed"):
        if knee_col in base_fixed:
            base = "fixed" if base_fixed[knee_col] else "pinned"
            notes.append("frame base %s: cfg['base'] is %r; the knee column's base entry is %s"
                         % (base, cfg.get("base"), "fixed" if base_fixed[knee_col] else "pinned"))
        else:
            why.append("the typical frame's column base (pinned / fixed) is not stated: cfg['base'] is %r and the "
                       "knee column has no column_base entry" % cfg.get("base"))

    # -- dado
    dado = None
    if cfg.get("cladding_brittle"):
        if isinstance(lit.get("DADO_H"), (int, float)):
            dado = float(lit["DADO_H"]) * 1000.0
        elif isinstance(ns.get("GIRTS"), (list, tuple)) and ns["GIRTS"]:
            dado = float(min(ns["GIRTS"]))
            notes.append("brick dado %.0f mm high: the lowest girt (no DADO_H constant; girts start above the dado)"
                         % dado)
        else:
            why.append("cfg['cladding_brittle'] is set but the dado height is not given (DADO_H in m)")

    # -- seismic
    seis = cfg.get("seis") or {}
    R_consts = {}
    for name, val in lit.items():
        m = re.match(r"^R_?([XY])$", name)
        if m and isinstance(val, (int, float)):
            R_consts[name] = m.group(1).lower()
    if not R_consts:
        why.append("no R constants (R_Y / R_X) in cfg.py")
    sys_y = str(cfg.get("system_y") or cfg.get("system") or "")
    route = "OMRF" if sys_y.upper().startswith("OMRF") else ("SMRF_IS18168" if re.search(r"\bS(MR)?MF|SMRF", sys_y.upper())
                                                             else None)
    if route is None:
        why.append("transverse system %r is neither an ordinary nor a special moment frame" % sys_y)
    if seis.get("zone") is None:
        why.append("no seismic zone (cfg['seis']['zone'])")

    # -- roof imposed load, secondary design, brace
    Lr_const = next((n for n in lit if re.match(r"^L_?R(_.*)?$", n) and isinstance(lit[n], (int, float))
                     and cfg.get("Lr") is not None and abs(float(lit[n]) - float(cfg["Lr"])) < 1e-9), None)
    if not Lr_const:
        why.append("no roof imposed-load constant (LR = cfg['Lr'])")
    sec = None
    sd = os.path.join(job_dir, "secondary")
    for f in sorted(os.listdir(sd)) if os.path.isdir(sd) else []:
        if not f.endswith(".py"):
            continue
        try:
            names = {n.id for node in ast.parse(open(os.path.join(sd, f), encoding="utf-8").read()).body
                     if isinstance(node, ast.Assign) for t in node.targets for n in ([t] if isinstance(t, ast.Name) else
                                                                                     getattr(t, "elts", []))
                     if isinstance(n, ast.Name)}
        except SyntaxError:
            continue
        if {"PURLIN", "GIRT", "FY"} <= names:
            sec = "secondary/" + f
            break
    span = ns.get("SX") if isinstance(ns.get("SX"), (int, float)) else cfg.get("SX")
    if not sec:
        why.append("no secondary design script (secondary/*.py with PURLIN, GIRT and FY, run with the CFS engine)")
    if not isinstance(span, (int, float)):
        why.append("no frame spacing (SX) for the purlin span")
    npd = {"collateral": float(cfg.get("D_roof_collateral") or 0.0)}
    if float(cfg.get("D_roof_pv") or 0.0) > 0.0:
        npd["pv"] = float(cfg["D_roof_pv"])
    brace = "BRACE" if isinstance(lit.get("BRACE"), str) else None
    if not brace:
        notes.append("no BRACE constant: the tension-rod lever and the OCBF brace re-sizing are not available")

    if why:
        raise InferError(why)
    spec = {
        "job": os.path.basename(job_dir.rstrip(os.sep)),
        "members": spec_members,
        "links": links,
        "fab": fab,
        "knee_column": knee_col,
        "splice_faces": faces,
        "base_consts": base_consts,
        "frame_line": int(frame_line), "base": base, "dado_height_mm": dado,
        "seismic": {"zone": str(seis["zone"]), "I": float(seis.get("I") or 1.0), "R_consts": R_consts, "route": route},
        "Lr_const": Lr_const,
        "secondary": {"script": sec, "consts": {"purlin": "PURLIN", "girt": "GIRT", "fy": "FY"},
                      "nonpermanent": npd, "span_mm": float(span)},
        "_source": "inferred from cfg.py",
        "_notes": notes,
    }
    if brace:
        spec["brace"] = {"const": brace}
    return spec


def infer_spec(job_dir, python=None, timeout=INFER_TIMEOUT_S):
    """The inferred spec of a PEB job folder, worked out in a child process (cfg.py is executed and its model built:
    the study's own process keeps no engine state from it).  Raises InferError."""
    r = subprocess.run([python or sys.executable, "-I", os.path.abspath(__file__), os.path.abspath(job_dir), "--json"],
                       capture_output=True, text=True, timeout=timeout,
                       env=dict(os.environ, PYTHONHASHSEED="0", PYTHONDONTWRITEBYTECODE="1", MPLBACKEND="Agg"))
    out = None
    for line in reversed((r.stdout or "").strip().splitlines()):      # the engine may print after the answer
        try:
            out = json.loads(line)
        except ValueError:
            continue
        if isinstance(out, dict) and ("spec" in out or "error" in out):
            break
        out = None
    if not isinstance(out, dict):
        raise InferError(["the job's cfg.py could not be read (%s)" % (((r.stderr or "").strip().splitlines() or
                                                                         ["exit code %s" % r.returncode])[-1][:300])])
    if out.get("error"):
        raise InferError(out["error"])
    return out["spec"]


def main(argv=None):
    import argparse
    ap = argparse.ArgumentParser(description="the PEB lever study's job spec, inferred from a PEB job's cfg.py")
    ap.add_argument("job_dir")
    ap.add_argument("--json", action="store_true", help="one JSON line: {'spec': ...} or {'error': [reasons]}")
    a = ap.parse_args(argv)
    import contextlib
    import io
    buf = io.StringIO()
    try:
        with contextlib.redirect_stdout(buf):            # a job script's own prints stay out of the answer
            spec = _infer_here(a.job_dir)
        out = {"spec": spec}
    except InferError as e:
        out = {"error": e.reasons}
    except Exception as e:                               # noqa: BLE001 -- a job script that fails to run
        out = {"error": ["cfg.py failed to run: %s: %s" % (type(e).__name__, str(e)[:300])]}
    if a.json:
        print(json.dumps(out, default=str))
    else:
        print(json.dumps(out, indent=1, default=str))
    return 0 if "spec" in out else 2


if __name__ == "__main__":
    sys.exit(main())
