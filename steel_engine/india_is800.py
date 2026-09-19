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
        "inputs": {
            "d_col_mm": d_col_mm,
            "tw_mm": tw_mm,
            "bf_mm": bf_mm,
            "tf_mm": tf_mm,
            "d_beam_mm": d_beam_mm,
            "V_design_N": V_design_N,
            "fy_MPa": fy_MPa,
            "gamma_m0": gamma_m0,
            "doubler_t_mm": doubler_t_mm,
        }
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
    """Concrete bearing under base plate — RAG capacity or geometry × RAG stress.

    Paths: (1) capacity_N from RAG; (2) B×L × bearing_stress from RAG;
    (3) B×L × (bearing_factor × fck) when both factor and fck from RAG/disclosed.
    Never invents bearing stress or plate plan.
    """
    cite = cite or "IS 800:2007 Ch.11 / IS 456 concrete bearing"
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
            "bearing_stress_MPa from RAG OR (fck_MPa + bearing_factor from RAG) "
            "— do not invent 0.45 fck silently"
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
    cite = cite or "IS 800:2007 Ch.11 / IS 456 anchorage — RAG"
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
    """IS 800 Ch.11 / base-plate component worksheet.

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
            "note": "Concrete bearing under plate — RAG IS 800 Ch.11 / IS 456; found:false until sized.",
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
            "note": "Anchor rods — RAG IS 800 / IS 456; found:false until sized.",
        },
        "welds": {
            "component": "column_to_plate_welds",
            "found": False, "DC": None, "capacity": {},
            "required_inputs": list(WELD_COMPONENT_REQUIRED),
            "note": "Fillet welds column-to-plate — RAG IS 816; found:false until sized.",
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
        cited_br = cited or "IS 800 Ch.11 bearing"
    if capacity_bearing_N is not None and P_N is not None:
        slots["bearing"] = fill_connection_component_dc(
            slots["bearing"], demand_N=float(P_N), capacity_N=float(capacity_bearing_N),
            cited=cited_br or cited or "IS 800 Ch.11 bearing",
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
        "cite": "IS 800:2007 Ch.11 / §10; IS 816 welds",
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
):
    """Fillet weld design/allowable capacity from RAG stress + geometry.

    IS 816:1969 §7.1.2 — permissible stress on throat 1100 kgf/cm² (ASD).
    Throat a = size/√2 when only leg size given. Capacity = stress × a × L × n_sides.
    Missing stress or length → found:false (never invent stress or size).
    """
    missing = []
    stress = permissible_stress_MPa
    if stress is None and permissible_stress_kgf_cm2 is not None:
        # 1 kgf/cm² = 0.0980665 N/mm² (MPa)
        stress = float(permissible_stress_kgf_cm2) * 0.0980665
    if stress is None:
        missing.append("permissible_stress_MPa or permissible_stress_kgf_cm2 from RAG (IS 816)")
    a = throat_mm
    if a is None and size_mm is not None:
        a = float(size_mm) / math.sqrt(2.0)
    if a is None or float(a) <= 0:
        missing.append("throat_mm or size_mm (leg)")
    if length_mm is None or float(length_mm) <= 0:
        missing.append("length_mm")
    if missing:
        return {
            "found": False,
            "capacity_N": None,
            "cite": cite or "IS 816:1969 §7.1.2",
            "required_inputs": missing,
            "note": "Do not invent weld size/length or stress — RAG stress + geometry required.",
        }
    cap = float(stress) * float(a) * float(length_mm) * float(n_sides or 1)
    return {
        "found": True,
        "capacity_N": cap,
        "throat_mm": float(a),
        "size_mm": float(size_mm) if size_mm is not None else None,
        "length_mm": float(length_mm),
        "n_sides": int(n_sides or 1),
        "stress_MPa": float(stress),
        "cite": cite or "IS 816:1969 §7.1.2 fillet weld throat stress",
        "note": "Capacity = stress × throat × length × n_sides — stress from RAG; geometry disclosed.",
    }


def bolt_group_capacity_N(
    *,
    n_bolts=None,
    V_one_bolt_N=None,
    cite=None,
    limit_state=None,
):
    """Bolt-group shear/bearing capacity = n × V_one from RAG (IS 800 §10 / IS 4000).

    Never invents per-bolt capacity — V_one_bolt_N must come from LIVE RAG.
    """
    missing = []
    if n_bolts is None or int(n_bolts) < 1:
        missing.append("n_bolts")
    if V_one_bolt_N is None or float(V_one_bolt_N) <= 0:
        missing.append("V_one_bolt_N from LIVE RAG (IS 800 §10 / IS 4000)")
    if missing:
        return {
            "found": False,
            "capacity_N": None,
            "cite": cite or "IS 800:2007 §10 / IS 4000:1992",
            "required_inputs": missing,
            "note": "Do not invent bolt grade/diameter capacity — retrieve Vdsb/Vdpb etc.",
        }
    return {
        "found": True,
        "capacity_N": float(n_bolts) * float(V_one_bolt_N),
        "n_bolts": int(n_bolts),
        "V_one_bolt_N": float(V_one_bolt_N),
        "limit_state": limit_state,
        "cite": cite or "IS 800:2007 §10 / IS 4000:1992",
        "note": "n × RAG per-bolt capacity — no invented V_one.",
    }


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
        dem = d.get("axial_N") or d.get("P_N") or d.get("V_N")

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
                w = fillet_weld_capacity_N(
                    throat_mm=rag_c.get("throat_mm"),
                    size_mm=rag_c.get("size_mm") or rag_c.get("leg_mm"),
                    length_mm=rag_c.get("length_mm"),
                    permissible_stress_MPa=rag_c.get("permissible_stress_MPa") or rag_c.get("stress_MPa"),
                    permissible_stress_kgf_cm2=rag_c.get("permissible_stress_kgf_cm2"),
                    cite=cited,
                    n_sides=rag_c.get("n_sides", 1),
                )
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
                b = bolt_group_capacity_N(
                    n_bolts=rag_c.get("n_bolts") or rag_c.get("n"),
                    V_one_bolt_N=rag_c.get("V_one_bolt_N") or rag_c.get("Vdsb_N"),
                    cite=cited,
                    limit_state=rag_c.get("limit_state"),
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
    fy_MPa: float = 250.0,
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


# --- IS 4000:1992 Table 2 (retrieved LIVE) — max permissible shear Vob, kN ----
# Source: engineering_rag_india exact_table 2 on IS_4000_1992 (clauses 5.2 / 5.3.2).
# Values are corpus-verbatim; do not invent additional diameters/classes.
IS4000_TABLE2_Vob_kN = {
    # (nominal_mm, property_class, plane) -> kN ; plane in {"shank","thread"}
    (16, "8.8", "shank"): 40.2, (16, "8.8", "thread"): 31.4,
    (16, "10.9", "shank"): 52.3, (16, "10.9", "thread"): 40.8,
    (20, "8.8", "shank"): 65.2, (20, "8.8", "thread"): 50.8,
    (20, "10.9", "shank"): 81.6, (20, "10.9", "thread"): 63.7,
    (24, "8.8", "shank"): 93.8, (24, "8.8", "thread"): 73.2,
    (24, "10.9", "shank"): 117.0, (24, "10.9", "thread"): 91.8,
    (30, "8.8", "shank"): 146.0, (30, "8.8", "thread"): 116.0,
    (30, "10.9", "shank"): 148.0, (30, "10.9", "thread"): 146.0,
    (36, "8.8", "shank"): 211.0, (36, "8.8", "thread"): 169.0,
    (36, "10.9", "shank"): 264.0, (36, "10.9", "thread"): 212.0,
}
IS4000_TABLE2_CITE = (
    "IS 4000:1992 Table 2 — Maximum Permissible Applied Forces for Joints "
    "(bearing-type shear Vob); RAG exact_table 2"
)

# IS 800 Table 5 γmw shop welds (common) — corpus; site welds use 1.5
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
    """n × Vob from IS 4000 Table 2 (RAG-backed constants). found:false if size missing."""
    missing = []
    if n_bolts is None or int(n_bolts) < 1:
        missing.append("n_bolts")
    if diameter_mm is None:
        missing.append("diameter_mm (M16/M20/M24/M30/M36)")
    key = None
    if diameter_mm is not None:
        key = (int(diameter_mm), str(property_class), str(plane).lower())
        if key not in IS4000_TABLE2_Vob_kN:
            missing.append("diameter/property_class/plane in IS 4000 Table 2 corpus set")
    if missing:
        return {
            "found": False,
            "capacity_N": None,
            "cite": cite or IS4000_TABLE2_CITE,
            "required_inputs": missing,
            "note": "Do not invent Vob — use Table 2 rows present in India RAG.",
        }
    Vob_kN = IS4000_TABLE2_Vob_kN[key]
    return {
        "found": True,
        "capacity_N": float(n_bolts) * Vob_kN * 1000.0,  # kN → N
        "Vob_one_kN": Vob_kN,
        "n_bolts": int(n_bolts),
        "diameter_mm": int(diameter_mm),
        "property_class": str(property_class),
        "plane": str(plane).lower(),
        "cite": cite or IS4000_TABLE2_CITE,
        "note": "Bearing-type joint shear — IS 4000 Table 2 RAG; LSD conversion not applied (ASD table).",
    }


def fillet_weld_capacity_is800_N(
    *,
    throat_mm=None,
    size_mm=None,
    length_mm=None,
    fu_MPa=None,
    gamma_mw=GAMMA_MW_SHOP,
    n_sides=1,
    cite=None,
):
    """IS 800:2007 §10.5.7.1.1 — fwd = fu/(√3 γmw); capacity = fwd × a × L × n_sides.

    fu and geometry required — never invent fu or size. Typical RAG: fu=410 E250; γmw=1.25 shop.
    """
    missing = []
    if fu_MPa is None or float(fu_MPa) <= 0:
        missing.append("fu_MPa from RAG (weld or parent; IS 800 §10.5.7.1.1)")
    a = throat_mm
    if a is None and size_mm is not None:
        a = float(size_mm) / math.sqrt(2.0)
    if a is None or float(a) <= 0:
        missing.append("throat_mm or size_mm")
    if length_mm is None or float(length_mm) <= 0:
        missing.append("length_mm")
    if missing:
        return {
            "found": False,
            "capacity_N": None,
            "cite": cite or "IS 800:2007 §10.5.7.1.1",
            "required_inputs": missing,
            "note": "Do not invent fu or weld size — RAG + disclosed geometry required.",
        }
    fwd = float(fu_MPa) / (math.sqrt(3.0) * float(gamma_mw))
    cap = fwd * float(a) * float(length_mm) * float(n_sides or 1)
    return {
        "found": True,
        "capacity_N": cap,
        "fwd_MPa": fwd,
        "fu_MPa": float(fu_MPa),
        "gamma_mw": float(gamma_mw),
        "throat_mm": float(a),
        "length_mm": float(length_mm),
        "n_sides": int(n_sides or 1),
        "cite": cite or "IS 800:2007 §10.5.7.1.1 fwd=fu/(√3 γmw); γmw Table 5",
        "note": "LSD fillet capacity from RAG fu + disclosed throat/length — no invented size.",
    }


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
    must come from RAG or eor_documented — never invent E250B availability (H7)
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
        missing.append("plate_fy_MPa or plate_grade from RAG / eor_documented")
    if not electrode:
        missing.append("electrode (IS 814 / IS 816 class) from RAG — do not invent")
    if missing:
        detail.update({
            "found": False,
            "required_inputs": missing,
            "cite": "IS 800:2007 §12.11.2.3–12.11.2.4 doubler; grade/electrode from RAG",
            "note": (
                "Doubler thickness may be flagged by panel_zone_check; plate grade and "
                "electrode remain found:false until RAG/EOR supplies them. H7 E250B "
                "procurement is a separate process note — do not invent availability."
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


# Allowlisted provenance for EOR-documented end-plate / continuity Rn (CFS-style R).
# Prefer LIVE RAG / QFM when clauses yield a numeric capacity; never invent Rn.
END_PLATE_RN_OK_SOURCES = frozenset({
    "rag", "corpus", "qfm", "live_rag", "is800", "is_800",
    "eor_documented", "eor", "documented", "explicit", "eor_explicit",
})
END_PLATE_RN_REFUSED_SOURCES = frozenset({
    "assumed", "assumption", "silent", "silent_default", "invented",
    "placeholder", "todo", "tbd", "guess", "thin_air",
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
    """End-plate / continuity Rn — RAG preferred; EOR-documented parallel to CFS R.

    Paths (never invent from thin air):
      1) LIVE RAG / QFM capacity_N (or Rn with source in rag/corpus/qfm) — preferred
         when QFM finds clauses that yield a numeric capacity.
      2) EOR-documented: Rn + cite + source='eor_documented' (allowlisted) —
         COMPLETE may use when labeled; refuse assumed/silent/invented sources.
      3) found:false if neither — required_inputs listed.

    cfg optional keys: end_plate_Rn / end_plate_capacity_N, end_plate_Rn_cite,
    end_plate_Rn_source (or nested under cfg['end_plate'] / cfg['continuity']).
    """
    cfg = cfg if isinstance(cfg, dict) else {}
    ep = cfg.get("end_plate") if isinstance(cfg.get("end_plate"), dict) else {}
    cont = cfg.get("continuity") if isinstance(cfg.get("continuity"), dict) else {}

    cite = (cite or cfg.get("end_plate_Rn_cite") or cfg.get("end_plate_cite")
            or ep.get("cite") or ep.get("Rn_cite") or cont.get("cite"))
    src = _norm_src(
        source or cfg.get("end_plate_Rn_source") or cfg.get("end_plate_source")
        or ep.get("source") or ep.get("Rn_source") or cont.get("source")
    )
    cap = capacity_N if capacity_N is not None else Rn
    if cap is None:
        cap = (cfg.get("end_plate_capacity_N") or cfg.get("end_plate_Rn")
               or ep.get("capacity_N") or ep.get("Rn")
               or cont.get("capacity_N") or cont.get("Rn"))
    dem = demand_N
    if dem is None and isinstance(cfg.get("end_plate"), dict):
        dem = ep.get("demand_N")

    default_cite = "IS 800:2007 §10 / §12.11 end-plate / continuity"

    # Path 1: RAG / QFM numeric capacity (preferred when clauses found)
    rag_like = (not src) or src in ("rag", "corpus", "qfm", "live_rag", "is800", "is_800")
    if cap is not None and float(cap) > 0 and rag_like and src not in END_PLATE_RN_REFUSED_SOURCES:
        # Bare capacity_N without source → treat as RAG passthrough (wave2/3 contract)
        if not src or src in ("rag", "corpus", "qfm", "live_rag", "is800", "is_800"):
            out = {
                "found": True,
                "capacity_N": float(cap),
                "Rn": float(cap),
                "limit_state": limit_state,
                "source": src or "rag",
                "resolved_via": "rag",
                "cite": cite or default_cite,
                "note": (
                    "End-plate/continuity Rn from LIVE RAG / QFM — preferred when clauses "
                    "yield a numeric capacity. Not invented."
                ),
                "policy": "prefer_rag_when_qfm_finds_clauses",
            }
            if dem is not None and float(cap) > 0:
                out["DC"] = float(dem) / float(cap)
                out["demand_N"] = float(dem)
            return out

    # Path 2: EOR-documented (CFS-style R parallel) — Rn + cite + allowlisted source
    if (cap is not None and float(cap) > 0
            and src in END_PLATE_RN_OK_SOURCES
            and src not in ("rag", "corpus", "qfm", "live_rag", "is800", "is_800")
            and cite):
        if src in END_PLATE_RN_REFUSED_SOURCES:
            return {
                "found": False,
                "capacity_N": None,
                "Rn": None,
                "source": src,
                "resolved_via": "refused",
                "cite": default_cite,
                "required_inputs": [
                    "Rn + cite + source=eor_documented (not assumed/silent/invented)",
                    "OR capacity_N from LIVE RAG / QFM",
                ],
                "note": (
                    "Refused end-plate Rn source=%r — never invent from thin air. "
                    "Use LIVE RAG when QFM finds clauses, or EOR-documented Rn+cite."
                    % (src,)
                ),
            }
        out = {
            "found": True,
            "capacity_N": float(cap),
            "Rn": float(cap),
            "limit_state": limit_state,
            "source": src,
            "resolved_via": "eor_documented" if ("eor" in src or src == "documented") else src,
            "cite": str(cite),
            "note": (
                "End-plate/continuity Rn from EOR-documented path (CFS-style eor_documented R "
                "parallel). Corpus/QFM often found:false for numeric Rn — COMPLETE may use "
                "this when labeled with cite. Not invented from thin air. Prefer RAG when "
                "QFM finds clauses."
            ),
            "policy": "eor_documented_ok_when_corpus_miss",
        }
        if dem is not None and float(cap) > 0:
            out["DC"] = float(dem) / float(cap)
            out["demand_N"] = float(dem)
        return out

    # Path 1b: capacity_N with explicit cite but no source → still RAG passthrough
    if cap is not None and float(cap) > 0 and (not src or src in END_PLATE_RN_OK_SOURCES):
        if src in END_PLATE_RN_REFUSED_SOURCES:
            pass  # fall through to miss
        elif cite or not src:
            out = {
                "found": True,
                "capacity_N": float(cap),
                "Rn": float(cap),
                "limit_state": limit_state,
                "source": src or "rag",
                "resolved_via": "rag" if (not src or src in ("rag", "corpus", "qfm", "live_rag")) else src,
                "cite": cite or default_cite,
                "note": "Capacity from provided RAG / disclosed value — not invented.",
            }
            if dem is not None and float(cap) > 0:
                out["DC"] = float(dem) / float(cap)
                out["demand_N"] = float(dem)
            return out

    refused = []
    if cap is None or (cap is not None and float(cap) <= 0):
        refused.append("capacity_N or Rn (LIVE RAG / QFM preferred; or EOR-documented)")
    if cap is not None and float(cap) > 0 and src and src not in END_PLATE_RN_OK_SOURCES:
        refused.append(
            "source in {%s} (got %r) — refused assumed/silent invent"
            % (", ".join(sorted(END_PLATE_RN_OK_SOURCES)), src)
        )
    if cap is not None and float(cap) > 0 and src in END_PLATE_RN_OK_SOURCES and src not in (
        "rag", "corpus", "qfm", "live_rag", "is800", "is_800",
    ) and not cite:
        refused.append("cite (required with eor_documented Rn)")
    return {
        "found": False,
        "capacity_N": None,
        "Rn": None,
        "source": src or None,
        "resolved_via": "found_false",
        "cite": cite or default_cite,
        "required_inputs": refused or [
            "capacity_N from LIVE RAG / QFM (prefer when clauses found)",
            "OR Rn + cite + source=eor_documented (CFS-style; never invent)",
        ],
        "note": (
            "End-plate/continuity Rn found:false — India corpus often lacks numeric capacity. "
            "Prefer RAG when QFM finds clauses; else supply EOR-documented Rn+cite+"
            "source=eor_documented. Never invent from thin air."
        ),
        "demand_N": float(dem) if dem is not None else None,
        "DC": None,
    }


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
):
    """IS 800 LSD base-plate bending / thickness check (Ch.11 practice).

    Paths (any one closes found:true — never invent t or m):
      1) RAG capacity_bending_N vs P_N, or capacity_bending_Nmm vs M_Nmm
      2) Disclosed plate_t_mm + fy + cantilever m (+ bearing pressure or P/plan)
         → t_req = m * sqrt(3 * w * γ_m0 / fy) from M = w m²/2 per unit width
            and σ_allow = fy/γ_m0 (equivalent to t = sqrt(6 M γ_m0 / fy))

    found:false when RAG/disclosed inputs miss — do not invent plate thickness.
    """
    gm0 = float(gamma_m0 if gamma_m0 is not None else GAMMA_M0_DEFAULT)
    cite = cited or "IS 800:2007 Ch.11 / LSD plate bending (cantilever); γ_m0 Table 5"
    missing = []

    # Path 1: direct RAG capacity
    if capacity_bending_N is not None and P_N is not None and float(capacity_bending_N) > 0:
        dc = float(P_N) / float(capacity_bending_N) if float(capacity_bending_N) > 0 else None
        return {
            "found": True,
            "DC": dc,
            "capacity_N": float(capacity_bending_N),
            "capacity": {"capacity_N": float(capacity_bending_N), "path": "rag_capacity_N"},
            "cite": cite,
            "cited": cite,
            "note": "Base-plate bending D/C from LIVE RAG capacity_N — t not invented.",
        }
    if capacity_bending_Nmm is not None and M_Nmm is not None and float(capacity_bending_Nmm) > 0:
        dc = float(M_Nmm) / float(capacity_bending_Nmm)
        return {
            "found": True,
            "DC": dc,
            "capacity_Nmm": float(capacity_bending_Nmm),
            "capacity": {"capacity_Nmm": float(capacity_bending_Nmm), "path": "rag_capacity_Nmm"},
            "cite": cite,
            "cited": cite,
            "note": "Base-plate bending moment D/C from LIVE RAG — t not invented.",
        }

    # Path 2: thickness from cantilever projection (disclosed / RAG geometry)
    m = cantilever_m_mm
    fy = fy_plate_MPa
    t_prov = plate_t_mm
    w = bearing_pressure_MPa
    if w is None and P_N is not None and plate_B_mm and plate_L_mm:
        area = float(plate_B_mm) * float(plate_L_mm)
        if area > 0:
            w = float(P_N) / area  # N/mm² = MPa
    if m is None:
        missing.append("cantilever_m_mm from RAG / disclosed projection")
    if fy is None:
        missing.append("fy_plate_MPa from RAG / IS 2062")
    if t_prov is None:
        missing.append("plate_t_mm disclosed (do not invent t)")
    if w is None:
        missing.append("bearing_pressure_MPa or P_N with plate_B_mm×plate_L_mm")
    if missing:
        return {
            "found": False,
            "DC": None,
            "capacity": {},
            "t_required_mm": None,
            "t_provided_mm": float(t_prov) if t_prov is not None else None,
            "required_inputs": missing,
            "missing": missing,
            "cite": cite,
            "note": (
                "Base-plate bending found:false — need RAG/disclosed m, fy, t, and bearing "
                "pressure (or P with plate plan). Never invent plate thickness."
            ),
        }

    m = float(m); fy = float(fy); t_prov = float(t_prov); w = float(w)
    # M per unit width = w * m² / 2; t_req = sqrt(6 M γ_m0 / fy) = m * sqrt(3 w γ_m0 / fy)
    t_req = m * math.sqrt(max(3.0 * w * gm0 / fy, 0.0))
    dc = (t_req / t_prov) if t_prov > 0 else None
    return {
        "found": True,
        "DC": dc,
        "t_required_mm": t_req,
        "t_provided_mm": t_prov,
        "m_mm": m,
        "w_MPa": w,
        "fy_plate_MPa": fy,
        "gamma_m0": gm0,
        "capacity": {
            "t_required_mm": t_req,
            "t_provided_mm": t_prov,
            "path": "cantilever_thickness_IS800_LSD",
        },
        "capacity_N": None,
        "cite": cite,
        "cited": cite,
        "note": (
            "t_req = m√(3 w γ_m0/fy) from cantilever plate bending (M=w m²/2). "
            "m/fy/t/w from RAG or disclosed geometry — thickness not invented."
        ),
        "pass": (dc is not None and dc <= 1.0),
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
    """Gusset Whitmore section yield — IS 800 LSD (RAG width or 30° construction).

    Capacity = bw * t * fy / γ_m0. bw from RAG whitmore_width_mm, or
    bw = w_brace + 2 L_wt tan(30°) when both disclosed. Direct capacity_N from RAG OK.
    found:false on miss — no invent.
    """
    gm0 = float(gamma_m0 if gamma_m0 is not None else GAMMA_M0_DEFAULT)
    cite = cite or "IS 800:2007 gusset Whitmore yield (LSD); γ_m0 Table 5"
    if capacity_N is not None and float(capacity_N) > 0:
        return {
            "found": True,
            "capacity_N": float(capacity_N),
            "cite": cite,
            "note": "Whitmore capacity from LIVE RAG — not invented.",
            "path": "rag_capacity_N",
        }
    missing = []
    bw = whitmore_width_mm
    if bw is None and L_wt_mm is not None and w_brace_mm is not None:
        bw = float(w_brace_mm) + 2.0 * float(L_wt_mm) * math.tan(math.radians(30.0))
    if bw is None:
        missing.append("whitmore_width_mm from RAG OR (L_wt_mm + w_brace_mm) disclosed")
    if t_gusset_mm is None:
        missing.append("t_gusset_mm disclosed / RAG")
    if fy_MPa is None:
        missing.append("fy_MPa from RAG / IS 2062")
    if missing:
        return {
            "found": False,
            "capacity_N": None,
            "required_inputs": missing,
            "cite": cite,
            "note": "Whitmore found:false — do not invent gusset t or Whitmore width.",
        }
    cap = float(bw) * float(t_gusset_mm) * float(fy_MPa) / gm0
    return {
        "found": True,
        "capacity_N": cap,
        "whitmore_width_mm": float(bw),
        "t_gusset_mm": float(t_gusset_mm),
        "fy_MPa": float(fy_MPa),
        "gamma_m0": gm0,
        "cite": cite,
        "note": "Whitmore T = bw t fy / γ_m0 — bw/t/fy from RAG or disclosed 30° construction.",
        "path": "whitmore_yield",
    }


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
):
    """Gusset block shear — IS 800:2007 §6.4.1 (RAG capacity or disclosed areas).

    T_db = Avg fy/(√3 γ_m0) + 0.9 Atn fu/γ_m1  (tension rupture + shear yield form).
    found:false without RAG capacity or full geometry — no invent.
    """
    gm0 = float(gamma_m0 if gamma_m0 is not None else GAMMA_M0_DEFAULT)
    gm1 = float(gamma_m1 if gamma_m1 is not None else 1.25)
    cite = cite or "IS 800:2007 §6.4.1 block shear"
    if capacity_N is not None and float(capacity_N) > 0:
        return {
            "found": True,
            "capacity_N": float(capacity_N),
            "cite": cite,
            "note": "Block shear capacity from LIVE RAG — not invented.",
            "path": "rag_capacity_N",
        }
    missing = []
    for name, val in (
        ("Avg_mm2 (gross shear area)", Avg_mm2),
        ("Atn_mm2 (net tension area)", Atn_mm2),
        ("fy_MPa", fy_MPa),
        ("fu_MPa", fu_MPa),
    ):
        if val is None:
            missing.append(name)
    if missing:
        return {
            "found": False,
            "capacity_N": None,
            "required_inputs": missing,
            "cite": cite,
            "note": "Block shear found:false — RAG capacity or Avg/Atn/fy/fu required; no invent.",
        }
    cap = (
        float(Avg_mm2) * float(fy_MPa) / (math.sqrt(3.0) * gm0)
        + 0.9 * float(Atn_mm2) * float(fu_MPa) / gm1
    )
    return {
        "found": True,
        "capacity_N": cap,
        "Avg_mm2": float(Avg_mm2),
        "Atn_mm2": float(Atn_mm2),
        "fy_MPa": float(fy_MPa),
        "fu_MPa": float(fu_MPa),
        "gamma_m0": gm0,
        "gamma_m1": gm1,
        "cite": cite,
        "note": "Block shear T_db per IS 800 §6.4.1 from disclosed areas — not invented.",
        "path": "section_6_4_1",
    }


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
    cite = cite or "IS 800:2007 Ch.11 / §10 column base or splice axial — RAG"
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
    fy_MPa=250.0,
    representative_only=False,
):
    """Optional multi-joint SCWB. Each joint: {columns: [...], beams: [...], id?}.

    If joints is None/empty → found:false with note that representative-joint scope is OK.
    If representative_only and one joint → same as scwb_ratio with scope note.
    """
    cite = "IS 800:2007 §12.11.3.2 ΣMpc/ΣMpb ≥ 1.2"
    if not joints:
        return {
            "found": False,
            "scope": "representative_joint_optional_multi",
            "joints": [],
            "cite": cite,
            "required_inputs": ["joints=[{columns, beams, id?}, ...]"],
            "note": (
                "Multi-joint SCWB optional — provide joints list to refine beyond the "
                "representative joint documented in wave2."
            ),
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
        "note": (
            "Multi-joint SCWB from provided joint list; worst ΣMpc/ΣMpb reported. "
            "H6/H7 remain process stubs."
            if len(results) > 1 else
            "Single/representative joint SCWB (multi-joint optional refinement not required)."
        ),
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
    ``disclosed`` may carry eor_documented geometry (bw/t/fy or Avg/Atn).
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
            for k in ("Avg_mm2", "Atn_mm2", "fy_MPa", "fu_MPa", "gamma_m0", "gamma_m1",
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
        "blocks_complete": False,  # non-blocking residual when found:false (Ex6–15 policy)
        "note": (
            "Whitmore + block shear from RAG / disclosed geometry."
            if (w_found and b_found) else
            "Whitmore/block shear found:false on corpus miss — do not invent bw/t/Avg/Atn; "
            "bolt/weld D/C may still close. Non-blocking residual toward COMPLETE."
        ),
        "policy": "rag_or_disclosed_else_found_false",
    }



def h6_h7_residual_status(cfg=None, pkg=None):
    """Disclosed non-blocking H6/H7 residual status (Wave D).

    H6 = IS 800 Ch. I composite worksheet stubs (studs/camber/wet/I_LB).
    H7 = E250B mill/stock procurement process note.
    Never invent PE stamps or mill availability. Product gates closed; process open.
    """
    cfg = cfg or {}
    pkg = pkg or {}
    composite_declared = bool(
        cfg.get("composite") or cfg.get("composite_floor")
        or (isinstance(pkg.get("composite_design"), dict))
    )
    h6 = {
        "id": "H6",
        "title": "IS 800 Ch. I composite worksheet",
        "found": False,
        "status": "disclose_only_stub",
        "blocking": False,
        "pe_stamp": None,
        "pe_stamp_invented": False,
        "slots": [
            "b_eff", "studs", "partial_composite", "camber", "wet_stage", "I_LB_deflection",
        ],
        "note": (
            "H6 Ch. I composite stubs — leave found:false rather than invent stud/"
            "camber/wet/I_LB. Fill from LIVE IS 800 Ch. I RAG or explicit scope statement."
        ),
        "cite": "IS 800:2007 Ch. I — retrieve LIVE; see COMPOSITE_I3.md",
        "composite_declared": composite_declared,
    }
    if composite_declared and isinstance(pkg.get("composite_design"), dict):
        cd = pkg["composite_design"]
        ws = cd.get("chI_worksheet") if isinstance(cd.get("chI_worksheet"), dict) else {}
        h6["worksheet_status"] = ws.get("status") or cd.get("status") or "stubs"
    elif not composite_declared:
        h6["note"] += " No composite declared — stubs remain available if needed."

    h7 = {
        "id": "H7",
        "title": "E250B mill / stock procurement",
        "found": False,
        "status": "process_open",
        "blocking": False,
        "pe_stamp": None,
        "pe_stamp_invented": False,
        "note": (
            "H7 E250B mill/stock procurement is a process residual — do not invent "
            "availability or PE stamp. Confirm mill cert before seal when E250B specified."
        ),
        "cite": "IS 2062 E250 / project procurement — process note (not a product invent)",
    }
    return {
        "H6": h6,
        "H7": h7,
        "blocking": False,
        "status": "disclose_only_residuals",
        "note": (
            "H6/H7 are disclosed non-blocking residuals (Wave D). Product COMPLETE gates "
            "closed without inventing PE stamps or mill stock."
        ),
        "policy": "disclose_only_no_pe_invent",
    }
