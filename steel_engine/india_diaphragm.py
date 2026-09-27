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


DIAPHRAGM_LABELS = ("rigid", "flexible")


def diaphragm_labels(cfg):
    """GOLD-COLL: the diaphragm label of every level 1..NF -- cfg['diaphragm_by_level'] = {k | 'k' | 'a-b' |
    'default': 'rigid' | 'flexible'} (e.g. a composite podium rigid under flexible CFS floors), else cfg['diaphragm']
    (default 'rigid') for the levels it does not name.  Returns ({k: label}, [errors])."""
    NF = len(cfg.get("heights") or [])
    base = str(cfg.get("diaphragm") or "rigid").lower()
    bl = cfg.get("diaphragm_by_level")
    errs = []
    labels = {k: base for k in range(1, NF + 1)}
    if bl in (None, {}, ""):
        return labels, errs
    if not isinstance(bl, dict):
        return labels, ["cfg['diaphragm_by_level'] must be {level | 'a-b' | 'default': 'rigid' | 'flexible'} (got %r)"
                        % (bl,)]
    import india_flexible_diaphragm as FD
    if "default" in bl:
        dv = str(bl["default"] or "").lower()
        if dv not in DIAPHRAGM_LABELS:
            errs.append("cfg['diaphragm_by_level']['default'] = %r: must be 'rigid' | 'flexible'" % (bl["default"],))
        else:
            labels = {k: dv for k in labels}
    seen = set()
    for key, v in bl.items():
        if key == "default":
            continue
        ks = FD._level_keys(key, NF)
        lab = str(v or "").lower()
        if ks is None:
            errs.append("cfg['diaphragm_by_level'] key %r is not a level 1..%d or a range 'a-b'" % (key, NF))
            continue
        if lab not in DIAPHRAGM_LABELS:
            errs.append("cfg['diaphragm_by_level'][%r] = %r: must be 'rigid' | 'flexible'" % (key, v))
            continue
        for k in ks:
            if k in seen:
                errs.append("cfg['diaphragm_by_level'] gives level %d twice" % k)
            seen.add(k)
            labels[k] = lab
    return labels, errs


def flexible_levels(cfg):
    """Levels labelled flexible (diaphragm_labels); malformed declarations give an empty set (preflight ERRORs)."""
    labels, errs = diaphragm_labels(cfg)
    return set() if errs else {k for k, v in labels.items() if v == "flexible"}


X01_COLLECTOR_NOTE = ("flexible-labelled levels, EQ combinations enveloped with the X01 flexible-diaphragm run "
                      "(IS 1893 Table 5(ii)): the rigid half carries the rigid-diaphragm load-path collectors / chords "
                      "(consistent with the rigid model), the flexible half the beam axial forces of the X01 deck model "
                      "directly (india_flexible_diaphragm.merge_records); the tributary accumulation is not added")


def collector_forces(cfg, kind="EQ", *, x01_flexible=False):
    """{'X': {beam_tag: N_comp}, 'Y': {...}, 'rows': [...]} per unit lateral factor (N).

    Per level (diaphragm_labels): rigid levels -> load path by equilibrium of the analysed rigid model; flexible
    levels -> accumulation of the tributary deck shear along each braced / frame line (_collector_forces_flexible).
    x01_flexible: the combination is enveloped with the X01 flexible-deck run, whose beam axial forces ARE the
    flexible case -- the flexible levels then take the rigid-case collectors here (X01_COLLECTOR_NOTE)."""
    labels, errs = diaphragm_labels(cfg)
    if errs:
        raise DiaphragmError("; ".join(errs))
    bad = sorted({v for v in labels.values() if v not in DIAPHRAGM_LABELS})
    if bad:
        raise DiaphragmError("diaphragm %r: collector / chord forces need a rigid or flexible diaphragm model "
                             "(semi-rigid shell diaphragms are not provided) -- the EOR must supply them (WP2.6)"
                             % bad[0])
    allk = set(labels)
    flex = {k for k, v in labels.items() if v == "flexible"}
    flex_acc = set() if x01_flexible else flex
    rig = allk - flex_acc
    if flex and flex == allk and not x01_flexible:
        out = _collector_forces_flexible(cfg, kind)
    else:
        out = _collector_forces_rigid(cfg, kind, levels=rig) if rig else {"X": {}, "Y": {}, "rows": [], "kind": kind,
                                                                           "cite": CITE}
        if flex_acc:
            fo = _collector_forces_flexible(cfg, kind, levels=flex_acc)
            for d in ("X", "Y"):
                for t, v in fo[d].items():
                    out[d][t] = out[d].get(t, 0.0) + v
            out["rows"] += fo["rows"]
            for q in ("upper_bound_lines", "accumulation_basis"):
                if fo.get(q):
                    out[q] = fo[q]
        out["diaphragm"] = "flexible" if flex == allk and flex else ("rigid" if not flex else "by_level")
    if cfg.get("diaphragm_by_level"):
        out["diaphragm_by_level"] = {str(k): v for k, v in sorted(labels.items())}
    if x01_flexible and flex:
        out["x01_flexible"] = True
        out["x01_note"] = X01_COLLECTOR_NOTE
        for r in out["rows"]:
            if r.get("level") in flex:
                r["case"] = "rigid half of the Table 5(ii) envelope (X01 deck-model axial = flexible half)"
    return out


def _collector_forces_rigid(cfg, kind="EQ", levels=None):
    """Rigid-diaphragm load path (module docstring 1-4); levels: the levels to evaluate (None = all)."""
    import engine3d as E
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
            if levels is not None and k not in levels:
                continue
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


def collector_demands(cfg, run=None, reg=None, x01_flexible=False):
    """Rows for calc_package['collectors'] (EQ and W), unit lateral factor.  x01_flexible (the EQ combinations were
    enveloped with the X01 flexible-deck run): the flexible levels' EQ rows of the rigid half are added with
    case = 'rigid half ...' beside the tributary-accumulation rows (which then apply to non-enveloped combinations)."""
    rows = []
    flex = flexible_levels(cfg)
    variants = [("EQ", False), ("W", False)]
    if x01_flexible and flex:
        variants.insert(1, ("EQ", True))
    for kind, x01 in variants:
        try:
            cf = collector_forces(cfg, kind, x01_flexible=x01)
        except DiaphragmError as ex:
            return [{"error": str(ex)}]
        for r in cf["rows"]:
            if x01 and r.get("level") not in flex:
                continue                                  # same rows as the plain EQ variant
            # H49: a row keeps its own cite (flexible rows cite 7.6.4 flexible / tributary), else the result's cite
            rows.append(dict(r, kind=kind, units="N per unit fE/fW (+ = compression under +dir)",
                             cite=r.get("cite") or cf.get("cite") or CITE))
        if x01:
            rows.append({"kind": kind, "role": "note", "levels": sorted(flex), "note": X01_COLLECTOR_NOTE,
                         "cite": "IS 1893 (Part 1):2016 Table 5(ii) (Amd 2); 7.6.4"})
    return rows


def pattern_collector_forces(cfg, kind, ref):
    """X05: collector / chord forces {beam_tag: N} per unit factor for a named story-force pattern that is not a plain
    <kind>_X / <kind>_Y (e.g. the IS 875-3 10.3 across-wind pattern W_X_across, which acts along Y): the pattern is
    run alone through collector_forces in the force direction it carries."""
    plan = cfg.get("load_plan") or {}
    raw = (plan.get("story_forces") or {}).get(ref)
    if not raw:
        return {}
    import india_loads as IL
    lat = IL._as_lateral(raw)
    sx = sum(abs(v[0]) for v in lat.values())
    sy = sum(abs(v[1]) for v in lat.values())
    dF = "X" if sx >= sy else "Y"
    cfg2 = dict(cfg, load_plan=dict(plan, story_forces={kind + "_" + dF: raw}))
    return dict(collector_forces(cfg2, kind).get(dF) or {})


def add_to_records(per_case, cases, reg, cfg, *, amplify_12_2_3=False, x01_labels=None):
    """Add fLat x collector/chord N to the beam records of every lateral combination (in place).

    per_case: {label: {frozenset(n1, n2): rec}} (static_model.solve_cases_si); records are tuples with
    N (tension +) first.  12.2.3-tagged combinations (col_only) receive the forces too, and are kept
    for the collector members' checks only when amplify_12_2_3 (EOR basis) is set.
    x01_labels: the combinations enveloped with the X01 flexible-deck run (Table 5(ii)); for them the flexible
    levels take the rigid-case collectors (collector_forces x01_flexible, X01_COLLECTOR_NOTE).
    Returns {beam_tag: max |added N|}."""
    cache = {}
    added = {}
    x01_labels = set(x01_labels or ()) if flexible_levels(cfg) else set()
    tag_of = {frozenset((n1, n2)): t for t, (k, s_, n1, n2) in reg.items() if k == "beam"}
    for c in cases:
        m = getattr(c, "meta", {}) or {}
        kind, d, f = m.get("kind"), m.get("direction"), m.get("fLat")
        if kind not in ("EQ", "W") or d not in ("X", "Y") or not f or m.get("service"):
            continue
        x01 = c[0] in x01_labels
        ck = (kind, x01)
        if ck not in cache:
            cache[ck] = collector_forces(cfg, kind, x01_flexible=x01)
        cf = cache[ck][d]
        res = per_case.get(c[0])
        if not res:
            continue
        extra = []
        for t2 in (m.get("source") or {}).get("terms") or []:
            ref2 = str(t2.get("ref", ""))
            if not ref2.startswith(kind + "_"):
                continue
            dd = ref2[len(kind) + 1:]
            if dd in ("X", "Y"):
                extra.append((cache[ck][dd], float(t2["f"])))
            else:                                   # X05: e.g. W_X_across -- collectors of that pattern itself
                if ref2 not in cache:
                    cache[ref2] = pattern_collector_forces(cfg, kind, ref2)
                extra.append((cache[ref2], float(t2["f"])))
        for fs, rec in list(res.items()):
            t = tag_of.get(fs)
            if t is None:
                continue
            Nc = float(f) * cf.get(t, 0.0) + sum(ff * mp.get(t, 0.0) for mp, ff in extra)
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
                   screed_mm=None, roof=False, plan_aspect_ratio=None, basis=None):
    """Rigid / flexible per 7.6.4.  With measured deflections: flexible when delta_max(chord) > 1.2 x average.
    Without them, the 'usually rigid' rule (RC monolithic slab, or precast with >= 50 mm floor / 75 mm roof screed,
    plan aspect ratio < 3) classifies as rigid; a bare metal deck / braced roof with no such data must be DECLARED
    (declared='flexible'|'rigid' with the EOR's basis) -- otherwise ok=None."""
    out = {"clause": "IS 1893 (Part 1):2016 7.6.4", "cite": CITE_7_6_4}
    if delta_max_from_chord_mm is not None and delta_avg_mm:
        r = float(delta_max_from_chord_mm) / float(delta_avg_mm)
        out.update(method="deflection ratio (Fig. 6)", ratio=r, limit=1.2, flexible=r > 1.2,
                   classification="flexible" if r > 1.2 else "rigid", ok=True, ratio_basis=RATIO_BASIS_7_6_4)
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
        if basis:
            out["basis"] = str(basis)                    # the EOR's recorded 7.6.4 basis (WP6-fix: was rejected)
        return out
    out.update(method=None, classification=None, flexible=None, ok=None,
               reason="7.6.4 classification needs the diaphragm deflection ratio, an RC/screeded slab, or a declaration")
    return out


FLEXIBLE_FROM_ANALYSIS = "flexible (IS 1893 7.6.4, from the analysis)"
RATIO_BASIS_7_6_4 = ("IS 1893 (Part 1):2016 7.6.4 literal: maximum lateral displacement measured from the chord of the "
                     "deformed shape / average displacement of the entire diaphragm (per level and direction)")
INFORMATIVE_DRIFT_7_6_4 = "informative (not the IS 1893 criterion): deviation from the chord / average storey drift"


def literal_ratio_7_6_4(r):
    """The 7.6.4 ratio of one per-level record: deviation from the chord / average displacement of the entire
    diaphragm.  Records written before the literal reading carried the drift-based value in 'ratio' and the literal
    one in 'ratio_vs_avg_displacement' (no 'ratio_basis'); the literal one is taken whenever it is present."""
    if not isinstance(r, dict):
        return None
    v = r.get("ratio_vs_avg_displacement")
    if isinstance(v, (int, float)) and not isinstance(v, bool):
        return float(v)
    if r.get("ratio_basis") or "avg_storey_drift_mm" not in r:
        v = r.get("ratio")
        return float(v) if isinstance(v, (int, float)) and not isinstance(v, bool) else None
    return None                                   # drift-only record: not the 7.6.4 criterion


def reconcile_7_6_4(rec, flexible_levels=None, declared=None, declared_by_level=None):
    """AUD-3 (gold audit M2): the package's 7.6.4 record states what the analysis found.  flexible_levels = the X01
    flexible-diaphragm run's per-level records {dir: [{level, ratio, limit, flexible, ...}]}.  The ratio is the
    7.6.4 literal one (literal_ratio_7_6_4: deviation from the chord / average displacement of the entire
    diaphragm; the deviation / average storey drift is informative only and never classifies).  When any level's
    literal ratio > 1.2 (or the record's own deflection-ratio evaluation), the classification is
    FLEXIBLE_FROM_ANALYSIS with the governing ratio, whatever was declared; the design stays enveloped (rigid and
    flexible runs, Table 5(ii)).  A declared label that contradicts the computed one is kept as
    'declared_classification' with 'declared_contradicted' True and a 'warning' (non-blocking: consistency /
    design_status warnings).  declared_by_level ({k: 'rigid' | 'flexible'}, cfg['diaphragm_by_level'] via
    diaphragm_labels): the declared label of each level is compared with that level's computed classification
    ('computed_by_level'; contradictions listed in 'contradicted_levels').  Returns rec (updated in place)."""
    if not isinstance(rec, dict):
        return rec
    decl = str(declared or "").strip().lower() or None
    rows = []
    for d, lv in (flexible_levels or {}).items():
        for r in lv or []:
            lr = literal_ratio_7_6_4(r)
            if lr is not None:
                rows.append((d, r, lr))
    computed, ratio, where = None, None, None
    if rows:
        lim = 1.2
        flex = [x for x in rows if x[2] > lim]
        pick = max(flex or rows, key=lambda x: x[2])
        computed = bool(flex)
        ratio, where = pick[2], {"dir": pick[0], "level": pick[1].get("level"),
                                 "source": "X01 flexible-diaphragm run (Table 5(ii))"}
        byk = {}
        for d, r, lr in rows:
            k = r.get("level")
            if k is None:
                continue
            cur = byk.get(k)
            if cur is None or lr > cur["ratio"]:
                byk[k] = {"ratio": lr, "dir": d, "classification": "flexible" if lr > lim else "rigid"}
        rec["computed_by_level"] = {str(k): v for k, v in sorted(byk.items())}
        inf = [(d, r) for d, r, _ in rows if isinstance(r.get("ratio_vs_storey_drift"), (int, float))]
        if inf:
            d_, r_ = max(inf, key=lambda x: x[1]["ratio_vs_storey_drift"])
            rec["informative_ratio_vs_storey_drift"] = {"value": r_["ratio_vs_storey_drift"], "dir": d_,
                                                        "level": r_.get("level"), "note": INFORMATIVE_DRIFT_7_6_4}
    elif rec.get("method") == "deflection ratio (Fig. 6)" and isinstance(rec.get("ratio"), (int, float)):
        computed, ratio, where = bool(rec.get("flexible")), rec["ratio"], {"source": "declared 7.6.4 deflections"}
    if computed is None:
        return rec
    rec["computed_classification"] = "flexible" if computed else "rigid"
    rec["computed_ratio"] = ratio
    rec["computed_at"] = where
    rec["ratio_basis"] = RATIO_BASIS_7_6_4
    if decl is None:
        decl = str(rec.get("classification") or "").lower() or None
    if computed:
        if rec.get("classification") != FLEXIBLE_FROM_ANALYSIS:
            rec.setdefault("declared_classification", decl)
        rec.update(classification=FLEXIBLE_FROM_ANALYSIS, flexible=True, ratio=ratio, limit=1.2, ok=True,
                   method="in-plane deformation ratio from the analysis (deviation from the chord / average "
                          "displacement of the entire diaphragm, limit 1.2, IS 1893 7.6.4 / Fig. 6)")
        if rows:
            rec["model"] = ("design enveloped: rigid-diaphragm model (7.8.2 eccentricity) and the flexible-diaphragm "
                            "3-D run (IS 1893 Table 5(ii)); the diaphragm is flexible by 7.6.4")
    if declared_by_level and rec.get("computed_by_level"):
        bad = []
        for k, c in rec["computed_by_level"].items():
            dk = str((declared_by_level or {}).get(int(k)) or "").lower()
            if dk in ("rigid", "flexible") and dk != c["classification"]:
                bad.append({"level": int(k), "declared": dk, "computed": c["classification"], "ratio": c["ratio"],
                            "dir": c["dir"]})
        if bad:
            rec["declared_contradicted"] = True
            rec["contradicted_levels"] = bad
            rec["warning"] = ("IS 1893 7.6.4: cfg['diaphragm_by_level'] contradicts the analysis at %s (deviation from "
                              "the chord / average displacement of the entire diaphragm vs 1.2) -- declare the "
                              "computed label per level (or show a ratio <= 1.2); the package reports the computed "
                              "classification" % "; ".join("level %d: declared %s, computed %s (ratio %.2f, %s)" % (
                                  b["level"], b["declared"], b["computed"], b["ratio"], b["dir"]) for b in bad))
        return rec
    if decl in ("rigid", "flexible") and decl != rec["computed_classification"]:
        rec["declared_contradicted"] = True
        rec["warning"] = ("IS 1893 7.6.4: the diaphragm is declared %s but the analysis gives %s (ratio %.2f vs 1.2 at "
                          "%s; deviation from the chord / average displacement of the entire diaphragm) -- declare "
                          "cfg['diaphragm'] = '%s' (or show a ratio <= 1.2); the package reports the computed "
                          "classification" % (decl, rec["computed_classification"], ratio,
                                              ", ".join("%s %s" % kv for kv in where.items() if kv[1] is not None),
                                              rec["computed_classification"]))
    return rec


def light_diaphragm_rigid_findings(cfg):
    """AUD-3: a board / CFS-sheathed floor or a bare metal deck declared rigid with no stiffness basis and no 7.6.4
    evaluation -> WARN (the 7.6.4 'usually rigid' rule covers RC / screeded floors only).  A stiffness basis is
    cfg['diaphragm_stiffness'] (in-plane Gd, X01), 7.6.4 deflections, an RC / screed record, the X01 flexible run
    (flexible_diaphragm_analysis True) or an EOR analysis record (flexible_diaphragm_eor).  The deck kind comes from
    cfg['diaphragm_type'] ('board' | 'cfs_board' | 'metal_deck' | 'rc_slab' | 'composite_deck' | 'braced_roof') or
    from the floor_system / 7.6.4 basis text."""
    import re as _re
    cfg = cfg or {}
    if str(cfg.get("diaphragm") or "rigid").lower() != "rigid":
        return []
    d764 = cfg.get("diaphragm_7_6_4") if isinstance(cfg.get("diaphragm_7_6_4"), dict) else {}
    if d764.get("rc_slab") or d764.get("screed_mm") is not None or (
            d764.get("delta_max_from_chord_mm") is not None and d764.get("delta_avg_mm")):
        return []
    if cfg.get("diaphragm_stiffness") or cfg.get("flexible_diaphragm_analysis") is True or cfg.get("flexible_diaphragm_eor"):
        return []
    kind = str(cfg.get("diaphragm_type") or "").strip().lower()
    if kind in ("rc_slab", "composite_deck", "braced_roof"):
        return []
    txt = " ".join(str(x or "") for x in (cfg.get("floor_system"), d764.get("basis"))).lower()
    light = kind in ("board", "cfs_board", "metal_deck", "sheathing")
    if not light and not kind:
        if _re.search(r"\bcfs\b|board|sheathing|plywood|\bosb\b", txt):
            light = True
        elif _re.search(r"bare (metal |steel )?(roof )?deck|metal (roof )?deck|profiled (metal |steel )?sheet|(metal|roof) sheeting", txt) \
                and not _re.search(r"concrete|screed|topping|composite", txt):
            light = True
    if not light:
        return []
    return [("WARN", "IS 1893 7.6.4: a board / CFS-sheathed or bare metal-deck diaphragm is declared rigid with no "
                     "stiffness basis and no 7.6.4 evaluation (the 'usually rigid' rule covers RC / screeded floors "
                     "only) -- give cfg['diaphragm_stiffness'] (in-plane Gd with source + cite) so the flexible run "
                     "measures the 7.6.4 ratio, declare the 7.6.4 deflections, or declare the diaphragm flexible")]


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
    # H49: the mass extent of each level is that level's own footprint (column-line coordinates), no half-bay padding
    ext_k = {}
    for k in range(1, NF + 1):
        xs = [ops.nodeCoord(E.ntag(i, j, k))[0] for (i, j) in info["present"][k]]
        ys = [ops.nodeCoord(E.ntag(i, j, k))[1] for (i, j) in info["present"][k]]
        ext_k[k] = {"X": (min(ys), max(ys)), "Y": (min(xs), max(xs))}
    out = {"cite": CITE_7_6_4 + "; tributary-width distribution (no diaphragm torsion)", "kind": kind, "lines": {},
           "mass_extent_mm": {k: {d: list(v) for d, v in e.items()} for k, e in ext_k.items()}}
    for d in ("X", "Y"):
        F = _story_forces(cfg, d, kind)
        if not F or not lines[d]:
            continue
        di = 0 if d == "X" else 1
        out["lines"][d] = sorted(lines[d])
        for k in range(1, NF + 1):
            f = F.get(k, (0.0, 0.0, 0.0))[di]
            ext = ext_k[k][d]
            b = ext[1] - ext[0]
            for tag, e in (("e0", 0.0), ("ea", 0.05 * b), ("eb", -0.05 * b)):
                out.setdefault(tag, {}).setdefault(d, {})[k] = tributary_line_shears(f, sorted(lines[d]), ext,
                                                                                    eccentricity_mm=e)
    return out


CITE_FLEX_COLL = ("IS 1893 (Part 1):2016 7.6.4 flexible diaphragm: storey shear to the lateral lines by tributary width; "
                  "collector (drag) force = the deck shear accumulated along the line from the free end / the previous "
                  "vertical element, delivered to each braced / frame bay (tributary distribution)")
UPPER_BOUND_TEXT = ("upper bound: the positions of the vertical lateral elements on this line at this level could not be "
                    "determined (no brace or moment-frame bay on the line in the model) -- every beam on the line is "
                    "given the whole line shear")


def accumulate_line_collector(segments, elements, V_line, x0=None, x1=None):
    """GOLD-COLL: collector (drag) axial along ONE lateral line of a flexible diaphragm at one level.

    segments = [(xa, xb, key)] the beams on the line (coordinate along the force);
    elements = [{'span': (a, b), 'nodes': [(x, w), ...]}] the vertical lateral elements on the line (braced bays /
               moment-frame bays): plan span and delivery nodes with weights (brace ends / frame columns);
    V_line   = the line's tributary deck shear (N), delivered uniformly along the line, q = V_line / (x1 - x0).
    Overlapping / touching spans merge into one element.  Each element takes the deck shear of its tributary length
    of the line (free end or mid-gap to the next element): R_i = q (hi_i - lo_i), shared among its delivery nodes by
    weight.  N(x) = q (x - x0) - sum of the deliveries before x (+ = compression under a +d force: the free end
    pushes into the bay, the far side is pulled); each beam takes the larger |N| at its two ends.
    Returns {'q', 'x0', 'x1', 'elements': [{span, lo, hi, R}], 'deliveries': [(x, r)], 'N': {key: N}}."""
    if not elements:
        raise DiaphragmError("accumulate_line_collector: no vertical lateral element on the line")
    xs = [v for (a, b, _k) in segments for v in (a, b)]
    for e in elements:
        xs += list(e["span"]) + [x for x, _w in e["nodes"]]
    x0 = min(xs) if x0 is None else float(x0)
    x1 = max(xs) if x1 is None else float(x1)
    if x1 - x0 <= 0:
        raise DiaphragmError("accumulate_line_collector: zero line length")
    q = float(V_line) / (x1 - x0)
    tol = 1.0
    els = sorted(({"span": (min(e["span"]), max(e["span"])), "nodes": list(e["nodes"])} for e in elements),
                 key=lambda e: e["span"][0])
    merged = [els[0]]
    for e in els[1:]:
        m = merged[-1]
        if e["span"][0] <= m["span"][1] + tol:
            m["span"] = (m["span"][0], max(m["span"][1], e["span"][1]))
            m["nodes"] += e["nodes"]
        else:
            merged.append(e)
    dels, rec = [], []
    for i, e in enumerate(merged):
        lo = x0 if i == 0 else 0.5 * (merged[i - 1]["span"][1] + e["span"][0])
        hi = x1 if i == len(merged) - 1 else 0.5 * (e["span"][1] + merged[i + 1]["span"][0])
        R = q * (hi - lo)
        nd = {}
        for x, w in e["nodes"]:
            nd[round(x, 3)] = nd.get(round(x, 3), 0.0) + float(w)
        if not nd or sum(nd.values()) <= 0:
            nd = {round(e["span"][0], 3): 1.0, round(e["span"][1], 3): 1.0}
        W = sum(nd.values())
        for x, w in sorted(nd.items()):
            dels.append((x, R * w / W))
        rec.append({"span": list(e["span"]), "lo": lo, "hi": hi, "R": R})

    def N(x, right):
        return q * (x - x0) - sum(r for (s_, r) in dels if (s_ <= x + 1e-6 if right else s_ < x - 1e-6))
    out = {}
    for (a, b, key) in segments:
        a_, b_ = min(a, b), max(a, b)
        Na, Nb = N(a_, True), N(b_, False)
        out[key] = Na if abs(Na) >= abs(Nb) else Nb
    return {"q": q, "x0": x0, "x1": x1, "elements": rec, "deliveries": dels, "N": out}


def _line_elements(info, d, k, pos, crd, tol=1.0):
    """The vertical lateral elements of the line at coordinate pos (normal to the force d) at level k, from the
    built model: braced bays (braces in d on the line with an end at level k: span = plan projection, delivery nodes
    = the brace ends at level k, weight = number of brace ends) and, when the line has no brace there, moment-frame
    bays (beams on the line at level k with a moment end, engine3d add_beam release record: delivery nodes = the
    moment ends).  Returns (elements, basis)."""
    ax, nx = (0, 1) if d == "X" else (1, 0)
    els = []
    for (t, kind_e, sec, n1, n2) in info["ele"]:
        if kind_e != "brace":
            continue
        c1, c2 = crd(n1), crd(n2)
        if (abs(c2[0] - c1[0]) >= abs(c2[1] - c1[1])) != (d == "X"):
            continue
        if abs(c1[nx] - pos) > tol or abs(c2[nx] - pos) > tol:
            continue
        ends = [(c[ax], 1.0) for n, c in ((n1, c1), (n2, c2)) if _lvl(n) == k]
        if not ends:
            continue
        els.append({"span": (c1[ax], c2[ax]), "nodes": ends})
    if els:
        return els, "braced bays of the model (brace ends at the level)"
    rel = info.get("beam_rel") or {}
    mn = info.get("moment_nodes") or set()
    for (t, kind_e, sec, n1, n2) in info["ele"]:
        if kind_e != "beam" or _lvl(n1) != k or _lvl(n2) != k:
            continue
        c1, c2 = crd(n1), crd(n2)
        if abs(c1[nx] - pos) > tol or abs(c2[nx] - pos) > tol or abs(c2[ax] - c1[ax]) < tol:
            continue
        rz = (rel.get(t) or ("both",))[0]
        ends = [(c[ax], 1.0) for n, c, free in ((n1, c1, rz in ("I", "both")), (n2, c2, rz in ("J", "both")))
                if not free and n in mn]
        if ends:
            els.append({"span": (c1[ax], c2[ax]), "nodes": ends})
    if els:
        return els, "moment-frame bays of the model (beams with moment ends on the line)"
    return [], None


def _collector_forces_flexible(cfg, kind="EQ", levels=None):
    """Flexible diaphragm (7.6.4): each lateral line receives its tributary storey shear (flexible_diaphragm_line_shears,
    e0); along the line the collector carries the deck shear accumulated from the free end (or the previous
    vertical element) into each braced / frame bay (accumulate_line_collector, GOLD-COLL): q = V_line / line length,
    each vertical element taking q x its tributary length of the line.  Only when the positions of the vertical
    elements on the line cannot be determined is every beam on the line given the whole line shear (upper bound,
    stated in the rows and in 'upper_bound_lines').  Chord forces: the deck spans between lines as a simple beam of
    span s (the tributary panel) -- chord T = w s^2 / (8 B) with w = the panel's share of the storey force per unit
    length and B the panel depth.  levels: the levels to evaluate (None = all)."""
    import engine3d as E
    ls = flexible_diaphragm_line_shears(cfg, kind)
    info = E.build(cfg, "Linear")
    NF = info["NF"]
    out = {"X": {}, "Y": {}, "rows": [], "kind": kind, "cite": CITE_7_6_4 + " (tributary distribution)",
           "diaphragm": "flexible", "accumulation_basis": CITE_FLEX_COLL, "upper_bound_lines": []}
    _c = {}

    def crd(n):
        if n not in _c:
            _c[n] = ops.nodeCoord(n)
        return _c[n]
    beams = {}
    for (t, k_, sec, n1, n2) in info["ele"]:
        if k_ == "beam":
            c1, c2 = crd(n1), crd(n2)
            d = "X" if abs(c2[0] - c1[0]) >= abs(c2[1] - c1[1]) else "Y"
            beams.setdefault((d, _lvl(n1), round(c1[1] if d == "X" else c1[0], 1)), []).append((t, c1, c2))
    for d, lines in (ls.get("lines") or {}).items():
        ax = 0 if d == "X" else 1
        for k in range(1, NF + 1):
            if levels is not None and k not in levels:
                continue
            sh = (ls.get("e0") or {}).get(d, {}).get(k) or {}
            for pos, V in sh.items():
                bl = beams.get((d, k, round(pos, 1)), [])
                if not bl or abs(V) < 1e-9:
                    continue
                els, ebasis = _line_elements(info, d, k, pos, crd)
                if els:
                    segs = [(c1[ax], c2[ax], t) for (t, c1, c2) in bl]
                    acc = accumulate_line_collector(segs, els, abs(V))
                    for (t, c1, c2) in bl:
                        Nt = acc["N"][t]
                        if abs(Nt) < 1.0:
                            continue
                        out[d][t] = out[d].get(t, 0.0) + Nt
                        out["rows"].append({"dir": d, "level": k, "line": pos, "beam": t, "role": "collector",
                                            "N_N": round(Nt, 1), "R_line_N": round(V, 1),
                                            "q_N_per_mm": round(acc["q"], 4),
                                            "x_mm": [round(min(c1[ax], c2[ax]), 1), round(max(c1[ax], c2[ax]), 1)],
                                            "vertical_elements": [{"span_mm": [round(v, 1) for v in e["span"]],
                                                                   "R_N": round(e["R"], 1)} for e in acc["elements"]],
                                            "basis": "tributary deck shear accumulated along the line (%s)" % ebasis,
                                            "cite": CITE_FLEX_COLL})
                else:
                    out["upper_bound_lines"].append({"dir": d, "level": k, "line": pos, "reason": UPPER_BOUND_TEXT})
                    for (t, c1, c2) in bl:
                        out[d][t] = out[d].get(t, 0.0) + abs(V)
                        out["rows"].append({"dir": d, "level": k, "line": pos, "beam": t, "role": "collector",
                                            "N_N": round(abs(V), 1), "R_line_N": round(V, 1),
                                            "basis": UPPER_BOUND_TEXT, "upper_bound": True,
                                            "cite": CITE_7_6_4 + " (tributary distribution; upper bound)"})
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
                    for (t, _c1, _c2) in beams.get((dd, k, round(pos_edge, 1)), []):
                        out[dd][t] = out[dd].get(t, 0.0) + T
                        out["rows"].append({"dir": d, "level": k, "beam": t, "role": "chord", "N_N": round(T, 1),
                                            "span_mm": span, "B_mm": B, "basis": "flexible panel w s^2/(8 B)"})
    return out
