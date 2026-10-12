"""peb_build.py -- PEB (2026-10): the stepped model of web-tapered welded portal members (docs/PEB_TAPERED_SCOPE.md).

A web-tapered member (cfg['custom_sections'] type 'tapered_I', label TI<D0>-<D1>X<bf>X<tf>X<tw>) is modelled as a chain
of prismatic welded I elements (WI<D>X<bf>X<tf>X<tw>); each element takes the depth at its mid-length (linear taper,
rounded to 1 mm).  The checks are made at every element end with the EXACT local section (stations, IS 800 checks per
owner ruling D-T1), and the joints use the section at the joint face (D-T7).  Flange plates are constant within a
member; a change of plates is a new member at a bolted end-plate splice.

custom_build use (columns):

    import peb_build as PB
    PB.reset()
    et = PB.column(et, eles, E.ntag(i, j, 0), E.ntag(i, j, 1), [(H, "TI300-750X200X10X6")], "Y", i=i, j=j)
    ...
    return PB.finish(info)

and rafters inside a roof plane (roof_geometry.add_plane_members) with the plane key

    'rafter_members': {'lo': [(6000.0, 'TI750-450X200X10X5'), (15000.0, 'WI450X180X8X5')],  # plan distance from the
                       'hi': [...]}                                                         # eave, last = the ridge
    ('hi' defaults to the mirror of 'lo'); 'rafter_members_by_line': {line: same layout} overrides it on single
    lines (the gable rafters of post-and-beam end frames), 'gravity_lines': [line, ...] marks lines that are not
    moment frames (end rafters pinned on wind columns: gravity beams, shear connections); 'apex_splice': False
    makes the two members that meet at the ridge one continuous piece (no apex joint).  Member boundaries inside the span are bolted end-plate splices; the apex
    is the apex end-plate joint; lifted grid nodes (interior columns) split the chain without a splice.

Node tags (engine conventions ntag = k*100000 + i*100 + j; roof_geometry apex 98000+, aux 99000+):
    column stations   (COL_K0 + s) * 100000 + i*100 + j        s = 1 .. 79 (k-part beyond every storey level)
    rafter stations   k*100000 + RAF_BASE + n*100 + line       n = 0 .. 79 on one rafter line

Restraints (cfg['flange_braces'], owner ruling D-T1 -- LTB segment by segment between restraints):
    {'rafter': {'purlins_mm': [plan distances from the eave of one slope ...],      # outer (top) flange restraints
                'fly_braces_mm': [...]},                                              # inner (bottom) flange restraints
     'column': {'girts_mm': [heights above the base ...], 'fly_braces_mm': [...]},
     'members': {...design of the brace angles, peb_checks.flange_brace_checks}}
The knee, the apex, the base and every lifted support count as restraints of both flanges.  Per element the module
derives LLT_sag_mm / LLT_hog_mm (rafters: sagging = top flange, purlin spacing; hogging = bottom flange, fly-brace
spacing; columns: the larger of the two for both signs), Ly_mm (fly-brace spacing: both flanges held), Lz_mm (the
member between frame nodes: base-knee, knee-apex or knee-support) and buckling_section (the member's smallest section,
major-axis buckling, D-T1), as element overrides (design_pipeline.member_override); explicit cfg['member_overrides']
'e<tag>' entries win.  C1 = 1.0 (conservative, D-T1).
"""
from __future__ import annotations

import math
import re

import sections as S

COL_K0 = 20
RAF_BASE = 90000
SRC = "steel_engine/peb_build.py"
_TI = re.compile(r"^TI(\d+(?:\.\d+)?)-(\d+(?:\.\d+)?)X(\d+(?:\.\d+)?)X(\d+(?:\.\d+)?)X(\d+(?:\.\d+)?)$")
_WI = re.compile(r"^WI(\d+(?:\.\d+)?)X(\d+(?:\.\d+)?)X(\d+(?:\.\d+)?)X(\d+(?:\.\d+)?)$")

_REG = {}


def reset():
    """Start a new build (call at the top of custom_build; finish() attaches the registry to info)."""
    _REG.clear()
    _REG.update(elements={}, chains={}, members={}, splices={}, continuous=set(), frame_nodes=set(), gravity=set())


reset()


# ------------------------------------------------------------------------------------------------ sections
def parse(label):
    """('tapered', D0, D1, bf, tf, tw) | ('welded', D, bf, tf, tw) | ('rolled', label)."""
    u = str(label).upper().replace(" ", "")
    m = _TI.match(u)
    if m:
        return ("tapered",) + tuple(float(v) for v in m.groups())
    m = _WI.match(u)
    if m:
        return ("welded",) + tuple(float(v) for v in m.groups())
    return ("rolled", label)


def ensure(label):
    """Register a WI / TI designation on first use (properties from the plates)."""
    p = parse(label)
    if p[0] == "welded" and S.normalize_label(label) not in S.CUSTOM:
        S.register_welded_I(label, *p[1:])
    if p[0] == "tapered" and S.normalize_label(label) not in S.TAPERED:
        S.register_tapered_I(label, *p[1:], n_seg=8)
    return p


def section_at(label, f):
    """Exact section (WI label, depth rounded to 1 mm) of member `label` at fraction f (0 = start) of its length;
    a prismatic member returns its own label."""
    p = ensure(label)
    if p[0] != "tapered":
        return label
    D0, D1, bf, tf, tw = p[1:]
    D = round(D0 + (D1 - D0) * f)
    lab = S.welded_I_label(D, bf, tf, tw)
    ensure(lab)
    return lab


def n_segments(label, cfg=None):
    p = ensure(label)
    if p[0] != "tapered":
        return 1
    try:
        return int(S.tapered(label)["n_seg"])
    except KeyError:
        return int((cfg or {}).get("taper_nseg") or 8)


def depth(label):
    p = ensure(label)
    if p[0] == "tapered":
        return max(p[1], p[2])
    if p[0] == "welded":
        return p[1]
    return float(S.props(label)["d"])


def mass_kg(label, L_mm):
    """Mass of a member (exact for a linear taper: the mean web area)."""
    p = ensure(label)
    if p[0] == "tapered":
        D0, D1, bf, tf, tw = p[1:]
        A = 2.0 * bf * tf + 0.5 * ((D0 - 2 * tf) + (D1 - 2 * tf)) * tw
        return A * 7850e-9 * L_mm
    return float(S.props(label)["Mass_kg_m"]) * L_mm / 1000.0 if S.props(label).get("Mass_kg_m") else \
        float(S.props(label)["A"]) * 7850e-9 * L_mm


# ------------------------------------------------------------------------------------------------ registry
def _member(mid, kind, label, n_start, n_end, L, **kw):
    rec = {"id": mid, "kind": kind, "section": label, "node_start": n_start, "node_end": n_end, "L_mm": L,
           "elements": [], "parse": parse(label)[0]}
    rec.update(kw)
    _REG["members"][mid] = rec
    return rec


def _element(t, member, s0, s1, f0, f1, sec, sec_i, sec_j, n1, n2, chain, pos0, pos1):
    _REG["elements"][t] = {"member": member["id"], "chain": chain, "f": (f0, f1), "s_mm": (s0, s1),
                           "pos_mm": (pos0, pos1), "section": sec, "sec_i": sec_i, "sec_j": sec_j,
                           "n1": n1, "n2": n2}
    member["elements"].append(t)


def column(et, eles, n_base, n_top, members, strong_dir, *, i, j, add_column=None, releases=None, chain_id=None,
           k0=None, extra_stations_mm=None, restraints=None):
    """A column line from n_base up to n_top as a chain of members [(to_mm above the base, label), ...] (the last
    reaches n_top).  Tapered members are split into their stepped segments with intermediate station nodes.
    releases = 'I' (pinned base), 'J' (pinned top) or 'both' for the column pinned at the rafter (gravity column):
    applied to the first / last element.  restraints = {'girts_mm': [...], 'fly_braces_mm': [...]} (heights above
    the base) for THIS column, replacing cfg['flange_braces']['column'] (e.g. an interior column with no girts,
    restrained only by the strut of a two-tier braced bay).  Returns the next element tag."""
    import openseespy.opensees as ops
    import engine3d as E
    add_column = add_column or E.add_column
    if isinstance(members, str):
        members = [(None, members)]
    c0, c1 = ops.nodeCoord(n_base), ops.nodeCoord(n_top)
    H = math.dist(c0, c1)
    cid = chain_id or "C%d-%d" % (i, j)
    k0 = COL_K0 if k0 is None else int(k0)
    pts = []                                          # (s_mm, member_index, f_in_member)
    s_prev = 0.0
    mrecs = []
    for mi, (to, lab) in enumerate(members):
        to = H if (to is None or mi == len(members) - 1) else float(to)
        L = to - s_prev
        n = n_segments(lab)
        m = _member("%s-m%d" % (cid, mi + 1), "column", lab, None, None, L, chain=cid, s0=s_prev, s1=to,
                    strong_dir=strong_dir, line=(i, j))
        mrecs.append(m)
        for s in range(n):
            pts.append((s_prev + L * s / n, mi, s / n))
        s_prev = to
    pts.append((H, len(members) - 1, 1.0))
    for xs_ in sorted(float(v) for v in (extra_stations_mm or [])):
        # extra station (e.g. a canopy bracket height) inside a member: a depth step only, no splice
        if any(abs(xs_ - p_[0]) < 1.0 for p_ in pts) or not (0.0 < xs_ < H):
            continue
        mi = max(k_ for k_, m in enumerate(mrecs) if m["s0"] <= xs_ + 1e-6)
        m = mrecs[mi]
        pts.append((xs_, mi, (xs_ - m["s0"]) / m["L_mm"]))
    pts.sort(key=lambda p_: (p_[0], p_[1]))
    nodes = []
    ns = 0
    for idx, (s, mi, f) in enumerate(pts):
        if idx == 0:
            nodes.append(n_base)
            continue
        if idx == len(pts) - 1:
            nodes.append(n_top)
            continue
        ns += 1
        tag = (k0 + ns) * 100000 + int(i) * 100 + int(j)
        r = s / H
        ops.node(tag, c0[0] + (c1[0] - c0[0]) * r, c0[1] + (c1[1] - c0[1]) * r, c0[2] + (c1[2] - c0[2]) * r)
        nodes.append(tag)
        _REG["continuous"].add(tag)
    mrecs[0]["node_start"] = n_base
    mrecs[-1]["node_end"] = n_top
    nel = len(pts) - 1
    for e in range(nel):
        s0, mi, f0 = pts[e]
        s1 = pts[e + 1][0]
        m = mrecs[mi]
        f1 = (s1 - m["s0"]) / m["L_mm"] if m["L_mm"] > 0 else 1.0
        lab = m["section"]
        fm = 0.5 * (f0 + f1)
        sec = section_at(lab, fm)
        sec_i, sec_j = section_at(lab, f0), section_at(lab, f1)
        rel = None
        if releases in ("I", "both") and e == 0:
            rel = "I"
        if releases in ("J", "both") and e == nel - 1:
            rel = "both" if rel == "I" else "J"
        add_column(et, nodes[e], nodes[e + 1], sec, strong_dir, releases=rel) if rel else \
            add_column(et, nodes[e], nodes[e + 1], sec, strong_dir)
        eles.append((et, "col", sec, nodes[e], nodes[e + 1]))
        _element(et, m, s0, s1, f0, f1, sec, sec_i, sec_j, nodes[e], nodes[e + 1], cid, s0, s1)
        et += 1
    # member boundaries inside the column = splices
    for m0, m1 in zip(mrecs, mrecs[1:]):
        nd = nodes[[idx for idx, p in enumerate(pts) if abs(p[0] - m0["s1"]) < 1e-6][0]]
        m0["node_end"] = nd
        m1["node_start"] = nd
        _REG["splices"][nd] = {"kind": "column_splice", "members": [m0["id"], m1["id"]], "chain": cid,
                               "sec_below": section_at(m0["section"], 1.0), "sec_above": section_at(m1["section"], 0.0)}
    _REG["chains"][cid] = {"id": cid, "kind": "column", "nodes": nodes, "members": [m["id"] for m in mrecs],
                           "L_mm": H, "line": (i, j), "base": n_base, "top": n_top, "releases": releases,
                           "strong_dir": strong_dir, "s_mm": [p_[0] for p_ in pts],
                           "restraints": dict(restraints) if restraints is not None else None}
    _REG["frame_nodes"].update((n_base, n_top))
    return et


def rafter_line(cfg, pl, q, on, k, et, eles, add_beam, rel_r=None):
    """roof_geometry.add_plane_members hook: the rafter chain of plane pl on frame line q.  on = [(a, node tag)]
    sorted along the span (eaves, lifted grid nodes, apex).  Returns the next element tag."""
    import openseespy.opensees as ops
    import roof_geometry as RG
    r = pl["raw"]
    lay = (r.get("rafter_members_by_line") or {}).get(q) or (r.get("rafter_members_by_line") or {}).get(str(q)) \
        or r["rafter_members"]
    gravity = int(q) in {int(v) for v in (r.get("gravity_lines") or [])}
    lo_m = [(float(a), str(s)) for a, s in (lay.get("lo") or lay.get("low") or [])]
    hi_m = [(float(a), str(s)) for a, s in (lay.get("hi") or lay.get("high") or lo_m)]
    lo, hi, ridge = pl["lo"], pl["hi"], pl["ridge"]
    ax = pl["ax"]
    cid_l, cid_h = "R%d-%d-lo" % (pl["idx"], q), "R%d-%d-hi" % (pl["idx"], q)
    # members as plan intervals [a0, a1] with the label oriented from the eave (start = eave side)
    mem = []
    prev = lo
    for n, (to, lab) in enumerate(lo_m):
        a1 = ridge if n == len(lo_m) - 1 else lo + to
        mem.append({"a0": prev, "a1": a1, "label": lab, "side": "lo", "eave_first": True, "n": n + 1})
        prev = a1
    prev = hi
    for n, (to, lab) in enumerate(hi_m):
        a0 = ridge if n == len(hi_m) - 1 else hi - to
        mem.append({"a0": a0, "a1": prev, "label": lab, "side": "hi", "eave_first": False, "n": n + 1})
        prev = a0
    mem.sort(key=lambda m: m["a0"])
    # break points: member ends, tapered segment boundaries, existing nodes
    exist = {round(a, 3): t for a, t in on}
    bps = set(exist)
    for m in mem:
        ns = n_segments(m["label"])
        for s in range(ns + 1):
            bps.add(round(m["a0"] + (m["a1"] - m["a0"]) * s / ns, 3))
    bps = sorted(b for b in bps if lo - 1.0 <= b <= hi + 1.0)
    # merge break points closer than 1 mm to an existing node
    pts = []
    for b in bps:
        if pts and abs(b - pts[-1]) < 1.0:
            if b in exist:
                pts[-1] = b
            continue
        pts.append(b)
    c0 = None
    for a, t in on:
        c0 = ops.nodeCoord(t)
        break
    node_at = {}
    nr = 0                                            # deterministic: station n-th new node of this line
    for a in pts:
        t = exist.get(a)
        if t is None:
            xy = [c0[0], c0[1]]
            xy[ax] = a
            t = int(k) * 100000 + RAF_BASE + nr * 100 + int(q)
            nr += 1
            if nr > 79:
                raise ValueError("rafter line %d: more than 80 station nodes (peb_build tag scheme)" % q)
            ops.node(t, xy[0], xy[1], RG.surface_z(pl, a))
            _REG["continuous"].add(t)
        node_at[a] = t

    def member_of(am):
        for m in mem:
            if m["a0"] - 1e-6 <= am <= m["a1"] + 1e-6:
                return m
        raise ValueError("rafter line %d: no member covers plan coordinate %.0f (rafter_members)" % (q, am))

    def frac(m, a):                                   # fraction along the member from its EAVE end
        L = m["a1"] - m["a0"]
        f = (a - m["a0"]) / L if L > 0 else 0.0
        return f if m["eave_first"] else 1.0 - f

    def slope_len(a0, a1):
        z0, z1 = RG.surface_z(pl, a0), RG.surface_z(pl, a1)
        return math.hypot(a1 - a0, z1 - z0)

    mrec = {}
    for m in mem:
        cid = cid_l if m["side"] == "lo" else cid_h
        L = slope_len(m["a0"], m["a1"])
        eave_a = m["a0"] if m["eave_first"] else m["a1"]
        mid = "%s-m%d" % (cid, m["n"])
        mrec[id(m)] = _member(mid, "rafter", m["label"], None, None, L, chain=cid, a0=m["a0"], a1=m["a1"],
                              eave_end=("start" if m["eave_first"] else "end"), plane=pl["idx"], line=q,
                              s0=abs(eave_a - (lo if m["side"] == "lo" else hi)))
    for a0, a1 in zip(pts, pts[1:]):
        m = member_of(0.5 * (a0 + a1))
        rec = mrec[id(m)]
        f0, f1 = frac(m, a0), frac(m, a1)
        sec = section_at(m["label"], 0.5 * (f0 + f1))
        n0, n1 = node_at[a0], node_at[a1]
        add_beam(et, n0, n1, sec, releases=rel_r)
        eles.append((et, "beam", sec, n0, n1))
        side_e = lo if m["side"] == "lo" else hi
        _element(et, rec, abs(a0 - side_e), abs(a1 - side_e), f0, f1, sec, section_at(m["label"], f0),
                 section_at(m["label"], f1), n0, n1, rec["chain"], a0, a1)
        if gravity:
            _REG["gravity"].add(et)
        if rec["node_start"] is None:
            rec["node_start"] = n0
        rec["node_end"] = n1
        et += 1
    # splices: member boundaries (apex = the ridge boundary); lifted grid nodes are frame nodes (supports)
    for a, t in on:
        _REG["frame_nodes"].add(t)
    for m0 in mem:
        for m1 in mem:
            if m0 is m1 or abs(m0["a1"] - m1["a0"]) > 1e-3:
                continue
            nd = node_at[round(m0["a1"], 3)] if round(m0["a1"], 3) in node_at else \
                min(node_at.items(), key=lambda kv: abs(kv[0] - m0["a1"]))[1]
            apex = abs(m0["a1"] - ridge) < 1.0
            r0, r1 = mrec[id(m0)], mrec[id(m1)]
            if apex and r.get("apex_splice") is False:
                # one piece continuous over the ridge (e.g. over a ridge column: no joint within 3 db of a column)
                _REG["continuous"].add(nd)
                continue
            _REG["splices"][nd] = {"kind": "apex" if apex else "rafter_splice", "members": [r0["id"], r1["id"]],
                                   "gravity": gravity,
                                   "chain": r0["chain"], "line": q, "plane": pl["idx"], "a_mm": m0["a1"],
                                   "dist_from_eave_mm": min(m0["a1"] - lo, hi - m0["a1"]),
                                   "sec_left": section_at(m0["label"], frac(m0, m0["a1"])),
                                   "sec_right": section_at(m1["label"], frac(m1, m1["a0"]))}
    _REG["chains"][cid_l] = {"id": cid_l, "kind": "rafter", "plane": pl["idx"], "line": q, "side": "lo",
                             "members": [mrec[id(m)]["id"] for m in mem if m["side"] == "lo"]}
    _REG["chains"][cid_h] = {"id": cid_h, "kind": "rafter", "plane": pl["idx"], "line": q, "side": "hi",
                             "members": [mrec[id(m)]["id"] for m in mem if m["side"] == "hi"]}
    _REG.setdefault("rafter_lines", {})[(pl["idx"], q)] = {"plane": pl["idx"], "line": q, "nodes": [node_at[a] for a in pts],
                                                           "a_mm": list(pts), "supports": [t for a, t in on],
                                                           "lo": lo, "hi": hi, "ridge": ridge,
                                                           "slope_factor": slope_len(lo, ridge) / (ridge - lo)}
    return et


def station_node(chain_id, s_mm):
    """Node of column chain `chain_id` at height s_mm above its base (an extra station or a segment end)."""
    ch = _REG["chains"][chain_id]
    for n, s_ in zip(ch["nodes"], ch["s_mm"]):
        if abs(s_ - float(s_mm)) < 1.0:
            return n
    raise KeyError("no station at %.0f mm on %s (declare it in extra_stations_mm)" % (s_mm, chain_id))


def beam(et, eles, nodes, label, *, kind="canopy", member_id=None, add_beam=None, gravity=True, root_joint=True):
    """A welded / tapered beam member along the given nodes (a cantilever canopy beam: nodes[0] = the root at the
    column, the label's start depth there).  Each element takes the section at its mid-length; stations as for the
    other stepped members.  gravity=True: not part of the moment frame (no Section 12 joint); root_joint=True
    registers the root as a moment connection designed for the factored root moment (peb_checks, kind
    'canopy_root', cfg['connections']['rafter_splice']['canopy_root'])."""
    import openseespy.opensees as ops
    import engine3d as E
    add_beam = add_beam or E.add_beam
    xyz = [ops.nodeCoord(n) for n in nodes]
    cum = [0.0]
    for a, b in zip(xyz, xyz[1:]):
        cum.append(cum[-1] + math.dist(a, b))
    L = cum[-1]
    mid = member_id or "B%d" % nodes[0]
    m = _member(mid, kind, label, nodes[0], nodes[-1], L, chain=mid, s0=0.0, s1=L)
    for e in range(len(nodes) - 1):
        f0, f1 = cum[e] / L, cum[e + 1] / L
        sec = section_at(label, 0.5 * (f0 + f1))
        add_beam(et, nodes[e], nodes[e + 1], sec)
        eles.append((et, "beam", sec, nodes[e], nodes[e + 1]))
        _element(et, m, cum[e], cum[e + 1], f0, f1, sec, section_at(label, f0), section_at(label, f1), nodes[e],
                 nodes[e + 1], mid, cum[e], cum[e + 1])
        if gravity:
            _REG["gravity"].add(et)
        et += 1
    for n in nodes[1:-1]:
        _REG["continuous"].add(n)
    _REG["chains"][mid] = {"id": mid, "kind": kind, "nodes": list(nodes), "members": [mid], "L_mm": L}
    if root_joint:
        _REG["splices"][nodes[0]] = {"kind": "canopy_root", "members": [mid], "chain": mid, "gravity": True,
                                     "sec_left": section_at(label, 0.0), "sec_right": section_at(label, 0.0)}
    return et


def nearest_column_face_mm(nd):
    """Rafter splice node -> plan distance to the nearest column-supported node of its rafter line, less half that
    column's face depth (IS 18168 6.5 location); None when unknown."""
    spl = _REG["splices"].get(nd)
    if not spl:
        return None
    ln = (_REG.get("rafter_lines") or {}).get((spl.get("plane"), spl.get("line")))
    cols = _REG.get("_col_nodes") or set()
    if not ln:
        return None
    a_s = spl.get("a_mm")
    best = None
    for a, n in zip(ln["a_mm"], ln["nodes"]):
        if n in cols:
            d = abs(a - a_s)
            if best is None or d < best[0]:
                best = (d, n)
    return best


def finish(info):
    """Attach the registry to the custom_build info dict (info['peb'])."""
    info["peb"] = snapshot()
    return info


def snapshot():
    return {"elements": dict(_REG["elements"]), "chains": dict(_REG["chains"]), "members": dict(_REG["members"]),
            "splices": dict(_REG["splices"]), "continuous_nodes": set(_REG["continuous"]),
            "frame_nodes": set(_REG["frame_nodes"]), "rafter_lines": dict(_REG.get("rafter_lines") or {}),
            "gravity": set(_REG["gravity"])}


def active():
    return bool(_REG["elements"])


# ------------------------------------------------------------------------------------------------ queries
def element(t):
    return _REG["elements"].get(int(t)) if str(t).lstrip("e").isdigit() else None


def stations(t):
    """(sec_i, sec_j) exact end sections of a stepped element of a tapered member, else None."""
    e = _REG["elements"].get(int(t))
    if not e or e["sec_i"] == e["sec_j"] == e["section"]:
        return None
    return e["sec_i"], e["sec_j"]


def face_section(t, node):
    """D-T7: the section of element t at node (the joint face), else None."""
    e = _REG["elements"].get(int(t))
    if not e:
        return None
    if node == e["n1"]:
        return e["sec_i"]
    if node == e["n2"]:
        return e["sec_j"]
    return None


def is_gravity(t):
    """A rafter element of a declared gravity line (plane key 'gravity_lines', e.g. the post-and-beam gable frames)."""
    return int(t) in _REG["gravity"]


def is_continuous(node):
    return node in _REG["continuous"]


def splices():
    return dict(_REG["splices"])


def member_of(t):
    e = _REG["elements"].get(int(t))
    return _REG["members"].get(e["member"]) if e else None


def _gaps(restr, a0, a1, total):
    """Largest distance between consecutive restraints (incl. 0 and total) over the interval [a0, a1]."""
    pts = sorted(set([0.0, float(total)] + [float(x) for x in restr if 0.0 <= float(x) <= float(total)]))
    best = 0.0
    for p0, p1 in zip(pts, pts[1:]):
        if p1 > a0 + 1e-6 and p0 < a1 - 1e-6:
            best = max(best, p1 - p0)
    return best or (a1 - a0)


def chain_frame_span(t):
    """Rafter element t: (plan length between the frame nodes bounding its chain piece, slope factor)."""
    e = _REG["elements"].get(int(t))
    if not e:
        return None
    m = _REG["members"].get(e["member"])
    if not m or m["kind"] != "rafter":
        return None
    ln = (_REG.get("rafter_lines") or {}).get((m["plane"], m["line"]))
    if not ln:
        return None
    am = 0.5 * (e["pos_mm"][0] + e["pos_mm"][1])
    sup = sorted(set([ln["lo"], ln["hi"]] + [a for a, nd in zip(ln["a_mm"], ln["nodes"]) if nd in ln["supports"]]))
    for p0, p1 in zip(sup, sup[1:]):
        if p0 - 1e-6 <= am <= p1 + 1e-6:
            return p1 - p0, ln["slope_factor"], (p0, p1)
    return None


def support_span(t):
    """Rafter element t: plan span between the COLUMN supports bounding it (eave to eave of a clear span; eave to
    the interior column of a multi-span frame)."""
    e = _REG["elements"].get(int(t))
    if not e:
        return None
    m = _REG["members"].get(e["member"])
    if not m or m["kind"] != "rafter":
        return None
    ln = (_REG.get("rafter_lines") or {}).get((m["plane"], m["line"]))
    cols = _REG.get("_col_nodes") or set()
    am = 0.5 * (e["pos_mm"][0] + e["pos_mm"][1])
    sup = sorted(set([ln["lo"], ln["hi"]] + [a for a, nd in zip(ln["a_mm"], ln["nodes"]) if nd in cols]))
    for p0, p1 in zip(sup, sup[1:]):
        if p0 - 1e-6 <= am <= p1 + 1e-6:
            return p1 - p0
    return ln["hi"] - ln["lo"]


def overrides(cfg, t):
    """D-T1 element overrides {LLT_sag_mm, LLT_hog_mm, Ly_mm, Lz_mm, buckling_section, c1} for a PEB element."""
    e = _REG["elements"].get(int(t))
    if not e:
        return {}
    m = _REG["members"].get(e["member"])
    fb = (cfg or {}).get("flange_braces") or {}
    out = {"c1": 1.0}
    if m["kind"] not in ("column", "rafter"):
        # cantilever / other beam members: restraints from cfg['flange_braces'][kind] {'purlins_mm', 'fly_braces_mm'}
        # (distances from the root), else the member length
        cb = fb.get(m["kind"]) or {}
        L = m["L_mm"]
        top = _gaps(cb.get("purlins_mm") or [], e["s_mm"][0], e["s_mm"][1], L)
        bot = _gaps(cb.get("fly_braces_mm") or [], e["s_mm"][0], e["s_mm"][1], L)
        out.update(LLT_sag_mm=top, LLT_hog_mm=bot, Ly_mm=bot, Lz_mm=L)
        p = parse(m["section"])
        out["buckling_section"] = section_at(m["section"], 1.0 if (p[0] == "tapered" and p[1] > p[2]) else 0.0)
        return out
    if m["kind"] == "column":
        ch = _REG["chains"][m["chain"]]
        H = ch["L_mm"]
        cb = ch.get("restraints") if ch.get("restraints") is not None else (fb.get("column") or {})
        g = _gaps(cb.get("girts_mm") or [], e["s_mm"][0], e["s_mm"][1], H)
        f = _gaps(cb.get("fly_braces_mm") or [], e["s_mm"][0], e["s_mm"][1], H)
        L = max(g, f)
        out.update(LLT_sag_mm=L, LLT_hog_mm=L, Ly_mm=f, Lz_mm=H)
        labs = [_REG["members"][mm]["section"] for mm in ch["members"]]
    else:
        fs = chain_frame_span(t)
        sf = fs[1] if fs else 1.0
        rb = fb.get("rafter") or {}
        span_a = fs[2] if fs else (e["s_mm"][0], e["s_mm"][1])
        # restraint positions are plan distances from the eave of each slope; map them to plan coordinates
        ln = (_REG.get("rafter_lines") or {}).get((m["plane"], m["line"]))
        lo, hi, ridge = ln["lo"], ln["hi"], ln["ridge"]
        def coords(lst):
            out_ = set()
            for d in lst:
                for a in (lo + float(d), hi - float(d)):
                    if lo - 1 <= a <= hi + 1:
                        out_.add(a)
            out_ |= {lo, hi, ridge}
            out_ |= {a for a, nd in zip(ln["a_mm"], ln["nodes"]) if nd in ln["supports"]}
            return sorted(out_)
        pur, fly = coords(rb.get("purlins_mm") or []), coords(rb.get("fly_braces_mm") or [])
        a0, a1 = sorted(e["pos_mm"])
        def gap(pts):
            best = 0.0
            for p0, p1 in zip(pts, pts[1:]):
                if p1 > a0 + 1e-6 and p0 < a1 - 1e-6:
                    best = max(best, p1 - p0)
            return (best or (a1 - a0)) * sf
        out.update(LLT_sag_mm=gap(pur), LLT_hog_mm=gap(fly), Ly_mm=gap(fly),
                   Lz_mm=(fs[0] * sf if fs else e["s_mm"][1] - e["s_mm"][0]))
        labs = [_REG["members"][mm]["section"] for mm in _REG["chains"][m["chain"]]["members"]]
    # major-axis member buckling: the smallest section of the chain (D-T1)
    cands = []
    for lab in labs:
        p = parse(lab)
        if p[0] == "tapered":
            cands.append(section_at(lab, 0.0 if p[1] <= p[2] else 1.0))
        else:
            cands.append(lab)
    if cands:
        out["buckling_section"] = min(cands, key=lambda s_: float(S.props(s_)["Ix"]))
    return out


def set_column_nodes(nodes):
    """design_pipeline: the nodes that carry a column (rafter supports for support_span)."""
    _REG["_col_nodes"] = set(nodes)
