"""peb_checks.py -- PEB (2026-10): the checks that belong to the stepped tapered-member model (docs/PEB_TAPERED_SCOPE.md).

  * splice_records   bolted end-plate rafter splices and the apex joint (cfg['connections']['rafter_splice']):
                     moment by IS 800 10.3.5 / 10.4.7 (end plate + prying, india_connections.end_plate_moment_capacity),
                     shear by HSFG slip 10.4.3 at ultimate (gamma_mf 1.25), 12.4.1 HSFG gate, 12.4.2 CJP gate for the
                     flange / web-to-end-plate welds (owner ruling D-T6: the connection welds).  Design moment:
                     apex = 1.2 Mp of the face section (owner ruling D-T7); rafter splice = the factored moment at the
                     splice, x 1.80 with the IS 18168 6.5 location rule (>= 3 db from the column face) where IS 18168
                     applies (SMRF, route B of D-T2).
  * flange_brace_records   IS 800 8.3.2: each inner-flange restraint resists max(2.5 % of the maximum compression
                     flange force / number of restraints, 1 % of it); the fly-brace angle is a single angle loaded
                     through one leg (7.5.1.2) at the declared inclination (cfg['flange_braces']['members']).
  * frame_stability  IS 800 4.6.2(b): elastic buckling load factor of the stepped model by a rational analysis --
                     lambda_cr = AF / (AF - 1) with AF the second-order / first-order sway ratio of each frame under the
                     factored gravity set with a small lateral perturbation; B-2.1 (lambda_cr > 5).
  * tonnage          steel take-off of the analysis model by group (primary / bracing / crane / canopy), plus the
                     declared secondary members (cfg['peb_secondary'] -- e.g. the IS 801 purlins and girts designed by
                     the CFS engine) -> kg and kg/m2 of plan area.
Units N, mm, MPa.
"""
from __future__ import annotations

import math

import sections as S

SRC = "steel_engine/peb_checks.py"


def _row(name, value, limit, *, clause, cite, dc=None, ok=None, gate=False, **extra):
    if dc is None and value is not None and limit not in (None, 0):
        dc = abs(float(value)) / float(limit)
    if ok is None and dc is not None:
        ok = dc <= 1.0
    r = {"name": name, "value": value, "limit": limit, "dc": dc, "ok": ok, "clause": clause, "cite": cite,
         "source": SRC}
    if gate:
        r["gate"] = True
    if ok is None:
        r["found"] = False
    r.update(extra)
    return r


def _fy_plate(sec, cfg):
    import india_is800 as I8
    p = S.props(sec)
    g = (cfg or {}).get("steel_grade")
    m = I8.material_for_section(p, g)
    return m.get("fy_MPa") or 250.0


def _mp(sec, cfg):
    p = S.props(sec)
    return p["Zx"] * _fy_plate(sec, cfg)


def _spec(cfg, kind, secs):
    """The declared cfg['connections']['rafter_splice'] spec of a joint: a key naming one of its sections first (e.g.
    the gable-line apex), then the joint kind ('apex' / 'rafter_splice' / 'canopy_root'), then 'default'."""
    sp = ((cfg or {}).get("connections") or {}).get("rafter_splice") or {}
    for k in list(secs) + [kind] + ["default"]:
        if k in sp and isinstance(sp[k], dict):
            return dict(sp[k]), k
    return None, None


def end_plate_layout(ep, sec, symmetric=False, tol_mm=30.0):
    """Bolt rows of a declared end plate: ep['rows'] are the tension rows for one sign of moment, lever arms h from the
    compression-flange centre.  symmetric=True: the same pattern mirrored about mid-depth for the other sign (rows that
    coincide within tol_mm are one row).  Returns {'rows_mm' (all bolt rows, from the bottom flange centre), 'n_bolts'
    (tension / flange bolts, both signs), 'reverse_rows' (lever arms for the opposite sign)}."""
    p = S.props(sec)
    hf = float(p["d"]) - float(p["tf"])
    rows = [(float(r["h_mm"]), int(r.get("n_pairs") or 1)) for r in (ep.get("rows") or [])]
    pos = list(rows)
    if symmetric:
        for h, n in rows:
            hm = hf - h
            if not any(abs(hm - q) <= tol_mm for q, _n in pos):
                pos.append((hm, n))
    rev = [{"h_mm": hf - q, "n_pairs": n} for q, n in pos if hf - q > 0.0]
    return {"rows_mm": sorted(q for q, _n in pos), "n_bolts": sum(2 * n for _q, n in pos), "reverse_rows": rev,
            "hf_mm": hf}


def end_plate_capacity(ep, cfg=None, rows=None):
    """india_connections.end_plate_moment_capacity of a declared end plate (optionally with other rows)."""
    import india_connections as C
    e = dict(ep)
    if rows is not None:
        e["rows"] = rows
    e.setdefault("plate_grade", (cfg or {}).get("plate_grade"))
    e.setdefault("job_steel_grade", (cfg or {}).get("steel_grade"))
    return C.end_plate_moment_capacity(**e)


def _signed_node_moments(reg, envt, nd):
    """Per element end framing into nd: {combo: M} with that end's own sign convention (consistent across combos)."""
    out = []
    for t, (kind, sec, n1, n2) in reg.items():
        if kind != "beam" or nd not in (n1, n2):
            continue
        end = "i" if nd == n1 else "j"
        ms = {}
        for lab, r in (envt[t].get("records") or {}).items():
            r = list(r) + [0.0] * 13
            ms[lab] = r[4] if end == "i" else r[5]
        if ms:
            out.append(ms)
    return out


def reverse_demand(reg, envt, nd):
    """The largest moment of the sign opposite to the governing one at node nd (N-mm, >= 0) and its combination."""
    best, lab_b = 0.0, None
    for ms in _signed_node_moments(reg, envt, nd):
        lab_g = max(ms, key=lambda l: abs(ms[l]))
        sg = 1.0 if ms[lab_g] >= 0 else -1.0
        for l, m in ms.items():
            if m * sg < 0 and abs(m) > best:
                best, lab_b = abs(m), l
    return best, lab_b


def _node_forces(reg, envt, nd):
    """{combo: (M, V, N)} at node nd: the largest |M| of the elements framing in at that end (concurrent V, N)."""
    out = {}
    for t, (kind, sec, n1, n2) in reg.items():
        if kind != "beam" or nd not in (n1, n2):
            continue
        end = "i" if nd == n1 else "j"
        for lab, r in (envt[t].get("records") or {}).items():
            r = list(r) + [0.0] * 13
            M = r[4] if end == "i" else r[5]
            V, N = r[9] or r[3], r[0]
            cur = out.get(lab)
            if cur is None or abs(M) > abs(cur[0]):
                out[lab] = (M, V, N)
    return out


def splice_records(cfg, peb, reg, envt, s12_cfg=None, system=None):
    """Connection records (pkg['connections'] format) for every PEB rafter splice and apex joint."""
    import india_connections as C
    import india_is800_s12 as S12
    recs = []
    is18 = _is18_smf(cfg, s12_cfg, system)
    for nd, spl in sorted((peb.get("splices") or {}).items()):
        kind = spl.get("kind")
        if kind not in ("apex", "rafter_splice", "canopy_root"):
            continue
        secs = [spl.get("sec_left"), spl.get("sec_right")]
        sec_min = min(secs, key=lambda s_: _mp(s_, cfg))
        Mp = _mp(sec_min, cfg)
        f = _node_forces(reg, envt, nd)
        if f:
            lab_m = max(f, key=lambda l: abs(f[l][0]))
            M_an = abs(f[lab_m][0])
            V_an = max(abs(v[1]) for v in f.values())
            N_an = max(abs(v[2]) for v in f.values())
        else:
            lab_m, M_an, V_an, N_an = None, 0.0, 0.0, 0.0
        rows, notes = [], []
        if kind == "canopy_root":
            Mdem = M_an
            basis = ("cantilever canopy beam root: the factored root moment (%s); not part of the moment frame"
                     % lab_m)
            clause_m = "IS 800:2007 10.3.5 / 10.4.7 (end plate in bending, bolt tension with prying)"
        elif spl.get("gravity"):
            Mdem = M_an
            basis = ("gravity (post-and-beam) frame line: the factored moment at the joint (%s); not part of the "
                     "moment frame, D-T7 does not apply" % lab_m)
            clause_m = "IS 800:2007 10.3.5 / 10.4.7 (end plate in bending, bolt tension with prying)"
        elif kind == "apex":
            Mdem = max(1.2 * Mp, (1.8 if is18 else 1.0) * M_an)
            basis = ("owner ruling D-T7: apex joint for 1.2 Mp of the section at the joint face (%s, Mp %.1f kN-m); "
                     "analysis %.1f kN-m (%s)%s" % (sec_min, Mp / 1e6, M_an / 1e6, lab_m,
                                                  "; IS 18168 6.5: >= 1.80 x the analysis moment" if is18 else ""))
            clause_m = "IS 800:2007 12.10.2.1 / 12.11.2.1 (by owner ruling D-T7) + 10.3.5 / 10.4.7" + \
                ("; IS 18168:2023 6.5" if is18 else "")
        elif is18:
            Mdem = 1.8 * M_an
            basis = "IS 18168:2023 6.5: design strength >= 1.80 x the required strength (%.1f kN-m, %s)" % (M_an / 1e6, lab_m)
            clause_m = "IS 18168:2023 6.5 + IS 800:2007 10.3.5 / 10.4.7"
        else:
            Mdem = M_an
            basis = "factored moment at the splice (%s)" % lab_m
            clause_m = "IS 800:2007 10.3.5 / 10.4.7 (end plate in bending, bolt tension with prying)"
        sp, key = _spec(cfg, kind, secs)
        if not sp:
            rows.append(_row("end-plate %s" % kind, Mdem, None, clause=clause_m, cite=basis, ok=None,
                             reason="cfg['connections']['rafter_splice'] not declared for %s / %s" % (kind, secs)))
        else:
            ep = dict(sp.get("end_plate") or {})
            ep.setdefault("plate_grade", sp.get("plate_grade") or cfg.get("plate_grade"))
            ep.setdefault("job_steel_grade", cfg.get("steel_grade"))
            r = C.end_plate_moment_capacity(**ep)
            cap = r.get("capacity_Nmm")
            jn = {"apex": "apex joint", "canopy_root": "canopy beam root"}.get(kind, "rafter splice")
            rows.append(_row("end-plate moment (%s)" % jn, Mdem, cap,
                             clause=clause_m, cite=basis + "; capacity: " + str(r.get("cite")),
                             governing_mode=r.get("governing"),
                             Te_per_bolt_N=r.get("Te_per_bolt_N"), Q_per_bolt_N=r.get("Q_per_bolt_N")))
            # moment reversal (wind uplift / seismic): the opposite sign with the bolts actually declared
            sym = bool(sp.get("symmetric"))
            lay = end_plate_layout(sp.get("end_plate") or {}, sec_min, symmetric=sym)
            M_rev, lab_rev = reverse_demand(reg, envt, nd)
            if kind == "apex" and not spl.get("gravity"):
                Mdem_r = max(1.2 * Mp, (1.8 if is18 else 1.0) * M_rev)
                basis_r = "D-T7: 1.2 Mp in either sign; analysis reverse %.1f kN-m (%s)%s" % (
                    M_rev / 1e6, lab_rev, " x 1.80 (IS 18168 6.5)" if is18 else "")
            elif is18 and kind == "rafter_splice":
                Mdem_r = 1.8 * M_rev
                basis_r = "IS 18168 6.5: 1.80 x the reverse required strength %.1f kN-m (%s)" % (M_rev / 1e6, lab_rev)
            else:
                Mdem_r = M_rev
                basis_r = "reverse factored moment %.1f kN-m (%s)" % (M_rev / 1e6, lab_rev)
            if sym:
                cap_r = cap
                cite_r = "symmetric bolt pattern (declared): the same rows at the other flange, %d bolts" % lay["n_bolts"]
            else:
                rr = end_plate_capacity(ep, cfg, rows=lay["reverse_rows"]) if lay["reverse_rows"] else {}
                cap_r = rr.get("capacity_Nmm") or 0.0
                cite_r = ("one-sided bolt pattern: the declared rows measured from the other flange (%s mm)"
                          % [round(x["h_mm"]) for x in lay["reverse_rows"]])
            rows.append(_row("end-plate moment, reverse sign (%s)" % jn, Mdem_r, cap_r if cap_r else None,
                             clause=clause_m, cite=basis_r + "; " + cite_r,
                             **({} if cap_r else ({"dc": 99.0, "ok": False,
                                                   "reason": "no bolt row on the tension side for the reverse sign"}
                                                  if Mdem_r > 0 else {"dc": 0.0, "ok": True}))))
            if sp.get("column_section"):
                # a joint bolted to a column flange (the canopy-beam root): the column flange is the other T-stub
                # flange the bolts pull on (IS 800 10.4.7 / 8.2.1.2), the same rows, both signs
                csec_ = sp["column_section"]
                pcol = S.props(csec_)
                t_cf = float(sp.get("column_flange_t_mm") or pcol["tf"])
                g_cf = sp.get("gauge_mm")
                lv_cf = float((float(g_cf) / 2.0 - pcol["tw"] / 2.0 - 8.0) if g_cf else ep.get("lv_mm"))
                grade_c = (sp.get("column_flange_grade") or (cfg.get("grade_by_section") or {}).get(csec_)
                           or cfg.get("steel_grade"))
                cf = dict(sp.get("end_plate") or {}, t_plate_mm=t_cf, fy_plate_MPa=_fy_plate(csec_, cfg), lv_mm=lv_cf,
                          plate_grade=grade_c, web_t_mm=float(pcol["tw"]) + float(sp.get("column_web_doubler_mm") or 0.0),
                          web_fy_MPa=_fy_plate(csec_, cfg), hf_mm=lay["hf_mm"])
                caps_cf = [(end_plate_capacity(cf, cfg) or {}).get("capacity_Nmm")]
                if not sym and lay["reverse_rows"]:
                    caps_cf.append((end_plate_capacity(cf, cfg, rows=lay["reverse_rows"]) or {}).get("capacity_Nmm"))
                caps_cf = [c_ for c_ in caps_cf if c_]
                rows.append(_row("column flange at the end-plate bolt rows (T-stub flange, both signs)",
                                 max(Mdem, Mdem_r), min(caps_cf) if caps_cf else None,
                                 clause="IS 800:2007 10.4.7 (prying) / 8.2.1.2 (column flange strip)",
                                 cite="column %s flange %.0f mm (%s), lv %.1f mm, the end-plate rows and %d M%d %s"
                                      % (csec_, t_cf, grade_c, lv_cf, lay["n_bolts"], int(ep.get("d_mm") or 0),
                                         ep.get("grade"))))
            notes.append("bolts: %d M%d %s tension / flange bolts (%s) + %d shear bolts" % (
                lay["n_bolts"], int(ep.get("d_mm") or 0), ep.get("grade"), "symmetric" if sym else "one-sided",
                int((sp.get("shear_bolts") or {}).get("n_bolts") or 0)))
            sb = sp.get("shear_bolts") or {}
            if sb:
                one = C.hsfg_slip_capacity(sb.get("d_mm"), sb.get("grade", "8.8"), mu_f=sb.get("mu_f"),
                                           surface=sb.get("surface"), n_e=sb.get("n_e", 1))
                Vcap = (one.get("Vdsf_N") or 0.0) * int(sb.get("n_bolts") or 0) or None
                Vdem = V_an * (1.8 if (is18 and kind == "rafter_splice") else 1.0)
                rows.append(_row("bolt slip in shear (%d M%d %s HSFG, ultimate)" % (int(sb.get("n_bolts") or 0),
                                                                                   int(sb.get("d_mm") or 0),
                                                                                   sb.get("grade", "8.8")),
                                 Vdem, Vcap, clause="IS 800:2007 10.4.3 (gamma_mf 1.25)", cite=one.get("cite")))
            else:
                rows.append(_row("bolt shear", V_an, None, clause="IS 800:2007 10.4.3", cite="shear bolts", ok=None,
                                 reason="rafter_splice shear_bolts not declared"))
            g1 = C.hsfg_gate(sp.get("bolt_type") or ep.get("bolt_type"))
            rows.append(dict(_row("12.4.1 bolt type", None, None, clause=g1["clause"], cite=g1["cite"], ok=g1["ok"],
                                  gate=True)))
            g2 = C.cjp_weld_gate(sp.get("weld_type"), location="splice_end_plate")  # not a column splice
            if "splice" in str(g2.get("clause")):
                g2 = C.cjp_weld_gate(sp.get("weld_type"), location="beam_column")
            rows.append(dict(_row("12.4.2 flange / web to end-plate welds (owner ruling D-T6: connection welds)", None,
                                  None, clause=g2["clause"], cite=g2["cite"], ok=g2["ok"], gate=True)))
        if is18 and kind == "rafter_splice":
            db = max(S.props(s_)["d"] for s_ in secs)
            d_face = spl.get("col_face_dist_mm")
            if d_face is None:
                d_face = float(spl.get("dist_from_eave_mm") or 0.0) - float(spl.get("col_half_depth_mm") or 0.0)
            rows.append(_row("IS 18168 6.5 splice location (>= 3 db from the column face)", 3.0 * db, d_face,
                             clause="IS 18168:2023 6.5", cite="splice at %.0f mm plan from the column face, db %.0f mm"
                                                              % (d_face, db), dc=3.0 * db / d_face if d_face > 0 else 99.0,
                             sense=">="))
        strength = [r_ for r_ in rows if isinstance(r_.get("dc"), (int, float)) and not r_.get("gate")]
        gov = max(strength, key=lambda r_: r_["dc"]) if strength else None
        if any(r_.get("ok") is None for r_ in rows):
            DC = None
        else:
            DC = gov["dc"] if gov else None
        recs.append({"id": "conn-peb-splice-%d" % nd, "type": "PEB %s (bolted extended end plate, HSFG)" % (
                        {"apex": "apex joint", "canopy_root": "canopy beam root"}.get(kind, "rafter splice")),
                     "section": "/".join(secs), "node": nd, "chain": spl.get("chain"),
                     "demand": {"M_design_Nmm": round(Mdem, 1), "M_analysis_Nmm": round(M_an, 1),
                                "V_N": round(V_an, 1), "N_N": round(N_an, 1), "combo": lab_m, "basis": basis},
                     "inputs": {"V_N": round(V_an, 1), "spec_key": key},
                     "design_basis": "PEB stepped model (peb_checks.splice_records); declared geometry in "
                                     "cfg['connections']['rafter_splice']",
                     "checks": rows, "DC": DC, "governing_check": gov.get("name") if gov else None,
                     "clause": gov.get("clause") if gov else None, "limit_state": "IS 800:2007 10 / 12.4",
                     "cited": gov.get("clause") if gov else None, "notes": notes})
    return recs


# ------------------------------------------------------------------------------------------- flange braces
def flange_brace_records(cfg, peb, reg, envt):
    """IS 800 8.3.2 restraint force and the fly-brace angle check, per member chain (rafters and columns)."""
    import india_is800 as I8
    fb = (cfg or {}).get("flange_braces") or {}
    mem = fb.get("members") or {}
    out = []
    if not fb:
        return out
    for kind in ("rafter", "column"):
        spec = mem.get(kind) or mem.get("default")
        lst = (fb.get(kind) or {}).get("fly_braces_mm") or []
        if not lst:
            continue
        # maximum compression flange force over the chains of this kind: M / (d - tf) + N / 2
        Ff, where = 0.0, None
        for t, e in (peb.get("elements") or {}).items():
            m = (peb.get("members") or {}).get(e["member"]) or {}
            if m.get("kind") != kind or t not in envt:
                continue
            for end, sec_e in (("i", e["sec_i"]), ("j", e["sec_j"])):
                p = S.props(sec_e)
                for lab, r in (envt[t].get("records") or {}).items():
                    r = list(r) + [0.0] * 13
                    M = abs(r[4] if end == "i" else r[5])
                    F = M / (p["d"] - p["tf"]) + max(-r[0], 0.0) * (p["bf"] * p["tf"]) / p["A"]
                    if F > Ff:
                        Ff, where = F, (t, end, sec_e, lab)
        n_r = max(len(lst), 1)
        F_point = max(0.025 * Ff / n_r, 0.01 * Ff)
        rows = [_row("restraint force per point: max(2.5 %% Ff,max / n, 1 %% Ff,max)", F_point, None,
                     clause="IS 800:2007 8.3.2", cite="2.5 percent of the maximum force in the compression flange "
                                                      "divided equally between the %d restraint points; each point "
                                                      ">= 1 percent (Ff,max = %.1f kN at element %s %s)"
                                                      % (n_r, Ff / 1e3, where[0] if where else "-",
                                                         where[1] if where else ""),
                     ok=True, gate=True, Ff_max_N=Ff)]
        if not spec:
            rows.append(_row("fly-brace member", F_point, None, clause="IS 800:2007 7.5.1.2", cite="fly brace", ok=None,
                             reason="cfg['flange_braces']['members']['%s'] not declared" % kind))
        else:
            sec = spec["section"]
            ang = math.radians(float(spec.get("angle_deg", 45.0)))
            Lb = float(spec["L_mm"])
            P = F_point / math.cos(ang)
            fy = float(spec.get("fy_MPa") or 250.0)
            r7 = I8.single_angle_7_5_1_2(sec, fy, Lb, n_bolts=int(spec.get("n_bolts", 1)),
                                         fixity=spec.get("fixity", "hinged"))
            rows.append(_row("fly brace %s (single angle, one leg, %d bolt(s)) in compression" % (
                sec, int(spec.get("n_bolts", 1))), P, r7.get("Pd_N"), clause="IS 800:2007 7.5.1.2 / 7.1.2",
                cite="axial = restraint force / cos %.0f deg; L = %.0f mm; %s" % (math.degrees(ang), Lb, r7.get("cite")),
                lambda_e=r7.get("lambda")))
            klr = r7.get("KL_over_r") or 0.0
            rows.append(_row("fly brace slenderness KL/r", klr, 180.0, clause="IS 800:2007 Table 3 (i)",
                             cite="compression member KL/r <= 180"))
            bolt = spec.get("bolt")
            if bolt:
                import india_connections as C
                one = C.bolt_capacity_is800(bolt["d_mm"], bolt.get("grade", "4.6"), nn=1, ns=0,
                                            t_mm=bolt.get("t_mm"), fu_plate_MPa=bolt.get("fu_plate_MPa", 410.0),
                                            e_mm=bolt.get("e_mm"), p_mm=bolt.get("p_mm", 60.0),
                                            d0_mm=bolt.get("d0_mm"))
                Vd = min(v for v in (one.get("Vdsb_N"), one.get("Vdpb_N")) if v) if one.get("found", True) else None
                rows.append(_row("fly-brace bolt (M%d %s) shear / bearing" % (bolt["d_mm"], bolt.get("grade", "4.6")),
                                 P, Vd, clause="IS 800:2007 10.3.3 / 10.3.4", cite=one.get("cite")))
        strength = [r_ for r_ in rows if isinstance(r_.get("dc"), (int, float)) and not r_.get("gate")]
        gov = max(strength, key=lambda r_: r_["dc"]) if strength else None
        DC = None if any(r_.get("ok") is None for r_ in rows) else (gov["dc"] if gov else None)
        out.append({"id": "conn-peb-flange-brace-%s" % kind, "type": "PEB flange (fly) braces on the %ss" % kind,
                    "section": (spec or {}).get("section"), "demand": {"F_point_N": round(F_point, 1),
                                                                       "Ff_max_N": round(Ff, 1), "n_points": n_r},
                    "inputs": {"positions_mm": lst}, "checks": rows, "DC": DC,
                    "governing_check": gov.get("name") if gov else None, "clause": gov.get("clause") if gov else None,
                    "design_basis": "IS 800:2007 8.3.2 restraint force; 7.5.1.2 single angle",
                    "limit_state": "IS 800:2007 8.3.2 / 7.5", "cited": "IS 800:2007 8.3.2", "notes": []})
    return out


# ------------------------------------------------------------------------------------------- frame stability
def frame_stability(cfg, fD=1.5, fL=1.5, ratio=0.005):
    """IS 800 4.6.2(b) rational elastic buckling load factor of the stepped model in each plan direction: on the
    P-Delta model, (A) a lateral perturbation H alone (no axial force: first-order sway d1), (B) the factored
    gravity set fD DL + fL LL (nodal) alone, (C) gravity + H; AF = (dC - dB) / dA at the eave (column-top) nodes and
    lambda_cr = AF / (AF - 1) (sway mode; every tapered column / rafter is 8 segments, so member P-delta is in)."""
    import openseespy.opensees as ops
    import engine3d as E
    out = {"method": "IS 800:2007 4.6.2(b) rational analysis: lambda_cr = AF / (AF - 1), AF = second-order / "
                     "first-order sway of the stepped P-Delta model under %.1fDL + %.1fLL with a %.1f %% lateral "
                     "perturbation (three solutions: H alone, gravity alone, gravity + H)" % (fD, fL, 100 * ratio),
           "cite": "IS 800:2007 4.6.1 / 4.6.2(b); Annex B-2.1"}

    def _solve(d, grav, lat):
        info = E.build(cfg, "PDelta")
        NF = info["NF"]
        ops.timeSeries("Linear", 1)
        ops.pattern("Plain", 1, 1)
        if grav:
            E._apply_nodal_gravity(cfg, info, fD, fL)
        if lat:
            for k in range(1, NF + 1):
                W = E.floor_w(cfg, k) * (fD + fL) / 2.0
                v = [0.0] * 6
                v[0 if d == "X" else 1] = ratio * W
                ops.load(E.mtag(k), *v)
        ops.constraints("Transformation"); ops.numberer("RCM"); ops.system("UmfPack")
        ops.test("NormDispIncr", 1e-9, 200); ops.algorithm("Newton")
        ops.integrator("LoadControl", 0.1); ops.analysis("Static")
        if ops.analyze(10) != 0:
            return None
        tops = [E.ntag(i, j, NF) for (i, j) in info["present"][NF]]
        return {n: ops.nodeDisp(n, 1 if d == "X" else 2) for n in tops}

    for d in ("X", "Y"):
        A, B, C = _solve(d, False, True), _solve(d, True, False), _solve(d, True, True)
        if A is None or B is None or C is None:
            out[d] = {"found": False, "note": "analysis did not converge"}
            continue
        best = None
        for n, d1 in A.items():
            if abs(d1) < 1e-6:
                continue
            af = (C[n] - B[n]) / d1
            if best is None or af > best[0]:
                best = (af, n, d1, C[n] - B[n])
        if best is None:
            out[d] = {"found": False, "note": "no sway"}
            continue
        af = best[0]
        lam = af / (af - 1.0) if af > 1.0 + 1e-9 else None
        out[d] = {"found": True, "AF": round(af, 4), "lambda_cr": round(lam, 2) if lam else None,
                  "node": best[1], "d_first_mm": round(best[2], 4), "d_second_mm": round(best[3], 4)}
    rows = []
    for d in ("X", "Y"):
        r = out.get(d) or {}
        if r.get("found"):
            lam = r["lambda_cr"] if r["lambda_cr"] is not None else 1e9
            rows.append(_row("elastic buckling load factor lambda_cr (%s sway): required 5 / provided" % d, 5.0, lam,
                             clause="IS 800:2007 4.6.2(b); Annex B-2.1",
                             cite="lambda_cr = %.2f > 5: the change in member stiffness due to axial force may be "
                                  "neglected (B-2.1); every combination is solved second-order (P-Delta, 4.4.3) in any "
                                  "case" % lam, lambda_cr=lam))
    out["checks"] = rows
    return out


# ------------------------------------------------------------------------------------------- tonnage
def element_mass_kg(sec, L_mm):
    try:
        A = float(E_Ipack(sec)[0])
    except Exception:
        A = float(S.props(sec)["A"])
    return A * L_mm * 7.85e-6


def E_Ipack(sec):
    import engine3d as E
    return E.Ipack(sec)


def tonnage(cfg, info, length, role_of, peb=None):
    """Steel take-off of the analysis model: {group: kg} + plan area + kg/m2.  Groups: primary (frame columns and
    rafters incl. the gable frames), bracing (braces, eave struts and the declared roof-bracing struts), crane
    (gantry girders: cfg['peb_mass_groups']['crane'] element tags / sections; brackets: a secondary_members record
    with 'group': 'crane'), canopy
    (cfg['peb_mass_groups']['canopy'], and by default the peb_build canopy members), secondary (cfg['peb_secondary'] records: purlins, girts, sag rods ...)."""
    mg = (cfg or {}).get("peb_mass_groups") or {}
    out = {"primary": 0.0, "bracing": 0.0, "crane": 0.0, "canopy": 0.0, "secondary": 0.0, "connections": 0.0}
    by_el = {}
    for (t, kind, sec, n1, n2) in info["ele"]:
        L = length.get(t, 0.0)
        kg = element_mass_kg(sec, L)
        grp = None
        for g, sel in mg.items():
            if g == "secondary":
                continue
            tags = set(sel.get("tags") or []) if isinstance(sel, dict) else set()
            secs = set(sel.get("sections") or []) if isinstance(sel, dict) else set()
            if t in tags or sec in secs:
                grp = g
                break
        if grp is None and peb:
            try:
                import peb_build as _PB
                if (_PB.member_of(t) or {}).get("kind") == "canopy":
                    grp = "canopy"                 # PEB canopy cantilevers (peb_build.beam kind 'canopy')
            except Exception:
                pass
        if grp is None:
            if kind == "brace":
                grp = "bracing"
            elif kind == "beam" and not (peb and t in (peb.get("elements") or {})):
                grp = "bracing"                    # eave struts, collectors
            else:
                grp = "primary"
        out[grp] = out.get(grp, 0.0) + kg
        by_el[t] = (grp, kg)
    for s_ in (cfg.get("secondary_members") or []):
        if s_.get("kind") == "strut" and s_.get("mass_kg") is not None:
            g_ = s_.get("group") or "bracing"     # e.g. 'crane' for the crane brackets of a crane shed
            out[g_] = out.get(g_, 0.0) + float(s_["mass_kg"])
    for r in (cfg.get("peb_secondary") or []):
        out[r.get("group", "secondary")] = out.get(r.get("group", "secondary"), 0.0) + float(r.get("mass_kg") or 0.0)
    out["connections"] += float((cfg.get("peb_connection_mass_kg") or 0.0))
    import roof_geometry as RG
    area = sum(RG.plane_area_mm2(pl) for pl in RG.planes(cfg)) / 1e6 if RG.has_planes(cfg) else None
    area = float(cfg.get("plan_area_m2") or area or 0.0)
    tot = sum(v for k, v in out.items())
    res = {"kg": {k: round(v, 1) for k, v in out.items()}, "total_kg": round(tot, 1), "plan_area_m2": round(area, 1)}
    if area:
        res["kg_per_m2"] = {k: round(v / area, 2) for k, v in out.items()}
        res["kg_per_m2"]["total"] = round(tot / area, 2)
    res["basis"] = ("analysis-model members by group (element mass = A L 7850 kg/m3; stepped segments at their own "
                    "depth) + declared secondary records (cfg['peb_secondary']) + connection plates "
                    "(cfg['peb_connection_mass_kg'])")
    res["by_element"] = {str(t): {"group": g, "kg": round(kg, 2)} for t, (g, kg) in by_el.items()}
    return res


# ------------------------------------------------------------------------------------------- knee joints
def _is18_smf(cfg, s12_cfg, system):
    """IS 18168 route applies to the moment frame of this job (SMRF): (applies, Ry function)."""
    import india_is800_s12 as S12
    for sysn in [(cfg or {}).get("system_y"), (cfg or {}).get("system_x"), system]:
        if not sysn:
            continue
        try:
            if S12.normalize_system(sysn) == "SMF" and S12.is18168_status(sysn, s12_cfg or cfg or {})["applies"]:
                return True
        except Exception:
            continue
    return False


def knee_records(cfg, peb, joints, reg, envt, system=None, s12_cfg=None):
    """PEB knee (rafter end plate on the column flange) -- the column side of the joint under the factored knee
    moment (IS 800 general design; the SMRF 12.11.2.3 panel check at 1.2 Mp stays in india_is800_s12):
      * panel shear: Vp = M / (d_b - t_fb) - V_col <= web shear (8.4, with 8.4.2.2(a) buckling, panel d_c x tw_c)
        + diagonal stiffener pair A_st fy / gamma_m0 cos(theta), theta = atan(d_b / d_c) (cfg['connections']
        ['knee_panel'] = {'diagonal_stiffener': {'b_mm', 't_mm', 'n', 'fy_MPa'}, 'doubler_t_mm'});
      * compression / tension stiffeners at the rafter flange levels: F = M / (d_b - t_fb) <= (A_st + tw_c (t_fb +
        5 (t_fc + s))) fy / gamma_m0 (8.7.4 web bearing length with the declared horizontal stiffener pair,
        'flange_stiffener': {'b_mm', 't_mm', 'n', 'fy_MPa'}).
    One record per knee section pair (worst knee)."""
    import india_is800 as I8
    import peb_build as PB
    spec = ((cfg or {}).get("connections") or {}).get("knee_panel") or {}
    worst = {}
    for j in joints or []:
        nd = j.get("node")
        cols = [c for c in (j.get("columns") or []) if c.get("position") == "below"]
        beams = j.get("beams") or []
        if not cols or not beams:
            continue
        tc = int(str(cols[0]["member_id"]).lstrip("e"))
        tb = int(str(beams[0]["member_id"]).lstrip("e"))
        if not PB.element(tc) or not PB.element(tb):
            continue
        csec = cols[0].get("face_section") or reg[tc][1]
        bsec = beams[0].get("face_section") or reg[tb][1]
        pc, pb = S.props(csec), S.props(bsec)
        Mk, Vc, lab_k = 0.0, 0.0, None
        endb = "i" if reg[tb][2] == nd else "j"
        for lab, r in (envt[tb].get("records") or {}).items():
            r = list(r) + [0.0] * 13
            M = abs(r[4] if endb == "i" else r[5])
            if M > Mk:
                Mk, lab_k = M, lab
                rc = list((envt[tc].get("records") or {}).get(lab) or []) + [0.0] * 13
                Vc = abs(rc[9] or rc[3])
        key = (csec, bsec)
        if key in worst and worst[key][0] >= Mk:
            continue
        worst[key] = (Mk, Vc, lab_k, nd, csec, bsec, pc, pb)
    out = []
    is18 = _is18_smf(cfg, s12_cfg, system)
    bc = (((cfg or {}).get("connections") or {}).get("beam_column") or {})
    for key, (Mk, Vc, lab_k, nd, csec, bsec, pc, pb) in worst.items():
        fyc = _fy_plate(csec, cfg)
        lever = pb["d"] - pb["tf"]
        kspec = bc.get(bsec) or bc.get("default") or {}
        kep = kspec.get("end_plate") or {}
        # the connection demand at the knee: owner ruling D-T7, 1.2 Mp of the face section in either sign (IS 800
        # 12.10.2.1 / 12.11.2.1); under IS 18168 (route B, SMRF) 8.4: 1.1 Ry fy Zpb
        Mp_f = _mp(bsec, cfg)
        if is18:
            import india_is800_s12 as S12
            ry, ry_note = S12._ry({"grade": ((cfg or {}).get("grade_by_section") or {}).get(bsec)
                                   or (cfg or {}).get("steel_grade")}, pb)
            fac, dem_basis = 1.1 * ry, "IS 18168:2023 8.4: 1.1 Ry fy Zpb (%s) = %.0f kN-m" % (ry_note, 1.1 * ry * Mp_f / 1e6)
            dem_clause = "IS 18168:2023 8.4 (route B, owner ruling D-T2); owner ruling D-T7"
        else:
            fac, dem_basis = 1.2, "owner ruling D-T7: 1.2 Mp(%s) = %.0f kN-m" % (bsec, 1.2 * Mp_f / 1e6)
            dem_clause = "IS 800:2007 12.10.2.1 / 12.11.2.1 (owner ruling D-T7)"
        Mconn = fac * Mp_f if kep.get("rows") else 0.0
        F = Mk / lever
        Vp = F - Vc
        # the panel is a web field bounded by the stiffeners at both rafter flange levels: c = d_b (8.4.2.2, Kv)
        sh = I8.shear_capacity(csec, fyc, axis="z", welded=True, stiffener_spacing_mm=pb["d"])
        Vweb = sh.get("Vd_N") or 0.0
        ds = spec.get("diagonal_stiffener") or {}
        theta = math.atan2(pb["d"], pc["d"])
        A_d = float(ds.get("n", 2)) * float(ds.get("b_mm", 0.0)) * float(ds.get("t_mm", 0.0))
        fy_d = float(ds.get("fy_MPa", 250.0))
        V_d = A_d * fy_d / 1.10 * math.cos(theta)
        dbl = float(spec.get("doubler_t_mm") or 0.0)
        V_dbl = (pc["d"] - 2 * pc["tf"]) * dbl * 250.0 / (math.sqrt(3.0) * 1.10)
        rows = [_row("knee panel shear (column web, stiffened field + diagonal stiffener%s)" % (" + doubler" if dbl else ""),
                     Vp, Vweb + V_d + V_dbl, clause="IS 800:2007 8.4 / 8.4.2.2(a); 8.7 (stiffeners)",
                     cite="Vp = M/(d_b - t_fb) - V_col = %.0f kN (M %.1f kN-m, %s; the factored knee moment: IS 800 "
                          "12.10 sets no panel demand for an OMF; the SMF panel at 1.2 Mp is IS 800 12.11.2.3 in "
                          "Section 12); web Vd %.0f kN + diagonal stiffener %.0f mm2 x %.0f / 1.10 x cos %.0f deg = "
                          "%.0f kN" % (Vp / 1e3, Mk / 1e6, lab_k, Vweb / 1e3, A_d, fy_d, math.degrees(theta),
                                       V_d / 1e3))]
        # column web stiffeners at the rafter flange levels: they carry the flange force of the connection moment
        # (the stiffeners are part of the joint that develops Mconn), not only the analysis moment
        fs_ = spec.get("flange_stiffener") or {}
        A_f = float(fs_.get("n", 2)) * float(fs_.get("b_mm", 0.0)) * float(fs_.get("t_mm", 0.0))
        fy_f = float(fs_.get("fy_MPa", 250.0))
        t_cfl = float(kspec.get("column_flange_t_mm") or pc["tf"])
        tw_c = float(pc["tw"]) + dbl
        b_web = pb["tf"] + 5.0 * (t_cfl + float(spec.get("weld_mm", 6.0)))
        cap_f = (A_f * fy_f + tw_c * b_web * fyc) / 1.10
        M_st = max(Mk, Mconn)
        F_st = M_st / lever
        rows.append(_row("column stiffeners at the rafter flange levels (flange force)", F_st, cap_f,
                         clause="IS 800:2007 8.7.4 / 8.7.1" + ("; " + dem_clause if Mconn > Mk else ""),
                         cite="F = M/(d_b - t_fb) = %.0f kN (M %.1f kN-m: %s); stiffener pair %.0f mm2 x %.0f + the "
                              "column web over the bearing length b = t_fb + 5 (t_fc + s) = %.0f with thickness t = "
                              "%.1f%s, x %.0f (/1.10)"
                              % (F_st / 1e3, M_st / 1e6, dem_basis if Mconn > Mk else "the factored knee moment, %s"
                                 % lab_k, A_f, fy_f, b_web, tw_c, " (incl. the doubler)" if dbl else "", fyc)))
        if not ds:
            rows.append(_row("diagonal stiffener declared", None, None, clause="IS 800:2007 8.7", cite="knee panel",
                             ok=None, reason="cfg['connections']['knee_panel'] not declared"))
        if kep.get("rows"):
            # the end plate in both signs at the connection demand (the primary sign under IS 800 alone is also the
            # 12.10.2.1 / 12.11.2.1 row of capacity_design)
            sym = bool(kspec.get("symmetric"))
            lay = end_plate_layout(kep, bsec, symmetric=sym)
            cap_p = (end_plate_capacity(kep, cfg) or {}).get("capacity_Nmm")
            if sym:
                cap_r = cap_p
            else:
                cap_r = (end_plate_capacity(kep, cfg, rows=lay["reverse_rows"]) or {}).get("capacity_Nmm") \
                    if lay["reverse_rows"] else None
            cap_ep = min(c_ for c_ in (cap_p, cap_r) if c_) if (cap_p and cap_r) else None
            rows.append(_row("knee end plate, both signs (%s)" % ("IS 18168 8.4: 1.1 Ry Mp" if is18 else
                                                                  "D-T7: 1.2 Mp of the face section"),
                             Mconn, cap_ep, clause=dem_clause + "; IS 800:2007 10.3.5 / 10.4.7",
                             cite="%s bolt pattern, %d M%d %s flange bolts; %s" % (
                                 "symmetric" if sym else "one-sided", lay["n_bolts"], int(kep.get("d_mm") or 0),
                                 kep.get("grade"), dem_basis),
                             **({} if cap_ep else {"dc": 99.0, "ok": False,
                                                   "reason": "no bolt row on the tension side for the reverse sign"})))
            # the column flange is the other plate the bolts pull on: the same rows and bolts, IS 800 10.4.7 / 8.2.1.2
            # with the column flange as the T-stub flange (t = the declared knee-zone flange plate, else the
            # column's own flange); lv from the declared gauge to the column web weld toe; the rows inside the rafter
            # flanges are fed through the column web (strip be x (tw + doubler) in tension, IS 800 6.2)
            t_cf = t_cfl
            g_cf = kspec.get("gauge_mm")
            lv_cf = float(kspec.get("column_flange_lv_mm")
                          or ((float(g_cf) / 2.0 - pc["tw"] / 2.0 - float(kspec.get("column_weld_mm", 8.0)))
                              if g_cf else kep.get("lv_mm")))
            grade_c = (kspec.get("column_flange_grade") or ((cfg or {}).get("grade_by_section") or {}).get(csec)
                       or (cfg or {}).get("steel_grade"))
            cf = dict(kep, t_plate_mm=t_cf, fy_plate_MPa=_fy_plate(csec, cfg), lv_mm=lv_cf, plate_grade=grade_c,
                      web_t_mm=tw_c, web_fy_MPa=fyc, hf_mm=lay["hf_mm"])
            caps_cf = [(end_plate_capacity(cf, cfg) or {}).get("capacity_Nmm")]
            if not sym and lay["reverse_rows"]:
                caps_cf.append((end_plate_capacity(cf, cfg, rows=lay["reverse_rows"]) or {}).get("capacity_Nmm"))
            caps_cf = [c_ for c_ in caps_cf if c_]
            cap_cf = min(caps_cf) if caps_cf else None
            rows.append(_row("column flange at the end-plate bolt rows (T-stub flange and column web, both signs)",
                             Mconn, cap_cf,
                             clause="IS 800:2007 10.4.7 (prying) / 8.2.1.2 (column flange strip) / 6.2 (web strip); "
                                    + dem_clause,
                             cite="column %s flange %s mm (%s), lv %.1f mm, be %.0f mm, column web thickness with "
                                  "its doubler %.1f; the end-plate rows and %d M%d %s; %s" % (
                                      csec, ("%.0f knee-zone plate" % t_cf) if kspec.get("column_flange_t_mm") else
                                      "%.0f" % t_cf, grade_c, lv_cf, float(kep.get("be_mm") or 0.0), tw_c,
                                      lay["n_bolts"], int(kep.get("d_mm") or 0), kep.get("grade"), dem_basis)))
        strength = [r_ for r_ in rows if isinstance(r_.get("dc"), (int, float)) and not r_.get("gate")]
        gov = max(strength, key=lambda r_: r_["dc"]) if strength else None
        DC = None if any(r_.get("ok") is None for r_ in rows) else (gov["dc"] if gov else None)
        out.append({"id": "conn-peb-knee-%s-%s" % (csec, bsec), "type": "PEB knee: column panel and stiffeners",
                    "section": "%s / %s" % (csec, bsec), "node": nd,
                    "demand": {"M_knee_Nmm": round(Mk, 1), "V_col_N": round(Vc, 1), "combo": lab_k,
                               "V_panel_N": round(Vp, 1), "F_flange_N": round(F, 1)},
                    "inputs": {"V_N": round(Vp, 1)}, "checks": rows, "DC": DC,
                    "governing_check": gov.get("name") if gov else None, "clause": gov.get("clause") if gov else None,
                    "design_basis": "factored knee moment (IS 800 Table 4 combinations); declared stiffeners",
                    "limit_state": "IS 800:2007 8.4 / 8.7", "cited": "IS 800:2007 8.4 / 8.7", "notes": []})
    return out
