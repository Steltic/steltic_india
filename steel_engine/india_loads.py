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
