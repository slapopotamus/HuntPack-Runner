"""Extract CQL hunt queries from a HuntPack HTML report.

HuntPack HTML files render each CrowdStrike LogScale (CQL) query inside a
``<pre class="cql" id="cqlN">`` block, wrapped in a ``.query-card`` whose
``.qc-title`` holds the human-readable name (e.g. "Q1 · FortiGate new admin ...").
This module pulls those out into ``HuntQuery`` objects with the CQL text fully
HTML-unescaped and ready to send to the Falcon API.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from bs4 import BeautifulSoup


@dataclass
class HuntQuery:
    """A single CQL query extracted from a HuntPack."""

    id: str      # the <pre> element id, e.g. "cql1"
    label: str   # short label, e.g. "Q1"
    title: str   # full card title, e.g. "Q1 · FortiGate new admin ..."
    query: str   # full CQL text (comments included, HTML-unescaped)
    source: str  # source HuntPack filename

    @property
    def query_no_comments(self) -> str:
        """CQL with leading ``//`` comment lines stripped (rarely needed —
        LogScale accepts ``//`` comments, but handy for compact logging)."""
        lines = [ln for ln in self.query.splitlines()
                 if not ln.lstrip().startswith("//")]
        return "\n".join(lines).strip()


def _short_label(title: str, fallback_id: str) -> str:
    """Derive a short label like 'Q1' from a title such as 'Q1 · Foo ...'."""
    if title:
        first = title.replace("·", "·").split("·")[0].strip()
        if first:
            return first
    # Fall back to the element id: cql1 -> Q1
    digits = "".join(c for c in fallback_id if c.isdigit())
    return f"Q{digits}" if digits else fallback_id


def parse_huntpack(path: str | Path) -> list[HuntQuery]:
    """Parse a HuntPack HTML file and return its CQL queries in document order."""
    path = Path(path)
    html = path.read_text(encoding="utf-8", errors="replace")
    soup = BeautifulSoup(html, "html.parser")

    queries: list[HuntQuery] = []
    for idx, pre in enumerate(soup.select("pre.cql"), start=1):
        qid = pre.get("id") or f"cql{idx}"
        # get_text() returns the concatenated, HTML-unescaped text of all
        # child nodes (comment <span>s + literal query text), newlines intact.
        cql = pre.get_text().strip()
        if not cql:
            continue

        title = ""
        card = pre.find_parent(class_="query-card")
        if card is not None:
            title_el = card.select_one(".qc-title")
            if title_el is not None:
                title = title_el.get_text(strip=True)

        queries.append(
            HuntQuery(
                id=qid,
                label=_short_label(title, qid),
                title=title or qid,
                query=cql,
                source=path.name,
            )
        )
    return queries


if __name__ == "__main__":  # quick manual test: python -m src.huntpack_parser <file>
    import sys

    target = sys.argv[1] if len(sys.argv) > 1 else "huntpacks"
    files = [Path(target)] if Path(target).is_file() else sorted(Path(target).glob("*.html"))
    for f in files:
        qs = parse_huntpack(f)
        print(f"\n=== {f.name}: {len(qs)} queries ===")
        for q in qs:
            print(f"  [{q.label}] {q.title}")
