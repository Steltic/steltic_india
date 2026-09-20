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
    if dia not in ("rigid",):
        raise DiaphragmError("diaphragm %r: collector / chord forces need a flexible or semi-rigid diaphragm "
                             "model, which the engine does not provide -- the EOR must supply them (WP2.6)" % dia)
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
        for k in range(1, NF + 1):
            nodes = [E.ntag(i, j, k) for (i, j) in info["present"][k]]
            crd = {n: ops.nodeCoord(n) for n in nodes}
            tot = sum(r.get(n, 0.0) for n in nodes)
            if abs(tot) < 1e-6:
                continue
            sg = 1.0 if tot > 0 else -1.0
            lines = {}
            for n in nodes:
                i, j = _ij(n)
                lines.setdefault(j if d == "X" else i, []).append(n)
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
