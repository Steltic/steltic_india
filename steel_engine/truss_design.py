"""truss_design.py -- MSME (2026-10): pin-jointed angle roof trusses on columns (IN_Ex21 angle-truss MSME shed).

Model (custom_build):
  * chords: continuous members through the panel points (kind 'beam', engine3d.add_beam), registered with
    engine3d.register_truss_member(tag, group='top_chord' | 'bottom_chord', truss=<id>); the top chord lies on a
    declared roof plane with 'purlins_at_nodes': True (the purlin reactions reach the chord at the panel points);
  * webs and knee braces: pin-ended truss members (kind 'truss', engine3d.add_truss, group 'vertical' | 'diagonal' |
    'knee_brace' | ...), axial force only;
  * the heel (truss seat on the column cap) pinned: the chord ends at the column top released about both axes;
  * knee braces from a column station to a bottom-chord panel point make the column + truss a portal frame
    (info['truss_knees'], Section 12.10 below).
The design role of a registered member is 'truss_<group>' (design_pipeline).

cfg['truss_connections'] = {key: spec}, key '<role>:<SECTION>' | '<role>' | 'default' (most specific wins), spec =
  {'n_bolts': >= 2, 'd_mm', 'grade' (bolt property class '4.6' | '8.8'), 'd0_mm' (hole, Table 19),
   'pitch_mm', 'end_mm' (end distance in the member), 'gauge_mm' (back of the angle to the bolt line),
   'gusset_t_mm', 'gusset_grade' ('E250'), 'edge' ('rolled' | 'sheared', 10.2.4.2), 'fixity' ('hinged' | 'fixed',
   Table 12, single angles), 'gusset_edge_mm' (bolt to the gusset edge), 'packing_t_mm' (back-to-back packs)}
cfg['truss_connections']['heel'] = the truss seat: {'n_bolts', 'd_mm', 'grade', 'd0_mm', 'pitch_mm', 'end_mm',
   't_plate_mm' (bearing plate: the thinner of the seat / gusset), 'fu_plate_MPa', 'nn', 'ns'}.

Clauses (IS 800:2007, corpus text): 6.2, 6.3.3 / 6.3.4, 6.4.1 (member ends -- india_is800.axial_member_check_is800 /
angle_end_connection_inputs); 7.2.4 / 7.5.1.2 / 7.5.2.1 / 7.5.3 (compression); 7.8.1 / 7.8.2 (back-to-back
interconnection); 10.2.2 / 10.2.3.2 / 10.2.4.2 (spacing, end and edge distances); 10.3.2-10.3.4 (bolts in shear and
bearing); 12.10.2.1 / 12.10.2.4 (OMF connections, applied to the knee: see knee_checks).  The gusset yield on the
Whitmore width is engineering practice (india_connections.whitmore_section), stated as such.
"""
from __future__ import annotations

import math

import india_connections as C
import india_is800 as I8
import sections as S

SRC = "steel_engine/truss_design.py"
CHORD_GROUPS = ("top_chord", "bottom_chord")


# ------------------------------------------------------------------------------------------------ specs
def role_of(group):
    return "truss_%s" % group


def is_truss_role(role):
    return str(role or "").startswith("truss_")


def is_chord_role(role):
    return str(role or "") in tuple(role_of(g) for g in CHORD_GROUPS)


def spec_for(cfg, role, sec=None):
    """The declared connection spec of a truss member end ('<role>:<SEC>' > '<role>' > 'default'), merged field by
    field (the more specific key wins); None when nothing is declared."""
    tc = (cfg or {}).get("truss_connections") or {}
    out, used = {}, []
    for k in ("default", str(role), "%s:%s" % (role, sec)):
        v = tc.get(k)
        if isinstance(v, dict):
            out.update(v)
            used.append(k)
    if not used:
        return None
    out["_keys"] = used
    return out


def _fy_fu(grade, t_mm):
    m = I8.is2062_properties(grade or "E250", t_mm)
    return m.get("fy_MPa"), m.get("fu_MPa")


def is_angle_section(sec):
    """True for a single IS 808 angle or a double angle (the sections the truss end-connection model covers)."""
    try:
        return S.props(sec).get("section_type") in ("angle", "double_angle")
    except Exception:
        return False


def member_inputs(cfg, role, sec, L_mm=None):
    """(angle_connection, tension_inputs, record) for the IS 800 check of a truss member of `sec` with the declared end
    connection; (None, None, {'error': ...}) when the spec is missing or incomplete.  A section other than an angle or
    a double angle (a CHS web or knee brace, review 2026-11) gets (None, None, {'general_member_check': True, ...}):
    its member is checked by the general member check and its end connection is not covered here."""
    if not is_angle_section(sec):
        return None, None, {"general_member_check": True,
                            "note": "%s is not an angle: general IS 800 member check; the truss end-connection model "
                                    "covers angles only" % sec}
    sp = spec_for(cfg, role, sec)
    if not sp:
        return None, None, {"error": "cfg['truss_connections'] has no spec for %s (%s)" % (role, sec)}
    need = ("n_bolts", "d0_mm", "pitch_mm", "end_mm", "gauge_mm")
    miss = [k for k in need if sp.get(k) is None]
    if miss:
        return None, None, {"error": "truss connection spec for %s %s misses %s" % (role, sec, miss)}
    p = S.props(sec)
    ti, rec = I8.angle_end_connection_inputs(p, n_bolts=sp["n_bolts"], d0_mm=sp["d0_mm"], pitch_mm=sp["pitch_mm"],
                                             end_mm=sp["end_mm"], gauge_mm=sp["gauge_mm"])
    # the bolts at each end: 7.5.1.2 (Table 12) for a single angle, the 7.5.2.1 / 7.5.2.2 condition for a double angle
    ac = {"n_bolts": int(sp["n_bolts"]), "fixity": sp.get("fixity", "hinged")}
    if L_mm:
        ac["l_mm"] = float(L_mm)
    rec["spec_keys"] = sp.get("_keys")
    return ac, ti, rec


# ------------------------------------------------------------------------------------------------ end connections
def bolt_group(sp, sec):
    """Bolt group of one member end (10.3.2-10.3.4): a double angle on opposite sides of the gusset puts every bolt in
    double shear (two shear planes, threads assumed in both: nn = 2) and in bearing on the gusset (t_g) or on the two
    angle legs (2 t), whichever governs; a single angle: single shear, bearing on min(t, t_g).  kb from the end
    distance in the member (e), the pitch (p), d0 and fub / fu (10.3.4).  Returns the group record."""
    p = S.props(sec)
    double = p.get("section_type") == "double_angle"
    t = float(p.get("t_mm") or p.get("tw"))
    tg = float(sp.get("gusset_t_mm") or 0.0)
    fy_a, fu_a = _fy_fu(sp.get("member_grade") or "E250", t)
    fy_g, fu_g = _fy_fu(sp.get("gusset_grade") or "E250", tg) if tg else (None, None)
    nn = 2 if double else 1
    base = dict(nn=nn, ns=0, d0_mm=sp["d0_mm"], p_mm=sp["pitch_mm"], e_mm=sp["end_mm"])
    lj = (int(sp["n_bolts"]) - 1) * float(sp["pitch_mm"])
    if lj > 0:
        base["lj_mm"] = lj
    ga = C.bolt_group_capacity_is800(int(sp["n_bolts"]), sp["d_mm"], sp.get("grade", "4.6"),
                                     t_mm=(2.0 * t if double else t), fu_plate_MPa=fu_a, **base)
    gg = None
    if tg:
        gb = dict(base, e_mm=sp.get("gusset_end_mm") or sp["end_mm"])
        gg = C.bolt_group_capacity_is800(int(sp["n_bolts"]), sp["d_mm"], sp.get("grade", "4.6"),
                                         t_mm=tg, fu_plate_MPa=fu_g, **gb)
    caps = [g for g in (ga, gg) if g and g.get("found")]
    if not caps or (tg and not (gg and gg.get("found"))):
        return {"found": False, "capacity_N": None, "angle_side": ga, "gusset_side": gg,
                "reason": "bolt group not evaluated (inputs)"}
    gov = min(caps, key=lambda g: g["capacity_N"])
    return {"found": True, "capacity_N": gov["capacity_N"], "governs": "gusset" if gov is gg else "angle",
            "angle_side": ga, "gusset_side": gg, "double_shear": double, "fu_angle_MPa": fu_a, "fu_gusset_MPa": fu_g,
            "fy_gusset_MPa": fy_g, "t_angle_mm": t, "t_gusset_mm": tg}


# 10.2.4.2: 1.7 d0 for sheared or hand-flame cut edges, 1.5 d0 for rolled, machine-flame cut, sawn and planed edges
_CUT_15 = ("rolled", "machine", "sawn", "planed")


def _k_edge(kind):
    return 1.5 if str(kind or "").lower().startswith(_CUT_15) else 1.7


def detailing_rows(sp, sec, *, compression, L_mm=None):
    """Bolt spacing / end / edge distances (10.2.2, 10.2.3.2, 10.2.4.2) and the >= 2 bolts of a double angle strut
    (7.5.2.1) as check rows (value, limit, dc, ok).  Review 2026-11: the end distance uses the cut of the angle END
    (spec 'end_cut': 'sheared' (default, 1.7 d0) | 'sawn' | 'machine_flame_cut' | 'planed' (1.5 d0)); the toe edge
    is rolled (spec 'edge', default 'rolled', 1.5 d0); the 10.2.3.2 pitch limit uses the thinner of the angle and the
    gusset."""
    p = S.props(sec)
    d, d0 = float(sp["d_mm"]), float(sp["d0_mm"])
    t = float(p.get("t_mm") or p.get("tw"))
    tg = float(sp.get("gusset_t_mm") or 0.0)
    t_thin = min(t, tg) if tg else t
    leg = float(p.get("leg_connected_mm") or p.get("d"))
    k_edge = _k_edge(sp.get("edge") or "rolled")
    end_cut = sp.get("end_cut") or "sheared"
    k_end = _k_edge(end_cut)
    rows = []
    n = int(sp["n_bolts"])
    if n >= 2:
        rows.append(("bolt pitch >= 2.5 d (10.2.2)", C._check(2.5 * d, float(sp["pitch_mm"]),
                     clause="IS 800:2007 10.2.2", cite="minimum spacing 2.5 d = %.0f mm, pitch %.0f mm"
                     % (2.5 * d, float(sp["pitch_mm"])))))
        pmax = min((12.0 if compression else 16.0) * t_thin, 200.0)
        rows.append(("bolt pitch <= %s (10.2.3.2)" % ("12t / 200" if compression else "16t / 200"),
                     C._check(float(sp["pitch_mm"]), pmax, clause="IS 800:2007 10.2.3.2",
                              cite="pitch %.0f <= %.0f mm in a %s member (t = %.0f mm, the thinner of the angle and "
                                   "the gusset)" % (float(sp["pitch_mm"]), pmax,
                                                    "compression" if compression else "tension", t_thin))))
    rows.append(("end distance >= %.1f d0 (10.2.4.2, %s end)" % (k_end, str(end_cut).replace("_", " ")),
                 C._check(k_end * d0, float(sp["end_mm"]), clause="IS 800:2007 10.2.4.2",
                          cite="end distance %.0f mm >= %.1f x %.0f (%s angle end)"
                               % (float(sp["end_mm"]), k_end, d0, str(end_cut).replace("_", " ")))))
    edge = leg - float(sp["gauge_mm"])
    rows.append(("edge distance (bolt line to the toe) >= %.1f d0 (10.2.4.2)" % k_edge,
                 C._check(k_edge * d0, edge, clause="IS 800:2007 10.2.4.2",
                          cite="leg %.0f - gauge %.0f = %.0f mm >= %.1f x %.0f" % (leg, float(sp["gauge_mm"]), edge,
                                                                                 k_edge, d0))))
    if p.get("section_type") == "double_angle":
        rows.append(("double angle strut: >= 2 bolts in line at each end (7.5.2.1)",
                     C._check(2.0, float(n), clause="IS 800:2007 7.5.2.1 / 7.8.2",
                              cite="%d bolts in line along the angles at each end" % n)))
    return rows


def stitch_record(sec, *, L_mm, KL_over_r_member=None, compression=True):
    """Back-to-back interconnection of a double angle member (7.8.1 / 7.8.2 compression; 10.2.5.4 tension): the
    largest spacing s so that the component slenderness s / r_min,1 <= min(40, 0.6 KL/r of the member), at least two
    intermediate connections in a compression member; tension members at <= 1000 mm.  Returns the record (number of
    intermediate connections, spacing, ratio) with a check row."""
    p = S.props(sec)
    if p.get("section_type") != "double_angle":
        return None
    r1 = float(p["r1_min_mm"])
    L = float(L_mm)
    if compression:
        lim = min(40.0, 0.6 * float(KL_over_r_member)) if KL_over_r_member else 40.0
        # review 2026-11: 10.2.5.5 -- tacking fasteners of a compression member in a line at <= 600 mm
        s_max = min(lim * r1, 600.0)
        n_int = max(2, int(math.ceil(L / s_max)) - 1)
        s = L / (n_int + 1)
        chk = C._check(s, s_max, clause="IS 800:2007 7.8.1 / 7.8.2 / 10.2.5.5",
                       cite="interconnections at %.0f mm <= min(min(40, 0.6 x %.0f) x r_min %.1f = %.0f, 600) mm "
                            "(component slenderness s / r_min = %.0f)"
                            % (s, KL_over_r_member or 0.0, r1, lim * r1, s / r1))
    else:
        s_max = 1000.0
        n_int = max(0, int(math.ceil(L / s_max)) - 1)
        s = L / (n_int + 1)
        chk = C._check(s, s_max, clause="IS 800:2007 10.2.5.4",
                       cite="tension member: interconnections at %.0f mm <= 1000 mm" % s)
    return {"n_intermediate": n_int, "spacing_mm": round(s, 0), "r1_min_mm": r1, "check": chk}


def stitch_bolt_check(sec, d_mm):
    """IS 800 7.8.4: the bolts of the back-to-back connections not less than 16 mm diameter for members up to and
    including 10 mm thick, 20 mm up to 16 mm, 22 mm over 16 mm."""
    p = S.props(sec)
    t = float(p.get("t_mm") or p.get("tw"))
    dmin = 16.0 if t <= 10.0 else (20.0 if t <= 16.0 else 22.0)
    return C._check(dmin, float(d_mm), clause="IS 800:2007 7.8.4",
                    cite="interconnection bolts M%d >= %.0f mm for %.0f mm thick angles" % (int(d_mm), dmin, t))


# review 2026-11: gusset buckling K by the support of the gusset edges (engineering practice, outside the corpus; the
# engine's brace-gusset rule, india_connections.whitmore_buckling): 0.65 for a compact gusset held on two edges
# (Thornton), 1.2 for a gusset held on one edge only, whose free end can sway (the knee gusset on the column, a
# panel-point gusset below / above the chord with a free edge).  A declared K below the support's value is raised.
GUSSET_K_BY_SUPPORT = {"two_edges": 0.65, "one_edge": 1.2}
GUSSET_SUPPORT_TEXT = {"two_edges": "gusset held on two edges: K 0.65",
                       "one_edge": "gusset held on one edge, free end can sway: K 1.2"}


def gusset_K(sp):
    """The gusset buckling K from the declared support ('gusset_support': 'one_edge' | 'two_edges') and / or K."""
    sup = sp.get("gusset_support")
    K = sp.get("gusset_K")
    if sup in GUSSET_K_BY_SUPPORT:
        k0 = GUSSET_K_BY_SUPPORT[sup]
        return k0 if K is None else max(float(K), k0)
    return None if K is None else float(K)


def gusset_rows(sp, N_N, N_comp_N=0.0, *, label="gusset"):
    """Gusset checks at one member end for the force N_N (both directions) and, when the member can be in compression,
    N_comp_N: [(name, check)].  Whitmore yield (bw = 2 L tan30 from a single bolt line, yield on bw t_g, engineering
    practice); block shear of the gusset (IS 800 6.4.1, one bolt line: shear along the line over gusset_end_mm +
    (n - 1) p, tension to the gusset edge gusset_edge_mm); gusset buckling on the Whitmore width (7.1.2 class c,
    K gusset_K over gusset_free_mm -- the free length to the nearest supported edge; engineering practice, as for brace
    gussets 12.7.3.4).  Missing declared inputs leave a row not evaluated."""
    rows = []
    tg = float(sp.get("gusset_t_mm") or 0.0)
    if not tg:
        return rows
    n = int(sp["n_bolts"])
    fy_g, fu_g = _fy_fu(sp.get("gusset_grade") or "E250", tg)
    Lc = (n - 1) * float(sp["pitch_mm"])
    # review 2026-11: the Whitmore width is capped by the gusset's declared width across the bolt line (its outline)
    wcap = sp.get("gusset_width_mm")
    wm = C.whitmore_section(t_gusset_mm=tg, fy_MPa=fy_g, w_start_mm=0.0, L_conn_mm=Lc, demand_N=N_N,
                            available_width_mm=float(wcap) if wcap else None)
    if wm.get("found"):
        capped = bool(wcap) and wm["whitmore_width_mm"] < 2.0 * Lc * math.tan(math.radians(30.0)) - 1e-6
        rows.append(("%s yield on the Whitmore width %.0f mm%s (engineering practice)"
                     % (label, wm["whitmore_width_mm"], " (the gusset width)" if capped else ""), dict(wm["check"])))
    e_g, edge_g = sp.get("gusset_end_mm") or sp.get("end_mm"), sp.get("gusset_edge_mm")
    if edge_g is None:
        rows.append(("%s block shear (6.4.1)" % label, {"ok": None, "clause": "IS 800:2007 6.4.1",
                                                         "reason": "gusset_edge_mm (bolt line to the gusset edge) not "
                                                                   "declared"}))
    else:
        ar = C.block_shear_bolted_areas(t_mm=tg, n_rows=n, pitch_mm=float(sp["pitch_mm"]), end_mm=float(e_g),
                                        d0_mm=float(sp["d0_mm"]), edge_mm=float(edge_g), n_lines=1, pattern="L")
        bs = C.block_shear(Avg_mm2=ar["Avg_mm2"], Avn_mm2=ar["Avn_mm2"], Atg_mm2=ar["Atg_mm2"], Atn_mm2=ar["Atn_mm2"],
                           fy_MPa=fy_g, fu_MPa=fu_g, demand_N=N_N)
        if bs.get("found"):
            c = dict(bs["check"])
            c["cite"] = ("gusset %.0f mm: one bolt line, shear over %.0f + %.0f mm, tension to the edge %.0f mm: "
                         "Tdb = %.1f kN" % (tg, float(e_g), Lc, float(edge_g), bs["Tdb_N"] / 1e3))
            rows.append(("%s block shear (6.4.1)" % label, c))
    if N_comp_N and N_comp_N > 0 and wm.get("found"):
        K, Lf = gusset_K(sp), sp.get("gusset_free_mm")
        if K is None or Lf is None:
            rows.append(("%s buckling on the Whitmore width" % label,
                         {"ok": None, "clause": "IS 800:2007 7.1.2",
                          "reason": "gusset_support (or gusset_K) and gusset_free_mm (free length to the nearest "
                                    "supported edge) not declared"}))
        else:
            gb = C.whitmore_buckling(whitmore_width_mm=wm["whitmore_width_mm"], t_gusset_mm=tg, fy_MPa=fy_g,
                                     L_unbraced_mm=float(Lf), K=float(K), demand_N=N_comp_N)
            if gb.get("found") and gb.get("check"):
                c = dict(gb["check"])
                c["cite"] = ("gusset %.0f mm on the Whitmore width %.0f mm, K %.2f over %.0f mm (%s), 7.1.2 class c "
                             "(engineering practice): Pd = %.1f kN" % (tg, wm["whitmore_width_mm"], float(K), float(Lf),
                                                                       GUSSET_SUPPORT_TEXT.get(sp.get("gusset_support"),
                                                                                               "declared K"),
                                                                       gb["Pd_N"] / 1e3))
                rows.append(("%s buckling on the Whitmore width (compression)" % label, c))
    return rows


def end_connection_record(cfg, role, sec, tags, envt, elem_results, length, *, sls_force_N=None, sfrs=False):
    """The connection record (pkg['connections'] shape) of one truss member group (role, section): bolts in shear /
    bearing for the largest axial force of the group's members, detailing rows, the gusset yield on the Whitmore width
    (engineering practice) for a member that ends at the gusset, and the back-to-back interconnection of a double
    angle.  The member's net-section rupture and block shear at this connection are in its member check (6.3 / 6.4).
    HSFG bolts (spec 'bolt_type': 'HSFG', 'slip_surface' (Table 20)) are also checked for slip at the service force
    (10.4.3, sls_force_N); when the truss is part of the lateral system (sfrs: a knee-braced portal) the 12.4.1 bolt
    type gate applies (fully tensioned HSFG or turned and fitted bolts)."""
    sp = spec_for(cfg, role, sec)
    N_c = max(envt[t]["comp"] for t in tags)
    N_t = max(envt[t]["tens"] for t in tags)
    N = max(N_c, N_t)
    rec = {"id": "conn-%s-%s" % (role, sec), "type": "truss member end (bolted to the gusset)", "section": sec,
           "demand": {"axial_N": round(N, 1), "P_comp_N": round(N_c, 1), "P_tens_N": round(N_t, 1)},
           "inputs": {"axial_N": round(N, 1), "V_N": round(N, 1)},
           "design_basis": "IS 800:2007 10.2 / 10.3 (bolts), 7.5.2.1 / 7.8 (double angles); gusset Whitmore yield "
                           "(engineering practice); the bolted geometry declared for each member end",
           "limit_state": "IS 800:2007 10 / 7.5 / 7.8", "notes": [], "checks": []}
    if not sp:
        rec["checks"].append({"name": "truss member end connection", "value": None, "limit": None, "dc": None,
                              "ok": None, "found": False, "clause": "IS 800:2007 10.3",
                              "reason": "cfg['truss_connections'] not declared for %s (%s)" % (role, sec),
                              "source": SRC})
        rec["DC"] = None
        return rec
    if not is_angle_section(sec):
        # review 2026-11: the truss end-connection model covers angles; a CHS / plate-ended web is not checked here
        rec["checks"].append({"name": "truss member end connection", "value": None, "limit": None, "dc": None,
                              "ok": None, "found": False, "clause": "IS 800:2007 10.3",
                              "reason": "%s is not an angle: the angle-truss connection model does not cover it (check "
                                        "it as a brace end connection)" % sec, "source": SRC})
        rec["DC"] = None
        return rec
    chord = is_chord_role(role)
    bg = bolt_group(sp, sec)

    def _row(name, c, **extra):
        r = {"name": name, "value": c.get("value"), "limit": c.get("limit"), "dc": c.get("dc"), "ok": c.get("ok"),
             "clause": c.get("clause"), "cite": c.get("cite"), "source": SRC}
        if c.get("ok") is None:
            r["found"] = False
            r["reason"] = c.get("reason")
        r.update(extra)
        return r

    if bg.get("found"):
        rec["checks"].append(_row("bolt group in shear / bearing (%d M%d %s, %s)"
                                  % (int(sp["n_bolts"]), int(sp["d_mm"]), sp.get("grade", "4.6"),
                                     "double shear" if bg["double_shear"] else "single shear"),
                                  C._check(N, bg["capacity_N"], clause="IS 800:2007 10.3.2-10.3.4",
                                           cite="n min(Vdsb, Vdpb) = %.1f kN (%s side governs)"
                                                % (bg["capacity_N"] / 1e3, bg["governs"]))))
    else:
        rec["checks"].append(_row("bolt group in shear / bearing", {"ok": None, "clause": "IS 800:2007 10.3",
                                                                    "reason": bg.get("reason")}))
    if str(sp.get("bolt_type") or "").lower().startswith(("hsfg", "friction")):
        p_ = S.props(sec)
        b_ = {"n_bolts": int(sp["n_bolts"]), "d_mm": sp["d_mm"], "grade": sp.get("grade", "8.8"),
              "n_e": 2 if p_.get("section_type") == "double_angle" else 1}
        if sls_force_N is None:
            rec["checks"].append(_row("HSFG slip at service (10.4.3)", {"ok": None, "clause": "IS 800:2007 10.4.3",
                                                                       "reason": "service force not available"}))
        else:
            one = C.hsfg_slip_capacity(b_["d_mm"], b_["grade"], surface=sp.get("slip_surface"), mu_f=sp.get("mu_f"),
                                       n_e=b_["n_e"], gamma_mf=C.GAMMA_MF_SERVICE)
            if one.get("found"):
                rec["checks"].append(_row("HSFG slip at service, %d interface(s), mu_f %.2f (10.4.3)"
                                          % (b_["n_e"], one["mu_f"]),
                                          C._check(abs(float(sls_force_N)), b_["n_bolts"] * one["Vdsf_N"],
                                                   clause="IS 800:2007 10.4.3",
                                                   cite="service-load slip: n mu_f ne Kh F0 / 1.10 = %.1f kN"
                                                        % (b_["n_bolts"] * one["Vdsf_N"] / 1e3))))
            else:
                rec["checks"].append(_row("HSFG slip at service (10.4.3)", {"ok": None, "clause": "IS 800:2007 10.4.3",
                                                                           "reason": str(one.get("required_inputs"))}))
    if sfrs:
        g_ = C.hsfg_gate(sp.get("bolt_type"))
        rec["checks"].append(_row("12.4.1 bolt type (truss of the knee-braced portal)", g_, gate=True))
    for nm, c in detailing_rows(sp, sec, compression=N_c > 0, L_mm=None):
        rec["checks"].append(_row(nm, c, gate=False))
    if sp.get("gusset_t_mm"):
        # review 2026-11: the gusset for the member force -- for a chord the FULL chord force (the heel and apex
        # gussets, where the chord ends; conservative at the panel points it passes through): Whitmore yield, block
        # shear of the gusset (one bolt line, 6.4.1) and, in compression, gusset buckling on the Whitmore width
        tag_ = " (full chord force: heel / apex gusset)" if chord else ""
        for nm_, c_ in gusset_rows(sp, N, N_c):
            rec["checks"].append(_row(nm_ + tag_, c_))
    if chord and isinstance(sp.get("splice"), dict):
        # review 2026-11: a chord splice made at a panel-point gusset.  IS 800 7.3.4.2: a compression member not faced
        # for bearing is spliced for all the forces -- the chord-end bolts and gusset rows above (full chord force) are
        # the splice connection on each side; the gusset itself carries the full chord force across the cut (gross
        # yield 6.2, net section across the one bolt line 6.3.1)
        spl = sp["splice"]
        bgd, tg = spl.get("gusset_depth_mm"), float(sp.get("gusset_t_mm") or 0.0)
        if bgd and tg:
            fy_g, fu_g = _fy_fu(sp.get("gusset_grade") or "E250", tg)
            Tg = min(float(bgd) * tg * fy_g / I8.GAMMA_M0_DEFAULT,
                     0.9 * (float(bgd) - float(sp["d0_mm"])) * tg * fu_g / I8.GAMMA_M1_DEFAULT)
            c = C._check(N, Tg, clause="IS 800:2007 7.3.4.2 + 6.2 / 6.3.1",
                         cite="chord splice at %s: gusset %.0f x %.0f mm across the cut, min(Ag fy / gamma_m0, 0.9 An "
                              "fu / gamma_m1) = %.1f kN for the full chord force %.1f kN; each side joined by the "
                              "chord-end bolts above" % (spl.get("at") or "a panel-point gusset", float(bgd), tg,
                                                         Tg / 1e3, N / 1e3))
            rec["checks"].append(_row("chord splice at a panel-point gusset (7.3.4.2)", c))
            rec["splice"] = {"at": spl.get("at"), "gusset_depth_mm": float(bgd), "capacity_N": round(Tg, 1)}
        else:
            rec["checks"].append(_row("chord splice at a panel-point gusset (7.3.4.2)",
                                      {"ok": None, "clause": "IS 800:2007 7.3.4.2",
                                       "reason": "splice gusset_depth_mm or gusset_t_mm not declared"}))
    if S.props(sec).get("section_type") == "double_angle":
        t0 = tags[0]
        res = elem_results.get(t0) or {}
        klr = ((res.get("capacities") or {}).get("compression") or {}).get("KL_over_r_max")
        st = stitch_record(sec, L_mm=max(length[t] for t in tags), KL_over_r_member=klr, compression=N_c > 0)
        if st:
            rec["stitches"] = st
            rec["checks"].append(_row("back-to-back interconnection: %d intermediate packed connections at %.0f mm"
                                      % (st["n_intermediate"], st["spacing_mm"]), st["check"]))
            rec["notes"].append("double angle interconnected by %d packed bolted connections at %.0f mm (7.8 / 10.2.5)"
                                % (st["n_intermediate"], st["spacing_mm"]))
            d_st = float(sp.get("stitch_bolt_d_mm") or sp["d_mm"])
            # a minimum-size rule, not a strength ratio: a gate (pass / fail), kept out of the connection D/C
            sb = dict(stitch_bolt_check(sec, d_st), dc=None)
            rec["checks"].append(_row("back-to-back interconnection bolts M%d (7.8.4)" % int(d_st), sb, gate=True))
    rec["bolt_group"] = bg
    strength = [c for c in rec["checks"] if isinstance(c.get("dc"), (int, float))]
    gov = max(strength, key=lambda c: c["dc"]) if strength else None
    rec["DC"] = gov["dc"] if gov else None
    if gov:
        rec["governing_check"] = gov["name"]
        rec["clause"] = gov.get("clause")
        rec["cited"] = gov.get("clause")
        rec["value"], rec["limit"] = gov.get("value"), gov.get("limit")
    return rec


# ------------------------------------------------------------------------------------------------ knees (12.10)
def knee_geometry(nodes, knee):
    """Lever arm e (perpendicular distance from the heel node to the knee-brace line) and the brace angle to the
    horizontal, from the node coordinates {tag: (x, y, z)} and the knee record {heel_node, knee_node, chord_node}."""
    h = nodes[knee["heel_node"]]
    a, b = nodes[knee["knee_node"]], nodes[knee["chord_node"]]
    v = [b[i] - a[i] for i in range(3)]
    L = math.sqrt(sum(x * x for x in v))
    u = [x / L for x in v]
    w = [h[i] - a[i] for i in range(3)]
    proj = sum(w[i] * u[i] for i in range(3))
    perp = [w[i] - proj * u[i] for i in range(3)]
    e = math.sqrt(sum(x * x for x in perp))
    theta = math.degrees(math.asin(min(1.0, abs(u[2]))))
    return {"lever_arm_mm": e, "brace_length_mm": L, "angle_deg": theta, "cos_h": math.sqrt(max(0.0, 1.0 - u[2] ** 2)),
            "sin_v": abs(u[2])}


D_T10_TEXT = ("Steltic design ruling D-T10 -- owner ruling 2026-11-01 (1.2 x what the knee brace can deliver); lead "
              "reading 2026-11-01: N_del = Ag fy characteristic, per IS 800 12.7.3.1(a), max over tension and "
              "compression")


def _col_props(sec):
    try:
        p = S.props(sec)
    except Exception:
        return None
    return p if p.get("tw") and p.get("d") and p.get("tf") else None


# ------------------------------------------------------------------------------------------------ gusset layout
def bolt_line(n, pitch, end_mm, u, clear_fn, c0, *, leg_mm, c_mm, gauge_mm, side):
    """The bolt positions of one angle end on a gusset (re-check 2, review 2026-11): the angle's axis (the force line,
    through the centroid) runs from the origin along the unit vector u; its connected leg lies on the gusset, the back
    at -c and the toe at leg - c across the axis on `side` (+1 / -1 along n = (-u_z, u_x)); the bolt line is at the
    gauge.  The angle end is placed as close to the origin as its corners allow, clear_fn(point) >= c0 (the obstacle:
    the column face, the chord), and the first bolt is end_mm beyond it.  Returns the bolt points [(x, z)]."""
    nx_, nz_ = -u[1], u[0]
    ws = [-c_mm * side, (leg_mm - c_mm) * side]
    # clear_fn is linear: clear_fn(p) = a . p + b0
    b0 = clear_fn((0.0, 0.0))
    ax, az = clear_fn((1.0, 0.0)) - b0, clear_fn((0.0, 1.0)) - b0
    au, an = ax * u[0] + az * u[1], ax * nx_ + az * nz_
    if au <= 0:
        return None
    s_end = max((c0 - b0 - w * an) / au for w in ws)
    d = (gauge_mm - c_mm) * side
    return [((s_end + end_mm + k * pitch) * u[0] + d * nx_, (s_end + end_mm + k * pitch) * u[1] + d * nz_)
            for k in range(int(n))]


def _edge_min(sp, cut):
    return (1.5 if str(cut or "sheared").lower().startswith(_CUT_15) else 1.7) * float(sp["d0_mm"])


def knee_gusset_layout(kg, sp, sec, col_d_mm, theta_deg):
    """The knee gusset's layout from ONE geometry source -- its declared outline (face_length_mm along the column,
    projection_mm into the bay, the angle's clearance from the column face, the cut of its edges) and the knee-brace
    bolt line (n, pitch, end distance, gauge) -- with the brace's line of force through the knee work point on the
    column centre line: the bolts placed as close to the column as the angle's corners allow, the gusset slid along
    the column as far as the bolts' edge distances allow towards centring its weld on the force line.  Returns
    {fits, e_face_mm (perpendicular distance of the force line from the weld centroid), face_length_min_e0_mm (the
    face length that would give e = 0), projection_needed_mm, side, bolts}."""
    th = math.radians(theta_deg)
    u = (math.cos(th), math.sin(th))
    p = S.props(sec)
    leg, c = float(p.get("leg_connected_mm") or p["d"]), float(p.get("Cz") or p.get("c_back_mm") or 0.0)
    L, B = float(kg["face_length_mm"]), float(kg.get("projection_mm") or 0.0)
    c0 = float(kg.get("angle_clearance_mm") or 15.0)
    em = _edge_min(sp, kg.get("edge_cut"))
    best = None
    for side in (1, -1):
        # origin F: the force line crosses the column face at d/2 tan(theta) above the knee work point
        pts = bolt_line(int(sp["n_bolts"]), float(sp["pitch_mm"]), float(sp["end_mm"]), u, lambda q: q[0], c0,
                        leg_mm=leg, c_mm=c, gauge_mm=float(sp["gauge_mm"]), side=side)
        if not pts:
            continue
        xs, zs = [q[0] for q in pts], [q[1] for q in pts]
        lo, hi = max(zs) + em - L, min(zs) - em                    # the gusset's bottom edge z0 range
        B_need = max(xs) + em
        fits = lo <= hi + 1e-9 and min(xs) >= em - 1e-9 and (not B or B_need <= B + 1e-9)
        zc = min(max(0.0, lo + L / 2.0), hi + L / 2.0) if lo <= hi else None
        rec = {"fits": fits, "side": side, "bolts": [(round(x, 1), round(z, 1)) for x, z in pts],
               "e_face_mm": (abs(zc) * math.cos(th)) if zc is not None else None,
               "face_length_min_e0_mm": 2.0 * max(max(zs) + em, -(min(zs) - em)),
               "projection_needed_mm": B_need, "edge_min_mm": em, "weld_centre_above_F_mm": zc,
               "force_line_at_face_above_work_point_mm": col_d_mm / 2.0 * math.tan(th)}
        key = (not fits, rec["e_face_mm"] if rec["e_face_mm"] is not None else 1e9)
        if best is None or key < best[0]:
            best = (key, rec)
    return best[1] if best else {"fits": False, "reason": "bolt line cannot clear the column"}


def chord_node_layout(gn, sp_kb, kb_sec, sp_v, v_sec, chord_sec, theta_deg, *, sp_chord=None):
    """The bottom-chord gusset where the knee brace lands (node 1), from its declared outline (toward_column_mm /
    toward_midspan_mm along the chord from the node, above_mm / below_mm from the chord work line; the chord heel
    'bottom' | 'top'; the clearance of the angle ends from the chord): the knee brace's bolt line below the chord at
    theta and the vertical's above it, each placed as close to the chord as the angles' corners allow, and the chord's
    own bolts at the node (sp_chord) along the chord.  Returns {fits, needed: {above_mm, below_mm, toward_column_mm,
    toward_midspan_mm, length_for_chord_bolts_mm}, lines}."""
    th = math.radians(theta_deg)
    pc = S.props(chord_sec)
    Dc = float(pc.get("leg_connected_mm") or pc["d"])
    cc = float(pc.get("c_back_mm") or 0.0)
    heel_bottom = str(gn.get("chord_heel") or "bottom") == "bottom"
    z_bot, z_top = (-cc, Dc - cc) if heel_bottom else (-(Dc - cc), cc)
    c0 = float(gn.get("angle_clearance_mm") or 15.0)
    em = _edge_min(sp_kb, gn.get("edge_cut"))
    out = {"lines": {}, "needed": {}}
    lines = []
    pkb = S.props(kb_sec)
    ub = (-math.cos(th), -math.sin(th))                 # the knee brace leaves node 1 down towards the column
    best = None
    for side in (1, -1):
        pts = bolt_line(int(sp_kb["n_bolts"]), float(sp_kb["pitch_mm"]), float(sp_kb["end_mm"]), ub,
                        lambda q: z_bot - q[1], c0, leg_mm=float(pkb["d"]), c_mm=float(pkb.get("Cz") or 0.0),
                        gauge_mm=float(sp_kb["gauge_mm"]), side=side)
        if pts and (best is None or -min(q[1] for q in pts) < -min(q[1] for q in best)):
            best = pts
    lines.append(("knee brace", best))
    if sp_v and v_sec:
        pv = S.props(v_sec)
        bestv = None
        for side in (1, -1):
            pts = bolt_line(int(sp_v["n_bolts"]), float(sp_v["pitch_mm"]), float(sp_v["end_mm"]), (0.0, 1.0),
                            lambda q: q[1] - z_top, c0, leg_mm=float(pv["d"]), c_mm=float(pv.get("Cz") or 0.0),
                            gauge_mm=float(sp_v["gauge_mm"]), side=side)
            if pts and (bestv is None or max(q[1] for q in pts) < max(q[1] for q in bestv)):
                bestv = pts
        lines.append(("vertical", bestv))
    allp = [q for _, pts in lines for q in (pts or [])]
    need = {"above_mm": max([q[1] for q in allp] + [z_top]) + em, "below_mm": -min([q[1] for q in allp] + [z_bot]) + em,
            "toward_column_mm": max([-q[0] for q in allp] + [0.0]) + em,
            "toward_midspan_mm": max([q[0] for q in allp] + [0.0]) + em}
    Lc_, Lm_ = float(gn["toward_column_mm"]), float(gn["toward_midspan_mm"])
    A_, Bl = float(gn["above_mm"]), float(gn["below_mm"])
    if sp_chord:
        need["length_for_chord_bolts_mm"] = (int(sp_chord["n_bolts"]) - 1) * float(sp_chord["pitch_mm"]) + 2.0 * em
    fits = (bool(allp) and None not in [v for _, v in lines] and need["above_mm"] <= A_ + 1e-9
            and need["below_mm"] <= Bl + 1e-9 and need["toward_column_mm"] <= Lc_ + 1e-9
            and need["toward_midspan_mm"] <= Lm_ + 1e-9
            and need.get("length_for_chord_bolts_mm", 0.0) <= Lc_ + Lm_ + 1e-9)
    out.update(fits=fits, needed={k: round(v, 1) for k, v in need.items()},
               lines={k: [(round(x, 1), round(z, 1)) for x, z in (v or [])] for k, v in lines}, edge_min_mm=em)
    return out


def knee_load_path_rows(knee, cfg, F_N, geo, *, H_N, V_heel_N):
    """Review 2026-11: the knee load path that D-T10's CJP welds imply, as checks (declared in
    cfg['truss_connections']['knee_gusset'] = {face_length_mm (gusset weld along the column flange), t_mm, grade,
    weld 'cjp', e_face_mm (offset of the brace line from the weld centroid)} and the heel cap plate
    cfg['truss_connections']['heel']['cap_weld'] = 'cjp'):
      * the knee gusset at the column face: shear (8.4.1) and axial + bending with the high-shear reduction (9.2.2,
        9.3.1.1 linear) on the section L_face x t, under the brace force 1.2 N_del resolved along / normal to the face;
      * its CJP weld to the column flange: butt weld = parent metal (10.5.7.1.2), fe = sqrt(fb^2 + 3 q^2) <= the
        parent metal's fy / gamma_m0 (10.5.10.2.2), with the moment of the eccentricity derived from the outline and
        the bolt line (knee_gusset_layout);
      * the column web at the knee under the normal component: 8.7.4 local capacity Fw = (b1 + n2) tw fyw / gamma_m0
        (b1 = the weld length, n2 = 1:2.5 through the flange and root, both sides) and 8.7.3.1 web buckling (class c,
        strut (b1 + d) tw, KL 0.7 d);
      * the column web shear between the knee and the heel / at the column top, H = the couple's horizontal force
        (8.4.1, Av = h tw);
      * the heel cap plate CJP weld to the column top: the weld plane is the column section, fe = sqrt(sigma^2 +
        3 tau^2) with tau = H / A, sigma = V / A (10.5.7.1.2)."""
    import india_connections as _C
    rows = []
    kid = knee.get("id")
    kg = ((cfg or {}).get("truss_connections") or {}).get("knee_gusset")
    heel = ((cfg or {}).get("truss_connections") or {}).get("heel") or {}
    pc = _col_props(knee.get("column_section"))
    base = {"source": SRC, "member": kid}

    def _na(rid, clause, why):
        rows.append(dict(base, id=rid, value=None, limit=None, dc=None, ok=None, clause=clause, cite=why, reason=why))
    th = math.radians(geo["angle_deg"])
    N_face, V_face = F_N * math.cos(th), F_N * math.sin(th)          # normal to / along the column face
    if not kg or not kg.get("face_length_mm") or not kg.get("t_mm"):
        _na("12.10.2.1_knee_gusset_face_section", "IS 800:2007 8.4.1 / 9.2.2 / 9.3.1.1",
            "knee gusset outline at the column face (truss_connections['knee_gusset']) not declared")
    else:
        Lf, t = float(kg["face_length_mm"]), float(kg["t_mm"])
        fy, fu = _fy_fu(kg.get("grade") or "E250", t)
        A = Lf * t
        # re-check 2: the eccentricity of the brace's line of force from the weld centroid comes from the declared
        # outline and the knee-brace bolt line (knee_gusset_layout), not a hand value
        sp_kb = spec_for(cfg, knee.get("brace_role") or "truss_knee_brace", knee.get("brace_section"))
        lay = (knee_gusset_layout(kg, sp_kb, knee["brace_section"], float(pc["d"]), geo["angle_deg"])
               if (pc and sp_kb and is_angle_section(knee.get("brace_section"))) else None)
        if lay is None:
            e_face = float(kg["e_face_mm"]) if kg.get("e_face_mm") is not None else None
        else:
            e_face = lay.get("e_face_mm")
            rows.append(dict(base, id="12.10.2.1_knee_gusset_layout", value=lay.get("projection_needed_mm"),
                             limit=kg.get("projection_mm"), dc=None, ok=bool(lay.get("fits")), gate=True,
                             clause="IS 800:2007 10.2.4.2 (edge distances) / 12.10.2.1",
                             cite="knee gusset %.0f x %.0f mm holds the %d-bolt line (bolts >= %.1f mm from its edges): "
                                  "the brace's line of force is %.1f mm from the weld centroid (a %.0f mm face would "
                                  "centre it)" % (Lf, float(kg.get("projection_mm") or 0.0), int(sp_kb["n_bolts"]),
                                                  lay.get("edge_min_mm") or 0.0, e_face if e_face is not None else -1,
                                                  lay.get("face_length_min_e0_mm") or 0.0), layout=lay))
        if e_face is None:
            _na("12.10.2.1_knee_gusset_face_section", "IS 800:2007 8.4.1 / 9.2.2 / 9.3.1.1",
                "the knee-brace bolt line does not fit the declared knee gusset")
            return rows
        M = F_N * float(e_face)
        Vd = A * fy / (math.sqrt(3.0) * I8.GAMMA_M0_DEFAULT)
        Nd = A * fy / I8.GAMMA_M0_DEFAULT
        Md = t * Lf ** 2 / 4.0 * fy / I8.GAMMA_M0_DEFAULT
        beta = (2.0 * V_face / Vd - 1.0) ** 2 if V_face > 0.6 * Vd else 0.0
        Mdv = Md * (1.0 - beta)
        inter = N_face / Nd + (M / Mdv if Mdv > 0 else (float("inf") if M else 0.0))
        dc = max(V_face / Vd, inter)
        rows.append(dict(base, id="12.10.2.1_knee_gusset_face_section", value=dc, limit=1.0, dc=dc, ok=dc <= 1.0,
                         clause="IS 800:2007 8.4.1 / 9.2.2 / 9.3.1.1",
                         cite="knee gusset %.0f x %.0f mm at the column face: V %.1f / Vd %.1f kN; N %.1f / Nd %.1f kN "
                              "+ M %.1f kN-m / Mdv %.1f kN-m (9.2.2 beta %.3f)" % (
                                  Lf, t, V_face / 1e3, Vd / 1e3, N_face / 1e3, Nd / 1e3, M / 1e6, Mdv / 1e6, beta)))
        if str(kg.get("weld") or "").lower() == "cjp":
            fb, q = N_face / A + 6.0 * M / (t * Lf ** 2), V_face / A
            fe = math.sqrt(fb ** 2 + 3.0 * q ** 2)
            lim = fy / I8.GAMMA_M0_DEFAULT
            rows.append(dict(base, id="12.10.2.1_knee_gusset_cjp_weld", value=fe, limit=lim, dc=fe / lim,
                             ok=fe <= lim, clause="IS 800:2007 10.5.7.1.2 / 10.5.10.2.2 / 12.4.2",
                             cite="CJP weld of the knee gusset to the column flange: 'butt welds shall be treated as "
                                  "parent metal with a thickness equal to the throat thickness, and the stresses shall "
                                  "not exceed those permitted in the parent metal' (10.5.7.1.2); fe = sqrt(fb^2 + 3 q^2) "
                                  "(10.5.10.2.2, fbr = 0) = %.1f MPa <= fy / gamma_m0 = %.1f MPa; fb includes the "
                                  "moment of the %.1f mm eccentricity" % (fe, lim, float(e_face))))
        else:
            _na("12.10.2.1_knee_gusset_cjp_weld", "IS 800:2007 12.4.2",
                "knee gusset weld not declared as CJP (D-T10 / 12.4.2)")
        if pc:
            tw, tf, d = float(pc["tw"]), float(pc["tf"]), float(pc["d"])
            fyc = _fy_fu("E250", max(tw, tf))[0]
            n2 = 2.5 * (tf + float(pc.get("R1") or 0.0))
            Fw = (Lf + 2.0 * n2) * tw * fyc / I8.GAMMA_M0_DEFAULT
            rows.append(dict(base, id="12.10.2.1_column_web_bearing", value=N_face, limit=Fw, dc=N_face / Fw,
                             ok=N_face <= Fw, clause="IS 800:2007 8.7.4",
                             cite="column %s web at the knee: Fw = (b1 + n2) tw fyw / gamma_m0, b1 = %.0f mm (the weld), "
                                  "n2 = 2.5 (tf + r) = %.0f mm each side: %.1f kN" % (knee.get("column_section"), Lf,
                                                                                     n2, Fw / 1e3)))
            bw, KL, r_ = Lf + d, 0.7 * d, tw / math.sqrt(12.0)
            pdw = I8.design_compressive_strength(bw * tw, fyc, KL, r_, buckling_class="c")
            if pdw.get("found"):
                rows.append(dict(base, id="12.10.2.1_column_web_buckling", value=N_face, limit=pdw["Pd_N"],
                                 dc=N_face / pdw["Pd_N"], ok=N_face <= pdw["Pd_N"], clause="IS 800:2007 8.7.3.1",
                                 cite="column web strut (b1 + d) tw = %.0f x %.1f mm, KL = 0.7 d, curve c: %.1f kN"
                                      % (bw, tw, pdw["Pd_N"] / 1e3)))
    if pc:
        tw, tf, d, A_c = float(pc["tw"]), float(pc["tf"]), float(pc["d"]), float(pc["A"])
        fyc = _fy_fu("E250", max(tw, tf))[0]
        Vd_c = d * tw * fyc / (math.sqrt(3.0) * I8.GAMMA_M0_DEFAULT)
        rows.append(dict(base, id="12.10.2.4_column_web_shear", value=H_N, limit=Vd_c, dc=H_N / Vd_c, ok=H_N <= Vd_c,
                         clause="IS 800:2007 8.4.1 / 12.10.2.4",
                         cite="column %s between the knee and the heel (and at the column top): H = 1.2 N_del cos(theta) "
                              "= %.1f kN <= Vd = h tw fy / (sqrt3 gamma_m0) = %.1f kN"
                              % (knee.get("column_section"), H_N / 1e3, Vd_c / 1e3)))
        if str(heel.get("cap_weld") or "").lower() == "cjp":
            tau, sig = H_N / A_c, V_heel_N / A_c
            fe = math.sqrt(sig ** 2 + 3.0 * tau ** 2)
            lim = fyc / I8.GAMMA_M0_DEFAULT
            rows.append(dict(base, id="12.10.2.4_heel_cap_weld", value=fe, limit=lim, dc=fe / lim, ok=fe <= lim,
                             clause="IS 800:2007 10.5.7.1.2 / 10.5.10.2.2 / 12.4.2",
                             cite="heel cap plate CJP-welded to the column top (butt weld = parent metal, 10.5.7.1.2; "
                                  "the weld plane is the column section, A = %.0f mm2): tau = H / A, sigma = V / A, fe = "
                                  "%.1f MPa <= fy / gamma_m0 = %.1f MPa (10.5.10.2.2)" % (A_c, fe, lim)))
        else:
            _na("12.10.2.4_heel_cap_weld", "IS 800:2007 12.4.2", "heel cap plate weld not declared as CJP")
    else:
        _na("12.10.2.4_column_web_shear", "IS 800:2007 8.4.1", "column section at the knee not available")
    return rows



def knee_chord_node_rows(knee, cfg, F_N, geo):
    """Re-check 2 (review 2026-11): the bottom-chord end of the knee load path, at the gusset where the knee brace
    lands (node 1; truss_connections['knee_chord_node'] = {toward_column_mm, toward_midspan_mm, above_mm, below_mm, t_mm,
    gusset_grade, chord_heel, angle_clearance_mm, edge_cut, n_bolts, d_mm, grade (bolts), d0_mm, pitch_mm, end_mm,
    gauge_mm (the chord's bolts through the gusset at the node)}):
      * the declared outline holds the knee brace's and the vertical's bolt lines and the chord bolts (gate);
      * the gusset-to-chord bolts for the horizontal component of 1.2 N_del (10.3, double shear through the chord);
      * the gusset section along the chord: the horizontal component in shear along it, the vertical component across
        it (8.4.1 / 9.2.2 / 9.3.1.1);
      * the short vertical there takes the vertical component: a ductility-order record (not a check) -- IS 800 12.10
        asks no member hierarchy of an ordinary moment frame; it says whether the vertical or its end bolts yield
        before the brace can deliver its vertical component."""
    rows = []
    kid = knee.get("id")
    tc = (cfg or {}).get("truss_connections") or {}
    gn = tc.get("knee_chord_node")
    base = {"source": SRC, "member": kid}
    th = math.radians(geo["angle_deg"])
    H, V = F_N * math.cos(th), F_N * math.sin(th)
    if not gn:
        rows.append(dict(base, id="12.10.2.1_knee_chord_bolts", value=H, limit=None, dc=None, ok=None,
                         clause="IS 800:2007 10.3", cite="the knee-brace node gusset on the chord is not declared",
                         reason="truss_connections['knee_chord_node'] not declared"))
        return rows
    sp_kb = spec_for(cfg, knee.get("brace_role") or "truss_knee_brace", knee.get("brace_section"))
    v_sec, ch_sec = knee.get("vertical_section"), knee.get("chord_section")
    sp_v = spec_for(cfg, "truss_vertical", v_sec) if v_sec else None
    if ch_sec and sp_kb and is_angle_section(knee.get("brace_section")):
        lay = chord_node_layout(gn, sp_kb, knee["brace_section"], sp_v, v_sec, ch_sec, geo["angle_deg"], sp_chord=gn)
        nd = lay.get("needed") or {}
        rows.append(dict(base, id="12.10.2.1_knee_chord_gusset_layout", value=None, limit=None, dc=None,
                         ok=bool(lay.get("fits")), gate=True, clause="IS 800:2007 10.2.4.2 / 12.10.2.1", layout=lay,
                         cite="knee-brace node gusset %.0f + %.0f mm along the chord, %.0f mm above / %.0f mm below it, "
                              "holds the knee brace's and the vertical's bolt lines and %d chord bolts with edge "
                              "distances >= %.1f mm (needs %.0f / %.0f along, %.0f above, %.0f below)"
                              % (float(gn["toward_column_mm"]), float(gn["toward_midspan_mm"]), float(gn["above_mm"]),
                                 float(gn["below_mm"]), int(gn["n_bolts"]), lay.get("edge_min_mm") or 0.0,
                                 nd.get("toward_column_mm", 0), nd.get("toward_midspan_mm", 0), nd.get("above_mm", 0),
                                 nd.get("below_mm", 0))))
        bg = bolt_group(dict(gn, gusset_t_mm=gn.get("t_mm")), ch_sec)
        if bg.get("found"):
            c = C._check(H, bg["capacity_N"], clause="IS 800:2007 12.10.2.1 + 10.3.2-10.3.4",
                         cite="gusset to the bottom chord at the knee-brace node: %d M%d %s %s, %.1f kN >= the horizontal "
                              "component of 1.2 N_del, %.1f kN" % (int(gn["n_bolts"]), int(gn["d_mm"]),
                                                                  gn.get("grade", "8.8"), "double shear" if
                                                                  bg.get("double_shear") else "single shear",
                                                                  bg["capacity_N"] / 1e3, H / 1e3))
            rows.append(dict(c, id="12.10.2.1_knee_chord_bolts", member=kid, source=SRC))
        Lg = float(gn["toward_column_mm"]) + float(gn["toward_midspan_mm"])
        t = float(gn.get("t_mm") or 0.0)
        if t:
            fy = _fy_fu(gn.get("gusset_grade") or "E250", t)[0]
            A = Lg * t
            Vd, Nd = A * fy / (math.sqrt(3.0) * I8.GAMMA_M0_DEFAULT), A * fy / I8.GAMMA_M0_DEFAULT
            dc = max(H / Vd, V / Nd)
            rows.append(dict(base, id="12.10.2.1_knee_chord_gusset_section", value=dc, limit=1.0, dc=dc, ok=dc <= 1.0,
                             clause="IS 800:2007 8.4.1 / 9.2.2 / 9.3.1.1",
                             cite="knee-brace node gusset %.0f x %.0f mm along the chord: H %.1f / Vd %.1f kN (shear "
                                  "along), V %.1f / Nd %.1f kN (across, to the vertical)"
                                  % (Lg, t, H / 1e3, Vd / 1e3, V / 1e3, Nd / 1e3)))
    # the short vertical at the node: ductility order (a record, not a check)
    if v_sec:
        pv = S.props(v_sec)
        Ty_v = float(pv["A"]) * _fy_fu("E250", float(pv.get("tw") or 6.0))[0]
        Vv = float(knee.get("Ty_N") or 0.0) * math.sin(th)
        bgv = bolt_group(sp_v, v_sec) if sp_v else {}
        capb = bgv.get("capacity_N")
        first = ("its end bolts reach their capacity" if (capb and capb < Ty_v) else "the vertical yields")
        rows.append(dict(base, id="12.10.2.1_short_vertical_order", value=Vv, limit=min(Ty_v, capb or Ty_v), dc=None,
                         ok=True, gate=True, advisory=True, clause="IS 800:2007 12.10 (ductility order, a record)",
                         cite="the short vertical %s at the knee-brace node takes the brace's vertical component: at the "
                              "brace's yield Ag fy sin(theta) = %.1f kN against the vertical's Ag fy %.1f kN and its "
                              "end bolts %s kN -- %s before the brace could deliver it; the brace-yields-first "
                              "hierarchy covers the knee and heel connections checked, not this vertical (IS 800 12.10 "
                              "asks no member hierarchy of an ordinary moment frame)"
                              % (v_sec, Vv / 1e3, Ty_v / 1e3, "%.1f" % (capb / 1e3) if capb else "-", first)))
    return rows

def knee_checks(knee, model_data, cfg, *, nodes, member_capacity):
    """IS 800 12.10.2.1 / 12.10.2.4 at a knee-braced truss portal (OMF), Steltic design ruling D-T10 (owner ruling
    2026-11-01: 1.2 x what the knee brace can deliver; lead reading 2026-11-01: N_del = Ag fy characteristic, per
    IS 800 12.7.3.1(a), max over tension and compression).  The truss is pinned on the column cap and delivers moment
    to the column only through the couple of the knee brace and the heel seat, so the 'maximum moment that can be
    delivered by the beam to the joint' (12.10.2.1) is the largest force the knee brace can deliver, in either
    direction, times its lever arm e about the heel.  N_del is characteristic (no gamma; the engine's Section 12
    convention, Mp = Zp fy for D-T7, and the 1.2 fy Ag of 12.7.3.1(a)): the larger of the gross yield Ag fy and the
    characteristic buckling strength Pd gamma_m0 (<= Ag fy, so Ag fy governs).  M_del = N_del e.  The joint is
    designed for 1.2 M_del:
      * each knee-brace end connection for 1.2 N_del: the bolt group and the gussets (Whitmore yield, block shear);
        gusset buckling for 1.2 x the characteristic buckling strength (the compression the brace can deliver);
      * the brace yields first: its bolted end (6.3.3 rupture, 6.4.1 block shear) is not weaker than its gross-section
        yield -- a ductility-order check, both sides as DESIGN values (Tdg = Ag fy / gamma_m0 against Tdn / Tdb), no
        1.2 margin on the angle's own end (a single angle bolted through one leg cannot develop 1.2 x its yield at
        its end under 6.3.3 shear lag, so the knee connection is designed for more than the brace can transmit);
      * the heel seat for the horizontal couple force 1.2 N_del cos(theta) with the 12.10.2.4 shear (1.2DL + 0.5LL end
        reaction + 2 (1.2 M_del) / span), and the knee load path (knee_load_path_rows).
    M_del is about twice the column's plastic moment, so the rule is conservative for the knee; the demand is not
    capped (the 'whichever is less' Mp alternative of 12.10.2.1 is not used: a triangular truss has no plastic
    moment at the column face).  member_capacity = N_del (characteristic)."""
    out = []
    kid = knee.get("id")
    sec = knee.get("brace_section")
    sp_kb = spec_for(cfg, knee.get("brace_role") or "truss_knee_brace", sec)
    sp_heel = ((cfg or {}).get("truss_connections") or {}).get("heel")
    geo = knee_geometry(nodes, knee)
    Nd = member_capacity
    base = {"clause": "IS 800:2007 12.10.2.1", "source": SRC, "member": kid}
    if not Nd:
        out.append(dict(base, id="12.10.2.1_knee_connection", value=None, limit=None, dc=None, ok=None,
                        cite="knee brace strength not available", reason="no member capacity"))
        return out
    Pd, Pc, Ty, Tdg = knee.get("Pd_N"), knee.get("Pd_char_N"), knee.get("Ty_N"), knee.get("Tdg_N")
    M_del = Nd * geo["lever_arm_mm"]
    F = 1.2 * Nd
    Mp_c = knee.get("column_Mp_Nmm")
    note = ("%s: the knee reaches the column through the knee-brace / heel couple; N_del = max(Ag fy %s, characteristic "
            "buckling Pd gamma_m0 %s) = %.1f kN; M_del = N_del e = %.1f kN x %.0f mm = %.1f kN-m%s; each knee-brace "
            "connection for 1.2 N_del = %.1f kN; the knee and heel connections checked are designed so that the brace "
            "yields (gross section) before they fail (the short vertical at the knee-brace node yields, or its end "
            "bolts reach their capacity, before the brace could deliver its vertical component; IS 800 12.10 asks no member hierarchy of an ordinary moment frame); "
            "a single angle bolted through one leg cannot develop 1.2 x its yield at its end (shear lag), so the knee "
            "connection is designed for more than the brace can transmit"
            % (D_T10_TEXT, "-" if Ty is None else "%.1f" % (Ty / 1e3), "-" if Pc is None else "%.1f" % (Pc / 1e3),
               Nd / 1e3, Nd / 1e3, geo["lever_arm_mm"], M_del / 1e6,
               (" = %.1f x the column's Mp (%.1f kN-m): conservative for the knee, not capped" % (M_del / Mp_c,
                                                                                                    Mp_c / 1e6))
               if Mp_c else "", F / 1e3))
    if not is_angle_section(sec):
        out.append(dict(base, id="12.10.2.1_knee_brace_connection", value=F, limit=None, dc=None, ok=None,
                        cite="knee brace %s is not an angle: its end connection is not covered by the angle-truss "
                             "model" % sec, reason="non-angle knee brace", note=note))
    elif sp_kb:
        bg = bolt_group(sp_kb, sec)
        if bg.get("found"):
            c = C._check(F, bg["capacity_N"], clause="IS 800:2007 12.10.2.1 + 10.3.2",
                         cite="knee-brace end bolts %d M%d %s: %.1f kN >= 1.2 N_del = %.1f kN"
                              % (int(sp_kb["n_bolts"]), int(sp_kb["d_mm"]), sp_kb.get("grade", "4.6"),
                                 bg["capacity_N"] / 1e3, F / 1e3))
            out.append(dict(c, id="12.10.2.1_knee_brace_connection", member=kid, note=note, source=SRC))
        else:
            out.append(dict(base, id="12.10.2.1_knee_brace_connection", value=None, limit=None, dc=None, ok=None,
                            cite="knee brace bolt group not evaluated", reason=bg.get("reason")))
        # the gussets at both knee-brace ends (column side and bottom-chord side, the same declared detail)
        for nm_, c_ in gusset_rows(sp_kb, F, 1.2 * (Pc or 0.0), label="knee gusset"):
            rid = "12.10.2.1_knee_gusset_" + ("whitmore_yield" if "yield" in nm_ else
                                               "block_shear" if "block shear" in nm_ else "buckling")
            out.append(dict(base, id=rid, value=c_.get("value"), limit=c_.get("limit"), dc=c_.get("dc"),
                            ok=c_.get("ok"), cite=c_.get("cite") or c_.get("reason"),
                            **({"reason": c_.get("reason")} if c_.get("ok") is None else {})))
        # the brace yields before its own bolted end fails (6.3.3 / 6.4.1 >= 6.2), both as design values
        Tend = [v for v in (knee.get("Tdn_N"), knee.get("Tdb_N")) if v]
        if Tdg and Tend:
            c = C._check(Tdg, min(Tend), clause="IS 800:2007 12.10.2.1 (D-T10) + 6.2 / 6.3.3 / 6.4.1",
                         cite="knee brace %s, design values: gross-section yield Tdg = Ag fy / gamma_m0 = %.1f kN <= its "
                              "bolted end, min(rupture %s, block shear %s) = %.1f kN -- the brace yields first "
                              "(ductility order; no 1.2 margin on the angle's own end)"
                              % (sec, Tdg / 1e3, "-" if not knee.get("Tdn_N") else "%.1f" % (knee["Tdn_N"] / 1e3),
                                 "-" if not knee.get("Tdb_N") else "%.1f" % (knee["Tdb_N"] / 1e3), min(Tend) / 1e3))
            out.append(dict(c, id="12.10.2.1_knee_brace_yields_first", member=kid, source=SRC))
        else:
            out.append(dict(base, id="12.10.2.1_knee_brace_yields_first", value=Tdg, limit=None, dc=None, ok=None,
                            cite="brace end rupture / block shear of the knee brace not available",
                            reason="tension limit states missing"))
    else:
        out.append(dict(base, id="12.10.2.1_knee_brace_connection", value=None, limit=None, dc=None, ok=None,
                        cite="cfg['truss_connections'] knee-brace spec missing", reason="not declared"))
    # heel seat: horizontal couple force + 12.10.2.4 shear
    V_g = float(knee.get("V_gravity_N") or 0.0)
    span = float(knee.get("span_mm") or 0.0)
    V_M = 2.0 * 1.2 * M_del / span if span > 0 else None
    H = F * geo["cos_h"]
    if sp_heel and V_M is not None:
        hb = C.bolt_group_capacity_is800(int(sp_heel["n_bolts"]), sp_heel["d_mm"], sp_heel.get("grade", "4.6"),
                                         nn=int(sp_heel.get("nn", 1)), ns=int(sp_heel.get("ns", 0)),
                                         t_mm=sp_heel["t_plate_mm"], fu_plate_MPa=sp_heel.get("fu_plate_MPa", 410.0),
                                         e_mm=sp_heel["end_mm"], p_mm=sp_heel["pitch_mm"], d0_mm=sp_heel["d0_mm"])
        R = math.hypot(H, V_g + V_M)
        if hb.get("found"):
            c = C._check(R, hb["capacity_N"], clause="IS 800:2007 12.10.2.1 / 12.10.2.4 + 10.3.2",
                         cite="heel seat bolts %d M%d %s: resultant of H = 1.2 N_del cos(theta) = %.1f kN and V = "
                              "1.2DL + 0.5LL %.1f kN + 2 x 1.2 M_del / span %.1f kN -> %.1f kN <= %.1f kN"
                              % (int(sp_heel["n_bolts"]), int(sp_heel["d_mm"]), sp_heel.get("grade", "4.6"), H / 1e3,
                                 V_g / 1e3, V_M / 1e3, R / 1e3, hb["capacity_N"] / 1e3))
            out.append(dict(c, id="12.10.2.4_heel_seat", member=kid, source=SRC,
                            demands={"H_N": H, "V_gravity_N": V_g, "V_moment_N": V_M, "R_N": R}))
        else:
            out.append(dict(base, id="12.10.2.4_heel_seat", clause="IS 800:2007 12.10.2.4", value=None, limit=None,
                            dc=None, ok=None, cite="heel seat bolts not evaluated", reason=str(hb.get("required_inputs"))))
        out += knee_load_path_rows(knee, cfg, F, geo, H_N=H, V_heel_N=V_g + V_M)
        out += knee_chord_node_rows(knee, cfg, F, geo)
    else:
        out.append(dict(base, id="12.10.2.4_heel_seat", clause="IS 800:2007 12.10.2.4", value=None, limit=None,
                        dc=None, ok=None, cite="cfg['truss_connections']['heel'] or the truss span missing",
                        reason="not declared"))
    for c in out:
        c.setdefault("knee", {"lever_arm_mm": round(geo["lever_arm_mm"], 1), "angle_deg": round(geo["angle_deg"], 1),
                              "N_d_N": round(Nd, 1), "N_del_N": round(Nd, 1),
                              "Pd_N": None if Pd is None else round(Pd, 1),
                              "Pd_char_N": None if Pc is None else round(Pc, 1),
                              "Ty_N": None if Ty is None else round(Ty, 1),
                              "Tdg_N": None if Tdg is None else round(Tdg, 1), "M_del_Nmm": round(M_del, 0),
                              "column_Mp_Nmm": None if not Mp_c else round(Mp_c, 0)})
    return out
