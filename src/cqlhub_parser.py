"""Parse a CQL-Hub YAML query file into a HuntQuery.

CQL-Hub (github.com/ByteRay-Labs/Query-Hub) stores ONE detection per .yml file:
  name, description, author, log_sources, cs_required_modules, tags,
  mitre_ids (optional), cql (a YAML block scalar), explanation.

We map that to the same HuntQuery the HuntPack parser produces, so the rest of
the runner (select / run / review / manifest) treats both sources identically.
A short metadata comment block is prepended to the CQL so MITRE ids, required
modules, and any lookup dependency are visible in --dry-run and the report.
"""
from __future__ import annotations

from pathlib import Path

import yaml

from .huntpack_parser import HuntQuery

# Heuristics that suggest the query correlates against an NG-SIEM lookup file
# (which must be uploaded to the tenant first, or the query errors).
_LOOKUP_HINTS = (".csv", "readfile(", "definetable(")


def references_lookup(cql: str) -> bool:
    low = cql.lower()
    return any(h in low for h in _LOOKUP_HINTS)


def _as_list(v) -> list[str]:
    if not v:
        return []
    return [str(x) for x in v] if isinstance(v, (list, tuple)) else [str(v)]


def parse_cqlhub(path: str | Path) -> list[HuntQuery]:
    """Parse one CQL-Hub .yml file -> a single-item list of HuntQuery."""
    path = Path(path)
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    cql = str(data.get("cql") or "").strip()
    if not cql:
        return []

    name = str(data.get("name") or path.stem).strip()
    mitre = _as_list(data.get("mitre_ids") or data.get("mitre"))
    modules = _as_list(data.get("cs_required_modules"))
    tags = _as_list(data.get("tags"))

    header = [f"// {name}"]
    if mitre:
        header.append(f"// MITRE: {', '.join(mitre)}")
    if modules:
        header.append(f"// Requires modules: {', '.join(modules)}")
    if tags:
        header.append(f"// Tags: {', '.join(tags)}")
    if references_lookup(cql):
        header.append("// NOTE: references a lookup file — upload it to NG-SIEM "
                      "first (see the CQL-Hub lookup-files/) or this query may error")
    query = "\n".join(header) + "\n" + cql

    return [HuntQuery(id=path.stem, label="Q1", title=name,
                      query=query, source=path.name)]


if __name__ == "__main__":  # python -m src.cqlhub_parser <file.yml>
    import sys
    for f in sys.argv[1:]:
        for q in parse_cqlhub(f):
            print(f"[{q.label}] {q.title}\n{q.query}\n")
