"""IS 800:2007 helpers for India HR design: member capacities (WP2.3), SMF SCWB/panel zone, connection worksheets.

Grounded on local India RAG / corpus equations (IS_800_2007 pages 40–41, §12.11).
Never invent capacities: when required inputs are missing, return found:false with
required_inputs listed. Clause citations travel with every result.
"""
from __future__ import annotations

import math
from typing import Any, Dict, List, Optional, Sequence, Tuple

# Table 7 — Imperfection Factor α (Clauses 7.1.1 and 7.1.2.1) — corpus page_041
IMPERFECTION_ALPHA = {
    "a": 0.21,
    "b": 0.34,
    "c": 0.49,
    "d": 0.76,
}

E_DEFAULT_MPA = 2.0e5  # IS 800 commonly 2×10^5 MPa
GAMMA_M0_DEFAULT = 1.10  # Table 5

# Required inputs for honest found:false stubs
SCWB_REQUIRED = [
    "column_Mp_above_Nmm (or Zx_col_above_mm3 + fy_MPa)",
    "column_Mp_below_Nmm (or Zx_col_below_mm3 + fy_MPa)",
    "beam_Mp_list_Nmm (or Zx_beam_mm3 list + fy_MPa)",
]
PANEL_ZONE_REQUIRED = [
    "column_d_mm", "column_tw_mm", "column_bf_mm", "column_tf_mm",
    "beam_d_mm", "V_design_N (or Mp_beam_Nmm + L_beam_clear_mm for 12.11.2.2 shear)",
    "fy_col_MPa", "gamma_m0",
]
CONN_COMPONENT_REQUIRED = {
    "gusset": ["demand_N", "capacity_N (from RAG: Whitmore/block shear/yield)", "cited"],
    "bolts": ["demand_N", "capacity_N (from RAG: n×bolt shear/bearing/slip)", "cited"],
    "welds": ["demand_N", "capacity_N (from RAG: throat×fu×length)", "cited"],
}


def alpha_for_class(buckling_class: str) -> Dict[str, Any]:
    """Table 7 α for buckling class a/b/c/d."""
    key = (buckling_class or "").strip().lower()
    if key not in IMPERFECTION_ALPHA:
        return {
            "found": False,
            "alpha": None,
            "buckling_class": buckling_class,
            "cite": "IS 800:2007 Table 7",
            "required_inputs": ["buckling_class in {a,b,c,d}"],
            "note": "Unknown buckling class — retrieve Table 10 classification or supply a/b/c/d",
        }
    return {
        "found": True,
        "alpha": IMPERFECTION_ALPHA[key],
        "buckling_class": key,
        "cite": "IS 800:2007 Table 7 (Clauses 7.1.1, 7.1.2.1)",
    }


def infer_buckling_class_rolled_I(
    h_mm: Optional[float],
    bf_mm: Optional[float],
    tf_mm: Optional[float],
    axis: str = "y",
) -> Dict[str, Any]:
    """Conservative Table 10-ish class for hot-rolled I/H about major (z) or minor (y).

    When geometry is incomplete → found:false (do not invent class).
    Default preference when borderline: more severe class (higher α).
    """
    if not h_mm or not bf_mm or h_mm <= 0 or bf_mm <= 0:
        return {
            "found": False,
            "buckling_class": None,
            "cite": "IS 800:2007 Table 10",
            "required_inputs": ["h_mm", "bf_mm", "tf_mm", "axis"],
            "note": "Cannot classify buckling class without section geometry",
        }
    ratio = float(h_mm) / float(bf_mm)
    tf = float(tf_mm or 0.0)
    ax = (axis or "y").lower()
    # Simplified Table 10 for rolled I-sections (tf ≤ 100 mm typical building stock)
    if ratio > 1.2:
        if ax in ("z", "major", "xx", "x"):
            cls = "a" if tf <= 40 else "b"
        else:
            cls = "b"
    else:
        if ax in ("z", "major", "xx", "x"):
            cls = "b"
        else:
            cls = "c"  # minor axis, stocky flanges — curve c
    return {
        "found": True,
        "buckling_class": cls,
        "h_over_bf": round(ratio, 3),
        "axis": ax,
        "cite": "IS 800:2007 Table 10 (simplified rolled I; verify tf band)",
        "note": "Agent should confirm Table 10 row for the exact section",
    }


def non_dimensional_slenderness(
    KL_mm: float,
    r_mm: float,
    fy_MPa: float,
    E_MPa: float = E_DEFAULT_MPA,
) -> Dict[str, Any]:
    """λ = (KL/r)/π · √(fy/E)  — IS 800 §7.1.2.1."""
    if not KL_mm or not r_mm or r_mm <= 0 or not fy_MPa or not E_MPa or E_MPa <= 0:
        return {
            "found": False,
            "lambda": None,
            "cite": "IS 800:2007 §7.1.2.1",
            "required_inputs": ["KL_mm", "r_mm", "fy_MPa", "E_MPa"],
        }
    KL_r = float(KL_mm) / float(r_mm)
    lam = (KL_r / math.pi) * math.sqrt(float(fy_MPa) / float(E_MPa))
    return {
        "found": True,
        "lambda": lam,
        "KL_over_r": KL_r,
        "fy_MPa": float(fy_MPa),
        "E_MPa": float(E_MPa),
        "cite": "IS 800:2007 §7.1.2.1  λ = (KL/r)/π · √(fy/E)",
    }


def chi_reduction(
    lam: float,
    alpha: float,
) -> Dict[str, Any]:
    """χ from φ = 0.5[1+α(λ−0.2)+λ²], χ = 1/(φ+√(φ²−λ²)) ≤ 1."""
    if lam is None or alpha is None:
        return {
            "found": False,
            "chi": None,
            "phi": None,
            "cite": "IS 800:2007 §7.1.2.1",
            "required_inputs": ["lambda", "alpha (Table 7)"],
        }
    lam = float(lam)
    alpha = float(alpha)
    if lam < 0:
        return {"found": False, "chi": None, "cite": "IS 800:2007 §7.1.2.1",
                "note": "λ must be ≥ 0"}
    phi = 0.5 * (1.0 + alpha * (lam - 0.2) + lam * lam)
    disc = phi * phi - lam * lam
    if disc < 0:
        # numerical guard — clamp
        disc = 0.0
    chi = 1.0 / (phi + math.sqrt(disc))
    if chi > 1.0:
        chi = 1.0
    return {
        "found": True,
        "chi": chi,
        "phi": phi,
        "lambda": lam,
        "alpha": alpha,
        "cite": "IS 800:2007 §7.1.2.1  φ=0.5[1+α(λ−0.2)+λ²]; χ=1/(φ+√(φ²−λ²))",
    }


def design_compressive_strength(
    A_mm2: float,
    fy_MPa: float,
    KL_mm: float,
    r_mm: float,
    buckling_class: Optional[str] = None,
    gamma_m0: float = GAMMA_M0_DEFAULT,
    E_MPa: float = E_DEFAULT_MPA,
    K: float = 1.0,
) -> Dict[str, Any]:
    """Pd = Ae · fcd with fcd = χ fy / γm0  — IS 800 §7.1.2 / §7.1.2.1.

    KL_mm may already include K, or pass bare L with K factor (multiplied here).
    Missing geometry / class → found:false (no silent A·fy/γm0 invention as 'with χ').
    """
    missing = []
    if not A_mm2 or A_mm2 <= 0:
        missing.append("A_mm2")
    if not fy_MPa or fy_MPa <= 0:
        missing.append("fy_MPa")
    if not KL_mm or KL_mm <= 0:
        missing.append("KL_mm (or L_mm with K)")
    if not r_mm or r_mm <= 0:
        missing.append("r_mm (governing radius of gyration)")
    if missing:
        return {
            "found": False,
            "Pd_N": None,
            "chi": None,
            "cite": "IS 800:2007 §7.1.2 / §7.1.2.1",
            "required_inputs": missing,
            "note": "Cannot compute χ-reduced Pd without listed inputs",
        }

    if not buckling_class:
        return {
            "found": False, "Pd_N": None, "chi": None, "cite": "IS 800:2007 Table 10",
            "required_inputs": ["buckling_class from Table 10 (use buckling_class()/buckling_class_for_section())"],
            "note": "No silent default class (HR800-19)",
        }
    ares = alpha_for_class(buckling_class)
    if not ares["found"]:
        return {
            "found": False,
            "Pd_N": None,
            "chi": None,
            "cite": ares["cite"],
            "required_inputs": ares.get("required_inputs"),
            "note": ares.get("note"),
        }

    KL_eff = float(KL_mm) * float(K if K else 1.0)
    # If caller already baked K into KL_mm, pass K=1.0 (default).
    nres = non_dimensional_slenderness(KL_eff, r_mm, fy_MPa, E_MPa)
    cres = chi_reduction(nres["lambda"], ares["alpha"])
    chi = cres["chi"]
    fcd = chi * float(fy_MPa) / float(gamma_m0)
    fcd_cap = float(fy_MPa) / float(gamma_m0)
    if fcd > fcd_cap:
        fcd = fcd_cap
    Pd = float(A_mm2) * fcd  # N (mm²·MPa = N)
    return {
        "found": True,
        "Pd_N": Pd,
        "fcd_MPa": fcd,
        "chi": chi,
        "phi": cres["phi"],
        "lambda": nres["lambda"],
        "KL_over_r": nres["KL_over_r"],
        "KL_mm": KL_eff,
        "r_mm": float(r_mm),
        "A_mm2": float(A_mm2),
        "fy_MPa": float(fy_MPa),
        "gamma_m0": float(gamma_m0),
        "E_MPa": float(E_MPa),
        "buckling_class": ares["buckling_class"],
        "alpha": ares["alpha"],
        "cite": "IS 800:2007 §7.1.2 / §7.1.2.1; Table 7 α; Pd=Ae·fcd; fcd=χ fy/γm0",
    }


def scwb_ratio(
    Mpc_list_Nmm: Optional[Sequence[float]] = None,
    Mpb_list_Nmm: Optional[Sequence[float]] = None,
    *,
    columns: Optional[Sequence[Dict[str, Any]]] = None,
    beams: Optional[Sequence[Dict[str, Any]]] = None,
    fy_MPa: Optional[float] = None,
    gamma_m0: float = GAMMA_M0_DEFAULT,
    limit: float = 1.2,
) -> Dict[str, Any]:
    """ΣMpc / ΣMpb ≥ 1.2 — IS 800:2007 §12.11.3.2 (SMF).

    Accepts either precomputed Mp lists, or dicts with Zx_mm3 / Mp_Nmm.
    When inputs missing → found:false with required_inputs (not always-stub).
    """
    def _mps_from(items, explicit):
        out = []
        if explicit:
            for v in explicit:
                if v is None:
                    continue
                out.append(float(v))
            return out
        for it in items or []:
            if it is None:
                continue
            if isinstance(it, (int, float)):
                out.append(float(it))
                continue
            if it.get("Mp_Nmm") is not None:
                out.append(float(it["Mp_Nmm"]))
                continue
            zx = it.get("Zx_mm3") or it.get("Zx")
            fy = it.get("fy_MPa", fy_MPa)
            r = plastic_moment_Mp(zx, fy)          # Section 12: Mp = Zp fy (no default fy)
            if r["found"]:
                out.append(r["Mp_Nmm"])
        return out

    Mpc = _mps_from(columns, Mpc_list_Nmm)
    Mpb = _mps_from(beams, Mpb_list_Nmm)
    if len(Mpc) < 1 or len(Mpb) < 1:
        return {
            "found": False,
            "ratio": None,
            "Sum_Mpc_Nmm": sum(Mpc) if Mpc else None,
            "Sum_Mpb_Nmm": sum(Mpb) if Mpb else None,
            "pass": None,
            "limit": limit,
            "cite": "IS 800:2007 §12.11.3.2  ΣMpc/ΣMpb ≥ 1.2",
            "required_inputs": list(SCWB_REQUIRED),
            "note": "SCWB numerical ratio needs column and beam plastic moments at the joint",
        }
    sum_c = sum(Mpc)
    sum_b = sum(Mpb)
    if sum_b <= 0:
        return {
            "found": False,
            "ratio": None,
            "cite": "IS 800:2007 §12.11.3.2",
            "required_inputs": list(SCWB_REQUIRED),
            "note": "ΣMpb must be > 0",
        }
    ratio = sum_c / sum_b
    return {
        "found": True,
        "ratio": ratio,
        "Sum_Mpc_Nmm": sum_c,
        "Sum_Mpb_Nmm": sum_b,
        "Mpc_terms_Nmm": list(Mpc),
        "Mpb_terms_Nmm": list(Mpb),
        "pass": bool(ratio >= limit),
        "limit": limit,
        "cite": "IS 800:2007 §12.11.3.2  ΣMpc/ΣMpb ≥ 1.2",
        "note": "Mp = Zp fy (Section 12, characteristic) unless caller supplied Mp_Nmm; per-joint SCWB with axial "
                "reduction and model connectivity: india_is800_s12.scwb_joint / joints_from_model",
    }


def panel_zone_check(
    *,
    d_col_mm: Optional[float] = None,
    tw_mm: Optional[float] = None,
    bf_mm: Optional[float] = None,
    tf_mm: Optional[float] = None,
    d_beam_mm: Optional[float] = None,
    V_design_N: Optional[float] = None,
    fy_MPa: Optional[float] = None,
    gamma_m0: float = GAMMA_M0_DEFAULT,
    doubler_t_mm: float = 0.0,
    Av_override_mm2: Optional[float] = None,
    continuity_plates: bool = True,
    tf_beam_mm: Optional[float] = None,
) -> Dict[str, Any]:
    """Panel zone - IS 800:2007 12.11.2.3 / 12.11.2.4 (HR800-17).

    12.11.2.4: the INDIVIDUAL thickness of the column web and of each doubler plate shall satisfy
    t >= (dp + bp)/90 (dp = panel depth between continuity plates, bp = width between column flanges).
    12.11.2.3: shear buckling per 8.4.2 at the 12.11.2.2 design shear: each plate's tau_b from 8.4.2.2(a)
    (Kv from c/d with c = dp when continuity plates bound the panel, else 5.35); Vd = sum(bp t_i tau_b_i)/gamma_m0.
    V_design_N = panel shear (see india_is800_s12.panel_zone_design_shear). Missing inputs -> found:false.
    """
    missing = []
    for name, val in (("column_d_mm", d_col_mm), ("column_tw_mm", tw_mm), ("column_bf_mm", bf_mm),
                      ("column_tf_mm", tf_mm), ("beam_d_mm", d_beam_mm), ("fy_col_MPa", fy_MPa)):
        if val is None or val <= 0:
            missing.append(name)
    if V_design_N is None or V_design_N < 0:
        missing.append("V_design_N")
    if missing:
        return {"found": False, "pass": None, "doubler_required_mm": None,
                "cite": "IS 800:2007 12.11.2.3 / 12.11.2.4 / 8.4.2",
                "required_inputs": list(PANEL_ZONE_REQUIRED), "missing": missing,
                "note": "Panel-zone check cannot run without listed inputs"}
    d_col, tw, tf = float(d_col_mm), float(tw_mm), float(tf_mm)
    fy, V = float(fy_MPa), float(V_design_N)
    t_dbl = float(doubler_t_mm or 0.0)
    dp = float(d_beam_mm) - (float(tf_beam_mm) if tf_beam_mm else 0.0)
    bp = max(d_col - 2.0 * tf, 1.0)
    t_min = (float(d_beam_mm) + bp) / 90.0 if not tf_beam_mm else (dp + bp) / 90.0
    web_ok = tw >= t_min
    dbl_ok = (t_dbl >= t_min) if t_dbl > 0 else None
    thickness_ok = web_ok and (dbl_ok is not False)
    eps = math.sqrt(250.0 / fy)

    def _tau_b(t):
        dt = bp / t
        if continuity_plates:
            cd = dp / bp
            Kv = (4.0 + 5.35 / cd ** 2) if cd < 1.0 else (5.35 + 4.0 / cd ** 2)
        else:
            Kv = 5.35
        limit = 67 * eps * math.sqrt(Kv / 5.35)
        if dt <= limit:
            return fy / math.sqrt(3.0), dt, Kv, False
        tcr = Kv * math.pi ** 2 * E_DEFAULT_MPA / (12 * (1 - 0.3 ** 2) * dt ** 2)
        lw = math.sqrt(fy / (math.sqrt(3.0) * tcr))
        if lw <= 0.8:
            tb = fy / math.sqrt(3.0)
        elif lw < 1.2:
            tb = (1 - 0.8 * (lw - 0.8)) * fy / math.sqrt(3.0)
        else:
            tb = fy / (math.sqrt(3.0) * lw ** 2)
        return tb, dt, Kv, True

    plates = [("column web", tw)] + ([("doubler", t_dbl)] if t_dbl > 0 else [])
    detail = []
    Vn = 0.0
    for name, t in plates:
        tb, dt, Kv, buck = _tau_b(t)
        Vn += bp * t * tb
        detail.append({"plate": name, "t_mm": t, "t_min_mm": t_min, "t_ok": t >= t_min, "b_over_t": dt,
                       "Kv": Kv, "tau_b_MPa": tb, "shear_buckling": buck})
    if Av_override_mm2:
        Vn = float(Av_override_mm2) * fy / math.sqrt(3.0)
    Vd = Vn / float(gamma_m0)
    dc = V / Vd if Vd > 0 else None
    shear_ok = dc is not None and dc <= 1.0
    t_need_shear = 0.0
    if dc is not None and dc > 1.0:
        t_need_shear = max(0.0, V * float(gamma_m0) * math.sqrt(3.0) / (fy * bp) - tw)
    # A doubler (if needed for shear) must itself be >= t_min (12.11.2.4); a web thinner than t_min cannot be
    # cured by a doubler -> doubler_required None (change the column section).
    if not web_ok:
        doubler_req = None
    elif t_need_shear > 0:
        doubler_req = max(t_need_shear, t_min)
    else:
        doubler_req = 0.0
    return {
        "found": True, "pass": bool(thickness_ok and shear_ok), "ok": bool(thickness_ok and shear_ok),
        "thickness_ok": bool(thickness_ok), "web_thickness_ok": web_ok, "doubler_thickness_ok": dbl_ok,
        "shear_ok": shear_ok, "t_provided_mm": tw + t_dbl, "t_min_mm": t_min, "dp_mm": dp, "bp_mm": bp,
        "plates": detail, "Vd_N": Vd, "V_design_N": V, "DC_shear": dc, "dc": max(dc or 0.0, (t_min / tw) if tw else 0.0),
        "doubler_required_mm": doubler_req,
        "doubler_provided_mm": t_dbl,
        "clause": "IS 800:2007 12.11.2.3 / 12.11.2.4",
        "cite": "IS 800:2007 12.11.2.4 individual thickness t >= (dp+bp)/90; 12.11.2.3 shear buckling per 8.4.2",
        "note": ("Web alone fails 12.11.2.4; a doubler must itself satisfy t >= (dp+bp)/90 (thicknesses are not "
                 "summed) - replace the column or use a thicker web section" if not web_ok else ""),
        "inputs": {"d_col_mm": d_col_mm, "tw_mm": tw_mm, "bf_mm": bf_mm, "tf_mm": tf_mm, "d_beam_mm": d_beam_mm,
                   "V_design_N": V_design_N, "fy_MPa": fy_MPa, "gamma_m0": gamma_m0, "doubler_t_mm": doubler_t_mm},
    }


def fill_connection_component_dc(
    slot: Dict[str, Any],
    *,
    demand_N: Optional[float] = None,
    capacity_N: Optional[float] = None,
    cited: Optional[str] = None,
    size: Optional[str] = None,
    limit_state: Optional[str] = None,
    fy_MPa: Optional[float] = None,
    Ag_mm2: Optional[float] = None,
    demand_factor: Optional[float] = None,
    system: Optional[str] = None,
) -> Dict[str, Any]:
    """Fill a §12 gusset/bolt/weld slot D/C when demand + capacity are both present.

    If demand omitted but fy+Ag given, the brace capacity-design tension is system-aware (HR800-03):
    SCBF 1.1·fy·Ag (IS 800 12.8.3.1a), OCBF 1.2·fy·Ag (12.7.3.1a; the caller must still take the minimum with
    the 12.2.3 force and the system maximum). Without a system (or explicit demand_factor) no demand is formed.
    Never invents capacity_N.
    """
    out = dict(slot or {})
    component = out.get("component") or "component"
    req = list(CONN_COMPONENT_REQUIRED.get(component, ["demand_N", "capacity_N", "cited"]))

    dem = demand_N
    if dem is None and fy_MPa and Ag_mm2:
        sysu = str(system or "").upper()
        if demand_factor is None and "SCBF" in sysu:
            demand_factor, clause = 1.1, "IS 800:2007 12.8.3.1(a) 1.1 fy Ag (SCBF)"
        elif demand_factor is None and ("OCBF" in sysu or "OBF" in sysu):
            demand_factor, clause = 1.2, "IS 800:2007 12.7.3.1(a) 1.2 fy Ag (OCBF; min with 12.2.3 force and system max)"
        else:
            clause = "explicit demand_factor"
        if demand_factor is not None:
            dem = float(demand_factor) * float(fy_MPa) * float(Ag_mm2)  # MPa·mm² = N
            out["demand_basis"] = f"{demand_factor}·fy·Ag ({clause})"
        else:
            out["demand_basis"] = "system (SCBF/OCBF) not given: no capacity-design demand formed"
    if dem is not None:
        out["demand_N"] = float(dem)

    if capacity_N is not None:
        out.setdefault("capacity", {})
        if isinstance(out["capacity"], dict):
            out["capacity"]["Rn_N"] = float(capacity_N)
        else:
            out["capacity"] = {"Rn_N": float(capacity_N)}

    if cited:
        out["cited"] = cited
    if size is not None:
        out["size"] = size
    if limit_state:
        out["limit_state"] = limit_state

    cap_val = None
    if isinstance(out.get("capacity"), dict):
        cap_val = out["capacity"].get("Rn_N") or out["capacity"].get("capacity_N")
    if cap_val is None and capacity_N is not None:
        cap_val = capacity_N

    if out.get("demand_N") is None or cap_val is None:
        missing = []
        if out.get("demand_N") is None:
            missing.append("demand_N (or fy_MPa+Ag_mm2)")
        if cap_val is None:
            missing.append("capacity_N from LIVE RAG (do not invent)")
        out["found"] = False
        out["DC"] = None
        out["required_inputs"] = req
        out["missing"] = missing
        out.setdefault(
            "note",
            "Leave found:false until RAG supplies component capacity; demand alone is not enough.",
        )
        return out

    dc = float(out["demand_N"]) / float(cap_val) if float(cap_val) else None
    out["DC"] = dc
    out["found"] = True
    out.setdefault("note", "D/C from provided demand and RAG capacity — no invented capacity")
    return out


def section12_smf_worksheets_stub() -> Dict[str, Any]:
    """Seed structure for SMF capacity_design SCWB + panel-zone worksheets."""
    return {
        "status": "worksheets",
        "cite": "IS 800:2007 §12.11 SMF",
        "SCWB": {
            "found": False,
            "ratio": None,
            "cite": "IS 800:2007 §12.11.3.2",
            "required_inputs": list(SCWB_REQUIRED),
            "note": "Call india_is800.scwb_ratio(...) when column/beam Mp or Zx available",
        },
        "panel_zone": {
            "found": False,
            "cite": "IS 800:2007 §12.11.2.3–12.11.2.4",
            "required_inputs": list(PANEL_ZONE_REQUIRED),
            "note": "Call india_is800.panel_zone_check(...) when joint geometry + V_design available",
        },
    }


def apply_scwb_to_capacity_design(
    capacity_design: Dict[str, Any],
    scwb_result: Dict[str, Any],
) -> Dict[str, Any]:
    """Merge a scwb_ratio() result into capacity_design['checks']['SCWB']."""
    cd = dict(capacity_design or {})
    checks = dict(cd.get("checks") or {})
    checks["SCWB"] = dict(scwb_result)
    cd["checks"] = checks
    return cd


def apply_panel_zone_to_capacity_design(
    capacity_design: Dict[str, Any],
    pz_result: Dict[str, Any],
) -> Dict[str, Any]:
    cd = dict(capacity_design or {})
    checks = dict(cd.get("checks") or {})
    checks["panel_zone"] = dict(pz_result)
    cd["checks"] = checks
    return cd



BASE_PLATE_REQUIRED = [
    "P_N (column axial demand)", "M_Nmm (optional moment)", "fy_col_MPa",
    "concrete_fck_MPa (or found:false)", "plate_plan_mm (B×L) or size from RAG",
    "anchor bolt grade/n/diameter from RAG",
]
WELD_COMPONENT_REQUIRED = [
    "demand_N_or_Nmm", "throat_mm / size from RAG", "electrode/fu from IS 816 RAG", "length_mm",
]


def resolve_base_or_splice_geometry(cfg=None, *, geometry=None):
    """Pull disclosed base/splice plate + anchor geometry from cfg (wave4).

    Accepts cfg['base_plate_geometry'], cfg['column_base_geometry'],
    cfg['splice_geometry'], cfg['base_plate'], or a direct geometry dict.
    Never invents sizes — returns found:false when nothing disclosed.
    """
    cfg = cfg if isinstance(cfg, dict) else {}
    g = geometry if isinstance(geometry, dict) else {}
    for key in (
        "base_plate_geometry", "column_base_geometry", "splice_geometry",
        "base_plate", "column_splice",
    ):
        block = cfg.get(key)
        if isinstance(block, dict) and block:
            # shallow merge: later explicit geometry wins
            merged = dict(block)
            merged.update(g)
            g = merged
            break
    # Also accept flat cfg keys
    flat_map = {
        "plate_B_mm": ("plate_B_mm", "B_mm", "base_plate_B_mm"),
        "plate_L_mm": ("plate_L_mm", "L_mm", "base_plate_L_mm"),
        "plate_t_mm": ("plate_t_mm", "t_mm", "base_plate_t_mm"),
        "fy_plate_MPa": ("fy_plate_MPa", "fy_MPa", "plate_fy_MPa"),
        "fck_MPa": ("fck_MPa", "concrete_fck_MPa"),
        "cantilever_m_mm": ("cantilever_m_mm", "m_mm", "projection_mm"),
        "anchor_n": ("anchor_n", "n_anchors", "n"),
        "anchor_dia_mm": ("anchor_dia_mm", "dia_mm", "anchor_diameter_mm"),
        "anchor_grade": ("anchor_grade", "grade"),
        "fy_col_MPa": ("fy_col_MPa",),
    }
    out = dict(g) if g else {}
    for dest, keys in flat_map.items():
        if out.get(dest) is not None:
            continue
        for k in keys:
            if g.get(k) is not None:
                out[dest] = g[k]
                break
            if cfg.get(k) is not None and k.startswith(("plate_", "base_plate_", "anchor_", "fck", "cantilever", "fy_")):
                out[dest] = cfg[k]
                break
    has = any(
        out.get(k) is not None
        for k in (
            "plate_B_mm", "plate_L_mm", "plate_t_mm",
            "anchor_n", "anchor_dia_mm", "cantilever_m_mm",
        )
    )
    if not has:
        return {
            "found": False,
            "geometry": {},
            "required_inputs": [
                "cfg base_plate_geometry / column_base_geometry / splice_geometry "
                "(plate_t_mm, plate_B_mm, plate_L_mm, anchor_n, anchor_dia_mm, …)",
            ],
            "note": (
                "No disclosed base/splice plate or anchor geometry in cfg — "
                "found:false (do not invent plate t / B / L / anchors)."
            ),
        }
    return {
        "found": True,
        "geometry": out,
        "cite": out.get("cite") or "cfg-disclosed base/splice geometry",
        "note": "Geometry from cfg / disclosed inputs — sizes not invented.",
    }


def base_plate_bearing_capacity_N(
    *,
    plate_B_mm=None,
    plate_L_mm=None,
    bearing_stress_MPa=None,
    fck_MPa=None,
    bearing_factor=None,
    capacity_N=None,
    cite=None,
):
    """Concrete bearing under a base plate: IS 800:2007 7.4.1 bearing strength 0.6 fck (HR800-12).

    Paths: (1) capacity_N supplied; (2) B×L × bearing_stress; (3) B×L × 0.6 fck (7.4.1; bearing_factor defaults to
    the IS 800 value 0.6 - 0.45 fck 'IS 456' is not the IS 800 LSD value). Concentric load only: for P+M use
    india_connections.base_plate_design (linear bearing).
    """
    cite = cite or "IS 800:2007 7.4.1 bearing strength 0.6 fck"
    if bearing_factor is None and fck_MPa is not None:
        bearing_factor = 0.6
    if capacity_N is not None and float(capacity_N) > 0:
        return {
            "found": True,
            "capacity_N": float(capacity_N),
            "cite": cite,
            "path": "rag_capacity_N",
            "note": "Bearing capacity from LIVE RAG — not invented.",
        }
    missing = []
    stress = bearing_stress_MPa
    if stress is None and fck_MPa is not None and bearing_factor is not None:
        stress = float(bearing_factor) * float(fck_MPa)
    if plate_B_mm is None or plate_L_mm is None:
        missing.append("plate_B_mm and plate_L_mm (cfg-disclosed geometry)")
    if stress is None:
        missing.append(
            "bearing_stress_MPa OR fck_MPa (IS 800 7.4.1: 0.6 fck)"
        )
    if missing:
        return {
            "found": False,
            "capacity_N": None,
            "required_inputs": missing,
            "cite": cite,
            "note": "Bearing found:false — need RAG capacity or geometry + RAG stress/factor.",
        }
    area = float(plate_B_mm) * float(plate_L_mm)
    cap = area * float(stress)
    return {
        "found": True,
        "capacity_N": cap,
        "plate_B_mm": float(plate_B_mm),
        "plate_L_mm": float(plate_L_mm),
        "bearing_stress_MPa": float(stress),
        "area_mm2": area,
        "cite": cite,
        "path": "geometry_x_rag_stress",
        "note": "Bearing = B×L×σ_bearing — plan from cfg; stress/factor from RAG. Not invented.",
    }


def anchor_group_capacity_N(
    *,
    n_anchors=None,
    capacity_one_N=None,
    dia_mm=None,
    grade=None,
    capacity_N=None,
    cite=None,
    limit_state=None,
):
    """Anchor group axial/shear capacity — RAG total or n × RAG per-anchor.

    Never invents per-anchor capacity from dia/grade alone (need RAG V/T one).
    dia/grade may be recorded as disclosed geometry provenance.
    """
    cite = cite or "IS 800:2007 10.3.5 / 10.3.6 anchor rods (embedment outside IS 800)"
    if capacity_N is not None and float(capacity_N) > 0:
        return {
            "found": True,
            "capacity_N": float(capacity_N),
            "cite": cite,
            "path": "rag_capacity_N",
            "anchor_dia_mm": float(dia_mm) if dia_mm is not None else None,
            "anchor_grade": grade,
            "note": "Anchor capacity from LIVE RAG — not invented.",
        }
    missing = []
    if n_anchors is None or int(n_anchors) < 1:
        missing.append("n_anchors (cfg-disclosed)")
    if capacity_one_N is None or float(capacity_one_N) <= 0:
        missing.append("capacity_one_N from LIVE RAG (do not invent from dia/grade alone)")
    if missing:
        return {
            "found": False,
            "capacity_N": None,
            "required_inputs": missing,
            "cite": cite,
            "anchor_dia_mm": float(dia_mm) if dia_mm is not None else None,
            "anchor_grade": grade,
            "note": (
                "Anchors found:false — disclose n (+ dia/grade geometry OK) and RAG "
                "per-anchor capacity; never invent from size alone."
            ),
        }
    return {
        "found": True,
        "capacity_N": float(n_anchors) * float(capacity_one_N),
        "n_anchors": int(n_anchors),
        "capacity_one_N": float(capacity_one_N),
        "anchor_dia_mm": float(dia_mm) if dia_mm is not None else None,
        "anchor_grade": grade,
        "limit_state": limit_state,
        "cite": cite,
        "path": "n_x_rag_one",
        "note": "n × RAG per-anchor capacity — geometry disclosed; capacity not invented.",
    }


def base_plate_worksheet(
    *,
    P_N=None,
    M_Nmm=None,
    fy_col_MPa=None,
    fck_MPa=None,
    plate_B_mm=None,
    plate_L_mm=None,
    plate_t_mm=None,
    capacity_bearing_N=None,
    capacity_anchor_N=None,
    capacity_bending_N=None,
    capacity_bending_Nmm=None,
    fy_plate_MPa=None,
    cantilever_m_mm=None,
    bearing_pressure_MPa=None,
    bearing_stress_MPa=None,
    bearing_factor=None,
    anchor_n=None,
    anchor_dia_mm=None,
    anchor_grade=None,
    capacity_one_anchor_N=None,
    gamma_m0=None,
    cited=None,
    cfg=None,
    geometry=None,
):
    """IS 800 §7.4 / §10 base-plate component worksheet (concentric P; use india_connections.base_plate_design for P+M+V).

    Wave4: cfg-supplied geometry (plate t/B/L, anchors) + RAG capacity formulas
    close slots when present; found:false if neither RAG capacity nor
    (geometry + RAG formula inputs). Never invents plate thickness or anchor capacity.
    """
    # Merge cfg / geometry disclosures (explicit kwargs win)
    geo_res = resolve_base_or_splice_geometry(cfg, geometry=geometry)
    geo = geo_res.get("geometry") or {}
    if plate_B_mm is None:
        plate_B_mm = geo.get("plate_B_mm")
    if plate_L_mm is None:
        plate_L_mm = geo.get("plate_L_mm")
    if plate_t_mm is None:
        plate_t_mm = geo.get("plate_t_mm")
    if fy_plate_MPa is None:
        fy_plate_MPa = geo.get("fy_plate_MPa")
    if fy_col_MPa is None:
        fy_col_MPa = geo.get("fy_col_MPa")
    if fck_MPa is None:
        fck_MPa = geo.get("fck_MPa")
    if cantilever_m_mm is None:
        cantilever_m_mm = geo.get("cantilever_m_mm")
    if anchor_n is None:
        anchor_n = geo.get("anchor_n")
    if anchor_dia_mm is None:
        anchor_dia_mm = geo.get("anchor_dia_mm")
    if anchor_grade is None:
        anchor_grade = geo.get("anchor_grade")
    if bearing_stress_MPa is None and bearing_pressure_MPa is not None:
        bearing_stress_MPa = bearing_pressure_MPa
    missing = []
    if P_N is None:
        missing.append("P_N")
    slots = {
        "bearing": {
            "component": "base_plate_bearing",
            "found": False, "DC": None, "capacity": {},
            "required_inputs": ["P_N", "plate plan BxL", "fck_MPa", "bearing capacity from RAG"],
            "note": "Concrete bearing under plate - IS 800 7.4.1 (0.6 fck); found:false until geometry declared.",
        },
        "plate_bending": {
            "component": "base_plate_bending",
            "found": False, "DC": None, "capacity": {},
            "required_inputs": ["P_N", "M_Nmm", "plate_t_mm", "fy_plate", "cantilever m from RAG"],
            "note": "Plate bending thickness — RAG IS 800; do not invent t.",
        },
        "anchors": {
            "component": "anchor_bolts",
            "found": False, "DC": None, "capacity": {},
            "required_inputs": ["shear/tension demand", "n, dia, grade from RAG", "embedment"],
            "note": "Anchor rods - IS 800 10.3.5/10.3.6; found:false until declared (never sized from demand).",
        },
        "welds": {
            "component": "column_to_plate_welds",
            "found": False, "DC": None, "capacity": {},
            "required_inputs": list(WELD_COMPONENT_REQUIRED),
            "note": "Column-to-plate welds - IS 800 10.5 (12.4.2 CJP in SFRS); found:false until declared.",
        },
    }
    # Prefill demand side only
    if P_N is not None:
        for k in slots:
            slots[k]["demand_N"] = float(P_N) if k != "plate_bending" else None
            if k == "plate_bending" and M_Nmm is not None:
                slots[k]["demand_Nmm"] = float(M_Nmm)
            elif k == "plate_bending" and P_N is not None:
                slots[k]["demand_N"] = float(P_N)
    # Fill D/C when RAG capacities OR (cfg geometry + RAG formula inputs) provided
    if capacity_bearing_N is None:
        br = base_plate_bearing_capacity_N(
            plate_B_mm=plate_B_mm, plate_L_mm=plate_L_mm,
            bearing_stress_MPa=bearing_stress_MPa or bearing_pressure_MPa,
            fck_MPa=fck_MPa, bearing_factor=bearing_factor,
            cite=cited,
        )
        if br.get("found"):
            capacity_bearing_N = br["capacity_N"]
            slots["bearing"]["bearing_capacity_detail"] = br
            cited_br = br.get("cite")
        else:
            slots["bearing"]["missing"] = br.get("required_inputs")
            cited_br = None
    else:
        cited_br = cited or "IS 800:2007 7.4.1 bearing"
    if capacity_bearing_N is not None and P_N is not None:
        slots["bearing"] = fill_connection_component_dc(
            slots["bearing"], demand_N=float(P_N), capacity_N=float(capacity_bearing_N),
            cited=cited_br or cited or "IS 800:2007 7.4.1 bearing",
        )
    if capacity_anchor_N is None:
        an = anchor_group_capacity_N(
            n_anchors=anchor_n, capacity_one_N=capacity_one_anchor_N,
            dia_mm=anchor_dia_mm, grade=anchor_grade, cite=cited,
        )
        if an.get("found"):
            capacity_anchor_N = an["capacity_N"]
            slots["anchors"]["anchor_capacity_detail"] = an
            cited_an = an.get("cite")
        else:
            slots["anchors"]["missing"] = an.get("required_inputs")
            # Still record disclosed geometry on the slot for audit
            if anchor_n is not None or anchor_dia_mm is not None:
                slots["anchors"]["disclosed_geometry"] = {
                    "anchor_n": anchor_n, "anchor_dia_mm": anchor_dia_mm,
                    "anchor_grade": anchor_grade,
                }
            cited_an = None
    else:
        cited_an = cited or "IS 800 anchors"
    if capacity_anchor_N is not None and P_N is not None:
        slots["anchors"] = fill_connection_component_dc(
            slots["anchors"], demand_N=float(P_N), capacity_N=float(capacity_anchor_N),
            cited=cited_an or cited or "IS 800 anchors",
        )
    # Plate bending thickness / capacity — IS 800 LSD cantilever; no invent t
    bend = base_plate_bending_check(
        P_N=P_N,
        M_Nmm=M_Nmm,
        plate_B_mm=plate_B_mm,
        plate_L_mm=plate_L_mm,
        plate_t_mm=plate_t_mm,
        fy_plate_MPa=fy_plate_MPa or fy_col_MPa,
        cantilever_m_mm=cantilever_m_mm,
        bearing_pressure_MPa=bearing_pressure_MPa,
        capacity_bending_N=capacity_bending_N,
        capacity_bending_Nmm=capacity_bending_Nmm,
        gamma_m0=gamma_m0,
        cited=cited,
    )
    slots["plate_bending"] = {**slots["plate_bending"], **{
        k: bend[k] for k in (
            "found", "DC", "capacity", "required_inputs", "note", "cited",
            "t_required_mm", "t_provided_mm", "m_mm", "w_MPa", "missing",
        ) if k in bend
    }}
    if bend.get("found"):
        slots["plate_bending"]["capacity"] = bend.get("capacity") or {
            "t_required_mm": bend.get("t_required_mm"),
            "capacity_N": bend.get("capacity_N"),
            "capacity_Nmm": bend.get("capacity_Nmm"),
        }
        slots["plate_bending"]["cited"] = bend.get("cite") or bend.get("cited")
    else:
        slots["plate_bending"]["missing"] = bend.get("required_inputs") or bend.get("missing")
        slots["plate_bending"]["note"] = bend.get("note") or slots["plate_bending"]["note"]
    any_filled = any(s.get("found") is True for s in slots.values())
    return {
        "status": "worksheets",
        "found": any_filled,  # True only if at least one component closed from RAG
        "cite": "IS 800:2007 7.4 (bases), 10.3 (anchors), 10.5 (welds)",
        "required_inputs": list(BASE_PLATE_REQUIRED) if missing or not any_filled else [],
        "missing_top": missing,
        "geometry": {
            "plate_B_mm": plate_B_mm, "plate_L_mm": plate_L_mm, "plate_t_mm": plate_t_mm,
            "fy_col_MPa": fy_col_MPa, "fck_MPa": fck_MPa,
            "cantilever_m_mm": cantilever_m_mm,
            "anchor_n": anchor_n, "anchor_dia_mm": anchor_dia_mm,
            "anchor_grade": anchor_grade,
            "cfg_geometry_found": bool(geo_res.get("found")),
        },
        "slots": list(slots.values()),
        "policy": (
            "Fill component capacities from LIVE RAG, or cfg-disclosed geometry + RAG "
            "capacity formulas. Demand may be prefilled from analysis; never invent "
            "plate t, bearing stress, anchors, or weld size."
        ),
        "note": (
            "Base-plate worksheet seeded. found:false on slots until RAG capacities "
            "or (cfg geometry + RAG formula inputs) present."
            if not any_filled else
            "One or more base-plate components filled from RAG and/or cfg geometry + RAG formulas."
        ),
    }


def section12_or_base_connection_stubs(role="brace"):
    """Route to brace §12 stubs or base-plate worksheet structure by role."""
    r = (role or "").lower()
    if "base" in r:
        return base_plate_worksheet()
    # default brace/gusset path kept in design_pipeline._section12_component_stubs
    return {
        "status": "defer_to_section12_component_stubs",
        "note": "Use design_pipeline._section12_component_stubs for gusset/bolt/weld",
    }


# --- complete-gap wave2: RAG → component capacity / D/C -----------------------

def fillet_weld_capacity_N(
    *,
    throat_mm=None,
    size_mm=None,
    length_mm=None,
    permissible_stress_MPa=None,
    permissible_stress_kgf_cm2=None,
    cite=None,
    n_sides=1,
    method=None,
):
    """IS 816:1969 WORKING-STRESS fillet weld value (HR800-10). Only with explicit method='WSM'.

    Returns permissible_N (working load) - never capacity_N: a working-stress value must not be compared with a
    factored (LSD) demand. For IS 800 LSD use fillet_weld_capacity_is800_N. Throat = 0.7 s (K, 90-degree faces).
    """
    if str(method or "").upper() != "WSM":
        return {"found": False, "capacity_N": None, "permissible_N": None, "method": method,
                "cite": cite or "IS 816:1969 7.1.2 (working stress)",
                "required_inputs": ["method='WSM' (IS 816 is working stress; use fillet_weld_capacity_is800_N for LSD)"]}
    missing = []
    stress = permissible_stress_MPa
    if stress is None and permissible_stress_kgf_cm2 is not None:
        stress = float(permissible_stress_kgf_cm2) * 0.0980665   # 1 kgf/cm2 = 0.0980665 MPa
    if stress is None:
        missing.append("permissible_stress_MPa or permissible_stress_kgf_cm2 (IS 816)")
    a = throat_mm
    if a is None and size_mm is not None:
        a = 0.70 * float(size_mm)
    if a is None or float(a) <= 0:
        missing.append("throat_mm or size_mm (leg)")
    if length_mm is None or float(length_mm) <= 0:
        missing.append("length_mm")
    if missing:
        return {"found": False, "capacity_N": None, "permissible_N": None, "method": "WSM",
                "cite": cite or "IS 816:1969 §7.1.2", "required_inputs": missing}
    perm = float(stress) * float(a) * float(length_mm) * float(n_sides or 1)
    return {"found": True, "capacity_N": None, "permissible_N": perm, "method": "WSM", "throat_mm": float(a),
            "size_mm": float(size_mm) if size_mm is not None else None, "length_mm": float(length_mm),
            "n_sides": int(n_sides or 1), "stress_MPa": float(stress),
            "cite": cite or "IS 816:1969 §7.1.2 fillet weld permissible stress (working stress)",
            "note": "Working-stress permissible load: compare only with SERVICE-level demand."}


def bolt_group_capacity_N(
    *,
    n_bolts=None,
    V_one_bolt_N=None,
    cite=None,
    limit_state=None,
    d_mm=None,
    grade=None,
    **geometry,
):
    """Bolt-group capacity = n x Vdb (IS 800 10.3.2). With d_mm + grade (+ plate t, fu, e, p, d0) the per-bolt
    value is computed by india_connections.bolt_capacity_is800 (10.3.3 + 10.3.4); a supplied V_one_bolt_N must be an
    IS 800 LSD value with a cite. Never an IS 4000 working value (HR800-09)."""
    if n_bolts and d_mm and grade:
        import india_connections as _C
        g = _C.bolt_group_capacity_is800(n_bolts, d_mm, grade, **geometry)
        g.setdefault("limit_state", limit_state or "10.3.2 min(Vdsb, Vdpb)")
        return g
    missing = []
    if n_bolts is None or int(n_bolts) < 1:
        missing.append("n_bolts")
    if V_one_bolt_N is None or float(V_one_bolt_N) <= 0:
        missing.append("d_mm + grade + plate t/fu/e/p/d0 (IS 800 10.3), or V_one_bolt_N (IS 800 LSD) with cite")
    if missing:
        return {"found": False, "capacity_N": None, "cite": cite or "IS 800:2007 10.3",
                "required_inputs": missing, "note": "Do not invent bolt capacity."}
    return {"found": True, "capacity_N": float(n_bolts) * float(V_one_bolt_N), "n_bolts": int(n_bolts),
            "V_one_bolt_N": float(V_one_bolt_N), "limit_state": limit_state,
            "cite": cite or "IS 800:2007 10.3", "note": "n x supplied per-bolt IS 800 LSD capacity."}


def apply_rag_capacities_to_connection(
    connection: Dict[str, Any],
    *,
    rag_capacities: Optional[Dict[str, Any]] = None,
    demand_N: Optional[float] = None,
) -> Dict[str, Any]:
    """Fill gusset/bolt/weld / base-plate slots from a RAG capacity map.

    rag_capacities keys (any subset):
      welds: {capacity_N|throat_mm+size_mm+length_mm+stress..., cite}
      bolts: {capacity_N|n_bolts+V_one_bolt_N, cite}
      gusset: {capacity_N, cite}
      bearing / anchors: {capacity_N, cite} for base plate

    found:false on any component whose RAG capacity is missing — never invent.
    """
    conn = dict(connection or {})
    rag = rag_capacities or conn.get("rag_capacities") or {}
    dem = demand_N
    if dem is None and isinstance(conn.get("demand"), dict):
        d = conn["demand"]
        # HR800-03: brace connections use the Section 12 capacity-design force when it is recorded
        dem = d.get("Pu_capacity_design_N") or d.get("axial_N") or d.get("P_N") or d.get("V_N")

    # Prefer existing worksheet slots
    ws = conn.get("section12_worksheet") or conn.get("base_plate_worksheet")
    if not isinstance(ws, dict):
        ws = {"status": "stubs", "slots": [], "fill_helper": "india_is800.fill_connection_component_dc"}

    slots = list(ws.get("slots") or [])
    if not slots and conn.get("component_checks"):
        slots = []
        for name, slot in (conn.get("component_checks") or {}).items():
            s = dict(slot or {})
            s.setdefault("component", name)
            slots.append(s)

    def _cap_for(component: str):
        aliases = {
            "welds": ["welds", "weld", "column_to_plate_welds"],
            "bolts": ["bolts", "bolt", "bolt_group"],
            "gusset": ["gusset", "gusset_plate"],
            "base_plate_bearing": ["bearing", "base_plate_bearing"],
            "anchor_bolts": ["anchors", "anchor_bolts", "anchor"],
            "base_plate_bending": ["plate_bending", "base_plate_bending"],
            "end_plate_or_continuity": ["end_plate_or_continuity", "end_plate", "continuity", "gusset"],
            "gusset_whitmore": ["gusset_whitmore", "whitmore", "gusset"],
            "gusset_block_shear": ["gusset_block_shear", "block_shear", "block_shear_gusset"],
            "column_axial_Pn": ["column_axial_Pn", "axial_Pn", "splice_Pn", "base_Pn"],
        }
        # Direct + forward aliases
        keys = list(aliases.get(component, [])) + [component]
        # Reverse: if component is an alias value, include the group keys
        for group, names in aliases.items():
            if component in names or component == group:
                keys.extend(names)
                keys.append(group)
        seen = set()
        for k in keys:
            if k in seen:
                continue
            seen.add(k)
            if k in rag and rag[k] is not None and rag[k] != {}:
                return rag[k]
        return None

    filled_slots = []
    for slot in slots:
        comp = slot.get("component") or "component"
        rag_c = _cap_for(comp)
        cap_N = None
        cited = None
        if isinstance(rag_c, (int, float)):
            cap_N = float(rag_c)
        elif isinstance(rag_c, dict):
            cited = rag_c.get("cite") or rag_c.get("cited")
            if rag_c.get("capacity_N") is not None:
                cap_N = float(rag_c["capacity_N"])
            elif comp in ("welds", "column_to_plate_welds") or "weld" in str(comp):
                if rag_c.get("fu_MPa") is not None:
                    w = fillet_weld_capacity_is800_N(
                        throat_mm=rag_c.get("throat_mm"), size_mm=rag_c.get("size_mm") or rag_c.get("leg_mm"),
                        length_mm=rag_c.get("length_mm"), fu_MPa=rag_c.get("fu_MPa"),
                        n_sides=rag_c.get("n_sides", 1), site=bool(rag_c.get("site")), lj_mm=rag_c.get("lj_mm"),
                        cite=cited,
                    )
                else:
                    w = {"found": False, "required_inputs": [
                        "fu_MPa + size_mm + length_mm (IS 800 10.5.7 LSD); IS 816 working-stress values are not "
                        "compared with factored demand"]}
                if w.get("found"):
                    cap_N = w["capacity_N"]
                    cited = w.get("cite")
                    slot = dict(slot)
                    slot["weld_capacity_detail"] = w
                else:
                    slot = fill_connection_component_dc(slot, demand_N=dem, capacity_N=None)
                    slot["missing_rag"] = w.get("required_inputs")
                    filled_slots.append(slot)
                    continue
            elif "bolt" in str(comp):
                geo = {k: rag_c[k] for k in ("t_mm", "fu_plate_MPa", "e_mm", "p_mm", "d0_mm", "nn", "ns", "lj_mm",
                                             "lg_mm", "hole") if rag_c.get(k) is not None}
                b = bolt_group_capacity_N(
                    n_bolts=rag_c.get("n_bolts") or rag_c.get("n"),
                    V_one_bolt_N=rag_c.get("V_one_bolt_N") or rag_c.get("Vdsb_N"),
                    cite=cited, limit_state=rag_c.get("limit_state"),
                    d_mm=rag_c.get("d_mm") or rag_c.get("diameter_mm"), grade=rag_c.get("grade"), **geo,
                )
                if b.get("found"):
                    cap_N = b["capacity_N"]
                    cited = b.get("cite")
                    slot = dict(slot)
                    slot["bolt_capacity_detail"] = b
                else:
                    slot = fill_connection_component_dc(slot, demand_N=dem, capacity_N=None)
                    slot["missing_rag"] = b.get("required_inputs")
                    filled_slots.append(slot)
                    continue
            elif "bearing" in str(comp) or comp == "base_plate_bearing":
                br = base_plate_bearing_capacity_N(
                    plate_B_mm=rag_c.get("plate_B_mm") or rag_c.get("B_mm"),
                    plate_L_mm=rag_c.get("plate_L_mm") or rag_c.get("L_mm"),
                    bearing_stress_MPa=rag_c.get("bearing_stress_MPa") or rag_c.get("stress_MPa"),
                    fck_MPa=rag_c.get("fck_MPa"),
                    bearing_factor=rag_c.get("bearing_factor"),
                    capacity_N=rag_c.get("capacity_N"),
                    cite=cited,
                )
                if br.get("found"):
                    cap_N = br["capacity_N"]
                    cited = br.get("cite")
                    slot = dict(slot)
                    slot["bearing_capacity_detail"] = br
                else:
                    slot = fill_connection_component_dc(slot, demand_N=dem, capacity_N=None)
                    slot["missing_rag"] = br.get("required_inputs")
                    filled_slots.append(slot)
                    continue
            elif "anchor" in str(comp):
                an = anchor_group_capacity_N(
                    n_anchors=rag_c.get("n_anchors") or rag_c.get("n") or rag_c.get("anchor_n"),
                    capacity_one_N=rag_c.get("capacity_one_N") or rag_c.get("V_one_N"),
                    dia_mm=rag_c.get("dia_mm") or rag_c.get("anchor_dia_mm"),
                    grade=rag_c.get("grade") or rag_c.get("anchor_grade"),
                    capacity_N=rag_c.get("capacity_N"),
                    cite=cited,
                )
                if an.get("found"):
                    cap_N = an["capacity_N"]
                    cited = an.get("cite")
                    slot = dict(slot)
                    slot["anchor_capacity_detail"] = an
                else:
                    slot = fill_connection_component_dc(slot, demand_N=dem, capacity_N=None)
                    slot["missing_rag"] = an.get("required_inputs")
                    filled_slots.append(slot)
                    continue
            elif "end_plate" in str(comp) or "continuity" in str(comp):
                ep = end_plate_or_continuity_capacity_N(
                    capacity_N=rag_c.get("capacity_N") or rag_c.get("Rn"),
                    Rn=rag_c.get("Rn"),
                    cite=cited or rag_c.get("cite"),
                    source=rag_c.get("source") or rag_c.get("Rn_source"),
                    limit_state=rag_c.get("limit_state"),
                    demand_N=dem,
                )
                if ep.get("found"):
                    cap_N = ep["capacity_N"]
                    cited = ep.get("cite")
                    slot = dict(slot)
                    slot["end_plate_detail"] = ep
                else:
                    slot = fill_connection_component_dc(slot, demand_N=dem, capacity_N=None)
                    slot["missing_rag"] = ep.get("required_inputs")
                    filled_slots.append(slot)
                    continue
        slot = fill_connection_component_dc(
            slot, demand_N=dem, capacity_N=cap_N, cited=cited,
        )
        filled_slots.append(slot)

    ws = dict(ws)
    ws["slots"] = filled_slots
    ws["status"] = "filled" if any(s.get("found") for s in filled_slots) else ws.get("status", "stubs")
    if "base_plate" in str(conn.get("type") or "").lower() or conn.get("base_plate_worksheet"):
        conn["base_plate_worksheet"] = ws
    else:
        conn["section12_worksheet"] = ws
    conn["component_checks"] = {
        s.get("component"): {
            "found": s.get("found"), "DC": s.get("DC"),
            "demand_N": s.get("demand_N"), "capacity": s.get("capacity"),
            "cited": s.get("cited"), "note": s.get("note"),
            "required_inputs": s.get("required_inputs"),
            "missing": s.get("missing"),
        }
        for s in filled_slots if s.get("component")
    }
    # Parent connection DC = max of filled component DCs when any found
    dcs = [s["DC"] for s in filled_slots if s.get("found") and s.get("DC") is not None]
    if dcs:
        conn["DC"] = max(dcs)
        conn["found_components"] = True
        conn["limit_state"] = conn.get("limit_state") or "component D/C from RAG capacities"
        if not conn.get("cited"):
            cites = [s.get("cited") for s in filled_slots if s.get("cited")]
            if cites:
                conn["cited"] = cites[0]
    return conn


def scwb_and_panel_from_schedule(
    *,
    column_props: Optional[Sequence[Dict[str, Any]]] = None,
    beam_props: Optional[Sequence[Dict[str, Any]]] = None,
    fy_MPa: Optional[float] = None,
    V_design_N: Optional[float] = None,
    panel_col: Optional[Dict[str, Any]] = None,
    panel_beam_d_mm: Optional[float] = None,
) -> Dict[str, Any]:
    """Compute SCWB + panel-zone when schedule Mp/geometry inputs exist (wave2).

    Returns dict with SCWB / panel_zone results (found:false if inputs missing).
    """
    scwb = scwb_ratio(columns=column_props, beams=beam_props, fy_MPa=fy_MPa)
    pz_kwargs = {}
    pc = panel_col or ((column_props or [None])[0] if column_props else None) or {}
    if isinstance(pc, dict):
        pz_kwargs = dict(
            d_col_mm=pc.get("d_mm") or pc.get("d"),
            tw_mm=pc.get("tw_mm") or pc.get("tw"),
            bf_mm=pc.get("bf_mm") or pc.get("bf"),
            tf_mm=pc.get("tf_mm") or pc.get("tf"),
            fy_MPa=pc.get("fy_MPa", fy_MPa),
        )
    pz_kwargs["d_beam_mm"] = panel_beam_d_mm
    if panel_beam_d_mm is None and beam_props:
        b0 = beam_props[0] if beam_props else {}
        if isinstance(b0, dict):
            pz_kwargs["d_beam_mm"] = b0.get("d_mm") or b0.get("d")
    pz_kwargs["V_design_N"] = V_design_N
    pz = panel_zone_check(**{k: v for k, v in pz_kwargs.items() if v is not None})
    return {"SCWB": scwb, "panel_zone": pz}


# --- IS 4000:1992 Table 2 - WORKING-STRESS permissible applied forces (HR800-09) ---------------------------------
# IS 4000:1992 Table 2 "Maximum Permissible Applied Forces for Joints" (pdf p.4) - working loads, Note 2:
# Vob = 0.25 x Rm,min x stress area. Kept ONLY as permissible_N (serviceability / installation data); IS 800 LSD
# bolt capacity is india_connections.bolt_capacity_is800 (M20 8.8 thread 90.5 kN vs 50.8 kN here).
# M30 10.9 shank prints "148" in the PDF - a misprint: 0.25 x 1040 x 706 = 183.6 kN (thread 146 = 0.25x1040x561).
IS4000_TABLE2_Vob_kN = {
    (16, "8.8", "shank"): 40.2, (16, "8.8", "thread"): 31.4,
    (16, "10.9", "shank"): 52.3, (16, "10.9", "thread"): 40.8,
    (20, "8.8", "shank"): 65.2, (20, "8.8", "thread"): 50.8,
    (20, "10.9", "shank"): 81.6, (20, "10.9", "thread"): 63.7,
    (24, "8.8", "shank"): 93.8, (24, "8.8", "thread"): 73.2,
    (24, "10.9", "shank"): 117.0, (24, "10.9", "thread"): 91.8,
    (30, "8.8", "shank"): 146.0, (30, "8.8", "thread"): 116.0,
    (30, "10.9", "shank"): 183.6, (30, "10.9", "thread"): 146.0,
    (36, "8.8", "shank"): 211.0, (36, "8.8", "thread"): 169.0,
    (36, "10.9", "shank"): 264.0, (36, "10.9", "thread"): 212.0,
}
IS4000_TABLE2_CITE = (
    "IS 4000:1992 Table 2 - Maximum Permissible Applied Forces for Joints (working stress, Vob); "
    "M30 10.9 shank corrected 148 -> 183.6 kN (0.25 Rm As)"
)

# IS 800 Table 5 gamma_mw: shop 1.25, site 1.50
GAMMA_MW_SHOP = 1.25
GAMMA_MW_SITE = 1.50


def is4000_bolt_shear_capacity_N(
    *,
    n_bolts=None,
    diameter_mm=None,
    property_class="8.8",
    plane="thread",
    cite=None,
):
    """n x Vob from IS 4000 Table 2 as a WORKING-STRESS permissible_N (never an LSD capacity_N)."""
    missing = []
    if n_bolts is None or int(n_bolts) < 1:
        missing.append("n_bolts")
    if diameter_mm is None:
        missing.append("diameter_mm (M16/M20/M24/M30/M36)")
    key = None
    if diameter_mm is not None:
        key = (int(diameter_mm), str(property_class), str(plane).lower())
        if key not in IS4000_TABLE2_Vob_kN:
            missing.append("diameter/property_class/plane in IS 4000 Table 2")
    if missing:
        return {"found": False, "capacity_N": None, "permissible_N": None,
                "cite": cite or IS4000_TABLE2_CITE, "required_inputs": missing}
    Vob_kN = IS4000_TABLE2_Vob_kN[key]
    return {
        "found": True, "capacity_N": None, "method": "WSM",
        "permissible_N": float(n_bolts) * Vob_kN * 1000.0,
        "Vob_one_kN": Vob_kN, "n_bolts": int(n_bolts), "diameter_mm": int(diameter_mm),
        "property_class": str(property_class), "plane": str(plane).lower(),
        "cite": cite or IS4000_TABLE2_CITE,
        "note": "Working-stress permissible load (IS 4000). Not an IS 800 LSD capacity: use "
                "india_connections.bolt_capacity_is800.",
    }


def fillet_weld_capacity_is800_N(
    *,
    throat_mm=None,
    size_mm=None,
    length_mm=None,
    fu_MPa=None,
    gamma_mw=None,
    n_sides=1,
    cite=None,
    site=False,
    lj_mm=None,
    angle_deg=90.0,
):
    """IS 800:2007 LSD fillet weld (delegates to india_connections): throat K s (Table 22, 0.70), fwd =
    fu/(sqrt3 gamma_mw) (10.5.7.1.1), gamma_mw 1.25 shop / 1.50 site, long joints beta_lw (10.5.7.3)."""
    import india_connections as _C
    return _C.fillet_weld_capacity_is800_N(size_mm=size_mm, length_mm=length_mm, fu_MPa=fu_MPa, n_sides=n_sides,
                                          angle_deg=angle_deg, site=site, lj_mm=lj_mm, throat_mm=throat_mm,
                                          gamma_mw=gamma_mw, cite=cite)


def panel_zone_doubler_detail(
    pz_result: Optional[Dict[str, Any]] = None,
    *,
    plate_fy_MPa=None,
    plate_fu_MPa=None,
    plate_grade=None,
    electrode=None,
    electrode_cite=None,
    plate_cite=None,
):
    """Attach plate grade / electrode provenance to a panel_zone_check result.

    Thickness (doubler_required_mm) comes from panel_zone_check. Grade/electrode
    must come from IS 2062 (grade) and IS 814 (electrode) - never invented
    or electrode classification.
    """
    pz = dict(pz_result or {})
    t_req = pz.get("doubler_required_mm")
    detail = {
        "doubler_required_mm": t_req,
        "plate_fy_MPa": plate_fy_MPa,
        "plate_fu_MPa": plate_fu_MPa,
        "plate_grade": plate_grade,
        "electrode": electrode,
        "plate_cite": plate_cite,
        "electrode_cite": electrode_cite,
    }
    missing = []
    if t_req is None and not pz.get("found"):
        missing.append("panel_zone_check result with doubler_required_mm")
    if plate_fy_MPa is None and not plate_grade:
        missing.append("plate_fy_MPa or plate_grade (IS 2062)")
    if not electrode:
        missing.append("electrode (IS 814 / IS 816 class) from RAG — do not invent")
    if missing:
        detail.update({
            "found": False,
            "required_inputs": missing,
            "cite": "IS 800:2007 §12.11.2.3–12.11.2.4 doubler; grade/electrode from RAG",
            "note": (
                "Doubler thickness may be flagged by panel_zone_check; plate grade and "
                "electrode remain found:false until declared. E250B (12.8.2.1/12.11.1) is a design "
                "requirement checked by india_is800_s12.material_gate."
            ),
        })
        pz["doubler_detail"] = detail
        return pz

    detail.update({
        "found": True,
        "cite": plate_cite or "IS 2062 plate grade (RAG) + IS 814/816 electrode (RAG)",
        "electrode_cite": electrode_cite or "IS 814 / IS 816 electrode (RAG)",
        "note": (
            "Doubler t≈%.1f mm from panel_zone_check; plate grade/electrode from RAG — "
            "confirm mill cert (H7) before seal." % (float(t_req or 0),)
        ),
    })
    pz["doubler_detail"] = detail
    # Thickness path may still fail shear until doubler is provided in the model
    return pz


# End-plate / continuity capacity (D3 ruling: no "eor_documented" bypass). A capacity is accepted only when it is
# derived from geometry + an IS 800 clause (source rag/corpus/is800/computed) and carries a cite.
END_PLATE_RN_OK_SOURCES = frozenset({"rag", "corpus", "qfm", "live_rag", "is800", "is_800", "computed"})
END_PLATE_RN_REFUSED_SOURCES = frozenset({
    "assumed", "assumption", "silent", "silent_default", "invented", "placeholder", "todo", "tbd", "guess",
    "thin_air", "eor_documented", "eor", "documented", "explicit", "eor_explicit",
})


def _norm_src(s):
    return (str(s or "").strip().lower().replace(" ", "_").replace("-", "_"))


def end_plate_or_continuity_capacity_N(
    *,
    capacity_N=None,
    Rn=None,
    cite=None,
    source=None,
    limit_state=None,
    cfg=None,
    demand_N=None,
):
    """End-plate / continuity capacity. Accepted only with an IS 800-derived source (rag/corpus/is800/computed);
    'eor_documented' / assumed sources are refused (D3: no foreign or undocumented design basis). found:false
    otherwise - never invented. Section 12 demands (1.2 Mp) come from india_is800_s12."""
    cfg = cfg if isinstance(cfg, dict) else {}
    ep = cfg.get("end_plate") if isinstance(cfg.get("end_plate"), dict) else {}
    cont = cfg.get("continuity") if isinstance(cfg.get("continuity"), dict) else {}
    cite = (cite or cfg.get("end_plate_Rn_cite") or cfg.get("end_plate_cite")
            or ep.get("cite") or ep.get("Rn_cite") or cont.get("cite"))
    src = _norm_src(source or cfg.get("end_plate_Rn_source") or cfg.get("end_plate_source")
                    or ep.get("source") or ep.get("Rn_source") or cont.get("source"))
    cap = capacity_N if capacity_N is not None else Rn
    if cap is None:
        cap = (cfg.get("end_plate_capacity_N") or cfg.get("end_plate_Rn") or ep.get("capacity_N") or ep.get("Rn")
               or cont.get("capacity_N") or cont.get("Rn"))
    dem = demand_N if demand_N is not None else ep.get("demand_N")
    default_cite = "IS 800:2007 §10 / §12.11 end-plate / continuity"
    if cap is not None and float(cap) > 0 and (not src or src in END_PLATE_RN_OK_SOURCES) and \
            src not in END_PLATE_RN_REFUSED_SOURCES:
        out = {"found": True, "capacity_N": float(cap), "Rn": float(cap), "limit_state": limit_state,
               "source": src or "rag", "resolved_via": "rag", "cite": cite or default_cite,
               "note": "Capacity from IS 800 geometry + clause (supplied) - not invented."}
        if dem is not None:
            out["DC"] = float(dem) / float(cap)
            out["demand_N"] = float(dem)
        return out
    reasons = []
    if cap is None or float(cap) <= 0:
        reasons.append("capacity_N derived from geometry + IS 800 clause (source rag/is800/computed)")
    if src in END_PLATE_RN_REFUSED_SOURCES:
        reasons.append("source %r refused (D3: no eor_documented / assumed capacities)" % src)
    return {"found": False, "capacity_N": None, "Rn": None, "source": src or None, "resolved_via": "found_false",
            "cite": cite or default_cite, "required_inputs": reasons,
            "note": "End-plate/continuity capacity found:false - derive from geometry + IS 800 clause; never invent.",
            "demand_N": float(dem) if dem is not None else None, "DC": None}


# --- complete-gap wave3: base-plate bending, Whitmore/block shear, Pn, PZ-in-model ---

def base_plate_bending_check(
    *,
    P_N=None,
    M_Nmm=None,
    plate_B_mm=None,
    plate_L_mm=None,
    plate_t_mm=None,
    fy_plate_MPa=None,
    cantilever_m_mm=None,
    bearing_pressure_MPa=None,
    capacity_bending_N=None,
    capacity_bending_Nmm=None,
    gamma_m0=None,
    cited=None,
    a_mm=None,
    b_mm=None,
    tf_col_mm=None,
):
    """IS 800:2007 7.4.3.1 slab-base thickness (concentric axial compression):
    ts = sqrt(2.5 w (a^2 - 0.3 b^2) gamma_m0 / fy) > tf. With only one projection m: b = 0 (a = m).
    DC = (t_req / t_prov)^2 (strength ratio, HR800-12). For P + M use india_connections.base_plate_design.
    found:false when geometry is not declared - thickness is never invented or sized from demand.
    """
    gm0 = float(gamma_m0 if gamma_m0 is not None else GAMMA_M0_DEFAULT)
    cite = cited or "IS 800:2007 7.4.3.1 ts = sqrt(2.5 w (a^2-0.3b^2) gamma_m0/fy) > tf"
    missing = []
    if capacity_bending_N is not None and P_N is not None and float(capacity_bending_N) > 0:
        dc = float(P_N) / float(capacity_bending_N)
        return {"found": True, "DC": dc, "capacity_N": float(capacity_bending_N),
                "capacity": {"capacity_N": float(capacity_bending_N), "path": "supplied_capacity_N"},
                "cite": cite, "cited": cite, "note": "Base-plate D/C from a supplied capacity - t not invented."}
    if capacity_bending_Nmm is not None and M_Nmm is not None and float(capacity_bending_Nmm) > 0:
        dc = float(M_Nmm) / float(capacity_bending_Nmm)
        return {"found": True, "DC": dc, "capacity_Nmm": float(capacity_bending_Nmm),
                "capacity": {"capacity_Nmm": float(capacity_bending_Nmm), "path": "supplied_capacity_Nmm"},
                "cite": cite, "cited": cite, "note": "Base-plate moment D/C from a supplied capacity."}
    if M_Nmm:
        return {"found": False, "DC": None, "capacity": {}, "cite": cite,
                "required_inputs": ["P+M base: use india_connections.base_plate_design (7.4.1 linear bearing)"],
                "missing": ["moment present - 7.4.3.1 applies to axial compression only (7.4.3.2)"],
                "note": "7.4.3.1 is for concentric compression; eccentric bases need 7.4.3.2 special calculation."}
    a = a_mm if a_mm is not None else cantilever_m_mm
    b = b_mm if b_mm is not None else (0.0 if cantilever_m_mm is not None else None)
    fy = fy_plate_MPa
    t_prov = plate_t_mm
    w = bearing_pressure_MPa
    if w is None and P_N is not None and plate_B_mm and plate_L_mm:
        area = float(plate_B_mm) * float(plate_L_mm)
        if area > 0:
            w = float(P_N) / area
    if a is None:
        missing.append("projections a_mm/b_mm (or cantilever_m_mm) - declared geometry")
    if fy is None:
        missing.append("fy_plate_MPa (IS 2062 Table 3 for the plate thickness)")
    if t_prov is None:
        missing.append("plate_t_mm declared (do not invent t)")
    if w is None:
        missing.append("bearing_pressure_MPa or P_N with plate_B_mm x plate_L_mm")
    if missing:
        return {"found": False, "DC": None, "capacity": {}, "t_required_mm": None,
                "t_provided_mm": float(t_prov) if t_prov is not None else None,
                "required_inputs": missing, "missing": missing, "cite": cite,
                "note": "Base-plate thickness found:false - declared geometry required; never invent thickness."}
    a = float(a); b = float(b or 0.0); fy = float(fy); t_prov = float(t_prov); w = float(w)
    t_req = math.sqrt(max(2.5 * w * (a * a - 0.3 * b * b) * gm0 / fy, 0.0))
    dc = (t_req / t_prov) ** 2 if t_prov > 0 else None
    ts_gt_tf = None if tf_col_mm is None else (t_prov > float(tf_col_mm))
    return {
        "found": True, "DC": dc, "t_required_mm": t_req, "t_provided_mm": t_prov, "a_mm": a, "b_mm": b,
        "m_mm": a, "w_MPa": w, "fy_plate_MPa": fy, "gamma_m0": gm0, "ts_gt_tf": ts_gt_tf,
        "capacity": {"t_required_mm": t_req, "t_provided_mm": t_prov, "path": "IS800_7.4.3.1"},
        "capacity_N": None, "cite": cite, "cited": cite,
        "note": "DC = (t_req/t_prov)^2 per 7.4.3.1; ts > tf also required.",
        "pass": (dc is not None and dc <= 1.0 and ts_gt_tf is not False),
    }


def gusset_whitmore_capacity_N(
    *,
    whitmore_width_mm=None,
    t_gusset_mm=None,
    fy_MPa=None,
    L_wt_mm=None,
    w_brace_mm=None,
    gamma_m0=None,
    capacity_N=None,
    cite=None,
):
    """Gusset Whitmore-section yield. The 30-degree Whitmore width is ENGINEERING PRACTICE (not an IS 800 clause);
    yield per IS 800 6.2 (fy/gamma_m0). Compression buckling: india_connections.whitmore_buckling (12.7.3.4/12.8.3.4)."""
    import india_connections as _C
    if capacity_N is not None and float(capacity_N) > 0:
        return {"found": True, "capacity_N": float(capacity_N), "cite": cite or _C.WHITMORE_CITE,
                "path": "supplied_capacity_N"}
    r = _C.whitmore_section(t_gusset_mm=t_gusset_mm, fy_MPa=fy_MPa, w_start_mm=w_brace_mm, L_conn_mm=L_wt_mm,
                            whitmore_width_mm=whitmore_width_mm)
    if r.get("found"):
        r.update(t_gusset_mm=float(t_gusset_mm), fy_MPa=float(fy_MPa), path="whitmore_yield",
                 gamma_m0=float(gamma_m0 or GAMMA_M0_DEFAULT))
    return r


def gusset_block_shear_capacity_N(
    *,
    capacity_N=None,
    Avg_mm2=None,
    Atn_mm2=None,
    fy_MPa=None,
    fu_MPa=None,
    gamma_m0=None,
    gamma_m1=None,
    cite=None,
    Avn_mm2=None,
    Atg_mm2=None,
):
    """Gusset block shear - IS 800 6.4.1: the SMALLER of both expressions (HR800-11). All four areas (Avg, Avn,
    Atg, Atn) are required; with any missing the result is found:false (the first expression alone is +9.5 %
    unconservative on a typical gusset)."""
    if capacity_N is not None and float(capacity_N) > 0:
        return {"found": True, "capacity_N": float(capacity_N), "cite": cite or "IS 800:2007 6.4.1",
                "path": "supplied_capacity_N"}
    r = block_shear_6_4_1(Avg_mm2=Avg_mm2, Avn_mm2=Avn_mm2, Atg_mm2=Atg_mm2, Atn_mm2=Atn_mm2, fy_MPa=fy_MPa,
                          fu_MPa=fu_MPa, gamma_m0=float(gamma_m0 or GAMMA_M0_DEFAULT),
                          gamma_m1=float(gamma_m1 or 1.25))
    r["path"] = "section_6_4_1_both_expressions"
    if r.get("found"):
        r.update(fy_MPa=float(fy_MPa), fu_MPa=float(fu_MPa))
    return r


def column_base_or_splice_Pn_capacity_N(
    *,
    capacity_N=None,
    cite=None,
    limit_state=None,
    demand_P_N=None,
    cfg=None,
    geometry=None,
    plate_B_mm=None,
    plate_L_mm=None,
    plate_t_mm=None,
    bearing_stress_MPa=None,
    fck_MPa=None,
    bearing_factor=None,
    capacity_bearing_N=None,
    anchor_n=None,
    anchor_dia_mm=None,
    anchor_grade=None,
    capacity_one_anchor_N=None,
    capacity_anchor_N=None,
):
    """Column base / splice axial Pn — RAG capacity or cfg geometry + RAG formulas.

    Never reuse beam bolt-group shear on P_N. Paths:
      1) capacity_N from LIVE RAG (direct)
      2) cfg/disclosed plate plan + RAG bearing stress/factor → bearing Pn
      3) cfg/disclosed anchors + RAG per-anchor → anchor Pn
      Governing = min of available component capacities when both present.
    found:false if neither RAG capacity nor (geometry + RAG formula). Optional
    demand_P_N yields DC when capacity present.
    """
    cite = cite or "IS 800:2007 §7.4 / §10 column base or splice axial"
    geo_res = resolve_base_or_splice_geometry(cfg, geometry=geometry)
    geo = geo_res.get("geometry") or {}
    if plate_B_mm is None:
        plate_B_mm = geo.get("plate_B_mm")
    if plate_L_mm is None:
        plate_L_mm = geo.get("plate_L_mm")
    if plate_t_mm is None:
        plate_t_mm = geo.get("plate_t_mm")
    if fck_MPa is None:
        fck_MPa = geo.get("fck_MPa")
    if anchor_n is None:
        anchor_n = geo.get("anchor_n")
    if anchor_dia_mm is None:
        anchor_dia_mm = geo.get("anchor_dia_mm")
    if anchor_grade is None:
        anchor_grade = geo.get("anchor_grade")

    components = {}
    if capacity_N is not None and float(capacity_N) > 0:
        components["rag_direct"] = {
            "found": True, "capacity_N": float(capacity_N), "cite": cite, "path": "rag_capacity_N",
        }

    br = base_plate_bearing_capacity_N(
        plate_B_mm=plate_B_mm, plate_L_mm=plate_L_mm,
        bearing_stress_MPa=bearing_stress_MPa, fck_MPa=fck_MPa,
        bearing_factor=bearing_factor, capacity_N=capacity_bearing_N, cite=cite,
    )
    if br.get("found"):
        components["bearing"] = br

    an = anchor_group_capacity_N(
        n_anchors=anchor_n, capacity_one_N=capacity_one_anchor_N,
        dia_mm=anchor_dia_mm, grade=anchor_grade,
        capacity_N=capacity_anchor_N, cite=cite,
    )
    if an.get("found"):
        components["anchors"] = an

    if not components:
        missing = [
            "capacity_N from LIVE RAG base-plate/anchor/splice "
            "(do not apply beam bolt shear to P_N)",
            "OR cfg plate_B/L + RAG bearing_stress/factor",
            "OR cfg anchor_n + RAG capacity_one_anchor_N",
        ]
        return {
            "found": False,
            "capacity_N": None,
            "DC": None,
            "demand_P_N": float(demand_P_N) if demand_P_N is not None else None,
            "required_inputs": missing,
            "geometry": {
                "plate_B_mm": plate_B_mm, "plate_L_mm": plate_L_mm,
                "plate_t_mm": plate_t_mm, "anchor_n": anchor_n,
                "anchor_dia_mm": anchor_dia_mm, "cfg_geometry_found": bool(geo_res.get("found")),
            },
            "bearing_detail": br,
            "anchor_detail": an,
            "cite": cite,
            "note": (
                "Column splice/base Pn found:false — need RAG axial capacity or "
                "cfg-disclosed plate/anchor geometry + RAG capacity formulas; "
                "beam bolt group must not be applied to P_N."
            ),
        }

    # Governing = min of available component capacities
    caps = [(k, float(v["capacity_N"])) for k, v in components.items() if v.get("capacity_N")]
    gov_key, gov_cap = min(caps, key=lambda x: x[1])
    dc = None
    if demand_P_N is not None and gov_cap > 0:
        dc = float(demand_P_N) / gov_cap
    return {
        "found": True,
        "capacity_N": gov_cap,
        "DC": dc,
        "demand_P_N": float(demand_P_N) if demand_P_N is not None else None,
        "governing": gov_key,
        "components": {k: {"capacity_N": v.get("capacity_N"), "path": v.get("path"), "cite": v.get("cite")}
                       for k, v in components.items()},
        "geometry": {
            "plate_B_mm": plate_B_mm, "plate_L_mm": plate_L_mm,
            "plate_t_mm": plate_t_mm, "anchor_n": anchor_n,
            "anchor_dia_mm": anchor_dia_mm, "cfg_geometry_found": bool(geo_res.get("found")),
        },
        "limit_state": limit_state or "column axial Pn (base/splice)",
        "cite": cite,
        "note": (
            "Axial Pn from RAG and/or cfg geometry + RAG formulas — not invented; "
            "not from beam bolt shear. Governing=%s." % gov_key
        ),
    }


def panel_zone_apply_doubler_in_model(
    pz_result=None,
    *,
    doubler_t_mm_in_model=None,
    cfg=None,
):
    """Re-evaluate panel zone when doubler thickness is present in the model/cfg.

    If doubler_t_mm_in_model (or cfg['panel_zone_doubler_t_mm']) is provided and the
    prior panel_zone_check inputs are retained on pz_result['inputs'], re-run with
    doubler_t_mm. Otherwise document FAIL / found detail until plate is in cfg —
    do not invent doubler thickness.
    """
    pz = dict(pz_result or {})
    cfg = cfg or {}
    t_model = doubler_t_mm_in_model
    if t_model is None:
        t_model = cfg.get("panel_zone_doubler_t_mm") or cfg.get("doubler_t_mm")
    detail = {
        "doubler_t_mm_in_model": float(t_model) if t_model is not None else None,
        "cite": "IS 800:2007 §12.11.2.3–12.11.2.4 doubler in model/cfg",
    }
    if t_model is None:
        detail.update({
            "found": False,
            "required_inputs": ["doubler_t_mm_in_model or cfg['panel_zone_doubler_t_mm']"],
            "note": (
                "Panel-zone shear remains FAIL / pending until doubler plate thickness is "
                "placed in the model or cfg — sizing from panel_zone_check is advisory only; "
                "do not invent plate in model."
            ),
            "panel_zone_pass": pz.get("pass"),
            "doubler_required_mm": pz.get("doubler_required_mm"),
        })
        pz["doubler_in_model"] = detail
        return pz

    inputs = dict(pz.get("inputs") or {})
    need = ("d_col_mm", "tw_mm", "bf_mm", "tf_mm", "d_beam_mm", "V_design_N", "fy_MPa")
    if not all(inputs.get(k) is not None for k in need):
        # Cannot re-run without stored inputs — attach provisionally
        detail.update({
            "found": True,
            "doubler_provided_mm": float(t_model),
            "recomputed": False,
            "required_inputs": ["pz_result['inputs'] with panel_zone_check kwargs to re-run"],
            "note": (
                "Doubler t=%.1f mm disclosed in model/cfg; re-run panel_zone_check with "
                "doubler_t_mm to confirm shear/thickness pass." % float(t_model)
            ),
        })
        pz["doubler_in_model"] = detail
        pz["doubler_provided_mm"] = float(t_model)
        return pz

    recomputed = panel_zone_check(
        d_col_mm=inputs["d_col_mm"],
        tw_mm=inputs["tw_mm"],
        bf_mm=inputs["bf_mm"],
        tf_mm=inputs["tf_mm"],
        d_beam_mm=inputs["d_beam_mm"],
        V_design_N=inputs["V_design_N"],
        fy_MPa=inputs["fy_MPa"],
        doubler_t_mm=float(t_model),
        gamma_m0=inputs.get("gamma_m0", GAMMA_M0_DEFAULT),
    )
    detail.update({
        "found": True,
        "recomputed": True,
        "doubler_provided_mm": float(t_model),
        "panel_zone_pass": recomputed.get("pass"),
        "DC_shear": recomputed.get("DC_shear"),
        "note": (
            "Panel zone re-checked with doubler t=%.1f mm in model/cfg." % float(t_model)
        ),
    })
    recomputed["doubler_in_model"] = detail
    if pz.get("doubler_detail"):
        recomputed["doubler_detail"] = pz["doubler_detail"]
    return recomputed


def scwb_multi_joint(
    joints=None,
    *,
    fy_MPa=None,
    representative_only=False,
):
    """Multi-joint SCWB from an explicit joint list. Each joint: {columns: [...], beams: [...], id?}.

    WP2.4: a 'representative joint' is NOT acceptable - every SMF joint from the model connectivity must be
    checked (india_is800_s12.joints_from_model + scwb_joint, with axial-reduced Mpc). Empty -> found:false.
    """
    cite = "IS 800:2007 §12.11.3.2 ΣMpc/ΣMpb ≥ 1.2"
    if not joints:
        return {
            "found": False,
            "scope": "representative_joint_optional_multi",
            "joints": [],
            "cite": cite,
            "required_inputs": ["joints=[{columns, beams, id?}, ...]"],
            "note": ("SCWB must be evaluated at every SMF joint from model connectivity "
                     "(india_is800_s12.joints_from_model / scwb_joint) - no representative joint."),
        }
    results = []
    for i, j in enumerate(joints):
        j = j or {}
        r = scwb_ratio(
            columns=j.get("columns") or j.get("column_props"),
            beams=j.get("beams") or j.get("beam_props"),
            fy_MPa=j.get("fy_MPa", fy_MPa),
        )
        r = dict(r)
        r["joint_id"] = j.get("id") or j.get("joint_id") or "joint_%d" % i
        results.append(r)
    any_found = any(r.get("found") for r in results)
    worst = None
    for r in results:
        if r.get("found") and r.get("ratio") is not None:
            if worst is None or r["ratio"] < worst:
                worst = r["ratio"]
    return {
        "found": any_found,
        "scope": "representative_only" if (representative_only or len(results) == 1) else "multi_joint",
        "n_joints": len(results),
        "worst_ratio": worst,
        "pass": (worst is not None and worst >= 1.2) if any_found else None,
        "joints": results,
        "cite": cite,
        "note": ("SCWB from the provided joint list; worst sum(Mpc)/sum(Mpb) reported. A single joint does not "
                 "demonstrate 12.11.3.2 - use india_is800_s12 for every joint."),
    }



# --- HR polish Wave D: Whitmore / block shear status object -------------------

def gusset_whitmore_block_shear_status(
    *,
    whitmore=None,
    block_shear=None,
    rag_hit=None,
    disclosed=None,
):
    """Consistent status object for gusset Whitmore + block shear (Wave D).

    Prefer RAG numeric capacity or disclosed geometry helpers. Emit found:false
    when corpus misses — never invent Whitmore width / block-shear areas.
    ``disclosed`` carries declared geometry (bw/t/fy or Avg/Avn/Atg/Atn).
    """
    disclosed = disclosed or {}
    rag_hit = rag_hit or {}

    # Whitmore
    if whitmore is None:
        w_kwargs = {}
        if rag_hit.get("whitmore_capacity_N") is not None:
            w_kwargs["capacity_N"] = rag_hit["whitmore_capacity_N"]
            w_kwargs["cite"] = rag_hit.get("whitmore_cite") or rag_hit.get("cite")
        else:
            for k in ("whitmore_width_mm", "t_gusset_mm", "fy_MPa", "L_wt_mm", "w_brace_mm",
                      "gamma_m0", "capacity_N", "cite"):
                if disclosed.get(k) is not None:
                    w_kwargs[k] = disclosed[k]
                elif rag_hit.get(k) is not None:
                    w_kwargs[k] = rag_hit[k]
        whitmore = gusset_whitmore_capacity_N(**w_kwargs) if w_kwargs else gusset_whitmore_capacity_N()

    # Block shear
    if block_shear is None:
        b_kwargs = {}
        if rag_hit.get("block_shear_capacity_N") is not None:
            b_kwargs["capacity_N"] = rag_hit["block_shear_capacity_N"]
            b_kwargs["cite"] = rag_hit.get("block_shear_cite") or rag_hit.get("cite")
        else:
            for k in ("Avg_mm2", "Avn_mm2", "Atg_mm2", "Atn_mm2", "fy_MPa", "fu_MPa", "gamma_m0", "gamma_m1",
                      "capacity_N", "cite"):
                if disclosed.get(k) is not None:
                    b_kwargs[k] = disclosed[k]
                elif rag_hit.get(k) is not None:
                    b_kwargs[k] = rag_hit[k]
        block_shear = (
            gusset_block_shear_capacity_N(**b_kwargs) if b_kwargs
            else gusset_block_shear_capacity_N()
        )

    w_found = bool(whitmore.get("found"))
    b_found = bool(block_shear.get("found"))
    return {
        "component": "gusset_whitmore_block_shear",
        "found": w_found and b_found,
        "whitmore": whitmore,
        "block_shear": block_shear,
        "status": (
            "ok" if (w_found and b_found) else
            "partial" if (w_found or b_found) else
            "found_false"
        ),
        # HR800-11: 12.7.3.2 / 12.8.3.2 make block shear mandatory for brace connections - a missing check blocks
        "blocks_complete": not (w_found and b_found),
        "note": (
            "Whitmore (engineering practice) + block shear (IS 800 6.4.1, both expressions) evaluated."
            if (w_found and b_found) else
            "Whitmore/block shear found:false - IS 800 12.7.3.2/12.8.3.2 require block shear for brace "
            "connections: this BLOCKS COMPLETE until the gusset geometry is declared."
        ),
        "policy": "rag_or_disclosed_else_found_false",
    }



def composite_is11384_worksheet_stubs(cfg=None):
    """WP2.9: composite floor worksheet. Composite beams are IS 11384 (not in the corpus) -> found:false slots.
    Scope 'bare_steel' replaces them with IS 800 8.2 bare-steel + construction-stage checks (see COMPOSITE_INDIA.md)."""
    cfg = cfg or {}
    scope = str(cfg.get("composite_scope") or "").lower()

    def _slot(component, note, cite):
        return {"component": component, "found": False, "DC": None, "capacity": {}, "cited": None,
                "cite": cite, "note": note}
    slots = [
        _slot("is11384_composite_strength", "IS 11384 composite flexure - not in corpus (found:false)", "IS 11384"),
        _slot("is11384_shear_connectors", "IS 11384 shear connectors - not in corpus (found:false)", "IS 11384"),
        _slot("bare_steel_8_2", "bare-steel IS 800 8.2.1.2 / 8.2.2 check of each floor beam",
              "IS 800:2007 8.2"),
        _slot("construction_stage", "unshored wet-concrete stage: 8.2.2 with pre-hardening restraint + camber",
              "IS 800:2007 8.2.2"),
    ]
    return {"status": "stubs", "scope": scope or None,
            "cite": "IS 11384 (not in corpus); IS 800:2007 8.2 bare-steel scope - COMPOSITE_INDIA.md",
            "policy": "found:false until bare_steel (IS 800 8.2 + construction stage) or delegated scope is recorded",
            "blocks_complete": scope not in ("bare_steel", "bare-steel", "delegated"),
            "slots": slots}


def h6_h7_residual_status(cfg=None, pkg=None):
    """H6 / H7 status (WP2.9, HR800-13/14).

    H6 composite floors: composite steel-concrete beams are IS 11384 (not in the corpus) -> found:false. IS 800:2007
    has no composite chapter. Allowed scopes: bare-steel design (IS 800 8.2 incl. construction stage) or delegation.
    H7 E250B: IS 800 12.8.2.1 (SCBF braces) / 12.11.1 (SMF) make IS 2062 E250B a DESIGN requirement (checked by
    india_is800_s12.material_gate) - blocking, not a procurement note.
    """
    cfg = cfg or {}
    pkg = pkg or {}
    composite_declared = bool(cfg.get("composite") or cfg.get("composite_floor")
                              or isinstance(pkg.get("composite_design"), dict)
                              or "composite" in str(cfg.get("floor_system", "")).lower())
    scope = str(cfg.get("composite_scope") or "").lower()
    h6 = {
        "id": "H6",
        "title": "Composite floor (IS 11384 - not in corpus)",
        "found": False,
        "status": ("bare_steel_scope" if scope in ("bare_steel", "bare-steel") else
                   "delegated" if scope == "delegated" else "found_false"),
        "blocking": bool(composite_declared and scope not in ("bare_steel", "bare-steel", "delegated")),
        "pe_stamp": None,
        "pe_stamp_invented": False,
        "slots": ["IS 11384 composite design (found:false)", "bare-steel IS 800 8.2 check",
                  "construction-stage (wet concrete) IS 800 8.2.2 check"],
        "note": ("Composite beams: IS 11384 governs and is not in the corpus (found:false). Declare "
                 "cfg['composite_scope'] = 'bare_steel' (IS 800 8.2 incl. construction stage) or 'delegated'."),
        "cite": "IS 11384 (not in corpus); IS 800:2007 8.2 bare-steel scope - see COMPOSITE_INDIA.md",
        "composite_declared": composite_declared,
    }
    h7 = {
        "id": "H7",
        "title": "IS 2062 E250B for SCBF braces (12.8.2.1) and SMF members (12.11.1)",
        "found": False,
        "status": "design_requirement",
        "blocking": True,
        "pe_stamp": None,
        "pe_stamp_invented": False,
        "note": ("E250B is a design requirement checked per member by india_is800_s12.material_gate; IS 1161 "
                 "YSt tubes do not satisfy it."),
        "cite": "IS 800:2007 12.8.2.1 / 12.11.1",
    }
    return {"H6": h6, "H7": h7, "blocking": bool(h6["blocking"] or h7["blocking"]),
            "status": "residuals", "policy": "no_pe_invent; E250B is a design check"}


# =====================================================================================================
# WP2.3  IS 800:2007 member-capacity layer (N, mm, MPa). Review HR800-08/13/19/20, HREX1-X-02, HREX2-X-01.
# Every result is a dict with the inputs, the clause, and found:false (never a silent default) when an
# input is missing. Clause values were read from the IS 800:2007 PDF (Tables 2, 5, 10, 17, 18, 42; 6.2-6.4;
# 7.1.2; 8.2.1.2; 8.2.2; 8.4; 9.2.2; 9.3; Annex E) and IS 2062 (Part 1):2025 Table 3.
# =====================================================================================================
GAMMA_M1_DEFAULT = 1.25          # IS 800 Table 5 (ultimate stress)
G_DEFAULT_MPA = 0.769e5          # IS 800 2.2.4.1 modulus of rigidity
POISSON = 0.3                    # IS 800 2.2.4.1

# IS 2062 (Part 1):2025 Table 3 "Mechanical Properties": Rm min (MPa) and ReH min (MPa) for thickness bands
# <=16, >16-40, >40-100, >100 mm (pdf pp.8-9; qualities A/BR/B0/C).
IS2062_TABLE3 = {
    "E235": (360.0, (235.0, 225.0, 215.0, 195.0)),
    "E250": (410.0, (250.0, 240.0, 230.0, 210.0)),
    "E275": (430.0, (275.0, 265.0, 255.0, 225.0)),
    "E300": (440.0, (300.0, 290.0, 280.0, 250.0)),
    "E350": (490.0, (350.0, 330.0, 320.0, 290.0)),
    "E410": (540.0, (410.0, 390.0, 380.0, 350.0)),
    "E450": (570.0, (450.0, 430.0, 420.0, 390.0)),
    "E500": (580.0, (500.0, 480.0, 470.0, 450.0)),
    "E550": (650.0, (550.0, 530.0, 520.0, None)),
    "E600": (700.0, (600.0, 580.0, 570.0, None)),
    "E650": (750.0, (650.0, 630.0, 620.0, None)),
}
IS2062_CITE = "IS 2062 (Part 1):2025 Table 3 (ReH min by thickness band; Rm min)"
IS2062_QUALITIES = ("A", "BR", "B0", "C", "B")


def parse_is2062_grade(grade):
    """'E250', 'E 250 BR', 'IS 2062 E250B0', 'E250B' -> ('E250', 'BR'|'B0'|'C'|'A'|'B'|None)."""
    import re as _re
    if not grade:
        return None, None
    s = str(grade).upper().replace("IS2062", "").replace("IS 2062", "").replace(" ", "").replace("-", "")
    m = _re.search(r"E(\d{3})(BR|B0|BO|C|A|B)?", s)
    if not m:
        return None, None
    q = m.group(2)
    if q == "BO":
        q = "B0"
    return "E" + m.group(1), q


def is2062_properties(grade, t_mm):
    """fy (ReH) and fu (Rm) from IS 2062:2025 Table 3 for the element thickness t (mm)."""
    key, quality = parse_is2062_grade(grade)
    if key not in IS2062_TABLE3 or t_mm is None or float(t_mm) <= 0:
        return {"found": False, "fy_MPa": None, "fu_MPa": None, "grade": grade, "t_mm": t_mm,
                "cite": IS2062_CITE,
                "required_inputs": ["IS 2062 grade E235..E650", "governing thickness t_mm"]}
    fu, bands = IS2062_TABLE3[key]
    t = float(t_mm)
    idx = 0 if t <= 16 else 1 if t <= 40 else 2 if t <= 100 else 3
    fy = bands[idx]
    if fy is None:
        return {"found": False, "fy_MPa": None, "fu_MPa": fu, "grade": key, "t_mm": t, "cite": IS2062_CITE,
                "note": "Table 3 gives no ReH for this grade above 100 mm (mutual agreement, Note 4)"}
    band = ("<=16", ">16-40", ">40-100", ">100")[idx]
    return {"found": True, "fy_MPa": fy, "fu_MPa": fu, "grade": key, "quality": quality, "t_mm": t,
            "thickness_band_mm": band, "cite": IS2062_CITE}


def fy_is2062(grade, t_mm):
    """IS 2062:2025 Table 3 yield stress for grade and thickness (MPa). Raises when unknown (no default 250)."""
    r = is2062_properties(grade, t_mm)
    if not r["found"]:
        raise ValueError("fy_is2062: %s" % (r.get("note") or r.get("required_inputs")))
    return r["fy_MPa"]


def _props(sec):
    if isinstance(sec, dict):
        return sec
    import sections as _S
    return _S.props(sec)


def governing_thickness_mm(p):
    """IS 2062 thickness for fy: max(tf, tw) for rolled I/channel (review HR800-13); t for angles/CHS."""
    vals = [v for v in (p.get("tf"), p.get("tw")) if v]
    return max(vals) if vals else None


def material_for_section(sec, grade=None, *, process=None):
    """fy/fu for a section: IS 1161 grade for CHS, IS 2062 Table 3 with max(tf, tw) otherwise."""
    p = _props(sec)
    if p.get("section_type") == "CHS":
        import sections as _S
        m = _S.chs_material(grade, process)
        m["found"] = bool(m.get("material_found"))
        m["cite"] = m.get("material_cite")
        return m
    r = is2062_properties(grade, governing_thickness_mm(p))
    r["t_governing"] = "max(tf, tw)"
    return r


# ---------------------------------------------------------------- Table 2 classification
_T2 = "IS 800:2007 Table 2 (Limiting width to thickness ratio), eps = (250/fy)^0.5"


def _cls(ratio, limits):
    p, c, s = limits
    if p is not None and ratio <= p:
        return "plastic"
    if c is not None and ratio <= c:
        return "compact"
    if s is not None and ratio <= s:
        return "semi-compact"
    return "slender"


_ORDER = {"plastic": 1, "compact": 2, "semi-compact": 3, "slender": 4}


def section_class_table2(sec, fy_MPa, *, P_N=0.0, welded=False, gamma_m0=GAMMA_M0_DEFAULT, loading="bending"):
    """IS 800 Table 2 classification (flange + web) of an IS 808 / IS 1161 section.

    P_N > 0 = axial compression (uses the 'generally' web rows with r1, r2 of Note 5); P_N < 0 tension.
    loading='axial' classifies angles/CHS for pure axial compression.
    Web d = D - 2(tf + R1) for rolled I (clear of root fillets, Fig. 2); D - 2tf for welded.
    Note: the printed web limits read 'but <= 42 eps'; applied as a floor of 42 eps (consistent with the
    'axial compression 42 eps' row).
    """
    if not fy_MPa or fy_MPa <= 0:
        return {"found": False, "section_class": None, "cite": _T2, "required_inputs": ["fy_MPa"]}
    p = _props(sec)
    eps = math.sqrt(250.0 / float(fy_MPa))
    st = p.get("section_type")
    el = []
    if st == "CHS":
        Dt = p["d"] / p["tw"]
        if loading == "axial":
            el.append(dict(element="CHS wall, axial compression", ratio=Dt,
                           limits=(None, None, 88 * eps ** 2)))
        else:
            el.append(dict(element="CHS wall, moment", ratio=Dt, limits=(42 * eps ** 2, 52 * eps ** 2, 146 * eps ** 2)))
    elif st == "angle":
        b, d, t = p["bf"], p["d"], p["tw"]
        if loading == "axial":
            el += [dict(element="angle leg b/t (axial)", ratio=b / t, limits=(None, None, 15.7 * eps)),
                   dict(element="angle leg d/t (axial)", ratio=d / t, limits=(None, None, 15.7 * eps)),
                   dict(element="angle (b+d)/t (axial)", ratio=(b + d) / t, limits=(None, None, 25 * eps))]
        else:
            el += [dict(element="angle b/t (bending)", ratio=b / t, limits=(9.4 * eps, 10.5 * eps, 15.7 * eps)),
                   dict(element="angle d/t (bending)", ratio=d / t, limits=(9.4 * eps, 10.5 * eps, 15.7 * eps))]
    else:
        D, B, tw, tf = p["d"], p["bf"], p["tw"], p["tf"]
        R1 = p.get("R1") or 0.0
        b_out = B / 2.0 if st == "I" else B      # channel: full flange width (Fig. 2)
        fl = (8.4 * eps, 9.4 * eps, 13.6 * eps) if welded else (9.4 * eps, 10.5 * eps, 15.7 * eps)
        el.append(dict(element="flange outstand b/tf (%s)" % ("welded" if welded else "rolled"),
                       ratio=b_out / tf, limits=fl))
        d = D - 2.0 * tf - (0.0 if welded else 2.0 * R1)
        if st == "channel":
            el.append(dict(element="web of a channel d/tw", ratio=d / tw, limits=(42 * eps, 42 * eps, 42 * eps)))
        else:
            P = float(P_N or 0.0)
            if abs(P) < 1e-9:
                el.append(dict(element="web d/tw (neutral axis at mid-depth)", ratio=d / tw,
                               limits=(84 * eps, 105 * eps, 126 * eps)))
            else:
                fcd = float(fy_MPa) / float(gamma_m0)
                r1 = (P / (d * tw)) / fcd
                r2 = (P / p["A"]) / fcd
                lp = max(84 * eps / (1 + r1), 42 * eps)
                lc = max((105 * eps / (1 + r1)) if r1 < 0 else (105 * eps / (1 + 1.5 * r1)), 42 * eps)
                ls = max(126 * eps / (1 + 2 * r2), 42 * eps)
                el.append(dict(element="web d/tw (generally, r1=%.3f, r2=%.3f)" % (r1, r2), ratio=d / tw,
                               limits=(lp, lc, ls), r1=r1, r2=r2))
    for e in el:
        e["class"] = _cls(e["ratio"], e["limits"])
    worst = max(el, key=lambda e: _ORDER[e["class"]])
    return {"found": True, "section_class": worst["class"], "eps": eps, "elements": el,
            "governing_element": worst["element"], "cite": _T2 + "; Note 4 least favourable element governs"}


# ---------------------------------------------------------------- Table 10 buckling class
_T10 = "IS 800:2007 Table 10 (Buckling class of cross-sections)"


def buckling_class(section_type, h=None, b=None, tf=None, axis="z", process=None, *, welded=False, tw=None,
                   thick_welds=False):
    """Full IS 800 Table 10. axis 'z' (major) or 'y' (minor). No silent default: unknown -> found:false."""
    st = (section_type or "").lower()
    ax = "z" if str(axis).lower() in ("z", "zz", "z-z", "major", "x", "xx") else "y"
    out = {"found": False, "buckling_class": None, "cite": _T10, "section_type": section_type, "axis": ax}
    if st in ("chs", "rhs", "shs", "hollow", "tube"):
        pr = (process or "").upper()
        if pr in ("HFS", "HOT", "HOT_ROLLED", "HOT ROLLED", "HOT FINISHED"):
            cls = "a"
        elif pr in ("ERW", "HFIW", "CDS", "COLD", "COLD_FORMED", "COLD FORMED", "HFW"):
            cls = "b"
        else:
            out["required_inputs"] = ["process (HFS -> hot rolled 'a'; ERW/HFIW/CDS -> cold formed 'b')"]
            return out
        out.update(found=True, buckling_class=cls, basis="hollow section, %s" % pr)
        return out
    if st in ("channel", "angle", "tee", "t", "solid", "built-up", "builtup"):
        out.update(found=True, buckling_class="c", basis="channel/angle/T/solid/built-up: any axis c")
        return out
    if st in ("welded_box", "box"):
        cls = "b"
        if thick_welds and ax == "z" and h and tf and h / tf < 30:
            cls = "c"
        if thick_welds and ax == "y" and h and tw and h / tw < 30:
            cls = "c"
        out.update(found=True, buckling_class=cls)
        return out
    if st in ("i", "rolled_i", "h", "i_rolled", "welded_i", "i_welded"):
        if tf is None or (not welded and (h is None or b is None)):
            out["required_inputs"] = ["h", "b", "tf"]
            return out
        tf = float(tf)
        if welded or st in ("welded_i", "i_welded"):
            cls = ("b" if ax == "z" else "c") if tf <= 40 else ("c" if ax == "z" else "d")
            out.update(found=True, buckling_class=cls, basis="welded I, tf %s 40" % ("<=" if tf <= 40 else ">"))
            return out
        hb = float(h) / float(b)
        if hb > 1.2:
            if tf <= 40:
                cls = "a" if ax == "z" else "b"
            elif tf <= 100:
                cls = "b" if ax == "z" else "c"
            else:
                out["note"] = "Table 10 has no rolled-I row for h/b > 1.2 with tf > 100 mm"
                return out
        else:
            cls = ("b" if ax == "z" else "c") if tf <= 100 else "d"
        out.update(found=True, buckling_class=cls, h_over_b=hb, basis="rolled I, h/b %.2f, tf %.1f" % (hb, tf))
        return out
    out["required_inputs"] = ["section_type in {I, welded_I, CHS(+process), channel, angle, tee, box}"]
    return out


def buckling_class_for_section(sec, axis, *, process=None, welded=False):
    p = _props(sec)
    st = p.get("section_type")
    if st == "CHS":
        return buckling_class("CHS", axis=axis, process=process or p.get("process"))
    if st == "angle":
        return buckling_class("angle", axis=axis)
    if st == "channel":
        return buckling_class("channel", axis=axis)
    return buckling_class("welded_I" if welded else "I", h=p["d"], b=p["bf"], tf=p["tf"], axis=axis, welded=welded)


# ---------------------------------------------------------------- 8.2.1.2 / Mp
def plastic_moment_Mp(Zp_mm3, fy_MPa):
    """Full plastic moment Mp = Zp fy (no gamma, no 1.2Ze cap) - for IS 800 Section 12 capacity design only."""
    if not Zp_mm3 or not fy_MPa:
        return {"found": False, "Mp_Nmm": None, "required_inputs": ["Zp_mm3", "fy_MPa"],
                "cite": "IS 800:2007 12.11 / 12.12 'full plastic moment'"}
    return {"found": True, "Mp_Nmm": float(Zp_mm3) * float(fy_MPa), "Zp_mm3": float(Zp_mm3),
            "fy_MPa": float(fy_MPa), "cite": "IS 800:2007 Section 12: Mp = Zp fy (characteristic, uncapped)"}


def design_moment_8_2_1(Zp_mm3, Ze_mm3, fy_MPa, section_class, *, support="simple", gamma_m0=GAMMA_M0_DEFAULT,
                        V_N=None, Vd_N=None, Mfd_Nmm=None):
    """IS 800 8.2.1.2 laterally supported Md = beta_b Zp fy / gamma_m0 <= 1.2 (1.5 cantilever) Ze fy / gamma_m0.

    High shear (V > 0.6 Vd): 9.2.2 Mdv = Md - beta (Md - Mfd) (plastic/compact; needs Mfd) or Ze fy/gamma_m0
    (semi-compact). Slender sections: found:false (effective section per specialist method not coded).
    """
    cite = "IS 800:2007 8.2.1.2 Md = beta_b Zp fy/gamma_m0; cap 1.2 Ze fy/gamma_m0 (1.5 cantilever)"
    if not (Zp_mm3 and Ze_mm3 and fy_MPa and section_class):
        return {"found": False, "Md_Nmm": None, "cite": cite,
                "required_inputs": ["Zp_mm3", "Ze_mm3", "fy_MPa", "section_class"]}
    if section_class == "slender":
        return {"found": False, "Md_Nmm": None, "cite": cite, "section_class": "slender",
                "note": "slender section: Table 2 Note 1; effective section not coded (found:false)"}
    bb = 1.0 if section_class in ("plastic", "compact") else float(Ze_mm3) / float(Zp_mm3)
    Md = bb * float(Zp_mm3) * float(fy_MPa) / gamma_m0
    capf = 1.5 if str(support).lower().startswith("cant") else 1.2
    cap = capf * float(Ze_mm3) * float(fy_MPa) / gamma_m0
    out = {"found": True, "beta_b": bb, "Md_uncapped_Nmm": Md, "cap_Nmm": cap, "cap_factor": capf,
           "Md_Nmm": min(Md, cap), "cap_governs": cap < Md, "section_class": section_class, "cite": cite}
    if V_N is not None and Vd_N:
        if abs(V_N) > 0.6 * Vd_N:
            if section_class == "semi-compact":
                out.update(Md_Nmm=float(Ze_mm3) * float(fy_MPa) / gamma_m0, high_shear=True,
                           cite_high_shear="IS 800:2007 9.2.2(b) Mdv = Ze fy/gamma_m0")
            elif Mfd_Nmm is None:
                out.update(found=False, Md_Nmm=None, high_shear=True,
                           required_inputs=["Mfd_Nmm (flange-only plastic strength) for 9.2.2(a)"])
            else:
                beta = (2.0 * abs(V_N) / Vd_N - 1.0) ** 2
                Mdv = min(out["Md_Nmm"] - beta * (out["Md_Nmm"] - Mfd_Nmm), 1.2 * float(Ze_mm3) * float(fy_MPa) / gamma_m0)
                out.update(Md_Nmm=Mdv, high_shear=True, beta_high_shear=beta,
                           cite_high_shear="IS 800:2007 9.2.2(a) Mdv = Md - beta(Md - Mfd)")
        else:
            out["high_shear"] = False
    return out


def plastic_moment_Nmm(
    Zx_mm3: float,
    fy_MPa: float,
    gamma_m0: float = GAMMA_M0_DEFAULT,
    beta_b: float = 1.0,
) -> Dict[str, Any]:
    """Legacy helper = beta_b Zp fy / gamma_m0 (UNCAPPED). Do not use as Md (use design_moment_8_2_1 /
    ltb_moment_capacity) and do not use as Mp for Section 12 (use plastic_moment_Mp) - HR800-20."""
    if not Zx_mm3 or Zx_mm3 <= 0 or not fy_MPa or fy_MPa <= 0:
        return {"found": False, "Mp_Nmm": None, "cite": "IS 800:2007 8.2.1.2",
                "required_inputs": ["Zx_mm3", "fy_MPa"]}
    Mp = float(beta_b) * float(Zx_mm3) * float(fy_MPa) / float(gamma_m0)
    return {"found": True, "Mp_Nmm": Mp, "Zx_mm3": float(Zx_mm3), "fy_MPa": float(fy_MPa),
            "gamma_m0": float(gamma_m0), "beta_b": float(beta_b),
            "cite": "IS 800:2007 8.2.1.2 beta_b Zp fy/gamma_m0 (uncapped; see design_moment_8_2_1 for the 1.2Ze cap)"}


# ---------------------------------------------------------------- 8.2.2 LTB (Annex E)
TABLE42_END_MOMENT_C1_K1 = [  # IS 800:2007 Table 42, end moments M and psi*M, K = 1.0: (psi, c1, c3)
    (1.0, 1.000, 1.000), (0.75, 1.141, 0.998), (0.5, 1.323, 0.992), (0.25, 1.563, 0.977), (0.0, 1.879, 0.939),
    (-0.25, 2.281, 0.855), (-0.5, 2.704, 0.676), (-0.75, 2.927, 0.366), (-1.0, 2.752, 0.000)]
TABLE42_TRANSVERSE_K1 = {  # IS 800:2007 Table 42 (concluded), K = 1.0: (c1, c2, c3)
    "udl_simply_supported": (1.132, 0.459, 0.525),
    "udl_fixed_ends": (1.285, 1.562, 0.753),
    "point_mid_simply_supported": (1.365, 0.553, 1.780),
    "point_mid_fixed_ends": (1.565, 1.257, 2.640),
    "two_points_quarter_simply_supported": (1.046, 0.430, 1.120),
}


def c1_from_end_moments(psi):
    """IS 800 Table 42 c1 (K = 1.0) for end moments M and psi*M, linear interpolation between tabulated psi."""
    psi = max(-1.0, min(1.0, float(psi)))
    rows = TABLE42_END_MOMENT_C1_K1
    for (p1, c1a, _), (p2, c1b, _) in zip(rows, rows[1:]):
        if p2 <= psi <= p1:
            return c1a + (c1b - c1a) * (psi - p1) / (p2 - p1)
    return 1.0


def elastic_critical_moment(sec, LLT_mm, *, c1=1.0, c2=0.0, yg_mm=0.0, K=1.0, Kw=1.0,
                            E_MPa=E_DEFAULT_MPA, G_MPa=G_DEFAULT_MPA):
    """Mcr per IS 800 Annex E-1.2 (y_j = 0 for doubly symmetric I). c1 = 1.0, yg = 0 reduce to 8.2.2.1."""
    p = _props(sec)
    Iy, It, Iw = p.get("Iy"), p.get("J"), p.get("Cw")
    cite = "IS 800:2007 Annex E-1.2 (Mcr) with Table 42 c1/c2"
    if not (LLT_mm and Iy and It) or Iw is None:
        return {"found": False, "Mcr_Nmm": None, "cite": cite,
                "required_inputs": ["LLT_mm", "Iy", "It", "Iw (IS 808 column; blank => found:false)"]}
    L = float(LLT_mm)
    a = math.pi ** 2 * E_MPa * Iy / L ** 2
    term = (K / Kw) ** 2 * Iw / Iy + G_MPa * It * L ** 2 / (math.pi ** 2 * E_MPa * Iy) + (c2 * yg_mm) ** 2
    Mcr = c1 * a * (math.sqrt(term) - c2 * yg_mm)
    return {"found": True, "Mcr_Nmm": Mcr, "c1": c1, "c2": c2, "yg_mm": yg_mm, "K": K, "Kw": Kw,
            "LLT_mm": L, "cite": cite}


def ltb_moment_capacity(sec, LLT_mm, fy_MPa, *, welded=False, section_class=None, c1=1.0, c2=0.0, yg_mm=0.0,
                        K=1.0, Kw=1.0, support="simple", gamma_m0=GAMMA_M0_DEFAULT, E_MPa=E_DEFAULT_MPA,
                        G_MPa=G_DEFAULT_MPA, axis="z"):
    """IS 800 8.2.2 major-axis design moment of a laterally unsupported beam.

    LLT_mm = physical unbraced length of the COMPRESSION flange for the moment sign considered (deck braces the top
    flange for sagging only; hogging/uplift needs the fly-brace spacing) times the 8.3 effective-length factor.
    alpha_LT = 0.21 rolled / 0.49 welded; lambda_LT = min(sqrt(beta_b Zp fy/Mcr), sqrt(1.2 Ze fy/Mcr));
    lambda_LT <= 0.4 => 8.2.2(c) no LTB check (Md per 8.2.1.2). Minor axis / hollow => 8.2.2(a)/(b).
    """
    cite = "IS 800:2007 8.2.2 (chi_LT, alpha_LT 0.21/0.49, lambda_LT <= sqrt(1.2 Ze fy/Mcr)); Annex E Mcr"
    p = _props(sec)
    if section_class is None:
        sc = section_class_table2(p, fy_MPa, welded=welded)
        section_class = sc.get("section_class")
    Zp = p["Zx"] if axis == "z" else p["Zy"]
    Ze = p["Sx"] if axis == "z" else p["Sy"]
    base = design_moment_8_2_1(Zp, Ze, fy_MPa, section_class, support=support, gamma_m0=gamma_m0)
    st = p.get("section_type")
    if axis != "z" or st == "CHS":
        base.update(ltb="not applicable (8.2.2 a/b: minor-axis bending or hollow section)", lambda_LT=None,
                    chi_LT=1.0, cite=cite)
        return base
    if st in ("angle", "channel"):
        return {"found": False, "Md_Nmm": None, "cite": cite,
                "note": "%s major-axis LTB: Annex E-1.2 covers sections symmetric about the minor axis only; "
                        "not coded (found:false)" % st}
    if not LLT_mm:
        return {"found": False, "Md_Nmm": None, "cite": cite,
                "required_inputs": ["LLT_mm (unbraced compression-flange length for this moment sign)"]}
    if not base.get("found"):
        return base
    mcr = elastic_critical_moment(p, LLT_mm, c1=c1, c2=c2, yg_mm=yg_mm, K=K, Kw=Kw, E_MPa=E_MPa, G_MPa=G_MPa)
    if not mcr["found"]:
        mcr["Md_Nmm"] = None
        return mcr
    Mcr = mcr["Mcr_Nmm"]
    bb = base["beta_b"]
    lam = min(math.sqrt(bb * Zp * fy_MPa / Mcr), math.sqrt(1.2 * Ze * fy_MPa / Mcr))
    aLT = 0.49 if welded else 0.21
    out = {"found": True, "Mcr_Nmm": Mcr, "lambda_LT": lam, "alpha_LT": aLT, "beta_b": bb, "LLT_mm": float(LLT_mm),
           "section_class": section_class, "c1": c1, "welded": welded, "cite": cite,
           "Md_8_2_1_Nmm": base["Md_Nmm"]}
    if lam <= 0.4:
        out.update(chi_LT=1.0, phi_LT=None, Md_Nmm=base["Md_Nmm"], ltb="lambda_LT <= 0.4: 8.2.2(c) no LTB reduction")
        return out
    phi = 0.5 * (1 + aLT * (lam - 0.2) + lam ** 2)
    chi = min(1.0, 1.0 / (phi + math.sqrt(max(phi ** 2 - lam ** 2, 0.0))))
    fbd = chi * fy_MPa / gamma_m0
    Md = bb * Zp * fbd
    out.update(chi_LT=chi, phi_LT=phi, fbd_MPa=fbd, Md_Nmm=min(Md, base["Md_Nmm"]), ltb="8.2.2 chi_LT applied")
    return out


# ---------------------------------------------------------------- 8.4 shear
def shear_capacity(sec, fy_MPa, *, axis="z", welded=False, stiffener_spacing_mm=None, V_N=None,
                   gamma_m0=GAMMA_M0_DEFAULT, E_MPa=E_DEFAULT_MPA):
    """IS 800 8.4: Vd = Vn/gamma_m0; Vn = Vp = Av fyw/sqrt(3) or Vcr (8.4.2.2(a) simple post-critical) when
    d/tw > 67 eps (unstiffened) / 67 eps sqrt(Kv/5.35) (stiffened). Av per 8.4.1.1."""
    p = _props(sec)
    st = p.get("section_type")
    cite = "IS 800:2007 8.4.1 / 8.4.1.1 (Av) / 8.4.2.2(a) (tau_b)"
    if not fy_MPa:
        return {"found": False, "Vd_N": None, "cite": cite, "required_inputs": ["fy_MPa"]}
    eps = math.sqrt(250.0 / fy_MPa)
    if st == "CHS":
        Av = 2.0 * p["A"] / math.pi
        basis = "circular hollow tube: 2A/pi"
    elif axis == "z":
        tf = p["tf"]
        Av = (p["d"] * p["tw"]) if not welded else (p["d"] - 2 * tf) * p["tw"]
        basis = "major axis: %s" % ("h tw (hot rolled)" if not welded else "d tw (welded)")
    else:
        Av = 2.0 * p["bf"] * p["tf"]
        basis = "minor axis: 2 b tf"
    Vp = Av * fy_MPa / math.sqrt(3.0)
    out = {"found": True, "Av_mm2": Av, "Av_basis": basis, "Vp_N": Vp, "eps": eps, "cite": cite}
    Vn = Vp
    if st not in ("CHS",) and axis == "z":
        R1 = p.get("R1") or 0.0
        d = p["d"] - 2 * p["tf"] - (0.0 if welded else 2 * R1)
        dtw = d / p["tw"]
        if stiffener_spacing_mm:
            cd = float(stiffener_spacing_mm) / d
            Kv = (4.0 + 5.35 / cd ** 2) if cd < 1.0 else (5.35 + 4.0 / cd ** 2)
        else:
            Kv = 5.35
        limit = 67 * eps * (math.sqrt(Kv / 5.35) if stiffener_spacing_mm else 1.0)
        out.update(d_over_tw=dtw, shear_buckling_limit=limit, Kv=Kv)
        if dtw > limit:
            tcr = Kv * math.pi ** 2 * E_MPa / (12 * (1 - POISSON ** 2) * dtw ** 2)
            lw = math.sqrt(fy_MPa / (math.sqrt(3.0) * tcr))
            if lw <= 0.8:
                tb = fy_MPa / math.sqrt(3.0)
            elif lw < 1.2:
                tb = (1 - 0.8 * (lw - 0.8)) * fy_MPa / math.sqrt(3.0)
            else:
                tb = fy_MPa / (math.sqrt(3.0) * lw ** 2)
            Vcr = d * p["tw"] * tb
            Vn = min(Vp, Vcr)
            out.update(shear_buckling=True, tau_cr_e_MPa=tcr, lambda_w=lw, tau_b_MPa=tb, Vcr_N=Vcr)
        else:
            out["shear_buckling"] = False
    Vd = Vn / gamma_m0
    out.update(Vn_N=Vn, Vd_N=Vd)
    if V_N is not None:
        out.update(V_N=float(V_N), dc=abs(float(V_N)) / Vd, high_shear=abs(float(V_N)) > 0.6 * Vd,
                   ok=abs(float(V_N)) <= Vd)
    return out


# ---------------------------------------------------------------- Section 6 tension
def block_shear_6_4_1(Avg_mm2=None, Avn_mm2=None, Atg_mm2=None, Atn_mm2=None, fy_MPa=None, fu_MPa=None,
                      gamma_m0=GAMMA_M0_DEFAULT, gamma_m1=GAMMA_M1_DEFAULT):
    """IS 800 6.4.1: Tdb = smaller of [Avg fy/(sqrt3 gm0) + 0.9 Atn fu/gm1] and [0.9 Avn fu/(sqrt3 gm1) + Atg fy/gm0].
    All four areas are required (found:false otherwise; never one expression only)."""
    cite = "IS 800:2007 6.4.1 (block shear, smaller of the two expressions)"
    miss = [n for n, v in (("Avg_mm2", Avg_mm2), ("Avn_mm2", Avn_mm2), ("Atg_mm2", Atg_mm2), ("Atn_mm2", Atn_mm2),
                           ("fy_MPa", fy_MPa), ("fu_MPa", fu_MPa)) if v is None]
    if miss:
        return {"found": False, "Tdb_N": None, "capacity_N": None, "cite": cite, "required_inputs": miss}
    t1 = Avg_mm2 * fy_MPa / (math.sqrt(3.0) * gamma_m0) + 0.9 * Atn_mm2 * fu_MPa / gamma_m1
    t2 = 0.9 * Avn_mm2 * fu_MPa / (math.sqrt(3.0) * gamma_m1) + Atg_mm2 * fy_MPa / gamma_m0
    return {"found": True, "Tdb1_N": t1, "Tdb2_N": t2, "Tdb_N": min(t1, t2), "capacity_N": min(t1, t2),
            "governing": "Tdb1 (shear yield + tension rupture)" if t1 <= t2 else "Tdb2 (shear rupture + tension yield)",
            "Avg_mm2": Avg_mm2, "Avn_mm2": Avn_mm2, "Atg_mm2": Atg_mm2, "Atn_mm2": Atn_mm2, "cite": cite}


def tension_capacity(Ag_mm2, fy_MPa, fu_MPa=None, *, An_mm2=None, member="plate", alpha_bolts=None,
                     Anc_mm2=None, Ago_mm2=None, w_mm=None, t_mm=None, bs_mm=None, Lc_mm=None,
                     block=None, gamma_m0=GAMMA_M0_DEFAULT, gamma_m1=GAMMA_M1_DEFAULT, T_N=None):
    """IS 800 6.1: Td = min(Tdg 6.2, Tdn 6.3, Tdb 6.4). Missing rupture/block-shear inputs => that limit state is
    found:false and the result is incomplete (ok=None), never silently skipped.

    member: 'plate' (6.3.1 Tdn = 0.9 An fu/gm1), 'rod' (6.3.2), 'angle' (6.3.3 with beta shear-lag),
    'other' (6.3.4 via 6.3.3 beta). alpha_bolts (6.3.3 preliminary alpha 0.6/0.7/0.8) is accepted for sizing only.
    block = dict(Avg_mm2, Avn_mm2, Atg_mm2, Atn_mm2) for 6.4.1.
    """
    out = {"cite": "IS 800:2007 6.1-6.4", "limit_states": {}}
    if not Ag_mm2 or not fy_MPa:
        return {"found": False, "Td_N": None, "required_inputs": ["Ag_mm2", "fy_MPa"], "cite": out["cite"]}
    ls = out["limit_states"]
    ls["6.2 yield"] = {"found": True, "T_N": Ag_mm2 * fy_MPa / gamma_m0, "cite": "IS 800:2007 6.2 Tdg = Ag fy/gm0"}
    if member in ("plate", "rod"):
        if An_mm2 and fu_MPa:
            ls["6.3 rupture"] = {"found": True, "T_N": 0.9 * An_mm2 * fu_MPa / gamma_m1,
                                 "cite": "IS 800:2007 6.3.%d Tdn = 0.9 An fu/gm1" % (1 if member == "plate" else 2)}
        else:
            ls["6.3 rupture"] = {"found": False, "T_N": None, "required_inputs": ["An_mm2", "fu_MPa"]}
    else:
        if all(v is not None for v in (Anc_mm2, Ago_mm2, w_mm, t_mm, bs_mm, Lc_mm, fu_MPa)):
            beta = 1.4 - 0.076 * (w_mm / t_mm) * (fy_MPa / fu_MPa) * (bs_mm / Lc_mm)
            beta = max(0.7, min(beta, fu_MPa * gamma_m0 / (fy_MPa * gamma_m1)))
            ls["6.3.3 rupture"] = {"found": True, "beta": beta,
                                   "T_N": 0.9 * Anc_mm2 * fu_MPa / gamma_m1 + beta * Ago_mm2 * fy_MPa / gamma_m0,
                                   "cite": "IS 800:2007 6.3.3 Tdn = 0.9 Anc fu/gm1 + beta Ago fy/gm0"}
        elif alpha_bolts and An_mm2 and fu_MPa:
            ls["6.3.3 rupture (preliminary alpha)"] = {
                "found": True, "T_N": alpha_bolts * An_mm2 * fu_MPa / gamma_m1, "preliminary": True,
                "cite": "IS 800:2007 6.3.3 preliminary Tdn = alpha An fu/gm1"}
        else:
            ls["6.3.3 rupture"] = {"found": False, "T_N": None,
                                   "required_inputs": ["Anc_mm2", "Ago_mm2", "w_mm", "t_mm", "bs_mm", "Lc_mm", "fu_MPa"]}
    b = block_shear_6_4_1(fy_MPa=fy_MPa, fu_MPa=fu_MPa, gamma_m0=gamma_m0, gamma_m1=gamma_m1, **(block or {}))
    ls["6.4 block shear"] = {"found": b["found"], "T_N": b.get("Tdb_N"), "detail": b}
    vals = [v["T_N"] for v in ls.values() if v.get("found")]
    complete = all(v.get("found") for v in ls.values())
    out.update(found=True, Td_N=min(vals), complete=complete,
               governing=min(((k, v["T_N"]) for k, v in ls.items() if v.get("found")), key=lambda x: x[1])[0])
    if T_N is not None:
        dc = abs(T_N) / out["Td_N"]
        out.update(T_N=T_N, dc=dc, ok=(dc <= 1.0) if complete else (False if dc > 1.0 else None))
    return out


# ---------------------------------------------------------------- 7.1.2 member compression
def compression_capacity(sec, fy_MPa, *, KLz_mm, KLy_mm, process=None, welded=False, gamma_m0=GAMMA_M0_DEFAULT,
                         E_MPa=E_DEFAULT_MPA, KLv_mm=None):
    """Pdz / Pdy per 7.1.2 with the element's own K*L about each axis and the full Table 10 class.
    Angles: minimum axis v-v with class c (7.5 single-angle eccentric connection factors not applied: flagged)."""
    p = _props(sec)
    st = p.get("section_type")
    sc = section_class_table2(p, fy_MPa, P_N=1.0, welded=welded, loading="axial")
    out = {"cite": "IS 800:2007 7.1.2 / 7.1.2.1, Table 10 class, Table 7 alpha", "section_class_axial": sc.get("section_class")}
    if sc.get("section_class") == "slender":
        out.update(found=False, Pd_N=None, note="slender cross-section in compression (Table 2 Note 1): 7.3.2 "
                                                  "effective area not coded (found:false)")
        return out
    axes = {"z": (KLz_mm, p["rx"]), "y": (KLy_mm, p["ry"])}
    if st == "angle":
        axes = {"v": (KLv_mm or max(KLz_mm, KLy_mm), p.get("rv") or p["r_min"])}
        out["note"] = "single/double angle: 7.5 eccentric-connection equivalent slenderness not applied (flag)"
    res = {}
    for ax, (KL, r) in axes.items():
        bc = buckling_class_for_section(p, "z" if ax == "z" else "y", process=process, welded=welded)
        if not bc["found"]:
            res[ax] = {"found": False, "Pd_N": None, "buckling_class": bc}
            continue
        r_ = design_compressive_strength(p["A"], fy_MPa, KL, r, buckling_class=bc["buckling_class"],
                                         gamma_m0=gamma_m0, E_MPa=E_MPa)
        r_["buckling_class_basis"] = bc.get("basis")
        res[ax] = r_
    out["axes"] = res
    if not all(v.get("found") for v in res.values()):
        out.update(found=False, Pd_N=None)
        return out
    out.update(found=True, Pd_N=min(v["Pd_N"] for v in res.values()),
               Pdz_N=res.get("z", {}).get("Pd_N"), Pdy_N=res.get("y", res.get("v", {})).get("Pd_N"),
               KL_over_r_max=max(v["KL_over_r"] for v in res.values()))
    return out


# ---------------------------------------------------------------- 9.3 interaction
def cm_factor(M_end1, M_end2, *, sway=False):
    """IS 800 Table 18 linear gradient: Cm = 0.6 + 0.4 psi >= 0.4, psi = M_small/M_large with the sign of the
    BENDING-MOMENT DIAGRAM values (psi > 0 single curvature). Sway buckling mode: Cm = 0.9."""
    if sway:
        return {"Cm": 0.9, "psi": None, "cite": "IS 800:2007 Table 18 (sway buckling mode Cm = 0.9)"}
    a, b = float(M_end1 or 0.0), float(M_end2 or 0.0)
    big, small = (a, b) if abs(a) >= abs(b) else (b, a)
    if abs(big) < 1e-9:
        return {"Cm": 1.0, "psi": None, "cite": "IS 800:2007 Table 18", "note": "no end moments; Cm = 1.0"}
    psi = small / big
    return {"Cm": max(0.6 + 0.4 * psi, 0.4), "psi": psi, "cite": "IS 800:2007 Table 18: 0.6 + 0.4 psi >= 0.4"}


def interaction_9_3(*, P_N=0.0, Mz_Nmm=0.0, My_Nmm=0.0, Nd_N=None, Pdz_N=None, Pdy_N=None, Mdz_Nmm=None,
                    Mdy_Nmm=None, Mdz_sec_Nmm=None, Mdy_sec_Nmm=None, lambda_z=None, lambda_y=None, lambda_LT=None,
                    Cmz=1.0, Cmy=1.0, CmLT=1.0, section_class="plastic", section_type="I", Ag_mm2=None,
                    Zec_mm3=None, Td_N=None, psi_tension=0.8):
    """IS 800 9.3: section strength 9.3.1 and member buckling 9.3.2 (both 9.3.2.2 equations for compression,
    9.3.2.1 M_eff for tension). P_N > 0 compression, < 0 tension. Mdz_Nmm = LTB design moment (8.2.2);
    Mdz_sec_Nmm / Mdy_sec_Nmm = laterally supported (8.2.1.2) capacities used in 9.3.1."""
    P, Mz, My = float(P_N or 0.0), abs(float(Mz_Nmm or 0.0)), abs(float(My_Nmm or 0.0))
    out = {"cite": "IS 800:2007 9.3.1 (section) + 9.3.2.2 (member, both equations)", "P_N": P, "Mz_Nmm": Mz,
           "My_Nmm": My}
    Mdzs = Mdz_sec_Nmm or Mdz_Nmm
    Mdys = Mdy_sec_Nmm or Mdy_Nmm
    if not (Nd_N and Mdzs and Mdys):
        out.update(found=False, dc=None, required_inputs=["Nd_N", "Mdz", "Mdy"])
        return out
    n = abs(P) / Nd_N
    # 9.3.1
    if section_class in ("plastic", "compact"):
        if section_type == "CHS":
            Mndz = min(1.04 * Mdzs * (1 - n ** 1.7), Mdzs)
            Mndy = min(1.04 * Mdys * (1 - n ** 1.7), Mdys)
            a1 = a2 = 2.0
        else:
            Mndz = min(1.11 * Mdzs * (1 - n), Mdzs)
            Mndy = Mdys if n <= 0.2 else 1.56 * Mdys * (1 - n) * (n + 0.6)
            a1, a2 = max(5.0 * n, 1.0), 2.0
        if Mndz <= 0 or Mndy <= 0:
            sec = float("inf")
        else:
            sec = (My / Mndy) ** a1 + (Mz / Mndz) ** a2
        out["section_9_3_1"] = {"dc": sec, "method": "9.3.1.1 (Mndy/Mndz per 9.3.1.2, alpha per Table 17)",
                                "n": n, "Mndz_Nmm": Mndz, "Mndy_Nmm": Mndy, "alpha1": a1, "alpha2": a2}
    else:
        sec = abs(P) / Nd_N + My / Mdys + Mz / Mdzs
        out["section_9_3_1"] = {"dc": sec, "method": "9.3.1.3 semi-compact linear", "n": n}
    dcs = [sec]
    if P > 0:
        if not (Pdz_N and Pdy_N and Mdz_Nmm and Mdy_Nmm and lambda_z is not None and lambda_y is not None):
            out.update(found=False, dc=None, required_inputs=["Pdz_N", "Pdy_N", "Mdz (LTB)", "Mdy", "lambda_z", "lambda_y"])
            return out
        ny, nz = P / Pdy_N, P / Pdz_N
        Ky = min(1 + (lambda_y - 0.2) * ny, 1 + 0.8 * ny)
        Kz = min(1 + (lambda_z - 0.2) * nz, 1 + 0.8 * nz)
        lamLT = lambda_LT or 0.0
        KLT = max(1 - 0.1 * lamLT * ny / (CmLT - 0.25), 1 - 0.1 * ny / (CmLT - 0.25))
        e1 = P / Pdy_N + Ky * Cmy * My / Mdy_Nmm + KLT * Mz / Mdz_Nmm
        e2 = P / Pdz_N + 0.6 * Ky * Cmy * My / Mdy_Nmm + Kz * Cmz * Mz / Mdz_Nmm
        out["member_9_3_2_2"] = {"eq1": e1, "eq2": e2, "Ky": Ky, "Kz": Kz, "KLT": KLT, "ny": ny, "nz": nz,
                                 "Cmy": Cmy, "Cmz": Cmz, "CmLT": CmLT}
        dcs += [e1, e2]
    elif P < 0:
        if Ag_mm2 and Zec_mm3 and Mdz_Nmm:
            Meff = max(Mz - psi_tension * abs(P) * Zec_mm3 / Ag_mm2, 0.0)
            out["member_9_3_2_1"] = {"Meff_Nmm": Meff, "dc": Meff / Mdz_Nmm, "psi": psi_tension}
            dcs.append(Meff / Mdz_Nmm)
        if Td_N:
            out["tension_Td"] = {"dc": abs(P) / Td_N}
            dcs.append(abs(P) / Td_N)
    else:
        dcs.append(Mz / Mdz_Nmm if Mdz_Nmm else float("inf"))
        dcs.append(My / Mdy_Nmm if Mdy_Nmm else 0.0)
    out.update(found=True, dc=max(dcs), ok=max(dcs) <= 1.0)
    return out


# ---------------------------------------------------------------- Table 3 slenderness
TABLE3_LIMITS = {
    "compression_DL_LL": 180, "tension_reversal_non_WL_EL": 180, "compression_WL_EL_only": 250,
    "beam_compression_flange_LTB": 300, "tie_reversal_WL_EL": 350, "tension_only": 400}


# ---------------------------------------------------------------- member check per combination
def member_check_is800(member, combo_forces, *, cfg=None):
    """IS 800 member check evaluated PER COMBINATION with concurrent P, Mz, My (HREX1-X-02, HREX2-X-01).

    member = {id, section, grade (IS 2062 'E250'...; IS 1161 'YSt 240' for CHS), process (CHS), role
              ('column'|'beam'|'brace'), L_mm (element length), Kz, Ky (Table 11 / Annex D; default 1.0 with a
              flag), Lz_mm/Ly_mm (optional member lengths if different from L_mm), LLT_sag_mm, LLT_hog_mm (unbraced
              compression-flange lengths for sagging / hogging), welded, support, sway (bool), fy_MPa (override)}
    combo_forces = [{combo, P_N (+compression), Mz_i_Nmm, Mz_j_Nmm, My_i_Nmm, My_j_Nmm (bending-moment-diagram
              values at the two ends, sagging +), Mz_mid_Nmm (optional span moment), Vy_N, Vz_N}]
    Returns {governing_combo, dc, ok, per_combo[...], capacities{...}, clause}.
    """
    import sections as _S
    sec = member["section"]
    p = _S.props(sec, grade=member.get("grade"), process=member.get("process")) if str(sec).upper().startswith(("CHS", "NB")) else _S.props(sec)
    mat = material_for_section(p, member.get("grade"), process=member.get("process"))
    fy = member.get("fy_MPa") or mat.get("fy_MPa")
    fu = member.get("fu_MPa") or mat.get("fu_MPa")
    res = {"id": member.get("id"), "section": sec, "role": member.get("role"), "material": mat, "fy_MPa": fy,
           "clause": "IS 800:2007 7.1.2, 8.2, 8.4, 9.3; Table 2/3/10", "flags": []}
    if not fy:
        res.update(found=False, ok=None, dc=None, reason="material grade not resolved (no default fy)")
        return res
    L = float(member.get("L_mm") or 0.0)
    if L <= 0:
        res.update(found=False, ok=None, dc=None, reason="element length L_mm missing")
        return res
    Kz, Ky = member.get("Kz"), member.get("Ky")
    if Kz is None or Ky is None:
        res["flags"].append("K not supplied: K = 1.0 used (Table 11 / Annex D basis must be declared)")
        Kz = 1.0 if Kz is None else Kz
        Ky = 1.0 if Ky is None else Ky
    KLz = Kz * float(member.get("Lz_mm") or L)
    KLy = Ky * float(member.get("Ly_mm") or L)
    welded = bool(member.get("welded"))
    comp = compression_capacity(p, fy, KLz_mm=KLz, KLy_mm=KLy, process=member.get("process"), welded=welded)
    shz = shear_capacity(p, fy, axis="z", welded=welded)
    shy = shear_capacity(p, fy, axis="y", welded=welded)
    sc0 = section_class_table2(p, fy, welded=welded)
    Md_y = design_moment_8_2_1(p["Zy"], p["Sy"], fy, sc0["section_class"], support=member.get("support", "simple"))
    Md_z_sec = design_moment_8_2_1(p["Zx"], p["Sx"], fy, sc0["section_class"], support=member.get("support", "simple"))
    ltb_cache = {}

    def _mdz(LLT, psi=None):
        key = (LLT, None if psi is None else round(psi, 3))
        if key not in ltb_cache:
            c1 = c1_from_end_moments(psi) if psi is not None and member.get("use_c1", True) else 1.0
            ltb_cache[key] = ltb_moment_capacity(p, LLT, fy, welded=welded, section_class=sc0["section_class"], c1=c1,
                                                 support=member.get("support", "simple"))
        return ltb_cache[key]

    Td = tension_capacity(p["A"], fy, fu, **(member.get("tension_inputs") or {}))
    res["capacities"] = {"compression": comp, "shear_z": shz, "shear_y": shy, "Mdy": Md_y, "Mdz_section": Md_z_sec,
                         "section_class": sc0, "tension": Td}
    klr = comp.get("KL_over_r_max")
    if klr is not None:
        lim = TABLE3_LIMITS["compression_WL_EL_only"] if member.get("compression_only_from_WL_EL") else TABLE3_LIMITS["compression_DL_LL"]
        res["table3_slenderness"] = {"value": klr, "limit": lim, "dc": klr / lim, "ok": klr <= lim,
                                     "clause": "IS 800:2007 3.8 / Table 3", "cite": "Table 3 maximum KL/r"}
    per = []
    for cf in combo_forces or []:
        P = float(cf.get("P_N") or 0.0)
        Mzi, Mzj = float(cf.get("Mz_i_Nmm") or 0.0), float(cf.get("Mz_j_Nmm") or 0.0)
        Myi, Myj = float(cf.get("My_i_Nmm") or 0.0), float(cf.get("My_j_Nmm") or 0.0)
        Mzm = cf.get("Mz_mid_Nmm")
        zs = [Mzi, Mzj] + ([float(Mzm)] if Mzm is not None else [])
        Mz_sag = max([m for m in zs if m > 0] or [0.0])
        Mz_hog = -min([m for m in zs if m < 0] or [0.0])
        My = max(abs(Myi), abs(Myj))
        sway = bool(member.get("sway"))
        cmz = cm_factor(Mzi, Mzj, sway=sway) if Mzm is None else {"Cm": 0.9 if sway else 1.0, "note": "span load: Cm=1.0 unless Table 18 row chosen"}
        cmy = cm_factor(Myi, Myj, sway=sway)
        psi = cmz.get("psi")
        rec = {"combo": cf.get("combo"), "P_N": P, "Mz_sag_Nmm": Mz_sag, "Mz_hog_Nmm": Mz_hog, "My_Nmm": My,
               "Cmz": cmz["Cm"], "Cmy": cmy["Cm"]}
        checks = []
        signs = []
        if Mz_sag > 0 or Mz_hog <= 0:
            signs.append(("sagging", Mz_sag, member.get("LLT_sag_mm")))
        if Mz_hog > 0:
            signs.append(("hogging", Mz_hog, member.get("LLT_hog_mm")))
        for sign, Mz, LLT in signs:
            if LLT is None:
                LLT = L if member.get("LLT_default_to_L", True) else None
                if LLT is not None:
                    res["flags"].append("LLT_%s not declared: element length used" % sign[:3])
            ltb = _mdz(LLT, psi)
            if not ltb.get("found"):
                checks.append({"moment_sign": sign, "found": False, "ltb": ltb})
                continue
            ia = interaction_9_3(P_N=P, Mz_Nmm=Mz, My_Nmm=My, Nd_N=p["A"] * fy / GAMMA_M0_DEFAULT,
                                 Pdz_N=comp.get("Pdz_N"), Pdy_N=comp.get("Pdy_N"), Mdz_Nmm=ltb["Md_Nmm"],
                                 Mdy_Nmm=Md_y.get("Md_Nmm"), Mdz_sec_Nmm=Md_z_sec.get("Md_Nmm"),
                                 Mdy_sec_Nmm=Md_y.get("Md_Nmm"),
                                 lambda_z=(comp.get("axes", {}).get("z") or {}).get("lambda"),
                                 lambda_y=(comp.get("axes", {}).get("y") or comp.get("axes", {}).get("v") or {}).get("lambda"),
                                 lambda_LT=ltb.get("lambda_LT"), Cmz=cmz["Cm"], Cmy=cmy["Cm"], CmLT=cmz["Cm"],
                                 section_class=sc0["section_class"], section_type="CHS" if p.get("section_type") == "CHS" else "I",
                                 Ag_mm2=p["A"], Zec_mm3=p["Sx"], Td_N=Td.get("Td_N"))
            ia.update(moment_sign=sign, LLT_mm=LLT, Mdz_LTB_Nmm=ltb["Md_Nmm"], chi_LT=ltb.get("chi_LT"),
                      lambda_LT=ltb.get("lambda_LT"))
            checks.append(ia)
        V = max(abs(float(cf.get("Vy_N") or 0.0)), 0.0)
        if V and shz.get("Vd_N"):
            checks.append({"shear_z": True, "dc": V / shz["Vd_N"], "found": True, "high_shear": V > 0.6 * shz["Vd_N"]})
        Vz = abs(float(cf.get("Vz_N") or 0.0))
        if Vz and shy.get("Vd_N"):
            checks.append({"shear_y": True, "dc": Vz / shy["Vd_N"], "found": True})
        if any(not c.get("found") for c in checks) or not checks:
            rec.update(dc=None, ok=None, checks=checks)
        else:
            rec.update(dc=max(c["dc"] for c in checks), checks=checks)
            rec["ok"] = rec["dc"] <= 1.0
        per.append(rec)
    res["per_combo"] = per
    if not per:
        res.update(found=False, ok=None, dc=None, reason="no combination forces")
        return res
    if any(r["dc"] is None for r in per):
        res.update(found=False, ok=None, dc=None, reason="one or more combinations not evaluable (missing capacity input)")
        worst = max((r for r in per if r["dc"] is not None), key=lambda r: r["dc"], default=None)
        res["governing_combo"] = worst and worst["combo"]
        return res
    worst = max(per, key=lambda r: r["dc"])
    dc = worst["dc"]
    if res.get("table3_slenderness") and not res["table3_slenderness"]["ok"]:
        dc = max(dc, res["table3_slenderness"]["dc"])
    res.update(found=True, governing_combo=worst["combo"], dc=dc, ok=dc <= 1.0,
               value=dc, limit=1.0, cite="IS 800:2007 9.3.2.2 / 9.3.1 per combination (concurrent P, Mz, My)")
    return res
