# IS 808 shapes database — gaps

**Built:** from IS 808:2021 Tables 1–5 via `pdftotext -layout` → `build_is808_shapes.py`
**Output:** `steel_engine/is808_shapes.csv` (267 rows)
**Parse errors/skipped lines:** 1

## Ingested
- Table 1: Medium / Wide flange beams (MB, WB)
- Table 2: Junior / Light beams (JB, LB)
- Table 3: Narrow parallel flange beams (NPB …×…×mass)
- Table 4: Wide parallel flange beams (WPB …×…×mass)
- Table 5: Column / heavy beam sections (SC, HB)

## NOT ingested this pass (found:false for auto-CSV)
- Tables 6–8: channels (JC, LC, MC, MPC) — layout/column count differs; TODO
- Tables 9–12: equal/unequal angles (ISA / ∠) — different property columns; TODO
- Table 13: bearing piles (PBP) — deferred with channels/angles
- Annex A/B formula-only custom sections — agent must compute via RAG, not invent

## Units
Pipeline still kip+inch. CSV properties are converted from IS 808 SI multipliers;
`A_si_mm2` / `Izz_si_mm4` / `Iyy_si_mm4` retain SI for audit. Full SI engine is a separate deferred item.

## Lookup labels
- `MB200`, `LB150`, `SC250`, …
- Duplicate designations (two `WB200`) become `WB200X28.8` / `WB200X52.09` (mass suffix)
- Parallel flange: `NPB100X55X8.1`, `WPB600X300X128.79`
