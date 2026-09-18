# USA ASCE 7-22 engine notes — NOT authoritative on steltic_india

This file previously documented embedded ASCE 7-22 load/combo math in the USA HR engine.

**steltic_india removes that as the primary load path.** Loads come from LIVE RAG of
IS 875 Parts 1–5 and IS 1893 Part 1:2016 into `cfg['load_plan']` (`steel_engine/india_loads.py`).
`engine3d.wind_forces()` raises; `design_pipeline.combos()` reads only `load_plan`.

Historical USA detail (if needed for cross-jurisdiction reading) remains in
`Steltic/steltic` — do not re-hardcode it here.
