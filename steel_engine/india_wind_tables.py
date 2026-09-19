"""IS 875 (Part 3) : 2015 Ka / Cpe helpers (S6) — corpus-prefer, in-repo fallback.

Policy (QFM 2026-09-19 OCR reingest — Tables 5/6/7/11/18/21/22/29 corpus-HIT):
  * Table 4 Ka — prefer corpus RAG ``exact_table 4``. In-repo breakpoints are **fallback only**
    when corpus returns found:false / unavailable. Never invent beyond the three points
    (interpolate between them only).
  * Table 5 wall Cpe — prefer corpus RAG ``exact_table 5`` (clean after OCR reingest).
    In-repo ``TABLE_5_CPE_WALLS`` / ``cpe_walls()`` are **fallback only** when corpus
    found:false. Do NOT invent Cpe; do NOT use legacy Docling OCR cells if they reappear.
  * Other wind-path tables now live in corpus (prefer exact_table): 6, 7, 11, 18, 21, 22, 29.
  * Never invent Ka/Cpe outside corpus / shipped fallback tables.

Provenance / QFM note:
  * ``/workspace/handoff/qfm/IS875_P3_OCR_reingest_2026-09-19.md``
  * PDF: /workspace/INDIA_STEEL/pdfs/IS_875_Part_3_2015.pdf (BIS)
  * Table 4: QFM ``Table_4_Ka_recovered.md``; corpus exact_table 4 OK.
  * Table 5: QFM recovered page 015 + ``Table_5_recovered``; corpus exact_table 5 HIT.
"""
from __future__ import annotations

STEM = "IS_875_Part_3_2015"
COLLECTION = "engineering_standards_IS875_P3"

# ---------------------------------------------------------------------------
# Table 4 — Area Averaging Factor Ka (Clause 7.2.2)
# Prefer corpus exact_table 4; these breakpoints are fallback only.
# ---------------------------------------------------------------------------
TABLE_4_KA = {
    "found": True,
    "stem": STEM,
    "clause": "7.2.2",
    "table": "Table 4",
    "title": "Area Averaging Factor (Ka)",
    "source": "corpus_preferred",  # exact_table 4 reliable as of 2026-09-19 QFM
    "fallback_ok": True,
    "provenance": (
        "IS 875 (Part 3) : 2015 Table 4 / cl.7.2.2. "
        "Prefer RAG exact_table 4 from engineering_standards_IS875_P3. "
        "Hardcoded breakpoints match QFM-verified recovery (≤10→1.0, 25→0.9, ≥100→0.8)."
    ),
    # (A_m2_max_or_exact, Ka) — breakpoints for lookup / interpolation
    "breakpoints": [
        {"A_m2": 10.0, "Ka": 1.0, "rule": "A <= 10"},
        {"A_m2": 25.0, "Ka": 0.9, "rule": "A == 25 (interpolate from 10 and 100)"},
        {"A_m2": 100.0, "Ka": 0.8, "rule": "A >= 100"},
    ],
    "note": "Linear interpolation for intermediate values of A is permitted (Table 4 Note *).",
}


def ka_for_area_m2(A_m2: float, *, allow_fallback: bool = True) -> dict:
    """Return Ka for tributary area A (m²).

    Prefer calling this only as fallback when RAG Table 4 is missing/noisy.
    Does not invent beyond the three shipped breakpoints (+ linear interpolation).
    """
    if not allow_fallback:
        return {
            "found": False,
            "Ka": None,
            "cite": "Table 4 fallback disabled — retrieve exact_table 4 from corpus",
            "source": "refused",
        }
    A = float(A_m2)
    if A <= 10.0:
        ka = 1.0
        rule = "A <= 10 m²"
    elif A >= 100.0:
        ka = 0.8
        rule = "A >= 100 m²"
    else:
        # Linear interpolation between (10, 1.0) and (100, 0.8); 25 → 0.9 is on that line
        # (1.0 - 0.8) * (100-A)/(100-10) + 0.8, or piecewise via 25 for clarity:
        if A <= 25.0:
            ka = 1.0 + (0.9 - 1.0) * (A - 10.0) / (25.0 - 10.0)
            rule = "linear interp 10→25 m²"
        else:
            ka = 0.9 + (0.8 - 0.9) * (A - 25.0) / (100.0 - 25.0)
            rule = "linear interp 25→100 m²"
    return {
        "found": True,
        "Ka": round(ka, 6),
        "A_m2": A,
        "rule": rule,
        "cite": "IS 875 (Part 3) : 2015 Table 4 / cl.7.2.2 (in-repo fallback; prefer corpus exact_table 4)",
        "source": "india_wind_tables.TABLE_4_KA",
        "table_meta": {k: TABLE_4_KA[k] for k in ("stem", "clause", "table", "provenance")},
    }


# ---------------------------------------------------------------------------
# Table 5 — External Pressure Coefficients Cpe for walls of rectangular clad
# buildings (Clause 7.3.3.1). Verified from PDF figure — NOT from Docling OCR.
# Surfaces A/B/C/D and Local Cpe per the code table layout.
# ---------------------------------------------------------------------------
# Each row: height_ratio band, plan_ratio band, wind_angle_deg -> Cpe A,B,C,D + local
# Bands use inclusive upper bounds matching the printed table wording.

def _row(hw, lw, theta, A, B, C, D, local):
    return {
        "h_over_w": hw,
        "l_over_w": lw,
        "theta_deg": theta,
        "Cpe": {"A": A, "B": B, "C": C, "D": D},
        "Cpe_local": local,
    }


# Verified transcription of IS 875 (Part 3) : 2015 Table 5 (PDF page 15 figure).
TABLE_5_CPE_WALLS = {
    "found": True,
    "stem": STEM,
    "clause": "7.3.3.1",
    "table": "Table 5",
    "title": "External Pressure Coefficients (Cpe) for Walls of Rectangular Clad Buildings",
    "source": "corpus_preferred",  # exact_table 5 HIT after 2026-09-19 QFM OCR reingest
    "fallback_ok": True,
    "ocr_trust": False,  # legacy Docling cells still untrusted if they reappear
    "provenance": (
        "IS 875 (Part 3) : 2015 Table 5 / cl.7.3.3.1. "
        "Prefer RAG exact_table 5 from engineering_standards_IS875_P3 "
        "(QFM OCR reingest 2026-09-19 HIT). "
        "In-repo rows match QFM Table_5_recovered — use only when corpus found:false. "
        "h = height to eaves/parapet; l = greater plan dim; w = lesser plan dim."
    ),
    "definitions": {
        "h": "height to eaves or parapet",
        "l": "greater horizontal dimension of building",
        "w": "lesser horizontal dimension of building",
        "theta_0": "wind normal to face A (along w)",
        "theta_90": "wind normal to face C (along l)",
    },
    "rows": [
        # h/w ≤ 1/2
        _row("<=0.5", "1<l/w<=1.5", 0, +0.7, -0.2, -0.5, -0.5, -0.8),
        _row("<=0.5", "1<l/w<=1.5", 90, -0.5, -0.5, +0.7, -0.2, -0.8),
        _row("<=0.5", "1.5<l/w<=4", 0, +0.7, -0.25, -0.6, -0.6, -1.0),
        _row("<=0.5", "1.5<l/w<=4", 90, -0.5, -0.5, +0.7, -0.1, -1.0),
        # 1/2 < h/w ≤ 3/2
        _row("0.5<h/w<=1.5", "1<=l/w<=1.5", 0, +0.7, -0.25, -0.6, -0.6, -1.1),
        _row("0.5<h/w<=1.5", "1<=l/w<=1.5", 90, -0.6, -0.6, +0.7, -0.25, -1.1),
        _row("0.5<h/w<=1.5", "1.5<=l/w<4", 0, +0.7, -0.3, -0.7, -0.7, -1.1),
        _row("0.5<h/w<=1.5", "1.5<=l/w<4", 90, -0.5, -0.5, +0.7, -0.1, -1.1),
        # 3/2 < h/w ≤ 6
        _row("1.5<h/w<=6", "1<l/w<=1.5", 0, +0.8, -0.25, -0.8, -0.8, -1.2),
        _row("1.5<h/w<=6", "1<l/w<=1.5", 90, -0.8, -0.8, +0.8, -0.25, -1.2),
        _row("1.5<h/w<=6", "1.5<=l/w<=4", 0, +0.7, -0.4, -0.7, -0.7, -1.2),
        _row("1.5<h/w<=6", "1.5<=l/w<=4", 90, -0.5, -0.5, +0.8, -0.1, -1.2),
        # h/w ≥ 6 (discrete plan ratios in the printed table)
        _row(">=6", "l/w=1.0", 0, +0.95, -1.25, -0.7, -0.7, -1.25),
        _row(">=6", "l/w=1.0", 90, -0.7, -0.7, +0.95, -1.25, -1.25),
        _row(">=6", "l/w=1.5", 0, +0.95, -1.85, -0.9, -0.9, -1.25),
        _row(">=6", "l/w=1.5", 90, -0.8, -0.8, +0.9, -0.85, -1.25),
        _row(">=6", "l/w=2", 0, +0.85, -0.75, -0.75, -0.75, -1.25),
        _row(">=6", "l/w=2", 90, -0.75, -0.75, +0.85, -0.75, -1.25),
    ],
}


def _hw_band(h_over_w: float) -> str | None:
    r = float(h_over_w)
    if r <= 0.5:
        return "<=0.5"
    if r <= 1.5:
        return "0.5<h/w<=1.5"
    if r <= 6.0:
        return "1.5<h/w<=6"
    return ">=6"


def _lw_band(h_band: str, l_over_w: float) -> str | None:
    """Map plan ratio into the printed Table 5 band for the given height band."""
    r = float(l_over_w)
    if h_band == "<=0.5":
        if 1.0 < r <= 1.5:
            return "1<l/w<=1.5"
        if 1.5 < r <= 4.0:
            return "1.5<l/w<=4"
        return None
    if h_band == "0.5<h/w<=1.5":
        if 1.0 <= r <= 1.5:
            return "1<=l/w<=1.5"
        if 1.5 <= r < 4.0:
            return "1.5<=l/w<4"
        return None
    if h_band == "1.5<h/w<=6":
        if 1.0 < r <= 1.5:
            return "1<l/w<=1.5"
        if 1.5 <= r <= 4.0:
            return "1.5<=l/w<=4"
        return None
    # h/w >= 6: discrete printed plan ratios only — no invention
    if abs(r - 1.0) < 1e-9:
        return "l/w=1.0"
    if abs(r - 1.5) < 1e-9:
        return "l/w=1.5"
    if abs(r - 2.0) < 1e-9:
        return "l/w=2"
    return None


def cpe_walls(h_over_w: float, l_over_w: float, theta_deg: float = 0.0) -> dict:
    """Lookup Table 5 wall Cpe. Returns found:false if outside shipped bands (no invention)."""
    theta = float(theta_deg)
    if abs(theta - 0.0) > 1e-9 and abs(theta - 90.0) > 1e-9:
        return {
            "found": False,
            "Cpe": None,
            "cite": "Table 5 override only ships θ = 0° and 90° — retrieve other angles from RAG/PDF",
            "source": "refused_angle",
        }
    theta_key = 0 if abs(theta - 0.0) <= 1e-9 else 90
    hw = _hw_band(h_over_w)
    lw = _lw_band(hw, l_over_w) if hw else None
    if not hw or not lw:
        return {
            "found": False,
            "Cpe": None,
            "h_over_w": float(h_over_w),
            "l_over_w": float(l_over_w),
            "cite": (
                "Geometry outside shipped Table 5 override bands — do not invent Cpe; "
                "consult IS 875 Part 3 PDF / specialist literature (Table 5 note)."
            ),
            "source": "refused_band",
            "table_meta": {k: TABLE_5_CPE_WALLS[k] for k in ("stem", "clause", "table", "provenance")},
        }
    for row in TABLE_5_CPE_WALLS["rows"]:
        if row["h_over_w"] == hw and row["l_over_w"] == lw and row["theta_deg"] == theta_key:
            return {
                "found": True,
                "Cpe": dict(row["Cpe"]),
                "Cpe_local": row["Cpe_local"],
                "h_over_w": float(h_over_w),
                "l_over_w": float(l_over_w),
                "theta_deg": theta_key,
                "band": {"h_over_w": hw, "l_over_w": lw},
                "cite": "IS 875 (Part 3) : 2015 Table 5 / cl.7.3.3.1 (in-repo fallback; prefer corpus exact_table 5)",
                "source": "india_wind_tables.TABLE_5_CPE_WALLS",
                "table_meta": {k: TABLE_5_CPE_WALLS[k] for k in ("stem", "clause", "table", "provenance")},
            }
    return {
        "found": False,
        "Cpe": None,
        "cite": "No Table 5 override row matched — refuse invented Cpe",
        "source": "refused_miss",
    }


# Common terrain category labels (Table 2 context) — descriptive only; k2 still from RAG/PDF.
TERRAIN_CATEGORIES = {
    "found": True,
    "stem": STEM,
    "clause": "6.3.2.1",
    "note": (
        "Terrain category descriptions for agent orientation. "
        "k2 multipliers remain Table 2 — retrieve from corpus/PDF; not duplicated here to avoid drift."
    ),
    "categories": {
        1: "Exposed open terrain with few or no obstructions; z0,1 = 0.002 m",
        2: "Open terrain with well-scattered obstructions generally 1.5–10 m; z0,2 = 0.02 m",
        3: "Terrain with numerous closely spaced obstructions up to 10 m (towns); z0,3 = 0.2 m",
        4: "Terrain with numerous large high closely spaced obstructions (city centres); z0,4 = 2.0 m",
    },
}


# Tables now corpus-HIT for the wind path (QFM OCR reingest 2026-09-19).
CORPUS_LIVE_WIND_TABLES = (4, 5, 6, 7, 11, 18, 21, 22, 29)
QFM_OCR_NOTE = "/workspace/handoff/qfm/IS875_P3_OCR_reingest_2026-09-19.md"


def _corpus_found(hit) -> bool:
    """True when an agent/RAG exact_table payload is usable (found:true with content)."""
    if not isinstance(hit, dict):
        return False
    if hit.get("found") is False:
        return False
    if hit.get("found") is True:
        return True
    # tolerate alternate shapes: non-empty text/rows with content
    if hit.get("text") or hit.get("rows") or hit.get("Ka") is not None or hit.get("Cpe"):
        return True
    return False


def resolve_ka(A_m2: float, corpus_hit=None, *, allow_fallback: bool = True) -> dict:
    """Prefer corpus exact_table 4; demote in-repo Ka to fallback when corpus found:false."""
    if _corpus_found(corpus_hit):
        out = dict(corpus_hit)
        out.setdefault("found", True)
        out.setdefault("source", "corpus_exact_table_4")
        out.setdefault(
            "cite",
            out.get("cite") or "IS 875 (Part 3) : 2015 Table 4 (corpus exact_table 4)",
        )
        out["A_m2"] = float(A_m2)
        out["resolved_via"] = "corpus"
        return out
    fb = ka_for_area_m2(A_m2, allow_fallback=allow_fallback)
    fb["resolved_via"] = "fallback" if fb.get("found") else "refused"
    fb["corpus_found"] = False
    return fb


def resolve_cpe_walls(h_over_w: float, l_over_w: float, theta_deg: float = 0.0,
                      corpus_hit=None, *, allow_fallback: bool = True) -> dict:
    """Prefer corpus exact_table 5; demote in-repo wall Cpe to fallback when corpus found:false."""
    if _corpus_found(corpus_hit):
        out = dict(corpus_hit)
        out.setdefault("found", True)
        out.setdefault("source", "corpus_exact_table_5")
        out.setdefault(
            "cite",
            out.get("cite") or "IS 875 (Part 3) : 2015 Table 5 (corpus exact_table 5)",
        )
        out["h_over_w"] = float(h_over_w)
        out["l_over_w"] = float(l_over_w)
        out["theta_deg"] = float(theta_deg)
        out["resolved_via"] = "corpus"
        return out
    if not allow_fallback:
        return {
            "found": False,
            "Cpe": None,
            "cite": "Table 5 fallback disabled — retrieve exact_table 5 from corpus",
            "source": "refused",
            "resolved_via": "refused",
            "corpus_found": False,
        }
    fb = cpe_walls(h_over_w, l_over_w, theta_deg)
    fb["resolved_via"] = "fallback" if fb.get("found") else fb.get("source", "refused")
    fb["corpus_found"] = False
    return fb


def override_policy() -> dict:
    """Agent-facing policy summary for load_plan / wind RAG (corpus-prefer)."""
    return {
        "Ka_Table_4": {
            "prefer": "corpus exact_table 4 (reliable as of 2026-09-19 QFM)",
            "fallback": (
                "india_wind_tables.ka_for_area_m2 — breakpoints ≤10→1.0, 25→0.9, ≥100→0.8 "
                "only when corpus found:false"
            ),
            "never": "invent Ka outside Table 4 / interpolation note",
        },
        "Cpe_Table_5_walls": {
            "prefer": "corpus exact_table 5 (HIT after 2026-09-19 QFM OCR reingest)",
            "fallback": (
                "india_wind_tables.cpe_walls / TABLE_5_CPE_WALLS — only when corpus found:false"
            ),
            "do_not_use": "legacy Docling OCR cells for Table 5 design Cpe (if they reappear)",
            "never": "invent Cpe outside corpus / shipped fallback bands; found:false if outside",
        },
        "other_wind_tables_corpus_live": list(CORPUS_LIVE_WIND_TABLES),
        "qfm_note": QFM_OCR_NOTE,
        "corpus_when_clean": (
            "When RAG returns found:true for Table 4/5 (and 6/7/11/18/21/22/29 as needed), "
            "corpus is authoritative; in-repo tables are fallback only."
        ),
    }
