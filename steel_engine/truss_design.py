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


def member_inputs(cfg, role, sec, L_mm=None):
    """(angle_connection, tension_inputs, record) for the IS 800 check of a truss member of `sec` with the declared end
    connection; (None, None, {'error': ...}) when the spec is missing or incomplete."""
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
    ac = None
    if p.get("section_type") == "angle":
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


def detailing_rows(sp, sec, *, compression, L_mm=None):
    """Bolt spacing / end / edge distances (10.2.2, 10.2.3.2, 10.2.4.2) and the >= 2 bolts of a double angle strut
    (7.5.2.1) as check rows (value, limit, dc, ok)."""
    p = S.props(sec)
    d, d0 = float(sp["d_mm"]), float(sp["d0_mm"])
    t = float(p.get("t_mm") or p.get("tw"))
    leg = float(p.get("leg_connected_mm") or p.get("d"))
    k_edge = 1.7 if str(sp.get("edge") or "rolled").lower().startswith("shear") else 1.5
    rows = []
    n = int(sp["n_bolts"])
    if n >= 2:
        rows.append(("bolt pitch >= 2.5 d (10.2.2)", C._check(2.5 * d, float(sp["pitch_mm"]),
                     clause="IS 800:2007 10.2.2", cite="minimum spacing 2.5 d = %.0f mm, pitch %.0f mm"
                     % (2.5 * d, float(sp["pitch_mm"])))))
        pmax = min((12.0 if compression else 16.0) * t, 200.0)
        rows.append(("bolt pitch <= %s (10.2.3.2)" % ("12t / 200" if compression else "16t / 200"),
                     C._check(float(sp["pitch_mm"]), pmax, clause="IS 800:2007 10.2.3.2",
                              cite="pitch %.0f <= %.0f mm in a %s member" % (float(sp["pitch_mm"]), pmax,
                                                                             "compression" if compression else "tension"))))
    rows.append(("end distance >= %.1f d0 (10.2.4.2)" % k_edge, C._check(k_edge * d0, float(sp["end_mm"]),
                 clause="IS 800:2007 10.2.4.2", cite="end distance %.0f mm >= %.1f x %.0f" % (float(sp["end_mm"]), k_edge, d0))))
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
        s_max = lim * r1
        n_int = max(2, int(math.ceil(L / s_max)) - 1)
        s = L / (n_int + 1)
        chk = C._check(s / r1, lim, clause="IS 800:2007 7.8.1 / 7.8.2",
                       cite="component slenderness between connections s / r_min = %.0f / %.1f <= min(40, 0.6 x %.0f)"
                            % (s, r1, KL_over_r_member or 0.0))
    else:
        s_max = 1000.0
        n_int = max(0, int(math.ceil(L / s_max)) - 1)
        s = L / (n_int + 1)
        chk = C._check(s, s_max, clause="IS 800:2007 10.2.5.4",
                       cite="tension member: interconnections at %.0f mm <= 1000 mm" % s)
    return {"n_intermediate": n_int, "spacing_mm": round(s, 0), "r1_min_mm": r1, "check": chk}


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
    if not chord and sp.get("gusset_t_mm"):
        n = int(sp["n_bolts"])
        p = S.props(sec)
        fy_g = bg.get("fy_gusset_MPa") or _fy_fu(sp.get("gusset_grade") or "E250", sp["gusset_t_mm"])[0]
        wm = C.whitmore_section(t_gusset_mm=float(sp["gusset_t_mm"]), fy_MPa=fy_g,
                                w_start_mm=0.0, L_conn_mm=(n - 1) * float(sp["pitch_mm"]), demand_N=N)
        if wm.get("found"):
            wch = dict(wm["check"])
            rec["checks"].append(_row("gusset yield on the Whitmore width %.0f mm (engineering practice)"
                                      % wm["whitmore_width_mm"], wch))
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


def knee_checks(knee, model_data, cfg, *, nodes, member_capacity):
    """IS 800 12.10.2.1 / 12.10.2.4 at a knee-braced truss portal (OMF).  The truss is pinned on the column cap and
    delivers moment to the column only through the couple of the knee brace and the heel seat, so the 'maximum moment
    that can be delivered by the beam to the joint' (12.10.2.1) is the design strength of the knee brace member,
    N_d = min(Pd, Td), times its lever arm e about the heel: M_del = N_d e.  The joint's connections are checked for
    1.2 M_del (each knee-brace end connection for 1.2 N_d, the force of that couple) and the heel seat for the
    horizontal couple force 1.2 N_d cos(theta) with the 12.10.2.4 shear: the 1.2DL + 0.5LL end reaction plus the
    shear of the design moment, 2 (1.2 M_del) / span.  The Mp alternative of 12.10.2.1 (the smaller governs) is not
    used: a triangular truss has no plastic moment at the column face (zero depth at the heel) -- the knee-brace route
    is the one that can be evaluated (stated in the record)."""
    out = []
    kid = knee.get("id")
    sp_kb = spec_for(cfg, knee.get("brace_role") or "truss_knee_brace", knee.get("brace_section"))
    sp_heel = ((cfg or {}).get("truss_connections") or {}).get("heel")
    geo = knee_geometry(nodes, knee)
    Nd = member_capacity
    if not Nd:
        out.append({"id": "12.10.2.1_knee_connection", "member": kid, "value": None, "limit": None, "dc": None,
                    "ok": None, "clause": "IS 800:2007 12.10.2.1", "source": SRC,
                    "cite": "knee brace design strength not available", "reason": "no member capacity"})
        return out
    M_del = Nd * geo["lever_arm_mm"]
    F = 1.2 * Nd
    base = {"clause": "IS 800:2007 12.10.2.1", "source": SRC, "member": kid}
    note = ("knee-braced truss portal: moment reaches the column through the knee-brace / heel couple; M_del = N_d e = "
            "%.1f kN x %.0f mm = %.1f kN-m (N_d = min(Pd, Td) of the knee brace %s); 1.2 M_del -> 1.2 N_d = %.1f kN "
            "in each knee-brace connection" % (Nd / 1e3, geo["lever_arm_mm"], M_del / 1e6, knee.get("brace_section"),
                                               F / 1e3))
    if sp_kb:
        bg = bolt_group(sp_kb, knee["brace_section"])
        if bg.get("found"):
            c = C._check(F, bg["capacity_N"], clause="IS 800:2007 12.10.2.1 + 10.3.2",
                         cite="knee-brace end bolts %d M%d %s: %.1f kN >= 1.2 N_d = %.1f kN"
                              % (int(sp_kb["n_bolts"]), int(sp_kb["d_mm"]), sp_kb.get("grade", "4.6"),
                                 bg["capacity_N"] / 1e3, F / 1e3))
            out.append(dict(c, id="12.10.2.1_knee_brace_connection", member=kid, note=note, source=SRC))
        else:
            out.append(dict(base, id="12.10.2.1_knee_brace_connection", value=None, limit=None, dc=None, ok=None,
                            cite="knee brace bolt group not evaluated", reason=bg.get("reason")))
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
                         cite="heel seat bolts %d M%d %s: resultant of H = 1.2 N_d cos(theta) = %.1f kN and V = "
                              "1.2DL + 0.5LL %.1f kN + 2 x 1.2 M_del / span %.1f kN -> %.1f kN <= %.1f kN"
                              % (int(sp_heel["n_bolts"]), int(sp_heel["d_mm"]), sp_heel.get("grade", "4.6"), H / 1e3,
                                 V_g / 1e3, V_M / 1e3, R / 1e3, hb["capacity_N"] / 1e3))
            out.append(dict(c, id="12.10.2.4_heel_seat", member=kid, source=SRC,
                            demands={"H_N": H, "V_gravity_N": V_g, "V_moment_N": V_M, "R_N": R}))
        else:
            out.append(dict(base, id="12.10.2.4_heel_seat", clause="IS 800:2007 12.10.2.4", value=None, limit=None,
                            dc=None, ok=None, cite="heel seat bolts not evaluated", reason=str(hb.get("required_inputs"))))
    else:
        out.append(dict(base, id="12.10.2.4_heel_seat", clause="IS 800:2007 12.10.2.4", value=None, limit=None,
                        dc=None, ok=None, cite="cfg['truss_connections']['heel'] or the truss span missing",
                        reason="not declared"))
    for c in out:
        c.setdefault("knee", {"lever_arm_mm": round(geo["lever_arm_mm"], 1), "angle_deg": round(geo["angle_deg"], 1),
                              "N_d_N": round(Nd, 1), "M_del_Nmm": round(M_del, 0)})
    return out
