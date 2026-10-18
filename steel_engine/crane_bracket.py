"""crane_bracket.py -- first wave item 2: the welded crane bracket at the column face.

A crane bracket is a short welded I cantilever from the column flange to the gantry girder seat.  The engine already
checks the bracket section for its vertical moment and shear as a declared secondary member; this module adds what a
checking engineer asks for next, at the column face, under the IS 800:2007 Table 4 crane rows.  Load path (the usual
Indian detail): the gantry girder sits on the bracket top flange (the seat) and its top flange is tied to the column
at rail level, so the moments of the surge and traction about the seat are taken by the girder and the tie, and the
bracket receives at the seat:

  V  the girder reaction (crane with the girder impact of IS 875-2 6.3(a), plus the gantry girder and rail) at the
     projection e  -> Mz = V e;
  H  the surge (IS 875-2 6.3(c)) as an axial force along the bracket, at the seat d/2 above the bracket axis
     -> N = H, Mz += H d/2 (conservative: the rail-level tie normally takes it);
  T  the traction (IS 875-2 6.3(d)) along the runway at the seat -> lateral bending of the bracket TOP FLANGE as a
     cantilever of length e, M_f = T e, resisted by the flange alone (Zp,f = tf bf^2 / 4).

Surge and traction are not simultaneous (IS 875-2 6.4.3 Note), so each crane row is checked twice.  Checks:

  1. bracket section: N/Nd + Mz/Mdz (8.2.1.3 high shear) + M_f/Md,f (top flange) <= 1 (9.3.1.1 linear form);
  2. bracket web shear V <= Vd (8.4.1);
  3. the fillet weld group at the column face: flanges welded both sides, web both sides; resultant stress from N, Mz,
     My = T e, V and the torsion T d/2 of the seat force about the group centroid, IS 800 10.5.10.1.1
     fe = sqrt(fa^2 + 3 q^2) <= fu / (sqrt(3) gamma_mw);
  4. the column web opposite the bracket compression flange: 8.7.4 web bearing (b1 + n2) tw fyw / gamma_m0 with
     b1 = bracket flange thickness and n2 = 5 (column flange thickness + weld leg) for a load away from the column
     end, plus a declared stiffener pair (A_st fy / gamma_m0).

Input: cfg['crane']['bracket'] = {
    'section': 'WI600X250X16X10',           # bracket root section at the column face
    'projection_mm': 475.0,                  # column face to the rail centreline (e)
    'rail_height_mm': 600.0,                 # seat to the rail top (girder depth + rail): recorded, not used in the checks
    'dead_N': 9500.0,                        # gantry girder + rail on one bracket (unfactored)
    'weld_leg_mm': 8.0, 'electrode_fu_MPa': 410.0, 'gamma_mw': 1.25,
    'column_section': 'WI550X250X16X8',
    'column_stiffeners': {'b_mm': 115, 't_mm': 12, 'n': 2, 'fy_MPa': 250},   # optional
    'fy_MPa': 250.0 }
Units N, mm, MPa.  Returns one connection record (pkg['connections'] format) or None when not declared.
"""
from __future__ import annotations

import math

import sections as S

GAMMA_M0 = 1.10

CRANE_ROWS = (("1.5DL+1.5CL (crane leading)", 1.5, 1.5),
              ("1.2DL+1.2LL+1.05CL+0.6WL", 1.2, 1.05))


def _row(name, value, limit, clause, cite, **extra):
    dc = (value / limit) if (isinstance(value, (int, float)) and isinstance(limit, (int, float)) and limit) else None
    r = {"name": name, "value": value, "limit": limit, "dc": dc, "ok": (dc <= 1.0) if dc is not None else None,
         "clause": clause, "cite": cite, "source": "crane_bracket"}
    r.update(extra)
    return r


def bracket_record(cfg):
    cr = (cfg or {}).get("crane") or {}
    br = cr.get("bracket")
    if not br:
        return None
    import india_loads as IL
    R = IL.crane_reactions(cr)
    sec = br["section"]
    p = S.props(sec)
    d, bf, tf, tw = p["d"], p["bf"], p["tf"], p["tw"]
    fy = float(br.get("fy_MPa") or 250.0)
    e = float(br["projection_mm"])
    h = float(br.get("rail_height_mm") or 0.0)
    Wd = float(br.get("dead_N") or 0.0)
    V_cr = (1.0 + R["impact_girder"]) * R["col_Rmax_N"]          # bracket = support of the girder: girder impact
    H_cr = R["col_surge_N"]
    T_cr = R["col_traction_N"]
    # section capacities (welded / rolled I: plastic modulus, compact or plastic assumed -> class gate below)
    Zpz = p.get("Zx") or p.get("Zpz_mm3")
    Zpy = p.get("Zy") or p.get("Zpy_mm3") or (tf * bf ** 2 / 2.0 + (d - 2 * tf) * tw ** 2 / 4.0)
    Mdz = Zpz * fy / GAMMA_M0
    Mdy = Zpy * fy / GAMMA_M0
    Mdf = (tf * bf ** 2 / 4.0) * fy / GAMMA_M0          # top flange alone about its own vertical axis
    Av = d * tw
    Vd = Av * fy / (math.sqrt(3.0) * GAMMA_M0)
    Nd = p["A"] * fy / GAMMA_M0
    tau_d = fy / (math.sqrt(3.0) * GAMMA_M0)
    # weld group (unit throat)
    s_w = float(br.get("weld_leg_mm") or 8.0)
    a_w = 0.7 * s_w
    fu_w = min(float(br.get("electrode_fu_MPa") or 410.0), float(br.get("parent_fu_MPa") or 410.0))
    g_mw = float(br.get("gamma_mw") or 1.25)
    f_wd = fu_w / (math.sqrt(3.0) * g_mw)
    Lf = 2.0 * bf - tw                                     # one flange, both sides
    Lw = 2.0 * (d - 2.0 * tf)                              # web, both sides
    Lt = 2.0 * Lf + Lw
    Iwz = 2.0 * Lf * ((d - tf) / 2.0) ** 2 + 2.0 * (d - 2.0 * tf) ** 3 / 12.0
    Iwy = 2.0 * 2.0 * bf ** 3 / 12.0 + Lw * (tw / 2.0) ** 2
    Jw = Iwz + Iwy
    rmax = math.hypot(d / 2.0, bf / 2.0)
    # column web
    col = br.get("column_section")
    pc = S.props(col) if col else None
    st = br.get("column_stiffeners") or {}
    A_st = float(st.get("b_mm") or 0.0) * float(st.get("t_mm") or 0.0) * int(st.get("n") or 0)
    fy_st = float(st.get("fy_MPa") or 250.0)
    fyc = float(br.get("column_fy_MPa") or 350.0)

    rows = []
    worst = {}
    for lab, fD, fC in CRANE_ROWS:
        V = fD * Wd + fC * V_cr
        for hz, (N, Th) in (("surge", (fC * H_cr, 0.0)), ("traction", (0.0, fC * T_cr))):
            Mz = V * e + N * d / 2.0
            My = Th * e                                  # traction at the seat: top-flange lateral bending
            Tq = Th * d / 2.0                            # seat force about the weld-group centroid
            # 8.2.1.3 high shear
            beta = (2.0 * V / Vd - 1.0) ** 2 if V > 0.6 * Vd else 0.0
            Mdz_v = Mdz - beta * (Mdz - (Zpz - Av * d / 4.0) * fy / GAMMA_M0) if beta else Mdz
            inter = N / Nd + Mz / Mdz_v + My / Mdf
            tau = V / Av
            fa = N / (Lt * a_w) + Mz * (d / 2.0) / (Iwz * a_w) + My * (bf / 2.0) / (Iwy * a_w)
            q = math.hypot(V / (Lw * a_w), Tq * rmax / (Jw * a_w))
            fe = math.sqrt(fa ** 2 + 3.0 * q ** 2)
            cases = {
                "interaction": (inter, 1.0),
                "shear": (tau, tau_d),
                "weld": (fe, f_wd),
            }
            if pc:
                Fc = Mz / (d - tf) + N / 2.0
                Fw = (tf + 5.0 * (pc["tf"] + s_w)) * pc["tw"] * fyc / GAMMA_M0 + A_st * fy_st / GAMMA_M0
                cases["column_web"] = (Fc / 1e3, Fw / 1e3)        # kN
            for k_, (v_, l_) in cases.items():
                if k_ not in worst or v_ / l_ > worst[k_][0]:
                    worst[k_] = (v_ / l_, v_, l_, lab, hz, V, N, Mz, My, Tq)
    labels = {
        "interaction": ("bracket section N/Nd + Mz/Mdz + Mf/Md,f at the column face (8.2.1.3 high shear)",
                        "IS 800:2007 8.2.1.2 / 8.2.1.3 / 9.3.1.1",
                        "Mz = V e + H d/2 (surge at the seat), Mf = T e on the top flange alone (traction at the "
                        "seat); Md = Zp fy / gamma_m0, Md,f = (tf bf^2 / 4) fy / gamma_m0"),
        "shear": ("bracket web shear stress V / (d tw) (MPa)", "IS 800:2007 8.4.1",
                  "tau = V / (d tw) <= fy / (sqrt 3 gamma_m0)"),
        "weld": ("fillet weld group at the column face, combined fe (MPa)", "IS 800:2007 10.5.7 / 10.5.10.1.1",
                 "throat 0.7 s = %.1f mm; flanges and web welded both sides; fe = sqrt(fa^2 + 3 q^2) <= fu / "
                 "(sqrt 3 gamma_mw), fu %.0f MPa, gamma_mw %.2f" % (a_w, fu_w, g_mw)),
        "column_web": ("column web opposite the bracket compression flange, F = Mz/(d - tf) + N/2 (kN)", "IS 800:2007 8.7.4",
                       "Fw = (b1 + n2) tw fyw / gamma_m0, b1 = %.0f mm, n2 = 5 (tf,c + s) = %.0f mm%s"
                       % (tf, 5.0 * ((pc or {}).get("tf", 0.0) + s_w),
                          ("; + stiffener pair A_st fy / gamma_m0 = %.0f kN" % (A_st * fy_st / GAMMA_M0 / 1e3)) if A_st else "")),
    }
    for k_, (r_, v_, l_, lab, hz, V, N, Mz, My, Tq) in worst.items():
        nm, cl, ct = labels[k_]
        rows.append(_row(nm, v_, l_, cl, ct + "; %s, %s case: V %.1f kN, N %.1f kN, Mz %.1f kN-m, My %.1f kN-m, "
                         "T d/2 %.2f kN-m" % (lab, hz, V / 1e3, N / 1e3, Mz / 1e6, My / 1e6, Tq / 1e6), combo=lab))
    gov = max(rows, key=lambda r_: r_["dc"] or 0.0)
    return {"id": "conn-crane-bracket", "type": "crane bracket (welded cantilever at the column face)", "section": sec,
            "demand": {"V_crane_N": round(V_cr, 1), "H_surge_N": round(H_cr, 1), "T_traction_N": round(T_cr, 1),
                       "dead_N": round(Wd, 1), "projection_mm": e, "rail_height_mm": h},
            "inputs": {k: v for k, v in br.items()},
            "checks": rows, "DC": gov["dc"], "governing_check": gov["name"], "clause": gov["clause"],
            "limit_state": "IS 800:2007 8 / 9.3 / 10.5 / 8.7.4", "cited": gov["clause"], "notes": [],
            "design_basis": "IS 875 (Part 2):1987 6.3 crane loads (girder impact, surge, traction; surge and traction "
                            "not simultaneous, 6.4.3 Note); IS 800:2007 Table 4 crane rows; girder seated on the "
                            "bracket top flange, girder top flange tied to the column at rail level (moments of the "
                            "rail-level forces about the seat taken by the girder and the tie)"}
