"""US-code residue scanner for the India agent contract and India reports (WP2.10 / WP0.3).

Two regexes:
  * CONTRACT_RESIDUE_RE -- the spec WP2.10 CI regex for the assembled system prompt.
  * REPORT_RESIDUE_RE   -- ASCE/AISC/IBC/ACI/AWS/OSHA terms and imperial unit labels in reports.

Deliberate refinement of the spec regex (reported to the lead): the bare patterns ``12\\.8\\.`` and
``12\\.12`` would also flag IS 800:2007 Section 12 clauses (12.8.3.1 SCBF brace connections,
12.12 column bases) that the India contract MUST cite.  Every clause number written as
"IS 800 12.x" / "IS 800:2007 12.x" / "IS 800 cl. 12.x" is therefore removed before matching; a bare
"12.8.x" / "12.12" (the ASCE 7 numbering the old contract used) is still a hit.
Text inside a fenced USA-only block is ignored:  ``<!-- USA-ONLY -->`` ... ``<!-- /USA-ONLY -->``
or a fenced code block opened with ```usa-only.
"""
from __future__ import annotations

import re

CONTRACT_RESIDUE_RE = re.compile(
    r"ASCE|7-22|A360|A341|A358|Cd·|psf|kip|12\.12|12\.8\.|\bSDC\b|Risk Category")

REPORT_RESIDUE_RE = re.compile(
    r"\bASCE\b|\bAISC\b|\bIBC\b|ACI\s*318|\bAWS\b|\bOSHA\b|Risk Category|Seismic Design Category|"
    r"\bSDC\b|\bSDS\b|\bSD1\b|Ω0|Ω₀|Omega0|\bCd\b|Eq\.\s*12\.\d|Table\s*12\.\d|§\s*12\.\d|"
    r"Ch\.\s*(?:16|26|27|28|29|30|31)\b|\bpsf\b|\bmph\b|\bkips?\b|\bksi\b|\d\s*ft\b|\d\s*in\b|"
    r"KLL|DG\s*11|0\.002α|\bFpx\b|ρ\s*=\s*1\.3|A992|RyFy|IEBC|ASCE\s*41")

_IS800_CLAUSE = re.compile(r"IS\s*800(?::\s*2007)?\s*(?:cl\.?|clause|§)?\s*\(?12(?:\.\d+)+\)?", re.I)
_IS800_LIST = re.compile(r"IS\s*800(?::\s*2007)?\s+(?:cl\.?\s*|§\s*)?12(?:\.\d+)+(?:\s*(?:,|/|and|or|&)\s*12(?:\.\d+)+)+", re.I)
_FENCE_HTML = re.compile(r"<!--\s*USA-ONLY\s*-->.*?<!--\s*/USA-ONLY\s*-->", re.S | re.I)
_FENCE_MD = re.compile(r"```usa-only.*?```", re.S | re.I)
_TAGS = re.compile(r"<[^>]+>")


def _strip(text: str) -> str:
    t = _FENCE_HTML.sub(" ", text or "")
    t = _FENCE_MD.sub(" ", t)
    t = _IS800_LIST.sub(" ", t)
    t = _IS800_CLAUSE.sub(" ", t)
    return t


def contract_hits(text: str) -> list:
    t = _strip(text)
    return [t[max(0, m.start() - 30): m.end() + 30].replace("\n", " ") for m in CONTRACT_RESIDUE_RE.finditer(t)]


def residue_hits(html_or_text: str) -> list:
    """Hits of REPORT_RESIDUE_RE in visible report text (tags, scripts, styles removed)."""
    t = re.sub(r"<(script|style)[^>]*>.*?</\1>", " ", html_or_text or "", flags=re.S | re.I)
    # quotations of earlier residue findings (the consistency section) are not themselves residue
    t = re.sub(r"<span class=['\"]residue-quote['\"]>.*?</span>", " ", t, flags=re.S)
    t = re.sub(r"data:[a-z/+]+;base64,[A-Za-z0-9+/=]+", " ", t)
    t = _TAGS.sub(" ", t)
    t = _strip(t)
    return [t[max(0, m.start() - 30): m.end() + 30].replace("\n", " ") for m in REPORT_RESIDUE_RE.finditer(t)]
