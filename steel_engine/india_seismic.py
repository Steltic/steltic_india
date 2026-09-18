"""IS 1893 (Part 1) : 2016 drift and irregularity helpers for steltic_india.

Clause text was checked against /workspace/INDIA_STEEL/pdfs/IS_1893_Part_1_2016_Amd2_Reff2021.pdf
(and the India RAG corpus stem IS_1893_Part_1_2016). Do not invent numerical limits —
missing items are explicit TODO with found:false.
"""
from __future__ import annotations

# --- authoritative clause anchors (found:true) ---------------------------------
CLAUSES = {
    "storey_drift_limit": {
        "found": True,
        "stem": "IS_1893_Part_1_2016",
        "clause": "7.11.1.1",
        "text": (
            "Storey drift in any storey shall not exceed 0.004 times the storey height, "
            "under the action of design base of shear VB with no load factors mentioned in 6.3, "
            "that is, with partial safety factor for all loads taken as 1.0."
        ),
        "limit_ratio": 0.004,
    },
    "drift_no_dynamic_scale": {
        "found": True,
        "stem": "IS_1893_Part_1_2016",
        "clause": "7.11.1.2",
        "text": (
            "Displacement estimates obtained from dynamic analysis methods shall not be "
            "scaled as given in 7.7.3."
        ),
    },
    "plan_irregularities_table": {
        "found": True,
        "stem": "IS_1893_Part_1_2016",
        "clause": "Table 5",
        "cite": "7.1 / Table 5",
        "types": [
            "Torsional Irregularity",
            "Re-entrant Corners",
            "Floor Slabs having Excessive Cut-Outs or Openings",
            "Out-of-Plane Offsets in Vertical Elements",
            "Non-Parallel Lateral Force System",
        ],
    },
    "vertical_irregularities_table": {
        "found": True,
        "stem": "IS_1893_Part_1_2016",
        "clause": "Table 6",
        "cite": "7.1 / Table 6",
        "types": [
            "Stiffness Irregularity (Soft Storey)",
            "Mass Irregularity",
            "Vertical Geometric Irregularity",
            "In-Plane Discontinuity in Vertical Elements Resisting Lateral Force",
            "Strength Irregularity (Weak Storey)",
            "Floating or Stub Columns",
            "Irregular Modes of Oscillation in Two Principal Plan Directions",
        ],
    },
    "torsional_irregularity_trigger": {
        "found": True,
        "stem": "IS_1893_Part_1_2016",
        "clause": "Table 5 (i)",
        "text": (
            "A building is said to be torsionally irregular, when the maximum horizontal "
            "displacement of any floor in the direction of the lateral force at one end of the "
            "floor is more than 1.5 times its minimum horizontal displacement at the far end of "
            "the same floor in that direction."
        ),
        "ratio_trigger": 1.5,
        # follow-on 1.5–2.0 and >2.0 configuration/analysis rules: see Table 5 concluded
    },
    "reentrant_corner": {
        "found": True,
        "stem": "IS_1893_Part_1_2016",
        "clause": "Table 5 (ii)",
        "text": (
            "A building is said to have a re-entrant corner in any plan direction, when its "
            "structural configuration in plan has a projection of size greater than 15 percent "
            "of its overall plan dimension in that direction."
        ),
        "projection_ratio": 0.15,
    },
    "soft_storey": {
        "found": True,
        "stem": "IS_1893_Part_1_2016",
        "clause": "Table 6 (i)",
        "text": (
            "A soft storey is a storey whose lateral stiffness is less than that of the storey above."
        ),
    },
    "mass_irregularity": {
        "found": True,
        "stem": "IS_1893_Part_1_2016",
        "clause": "Table 6 (ii)",
        "text": (
            "Mass irregularity shall be considered to exist, when the seismic weight (as per 7.7) "
            "of any floor is more than 150 percent of that of the floors below."
        ),
        "ratio_trigger": 1.5,
    },
    "design_eccentricity": {
        "found": True,
        "stem": "IS_1893_Part_1_2016",
        "clause": "7.8.2",
        "text": (
            "edi = 1.5*esi + 0.05*bi  OR  esi - 0.05*bi, whichever gives the more severe effect "
            "on lateral force resisting elements."
        ),
    },
}

# Explicit gaps — do not fabricate ASCE analogues
TODO = [
    {
        "id": "asce_Cd_Ie_drift_amplification",
        "found": False,
        "note": (
            "IS 1893 7.11.1.1 checks storey drift under VB with γ=1.0; it does NOT use ASCE 7 "
            "δ = Cd*δe/Ie. India path must NOT apply Cd/Ie amplification to the drift gate."
        ),
    },
    {
        "id": "asce_table_12_12_1_risk_category_limits",
        "found": False,
        "note": "No IS 1893 equivalent to ASCE Table 12.12-1 risk-category drift limits; use 0.004 h.",
    },
    {
        "id": "asce_12_12_1_1_rho_drift_reduction",
        "found": False,
        "note": "No IS 1893 ρ divisor on drift limit for moment-frame-only systems.",
    },
    {
        "id": "tir_ax_amplification_asce_12_8_4_3",
        "found": False,
        "note": (
            "ASCE Ax = (δmax/(1.2 δavg))^2 does not appear in IS 1893. Use 7.8.2 design "
            "eccentricity (1.5 esi ± 0.05 bi) instead; do not invent an Ax factor."
        ),
    },
    {
        "id": "vertical_geometric_125pct_automation",
        "found": True,
        "clause": "Table 6 (iii)",
        "note": (
            "Limit (horizontal dimension of LFRS in a storey > 125% of storey below) is known, "
            "but automated detection from cfg footprint is only a geometric proxy — agent must confirm."
        ),
    },
]


def drift_allowable(cfg) -> tuple[float, bool]:
    """Return (allowable storey drift ratio, rho_applied).

    Default 0.004 per IS 1893 Part 1:2016 cl.7.11.1.1. cfg['drift_limit'] may override
    when the agent has RAG-justified a stricter project/special limit (e.g. 0.002 for
    URM-infill storeys per Table 6 notes). rho_applied is always False (no ASCE ρ rule).
    """
    dl = cfg.get("drift_limit")
    if dl is None or dl == "":
        dl = CLAUSES["storey_drift_limit"]["limit_ratio"]
    return float(dl), False


def design_story_drifts(elastic_drifts, cfg) -> list[float]:
    """Map analysis interstorey drifts to the IS 1893 design-drift check values.

    Under 7.11.1.1 the check uses drifts from design base shear VB with load factors = 1.0.
    When the analysis already applied design seismic forces (Ah with R), elastic storey
    drifts are the design drifts — do NOT multiply by Cd/Ie.

    If cfg['load_plan']['seismic_summary'] supplies an explicit drift_amplification factor
    retrieved from RAG, that factor is applied; otherwise factor = 1.0.
    """
    factor = 1.0
    lp = cfg.get("load_plan") or {}
    summ = lp.get("seismic_summary") or {}
    if summ.get("drift_amplification") is not None:
        factor = float(summ["drift_amplification"])
    # Honor explicit cfg override only when agent set it from RAG
    if cfg.get("is1893_drift_factor") is not None:
        factor = float(cfg["is1893_drift_factor"])
    return [float(d) * factor for d in elastic_drifts]


def max_design_drift(elastic_drifts, cfg) -> float:
    vals = design_story_drifts(elastic_drifts, cfg)
    return max(abs(v) for v in vals) if vals else 0.0


def classify_plan_irregularities(cfg, footprint_flags: dict | None = None) -> dict:
    """IS 1893 Table 5 screen from footprint flags (+ optional torsion ratio).

    footprint_flags keys (from engine3d.plan_irregularities geometric proxy):
      reentrant, setback, nonparallel, nonrect
    Optional cfg['torsion_ratio'] or cfg['_tir_screen'] = δmax/δmin for Table 5(i).
    """
    flags = dict(footprint_flags or {})
    out = {
        "standard": "IS_1893_Part_1_2016",
        "cite": "Table 5 / cl.7.1",
        "items": [],
        "todos": [t for t in TODO if not t.get("found", True)],
    }
    tir = cfg.get("torsion_ratio")
    if tir is None:
        tir = cfg.get("_tir_screen")
    if tir is not None:
        tir = float(tir)
        trig = CLAUSES["torsional_irregularity_trigger"]["ratio_trigger"]
        out["items"].append({
            "type": "Torsional Irregularity",
            "triggered": tir > trig,
            "ratio": tir,
            "trigger": trig,
            "cite": "IS 1893 Table 5 (i)",
            "found": True,
        })
    else:
        out["items"].append({
            "type": "Torsional Irregularity",
            "triggered": None,
            "cite": "IS 1893 Table 5 (i)",
            "found": True,
            "note": "No δmax/δmin ratio in cfg — agent must compute from accidental-torsion analysis.",
        })

    out["items"].append({
        "type": "Re-entrant Corners",
        "triggered": bool(flags.get("reentrant")),
        "cite": "IS 1893 Table 5 (ii)",
        "trigger": "projection > 15% of plan dimension",
        "found": True,
        "note": "Geometric proxy from footprint non-convexity; confirm projection ratio vs 15%.",
    })
    out["items"].append({
        "type": "Non-Parallel Lateral Force System",
        "triggered": bool(flags.get("nonparallel")),
        "cite": "IS 1893 Table 5 (v)",
        "found": True,
    })
    # Cut-outs / out-of-plane offsets: not inferred from grid alone
    out["items"].append({
        "type": "Floor Slabs having Excessive Cut-Outs or Openings",
        "triggered": None,
        "cite": "IS 1893 Table 5 (iii)",
        "found": True,
        "note": "TODO agent/RAG: opening area vs 50% floor slab — not auto-detected from cfg grid.",
    })
    out["items"].append({
        "type": "Out-of-Plane Offsets in Vertical Elements",
        "triggered": None,
        "cite": "IS 1893 Table 5 (iv)",
        "found": True,
        "note": "TODO agent: declare if LFRS offsets exist; Zones III–V have 0.2% drift / specialist rules.",
    })
    return out


def classify_vertical_irregularities(cfg) -> dict:
    """IS 1893 Table 6 screen — stiffness/mass/geometry proxies only where cfg allows."""
    out = {
        "standard": "IS_1893_Part_1_2016",
        "cite": "Table 6 / cl.7.1",
        "items": [],
    }
    heights = cfg.get("heights") or []
    soft = bool(cfg.get("softstorey_check"))
    # Height jump proxy: first storey much taller than typical
    if len(heights) >= 2 and heights[0] > 1.3 * (sum(heights[1:]) / max(1, len(heights) - 1)):
        soft = True
    out["items"].append({
        "type": "Stiffness Irregularity (Soft Storey)",
        "triggered": soft,
        "cite": "IS 1893 Table 6 (i)",
        "found": True,
        "note": "True soft-storey is stiffness-based; height jump / cfg flag is advisory only.",
    })

    mass_irreg = False
    extra = cfg.get("extra_mass_floors") or {}
    if extra:
        mass_irreg = True  # agent must verify 150% rule with seismic weights
    out["items"].append({
        "type": "Mass Irregularity",
        "triggered": mass_irreg if extra else None,
        "cite": "IS 1893 Table 6 (ii)",
        "trigger": "floor seismic weight > 150% of floor below",
        "found": True,
        "note": "cfg['extra_mass_floors'] present ⇒ check 150% rule via RAG/weights; not auto-proven.",
    })

    setback = False
    # geometric setback via plan callable name or flag from plan_irregularities
    if cfg.get("_vertical_setback") or cfg.get("plan") is not None:
        # plan=setback is a USA archetype hint; treat as possible vertical geometric irregularity
        setback = True
    out["items"].append({
        "type": "Vertical Geometric Irregularity",
        "triggered": setback if cfg.get("_vertical_setback") is not None else None,
        "cite": "IS 1893 Table 6 (iii)",
        "trigger": "LFRS horizontal dimension > 125% of storey below",
        "found": True,
    })
    for t, cite in [
        ("In-Plane Discontinuity in Vertical Elements Resisting Lateral Force", "Table 6 (iv)"),
        ("Strength Irregularity (Weak Storey)", "Table 6 (v)"),
        ("Floating or Stub Columns", "Table 6 (vi)"),
        ("Irregular Modes of Oscillation in Two Principal Plan Directions", "Table 6 (vii)"),
    ]:
        out["items"].append({
            "type": t, "triggered": None, "cite": f"IS 1893 {cite}", "found": True,
            "note": "Not auto-screened — agent must classify from analysis/RAG.",
        })
    return out


def drift_limit_label(cfg) -> str:
    dl, _ = drift_allowable(cfg)
    return (
        f"{dl*100:.2f}% of storey height (IS 1893 Part 1:2016 cl.7.11.1.1; "
        f"VB with γ=1.0; no Cd/Ie amplification)"
    )
