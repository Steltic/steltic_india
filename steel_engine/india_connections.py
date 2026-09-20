"""IS 800:2007 connection and column-base capacities (WP2.5; review HR800-09/10/11/12, HREX1-X-06/07).

Units: N, mm, MPa. Every function returns a dict with the inputs, the clause, and found:false (never an invented
number) when a geometric/material input is missing. Capacities are NEVER sized from demand.

Clauses read from the IS 800:2007 PDF: 10.3.2-10.3.6 (bearing bolts), 10.4.3 + Table 20 (slip), 10.5.3.2 + Table 22
(fillet throat K), 10.5.7.1.1 / 10.5.7.2 / 10.5.7.3 (weld strength, site gamma_mw, long joints), Table 5 (gamma),
6.4.1 (block shear), 7.4.1 / 7.4.3.1 (column bases, 0.6 fck, slab thickness), 12.4.1-12.4.3, 12.12.
The Whitmore 30-degree spread is ENGINEERING PRACTICE (not an IS 800 clause) and is labelled as such.
"""
from __future__ import annotations

import math
from typing import Any, Dict, Optional

GAMMA_M0 = 1.10
GAMMA_M1 = 1.25
GAMMA_MB = 1.25            # Table 5 bolts, bearing type (shop and field)
GAMMA_MF_SERVICE = 1.10    # 10.4.3 slip resistance designed at service load
GAMMA_MF_ULTIMATE = 1.25   # 10.4.3 slip resistance designed at ultimate load
GAMMA_MW_SHOP = 1.25       # Table 5 welds, shop
GAMMA_MW_SITE = 1.50       # Table 5 welds, field; 10.5.7.2
E_MPA = 2.0e5

# IS 4000:1992 Table 2 col (2)/(3): stress area of bolt, shank / thread (mm2) (pdf p.4)
IS4000_STRESS_AREA_MM2 = {16: (201.0, 157.0), 20: (314.0, 245.0), 24: (452.0, 353.0), 30: (706.0, 561.0),
                          36: (1017.0, 817.0)}
# IS 800 Table 20 typical coefficient of friction mu_f (10.4.3)
TABLE20_MU_F = {
    "not_treated": 0.20, "blasted_short_or_grit_loose_rust_removed": 0.50, "blasted_hot_dip_galvanized": 0.10,
    "blasted_zinc_spray_50_70um": 0.25, "blasted_ethylzinc_silicate_30_60um": 0.30, "sand_blasted_after_light_rusting": 0.52,
    "blasted_ethylzinc_silicate_60_80um": 0.30, "blasted_alkalizinc_silicate_60_80um": 0.30,
    "blasted_aluminium_spray_gt_50um": 0.50, "clean_mill_scale": 0.33, "sand_blasted": 0.48, "red_lead_painted": 0.10,
}
# IS 800 Table 22: K for angle between fusion faces
TABLE22_K = [((60, 90), 0.70), ((91, 100), 0.65), ((101, 106), 0.60), ((107, 113), 0.55), ((114, 120), 0.50)]


def _check(value, limit, *, clause, cite, dc=None, ok=None, **extra):
    """Uniform structured result {value, limit, dc, ok, clause, cite, source}."""
    if dc is None and value is not None and limit not in (None, 0):
        dc = abs(value) / limit
    if ok is None and dc is not None:
        ok = dc <= 1.0
    out = {"value": value, "limit": limit, "dc": dc, "ok": ok, "clause": clause, "cite": cite,
           "source": "steel_engine/india_connections.py"}
    out.update(extra)
    return out


def bolt_material(grade, fub=None, fyb=None):
    """Property class 'x.y' -> nominal fub = 100x, fyb = 10xy MPa (IS 1367 Part 3 designation); overrides win."""
    if fub and fyb:
        return float(fub), float(fyb), "user fub/fyb"
    try:
        a, b = str(grade).split(".")
        return (float(fub) if fub else 100.0 * float(a)), (float(fyb) if fyb else 10.0 * float(a) * float(b)), \
            "property class %s nominal (IS 1367 Part 3 designation)" % grade
    except Exception:
        return None, None, "unknown bolt grade %r" % (grade,)


def bolt_areas(d_mm, Anb_mm2=None, Asb_mm2=None):
    """Anb: tensile stress area at the thread (IS 4000 Table 2 col 3); Asb = nominal plain shank area pi d^2/4."""
    if Anb_mm2 is None and d_mm is not None and int(d_mm) in IS4000_STRESS_AREA_MM2 and float(d_mm) == int(d_mm):
        Anb_mm2 = IS4000_STRESS_AREA_MM2[int(d_mm)][1]
    if Asb_mm2 is None and d_mm:
        Asb_mm2 = math.pi * float(d_mm) ** 2 / 4.0
    return Anb_mm2, Asb_mm2


def bolt_capacity_is800(d_mm, grade="8.8", *, nn=1, ns=0, t_mm=None, fu_plate_MPa=None, e_mm=None, p_mm=None,
                        d0_mm=None, lj_mm=None, lg_mm=None, t_pk_mm=None, hole="standard", V_N=None, T_N=None,
                        Anb_mm2=None, Asb_mm2=None, fub_MPa=None, fyb_MPa=None, gamma_mb=GAMMA_MB,
                        end_bolt=True):
    """Design strength of ONE bearing-type bolt, IS 800:2007 10.3.

    10.3.3 Vdsb = fub/sqrt3 (nn Anb + ns Asb)/gamma_mb x beta_lj (10.3.3.1) x beta_lg (10.3.3.2) x beta_pk (10.3.3.3)
    10.3.4 Vdpb = 2.5 kb d t fu/gamma_mb; kb = min(e/3d0, p/3d0 - 0.25, fub/fu, 1.0); x0.7 oversize/short slot,
           x0.5 long slot. (Interior bolt: pass end_bolt=False to drop the e term; e/p both needed otherwise.)
    10.3.5 Tdb = 0.9 fub An/gamma_mb <= fyb Asb (gamma_mb/gamma_m0)/gamma_mb
    10.3.6 (V/Vdb)^2 + (T/Tdb)^2 <= 1
    """
    fub, fyb, mat_src = bolt_material(grade, fub_MPa, fyb_MPa)
    Anb, Asb = bolt_areas(d_mm, Anb_mm2, Asb_mm2)
    out = {"d_mm": d_mm, "grade": grade, "fub_MPa": fub, "fyb_MPa": fyb, "material_basis": mat_src,
           "Anb_mm2": Anb, "Asb_mm2": Asb, "nn": nn, "ns": ns, "gamma_mb": gamma_mb,
           "cite": "IS 800:2007 10.3.3-10.3.6; Table 5 gamma_mb", "source": "steel_engine/india_connections.py"}
    if not (fub and d_mm and (Anb or nn == 0) and Asb):
        out.update(found=False, required_inputs=["d_mm", "grade/fub", "Anb (thread stress area)"])
        return out
    Vnsb = fub / math.sqrt(3.0) * ((nn * Anb if nn else 0.0) + ns * Asb)
    red = {}
    if lj_mm is not None and lj_mm > 15 * d_mm:
        red["beta_lj"] = min(max(1.075 - lj_mm / (200.0 * d_mm), 0.75), 1.0)
    if lg_mm is not None and lg_mm > 5 * d_mm:
        if lg_mm > 8 * d_mm:
            out["grip_note"] = "10.3.3.2: grip length shall in no case exceed 8d (%.0f > %.0f)" % (lg_mm, 8 * d_mm)
        blg = 8.0 * d_mm / (3.0 * d_mm + lg_mm)
        red["beta_lg"] = min(blg, red.get("beta_lj", 1.0))
    if t_pk_mm is not None and t_pk_mm > 6:
        red["beta_pk"] = 1.0 - 0.0125 * t_pk_mm
    fac = 1.0
    for v in red.values():
        fac *= v
    Vdsb = Vnsb / gamma_mb * fac
    out.update(Vnsb_N=Vnsb, reductions=red, Vdsb_N=Vdsb)
    # bearing
    bearing_missing = [n for n, v in (("t_mm", t_mm), ("fu_plate_MPa", fu_plate_MPa), ("d0_mm", d0_mm),
                                      ("p_mm", p_mm)) if v is None]
    if end_bolt and e_mm is None:
        bearing_missing.append("e_mm")
    if bearing_missing:
        out.update(found=False, Vdpb_N=None, Vdb_N=None, required_inputs=bearing_missing,
                   note="bearing 10.3.4 needs plate t, fu, e, p, d0: bolt shear alone is not the bolt capacity")
    else:
        terms = {"p/3d0-0.25": p_mm / (3 * d0_mm) - 0.25, "fub/fu": fub / fu_plate_MPa, "1.0": 1.0}
        if end_bolt:
            terms["e/3d0"] = e_mm / (3 * d0_mm)
        kb = min(terms.values())
        hole_f = {"standard": 1.0, "oversize": 0.7, "short_slot": 0.7, "long_slot": 0.5}.get(hole, 1.0)
        Vnpb = 2.5 * kb * d_mm * t_mm * fu_plate_MPa * hole_f
        Vdpb = Vnpb / gamma_mb
        out.update(kb=kb, kb_terms=terms, hole_factor=hole_f, Vnpb_N=Vnpb, Vdpb_N=Vdpb, Vdb_N=min(Vdsb, Vdpb),
                   found=True)
    # tension
    if Anb and fyb:
        Tnb = min(0.9 * fub * Anb, fyb * Asb * gamma_mb / GAMMA_M0)
        out.update(Tnb_N=Tnb, Tdb_N=Tnb / gamma_mb)
    if V_N is not None and out.get("Vdb_N"):
        out["shear_check"] = _check(abs(V_N), out["Vdb_N"], clause="IS 800:2007 10.3.2", cite="Vsb <= Vdb")
    if T_N is not None and out.get("Tdb_N"):
        out["tension_check"] = _check(abs(T_N), out["Tdb_N"], clause="IS 800:2007 10.3.5", cite="Tb <= Tdb")
    if V_N is not None and T_N is not None and out.get("Vdb_N") and out.get("Tdb_N"):
        r = (abs(V_N) / out["Vdb_N"]) ** 2 + (abs(T_N) / out["Tdb_N"]) ** 2
        out["combined_check"] = _check(r, 1.0, clause="IS 800:2007 10.3.6", cite="(V/Vdb)^2 + (T/Tdb)^2 <= 1")
    return out


def bolt_group_capacity_is800(n_bolts, d_mm, grade="8.8", *, V_N=None, **kw):
    """n x min(Vdsb, Vdpb) for a concentrically loaded bolt group (10.3.2). Long-joint beta_lj via lj_mm."""
    one = bolt_capacity_is800(d_mm, grade, **kw)
    if not one.get("found") or not n_bolts:
        return {"found": False, "capacity_N": None, "per_bolt": one, "cite": one.get("cite"),
                "required_inputs": one.get("required_inputs") or ["n_bolts"]}
    cap = int(n_bolts) * one["Vdb_N"]
    out = {"found": True, "capacity_N": cap, "n_bolts": int(n_bolts), "per_bolt": one,
           "cite": "IS 800:2007 10.3.2 (Vdb = min(Vdsb, Vdpb)) x n"}
    if V_N is not None:
        out["check"] = _check(abs(V_N), cap, clause="IS 800:2007 10.3.2", cite="bolt group shear/bearing")
    return out


def hsfg_slip_capacity(d_mm, grade="8.8", *, mu_f=None, surface=None, n_e=1, Kh=1.0, gamma_mf=GAMMA_MF_ULTIMATE,
                       Anb_mm2=None, fub_MPa=None, lj_mm=None, V_N=None):
    """IS 800 10.4.3: Vdsf = mu_f n_e Kh F0 / gamma_mf, F0 = Anb x 0.70 fub; 10.4.3.1 long joints (beta_lj).
    gamma_mf 1.10 when slip is designed at service load, 1.25 at ultimate load. mu_f from Table 20."""
    fub, _, src = bolt_material(grade, fub_MPa, None)
    Anb, _ = bolt_areas(d_mm, Anb_mm2, None)
    if mu_f is None and surface:
        mu_f = TABLE20_MU_F.get(surface)
    cite = "IS 800:2007 10.4.3 (Vnsf = mu_f ne Kh F0, F0 = 0.7 fub Anb), Table 20 mu_f"
    if not (fub and Anb and mu_f):
        return {"found": False, "Vdsf_N": None, "cite": cite,
                "required_inputs": ["d_mm/Anb", "grade/fub", "mu_f (Table 20 surface treatment)"]}
    F0 = Anb * 0.70 * fub
    Vnsf = mu_f * n_e * Kh * F0
    blj = min(max(1.075 - lj_mm / (200.0 * d_mm), 0.75), 1.0) if (lj_mm and lj_mm > 15 * d_mm) else 1.0
    Vdsf = Vnsf / gamma_mf * blj
    out = {"found": True, "F0_N": F0, "Vnsf_N": Vnsf, "Vdsf_N": Vdsf, "mu_f": mu_f, "n_e": n_e, "Kh": Kh,
           "gamma_mf": gamma_mf, "beta_lj": blj, "material_basis": src, "cite": cite}
    if V_N is not None:
        out["check"] = _check(abs(V_N), Vdsf, clause="IS 800:2007 10.4.3", cite="Vsf <= Vdsf")
    return out


def table22_K(angle_deg=90.0):
    for (lo, hi), K in TABLE22_K:
        if lo <= float(angle_deg) <= hi:
            return K
    return None


def fillet_weld_capacity_is800_N(*, size_mm=None, length_mm=None, fu_MPa=None, n_sides=1, angle_deg=90.0,
                                 site=False, lj_mm=None, throat_mm=None, gamma_mw=None, demand_N=None, cite=None):
    """IS 800 LSD fillet weld: throat = K s (Table 22, K 0.70 at 60-90 deg) - never s/sqrt2; fwd = fu/(sqrt3 gamma_mw)
    (10.5.7.1.1), gamma_mw 1.25 shop / 1.50 site (Table 5, 10.5.7.2); long joint beta_lw = 1.2 - 0.2 lj/(150 tt)
    <= 1.0 when lj > 150 tt (10.5.7.3). length_mm = EFFECTIVE length (10.5.4.1) per side."""
    miss = []
    K = table22_K(angle_deg)
    if throat_mm is None:
        if size_mm is None:
            miss.append("size_mm (or throat_mm)")
        elif K is None:
            miss.append("angle between fusion faces within Table 22 (60-120 deg)")
        else:
            throat_mm = K * float(size_mm)
    if not fu_MPa:
        miss.append("fu_MPa (smaller of weld and parent metal, 10.5.7.1.1)")
    if not length_mm:
        miss.append("length_mm (effective)")
    cite = cite or "IS 800:2007 10.5.3.2 + Table 22 (K), 10.5.7.1.1 fwd = fu/(sqrt3 gamma_mw), Table 5"
    if miss:
        return {"found": False, "capacity_N": None, "cite": cite, "required_inputs": miss}
    gmw = gamma_mw if gamma_mw is not None else (GAMMA_MW_SITE if site else GAMMA_MW_SHOP)
    fwd = float(fu_MPa) / (math.sqrt(3.0) * gmw)
    blw = 1.0
    if lj_mm is not None and lj_mm > 150 * throat_mm:
        blw = min(1.2 - 0.2 * lj_mm / (150.0 * throat_mm), 1.0)
    cap = fwd * blw * throat_mm * float(length_mm) * int(n_sides or 1)
    out = {"found": True, "capacity_N": cap, "throat_mm": throat_mm, "K": K, "fwd_MPa": fwd, "gamma_mw": gmw,
           "site": bool(site), "beta_lw": blw, "length_mm": float(length_mm), "n_sides": int(n_sides or 1),
           "size_mm": size_mm, "fu_MPa": float(fu_MPa), "cite": cite, "method": "LSD"}
    if demand_N is not None:
        out["check"] = _check(abs(demand_N), cap, clause="IS 800:2007 10.5.7", cite="fillet weld")
    return out


def cjp_weld_gate(weld_type, *, location="beam_column", sfrs=True, eor_exception=None):
    """IS 800 12.4.2: welds in frames resisting EQ shall be complete penetration butt welds, except column splices
    (12.5.2). Fillet welds fail the gate unless an EOR exception is recorded (it is reported, never silently OK)."""
    clause = "IS 800:2007 12.4.2"
    cite = "welds in EQ-resisting frames: complete penetration butt welds, except column splices"
    if not sfrs:
        return _check(None, None, clause=clause, cite=cite, ok=True, note="not part of the SFRS")
    if weld_type is None:
        return _check(None, None, clause=clause, cite=cite, ok=None, reason="weld type not declared")
    wt = str(weld_type).lower()
    if "splice" in str(location).lower():
        return _check(None, None, clause=clause + " / 12.5.2", cite=cite, ok=True,
                      note="column splice: PJP permitted per 12.5.2 (200 % strength, 1.2 fy Af flange force)")
    if wt in ("cjp", "complete_penetration", "complete penetration butt", "full_penetration", "full penetration"):
        return _check(None, None, clause=clause, cite=cite, ok=True, weld_type=weld_type)
    if eor_exception:
        return _check(None, None, clause=clause, cite=cite, ok=False, weld_type=weld_type,
                      eor_exception=eor_exception,
                      note="EOR exception recorded; 12.4.2 is not met as written - status stays PARTIAL")
    return _check(None, None, clause=clause, cite=cite, ok=False, weld_type=weld_type,
                  reason="%s weld in an SFRS connection (12.4.2 requires CJP)" % weld_type)


def no_load_sharing_gate(bolts_and_welds_same_faying_surface):
    """IS 800 12.4.3: bolts shall not share load with welds on the same faying surface."""
    if bolts_and_welds_same_faying_surface is None:
        return _check(None, None, clause="IS 800:2007 12.4.3", cite="no bolt/weld load sharing", ok=None,
                      reason="load path not declared")
    return _check(None, None, clause="IS 800:2007 12.4.3", cite="no bolt/weld load sharing",
                  ok=not bool(bolts_and_welds_same_faying_surface))


def hsfg_gate(bolt_type):
    """IS 800 12.4.1: bolts in EQ-resisting frames fully tensioned HSFG or turned-and-fitted."""
    clause, cite = "IS 800:2007 12.4.1", "fully tensioned HSFG or turned and fitted bolts"
    if bolt_type is None:
        return _check(None, None, clause=clause, cite=cite, ok=None, reason="bolt type not declared")
    bt = str(bolt_type).lower()
    return _check(None, None, clause=clause, cite=cite,
                  ok=("hsfg" in bt or "friction" in bt or "turned" in bt or "fitted" in bt), bolt_type=bolt_type)


# ------------------------------------------------------------------- block shear / Whitmore / gusset buckling
def block_shear(*, Avg_mm2=None, Avn_mm2=None, Atg_mm2=None, Atn_mm2=None, fy_MPa=None, fu_MPa=None,
                demand_N=None):
    """IS 800 6.4.1: minimum of BOTH expressions; found:false when any of the four areas is missing."""
    import india_is800 as _I
    r = _I.block_shear_6_4_1(Avg_mm2=Avg_mm2, Avn_mm2=Avn_mm2, Atg_mm2=Atg_mm2, Atn_mm2=Atn_mm2,
                             fy_MPa=fy_MPa, fu_MPa=fu_MPa)
    if r["found"] and demand_N is not None:
        r["check"] = _check(abs(demand_N), r["Tdb_N"], clause="IS 800:2007 6.4.1", cite="block shear")
    return r


def block_shear_bolted_areas(*, t_mm, n_rows, pitch_mm, end_mm, d0_mm, edge_mm=None, n_lines=1, gauge_mm=None,
                             pattern=None):
    """Areas for a bolted end connection with n_rows bolts along the load in n_lines lines.
    pattern 'L' (single line: one shear plane + tension to the free edge) or 'U' (two shear planes + tension
    between outer lines). Returns Avg, Avn, Atg, Atn (mm2)."""
    Ls = end_mm + (n_rows - 1) * pitch_mm
    pattern = pattern or ("L" if n_lines == 1 else "U")
    if pattern == "L":
        if edge_mm is None:
            return {"found": False, "required_inputs": ["edge_mm"]}
        Avg = Ls * t_mm
        Avn = (Ls - (n_rows - 0.5) * d0_mm) * t_mm
        Atg = edge_mm * t_mm
        Atn = (edge_mm - 0.5 * d0_mm) * t_mm
    else:
        if gauge_mm is None:
            return {"found": False, "required_inputs": ["gauge_mm"]}
        Avg = 2 * Ls * t_mm
        Avn = 2 * (Ls - (n_rows - 0.5) * d0_mm) * t_mm
        Atg = (n_lines - 1) * gauge_mm * t_mm
        Atn = ((n_lines - 1) * gauge_mm - (n_lines - 1) * d0_mm) * t_mm
    return {"found": True, "Avg_mm2": Avg, "Avn_mm2": Avn, "Atg_mm2": Atg, "Atn_mm2": Atn, "pattern": pattern}


WHITMORE_CITE = ("Whitmore 30-degree effective width: ENGINEERING PRACTICE (not an IS 800 clause); "
                 "yield per IS 800:2007 6.2 (fy/gamma_m0)")


def whitmore_section(*, t_gusset_mm, fy_MPa, w_start_mm=None, L_conn_mm=None, whitmore_width_mm=None,
                     available_width_mm=None, demand_N=None):
    """Whitmore width bw = w + 2 L tan30 (capped by the available gusset width); Tdw = bw t fy/gamma_m0."""
    bw = whitmore_width_mm
    if bw is None and w_start_mm is not None and L_conn_mm is not None:
        bw = float(w_start_mm) + 2.0 * float(L_conn_mm) * math.tan(math.radians(30.0))
    if bw is None or not t_gusset_mm or not fy_MPa:
        return {"found": False, "capacity_N": None, "cite": WHITMORE_CITE,
                "required_inputs": ["whitmore_width_mm or (w_start_mm + L_conn_mm)", "t_gusset_mm", "fy_MPa"]}
    if available_width_mm:
        bw = min(bw, float(available_width_mm))
    cap = bw * t_gusset_mm * fy_MPa / GAMMA_M0
    out = {"found": True, "whitmore_width_mm": bw, "capacity_N": cap, "cite": WHITMORE_CITE,
           "basis": "engineering practice"}
    if demand_N is not None:
        out["check"] = _check(abs(demand_N), cap, clause="IS 800:2007 6.2 (on Whitmore width; engineering practice)",
                              cite=WHITMORE_CITE)
    return out


def whitmore_buckling(*, whitmore_width_mm, t_gusset_mm, fy_MPa, L_unbraced_mm, K=None, demand_N=None):
    """Gusset compression on the Whitmore width (12.7.3.4 / 12.8.3.4 'gusset plates checked for buckling out of
    their plane'): IS 800 7.1.2 with class c (solid section, Table 10), r = t/sqrt12. K is an EOR input
    (engineering practice, e.g. 0.65 for a compact corner gusset, 1.2 where the gusset end can sway) - no default."""
    import india_is800 as _I
    cite = "IS 800:2007 12.7.3.4 / 12.8.3.4; 7.1.2 class c on the Whitmore width (engineering practice model)"
    if K is None or not (whitmore_width_mm and t_gusset_mm and fy_MPa and L_unbraced_mm):
        return {"found": False, "Pd_N": None, "cite": cite,
                "required_inputs": ["whitmore_width_mm", "t_gusset_mm", "fy_MPa", "L_unbraced_mm", "K (EOR)"]}
    r = t_gusset_mm / math.sqrt(12.0)
    A = whitmore_width_mm * t_gusset_mm
    pd = _I.design_compressive_strength(A, fy_MPa, K * L_unbraced_mm, r, buckling_class="c")
    pd["cite"] = cite
    if demand_N is not None and pd.get("found"):
        pd["check"] = _check(abs(demand_N), pd["Pd_N"], clause="IS 800:2007 12.7.3.4/12.8.3.4 + 7.1.2", cite=cite)
    return pd


# ------------------------------------------------------------------- column bases (7.4, 10.3.5/6, 12.12)
def base_plate_thickness_7_4_3_1(*, w_MPa, a_mm, b_mm, fy_MPa, tf_col_mm=None, t_prov_mm=None, c_mm=None):
    """IS 800 7.4.3.1 ts = sqrt(2.5 w (a^2 - 0.3 b^2) gamma_m0/fy) > tf (c^2 when the effective area of 7.4.1.1 is
    used). DC = (t_req/t_prov)^2 (strength ratio)."""
    term = (c_mm ** 2) if c_mm is not None else (a_mm ** 2 - 0.3 * b_mm ** 2)
    ts = math.sqrt(max(2.5 * w_MPa * term * GAMMA_M0 / fy_MPa, 0.0))
    t_req = max(ts, tf_col_mm or 0.0)
    out = {"found": True, "ts_mm": ts, "t_required_mm": t_req, "w_MPa": w_MPa, "a_mm": a_mm, "b_mm": b_mm,
           "cite": "IS 800:2007 7.4.3.1 ts = sqrt(2.5 w (a^2-0.3b^2) gamma_m0/fy) > tf"}
    if t_prov_mm:
        # DC on the REQUIRED thickness (ts with the tf floor of 7.4.3.1), so that value / limit and dc agree
        # (WP6-fix: dc used ts alone and disagreed with the stored value/limit pair whenever tf > ts)
        out["check"] = _check(t_req ** 2, t_prov_mm ** 2, dc=(t_req / t_prov_mm) ** 2, clause="IS 800:2007 7.4.3.1",
                              cite="DC = (t_req/t_prov)^2 (value/limit are the squared thicknesses, mm2; t_req = max(ts, tf))",
                              t_req_mm=t_req, t_prov_mm=t_prov_mm, ts_mm=ts)
        out["check"]["ok"] = (t_req / t_prov_mm) ** 2 <= 1.0 and (tf_col_mm is None or t_prov_mm > tf_col_mm)
        out["ts_gt_tf"] = None if tf_col_mm is None else t_prov_mm > tf_col_mm
    return out


def _bearing_linear(P, M, B, L, f_anchor, As_t, n_mod):
    """Linear (elastic) bearing with anchor tension: solve Y^3 + K1 Y^2 + K2 Y + K3 = 0 (e > L/6)."""
    e = M / P
    K1 = 3.0 * (e - L / 2.0)
    K2 = 6.0 * n_mod * As_t / B * (f_anchor + e)
    K3 = -K2 * (L / 2.0 + f_anchor)
    lo, hi = 1e-6, L
    fn = lambda y: y ** 3 + K1 * y ** 2 + K2 * y + K3
    if fn(lo) * fn(hi) > 0:
        return None
    for _ in range(200):
        mid = 0.5 * (lo + hi)
        if fn(lo) * fn(mid) <= 0:
            hi = mid
        else:
            lo = mid
    Y = 0.5 * (lo + hi)
    C = (M + P * f_anchor) / (L / 2.0 + f_anchor - Y / 3.0)
    T = C - P
    fp = 2.0 * C / (B * Y)
    return {"Y_mm": Y, "C_N": C, "T_N": T, "fp_max_MPa": fp, "e_mm": e}


IS456_EC_CITE = "IS 456:2000 6.2.3.1: Ec = 5000 sqrt(fck) (short-term static modulus, MPa)"


def ec_is456(fck_MPa):
    """IS 456:2000 6.2.3.1 short-term modulus Ec = 5000 sqrt(fck) MPa (the default when the EOR gives no Ec)."""
    return 5000.0 * math.sqrt(float(fck_MPa))


def base_plate_design(*, P_N, M_Nmm=0.0, V_N=0.0, B_mm, L_mm, t_plate_mm, fy_plate_MPa, fck_MPa,
                      col_d_mm, col_bf_mm, col_tf_mm, anchors=None, Ec_MPa=None, modular_ratio=None,
                      sfrs_fixed_base=False, col_Zp_mm3=None, col_fy_MPa=None, col_Vd_N=None, shear_key_N=None,
                      friction_mu=0.45, weld_length_mm=None, col_perimeter_mm=None, embedment=None,
                      sfrs_moment_factor=1.2, Ec_source=None):
    """Column base per IS 800 7.4 (P + M + V) - a CHECK of declared geometry; it never sizes from demand.

    Axis: moment about the axis perpendicular to L (L = plate dimension along the moment, B across).
    P_N > 0 compression. anchors = {n_total, n_tension (on the tension side), d_mm, grade, f_mm (distance of the
    tension anchor line from the plate centre), pitch_mm, edge_mm, Anb_mm2?}.
    - bearing: linear pressure <= 0.6 fck (7.4.1); e <= L/6 trapezoid, e > L/6 elastic compatibility with anchors
      (modular ratio n = E/Ec; Ec from the EOR, else IS 456:2000 6.2.3.1 Ec = 5000 sqrt(fck) - recorded as the source).
    - anchors: 10.3.5 tension, 10.3.3 shear, 10.3.6 combined; concrete embedment/pull-out is outside IS 800
      (found:false unless embedment={capacity_N, cite} is supplied by the EOR).
    - shear path: friction 0.45 x compression (7.4.1) or shear key or anchors.
    - thickness: compression-side cantilever per 7.4.3.1 form (M = 0.2 t^2 fy/gamma_m0 per unit width, the
      1.2 Ze cap of 8.2.1.2 - equivalent to 7.4.3.1 with b = 0), tension-side anchor-line moment; ts > tf.
    - 12.12: for SFRS fixed bases M_dem = max(M, sfrs_moment_factor x Mp_col) (1.2 per IS 800 12.12.1; 1.1 Ry per
      IS 18168 9.3 when it governs), V_dem = max(V, 1.2 Vd_col).
    - geometric feasibility: anchor pitch >= 2.5 d (10.2.2), edge >= 1.5 d0 (10.2.4.2 min edge), weld length <=
      column perimeter.
    """
    checks = {}
    cite_b = "IS 800:2007 7.4.1 (linear bearing, 0.6 fck)"
    M_dem, V_dem = abs(float(M_Nmm or 0.0)), abs(float(V_N or 0.0))
    if sfrs_fixed_base:
        if col_Zp_mm3 and col_fy_MPa:
            M12 = float(sfrs_moment_factor) * col_Zp_mm3 * col_fy_MPa
            checks["12.12.1_moment_demand"] = {"value": M12, "clause": "IS 800:2007 12.12.1" + (
                " + IS 18168:2023 9.3" if sfrs_moment_factor > 1.2 else ""),
                                               "cite": "%.2f x full plastic moment of the column" % sfrs_moment_factor,
                                               "ok": True}
            M_dem = max(M_dem, M12)
        else:
            checks["12.12.1_moment_demand"] = _check(None, None, clause="IS 800:2007 12.12.1",
                                                     cite="1.2 Mp column", ok=None, reason="column Zp/fy missing")
        if col_Vd_N:
            V_dem = max(V_dem, 1.2 * col_Vd_N)
            checks["12.12.2_shear_demand"] = {"value": 1.2 * col_Vd_N, "clause": "IS 800:2007 12.12.2",
                                              "cite": "max(full shear, 1.2 x column shear capacity)", "ok": True}
        else:
            checks["12.12.2_shear_demand"] = _check(None, None, clause="IS 800:2007 12.12.2", cite="1.2 Vd column",
                                                    ok=None, reason="column Vd missing")
    fb = 0.6 * float(fck_MPa)
    P = float(P_N)
    e = M_dem / P if P > 0 else float("inf")
    T_anchor = 0.0
    a = anchors or {}
    As_t = None
    if a.get("d_mm") and a.get("n_tension"):
        Anb, _ = bolt_areas(a["d_mm"], a.get("Anb_mm2"), None)
        As_t = a["n_tension"] * Anb if Anb else None
    bearing = {"e_mm": e, "L_over_6_mm": L_mm / 6.0}
    if P > 0 and e <= L_mm / 6.0:
        fmax = P / (B_mm * L_mm) + 6 * M_dem / (B_mm * L_mm ** 2)
        bearing.update(method="trapezoidal: eccentricity within the middle third (e_mm vs L_over_6_mm above)", fp_max_MPa=fmax, Y_mm=L_mm)
        checks["bearing"] = _check(fmax, fb, clause="IS 800:2007 7.4.1", cite=cite_b)
    elif P > 0:
        if not modular_ratio and not Ec_MPa:
            Ec_MPa, Ec_source = ec_is456(fck_MPa), IS456_EC_CITE
        n = modular_ratio or ((E_MPA / Ec_MPa) if Ec_MPa else None)
        bearing.update(Ec_MPa=Ec_MPa, Ec_source=Ec_source or ("EOR" if (Ec_MPa or modular_ratio) else None))
        if not (n and As_t and a.get("f_mm") is not None):
            bearing.update(method="e > L/6 needs anchors (n_tension, d, f_mm) and Ec/modular ratio (EOR input)")
            checks["bearing"] = _check(None, fb, clause="IS 800:2007 7.4.1", cite=cite_b, ok=None,
                                       reason="elastic compatibility inputs missing")
            checks["anchor_tension_demand"] = _check(None, None, clause="IS 800:2007 7.4.1 / 12.12.1",
                                                     cite="anchor tension by equilibrium", ok=None,
                                                     reason="inputs missing")
        else:
            sol = _bearing_linear(P, M_dem, B_mm, L_mm, float(a["f_mm"]), As_t, n)
            if sol is None:
                checks["bearing"] = _check(None, fb, clause="IS 800:2007 7.4.1", cite=cite_b, ok=None,
                                           reason="no bearing solution")
            else:
                bearing.update(method="linear bearing with anchor tension (elastic compatibility)", **sol,
                               modular_ratio=n)
                T_anchor = sol["T_N"]
                checks["bearing"] = _check(sol["fp_max_MPa"], fb, clause="IS 800:2007 7.4.1", cite=cite_b)
    else:
        bearing.update(method="net uplift: no bearing")
        T_anchor = abs(P) + (2 * M_dem / L_mm if M_dem else 0.0)
    # anchors
    if a.get("d_mm") and a.get("n_total"):
        one = bolt_capacity_is800(a["d_mm"], a.get("grade", "4.6"), nn=1, ns=0, e_mm=None, p_mm=None,
                                  fub_MPa=a.get("fub_MPa"), fyb_MPa=a.get("fyb_MPa"), Anb_mm2=a.get("Anb_mm2"))
        Tdb, Vdsb = one.get("Tdb_N"), one.get("Vdsb_N")
        nt = a.get("n_tension") or 0
        T_one = T_anchor / nt if nt else (0.0 if T_anchor <= 0 else float("inf"))
        C_bear = (bearing.get("C_N") or max(P, 0.0))
        V_fric = friction_mu * C_bear
        V_anchor = max(V_dem - V_fric - (shear_key_N or 0.0), 0.0)
        V_one = V_anchor / a["n_total"]
        checks["anchor_tension_demand"] = {"value": T_anchor, "clause": "IS 800:2007 7.4.1 / 12.12.1",
                                           "cite": "equilibrium of the bearing block", "ok": True}
        if Tdb:
            checks["anchor_tension_10_3_5"] = _check(T_one, Tdb, clause="IS 800:2007 10.3.5", cite="Tb <= Tdb")
        if Vdsb:
            checks["anchor_shear_10_3_3"] = _check(V_one, Vdsb, clause="IS 800:2007 10.3.3", cite="Vsb <= Vdsb")
        if Tdb and Vdsb:
            checks["anchor_combined_10_3_6"] = _check((V_one / Vdsb) ** 2 + (T_one / Tdb) ** 2, 1.0,
                                                      clause="IS 800:2007 10.3.6", cite="(V/Vdb)^2+(T/Tdb)^2 <= 1")
        checks["shear_path"] = {"value": V_dem, "friction_N": V_fric, "shear_key_N": shear_key_N,
                                "anchors_N": V_anchor, "clause": "IS 800:2007 7.4.1 (friction 0.45)",
                                "cite": "shear by friction, shear key, then anchors", "ok": True}
        if a.get("pitch_mm") is not None:
            checks["geometry_anchor_pitch"] = _check(2.5 * a["d_mm"], a["pitch_mm"], clause="IS 800:2007 10.2.2",
                                                     cite="pitch >= 2.5 d")
        if a.get("edge_mm") is not None:
            d0 = a.get("d0_mm") or (a["d_mm"] + (1 if a["d_mm"] <= 14 else 2 if a["d_mm"] <= 24 else 3))  # Table 19
            checks["geometry_anchor_edge"] = _check(1.5 * d0, a["edge_mm"], clause="IS 800:2007 10.2.4.2",
                                                    cite="edge >= 1.5 d0 (min, sheared/rough edge 1.7 d0)")
        if a.get("pitch_mm") and a.get("n_per_row"):
            span = (a["n_per_row"] - 1) * a["pitch_mm"] + 2 * (a.get("edge_mm") or 0)
            checks["geometry_anchor_fit"] = _check(span, B_mm, clause="geometric feasibility",
                                                   cite="anchor row must fit in the plate width")
        if embedment and embedment.get("capacity_N") and embedment.get("cite"):
            checks["anchorage_embedment"] = _check(T_one, embedment["capacity_N"], clause=embedment["cite"],
                                                   cite="EOR/product anchorage capacity (outside IS 800)")
        elif T_anchor > 0:
            checks["anchorage_embedment"] = _check(T_one, None, clause="outside IS 800 (IS 456 / product data)",
                                                   cite="concrete breakout/pull-out", ok=None,
                                                   reason="found:false - EOR anchorage basis not supplied")
    elif T_anchor > 0 or V_dem > friction_mu * max(P, 0.0) + (shear_key_N or 0.0):
        checks["anchors"] = _check(None, None, clause="IS 800:2007 10.3.5/10.3.6", cite="anchor rods", ok=None,
                                   reason="anchor geometry not declared (found:false)")
    else:
        checks["shear_path"] = _check(V_dem, friction_mu * max(P, 0.0) + (shear_key_N or 0.0),
                                      clause="IS 800:2007 7.4.1", cite="friction 0.45 x compression (+ key)")
    # plate thickness
    a_proj = (L_mm - 0.95 * col_d_mm) / 2.0
    b_proj = (B_mm - 0.8 * col_bf_mm) / 2.0
    big, small = max(a_proj, b_proj), min(a_proj, b_proj)
    if P > 0 and e <= L_mm / 6.0 and M_dem == 0:
        w = P / (B_mm * L_mm)
        th = base_plate_thickness_7_4_3_1(w_MPa=w, a_mm=big, b_mm=small, fy_MPa=fy_plate_MPa, tf_col_mm=col_tf_mm,
                                          t_prov_mm=t_plate_mm)
        checks["plate_thickness_7_4_3_1"] = th["check"]
        checks["plate_thickness_7_4_3_1"]["t_req_mm"] = th["t_required_mm"]
    else:
        fp = bearing.get("fp_max_MPa")
        Mcomp = None
        if fp is not None:
            m = a_proj
            Y = bearing.get("Y_mm", L_mm)
            if Y >= m:
                f_face = fp * (1 - m / Y) if Y < L_mm else fp
                Mcomp = f_face * m ** 2 / 2 + (fp - f_face) * m ** 2 / 3
            else:
                Mcomp = fp * Y / 2 * (m - Y / 3)
        Mten = None
        if T_anchor > 0 and a.get("f_mm") is not None:
            lever = max(a["f_mm"] - col_d_mm / 2.0 + col_tf_mm / 2.0, 0.0)
            Mten = T_anchor * lever / B_mm
        Mu = max([v for v in (Mcomp, Mten) if v is not None] or [None]) if (Mcomp or Mten) else None
        if Mu is None:
            checks["plate_thickness"] = _check(None, t_plate_mm, clause="IS 800:2007 7.4.3.2", cite="plate bending",
                                               ok=None, reason="bearing / anchor solution missing")
        else:
            t_req = math.sqrt(5.0 * Mu * GAMMA_M0 / fy_plate_MPa)
            Mcap = 0.2 * t_plate_mm ** 2 * fy_plate_MPa / GAMMA_M0
            c = _check(Mu, Mcap, dc=Mu / Mcap, clause="IS 800:2007 7.4.3.2 / 7.4.3.1",
                       cite="plate moment per unit width (N-mm/mm) <= 0.2 t^2 fy/gamma_m0 (7.4.3.1 form); DC=(t_req/t)^2",
                       M_per_mm=Mu, M_comp_side=Mcomp, M_tension_side=Mten, t_req_mm=t_req, t_prov_mm=t_plate_mm)
            c["ok"] = c["dc"] <= 1.0 and t_plate_mm > col_tf_mm
            checks["plate_thickness"] = c
    if weld_length_mm is not None:
        per = col_perimeter_mm or (2 * col_bf_mm + 2 * col_d_mm - 2 * 0)  # outer outline upper bound
        checks["geometry_weld_length"] = _check(weld_length_mm, per, clause="geometric feasibility",
                                                cite="weld length <= column profile perimeter")
    oks = [c.get("ok") for c in checks.values() if isinstance(c, dict)]
    ok = (None if any(o is None for o in oks) else all(oks))
    dcs = [c.get("dc") for c in checks.values() if isinstance(c, dict) and c.get("dc") is not None]
    return {"found": True, "ok": ok, "dc": max(dcs) if dcs else None, "checks": checks, "bearing": bearing,
            "demands": {"P_N": P, "M_Nmm": M_dem, "V_N": V_dem, "T_anchor_N": T_anchor},
            "clause": "IS 800:2007 7.4, 10.3, 12.12", "policy": "check of declared geometry; never sized from demand"}


# ------------------------------------------------------------------- HR-INTEGRATE: connection capacities used by
# the India pipeline (beam-column moment / shear connections, CJP welds, prying).  Still checks of DECLARED geometry.
def cjp_weld_capacity_N(*, t_mm, length_mm, fy_MPa, n_sides=1, site=False, gamma_mw=None, action="shear"):
    """IS 800 10.5.7.1.2: a complete penetration butt weld has the design strength of the parent metal (throat = the
    thinner part, 10.5.3.1).  Shear: t L fy/(sqrt3 gamma_mw) (8.4.1 form); tension: t L fy/gamma_mw."""
    miss = [k for k, v in (("t_mm", t_mm), ("length_mm", length_mm), ("fy_MPa", fy_MPa)) if not v]
    cite = "IS 800:2007 10.5.7.1.2 (CJP butt weld = parent metal), 10.5.3.1 throat = thinner part, Table 5 gamma_mw"
    if miss:
        return {"found": False, "capacity_N": None, "cite": cite, "required_inputs": miss}
    gmw = gamma_mw if gamma_mw is not None else (GAMMA_MW_SITE if site else GAMMA_MW_SHOP)
    f = float(fy_MPa) / gmw / (math.sqrt(3.0) if action == "shear" else 1.0)
    cap = f * float(t_mm) * float(length_mm) * int(n_sides or 1)
    return {"found": True, "capacity_N": cap, "throat_mm": float(t_mm), "length_mm": float(length_mm),
            "n_sides": int(n_sides or 1), "gamma_mw": gmw, "action": action, "cite": cite, "method": "LSD",
            "weld_type": "cjp"}


def prying_10_4_7(*, Te_N, lv_mm, le_mm, t_mm, be_mm, fo_MPa, fy_MPa, pretensioned=True, eta=1.5):
    """IS 800 10.4.7 (pdf p. 83): Q = lv/(2 le) [Te - beta eta fo be t^4/(27 le lv^2)], beta 2 (non-pretensioned)
    / 1 (pretensioned), eta 1.5, le = min(end distance, 1.1 t sqrt(beta fo/fy)); Q >= 0."""
    beta = 1.0 if pretensioned else 2.0
    le = min(float(le_mm), 1.1 * float(t_mm) * math.sqrt(beta * float(fo_MPa) / float(fy_MPa)))
    Q = float(lv_mm) / (2.0 * le) * (float(Te_N) - beta * eta * float(fo_MPa) * float(be_mm) * float(t_mm) ** 4
                                     / (27.0 * le * float(lv_mm) ** 2))
    return {"Q_N": max(Q, 0.0), "le_used_mm": le, "beta": beta, "eta": eta,
            "cite": "IS 800:2007 10.4.7 prying force; le = min(end distance, 1.1 t sqrt(beta fo/fy))"}


def end_plate_moment_capacity(*, rows, d_mm, grade="8.8", t_plate_mm, fy_plate_MPa, be_mm, lv_mm, le_mm,
                              pretensioned=True, bolt_type="HSFG", Anb_mm2=None, fub_MPa=None, fyb_MPa=None):
    """Bolted end-plate moment connection: capacity = sum over tension bolt rows of (2 Te_row x h_row) where the
    bolt tension Te per bolt is limited by (i) 10.3.5 Tdb with the 10.4.7 prying force added (Te + Q <= Tdb) and
    (ii) the end-plate bending at the bolt line per pair, M = Te lv - Q le <= 1.2 (be t^2/6) fy/gamma_m0 (8.2.1.2
    cap on a plate strip).  rows = [{h_mm (lever arm from the compression flange centre), n_pairs (default 1)}].
    The compression side (flange bearing / column continuity / panel zone) is checked at the joint (12.11.2.3-.5)."""
    one = bolt_capacity_is800(d_mm, grade, nn=1, ns=0, e_mm=None, p_mm=None, Anb_mm2=Anb_mm2, fub_MPa=fub_MPa,
                              fyb_MPa=fyb_MPa)
    Tdb = one.get("Tdb_N")
    cite = "IS 800:2007 10.3.5 (Tdb) + 10.4.7 (prying) + 8.2.1.2 plate strip (1.2 Ze fy/gamma_m0)"
    if not Tdb or not rows:
        return {"found": False, "capacity_Nmm": None, "cite": cite, "required_inputs": ["rows", "d_mm", "grade"]}
    fo = 0.70 * float(one["fub_MPa"])                                       # proof stress (10.4.3 F0 basis)
    Mp_strip = 1.2 * (float(be_mm) * float(t_plate_mm) ** 2 / 6.0) * float(fy_plate_MPa) / GAMMA_M0
    beta = 1.0 if pretensioned else 2.0
    le = min(float(le_mm), 1.1 * float(t_plate_mm) * math.sqrt(beta * fo / float(fy_plate_MPa)))
    K = beta * 1.5 * fo * float(be_mm) * float(t_plate_mm) ** 4 / (27.0 * le * float(lv_mm) ** 2)
    a = float(lv_mm) / (2.0 * le)
    # (i) bolt: Te + a (Te - K) <= Tdb  ->  Te <= (Tdb + a K)/(1 + a)   (prying active when Te > K)
    Te_bolt = min((Tdb + a * K) / (1.0 + a), Tdb) if Tdb > K else Tdb
    # (ii) plate: Te lv - Q le <= Mp_strip, Q = a (Te - K)  ->  Te (lv - a le) + a K le <= Mp_strip
    coef = float(lv_mm) - a * le
    Te_plate = (Mp_strip - a * K * le) / coef if coef > 0 else float("inf")
    Te = max(min(Te_bolt, Te_plate), 0.0)
    Q = prying_10_4_7(Te_N=Te, lv_mm=lv_mm, le_mm=le_mm, t_mm=t_plate_mm, be_mm=be_mm, fo_MPa=fo, fy_MPa=fy_plate_MPa,
                      pretensioned=pretensioned)["Q_N"]
    Mcap, terms = 0.0, []
    for r in rows:
        n = int(r.get("n_pairs") or 1)
        Mcap += 2.0 * n * Te * float(r["h_mm"])
        terms.append({"h_mm": float(r["h_mm"]), "n_pairs": n, "Te_per_bolt_N": Te})
    out = {"found": True, "capacity_Nmm": Mcap, "Te_per_bolt_N": Te, "Q_per_bolt_N": Q, "Tdb_N": Tdb,
           "governing": "bolt tension + prying" if Te_bolt <= Te_plate else "end-plate bending", "Te_bolt_N": Te_bolt,
           "Te_plate_N": Te_plate, "Mp_strip_Nmm": Mp_strip, "le_used_mm": le, "rows": terms, "cite": cite,
           "bolt_type": bolt_type, "type": "end_plate"}
    g = hsfg_gate(bolt_type)
    out["12.4.1"] = g
    return out


def cover_plate_moment_capacity(*, Zp_beam_mm3, fy_beam_MPa, plate_b_mm, plate_t_mm, d_beam_mm, fy_plate_MPa=None,
                                weld=None):
    """Reinforced (cover-plated) CJP-welded moment connection at the column face: Mcap = (Zp,beam + Zp,plates)
    fy/gamma_m0 with Zp,plates = b t (d + t) (one plate each flange); the plate-to-flange fillet welds must carry the
    plate force b t fy/gamma_m0 (10.5.7) and the plate-to-column welds are CJP (12.4.2).  weld = {size_mm, length_mm
    (per plate, total), fu_MPa, site}."""
    fyp = float(fy_plate_MPa or fy_beam_MPa)
    Zp_pl = float(plate_b_mm) * float(plate_t_mm) * (float(d_beam_mm) + float(plate_t_mm))
    Mcap = (float(Zp_beam_mm3) * float(fy_beam_MPa) + Zp_pl * fyp) / GAMMA_M0
    out = {"found": True, "capacity_Nmm": Mcap, "Zp_plates_mm3": Zp_pl, "Zp_beam_mm3": float(Zp_beam_mm3),
           "cite": "IS 800:2007 8.2.1.2 (plastic section at the column face incl. cover plates) / 10.5.7.1.2 CJP",
           "type": "welded_cover_plate", "weld_type": "cjp"}
    if weld:
        Fpl = float(plate_b_mm) * float(plate_t_mm) * fyp / GAMMA_M0
        w = fillet_weld_capacity_is800_N(**weld)
        if w.get("found"):
            out["plate_weld_check"] = _check(Fpl, w["capacity_N"], clause="IS 800:2007 10.5.7",
                                             cite="cover-plate fillet welds carry the plate force b t fy/gamma_m0")
            if out["plate_weld_check"]["dc"] > 1.0:
                out["capacity_Nmm"] = (float(Zp_beam_mm3) * float(fy_beam_MPa) + Zp_pl * fyp * w["capacity_N"] / Fpl) / GAMMA_M0
                out["governing"] = "cover-plate welds"
        else:
            out["plate_weld_check"] = {"found": False, "required_inputs": w.get("required_inputs")}
    return out


def fin_plate_shear_checks(*, V_N, t_plate_mm, h_plate_mm, fy_plate_MPa, fu_plate_MPa, bolts, weld=None,
                           block_shear_areas=None, cjp=None):
    """Simple (shear) beam-end connection: bolt group 10.3, plate shear yield 8.4.1 (Av fy/(sqrt3 gamma_m0)),
    block shear 6.4.1 (areas from block_shear_bolted_areas), plate-to-support weld 10.5.7 (fillet) or 10.5.7.1.2
    (CJP).  Returns {checks{}, capacity_N (minimum), ok, dc}."""
    checks = {}
    b = dict(bolts)
    n = b.pop("n_bolts")
    g = bolt_group_capacity_is800(n, b.pop("d_mm"), b.pop("grade", "8.8"), V_N=V_N, **b)
    checks["bolts_10_3"] = g["check"] if g.get("found") else _check(None, None, clause="IS 800:2007 10.3", cite="bolts",
                                                                     ok=None, reason=str(g.get("required_inputs")))
    Vd = float(h_plate_mm) * float(t_plate_mm) * float(fy_plate_MPa) / (math.sqrt(3.0) * GAMMA_M0)
    checks["plate_shear_8_4_1"] = _check(abs(V_N), Vd, clause="IS 800:2007 8.4.1", cite="Av fy/(sqrt3 gamma_m0)")
    if block_shear_areas:
        bs = block_shear(fy_MPa=fy_plate_MPa, fu_MPa=fu_plate_MPa, demand_N=V_N, **block_shear_areas)
        checks["block_shear_6_4_1"] = bs["check"] if bs.get("found") else _check(None, None, clause="IS 800:2007 6.4.1",
                                                                                cite="block shear", ok=None,
                                                                                reason="areas missing")
    if cjp:
        w = cjp_weld_capacity_N(**cjp)
    elif weld:
        w = fillet_weld_capacity_is800_N(**weld)
    else:
        w = None
    if w is not None:
        checks["support_weld"] = _check(abs(V_N), w["capacity_N"], clause="IS 800:2007 10.5.7", cite=w["cite"]) \
            if w.get("found") else _check(None, None, clause="IS 800:2007 10.5.7", cite="weld", ok=None,
                                          reason=str(w.get("required_inputs")))
    caps = [c["limit"] for c in checks.values() if c.get("limit")]
    oks = [c.get("ok") for c in checks.values()]
    return {"found": bool(caps), "checks": checks, "capacity_N": min(caps) if caps else None,
            "ok": None if any(o is None for o in oks) else all(oks),
            "dc": max([c["dc"] for c in checks.values() if c.get("dc") is not None] or [None]) if caps else None,
            "cite": "IS 800:2007 10.3 / 8.4.1 / 6.4.1 / 10.5.7 (simple beam-end connection)"}


def column_splice_checks(*, sfrs, Af_mm2, fy_MPa, P_N, M_Nmm, Zx_mm3, A_mm2, d_mm, splice):
    """Column splice: SFRS columns per 12.5.2.2 (each flange splice >= 1.2 fy Af; PJP welds 200 % of required,
    12.5.2.1); gravity columns for the member forces.  splice = {type: 'flange_plates'|'cjp'|'pjp',
    plate: {A_mm2, fy_MPa}, bolts: {n_bolts, d_mm, grade, ...} | weld: {t_mm, length_mm, n_sides}}."""
    Ff_dem = 1.2 * float(fy_MPa) * float(Af_mm2) if sfrs else max(abs(float(P_N)) / 2.0 + abs(float(M_Nmm)) / float(d_mm),
                                                                   0.0)
    typ = str(splice.get("type") or "").lower()
    cl = "IS 800:2007 12.5.2.2" if sfrs else "IS 800:2007 10 (member forces)"
    cite = ("each flange splice >= 1.2 fy Af (Fig. 20, smaller column)" if sfrs else
            "flange force P/2 + M/d from the governing combination")
    checks = {}
    if typ == "flange_plates":
        pl = splice.get("plate") or {}
        if pl.get("A_mm2") and pl.get("fy_MPa"):
            checks["plate_yield_6_2"] = _check(Ff_dem, float(pl["A_mm2"]) * float(pl["fy_MPa"]) / GAMMA_M0,
                                               clause=cl + " / 6.2", cite=cite + "; plate Ag fy/gamma_m0")
        b = splice.get("bolts")
        if b:
            b = dict(b)
            g = bolt_group_capacity_is800(b.pop("n_bolts"), b.pop("d_mm"), b.pop("grade", "8.8"), V_N=Ff_dem, **b)
            checks["bolts_10_3"] = g["check"] if g.get("found") else _check(None, None, clause="IS 800:2007 10.3",
                                                                             cite="bolts", ok=None,
                                                                             reason=str(g.get("required_inputs")))
        w = splice.get("weld")
        if w:
            wc = fillet_weld_capacity_is800_N(**w)
            checks["plate_weld_10_5_7"] = _check(Ff_dem, wc["capacity_N"], clause="IS 800:2007 10.5.7", cite=wc["cite"]) \
                if wc.get("found") else _check(None, None, clause="IS 800:2007 10.5.7", cite="weld", ok=None)
    elif typ in ("cjp", "pjp"):
        w = splice.get("weld") or {}
        t = w.get("t_mm") or (Af_mm2 / w["length_mm"] if w.get("length_mm") else None)
        wc = cjp_weld_capacity_N(t_mm=t, length_mm=w.get("length_mm"), fy_MPa=fy_MPa, n_sides=1, action="tension")
        fac = 0.5 if typ == "pjp" else 1.0                   # 12.5.2.1: PJP joint strength >= 200 % of required
        checks["flange_weld"] = _check(Ff_dem, fac * wc["capacity_N"], clause=cl + (" / 12.5.2.1" if typ == "pjp" else
                                       " / 10.5.7.1.2"), cite=cite + "; butt weld = parent metal" +
                                       (" x 0.5 (PJP 200 %)" if typ == "pjp" else "")) if wc.get("found") else \
            _check(None, None, clause=cl, cite="weld", ok=None, reason=str(wc.get("required_inputs")))
    else:
        checks["splice"] = _check(None, None, clause=cl, cite=cite, ok=None, reason="splice type not declared")
    caps = [c["limit"] for c in checks.values() if c.get("limit")]
    oks = [c.get("ok") for c in checks.values()]
    return {"found": bool(caps), "checks": checks, "demand_N": Ff_dem, "capacity_N": min(caps) if caps else None,
            "ok": None if any(o is None for o in oks) else all(oks),
            "dc": max([c["dc"] for c in checks.values() if c.get("dc") is not None] or [None]) if caps else None,
            "clause": cl, "cite": cite}
