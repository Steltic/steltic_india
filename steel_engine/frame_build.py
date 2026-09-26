"""frame_build.py -- JSON-declared frame builder (shared by the HR and the CFS India engines; X06, E11 / HR-B-20).

A generic cfg['custom_build'] for plans that are not a full NX x NY rectangle (L / Z / T / U / cruciform / split-level /
podium / high-bay) or whose lateral system needs chevron EBF links, moment lines, per-line sections or stepped bases --
the frame_build of the GOLD-HR-B packages driven by a JSON-declarative `gold` block instead of Python callables, so it
can also cross the subprocess boundary of the CFS engine (india_cfs_lateral -> hr_vendor_runner; the CFS module
india_cfs_frame_build is a thin wrapper that loads this file from its hr_vendor copy).

HR use (see example_build_ebf.py for a complete EBF job):
    import frame_build as FB
    FB.attach_gold(cfg, gold)          # cfg['custom_build'] = FB.frame_build, cfg['plan'], cfg['xcoords'] / ['ycoords']
    pipeline.design_and_report(name, cfg)
CFS use: hr_vendor_runner calls attach(cfg, spec) with the CFS lateral spec (spec['gold'] = the block below).

gold = {
  "xcoords_m": [...], "ycoords_m": [...],            # optional non-uniform grid (else i * bay_x, j * bay_y)
  "present": {"default": [[i, j], ...], "1": [...], "3-5": [...]},   # column nodes present at storey k (k = 0 -> storey 1;
                                                        # an explicit "0" key = the base (foundation) node set)
  "stepped_bases": {"1": [[i, j], ...]},               # split-level site: these columns are founded on the grade at level k (fixed there,
                                                        # outside that level's diaphragm); "omit_beams_at": {"1": [...]} = no beams into them
  "xbays": {"1-4": [["X", i, j], ...]},              # concentric X-braced bays (both diagonals) per storey range
  "ebf_bays": {"1-4": [["X", i, j], ...]}, "e_link_mm": 900.0, "ebf_beam_column_pinned": false,
  "ebf_beam_sec": {"X": {"1-4": sec}, "Y": {...}}, "ebf_link_sec": {...}, "ebf_brace_sec": {"1-4": sec},
                                                        # centre-link chevron EBF bay: beam - link (ElasticTimoshenkoBeam) - beam,
                                                        # two braces from the storey-below column nodes to the link ends; each link is
                                                        # declared in info['links'] (tag, e_mm, bay_L_mm, brace/beam/column tags,
                                                        # IS 18168 11.4 stiffeners, 12.3.1 / 12.3.3.2 flags) for ebf_link_checks
  "brace_sec": {"1-4": sec},
  "moment_lines": [["X", j], ["Y", i]],             # rigid beam-column joints along a frame line (else simple shear joints)
  "col_sec": {"lateral": {"1-4": sec}, "gravity": {"1-4": sec}}, "beam_sec": {"floor_X": sec | {"1-2": sec, "3-8": sec}, "floor_Y": ..,
             "roof_X": sec, "roof_Y": sec},                     # beam groups may be storey-ranged like col_sec
  "col_sec_by_line": {"X0": {"1-4": sec}, "Y3": sec, "2,0": sec},   # per-line (or per-node "i,j") overrides, e.g. stiffer
  "beam_sec_by_line": {"X0": {"1-4": sec}, "Y3": sec},              # end frames; line "Xj" = y-grid line j, "Yi" = x-grid line i
  "sfrs_base": "fixed" | "pinned" | {"X0": "pinned", "Y2": "fixed", "1,0": "pinned", "default": "fixed"},
                                                        # SFRS column bases (default cfg / spec base, else fixed)
  "max_beam_span_m": 8.0,                               # beams join CONSECUTIVE present nodes on a grid line up to this
                                                        # span (default = the largest grid bay, i.e. adjacent nodes only)
  "free_nodes": {"2": [[i, j], ...]},                   # nodes of level k kept out of that level's rigid diaphragm
  "plan_area_m2": 1200.0 | {"1": 800.0, "2": 1200.0},   # declared floor / roof plan area per level (CFS framed-area check)
  "voids_m2": {"1": 40.0},                              # declared voids (stair / lift / double height) per level
  "gravity_base": "pinned" | "fixed", "default_strong": "X",
  "roof_planes": [{"axis": "X", "eave_coords_m": [0, 24], "ridge_coord_m": 12, "eave_z_m": 8, "ridge_z_m": 11,
                   "lines": [0, 1, 2], "rafter_sec": sec, "ridge_sec": sec}],   # X02: true-slope pitched roof (apex
                                                        # nodes, rafters, eave spread free) -> cfg['roof_planes'] in mm;
                                                        # *_mm keys are taken as they are
  "roof_regions": {"1": [[i, j], ...]} }                # X02: roof bays of an intermediate level -> cfg['roof_regions']
Columns run between the consecutive levels at which their node exists (a high-bay column passes a level where the
node is absent).  Node tags: engine3d.ntag(i, j, k) / mtag(k); EBF link-end nodes k*100000 + 50000/60000 + i*100 + j (X)
and 70000/80000 + j*100 + i (Y).  Returns the standard info dict + 'links', 'bases', 'framed_area_m2'.
"""
from __future__ import annotations


def _rng_pick(groups, k):
    for rng, v in (groups or {}).items():
        if rng == "default":
            continue
        a, _, b = str(rng).partition("-")
        a = int(a); b = int(b) if b else a
        if a <= k <= b:
            return v
    return (groups or {}).get("default")


def make_gold(spec):
    """JSON gold block + section maps of the CFS spec -> the callables frame_build reads from cfg['_gold']."""
    g = spec["gold"]
    NX, NY = int(spec["NX"]), int(spec["NY"])
    NF = len(spec["heights_m"])
    full = [[i, j] for i in range(NX + 1) for j in range(NY + 1)]
    pres_spec = g.get("present") or {"default": full}

    def present(k):
        kk = k if (k == 0 and "0" in pres_spec) else (1 if k == 0 else k)      # an explicit "0" key = the base (foundation) node set
        P = _rng_pick(pres_spec, kk)
        if P is None:
            P = pres_spec.get("default", full)
        return {tuple(p) for p in P}

    def xbays(k):
        return [tuple([d, int(i), int(j)]) for (d, i, j) in (_rng_pick(g.get("xbays"), k) or [])]

    def ebf_bays(k):
        return [tuple([d, int(i), int(j)]) for (d, i, j) in (_rng_pick(g.get("ebf_bays"), k) or [])]

    mset = {(m[0], int(m[1])) for m in (g.get("moment_lines") or spec.get("moment_lines") or [])}
    lateral_cols = set()
    for k in range(1, NF + 1):
        for (d, i, j) in xbays(k) + ebf_bays(k):
            lateral_cols.add((i, j)); lateral_cols.add((i + 1, j) if d == "X" else (i, j + 1))
    for (d, kk) in mset:
        for q in range((NX if d == "X" else NY) + 1):
            lateral_cols.add((q, kk) if d == "X" else (kk, q))

    def sfrs_col(i, j):
        return (i, j) in lateral_cols

    col_groups = g.get("col_sec") or spec.get("col_sec") or {}
    beam_groups = g.get("beam_sec") or spec.get("beam_sec") or {}
    col_by_line = g.get("col_sec_by_line") or {}
    beam_by_line = g.get("beam_sec_by_line") or {}

    def _grp(v, k):
        return _rng_pick(v, k) if isinstance(v, dict) else v

    # frame lines on which a column is part of the SFRS ("Xj" = the y-grid line j along X, "Yi" = the x-grid line i)
    col_lines = {}
    for k in range(1, NF + 1):
        for (d, i, j) in xbays(k) + ebf_bays(k):
            for n in ((i, j), ((i + 1, j) if d == "X" else (i, j + 1))):
                col_lines.setdefault(n, set()).add("X%d" % j if d == "X" else "Y%d" % i)
    for (d, kk) in mset:
        for q in range((NX if d == "X" else NY) + 1):
            col_lines.setdefault((q, kk) if d == "X" else (kk, q), set()).add("%s%d" % (d, kk))

    def col_sec(i, j, k):
        for key in ("%d,%d" % (i, j), "Y%d" % i, "X%d" % j):     # C11: per-node / per-line override first
            if key in col_by_line:
                v = _grp(col_by_line[key], k)
                if v:
                    return v
        grp = col_groups.get("lateral" if sfrs_col(i, j) else "gravity") or {}
        return _rng_pick(grp, k) or spec["col"]

    def beam_sec(i, j, k, dirn):
        key = ("X%d" % j) if dirn == "X" else ("Y%d" % i)
        if key in beam_by_line:
            v = _grp(beam_by_line[key], k)
            if v:
                return v
        roof = (k == NF)
        v = beam_groups.get(("roof" if roof else "floor") + "_" + dirn) or beam_groups.get("roof" if roof else "floor")
        return _grp(v, k) or spec["beam"]          # C11: a storey-ranged group {"1-2": sec, "3-8": sec} like col_sec

    base_decl = g.get("sfrs_base") or spec.get("base") or "fixed"

    def sfrs_base(i, j):
        """C11: base fixity of an SFRS column -- gold.sfrs_base (string or per node / line dict) else lateral_frame.base."""
        if not isinstance(base_decl, dict):
            return str(base_decl)
        if "%d,%d" % (i, j) in base_decl:
            return str(base_decl["%d,%d" % (i, j)])
        vals = {str(base_decl[ln]) for ln in col_lines.get((i, j), ()) if ln in base_decl}
        if len(vals) > 1:
            raise ValueError("gold.sfrs_base: column (%d, %d) is on frame lines %s with conflicting bases %s -- declare the "
                             "node key '%d,%d'" % (i, j, sorted(col_lines.get((i, j), ())), sorted(vals), i, j))
        if vals:
            return vals.pop()
        return str(base_decl.get("default", spec.get("base") or "fixed"))

    def col_strong(i, j):
        for (d, kk) in mset:
            if (d == "X" and j == kk) or (d == "Y" and i == kk):
                return d
        for k in range(1, NF + 1):
            for (d, bi, bj) in xbays(k) + ebf_bays(k):
                if d == "X" and j == bj and i in (bi, bi + 1):
                    return "X"
                if d == "Y" and i == bi and j in (bj, bj + 1):
                    return "Y"
        return g.get("default_strong", spec.get("default_strong", "X"))

    def releases(i, j, k, dirn):
        if (dirn, j if dirn == "X" else i) in mset:
            return ("none", "none")
        return ("both", "none")

    def brace_sec(k):
        return _rng_pick(g.get("brace_sec"), k) or spec.get("brace")

    stepped = {int(k): {tuple(p) for p in v} for k, v in (g.get("stepped_bases") or {}).items()}   # split-level: supports at level k
    omit = {int(k): {tuple(p) for p in v} for k, v in (g.get("omit_beams_at") or {}).items()}      # no beams into these nodes at level k

    free = {int(k): {tuple(p) for p in v} for k, v in (g.get("free_nodes") or {}).items()}          # C11: out of the diaphragm
    out = {"present": present, "sfrs_col": sfrs_col, "col_sec": col_sec, "beam_sec": beam_sec, "col_strong": col_strong,
           "releases": releases, "xbays": xbays, "brace_sec": brace_sec, "gravity_base": g.get("gravity_base", "pinned"),
           "lateral_cols": lateral_cols, "stepped_bases": stepped, "omit_beams_at": omit, "sfrs_base": sfrs_base,
           "free_nodes": free, "max_beam_span_m": g.get("max_beam_span_m")}
    if g.get("ebf_bays"):
        out.update({"ebf_bays": ebf_bays, "e_link_mm": float(g["e_link_mm"]), "ebf_beam_column_pinned": bool(g.get("ebf_beam_column_pinned")),
                    "ebf_beam_sec": lambda dirn, k: _rng_pick((g.get("ebf_beam_sec") or {}).get(dirn), k),
                    "ebf_link_sec": lambda dirn, k: _rng_pick((g.get("ebf_link_sec") or {}).get(dirn), k),
                    "ebf_brace_sec": lambda k: _rng_pick(g.get("ebf_brace_sec"), k)})
    return out


_M_KEYS = {"eave_coords_m": "eave_coords_mm", "ridge_coord_m": "ridge_coord_mm", "eave_z_m": "eave_z_mm",
           "ridge_z_m": "ridge_z_mm", "extent_m": "extent_mm"}


def roof_planes_mm(raw):
    """X02: CFS / gold roof planes with metre keys (eave_coords_m, ridge_coord_m, eave_z_m, ridge_z_m, extent_m) -> the
    HR cfg['roof_planes'] (mm keys); *_mm keys and the other fields pass through unchanged."""
    out = []
    for r in raw or []:
        d = {}
        for k, v in dict(r).items():
            if k in _M_KEYS:
                d[_M_KEYS[k]] = [float(x) * 1000.0 for x in v] if isinstance(v, (list, tuple)) else float(v) * 1000.0
            else:
                d[k] = v
        out.append(d)
    return out


def attach(cfg, spec):
    """Wire the builder into an HR cfg from a spec (the CFS lateral spec; hr_vendor_runner calls it after build_cfg).
    The cfg must already be in N-mm (xcoords_m / ycoords_m are converted to mm here).  HR jobs use attach_gold."""
    g = spec["gold"]
    gold = make_gold(spec)
    if g.get("roof_planes"):
        cfg["roof_planes"] = roof_planes_mm(g["roof_planes"])          # X02
    if g.get("roof_regions"):
        cfg["roof_regions"] = {int(k): [tuple(b) for b in v] for k, v in dict(g["roof_regions"]).items()}
    cfg["_gold"] = gold
    cfg["custom_build"] = frame_build
    cfg["plan"] = lambda k, NX_, NY_: gold["present"](k)
    if g.get("xcoords_m"):
        cfg["xcoords"] = [float(x) * 1000.0 for x in g["xcoords_m"]]
    if g.get("ycoords_m"):
        cfg["ycoords"] = [float(y) * 1000.0 for y in g["ycoords_m"]]
    cfg["braces"] = None          # braces are drawn by the builder (xbays / ebf_bays), not by the regular-grid callable
    cfg["sway_frame"] = bool(g.get("moment_lines") or spec.get("moment_lines"))
    if g.get("ebf_bays"):
        cfg["brace_config"] = "chevron"
    return cfg


def spec_from_cfg(cfg, gold):
    """The spec make_gold / attach read, from an HR cfg (NX, NY, heights, col / beam / brace fallbacks, base,
    moment_lines, default_strong) and the gold block."""
    return {"NX": cfg["NX"], "NY": cfg["NY"], "heights_m": list(cfg["heights"]), "gold": gold,
            "col": cfg.get("col"), "beam": cfg.get("beam"), "brace": cfg.get("brace"), "base": cfg.get("base"),
            "moment_lines": cfg.get("moment_lines"), "default_strong": cfg.get("default_strong", "X")}


def attach_gold(cfg, gold):
    """HR entry point: wire this builder into an HR cfg from a JSON gold block (see the module docstring).  The cfg
    geometry is normalised to N-mm first (india_units.apply_si_geometry, idempotent) so the gold xcoords_m /
    ycoords_m (metres) land in mm exactly once.  Returns cfg."""
    import india_units as IU
    IU.apply_si_geometry(cfg)
    cfg["gold"] = gold
    return attach(cfg, spec_from_cfg(cfg, gold))



def _cells_area(NX, NY, P, XY):
    """Plan area of the grid cells whose four corner nodes are all present (the framed floor / roof plate)."""
    a = 0.0
    for i in range(NX):
        for j in range(NY):
            if {(i, j), (i + 1, j), (i, j + 1), (i + 1, j + 1)} <= set(P):
                (x0, y0), (x1, y1) = XY(i, j), XY(i + 1, j + 1)
                a += abs(x1 - x0) * abs(y1 - y0)
    return a


def framed_area_m2(spec, k):
    """C06: framed plan area (m2) of level k of the frame that this builder (gold) or the regular grid builds."""
    NX, NY = int(spec["NX"]), int(spec["NY"])
    g = spec.get("gold")
    xs = [float(x) for x in (g or {}).get("xcoords_m") or [i * float(spec["bay_x_m"]) for i in range(NX + 1)]]
    ys = [float(y) for y in (g or {}).get("ycoords_m") or [j * float(spec["bay_y_m"]) for j in range(NY + 1)]]
    XY = lambda i, j: (xs[i], ys[j])
    if g:
        P = make_gold(spec)["present"](k)
    else:
        P = {(i, j) for i in range(NX + 1) for j in range(NY + 1)}
    return _cells_area(NX, NY, P, XY)



def _xy(cfg, i, j):
    xco = cfg.get("xcoords"); yco = cfg.get("ycoords")
    return ((xco[i] if xco else i * cfg["SX"]), (yco[j] if yco else j * cfg["SY"]))


def frame_build(cfg, transf="PDelta"):
    """Generic custom_build driven by cfg['_gold'] (port of gold_common.frame_build, GOLD-HR-B):
      present(k) -> set of (i, j); sfrs_col(i, j) -> fixed base; col_sec(i, j, k); beam_sec(i, j, k, dirn);
      col_strong(i, j); releases(i, j, k, dirn); xbays(k) -> [(dirn, i, j)] X-braced bays; brace_sec(k);
      ebf_bays(k) chevron EBF bays with a centre link (ebf_beam_sec / ebf_link_sec / ebf_brace_sec, e_link_mm,
      IS 18168 11.4 stiffener rule); gravity_base 'pinned' (default) | 'fixed'."""
    import openseespy.opensees as ops
    import engine3d as E
    import sections as S
    g = cfg["_gold"]
    ops.wipe(); ops.model("basic", "-ndm", 3, "-ndf", 6)
    NF = len(cfg["heights"]); NX, NY = cfg["NX"], cfg["NY"]
    z = E.zlevels(cfg)
    XY = lambda i, j: _xy(cfg, i, j)
    pres = {k: set(g["present"](k)) for k in range(NF + 1)}          # floor plates (areas / masses / diaphragms)
    stepped = g.get("stepped_bases") or {}
    node_sets = {k: pres[k] | (stepped.get(k) or set()) for k in range(NF + 1)}   # + grade supports of a split-level site
    rp = cfg.get("roof_planes")                                     # X02: true-slope pitched roof (HR roof_geometry)
    if rp:
        import roof_geometry as RG
    for k in range(NF + 1):
        for (i, j) in node_sets[k]:
            x, y = XY(i, j)
            zl = RG.lifted_z(cfg, k, x, y) if (rp and k) else None   # grid node under a roof plane -> on the slope
            ops.node(E.ntag(i, j, k), x, y, z[k] if zl is None else zl)
    bases = {}
    def _is_fixed(i, j):
        # C11: SFRS columns take gold.sfrs_base / lateral_frame.base (per line), gravity columns gravity_base
        if g["sfrs_col"](i, j):
            return str((g.get("sfrs_base") or (lambda a, b: "fixed"))(i, j)).lower() == "fixed"
        return g.get("gravity_base", "pinned") == "fixed"
    for (i, j) in pres[0]:
        fixed = _is_fixed(i, j)
        ops.fix(E.ntag(i, j, 0), 1, 1, 1, *((1, 1, 1) if fixed else (0, 0, 0)))
        bases[(i, j)] = "fixed" if fixed else "pinned"
    grade_nodes = set()
    for kb, pts_b in stepped.items():                       # split-level site: columns founded on the uphill grade at level kb
        for (i, j) in pts_b:                                # (a column stub below it, if declared in present "0", is a retained basement stub)
            fixed = _is_fixed(i, j)
            ops.fix(E.ntag(i, j, kb), 1, 1, 1, *((1, 1, 1) if fixed else (0, 0, 0)))
            bases[(i, j)] = ("fixed" if fixed else "pinned") + "@L%d" % kb
            grade_nodes.add(E.ntag(i, j, kb))
    omit = g.get("omit_beams_at") or {}
    cm = {}
    for k in range(1, NF + 1):
        pts = [p for p in pres[k] if E.ntag(*p, k) not in grade_nodes] or list(pres[k])
        cx = sum(XY(i, j)[0] for i, j in pts) / len(pts); cy = sum(XY(i, j)[1] for i, j in pts) / len(pts)
        cm[k] = (cx, cy); ops.node(E.mtag(k), cx, cy, z[k]); ops.fix(E.mtag(k), 0, 0, 1, 1, 1, 0)
    et = 1; eles = []; links = []; col_tag = {}
    for i in range(NX + 1):
        for j in range(NY + 1):
            sd = g["col_strong"](i, j)
            # C11: a column joins the CONSECUTIVE levels at which its node exists (a high-bay column passes a level
            # where the node is absent, instead of being dropped)
            lv = [k for k in range(NF + 1) if (i, j) in node_sets[k]]
            for ka, kb_ in zip(lv, lv[1:]):
                sec = g["col_sec"](i, j, kb_)
                E.add_column(et, E.ntag(i, j, ka), E.ntag(i, j, kb_), sec, sd)
                eles.append((et, "col", sec, E.ntag(i, j, ka), E.ntag(i, j, kb_)))
                for kk in range(ka + 1, kb_ + 1):
                    col_tag[(i, j, kk)] = et
                et += 1
    ops.uniaxialMaterial("Elastic", 1, E.E)
    xb = g.get("xbays") or (lambda k: [])
    eb = g.get("ebf_bays") or (lambda k: [])
    e_link = float(g.get("e_link_mm") or 0.0)
    # C11: beams join consecutive present nodes of a grid line up to max_beam_span_m (default = the largest grid bay,
    # i.e. adjacent nodes only on a uniform grid); an omitted (grade) node breaks the line
    gx = [XY(i, 0)[0] for i in range(NX + 1)]; gy = [XY(0, j)[1] for j in range(NY + 1)]
    max_bay = max([b - a for a, b in zip(gx, gx[1:])] + [b - a for a, b in zip(gy, gy[1:])] or [0.0])
    max_span = float(g["max_beam_span_m"]) * 1000.0 if g.get("max_beam_span_m") else max_bay
    for k in range(1, NF + 1):
        P = node_sets[k]
        ebays = set(eb(k)); xbays = set(xb(k))
        for dirn in ("X", "Y"):
            pairs = []
            for q in range((NY if dirn == "X" else NX) + 1):
                on = [((p, q) if dirn == "X" else (q, p)) for p in range((NX if dirn == "X" else NY) + 1)]
                on = [n for n in on if n in P]
                for a_, b_ in zip(on, on[1:]):
                    if a_ in omit.get(k, set()) or b_ in omit.get(k, set()):
                        continue
                    span = (XY(*b_)[0] - XY(*a_)[0]) if dirn == "X" else (XY(*b_)[1] - XY(*a_)[1])
                    if span > max_span + 1e-6:
                        continue
                    if rp and RG.plane_spans_segment(cfg, z[k], XY(*a_), XY(*b_)):
                        continue                                    # X02: no tie across a pitched roof
                    pairs.append((a_, b_))
            for ((i, j), b) in pairs:
                A, B = E.ntag(i, j, k), E.ntag(*b, k)
                if (dirn, i, j) in ebays and b == ((i + 1, j) if dirn == "X" else (i, j + 1)):
                    xa, ya = XY(i, j); xb_, yb_ = XY(*b)
                    L = (xb_ - xa) if dirn == "X" else (yb_ - ya)
                    s1 = (L - e_link) / 2.0; s2 = (L + e_link) / 2.0
                    # link-end node tags in their own 10 000 blocks (the (50 + i) * 100 scheme of gold_common collided for i >= 10)
                    if dirn == "X":
                        L1 = k * 100000 + 50000 + i * 100 + j; L2 = k * 100000 + 60000 + i * 100 + j
                        ops.node(L1, xa + s1, ya, z[k]); ops.node(L2, xa + s2, ya, z[k])
                    else:
                        L1 = k * 100000 + 70000 + j * 100 + i; L2 = k * 100000 + 80000 + j * 100 + i
                        ops.node(L1, xa, ya + s1, z[k]); ops.node(L2, xa, ya + s2, z[k])
                    bsec, lsec, brs = g["ebf_beam_sec"](dirn, k), g["ebf_link_sec"](dirn, k), g["ebf_brace_sec"](k)
                    # centre-link chevron EBF: the beam-to-column joint may be a simple (pinned) connection -- the link is not
                    # adjacent to the column (IS 18168 12.3.4.4 FR joints are for column links); default rigid as in gold_common
                    relA = ("I", "none") if g.get("ebf_beam_column_pinned") else ("none", "none")
                    relB = ("J", "none") if g.get("ebf_beam_column_pinned") else ("none", "none")
                    E.add_beam(et, A, L1, bsec, releases=relA); eles.append((et, "beam", bsec, A, L1)); tb1 = et; et += 1
                    p = S.props(lsec)
                    Avz = (p["d"] - 2 * p["tf"]) * p["tw"]; Avy = 2 * p["bf"] * p["tf"]
                    ops.element("ElasticTimoshenkoBeam", et, L1, L2, E.E, E.Gmod, p["A"], p["J"], p["Ix"], p["Iy"], Avy, Avz, 3)
                    eles.append((et, "beam", lsec, L1, L2)); tl = et; et += 1
                    E.add_beam(et, L2, B, bsec, releases=relB); eles.append((et, "beam", bsec, L2, B)); tb2 = et; et += 1
                    brA = S.props(brs)["A"]
                    ops.element("Truss", et, E.ntag(i, j, k - 1), L1, brA, 1); eles.append((et, "brace", brs, E.ntag(i, j, k - 1), L1)); tr1 = et; et += 1
                    ops.element("Truss", et, E.ntag(*b, k - 1), L2, brA, 1); eles.append((et, "brace", brs, E.ntag(*b, k - 1), L2)); tr2 = et; et += 1
                    links.append({"tag": tl, "e_mm": e_link, "bay_L_mm": L, "dir": dirn, "storey": k,
                                  "brace_tags": [tr1, tr2], "beam_tags": [tb1, tb2],
                                  "column_tags": [t for t in (col_tag.get((i, j, k)), col_tag.get((b[0], b[1], k))) if t],
                                  "end_stiffeners": {"both_sides": True, "width_mm": p["bf"] - 2 * p["tw"] + 2.0,
                                                     "t_mm": max(0.75 * p["tw"], 10.0) + 2.0},
                                  "intermediate_stiffener_spacing_mm": round(min(30 * p["tw"] - 0.2 * p["d"], e_link / 2.0) - 5.0),
                                  "braced_both_flanges": True, "connected_to_column": False,
                                  "continuous_link_beam": (bsec == lsec), "doubler": False})
                else:
                    sec = g["beam_sec"](i, j, k, dirn)
                    rel = g["releases"](i, j, k, dirn)
                    E.add_beam(et, A, B, sec, releases=rel); eles.append((et, "beam", sec, A, B)); et += 1
        if rp:                                                      # X02: rafters (eave -> apex -> eave) + ridge members
            et = RG.add_plane_members(cfg, k, XY, node_sets[k], et, eles,
                                      beam_sec=lambda q, kk, d: g["beam_sec"](0 if d == "X" else q, q if d == "X" else 0, kk, d))
        for (dirn, i, j) in sorted(xbays):          # deterministic element tags (set order is hash-seed dependent)
            a = (i, j); b = (i + 1, j) if dirn == "X" else (i, j + 1)
            brs = g["brace_sec"](k); brA = S.props(brs)["A"]
            if a in node_sets[k - 1] and b in node_sets[k]:
                ops.element("Truss", et, E.ntag(*a, k - 1), E.ntag(*b, k), brA, 1)
                eles.append((et, "brace", brs, E.ntag(*a, k - 1), E.ntag(*b, k))); et += 1
            if a in node_sets[k] and b in node_sets[k - 1]:
                ops.element("Truss", et, E.ntag(*a, k), E.ntag(*b, k - 1), brA, 1)
                eles.append((et, "brace", brs, E.ntag(*a, k), E.ntag(*b, k - 1))); et += 1
    info = {"cm": cm, "present": pres, "z": z, "NF": NF, "ele": eles, "links": links, "bases": bases,
            "framed_area_m2": {k: _cells_area(NX, NY, pres[k], XY) / 1e6 for k in range(1, NF + 1)}}
    link_nodes = {}
    for ln in links:
        for (t, kind, sec, n1, n2) in eles:
            if t == ln["tag"]:
                link_nodes.setdefault(ln["storey"], []).extend([n1, n2])
    for k in range(1, NF + 1):
        # grade-level support nodes of a split-level site stay out of the diaphragm constraint (they are fixed)
        freek = (g.get("free_nodes") or {}).get(k) or set()          # C11: declared free nodes stay out of the diaphragm
        sl = [E.ntag(i, j, k) for (i, j) in pres[k] if E.ntag(i, j, k) not in grade_nodes and (i, j) not in freek] + link_nodes.get(k, [])
        # X01: the flexible-diaphragm variant (india_flexible_diaphragm.build_flexible) intercepts the rigidDiaphragm
        # call -- the slave list is the floor plate that gets the deck membrane (free / grade nodes stay out of it)
        if rp:
            RG.tie_diaphragm(cfg, k, E.mtag(k), sl, z[k])          # X02: eave spread free (roof_geometry)
        else:
            ops.rigidDiaphragm(3, E.mtag(k), *sl)
        w = E.floor_w(cfg, k); m = w / E.g
        pts = pres[k]; xs = [XY(i, j)[0] for i, j in pts]; ys = [XY(i, j)[1] for i, j in pts]
        # rotational inertia of the floor plate: the plan extents between the perimeter columns (the +SX / +SY of the HR
        # gold_common version doubled the depth of a single-bay portal and over-stated its torsional period)
        Bx = max(xs) - min(xs); By = max(ys) - min(ys)
        ops.mass(E.mtag(k), m, m, 0.0, 0.0, 0.0, m * (Bx ** 2 + By ** 2) / 12.0)
    return info
