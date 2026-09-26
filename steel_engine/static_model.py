"""
static_model.py -- the STATIC building model (the second model).

The dynamic model (engine3d.build) LUMPS each floor's gravity at the joints -- correct for mass /
period / seismic base shear, but the beam ELEMENTS then carry ~0 gravity force, so internal force
diagrams cannot be drawn from it. This static model instead DISTRIBUTES the floor pressures onto the
beams as their true two-way (45-degree) tributary line loads -- triangular on the short bay edge,
trapezoidal on the long edge -- by sub-dividing every beam into `nseg` sub-elements with real
intermediate nodes and applying the exact stepped load. Every India load_plan combination is then
analysed statically with P-Delta, so N / V / M are correct everywhere for the force diagrams and the
gravity member demands. The dynamic model is untouched.

Geometry, sections, orientation, base fixity, diaphragm, per-member releases and the lateral story
forces are all replicated from engine3d so the two models are the same structure.
"""
import math
import openseespy.opensees as ops
import engine3d as eng
from engine3d import ntag, mtag, grid, zlevels, Ipack

EMOD = eng.E
GMOD = eng.Gmod

_SUB0 = 9_000_000          # base tag for intermediate beam nodes / sub-elements


def export_static_model(cfg, outdir, name="model", nseg=6):
    """Write a STANDALONE, runnable STATIC model (model_static.py) -- the SECOND model used for the force
    diagrams (beams sub-divided with the true two-way tributary gravity). Replays the exact OpenSees calls
    build_static issues, mirroring engine3d.export_model, so the user can open BOTH models independently."""
    import os as _os
    rec = []
    funcs = ["wipe", "model", "node", "fix", "mass", "geomTransf", "uniaxialMaterial", "element",
             "rigidDiaphragm", "equalDOF", "rigidLink"]
    orig = {f: getattr(ops, f) for f in funcs if hasattr(ops, f)}
    def _shim(fn, real):
        def w(*a):
            rec.append((fn, list(a))); return real(*a)
        return w
    for f, real in orig.items():
        setattr(ops, f, _shim(f, real))
    try:
        build_static(cfg, "PDelta", nseg)
    finally:
        for f, real in orig.items():
            setattr(ops, f, real)
    _os.makedirs(outdir, exist_ok=True)
    arch = str(cfg.get("arch", ""))
    py = ['"""Standalone STATIC building model for %s -- %s.' % (name, arch),
          'The SECOND (force-diagram) model: beams sub-divided into sub-elements carrying the true two-way',
          'tributary gravity, so internal N / V / M are correct everywhere. Auto-generated; replays the exact',
          'build_static OpenSees calls.  Run:  python model_static.py"""',
          'import openseespy.opensees as ops', '']
    _gt_seen = set()
    for cmd, a in rec:
        if cmd == "geomTransf" and len(a) >= 2:
            if a[1] in _gt_seen:
                continue
            _gt_seen.add(a[1])
        py.append("ops.%s(%s)" % (cmd, ", ".join(repr(x) for x in a)))
    py += ['', '# --- quick self-check ---',
           'print("static model -- nodes:", len(ops.getNodeTags()), " elements:", len(ops.getEleTags()))']
    pyp = _os.path.join(outdir, "model_static.py")
    open(pyp, "w").write("\n".join(py) + "\n")
    return [pyp]


def _XY(cfg, i, j):
    SX, SY = cfg["SX"], cfg["SY"]
    xco = cfg.get("xcoords"); yco = cfg.get("ycoords"); skew = cfg.get("skew", 0.0)
    return ((xco[i] if xco else i*SX) + skew*j, (yco[j] if yco else j*SY))


def _rel_parts(code):
    """Split a per-member release code into its I-end and J-end pieces."""
    rel_i = "I" if code in ("I", "both") else "none"
    rel_j = "J" if code in ("J", "both") else "none"
    return rel_i, rel_j



def _parse_rel(rel):
    """['-releasez',3,'-releasey',1] -> (relz_code, rely_code) as none/I/J/both."""
    cm = {0: "none", 1: "I", 2: "J", 3: "both"}; rz = ry = "none"; i = 0
    rel = list(rel)
    while i < len(rel):
        if rel[i] == "-releasey" and i+1 < len(rel): rz = cm.get(rel[i+1], "none"); i += 2   # -releasey = MAJOR = relz
        elif rel[i] == "-releasez" and i+1 < len(rel): ry = cm.get(rel[i+1], "none"); i += 2  # -releasez = minor = rely
        else: i += 1
    return rz, ry


def _end_rel(relz, rely, end):
    if end == "I":
        return ("I" if relz in ("I", "both") else "none", "I" if rely in ("I", "both") else "none")
    return ("J" if relz in ("J", "both") else "none", "J" if rely in ("J", "both") else "none")


def grid_ijk_from_coords(cfg, x, y, z, dirn, tol=1.0):
    """(i, j, k) of the column-grid bay a beam piece lies in, from its coordinates -- for beams whose I-node is
    NOT a column-grid node (EBF link / beam-outside-link pieces, brace work points at the link ends, WP6).
    i (X beam) is the grid line at or just below min x; j is the grid line at y (nearest); k from z."""
    NX, NY = cfg["NX"], cfg["NY"]
    xs = [_XY(cfg, i, 0)[0] for i in range(NX + 1)]
    ys = [_XY(cfg, 0, j)[1] for j in range(NY + 1)]
    zs = zlevels(cfg)
    k = min(range(len(zs)), key=lambda kk: abs(zs[kk] - z))
    if dirn == "X":
        i = max([ii for ii in range(NX + 1) if xs[ii] <= x + tol] or [0])
        i = min(i, NX - 1)
        j = min(range(NY + 1), key=lambda jj: abs(ys[jj] - y))
    else:
        j = max([jj for jj in range(NY + 1) if ys[jj] <= y + tol] or [0])
        j = min(j, NY - 1)
        i = min(range(NX + 1), key=lambda ii: abs(xs[ii] - x))
    return i, j, k


def _staticize_custom(cfg, transf="PDelta", nseg=10):
    """Distribute gravity over an AGENT-BUILT (custom_build) model. We RECORD every OpenSees call the
    custom_build makes, then REPLAY it with the beams sub-divided into `nseg` elements so the true
    two-way tributary line loads produce correct internal-force diagrams -- the same treatment the
    parametric model gets. Relies on the custom_build conventions (ntag/mtag, beams on transf 3,
    release_args, returns the info dict with per-element kind+section)."""
    rec = {k: [] for k in ("node", "fix", "geomTransf", "element", "rigidDiaphragm", "mass", "uniaxialMaterial")}
    real = {k: getattr(ops, k) for k in rec}
    def mk(name):
        def f(*a):
            rec[name].append(a); return real[name](*a)
        return f
    for k in rec: setattr(ops, k, mk(k))
    try:
        info = cfg["custom_build"](cfg, transf)
    finally:
        for k in rec: setattr(ops, k, real[k])

    ops.wipe(); ops.model("basic", "-ndm", 3, "-ndf", 6)
    coord = {}
    for a in rec["node"]: ops.node(*a); coord[a[0]] = (a[1], a[2], a[3])
    for a in rec["fix"]: ops.fix(*a)
    _gt_seen = set()                       # a custom_build may register the SAME transf tag twice
    for a in rec["geomTransf"]:            # (explicit register_col_transf + add_*/_ensure auto-register);
        if a[1] in _gt_seen: continue      # the live build swallows the dup, but replay must not re-add it
        _gt_seen.add(a[1]); ops.geomTransf(*a)
    for a in rec["uniaxialMaterial"]: ops.uniaxialMaterial(*a)

    def dec(t): r = t % 100000; return r // 100, r % 100, t // 100000
    einfos = info.get("ele", [])
    sub_node = _SUB0; sub_ele = _SUB0; beams = []; cols = []; braces = []; dia_extra = {}
    for idx, a in enumerate(rec["element"]):
        kind = einfos[idx][1] if idx < len(einfos) else None
        sec = einfos[idx][2] if idx < len(einfos) else None
        if a[0] in ("elasticBeamColumn", "ElasticTimoshenkoBeam") and kind == "beam":
            n1, n2 = a[2], a[3]
            if a[0] == "ElasticTimoshenkoBeam":
                # EBF shear link (WP6): E, G, A, Jx, Iy, Iz, Avy, Avz, transf -- shear deformation kept, no releases
                props = a[4:12]; ttag = a[12]; relz, rely = "none", "none"
            else:
                props = a[4:10]; ttag = a[10]; relz, rely = _parse_rel(a[11:])
            (x1, y1, z1) = coord[n1]; (x2, y2, z2) = coord[n2]
            L = ((x2-x1)**2 + (y2-y1)**2 + (z2-z1)**2) ** 0.5
            chain = [n1]
            for sgi in range(1, nseg):
                t = sgi/float(nseg); nd = sub_node; sub_node += 1
                ops.node(nd, x1+(x2-x1)*t, y1+(y2-y1)*t, z1+(z2-z1)*t)
                dia_extra.setdefault(round(z1, 6), []).append(nd); chain.append(nd)
            chain.append(n2); segs = []
            for sgi in range(nseg):
                ra = []
                if sgi == 0: ra += eng.release_args(*_end_rel(relz, rely, "I"))
                if sgi == nseg-1: ra += eng.release_args(*_end_rel(relz, rely, "J"))
                te = sub_ele; sub_ele += 1
                ops.element(a[0], te, chain[sgi], chain[sgi+1], *props, ttag, *ra); segs.append(te)
            i, j, k = dec(n1); dirn = "X" if abs(x2-x1) >= abs(y2-y1) else "Y"
            if not (0 <= i <= cfg["NX"] and 0 <= j <= cfg["NY"] and n1 == ntag(i, j, k)):
                # beam piece starting at an off-grid work point (EBF link ends): locate its bay from the
                # coordinates so it carries its share of the floor load like any other beam (WP6)
                i, j, k = grid_ijk_from_coords(cfg, min(x1, x2), min(y1, y2), z1, dirn)
            beams.append({"i": i, "j": j, "k": k, "dir": dirn, "L": L, "A": n1, "B": n2,
                          "nodes": chain, "segs": segs, "sec": sec, "relz": relz, "rely": rely})
        else:
            ops.element(*a)
            if kind == "col":
                i, j, k = dec(a[2]); cols.append({"tag": a[1], "sec": sec, "n1": a[2], "n2": a[3],
                                                  "i": i, "j": j, "k": k, "axis": "col",
                                                  "transf": (a[10] if a[0] == "elasticBeamColumn" and len(a) > 10 else None)})
            elif kind == "brace":
                braces.append({"tag": a[1], "sec": sec, "n1": a[2], "n2": a[3]})
    for a in rec["rigidDiaphragm"]:
        master = a[1]; slaves = list(a[2:])
        mz = round(coord[master][2], 6) if master in coord else None
        ops.rigidDiaphragm(a[0], master, *(slaves + dia_extra.get(mz, [])))

    NF = len(cfg["heights"]); NX, NY = cfg["NX"], cfg["NY"]; present = {}
    for t, (x, y, zz) in coord.items():
        i, j, k = dec(t)
        if 0 <= i <= NX and 0 <= j <= NY: present.setdefault(k, set()).add((i, j))
    for k in range(NF+1): present.setdefault(k, set())
    bases = {}
    for a in rec["fix"]:
        if len(a) >= 7:
            i, j, k = dec(a[0])
            if k == 0 and 0 <= i <= NX and 0 <= j <= NY:
                bases[(i, j)] = "fixed" if a[4] == 1 else "pinned"   # a[4] = rotational restraint rx
    return {"cm": info.get("cm", {}), "present": present, "z": zlevels(cfg), "NF": NF,
            "cols": cols, "beams": beams, "braces": braces, "bases": bases}

def build_static(cfg, transf="PDelta", nseg=10):
    """Build the static model. Beams are sub-divided into `nseg` sub-elements with real intermediate
    nodes; columns and braces stay single elements. Returns a dict describing the model so loads can
    be applied and per-member diagrams reassembled."""
    if cfg.get("custom_build"):
        return _staticize_custom(cfg, transf, nseg)
    ops.wipe(); ops.model("basic", "-ndm", 3, "-ndf", 6)
    NX, NY = cfg["NX"], cfg["NY"]; SX, SY = cfg["SX"], cfg["SY"]
    z = zlevels(cfg); NF = len(cfg["heights"])
    present = {k: grid(cfg, k) for k in range(NF+1)}

    # primary (column-line) nodes
    for k in range(NF+1):
        for (i, j) in present[k]:
            x, y = _XY(cfg, i, j); ops.node(ntag(i, j, k), x, y, z[k])
    base = cfg.get("base", "fixed")
    for (i, j) in present[0]:
        if base == "pinned": ops.fix(ntag(i, j, 0), 1, 1, 1, 0, 0, 0)
        else:                ops.fix(ntag(i, j, 0), 1, 1, 1, 1, 1, 1)

    # diaphragm masters
    cm = {}
    for k in range(1, NF+1):
        pts = present[k]
        cx = sum(_XY(cfg, i, j)[0] for i, j in pts)/len(pts)
        cy = sum(_XY(cfg, i, j)[1] for i, j in pts)/len(pts)
        cm[k] = (cx, cy); ops.node(mtag(k), cx, cy, z[k]); ops.fix(mtag(k), 0, 0, 1, 1, 1, 0)

    cT = "PDelta" if transf == "PDelta" else "Linear"
    ops.geomTransf(cT, 1, 1.0, 0.0, 0.0); ops.geomTransf(cT, 2, 0.0, 1.0, 0.0)
    ops.geomTransf("Linear", 3, 0.0, 0.0, 1.0)
    cA, cIx, cIy, cJ = Ipack(cfg["col"]); bA, bIx, bIy, bJ = Ipack(cfg["beam"])
    relf = cfg.get("releases")

    et = 1; cols = []; beams = []
    sub_node = _SUB0; sub_ele = _SUB0
    dia_extra = {k: [] for k in range(1, NF+1)}   # interior beam nodes to add to each diaphragm

    # columns (single elements, exactly as the dynamic model)
    for i in range(NX+1):
        for j in range(NY+1):
            tt = 2 if (i == 0 or i == NX) else 1
            for k in range(NF):
                if (i, j) in present[k] and (i, j) in present[k+1]:
                    ops.element("elasticBeamColumn", et, ntag(i, j, k), ntag(i, j, k+1),
                                cA, eng.E, eng.Gmod, cJ, cIy, cIx, tt)
                    cols.append({"tag": et, "sec": cfg["col"], "n1": ntag(i, j, k), "n2": ntag(i, j, k+1),
                                 "i": i, "j": j, "k": k, "axis": "col"})
                    et += 1

    def _add_beam(i, j, k, dirn, A, B):
        nonlocal et, sub_node, sub_ele
        xa, ya = ops.nodeCoord(A)[0], ops.nodeCoord(A)[1]
        xb, yb = ops.nodeCoord(B)[0], ops.nodeCoord(B)[1]
        zk = z[k]; L = math.hypot(xb-xa, yb-ya)
        relz, rely = (relf(i, j, k, dirn) if relf else ("none", "none"))
        # interior nodes
        chain = [A]
        for s in range(1, nseg):
            t = s/float(nseg)
            nd = sub_node; sub_node += 1
            ops.node(nd, xa+(xb-xa)*t, ya+(yb-ya)*t, zk)
            dia_extra[k].append(nd); chain.append(nd)
        chain.append(B)
        seg_tags = []
        for s in range(nseg):
            n1, n2 = chain[s], chain[s+1]
            ra = []
            if s == 0:
                ri_z, _ = _rel_parts(relz); ri_y, _ = _rel_parts(rely)
                ra = eng.release_args(ri_z, ri_y)
            if s == nseg-1:
                _, rj_z = _rel_parts(relz); _, rj_y = _rel_parts(rely)
                ra2 = eng.release_args(rj_z, rj_y)
                ra = ra + ra2
            tag = sub_ele; sub_ele += 1
            ops.element("elasticBeamColumn", tag, n1, n2, bA, eng.E, eng.Gmod, bJ, bIx, bIy, 3, *ra)
            seg_tags.append(tag)
        beams.append({"sec": cfg["beam"], "i": i, "j": j, "k": k, "dir": dirn, "L": L,
                      "A": A, "B": B, "nodes": chain, "segs": seg_tags})

    # beams X and Y (sub-divided)
    for k in range(1, NF+1):
        P = present[k]
        for j in range(NY+1):
            for i in range(NX):
                if (i, j) in P and (i+1, j) in P:
                    _add_beam(i, j, k, "X", ntag(i, j, k), ntag(i+1, j, k))
        for i in range(NX+1):
            for j in range(NY):
                if (i, j) in P and (i, j+1) in P:
                    _add_beam(i, j, k, "Y", ntag(i, j, k), ntag(i, j+1, k))

    # braces (single truss elements)
    braces = []
    if cfg.get("braces"):
        ops.uniaxialMaterial("Elastic", 1, eng.E)
        brA = eng.Ipack(cfg["brace"])[0] if eng.unit_system() == "N-mm" else eng.HSS[cfg["brace"]]
        for k in range(1, NF+1):
            for (dirn, i, j) in cfg["braces"](k, NX, NY):
                a = (i, j); b = (i+1, j) if dirn == "X" else (i, j+1)
                if a in present[k-1] and b in present[k]:
                    n1, n2 = ntag(a[0], a[1], k-1), ntag(b[0], b[1], k)
                    ops.element("Truss", et, n1, n2, brA, 1)
                    braces.append({"tag": et, "sec": cfg.get("brace"), "n1": n1, "n2": n2}); et += 1
                if a in present[k] and b in present[k-1]:
                    n1, n2 = ntag(a[0], a[1], k), ntag(b[0], b[1], k-1)
                    ops.element("Truss", et, n1, n2, brA, 1)
                    braces.append({"tag": et, "sec": cfg.get("brace"), "n1": n1, "n2": n2}); et += 1

    # rigid diaphragm (corner nodes + interior beam nodes), no mass (static)
    for k in range(1, NF+1):
        sl = [ntag(i, j, k) for (i, j) in present[k]] + dia_extra[k]
        ops.rigidDiaphragm(3, mtag(k), *sl)

    return {"cm": cm, "present": present, "z": z, "NF": NF,
            "cols": cols, "beams": beams, "braces": braces}


def _bays_adjacent(present_k, i, j, dirn):
    """How many present bays bound this beam (1 perimeter, 2 interior)."""
    n = 0
    if dirn == "X":      # beam (i,j)-(i+1,j): bays south (j-1) and north (j)
        for jj in (j-1, j):
            if all(c in present_k for c in ((i, jj), (i+1, jj), (i, jj+1), (i+1, jj+1))): n += 1
    else:                # beam (i,j)-(i,j+1): bays west (i-1) and east (i)
        for ii in (i-1, i):
            if all(c in present_k for c in ((ii, j), (ii+1, j), (ii, j+1), (ii+1, j+1))): n += 1
    return n


def apply_gravity(cfg, model, fD, fL, fLr):
    """Apply two-way tributary gravity to beam sub-elements (+ perimeter cladding).

    kip-in: line load in kip/in, pressures psf; returns total kip.
    N-mm: line load in N/mm, pressures kN/m²; returns total N.
    """
    if eng.unit_system() == "N-mm":
        return sum(apply_gravity_state(cfg, model, fD, fL, fLr,
                                       self_weight=cfg.get("self_weight", True)).values())
    NF = model["NF"]; SX, SY = cfg["SX"], cfg["SY"]
    heights = cfg["heights"]; clad = cfg.get("clad", 0.0)
    extra = cfg.get("extra_mass_floors", {})
    total = 0.0
    for b in model["beams"]:
        i, j, k, dirn, L = b["i"], b["j"], b["k"], b["dir"], b["L"]
        if not (1 <= k <= NF):
            continue
        roof = (k == NF)
        pD = (cfg["D_roof"] if roof else cfg["D_floor"]) + extra.get(k, 0.0)
        pL = 0.0 if roof else cfg["L_floor"]
        pLr = (cfg.get("snow") or 20.0) if roof else 0.0
        p = fD*pD + fL*pL + fLr*pLr
        nb = _bays_adjacent(model["present"].get(k, set()), i, j, dirn)
        other = SY if dirn == "X" else SX
        wcap = other/2.0
        th = heights[k-1]/12.0; th = th/2.0 if roof else th
        wclad = fD*clad*th/12000.0 if (clad and nb == 1) else 0.0
        segs = b["segs"]
        for s, tag in enumerate(segs):
            s0 = L*s/len(segs); s1 = L*(s+1)/len(segs); smid = 0.5*(s0+s1)
            width_in = min(smid, L-smid, wcap)
            w = nb * p * (width_in/12.0) / 12000.0 + wclad
            ops.eleLoad("-ele", tag, "-type", "-beamUniform", 0.0, -w, 0.0)
            total += w*(s1-s0)
    return total


def _apply_gravity_si(cfg, model, fD, fL, fLr):
    """SI gravity: p in kN/m² → beamUniform w in N/mm. Returns total vertical load (N)."""
    NF = model["NF"]; SX, SY = cfg["SX"], cfg["SY"]
    heights = cfg["heights"]; clad = float(cfg.get("clad") or 0.0)
    extra = cfg.get("extra_mass_floors", {})
    total = 0.0
    for b in model["beams"]:
        i, j, k, dirn, L = b["i"], b["j"], b["k"], b["dir"], b["L"]
        if not (1 <= k <= NF):
            continue
        roof = (k == NF)
        # WP2.1.5: roof imposed load from cfg['Lr'] (IS 875-2 Table 2) and snow from cfg['snow'] -- both under the
        # roof-imposed factor on this legacy path; no 1.0 kN/m2 placeholder (floor_pressures raises when Lr is missing)
        D_, L_, Lr_, S_ = floor_pressures(cfg, k)
        pD = D_
        pL = 0.0 if roof else L_
        pLr = (Lr_ + S_) if roof else 0.0
        p = fD*pD + fL*pL + fLr*pLr  # kN/m²
        nb = _bays_adjacent(model["present"].get(k, set()), i, j, dirn)
        other = SY if dirn == "X" else SX  # mm
        wcap = other / 2.0
        th = heights[k-1]; th = th/2.0 if roof else th  # mm
        # clad[kN/m²]*th[mm]/1000 = kN/m = N/mm on perimeter
        wclad = (fD * clad * th / 1000.0) if (clad and nb == 1) else 0.0
        segs = b["segs"]
        for s, tag in enumerate(segs):
            s0 = L*s/len(segs); s1 = L*(s+1)/len(segs); smid = 0.5*(s0+s1)
            width_mm = min(smid, L-smid, wcap)
            # p[kN/m²] * (width_mm/1000)[m] = kN/m = N/mm
            w = nb * p * (width_mm / 1000.0) + wclad
            ops.eleLoad("-ele", tag, "-type", "-beamUniform", 0.0, -w, 0.0)
            total += w * (s1 - s0)
    return total


def apply_lateral(lateral):
    for k, (fx, fy, mz) in lateral.items():
        ops.load(mtag(k), fx, fy, 0.0, 0.0, 0.0, mz)


def _solve():
    ops.constraints("Transformation"); ops.numberer("RCM"); ops.system("UmfPack")
    ops.test("NormDispIncr", 1e-7, 200); ops.algorithm("Newton")
    ops.integrator("LoadControl", 1.0); ops.analysis("Static")
    return ops.analyze(1)


def run_combo(cfg, fD, fL, fLr, lateral, transf="PDelta", nseg=10):
    """Build + analyse ONE LRFD combination statically with P-Delta. Returns (model, applied_kip, ok)."""
    model = build_static(cfg, transf, nseg)
    ops.timeSeries("Linear", 1); ops.pattern("Plain", 1, 1)
    applied = apply_gravity(cfg, model, fD, fL, fLr)
    apply_lateral(lateral)
    ok = _solve()
    return model, applied, ok


# ====================================================================================
# DEMAND ENVELOPE on the single distributed static model  (replaces design_post.run_case
# for the gravity-correct column axial / base reactions).  Beam gravity moment follows the
# cfg["floor_system"] convention: "one-way" (default, composite steel deck->fillers->girder ->
# conservative w*L^2/8 on the girder) or "two-way" (slab 45-deg tributary -> the solved moment).
# Two-key DISK cache (jobs/<name>/design/): gravity envelope keyed sectionless (size-invariant when
# the gravity path is determinate) so it is computed ONCE and reused across resizes; seismic envelope
# keyed on the LATERAL members' sections + mass, so it is reused while only gravity members change.
# ====================================================================================
import hashlib as _hashlib, json as _json, os as _os

def _one_way_grav(cfg, b, fD, fL, fLr):
    """One-way girder gravity moment/shear (w*L^2/8, w*L/2) over the full perpendicular-bay tributary
    -- the realistic design moment for a one-way composite floor (deck -> filler beams -> girder)."""
    if eng.unit_system() == "N-mm":
        # WP2.1: kN/m2 x trib[mm] / 1000 = N/mm (the old /1000/144 was a psf->ksi factor: 144x low)
        return one_way_gravity(cfg, b, fD, fL, fLr)
    k = b["k"]; NF = len(cfg["heights"]); roof = (k >= NF); L = b["L"]
    trib = cfg["SY"] if b["dir"] == "X" else cfg["SX"]
    Dp = cfg["D_roof"] if roof else cfg["D_floor"]; Lp = 0.0 if roof else cfg["L_floor"]
    LrS = ((cfg.get("snow", 0.0) or cfg.get("Lr", 20.0)) if roof else 0.0)
    w = (fD*Dp + fL*Lp + fLr*LrS)/1000.0/144.0*trib
    return w*L*L/8.0, w*L/2.0

def _member_kinds(model):
    """fset(corner nodes) -> ('col'|'beam'|'brace', section)."""
    kinds = {}
    for c in model["cols"]:   kinds[frozenset((c["n1"], c["n2"]))] = ("col", c.get("sec"))
    for b in model["beams"]:  kinds[frozenset((b["A"], b["B"]))]   = ("beam", b.get("sec"))
    for b in model["braces"]: kinds[frozenset((b["n1"], b["n2"]))] = ("brace", b.get("sec"))
    return kinds

def _extract(model, cfg, fD, fL, fLr, floor_system):
    """Per-PARENT-member demands {fset(corner nodes): (N, Mz, My, V)} from the solved static model."""
    out = {}
    for c in model["cols"]:
        bf = ops.basicForce(c["tag"]); N = bf[0]
        m_z = max(abs(bf[1]), abs(bf[2])); m_y = max(abs(bf[3]), abs(bf[4]))
        L = max(1e-6, abs(ops.nodeCoord(c["n2"])[2]-ops.nodeCoord(c["n1"])[2]))
        V = max((abs(bf[1])+abs(bf[2]))/L, (abs(bf[3])+abs(bf[4]))/L)
        out[frozenset((c["n1"], c["n2"]))] = (N, m_z, m_y, V)             # column strong axis = local z
    for b in model["braces"]:
        out[frozenset((b["n1"], b["n2"]))] = (ops.basicForce(b["tag"])[0], 0.0, 0.0, 0.0)
    for b in model["beams"]:
        Nb = Mmaj = Mmin = 0.0
        for t in b["segs"]:                                # envelope moment along the real diagram
            f = ops.basicForce(t)
            Nb = max(Nb, abs(f[0]))
            mz = max(abs(f[1]), abs(f[2])); my = max(abs(f[3]), abs(f[4]))
            Mmaj = max(Mmaj, max(mz, my)); Mmin = max(Mmin, min(mz, my))
        Mg, Vg = _one_way_grav(cfg, b, fD, fL, fLr)
        if floor_system != "two-way":
            Mmaj = max(Mmaj, Mg)                            # one-way girder design moment (conservative)
        out[frozenset((b["A"], b["B"]))] = (Nb, Mmaj, Mmin, Vg)   # Vg = simple-span design shear (wL/2)
    return out

def _solve_case(cfg, case, nseg, floor_system):
    label, fD, fL, fLr, lat, col_only = case
    model = build_static(cfg, "PDelta", nseg)
    ops.timeSeries("Linear", 1); ops.pattern("Plain", 1, 1)
    apply_gravity(cfg, model, fD, fL, fLr); apply_lateral(lat); _solve()
    return _extract(model, cfg, fD, fL, fLr, floor_system), _member_kinds(model)

def _merge(env, kinds, res, label, col_only):
    """Fold one case's per-member result into the running envelope (respecting col_only)."""
    for fs, (N, Mz, My, V) in res.items():
        kind = kinds.get(fs, ("beam", None))[0]
        if col_only and kind != "col":
            continue
        e = env.setdefault(fs, dict(comp=0.0, tens=0.0, Mz=0.0, My=0.0, V=0.0, combo="", score=-1.0))
        e["comp"] = max(e["comp"], max(-N, 0.0)); e["tens"] = max(e["tens"], max(N, 0.0))
        e["Mz"] = max(e["Mz"], abs(Mz)); e["My"] = max(e["My"], abs(My)); e["V"] = max(e["V"], abs(V))
        sc = abs(N) if kind in ("col", "brace") else abs(Mz)
        if sc > e["score"]: e["score"] = sc; e["combo"] = label

def _grav_key(cfg, nseg, floor_system, determinate, sec_sig):
    base = dict(NX=cfg["NX"], NY=cfg["NY"], SX=cfg["SX"], SY=cfg["SY"], H=tuple(cfg["heights"]),
                base=cfg.get("base", "fixed"), D=cfg.get("D_floor"), Dr=cfg.get("D_roof"),
                clad=cfg.get("clad"), L=cfg.get("L_floor"), Lr=cfg.get("Lr"), snow=cfg.get("snow"),
                xtra=tuple(sorted((cfg.get("extra_mass_floors") or {}).items())),
                fs=floor_system, nseg=nseg)
    if not determinate:                  # indeterminate (moment-frame) gravity -> size-dependent
        base["sec"] = sec_sig
    return "G" + _hashlib.md5(repr(sorted(base.items())).encode()).hexdigest()

def _seis_key(cfg, nseg, floor_system, lat_sig):
    base = dict(NX=cfg["NX"], NY=cfg["NY"], SX=cfg["SX"], SY=cfg["SY"], H=tuple(cfg["heights"]),
                base=cfg.get("base", "fixed"), seis=tuple(sorted((cfg.get("seis") or {}).items())),
                gov=cfg.get("governing"), wind=bool(cfg.get("wind")), rho=cfg.get("rho"),
                D=cfg.get("D_floor"), Dr=cfg.get("D_roof"), clad=cfg.get("clad"),
                fs=floor_system, nseg=nseg, lat=lat_sig)
    return "S" + _hashlib.md5(repr(sorted(base.items())).encode()).hexdigest()

def _cache_load(cache_dir, key):
    if not cache_dir: return None
    p = _os.path.join(cache_dir, "_demand_cache.json")
    try:
        d = _json.load(open(p))
        if d.get("key") == key:
            return {frozenset(int(x) for x in k.split("|")): v for k, v in d["env"].items()}
    except Exception:
        pass
    return None

def _cache_save(cache_dir, key, env):
    if not cache_dir: return
    try:
        _os.makedirs(cache_dir, exist_ok=True)
        ser = {"|".join(str(n) for n in fs): v for fs, v in env.items()}
        _json.dump({"key": key, "env": ser}, open(_os.path.join(cache_dir, "_demand_cache.json"), "w"))
    except Exception:
        pass

def demand_envelope(cfg, cases, nseg=6, floor_system=None, determinate=True,
                    sec_sig="", lat_sig="", cache_dir=None):
    """Per-member DEMAND envelope from the SINGLE distributed static model, with the two-key disk
    cache. Returns (env, kinds): env[fset] = {comp,tens,Mz,My,V,combo}; kinds[fset] = (kind, sec).
    fset = frozenset of the member's two corner-grid nodes (matches engine3d.build element nodes)."""
    if eng.unit_system() == "N-mm":
        return demand_envelope_si(cfg, cases, nseg, floor_system, cache_dir=cache_dir,
                                  rsa=(cfg.get("_rsa_element_forces") or None))
    floor_system = (floor_system or cfg.get("floor_system") or "one-way")
    grav = [c for c in cases if not c[4]]            # lateral dict empty -> pure gravity
    seis = [c for c in cases if c[4]]
    kinds = _member_kinds(build_static(cfg, "Linear", 1))     # cheap topology map (nseg=1)
    # ---- gravity envelope (size-invariant when determinate): disk cache, compute ONCE ----
    _cd = _hashlib.md5(repr([(tuple(c)[:4], sorted((c[4] or {}).items()), c[5],
                              sorted((getattr(c, "meta", {}) or {}).get("rsa", {}) or {}) if isinstance(
                                  (getattr(c, "meta", {}) or {}).get("rsa"), dict) else None)
                             for c in cases]).encode()).hexdigest()   # WP1.1: factors are in the key
    gkey = _grav_key(cfg, nseg, floor_system, determinate, sec_sig) + _cd
    genv = _cache_load(cache_dir, gkey + "|grav")
    if genv is None:
        genv = {}
        for case in grav:
            res, _k = _solve_case(cfg, case, nseg, floor_system); _merge(genv, _k, res, case[0], case[5])
        _cache_save(cache_dir, gkey + "|grav", genv)
    # ---- seismic/wind envelope (keyed on lateral sections + mass): disk cache ----
    skey = _seis_key(cfg, nseg, floor_system, lat_sig) + _cd
    senv = _cache_load(cache_dir, skey + "|seis")
    if senv is None:
        senv = {}
        for case in seis:
            res, _k = _solve_case(cfg, case, nseg, floor_system); _merge(senv, _k, res, case[0], case[5])
        _cache_save(cache_dir, skey + "|seis", senv)
    # ---- merge the two envelopes per member ----
    env = {}
    for src in (genv, senv):
        for fs, e in src.items():
            d = env.setdefault(fs, dict(comp=0.0, tens=0.0, Mz=0.0, My=0.0, V=0.0, combo="", score=-1.0))
            for q in ("comp", "tens", "Mz", "My", "V"): d[q] = max(d[q], e[q])
            if e.get("score", -1.0) > d["score"]: d["score"] = e["score"]; d["combo"] = e["combo"]
    return env, kinds


# ====================================================================================
# India SI demand engine (WP1.1-1.3, WP2.1, WP2.7): gravity states solved once with P-Delta,
# lateral / torsion / notional patterns superposed on the gravity-stiffened tangent (linear
# '-factorOnce' steps), RSA member forces (CQC, scaled per 7.7.3.1) combined +- per case.
# Every combination keeps a per-member record (N, Mz, My, V, end moments) so the IS 800
# interaction is evaluated with CONCURRENT forces per combination (WP2.3 hand-off).
# ====================================================================================
import numpy as _np

STEEL_UNIT_WEIGHT_N_PER_MM3 = 7850.0 * 9.81 * 1e-9     # 7850 kg/m3 x g -> N/mm3 (IS 875 Part 1: steel 78.5 kN/m3)


def _E_G():
    return eng.E, eng.Gmod


def _table10_fraction(p_imposed):
    """IS 1893 Table 10: 25 % of imposed load up to and including 3.0 kN/m2, 50 % above."""
    return 0.25 if float(p_imposed or 0.0) <= 3.0 else 0.50


def _roof_live(cfg):
    """Roof imposed load in kN/m2 from cfg['Lr'] (IS 875-2 Table 2); never a placeholder (WP2.1)."""
    v = cfg.get("Lr")
    if v is None:
        raise ValueError("cfg['Lr'] (roof imposed load, kN/m2, IS 875 (Part 2) Table 2) is required")
    return float(v)


def partition_design_load(cfg):
    """IS 875-2 3.1.2 partition allowance carried as IMPOSED gravity for member design (kN/m2)."""
    return float(cfg.get("partition_load_kNm2") or 0.0)


def roof_level_set(cfg, NF=None):
    """H50: levels treated as roofs -- the top level plus cfg['roof_levels'] (1-based storey levels of lower roofs,
    lean-tos, setbacks).  Roof levels carry D_roof, Lr and snow and no partitions / floor imposed load.
    (india_loads.roof_level_set is the same rule for callers that do not import the static model.)"""
    import india_loads as _IL
    return _IL.roof_level_set(cfg, NF)


def floor_pressures(cfg, k):
    """(D, L_floor_incl_partitions, Lr, S) in kN/m2 at level k (roof = top level or a cfg['roof_levels'] level,
    H50: D_roof, Lr, snow, no partitions)."""
    NF = len(cfg["heights"]); roof = (k >= NF) or (k in roof_level_set(cfg, NF))
    by = cfg.get("D_by_level") or {}
    D = float(by.get(k, by.get(str(k), cfg["D_roof"] if roof else cfg["D_floor"])))
    D += float((cfg.get("extra_mass_floors") or {}).get(k, 0.0) or 0.0)
    lb = cfg.get("L_by_level") or {}
    L = 0.0 if roof else float(lb.get(k, lb.get(str(k), cfg["L_floor"]))) + partition_design_load(cfg)
    Lr = _roof_live(cfg) if roof else 0.0
    S = float(cfg.get("snow") or 0.0) if roof else 0.0
    return D, L, Lr, S


def _deck_span(cfg):
    d = str(cfg.get("deck_span") or "").upper()
    return d if d in ("X", "Y") else None


def _beam_floor_width(model, b, cfg):
    """(two_way, one_way_trib_mm) for a beam: the bays on either side."""
    SX, SY = cfg["SX"], cfg["SY"]
    nb = _bays_adjacent(model["present"].get(b["k"], set()), b["i"], b["j"], b["dir"])
    other = SY if b["dir"] == "X" else SX
    return nb, nb * other / 2.0


def _grid_xy_lines(cfg):
    """Actual grid-line coordinates (xcoords / ycoords when given, else i*SX / j*SY)."""
    NX, NY = int(cfg.get("NX") or 0), int(cfg.get("NY") or 0)
    xco, yco = cfg.get("xcoords"), cfg.get("ycoords")
    xs = [float(xco[i]) if xco else i * float(cfg["SX"]) for i in range(NX + 1)]
    ys = [float(yco[j]) if yco else j * float(cfg["SY"]) for j in range(NY + 1)]
    return xs, ys


def adjacent_panels(cfg, present_k, i, j, dirn):
    """H13: the present bays bounding grid beam (i, j, dirn) as [(width_perpendicular_mm, span_along_mm)] from the
    actual grid coordinates (edge beam: one panel, interior: two)."""
    xs, ys = _grid_xy_lines(cfg)
    out = []
    try:
        if dirn == "X":
            for jj in (j - 1, j):
                if all(c in present_k for c in ((i, jj), (i + 1, jj), (i, jj + 1), (i + 1, jj + 1))):
                    out.append((ys[jj + 1] - ys[jj], xs[i + 1] - xs[i]))
        else:
            for ii in (i - 1, i):
                if all(c in present_k for c in ((ii, j), (ii + 1, j), (ii, j + 1), (ii + 1, j + 1))):
                    out.append((xs[ii + 1] - xs[ii], ys[j + 1] - ys[j]))
    except (IndexError, TypeError):
        return []
    return out


def secondary_spacing(cfg):
    """cfg['secondary_spacing_mm'] (H13): spacing of the secondary beams that run PARALLEL to cfg['deck_span'] and
    frame into the girders perpendicular to it (None when not declared)."""
    v = cfg.get("secondary_spacing_mm")
    try:
        v = float(v)
    except (TypeError, ValueError):
        return None
    return v if v > 0 else None


def one_way_trib_mm(cfg, present_k, i, j, dirn):
    """H13: one-way tributary width (mm) of a grid beam, from the actual bays bounding it.

    Without secondaries: a beam parallel to cfg['deck_span'] carries 0, a girder perpendicular to it carries half of
    each bounding bay (edge girder: half bay).  With cfg['secondary_spacing_mm'] = s: a grid beam parallel to the
    span is a secondary line and carries min(s/2, bay/2) from each bounding bay (edge s/2, interior s capped at the
    bay); the girders perpendicular to it carry the rest, (w/2)(1 - s/B) per bay (B = bay dimension along the
    girder), so the panel load is conserved.  Returns None when the beam bounds no present bay (caller falls back)."""
    ds = _deck_span(cfg)
    panels = adjacent_panels(cfg, present_k, i, j, dirn)
    if not panels:
        return None
    s = secondary_spacing(cfg)
    if ds is None:
        return sum(w / 2.0 for (w, _) in panels)
    if dirn == ds:
        return sum(min(s / 2.0, w / 2.0) for (w, _) in panels) if s else 0.0
    if s:
        return sum((w / 2.0) * max(0.0, 1.0 - s / B) if B > 0 else 0.0 for (w, B) in panels)
    return sum(w / 2.0 for (w, _) in panels)


def apply_gravity_state(cfg, model, fD, fL, fLr, fS=0.0, fC=0.0, fEv=0.0, self_weight=True, crane_pattern=None,
                        snow_pattern=None):
    """SI gravity for one gravity state; returns {level: total vertical load N}.

    * floor pressure p = fD D + fL L + fLr Lr + fS S + fEv (D + Table-10 share of L)   [kN/m2]
      (fEv = +-factor x Av, IS 1893 6.4.6 vertical shaking on the seismic weight)
    * distribution: two-way 45-deg tributary, or one-way onto the beams perpendicular to
      cfg['deck_span'] ('X'|'Y') when declared (WP2.7: explicit span direction)
    * cladding line load on perimeter beams, member self-weight as element loads (WP1.6)
    """
    NF = model["NF"]; heights = cfg["heights"]; clad = float(cfg.get("clad") or 0.0)
    ds = _deck_span(cfg)
    lev = {k: 0.0 for k in range(1, NF + 1)}
    fdead = fD + fEv
    # IS 875 (Part 4):2021 4.3 partial snow: snow_pattern = (axis, 'lo'|'hi') keeps the roof snow on the half of the
    # plan below / above the mid-line normal to `axis` (zero snow on the other half; WP6-fix)
    sp_axis, sp_side, sp_mid = None, None, None
    roofs = roof_level_set(cfg, NF)
    if snow_pattern:
        sp_axis = 0 if str(snow_pattern[0]).upper() == "X" else 1
        sp_side = str(snow_pattern[1]).lower()
        # H50 (HR-E-06): split at the declared ridge cfg['snow_partial']['ridge_mm'] (default: plan mid-line)
        spx = cfg.get("snow_partial")
        rmm = spx.get("ridge_mm") if isinstance(spx, dict) else None
        if rmm is not None:
            sp_mid = float(rmm)
        else:
            crd_all = [ops.nodeCoord(n) for n in ops.getNodeTags()]
            sp_mid = 0.5 * (min(c[sp_axis] for c in crd_all) + max(c[sp_axis] for c in crd_all))
    for b in model["beams"]:
        i, j, k, dirn, L = b["i"], b["j"], b["k"], b["dir"], b["L"]
        if not (1 <= k <= NF):
            continue
        D, Lf, Lr, S = floor_pressures(cfg, k)
        p = fD * D + fL * Lf + fLr * Lr + fS * S + fEv * (D + _table10_fraction(Lf) * Lf)
        p_nosnow = p - fS * S
        nb, trib1 = _beam_floor_width(model, b, cfg)
        if ds is not None:
            tw = one_way_trib_mm(cfg, model["present"].get(k, set()), i, j, dirn)       # H13
            if tw is not None:
                trib1 = tw
        other = cfg["SY"] if dirn == "X" else cfg["SX"]
        wcap = other / 2.0
        th = heights[k - 1] / 2.0 if k == NF else heights[k - 1]
        wclad = (fdead * clad * th / 1000.0) if (clad and nb == 1) else 0.0
        segs = b["segs"]
        A_sw = b.get("_A")
        if A_sw is None:
            try:
                A_sw = eng.Ipack(b["sec"])[0] if b.get("sec") else 0.0
            except Exception:
                A_sw = 0.0
            b["_A"] = A_sw
        wsw = fdead * A_sw * STEEL_UNIT_WEIGHT_N_PER_MM3 if self_weight else 0.0
        for s_, tag in enumerate(segs):
            s0 = L * s_ / len(segs); s1 = L * (s_ + 1) / len(segs); smid = 0.5 * (s0 + s1)
            if ds is None:
                width_mm = nb * min(smid, L - smid, wcap)
            else:
                # one-way (H13): girders perpendicular to the span carry their bays; a beam parallel to the span
                # carries nothing, or its secondary strip when cfg['secondary_spacing_mm'] is declared
                width_mm = trib1 if (dirn != ds or secondary_spacing(cfg)) else 0.0
            pp = p
            if sp_axis is not None and k in roofs and S:
                ca_, cb_ = ops.nodeCoord(b["A"]), ops.nodeCoord(b["B"])
                xm = ca_[sp_axis] + (cb_[sp_axis] - ca_[sp_axis]) * (smid / L)
                loaded = (xm <= sp_mid + 1e-6) if sp_side == "lo" else (xm >= sp_mid - 1e-6)
                if not loaded:
                    pp = p_nosnow
            w = pp * (width_mm / 1000.0) + wclad + wsw
            ops.eleLoad("-ele", tag, "-type", "-beamUniform", 0.0, -w, 0.0)
            lev[k] += w * (s1 - s0)
    for c in model["cols"]:
        if not self_weight:
            break
        try:
            A = c.get("_A") or eng.Ipack(c["sec"])[0]
        except Exception:
            continue
        c["_A"] = A
        L = abs(ops.nodeCoord(c["n2"])[2] - ops.nodeCoord(c["n1"])[2])
        w = fdead * A * STEEL_UNIT_WEIGHT_N_PER_MM3
        ops.eleLoad("-ele", c["tag"], "-type", "-beamUniform", 0.0, 0.0, -w)     # axial (local x up)
        ktop = c["n2"] // 100000
        if 1 <= ktop <= NF:
            lev[ktop] += 0.5 * w * L
        kb = c["n1"] // 100000
        if 1 <= kb <= NF:
            lev[kb] += 0.5 * w * L
    for br in model["braces"]:
        if not self_weight:
            break
        try:
            A = br.get("_A") or eng.Ipack(br["sec"])[0]
        except Exception:
            continue
        br["_A"] = A
        c1, c2 = ops.nodeCoord(br["n1"]), ops.nodeCoord(br["n2"])
        L = math.dist(c1, c2)
        W = fdead * A * STEEL_UNIT_WEIGHT_N_PER_MM3 * L
        for nd in (br["n1"], br["n2"]):
            if nd // 100000 >= 1:
                ops.load(nd, 0.0, 0.0, -0.5 * W, 0.0, 0.0, 0.0)
                kk = nd // 100000
                if kk in lev:
                    lev[kk] += 0.5 * W
    # declared permanent nodal loads (WP6-fix): gantry girder + rail reactions on crane brackets, hung equipment --
    # cfg['nodal_dead_loads'] = [{node, Fz_N (down < 0), Mx_Nmm, My_Nmm, level, note}], factored with the dead load
    for nl in (cfg.get("nodal_dead_loads") or []):
        try:
            nd = int(nl["node"])
        except (KeyError, TypeError, ValueError):
            continue
        Fz = float(nl.get("Fz_N") or 0.0)
        ops.load(nd, 0.0, 0.0, fdead * Fz, fdead * float(nl.get("Mx_Nmm") or 0.0), fdead * float(nl.get("My_Nmm") or 0.0), 0.0)
        kk = nl.get("level")
        if kk in lev:
            lev[kk] += -fdead * Fz
    # declared imposed point loads (H50, HR-E-26): cfg['nodal_imposed_loads'] = [{node, Fz_N (down < 0), Mx_Nmm,
    # My_Nmm, level, kind: 'floor' | 'roof'}] -- factored with fL (floor imposed) or fLr (roof imposed; replaced by
    # snow per IS 875-5 8.1 Note 1 in the rows where fS carries the roof term)
    for nl in (cfg.get("nodal_imposed_loads") or []):
        try:
            nd = int(nl["node"])
        except (KeyError, TypeError, ValueError):
            continue
        fI = fLr if str(nl.get("kind") or "floor").lower() == "roof" else fL
        if not fI:
            continue
        Fz = float(nl.get("Fz_N") or 0.0)
        ops.load(nd, 0.0, 0.0, fI * Fz, fI * float(nl.get("Mx_Nmm") or 0.0), fI * float(nl.get("My_Nmm") or 0.0), 0.0)
        kk = nl.get("level")
        if kk is None:
            kk = nd // 100000
        if kk in lev:
            lev[kk] += -fI * Fz
    # declared snow point loads (WP6-fix): reactions of an attached lower roof (lean-to drift, IS 875-4 5.2.4) on the
    # main columns -- cfg['nodal_snow_loads'] = [{node, Fz_N (down < 0), Mx_Nmm, My_Nmm, level}], factored with fS
    if fS:
        for nl in (cfg.get("nodal_snow_loads") or []):
            try:
                nd = int(nl["node"])
            except (KeyError, TypeError, ValueError):
                continue
            Fz = float(nl.get("Fz_N") or 0.0)
            ops.load(nd, 0.0, 0.0, fS * Fz, fS * float(nl.get("Mx_Nmm") or 0.0), fS * float(nl.get("My_Nmm") or 0.0), 0.0)
            kk = nl.get("level")
            if kk in lev:
                lev[kk] += -fS * Fz
    if fC:
        apply_crane_loads(cfg, model, fC, crane_pattern)
    return lev


def apply_crane_loads(cfg, model, fC, pattern=None):
    """Crane wheel reactions (+ impact, R e), surge or traction (WP2.7) -- india_loads.crane_frame_loads."""
    from india_loads import crane_frame_loads
    for nd, (fx, fy, fz, mx, my, mz) in crane_frame_loads(cfg, pattern or ("L", None)).items():
        ops.load(int(nd), fC * fx, fC * fy, fC * fz, fC * mx, fC * my, fC * mz)


def pitched_roof_findings(cfg, info=None) -> list:
    """H18 (HR-E-05, NEW-1): stop the silent zero roof load / zero roof weight of a true-slope roof.

    ERROR when any beam's end levels differ by more than 1 mm (the static loads, seismic weight and diaphragm all
    assume level beams; unless cfg['roof_planes'] is declared -- reserved for the phase-2 roof-plane input, X02), or
    when a roof-level beam bounds no complete bay (zero tributary) while the roof area loads are non-zero.  ``info``
    = an engine3d.build info dict (built here when omitted).  Returns [(severity, message)]."""
    out = []
    if info is None:
        info = eng.build(cfg, "Linear")
    NF = int(info.get("NF") or len(cfg.get("heights") or []))
    present = info.get("present") or {}
    NX, NY = int(cfg.get("NX") or 0), int(cfg.get("NY") or 0)
    sloped, zero = [], []
    area = float(cfg.get("D_roof") or 0.0) + float(cfg.get("Lr") or 0.0) + float(cfg.get("snow") or 0.0)
    roofs = roof_level_set(cfg, NF)
    for (t, kind, sec, n1, n2) in info.get("ele") or []:
        if kind != "beam":
            continue
        try:
            c1, c2 = ops.nodeCoord(n1), ops.nodeCoord(n2)
        except Exception:
            continue
        if abs(c1[2] - c2[2]) > 1.0:
            sloped.append(t)
            continue
        k = n1 // 100000
        if k not in roofs or area <= 0.0:
            continue
        nlo = min(n1, n2)
        i, j = (nlo % 100000) // 100, nlo % 100
        pk = present.get(k, set())
        if not (0 <= i <= NX and 0 <= j <= NY) or (i, j) not in pk:
            continue                                   # off-grid work point (EBF link piece): not screened here
        dirn = "X" if abs(c2[0] - c1[0]) >= abs(c2[1] - c1[1]) else "Y"
        if _bays_adjacent(pk, i, j, dirn) == 0:
            zero.append(t)
    if sloped and not cfg.get("roof_planes"):
        out.append(("ERROR", "%d beam(s) have end levels differing by > 1 mm (e.g. element %s): true-slope rafters "
                             "are not supported yet -- the static roof load, the seismic weight (IS 1893 7.4) and "
                             "the diaphragm assume level beams, so the roof load would silently be zero. Model the "
                             "rafters flat at the eave with IS 875-3 Table 6 at the true pitch (roof_planes: X02)"
                             % (len(sloped), sloped[0])))
    if zero:
        out.append(("ERROR", "%d roof-level beam(s) bound no complete bay (zero tributary, e.g. element %s) while the "
                             "roof area loads D_roof + Lr + snow = %.2f kN/m2 are non-zero: the roof load and roof "
                             "weight would silently be lost -- check the roof footprint / present set"
                             % (len(zero), zero[0], area)))
    return out


def _strip_widths(coords, tol=1.0):
    """H14 (HR-B-12): tributary wall width per column line = half the distance to each neighbouring line
    (end line: half the distance to its one neighbour).  coords = the distinct line coordinates."""
    cs = sorted(coords)
    out = {}
    for n, c in enumerate(cs):
        lo = (c - cs[n - 1]) / 2.0 if n > 0 else 0.0
        hi = (cs[n + 1] - c) / 2.0 if n + 1 < len(cs) else 0.0
        out[c] = lo + hi
    return out


def _roof_split(cfg, pat, ax, nodes):
    """(split coordinate along the wind axis, windward side 'lo'|'hi') for the roof zones of one pattern (H14).
    Wind across a declared ridge (cfg['ridge'] = {'axis': plan axis the ridge coordinate is measured on, i.e. the
    axis normal to the ridge line, 'coord_mm': ridge position}) splits at the ridge; otherwise at the plan mid-line
    normal to the wind (Table 6 key plan: the line normal to the ridge divides E/G from F/H)."""
    rg = cfg.get("ridge") if isinstance(cfg.get("ridge"), dict) else None
    axn = "X" if ax == 0 else "Y"
    if rg and str(rg.get("axis") or "").upper() == axn and rg.get("coord_mm") is not None:
        split = float(rg["coord_mm"])
    else:
        split = 0.5 * (min(c[ax] for c in nodes) + max(c[ax] for c in nodes))
    return split, ("hi" if _pattern_sign(pat) < 0 else "lo")


def _pattern_sign(pat):
    """+1: wind blowing towards +axis (windward face = low-coordinate edge); -1: reversed (H14)."""
    try:
        return -1.0 if float(pat.get("sign", 1)) < 0 else 1.0
    except (TypeError, ValueError):
        return 1.0


def member_wind_loads(cfg, model, pat, f):
    """IS 875-3 7.3.1 member wind for one pattern x factor f, applied inside the current load pattern.

    H14 (HR-A-15, HR-B-12, HR-E-16):
    * direction: pat['sign'] = +1 (wind towards +wind_axis, windward = low-coordinate side) or -1 (reversed;
      india_combos generates both for every pattern);
    * roof: (Cpe - Cpi) pd on EVERY roof-level beam (top level + cfg['roof_levels']), + = downward, with the
      windward / leeward zone decided per sub-segment at the declared ridge cfg['ridge'] (or the plan mid-line),
      width = the gravity tributary (two-way 45-deg or one-way incl. secondary strips);
    * walls: the first exposed column line met from upwind in each strip normal to the wind (projected-envelope
      scan per column piece, so a main wall above / beyond a lean-to is loaded) takes the windward pressure, the
      last one the leeward pressure, each over its tributary width (half the distance to the neighbouring lines).
    Returns {'roof_N': total vertical, 'wall_N': total horizontal} for the record."""
    NF = model["NF"]; ax = 0 if pat["wind_axis"] == "X" else 1
    oth = 1 - ax
    ds = _deck_span(cfg)
    sgn_w = _pattern_sign(pat)
    nodes = [ops.nodeCoord(n) for n in ops.getNodeTags()]
    tot = {"roof_N": 0.0, "wall_N": 0.0}
    pw, pl = pat.get("roof_windward_kNm2"), pat.get("roof_leeward_kNm2")
    if pw is not None and pl is not None:
        roofs = roof_level_set(cfg, NF)
        split, wside = _roof_split(cfg, pat, ax, nodes)
        for b in model["beams"]:
            if b["k"] not in roofs:
                continue
            nb, trib1 = _beam_floor_width(model, b, cfg)
            if ds is not None:
                tw = one_way_trib_mm(cfg, model["present"].get(b["k"], set()), b["i"], b["j"], b["dir"])
                trib1 = tw if tw is not None else (0.0 if b["dir"] == ds else trib1)
                if trib1 <= 0.0:
                    continue
            other = cfg["SY"] if b["dir"] == "X" else cfg["SX"]
            ca, cb = ops.nodeCoord(b["A"]), ops.nodeCoord(b["B"])
            L = b["L"]; segs = b["segs"]
            for s_, t in enumerate(segs):
                s0 = L * s_ / len(segs); s1 = L * (s_ + 1) / len(segs); smid = 0.5 * (s0 + s1)
                width = trib1 if ds is not None else nb * min(smid, L - smid, other / 2.0)
                xm = ca[ax] + (cb[ax] - ca[ax]) * (smid / L)
                windward = (xm <= split + 1e-6) if wside == "lo" else (xm >= split - 1e-6)
                pp = pw if windward else pl
                w = f * float(pp) * width / 1000.0                      # N/mm, + downward
                ops.eleLoad("-ele", t, "-type", "-beamUniform", 0.0, -w, 0.0)
                tot["roof_N"] += w * (s1 - s0)
    qw, ql = pat.get("wall_windward_kNm2"), pat.get("wall_leeward_kNm2")
    if qw is not None and ql is not None:
        # wall pressure as a DISTRIBUTED load on the exposed column elements (every piece of the column, full
        # height): a portal column bends under the wall wind along its height and the lower half of the wall load
        # reaches the base through the column shear, not as a nodal force at the roof (WP6-fix, HREX3-Ex14-02);
        # nodal fallback (tributary storey height at the level's grid nodes) when no column element is on the line
        # (face, q, force sign along +axis): windward face inward = along the wind; leeward face inward = against it
        faces = (("up", qw, sgn_w), ("down", ql, -sgn_w))
        cols = []
        for c in model["cols"]:
            c1, c2 = ops.nodeCoord(c["n1"]), ops.nodeCoord(c["n2"])
            cols.append((c, c1, c2, 0.5 * (c1[ax] + c2[ax]), round(0.5 * (c1[oth] + c2[oth]), 3),
                         min(c1[2], c2[2]), max(c1[2], c2[2])))
        if cols and all(c.get("transf") in (1, 2) for (c, *_r) in cols):
            for (c, c1, c2, xa, yo, z0, z1) in cols:
                zm = 0.5 * (z0 + z1)
                same_h = [r for r in cols if r[5] - 1e-6 <= zm <= r[6] + 1e-6]        # pieces at this height
                strip = [r[3] for r in same_h if abs(r[4] - yo) < 1.0]
                widths = _strip_widths({r[4] for r in same_h})
                wtrib = widths.get(yo) or (cfg["SY"] if ax == 0 else cfg["SX"])
                for face, q, fs in faces:
                    upwind_first = (min(strip) if (face == "up") == (sgn_w > 0) else max(strip))
                    if abs(xa - upwind_first) > 1e-6:
                        continue
                    F = f * float(q) * wtrib / 1000.0 * fs      # N/mm along +axis
                    # column local axes: x up; transf 2 (vecxz 0,1,0): y_l = +X, z_l = +Y; transf 1 (vecxz 1,0,0): y_l = -Y, z_l = +X
                    if c["transf"] == 2:
                        Wy, Wz = (F, 0.0) if ax == 0 else (0.0, F)
                    else:
                        Wy, Wz = (0.0, F) if ax == 0 else (-F, 0.0)
                    ops.eleLoad("-ele", c["tag"], "-type", "-beamUniform", Wy, Wz)
                    tot["wall_N"] += F * abs(c2[2] - c1[2])
        else:
            alln = set(ops.getNodeTags())
            for k in range(1, NF + 1):
                h_t = cfg["heights"][k - 1] / 2.0 + (cfg["heights"][k] / 2.0 if k < NF else 0.0)
                lvl = [ntag(i, j, k) for (i, j) in (model.get("present") or {}).get(k, ())]
                crd = {n: ops.nodeCoord(n) for n in lvl if n in alln}
                if not crd:
                    continue
                strips = {}
                for n, c in crd.items():
                    strips.setdefault(round(c[oth], 3), []).append(n)
                widths = _strip_widths(strips)
                for yo, ns in strips.items():
                    wtrib = widths.get(yo) or (cfg["SY"] if ax == 0 else cfg["SX"])
                    for face, q, fs in faces:
                        pick = min if (face == "up") == (sgn_w > 0) else max
                        n = pick(ns, key=lambda nn: crd[nn][ax])
                        Ftot = f * float(q) * wtrib * h_t / 1000.0 * fs          # N along +axis
                        v = [0.0] * 6; v[ax] = Ftot
                        ops.load(n, *v)
                        tot["wall_N"] += Ftot
    return tot


def _responses(model):
    """{tag: np.array} -- localForce (12) for beam-columns, [N] for trusses."""
    R = {}
    for c in model["cols"]:
        R[c["tag"]] = _np.array(ops.eleResponse(c["tag"], "localForce"), dtype=float)
    for b in model["braces"]:
        R[b["tag"]] = _np.array([ops.basicForce(b["tag"])[0]], dtype=float)
    for bm in model["beams"]:
        for t in bm["segs"]:
            R[t] = _np.array(ops.eleResponse(t, "localForce"), dtype=float)
    return R


def _solve_newton():
    ops.constraints("Transformation"); ops.numberer("RCM"); ops.system("UmfPack")
    ops.test("NormDispIncr", 1e-7, 200); ops.algorithm("Newton")
    ops.integrator("LoadControl", 1.0); ops.analysis("Static")
    return ops.analyze(1)


def _to_linear_increments():
    ops.loadConst("-time", 0.0)
    ops.wipeAnalysis()
    ops.constraints("Transformation"); ops.numberer("RCM"); ops.system("UmfPack")
    ops.test("NormDispIncr", 1e-7, 10)
    ops.algorithm("Linear", "-factorOnce")
    ops.integrator("LoadControl", 1.0); ops.analysis("Static")
    try:
        ops.timeSeries("Constant", 77)
    except Exception:
        pass


def notional_loads(lev, notional, model):
    """IS 800 4.3.6: 0.5 % of the factored gravity at each level, at the diaphragm master."""
    if not notional:
        return {}
    d = notional.get("dir"); s = float(notional.get("sign", 1)); r = float(notional.get("ratio", 0.005))
    out = {}
    for k, W in lev.items():
        f = s * r * W
        out[mtag(k)] = (f, 0.0, 0.0, 0.0, 0.0, 0.0) if d == "X" else (0.0, f, 0.0, 0.0, 0.0, 0.0)
    return out


def _grav_state_key(c):
    m = getattr(c, "meta", {}) or {}
    return (round(float(c[1]), 6), round(float(c[2]), 6), round(float(c[3]), 6),
            round(float(m.get("fS") or 0.0), 6), round(float(m.get("fC") or 0.0), 6),
            round(float(m.get("fEv") or 0.0), 9), tuple(m.get("crane_pattern") or ()),
            tuple(m.get("snow_pattern") or ()))


def one_way_gravity(cfg, b, fD, fL, fLr, fS=0.0, fEv=0.0, present=None):
    """One-way girder gravity (Mg = w L^2/8, Vg = w L/2) in N-mm (WP2.1: kN/m2 x mm / 1000 = N/mm).
    With cfg['deck_span'] declared, beams parallel to the deck span get no deck load, or their secondary strip when
    cfg['secondary_spacing_mm'] is declared (H13).  H13 (HR-C-03): the tributary is taken from the bays actually
    bounding the beam (edge girder: half bay) with the actual xcoords / ycoords, when the beam's grid position
    (b['i'], b['j']) and the level footprint (``present`` = {k: {(i, j)}}, or b['present_k']) are known; otherwise
    the legacy full bay width."""
    k = b["k"]; L = b["L"]
    D, Lf, Lr, S = floor_pressures(cfg, k)
    p = fD * D + fL * Lf + fLr * Lr + fS * S + fEv * (D + _table10_fraction(Lf) * Lf)
    ds = _deck_span(cfg)
    pk = b.get("present_k")
    if pk is None and present is not None:
        pk = present.get(k, set())
    tw = None
    if pk is not None and b.get("i") is not None and b.get("j") is not None:
        tw = one_way_trib_mm(cfg, pk, int(b["i"]), int(b["j"]), b["dir"])
    if tw is not None:
        trib = tw
    elif ds is not None and b["dir"] == ds:
        trib = 0.0
    else:
        trib = cfg["SY"] if b["dir"] == "X" else cfg["SX"]
    w = p * trib / 1000.0
    if tw is not None and cfg.get("clad") and len(adjacent_panels(cfg, pk, int(b["i"]), int(b["j"]), b["dir"])) == 1:
        NF = len(cfg["heights"])                     # perimeter beam: cladding line load, as apply_gravity_state
        th = cfg["heights"][k - 1] / 2.0 if k == NF else cfg["heights"][k - 1]
        w += (fD + fEv) * float(cfg["clad"]) * th / 1000.0
    A = b.get("_A") or 0.0
    w += (fD + fEv) * A * STEEL_UNIT_WEIGHT_N_PER_MM3
    return w * L * L / 8.0, w * L / 2.0


REC_FIELDS = ("N", "Mmaj", "Mmin", "V", "Mmaj_i", "Mmaj_j", "Mmin_i", "Mmin_j", "Mmaj_sag_max", "Vmaj", "Vmin",
              "N_LAT", "V_LAT")
# N_LAT / V_LAT (WP6, EBF): the LATERAL-load part of the member axial force / major shear in this combination
# (static lateral increment or fLat x RSA response) -- the EL share that IS 18168 12.3.2.2 / 12.3.4.5 amplify to
# the link overstrength. Zero on gravity-only combinations; records without the field read as 0.0.


def _lateral_axial_shear(model, RL):
    """{fset: (N_LAT, V_LAT)} from a lateral-only response dict (same element responses as member_records)."""
    out = {}
    for c in model["cols"]:
        lf = RL[c["tag"]]
        out[frozenset((c["n1"], c["n2"]))] = (float(lf[6]), max(abs(lf[1]), abs(lf[7])))
    for b in model["braces"]:
        out[frozenset((b["n1"], b["n2"]))] = (float(RL[b["tag"]][0]), 0.0)
    for b in model["beams"]:
        segs = b["segs"]
        out[frozenset((b["A"], b["B"]))] = (float(RL[segs[0]][6]),
                                           max(max(abs(RL[t][2]), abs(RL[t][8])) for t in segs))
    return out


def member_records(model, R, cfg, case_grav, floor_system):
    """Per parent member {fset: rec} with rec fields REC_FIELDS (N tension +, N-mm, N).

    Columns: major axis = local z, end moments in the element's vector convention (M(0) = -f_i,
    M(L) = +f_j) -- consistent along the member, so psi = Mj/Mi gives the curvature for Cm.
    Beams: major axis = local y, BENDING-MOMENT-DIAGRAM values with sagging positive
    (sag_i = +f_i, sag_j = -f_j, checked numerically), Mmaj_sag_max = largest sagging value along
    the span.  One-way girder: Mg = w L^2/8 and Vg = w L/2 in N-mm (WP2.1) bound the FE values."""
    out = {}
    for c in model["cols"]:
        lf = R[c["tag"]]
        N = lf[6]
        Mzi, Mzj = -lf[5], lf[11]
        Myi, Myj = -lf[4], lf[10]
        Vmaj = max(abs(lf[1]), abs(lf[7])); Vmin = max(abs(lf[2]), abs(lf[8]))
        out[frozenset((c["n1"], c["n2"]))] = (N, max(abs(Mzi), abs(Mzj)), max(abs(Myi), abs(Myj)),
                                             max(Vmaj, Vmin), Mzi, Mzj, Myi, Myj, 0.0, Vmaj, Vmin)
    for b in model["braces"]:
        out[frozenset((b["n1"], b["n2"]))] = (float(R[b["tag"]][0]),) + (0.0,) * 10
    fD, fL, fLr, fS, fC, fEv = case_grav[:6]
    for b in model["beams"]:
        segs = b["segs"]
        Nb = R[segs[0]][6]
        sag = []
        Mmin = Vmaj = Vmin = 0.0
        for t in segs:
            lf = R[t]
            sag += [lf[4], -lf[10]]
            Mmin = max(Mmin, abs(lf[5]), abs(lf[11]))
            Vmaj = max(Vmaj, abs(lf[2]), abs(lf[8]))
            Vmin = max(Vmin, abs(lf[1]), abs(lf[7]))
        Mi, Mj = sag[0], sag[-1]
        Mmaj = max(abs(x) for x in sag)
        sag_max = max(sag)
        Mni, Mnj = -R[segs[0]][5], R[segs[-1]][11]
        if floor_system != "two-way":
            Mg, Vg = one_way_gravity(cfg, b, fD, fL, fLr, fS, fEv, present=model.get("present"))
            if _deck_span(cfg) is None and Mg > sag_max:
                sag_max = Mg                                # legacy conservative one-way bound
                Mmaj = max(Mmaj, Mg)
            Vmaj = max(Vmaj, Vg)
        out[frozenset((b["A"], b["B"]))] = (Nb, Mmaj, Mmin, max(Vmaj, Vmin), Mi, Mj, Mni, Mnj, sag_max, Vmaj, Vmin)
    return out


def combo_forces_for_member_check(records, kind):
    """{label: rec} -> the combo_forces list of india_is800.member_check_is800 (HR-MEMBERS API):
    P_N compression +, Mz = major axis, My = minor axis, Mz_mid (beams), Vy = major shear."""
    out = []
    for lab, r in records.items():
        r = list(r) + [0.0] * (len(REC_FIELDS) - len(r))
        d = dict(zip(REC_FIELDS, r))
        cf = {"combo": lab, "P_N": -d["N"], "Mz_i_Nmm": d["Mmaj_i"], "Mz_j_Nmm": d["Mmaj_j"],
              "My_i_Nmm": d["Mmin_i"], "My_j_Nmm": d["Mmin_j"], "Vy_N": d["Vmaj"], "Vz_N": d["Vmin"],
              "P_LAT_N": -d["N_LAT"], "V_LAT_N": d["V_LAT"]}
        if kind == "beam":
            cf["Mz_mid_Nmm"] = d["Mmaj_sag_max"]
        out.append(cf)
    return out


# IS 875 (Part 2):1987 3.2.1 (corpus: spec:IS_875_Part_2_1987:standard:3.2.1, pdf p. 14) -- reduction in the total
# distributed imposed load on all floors carried by a column, by the number of floors (including the roof) carried:
IS875_2_321_REDUCTION = ((1, 0.0), (2, 0.10), (3, 0.20), (4, 0.30), (10, 0.40), (10 ** 6, 0.50))
IS875_2_321_CITE = ("IS 875 (Part 2):1987 3.2.1: reduction in total distributed imposed load on all floors carried by "
                    "a column: 1 floor 0 %, 2 10 %, 3 20 %, 4 30 %, 5-10 40 %, over 10 50 % (not for storage / "
                    "warehouses / garages, 3.2.1.1; not for partitions, plant or machinery)")


def imposed_load_reduction_321(n_floors):
    n = int(n_floors)
    for lim, r in IS875_2_321_REDUCTION:
        if n <= lim:
            return r
    return 0.50


def column_imposed_load_reduction_factors(cfg):
    """{column element tag: r} for cfg['column_imposed_load_reduction'] (opt-in, IS 875-2 3.2.1): a column between
    levels k-1 and k carries the floors k .. NF (the roof counts as a floor).  Storage buildings are refused
    (3.2.1.1)."""
    if not cfg.get("column_imposed_load_reduction"):
        return {}
    if cfg.get("storage") or cfg.get("storage_levels"):
        raise ValueError("IS 875-2 3.2.1.1: no imposed-load reduction for storage buildings / warehouses")
    NF = len(cfg["heights"])
    out = {}
    info = eng.build(cfg, "Linear")
    for (t, kind, sec, n1, n2) in info["ele"]:
        if kind == "col":
            k_top = max(n1, n2) // 100000
            out[t] = imposed_load_reduction_321(NF - k_top + 1)
    return out


def solve_cases_si(cfg, cases, nseg=6, floor_system="one-way", rsa=None, keep_responses=False, service=False):
    """Run every strength case (service=False) or every serviceability case (service=True; used for the IS 800
    10.4.3 service-load slip check of HSFG connections).  Returns ({label: {fset: rec}}, kinds, info).

    rsa = {"X": {tag: |E| array}, "Y": ...} scaled RSA element responses (engine3d.rsa_analysis)."""
    per_case = {}
    info = {"gravity_states": 0, "levels": {}}
    groups = {}
    for c in cases:
        m = getattr(c, "meta", {}) or {}
        if bool(m.get("service")) != bool(service):
            continue
        groups.setdefault(_grav_state_key(c), []).append(c)
    kinds = None
    llr = column_imposed_load_reduction_factors(cfg)          # IS 875-2 3.2.1 (opt-in), {column tag: r}
    for gk, cs in groups.items():
        fD, fL, fLr, fS, fC, fEv, cpat, spat = gk
        model = build_static(cfg, "PDelta", nseg)
        if kinds is None:
            kinds = _member_kinds(model)
        N_LL = {}
        if llr and fL:
            # imposed FLOOR load alone (no partitions, cladding, self-weight, roof imposed): the part of the column
            # axial force that IS 875-2 3.2.1 lets the designer reduce by the number of floors carried
            c2 = dict(cfg, partition_load_kNm2=0.0, clad=0.0)
            ops.timeSeries("Linear", 1); ops.pattern("Plain", 1, 1)
            apply_gravity_state(c2, model, 0.0, fL, 0.0, 0.0, 0.0, 0.0, self_weight=False)
            if _solve_newton() != 0:
                raise RuntimeError("imposed-load state %s did not converge" % (gk,))
            RLL = _responses(model)
            N_LL = {c["tag"]: float(RLL[c["tag"]][6]) for c in model["cols"]}
            ops.wipe()
            model = build_static(cfg, "PDelta", nseg)
        ops.timeSeries("Linear", 1); ops.pattern("Plain", 1, 1)
        lev = apply_gravity_state(cfg, model, fD, fL, fLr, fS, fC, fEv,
                                  self_weight=cfg.get("self_weight", True), crane_pattern=cpat or None,
                                  snow_pattern=spat or None)
        ok = _solve_newton()
        if ok != 0:
            raise RuntimeError("gravity state %s did not converge (P-Delta)" % (gk,))
        info["gravity_states"] += 1
        info["levels"][gk] = lev
        RG = _responses(model)
        _to_linear_increments()
        ptag = 1000
        for c in cs:
            m = getattr(c, "meta", {}) or {}
            loads = {}
            for k, (fx, fy, mz) in (c[4] or {}).items():
                loads[mtag(int(k))] = (fx, fy, 0.0, 0.0, 0.0, mz)
            for nd, v in notional_loads(lev, m.get("notional"), model).items():
                a = loads.get(nd, (0.0,) * 6)
                loads[nd] = tuple(x + y for x, y in zip(a, v))
            mw = m.get("member_wind")
            if loads or mw:
                ptag += 1
                ops.pattern("Plain", ptag, 77)
                for nd, v in loads.items():
                    ops.load(int(nd), *v)
                if mw:
                    member_wind_loads(cfg, model, mw, float(m.get("fWM") or 0.0))
                ops.analyze(1)
                R1 = _responses(model)
                ops.remove("loadPattern", ptag)
                ops.analyze(1)                            # linear step back to the gravity state
                RC = {t: RG[t] + (R1[t] - RG[t]) for t in RG}
            else:
                RC = RG
            rs = m.get("rsa") or {}
            if rs:
                if not rsa:
                    raise RuntimeError("case %r needs RSA forces but no RSA analysis was supplied" % c[0])
                RC = dict(RC)
                for d, f in rs.items():
                    E_ = rsa.get(d)
                    if E_ is None:
                        raise RuntimeError("RSA direction %s missing" % d)
                    for t in RC:
                        if t in E_:
                            RC[t] = RC[t] + float(f) * E_[t]
            recs = member_records(model, RC, cfg, gk, floor_system)
            if RC is not RG:
                lat = _lateral_axial_shear(model, {t: RC[t] - RG[t] for t in RG})
                recs = {fs: tuple(r) + lat.get(fs, (0.0, 0.0)) for fs, r in recs.items()}
            if N_LL:
                # IS 875-2 3.2.1: column axial = N - r x N_imposed (tension-positive records; only the axial force)
                for col in model["cols"]:
                    r_ = llr.get(col["tag"], 0.0)
                    fs = frozenset((col["n1"], col["n2"]))
                    if r_ and fs in recs:
                        rec = list(recs[fs]); rec[0] = rec[0] - r_ * N_LL[col["tag"]]; recs[fs] = tuple(rec)
            per_case[c[0]] = recs
    return per_case, kinds or {}, info


def envelope_from_records(per_case, kinds, cases):
    """Envelope + governing combination + per-combination records per member."""
    env = {}
    col_only = {c[0]: (bool(c[5]) or "col_only" in ((getattr(c, "meta", {}) or {}).get("tags") or []))
                for c in cases}
    conn_only = {c[0]: "conn_only" in ((getattr(c, "meta", {}) or {}).get("tags") or []) for c in cases}
    for lab, res in per_case.items():
        for fs, rec in res.items():
            kind = kinds.get(fs, ("beam", None))[0]
            e = env.setdefault(fs, dict(comp=0.0, tens=0.0, Mz=0.0, My=0.0, V=0.0, combo="", score=-1.0,
                                        records={}, conn={}))
            e["records"][lab] = [round(float(x), 1) for x in rec]
            if col_only.get(lab) and kind != "col":
                e["conn"][lab] = [round(float(x), 1) for x in rec]     # 12.2.3 forces kept for connections
                continue
            N, Mz, My, V = rec[0], rec[1], rec[2], rec[3]
            e["comp"] = max(e["comp"], max(-N, 0.0)); e["tens"] = max(e["tens"], max(N, 0.0))
            e["Mz"] = max(e["Mz"], abs(Mz)); e["My"] = max(e["My"], abs(My)); e["V"] = max(e["V"], abs(V))
            sc = abs(N) if kind in ("col", "brace") else abs(Mz)
            if sc > e["score"]:
                e["score"] = sc; e["combo"] = lab
    return env


def demand_envelope_si(cfg, cases, nseg=6, floor_system=None, cache_dir=None, rsa=None):
    floor_system = (floor_system or cfg.get("floor_system") or "one-way")
    floor_system = "two-way" if "two" in str(floor_system).lower() else "one-way"
    key = None
    if cache_dir:
        try:
            info0 = eng.build(cfg, "Linear")
            sig = repr((sorted((e[1], e[2], e[3], e[4]) for e in info0["ele"]), cfg.get("heights"), cfg.get("SX"),
                        cfg.get("SY"), cfg.get("D_floor"), cfg.get("D_roof"), cfg.get("L_floor"), cfg.get("Lr"),
                        cfg.get("snow"), cfg.get("clad"), cfg.get("deck_span"), cfg.get("partition_load_kNm2"),
                        # H13 / H14 / H50 load-distribution inputs
                        cfg.get("secondary_spacing_mm"), cfg.get("roof_levels"), cfg.get("ridge"),
                        cfg.get("snow_partial"), cfg.get("nodal_imposed_loads"), cfg.get("xcoords"),
                        cfg.get("ycoords"),
                        floor_system, nseg, [(tuple(c)[:4], sorted((c[4] or {}).items()), c[5],
                                              sorted(((getattr(c, "meta", {}) or {}).items()), key=str)
                                              .__repr__()) for c in cases],
                        {d: sorted((t, list(v)) for t, v in a.items()) for d, a in (rsa or {}).items()}))
            key = "SI" + _hashlib.md5(sig.encode()).hexdigest()
            p = _os.path.join(cache_dir, "_demand_cache_si.json")
            d = _json.load(open(p))
            if d.get("key") == key:
                env = {frozenset(int(x) for x in k.split("|")): v for k, v in d["env"].items()}
                kinds = {frozenset(int(x) for x in k.split("|")): tuple(v) for k, v in d["kinds"].items()}
                return env, kinds
        except Exception:
            pass
    per_case, kinds, _info = solve_cases_si(cfg, cases, nseg, floor_system, rsa=rsa)
    env = envelope_from_records(per_case, kinds, cases)
    if cache_dir and key:
        try:
            _os.makedirs(cache_dir, exist_ok=True)
            _json.dump({"key": key,
                        "env": {"|".join(str(n) for n in fs): v for fs, v in env.items()},
                        "kinds": {"|".join(str(n) for n in fs): list(v) for fs, v in kinds.items()}},
                       open(_os.path.join(cache_dir, "_demand_cache_si.json"), "w"))
        except Exception:
            pass
    return env, kinds
