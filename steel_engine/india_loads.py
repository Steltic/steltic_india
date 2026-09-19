"""
india_loads.py — India (IS/BIS) load path: LIVE RAG retrieval, not hardcoded formulas.

CRITICAL (steltic_india):
  USA steltic embeds ASCE 7-22 wind/seismic/LRFD combo math in the engine.
  India MUST NOT replace that with a permanent Python port of IS 875 / IS 1893.
  Every job the agent RAG-queries IS 875 Parts 1–5 and IS 1893 Part 1:2016 (same
  pattern as design RAG for IS 800), then writes the retrieved combination factors
  and story forces into cfg['load_plan']. This module only VALIDATES that plan and
  turns it into the (label, fD, fL, fLr, lateral, col_only) tuples the demand
  envelope already understands.

Schema (cfg['load_plan']):
  {
    "jurisdiction": "india",
    "partial_factors_cite": "IS 800:2007 Table 4 (or retrieved clause)",
    "retrieval": [   # REQUIRED — evidence of live RAG this job
      {"stem": "IS_875_Part_3_2015", "query": "...", "found": true,
       "cite": "§6.3 / Table …", "collection": "engineering_standards_IS875_P3"},
      {"stem": "IS_1893_Part_1_2016", "query": "...", "found": true, "cite": "…"},
      ...
    ],
    "combinations": [   # REQUIRED — at least gravity; lateral when EQ/WL apply
      {"label": "1.5DL+1.5LL", "fD": 1.5, "fL": 1.5, "fLr": 0.0,
       "lateral": {}, "col_only": false, "cite": "IS 800:2007 Table 4"},
      {"label": "1.2DL+1.2LL+1.2EQ_X", "fD": 1.2, "fL": 1.2, "fLr": 0.0,
       "lateral": {"1": [Fx, Fy, Mz], ...}, "col_only": false,
       "cite": "IS 800 Table 4 + IS 1893 …"},
      ...
    ],
    "notes": "optional free text"
  }

lateral values: kip forces/moments at each story index (str or int keys), matching
the existing design_pipeline / design_post run_case contract (engine remains kip+inch).
"""
from __future__ import annotations

# Canonical India load / seismic stems the agent must hit via RAG every job.
LOAD_STEMS = (
    "IS_875_Part_1_2026",   # dead loads
    "IS_875_Part_2_1987",   # imposed / live
    "IS_875_Part_3_2015",   # wind
    "IS_875_Part_4_1987",   # snow
    "IS_875_Part_5_1987",   # special loads / combinations notes
    "IS_1893_Part_1_2016",  # seismic
)

# Design stems (not loads, but listed for contract / retrieval plans).
DESIGN_STEMS = (
    "IS_800_2007",
    "IS_808_2021",
    "IS_816_1969",
    "IS_9595_1996",
    "IS_4000_1992",
    "IS_1161_2014",
    "IS_2062_Part_1_2025",
)

# Agent-facing RAG collection names → preferred document stem.
COLLECTION_TO_STEM = {
    "engineering_standards_IS800": "IS_800_2007",
    "engineering_standards_IS808": "IS_808_2021",
    "engineering_standards_IS816": "IS_816_1969",
    "engineering_standards_IS9595": "IS_9595_1996",
    "engineering_standards_IS4000": "IS_4000_1992",
    "engineering_standards_IS1161": "IS_1161_2014",
    "engineering_standards_IS2062": "IS_2062_Part_1_2025",
    "engineering_standards_IS875_P1": "IS_875_Part_1_2026",
    "engineering_standards_IS875_P2": "IS_875_Part_2_1987",
    "engineering_standards_IS875_P3": "IS_875_Part_3_2015",
    "engineering_standards_IS875_P4": "IS_875_Part_4_1987",
    "engineering_standards_IS875_P5": "IS_875_Part_5_1987",
    "engineering_standards_IS1893": "IS_1893_Part_1_2016",
    # short aliases
    "IS800": "IS_800_2007",
    "IS875_P3": "IS_875_Part_3_2015",
    "IS1893": "IS_1893_Part_1_2016",
}

STEM_TO_COLLECTION = {v: k for k, v in COLLECTION_TO_STEM.items()
                      if k.startswith("engineering_standards_")}


class LoadPlanError(ValueError):
    """cfg['load_plan'] missing, incomplete, or not RAG-backed."""


def _as_lateral(raw):
    """Normalize lateral story map to {int: (fx, fy, mz)}."""
    if not raw:
        return {}
    out = {}
    for k, v in dict(raw).items():
        ki = int(k)
        if isinstance(v, dict):
            out[ki] = (float(v.get("fx", 0)), float(v.get("fy", 0)), float(v.get("mz", 0)))
        else:
            seq = list(v)
            fx = float(seq[0]) if len(seq) > 0 else 0.0
            fy = float(seq[1]) if len(seq) > 1 else 0.0
            mz = float(seq[2]) if len(seq) > 2 else 0.0
            out[ki] = (fx, fy, mz)
    return out



def _retrieval_hits(plan, pred):
    """Return retrieval entries matching pred(stem_lower, hit)."""
    out = []
    for hit in (plan.get("retrieval") or []):
        if not isinstance(hit, dict):
            continue
        stem = str(hit.get("stem") or hit.get("doc") or "").lower()
        if pred(stem, hit):
            out.append(hit)
    return out


def _is_part3_stem(stem: str) -> bool:
    s = stem.lower()
    return (
        "875_part_3" in s or "875_p3" in s or "is875_p3" in s
        or "is_875_part_3" in s or "part3" in s and "875" in s
        or "part_3" in s and "875" in s
    )


def _no_wind_flag(cfg, plan):
    """Return (active: bool, reason: str|None)."""
    for src in (plan, cfg):
        if not isinstance(src, dict):
            continue
        for key in ("no_wind", "omit_wind", "wind_not_applicable", "wind_omitted"):
            val = src.get(key)
            if val is True:
                reason = (
                    src.get("no_wind_reason")
                    or src.get("omit_wind_reason")
                    or src.get("wind_omit_reason")
                    or ""
                )
                return True, str(reason).strip() or None
            if isinstance(val, str) and val.strip():
                return True, val.strip()
            if isinstance(val, dict):
                reason = str(val.get("reason") or val.get("note") or "").strip()
                return True, reason or None
    return False, None


def _has_wind_lateral_evidence(plan) -> bool:
    """True when wind story forces or WL combinations are present (not invented Ka/Cpe)."""
    if not isinstance(plan, dict):
        return False
    ws = plan.get("wind_summary") or plan.get("wind") or {}
    if isinstance(ws, dict) and ws:
        # Numeric base shear / story forces count as evidence; params-only without forces do not
        for k in ("VB_x_kN", "VB_y_kN", "VB_x", "VB_y", "Qi_x_kN", "Qi_y_kN", "story_forces", "Fx", "Fy"):
            if ws.get(k) not in (None, "", [], {}):
                return True
        if ws.get("applied") is True or ws.get("laterals_applied") is True:
            return True
    sf = plan.get("story_forces") or {}
    if isinstance(sf, dict):
        for name, forces in sf.items():
            n = str(name).lower()
            if any(t in n for t in ("wind", "wl", "w_x", "w_y", "wx", "wy")) and forces:
                return True
    for c in (plan.get("combinations") or []):
        if not isinstance(c, dict):
            continue
        lab = str(c.get("label") or "").upper()
        cite = str(c.get("cite") or "").upper()
        if not any(t in lab or t in cite for t in ("WL", "WIND", "+W", " W", "W+", "W-", "W_X", "W_Y")):
            # also accept bare W as load letter when combined with DL
            if "W" not in lab.replace("SW", "").replace("OWN", ""):
                continue
        lat = c.get("lateral") or {}
        ref = c.get("lateral_ref")
        if lat or ref:
            return True
    return False


def validate_wind_gate(cfg, plan: dict | None = None) -> list:
    """S5/H2: require wind retrieval evidence OR explicit found:false + documented no-wind.

    Never allow silent omission of wind laterals. found:false alone is honest but
    insufficient without ``no_wind`` + reason — do not invent Ka/Cpe.
    """
    out = []
    if not isinstance(cfg, dict):
        return out
    plan = plan if plan is not None else (cfg.get("load_plan") or {})
    if not isinstance(plan, dict) or not plan:
        return out

    no_wind, reason = _no_wind_flag(cfg, plan)
    part3 = _retrieval_hits(plan, lambda stem, _h: _is_part3_stem(stem))
    part3_found = [h for h in part3 if h.get("found") is True]
    part3_false = [h for h in part3 if h.get("found") is False]
    has_laterals = _has_wind_lateral_evidence(plan)

    if no_wind:
        if not reason:
            out.append((
                "ERROR",
                "load_plan declares no_wind/omit_wind but no reason is documented — "
                "set no_wind to a non-empty reason string (or no_wind_reason). "
                "found:false on Part 3 is honest; inventing Ka/Cpe is not.",
            ))
        elif not part3 and not part3_false:
            out.append((
                "WARN",
                "no_wind documented (%s) but load_plan.retrieval has no IS 875 Part 3 hit — "
                "prefer an explicit found:false Part 3 retrieval for provenance." % reason,
            ))
        return out

    # Wind is expected for a normal building job
    if not part3:
        out.append((
            "ERROR",
            "Wind gate (S5/H2): load_plan.retrieval has no IS 875 Part 3 stem — "
            "RAG-query Part 3 for Vb/k1/k2/Cp OR set load_plan.no_wind with a documented "
            "reason. Never silently omit wind laterals before design_and_report.",
        ))
        return out

    if not part3_found and part3_false:
        out.append((
            "ERROR",
            "Wind gate (S5/H2): IS 875 Part 3 retrieval is found:false and no_wind is not "
            "set — do not invent Ka/Cpe or silently drop wind laterals. Either retry RAG "
            "until found:true and apply wind forces, or set load_plan.no_wind='<reason>'.",
        ))
        return out

    if part3_found and not has_laterals:
        out.append((
            "ERROR",
            "Wind gate (S5/H2): Part 3 retrieved (found:true) but no wind laterals / "
            "wind_summary forces / WL combinations are present — never silently omit wind "
            "laterals. Write wind story forces into load_plan or set no_wind with reason.",
        ))
    return out


def validate_load_plan(cfg) -> list:
    """Return a list of (level, message) findings. level in ERROR/WARN/INFO.

    ERRORs mean the demand envelope must not invent loads — agent must RAG-fill load_plan.
    """
    out = []
    plan = cfg.get("load_plan") if isinstance(cfg, dict) else None
    if not plan or not isinstance(plan, dict):
        out.append(("ERROR",
                    "cfg['load_plan'] missing. India jobs MUST RAG-query IS 875 Parts 1–5 and "
                    "IS 1893 Part 1:2016 LIVE this job, then write retrieved combination factors "
                    "and story forces into cfg['load_plan'] (see india_loads.py). The engine will "
                    "NOT compute ASCE 7 or hardcode IS load formulas."))
        return out

    if str(plan.get("jurisdiction", "")).lower() not in ("india", "is", "is_bis", "bis"):
        out.append(("WARN",
                    "cfg['load_plan'].jurisdiction should be 'india' (got %r)" % plan.get("jurisdiction")))

    retrieval = plan.get("retrieval") or []
    if not isinstance(retrieval, list) or len(retrieval) < 2:
        out.append(("ERROR",
                    "cfg['load_plan'].retrieval must list ≥2 LIVE RAG hits this job "
                    "(IS 875 family + IS 1893 as applicable). Do not invent citations; "
                    "found:false is honest."))
    else:
        stems_hit = set()
        found_any = False
        for i, hit in enumerate(retrieval):
            if not isinstance(hit, dict):
                out.append(("ERROR", "load_plan.retrieval[%d] must be an object" % i))
                continue
            stem = str(hit.get("stem") or hit.get("doc") or "")
            if stem:
                stems_hit.add(stem)
            if hit.get("found") is True:
                found_any = True
            if hit.get("found") is False:
                out.append(("WARN",
                            "load_plan.retrieval[%d] found:false for %s — do not invent; "
                            "retry FTS/exact or note gap" % (i, stem or "?")))
            if not (hit.get("query") or hit.get("cite")):
                out.append(("WARN", "load_plan.retrieval[%d] missing query/cite" % i))
        load_needed = set(LOAD_STEMS)
        # Always expect at least one IS 875 and IS 1893 when seismic is declared
        if not any(s.startswith("IS_875") for s in stems_hit):
            out.append(("ERROR",
                        "load_plan.retrieval has no IS_875_* stem — query dead/imposed/wind/snow "
                        "from IS 875 Parts 1–5 before running the pipeline."))
        seis = cfg.get("seis") or {}
        if seis and not any("1893" in s for s in stems_hit):
            out.append(("ERROR",
                        "cfg has seismic inputs but load_plan.retrieval has no IS_1893_* hit — "
                        "RAG-query IS 1893 Part 1:2016 for zone factor / design spectrum / base shear."))
        if not found_any:
            out.append(("ERROR",
                        "load_plan.retrieval has no found:true hits — refuse to invent load factors."))

    combos = plan.get("combinations") or []
    if not isinstance(combos, list) or len(combos) < 1:
        out.append(("ERROR",
                    "cfg['load_plan'].combinations empty — after RAG, write IS 800 Table 4 "
                    "(partial factors) combinations with fD/fL/fLr and any lateral story forces."))
    else:
        for i, c in enumerate(combos):
            if not isinstance(c, dict):
                out.append(("ERROR", "combinations[%d] must be an object" % i))
                continue
            if not c.get("label"):
                out.append(("ERROR", "combinations[%d] missing label" % i))
            for key in ("fD", "fL", "fLr"):
                if key not in c:
                    out.append(("ERROR", "combinations[%d] missing %s" % (i, key)))
            if not c.get("cite"):
                out.append(("WARN", "combinations[%d] (%s) has no cite — attach the retrieved clause"
                            % (i, c.get("label", "?"))))

    # ---- P0 gates: wind (S5/H2) + Ta fail-closed (H1) ----
    out.extend(validate_wind_gate(cfg, plan))
    try:
        from india_seismic import validate_Ta_for_system as _vTa
        out.extend(_vTa(cfg, plan))
    except Exception as _ex:
        out.append(("WARN", "Ta fail-closed gate unavailable: %s" % _ex))

    # Hard ban: residual ASCE keys that imply the USA hardcoded path is still driving loads
    if cfg.get("use_asce7_engine_loads"):
        out.append(("ERROR",
                    "use_asce7_engine_loads is set — forbidden on steltic_india. "
                    "Remove it and supply cfg['load_plan'] from IS RAG."))

    return out


def cases_from_load_plan(cfg) -> list:
    """Build design_pipeline combo tuples from cfg['load_plan']. Raises LoadPlanError on ERRORs."""
    findings = validate_load_plan(cfg)
    errors = [m for lvl, m in findings if lvl == "ERROR"]
    if errors:
        raise LoadPlanError("India load_plan invalid:\n- " + "\n- ".join(errors))

    plan = cfg["load_plan"]
    cases = []
    for c in plan["combinations"]:
        label = str(c["label"])
        fD = float(c["fD"])
        fL = float(c.get("fL", 0.0))
        fLr = float(c.get("fLr", 0.0))
        lateral = _as_lateral(c.get("lateral") or {})
        # Allow named pattern reference: lateral_ref -> plan['story_forces'][name]
        ref = c.get("lateral_ref")
        if ref and not lateral:
            forces = (plan.get("story_forces") or {}).get(ref)
            if forces is None:
                raise LoadPlanError("combinations entry %r lateral_ref=%r not in load_plan.story_forces"
                                    % (label, ref))
            lateral = _as_lateral(forces)
        col_only = bool(c.get("col_only", False))
        cases.append((label, fD, fL, fLr, lateral, col_only))
    return cases


def render_findings(findings) -> str:
    if not findings:
        return "[india_loads] load_plan OK"
    lines = ["[india_loads] load_plan check:"]
    for lvl, msg in findings:
        lines.append("  [%s] %s" % (lvl, msg))
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# S6: Ka / Cpe — corpus exact_table prefer; india_wind_tables = fallback only
# ---------------------------------------------------------------------------
def wind_table_override_policy() -> dict:
    """Documented Ka/Cpe policy for agents (S6). See docs/IS875_P3_Ka_Cpe_OVERRIDES.md."""
    try:
        from india_wind_tables import override_policy
        return override_policy()
    except Exception as ex:
        return {"error": str(ex), "note": "india_wind_tables unavailable"}


def ka_fallback(A_m2: float) -> dict:
    """Table 4 Ka fallback when corpus exact_table 4 returns found:false."""
    from india_wind_tables import ka_for_area_m2
    return ka_for_area_m2(A_m2)


def cpe_walls_fallback(h_over_w: float, l_over_w: float, theta_deg: float = 0.0) -> dict:
    """Table 5 wall Cpe fallback when corpus exact_table 5 returns found:false."""
    from india_wind_tables import cpe_walls
    return cpe_walls(h_over_w, l_over_w, theta_deg)


# P1 alias — still fallback-only after corpus-prefer demotion.
cpe_walls_override = cpe_walls_fallback


def resolve_ka(A_m2: float, corpus_hit=None, *, allow_fallback: bool = True) -> dict:
    """Prefer corpus exact_table 4; fallback to in-repo Ka only if found:false."""
    from india_wind_tables import resolve_ka as _resolve
    return _resolve(A_m2, corpus_hit, allow_fallback=allow_fallback)


def resolve_cpe_walls(h_over_w: float, l_over_w: float, theta_deg: float = 0.0,
                      corpus_hit=None, *, allow_fallback: bool = True) -> dict:
    """Prefer corpus exact_table 5; fallback to in-repo Cpe only if found:false."""
    from india_wind_tables import resolve_cpe_walls as _resolve
    return _resolve(h_over_w, l_over_w, theta_deg, corpus_hit, allow_fallback=allow_fallback)



def resolve_k4(corpus_hit=None, *, eor_k4=None, eor_cite=None, eor_source=None,
               structure_class=None):
    """Prefer corpus §6.3.4 digits; else EOR-documented k4+cite (never invent)."""
    from india_wind_tables import resolve_k4 as _resolve
    return _resolve(
        corpus_hit, eor_k4=eor_k4, eor_cite=eor_cite, eor_source=eor_source,
        structure_class=structure_class,
    )


def resolve_building_length_m(cfg, *, bay_spacing_m=None, n_bays=None, n_frames=None):
    """Building length along portal spacing for wind l/w and Ka.

    Prefer explicit cfg keys (brief field). If missing, allow a *documented*
    assumption with cite — never a silent invented length.
    """
    cfg = cfg or {}
    for key in ("building_length_m", "length_m", "L_m", "plan_length_m"):
        if cfg.get(key) is not None:
            return {
                "found": True,
                "L_m": float(cfg[key]),
                "source": "cfg",
                "key": key,
                "cite": cfg.get("building_length_cite") or cfg.get("length_cite") or "cfg explicit",
            }
    # nested geometry
    geom = cfg.get("geometry") if isinstance(cfg.get("geometry"), dict) else {}
    if geom.get("length_m") is not None:
        return {
            "found": True, "L_m": float(geom["length_m"]), "source": "cfg.geometry",
            "cite": geom.get("length_cite") or "cfg.geometry.length_m",
        }
    # Documented assumption path
    assum = cfg.get("building_length_assumption_m")
    assum_cite = cfg.get("building_length_assumption_cite") or cfg.get("length_assumption_cite")
    if assum is not None and assum_cite:
        return {
            "found": True,
            "L_m": float(assum),
            "source": "documented_assumption",
            "cite": str(assum_cite),
            "note": "Brief omitted building length; documented assumption — not silent invent",
            "brief_field_required": "building_length_m (or n_frames × bay spacing stated in brief)",
        }
    # Derive only when spacing + count are explicit in cfg AND cite documents the assumption
    sp = bay_spacing_m if bay_spacing_m is not None else cfg.get("bay_spacing_m") or cfg.get("bay_y") or cfg.get("frame_spacing_m")
    nb = n_bays if n_bays is not None else cfg.get("n_bays_length") or cfg.get("NY")
    nf = n_frames if n_frames is not None else cfg.get("n_frames")
    derive_cite = cfg.get("building_length_derive_cite")
    if sp and (nb is not None) and derive_cite:
        L = float(sp) * float(nb)
        return {
            "found": True, "L_m": L, "source": "derived_documented",
            "cite": str(derive_cite),
            "bay_spacing_m": float(sp), "n_bays": float(nb),
            "note": "L = n_bays × spacing with documented cite; prefer brief building_length_m",
            "brief_field_required": "building_length_m",
        }
    if sp and nf is not None and derive_cite:
        # n_frames = n_bays + 1 → length = (n_frames-1)*spacing
        L = float(sp) * max(float(nf) - 1.0, 0.0)
        return {
            "found": True, "L_m": L, "source": "derived_documented",
            "cite": str(derive_cite),
            "bay_spacing_m": float(sp), "n_frames": float(nf),
            "note": "L = (n_frames-1) × spacing with documented cite",
            "brief_field_required": "building_length_m",
        }
    return {
        "found": False,
        "L_m": None,
        "required_inputs": [
            "cfg['building_length_m'] (preferred brief field)",
            "OR building_length_assumption_m + building_length_assumption_cite",
            "OR bay spacing + n_bays/n_frames + building_length_derive_cite",
        ],
        "brief_field_required": "building_length_m",
        "note": (
            "Brief gave frame spacing but not building length (IN_Ex3 pattern). "
            "Do not silently assume L=36 m — set cfg building_length_m or document the assumption with cite."
        ),
    }


def resolve_storage_height_m(cfg=None, *, eor_h_m=None, eor_cite=None, eor_source=None,
                             unit_load_kNpm2_per_m=2.0):
    """Mezz/warehouse storage height for IS 875 Part 2 storage UDL (kN/m² per m height).

    Prefer cfg['storage_height_m'] (brief). Else documented assumption with cite.
    Never invent a silent 2.5 m.
    Returns L_floor = unit_load × height when resolved.
    """
    cfg = cfg or {}
    for key in ("storage_height_m", "mezz_storage_height_m", "stack_height_m"):
        if cfg.get(key) is not None:
            h = float(cfg[key])
            return {
                "found": True,
                "h_m": h,
                "L_kNpm2": float(unit_load_kNpm2_per_m) * h,
                "unit_load_kNpm2_per_m": float(unit_load_kNpm2_per_m),
                "source": "cfg",
                "key": key,
                "cite": cfg.get("storage_height_cite") or "cfg explicit storage height",
            }
    h = eor_h_m if eor_h_m is not None else cfg.get("storage_height_assumption_m")
    cite = eor_cite or cfg.get("storage_height_assumption_cite")
    src = (eor_source or cfg.get("storage_height_source") or "").strip().lower().replace(" ", "_")
    ok = {"eor_documented", "eor", "documented", "explicit", "documented_assumption", "assumption_documented"}
    if h is not None and cite and (src in ok or src == "" or "document" in src or "eor" in src or "assum" in src):
        return {
            "found": True,
            "h_m": float(h),
            "L_kNpm2": float(unit_load_kNpm2_per_m) * float(h),
            "unit_load_kNpm2_per_m": float(unit_load_kNpm2_per_m),
            "source": src or "documented_assumption",
            "resolved_via": "eor_documented" if "eor" in (src or "documented") else "documented_assumption",
            "cite": str(cite),
            "note": (
                "Storage height documented (not silent invent). Prefer brief storage_height_m. "
                "IS 875 P2 Table 1 warehouses 2.0 kN/m² per m of storage height."
            ),
            "brief_field_required": "storage_height_m",
        }
    return {
        "found": False,
        "h_m": None,
        "L_kNpm2": None,
        "required_inputs": [
            "cfg['storage_height_m'] (preferred brief field)",
            "OR storage_height_assumption_m + storage_height_assumption_cite",
        ],
        "brief_field_required": "storage_height_m",
        "cite": "IS 875 (Part 2):1987 Table 1 STORAGE — 2.0 kN/m² per m of storage height",
        "note": "Do not silently assume 2.5 m stack height — set cfg or document with cite.",
    }
