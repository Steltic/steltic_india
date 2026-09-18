# India RAG collection → corpus stem map

Canonical map lives in `steltic/india_collections.py`. Corpus: `/workspace/engineering_rag_india`.

| collection= | stem |
|-------------|------|
| `engineering_standards_IS800` | `IS_800_2007` |
| `engineering_standards_IS808` | `IS_808_2021` |
| `engineering_standards_IS816` | `IS_816_1969` |
| `engineering_standards_IS9595` | `IS_9595_1996` |
| `engineering_standards_IS4000` | `IS_4000_1992` |
| `engineering_standards_IS1161` | `IS_1161_2014` |
| `engineering_standards_IS2062` | `IS_2062_Part_1_2025` |
| `engineering_standards_IS875_P1` | `IS_875_Part_1_2026` |
| `engineering_standards_IS875_P2` | `IS_875_Part_2_1987` |
| `engineering_standards_IS875_P3` | `IS_875_Part_3_2015` |
| `engineering_standards_IS875_P4` | `IS_875_Part_4_1987` |
| `engineering_standards_IS875_P5` | `IS_875_Part_5_1987` |
| `engineering_standards_IS1893` | `IS_1893_Part_1_2016` |

Load collections (IS875_P* + IS1893) are **mandatory every job** before writing `cfg['load_plan']`.
