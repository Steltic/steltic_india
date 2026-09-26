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


# ------------------------------------------------------------------ AUD-2: plate yield stress by thickness (IS 2062)
PLATE_FY_CLAUSE = "IS 2062 (Part 1):2025 Table 3 (ReH min by thickness band); IS 800:2007 2.2.4 (fy of the part)"
_PLATE_GRADES = ("E250", "E275", "E300", "E350", "E410", "E450", "E500", "E550", "E600", "E650")


def plate_fy_is2062(fy_MPa, t_mm, grade=None, *, job_grade=None, what="plate"):
    """AUD-2 (gold audit H2/M1): the yield stress of a plate (base plate, gusset, splice / cover / end / fin plate,
    stiffener, shear key) is the IS 2062:2025 Table 3 ReH of its grade for ITS thickness band (<=16, >16-40, >40-100,
    >100 mm; e.g. E250: 250/240/230/210).  A declared fy above the table value is replaced by the table value and the
    reduction recorded; a lower declared fy is kept.
    Grade: the plate's own declared grade; else the job steel_grade when the declared fy does not exceed that grade's
    designation (<=16 mm ReH); else the lowest IS 2062 grade (E250 up) whose designation is >= the declared fy
    (inferred -- declare the plate grade to use a higher one).
    Returns (fy_used, record); record None when fy is None."""
    if fy_MPa is None:
        return None, None
    import india_is800 as _I8
    fy = float(fy_MPa)
    rec = {"what": what, "fy_declared_MPa": fy, "fy_used_MPa": fy, "t_mm": t_mm, "reduced": False,
           "clause": PLATE_FY_CLAUSE, "cite": _I8.IS2062_CITE, "source": "steel_engine/india_connections.py"}
    if t_mm is None or not _isnum(t_mm) or float(t_mm) <= 0:
        rec.update(band_checked=False, note="%s thickness not declared: IS 2062 Table 3 band not verified for the "
                                            "declared fy %.0f MPa (declare t_mm)" % (what, fy))
        return fy, rec
    key, basis = None, None
    g, _q = _I8.parse_is2062_grade(grade)
    if g in _I8.IS2062_TABLE3:
        key, basis = g, "declared plate grade %s" % grade
    else:
        jg, _q = _I8.parse_is2062_grade(job_grade)
        if jg in _I8.IS2062_TABLE3 and fy <= _I8.IS2062_TABLE3[jg][1][0] + 1e-9:
            key, basis = jg, "job steel_grade %s (plate grade not declared)" % job_grade
        else:
            for cand in _PLATE_GRADES:
                if _I8.IS2062_TABLE3[cand][1][0] >= fy - 1e-9:
                    key, basis = cand, ("inferred %s: lowest IS 2062 grade whose designation >= the declared fy "
                                        "(plate grade not declared -- declare it to use another grade)" % cand)
                    break
    if key is None:
        rec.update(band_checked=False, note="no IS 2062 grade has ReH >= declared fy %.0f MPa" % fy)
        return fy, rec
    tab = _I8.is2062_properties(key, float(t_mm))
    rec.update(grade=key, grade_basis=basis, thickness_band_mm=tab.get("thickness_band_mm"))
    if not tab.get("found"):
        rec.update(band_checked=False, fy_table_MPa=None,
                   note="IS 2062 Table 3 gives no ReH for %s above 100 mm (Note 4: by agreement) -- declared fy kept, "
                        "VERIFY with the mill certificate" % key)
        return fy, rec
    ft = float(tab["fy_MPa"])
    rec.update(band_checked=True, fy_table_MPa=ft)
    if fy > ft + 1e-9:
        rec.update(fy_used_MPa=ft, reduced=True,
                   note="%s: declared fy %.0f MPa exceeds IS 2062:2025 Table 3 ReH %.0f MPa for %s at t = %g mm "
                        "(band %s mm); %.0f MPa used" % (what, fy, ft, key, float(t_mm), tab.get("thickness_band_mm"), ft))
        return ft, rec
    return fy, rec


def tag_plate_fy(check, rec):
    """Attach a plate_fy record to a check row; a reduction is stated in the row's note and cite (AUD-2)."""
    if not isinstance(check, dict) or not rec:
        return check
    lst = check.get("plate_fy") if isinstance(check.get("plate_fy"), list) else []
    if rec not in lst:
        lst.append(rec)
    check["plate_fy"] = lst
    if rec.get("reduced"):
        check["note"] = ((str(check["note"]) + "; ") if check.get("note") else "") + rec["note"]
        c = str(check.get("cite") or "")
        if PLATE_FY_CLAUSE not in c:
            check["cite"] = (c + "; " if c else "") + "fy by thickness: " + PLATE_FY_CLAUSE
    return check


def _geom_gate(value, limit, *, clause, cite, **extra):
    """H31: geometric feasibility row (pitch / edge / fit / weld length) -- a gate, not a strength ratio: ok is
    value <= limit, dc None, gate True, so it never becomes the governing D/C of a connection."""
    ok = None if (value is None or limit is None) else bool(value <= limit)
    out = {"value": value, "limit": limit, "dc": None, "ok": ok, "gate": True, "clause": clause, "cite": cite,
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


BOLT_SPEC_ONLY_KEYS = ("n_e", "Kh", "mu_f", "slip_surface", "bolt_type", "slip_at_ultimate")


def bolt_kwargs(spec):
    """The subset of a declared bolts dict that bolt_capacity_is800 accepts (H37).  The same dict also carries the
    10.4.3 slip keys (n_e effective interfaces, Kh hole factor, mu_f / slip_surface Table 20) read by the HSFG
    slip check, which are not bearing-bolt arguments; they are dropped here instead of raising TypeError."""
    import inspect
    allowed = set(inspect.signature(bolt_capacity_is800).parameters) - {"d_mm", "grade"}
    return {k: v for k, v in (spec or {}).items() if k in allowed}


def bolt_group_capacity_is800(n_bolts, d_mm, grade="8.8", *, V_N=None, **kw):
    """n x min(Vdsb, Vdpb) for a concentrically loaded bolt group (10.3.2). Long-joint beta_lj via lj_mm.
    Keys that are not bolt_capacity_is800 arguments (n_e, Kh, mu_f, slip_surface: the 10.4.3 slip inputs) are
    ignored (H37)."""
    one = bolt_capacity_is800(d_mm, grade, **bolt_kwargs(kw))
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


def _anchor_equilibrium_uplift(P, M, B, L, f_anchor, As_t, n_mod):
    """Net uplift / zero axial (P <= 0, H08, HR-E-11): equilibrium of the plate on the anchors (rows at +/- f) and, when
    the moment lifts the far row, linear bearing at the compression edge (plane sections: bearing block Y with peak
    fp, tension anchors As_t at f from the centre, modular ratio n).  Returns {T_N (tension-side row), C_N (bearing
    resultant, 0 when all anchors are in tension), T_other_N, Y_mm, fp_max_MPa, method}."""
    P, M = float(P), abs(float(M))
    Pt = -P                                                  # net uplift >= 0
    if f_anchor is None or f_anchor <= 0:
        return None
    T_other = Pt / 2.0 - M / (2.0 * f_anchor)
    if T_other >= 0.0:
        # every anchor row in tension: statics of two rows (T + T_o = uplift, (T - T_o) f = M)
        return {"T_N": Pt / 2.0 + M / (2.0 * f_anchor), "T_other_N": T_other, "C_N": 0.0, "Y_mm": 0.0,
                "fp_max_MPa": 0.0, "method": "net uplift: both anchor rows in tension (statics)"}
    if not (As_t and n_mod):
        return None
    g = lambda y: B * y / 2.0                                # C / fp
    h = lambda y: n_mod * As_t * (L / 2.0 + f_anchor - y) / y   # T / fp (strain compatibility)
    F = lambda y: M * (g(y) - h(y)) - P * (g(y) * (L / 2.0 - y / 3.0) + h(y) * f_anchor)
    lo, hi = 1e-6, min(L, L / 2.0 + f_anchor)
    if F(lo) * F(hi) > 0:
        return None
    for _ in range(200):
        mid = 0.5 * (lo + hi)
        if F(lo) * F(mid) <= 0:
            hi = mid
        else:
            lo = mid
    Y = 0.5 * (lo + hi)
    den = g(Y) * (L / 2.0 - Y / 3.0) + h(Y) * f_anchor
    if den <= 0:
        return None
    fp = M / den
    return {"T_N": h(Y) * fp, "T_other_N": 0.0, "C_N": g(Y) * fp, "Y_mm": Y, "fp_max_MPa": fp,
            "method": "net uplift / zero axial with moment: linear bearing + anchor tension (equilibrium and plane "
                      "sections)"}


IS456_EC_CITE = "IS 456:2000 6.2.3.1: Ec = 5000 sqrt(fck) (short-term static modulus, MPa)"


def ec_is456(fck_MPa):
    """IS 456:2000 6.2.3.1 short-term modulus Ec = 5000 sqrt(fck) MPa (the default when the EOR gives no Ec)."""
    return 5000.0 * math.sqrt(float(fck_MPa))


# ------------------------------------------------------------------- X03: stiffened (gusseted) and embedded bases
CITE_7_4_2 = ("IS 800:2007 7.4.2: 'For stanchion with gusseted bases, the gusset plates, angle cleats, stiffeners, "
              "fastenings, etc, in combination with the bearing area of the shaft, shall be sufficient to take the loads, "
              "bending moments and reactions to the base plate without exceeding specified strength.'; 7.4.2.1: 'Where the "
              "ends of the column shaft and the gusset plates are not faced for complete bearing, the weldings, fastenings "
              "connecting them to the base plate shall be sufficient to transmit all the forces to which the base is "
              "subjected.'")
CITE_7_4_3_2 = ("IS 800:2007 7.4.3.2: 'When the slab does not distribute the column load uniformly, due to eccentricity of "
                "the load etc, special calculation shall be made to show that the base is adequate to resist the moment "
                "due to the non-uniform pressure from below.'")
STIFF_PLATE_BASIS = (
    "EOR method, VERIFY: IS 800 7.4.2 gives no plate formula for a gusseted base.  Plate panels by the Hillerborg simple "
    "strip method (lower-bound theorem of plasticity; A. Hillerborg, Strip Method of Design, 1975; Park & Gamble, "
    "Reinforced Concrete Slabs, ch. 9): the load w is split between strips spanning between the gussets and strips "
    "cantilevering from the column face / gussets so that both carry the same moment -- 3-edge panel (column face + "
    "2 gussets, outer edge free) M = w s^2 m^2 / (2 (s^2 + 4 m^2)); 2-adjacent-edge panel M = w c^2 m^2 / (2 (c^2 + "
    "m^2)); 2 opposite edges (gussets only) w s^2/8; 1 edge (cantilever) w c^2/2; w = the peak bearing pressure "
    "applied uniformly (conservative); resistance 0.2 t^2 fy/gamma_m0 per mm (1.2 Ze, 7.4.3.1 / 8.2.1.2 form).  The "
    "governing moment per side is the smaller of this field and the unstiffened cantilever field (each is statically "
    "admissible on its own).")
STIFF_ANCHOR_BASIS = (
    "EOR method, VERIFY: tension-side anchor pull on the plate between gussets = point load on a strip simply supported "
    "on the two gussets (M = T a (s - a)/s; cantilever beyond the outer gusset M = T c), spread over the effective "
    "width b_eff = 2.48 a (1 - a/s) + 2 d (cantilever 1.2 c + 2 d), capped at the gusset length (the one-way slab "
    "effective-width form of IS 456:2000 24.3.2, not in the corpus); the smaller of this and the unstiffened "
    "anchor-line cantilever T lever / B is used")
STIFF_WELD_CITE = ("IS 800:2007 10.5.7.1.1 fwd = fu/(sqrt3 gamma_mw), 10.5.3.2 + Table 22 throat K s, 10.5.4.1 effective "
                   "length = overall - 2 s; resultant force per mm on the throat (vector sum, 10.5.7.1.1); the 10.5.10.1.1 "
                   "combined-stress formula is an image not transcribed in the corpus -> VERIFY")


def _stiffener_spec(stiffeners):
    """Validate cfg column_base 'stiffeners'; returns (spec, layout, missing inputs)."""
    s = dict(stiffeners or {})
    miss = []
    layout = str(s.get("layout") or "flange_extension").lower()
    if layout not in ("flange_extension", "cross"):
        miss.append("layout ('flange_extension' | 'cross')")
    if not (s.get("x_mm") or (s.get("n_per_side") and int(s["n_per_side"]) >= 1)):
        miss.append("n_per_side (>= 1) or x_mm")
    for k in ("t_mm", "h_mm", "fy_MPa"):
        if not s.get(k):
            miss.append(k)
    for key in ("weld_column", "weld_plate"):
        w = s.get(key) or s.get("weld") or {}
        if str(w.get("type") or "fillet").lower() == "cjp":
            continue
        for k in ("size_mm", "fu_MPa"):
            if not w.get(k):
                miss.append("%s.%s" % ("weld" if not s.get(key) else key, k))
    return s, layout, sorted(set(miss), key=miss.index)


def _gusset_positions(n, explicit, coverage_mm, t_mm):
    """Gusset centre lines across the zone (mm from the plate centre line): declared, else n evenly spaced across the
    column face (outer ones flush with the face edges: +/-(coverage - t)/2; n = 1 on the centre line)."""
    if explicit:
        return sorted(float(x) for x in explicit)
    n = int(n or 0)
    if n <= 0:
        return []
    if n == 1:
        return [0.0]
    half = coverage_mm / 2.0 - t_mm / 2.0
    return [-half + i * 2.0 * half / (n - 1) for i in range(n)]


def _stiffener_layout(spec, layout, axis, col_d_mm, col_bf_mm):
    """Gusset positions in the LOCAL frame of one base_plate_design call (L along the moment, B across; col_bf across
    B, col_d along L).  axis 'z' (major): main zones (the L-projections) carry the flange-extension gussets; the
    side zones carry the side gussets of a 'cross' layout.  axis 'y' (the swapped minor-axis call): the roles swap."""
    t = float(spec["t_mm"])
    n_fl, x_fl = spec.get("n_per_side"), spec.get("x_mm")
    n_sd, y_sd = spec.get("n_per_side_y") or spec.get("n_per_side"), spec.get("y_mm")
    cross = layout == "cross"
    if axis == "y":
        main = _gusset_positions(n_sd, y_sd, col_bf_mm, t) if cross else []
        side = _gusset_positions(n_fl, x_fl, col_d_mm, t)
    else:
        main = _gusset_positions(n_fl, x_fl, col_bf_mm, t)
        side = _gusset_positions(n_sd, y_sd, col_d_mm, t) if cross else []
    corner = bool(side) and max(abs(y) for y in side) + t / 2.0 >= col_d_mm / 2.0 - 1.0
    return main, side, corner


def _panel_moments(w, W, wc, m, pos, corner_supported, tol=1.0):
    """Hillerborg simple-strip moments per unit width (N-mm/mm) of the panels of one projection zone: zone width W
    (across), column-face coverage wc (centred), depth m (face to plate edge), gusset centre lines pos."""
    if not pos:
        return [{"panel": "1-edge (column face) cantilever", "span_mm": m, "M_per_mm": w * m * m / 2.0}]
    out = []
    for a, b in zip(pos, pos[1:]):
        s = b - a
        if a >= -wc / 2.0 - tol and b <= wc / 2.0 + tol:
            out.append({"panel": "3-edge (column face + 2 gussets, outer edge free)", "s_mm": s, "m_mm": m,
                        "M_per_mm": w * s * s * m * m / (2.0 * (s * s + 4.0 * m * m))})
        else:
            out.append({"panel": "2 opposite edges (gussets), one-way", "s_mm": s, "M_per_mm": w * s * s / 8.0})
    for c in (pos[0] + W / 2.0, W / 2.0 - pos[-1]):
        if c <= tol:
            continue
        if W / 2.0 <= wc / 2.0 + tol or corner_supported:
            out.append({"panel": "2-adjacent-edge (gusset + column face / orthogonal gusset)", "c_mm": c, "m_mm": m,
                        "M_per_mm": w * c * c * m * m / (2.0 * (c * c + m * m))})
        else:
            out.append({"panel": "1-edge (outer gusset) cantilever", "c_mm": c, "M_per_mm": w * c * c / 2.0})
    return out


def _pressure_fn(bearing, P, B, L):
    """Bearing pressure p(s) at distance s from the compression edge (linear, 7.4.1): cracked block fp (1 - s/Y), or
    the full-contact trapezoid fmax -> fmin."""
    fp = float((bearing or {}).get("fp_max_MPa") or 0.0)
    Y = (bearing or {}).get("Y_mm")
    if fp <= 0.0:
        return lambda s: 0.0
    if Y is not None and float(Y) < L - 1e-6:
        Y = float(Y)
        return lambda s: fp * (1.0 - s / Y) if s < Y else 0.0
    fmin = 2.0 * max(float(P), 0.0) / (B * L) - fp
    return lambda s: max(fp - (fp - fmin) * s / L, 0.0)


def _integrate(fn, a, b, n=400):
    """Simpson rule on [a, b]."""
    if b <= a:
        return 0.0
    h = (b - a) / n
    s = fn(a) + fn(b)
    for i in range(1, n):
        s += (4 if i % 2 else 2) * fn(a + i * h)
    return s * h / 3.0


def _anchor_positions(a, nt, key="x_mm"):
    """x of the tension-row anchors across the plate: declared anchors[key], else n_per_row at pitch centred (rows =
    n_tension / n_per_row stacked at the same x).  None when neither is declared."""
    if a.get(key):
        xs = [float(x) for x in a[key]]
        rows = max(float(nt) / len(xs), 1.0) if nt else 1.0
        return xs, rows
    n_row = int(a.get("n_per_row") or 0)
    if a.get("pitch_mm") and n_row:
        p = float(a["pitch_mm"])
        return [-(n_row - 1) * p / 2.0 + i * p for i in range(n_row)], max(float(nt) / n_row, 1.0) if nt else 1.0
    return None, None


def stiffened_base_checks(*, stiffeners, axis, P_N, bearing, T_anchor_N, anchors, B_mm, L_mm, t_plate_mm,
                          fy_plate_MPa, col_d_mm, col_bf_mm, col_tf_mm, M_unstiff_comp=None, M_unstiff_ten=None,
                          uniform_w=None):
    """IS 800 7.4.2 gusseted base (X03): plate panels, gussets and gusset welds for one axis of base_plate_design
    (local frame: L along the moment).  Returns {'applied', 'checks', 'plate' (governing M per mm), 'detail'};
    applied False (no gussets in this axis' zones) leaves the unstiffened model in force."""
    spec, layout, miss = _stiffener_spec(stiffeners)
    if miss:
        return {"applied": False, "checks": {"stiffeners_input": _check(
            None, None, clause="IS 800:2007 7.4.2", cite=CITE_7_4_2, ok=None,
            reason="found:false - stiffener inputs missing: %s" % miss)}, "missing": miss}
    main, side, corner = _stiffener_layout(spec, layout, axis, col_d_mm, col_bf_mm)
    if not main:
        return {"applied": False, "checks": {}, "note": "no gussets in the %s-axis projection zones (%s layout): "
                                                        "unstiffened model about this axis" % (axis, layout)}
    B, L, P = float(B_mm), float(L_mm), float(P_N)
    t_g, h_g, fy_g = float(spec["t_mm"]), float(spec["h_mm"]), float(spec["fy_MPa"])
    w_col = dict(spec.get("weld_column") or spec.get("weld") or {})
    w_pl = dict(spec.get("weld_plate") or spec.get("weld") or {})
    s_w = float(w_pl.get("size_mm") or 0.0) if str(w_pl.get("type") or "fillet").lower() != "cjp" else 0.0
    m_pl = (L - 0.95 * col_d_mm) / 2.0             # plate cantilever convention of the unstiffened model
    b_pl = (B - 0.8 * col_bf_mm) / 2.0
    m_g = (L - col_d_mm) / 2.0                      # gusset length: column face to plate edge
    a = anchors or {}
    checks, det = {}, {"layout": layout, "axis": axis, "gussets_main_mm": main, "gussets_side_mm": side,
                       "corner_panels_supported": corner, "gusset_length_mm": m_g}
    # ---- compression side: plate panels and gusset loads from the bearing distribution
    pfn = (lambda s: float(uniform_w)) if uniform_w is not None else _pressure_fn(bearing, P, B, L)
    w_peak = pfn(0.0)
    M_comp_st, M_side = None, None
    Vg_c = Mg_c = q_plate_c = 0.0
    if w_peak > 0.0:
        panels = _panel_moments(w_peak, B, col_bf_mm, m_pl, main, corner)
        M_comp_st = max(p_["M_per_mm"] for p_ in panels)
        w_face = pfn(m_g) if uniform_w is None else float(uniform_w)
        if side:
            sp_ = _panel_moments(w_face, col_d_mm, col_d_mm, b_pl, side, False)
        else:
            sp_ = [{"panel": "side zone 1-edge (column side) cantilever", "span_mm": b_pl,
                    "M_per_mm": w_face * b_pl * b_pl / 2.0}]
        M_side = max(p_["M_per_mm"] for p_ in sp_)
        det.update(panels_comp=panels, panels_side=sp_, w_peak_MPa=w_peak, w_face_MPa=w_face)
        F = _integrate(pfn, 0.0, m_g)                                   # N/mm across
        Mf = _integrate(lambda s: pfn(s) * (m_g - s), 0.0, m_g)         # N-mm/mm about the column face
        # gusset share of each panel = the strip-method split used for the plate (x-strips to the gussets)
        eff = [0.0] * len(main)
        for k in range(len(main) - 1):
            s_ = main[k + 1] - main[k]
            cov = main[k] >= -col_bf_mm / 2.0 - 1.0 and main[k + 1] <= col_bf_mm / 2.0 + 1.0
            al = 4.0 * m_pl ** 2 / (s_ ** 2 + 4.0 * m_pl ** 2) if cov else 1.0
            eff[k] += al * s_ / 2.0
            eff[k + 1] += al * s_ / 2.0
        for k, c_ in ((0, main[0] + B / 2.0), (len(main) - 1, B / 2.0 - main[-1])):
            if c_ > 1.0:
                two = B / 2.0 <= col_bf_mm / 2.0 + 1.0 or corner
                eff[k] += (m_pl ** 2 / (c_ ** 2 + m_pl ** 2) if two else 1.0) * c_
        trib = max(eff)
        Vg_c, Mg_c = F * trib, Mf * trib
        q_plate_c = w_peak * trib                                        # N/mm along the gusset (peak)
        det.update(gusset_share_width_mm=eff, F_per_mm=F, Mf_per_mm=Mf)
    # ---- tension side: anchor pulls into the panels
    M_ten_st, Vg_t, Mg_t, q_plate_t = None, 0.0, 0.0, 0.0
    nt = a.get("n_tension") or 0
    if T_anchor_N and T_anchor_N > 0 and a.get("f_mm") is not None and nt:
        lever = float(a["f_mm"]) - col_d_mm / 2.0
        T_one = float(T_anchor_N) / nt
        xs, rows = _anchor_positions(a, nt, "x_mm" if axis == "z" else "y_mm")
        dA = float(a.get("d_mm") or 0.0)
        if lever <= 0.0:
            M_ten_st = 0.0
        elif xs is None:
            det["tension_note"] = ("anchor positions across the plate (anchors.x_mm or n_per_row + pitch_mm) not "
                                   "declared: tension side kept on the unstiffened anchor-line cantilever; gusset "
                                   "load by tributary width")
            edges = [-B / 2.0] + [(x0 + x1) / 2.0 for x0, x1 in zip(main, main[1:])] + [B / 2.0]
            trib = max(edges[i + 1] - edges[i] for i in range(len(main)))
            Vg_t = float(T_anchor_N) * trib / B
            Mg_t = Vg_t * lever
            q_plate_t = Vg_t / max(min(trib, m_g - 2 * s_w), 1.0) / 2.0
        else:
            reac = [0.0] * len(main)
            worst, qmax = 0.0, 0.0
            pan = []
            for x in xs:
                T = T_one * rows
                if x <= main[0] or x >= main[-1]:
                    k = 0 if x <= main[0] else len(main) - 1
                    c = abs(x - main[k])
                    b_eff = min(1.2 * c + 2.0 * dA, m_g)
                    M = T * c
                    reac[k] += T
                    q = T / max(min(b_eff, m_g - 2 * s_w), 1.0) / 2.0
                    pan.append({"x_mm": x, "panel": "cantilever beyond gusset", "c_mm": c, "b_eff_mm": b_eff,
                                "M_per_mm": M / b_eff})
                else:
                    k = max(i for i in range(len(main) - 1) if main[i] <= x)
                    s = main[k + 1] - main[k]
                    a_ = x - main[k]
                    b_eff = min(2.48 * a_ * (1.0 - a_ / s) + 2.0 * dA, m_g)
                    M = T * a_ * (s - a_) / s
                    reac[k] += T * (s - a_) / s
                    reac[k + 1] += T * a_ / s
                    q = T / max(min(b_eff, m_g - 2 * s_w), 1.0) / 2.0
                    pan.append({"x_mm": x, "panel": "between gussets", "s_mm": s, "a_mm": a_, "b_eff_mm": b_eff,
                                "M_per_mm": M / b_eff})
                worst = max(worst, M / b_eff)
                qmax = max(qmax, q)
            M_ten_st = worst
            Vg_t = max(reac)
            Mg_t = Vg_t * lever
            q_plate_t = qmax
            det.update(panels_tension=pan, anchor_rows_at_x=rows, T_one_N=T_one)
    # ---- plate: governing moment per unit width (min of the stiffened and unstiffened fields per side)
    def _mn(st, un):
        v = [x for x in (st, un) if x is not None]
        return min(v) if v else None
    comp = _mn(M_comp_st, M_unstiff_comp)
    ten = _mn(M_ten_st, M_unstiff_ten)
    vals = [x for x in (comp, ten, M_side) if x is not None]
    Mu = max(vals) if vals else None
    if Mu is None:
        checks["plate_thickness"] = _check(None, t_plate_mm, clause="IS 800:2007 7.4.2 / 7.4.3.2", cite=CITE_7_4_2,
                                           ok=None, reason="bearing / anchor solution missing")
    else:
        t_req = math.sqrt(5.0 * Mu * GAMMA_M0 / fy_plate_MPa)
        Mcap = 0.2 * t_plate_mm ** 2 * fy_plate_MPa / GAMMA_M0
        c = _check(Mu, Mcap, dc=Mu / Mcap, clause="IS 800:2007 7.4.2 (gusseted base) / 7.4.3.2",
                   cite="plate moment per unit width (N-mm/mm) <= 0.2 t^2 fy/gamma_m0; DC=(t_req/t)^2; " + STIFF_PLATE_BASIS,
                   basis="EOR method, VERIFY", verify=True, M_per_mm=Mu, M_comp_side=comp, M_tension_side=ten,
                   M_side_zone=M_side, M_comp_stiffened=M_comp_st, M_comp_unstiffened=M_unstiff_comp,
                   M_ten_stiffened=M_ten_st, M_ten_unstiffened=M_unstiff_ten, t_req_mm=t_req, t_prov_mm=t_plate_mm,
                   quote_7_4_3_2=CITE_7_4_3_2, anchor_basis=STIFF_ANCHOR_BASIS if M_ten_st else None)
        c["ok"] = c["dc"] <= 1.0 and t_plate_mm > col_tf_mm
        checks["plate_thickness"] = c
    # ---- gusset: outstand (Table 2), shear (8.4.1), bending (8.2.1.2 / 9.2.2) at the column face
    eps = math.sqrt(250.0 / fy_g)
    ratio = h_g / t_g
    lims = (8.4 * eps, 9.4 * eps, 13.6 * eps)
    cls = "plastic" if ratio <= lims[0] else "compact" if ratio <= lims[1] else "semi-compact" if ratio <= lims[2] \
        else "slender"
    checks["gusset_outstand_table2"] = _geom_gate(
        ratio, lims[2], clause="IS 800:2007 Table 2 (3.7.2) / 7.4.2",
        cite="gusset = outstanding welded element h/t (one edge on the base plate, the far edge free): plastic 8.4 eps, "
             "compact 9.4 eps, semi-compact 13.6 eps; slender gussets are outside this model (stiffen the free edge, "
             "8.7.1.2)", section_class=cls, eps=eps)
    Vg, Mg = max(Vg_c, Vg_t), max(Mg_c, Mg_t)
    Vd = h_g * t_g * fy_g / (math.sqrt(3.0) * GAMMA_M0)
    checks["gusset_shear_8_4"] = _check(Vg, Vd, clause="IS 800:2007 8.4.1 / 7.4.2",
                                        cite="gusset at the column face: V <= h t fy/(sqrt3 gamma_m0) (Av = h t)",
                                        V_comp_N=Vg_c, V_ten_N=Vg_t)
    Ze, Zp = t_g * h_g ** 2 / 6.0, t_g * h_g ** 2 / 4.0
    Md = (Zp if cls in ("plastic", "compact") else Ze) * fy_g / GAMMA_M0
    cite_b = "gusset alone (base plate not counted as a flange) at the column face: Md = %s fy/gamma_m0 (8.2.1.2, %s)" % (
        "Zp" if cls in ("plastic", "compact") else "Ze", cls)
    if Vg > 0.6 * Vd:
        beta = (2.0 * Vg / Vd - 1.0) ** 2
        Md = min(Md, Zp * fy_g / GAMMA_M0 * (1.0 - beta)) if cls != "slender" else Md
        cite_b += "; high shear V > 0.6 Vd: Mdv = Md (1 - beta), beta = (2V/Vd - 1)^2, Mfd = 0 for a plate (9.2.2)"
    if cls == "slender":
        checks["gusset_bending"] = _check(Mg, None, clause="IS 800:2007 7.4.2 / 8.2.1.2", cite=cite_b, ok=False,
                                          reason="slender gusset (h/t > 13.6 eps)")
    else:
        checks["gusset_bending"] = _check(Mg, Md, clause="IS 800:2007 8.2.1.2 / 9.2.2 / 7.4.2", cite=cite_b,
                                          M_comp_Nmm=Mg_c, M_ten_Nmm=Mg_t)
    # ---- welds (10.5.7): gusset-to-column (2 lines, length h) and gusset-to-plate (2 lines, length m_g)
    def _fillet_per_mm(w):
        return fillet_weld_capacity_is800_N(size_mm=float(w["size_mm"]), length_mm=1.0, fu_MPa=float(w["fu_MPa"]),
                                            n_sides=1, site=bool(w.get("site")), gamma_mw=w.get("gamma_mw"))

    def _gmw(w):
        return w.get("gamma_mw") or (GAMMA_MW_SITE if w.get("site") else GAMMA_MW_SHOP)
    if str(w_col.get("type") or "fillet").lower() == "cjp":
        fb, qs = 6.0 * Mg / (t_g * h_g ** 2), Vg / (t_g * h_g)
        checks["gusset_weld_to_column_10_5_7"] = _check(
            math.sqrt(fb ** 2 + 3.0 * qs ** 2), fy_g / _gmw(w_col), clause="IS 800:2007 10.5.7.1.2 / 10.5.10.2.2 / 7.4.2.1",
            cite="CJP butt weld = parent metal (10.5.7.1.2: 'Butt welds shall be treated as parent metal with a "
                 "thickness equal to the throat thickness'); fe = sqrt(fb^2 + 3 q^2) <= fy/gamma_mw (10.5.10.2.2, "
                 "fbr = 0), fb = 6M/(t h^2), q = V/(t h)", weld_type="cjp", fb_MPa=fb, q_MPa=qs)
    else:
        per_mm = _fillet_per_mm(w_col)
        Lc = h_g - 2.0 * float(w_col["size_mm"])
        qv, qm = Vg / (2.0 * Lc), 6.0 * Mg / (2.0 * Lc ** 2)
        checks["gusset_weld_to_column_10_5_7"] = _check(
            math.hypot(qv, qm), per_mm.get("capacity_N"), clause="IS 800:2007 10.5.7.1.1 / 7.4.2.1",
            cite="2 fillet lines along the column face, effective length h - 2s; force per mm = sqrt((V/2L)^2 + "
                 "(6M/2L^2)^2); " + STIFF_WELD_CITE, weld_type="fillet", q_shear_N_per_mm=qv, q_moment_N_per_mm=qm,
            L_eff_mm=Lc, weld=per_mm)
    q_pl = max(q_plate_c / 2.0, q_plate_t)                              # per line (2 lines)
    cite_pl = ("gusset to base plate carrying all the bearing / anchor load (not faced for bearing, 7.4.2.1): "
               "compression side peak pressure x gusset share width; tension side anchor reaction over its "
               "effective width")
    if str(w_pl.get("type") or "fillet").lower() == "cjp":
        checks["gusset_weld_to_plate_10_5_7"] = _check(
            2.0 * q_pl / t_g, fy_g / (math.sqrt(3.0) * _gmw(w_pl)), clause="IS 800:2007 10.5.7.1.2 / 7.4.2.1",
            cite="CJP butt weld = parent metal: shear stress (line load / t) <= fy/(sqrt3 gamma_mw); " + cite_pl,
            weld_type="cjp", q_comp_N_per_mm=q_plate_c, q_ten_N_per_mm=2.0 * q_plate_t)
    else:
        per_mm = _fillet_per_mm(w_pl)
        checks["gusset_weld_to_plate_10_5_7"] = _check(
            q_pl, per_mm.get("capacity_N"), clause="IS 800:2007 10.5.7.1.1 / 7.4.2.1",
            cite="2 fillet lines, force per mm per line; " + cite_pl + "; " + STIFF_WELD_CITE, weld_type="fillet",
            q_comp_N_per_mm=q_plate_c / 2.0, q_ten_N_per_mm=q_plate_t, L_eff_mm=m_g - 2.0 * s_w, weld=per_mm)
    det.update(V_gusset_N=Vg, M_gusset_Nmm=Mg, not_checked=[
        "column wall local bending under gussets not in line with the webs/flanges (EOR)",
        "gusset sloped free edge / taper (the section at the column face governs by declaration)",
        "composite gusset + base-plate T-section (conservatively ignored)"])
    return {"applied": True, "checks": checks, "plate": Mu, "detail": det, "basis": STIFF_PLATE_BASIS,
            "clause": "IS 800:2007 7.4.2", "cite": CITE_7_4_2}


def embedded_base_checks(*, P_N, Mz_Nmm=0.0, My_Nmm=0.0, V_N=0.0, embedded=None):
    """Embedded / socket column base (X03): the socket (IS 456 concrete, outside IS 800 and the corpus) is checked
    against EOR capacities {capacity_Nmm (moment; capacity_Nmm_y for the minor axis), capacity_N (horizontal shear),
    capacity_P_N (compression, optional), capacity_T_N (uplift), source, cite}.  found:true only with source + cite
    (VERIFY); otherwise every row is not evaluated (found:false) and the base cannot be COMPLETE."""
    e = dict(embedded or {})
    Mz, My, V, P = abs(float(Mz_Nmm or 0.0)), abs(float(My_Nmm or 0.0)), abs(float(V_N or 0.0)), float(P_N or 0.0)
    found = bool(e.get("source") and e.get("cite") and e.get("capacity_Nmm"))
    cl = str(e.get("cite") or "EOR embedded-base capacity (outside IS 800)")
    base = {"verify": True, "basis": "EOR capacity (embedded/socket base), VERIFY", "eor_source": e.get("source")}
    checks = {}
    if not found:
        miss = [k for k in ("capacity_Nmm", "source", "cite") if not e.get(k)]
        checks["embedded_base_capacity"] = _check(None, None, clause="IS 800:2007 7.4.1 (base transfers P, M, V) / EOR",
                                                  cite="embedded/socket base: EOR capacity record", ok=None,
                                                  reason="found:false - EOR embedded-base capacity needs %s" % miss, **base)
    else:
        Mcz = float(e["capacity_Nmm"])
        if e.get("capacity_Nmm_y"):
            Mcy = float(e["capacity_Nmm_y"])
            checks["embedded_moment"] = _check(Mz / Mcz + My / Mcy, 1.0, clause=cl,
                                               cite="Mz/Mcz + My/Mcy <= 1 (linear interaction, EOR capacities)",
                                               Mz_Nmm=Mz, My_Nmm=My, Mcz_Nmm=Mcz, Mcy_Nmm=Mcy, **base)
        else:
            checks["embedded_moment"] = _check(math.hypot(Mz, My), Mcz, clause=cl,
                                               cite="resultant moment sqrt(Mz^2 + My^2) <= EOR capacity", Mz_Nmm=Mz,
                                               My_Nmm=My, **base)
        if e.get("capacity_N"):
            checks["embedded_shear"] = _check(V, float(e["capacity_N"]), clause=cl, cite="V <= EOR shear capacity",
                                              **base)
        else:
            checks["embedded_shear"] = _check(V, None, clause=cl, cite="V <= EOR shear capacity", ok=None,
                                              reason="capacity_N (shear) not given", **base)
        if P > 0 and e.get("capacity_P_N"):
            checks["embedded_compression"] = _check(P, float(e["capacity_P_N"]), clause=cl,
                                                    cite="P <= EOR compression capacity", **base)
        if P < 0:
            if e.get("capacity_T_N"):
                checks["embedded_uplift"] = _check(-P, float(e["capacity_T_N"]), clause=cl,
                                                   cite="uplift <= EOR tension capacity", **base)
            else:
                checks["embedded_uplift"] = _check(-P, None, clause=cl, cite="uplift <= EOR tension capacity", ok=None,
                                                   reason="net uplift and capacity_T_N not given", **base)
    oks = [c.get("ok") for c in checks.values()]
    dcs = [c.get("dc") for c in checks.values() if c.get("dc") is not None]
    return {"found": found, "base_type": "embedded", "ok": None if any(o is None for o in oks) else all(oks),
            "dc": max(dcs) if dcs else None, "checks": checks, "bearing": None, "verify": True,
            "demands": {"P_N": P, "M_Nmm": Mz, "Mz_Nmm": Mz, "My_Nmm": My, "V_N": V, "T_anchor_N": None,
                        "T_corner_anchor_N": None},
            "clause": "IS 800:2007 7.4.1 + EOR embedded-base capacity", "source_record": e.get("source"),
            "policy": "EOR capacity with source + cite (found:false otherwise); VERIFY"}


# ------------------------------------------------------------------ AUD-4: anchorage (embedment) transparency
IS456_BOND_CITE = ("IS 456:2000 26.2.1 / 26.2.1.1 development length Ld = phi sigma_s / (4 tau_bd): bond capacity "
                   "pi d L tau_bd, tau_bd increased by 60 percent for deformed bars (IS 1786) -- IS 456 is not in the "
                   "corpus: tau_bd, the bar type and L are EOR inputs (VERIFY)")
BREAKOUT_NOTE = "not covered by IS 800/IS 456 in the corpus: foundation EOR (delegated design)"
def _nonempty(x):
    return isinstance(x, str) and bool(x.strip())


def anchorage_embedment_capacity(embedment, d_mm, *, anchor_grade=None):
    """AUD-4 (gold audit M3): the per-anchor anchorage (embedment) capacity, in one of two forms:
    - derived: {method: 'bond', tau_bd_MPa (EOR design bond stress, IS 456 26.2.1.1 -- outside the corpus), bar:
      'plain' | 'deformed', L_mm (embedded length), source, cite} -> capacity = pi d L tau_bd (x 1.6 only for
      bar = 'deformed', i.e. the EOR states a deformed-bar rod; threaded rods / plain bolts get no increase);
    - asserted: {capacity_N, source, cite} -> kept, with a warning asking for the derivation.
    Returns None (no record) or {found, capacity_N, method, ..., warn?, missing?}."""
    import re as _re
    e = embedment if isinstance(embedment, dict) else None
    if not e:
        return None
    method = str(e.get("method") or "").strip().lower() or ("asserted" if e.get("capacity_N") is not None else "")
    src, cite = e.get("source"), e.get("cite")
    base = {"method": method or None, "source": src, "cite": cite, "verify": True,
            "clause": "outside IS 800 (IS 456:2000 anchorage; EOR input)"}
    if method == "bond":
        tau, L, bar = e.get("tau_bd_MPa"), e.get("L_mm"), str(e.get("bar") or "").strip().lower()
        miss = [k for k, v in (("tau_bd_MPa", tau), ("L_mm", L), ("anchor d_mm", d_mm)) if not (_isnum(v) and float(v) > 0)]
        if bar not in ("plain", "deformed"):
            miss.append("bar ('plain' | 'deformed')")
        miss += [k for k, v in (("source", src), ("cite", cite)) if not _nonempty(v)]
        if miss:
            return dict(base, found=False, capacity_N=None, missing=miss,
                        reason="found:false - embedment {method: 'bond'} missing %s" % ", ".join(miss))
        k = 1.6 if bar == "deformed" else 1.0
        cap = math.pi * float(d_mm) * float(L) * float(tau) * k
        rec = dict(base, found=True, capacity_N=cap, tau_bd_MPa=float(tau), L_mm=float(L), bar=bar, d_mm=float(d_mm),
                   deformed_factor=k, clause=IS456_BOND_CITE,
                   derivation="pi d L tau_bd%s = pi x %g x %g x %g%s = %.0f N per anchor"
                              % (" x 1.6" if k > 1 else "", float(d_mm), float(L), float(tau),
                                 " x 1.6" if k > 1 else "", cap))
        if k > 1 and _re.match(r"^\s*\d+\.\d+\s*$", str(anchor_grade or "")):
            rec["warn"] = ("anchorage: x1.6 deformed-bar bond increase (IS 456 26.2.1.1) on a property-class %s anchor "
                           "(threaded rod / bolt) -- valid only for a deformed-bar rod (IS 1786); confirm the rod type "
                           "or use bar 'plain'" % anchor_grade)
        return rec
    cap = e.get("capacity_N")
    miss = [k for k, v in (("capacity_N", cap),) if not (_isnum(v) and float(v) > 0)]
    miss += [k for k, v in (("source", src), ("cite", cite)) if not _nonempty(v)]
    if miss:
        return dict(base, method="asserted", found=False, capacity_N=float(cap) if _isnum(cap) else None, missing=miss,
                    reason="found:false - asserted embedment capacity needs capacity_N + source + cite (missing %s); "
                           "or give embedment {method: 'bond', tau_bd_MPa, bar, L_mm, source, cite}" % ", ".join(miss))
    return dict(base, method="asserted", found=True, capacity_N=float(cap),
                warn="anchorage: asserted per-anchor embedment capacity %.0f kN (%s) without a derivation -- give "
                     "embedment {method: 'bond', tau_bd_MPa, bar, L_mm, source, cite} or the EOR cone / breakout basis"
                     % (float(cap) / 1e3, str(src)[:60]))


def concrete_breakout_record(delegation=None):
    """AUD-4: concrete cone / group breakout and the pedestal are outside IS 800 / IS 456 in the corpus -> an explicit
    record; satisfied only by a cfg['delegated_design'] item for anchor breakout / pedestal design with criteria
    (india_connection_design.breakout_delegation).  Unsatisfied is a WARN, not a blocker."""
    ok = isinstance(delegation, dict)
    return {"component": "concrete_breakout", "note": BREAKOUT_NOTE, "satisfied": ok,
            "delegated_item": delegation.get("item") if ok else None,
            "delegated_criteria": delegation.get("criteria") if ok else None,
            "clause": "outside IS 800:2007 / IS 456 (corpus); foundation EOR", "gate": True, "blocks_complete": False,
            "warn": None if ok else ("anchorage: concrete cone / group breakout and the pedestal are %s -- add a "
                                     "cfg['delegated_design'] item for anchor breakout / pedestal design with criteria "
                                     "(anchor tension and shear per base)" % BREAKOUT_NOTE)}


SHEAR_KEY_BASIS = ("the key resists all base shear beyond friction (0.45 x bearing compression, IS 800 7.4.1); the "
                   "anchors are not counted together with the key (a stiff key bears before anchors in clearance holes "
                   "slip -- conservative where IS 800 is silent)")


def _isnum(x):
    return isinstance(x, (int, float)) and not isinstance(x, bool) and math.isfinite(float(x))


def shear_key_check(V_key_N, shear_key, *, job_steel_grade=None):
    """GOLD-4 (IN_Ex8): the declared base shear key / lug.  Row: V_key (shear beyond friction) <= capacity_N, the
    EOR capacity with its source and cite (IS 456 bearing / lug shear, bending and weld are outside the IS 800 base
    rules the engine checks: the capacity is an EOR record, VERIFY).  Missing capacity, source or cite -> not
    evaluated (ok None, found:false): a capacity that is subtracted from the anchor shear must be traceable."""
    sk = shear_key or {}
    cap, src, cite = sk.get("capacity_N"), sk.get("source"), sk.get("cite")
    # AUD-2: a key record that states its plate (t_mm, fy_MPa, grade?) is held to the IS 2062 Table 3 fy for that
    # thickness; a declared fy above it scales the declared capacity by fy_table / fy_declared (conservative: only the
    # plate shear / bending terms are proportional to fy, the concrete bearing term is not)
    kfy = None
    if _isnum(sk.get("fy_MPa")):
        _fyu, kfy = plate_fy_is2062(sk.get("fy_MPa"), sk.get("t_mm"), sk.get("grade"), job_grade=job_steel_grade,
                                    what="shear key plate")
        if kfy and kfy.get("reduced") and _isnum(cap):
            kfy["capacity_declared_N"] = float(cap)
            cap = float(cap) * kfy["fy_used_MPa"] / kfy["fy_declared_MPa"]
            kfy["note"] += "; declared capacity scaled by fy_table/fy_declared"
    miss = [k for k, v in (("capacity_N", cap), ("source", src), ("cite", cite))
            if not (_isnum(v) and float(v) > 0 if k == "capacity_N" else isinstance(v, str) and v.strip())]
    common = dict(clause="IS 800:2007 7.4.1 (base shear transfer) / 12.12.2; EOR shear key capacity",
                  basis=SHEAR_KEY_BASIS, capacity_source=src, capacity_cite=cite, verify=True)
    if miss:
        r = _check(V_key_N, None, cite="shear key demand <= declared capacity", found=False,
                   reason="found:false - shear key %s missing: declare shear_key = {capacity_N, source, cite} (or "
                          "shear_key_N + shear_key_source + shear_key_cite)" % "/".join(miss), **common)
        r.update(limit=float(cap) if _isnum(cap) else None, dc=None, ok=None)      # not evaluated, never a pass
        return tag_plate_fy(r, kfy)
    return tag_plate_fy(_check(V_key_N, float(cap), cite="shear key demand (shear beyond friction) <= declared "
                               "capacity: %s" % cite.strip(), **common), kfy)


def base_plate_design(*, P_N, M_Nmm=0.0, V_N=0.0, B_mm, L_mm, t_plate_mm, fy_plate_MPa, fck_MPa,
                      col_d_mm, col_bf_mm, col_tf_mm, anchors=None, Ec_MPa=None, modular_ratio=None,
                      sfrs_fixed_base=False, col_Zp_mm3=None, col_fy_MPa=None, col_Vd_N=None, shear_key_N=None,
                      shear_key=None, shear_key_source=None, shear_key_cite=None, friction_mu=0.45, weld_length_mm=None, col_perimeter_mm=None, embedment=None,
                      sfrs_moment_factor=1.2, Ec_source=None, col_A_mm2=None, stiffeners=None,
                      stiffener_axis="z", plate_grade=None, job_steel_grade=None, breakout_delegation=None):
    """Column base per IS 800 7.4 (P + M + V) - a CHECK of declared geometry; it never sizes from demand.

    Axis: moment about the axis perpendicular to L (L = plate dimension along the moment, B across).
    P_N > 0 compression. anchors = {n_total, n_tension (on the tension side), d_mm, grade, f_mm (distance of the
    tension anchor line from the plate centre), pitch_mm, edge_mm, Anb_mm2?}.
    - bearing: linear pressure <= 0.6 fck (7.4.1); e <= L/6 trapezoid, e > L/6 elastic compatibility with anchors
      (modular ratio n = E/Ec; Ec from the EOR, else IS 456:2000 6.2.3.1 Ec = 5000 sqrt(fck) - recorded as the source).
    - anchors: 10.3.5 tension, 10.3.3 shear, 10.3.6 combined; concrete embedment/pull-out is outside IS 800
      (found:false unless embedment={capacity_N, cite} is supplied by the EOR).
    - shear path: friction 0.45 x compression (7.4.1) or shear key or anchors.  A declared shear key
      (shear_key = {capacity_N, source, cite} or shear_key_N + shear_key_source + shear_key_cite) gets its own row
      'shear_key': the shear beyond friction <= the declared capacity (shear_key_check); without source + cite the
      row is found:false (not evaluated) -- an EOR capacity is never a bare number.
    - thickness: compression-side cantilever per 7.4.3.1 form (M = 0.2 t^2 fy/gamma_m0 per unit width, the
      1.2 Ze cap of 8.2.1.2 - equivalent to 7.4.3.1 with b = 0), tension-side anchor-line moment; ts > tf.
    - 12.12: for SFRS fixed bases M_dem = max(M, sfrs_moment_factor x Mp_col) (1.2 per IS 800 12.12.1; 1.1 Ry per
      IS 18168 9.3 when it governs), V_dem = max(V, 1.2 Vd_col); with col_A_mm2 the column moment is Mpc reduced for
      the concurrent P (IS 800 9.3.1.2, H08).  india_is800_s12.base_checks assembles these demands per case itself.
    - net uplift (P <= 0): anchor / bearing equilibrium (_anchor_equilibrium_uplift, H08), not |P| + 2M/L.
    - geometric feasibility: anchor pitch >= 2.5 d (10.2.2), edge >= 1.5 d0 (10.2.4.2 min edge), weld length <=
      column perimeter.
    - stiffeners (X03, opt-in): {n_per_side | x_mm, t_mm, h_mm, fy_MPa, weld{size_mm, fu_MPa, site?}, layout
      'flange_extension' | 'cross', n_per_side_y?, y_mm?} -> IS 800 7.4.2 gusseted base (stiffened_base_checks):
      plate panels (strip method, EOR method VERIFY), gusset outstand / shear / bending, gusset welds; bearing and
      anchors unchanged.  Without stiffeners the result is the unstiffened model, unchanged.
    - plate / stiffener fy (AUD-2): IS 2062:2025 Table 3 ReH for the plate thickness (plate_fy_is2062; plate_grade,
      stiffeners.grade, else job_steel_grade / inferred); a declared fy above the table value is reduced and recorded.
    """
    checks = {}
    cite_b = "IS 800:2007 7.4.1 (linear bearing, 0.6 fck)"
    fy_plate_MPa, _pfy = plate_fy_is2062(fy_plate_MPa, t_plate_mm, plate_grade, job_grade=job_steel_grade,
                                         what="base plate")
    _sfy = None
    if isinstance(stiffeners, dict) and stiffeners.get("fy_MPa"):
        stiffeners = dict(stiffeners)
        stiffeners["fy_MPa"], _sfy = plate_fy_is2062(stiffeners["fy_MPa"], stiffeners.get("t_mm"),
                                                     stiffeners.get("grade") or plate_grade, job_grade=job_steel_grade,
                                                     what="base stiffener (gusset)")
    M_dem, V_dem = abs(float(M_Nmm or 0.0)), abs(float(V_N or 0.0))
    if shear_key is not None or shear_key_N:
        sk_ = dict(shear_key) if isinstance(shear_key, dict) else {}
        if shear_key is not None and not isinstance(shear_key, dict):
            sk_["capacity_N"] = shear_key
        sk_.setdefault("capacity_N", shear_key_N)
        if shear_key_source is not None:
            sk_.setdefault("source", shear_key_source)
        if shear_key_cite is not None:
            sk_.setdefault("cite", shear_key_cite)
        shear_key, shear_key_N = sk_, (float(sk_["capacity_N"]) if _isnum(sk_.get("capacity_N")) else None)
    if sfrs_fixed_base:
        if col_Zp_mm3 and col_fy_MPa:
            Mp_ = col_Zp_mm3 * col_fy_MPa
            if col_A_mm2:
                n_ = max(float(P_N or 0.0), 0.0) / (float(col_A_mm2) * col_fy_MPa)
                Mp_ = min(1.11 * Mp_ * (1.0 - n_), Mp_)             # IS 800 9.3.1.2 (major axis) Mpc
            M12 = float(sfrs_moment_factor) * Mp_
            checks["12.12.1_moment_demand"] = {"value": M12, "clause": "IS 800:2007 12.12.1" + (
                " + IS 18168:2023 9.3" if sfrs_moment_factor > 1.2 else ""),
                                               "cite": "%.2f x %s of the column" % (sfrs_moment_factor,
                                                   "Mpc (9.3.1.2, concurrent P)" if col_A_mm2 else "full plastic moment"),
                                               "ok": True}
            M_dem = max(M_dem, M12)
        else:
            checks["12.12.1_moment_demand"] = _check(None, None, clause="IS 800:2007 12.12.1",
                                                     cite="1.2 Mp column", ok=None, reason="column Zp/fy missing")
        if col_Vd_N:
            V_dem = max(V_dem, 1.2 * col_Vd_N)
            checks["12.12.2_shear_demand"] = {"value": 1.2 * col_Vd_N, "clause": "IS 800:2007 12.12.2",
                                              "cite": "max(full shear, 1.2 x column shear capacity) (owner ruling O1: literal, "
                                                      "pinned braced-frame bases included)", "ok": True}
        else:
            checks["12.12.2_shear_demand"] = _check(None, None, clause="IS 800:2007 12.12.2", cite="1.2 Vd column",
                                                    ok=None, reason="column Vd missing")
    fb = 0.6 * float(fck_MPa)
    P = float(P_N)
    e = M_dem / P if P > 0 else None                       # None (not inf) under net uplift: JSON-safe
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
        # H08 (HR-E-11): net uplift / zero axial -> anchor and bearing equilibrium (was |P| + 2M/L on n_tension)
        if not modular_ratio and not Ec_MPa:
            Ec_MPa, Ec_source = ec_is456(fck_MPa), IS456_EC_CITE
        n = modular_ratio or ((E_MPA / Ec_MPa) if Ec_MPa else None)
        sol = _anchor_equilibrium_uplift(P, M_dem, B_mm, L_mm, a.get("f_mm"), As_t, n) \
            if a.get("f_mm") is not None else None
        if sol is None and M_dem == 0 and P <= 0:
            sol = {"T_N": -P / 2.0, "T_other_N": -P / 2.0, "C_N": 0.0, "Y_mm": 0.0, "fp_max_MPa": 0.0,
                   "method": "net uplift, no moment: shared by the anchor rows"}
        if sol is None:
            bearing.update(method="net uplift: anchor rows (n_tension, d, f_mm) and Ec needed for equilibrium")
            T_anchor = abs(P) + (2 * M_dem / L_mm if M_dem else 0.0)
            checks["anchor_tension_demand"] = _check(None, None, clause="IS 800:2007 7.4.1 / 12.12.1",
                                                     cite="anchor tension by equilibrium", ok=None,
                                                     reason="net uplift: anchor geometry (f_mm, n_tension, d) missing")
        else:
            bearing.update(sol, modular_ratio=n, Ec_MPa=Ec_MPa, Ec_source=Ec_source)
            T_anchor = sol["T_N"]
            if sol["C_N"] > 0:
                checks["bearing"] = _check(sol["fp_max_MPa"], fb, clause="IS 800:2007 7.4.1", cite=cite_b)
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
        if not (isinstance(checks.get("anchor_tension_demand"), dict) and checks["anchor_tension_demand"].get("ok") is None):
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
        if shear_key is not None:
            checks["shear_key"] = shear_key_check(max(V_dem - V_fric, 0.0), shear_key, job_steel_grade=job_steel_grade)
        if a.get("pitch_mm") is not None:
            checks["geometry_anchor_pitch"] = _geom_gate(2.5 * a["d_mm"], a["pitch_mm"], clause="IS 800:2007 10.2.2",
                                                     cite="pitch >= 2.5 d")
        if a.get("edge_mm") is not None:
            d0 = a.get("d0_mm") or (a["d_mm"] + (1 if a["d_mm"] <= 14 else 2 if a["d_mm"] <= 24 else 3))  # Table 19
            checks["geometry_anchor_edge"] = _geom_gate(1.5 * d0, a["edge_mm"], clause="IS 800:2007 10.2.4.2",
                                                    cite="edge >= 1.5 d0 (min, sheared/rough edge 1.7 d0)")
        if a.get("pitch_mm") and a.get("n_per_row"):
            span = (a["n_per_row"] - 1) * a["pitch_mm"] + 2 * (a.get("edge_mm") or 0)
            checks["geometry_anchor_fit"] = _geom_gate(span, B_mm, clause="geometric feasibility",
                                                   cite="anchor row must fit in the plate width")
        emb = anchorage_embedment_capacity(embedment if embedment else a.get("embedment"), a.get("d_mm"),
                                           anchor_grade=a.get("grade"))
        if emb and emb.get("found"):
            checks["anchorage_embedment"] = _check(
                T_one, emb["capacity_N"], clause=emb["cite"] if emb["method"] == "asserted" else emb["clause"],
                cite=("EOR/product anchorage capacity (outside IS 800), asserted: %s" % emb["source"]
                      if emb["method"] == "asserted" else "bond: %s; %s" % (emb["derivation"], emb["cite"])),
                embedment=emb)
        elif T_anchor > 0:
            checks["anchorage_embedment"] = _check(T_one, None, clause="outside IS 800 (IS 456 / product data)",
                                                   cite="concrete breakout/pull-out", ok=None, embedment=emb,
                                                   reason=(emb or {}).get("reason") or
                                                   "found:false - EOR anchorage basis not supplied")
    elif T_anchor > 0 or V_dem > friction_mu * max(P, 0.0) + (shear_key_N or 0.0):
        checks["anchors"] = _check(None, None, clause="IS 800:2007 10.3.5/10.3.6", cite="anchor rods", ok=None,
                                   reason="anchor geometry not declared (found:false)")
    else:
        checks["shear_path"] = _check(V_dem, friction_mu * max(P, 0.0) + (shear_key_N or 0.0),
                                      clause="IS 800:2007 7.4.1", cite="friction 0.45 x compression (+ key)")
    if shear_key is not None and "shear_key" not in checks:
        checks["shear_key"] = shear_key_check(max(V_dem - friction_mu * max(P, 0.0), 0.0), shear_key,
                                              job_steel_grade=job_steel_grade)
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
            # anchor line inside the column flange line -> zero lever -> zero tension-side plate moment (H08)
            lever = max(a["f_mm"] - col_d_mm / 2.0 + col_tf_mm / 2.0, 0.0)
            Mten = T_anchor * lever / B_mm
        vals = [v for v in (Mcomp, Mten) if v is not None]
        Mu = max(vals) if vals else None
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
    stiff = None
    if stiffeners:
        # X03: IS 800 7.4.2 gusseted base -- replaces the plate row (the smaller of the stiffened and unstiffened
        # fields per side), adds the gusset and gusset-weld rows; bearing (7.4.1) and anchors are unchanged
        pt = checks.get("plate_thickness") or {}
        p7 = checks.get("plate_thickness_7_4_3_1")
        uw = None
        if p7 is not None:
            uw = P / (B_mm * L_mm)
            Mc_un = 0.2 * float(p7.get("ts_mm") or 0.0) ** 2 * fy_plate_MPa / GAMMA_M0
            Mt_un = None
        else:
            Mc_un, Mt_un = pt.get("M_comp_side"), pt.get("M_tension_side")
        stiff = stiffened_base_checks(stiffeners=stiffeners, axis=stiffener_axis, P_N=P, bearing=bearing,
                                      T_anchor_N=T_anchor, anchors=a, B_mm=B_mm, L_mm=L_mm, t_plate_mm=t_plate_mm,
                                      fy_plate_MPa=fy_plate_MPa, col_d_mm=col_d_mm, col_bf_mm=col_bf_mm,
                                      col_tf_mm=col_tf_mm, M_unstiff_comp=Mc_un, M_unstiff_ten=Mt_un, uniform_w=uw)
        if stiff.get("applied"):
            checks.pop("plate_thickness_7_4_3_1", None)
            if p7 is not None:
                stiff["checks"]["plate_thickness"]["t_req_unstiffened_7_4_3_1_mm"] = p7.get("t_req_mm")
        checks.update(stiff["checks"])
    for k_, c_ in checks.items():                      # AUD-2: fy basis on every plate / stiffener row
        if k_.startswith("plate_thickness"):
            tag_plate_fy(c_, _pfy)
        elif k_.startswith("gusset_"):
            tag_plate_fy(c_, _sfy)
    if weld_length_mm is not None:
        per = col_perimeter_mm or (2 * col_bf_mm + 2 * col_d_mm - 2 * 0)  # outer outline upper bound
        checks["geometry_weld_length"] = _geom_gate(weld_length_mm, per, clause="geometric feasibility",
                                                cite="weld length <= column profile perimeter")
    oks = [c.get("ok") for c in checks.values() if isinstance(c, dict)]
    ok = (None if any(o is None for o in oks) else all(oks))
    dcs = [c.get("dc") for c in checks.values() if isinstance(c, dict) and c.get("dc") is not None]
    out = {"found": True, "ok": ok, "dc": max(dcs) if dcs else None, "checks": checks, "bearing": bearing,
           "demands": {"P_N": P, "M_Nmm": M_dem, "V_N": V_dem, "T_anchor_N": T_anchor},
           "clause": "IS 800:2007 7.4, 10.3, 12.12", "policy": "check of declared geometry; never sized from demand"}
    if a.get("d_mm") and a.get("n_total"):
        out["concrete_breakout"] = concrete_breakout_record(breakout_delegation)     # AUD-4 (record, not a check)
    out["plate_fy"] = _pfy
    if _sfy is not None:
        out["stiffener_fy"] = _sfy
    if stiff is not None:
        out["stiffened"] = {k: v for k, v in stiff.items() if k != "checks"}
        if stiff.get("applied"):
            out["clause"] = "IS 800:2007 7.4 (7.4.2 gusseted base), 10.3, 10.5.7, 12.12"
    return out


def base_plate_design_biaxial(*, P_N, Mz_Nmm=0.0, My_Nmm=0.0, V_N=0.0, B_mm, L_mm, col_d_mm, col_bf_mm, col_tf_mm,
                              anchors=None, **kw):
    """Column base under concurrent P, Mz and My (H08, HR-B-15): base_plate_design about the major axis (L along
    the column depth) and, when My != 0, about the minor axis (plate and column dimensions swapped, anchors
    f_y_mm / n_tension_y; a square plate without them assumes the same pattern, flagged).  The corner anchor carries
    the sum of the two tension-side shares, the concurrent axial counted once:
    T_corner = max(Tz(P)/nz + Ty(0)/ny, Tz(0)/nz + Ty(P)/ny), checked for 10.3.5 / 10.3.6 (and the EOR embedment)."""
    a = dict(anchors or {})
    Mz, My = abs(float(Mz_Nmm or 0.0)), abs(float(My_Nmm or 0.0))
    kw.pop("stiffener_axis", None)
    common = {k: v for k, v in kw.items() if k not in ("weld_length_mm", "col_perimeter_mm")}
    common_y = dict(common, stiffener_axis="y") if common.get("stiffeners") else common
    rz = base_plate_design(P_N=P_N, M_Nmm=Mz, V_N=V_N, B_mm=B_mm, L_mm=L_mm, col_d_mm=col_d_mm, col_bf_mm=col_bf_mm,
                           col_tf_mm=col_tf_mm, anchors=anchors, **kw)
    rz["demands"].update(Mz_Nmm=rz["demands"]["M_Nmm"], My_Nmm=My)
    if My <= 0.0:
        rz["biaxial"] = False
        return rz
    ay = dict(a)
    note = None
    if a.get("f_y_mm") is not None:
        ay["f_mm"] = a["f_y_mm"]
        ay["n_tension"] = a.get("n_tension_y") or a.get("n_tension")
    elif abs(float(B_mm) - float(L_mm)) < 1e-6:
        note = "minor-axis anchors: square plate, the major-axis pattern (f_mm, n_tension) assumed about y (flag)"
    else:
        ay = {}
    out = {"found": True, "biaxial": True, "checks": dict(rz["checks"]), "bearing": rz.get("bearing"),
           "clause": rz.get("clause"), "policy": rz.get("policy")}
    if rz.get("stiffened") is not None:
        out["stiffened"] = rz["stiffened"]
    if not ay:
        out["checks"]["y:anchors"] = _check(None, None, clause="IS 800:2007 7.4.1 / 10.3.5",
                                            cite="minor-axis moment on the base", ok=None,
                                            reason="anchors.f_y_mm / n_tension_y needed for My on a B != L plate")
        T_corner = None
    else:
        ry = base_plate_design(P_N=P_N, M_Nmm=My, V_N=0.0, B_mm=L_mm, L_mm=B_mm, col_d_mm=col_bf_mm, col_bf_mm=col_d_mm,
                               col_tf_mm=col_tf_mm, anchors=ay, **common_y)
        for k, v in ry["checks"].items():
            if k.startswith(("geometry_", "shear_path", "shear_key", "anchor_shear", "anchorage_embedment")):
                continue
            out["checks"]["y:" + k] = v
        out["bearing_y"] = ry.get("bearing")
        if ry.get("stiffened") is not None:
            out["stiffened_y"] = ry["stiffened"]
        nz, ny = a.get("n_tension") or 0, ay.get("n_tension") or 0
        T_corner = None
        if nz and ny and a.get("d_mm"):
            def _T(P, M, geo_z):
                if M <= 0:
                    return 0.0 if P >= 0 else -P / 2.0
                if geo_z:
                    r = base_plate_design(P_N=P, M_Nmm=M, V_N=0.0, B_mm=B_mm, L_mm=L_mm, col_d_mm=col_d_mm,
                                          col_bf_mm=col_bf_mm, col_tf_mm=col_tf_mm, anchors=a, **common)
                else:
                    r = base_plate_design(P_N=P, M_Nmm=M, V_N=0.0, B_mm=L_mm, L_mm=B_mm, col_d_mm=col_bf_mm,
                                          col_bf_mm=col_d_mm, col_tf_mm=col_tf_mm, anchors=ay, **common_y)
                return max(float(r["demands"]["T_anchor_N"]), 0.0)
            P = float(P_N)
            in_kern = P > 0 and (Mz / P) / (float(L_mm) / 6.0) + (My / P) / (float(B_mm) / 6.0) <= 1.0
            if in_kern:
                # resultant inside the rhombic kern of the rectangle: the whole plate bears, no anchor tension
                T_corner = 0.0
            else:
                Tz_P, Ty_P = max(float(rz["demands"]["T_anchor_N"]), 0.0), max(float(ry["demands"]["T_anchor_N"]), 0.0)
                Tz_0, Ty_0 = _T(0.0, Mz, True), _T(0.0, My, False)
                T_corner = max(Tz_P / nz + Ty_0 / ny, Tz_0 / nz + Ty_P / ny)
            one = bolt_capacity_is800(a["d_mm"], a.get("grade", "4.6"), nn=1, ns=0, e_mm=None, p_mm=None,
                                      fub_MPa=a.get("fub_MPa"), fyb_MPa=a.get("fyb_MPa"), Anb_mm2=a.get("Anb_mm2"))
            Tdb, Vdsb = one.get("Tdb_N"), one.get("Vdsb_N")
            V_one = float((rz["checks"].get("anchor_shear_10_3_3") or {}).get("value") or 0.0)
            cite = ("corner anchor: sum of the major- and minor-axis tension-side shares, axial counted once: "
                    "max(Tz(P)/nz + Ty(0)/ny, Tz(0)/nz + Ty(P)/ny)")
            if Tdb:
                out["checks"]["anchor_tension_biaxial_10_3_5"] = _check(T_corner, Tdb, clause="IS 800:2007 10.3.5",
                                                                        cite=cite + "; Tb <= Tdb")
            if Tdb and Vdsb:
                out["checks"]["anchor_combined_biaxial_10_3_6"] = _check(
                    (V_one / Vdsb) ** 2 + (T_corner / Tdb) ** 2, 1.0, clause="IS 800:2007 10.3.6",
                    cite=cite + "; (V/Vdb)^2 + (T/Tdb)^2 <= 1")
            fb = 0.6 * float(kw["fck_MPa"])
            if in_kern:
                fmax = P / (B_mm * L_mm) + 6.0 * Mz / (B_mm * L_mm ** 2) + 6.0 * My / (L_mm * B_mm ** 2)
                out["checks"]["bearing_biaxial"] = _check(fmax, fb, clause="IS 800:2007 7.4.1",
                                                          cite="corner bearing P/A + 6Mz/(B L^2) + 6My/(L B^2) <= 0.6 fck "
                                                               "(resultant within the kern)")
            else:
                fz = (rz.get("bearing") or {}).get("fp_max_MPa")
                fyp = (ry.get("bearing") or {}).get("fp_max_MPa")
                if fz is not None and fyp is not None:
                    fmax = fz + fyp - max(P, 0.0) / (B_mm * L_mm)
                    out["checks"]["bearing_biaxial"] = _check(fmax, fb, clause="IS 800:2007 7.4.1",
                                                              cite="corner bearing approximated as fp_z + fp_y - P/A "
                                                                   "(superposition of the two uniaxial solutions)")
            emb = anchorage_embedment_capacity(kw.get("embedment") or a.get("embedment"), a.get("d_mm"),
                                               anchor_grade=a.get("grade"))
            if emb and emb.get("found"):
                out["checks"]["anchorage_embedment"] = _check(
                    T_corner, emb["capacity_N"], clause=emb["cite"] if emb["method"] == "asserted" else emb["clause"],
                    cite=("EOR/product anchorage capacity (outside IS 800), biaxial corner anchor, asserted: %s"
                          % emb["source"] if emb["method"] == "asserted" else
                          "bond, biaxial corner anchor: %s; %s" % (emb["derivation"], emb["cite"])), embedment=emb)
            elif T_corner > 0:
                out["checks"]["anchorage_embedment"] = _check(T_corner, None, clause="outside IS 800 (IS 456 / product data)",
                                                              cite="concrete breakout/pull-out", ok=None, embedment=emb,
                                                              reason=(emb or {}).get("reason") or
                                                              "found:false - EOR anchorage basis not supplied")
    if note:
        out["note"] = note
    oks = [c.get("ok") for c in out["checks"].values() if isinstance(c, dict)]
    out["ok"] = None if any(o is None for o in oks) else all(oks)
    dcs = [c.get("dc") for c in out["checks"].values() if isinstance(c, dict) and c.get("dc") is not None]
    out["dc"] = max(dcs) if dcs else None
    out["demands"] = dict(rz["demands"], Mz_Nmm=rz["demands"]["M_Nmm"], My_Nmm=My, T_corner_anchor_N=T_corner)
    for k_ in ("concrete_breakout", "plate_fy", "stiffener_fy"):
        if k_ in rz:
            out[k_] = rz[k_]
    return out


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
                              pretensioned=True, bolt_type="HSFG", Anb_mm2=None, fub_MPa=None, fyb_MPa=None,
                              plate_grade=None, job_steel_grade=None):
    """Bolted end-plate moment connection: capacity = sum over tension bolt rows of (2 Te_row x h_row) where the
    bolt tension Te per bolt is limited by (i) 10.3.5 Tdb with the 10.4.7 prying force added (Te + Q <= Tdb) and
    (ii) the end-plate bending at the bolt line per pair, M = Te lv - Q le <= 1.2 (be t^2/6) fy/gamma_m0 (8.2.1.2
    cap on a plate strip).  rows = [{h_mm (lever arm from the compression flange centre), n_pairs (default 1)}].
    The compression side (flange bearing / column continuity / panel zone) is checked at the joint (12.11.2.3-.5).
    AUD-2: the end-plate fy is the IS 2062 Table 3 value for t_plate_mm (plate_fy_is2062) when the declared is higher."""
    fy_plate_MPa, _pfy = plate_fy_is2062(fy_plate_MPa, t_plate_mm, plate_grade, job_grade=job_steel_grade,
                                         what="end plate")
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
           "bolt_type": bolt_type, "type": "end_plate", "plate_fy": _pfy}
    if _pfy and _pfy.get("reduced"):
        out["note"] = _pfy["note"]
        out["cite"] = cite + "; fy by thickness: " + PLATE_FY_CLAUSE
    g = hsfg_gate(bolt_type)
    out["12.4.1"] = g
    return out


def cover_plate_moment_capacity(*, Zp_beam_mm3, fy_beam_MPa, plate_b_mm, plate_t_mm, d_beam_mm, fy_plate_MPa=None,
                                weld=None, plate_grade=None, job_steel_grade=None):
    """Reinforced (cover-plated) CJP-welded moment connection at the column face: Mcap = (Zp,beam + Zp,plates)
    fy/gamma_m0 with Zp,plates = b t (d + t) (one plate each flange); the plate-to-flange fillet welds must carry the
    plate force b t fy/gamma_m0 (10.5.7) and the plate-to-column welds are CJP (12.4.2).  weld = {size_mm, length_mm
    (per plate, total), fu_MPa, site}."""
    # AUD-2: cover-plate fy = IS 2062 Table 3 value for plate_t_mm when the declared (or beam) fy is higher
    fyp, _pfy = plate_fy_is2062(float(fy_plate_MPa or fy_beam_MPa), plate_t_mm, plate_grade, job_grade=job_steel_grade,
                                what="cover plate")
    Zp_pl = float(plate_b_mm) * float(plate_t_mm) * (float(d_beam_mm) + float(plate_t_mm))
    Mcap = (float(Zp_beam_mm3) * float(fy_beam_MPa) + Zp_pl * fyp) / GAMMA_M0
    out = {"found": True, "capacity_Nmm": Mcap, "Zp_plates_mm3": Zp_pl, "Zp_beam_mm3": float(Zp_beam_mm3),
           "cite": "IS 800:2007 8.2.1.2 (plastic section at the column face incl. cover plates) / 10.5.7.1.2 CJP",
           "type": "welded_cover_plate", "weld_type": "cjp", "plate_fy": _pfy}
    if _pfy and _pfy.get("reduced"):
        out["note"] = _pfy["note"]
        out["cite"] += "; fy by thickness: " + PLATE_FY_CLAUSE
    if weld:
        Fpl = float(plate_b_mm) * float(plate_t_mm) * fyp / GAMMA_M0
        w = fillet_weld_capacity_is800_N(**weld)
        if w.get("found"):
            out["plate_weld_check"] = tag_plate_fy(_check(Fpl, w["capacity_N"], clause="IS 800:2007 10.5.7",
                                             cite="cover-plate fillet welds carry the plate force b t fy/gamma_m0"), _pfy)
            if out["plate_weld_check"]["dc"] > 1.0:
                out["capacity_Nmm"] = (float(Zp_beam_mm3) * float(fy_beam_MPa) + Zp_pl * fyp * w["capacity_N"] / Fpl) / GAMMA_M0
                out["governing"] = "cover-plate welds"
        else:
            out["plate_weld_check"] = {"found": False, "required_inputs": w.get("required_inputs")}
    return out


def fin_plate_shear_checks(*, V_N, t_plate_mm, h_plate_mm, fy_plate_MPa, fu_plate_MPa, bolts, weld=None,
                           block_shear_areas=None, cjp=None, plate_grade=None, job_steel_grade=None, n_plates=1):
    """Simple (shear) beam-end connection: bolt group 10.3, plate shear yield 8.4.1 (Av fy/(sqrt3 gamma_m0)),
    block shear 6.4.1 (areas from block_shear_bolted_areas), plate-to-support weld 10.5.7 (fillet) or 10.5.7.1.2
    (CJP).  Returns {checks{}, capacity_N (minimum), ok, dc}.
    AUD-2: the plate fy (and the CJP parent fy at its t_mm) is the IS 2062 Table 3 value for the thickness when the
    declared value is higher (plate_fy_is2062); t_plate_mm is the total of n_plates equal plates (double fin plates:
    n_plates 2), the band is read at t_plate_mm / n_plates."""
    checks = {}
    n_pl = max(int(n_plates or 1), 1)
    fy_plate_MPa, _pfy = plate_fy_is2062(fy_plate_MPa, float(t_plate_mm) / n_pl if _isnum(t_plate_mm) else t_plate_mm,
                                         plate_grade, job_grade=job_steel_grade,
                                         what="fin / shear plate" + (" (each of %d)" % n_pl if n_pl > 1 else ""))
    _cfy = None
    if cjp and cjp.get("fy_MPa"):
        cjp = dict(cjp)
        cjp["fy_MPa"], _cfy = plate_fy_is2062(cjp["fy_MPa"], cjp.get("t_mm"), plate_grade, job_grade=job_steel_grade,
                                              what="fin plate CJP parent")
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
    for k_ in ("plate_shear_8_4_1", "block_shear_6_4_1"):
        tag_plate_fy(checks.get(k_), _pfy)
    tag_plate_fy(checks.get("support_weld") if cjp else None, _cfy)
    caps = [c["limit"] for c in checks.values() if c.get("limit")]
    oks = [c.get("ok") for c in checks.values()]
    return {"found": bool(caps), "checks": checks, "capacity_N": min(caps) if caps else None,
            "ok": None if any(o is None for o in oks) else all(oks),
            "dc": max([c["dc"] for c in checks.values() if c.get("dc") is not None] or [None]) if caps else None,
            "cite": "IS 800:2007 10.3 / 8.4.1 / 6.4.1 / 10.5.7 (simple beam-end connection)"}


def _splice_flange_force(P, Mz, My, *, Af, A, d, bf, axial_share, bearing):
    """Flange-plate force of one flange for concurrent (P, Mz, My) (H41 / H10): axial share P Af/A when the web is
    spliced (web plates) - P/2 otherwise; with machined bearing ends (IS 800 7.3.4.1) compression is carried by
    bearing and only the tension side remains; Mz/d; minor-axis moment My at the flange tips 3 My/bf (the elastic
    peak stress of My/2 on one flange, tf bf^2/6, times Af)."""
    Pax = P * (Af / A if axial_share else 0.5)
    Mterm = abs(Mz) / d + (3.0 * abs(My) / bf if (bf and My) else 0.0)
    if bearing:
        return max(Mterm - max(Pax, 0.0), 0.0) + max(-Pax, 0.0)    # tension: M/d - P Af/A (P > 0), or uplift share
    return abs(Pax) + Mterm


def column_splice_checks(*, sfrs, Af_mm2, fy_MPa, P_N, M_Nmm, Zx_mm3, A_mm2, d_mm, splice, My_Nmm=0.0, cases=None,
                         bf_mm=None, tf_mm=None, tw_mm=None, is18168=None, tie_force_N=None, Hc_mm=None,
                         Zx_lower_mm3=None, job_steel_grade=None):
    """Column splice checks of DECLARED geometry.
    IS 800: SFRS columns 12.5.2.2 (each flange splice >= 1.2 fy Af; PJP welds 200 % of required, 12.5.2.1); gravity
    columns for the member forces, per combination with concurrent P, Mz, My (H10): flange force
    P Af/A + Mz/d + 3 My/bf when the web is spliced (web_plate), P/2 + ... otherwise (H41).
    Bearing option (H41): splice['bearing'] = True (ends machined for bearing, IS 800 7.3.4.1): compression by bearing;
    the splice resists the tension side and the IS 800 5.1.2 tie force (largest factored DL + LL reaction of one
    floor, tie_force_N from the pipeline or splice['tie_force_N']).
    CJP (ruling R4, H41): a complete-penetration butt weld with matching electrode develops the parent metal
    (IS 800 10.5.7.1.2) -> deemed-to-comply gate for 12.5.2.2 / IS 18168 7.5; the weld record is required.
    IS 18168 (is18168 = {applies, system, Ry}; H10): 7.5 (12.1.4.6 SMRF, 12.2.4.6 SCBF, 12.3.4.7 EBF) - demand from
    the 5.5 combinations (cases with family '5.5'), flange and web splice plates >= 1.2 Ry x the flange / web strength;
    12.2.4.6 / 12.3.4.7 (SCBF, EBF): >= 0.5 Mp of the smaller connected member and shear > sum Mp / Hc.
    splice = {type: 'flange_plates'|'cjp'|'pjp', plate: {A_mm2, fy_MPa}, bolts: {...}, weld: {...} (fillet for the
    flange plates; CJP record {matching_electrode: bool, electrode, t_mm?}), web_plate: {A_mm2, fy_MPa, Av_mm2?},
    web_bolts: {...}, bearing: bool, tie_force_N?, Hc_mm?}.
    AUD-2: plate / web_plate {t_mm (or b_mm with A_mm2), grade?} -> fy = IS 2062 Table 3 value for that thickness when
    the declared fy is higher (plate_fy_is2062; splice['plate_grade'] or the job steel_grade otherwise)."""
    _pfy = {}
    splice = dict(splice or {})
    for key_ in ("plate", "web_plate"):
        pl_ = splice.get(key_)
        if isinstance(pl_, dict) and pl_.get("fy_MPa"):
            pl_ = dict(pl_)
            t_ = pl_.get("t_mm")
            if t_ is None and pl_.get("b_mm") and pl_.get("A_mm2"):
                t_ = float(pl_["A_mm2"]) / float(pl_["b_mm"])
            pl_["fy_MPa"], _pfy[key_] = plate_fy_is2062(pl_["fy_MPa"], t_, pl_.get("grade") or splice.get("plate_grade"),
                                                        job_grade=job_steel_grade,
                                                        what="splice %s" % key_.replace("_", " "))
            splice[key_] = pl_
    typ = str(splice.get("type") or "").lower()
    A, Af, d = float(A_mm2), float(Af_mm2), float(d_mm)
    bf = float(bf_mm) if bf_mm else None
    fy = float(fy_MPa)
    web_spliced = bool(splice.get("web_plate"))
    bearing = bool(splice.get("bearing"))
    if cases is None:
        cases = [{"combo": "governing", "P_N": P_N, "Mz_Nmm": M_Nmm, "My_Nmm": My_Nmm, "V_N": 0.0}]
    ff = []
    for c in cases:
        f = _splice_flange_force(float(c.get("P_N") or 0.0), float(c.get("Mz_Nmm", c.get("M_Nmm")) or 0.0),
                                 float(c.get("My_Nmm") or 0.0), Af=Af, A=A, d=d, bf=bf,
                                 axial_share=web_spliced or bearing, bearing=bearing)
        ff.append((f, c))
    f_t4, c_t4 = max(ff, key=lambda x: x[0]) if ff else (0.0, {})
    comps = {"member forces (concurrent P, Mz, My: %s)" % c_t4.get("combo"): f_t4}
    notes = []
    tie = tie_force_N if tie_force_N is not None else splice.get("tie_force_N")
    if bearing:
        notes.append("ends machined for bearing (IS 800 7.3.4.1): compression by bearing, splice for tension / bending")
    if tie is not None:
        # IS 800 5.1.2: 'All column splices should be capable of resisting a tensile force equal to the largest of a
        # factored dead and live load reaction from a single floor level ...' (flange plates: T/2 per flange)
        comps["IS 800 5.1.2 tie force (one flange: T/2)"] = float(tie) / 2.0
    elif bearing:
        notes.append("IS 800 5.1.2 splice tie force not supplied (splice.tie_force_N)")
    a18 = is18168 or {}
    use18 = bool(sfrs and a18.get("applies"))
    Ry = float(a18.get("Ry") or 1.0)
    if sfrs:
        comps["1.2 fy Af (IS 800 12.5.2.2)"] = 1.2 * fy * Af
        cl = "IS 800:2007 12.5.2.2"
        cite = "each flange splice >= 1.2 fy Af (Fig. 20, smaller column)"
    else:
        cl = "IS 800:2007 10 (member forces)" + (" / 7.3.4.1" if bearing else "")
        cite = "flange force %s + Mz/d + 3 My/bf per combination (concurrent)" % ("P Af/A" if (web_spliced or bearing) else "P/2")
    Mp = None
    sys18 = str(a18.get("system") or "")
    if use18:
        comps["1.2 Ry fy Af (IS 18168 7.5)"] = 1.2 * Ry * fy * Af
        f55 = [x for x in ff if str(x[1].get("family") or "") in ("5.5", "12.2.3")]
        if f55:
            f, c = max(f55, key=lambda x: x[0])
            comps["IS 18168 5.5 combination %s (7.5)" % c.get("combo")] = f
        cl += " + IS 18168:2023 7.5"
        cite += "; IS 18168 7.5: 5.5 demand, flange / web splice plates >= 1.2 Ry x their strengths"
        if sys18 in ("SCBF", "EBF"):
            Zmin = min([z for z in (Zx_mm3, Zx_lower_mm3) if z] or [Zx_mm3])
            Mp = float(Zmin) * fy
            comps["0.5 Mp / d of the smaller member (IS 18168 %s)" % ("12.2.4.6" if sys18 == "SCBF" else "12.3.4.7")] = \
                0.5 * Mp / d
            cl += " + %s" % ("12.2.4.6" if sys18 == "SCBF" else "12.3.4.7")
    Ff_dem = max(comps.values()) if comps else 0.0
    gov = max(comps, key=comps.get) if comps else None
    checks = {}
    if typ == "flange_plates":
        pl = splice.get("plate") or {}
        if pl.get("A_mm2") and pl.get("fy_MPa"):
            checks["plate_yield_6_2"] = _check(Ff_dem, float(pl["A_mm2"]) * float(pl["fy_MPa"]) / GAMMA_M0,
                                               clause=cl + " / 6.2", cite=cite + "; plate Ag fy/gamma_m0",
                                               governing_demand=gov, demand_components=comps)
        else:
            checks["plate_yield_6_2"] = _check(None, None, clause=cl + " / 6.2", cite="flange splice plate", ok=None,
                                               reason="splice.plate {A_mm2, fy_MPa} not declared")
        b = splice.get("bolts")
        if b:
            b = dict(b)
            g = bolt_group_capacity_is800(b.pop("n_bolts"), b.pop("d_mm"), b.pop("grade", "8.8"), V_N=Ff_dem, **b)
            checks["bolts_10_3"] = g["check"] if g.get("found") else _check(None, None, clause="IS 800:2007 10.3",
                                                                             cite="bolts", ok=None,
                                                                             reason=str(g.get("required_inputs")))
        w = splice.get("weld")
        if w:
            wc = fillet_weld_capacity_is800_N(**{k: v for k, v in w.items() if k in (
                "size_mm", "length_mm", "fu_MPa", "n_sides", "angle_deg", "site", "lj_mm", "throat_mm", "gamma_mw")})
            checks["plate_weld_10_5_7"] = _check(Ff_dem, wc["capacity_N"], clause="IS 800:2007 10.5.7", cite=wc["cite"]) \
                if wc.get("found") else _check(None, None, clause="IS 800:2007 10.5.7", cite="weld", ok=None,
                                               reason=str(wc.get("required_inputs")))
    elif typ == "cjp":
        w = splice.get("weld")
        gate_cl = "IS 800:2007 10.5.7.1.2 (ruling R4)" + (" / 12.5.2.2" if sfrs else "") + (" / IS 18168:2023 7.5" if use18 else "")
        if not w:
            checks["cjp_parent_metal"] = _check(None, None, clause=gate_cl, cite="CJP butt weld = parent metal", ok=None,
                                                reason="CJP splice declared without its weld record: add splice.weld = "
                                                       "{matching_electrode: true, electrode, t_mm} (IS 800 10.5.7.1.2)")
        elif w.get("matching_electrode") is True or w.get("matching") is True:
            checks["cjp_parent_metal"] = _check(True, True, clause=gate_cl, ok=True, dc=None, gate=True,
                                                electrode=w.get("electrode"),
                                                cite="complete-penetration butt weld with matching electrode develops the "
                                                     "parent metal (IS 800 10.5.7.1.2): the flange splice develops the "
                                                     "flange -> deemed to comply with the flange-force requirement "
                                                     "(ruling R4); flange plates remain the alternative")
        elif w.get("matching_electrode") is False or w.get("matching") is False:
            checks["cjp_parent_metal"] = _check(False, True, clause=gate_cl, ok=False, dc=None, gate=True,
                                                cite="an undermatched CJP does not develop the parent metal",
                                                reason="weld electrode declared not matching")
        else:
            checks["cjp_parent_metal"] = _check(None, None, clause=gate_cl, cite="CJP butt weld = parent metal", ok=None,
                                                reason="state splice.weld.matching_electrode (true for a matching "
                                                       "electrode, IS 800 10.5.7.1.2)")
    elif typ == "pjp":
        w = splice.get("weld") or {}
        t = w.get("t_mm") or (Af_mm2 / w["length_mm"] if w.get("length_mm") else None)
        wc = cjp_weld_capacity_N(t_mm=t, length_mm=w.get("length_mm"), fy_MPa=fy_MPa, n_sides=1, action="tension")
        checks["flange_weld"] = _check(Ff_dem, 0.5 * wc["capacity_N"], clause=cl + " / 12.5.2.1",
                                       cite=cite + "; butt weld = parent metal x 0.5 (PJP 200 %)") if wc.get("found") else \
            _check(None, None, clause=cl, cite="weld", ok=None, reason=str(wc.get("required_inputs")))
    else:
        checks["splice"] = _check(None, None, clause=cl, cite=cite, ok=None, reason="splice type not declared")
    # web splice (IS 18168 7.5; the web share when the web is spliced) and the 12.2.4.6 / 12.3.4.7 shear
    if typ != "cjp" and (use18 or web_spliced):
        wp = splice.get("web_plate") or {}
        Aw = (d - 2.0 * float(tf_mm)) * float(tw_mm) if (tf_mm and tw_mm) else None
        wd = {}
        if Aw:
            if use18:
                wd["1.2 Ry fy Aw (IS 18168 7.5)"] = 1.2 * Ry * fy * Aw
            Pw = max([abs(float(c.get("P_N") or 0.0)) for c in cases] + [0.0]) * Aw / A
            if web_spliced and not bearing:
                wd["web share P Aw/A"] = Pw
        if wp.get("A_mm2") and wp.get("fy_MPa") and wd:
            checks["web_plate_6_2"] = _check(max(wd.values()), float(wp["A_mm2"]) * float(wp["fy_MPa"]) / GAMMA_M0,
                                             clause=("IS 18168:2023 7.5 / " if use18 else "") + "IS 800:2007 6.2",
                                             cite="web splice plate Ag fy/gamma_m0 >= %s" % max(wd, key=wd.get),
                                             demand_components=wd)
        elif use18:
            checks["web_plate_6_2"] = _check(None, None, clause="IS 18168:2023 7.5", cite="web splice plates >= 1.2 Ry x "
                                             "web strength", ok=None,
                                             reason="splice.web_plate {A_mm2, fy_MPa} not declared (IS 18168 7.5 web "
                                                    "splice)" if Aw else "column tf / tw not supplied")
        if use18 and sys18 in ("SCBF", "EBF") and Mp:
            Hc = Hc_mm or splice.get("Hc_mm")
            Vdem = 2.0 * Mp / float(Hc) if Hc else None
            caps = []
            if wp.get("A_mm2") and wp.get("fy_MPa"):
                Av = float(wp.get("Av_mm2") or wp["A_mm2"])
                caps.append(Av * float(wp["fy_MPa"]) / (math.sqrt(3.0) * GAMMA_M0))
            wb = splice.get("web_bolts")
            if wb:
                wb = dict(wb)
                g = bolt_group_capacity_is800(wb.pop("n_bolts"), wb.pop("d_mm"), wb.pop("grade", "8.8"), **wb)
                if g.get("found"):
                    caps.append(g["capacity_N"])
            clv = "IS 18168:2023 %s" % ("12.2.4.6" if sys18 == "SCBF" else "12.3.4.7")
            if Vdem is not None and caps:
                checks["splice_shear_sumMp_Hc"] = _check(Vdem, min(caps), clause=clv,
                                                         cite="splice shear strength > sum Mp / Hc (Mp top + bottom of "
                                                              "the smaller member, Hc clear height %.0f mm)" % float(Hc))
            else:
                checks["splice_shear_sumMp_Hc"] = _check(Vdem, None, clause=clv, cite="shear > sum Mp / Hc", ok=None,
                                                         reason="web splice plate / web bolts or Hc not declared")
    tag_plate_fy(checks.get("plate_yield_6_2"), _pfy.get("plate"))
    for k_ in ("web_plate_6_2", "splice_shear_sumMp_Hc"):
        tag_plate_fy(checks.get(k_), _pfy.get("web_plate"))
    caps = [c["limit"] for c in checks.values() if isinstance(c.get("limit"), (int, float))]
    oks = [c.get("ok") for c in checks.values()]
    return {"found": bool(caps) or any(c.get("gate") for c in checks.values()), "checks": checks, "demand_N": Ff_dem,
            "demand_components": comps, "governing_demand": gov, "capacity_N": min(caps) if caps else None,
            "ok": None if any(o is None for o in oks) else all(oks),
            "dc": max([c["dc"] for c in checks.values() if c.get("dc") is not None] or [None]) if caps else None,
            "clause": cl, "cite": cite, "notes": notes, "bearing": bearing, "n_cases": len(cases)}
