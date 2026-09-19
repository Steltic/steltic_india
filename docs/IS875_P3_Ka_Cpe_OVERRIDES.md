# IS 875 Part 3 — Ka / Cpe override policy (S6)

**Date:** 2026-09-19 Asia/Bangkok (ICT)  
**Module:** `steel_engine/india_wind_tables.py`  
**Stem:** `IS_875_Part_3_2015` · collection `engineering_standards_IS875_P3`

## Policy

| Table | Prefer | Fallback / override | Never |
|-------|--------|---------------------|-------|
| **Table 4 Ka** (cl.7.2.2) | Corpus **exact_table 4** (QFM: reliable as of 2026-09-19) | In-repo breakpoints ≤10 m²→1.0, 25→0.9, ≥100→0.8 + linear interp (`ka_for_area_m2`) | Invent Ka outside Table 4 |
| **Table 5 Cpe walls** (cl.7.3.3.1) | **Verified in-repo** `cpe_walls()` / `TABLE_5_CPE_WALLS` | — | **Docling OCR cells** for design Cpe; invent outside shipped bands |

When corpus OCR of Table 4/5 is clean and RAG returns `found:true`, **corpus remains authoritative**.  
Overrides exist so agents do not invent numbers when OCR is noisy (Table 5) or retrieval is unavailable (Table 4 fallback).

## Provenance

* PDF: BIS `IS_875_Part_3_2015.pdf` (workspace `INDIA_STEEL/pdfs/`).
* Table 4: pdftotext + QFM `Table_4_Ka_recovered.md`; corpus exact_table 4 OK.
* Table 5: transcribed from PDF table figure (raster page); Docling CSV/MD for that page is garbled.

## Agent usage

```python
from india_wind_tables import ka_for_area_m2, cpe_walls, override_policy

# Ka — only if RAG exact_table 4 missed:
ka_for_area_m2(40.0)   # interpolate; cite as fallback

# Cpe walls — use override for design (do not trust Docling OCR):
cpe_walls(h_over_w=0.8, l_over_w=1.2, theta_deg=0)
# found:false if geometry outside shipped bands → stop; do not invent
```

See `override_policy()` for the machine-readable summary.
