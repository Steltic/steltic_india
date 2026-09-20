"""Live IS 18168:2023 Ω retrieval for India steel SFRS (no invent).

Queries the India corpus for IS_18168_2023 §5.5 (exact_section preferred) and
returns a corpus_hit dict suitable for ``india_seismic_gates.resolve_Omega0``.

Policy:
  * found:true ONLY when the corpus HIT is present and Ω digits are parsed
    from that HIT text (or verified structured fields derived from it).
  * Do NOT hardcode 2.5 / 3.0 as resolve defaults — numbers must come from
    the HIT. On miss / unmapped SFRS: found:false (honest).
  * §5.5 tabulates Ω for SCBF / EBF / SMRF only (ELm = Ω · EL).
"""
from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any, Optional

# Document / section constants (ids only — not Ω numeric defaults)
IS18168_DOC = "IS_18168_2023"
IS18168_SECTION = "5.5"
IS18168_CITE = "IS 18168:2023 §5.5"
IS18168_ELM_RULE = "ELm=Ω·EL"
DEFAULT_CORPUS_ROOT = "/workspace/engineering_rag_india"

# SFRS aliases → canonical key used when selecting from parsed HIT fields
_SFRS_ALIASES = {
    "scbf": "SCBF",
    "sbf_concentric": "SCBF",
    "sbf_concentric_braces": "SCBF",
    "special_concentrically_braced": "SCBF",
    "special_concentric": "SCBF",
    "ebf": "EBF",
    "sbf_eccentric": "EBF",
    "eccentric": "EBF",
    "eccentrically_braced": "EBF",
    "smrf": "SMRF",
    "smf": "SMRF",
    "special_moment": "SMRF",
    "special_moment_resisting": "SMRF",
}

# HIT text pattern (verbatim IS 18168 §5.5 wording family)
_OMEGA_HIT_RE = re.compile(
    r"Overstrength\s+factor\s*=\s*"
    r"(?P<scbf_ebf>[0-9]+(?:\.[0-9]+)?)\s+for\s+SCBFs?\s+and\s+EBFs?"
    r"\s*=\s*"
    r"(?P<smrf>[0-9]+(?:\.[0-9]+)?)\s+for\s+SMRFs?",
    re.IGNORECASE | re.DOTALL,
)


def _norm_key(s) -> str:
    return str(s or "").strip().lower().replace(" ", "_").replace("-", "_")


def normalize_sfrs(sfrs_type) -> Optional[str]:
    """Map job system strings to SCBF / EBF / SMRF, or None if unmapped.

    Dual / OCBF / BRBF / SPSW / IMF / OMRF → None (honest miss). Do not treat
    bare "concentric" as SCBF (OCBF labels also say concentric).
    """
    raw = _norm_key(sfrs_type)
    if not raw:
        return None
    if raw in _SFRS_ALIASES:
        return _SFRS_ALIASES[raw]
    # Explicit ordinary / other systems first (not in §5.5 Ω table)
    if any(t in raw for t in ("ocbf", "obf", "brbf", "brb", "spsw", "imf", "omrf")):
        # Allow "smrf"/"scbf"/"ebf" to still win if also present without dual —
        # but OCBF/BRBF/etc. alone must miss.
        pass
    has_scbf = (
        "scbf" in raw
        or "sbf_concentric" in raw
        or "special_concentric" in raw
        or "special_concentrically" in raw
    )
    has_ebf = "ebf" in raw or "eccentric" in raw or "sbf_eccentric" in raw
    has_smrf = (
        "smrf" in raw
        or "special_moment" in raw
        or re.search(r"(^|[^a-z])smf([^a-z]|$)", raw) is not None
    )
    # Ordinary / other SFRS tokens that are NOT §5.5 Ω rows
    has_other = any(
        t in raw for t in ("ocbf", "obf", "brbf", "brb", "spsw", "imf", "omrf")
    )
    # dual / mixed / other → honest miss (different or untabulated Ω)
    n_hit = sum(bool(x) for x in (has_scbf, has_ebf, has_smrf))
    if "dual" in raw or n_hit > 1:
        return None
    if has_other and n_hit == 0:
        return None
    if has_scbf:
        return "SCBF"
    if has_ebf:
        return "EBF"
    if has_smrf:
        return "SMRF"
    return None


def corpus_root(root: Optional[str] = None) -> Path:
    env = os.environ.get("INDIA_CORPUS_ROOT") or os.environ.get("ENGINEERING_RAG_INDIA")
    return Path(root or env or DEFAULT_CORPUS_ROOT)


def corpus_available(root: Optional[str] = None) -> bool:
    """True when India corpus indexes + search scripts look present."""
    r = corpus_root(root)
    scripts = r / "scripts"
    return (
        r.is_dir()
        and (scripts / "retrieval.py").is_file()
        and (scripts / "search.py").is_file()
        and ((r / "indexes" / "sections.json").is_file()
             or (r / "indexes" / "documents.json").is_file())
    )


def parse_omega_table_from_hit_text(text: str) -> Optional[dict]:
    """Parse Ω(SCBF/EBF) and Ω(SMRF) digits from §5.5 HIT text.

    Returns None unless both values are captured from the HIT (no invent).
    """
    if not text:
        return None
    m = _OMEGA_HIT_RE.search(text)
    if not m:
        return None
    try:
        scbf_ebf = float(m.group("scbf_ebf"))
        smrf = float(m.group("smrf"))
    except (TypeError, ValueError):
        return None
    if scbf_ebf <= 0 or smrf <= 0:
        return None
    return {
        "SCBF": scbf_ebf,
        "EBF": scbf_ebf,
        "SMRF": smrf,
        "raw_match": m.group(0),
    }


def _miss(**extra) -> dict:
    out = {
        "found": False,
        "source": "is18168",
        "Omega": None,
        "omega": None,
        "cite": IS18168_CITE,
        "Elm_rule": IS18168_ELM_RULE,
        "section_id": IS18168_SECTION,
        "doc": IS18168_DOC,
    }
    out.update(extra)
    return out


def _query_exact_section_55(root: Path) -> dict:
    """Run corpus exact_section 5.5 for IS_18168_2023. Returns raw run_query dict."""
    scripts = str(root / "scripts")
    import sys
    if scripts not in sys.path:
        sys.path.insert(0, scripts)
    from retrieval import Corpus  # type: ignore

    corpus = Corpus(root)
    return corpus.run_query(
        {
            "type": "exact_section",
            "query": IS18168_SECTION,
            "doc": IS18168_DOC,
            "want_commentary": False,
            "context_neighbors": 0,
            "limit": 3,
            "bypass_cache": False,
        }
    )


def fetch_is18168_section_55(*, root: Optional[str] = None) -> dict:
    """Fetch raw §5.5 HIT (or found:false). Does not select an SFRS Ω."""
    r = corpus_root(root)
    if not corpus_available(r):
        return _miss(note="India corpus unavailable", reason="corpus_unavailable")
    try:
        result = _query_exact_section_55(r)
    except Exception as ex:  # pragma: no cover - IO / import failures
        return _miss(note="IS 18168 §5.5 query failed: %s" % ex, reason="query_error")
    if not result or not result.get("found"):
        return _miss(note="IS 18168 §5.5 exact_section miss", reason="section_miss",
                     raw_found=bool(result and result.get("found")))
    hits = result.get("hits") or []
    hit = hits[0] if hits else {}
    text = hit.get("text") or ""
    parsed = parse_omega_table_from_hit_text(text)
    if not parsed:
        return _miss(
            note="§5.5 HIT present but Ω digits not parseable from HIT text",
            reason="parse_miss",
            section_id=hit.get("section_id") or IS18168_SECTION,
            hit_id=hit.get("id"),
            pdf_page=hit.get("pdf_page"),
        )
    return {
        "found": True,
        "source": "is18168",
        "cite": IS18168_CITE,
        "Elm_rule": IS18168_ELM_RULE,
        "section_id": hit.get("section_id") or IS18168_SECTION,
        "hit_id": hit.get("id"),
        "pdf_page": hit.get("pdf_page"),
        "doc": hit.get("doc") or IS18168_DOC,
        "title": hit.get("title"),
        "text": text,
        "omega_by_sfrs": {
            "SCBF": parsed["SCBF"],
            "EBF": parsed["EBF"],
            "SMRF": parsed["SMRF"],
        },
        "raw_match": parsed.get("raw_match"),
        "note": "IS 18168 §5.5 HIT — Ω table parsed from corpus text",
    }


def fetch_is18168_omega(sfrs_type, *, root: Optional[str] = None,
                        section_hit: Optional[dict] = None) -> dict:
    """Return corpus_hit for resolve_Omega0 for the given SFRS type.

    Parameters
    ----------
    sfrs_type : str
        Job system label (SCBF / EBF / SMRF and aliases). Dual / unmapped → miss.
    root : optional corpus root override
    section_hit : optional pre-fetched ``fetch_is18168_section_55`` result
        (tests inject a fixture HIT without touching the live corpus).

    Returns
    -------
    dict with found:true only when HIT + parse + SFRS map succeed.
    Keys: found, source, Omega/omega, cite, sfrs, Elm_rule, section_id, ...
    """
    sfrs = normalize_sfrs(sfrs_type)
    if sfrs is None:
        return _miss(
            sfrs=None,
            requested=sfrs_type,
            note=(
                "IS 18168 §5.5 Ω tabulated for SCBF/EBF/SMRF only; "
                "SFRS %r unmapped or dual — honest found:false"
                % (sfrs_type,)
            ),
            reason="sfrs_unmapped",
        )

    sec = section_hit if isinstance(section_hit, dict) else fetch_is18168_section_55(root=root)
    if not sec or sec.get("found") is not True:
        out = _miss(
            sfrs=sfrs,
            requested=sfrs_type,
            note=(sec or {}).get("note") or "IS 18168 §5.5 miss",
            reason=(sec or {}).get("reason") or "section_miss",
        )
        if isinstance(sec, dict):
            for k in ("hit_id", "pdf_page", "section_id"):
                if sec.get(k) is not None:
                    out[k] = sec[k]
        return out

    by = sec.get("omega_by_sfrs") or {}
    # Prefer structured fields from helper; verify they match HIT text digits.
    om = by.get(sfrs)
    if om is None and sec.get("text"):
        parsed = parse_omega_table_from_hit_text(sec["text"])
        if parsed:
            om = parsed.get(sfrs)
            by = {k: parsed[k] for k in ("SCBF", "EBF", "SMRF")}
    if om is None:
        return _miss(
            sfrs=sfrs,
            requested=sfrs_type,
            note="§5.5 HIT found but no Ω for SFRS %s" % sfrs,
            reason="sfrs_value_miss",
            section_id=sec.get("section_id"),
            hit_id=sec.get("hit_id"),
        )

    # Re-verify digits appear in HIT text when text is present (anti-invent)
    text = sec.get("text") or ""
    if text:
        parsed = parse_omega_table_from_hit_text(text)
        if not parsed or abs(float(parsed[sfrs]) - float(om)) > 1e-9:
            return _miss(
                sfrs=sfrs,
                requested=sfrs_type,
                note="Ω value failed HIT-text verification",
                reason="verify_fail",
            )

    return {
        "found": True,
        "source": "is18168",
        "Omega": float(om),
        "omega": float(om),
        "cite": sec.get("cite") or IS18168_CITE,
        "sfrs": sfrs,
        "requested": sfrs_type,
        "Elm_rule": IS18168_ELM_RULE,
        "section_id": sec.get("section_id") or IS18168_SECTION,
        "hit_id": sec.get("hit_id"),
        "pdf_page": sec.get("pdf_page"),
        "doc": sec.get("doc") or IS18168_DOC,
        "omega_by_sfrs": dict(by) if by else None,
        "note": (
            "Ω from live IS 18168 §5.5 corpus HIT for %s (ELm=Ω·EL); "
            "digits parsed from HIT text — not invented."
            % sfrs
        ),
    }


def resolve_Omega0_with_is18168(cfg=None, *, sfrs_type=None, root=None,
                                section_hit=None, **resolve_kw) -> dict:
    """Fetch IS 18168 Ω HIT for SFRS then pass corpus_hit into resolve_Omega0.

    ``sfrs_type`` defaults to cfg['system'] / seis.system when omitted.
    Extra kwargs are forwarded to ``resolve_Omega0`` (eor_* etc.).
    """
    from india_seismic_gates import resolve_Omega0

    cfg = cfg or {}
    seis = cfg.get("seis") if isinstance(cfg.get("seis"), dict) else {}
    plan = cfg.get("load_plan") if isinstance(cfg.get("load_plan"), dict) else {}
    summ = plan.get("seismic_summary") if isinstance(plan.get("seismic_summary"), dict) else {}
    sfrs = sfrs_type or cfg.get("system") or seis.get("system") or summ.get("system")
    hit = fetch_is18168_omega(sfrs, root=root, section_hit=section_hit)
    return resolve_Omega0(cfg, corpus_hit=hit, **resolve_kw)
