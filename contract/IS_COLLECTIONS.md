# India RAG collection → corpus stem map

Canonical map: `steltic/india_collections.py`. Corpus: `/workspace/engineering_rag_india`.

Hosted `rag_server` may register either `engineering_standards_IS*` **or** `engineering_standards_IS*` —
both resolve to the same stem via `stem_for_collection()`.

| collection= (either prefix) | stem |
|-----------------------------|------|
| `…_IS800` | `IS_800_2007` |
| `…_IS808` | `IS_808_2021` |
| `…_IS816` | `IS_816_1969` |
| `…_IS9595` | `IS_9595_1996` |
| `…_IS4000` | `IS_4000_1992` |
| `…_IS1161` | `IS_1161_2014` |
| `…_IS2062` / `…_IS2062_P1` | `IS_2062_Part_1_2025` |
| `…_IS875_P1` … `…_IS875_P5` | `IS_875_Part_1_2026` … `IS_875_Part_5_1987` |
| `…_IS1893` / `…_IS1893_P1` | `IS_1893_Part_1_2016` |

Load collections (IS875_P* + IS1893) are **mandatory every job** before writing `cfg['load_plan']`.

`job_tools._collection_stem()` posts `stem` / `doc` on the RAG payload so the hosted registry
can resolve India corpus aliases without re-hardcoding formulas.
