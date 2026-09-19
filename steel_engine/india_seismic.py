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
        "clause": "Table 6 (i) + Amendment 2",
        "text": (
            "A soft storey is a storey whose lateral stiffness is less than that of the storey above. "
            "In a building with stiffness irregularity: (1) Dynamic Analysis shall be employed to "
            "capture the actual distribution of lateral stiffness along the height; and (2) the "
            "inter-storey drift shall be limited to 0.2 percent in that storey and all storeys below "
            "with stiffness irregularity. (URM-infill SPD >20% → model infills; see also 7.9.)"
        ),
        "stiffness_ratio_trigger": 1.0,  # Ki < Ki_above  ⇒ soft (Amd2 wording; no 0.7 factor)
        "soft_storey_drift_limit": 0.002,
        "requires_dynamic_analysis": True,
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



def storey_stiffness_soft_flags(storey_stiffness: list[float] | None) -> dict:
    """Classify soft storeys from lateral stiffness samples (force/displacement per storey).

    IS 1893 Table 6 (i) Amd2: soft when Ki < K(i+1) (storey above). Returns per-storey flags
    and the governing drift limit (0.002 on soft storeys and all below).

    storey_stiffness: list length = n_storeys, index 0 = lowest storey. Units arbitrary but
    consistent (e.g. kip/in from Vb_storey / drift_storey). If None/empty → found data missing.
    """
    out = {
        "found": True,
        "standard": "IS_1893_Part_1_2016 Table 6 (i) Amd2",
        "asce_Ax": {"found": False, "note": "No Ax amplification in IS 1893; use cl.7.8.2 eccentricity."},
        "soft_storeys": [],
        "drift_limit_by_storey": [],
        "requires_dynamic_analysis": False,
        "note": None,
    }
    if not storey_stiffness:
        out["note"] = (
            "No storey_stiffness[] provided — height-jump proxy in classify_vertical_irregularities "
            "is advisory only; agent must supply Ki from analysis (e.g. storey shear / storey drift)."
        )
        return out
    K = [float(x) for x in storey_stiffness]
    n = len(K)
    soft = [False] * n
    for i in range(n - 1):
        # i is below i+1; soft if Ki < K(above)
        if K[i] < K[i + 1]:
            soft[i] = True
    # Once a soft storey exists, Amd2 limits drift to 0.002 in that storey AND all below
    lim = []
    below_soft = False
    # walk from top: mark cascade downward
    cascade = [False] * n
    seen = False
    for i in range(n - 1, -1, -1):
        if soft[i]:
            seen = True
        if seen and (soft[i] or any(soft[j] for j in range(i, n))):
            # all storeys at or below any soft storey
            pass
    for i in range(n):
        if any(soft[j] for j in range(i, n)):  # this storey or any above is soft → 0.002 if at/below soft
            # Amd2: "in that storey and all storeys below"
            pass
    # Correct cascade: for each soft storey s, storeys 0..s get 0.002
    limit = [CLAUSES["storey_drift_limit"]["limit_ratio"]] * n
    for s, is_soft in enumerate(soft):
        if is_soft:
            for i in range(0, s + 1):
                limit[i] = CLAUSES["soft_storey"]["soft_storey_drift_limit"]
    out["soft_storeys"] = soft
    out["drift_limit_by_storey"] = limit
    out["requires_dynamic_analysis"] = any(soft)
    out["soft_storey_indices"] = [i for i, f in enumerate(soft) if f]
    return out


def drift_allowable_for_storey(cfg, storey_index: int = 0) -> float:
    """Allowable drift ratio for a storey, applying soft-storey 0.002 when flagged."""
    base, _ = drift_allowable(cfg)
    flags = cfg.get("_soft_storey_flags") or {}
    lims = flags.get("drift_limit_by_storey")
    if lims and 0 <= storey_index < len(lims):
        return float(lims[storey_index])
    # cfg may list soft storey indices directly
    soft_idx = cfg.get("soft_storey_indices") or []
    if soft_idx:
        # storeys at or below any soft storey → 0.002
        max_soft = max(int(i) for i in soft_idx)
        if storey_index <= max_soft:
            return float(CLAUSES["soft_storey"]["soft_storey_drift_limit"])
    return base


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
        "note": (
            "True soft-storey is stiffness-based (Table 6(i) Amd2: Ki < K_above). "
            "Call storey_stiffness_soft_flags(Ki) after analysis; height jump / cfg flag is advisory only. "
            "When soft: dynamic analysis required; inter-storey drift ≤ 0.002 in soft storey and below. "
            "ASCE Ax amplification: found:false — use cl.7.8.2 design eccentricity."
        ),
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


# ---------------------------------------------------------------------------
# IS 1893 (Part 1) : 2016 §7.6.2 — approximate fundamental period Ta
# ---------------------------------------------------------------------------
# (a) bare RC MRF:   Ta = 0.075 h^0.75
# (b) bare steel MRF: Ta = 0.085 h^0.75
# (c) all other buildings: Ta = 0.09 h / sqrt(d)
# Fail closed when a non-MRF system (SCBF/CBF/EBF/…) is paired with an MRF formula.

class TaFormulaError(ValueError):
    """Non-MRF system paired with MRF Ta formula (IS 1893 §7.6.2 fail-closed)."""


_MRF_TOKENS = (
    "smrf", "omrf", "imrf", "mrf", "moment frame", "moment-frame", "moment_frame",
    "bare mrf", "steel mrf", "rc mrf", "rcc mrf", "smf", "omf", "imf",
    "special moment", "intermediate moment", "ordinary moment",
)
_NON_MRF_TOKENS = (
    "scbf", "ocbf", "cbf", "ebf", "brbf", "braced", "sbf", "concentric",
    "eccentric", "buckling restrained", "shear wall", "dual", "spsw",
    "frame-shear", "wall frame", "infill",
)


def is_bare_mrf_system(system) -> bool:
    """True only when the SFRS is a bare moment frame (IS 1893 §7.6.2 a/b)."""
    s = str(system or "").strip().lower()
    if not s:
        return False
    if any(t in s for t in _NON_MRF_TOKENS):
        return False
    return any(t in s for t in _MRF_TOKENS)


def _looks_like_mrf_formula(formula: str) -> bool:
    f = str(formula or "").lower().replace(" ", "")
    if not f:
        return False
    # Explicit all-other / 0.09 h/√d wins even if "0.085" appears in a note
    if "0.09" in f and ("sqrt" in f or "√" in formula or "/d" in f or "√d" in formula or "h/" in f):
        return False
    if "allother" in f or "all-other" in f or "§7.6.2(c)" in formula.lower() or "7.6.2(c)" in formula.lower():
        return False
    if "0.085" in f or "0.075" in f:
        return True
    if ("h^0.75" in f or "h**0.75" in f or "h0.75" in f) and "0.09" not in f:
        return True
    return False


def approximate_Ta(h_m: float, d_m: float | None = None, system: str | None = None,
                   formula: str | None = None, material: str | None = None) -> dict:
    """Compute IS 1893 §7.6.2 Ta (seconds). Heights/base d in metres.

    If ``formula`` is supplied it must match the system class; non-MRF + MRF
    formula raises ``TaFormulaError`` (fail closed). When formula is omitted the
    system selects (a)/(b)/(c) automatically.
    """
    h = float(h_m)
    if h <= 0:
        raise ValueError("h_m must be positive (building height in metres)")
    sys = system or ""
    bare_mrf = is_bare_mrf_system(sys)
    mat = str(material or "").lower()
    if bare_mrf and ("steel" in mat or "steel" in str(sys).lower()):
        kind = "steel_mrf"
        coeff = 0.085
        clause = "7.6.2(b)"
        ta = coeff * (h ** 0.75)
        used = "0.085 h^0.75"
    elif bare_mrf:
        kind = "rc_mrf"
        coeff = 0.075
        clause = "7.6.2(a)"
        ta = coeff * (h ** 0.75)
        used = "0.075 h^0.75"
    else:
        kind = "all_other"
        clause = "7.6.2(c)"
        if d_m is None or float(d_m) <= 0:
            raise ValueError("d_m (base dimension in metres along vibration) required for §7.6.2(c)")
        ta = 0.09 * h / (float(d_m) ** 0.5)
        used = "0.09 h/√d"

    if formula is not None and _looks_like_mrf_formula(formula) and not bare_mrf:
        raise TaFormulaError(
            "IS 1893 §7.6.2 fail-closed: system %r is not a bare MRF but Ta formula %r "
            "looks like MRF 0.075/0.085 h^0.75 — use 0.09 h/√d (§7.6.2(c) all other buildings)."
            % (sys, formula)
        )

    return {
        "found": True,
        "standard": "IS_1893_Part_1_2016",
        "clause": clause,
        "kind": kind,
        "Ta_s": float(ta),
        "formula": used,
        "h_m": h,
        "d_m": None if d_m is None else float(d_m),
        "system": sys,
        "bare_mrf": bare_mrf,
    }


def validate_Ta_for_system(cfg, plan: dict | None = None) -> list:
    """Fail-closed findings when non-MRF jobs use an MRF Ta formula.

    Inspects cfg['system'] / load_plan.seismic_summary Ta_formula / Ta_s notes.
    Returns list of (level, message). Missing Ta is not an ERROR (agent may still
    be building the plan); wrong formula for the system is ERROR.
    """
    out = []
    if not isinstance(cfg, dict):
        return out
    plan = plan if plan is not None else (cfg.get("load_plan") or {})
    if not isinstance(plan, dict):
        plan = {}
    ss = plan.get("seismic_summary") or plan.get("seis_summary") or {}
    if not isinstance(ss, dict):
        ss = {}
    system = (
        cfg.get("system")
        or ss.get("system")
        or (cfg.get("seis") or {}).get("system")
        or ""
    )
    formula = (
        ss.get("Ta_formula")
        or ss.get("Ta_formula_note")
        or ss.get("formula")
        or cfg.get("Ta_formula")
        or ""
    )
    if not formula and not ss:
        return out  # nothing to check yet
    if formula and _looks_like_mrf_formula(str(formula)) and not is_bare_mrf_system(system):
        out.append((
            "ERROR",
            "IS 1893 §7.6.2 Ta fail-closed: system %r is not a bare MRF but load_plan "
            "uses MRF Ta formula %r. Use §7.6.2(c) Ta=0.09 h/√d (all other buildings). "
            "Do not silently keep 0.085 h^0.75 / 0.075 h^0.75 for SCBF/CBF/EBF/dual/wall systems."
            % (system or "(undeclared)", formula),
        ))
        return out
    # If system is clearly non-MRF and Ta present without formula, require formula citation
    if system and not is_bare_mrf_system(system) and ss.get("Ta_s") is not None and not formula:
        out.append((
            "WARN",
            "load_plan.seismic_summary has Ta_s but no Ta_formula — record §7.6.2(c) "
            "'0.09 h/√d' (or MRF clause if truly bare MRF) so the fail-closed gate can verify.",
        ))
    return out



def mass_irregularity_screen_note(W_by_floor_kN=None, *, zone=None, ratio_trigger=1.5):
    """Document IS 1893 Table 6(ii) mass irregularity screen (mezzanine / partial floors).

    Flags when any floor seismic weight > 150% of the floor below. Returns found screen
    result + Zone applicability note. Does not invent a dynamic-analysis mandate beyond
    what the clause/table requires — agent/policy decides RS vs ELF follow-up.
    """
    clause = CLAUSES.get("mass_irregularity") or {}
    trigger = float(clause.get("ratio_trigger") or ratio_trigger)
    weights = [float(w) for w in (W_by_floor_kN or []) if w is not None]
    ratios = []
    flagged = []
    for i in range(1, len(weights)):
        below = weights[i - 1]
        if below <= 0:
            continue
        r = weights[i] / below
        ratios.append({"floor_above_1based": i + 1, "ratio": r, "W_above": weights[i], "W_below": below})
        if r > trigger:
            flagged.append(ratios[-1])
    irregular = len(flagged) > 0
    zone_s = str(zone or "").upper().replace("ZONE", "").strip()
    return {
        "found": True if weights else False,
        "irregular": irregular if weights else None,
        "ratio_trigger": trigger,
        "ratios": ratios,
        "flagged": flagged,
        "cite": clause.get("clause") or "IS 1893 Table 6 (ii)",
        "clause_text": clause.get("text"),
        "zone": zone,
        "note": (
            "Mass irregularity Table 6(ii): seismic weight of any floor > 150%% of floor below. "
            "Mezzanine / partial-footprint floors often trigger. Zone %s — document screen; "
            "dynamic analysis / RS follow-up is a project-policy choice when irregular "
            "(do not invent a mandatory RS path beyond code). ELF + disclosure OK when "
            "policy accepts and drift/strength gates pass."
            % (zone_s or "(undeclared)")
        ),
        "required_inputs": [] if weights else ["W_by_floor_kN list (seismic weight per floor)"],
    }

# --- complete-gap wave2: R / Ω0 provenance (re-export) -------------------------
try:
    from india_seismic_gates import (  # noqa: E402
        resolve_R,
        resolve_Omega0,
        validate_R,
        complete_allowed,
        R_is_proxy,
        omega0_blocks_complete,
        design_status,
        R_OK_SOURCES,
        R_PROXY_SOURCES,
    )
except ImportError:  # pragma: no cover
    pass

