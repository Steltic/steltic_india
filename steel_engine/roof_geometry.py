"""roof_geometry.py -- X02 (HR-E-05, HR-A-15, HR-B-16, CFS-A-15): true-slope pitched roofs and region roofs.

cfg['roof_planes'] = [ {                      # every length in mm (whatever cfg['units'] says)
    'axis': 'X' | 'Y',                         # SPAN direction: the rafters run along this plan axis
    'eave_coords_mm': [lo, hi],                # plan coordinates (along `axis`) of the two eave lines (grid lines)
    'ridge_coord_mm': r,                       # ridge line coordinate along `axis`, lo < r < hi
    'eave_z_mm': ze, 'ridge_z_mm': zr,         # eave elevation (= a storey level z) and ridge elevation (> ze)
    'lines': [j, ...] | 'bays': [(i, j), ...], # frame lines that carry rafters (grid indices across `axis`: j for 'X',
                                               # i for 'Y'); 'bays' = grid cells, their bounding lines; default all
    'level': k,                                # optional; default = the storey level whose z equals eave_z_mm
    'rafter_sec', 'ridge_sec',                 # optional builder sections (default cfg beam_sec / beam)
    'rafter_releases', 'ridge_releases',       # optional (relz, rely); default rigid rafters, pinned ridge members
    'D', 'Lr', 'snow',                         # optional kN/m2 overrides of the roof pressures on this plane
  }, ... ]
cfg['roof_regions'] = {k: [(i, j), ...] | {'bays': [(i, j)], 'D': .., 'Lr': .., 'snow': ..}}
    grid cells (i, j) = the bay with lower-left grid corner (i, j) of an INTERMEDIATE level k that are roof
    (lean-to, lower roof of an L-plan): D_roof (or 'D'), Lr, snow, no floor imposed load, no partitions, no Table 10
    share in the seismic weight.  A roof plane on a level that is not a roof level is a roof region automatically.

Model conventions (both builders -- example_build and the CFS india_cfs_frame_build -- use these helpers):
  * the eave nodes are the ordinary grid nodes ntag(i, j, k) at z[k]; a grid node of level k strictly inside a plane's
    span is lifted onto the roof surface (an internal column / a ridge column runs up to it);
  * where the ridge is not a present grid node, an APEX node apex_tag(k, p, line) is added on every rafter line;
  * rafters (kind 'beam') run eave -> (lifted nodes) -> apex -> eave along every declared line; ridge members join
    consecutive apex nodes; the horizontal girders a flat builder would draw across the span at eave level (ties) are
    NOT drawn (plane_spans_segment);
  * diaphragm (tie_diaphragm): the level master stays at eave level z[k] (modal / drift / story forces unchanged);
    eave nodes are tied to the diaphragm ONLY across the span, ridge (apex) nodes ONLY along the span (auxiliary
    diaphragm nodes + stiff zeroLength springs), so the eaves spread freely (no tied portal) and the diaphragm drives
    every frame at its ridge; lifted interior nodes are not tied.  Documented approach for the seismic gates: the roof
    mass (roof dead load by plan area + half the walls) is lumped at the eave-level master (IS 1893 7.3 / 7.4); along
    the span the storey force / inertia enters each frame at the ridge -- for a symmetric portal the same frame
    forces as half of it at each knee (the roof mass is spread over the span); across the span it enters the eave
    lines; drift (7.11.1) is measured at the column-top (eave) nodes.
  * loads (static_model): per horizontal (plan) area in global -Z -- a rafter carries p x (strip width between its
    frame lines) per unit PLAN length, i.e. p x w x cos(theta) per unit slope length, decomposed into element-local
    components (gravity_components); longitudinal members in the plane (eave struts, purlin lines, ridge members) carry
    no area load (the purlins deliver it to the rafters); wind acts normal to the slope on the rafters, windward /
    leeward split at the plane's ridge; partial snow (IS 875-4 4.3) is split at the plane's ridge.
"""
from __future__ import annotations

import math

APEX_BASE = 98000          # apex_tag(k, p, line) = k*100000 + 98000 + p*100 + line  (p 0..9, line 0..99)
AUX_BASE = 99000           # aux diaphragm nodes k*100000 + 99000 + n (n 0..998; mtag = k*100000 + 99999)
AUX_ELE_BASE = 8_000_000   # zeroLength spring tags 8_000_000 + k*1000 + n
AUX_MAT_BASE = 990_000     # uniaxialMaterial Elastic tags 990_000 + k
AUX_K = 1.0e9              # N/mm: spring stiffness across the span (rigid compared with any frame, F/K ~ 1e-4 mm)
TOL = 2.0                  # mm


def apex_tag(k, p, line):
    return int(k) * 100000 + APEX_BASE + int(p) * 100 + int(line)


def aux_tag(k, n):
    return int(k) * 100000 + AUX_BASE + int(n)


def _zlevels(cfg):
    z = [0.0]
    for h in cfg.get("heights") or []:
        z.append(z[-1] + float(h))
    return z


def grid_lines(cfg):
    """(xs, ys) grid-line coordinates (xcoords / ycoords, else i*SX / j*SY)."""
    NX, NY = int(cfg.get("NX") or 0), int(cfg.get("NY") or 0)
    xco, yco = cfg.get("xcoords"), cfg.get("ycoords")
    xs = [float(xco[i]) if xco else i * float(cfg["SX"]) for i in range(NX + 1)]
    ys = [float(yco[j]) if yco else j * float(cfg["SY"]) for j in range(NY + 1)]
    return xs, ys


def has_planes(cfg):
    return bool(isinstance(cfg, dict) and cfg.get("roof_planes"))


def planes(cfg, strict=False):
    """Normalised roof planes.  Invalid entries are skipped (strict=False) or raise ValueError (strict=True);
    validate() reports them."""
    out = []
    raw = cfg.get("roof_planes") if isinstance(cfg, dict) else None
    if not raw:
        return out
    xs, ys = grid_lines(cfg)
    zl = _zlevels(cfg)
    for p, r in enumerate(raw):
        try:
            out.append(_norm(cfg, p, r, xs, ys, zl))
        except (KeyError, TypeError, ValueError) as ex:
            if strict:
                raise ValueError("roof_planes[%d]: %s" % (p, ex))
    return out


def _norm(cfg, p, r, xs, ys, zl):
    if not isinstance(r, dict):
        raise ValueError("not a dict")
    axis = str(r["axis"]).upper()
    if axis not in ("X", "Y"):
        raise ValueError("axis must be 'X' or 'Y' (span direction)")
    ax = 0 if axis == "X" else 1
    lo, hi = sorted(float(v) for v in r["eave_coords_mm"])
    ridge = float(r["ridge_coord_mm"])
    ez, rz = float(r["eave_z_mm"]), float(r["ridge_z_mm"])
    if not (lo + TOL < ridge < hi - TOL):
        raise ValueError("ridge_coord_mm %.0f must lie strictly between the eaves %.0f and %.0f" % (ridge, lo, hi))
    if rz <= ez + TOL:
        raise ValueError("ridge_z_mm must exceed eave_z_mm")
    k = r.get("level")
    if k is None:
        ks = [kk for kk in range(1, len(zl)) if abs(zl[kk] - ez) <= 1.0]
        if not ks:
            raise ValueError("eave_z_mm %.0f is not a storey level z %s" % (ez, [round(v) for v in zl[1:]]))
        k = ks[0]
    k = int(k)
    if not (1 <= k < len(zl)) or abs(zl[k] - ez) > 1.0:
        raise ValueError("level %s does not have z = eave_z_mm %.0f" % (k, ez))
    along = xs if ax == 0 else ys
    across = ys if ax == 0 else xs
    for e in (lo, hi):
        if not any(abs(e - g) <= 1.0 for g in along):
            raise ValueError("eave coordinate %.0f is not a grid line along %s" % (e, axis))
    if r.get("lines") is not None:
        lines = sorted({int(v) for v in r["lines"]})
    elif r.get("bays") is not None:
        lines = sorted({int(b[1 - ax]) + d for b in r["bays"] for d in (0, 1)})
    else:
        lines = list(range(len(across)))
    if not lines or any(not (0 <= q < len(across)) for q in lines):
        raise ValueError("lines %s outside the grid (0..%d)" % (lines, len(across) - 1))
    if any(q > 99 for q in lines) or p > 9:
        raise ValueError("at most 10 planes and 100 frame lines per plane (node tag scheme)")
    lc = {q: across[q] for q in lines}
    ext = r.get("extent_mm")
    olo, ohi = (sorted(float(v) for v in ext) if ext else (min(lc.values()), max(lc.values())))
    return {"idx": p, "axis": axis, "ax": ax, "oax": 1 - ax, "lo": lo, "hi": hi, "ridge": ridge, "ez": ez, "rz": rz,
            "k": k, "lines": lines, "lcoord": lc, "olo": olo, "ohi": ohi, "raw": r}


def planes_at(cfg, k):
    return [pl for pl in planes(cfg) if pl["k"] == int(k)]


def surface_z(pl, a):
    """Roof-surface elevation at plan coordinate a (along the span axis)."""
    if a <= pl["ridge"]:
        return pl["ez"] + (pl["rz"] - pl["ez"]) * (a - pl["lo"]) / (pl["ridge"] - pl["lo"])
    return pl["rz"] - (pl["rz"] - pl["ez"]) * (a - pl["ridge"]) / (pl["hi"] - pl["ridge"])


def pitch_deg(pl):
    """(pitch of the low-coordinate slope, pitch of the high-coordinate slope) in degrees."""
    d = pl["rz"] - pl["ez"]
    return (math.degrees(math.atan2(d, pl["ridge"] - pl["lo"])), math.degrees(math.atan2(d, pl["hi"] - pl["ridge"])))


def _inside(pl, a, o, tol=TOL):
    return pl["lo"] + tol < a < pl["hi"] - tol and pl["olo"] - tol <= o <= pl["ohi"] + tol


def lifted_z(cfg, k, x, y):
    """Roof-surface z for a grid node of level k lying strictly inside a plane's span (None otherwise)."""
    for pl in planes_at(cfg, k):
        c = (x, y)
        if _inside(pl, c[pl["ax"]], c[pl["oax"]]):
            return surface_z(pl, c[pl["ax"]])
    return None


def plane_spans_segment(cfg, z, pa, pb, tol=TOL, under_roof=False):
    """True when the horizontal segment pa-pb (plan points, at elevation z) runs along a plane's span axis at the
    plane's eave level and overlaps the span interior -- i.e. it would be a tie across the pitched roof.  Builders do
    not draw it and floor_beam_gaps does not ask for it (under_roof=True: at any elevation from the eave to the ridge,
    e.g. two lifted nodes at equal height on opposite slopes)."""
    for pl in planes(cfg):
        if under_roof:
            if not (pl["ez"] - 1.0 <= z <= pl["rz"] + 1.0):
                continue
        elif abs(pl["ez"] - z) > 1.0:
            continue
        ax, oax = pl["ax"], pl["oax"]
        if abs(pa[oax] - pb[oax]) > tol:
            continue
        o = pa[oax]
        if not (pl["olo"] - tol <= o <= pl["ohi"] + tol):
            continue
        a0, a1 = sorted((pa[ax], pb[ax]))
        if min(a1, pl["hi"]) - max(a0, pl["lo"]) > tol:
            return True
    return False


def classify(cfg, c1, c2, tol=TOL):
    """(plane, role) of a beam from its end coordinates, or None.  role: 'rafter' (along the span, on the roof
    surface), 'longitudinal' (normal to the span on the surface: eave strut, purlin line, ridge member) or 'tie'
    (along the span at eave level under the roof)."""
    for pl in planes(cfg):
        ax, oax = pl["ax"], pl["oax"]
        if not (pl["olo"] - tol <= c1[oax] <= pl["ohi"] + tol and pl["olo"] - tol <= c2[oax] <= pl["ohi"] + tol):
            continue
        if not (pl["lo"] - tol <= c1[ax] <= pl["hi"] + tol and pl["lo"] - tol <= c2[ax] <= pl["hi"] + tol):
            continue
        on1 = abs(c1[2] - surface_z(pl, min(max(c1[ax], pl["lo"]), pl["hi"]))) <= tol
        on2 = abs(c2[2] - surface_z(pl, min(max(c2[ax], pl["lo"]), pl["hi"]))) <= tol
        if abs(c1[oax] - c2[oax]) <= tol and abs(c1[ax] - c2[ax]) > tol:
            am = 0.5 * (c1[ax] + c2[ax]); zm = 0.5 * (c1[2] + c2[2])
            if on1 and on2 and abs(zm - surface_z(pl, am)) <= tol:
                return pl, "rafter"
            if abs(c1[2] - pl["ez"]) <= tol and abs(c2[2] - pl["ez"]) <= tol:
                return pl, "tie"
        elif abs(c1[ax] - c2[ax]) <= tol and on1 and on2:
            return pl, "longitudinal"
    return None


def rafter_trib_mm(pl, o, tol=TOL):
    """Tributary width (mm, across the span) of the rafter line at coordinate o: half the distance to each
    neighbouring declared line, the end lines to the plane extent (0 when o is not a declared line)."""
    cs = sorted(set(pl["lcoord"].values()))
    for n, c in enumerate(cs):
        if abs(c - o) <= tol:
            lo = (c - cs[n - 1]) / 2.0 if n > 0 else (c - pl["olo"])
            hi = (cs[n + 1] - c) / 2.0 if n + 1 < len(cs) else (pl["ohi"] - c)
            return max(lo, 0.0) + max(hi, 0.0)
    return 0.0


def plane_area_mm2(pl):
    return (pl["hi"] - pl["lo"]) * (pl["ohi"] - pl["olo"])


def plane_cells(cfg, pl, tol=TOL):
    """Grid cells (i, j) whose rectangle lies inside the plane's plan footprint."""
    xs, ys = grid_lines(cfg)
    out = set()
    for i in range(len(xs) - 1):
        for j in range(len(ys) - 1):
            r = ((xs[i], xs[i + 1]), (ys[j], ys[j + 1]))
            a0, a1 = r[pl["ax"]]; o0, o1 = r[pl["oax"]]
            if a0 >= pl["lo"] - tol and a1 <= pl["hi"] + tol and o0 >= pl["olo"] - tol and o1 <= pl["ohi"] + tol:
                out.add((i, j))
    return out


def uncovered_plane_area_mm2(cfg, k, framed_cells):
    """Plan area of the level-k roof planes NOT already counted as framed grid cells (apex-node planes over a grid
    without the interior nodes); framed_cells = the 4-corner cells counted by floor_area_mm2."""
    xs, ys = grid_lines(cfg)
    a = 0.0
    for pl in planes_at(cfg, k):
        rect = ((pl["lo"], pl["hi"]), (pl["olo"], pl["ohi"])) if pl["ax"] == 0 else ((pl["olo"], pl["ohi"]), (pl["lo"], pl["hi"]))
        cov = 0.0
        for (i, j) in framed_cells:
            dx = min(rect[0][1], xs[i + 1]) - max(rect[0][0], xs[i])
            dy = min(rect[1][1], ys[j + 1]) - max(rect[1][0], ys[j])
            if dx > 0 and dy > 0:
                cov += dx * dy
        a += max(plane_area_mm2(pl) - cov, 0.0)
    return a


def _covered(cfg, k, x, y, present_k):
    """True when plan point (x, y) lies under a level-k roof plane or inside a framed grid cell of present_k."""
    c = (x, y)
    for pl in planes_at(cfg, k):
        if pl["lo"] < c[pl["ax"]] < pl["hi"] and pl["olo"] < c[pl["oax"]] < pl["ohi"]:
            return True
    xs, ys = grid_lines(cfg)
    P = set(present_k or ())
    for i in range(len(xs) - 1):
        if not (xs[i] < x < xs[i + 1]):
            continue
        for j in range(len(ys) - 1):
            if ys[j] < y < ys[j + 1] and {(i, j), (i + 1, j), (i, j + 1), (i + 1, j + 1)} <= P:
                return True
    return False


def on_perimeter(cfg, k, ca, cb, present_k, d=50.0):
    """X02: a horizontal plane member (eave strut, gable-end rafter) is on the building perimeter when exactly one
    side of it (offset d mm normal to it in plan, at its mid-point) is covered by roof / floor."""
    mx, my = 0.5 * (ca[0] + cb[0]), 0.5 * (ca[1] + cb[1])
    dx, dy = cb[0] - ca[0], cb[1] - ca[1]
    L = math.hypot(dx, dy) or 1.0
    nx, ny = -dy / L * d, dx / L * d
    return _covered(cfg, k, mx + nx, my + ny, present_k) != _covered(cfg, k, mx - nx, my - ny, present_k)


def gable_cladding_N(cfg, k):
    """Weight (N) of the two gable-wall triangles above the eave of every level-k plane (cfg['clad'] kN/m2 x
    (hi - lo) (ridge_z - eave_z) / 2 each) -- the gable-end rafters carry the same cladding in the static model."""
    clad = float(cfg.get("clad") or 0.0)
    if not clad:
        return 0.0
    return sum(clad * (pl["hi"] - pl["lo"]) * (pl["rz"] - pl["ez"]) / 1000.0 for pl in planes_at(cfg, k))


# ---------------------------------------------------------------- region roofs (HR-B-16)
def _roof_level_set(cfg):
    import india_loads as _IL
    return _IL.roof_level_set(cfg, len(cfg.get("heights") or []))


def roof_region_bays(cfg, k):
    """{(i, j): {'D', 'Lr', 'snow' overrides (may be empty)}} -- the roof bays of an INTERMEDIATE level k (declared
    cfg['roof_regions'][k] plus the cells under a roof plane of level k).  Empty on roof levels (the whole level is
    a roof) and when nothing is declared."""
    if not isinstance(cfg, dict):
        return {}
    k = int(k)
    if k in _roof_level_set(cfg):
        return {}
    out = {}
    rr = cfg.get("roof_regions") or {}
    v = rr.get(k, rr.get(str(k))) if isinstance(rr, dict) else None
    if v:
        ov = {}
        bays = v
        if isinstance(v, dict):
            bays = v.get("bays") or []
            ov = {q: float(v[q]) for q in ("D", "Lr", "snow") if v.get(q) is not None}
        for b in bays:
            out[(int(b[0]), int(b[1]))] = dict(ov)
    for pl in planes_at(cfg, k):
        ov = {q: float(pl["raw"][q]) for q in ("D", "Lr", "snow") if pl["raw"].get(q) is not None}
        for c in plane_cells(cfg, pl):
            out.setdefault(c, dict(ov))
    return out


def roof_pressures(cfg, k, ov=None):
    """(D, 0, Lr, S) kN/m2 of a roof bay / plane at level k: the level's roof pressures (static_model.floor_pressures
    when k is a roof level), else D_roof / Lr / snow, with the region / plane overrides 'D', 'Lr', 'snow'."""
    import static_model as _SM
    ov = ov or {}
    if int(k) in _roof_level_set(cfg):
        D, _L, Lr, S = _SM.floor_pressures(cfg, k)
    else:
        D = float(cfg["D_roof"]) + float((cfg.get("extra_mass_floors") or {}).get(k, 0.0) or 0.0)
        Lr = _SM._roof_live(cfg)
        S = float(cfg.get("snow") or 0.0)
    D = float(ov.get("D", D)); Lr = float(ov.get("Lr", Lr)); S = float(ov.get("snow", S))
    return D, 0.0, Lr, S


def plane_pressures(cfg, pl):
    ov = {q: float(pl["raw"][q]) for q in ("D", "Lr", "snow") if pl["raw"].get(q) is not None}
    return roof_pressures(cfg, pl["k"], ov)


def region_split_area_mm2(cfg, k, present_k=None):
    """{'floor': mm2, 'roof': [(mm2, overrides)]} of the framed cells of level k split by roof_region_bays."""
    xs, ys = grid_lines(cfg)
    reg = roof_region_bays(cfg, k)
    if present_k is None:
        import engine3d as _E
        present_k = _E.grid(cfg, k)
    P = set(present_k)
    fl = 0.0; roof = []
    for i in range(len(xs) - 1):
        for j in range(len(ys) - 1):
            if {(i, j), (i + 1, j), (i, j + 1), (i + 1, j + 1)} <= P:
                a = abs(xs[i + 1] - xs[i]) * abs(ys[j + 1] - ys[j])
                if (i, j) in reg:
                    roof.append((a, reg[(i, j)]))
                else:
                    fl += a
    return {"floor": fl, "roof": roof}


# ---------------------------------------------------------------- loads
def local_axes(ca, cb, vecxz=(0.0, 0.0, 1.0)):
    """OpenSees 3-D beam local axes (x, y, z) for end coordinates ca -> cb and the transformation's vecxz."""
    x = [cb[i] - ca[i] for i in range(3)]
    L = math.sqrt(sum(v * v for v in x)) or 1.0
    x = [v / L for v in x]
    v = list(vecxz)
    y = [v[1] * x[2] - v[2] * x[1], v[2] * x[0] - v[0] * x[2], v[0] * x[1] - v[1] * x[0]]
    ny = math.sqrt(sum(q * q for q in y)) or 1.0
    y = [q / ny for q in y]
    z = [x[1] * y[2] - x[2] * y[1], x[2] * y[0] - x[0] * y[2], x[0] * y[1] - x[1] * y[0]]
    return x, y, z


def gravity_components(ca, cb, vecxz=(0.0, 0.0, 1.0)):
    """(Wy, Wz, Wx) local components of a UNIT distributed load in global -Z (for eleLoad -beamUniform Wy Wz Wx)."""
    x, y, z = local_axes(ca, cb, vecxz)
    return (-y[2], -z[2], -x[2])


# ---------------------------------------------------------------- diaphragm
def _quiet(fn, *a):
    """Run an OpenSees call with the C-level stdout/stderr silenced (the ridge springs are zeroLength elements between
    non-coincident nodes, which OpenSees reports with a harmless length WARNING)."""
    import os
    saved = None
    try:
        saved = (os.dup(1), os.dup(2)); dn = os.open(os.devnull, os.O_WRONLY)
        os.dup2(dn, 1); os.dup2(dn, 2)
    except Exception:
        saved = None
    try:
        return fn(*a)
    finally:
        if saved:
            try:
                os.dup2(saved[0], 1); os.dup2(saved[1], 2)
                os.close(dn); os.close(saved[0]); os.close(saved[1])
            except Exception:
                pass


def element_quiet(*a):
    import openseespy.opensees as ops
    return _quiet(ops.element, *a)


def ridge_nodes(k, pls):
    """Nodes of level k on a plane's ridge line (apex tags or lifted grid nodes at the ridge)."""
    import openseespy.opensees as ops
    out = []
    for t in ops.getNodeTags():
        if t // 100000 != int(k) or (t % 100000) >= AUX_BASE:
            continue
        c = ops.nodeCoord(t)
        for pl in pls:
            if (abs(c[pl["ax"]] - pl["ridge"]) <= TOL and pl["olo"] - TOL <= c[pl["oax"]] <= pl["ohi"] + TOL
                    and abs(c[2] - pl["rz"]) <= TOL):
                out.append(t)
                break
    return out


def tie_diaphragm(cfg, k, master, slaves, zk):
    """rigidDiaphragm of level k with the eave spread of the level's roof planes left free (see module doc).
    Without a roof plane on level k this is exactly ops.rigidDiaphragm(3, master, *slaves).

    With planes: nodes on an eave line are tied to the diaphragm ACROSS the span only (a coincident auxiliary
    diaphragm node + a stiff zeroLength spring normal to the span); the ridge nodes (apex) are tied ALONG the span only
    (auxiliary node at eave level under the apex + a stiff spring along the span), so the diaphragm drives each frame
    at its ridge -- for a symmetric portal the same frame forces as half the storey force at each knee -- and the
    eaves spread freely; every other node of the level plane is fully tied.  Returns {'full', 'spring', 'ridge'}."""
    import openseespy.opensees as ops
    pls = planes_at(cfg, k)
    if not pls:
        ops.rigidDiaphragm(3, master, *slaves)
        return {"full": list(slaves), "spring": [], "ridge": []}
    ax = pls[0]["ax"]
    full, eave = [], []
    for t in slaves:
        c = ops.nodeCoord(t)
        if abs(c[2] - zk) > 1.0:
            continue                                  # lifted / apex nodes are not in the diaphragm plane
        on_eave = any(abs(c[pl["ax"]] - e) <= TOL and pl["olo"] - TOL <= c[pl["oax"]] <= pl["ohi"] + TOL
                      for pl in pls for e in (pl["lo"], pl["hi"]))
        (eave if on_eave else full).append(t)
    ridge = ridge_nodes(k, pls)
    if not ridge:                                     # no rafters (preflight ERROR): keep the model stable --
        full += eave; eave = []                       # tie the eaves fully (tied portal)
    across = 2 if ax == 0 else 1
    along = 1 if ax == 0 else 2
    springs = []
    n = 0
    for grp, dof in ((eave, across), (ridge, along)):
        for t in grp:
            a = aux_tag(k, n)
            c = ops.nodeCoord(t)
            ops.node(a, c[0], c[1], zk)
            ops.fix(a, 0, 0, 1, 1, 1, 0)
            full.append(a)
            springs.append((a, t, dof, AUX_ELE_BASE + int(k) * 1000 + n))
            n += 1
    if springs:
        ops.uniaxialMaterial("Elastic", AUX_MAT_BASE + int(k), AUX_K)
    ops.rigidDiaphragm(3, master, *full)
    for (a, t, dof, et) in springs:
        element_quiet("zeroLength", et, a, t, "-mat", AUX_MAT_BASE + int(k), "-dir", dof)
    return {"full": full, "spring": [(a, t) for (a, t, _d, _e) in springs], "ridge": ridge}


# ---------------------------------------------------------------- builder helper
def add_plane_members(cfg, k, XY, present_k, et, eles, beam_sec=None, add_beam=None):
    """Draw the rafters (eave -> lifted grid nodes -> apex -> eave) and ridge members of every plane of level k.
    XY(i, j) -> plan (x, y); present_k = the level's grid nodes (eave nodes at z[k], interior ones lifted by the
    builder via lifted_z).  Returns the next element tag; appends (tag, 'beam', sec, n1, n2) to eles."""
    import openseespy.opensees as ops
    import engine3d as eng
    add_beam = add_beam or eng.add_beam
    for pl in planes_at(cfg, k):
        ax, p = pl["ax"], pl["idx"]
        r = pl["raw"]
        rel_r = tuple(r["rafter_releases"]) if r.get("rafter_releases") else None
        rel_g = tuple(r["ridge_releases"]) if r.get("ridge_releases") else ("both", "none")
        apex = {}
        for q in pl["lines"]:
            # grid nodes on this line inside [lo, hi], ordered along the span
            on = []
            for (i, j) in present_k:
                if (j if ax == 0 else i) != q:
                    continue
                c = XY(i, j)
                if pl["lo"] - TOL <= c[ax] <= pl["hi"] + TOL:
                    on.append((c[ax], eng.ntag(i, j, k)))
            ends = [a for a, _t in on]
            if not any(abs(a - pl["lo"]) <= TOL for a in ends) or not any(abs(a - pl["hi"]) <= TOL for a in ends):
                continue                                    # no eave column pair on this line: no rafter
            at_ridge = [t for a, t in on if abs(a - pl["ridge"]) <= TOL]
            if at_ridge:
                apex[q] = at_ridge[0]
            else:
                t = apex_tag(k, p, q)
                c0 = XY(*((0, q) if ax == 0 else (q, 0)))
                xy = [0.0, 0.0]; xy[ax] = pl["ridge"]; xy[1 - ax] = c0[1 - ax]
                ops.node(t, xy[0], xy[1], pl["rz"])
                apex[q] = t
                on.append((pl["ridge"], t))
            on.sort()
            for (a0, n0), (a1, n1) in zip(on, on[1:]):
                sec = r.get("rafter_sec") or (beam_sec(q, k, pl["axis"]) if beam_sec else cfg.get("beam"))
                add_beam(et, n0, n1, sec, releases=rel_r)
                eles.append((et, "beam", sec, n0, n1)); et += 1
        qs = sorted(apex)
        for q0, q1 in zip(qs, qs[1:]):
            n0, n1 = apex[q0], apex[q1]
            if (n0 % 100000) < APEX_BASE and (n1 % 100000) < APEX_BASE:
                continue                                    # both on grid nodes: the builder's own girder joins them
            sec = r.get("ridge_sec") or (beam_sec(q0, k, "Y" if ax == 0 else "X") if beam_sec else cfg.get("beam"))
            add_beam(et, n0, n1, sec, releases=rel_g)
            eles.append((et, "beam", sec, n0, n1)); et += 1
    return et


# ---------------------------------------------------------------- validation (preflight / H18)
def validate(cfg):
    """[(severity, message)] for cfg['roof_planes'] / cfg['roof_regions']."""
    out = []
    raw = cfg.get("roof_planes")
    if raw:
        if not isinstance(raw, (list, tuple)):
            return [("ERROR", "cfg['roof_planes'] must be a list of plane dicts (X02)")]
        if cfg.get("skew"):
            out.append(("ERROR", "cfg['roof_planes'] with a skewed grid is not supported (X02)"))
        xs, ys = grid_lines(cfg)
        zl = _zlevels(cfg)
        ok = []
        for p, r in enumerate(raw):
            try:
                ok.append(_norm(cfg, p, r, xs, ys, zl))
            except (KeyError, TypeError, ValueError) as ex:
                out.append(("ERROR", "roof_planes[%d] invalid: %s (keys axis, eave_coords_mm, ridge_coord_mm, "
                                     "eave_z_mm, ridge_z_mm, lines|bays; X02)" % (p, ex)))
        for a in ok:
            for b in ok:
                if b["idx"] <= a["idx"] or a["k"] != b["k"]:
                    continue
                if a["axis"] != b["axis"]:
                    out.append(("ERROR", "roof_planes[%d] and [%d] on level %d span different axes -- one span axis per "
                                         "level (the eave-spread diaphragm, X02)" % (a["idx"], b["idx"], a["k"])))
                elif (min(a["hi"], b["hi"]) - max(a["lo"], b["lo"]) > TOL
                      and min(a["ohi"], b["ohi"]) - max(a["olo"], b["olo"]) > TOL):
                    out.append(("ERROR", "roof_planes[%d] and [%d] overlap in plan" % (a["idx"], b["idx"])))
        if ok and float(cfg.get("snow") or 0.0) > 0.0 and not cfg.get("snow_partial"):
            out.append(("WARN", "roof_planes with snow but no cfg['snow_partial'] = {'axis': span axis}: the IS 875-4 "
                                "4.3 unbalanced rows (one slope unloaded, split at the plane's ridge) are not generated"))
        pd = cfg.get("roof_pitch_deg")
        if pd is not None and ok:
            worst = max(abs(float(pd) - v) for pl in ok for v in pitch_deg(pl))
            if worst > 0.5:
                out.append(("WARN", "cfg['roof_pitch_deg'] = %.1f deg differs from the roof_planes pitch %s: IS 875-3 "
                                    "Table 6 member wind must be taken at the true pitch"
                            % (float(pd), sorted({round(v, 1) for pl in ok for v in pitch_deg(pl)}))))
    rr = cfg.get("roof_regions")
    if rr:
        if not isinstance(rr, dict):
            out.append(("ERROR", "cfg['roof_regions'] must be {level: [(i, j) bays]} (X02, HR-B-16)"))
        else:
            NF = len(cfg.get("heights") or [])
            NX, NY = int(cfg.get("NX") or 0), int(cfg.get("NY") or 0)
            for kk, v in rr.items():
                try:
                    k = int(kk)
                except (TypeError, ValueError):
                    out.append(("ERROR", "roof_regions key %r is not a level" % (kk,)))
                    continue
                bays = v.get("bays") if isinstance(v, dict) else v
                if not (1 <= k <= NF):
                    out.append(("ERROR", "roof_regions level %d outside 1..%d" % (k, NF)))
                bad = [b for b in (bays or []) if not (0 <= int(b[0]) < NX and 0 <= int(b[1]) < NY)]
                if bad:
                    out.append(("ERROR", "roof_regions[%d] bays %s outside the grid" % (k, bad[:3])))
    return out
