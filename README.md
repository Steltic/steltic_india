# Steltic India (HR)

A free, open-source **India (IS/BIS) hot-rolled steel-design agent** that runs locally.
Paste a design brief and watch the agent build an OpenSees model + a stamped-style HTML report +
an interactive 3D viewer — **bringing your own LLM** (API base-url + key, held in memory only).

This repository is the **India HR variant** of [Steltic/steltic](https://github.com/Steltic/steltic)
(USA AISC/ASCE). Do **not** confuse the two. Design authority: **IS 800:2007** (+ IS 808, IS 816/9595,
IS 4000, IS 2062, IS 1161). Loads: **IS 875 Parts 1–5** and **IS 1893 Part 1:2016**: the job's load VALUES
(Vb, zone / Z, I, R, imposed and dead loads, snow, Cpe for the building) are retrieved LIVE via RAG every job into
`cfg['load_plan']`. The engine carries transcriptions of the code tables it computes with — IS 875-3 Tables 4 / 5 /
6, 6.3.4 k4 and 7.3.2.2 Cpi (`india_wind_tables`), IS 1893 Tables 3 / 7 / 9 and the Table 8 keyword rules
(`india_seismic`, `india_seismic_gates`), IS 800 tables (`india_is800`, `india_connections`) and IS 18168 Table 1
Ry / Ru (`india_is18168`). Retrieved values take precedence where the engine accepts them (e.g. the Table 5
record passed to `lowrise_member_wind`), and `tests/test_fix_H15_tables_vs_corpus.py` diffs the IS 875-3 Table 5 /
6 transcriptions against the corpus cell by cell.

```
browser ──▶ FastAPI app (localhost) ──▶ your LLM (key in app memory, never stored)
                 │  parses tool calls
                 ▼
           sandbox executor (run_python only) — Docker when available
                 │
           steel engine + OpenSees ─▶ report.html + viewer_3d.html
```

> **Not for construction.** Every output is produced by your own AI model, may be incomplete or
> incorrect, and must be independently checked and sealed by a licensed professional engineer before
> any use for design, construction, or permitting. See [DISCLAIMER.md](DISCLAIMER.md).

## For videos and demonstrations see [stelticai.com](https://stelticai.com)

## Install & run

With [uv](https://docs.astral.sh/uv/) (recommended):

```bash
uv tool install --python 3.12 steltic-india
steltic-india                 # starts on http://127.0.0.1:8000 and opens your browser
```

Or from a checkout:

```bash
git clone https://github.com/Steltic/steltic_india && cd steltic_india
python -m venv .venv && . .venv/bin/activate
pip install -e .
./run_local.sh               # http://localhost:8000
```

First run: open **Settings**, enter your provider's **API base URL**, **API key**, and **model**.
Point `RAG_API_URL` at your IS corpus (see [IS corpus](#is-corpus-standards-grounding) below; never a USA
AISC / ASCE corpus). Then paste a brief and click **Design building**.

Offline smoke test: set Model to `MOCK`.

## Critical difference from USA steltic: loads are retrieved

| | USA `steltic` | India `steltic_india` |
|--|--|--|
| Design code | AISC 360/341/358 | IS 800:2007 family |
| Loads | ASCE 7-22 **computed inside the engine** | IS 875 + IS 1893 **RAG every job → cfg['load_plan']** |
| Corpus | the USA corpus (AISC / ASCE / AISI) | your IS corpus (BIS documents), built in the Steltic hub |

The agent must call `search_engineering_standards` against `engineering_standards_IS875_P*` and
`engineering_standards_IS1893` before `pipeline.design_and_report`, then write retrieved factors into
`cfg['load_plan']` (schema in `steel_engine/india_loads.py`). Preflight fails closed if that is missing.

## Sandbox

Same as USA: `EXECUTOR=auto|docker|subprocess`. Binds to 127.0.0.1; no auth — don't expose the port.
Data under `DATA_DIR` (default OS user-data `Steltic` / override for India installs if desired).

## IS corpus (standards grounding)

The agent grounds every load value, clause and factor in **your IS corpus, built in the Steltic hub from your own
licensed BIS PDFs** (see [`CORPUS_FIX_LLM_INSTRUCTIONS.md`](CORPUS_FIX_LLM_INSTRUCTIONS.md)). BIS standards are
copyrighted: no corpus is published with Steltic, and each user builds their own. Recommended workflow:

1. In the Steltic hub, convert your licensed BIS PDFs (first pass, Docling): **Standards** / **Convert**, then
   **Rebuild index** and **Validate**.
2. Zip that first-pass corpus with your PDFs and `CORPUS_FIX_LLM_INSTRUCTIONS.md`, and give them to a frontier LLM
   agent with code execution (the smarter the better). It fixes OCR, tables, figures and metadata, and returns a
   fixed corpus.
3. Replace the hub's corpus with it, then **Rebuild index** and **Validate**.
4. Point the engines at it: the hub sets `RAG_API_URL` (and `INDIA_CORPUS_ROOT`) for every engine it starts;
   standalone, set them yourself:

```bash
export RAG_API_URL=http://127.0.0.1:<port>/query      # the hub's IS corpus server (POST /query, GET /healthz)
export INDIA_CORPUS_ROOT=/path/to/your/is_corpus       # the corpus folder (documents/, indexes/, scripts/)
```

**Without a corpus** the engine still runs, but every standards retrieval comes back `found: false`. The gates
never turn a miss into a value: each found:false `load_plan.retrieval` row needs an EOR record
`{value, source, cite, verify: True}` (on the row or in `cfg['eor_assumptions']`), which the report discloses as
an engineer's assumption to verify; a row without one keeps the job PARTIAL. The engine's own table
transcriptions still compute, and the corpus cross-check tests skip.

**How the agent queries it:** [`contract/QUERYING_IS_CORPUS.md`](contract/QUERYING_IS_CORPUS.md) is part of the
design agent's prompt. It covers one document per call, an exact clause or table id when the provision is known,
full text only to navigate, the IS id formats and traps, and what each kind of "not found" means. The
`search_engineering_standards` tool takes the same fields (`type`, `doc`, `query`, `purpose`, `context_neighbors`),
applies the policy to every call, and records the form it sent. The same file ships in `steltic_CFS_india` and
`steltic_nonlinear_india`.

### Retrieval details

Set `RAG_API_URL` / `RAG_API_TOKEN` / optionally `RAG_ALIASES_FILE` (default `$INDIA_CORPUS_ROOT/indexes/aliases.json`).
`INDIA_CORPUS_ROOT` is the one place the corpus location is decided (the app's aliases and the engine's own
corpus lookups, e.g. `india_omega_is18168`). The search tool reports `not_found_kind` = `no_specification_index`,
`document_not_in_corpus`, `not_tabulated` (the corpus answered: no table row, e.g. a town in neither Annex A nor
Annex E), `server_error` (`found: None`, retry — never evidence of absence) or `term_absent_from_document`; hits carry
`exact_match` / `also_found_in`, and `retrieval_errors` lists failed rungs. Every hit is saved under the job's `rag/`
(keyed on collection, clause, type, query and a content hash; never overwritten).

## Design contract and capabilities

The agent contract is `contract/AGENT_START.md` + `contract/README_AGENT.md` (cfg key index) +
`contract/IS800_WORKED_METHOD.md`. Beyond the regular grid model the engine supports: per-direction R
(`R_x` / `R_y`), the IS 1893 Table 5(ii) flexible-diaphragm 3-D analysis of re-entrant plans (`diaphragm_stiffness`),
true-slope pitched roofs (`roof_planes`) and roof regions, the JSON frame builder with chevron EBF links
(`frame_build.py`, `example_build_ebf.py`), several seismically separated units in one job
(`pipeline.design_units`), the IS 875-3 10.3 across-wind load case, gusseted / embedded column bases, IS 18168
column splices, and an optional erection sequence (braces after the dead load).

### Engine cfg keys outside the India contract

The engine is shared with the USA heritage code and still reads a few keys that India jobs must not use (the
contract lint `tests/test_fix_D05_contract_lint.py` checks that they are named here): `sdc`, `rho`, `drift_relief_16_1_2`,
`use_asce7_engine_loads`, `force_kip_in`, `metric` / `si_native`, `code_jurisdiction` / `code_region` (aliases of
`jurisdiction`), `Fy` (the viewer's legacy yield default), `L_roof` (legacy report label; India uses `Lr`),
`Omega0` / `Om0` / `Omega0_source` / `Omega0_cite` / `Omega0_found` (the legacy overstrength provenance API — India
jobs use the IS 18168 5.5 / IS 800 12.2.3 combinations and never declare it), `r_source` (alias of `R_source`),
`imf_as_smrf` (maps an 'IMF' label; IMF has no Indian basis and is refused), `dual_check` / `softstorey_check` /
`torsion_check` (flags of the legacy quick `run()` path; the India gates screen these themselves), and the legacy
connection worksheet inputs `base_plate_geometry` / `column_base_geometry` / `base_plate` / `splice_geometry` /
`connection_rag_capacities` (India jobs declare `cfg['connections']`). Keys with a leading underscore are
engine-private caches.

## Product shape (unchanged)

brief → OpenSees → `report.html` + `viewer_3d.html` + agent contract (`contract/AGENT_START.md`).

## License

MIT — see LICENSE / NOTICE / DISCLAIMER.md.
