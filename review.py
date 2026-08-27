#!/usr/bin/env python3
r"""Review HuntPack-Runner output — a fast, readable summary of a run.

Reads the JSON result files a run produced and shows, at a glance, which
queries fired and what they matched. Two outputs:

  * a console summary (always) — every query, hit counts, timing, grouped
    by pack; queries WITH hits are marked;
  * an HTML report (default) — a self-contained dark-themed page with the
    summary plus, for each query that fired, its CQL and an events table.

Needs no credentials and no virtualenv — it only reads local files
(standard library only).

Usage:
  python review.py                       # newest run under output/
  python review.py output\20260709-113237
  python review.py output\...\SomePack   # a single pack folder
  python review.py --no-html             # console only
  python review.py --open                # also open the report in a browser
"""
from __future__ import annotations

import argparse
import glob
import html
import json
import re
import sys
import webbrowser
from datetime import datetime
from pathlib import Path


def _natural_key(s: str) -> str:
    """Sort key so Q2 < Q10 (zero-pad digit runs), not the string default Q10 < Q2."""
    return re.sub(r"\d+", lambda m: m.group().zfill(12), s or "").lower()

for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

ROOT = Path(__file__).resolve().parent
OUTPUT_DIR = ROOT / "output"
LOGSCALE_DEFAULT_CAP = 200   # non-aggregating queries return up to this many rows


def latest_run() -> Path | None:
    runs = [p for p in OUTPUT_DIR.glob("*") if p.is_dir()]
    return max(runs, key=lambda p: p.name) if runs else None


def load_results(target: Path) -> list[dict]:
    """Load every result JSON under target (recursively), sorted by pack then label."""
    results = []
    for f in sorted(target.rglob("*.json")):
        if f.name == "summary.json":      # run manifest, not a query result
            continue
        try:
            d = json.loads(f.read_text(encoding="utf-8"))
            d["_file"] = str(f)
            results.append(d)
        except Exception as exc:
            print(f"[!] Skipping {f}: {exc}", file=sys.stderr)
    results.sort(key=lambda d: (d.get("source", ""), _natural_key(d.get("label", ""))))
    return results


def console_summary(results: list[dict], target: Path) -> None:
    total = len(results)
    hits = [d for d in results if d.get("event_count", 0) > 0]
    print(f"\nRun: {target.name}   ({total} queries, {len(hits)} with hits)\n")
    current = None
    for d in results:
        src = d.get("source", "")
        if src != current:
            print(f"  {src}")
            current = src
        n = d.get("event_count", 0)
        mark = "**" if n > 0 else "  "
        cap = " (capped)" if n >= d.get("row_limit", LOGSCALE_DEFAULT_CAP) else ""
        dur = d.get("duration_seconds", "?")
        print(f"   {mark} {d.get('label',''):<4} {n:>4} events{cap:<9} {dur:>6}s  {d.get('title','')}")
    print()
    if hits:
        print("Queries with hits — review these first:")
        for d in hits:
            print(f"   {d.get('label','')}  {d.get('title','')}  ({d.get('event_count')} events)")
        print()


def _table(events: list[dict]) -> str:
    if not events:
        return "<p class='muted'>no events</p>"
    cols: list[str] = []
    for ev in events:
        for k in ev:
            if k not in cols:
                cols.append(k)
    head = "".join(f"<th>{html.escape(c)}</th>" for c in cols)
    rows = []
    for ev in events:
        cells = "".join(
            f"<td>{html.escape(str(ev.get(c, '')))}</td>" for c in cols
        )
        rows.append(f"<tr>{cells}</tr>")
    return (f"<div class='tw'><table><thead><tr>{head}</tr></thead>"
            f"<tbody>{''.join(rows)}</tbody></table></div>")


def build_html(results: list[dict], target: Path) -> str:
    total = len(results)
    hits = [d for d in results if d.get("event_count", 0) > 0]
    gen = datetime.now().strftime("%Y-%m-%d %H:%M")

    sum_rows = []
    for i, d in enumerate(results, 1):
        n = d.get("event_count", 0)
        cls = "hit" if n > 0 else ""
        cap = " <span class='cap'>capped</span>" if n >= d.get("row_limit", LOGSCALE_DEFAULT_CAP) else ""
        anchor = f"<a href='#q{i}'>{html.escape(d.get('label',''))}</a>" if n > 0 else html.escape(d.get("label", ""))
        sum_rows.append(
            f"<tr class='{cls}'><td>{anchor}</td>"
            f"<td>{html.escape(d.get('source',''))}</td>"
            f"<td class='num'>{n}{cap}</td>"
            f"<td class='num'>{d.get('duration_seconds','?')}s</td>"
            f"<td>{html.escape(d.get('title',''))}</td></tr>"
        )

    findings = []
    for i, d in enumerate(results, 1):
        if d.get("event_count", 0) <= 0:
            continue
        n = d.get("event_count", 0)
        rl = d.get("row_limit", LOGSCALE_DEFAULT_CAP)
        cap_note = (f"<p class='cap-note'>Showing {n} events — this hit the row cap "
                    f"of {rl}, so results are likely truncated. Raise <code>--limit</code>, "
                    f"tighten the query, or narrow the time window.</p>") if n >= rl else ""
        findings.append(
            f"<section id='q{i}' class='finding'>"
            f"<h3>{html.escape(d.get('label',''))} · {html.escape(d.get('title',''))} "
            f"<span class='badge'>{n} events</span></h3>"
            f"<div class='src'>{html.escape(d.get('source',''))}</div>"
            f"{cap_note}"
            f"<details><summary>CQL</summary><pre>{html.escape(d.get('query',''))}</pre></details>"
            f"{_table(d.get('events', []))}"
            f"</section>"
        )

    finding_html = "".join(findings) or "<p class='muted'>No queries returned events in this run.</p>"

    return f"""<!doctype html><html><head><meta charset="utf-8">
<title>HuntPack review — {html.escape(target.name)}</title>
<style>
:root{{--bg:#0d1117;--surface:#161b22;--surface2:#21262d;--border:#30363d;--text:#e6edf3;--muted:#8b949e;--accent:#02c39a;--red:#f85149;}}
*{{box-sizing:border-box;margin:0;padding:0}}
body{{background:var(--bg);color:var(--text);font-family:-apple-system,'Segoe UI',sans-serif;font-size:14px;line-height:1.5;padding:24px;max-width:1200px;margin:0 auto}}
h1{{font-size:20px;color:var(--accent);margin-bottom:2px}}
.meta{{color:var(--muted);font-size:12px;margin-bottom:18px}}
h2{{font-size:14px;margin:22px 0 8px;color:var(--text)}}
table{{width:100%;border-collapse:collapse;font-size:12px}}
th{{background:var(--surface2);color:var(--muted);text-transform:uppercase;font-size:9.5px;letter-spacing:.05em;padding:6px 9px;text-align:left;position:sticky;top:0}}
td{{padding:5px 9px;border-bottom:1px solid var(--border);vertical-align:top;white-space:nowrap}}
.num{{text-align:right;font-variant-numeric:tabular-nums}}
tr.hit td{{background:rgba(2,195,154,.06)}}
tr.hit td:first-child a{{color:var(--accent);font-weight:700}}
.cap{{color:var(--red);font-size:9px;text-transform:uppercase;border:1px solid var(--red);border-radius:3px;padding:0 4px;margin-left:4px}}
.summary{{background:var(--surface);border:1px solid var(--border);border-radius:6px;overflow:hidden}}
.finding{{background:var(--surface);border:1px solid var(--border);border-radius:6px;padding:14px;margin:14px 0}}
.finding h3{{font-size:13px;margin-bottom:2px}}
.badge{{background:rgba(2,195,154,.15);color:var(--accent);font-size:10px;padding:1px 7px;border-radius:10px;margin-left:6px}}
.src{{color:var(--muted);font-size:11px;margin-bottom:8px}}
.cap-note{{color:#d29922;font-size:11px;background:rgba(210,153,34,.08);border:1px solid rgba(210,153,34,.3);border-radius:4px;padding:6px 9px;margin:6px 0}}
details{{margin:8px 0}}summary{{cursor:pointer;color:var(--muted);font-size:11px}}
pre{{background:#010409;border:1px solid var(--border);border-radius:4px;padding:9px;font-family:'Cascadia Code',Consolas,monospace;font-size:11px;overflow-x:auto;margin-top:6px;white-space:pre}}
.tw{{overflow-x:auto;border:1px solid var(--border);border-radius:4px;margin-top:8px}}
.muted{{color:var(--muted)}}
kbd{{color:var(--accent)}}
</style></head><body>
<h1>HuntPack Review</h1>
<div class="meta">Run <kbd>{html.escape(target.name)}</kbd> · {total} queries · {len(hits)} with hits · generated {gen}</div>
<h2>Summary</h2>
<div class="summary"><table><thead><tr><th>Query</th><th>Pack</th><th>Events</th><th>Time</th><th>Detection</th></tr></thead>
<tbody>{''.join(sum_rows)}</tbody></table></div>
<h2>Findings ({len(hits)})</h2>
{finding_html}
</body></html>"""


def main() -> int:
    p = argparse.ArgumentParser(description="Review HuntPack-Runner output files.")
    p.add_argument("path", nargs="?", help="Run folder or pack folder (default: newest run).")
    p.add_argument("--no-html", action="store_true", help="Console summary only.")
    p.add_argument("--open", action="store_true", help="Open the HTML report in a browser.")
    args = p.parse_args()

    target = Path(args.path) if args.path else latest_run()
    if not target or not target.exists():
        print("[!] No run found. Point me at an output folder, e.g. "
              "python review.py output\\<timestamp>", file=sys.stderr)
        return 2

    results = load_results(target)
    if not results:
        print(f"[!] No result JSON files under {target}", file=sys.stderr)
        return 1

    console_summary(results, target)

    if not args.no_html:
        report = target / "review.html"
        report.write_text(build_html(results, target), encoding="utf-8")
        print(f"HTML report: {report}")
        if args.open:
            webbrowser.open(report.as_uri())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
