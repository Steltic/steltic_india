"""The agent is told HOW to query the IS corpus, and the tool takes the policy's fields.

contract/QUERYING_IS_CORPUS.md (the same file ships in steltic_CFS_india and steltic_nonlinear_india) is the
query instruction set; before it the India design prompt had a short table and no retrieval policy, and the
tool had no `type` / `doc`, so every run sent sentences."""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from steltic import contract                    # noqa: E402
from steltic.agent import TOOL_SPECS            # noqa: E402


def test_the_design_prompt_carries_the_query_instructions():
    t = contract.system_contract()
    assert "HOW TO QUERY THE IS CORPUS" in t and "[missing QUERYING_IS_CORPUS.md" not in t
    for must in ('"type": "exact_section"', "Table 9(a)", "not_tabulated", "context_neighbors",
                 "IS_1893_Part_1_2016", "declared"):
        assert must in t, must


def test_the_search_tool_takes_the_policy_fields():
    spec = next(s for s in TOOL_SPECS if s["function"]["name"] == "search_engineering_standards")["function"]
    props = spec["parameters"]["properties"]
    for f in ("type", "doc", "purpose", "context_neighbors", "want_commentary", "query"):
        assert f in props, f
    assert set(props["type"]["enum"]) >= {"exact_section", "exact_table", "fts"}
    assert "QUERYING_IS_CORPUS.md" in spec["description"]
