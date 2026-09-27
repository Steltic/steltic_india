"""D05 contract lint: every top-level cfg key the HR engine reads -- cfg.get("key"), cfg.setdefault("key"),
cfg["key"] or (cfg or {}).get("key") in steel_engine/*.py -- is named somewhere in contract/*.md or README*.md.

Allowlist (documented here, deliberately minimal): keys with a leading underscore.  They are engine-private caches
and run markers written by the engine itself (_sw_by_level, _pw_by_level, _units_converted, _pressures_converted,
_rsa_element_forces, _soft_storey_flags, _tir_screen, _vertical_setback, _irregular, _gold, ...); an agent never
sets them.  Every other key -- including legacy keys India jobs must not use -- is documented (the legacy ones in
README.md, 'Engine cfg keys outside the India contract').  Fix a failure by documenting the key, not by widening
the allowlist.

Also (HR-B-20): every field of an info['links'] record that design_pipeline.ebf_links_model_data reads is named in
contract/AGENT_START.md."""
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ENGINE = ROOT / "steel_engine"

KEY_RE = re.compile(r"""(?:\bcfg|(?<!\w)\(cfg or \{\}\))(?:\.get\(|\.setdefault\(|\[)\s*(['"])([A-Za-z_][A-Za-z0-9_]*)\1\s*[,)\]]""")


def is_allowlisted(key):
    return key.startswith("_")


def engine_keys():
    keys = {}
    for f in sorted(ENGINE.glob("*.py")):
        for i, line in enumerate(f.read_text(encoding="utf-8", errors="replace").splitlines(), 1):
            for m in KEY_RE.finditer(line):
                keys.setdefault(m.group(2), []).append("%s:%d" % (f.name, i))
    return keys


def docs_text():
    parts = [p.read_text(encoding="utf-8") for p in sorted((ROOT / "contract").glob("*.md"))]
    parts += [p.read_text(encoding="utf-8") for p in sorted(ROOT.glob("README*.md"))]
    return "\n".join(parts)


def _named(key, text):
    return re.search(r"(?<![A-Za-z0-9_])%s(?![A-Za-z0-9_])" % re.escape(key), text) is not None


def test_scanner_is_not_vacuous():
    keys = engine_keys()
    assert len(keys) > 150, len(keys)
    for k in ("diaphragm_stiffness", "member_overrides", "roof_planes", "R_x", "scwb_pu_basis",
              "braces_after_dead_load", "delegated_design", "flexible_diaphragm_analysis"):
        assert k in keys, k


def test_every_engine_cfg_key_is_documented():
    keys, text = engine_keys(), docs_text()
    missing = {k: v[:3] for k, v in sorted(keys.items()) if not is_allowlisted(k) and not _named(k, text)}
    assert not missing, "cfg keys read by the engine but named in no contract/*.md or README*.md: %s" % missing


def test_allowlist_is_only_private_keys():
    keys = engine_keys()
    allow = sorted(k for k in keys if is_allowlisted(k))
    assert all(k.startswith("_") for k in allow)
    assert len(allow) <= 15, allow          # a growing private-key list is a smell: document public keys instead


def test_ebf_links_schema_named_in_agent_start():
    src = (ENGINE / "design_pipeline.py").read_text(encoding="utf-8")
    i0 = src.index("def ebf_links_model_data")
    body = src[i0:src.index("\ndef ", i0 + 10)]
    fields = set(re.findall(r"""\bln(?:\.get\(|\[)\s*["']([A-Za-z_][A-Za-z0-9_]*)["']""", body))
    assert {"tag", "e_mm", "brace_tags", "end_stiffeners"} <= fields, fields
    agent = (ROOT / "contract" / "AGENT_START.md").read_text(encoding="utf-8")
    missing = sorted(f for f in fields if not _named(f, agent))
    assert not missing, "info['links'] fields not in AGENT_START: %s" % missing
