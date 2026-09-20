"""India HR seismic provenance gates (complete-gap wave2 + HR polish Wave D).

Dual SMF+SCBF (IN_Ex4) and Ex6–15 steel SFRS where IS 1893 Table 9 lacks an
exact row (BRBF / SPSW / EBF / IMF / dual+BRBF): require explicit R + R_source
+ R_cite (CFS-style eor_documented). Never silently invent R or ASCE-style Ω0.

COMPLETE gate refuses proxy / silent invent / is800_omrf. Honest found:false
for missing Table 9 rows or Ω0 does NOT alone block COMPLETE when EOR
provenance (or disclosed Table 9 mapping with cite) is present.

EXAMPLE EOR fixtures are OK when labeled not-for-construction.
"""
from __future__ import annotations

# --- response reduction R -------------------------------------------------
R_PROXY_SOURCES = frozenset({
    "proxy", "silent_proxy", "silent", "invented", "assumed", "assumption",
    "guess", "placeholder", "todo", "tbd",
    # Using SBF/SMRF Table 9 row as a silent stand-in for a missing steel dual
    # row without eor_documented disclosure is a proxy path:
    "sbf_proxy", "smrf_proxy", "table9_proxy", "silent_sbf", "silent_smrf",
    # Wave D — refuse COMPLETE when R is invented from IS 800 OMRF / silent
    # system mapping without Table 9 row or eor_documented cite (Ex6–15):
    "is800_omrf", "is_800_omrf", "omrf_proxy", "silent_omrf",
    "imf_proxy", "brbf_proxy", "spsw_proxy", "ebf_proxy",
    "is800_proxy", "is_800_proxy",
})
R_OK_SOURCES = frozenset({
    "is1893_table9", "is_1893_table9", "table9", "is1893", "rag",
    "explicit", "eor_explicit", "documented", "eor_documented", "eor",
    # Disclosed use of concentric SBF R for a dual when steel dual row absent —
    # only with R_steel_dual_table9_found=false + R_cite (not silent).
    "sbf_concentric_for_dual", "table9_sbf_for_dual",
})

OMEGA0_OK_SOURCES = frozenset({
    "eor_documented", "eor", "documented", "explicit", "eor_explicit",
    "is1893", "rag",  # only if corpus actually has Ω0 (it does not today)
    # IS 18168 is the preferred India steel-SFRS corpus source for Ω. Keep
    # both spellings because retrieval metadata uses both forms.
    "is18168", "is_18168",
})
OMEGA0_REFUSED = frozenset({
    "assumed", "assumption", "silent", "silent_default", "invented",
    "asce7", "asce_7", "asce722", "proxy", "placeholder", "todo", "tbd", "guess",
})

# India policy: IS 1893 does not tabulate an ASCE-style Ω0. For steel SFRS,
# prefer the IS 18168 Ω/ELm=Ω·EL corpus path when it is actually ingested; do
# not manufacture the familiar SCBF/EBF/SMRF values from memory.
OMEGA0_POLICY = {
    "blocks_complete": False,
    "preferred_source_when_available": "is18168",
    "honest_is1893_found_false_blocks_complete": False,
    "is18168_values_require_corpus_hit": True,
    "note": (
        "IS 1893 has no ASCE-style Ω0. Prefer corpus IS 18168 Ω for steel "
        "SFRS (ELm=Ω·EL); never invent Ω values without a found:true corpus hit."
    ),
}


def _omega0_policy() -> dict:
    """Return a fresh Ω0 policy/disclosure object for public result payloads."""
    return dict(OMEGA0_POLICY)

# Wave D — Table 9 system miss flags (Ex6–15). When found:false, COMPLETE
# requires non-proxy R_source + R_cite (eor_documented or disclosed Table 9 map).
# EXAMPLE fixtures OK when labeled not-for-construction.
TABLE9_SYSTEM_FLAGS = (
    # (cfg_keys_tuple, system_name_substrings, out_key)
    (("R_steel_dual_table9_found", "steel_dual_table9_found"),
     ("dual",), "steel_dual_table9_found"),
    (("R_steel_brbf_table9_found", "steel_brbf_table9_found", "R_steel_brb_table9_found"),
     ("brbf", "brb", "buckling_restrained"), "steel_brbf_table9_found"),
    (("R_steel_spsw_table9_found", "steel_spsw_table9_found"),
     ("spsw", "steel_plate_shear", "plate_shear_wall"), "steel_spsw_table9_found"),
    (("R_steel_ebf_table9_found", "steel_ebf_table9_found"),
     ("ebf", "eccentric"), "steel_ebf_table9_found"),
    (("R_steel_imf_table9_found", "steel_imf_table9_found"),
     ("imf", "intermediate_moment"), "steel_imf_table9_found"),
)


def _norm(s) -> str:
    return str(s or "").strip().lower().replace(" ", "_").replace("-", "_")


def _pull_flag(cfg, seis, summ, keys):
    for k in keys:
        if cfg.get(k) is not None:
            return cfg.get(k)
        if seis.get(k) is not None:
            return seis.get(k)
        if summ.get(k) is not None:
            return summ.get(k)
    return None


def table9_system_flags(cfg) -> dict:
    """Collect IS 1893 Table 9 found flags for dual/BRBF/SPSW/EBF/IMF."""
    cfg = cfg or {}
    seis = cfg.get("seis") if isinstance(cfg.get("seis"), dict) else {}
    plan = cfg.get("load_plan") if isinstance(cfg.get("load_plan"), dict) else {}
    summ = plan.get("seismic_summary") if isinstance(plan.get("seismic_summary"), dict) else {}
    out = {}
    for keys, _subs, out_key in TABLE9_SYSTEM_FLAGS:
        out[out_key] = _pull_flag(cfg, seis, summ, keys)
    return out


def table9_miss_systems(cfg) -> list:
    """Systems whose Table 9 row is explicitly found:false (or name implies miss gate)."""
    cfg = cfg or {}
    sysname = _norm(cfg.get("system") or "")
    flags = table9_system_flags(cfg)
    misses = []
    for keys, subs, out_key in TABLE9_SYSTEM_FLAGS:
        val = flags.get(out_key)
        name_hit = any(s in sysname for s in subs)
        if val is False or (name_hit and val is False):
            if out_key not in misses and val is False:
                misses.append(out_key)
        elif name_hit and val is False:
            misses.append(out_key)
    # Name-implied systems with no flag set still need provenance when R present
    # only if an explicit found:false was set — name alone without flag does not
    # force miss (Ex8 OCBF Table 9 found:true stays clean).
    return misses


def needs_table9_miss_gate(cfg) -> bool:
    """True when dual/BRBF/SPSW/EBF/IMF Table 9 row is found:false (or dual by name)."""
    cfg = cfg or {}
    sysname = _norm(cfg.get("system") or "")
    flags = table9_system_flags(cfg)
    if "dual" in sysname:
        return True
    if any(v is False for v in flags.values()):
        return True
    return False


def resolve_R(cfg) -> dict:
    """Normalize R + provenance from cfg / seis / load_plan.seismic_summary.

    Prefer corpus Table 9 when the system row is found:true. When BRBF / SPSW /
    EBF / IMF / dual Table 9 is found:false, accept R only via allowlisted
    eor_documented / explicit / disclosed Table 9 mapping with R_cite —
    never invent silently (Wave D).
    """
    cfg = cfg or {}
    seis = cfg.get("seis") if isinstance(cfg.get("seis"), dict) else {}
    plan = cfg.get("load_plan") if isinstance(cfg.get("load_plan"), dict) else {}
    summ = plan.get("seismic_summary") if isinstance(plan.get("seismic_summary"), dict) else {}

    R = cfg.get("R")
    if R is None:
        R = seis.get("R")
    if R is None:
        R = summ.get("R")

    source = (cfg.get("R_source") or seis.get("R_source") or summ.get("R_source")
              or cfg.get("r_source") or summ.get("response_reduction_source"))
    cite = cfg.get("R_cite") or seis.get("R_cite") or summ.get("R_cite") or summ.get("cite")

    flags = table9_system_flags(cfg)
    return {
        "R": R,
        "source": source,
        "cite": cite,
        "steel_dual_table9_found": flags.get("steel_dual_table9_found"),
        "steel_brbf_table9_found": flags.get("steel_brbf_table9_found"),
        "steel_spsw_table9_found": flags.get("steel_spsw_table9_found"),
        "steel_ebf_table9_found": flags.get("steel_ebf_table9_found"),
        "steel_imf_table9_found": flags.get("steel_imf_table9_found"),
        "table9_misses": [k for k, v in flags.items() if v is False],
        "raw_source": _norm(source),
    }


def resolve_Omega0(cfg=None, *, eor_Omega0=None, eor_cite=None, eor_source=None,
                   corpus_hit=None) -> dict:
    """Resolve India steel overstrength without inventing ASCE-style Ω0.

    IS 1893 has no Ω0 — default found:false. The preferred path, when the
    corpus is available, is IS 18168 Ω for steel SFRS (ELm=Ω·EL), not an ASCE
    Ω0 term. An ``is18168`` value is accepted only from a found:true corpus
    hit; do not hardcode the familiar 2.5/3.0 values. The optional
    eor_documented hook remains valid for a project EOR value + cite.
    Honest found:false does not block COMPLETE and does not invent IS-native Ω.
    """
    cfg = cfg or {}
    seis = cfg.get("seis") if isinstance(cfg.get("seis"), dict) else {}
    plan = cfg.get("load_plan") if isinstance(cfg.get("load_plan"), dict) else {}
    summ = plan.get("seismic_summary") if isinstance(plan.get("seismic_summary"), dict) else {}

    # Corpus path (almost always miss for IS 1893). IS 18168 calls this Ω;
    # accept common Ω/Ω0 key spellings but preserve the public Omega0 field for
    # compatibility with existing India disclosures.
    if isinstance(corpus_hit, dict) and corpus_hit.get("found") is True:
        corpus_source = _norm(corpus_hit.get("source"))
        om = (corpus_hit.get("Omega") or corpus_hit.get("omega")
              or corpus_hit.get("Omega0") or corpus_hit.get("Om0")
              or corpus_hit.get("omega0"))
        # ASCE-labeled corpus material is never an India Ω source.
        if (om is not None and corpus_source not in OMEGA0_REFUSED
                and "asce" not in corpus_source):
            policy = _omega0_policy()
            return {
                "found": True,
                "Omega0": float(om),
                "source": corpus_source or "corpus",
                "resolved_via": "corpus",
                # In particular, an IS 18168 result must disclose the cite
                # returned by that hit rather than a made-up/default cite.
                "cite": corpus_hit.get("cite") or "IS 1893 (corpus)",
                "note": (
                    "Ω from corpus IS 18168 hit (ELm=Ω·EL); use the hit cite."
                    if corpus_source in {"is18168", "is_18168"}
                    else "Ω0 from corpus hit — rare for IS 1893; confirm clause."
                ),
                "omega0_policy": policy,
                "disclosure": policy,
            }

    om = eor_Omega0
    if om is None:
        om = cfg.get("Omega0") or cfg.get("Om0") or seis.get("Omega0") or seis.get("Om0")
        if om is None:
            om = summ.get("Omega0") or summ.get("Om0")
    src = _norm(eor_source or cfg.get("Omega0_source") or seis.get("Omega0_source")
                or summ.get("Omega0_source"))
    cite = (eor_cite or cfg.get("Omega0_cite") or seis.get("Omega0_cite")
            or summ.get("Omega0_cite"))

    # Explicit found:false disclosure (preferred India path)
    flagged_false = (
        cfg.get("Omega0_found") is False
        or seis.get("Omega0_found") is False
        or summ.get("Omega0_found") is False
        or (isinstance(corpus_hit, dict) and corpus_hit.get("found") is False)
    )

    if om is not None and src in OMEGA0_OK_SOURCES and cite:
        # IS 18168 values are not an EOR alias and may not be supplied as an
        # unexplained literal. They must come from the found:true corpus
        # branch above; this prevents inventing 2.5/3.0 without the PDF hit.
        if src in {"is18168", "is_18168"}:
            policy = _omega0_policy()
            return {
                "found": False,
                "Omega0": None,
                "corpus_found": False,
                "source": src,
                "resolved_via": "found_false",
                "cite": "IS 18168 Ω requires a found:true corpus hit",
                "note": (
                    "Refused literal IS 18168 Ω without a found:true corpus hit; "
                    "do not hardcode SCBF/EBF/SMRF values."
                ),
                "required_inputs": ["corpus_hit={found:true, source:is18168, cite, Ω}"],
                "is1893_omega0_present": False,
                "flagged_false": bool(flagged_false) or True,
                "omega0_policy": policy,
                "disclosure": policy,
            }
        if src in OMEGA0_REFUSED or "asce" in src:
            policy = _omega0_policy()
            return {
                "found": False,
                "Omega0": None,
                "source": src,
                "resolved_via": "refused",
                "cite": "IS 1893 has no Ω0 — refuse silent ASCE invent",
                "note": (
                    "Refused Ω0 source=%r. Do not invent ASCE 7 Ω0 for India. "
                    "Use IS 800 §12 capacity-design factors, or supply "
                    "Omega0_source='eor_documented' with Omega0_cite (project EOR)."
                    % (src,)
                ),
                "required_inputs": ["Omega0_source in eor_documented/explicit", "Omega0_cite"],
                "omega0_policy": policy,
                "disclosure": policy,
            }
        policy = _omega0_policy()
        return {
            "found": True,
            "Omega0": float(om),
            "corpus_found": False,
            "source": src,
            "resolved_via": "eor_documented" if ("eor" in src or src == "documented") else src,
            "cite": str(cite),
            "note": (
                "Ω0 from EOR/documented path — IS 1893 has no tabulated Ω0. "
                "Not invented silently. Prefer IS 800 §12 factors for capacity design."
            ),
            "policy": "eor_documented_ok_when_is1893_miss",
            "omega0_policy": policy,
            "disclosure": policy,
        }

    # Default honest miss
    refused = []
    if om is not None and (src in OMEGA0_REFUSED or "asce" in src or not src):
        refused.append("Omega0_source must be eor_documented/explicit (not asce/assumed/silent)")
    if om is not None and not cite:
        refused.append("Omega0_cite")
    policy = _omega0_policy()
    return {
        "found": False,
        "Omega0": None,
        "corpus_found": False,
        "source": src or None,
        "resolved_via": "found_false",
        "cite": "IS 1893 (Part 1):2016 — no ASCE-style Ω0; capacity design via IS 800 §12",
        "note": (
            "Ω0 found:false (honest). Do not invent ASCE 7 Ω0. Optional: set "
            "Omega0 + Omega0_source='eor_documented' + Omega0_cite for project EOR value; "
            "otherwise use IS 800 §12 capacity-design factors (1.2 fy Ag, §12.2.3, …)."
        ),
        "required_inputs": refused or [
            "leave Omega0_found=false",
            "OR Omega0 + Omega0_source=eor_documented + Omega0_cite",
        ],
        "is1893_omega0_present": False,
        "flagged_false": bool(flagged_false) or True,
        "omega0_policy": policy,
        "disclosure": policy,
    }


def validate_R(cfg) -> list:
    """(severity, message) findings for dual/BRBF/SPSW/EBF/IMF/HR R provenance (Wave D)."""
    out = []
    if not isinstance(cfg, dict):
        return [("ERROR", "cfg is not a dict")]

    info = resolve_R(cfg)
    R, src = info["R"], info["raw_source"]
    needs_gate = needs_table9_miss_gate(cfg)
    misses = info.get("table9_misses") or []

    if R is None or R == "":
        if needs_gate:
            out.append(("ERROR",
                        "cfg['R'] missing for steel-SFRS job with Table 9 miss / dual. "
                        "Set R from IS 1893 Table 9 RAG, or R_source='eor_documented' + "
                        "R_cite when the system Table 9 row is found:false. Never invent R "
                        "silently (incl. is800_omrf)."))
        return out

    try:
        float(R)
    except (TypeError, ValueError):
        out.append(("ERROR", "R=%r is not numeric" % (R,)))
        return out

    if needs_gate and not src:
        out.append(("ERROR",
                    "R_source missing while IS 1893 Table 9 system row is found:false "
                    "(or system is dual). Silent invent (incl. is800_omrf / silent SBF/"
                    "SMRF/OMRF mapping) is forbidden. Set the matching "
                    "R_steel_*_table9_found=false and R_source='eor_documented'|'explicit'|"
                    "'is1893_table9' (disclosed mapping) |'sbf_concentric_for_dual' with R_cite. "
                    "Misses=%s" % (misses or ["dual_by_name"],)))
        return out

    if src in R_PROXY_SOURCES or "proxy" in src or "silent" in src or "invent" in src:
        out.append(("WARN",
                    "R_source=%r is a proxy/silent-invent path (Wave D includes is800_omrf). "
                    "Job MUST stay PARTIAL — complete_allowed=false. Prefer "
                    "R_source='eor_documented' with R_steel_*_table9_found=false + R_cite "
                    "(EXAMPLE fixtures OK when labeled not-for-construction)."
                    % (info["source"],)))

    if src and src not in R_OK_SOURCES and src not in ("user", "brief"):
        out.append(("WARN",
                    "R_source=%r unusual — prefer is1893_table9 / eor_documented / "
                    "sbf_concentric_for_dual / explicit" % (info["source"],)))

    if misses:
        if not (info["cite"] or "").strip():
            out.append(("ERROR",
                        "Table 9 found:false for %s but R_cite missing — disclose EOR or "
                        "the Table 9 mapping basis (never silent is800_omrf invent)."
                        % (", ".join(misses),)))
        else:
            out.append(("WARN",
                        "IS 1893 Table 9 row found:false for %s. R_source must stay "
                        "non-proxy (eor_documented/explicit/is1893_table9 disclosed map/"
                        "sbf_concentric_for_dual). COMPLETE gate refuses proxy/is800_omrf."
                        % (", ".join(misses),)))

    return out


def R_is_proxy(cfg, pkg=None) -> bool:
    """True if R provenance is proxy / silent invent (Wave D: is800_omrf + Table 9 miss)."""
    info = resolve_R(cfg or {})
    src = info["raw_source"]
    if src in R_PROXY_SOURCES or "proxy" in src or "silent" in src or "invent" in src:
        return True
    # Silent invent when Table 9 miss / dual and R present without source
    if needs_table9_miss_gate(cfg or {}) and not src and info["R"] is not None:
        return True
    if not isinstance(pkg, dict):
        return False
    notes = pkg.get("design_basis_notes") or {}
    blob = _norm(notes.get("R_basis") or notes.get("R_source") or "")
    if "proxy" in blob or "silent" in blob or "invent" in blob:
        return True
    summ = ((pkg.get("load_plan") or {}).get("seismic_summary")
            if isinstance(pkg.get("load_plan"), dict) else None) or {}
    if "proxy" in _norm(summ.get("R_source") or summ.get("note") or ""):
        return True
    return False


def omega0_blocks_complete(cfg=None, pkg=None) -> bool:
    """Ω0 found:false alone must NOT block COMPLETE (honest IS gap)."""
    return False


def complete_allowed(cfg, pkg=None) -> tuple:
    """Refuse COMPLETE if R is proxy/silent invent / is800_omrf.

    Ω0 found:false and Table 9 found:false alone do NOT block when R_source is
    allowlisted eor_documented (or disclosed Table 9 mapping) with cite.
    EXAMPLE EOR fixtures OK when labeled not-for-construction.
    """
    reasons = []
    if R_is_proxy(cfg, pkg):
        reasons.append(
            "R source is proxy / silent invent / is800_omrf — IS 1893 Table 9 row or "
            "R_source='eor_documented' (non-proxy) + R_cite required for COMPLETE"
        )
    for sev, msg in validate_R(cfg or {}):
        if sev == "ERROR":
            reasons.append(msg)
    seen = set()
    uniq = []
    for r in reasons:
        if r not in seen:
            seen.add(r)
            uniq.append(r)
    return (len(uniq) == 0, uniq)


def design_status(cfg, pkg=None) -> dict:
    """COMPLETE vs PARTIAL label + Wave D disclosure (Ω0 / Table 9 / R)."""
    ok, reasons = complete_allowed(cfg, pkg)
    info = resolve_R(cfg or {})
    om = resolve_Omega0(cfg)
    misses = info.get("table9_misses") or []
    return {
        "status": "complete" if ok else "partial",
        "complete_allowed": ok,
        "reasons": reasons,
        "R": info,
        "Omega0": {
            "found": om.get("found"),
            "Omega0": om.get("Omega0"),
            "resolved_via": om.get("resolved_via"),
            "cite": om.get("cite"),
            "note": om.get("note"),
            "eor_documented": bool(om.get("found") and "eor" in _norm(om.get("resolved_via"))),
            "blocks_complete": False,  # honest IS gap never alone blocks
            "omega0_policy": _omega0_policy(),
            "disclosure": {
                "blocks_complete": False,
                "preferred_source_when_available": "is18168",
                "honest_is1893_found_false_blocks_complete": False,
            },
        },
        "omega0_policy": _omega0_policy(),
        "table9": {
            "misses": misses,
            "flags": {
                "steel_dual_table9_found": info.get("steel_dual_table9_found"),
                "steel_brbf_table9_found": info.get("steel_brbf_table9_found"),
                "steel_spsw_table9_found": info.get("steel_spsw_table9_found"),
                "steel_ebf_table9_found": info.get("steel_ebf_table9_found"),
                "steel_imf_table9_found": info.get("steel_imf_table9_found"),
            },
            "needs_miss_gate": needs_table9_miss_gate(cfg or {}),
            "example_fixtures_ok_when_labeled": True,
        },
        "note": (
            "COMPLETE allowed when R provenance is non-proxy (eor_documented / "
            "disclosed Table 9 map OK). Ω0 found:false does not alone block. "
            "proxy/is800_omrf refused."
            if ok else
            "PARTIAL — fix R_source/R_cite (eor_documented or disclosed Table 9 map); "
            "refuse proxy/is800_omrf before COMPLETE."
        ),
    }


def complete_gate_disclosure(cfg, pkg=None) -> dict:
    """Wave D COMPLETE-gate disclosure object (Ω0 + Table 9 + R) for calc packages."""
    st = design_status(cfg, pkg)
    om = st["Omega0"]
    return {
        "complete_allowed": st["complete_allowed"],
        "status": st["status"],
        "reasons": st["reasons"],
        "Omega0": om,
        "omega0_policy": _omega0_policy(),
        "disclosure": {
            "Omega0": om,
            "blocks_complete": False,
            "preferred_source_when_available": "is18168",
            "honest_is1893_found_false_blocks_complete": False,
        },
        "table9": st["table9"],
        "R_source": (st["R"] or {}).get("source"),
        "R_cite": (st["R"] or {}).get("cite"),
        "policy": (
            "India path never invents Ω0 or Table 9 R. found:false / eor_documented "
            "consistent; EXAMPLE fixtures OK labeled not-for-construction; "
            "proxy/is800_omrf refuse COMPLETE."
        ),
    }
