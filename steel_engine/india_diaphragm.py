"""WP2.6 -- diaphragm load path: collector (drag) and chord axial forces for India jobs.

The rigid-diaphragm constraint of the engine model gives every floor beam P = 0, so collectors and
braced-bay beams would be designed for flexure only.  This module recovers the axial forces from
equilibrium of the analysed model:

1. Apply the unfactored story forces (EQ_<d> or W_<d>, N) at the diaphragm masters (gamma = 1.0),
   linear analysis on the engine model.
2. At every level k and every frame line parallel to the force, the diaphragm delivers to each
   node the sum of the horizontal end forces of the vertical elements (columns + braces) framing
   into it (storey below and storey above): r_n.  The line total R_line is the line's share of F_k
   (rigid diaphragm -> stiffness-based, including torsion).
3. Collector (drag) force along the line, with the diaphragm shear flow q = R_line / L_line spread
   uniformly along the line:  N(x) = q (x - x0) - sum_{x_n < x} r_n  (positive = compression under a
   +d force; the combinations carry both signs).  Each beam segment gets the larger |N| at its ends.
4. Chords: the diaphragm spans between the lines as a beam loaded by w = F_k / depth, supported by
   the line reactions: M(s) = w (s - s0)^2 / 2 - sum_{s_l < s} R_l (s - s_l); chord force M / B on
   the two edge beams normal to the force (B = plan dimension along the force).

Returned forces are per unit lateral factor (fE / fW = 1).  design_pipeline.design_india adds
fLat x N to the beam records of every lateral combination before the IS 800 member checks
(9.3 interaction).  Flexible diaphragms (IS 1893 7.6.4 / Amd 2 Table 5(ii) re-entrant plans) are
NOT modelled here: collector_forces() raises so the job cannot pass silently.
"""
from __future__ import annotations

import openseespy.opensees as ops

CITE = ("Diaphragm load path by equilibrium of the analysed model (IS 1893 (Part 1):2016 7.6.4 rigid "
        "diaphragm; collector / chord axial combined with flexure under IS 800:2007 9.3)")


class DiaphragmError(RuntimeError):
    pass


def _lvl(n):
    return n // 100000


def _ij(n):
    r = n % 100000
    return r // 100, r % 100


def _story_forces(cfg, d, kind):
    import engine3d as E
    return E.india_story_forces(cfg, d, kind=kind)


def collector_forces(cfg, kind="EQ"):
    """{'X': {beam_tag: N_comp}, 'Y': {...}, 'rows': [...]} per unit lateral factor (N)."""
    import engine3d as E
    dia = str(cfg.get("diaphragm") or "rigid").lower()
    if dia in ("flexible",):
        return _collector_forces_flexible(cfg, kind)
    if dia not in ("rigid",):
        raise DiaphragmError("diaphragm %r: collector / chord forces need a rigid or flexible diaphragm model "
                             "(semi-rigid shell diaphragms are not provided) -- the EOR must supply them (WP2.6)" % dia)
    out = {"X": {}, "Y": {}, "rows": [], "kind": kind, "cite": CITE}
    for d in ("X", "Y"):
        F = _story_forces(cfg, d, kind)
        if not F:
            continue
        di = 0 if d == "X" else 1
        info = E.build(cfg, "Linear")
        NF = info["NF"]
        ops.timeSeries("Linear", 1); ops.pattern("Plain", 1, 1)
        for k in range(1, NF + 1):
            fx, fy, mz = F.get(k, (0.0, 0.0, 0.0))
            ops.load(E.mtag(k), fx, fy, 0.0, 0.0, 0.0, mz)
        ops.constraints("Transformation"); ops.numberer("RCM"); ops.system("UmfPack")
        ops.test("NormDispIncr", 1e-8, 50); ops.algorithm("Linear")
        ops.integrator("LoadControl", 1.0); ops.analysis("Static")
        if ops.analyze(1) != 0:
            raise DiaphragmError("collector analysis (%s) failed" % d)
        # node deliveries r_n from vertical elements
        r = {}
        beams = {}
        for (t, kind_e, sec, n1, n2) in info["ele"]:
            if kind_e == "beam":
                beams[frozenset((n1, n2))] = t
                continue
            if _lvl(n1) == _lvl(n2):
                continue
            gf = ops.eleResponse(t, "globalForce")
            for nd, off in ((n1, 0), (n2, 6)):
                if _lvl(nd) >= 1:
                    r[nd] = r.get(nd, 0.0) + gf[off + di]
        # sign: make the level total positive along +d
        ax = 0 if d == "X" else 1           # coordinate along the force
        zlev = E.zlevels(cfg)
        for k in range(1, NF + 1):
            nodes = [E.ntag(i, j, k) for (i, j) in info["present"][k]]
            crd = {n: ops.nodeCoord(n) for n in nodes}
            # off-grid work points at this level (EBF link ends, WP6): the braces deliver their storey shear
            # to the diaphragm THERE, on the frame line, so they are part of the line's node set
            gridset = set(nodes)
            for n in r:
                if n in gridset or n == E.mtag(k) or n >= 9_000_000:
                    continue
                c = ops.nodeCoord(n)
                if abs(c[2] - zlev[k]) < 1e-6:
                    nodes.append(n); crd[n] = c
            tot = sum(r.get(n, 0.0) for n in nodes)
            if abs(tot) < 1e-6:
                continue
            sg = 1.0 if tot > 0 else -1.0
            lines = {}
            # line key = the coordinate normal to the force (grid nodes and work points on one line share it)
            for n in nodes:
                lines.setdefault(round(crd[n][1 if d == "X" else 0], 1), []).append(n)
            reac = []
            for key, ln in lines.items():
                ln.sort(key=lambda n: crd[n][ax])
                rr = [sg * r.get(n, 0.0) for n in ln]
                R = sum(rr)
                pos = crd[ln[0]][1 - ax]
                reac.append((pos, R))
                if abs(R) < 1e-3 * abs(tot) or len(ln) < 2:
                    continue
                x0, x1 = crd[ln[0]][ax], crd[ln[-1]][ax]
                q = R / (x1 - x0)
                acc = 0.0
                for a, b in zip(ln[:-1], ln[1:]):
                    acc += rr[ln.index(a)]
                    Na = q * (crd[a][ax] - x0) - acc
                    Nb = q * (crd[b][ax] - x0) - acc
                    N = Na if abs(Na) >= abs(Nb) else Nb
                    t = beams.get(frozenset((a, b)))
                    if t is None or abs(N) < 1.0:
                        continue
                    out[d][t] = out[d].get(t, 0.0) + N
                    out["rows"].append({"dir": d, "level": k, "line": key, "beam": t, "role": "collector",
                                        "N_N": round(N, 1), "q_N_per_mm": round(q, 4), "R_line_N": round(R, 1)})
            # chords: diaphragm spanning between the lines (coordinate s normal to the force)
            reac.sort()
            svals = sorted({crd[n][1 - ax] for n in nodes})
            s0, s1 = svals[0], svals[-1]
            if s1 - s0 <= 0:
                continue
            w = sum(R for _, R in reac) / (s1 - s0)
            B = max(c[ax] for c in crd.values()) - min(c[ax] for c in crd.values())
            if B <= 0:
                continue

            def M(s):
                return w * (s - s0) ** 2 / 2.0 - sum(R * (s - sl) for sl, R in reac if sl < s - 1e-9)
            lo = min(c[ax] for c in crd.values()); hi = max(c[ax] for c in crd.values())
            for edge, sgn in ((lo, 1.0), (hi, -1.0)):
                en = sorted([n for n in nodes if abs(crd[n][ax] - edge) < 1e-6], key=lambda n: crd[n][1 - ax])
                for a, b in zip(en[:-1], en[1:]):
                    t = beams.get(frozenset((a, b)))
                    if t is None:
                        continue
                    Ms = max((M(crd[a][1 - ax]), M(crd[b][1 - ax])), key=abs)
                    Tn = sgn * Ms / B
                    if abs(Tn) < 1.0:
                        continue
                    out[d][t] = out[d].get(t, 0.0) + Tn
                    out["rows"].append({"dir": d, "level": k, "beam": t, "role": "chord", "N_N": round(Tn, 1),
                                        "M_diaphragm_Nmm": round(Ms, 0), "B_mm": round(B, 0)})
    return out


def collector_demands(cfg, run=None, reg=None):
    """Rows for calc_package['collectors'] (EQ and W), unit lateral factor."""
    rows = []
    for kind in ("EQ", "W"):
        try:
            cf = collector_forces(cfg, kind)
        except DiaphragmError as ex:
            return [{"error": str(ex)}]
        for r in cf["rows"]:
            rows.append(dict(r, kind=kind, units="N per unit fE/fW (+ = compression under +dir)", cite=CITE))
    return rows


def add_to_records(per_case, cases, reg, cfg, *, amplify_12_2_3=False):
    """Add fLat x collector/chord N to the beam records of every lateral combination (in place).

    per_case: {label: {frozenset(n1, n2): rec}} (static_model.solve_cases_si); records are tuples with
    N (tension +) first.  12.2.3-tagged combinations (col_only) receive the forces too, and are kept
    for the collector members' checks only when amplify_12_2_3 (EOR basis) is set.
    Returns {beam_tag: max |added N|}."""
    cache = {}
    added = {}
    tag_of = {frozenset((n1, n2)): t for t, (k, s_, n1, n2) in reg.items() if k == "beam"}
    for c in cases:
        m = getattr(c, "meta", {}) or {}
        kind, d, f = m.get("kind"), m.get("direction"), m.get("fLat")
        if kind not in ("EQ", "W") or d not in ("X", "Y") or not f or m.get("service"):
            continue
        if kind not in cache:
            cache[kind] = collector_forces(cfg, kind)
        cf = cache[kind][d]
        res = per_case.get(c[0])
        if not res:
            continue
        extra = [(t2["ref"][-1], float(t2["f"])) for t2 in (m.get("source") or {}).get("terms") or []
                 if str(t2.get("ref", "")).startswith(kind + "_")]
        for fs, rec in list(res.items()):
            t = tag_of.get(fs)
            if t is None:
                continue
            Nc = float(f) * cf.get(t, 0.0) + sum(ff * cache[kind][dd].get(t, 0.0) for dd, ff in extra)
            if Nc == 0.0:
                continue
            rec = list(rec)
            rec[0] = rec[0] - Nc                     # compression + under +dir -> tension-positive record
            res[fs] = tuple(rec)
            added[t] = max(added.get(t, 0.0), abs(Nc))
    return added


# =====================================================================================================
# IS 1893 (Part 1):2016 7.6.4 -- diaphragm classification and the flexible-diaphragm distribution
# (HR-INTEGRATE; text from IS_1893_Part_1_2016 page_025.md).  Pure functions: the flexible-diaphragm
# 3D model (nodal masses, deck shear stiffness) is the wave-3 engine item; until then a job declaring
# cfg['diaphragm'] = 'flexible' gets its storey shear distributed here by tributary width and the
# braced-line shears written to the package for the line members / collectors.
# =====================================================================================================
CITE_7_6_4 = ("IS 1893 (Part 1):2016 7.6.4: 'flexible, if ... the maximum lateral displacement measured from the "
              "chord of the deformed shape at any point of the diaphragm is more than 1.2 times the average "
              "displacement of the entire diaphragm'; rigid action for RC slabs / screeded precast with plan aspect "
              "ratio < 3")


def classify_7_6_4(*, delta_max_from_chord_mm=None, delta_avg_mm=None, declared=None, rc_slab=None,
                   screed_mm=None, roof=False, plan_aspect_ratio=None):
    """Rigid / flexible per 7.6.4.  With measured deflections: flexible when delta_max(chord) > 1.2 x average.
    Without them, the 'usually rigid' rule (RC monolithic slab, or precast with >= 50 mm floor / 75 mm roof screed,
    plan aspect ratio < 3) classifies as rigid; a bare metal deck / braced roof with no such data must be DECLARED
    (declared='flexible'|'rigid' with the EOR's basis) -- otherwise ok=None."""
    out = {"clause": "IS 1893 (Part 1):2016 7.6.4", "cite": CITE_7_6_4}
    if delta_max_from_chord_mm is not None and delta_avg_mm:
        r = float(delta_max_from_chord_mm) / float(delta_avg_mm)
        out.update(method="deflection ratio (Fig. 6)", ratio=r, limit=1.2, flexible=r > 1.2,
                   classification="flexible" if r > 1.2 else "rigid", ok=True)
        return out
    if rc_slab or (screed_mm is not None and float(screed_mm) >= (75.0 if roof else 50.0)):
        ar_ok = plan_aspect_ratio is None or float(plan_aspect_ratio) < 3.0
        out.update(method="7.6.4 'usually rigid' rule", flexible=not ar_ok,
                   classification="rigid" if ar_ok else "flexible (plan aspect ratio >= 3)", ok=True,
                   plan_aspect_ratio=plan_aspect_ratio)
        return out
    if declared in ("flexible", "rigid"):
        out.update(method="declared by the EOR (7.6.4 basis to be recorded)", classification=declared,
                   flexible=declared == "flexible", ok=True)
        return out
    out.update(method=None, classification=None, flexible=None, ok=None,
               reason="7.6.4 classification needs the diaphragm deflection ratio, an RC/screeded slab, or a declaration")
    return out


def tributary_line_shears(story_force_N, line_positions_mm, mass_extent_mm, *, eccentricity_mm=0.0):
    """Flexible diaphragm: the storey force is distributed to the vertical lateral elements by tributary width
    (7.6.4 'considering the in-plane flexibility'); no diaphragm torsion is transferred, so the 7.8.2 eccentricity
    acts as a shift of the mass centre (the tributary widths are measured about the shifted mass distribution).

    line_positions_mm: sorted coordinates (perpendicular to the force) of the braced / moment lines;
    mass_extent_mm: (x_min, x_max) of the uniformly distributed floor mass.  Returns {position: V_N}."""
    x0, x1 = float(mass_extent_mm[0]) + float(eccentricity_mm), float(mass_extent_mm[1]) + float(eccentricity_mm)
    L = x1 - x0
    pos = sorted(float(p) for p in line_positions_mm)
    if not pos or L <= 0:
        raise DiaphragmError("tributary distribution needs >= 1 line and a positive mass extent")
    out = {}
    for i, p in enumerate(pos):
        lo = x0 if i == 0 else 0.5 * (pos[i - 1] + p)
        hi = x1 if i == len(pos) - 1 else 0.5 * (p + pos[i + 1])
        w = max(min(hi, x1) - max(lo, x0), 0.0)
        out[p] = float(story_force_N) * w / L
    return out


def flexible_diaphragm_line_shears(cfg, kind="EQ"):
    """cfg['diaphragm'] == 'flexible': per storey and direction, the storey force by tributary width to the lateral
    lines (braced bays / moment frames) -- {d: {level: {line_coord_mm: V_N}}} per unit lateral factor, plus the
    7.8.2 eccentricity variants (+/- 0.05 b as a mass-centre shift, 7.8.2 e_si = 0 for a symmetric flexible floor
    without a torsional load path)."""
    import engine3d as E
    info = E.build(cfg, "Linear")
    NF = info["NF"]
    lines = {"X": set(), "Y": set()}
    for (t, k_, sec, n1, n2) in info["ele"]:
        if k_ == "brace":
            c1, c2 = ops.nodeCoord(n1), ops.nodeCoord(n2)
            if abs(c2[0] - c1[0]) >= abs(c2[1] - c1[1]):
                lines["X"].add(round(c1[1], 1))           # X-direction brace line at y = const
            else:
                lines["Y"].add(round(c1[0], 1))
    for nd in info.get("moment_nodes", set()):
        pass                                            # moment frames: declared via cfg['lateral_lines'] when no braces
    decl = cfg.get("lateral_lines") or {}
    for d in ("X", "Y"):
        for v in decl.get(d) or []:
            lines[d].add(float(v))
    xs = [ops.nodeCoord(E.ntag(i, j, 1))[0] for (i, j) in info["present"][1]]
    ys = [ops.nodeCoord(E.ntag(i, j, 1))[1] for (i, j) in info["present"][1]]
    ext = {"X": (min(ys) - cfg["SY"] / 2.0, max(ys) + cfg["SY"] / 2.0),
           "Y": (min(xs) - cfg["SX"] / 2.0, max(xs) + cfg["SX"] / 2.0)}
    out = {"cite": CITE_7_6_4 + "; tributary-width distribution (no diaphragm torsion)", "kind": kind, "lines": {}}
    for d in ("X", "Y"):
        F = _story_forces(cfg, d, kind)
        if not F or not lines[d]:
            continue
        di = 0 if d == "X" else 1
        b = ext[d][1] - ext[d][0]
        out["lines"][d] = sorted(lines[d])
        for k in range(1, NF + 1):
            f = F.get(k, (0.0, 0.0, 0.0))[di]
            for tag, e in (("e0", 0.0), ("ea", 0.05 * b), ("eb", -0.05 * b)):
                out.setdefault(tag, {}).setdefault(d, {})[k] = tributary_line_shears(f, sorted(lines[d]), ext[d],
                                                                                    eccentricity_mm=e)
    return out


def _collector_forces_flexible(cfg, kind="EQ"):
    """Flexible diaphragm (7.6.4): each lateral line receives its tributary storey shear; the collector on that
    line carries the accumulated deck shear into the braced bay, so every beam on the line at that level is
    given the line shear as its collector axial (upper bound: the whole line shear reaches the bay through one
    beam).  Chord forces: the deck spans between lines as a simple beam of span s (the tributary panel) -- chord
    T = w s^2 / (8 B) with w = the panel's share of the storey force per unit length and B the panel depth."""
    import engine3d as E
    ls = flexible_diaphragm_line_shears(cfg, kind)
    info = E.build(cfg, "Linear")
    NF = info["NF"]
    out = {"X": {}, "Y": {}, "rows": [], "kind": kind, "cite": CITE_7_6_4 + " (tributary distribution)",
           "diaphragm": "flexible"}
    beams = {}
    for (t, k_, sec, n1, n2) in info["ele"]:
        if k_ == "beam":
            c1, c2 = ops.nodeCoord(n1), ops.nodeCoord(n2)
            d = "X" if abs(c2[0] - c1[0]) >= abs(c2[1] - c1[1]) else "Y"
            beams.setdefault((d, _lvl(n1), round(c1[1] if d == "X" else c1[0], 1)), []).append(t)
    for d, lines in (ls.get("lines") or {}).items():
        for k in range(1, NF + 1):
            sh = (ls.get("e0") or {}).get(d, {}).get(k) or {}
            for pos, V in sh.items():
                for t in beams.get((d, k, round(pos, 1)), []):
                    out[d][t] = out[d].get(t, 0.0) + abs(V)
                    out["rows"].append({"dir": d, "level": k, "line": pos, "beam": t, "role": "collector",
                                        "N_N": round(abs(V), 1), "R_line_N": round(V, 1), "basis": "tributary line shear"})
            # chords: panel between adjacent lines, uniform deck load w = (F x panel width / b) / span
            srt = sorted(lines)
            F = sum(abs(v) for v in sh.values())
            b = (srt[-1] - srt[0]) if len(srt) > 1 else 0.0
            for a, c in zip(srt[:-1], srt[1:]):
                span = c - a
                w = F * (span / b) / span if b else 0.0
                # panel depth B = building dimension along the force
                xs = [ops.nodeCoord(E.ntag(i, j, k))[0 if d == "X" else 1] for (i, j) in info["present"][k]]
                B = (max(xs) - min(xs)) if xs else 0.0
                if B <= 0:
                    continue
                T = w * span ** 2 / (8.0 * B)
                dd = "Y" if d == "X" else "X"
                for pos_edge in (min(xs), max(xs)):
                    for t in beams.get((dd, k, round(pos_edge, 1)), []):
                        out[dd][t] = out[dd].get(t, 0.0) + T
                        out["rows"].append({"dir": d, "level": k, "beam": t, "role": "chord", "N_N": round(T, 1),
                                            "span_mm": span, "B_mm": B, "basis": "flexible panel w s^2/(8 B)"})
    return out
