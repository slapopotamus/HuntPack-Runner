#!/usr/bin/env python3
"""Run HuntPack CQL queries against CrowdStrike Next-Gen SIEM / LogScale.

Examples
--------
  # List every query found in a HuntPack (no credentials needed):
  python run_hunt.py --huntpack huntpacks/FortiBleed-CVE-2026-24858-Hunt.html --list

  # Print the CQL that WOULD run, without touching the API:
  python run_hunt.py --huntpack huntpacks/FortiBleed-CVE-2026-24858-Hunt.html --dry-run

  # Run one query over the last 7 days:
  python run_hunt.py --huntpack huntpacks/FortiBleed-CVE-2026-24858-Hunt.html --query Q1

  # Run all queries, 24h lookback, against a specific repository:
  python run_hunt.py --huntpack huntpacks/FortiBleed-CVE-2026-24858-Hunt.html \
      --start 24h --repository search-all
"""
from __future__ import annotations

import argparse
import getpass
import hashlib
import json
import os
import re
import socket
import sys
import time
from datetime import datetime
from pathlib import Path

import yaml
from dotenv import load_dotenv

from src import huntpack_source, cqlhub_source
from src.huntpack_source import is_url
from src.huntpack_parser import parse_huntpack, HuntQuery
from src.cqlhub_parser import parse_cqlhub
from src.regions import base_url as region_base_url
from src.secure_io import restrict_dir, restrict_file

# Hunt titles contain em dashes / arrows (—, →). On a legacy Windows console
# (cp1252) printing those raises UnicodeEncodeError, so force UTF-8 output and
# fall back to a replacement char rather than crashing.
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

HUNTPACK_DIR = Path(__file__).resolve().parent / "huntpacks"
CQLHUB_DIR = Path(__file__).resolve().parent / "cqlhub"

# Two interchangeable query libraries behind one --source flag.
SOURCES = {"huntpack": huntpack_source, "cqlhub": cqlhub_source}
SOURCE_LABELS = {"huntpack": "HuntPack", "cqlhub": "CQL-Hub"}


def source_module(name: str):
    return SOURCES.get(name, huntpack_source)


def download_dir(name: str) -> Path:
    return CQLHUB_DIR if name == "cqlhub" else HUNTPACK_DIR


def parse_any(path: Path) -> list[HuntQuery]:
    """Dispatch to the right parser by file extension (.yml/.yaml = CQL-Hub)."""
    if str(path).lower().endswith((".yml", ".yaml")):
        return parse_cqlhub(path)
    return parse_huntpack(path)

LOGSCALE_MAX_ROWS = 20000    # table()'s maximum limit
DEFAULT_ROW_CAP = 200        # table()'s default row limit when none is given


def safe_result_filename(name: str, *, max_length: int = 120) -> str:
    """Return a portable filename stem for a saved query result.

    HuntPack query labels are author-controlled and can include punctuation that
    is valid in HTML but illegal in Windows filenames (for example ``\"``).
    Keep result saving independent of the label format so one malformed label
    cannot terminate an otherwise successful batch.
    """
    safe = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", name)
    safe = re.sub(r"\s+", " ", safe).strip(" .")
    safe = safe[:max_length].rstrip(" .")
    # Windows reserves these device names even when they have an extension.
    if not safe or safe.upper().split(".", 1)[0] in {
        "CON", "PRN", "AUX", "NUL", "COM1", "COM2", "COM3", "COM4",
        "COM5", "COM6", "COM7", "COM8", "COM9", "LPT1", "LPT2",
        "LPT3", "LPT4", "LPT5", "LPT6", "LPT7", "LPT8", "LPT9",
    }:
        return "result"
    return safe


def _table_span(q: str) -> tuple[int, int] | None:
    """Return [start, end) of the last top-level table(...) call, or None."""
    idx = q.rfind("table(")
    if idx == -1:
        return None
    i = idx + len("table(")
    depth = 1
    while i < len(q) and depth:
        if q[i] == "(":
            depth += 1
        elif q[i] == ")":
            depth -= 1
        i += 1
    return (idx, i) if depth == 0 else None


def apply_row_limit(query: str, n: int) -> str:
    """Make a query return up to n rows. Rewrites the trailing table(...) limit
    if present (that's where LogScale's 200-row default comes from), else
    appends `| head(n)`."""
    span = _table_span(query)
    if span:
        s, e = span
        inner = query[s:e]
        if re.search(r"limit\s*=\s*\d+", inner):
            inner = re.sub(r"limit\s*=\s*\d+", f"limit={n}", inner)
        else:
            inner = inner[:-1] + f", limit={n})"
        return query[:s] + inner + query[e:]
    return query.rstrip() + f"\n| head({n})"

ROOT = Path(__file__).resolve().parent
CONFIG_PATH = ROOT / "config.yaml"
OUTPUT_DIR = ROOT / "output"


def load_config() -> dict:
    cfg = {
        "region": "us-1",
        "repository": "search-all",
        "search": {"start": "7d", "end": "now",
                   "poll_interval_seconds": 2, "timeout_seconds": 300},
    }
    if CONFIG_PATH.exists():
        loaded = yaml.safe_load(CONFIG_PATH.read_text(encoding="utf-8")) or {}
        # shallow-merge, one level deep for 'search'
        for k, v in loaded.items():
            if isinstance(v, dict) and isinstance(cfg.get(k), dict):
                cfg[k].update(v)
            else:
                cfg[k] = v
    # Coerce the numeric search fields so a stringy YAML value fails here with a
    # clear message rather than deep inside the run.
    s = cfg["search"]
    for key, default in (("poll_interval_seconds", 2.0), ("timeout_seconds", 300.0)):
        try:
            s[key] = float(s.get(key, default))
        except (TypeError, ValueError):
            raise SystemExit(f"[!] config.yaml: search.{key} must be a number "
                             f"(got {s.get(key)!r}).")
    return cfg


def parse_index_spec(spec: str, max_index: int) -> list[int]:
    """Turn '9', '9-10', '1,3,5-7' into an ordered, de-duplicated list of
    1-based indices. Accepts commas or spaces as separators and normalises
    en/em dashes to '-'. Raises ValueError on bad tokens or out-of-range."""
    spec = spec.replace("–", "-").replace("—", "-")
    picked: list[int] = []
    for tok in spec.replace(",", " ").split():
        if "-" in tok.strip("-"):  # a range like 9-10
            a_str, b_str = tok.split("-", 1)
            a, b = int(a_str), int(b_str)
            step = 1 if b >= a else -1
            picked.extend(range(a, b + step, step))
        else:
            picked.append(int(tok))
    out: list[int] = []
    seen: set[int] = set()
    for i in picked:
        if not (1 <= i <= max_index):
            raise ValueError(f"index {i} is out of range (1..{max_index})")
        if i not in seen:
            seen.add(i)
            out.append(i)
    if not out:
        raise ValueError("no valid indices given")
    return out


def select_queries(queries: list[HuntQuery], wanted: list[str] | None) -> list[HuntQuery]:
    """Select queries by global list number (1-based, as shown by --list),
    a numeric range (5-8), or a Q-label / id (Q1, cql1). Numbers disambiguate
    when labels repeat across multiple packs."""
    if not wanted:
        return queries
    n = len(queries)
    order: list[int] = []          # 0-based indices, selection order, de-duped
    seen: set[int] = set()
    unmatched: list[str] = []

    def add(i0: int) -> None:
        if 0 <= i0 < n and i0 not in seen:
            seen.add(i0)
            order.append(i0)

    tokens = [p for w in wanted for p in w.split(",")]   # allow -q 1,3,5
    for tok in tokens:
        t = tok.strip().replace("–", "-").replace("—", "-")
        if not t:
            continue
        if re.fullmatch(r"\d+(-\d+)?", t):          # number or numeric range
            try:
                for idx in parse_index_spec(t, n):
                    add(idx - 1)
            except ValueError:
                unmatched.append(tok)
            continue
        tl = t.lower()                               # else match label / id
        matched = False
        for j, q in enumerate(queries):
            if q.label.lower() == tl or q.id.lower() == tl:
                add(j)
                matched = True
        if not matched:
            unmatched.append(tok)

    if unmatched:
        print(f"[!] No match for: {', '.join(unmatched)}", file=sys.stderr)
    return [queries[i] for i in order]


CHEATSHEET = r"""
============================================================================
  HuntPack-Runner  -  CHEAT SHEET   (run:  hunt --tldr)
============================================================================

TWO LIBRARIES  (choose with --source)
  huntpack  (default)   HTML packs, several queries each, newest-first
                        https://slapopotamus.github.io/HuntPack/
  cqlhub                ~150 YAML detections, one query each, A-Z
                        https://github.com/ByteRay-Labs/Query-Hub
  NOTE: long flags take TWO dashes (--list-remote). Only -i -q -f -l -h are single.

BROWSE A LIBRARY  (no credentials needed)
  hunt --list-remote                     List HuntPacks (numbered, newest first)
  hunt --source cqlhub --list-remote     List CQL-Hub detections (numbered, A-Z)

RUN FROM A LIBRARY  (by the numbers shown in --list-remote)
  hunt --pick 9                          One entry
  hunt --pick 9-10                       A range
  hunt --pick 1,3,5-7                    A mix
  hunt --latest 2                        The 2 newest (HuntPacks; cqlhub = first 2 A-Z)
  hunt --source cqlhub --pick 5-10       Same, from CQL-Hub
  (add --source cqlhub to any --pick / --latest / --list-remote to switch library)

RUN A URL OR LOCAL FILE  (source auto-detected by extension)
  hunt -f huntpacks\Pack.html            Local HuntPack
  hunt -f cqlhub\Query.yml               Local CQL-Hub query
  hunt -f https://.../SomePack.html      Pull + run a HuntPack URL
  hunt -f https://.../queries/Foo.yml    Pull + run a CQL-Hub URL
  hunt -f huntpacks                      Every .html / .yml in a folder

PICK SPECIFIC QUERIES  (-q, repeatable, comma-ok)
  hunt -f Pack.html -q 1-4               By list number / range
  hunt -f Pack.html -q Q1,Q5             By label
  (numbers come from --list; labels come from the pack)

PREVIEW & REVIEW  (no queries run)
  ... --list                             List the queries in the selection
  ... --dry-run                          Print the exact CQL that would run
  ... -i                                 Approve each query first (Y=yes n=skip a=all q=quit)
  python review.py --open                Open the newest run's HTML report
  python review.py output\<stamp>        Rebuild a report for an older run

TIME WINDOW & ROW LIMIT
  --start 24h   --start 90m   --start 7d   --start 30d
  --end 1d                                Window is [start .. end]; end defaults to now
  --limit 20000                           Raise LogScale's 200-row cap (max 20000)

OTHER FLAGS
  --region us-2                           Override Falcon cloud (config.yaml sets default)
  --repository search-all                 Override NG-SIEM repository
  --verbose                               Show full API error bodies
  hunt -h                                 Full argparse help

RESULTS  (written to output\<timestamp>\)
  <Pack>\Q#_id.json     per-query events         review.html    formatted report
  summary.json          run manifest (user/host/region/window/pack SHA256/status)
  ..\huntpack.log       one cumulative audit line per run

SETUP & CONFIG
  setup.bat             One-time install (venv + deps + guided key/region setup)
  python configure.py   Change API keys or region (secret hidden; .env locked down)
  run.bat               Open the ready-to-type window

AUTOMATION / SCHEDULING  (headless)
  Set FALCON_CLIENT_ID / FALCON_CLIENT_SECRET / FALCON_REGION as env vars, run
  without -i. Exit codes: 0 = ok | 1 = ran-with-failures | 2 = config/aborted.
  Alert on non-zero; parse summary.json for detail.

GOTCHAS
  - Use TWO dashes for long flags:  --list-remote  (not -list-remote).
  - "0 events" = success (the query ran, nothing matched).
  - "capped" = hit the row limit; raise --limit or tighten the query.
  - A broad query over search-all can take a while; you'll see "...running Ns"
    while it polls. It gives up at 300s (config.yaml search.timeout_seconds).
    Ctrl+C stops cleanly. Narrow with --repository or a shorter --start.
  - Some CQL-Hub queries use ?parameters (interactive inputs) and 400 with
    "No content was received" when run headless. They are flagged in --dry-run.
  - Some CQL-Hub queries need lookup CSVs uploaded to NG-SIEM first (flagged).
  - The online libraries are third-party; review with --dry-run or -i.

EXAMPLES
  hunt --source cqlhub --list-remote
  hunt --source cqlhub --pick 5-10 -i --start 24h
  hunt --latest 2 --start 7d
  hunt -f huntpacks\FortiBleed.html -q 1-4 --limit 20000
  python review.py --open
============================================================================
"""


def print_cheatsheet() -> None:
    print(CHEATSHEET)


def cmd_list(queries: list[HuntQuery]) -> None:
    print(f"\n{len(queries)} queries found:\n")
    width = len(str(len(queries)))
    multi = len({q.source for q in queries}) > 1
    for i, q in enumerate(queries, start=1):
        src = f"[{Path(q.source).stem}] " if multi else ""
        print(f"  {i:>{width}}. {src}{q.title}")
    print("\nSelect with -q <number>, a range (-q 5-8), or a label (-q Q1). "
          "Repeatable / comma-ok.")


def cmd_dry_run(queries: list[HuntQuery]) -> None:
    multi = len({q.source for q in queries}) > 1
    for i, q in enumerate(queries, start=1):
        src = f"[{Path(q.source).stem}] " if multi else ""
        print("\n" + "=" * 70)
        print(f"{i}. {src}{q.title}")
        print("=" * 70)
        print(q.query)
    print()


def _confirm_query(q: HuntQuery) -> str:
    """Interactive review prompt for one query → 'run' | 'skip' | 'all' | 'quit'."""
    print("\n" + "=" * 70)
    print(f"{Path(q.source).stem} · {q.label} — {q.title}")
    print("=" * 70)
    print(q.query)
    ans = input("\nRun this query? [Y]es / [n]o skip / [a]ll / [q]uit: ").strip().lower()
    if ans in ("q", "quit"):
        return "quit"
    if ans in ("a", "all"):
        return "all"
    if ans in ("n", "no", "s", "skip"):
        return "skip"
    return "run"


TRUST_NOTICE = (
    "[trust] HuntPacks pulled from the public library are third-party content; "
    "their CQL runs against your Falcon tenant.\n"
    "        Review unfamiliar packs first with --dry-run or run with "
    "--interactive. (This notice shows once.)"
)


def _maybe_trust_notice(from_remote: bool) -> None:
    """Print the third-party trust notice once, ever (marker under output/)."""
    if not from_remote:
        return
    marker = OUTPUT_DIR / ".trust_ack"
    if marker.exists():
        return
    print(TRUST_NOTICE, file=sys.stderr)
    try:
        OUTPUT_DIR.mkdir(exist_ok=True)
        marker.write_text("acknowledged\n", encoding="utf-8")
    except Exception:
        pass


def cmd_run(queries: list[HuntQuery], files: list[Path],
            cfg: dict, args: argparse.Namespace, from_remote: bool = False) -> int:
    # Import here so --list / --dry-run work without falconpy installed.
    from src.falcon_client import FalconHunter

    client_id = os.getenv("FALCON_CLIENT_ID")
    client_secret = os.getenv("FALCON_CLIENT_SECRET")
    if not client_id or not client_secret:
        print("[!] Missing FALCON_CLIENT_ID / FALCON_CLIENT_SECRET.\n"
              "    Run setup.bat / configure.py, or set them as environment variables.",
              file=sys.stderr)
        return 2

    region = args.region or os.getenv("FALCON_REGION") or cfg["region"]
    repository = args.repository or os.getenv("FALCON_REPOSITORY") or cfg["repository"]
    scfg = cfg["search"]
    start = args.start or scfg["start"]
    end = args.end or scfg["end"]

    # --interactive can't prompt without a terminal (e.g. scheduled runs).
    if args.interactive and not sys.stdin.isatty():
        print("[!] --interactive needs a terminal (stdin is not a TTY).", file=sys.stderr)
        return 2

    try:
        hunter = FalconHunter(
            client_id=client_id,
            client_secret=client_secret,
            region=region,
            repository=repository,
            poll_interval=float(scfg["poll_interval_seconds"]),
            timeout=float(scfg["timeout_seconds"]),
            verbose=args.verbose,
        )
    except ValueError as exc:                 # unknown region (S6)
        print(f"[!] {exc}", file=sys.stderr)
        return 2

    ok, msg = hunter.verify_auth()
    print(f"[*] {msg}")
    if not ok:
        return 2

    _maybe_trust_notice(from_remote)

    eff_limit = None
    if args.limit:
        eff_limit = max(1, min(args.limit, LOGSCALE_MAX_ROWS))
        if args.limit > LOGSCALE_MAX_ROWS:
            print(f"[*] --limit {args.limit} capped to LogScale max {LOGSCALE_MAX_ROWS}.")
    row_limit = eff_limit or DEFAULT_ROW_CAP

    print(f"[*] Region={region}  Repository={repository}  Window={start}..{end}  "
          f"Row limit={row_limit}\n")

    OUTPUT_DIR.mkdir(exist_ok=True)
    restrict_dir(OUTPUT_DIR)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    run_dir = OUTPUT_DIR / stamp
    run_dir.mkdir(parents=True, exist_ok=True)
    restrict_dir(run_dir)

    # Live progress while a search polls, so a slow query isn't mistaken for a
    # hang. In-place update on a real terminal only (skipped when redirected).
    show_progress = sys.stdout.isatty()
    clear_line = ("\r" + " " * 60 + "\r") if show_progress else ""
    if show_progress:
        hunter.on_poll = lambda elapsed: print(
            f"\r    ...running {elapsed:4.0f}s (Ctrl+C to stop)", end="", flush=True)

    summary: list[dict] = []          # per-query records; also feeds summary.json
    run_all = not args.interactive
    aborted = False
    total_t0 = time.monotonic()

    for q in queries:
        if args.interactive and not run_all:
            decision = _confirm_query(q)
            if decision == "quit":
                aborted = True
                print("[*] Aborted — remaining queries not run.")
                break
            if decision == "all":
                run_all = True
            elif decision == "skip":
                print(f"    skipped {q.label}")
                summary.append({"label": q.label, "source": q.source, "status": "skipped",
                                "event_count": 0, "duration_seconds": 0.0, "error": None})
                continue

        print(f"[>] {q.source} · {q.label} — {q.title}")
        exec_q = apply_row_limit(q.query, eff_limit) if eff_limit else q.query
        try:
            res = hunter.run(exec_q, label=q.label, title=q.title, start=start, end=end)
        except Exception as exc:      # isolate — one failure must not kill the batch
            print(clear_line, end="")
            print(f"    FAILED — unhandled error: {exc}", file=sys.stderr)
            summary.append({"label": q.label, "source": q.source, "status": "error",
                            "event_count": 0, "duration_seconds": 0.0,
                            "error": f"unhandled: {exc}"})
            continue

        print(clear_line, end="")
        if res.ok:
            cap = " (capped — raise --limit)" if res.event_count >= row_limit else ""
            print(f"    OK — {res.event_count} event(s){cap} in {res.duration:.1f}s")
            # One folder per pack so identical labels (Q1, Q1) never collide.
            pack_dir = run_dir / Path(q.source).stem
            pack_dir.mkdir(parents=True, exist_ok=True)
            result_name = safe_result_filename(f"{q.label}_{q.id}")
            out = pack_dir / f"{result_name}.json"
            out.write_text(json.dumps({
                "label": q.label, "title": q.title, "source": q.source,
                "query": exec_q, "event_count": res.event_count,
                "row_limit": row_limit,
                "duration_seconds": round(res.duration, 3),
                "events": res.events,
            }, indent=2, default=str), encoding="utf-8")
            restrict_file(out)
            status = "ok"
        else:
            print(f"    FAILED in {res.duration:.1f}s — {res.error}")
            status = "error"
        summary.append({"label": q.label, "source": q.source, "status": status,
                        "event_count": res.event_count,
                        "duration_seconds": round(res.duration, 3), "error": res.error})
    total_elapsed = time.monotonic() - total_t0

    # ---- console summary ----
    print("\n" + "=" * 70)
    print("SUMMARY")
    print("=" * 70)
    tags = {"ok": "OK ", "error": "ERR", "skipped": "SKIP"}
    current_source = None
    for rec in summary:
        if rec["source"] != current_source:
            print(f"\n  {rec['source']}")
            current_source = rec["source"]
        if rec["status"] == "ok":
            detail = f"{rec['event_count']} events"
        elif rec["status"] == "skipped":
            detail = "skipped"
        else:
            detail = f"FAILED: {rec['error']}"
        print(f"    {rec['label']:<4} {tags[rec['status']]:<4} "
              f"{rec['duration_seconds']:6.1f}s  {detail}")

    hits = sum(1 for r in summary if r["status"] == "ok" and r["event_count"] > 0)
    ran = sum(1 for r in summary if r["status"] == "ok")
    failed = sum(1 for r in summary if r["status"] == "error")
    skipped = sum(1 for r in summary if r["status"] == "skipped")
    print(f"\n  {len(summary)} queries · {ran} ran · {hits} with hits · "
          f"{failed} failed · {skipped} skipped · total {total_elapsed:.1f}s")
    print(f"\nResults saved under: {run_dir}")

    # ---- machine-readable manifest / audit trail (S5/P2) ----
    try:
        packs = []
        for fp in files:
            try:
                digest = hashlib.sha256(Path(fp).read_bytes()).hexdigest()
            except Exception:
                digest = None
            packs.append({"name": Path(fp).name, "sha256": digest})
        manifest = {
            "timestamp": datetime.now().isoformat(timespec="seconds"),
            "user": getpass.getuser(),
            "host": socket.gethostname(),
            "region": region, "repository": repository,
            "window": {"start": start, "end": end},
            "row_limit": row_limit,
            "interactive": bool(args.interactive),
            "aborted": aborted,
            "packs": packs,
            "queries": summary,
            "totals": {"queries": len(summary), "ran": ran, "hits": hits,
                       "failed": failed, "skipped": skipped,
                       "duration_seconds": round(total_elapsed, 3)},
        }
        mpath = run_dir / "summary.json"
        mpath.write_text(json.dumps(manifest, indent=2, default=str), encoding="utf-8")
        restrict_file(mpath)
        # Cumulative one-line audit trail across all runs (P5) — parseable by
        # scheduled/CI consumers without opening each run folder.
        logline = (f"{manifest['timestamp']} user={manifest['user']} "
                   f"host={manifest['host']} region={region} repo={repository} "
                   f"window={start}..{end} packs={len(packs)} "
                   f"queries={len(summary)} ran={ran} hits={hits} "
                   f"failed={failed} skipped={skipped} dir={run_dir.name}\n")
        logpath = OUTPUT_DIR / "huntpack.log"
        with logpath.open("a", encoding="utf-8") as fh:
            fh.write(logline)
        restrict_file(logpath)
    except Exception as exc:
        print(f"[!] (summary.json skipped: {exc})", file=sys.stderr)

    # ---- HTML review report ----
    try:
        from review import load_results, build_html
        report = run_dir / "review.html"
        report.write_text(build_html(load_results(run_dir), run_dir), encoding="utf-8")
        print(f"HTML report:         {report}")
    except Exception as exc:
        print(f"[!] (review report skipped: {exc})", file=sys.stderr)

    if aborted:
        return 2
    return 0 if failed == 0 else 1


def main() -> int:
    p = argparse.ArgumentParser(description="Run HuntPack CQL queries via the CrowdStrike API.")
    p.add_argument("--huntpack", "-f",
                   help="A HuntPack .html file, a directory of them, or a hunt URL "
                        "(https://slapopotamus.github.io/HuntPack/hunts/...). "
                        "URLs are downloaded into huntpacks/ and kept.")
    p.add_argument("--source", choices=["huntpack", "cqlhub"], default="huntpack",
                   help="Which online library --list-remote / --latest / --pick use: "
                        "huntpack (HTML packs, default) or cqlhub (ByteRay Query-Hub YAML). "
                        "A -f path/URL is auto-detected by extension regardless.")
    p.add_argument("--tldr", "--cheatsheet", action="store_true",
                   help="Print the full command cheat sheet and exit.")
    p.add_argument("--list-remote", action="store_true",
                   help="List every entry in the selected --source library and exit.")
    p.add_argument("--latest", type=int, metavar="N",
                   help="Pull the N most recently added hunts from the library and run them.")
    p.add_argument("--pick", metavar="SPEC",
                   help="Run library hunts by their --list-remote number(s): "
                        "e.g. --pick 9, --pick 9-10, --pick 1,3,5-7.")
    p.add_argument("--query", "-q", action="append",
                   help="Run only these queries — by list number (7), range (5-8), "
                        "or label (Q1). Repeatable and comma-ok: -q 5-8 or -q Q1,Q5.")
    p.add_argument("--list", "-l", action="store_true", help="List queries and exit.")
    p.add_argument("--dry-run", action="store_true", help="Print the CQL without running it.")
    p.add_argument("--interactive", "-i", action="store_true",
                   help="Review each query and confirm before it runs "
                        "([Y]es / [n]o skip / [a]ll / [q]uit). Needs a terminal.")
    p.add_argument("--verbose", action="store_true",
                   help="Show full API error responses (default: concise).")
    p.add_argument("--limit", type=int, metavar="N",
                   help=f"Return up to N rows per query (default {DEFAULT_ROW_CAP}, "
                        f"max {LOGSCALE_MAX_ROWS}). Raises LogScale's row cap so a "
                        f"noisy hit shows its true volume.")
    p.add_argument("--start", help="Lookback start (LogScale relative, e.g. 24h, 7d).")
    p.add_argument("--end", help="Window end (default: now).")
    p.add_argument("--region", help="Falcon region: us-1, us-2, eu-1, us-gov-1, us-gov-2.")
    p.add_argument("--repository", help="NG-SIEM repository (default: search-all).")
    args = p.parse_args()

    if args.tldr:
        print_cheatsheet()
        return 0

    load_dotenv(ROOT / ".env")
    cfg = load_config()

    if args.list_remote:
        src = source_module(args.source)
        try:
            library = src.list_library_by_date()
        except Exception as exc:
            print(f"[!] Primary listing failed ({exc}); trying fallback.", file=sys.stderr)
            try:
                library = src.list_library()
            except Exception as exc2:
                print(f"[!] Could not reach the {SOURCE_LABELS[args.source]} library: {exc2}",
                      file=sys.stderr)
                return 2
        has_dates = any(e.published for e in library)
        order = "newest first" if has_dates else "A-Z"
        print(f"\n{len(library)} {SOURCE_LABELS[args.source]} entries ({order}) — "
              f"{src.LIBRARY_URL}\n")
        width = len(str(len(library)))
        for i, e in enumerate(library, start=1):
            meta = f"{e.published}  " if has_dates else ""
            cat = f"[{e.category}] " if e.category and args.source == "huntpack" else ""
            print(f"  {i:>{width}}. {meta}{cat}{e.title}\n      {' ' * width}  {e.url}")
        print(f"\nRun by number:  python run_hunt.py --source {args.source} --pick 9-10")
        print("Or by URL:      python run_hunt.py -f <url>")
        return 0

    if not args.huntpack and not args.latest and not args.pick:
        print("[!] Provide a HuntPack with -f (local path, directory, or URL), "
              "use --latest N or --pick <numbers>, or --list-remote to browse.",
              file=sys.stderr)
        return 2

    from_remote = bool(args.latest or args.pick
                       or (args.huntpack and is_url(args.huntpack)))
    files: list[Path] = []
    if args.latest or args.pick:
        src = source_module(args.source)
        dest = download_dir(args.source)
        try:
            library = src.list_library_by_date()
        except Exception as exc:
            print(f"[!] Could not reach the {SOURCE_LABELS[args.source]} library: {exc}",
                  file=sys.stderr)
            return 2
        if args.pick:
            try:
                indices = parse_index_spec(args.pick, len(library))
            except ValueError as exc:
                print(f"[!] --pick {args.pick}: {exc}\n"
                      f"    Use --list-remote to see the numbers (1..{len(library)}).",
                      file=sys.stderr)
                return 2
            picks = [library[i - 1] for i in indices]
            print(f"[*] Pulling {len(picks)} {SOURCE_LABELS[args.source]} "
                  f"entr{'y' if len(picks) == 1 else 'ies'} by number ({args.pick}):")
        else:
            picks = library[:args.latest]
            print(f"[*] Pulling the {len(picks)} most recent {SOURCE_LABELS[args.source]} "
                  f"entr{'y' if len(picks) == 1 else 'ies'}:")
        for e in picks:
            date = f"{e.published}  " if e.published else ""
            print(f"    {date}{e.title}")
            try:
                files.append(src.download_to(e.url, dest))
            except Exception as exc:
                print(f"    [!] download failed: {exc}", file=sys.stderr)
        print()
    elif is_url(args.huntpack):
        low = args.huntpack.lower()
        src = cqlhub_source if low.endswith((".yml", ".yaml")) else huntpack_source
        dest = CQLHUB_DIR if src is cqlhub_source else HUNTPACK_DIR
        try:
            print(f"[*] Downloading {args.huntpack}")
            local = src.download_to(args.huntpack, dest)
            print(f"    saved -> {local}")
        except Exception as exc:
            print(f"[!] Download failed: {exc}", file=sys.stderr)
            return 2
        files = [local]
    else:
        target = Path(args.huntpack)
        if target.is_dir():
            files = sorted(list(target.glob("*.html"))
                           + list(target.glob("*.yml")) + list(target.glob("*.yaml")))
        elif target.is_file():
            files = [target]
        else:
            print(f"[!] Not found: {target}", file=sys.stderr)
            return 2

    if not files:
        print("[!] No HuntPack files to run.", file=sys.stderr)
        return 2

    queries: list[HuntQuery] = []
    for f in files:
        queries.extend(parse_any(f))
    if not queries:
        print("[!] No CQL queries found in the selected file(s).", file=sys.stderr)
        return 1

    queries = select_queries(queries, args.query)
    if not queries:
        return 1

    if args.list:
        cmd_list(queries)
        return 0
    if args.dry_run:
        cmd_dry_run(queries)
        return 0
    return cmd_run(queries, files, cfg, args, from_remote=from_remote)


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        print("\n[!] Interrupted — stopping. (In-flight search jobs expire on "
              "the server automatically.)", file=sys.stderr)
        raise SystemExit(130)
