"""H32 (HR-D-09): a negated "EXAMPLE" in a free-text note no longer forces example_only; only cite / label /
source / basis leaves are scanned."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "steel_engine"))

import india_seismic_gates as G

CFG = {"system": "SCBF", "R": 4.5, "zone": "IV"}


def test_notes_are_exempt():
    for k in ("notes", "note", "detail_note", "design_notes"):
        cfg = dict(CFG, **{k: "EXAMPLE EOR json not used."})
        assert G.example_label_hits(cfg) == [], k
        assert G.design_status(cfg)["status"] != "example_only"
    assert G.example_label_hits({"notes": ["EXAMPLE only in a list note"]}) == []


def test_provenance_leaves_still_scanned():
    for k in ("R_cite", "label", "source", "basis", "Vb_source"):
        assert G.example_label_hits(dict(CFG, **{k: "EXAMPLE placeholder"})), k
    assert G.design_status(dict(CFG, R_cite="EXAMPLE / not-for-construction memo"))["status"] == "example_only"
