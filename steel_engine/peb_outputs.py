"""peb_outputs.py -- PEB (2026-10) deliverables (docs/PEB_TAPERED_SCOPE.md 6.x):

  design/reactions.csv        unfactored base reactions per basic load case and column line (foundation interface)
  design/bom.csv              bill of materials: plates of every welded / tapered member (flanges, web), rolled and
                              tube members, connection plates and bolts declared in cfg['connections'], the secondary
                              members (cfg['peb_secondary']) -- with mass_kg and the totals
  design/anchor_bolt_plan.svg setting-out plan of the column bases: grid, base plates, anchors, shear keys, reactions
  model.std                   STAAD.Pro input of the stepped analysis model (nodes, members, TAPERED properties,
                              releases, supports, material, the basic load cases as nodal / member loads)
and the PEB columns of design/member_schedule.csv (start / end depth, plates, mass_kg).
Units: N-mm inside; kN, kN-m, mm in the files (STAAD: UNIT MMS KN)."""
from __future__ import annotations

import csv
import math
import os

import sections as S

SRC = "steel_engine/peb_outputs.py"
STEEL = 7.85e-6          # kg/mm3


# ------------------------------------------------------------------------------------------- schedule columns
def schedule_extra(t, sec, L_mm):
    """(start_depth_mm, end_depth_mm, plates, mass_kg, peb_member) for one element."""
    import peb_build as PB
    e = PB.element(t) if PB.active() else None
    p = S.props(sec)
    if e:
        pi, pj = S.props(e["sec_i"]), S.props(e["sec_j"])
        d0, d1 = pi["d"], pj["d"]
        plates = "flanges 2 x %gx%g, web %gx(%g..%g)" % (p["bf"], p["tf"], p["tw"], d0 - 2 * p["tf"], d1 - 2 * p["tf"])
        A = 2 * p["bf"] * p["tf"] + 0.5 * ((d0 - 2 * p["tf"]) + (d1 - 2 * p["tf"])) * p["tw"]
        return d0, d1, plates, A * L_mm * STEEL, e["member"]
    plates = ""
    if p.get("plates"):
        plates = "flanges 2 x %gx%g, web %gx%g" % (p["bf"], p["tf"], p["d"] - 2 * p["tf"], p["tw"])
    try:
        import engine3d as E
        A = E.Ipack(sec)[0]
    except Exception:
        A = p["A"]
    return p.get("d"), p.get("d"), plates, A * L_mm * STEEL, ""


# ------------------------------------------------------------------------------------------- reactions
def basic_cases(cfg):
    """[(label, kind, data)] -- DL, LL (roof imposed), every member-wind pattern both ways, EQ_X / EQ_Y."""
    plan = cfg.get("load_plan") or {}
    out = [("DL", "D", None)]
    import engine3d as E
    if E.roof_nonpermanent_kNm2(cfg) > 0.0:
        # first wave item 8: vendors list collateral (and PV) apart from the dead load
        out.append(("DL collateral + PV", "DNP", None))
    out.append(("LL (roof imposed)", "Lr", None))
    if cfg.get("crane") or cfg.get("cranes"):
        for cp in (("L", None), ("R", None), ("L", "S+"), ("L", "S-"), ("R", "S+"), ("R", "S-"), ("L", "T+"),
                   ("L", "T-")):
            out.append(("CL %s%s" % (cp[0], (" " + cp[1]) if cp[1] else " vertical"), "C", cp))
    for p in plan.get("member_wind") or []:
        signs = [p["sign"]] if p.get("sign") is not None else [1, -1]
        for sg in signs:
            nm = str(p["name"]) + ("R" if (p.get("sign") is None and sg < 0) else "")
            out.append(("WL " + nm, "W", dict(p, sign=sg, name=nm)))
    for ref in ("EQ_X", "EQ_Y"):
        if (plan.get("story_forces") or {}).get(ref):
            out.append((ref, "EQ", plan["story_forces"][ref]))
    return out


def base_reactions(cfg, nseg=6):
    """{case label: {base node: (Fx, Fy, Fz, Mx, My, Mz) N / N-mm}} by linear analysis of the static model."""
    import openseespy.opensees as ops
    import engine3d as E
    import static_model as SM
    res = {}
    for lab, kind, data in basic_cases(cfg):
        model = SM.build_static(cfg, "Linear", nseg)
        ops.timeSeries("Linear", 1)
        ops.pattern("Plain", 1, 1)
        if kind == "D":
            SM.apply_gravity_state(dict(cfg, D_roof_collateral=0.0, D_roof_pv=0.0), model, 1.0, 0.0, 0.0, 0.0, 0.0,
                                   0.0, self_weight=cfg.get("self_weight", True))
        elif kind == "DNP":                             # full dead minus the permanent case (linear analysis)
            SM.apply_gravity_state(cfg, model, 1.0, 0.0, 0.0, 0.0, 0.0, 0.0, self_weight=cfg.get("self_weight", True))
        elif kind == "C":
            SM.apply_gravity_state(cfg, model, 0.0, 0.0, 0.0, 0.0, 1.0, 0.0, self_weight=False, crane_pattern=data)
        elif kind == "Lr":
            SM.apply_gravity_state(cfg, model, 0.0, 1.0, 1.0, 0.0, 0.0, 0.0, self_weight=False)
        elif kind == "W":
            SM.member_wind_loads(cfg, model, data, 1.0)
        elif kind == "EQ":
            for k, v in data.items():
                fx, fy, mz = (list(v) + [0.0, 0.0, 0.0])[:3]
                ops.load(E.mtag(int(k)), float(fx), float(fy), 0.0, 0.0, 0.0, float(mz))
        ops.constraints("Transformation"); ops.numberer("RCM"); ops.system("UmfPack")
        ops.test("NormDispIncr", 1e-9, 50); ops.algorithm("Linear")
        ops.integrator("LoadControl", 1.0); ops.analysis("Static")
        if ops.analyze(1) != 0:
            res[lab] = {"_error": "analysis failed"}
            continue
        ops.reactions()
        rr = {}
        for n in ops.getNodeTags():
            if n // 100000 != 0 or n % 100000 >= 90000:
                continue
            try:
                fx = ops.getFixedDOFs(n)
            except Exception:
                fx = []
            if not fx:
                continue
            rr[n] = tuple(ops.nodeReaction(n))
        if kind == "DNP" and isinstance(res.get("DL"), dict) and "_error" not in res["DL"]:
            rr = {n: tuple(a - b for a, b in zip(v, res["DL"].get(n, (0.0,) * 6))) for n, v in rr.items()}
        res[lab] = rr
    return res


def write_reactions(cfg, outdir):
    """design/reactions.csv: one row per (basic case, base node); + a JSON-able summary."""
    import engine3d as E
    R = base_reactions(cfg)
    path = os.path.join(outdir, "reactions.csv")
    summ = {}
    with open(path, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["case", "node", "grid_i", "grid_j", "x_m", "y_m", "Fx_kN", "Fy_kN", "Fz_kN", "Mx_kNm", "My_kNm",
                    "Mz_kNm", "note"])
        for lab, rr in R.items():
            if "_error" in rr:
                w.writerow([lab, "", "", "", "", "", "", "", "", "", "", "", rr["_error"]])
                continue
            for n in sorted(rr):
                i, j = (n % 100000) // 100, n % 100
                try:
                    import openseespy.opensees as ops
                    c = ops.nodeCoord(n)
                except Exception:
                    c = (i * float(cfg["SX"]), j * float(cfg["SY"]), 0.0)
                Fx, Fy, Fz, Mx, My, Mz = rr[n]
                w.writerow([lab, n, i, j, round(c[0] / 1000.0, 3), round(c[1] / 1000.0, 3), round(Fx / 1e3, 2),
                            round(Fy / 1e3, 2), round(Fz / 1e3, 2), round(Mx / 1e6, 2), round(My / 1e6, 2),
                            round(Mz / 1e6, 2), "unfactored; reaction on the structure (+ = along +axis / up)"])
                s = summ.setdefault(n, {"grid": (i, j), "Fz_max_kN": -1e9, "Fz_min_kN": 1e9, "H_max_kN": 0.0})
                s["Fz_max_kN"] = max(s["Fz_max_kN"], Fz / 1e3)
                s["Fz_min_kN"] = min(s["Fz_min_kN"], Fz / 1e3)
                s["H_max_kN"] = max(s["H_max_kN"], math.hypot(Fx, Fy) / 1e3)
    return {"file": "design/reactions.csv", "cases": list(R), "summary": {str(k): v for k, v in summ.items()},
            "basis": "linear static analysis of the stepped model for each basic load case at gamma_f = 1.0 "
                     "(self-weight + permanent roof / cladding dead; collateral + PV apart; roof imposed; crane "
                     "patterns with impact, surge and traction where a crane is declared; every IS 875-3 member-wind "
                     "pattern both ways; IS 1893 ESM storey forces)"}


# ------------------------------------------------------------------------------------------- BOM
def write_bom(cfg, info, length, outdir, pkg=None, tonnage=None):
    """design/bom.csv -- members by plate / section, connection plates, bolts, secondary members; then the totals by
    category and kg/m2 of plan area from the steel take-off (peb_checks.tonnage, when given)."""
    import peb_build as PB
    rows = []
    peb = PB.snapshot() if PB.active() else {}
    members = peb.get("members") or {}
    done = set()
    # welded / tapered members (one row per member, plates listed)
    for mid, m in sorted(members.items()):
        p = PB.parse(m["section"])
        n_el = len(m["elements"])
        L = sum(length.get(t, 0.0) for t in m["elements"])
        done.update(m["elements"])
        if p[0] == "tapered":
            D0, D1, bf, tf, tw = p[1:]
            hw0, hw1 = D0 - 2 * tf, D1 - 2 * tf
            fl = 2 * bf * tf * L * STEEL
            web = 0.5 * (hw0 + hw1) * tw * L * STEEL
            rows.append([mid, m["kind"], m["section"], "flange plate", "2 x %g x %g x %.0f" % (bf, tf, L), 2, round(fl, 1)])
            rows.append([mid, m["kind"], m["section"], "web plate (tapered)", "%g x (%g..%g) x %.0f" % (tw, hw0, hw1, L),
                         1, round(web, 1)])
        elif p[0] == "welded":
            D, bf, tf, tw = p[1:]
            rows.append([mid, m["kind"], m["section"], "flange plate", "2 x %g x %g x %.0f" % (bf, tf, L), 2,
                         round(2 * bf * tf * L * STEEL, 1)])
            rows.append([mid, m["kind"], m["section"], "web plate", "%g x %g x %.0f" % (tw, D - 2 * tf, L), 1,
                         round((D - 2 * tf) * tw * L * STEEL, 1)])
        else:
            pp = S.props(m["section"])
            rows.append([mid, m["kind"], m["section"], "rolled / tube", "L %.0f" % L, 1, round(pp["A"] * L * STEEL, 1)])
    import engine3d as E
    for (t, kind, sec, n1, n2) in info["ele"]:
        if t in done:
            continue
        L = length.get(t, 0.0)
        try:
            A = E.Ipack(sec)[0]
        except Exception:
            A = S.props(sec)["A"]
        rows.append(["e%d" % t, kind, sec, "member", "L %.0f" % L, 1, round(A * L * STEEL, 1)])
    # connection plates and bolts (declared geometry): every splice counted under the spec key that designs it
    import peb_checks as PC
    conn = cfg.get("connections") or {}

    def _plate(ep, sec, sym, b_decl):
        """(b, h) of an extended end plate from its bolt rows: the rows beyond the flange set the extension, both
        ends when the pattern is symmetric; width = the declared plate_b_mm, else the flange width + 2 x 25."""
        lay = PC.end_plate_layout(ep, sec, symmetric=sym)
        p_ = S.props(sec)
        top = max(lay["rows_mm"]) - lay["hf_mm"]                  # beyond the tension flange centre
        bot = -min(lay["rows_mm"])                                # beyond the other flange centre (symmetric)
        edge = float(ep.get("le_mm") or 50.0) + 10.0
        h = p_["d"] + max(top - p_["tf"] / 2.0, 0.0) + edge + (max(bot - p_["tf"] / 2.0, 0.0) + edge if bot > 0 else 25.0)
        b = float(b_decl or (p_["bf"] + 50.0))
        return b, h, lay["n_bolts"]
    def _extra_plates(rows_, spec_, key_, n_):
        """declared extra plates of a joint (spec 'bom_plates': [{part, size, qty_per_joint, kg_each}]), e.g. the
        extension rib stiffeners and the knee-zone column flange plates."""
        for x in spec_.get("bom_plates") or []:
            q = int(x.get("qty_per_joint") or 1) * n_
            kg_ = x.get("kg_each")
            rows_.append([x.get("item") or "%s plates" % key_, "connection", key_, x.get("part", "plate"),
                          x.get("size", ""), q, round(float(kg_) * q, 1) if kg_ is not None else ""])
    knees = [ch for ch in (peb.get("chains") or {}).values() if ch.get("kind") == "column" and not ch.get("releases")]
    for key, spec in (conn.get("beam_column") or {}).items():
        ep = (spec or {}).get("end_plate") or {}
        if not ep or key == "default" or not knees:
            continue
        b, h, nbolt = _plate(ep, key, bool(spec.get("symmetric")), spec.get("plate_b_mm"))
        kg = b * ep["t_plate_mm"] * h * STEEL
        n_ = len(knees)
        rows.append(["knee end plates", "connection", key, "end plate (%s)" % (ep.get("plate_grade") or "E250"),
                     "%.0f x %.0f x %.0f" % (b, ep["t_plate_mm"], h), n_, round(kg * n_, 1)])
        _extra_plates(rows, spec, key, n_)
        rows.append(["knee bolts", "connection", key, "HSFG bolt M%d %s" % (ep["d_mm"], ep["grade"]),
                     "%d per knee (%s); the knee shear check uses the compression-zone bolts of this set"
                     % (nbolt, "symmetric" if spec.get("symmetric") else "one-sided"), nbolt * n_, ""])
    by_key = {}
    for nd, spl in (peb.get("splices") or {}).items():
        kind = spl.get("kind")
        if kind not in ("apex", "rafter_splice", "canopy_root"):
            continue
        secs = [spl.get("sec_left"), spl.get("sec_right")]
        sp, key = PC._spec(cfg, kind, secs)
        if not sp:
            continue
        sec = min(secs, key=lambda s_: S.props(s_)["d"])
        by_key.setdefault(key, {"spec": sp, "n": 0, "sec": sec, "kind": kind})["n"] += 1
    for key, v in sorted(by_key.items()):
        sp, n_ = v["spec"], v["n"]
        ep = sp.get("end_plate") or {}
        if not ep:
            continue
        b, h, nbolt = _plate(ep, v["sec"], bool(sp.get("symmetric")), sp.get("plate_b_mm"))
        npl = 1 if v.get("kind") == "canopy_root" else 2                  # a root plate on the column / a matching pair
        kg = npl * b * ep["t_plate_mm"] * h * STEEL
        rows.append(["%s end plates" % key, "connection", v["sec"],
                     ("end plate pair (%s)" if npl == 2 else "end plate on the column flange (%s)")
                     % (ep.get("plate_grade") or "E250"),
                     ("2 x " if npl == 2 else "") + "%.0f x %.0f x %.0f" % (b, ep["t_plate_mm"], h), n_, round(kg * n_, 1)])
        _extra_plates(rows, sp, key, n_)
        rows.append(["%s bolts" % key, "connection", v["sec"], "HSFG bolt M%d %s" % (ep["d_mm"], ep["grade"]),
                     "%d per joint (%s)" % (nbolt, "symmetric" if sp.get("symmetric") else "one-sided"), nbolt * n_, ""])
        sb = sp.get("shear_bolts") or {}
        if sb.get("n_bolts"):
            rows.append(["%s shear bolts" % key, "connection", v["sec"], "HSFG bolt M%d %s" % (sb.get("d_mm", 0),
                                                                                             sb.get("grade", "")),
                         "%d per joint" % int(sb["n_bolts"]), int(sb["n_bolts"]) * n_, ""])
    bases = [b for b in (info.get("ele") or []) if b[1] == "col" and b[3] // 100000 == 0]
    # each base counted once: role-keyed specs ('lateral_col:<section>') first, then bare section keys, then 'default'
    assigned = set()
    base_specs = sorted((conn.get("column_base") or {}).items(),
                        key=lambda kv: (0 if ":" in kv[0] else (2 if kv[0] == "default" else 1)))
    for key, spec in base_specs:
        sec_k = key.split(":", 1)[1] if ":" in key else key
        hit = [b for b in bases if b[0] not in assigned and (key == "default" or b[2] == sec_k)]
        assigned.update(b[0] for b in hit)
        n_ = len(hit)
        if not n_ or not isinstance(spec, dict) or not spec.get("B_mm"):
            continue
        kg = spec["B_mm"] * spec["L_mm"] * spec["t_plate_mm"] * STEEL
        rows.append(["base plates", "connection", key, "base plate (%s)" % (spec.get("plate_grade") or "E250"),
                     "%.0f x %.0f x %.0f" % (spec["L_mm"], spec["B_mm"], spec["t_plate_mm"]), n_, round(kg * n_, 1)])
        _extra_plates(rows, spec, key, n_)
        a = spec.get("anchors") or {}
        rows.append(["anchor bolts", "connection", key, "anchor rod M%d %s" % (a.get("d_mm", 0), a.get("grade", "")),
                     "%d per base, L %.0f embedment" % (a.get("n_total", 0), ((a.get("embedment") or {}).get("L_mm") or 0)),
                     a.get("n_total", 0) * n_, ""])
        if spec.get("shear_key"):
            sk = spec["shear_key"]
            mk = sk.get("mass_kg")
            rows.append(["shear keys", "connection", key, "shear key (E250)", sk.get("size") or "see anchor_bolt_plan.svg",
                         n_, round(float(mk) * n_, 1) if mk else ""])
    for r in cfg.get("peb_secondary") or []:
        rows.append([r.get("id"), r.get("kind"), r.get("section"), "cold-formed (IS 811)", "lapped", "",
                     round(float(r.get("mass_kg") or 0.0), 1)])
    for s_ in cfg.get("secondary_members") or []:
        if s_.get("mass_kg") is not None:
            rows.append([s_.get("id"), s_.get("kind"), s_.get("section"), "secondary member", "", "",
                         round(float(s_["mass_kg"]), 1)])
    path = os.path.join(outdir, "bom.csv")
    tot = sum(float(r[6]) for r in rows if isinstance(r[6], (int, float)))
    with open(path, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["item", "kind", "section", "part", "size_mm", "qty", "mass_kg"])
        for r in rows:
            w.writerow(r)
        w.writerow(["TOTAL", "", "", "", "", "", round(tot, 1)])
        w.writerow(["note", "", "", "", "TOTAL is the sum of the rows listed; the take-off below also holds the "
                    "declared connection plates not itemised here (stiffeners, continuity plates, doublers, gussets of "
                    "brace ends) through cfg['peb_connection_mass_kg']", "", ""])
        if tonnage and tonnage.get("kg"):
            area = tonnage.get("plan_area_m2") or 0.0
            w.writerow([])
            w.writerow(["steel take-off by category (calc_package peb.tonnage: analysis members + secondary + "
                        "connection plate take-off)", "", "", "", "", "", ""])
            w.writerow(["category", "", "", "", "kg/m2 of plan", "", "mass_kg"])
            for g, kg in tonnage["kg"].items():
                if kg:
                    w.writerow([g, "", "", "", round(kg / area, 2) if area else "", "", round(kg, 1)])
            w.writerow(["TOTAL (take-off)", "", "", "", (tonnage.get("kg_per_m2") or {}).get("total", ""), "",
                        tonnage.get("total_kg")])
            w.writerow(["plan area m2", "", "", "", "", "", area])
    return {"file": "design/bom.csv", "n_rows": len(rows), "total_kg": round(tot, 1),
            "basis": "plates of the welded / tapered members (flanges, linear web), rolled / tube members, declared "
                     "connection plates (end plates, base plates; bolts counted), secondary members (IS 801 purlins / "
                     "girts, roof girder struts); welds, stiffeners and fly braces are listed in the report"}


# ------------------------------------------------------------------------------------------- anchor plan
def write_anchor_plan(cfg, info, outdir, reactions=None):
    """design/anchor_bolt_plan.svg -- grid, base plates, anchors, shear keys, max / min Fz and H per base."""
    import openseespy.opensees as ops
    conn = (cfg.get("connections") or {}).get("column_base") or {}
    bases = [(t, sec, n1, n2) for (t, kind, sec, n1, n2) in info["ele"] if kind == "col" and n1 // 100000 == 0]
    if not bases:
        return None
    xs = [ops.nodeCoord(b[2])[0] for b in bases]
    ys = [ops.nodeCoord(b[2])[1] for b in bases]
    x0, x1, y0, y1 = min(xs), max(xs), min(ys), max(ys)
    W, H = 1400.0, 1400.0 * max((y1 - y0), 1.0) / max((x1 - x0), 1.0) + 260.0
    sc = (W - 200.0) / max(x1 - x0, 1.0)
    P = lambda x, y: (100.0 + (x - x0) * sc, 120.0 + (y1 - y) * sc)
    out = ['<svg xmlns="http://www.w3.org/2000/svg" width="%d" height="%d" viewBox="0 0 %d %d" '
           'font-family="Arial, sans-serif" font-size="11">' % (W, H, W, H),
           '<rect x="0" y="0" width="%d" height="%d" fill="#fff"/>' % (W, H),
           '<text x="20" y="28" font-size="16" font-weight="bold">%s -- anchor bolt plan (column bases)</text>'
           % cfg.get("name", ""),
           '<text x="20" y="48">Grid in m; base plates and anchors drawn x10 at each base. Reactions unfactored '
           '(design/reactions.csv): Fz max / min (kN), H max (kN).</text>']
    gx = sorted({round(x, 1) for x in xs}); gy = sorted({round(y, 1) for y in ys})
    for x in gx:
        a, b = P(x, y1), P(x, y0)
        out.append('<line x1="%.1f" y1="%.1f" x2="%.1f" y2="%.1f" stroke="#bbb" stroke-dasharray="4,3"/>' % (a[0], a[1] - 30, b[0], b[1] + 30))
        out.append('<text x="%.1f" y="%.1f" text-anchor="middle" fill="#555">%.1f</text>' % (a[0], a[1] - 36, x / 1000.0))
    for y in gy:
        a, b = P(x0, y), P(x1, y)
        out.append('<line x1="%.1f" y1="%.1f" x2="%.1f" y2="%.1f" stroke="#bbb" stroke-dasharray="4,3"/>' % (a[0] - 30, a[1], b[0] + 30, b[1]))
        out.append('<text x="%.1f" y="%.1f" text-anchor="end" fill="#555">%.1f</text>' % (a[0] - 36, a[1] + 4, y / 1000.0))
    summ = (reactions or {}).get("summary") or {}
    zoom = 10.0 * sc
    for (t, sec, n1, n2) in bases:
        c = ops.nodeCoord(n1)
        cx, cy = P(c[0], c[1])
        spec = conn.get(sec) or conn.get("default") or {}
        Lp, Bp = float(spec.get("L_mm") or 400.0), float(spec.get("B_mm") or 300.0)
        col_dir = (info.get("col_dir") or {}).get(t, "Y")
        # plate L along the column depth = the frame plane
        lx, ly = (Bp, Lp) if col_dir == "Y" else (Lp, Bp)
        out.append('<rect x="%.1f" y="%.1f" width="%.1f" height="%.1f" fill="#e8eef7" stroke="#1f4e8c"/>'
                   % (cx - lx * zoom / 2, cy - ly * zoom / 2, lx * zoom, ly * zoom))
        a = spec.get("anchors") or {}
        f_ = float(a.get("f_mm") or 100.0); p_ = float(a.get("pitch_mm") or 100.0)
        n_ = int(a.get("n_total") or 4)
        pts = [(-p_ / 2, -f_), (p_ / 2, -f_), (-p_ / 2, f_), (p_ / 2, f_)] if n_ == 4 else \
            [(-p_ / 2 + k * p_ / max(n_ // 2 - 1, 1), s * f_) for s in (-1, 1) for k in range(max(n_ // 2, 1))]
        for (u, v) in pts:
            ux, uy = (u, v) if col_dir == "Y" else (v, u)
            out.append('<circle cx="%.1f" cy="%.1f" r="%.1f" fill="#c0392b"/>' % (cx + ux * zoom, cy + uy * zoom,
                                                                                   max(1.5, a.get("d_mm", 24) * zoom / 2)))
        if spec.get("shear_key"):
            out.append('<rect x="%.1f" y="%.1f" width="%.1f" height="%.1f" fill="none" stroke="#27ae60" '
                       'stroke-dasharray="2,2"/>' % (cx - 4, cy - 4, 8, 8))
        s = summ.get(str(n1)) or {}
        if s:
            out.append('<text x="%.1f" y="%.1f" font-size="9" fill="#333">%.0f / %.0f / %.0f</text>'
                       % (cx + 8, cy - 8, s.get("Fz_max_kN", 0), s.get("Fz_min_kN", 0), s.get("H_max_kN", 0)))
    yk = H - 110
    out.append('<text x="20" y="%.0f" font-weight="bold">Base types</text>' % yk)
    k = 0
    for key, spec in conn.items():
        a = spec.get("anchors") or {}
        sk = spec.get("shear_key") or {}
        out.append('<text x="20" y="%.0f">%s: plate %.0f x %.0f x %.0f (E250); %d anchors M%d %s, embedment %.0f mm%s</text>'
                   % (yk + 18 * (k + 1), key, spec.get("L_mm", 0), spec.get("B_mm", 0), spec.get("t_plate_mm", 0),
                      a.get("n_total", 0), a.get("d_mm", 0), a.get("grade", ""),
                      (a.get("embedment") or {}).get("L_mm") or 0,
                      ("; shear key %.0f kN" % (sk.get("capacity_N", 0) / 1e3)) if sk else ""))
        k += 1
    out.append("</svg>")
    path = os.path.join(outdir, "anchor_bolt_plan.svg")
    open(path, "w").write("\n".join(out))
    return {"file": "design/anchor_bolt_plan.svg", "n_bases": len(bases)}


# ------------------------------------------------------------------------------------------- STAAD export
def staad_label(sec):
    """IS 808:2021 designations without the old 'IS' prefix (MB 300, MC 150) -> the STAAD.Pro Indian table names
    (ISMB300, ISMC150); angles (ISA...) and other labels unchanged.  MSME (2026-10)."""
    u = str(sec).upper().replace(" ", "")
    for pre in ("MB", "MC", "WB", "LB", "JB", "HB", "SC", "LC", "JC"):
        if u.startswith(pre) and len(u) > len(pre) and u[len(pre)].isdigit():
            return "IS" + u
    return u


def write_staad(cfg, info, path, pkg=None):
    """model.std -- STAAD.Pro input of the stepped analysis model.  Coordinates: STAAD X = x, STAAD Y = z (up),
    STAAD Z = -y (right-handed).  Tapered segments as TAPERED (depth at each end, web, flange), prismatic welded I
    as TAPERED with equal depths, tubes as PIPE, rolled sections by their IS 808 name (TABLE ST, may need the STAAD
    Indian table).  The roof diaphragm of the Steltic model (eave nodes tied across the span, ridge nodes along it,
    roof_geometry.tie_diaphragm) is written as SLAVE commands to the master joint of each level (the Steltic master,
    supported vertically and against tilting like the OpenSees one); load cases: every engine basic case recorded
    from the engine's own load application (staad_loads: dead, collateral + PV, imposed, snow, crane, member wind,
    storey forces and accidental torsion at the master, vertical earthquake, IS 800 4.3.6 notional loads) and a LOAD
    COMBINATION for every engine combination (pkg['load_combinations']).  The ops domain is rebuilt by the caller."""
    import openseespy.opensees as ops
    import peb_build as PB
    import roof_geometry as RG
    eles = info["ele"]
    ties = {k: v for k, v in sorted((getattr(RG, "TIES", None) or {}).items())}
    masters = {int(v["master"]) for v in ties.values()}
    nodes = sorted({n for e in eles for n in e[3:5]} | masters)
    nid = {n: i + 1 for i, n in enumerate(nodes)}
    L = ["STAAD SPACE", "* %s -- stepped analysis model exported by Steltic (peb_outputs.write_staad)" % cfg.get("name"),
         "* Coordinates: STAAD X = x, Y = z (up), Z = -y. Units mm, kN.",
         "* Tapered members are stepped (one STAAD member per segment, TAPERED with the exact end depths).",
         "* Every engine load case is exported (staad_loads): dead (permanent), collateral + PV, imposed, snow,",
         "*   crane patterns, member wind patterns, storey forces + accidental torsion at the diaphragm master,",
         "*   vertical earthquake and the IS 800 4.3.6 notional loads; one LOAD COMBINATION per engine combination.",
         "*   Combinations marked (RSA->ESM) used response spectrum forces in Steltic; here they carry the",
         "*   equivalent static storey forces of the same direction (replace with a STAAD IS 1893 spectrum).",
         "*   The Steltic roof diaphragm is written as SLAVE commands to the master joint of each level.",
         "START JOB INFORMATION", "ENGINEER DATE %s" % "2026-10", "END JOB INFORMATION",
         "INPUT WIDTH 79", "UNIT MMS KN", "JOINT COORDINATES"]
    for n in nodes:
        c = ops.nodeCoord(n)
        L.append("%d %.1f %.1f %.1f;" % (nid[n], c[0], c[2], -c[1]))
    L.append("MEMBER INCIDENCES")
    mid = {}
    for k_, (t, kind, sec, n1, n2) in enumerate(eles):
        mid[t] = k_ + 1
        L.append("%d %d %d;" % (k_ + 1, nid[n1], nid[n2]))
    L.append("DEFINE MATERIAL START")
    L.append("ISOTROPIC STEEL")
    L.append("E 200")
    L.append("POISSON 0.3")
    L.append("DENSITY 7.85e-08")
    L.append("ALPHA 1.2e-05")
    L.append("END DEFINE MATERIAL")
    L.append("MEMBER PROPERTY")
    for (t, kind, sec, n1, n2) in eles:
        e = PB.element(t) if PB.active() else None
        p = S.props(sec)
        if e or p.get("plates"):
            di = S.props(e["sec_i"])["d"] if e else p["d"]
            dj = S.props(e["sec_j"])["d"] if e else p["d"]
            L.append("%d TAPERED %.1f %.1f %.1f %.1f %.1f %.1f %.1f" % (mid[t], di, p["tw"], dj, p["bf"], p["tf"],
                                                                         p["bf"], p["tf"]))
        elif str(sec).upper().startswith("CHS"):
            od = p.get("d") or p.get("D") or 100.0
            tt = p.get("t") or p.get("tw") or 4.0
            L.append("%d PIPE OD %.1f ID %.1f" % (mid[t], od, od - 2 * tt))
        elif p.get("section_type") == "double_angle":
            # MSME (2026-10): two angles back to back (STAAD 'D' double angle, equal legs; LD / SD long / short legs
            # back to back for an unequal pair), SP = the gusset gap
            comp = str(p["component"])
            eq = abs(float(p["leg_connected_mm"]) - float(p["leg_outstanding_mm"])) < 1e-6
            kind_ = "D" if eq else ("LD" if p["leg_connected_mm"] > p["leg_outstanding_mm"] else "SD")
            L.append("%d TABLE %s %s SP %.1f" % (mid[t], kind_, comp, float(p["gap_mm"])))
        else:
            L.append("%d TABLE ST %s" % (mid[t], staad_label(sec)))
    L.append("CONSTANTS")
    L.append("MATERIAL STEEL ALL")
    col_dir = info.get("col_dir") or {}
    b90 = [mid[t] for (t, kind, sec, n1, n2) in eles if kind == "col" and str(col_dir.get(t, "Y")).upper() == "Y"]
    if b90:
        L.append("BETA 90 MEMB %s" % " ".join(str(m) for m in b90))
    L.append("SUPPORTS")
    sup_pin, sup_fix = [], []
    for n in nodes:
        if n in masters:
            continue
        try:
            fx = ops.getFixedDOFs(n)
        except Exception:
            fx = []
        if fx:
            (sup_fix if len(fx) >= 6 else sup_pin).append(nid[n])
    if sup_pin:
        L.append("%s PINNED" % " ".join(str(x) for x in sup_pin))
    if sup_fix:
        L.append("%s FIXED" % " ".join(str(x) for x in sup_fix))
    if masters:      # the Steltic master: free in plan (FX, FZ) and about the vertical (MY), held otherwise
        L.append("%s FIXED BUT FX FZ MY" % " ".join(str(nid[m]) for m in sorted(masters)))
    rel = info.get("beam_rel") or {}
    crel = info.get("col_rel") or {}
    rl = []
    for (t, kind, sec, n1, n2) in eles:
        if kind == "beam" and rel.get(t) and rel[t][0] != "none":
            r = rel[t][0]
            if r in ("I", "both"):
                rl.append("%d START MZ" % mid[t])
            if r in ("J", "both"):
                rl.append("%d END MZ" % mid[t])
        if kind == "col" and crel.get(t):
            r = crel[t]
            if r in ("I", "both"):
                rl.append("%d START MY MZ" % mid[t])
            if r in ("J", "both"):
                rl.append("%d END MY MZ" % mid[t])
    if rl:
        L.append("MEMBER RELEASE")
        L += rl
    br = [mid[t] for (t, kind, sec, n1, n2) in eles if kind in ("brace", "truss")]   # MSME: truss webs / knee braces
    if br:
        L.append("MEMBER TRUSS")
        L.append(" ".join(str(m) for m in br))
    # diaphragm as SLAVE commands (roof_geometry.TIES: eave / braced-line joints follow the master across the span,
    # ridge joints along it, every other diaphragm joint fully in plan)
    pls = RG.planes(cfg) if RG.has_planes(cfg) else []
    dof = {1: "FX", 2: "FZ"}                       # OpenSees X -> STAAD X, OpenSees Y -> STAAD -Z
    sl = []
    for k, tv in ties.items():
        m = nid[int(tv["master"])]
        both = set(tv.get("across") or []) & set(tv.get("along") or [])     # e.g. a gable apex on a braced line
        full = [nid[n] for n in list(tv.get("full") or []) + sorted(both) if n in nid]
        acr = [nid[n] for n in tv.get("across") or [] if n in nid and n not in both]
        alg = [nid[n] for n in tv.get("along") or [] if n in nid and n not in both]
        if full:
            sl.append("SLAVE ZX MASTER %d JOINT %s" % (m, " ".join(str(x) for x in full)))
        if acr and tv.get("across_dof"):
            sl.append("SLAVE %s MASTER %d JOINT %s" % (dof[tv["across_dof"]], m, " ".join(str(x) for x in acr)))
        if alg and tv.get("along_dof"):
            sl.append("SLAVE %s MASTER %d JOINT %s" % (dof[tv["along_dof"]], m, " ".join(str(x) for x in alg)))
    if sl:
        L.append("* roof diaphragm (Steltic tie_diaphragm): eave joints follow the master across the span only, ridge")
        L.append("* joints along it only, so the eaves spread freely under gravity")
        L += sl
    # load cases (first wave item 8): every engine basic case, recorded from the engine's own load application
    import staad_loads as SL
    mk = {k: nid[int(v["master"])] for k, v in ties.items()}
    try:
        lines_, summ = SL.staad_lines(cfg, list((pkg or {}).get("load_combinations") or []), nid, mid, mk)
    except Exception as ex:                                  # never lose the geometry for a load-export failure
        lines_, summ = ["* load export failed: %s: %s" % (type(ex).__name__, ex)], {"error": str(ex)}
    L += lines_
    L.append("PERFORM ANALYSIS")
    L.append("FINISH")
    open(path, "w").write("\n".join(L) + "\n")
    out = {"file": os.path.basename(path), "n_joints": len(nodes), "n_members": len(eles),
           "n_masters": len(masters), "n_primary_cases": summ.get("n_primary"),
           "n_combinations": summ.get("n_combinations"), "n_combinations_not_exported": 0,
           "rsa_combinations_as_static": summ.get("rsa_as_static"), "unmapped_loads": summ.get("unmapped_loads"),
           "missing_terms": summ.get("missing_terms", 0),
           "unmapped_calls": summ.get("unmapped_calls"), "case_totals_kN": summ.get("case_totals_kN"),
           "note": "geometry, stepped TAPERED properties, releases, supports, roof diaphragm (SLAVE) and every engine "
                   "load case (dead, collateral + PV, imposed, snow, crane, member wind, storey forces, torsion, "
                   "vertical EQ, notional) with all combinations"}
    if summ.get("error"):
        out["error"] = summ["error"]
    return out
