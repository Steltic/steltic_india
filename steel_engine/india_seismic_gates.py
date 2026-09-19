"""India HR seismic provenance gates (complete-gap wave2).

Dual SMF+SCBF (IN_Ex4) and similar steel SFRS where IS 1893 Table 9 lacks an
exact row: require explicit R + R_source + R_cite (CFS-style eor_documented).
Never silently invent R or ASCE-style Ω0.

COMPLETE gate refuses proxy / silent invent. Honest found:false for missing
steel-dual Table 9 row or Ω0 does NOT alone block COMPLETE when EOR provenance
is present.
"""
from __future__ import annotations

# --- response reduction R -------------------------------------------------
R_PROXY_SOURCES = frozenset({
    "proxy", "silent_proxy", "silent", "invented", "assumed", "assumption",
    "guess", "placeholder", "todo", "tbd",
    # Using SBF/SMRF Table 9 row as a silent stand-in for a missing steel dual
    # row without eor_documented disclosure is a proxy path:
    "sbf_proxy", "smrf_proxy", "table9_proxy", "silent_sbf", "silent_smrf",
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
})
OMEGA0_REFUSED = frozenset({
    "assumed", "assumption", "silent", "silent_default", "invented",
    "asce7", "asce_7", "asce722", "proxy", "placeholder", "todo", "tbd", "guess",
})


def _norm(s) -> str:
    return str(s or "").strip().lower().replace(" ", "_").replace("-", "_")


def resolve_R(cfg) -> dict:
    """Normalize R + provenance from cfg / seis / load_plan.seismic_summary.

    Prefer corpus Table 9 when steel_dual_table9_found is True. When the steel
    dual row is found:false, accept R only via allowlisted eor_documented /
    explicit paths with R_cite — never invent silently.
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

    dual_row = cfg.get("R_steel_dual_table9_found")
    if dual_row is None:
        dual_row = seis.get("R_steel_dual_table9_found")
    if dual_row is None:
        dual_row = summ.get("R_steel_dual_table9_found")
    if dual_row is None:
        dual_row = summ.get("steel_dual_table9_found")

    return {
        "R": R,
        "source": source,
        "cite": cite,
        "steel_dual_table9_found": dual_row,
        "raw_source": _norm(source),
    }


def resolve_Omega0(cfg=None, *, eor_Omega0=None, eor_cite=None, eor_source=None,
                   corpus_hit=None) -> dict:
    """Resolve ASCE-style Ω0 for India jobs.

    IS 1893 has no Ω0 — default found:false. Optional eor_documented hook when
    the EOR supplies a project Ω0 + cite (never invent from ASCE 7 silently).
    Honest found:false does not invent IS-native Ω0.
    """
    cfg = cfg or {}
    seis = cfg.get("seis") if isinstance(cfg.get("seis"), dict) else {}
    plan = cfg.get("load_plan") if isinstance(cfg.get("load_plan"), dict) else {}
    summ = plan.get("seismic_summary") if isinstance(plan.get("seismic_summary"), dict) else {}

    # Corpus path (almost always miss for IS 1893)
    if isinstance(corpus_hit, dict) and corpus_hit.get("found") is True:
        om = corpus_hit.get("Omega0") or corpus_hit.get("Om0") or corpus_hit.get("omega0")
        if om is not None:
            return {
                "found": True,
                "Omega0": float(om),
                "source": corpus_hit.get("source") or "corpus",
                "resolved_via": "corpus",
                "cite": corpus_hit.get("cite") or "IS 1893 (corpus)",
                "note": "Ω0 from corpus hit — rare for IS 1893; confirm clause.",
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
        if src in OMEGA0_REFUSED or "asce" in src:
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
            }
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
        }

    # Default honest miss
    refused = []
    if om is not None and (src in OMEGA0_REFUSED or "asce" in src or not src):
        refused.append("Omega0_source must be eor_documented/explicit (not asce/assumed/silent)")
    if om is not None and not cite:
        refused.append("Omega0_cite")
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
    }


def validate_R(cfg) -> list:
    """(severity, message) findings for dual/HR R provenance."""
    out = []
    if not isinstance(cfg, dict):
        return [("ERROR", "cfg is not a dict")]

    info = resolve_R(cfg)
    R, src = info["R"], info["raw_source"]
    sysname = _norm(cfg.get("system") or "")
    needs_dual_gate = ("dual" in sysname) or (info["steel_dual_table9_found"] is False)

    if R is None or R == "":
        if needs_dual_gate:
            out.append(("ERROR",
                        "cfg['R'] missing for dual/steel-SFRS job. Set R from IS 1893 "
                        "Table 9 RAG, or R_source='eor_documented' + R_cite when the steel "
                        "dual Table 9 row is found:false. Never invent R silently."))
        return out

    try:
        float(R)
    except (TypeError, ValueError):
        out.append(("ERROR", "R=%r is not numeric" % (R,)))
        return out

    if needs_dual_gate and not src:
        out.append(("ERROR",
                    "R_source missing while steel dual Table 9 row is absent / system is dual. "
                    "Silent use of concentric SBF R=4.5 (or SMRF R=5) as a dual Table 9 invent "
                    "is forbidden. Set R_steel_dual_table9_found=false and "
                    "R_source='eor_documented'|'explicit'|'sbf_concentric_for_dual' with R_cite."))
        return out

    if src in R_PROXY_SOURCES or "proxy" in src or "silent" in src or "invent" in src:
        out.append(("WARN",
                    "R_source=%r is a proxy/silent-invent path. Job MUST stay PARTIAL — "
                    "complete_allowed=false. Prefer R_source='eor_documented' with "
                    "R_steel_dual_table9_found=false + R_cite disclosing SBF/SMRF Table 9 basis."
                    % (info["source"],)))

    if src and src not in R_OK_SOURCES and src not in ("user", "brief"):
        out.append(("WARN",
                    "R_source=%r unusual — prefer is1893_table9 / eor_documented / "
                    "sbf_concentric_for_dual / explicit" % (info["source"],)))

    if info["steel_dual_table9_found"] is False:
        if not (info["cite"] or "").strip():
            out.append(("ERROR",
                        "R_steel_dual_table9_found=false but R_cite missing — disclose the "
                        "EOR/Table 9 SBF basis for R (steel dual row absent from IS 1893 Table 9)."))
        else:
            out.append(("WARN",
                        "Steel SMF+SCBF dual R row missing from IS 1893 Table 9 (found:false). "
                        "R_source must stay non-proxy (eor_documented/explicit/"
                        "sbf_concentric_for_dual). COMPLETE gate refuses proxy."))

    return out


def R_is_proxy(cfg, pkg=None) -> bool:
    """True if R provenance is proxy / silent invent."""
    info = resolve_R(cfg or {})
    src = info["raw_source"]
    if src in R_PROXY_SOURCES or "proxy" in src or "silent" in src or "invent" in src:
        return True
    sysname = _norm((cfg or {}).get("system") or "")
    dualish = ("dual" in sysname) or (info["steel_dual_table9_found"] is False)
    if dualish and not src and info["R"] is not None:
        return True  # silent invent class
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
    """Refuse COMPLETE if R is proxy/silent invent.

    Ω0 found:false and steel-dual Table 9 found:false alone do NOT block when
    R_source is allowlisted eor_documented with cite.
    """
    reasons = []
    if R_is_proxy(cfg, pkg):
        reasons.append(
            "R source is proxy / silent invent — IS 1893 Table 9 row or "
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
    """Label helper: complete vs partial based on R provenance gate."""
    ok, reasons = complete_allowed(cfg, pkg)
    info = resolve_R(cfg or {})
    om = resolve_Omega0(cfg)
    return {
        "status": "complete" if ok else "partial",
        "complete_allowed": ok,
        "reasons": reasons,
        "R": info,
        "Omega0": {"found": om.get("found"), "resolved_via": om.get("resolved_via")},
        "note": (
            "COMPLETE allowed when R provenance is non-proxy. "
            "Ω0 found:false does not alone block."
            if ok else
            "PARTIAL — fix R_source/R_cite (eor_documented) before COMPLETE."
        ),
    }
