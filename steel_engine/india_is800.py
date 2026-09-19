"""IS 800:2007 helpers for India HR design (buckling χ, SMF SCWB, panel-zone, §12 slots).

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
    buckling_class: str = "c",
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


def plastic_moment_Nmm(
    Zx_mm3: float,
    fy_MPa: float,
    gamma_m0: float = GAMMA_M0_DEFAULT,
    beta_b: float = 1.0,
) -> Dict[str, Any]:
    """Md / Mp proxy = βb Zp fy / γm0 — IS 800 §8.2.1 (laterally supported)."""
    if not Zx_mm3 or Zx_mm3 <= 0 or not fy_MPa or fy_MPa <= 0:
        return {
            "found": False,
            "Mp_Nmm": None,
            "cite": "IS 800:2007 §8.2.1",
            "required_inputs": ["Zx_mm3", "fy_MPa"],
        }
    Mp = float(beta_b) * float(Zx_mm3) * float(fy_MPa) / float(gamma_m0)
    return {
        "found": True,
        "Mp_Nmm": Mp,
        "Zx_mm3": float(Zx_mm3),
        "fy_MPa": float(fy_MPa),
        "gamma_m0": float(gamma_m0),
        "beta_b": float(beta_b),
        "cite": "IS 800:2007 §8.2.1  Md = βb Zp fy / γm0",
    }


def scwb_ratio(
    Mpc_list_Nmm: Optional[Sequence[float]] = None,
    Mpb_list_Nmm: Optional[Sequence[float]] = None,
    *,
    columns: Optional[Sequence[Dict[str, Any]]] = None,
    beams: Optional[Sequence[Dict[str, Any]]] = None,
    fy_MPa: float = 250.0,
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
            gm = it.get("gamma_m0", gamma_m0)
            r = plastic_moment_Nmm(zx, fy, gm)
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
        "note": "Mp from §8.2.1 Zp fy/γm0 unless caller supplied Mp_Nmm directly",
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
) -> Dict[str, Any]:
    """Panel-zone / doubler worksheet — IS 800 §12.11.2.3–12.11.2.4 + §8.4.2 shear.

    Thickness rule: t ≥ (dp + bp)/90 with dp≈d_beam, bp≈d_col−2 tf (panel width between flanges).
    Shear capacity (simplified): Vd = Av fy /(√3 γm0) with Av ≈ (d_col−2 tf)·(tw+tdoubler).
    Missing inputs → found:false with required_inputs listed (no invented doubler size).
    """
    missing = []
    for name, val in (
        ("column_d_mm", d_col_mm),
        ("column_tw_mm", tw_mm),
        ("column_bf_mm", bf_mm),
        ("column_tf_mm", tf_mm),
        ("beam_d_mm", d_beam_mm),
        ("V_design_N", V_design_N),
        ("fy_col_MPa", fy_MPa),
    ):
        if val is None or (isinstance(val, (int, float)) and val <= 0 and name != "V_design_N"):
            missing.append(name)
        if name == "V_design_N" and (val is None or val < 0):
            if "V_design_N" not in missing:
                missing.append("V_design_N")
    if missing:
        return {
            "found": False,
            "pass": None,
            "doubler_required_mm": None,
            "cite": "IS 800:2007 §12.11.2.3 / §12.11.2.4 / §8.4.2",
            "required_inputs": list(PANEL_ZONE_REQUIRED),
            "missing": missing,
            "note": "Panel-zone worksheet cannot size/flag without listed inputs",
        }

    d_col = float(d_col_mm)
    tw = float(tw_mm)
    bf = float(bf_mm)
    tf = float(tf_mm)
    d_beam = float(d_beam_mm)
    V = float(V_design_N)
    fy = float(fy_MPa)
    t_dbl = float(doubler_t_mm or 0.0)

    # Panel geometry (corpus §12.11.2.4): dp = panel-zone depth between continuity plates ≈ beam depth
    # bp = panel-zone width between column flanges ≈ d_col − 2 tf
    dp = d_beam
    bp = max(d_col - 2.0 * tf, 1.0)
    t_min = (dp + bp) / 90.0
    t_provided = tw + t_dbl
    thickness_ok = t_provided >= t_min

    # Shear area & capacity (§8.4.1 / 8.4.2 style)
    if Av_override_mm2 is not None and Av_override_mm2 > 0:
        Av = float(Av_override_mm2)
    else:
        Av = max(d_col - 2.0 * tf, 0.0) * t_provided
    Vd = Av * fy / (math.sqrt(3.0) * float(gamma_m0)) if Av > 0 else 0.0
    dc = (V / Vd) if Vd > 0 else None
    shear_ok = (dc is not None) and (dc <= 1.0)

    # Suggested doubler if thickness fails (honest sizing from t_min only — not inventing grade)
    t_need_extra = max(0.0, t_min - tw)
    # If shear governs, estimate extra t from required Av
    t_need_shear = 0.0
    if Vd > 0 and dc is not None and dc > 1.0 and (d_col - 2.0 * tf) > 0:
        Av_need = V * math.sqrt(3.0) * float(gamma_m0) / fy
        t_need_shear = max(0.0, Av_need / (d_col - 2.0 * tf) - tw)

    doubler_req = max(t_need_extra, t_need_shear)

    return {
        "found": True,
        "pass": bool(thickness_ok and shear_ok),
        "thickness_ok": thickness_ok,
        "shear_ok": shear_ok,
        "t_provided_mm": t_provided,
        "t_min_mm": t_min,
        "dp_mm": dp,
        "bp_mm": bp,
        "Av_mm2": Av,
        "Vd_N": Vd,
        "V_design_N": V,
        "DC_shear": dc,
        "doubler_required_mm": doubler_req if doubler_req > 1e-6 else 0.0,
        "doubler_provided_mm": t_dbl,
        "cite": "IS 800:2007 §12.11.2.3–12.11.2.4 (t≥(dp+bp)/90); shear §8.4.2 / §8.4.1",
        "note": (
            "Doubler suggestion is thickness-only from code inequalities; confirm electrode/"
            "plate grade via IS 816 / IS 800 RAG before detailing."
        ),
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
    demand_factor: float = 1.2,
) -> Dict[str, Any]:
    """Fill a §12 gusset/bolt/weld slot D/C when demand + RAG capacity are both present.

    If demand omitted but fy+Ag given, demand defaults to demand_factor·fy·Ag (N)
    (IS 800 §12.7.3.1 brace CD form) — still requires an explicit capacity from RAG.
    Never invents capacity_N.
    """
    out = dict(slot or {})
    component = out.get("component") or "component"
    req = list(CONN_COMPONENT_REQUIRED.get(component, ["demand_N", "capacity_N", "cited"]))

    dem = demand_N
    if dem is None and fy_MPa and Ag_mm2:
        dem = float(demand_factor) * float(fy_MPa) * float(Ag_mm2)  # MPa·mm² = N
        out["demand_basis"] = f"{demand_factor}·fy·Ag (IS 800 §12.7.3.1 style)"
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
