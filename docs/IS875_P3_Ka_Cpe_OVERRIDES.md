# IS 875 Part 3 — Ka / Cpe policy (S6) — corpus-prefer

**Date:** 2026-09-19 Asia/Bangkok (ICT)  
**Module:** `steel_engine/india_wind_tables.py`  
**Stem:** `IS_875_Part_3_2015` · collection `engineering_standards_IS875_P3`  
**QFM note:** `/workspace/handoff/qfm/IS875_P3_OCR_reingest_2026-09-19.md`

## Policy (after OCR reingest HIT)

| Table | Prefer | Fallback (corpus `found:false` only) | Never |
|-------|--------|--------------------------------------|-------|
| **Table 4 Ka** (cl.7.2.2) | Corpus **exact_table 4** | In-repo breakpoints ≤10 m²→1.0, 25→0.9, ≥100→0.8 + linear interp (`ka_for_area_m2`) | Invent Ka outside Table 4 |
| **Table 5 Cpe walls** (cl.7.3.3.1) | Corpus **exact_table 5** (HIT 2026-09-19) | In-repo `cpe_walls()` / `TABLE_5_CPE_WALLS` | Invent Cpe; legacy Docling OCR cells |
| **Tables 6 / 7 / 11 / 18 / 21 / 22 / 29** | Corpus **exact_table** (now HIT) | — (no in-repo duplicates; retrieve or `found:false`) | Invent roof/member Cp/Cf |

When RAG returns `found:true`, **corpus is authoritative**.  
`india_wind_tables.py` agent overrides are **fallback only**.

## Agent usage

```python
from india_wind_tables import resolve_ka, resolve_cpe_walls, override_policy
# or: from india_loads import resolve_ka, resolve_cpe_walls

# After RAG exact_table 4 / 5:
resolve_ka(40.0, corpus_hit)          # uses corpus when found:true
resolve_cpe_walls(0.8, 1.2, 0, corpus_hit)

# Only if corpus found:false:
resolve_ka(40.0, {"found": False})    # in-repo fallback
resolve_cpe_walls(0.8, 1.2, 0, {"found": False})
```

See `override_policy()` / `CORPUS_LIVE_WIND_TABLES` for the machine-readable summary.
