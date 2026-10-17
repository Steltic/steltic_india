"""staad_loads.py -- first wave item 8 (2026-10): every engine load case in the STAAD.Pro export.

The STAAD file of a PEB job (peb_outputs.write_staad) used to carry dead, roof imposed and the earthquake storey
forces only.  This module records the loads the engine itself applies (static_model.apply_gravity_state,
member_wind_loads, apply_crane_loads, the storey forces of india_loads.case_from_combination and the IS 800 4.3.6
notional loads) by wrapping ops.load / ops.eleLoad while the engine applies them to its static model, converts each
one to STAAD global loads on the members of the exported (stepped) model, and builds one STAAD primary load case per
engine basic case:

  DL      dead load: member self-weight, roof and wall dead loads, declared nodal dead loads (permanent part)
  DLNP    collateral + solar PV on the roof (IS 800 Table 4: not taken as resisting -> factor 0 in the 0.9DL rows)
  LL / LR floor imposed / roof imposed;  SN snow (per partial pattern);  CR crane (per pattern, impact included)
  EV      vertical earthquake on the seismic weight (unit Av)
  EQ_X .. W_Y_across  storey forces at the diaphragm master (unit factor);  TOR_<d><a|b>  7.8.2 accidental torsion
  WM <name>  member wind (IS 875-3 7.3.1 roof and wall pressures, one case per pattern)
  NOT <n>    IS 800 4.3.6 notional loads of one combination (0.5 % of that combination's factored gravity)

and a LOAD COMBINATION for every engine combination.  Combinations whose earthquake part comes from response
spectrum analysis are written with the equivalent static storey forces of the same direction (the file says so);
STAAD's own IS 1893 response spectrum can replace them.  Units: N, mm in the engine; kN, mm in the file.
STAAD axes: X = x, Y = z (up), Z = -y.
"""
from __future__ import annotations

import math

import openseespy.opensees as ops

TOL_N = 1e-6          # N or N/mm below which a component is dropped


def _vec_staad(v):
    """OpenSees global (x, y, z) -> STAAD global (X, Y, Z) = (x, z, -y)."""
    return (v[0], v[2], -v[1])


class _Recorder:
    """Wrap ops.load / ops.eleLoad while an engine function applies loads to the static model."""

    def __init__(self):
        self.calls = []
        self._real = None

    def __enter__(self):
        self._real = (ops.load, ops.eleLoad)
        rl, re_ = self._real

        def _load(nd, *v):
            self.calls.append(("node", int(nd), [float(x) for x in v]))
            return rl(nd, *v)

        def _ele(*a):
            self.calls.append(("ele", a))
            return re_(*a)
        ops.load, ops.eleLoad = _load, _ele
        return self

    def __exit__(self, *exc):
        ops.load, ops.eleLoad = self._real
        return False


def _maps(model, nseg):
    """Static-model element / node -> (builder element tag, start, end distance from the builder element's i node)."""
    seg_of, node_on = {}, {}
    for b in model.get("beams") or []:
        et = b.get("etag")
        if et is None:
            continue
        L = float(b["L"])
        n = len(b["segs"])
        for s, t in enumerate(b["segs"]):
            seg_of[t] = (et, L * s / n, L * (s + 1) / n)
        for s, nd in enumerate(b.get("nodes") or []):
            if 0 < s < len(b["nodes"]) - 1:
                node_on[nd] = (et, L * s / n)
    for c in model.get("cols") or []:
        try:
            c1, c2 = ops.nodeCoord(c["n1"]), ops.nodeCoord(c["n2"])
            L = math.dist(c1, c2)
        except Exception:
            L = None
        seg_of[c["tag"]] = (c["tag"], 0.0, L)
    return seg_of, node_on


def _convert(calls, seg_of, node_on):
    """Recorded calls -> {('m', member, d1, d2): [gx, gy, gz] N/mm} + {('n', node): [6] N, N-mm} +
    {('p', member, d): [gx, gy, gz] N} (point loads on beam interior nodes) and the unmapped count."""
    out, bad = {}, 0
    for c in calls:
        if c[0] == "node":
            nd, v = c[1], (list(c[2]) + [0.0] * 6)[:6]
            if nd in node_on:
                et, d = node_on[nd]
                k = ("p", et, round(d, 3))
                a = out.setdefault(k, [0.0, 0.0, 0.0])
                for i in range(3):
                    a[i] += v[i]
                if any(abs(x) > TOL_N for x in v[3:]):
                    bad += 1                              # moment on a beam interior node: not exported
                continue
            a = out.setdefault(("n", nd), [0.0] * 6)
            for i in range(6):
                a[i] += v[i]
            continue
        a = list(c[1])
        try:
            t = int(a[a.index("-ele") + 1])
            typ = a[a.index("-type") + 1]
        except (ValueError, IndexError):
            bad += 1
            continue
        if typ != "-beamUniform" or t not in seg_of:
            bad += 1
            continue
        vals = [float(x) for x in a[a.index("-type") + 2:]]
        Wy, Wz = (vals + [0.0, 0.0])[:2]
        Wx = vals[2] if len(vals) > 2 else 0.0
        try:
            xa, ya, za = (ops.eleResponse(t, r) for r in ("xaxis", "yaxis", "zaxis"))
        except Exception:
            bad += 1
            continue
        g = [Wx * xa[i] + Wy * ya[i] + Wz * za[i] for i in range(3)]
        et, d1, d2 = seg_of[t]
        k = ("m", et, round(d1, 3), round(d2, 3) if d2 is not None else None)
        acc = out.setdefault(k, [0.0, 0.0, 0.0])
        for i in range(3):
            acc[i] += g[i]
    return out, bad


def _totals(rec):
    """Resultant force (N) of a converted record: sum of nodal forces + w x length of the member loads."""
    F = [0.0, 0.0, 0.0]
    for k, v in rec.items():
        if k[0] == "m":
            L = (k[3] - k[2]) if k[3] is not None else 0.0
            for i in range(3):
                F[i] += v[i] * L
        else:
            for i in range(3):
                F[i] += v[i]
    return F


def _diff(a, b):
    out = {}
    for k in set(a) | set(b):
        va, vb = a.get(k), b.get(k)
        n = len(va if va is not None else vb)
        v = [(va[i] if va else 0.0) - (vb[i] if vb else 0.0) for i in range(n)]
        if any(abs(x) > TOL_N for x in v):
            out[k] = v
    return out


def _record(cfg, nseg, fn):
    import static_model as SM
    model = SM.build_static(cfg, "Linear", nseg)
    ops.timeSeries("Linear", 1)
    ops.pattern("Plain", 1, 1)
    with _Recorder() as r:
        ret = fn(model)
    seg_of, node_on = _maps(model, nseg)
    rec, bad = _convert(r.calls, seg_of, node_on)
    ops.wipe()
    return rec, bad, ret


def basic_cases(cfg, combos, nseg=6):
    """Engine basic cases for the combinations: [(key, title, loadtype, rec)] plus the combination terms
    [(label, [(key, factor)], notes)] and diagnostics."""
    import engine3d as E
    import india_loads as IL
    import static_model as SM
    plan = cfg.get("load_plan") or {}
    sw = cfg.get("self_weight", True)
    cases, order, diag = {}, [], {"unmapped_calls": 0, "rsa_as_static": 0, "checks": []}

    def add(key, title, ltype, fn):
        if key in cases:
            return
        rec, bad, ret = _record(cfg, nseg, fn)
        diag["unmapped_calls"] += bad
        cases[key] = (title, ltype, rec, ret)
        order.append(key)

    def grav(cfg_, **kw):
        base = dict(fD=0.0, fL=0.0, fLr=0.0, fS=0.0, fC=0.0, fEv=0.0, self_weight=False, crane_pattern=None,
                    snow_pattern=None)
        base.update(kw)
        return lambda m: SM.apply_gravity_state(cfg_, m, base["fD"], base["fL"], base["fLr"], base["fS"], base["fC"],
                                                base["fEv"], self_weight=base["self_weight"],
                                                crane_pattern=base["crane_pattern"],
                                                snow_pattern=base["snow_pattern"])

    # dead: permanent and non-permanent (collateral + PV)
    cfg_perm = dict(cfg, D_roof_collateral=0.0, D_roof_pv=0.0)
    add("DL", "DEAD (SELF WEIGHT + PERMANENT ROOF AND WALL DEAD LOADS)", "Dead", grav(cfg_perm, fD=1.0, self_weight=sw))
    if E.roof_nonpermanent_kNm2(cfg) > 0.0:
        full, bad, lev_full = _record(cfg, nseg, grav(cfg, fD=1.0, self_weight=sw))
        diag["unmapped_calls"] += bad
        np_ = _diff(full, cases["DL"][2])
        cases["DLNP"] = ("COLLATERAL %.3f + SOLAR PV %.3f kN/m2 ON THE ROOF" % (float(cfg.get("D_roof_collateral") or 0),
                                                                              float(cfg.get("D_roof_pv") or 0)),
                         "Dead", np_, None)
        order.append("DLNP")
    if any(float(c.get("fL") or 0) for c in combos) and float(cfg.get("L_floor") or 0.0) > 0.0:
        add("LL", "FLOOR IMPOSED", "Live", grav(cfg, fL=1.0))
    if any(float(c.get("fLr") or 0) for c in combos):
        add("LR", "ROOF IMPOSED %.2f kN/m2" % float(cfg.get("Lr") or 0.0), "Roof Live", grav(cfg, fLr=1.0))
    for c in combos:
        if float(c.get("fS") or 0):
            sp = tuple(c["snow_pattern"]) if c.get("snow_pattern") else None
            add(("SN", sp), "SNOW%s" % ((" PARTIAL %s %s" % sp) if sp else ""), "Snow",
                grav(cfg, fS=1.0, snow_pattern=sp))
        if float(c.get("fC") or 0):
            cp = tuple(c["crane_pattern"]) if c.get("crane_pattern") else ("L", None)
            add(("CR", cp), "CRANE %s %s (WHEEL LOADS WITH IMPACT, SURGE / TRACTION)" % (cp[0], cp[1] or "vertical only"),
                "Crane Hook", grav(cfg, fC=1.0, crane_pattern=cp))
        if float(c.get("fEv") or 0):
            add("EV", "VERTICAL EARTHQUAKE (UNIT, ON THE SEISMIC WEIGHT)", "Seismic", grav(cfg, fEv=1.0, self_weight=sw))
        mw = c.get("member_wind")
        if mw:
            add(("WM", mw.get("name")), "MEMBER WIND %s (IS 875-3 7.3.1, Cpi %s)" % (mw.get("name"), mw.get("Cpi")),
                "Wind", lambda m, mw=mw: SM.member_wind_loads(cfg, m, mw, 1.0))

    # storey forces at the diaphragm master (unit factor) and the accidental torsion
    def story_case(ref, key_f):
        rec = {}
        try:
            cs = IL.case_from_combination({"label": ref, "fD": 0.0, key_f: 1.0, "lateral_ref": ref}, plan)
        except Exception:
            return None
        for k, (fx, fy, mz) in (cs[4] or {}).items():
            rec[("n", E.mtag(int(k)))] = [fx, fy, 0.0, 0.0, 0.0, mz]
        return rec

    terms_of = []
    notional_n = 0
    lev_cache = {}
    for c in combos:
        f, key = IL.combo_lateral_factor(c)
        terms = []
        fD = float(c.get("fD") or 0.0)
        terms.append(("DL", fD))
        if "DLNP" in cases:
            terms.append(("DLNP", E.nonpermanent_factor(fD)))
        if "LL" in cases:
            terms.append(("LL", float(c.get("fL") or 0.0)))
        if "LR" in cases:
            terms.append(("LR", float(c.get("fLr") or 0.0)))
        if float(c.get("fS") or 0):
            terms.append((("SN", tuple(c["snow_pattern"]) if c.get("snow_pattern") else None), float(c["fS"])))
        if float(c.get("fC") or 0):
            terms.append((("CR", tuple(c["crane_pattern"]) if c.get("crane_pattern") else ("L", None)), float(c["fC"])))
        if float(c.get("fEv") or 0):
            terms.append(("EV", float(c["fEv"])))
        note = []
        if f is not None:
            ref = c.get("lateral_ref")
            if c.get("rsa") and not ref:
                ref = "EQ_%s" % (c["rsa"] if isinstance(c["rsa"], str) else c.get("direction"))
                note.append("RSA -> static")
                diag["rsa_as_static"] += 1
            if ref:
                if ref not in cases:
                    rec = story_case(ref, key or "fE")
                    if rec is not None:
                        lt = "Seismic" if ref.startswith("EQ") else "Wind"
                        cases[ref] = ("%s STOREY FORCES AT THE DIAPHRAGM MASTER (UNIT)" % ref, lt, rec, None)
                        order.append(ref)
                if ref in cases:
                    terms.append((ref, f))
                else:
                    note.append("storey forces %s missing" % ref)
                    diag["missing_terms"] = diag.get("missing_terms", 0) + 1
            tv = c.get("torsion")
            if tv and c.get("torsion_mz"):
                d = c.get("direction") or (ref[-1] if ref else "X")
                tk = "TOR_%s%s" % (d, tv)
                if tk not in cases:
                    sc = IL._story_force_scale(plan, c)
                    rec = {("n", E.mtag(int(k))): [0.0, 0.0, 0.0, 0.0, 0.0, float(v) * sc]
                           for k, v in dict(c["torsion_mz"]).items()}
                    cases[tk] = ("ACCIDENTAL TORSION %s (%s) IS 1893 7.8.2 (UNIT)" % (d, tv), "Seismic", rec, None)
                    order.append(tk)
                terms.append((tk, f))
            for t in c.get("terms") or []:
                r2 = t.get("ref") or ("EQ_%s" % t["rsa"] if t.get("rsa") else None)
                if not r2:
                    continue
                if r2 not in cases:
                    rec = story_case(r2, "fE" if r2.startswith("EQ") else "fW")
                    if rec is not None:
                        cases[r2] = ("%s STOREY FORCES AT THE DIAPHRAGM MASTER (UNIT)" % r2,
                                     "Seismic" if r2.startswith("EQ") else "Wind", rec, None)
                        order.append(r2)
                if r2 in cases:
                    terms.append((r2, float(t["f"])))
                else:
                    note.append("term %s missing" % r2)
                    diag["missing_terms"] = diag.get("missing_terms", 0) + 1
        mw = c.get("member_wind")
        if mw:
            terms.append((("WM", mw.get("name")), float(c.get("fWM") or 0.0)))
        nt = c.get("notional")
        if nt:
            gk = (fD, float(c.get("fL") or 0), float(c.get("fLr") or 0), float(c.get("fS") or 0),
                  float(c.get("fC") or 0), float(c.get("fEv") or 0))
            if gk not in lev_cache:
                _r, _b, lev = _record(cfg, nseg, grav(cfg, fD=gk[0], fL=gk[1], fLr=gk[2], fS=gk[3], fC=gk[4],
                                                      fEv=gk[5], self_weight=sw))
                lev_cache[gk] = lev
            lev = lev_cache[gk]
            notional_n += 1
            nk = ("NOT", notional_n)
            v = {}
            for nd, vec in SM.notional_loads(lev, nt, None).items():
                v[("n", nd)] = list(vec)
            cases[nk] = ("NOTIONAL %s%s 0.5 %% OF THE FACTORED GRAVITY OF %s (IS 800 4.3.6)"
                         % ("+" if float(nt.get("sign", 1)) >= 0 else "-", nt.get("dir"), c.get("label")),
                         "None", v, None)
            order.append(nk)
            terms.append((nk, 1.0))
        terms = [(k, x) for k, x in terms if abs(x) > 1e-12]
        terms_of.append((c.get("label", ""), terms, note, bool(c.get("service"))))
    return cases, order, terms_of, diag


def staad_lines(cfg, combos, nid, member_id, master_of_level, nseg=6):
    """STAAD primary load cases + combinations.  nid: OpenSees node -> STAAD joint; member_id: builder element tag ->
    STAAD member; master_of_level: {k: STAAD joint of the diaphragm master}.  Returns (lines, summary)."""
    import engine3d as E
    cases, order, terms_of, diag = basic_cases(cfg, combos, nseg)
    num, L = {}, []
    unm = 0
    totals = {}
    mtag_level = {}
    for k in range(1, len(cfg.get("heights") or []) + 1):
        mtag_level[E.mtag(k)] = k
    for i, key in enumerate(order):
        title, ltype, rec, _ret = cases[key]
        n = i + 1
        num[key] = n
        L.append("LOAD %d LOADTYPE %s TITLE %s" % (n, ltype, title[:70]))
        jl, ml = [], []
        F = [0.0, 0.0, 0.0]
        for k, v in sorted(rec.items(), key=lambda kv: str(kv[0])):
            if k[0] == "n":
                nd = k[1]
                j = nid.get(nd)
                if j is None and nd in mtag_level:
                    j = master_of_level.get(mtag_level[nd])
                if j is None:
                    unm += 1
                    continue
                f = _vec_staad(v[:3])
                m = _vec_staad(v[3:6])
                parts = ["%s %.4f" % (lab, x / 1e3) for lab, x in zip(("FX", "FY", "FZ"), f) if abs(x) > TOL_N] + \
                        ["%s %.3f" % (lab, x / 1e3) for lab, x in zip(("MX", "MY", "MZ"), m) if abs(x) > 1e-3]
                if parts:
                    jl.append("%d %s" % (j, " ".join(parts)))
                for q in range(3):
                    F[q] += v[q]
            elif k[0] == "m":
                mid = member_id.get(k[1])
                if mid is None:
                    unm += 1
                    continue
                g = _vec_staad(v)
                for lab, x in zip(("GX", "GY", "GZ"), g):
                    if abs(x) > 1e-9:
                        if k[3] is None:
                            ml.append("%d UNI %s %.6f" % (mid, lab, x / 1e3))
                        else:
                            ml.append("%d UNI %s %.6f %.1f %.1f" % (mid, lab, x / 1e3, k[2], k[3]))
                Lm = (k[3] - k[2]) if k[3] is not None else 0.0
                for q in range(3):
                    F[q] += v[q] * Lm
            elif k[0] == "p":
                mid = member_id.get(k[1])
                if mid is None:
                    unm += 1
                    continue
                g = _vec_staad(v)
                for lab, x in zip(("GX", "GY", "GZ"), g):
                    if abs(x) > TOL_N:
                        ml.append("%d CON %s %.4f %.1f" % (mid, lab, x / 1e3, k[2]))
                for q in range(3):
                    F[q] += v[q]
        if ml:
            L.append("MEMBER LOAD")
            L += ml
        if jl:
            L.append("JOINT LOAD")
            L += jl
        totals[str(key)] = [round(x / 1e3, 3) for x in F]
        L.append("* resultant of this case (kN, engine axes x, y, z): %.3f %.3f %.3f" % tuple(x / 1e3 for x in F))
    nc = 0
    for q, (lab, terms, note, service) in enumerate(terms_of):
        nc += 1
        L.append("LOAD COMBINATION %d %s%s" % (100 + q + 1, lab[:56], " (RSA->ESM)" if "RSA -> static" in note else ""))
        for n_ in note:
            if n_ != "RSA -> static":
                L.append("* NOTE: %s in the Steltic load plan -- this combination is incomplete here" % n_)
        L.append(" ".join("%d %.4f" % (num[k], x) for k, x in terms if k in num))
    diag["unmapped_loads"] = unm
    return L, {"n_primary": len(order), "n_combinations": nc, "case_totals_kN": totals, **diag}
