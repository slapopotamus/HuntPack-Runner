# HuntPack-Runner

Run CQL threat-hunt queries against **CrowdStrike Next-Gen SIEM / Falcon
LogScale** via the official Falcon API (using the
[FalconPy](https://www.falconpy.io) SDK, `NGSIEM` service collection) from
**two query libraries**:

- **HuntPacks** — multi-query HTML playbooks from
  <https://slapopotamus.github.io/HuntPack/> (the default source).
- **CQL-Hub** — ~150 standalone YAML detections from
  [ByteRay-Labs/Query-Hub](https://github.com/ByteRay-Labs/Query-Hub)
  (`--source cqlhub`).

Pick a library with `--source`, browse it with `--list-remote`, pull queries by
number/URL, run each as a LogScale **query job**, and save results as JSON plus
an HTML review report. See [Query sources](#query-sources) below.

```
setup.bat / setup.ps1  one-step installer: venv + deps + guided credential/region setup
run.bat                double-click to open a ready-to-type prompt (venv active)
configure.py           interactive credential + region config (re-run any time)
run_hunt.py            CLI entry point
review.py              summarize a run + build an HTML report (auto-runs after each hunt)
hunt.bat / hunt.ps1    launcher — runs via the venv, no activation needed
config.yaml            region / repository / time-window defaults (non-secret)
.env                   your API credentials (create from .env.example)
src/
  huntpack_parser.py   pull CQL out of HuntPack HTML
  huntpack_source.py   HuntPack library (index + Atom feed)
  cqlhub_parser.py     pull CQL out of a CQL-Hub YAML file
  cqlhub_source.py     CQL-Hub library (GitHub Query-Hub repo)
  falcon_client.py     OAuth + start-search -> poll -> events
huntpacks/             drop HuntPack .html files here
output/                query results (JSON), one folder per run
```

> **New to this / setting it up somewhere fresh?** Follow
> [SETUP.md](SETUP.md) — a step-by-step install guide with troubleshooting.
> The section below is the quick version.
>
> **Want worked examples?** [EXAMPLES.md](EXAMPLES.md) walks from the simplest
> commands up to advanced workflows.

---

## Requirements

- **Python 3.10+** (the installer checks, and points you at python.org if not found)
- A **CrowdStrike Falcon** tenant with **Next-Gen SIEM / LogScale**
- A Falcon **API client** with `NGSIEM search` Read & Write scope (see step 2)

Windows is the primary target (`.bat` / `.ps1` launchers), but the Python
entry points run anywhere.

---

## 1. Setup

**Fastest — one step:** run the guided installer. It creates the environment,
installs dependencies, then asks for your API keys and region and saves them.

```cmd
setup.bat            REM PowerShell: .\setup.ps1
```

**Or manually:**

```powershell
cd path\to\HuntPack-Runner    # the folder you unzipped this into

# (recommended) create a virtual environment
python -m venv .venv
.\.venv\Scripts\Activate.ps1

pip install -r requirements.txt
```

## 2. Get API credentials

In the Falcon console: **Support and resources → API clients and keys →
Create API client**. Grant scope:

| Scope         | Access         | Why |
|---------------|----------------|-----|
| NGSIEM search | Read & Write   | Start/poll/stop CQL query jobs |

Copy the **Client ID** and **Client Secret**, then:

```powershell
copy .env.example .env
# edit .env and paste in FALCON_CLIENT_ID / FALCON_CLIENT_SECRET
```

Set your region in `config.yaml` (`us-1`, `us-2`, `eu-1`, `us-gov-1`,
`us-gov-2`) — pick the one that matches the URL you log into Falcon with.

## 3. Use it

```powershell
# List the queries in a HuntPack (no credentials needed):
python run_hunt.py -f huntpacks\FortiBleed-CVE-2026-24858-Hunt.html --list

# See the exact CQL that would run (no credentials needed):
python run_hunt.py -f huntpacks\FortiBleed-CVE-2026-24858-Hunt.html --dry-run

# Run one query over the last 7 days:
python run_hunt.py -f huntpacks\FortiBleed-CVE-2026-24858-Hunt.html -q Q1

# Run several, 24h lookback (by label, number, range, or a comma list):
python run_hunt.py -f huntpacks\FortiBleed-CVE-2026-24858-Hunt.html -q Q1 -q Q5 --start 24h
python run_hunt.py -f huntpacks\FortiBleed-CVE-2026-24858-Hunt.html -q 1,5 --start 24h
python run_hunt.py -f huntpacks\FortiBleed-CVE-2026-24858-Hunt.html -q 1-4      # first four

# Run everything in the pack:
python run_hunt.py -f huntpacks\FortiBleed-CVE-2026-24858-Hunt.html
```

### Pull hunts from the online HuntPack library

Instead of a local file, `-f` also accepts a **hunt URL** from
<https://slapopotamus.github.io/HuntPack/>. The file is downloaded into
`huntpacks/` (so you keep a local copy) and then run.

```powershell
# Browse the whole online library (100+ hunts), newest-added first,
# with publish date + category + copy-paste URLs:
python run_hunt.py --list-remote

# Pull a hunt straight from the library and list its queries:
python run_hunt.py -f https://slapopotamus.github.io/HuntPack/hunts/ScatteredSpider-Hunt.html --list

# Pull it and run everything:
python run_hunt.py -f https://slapopotamus.github.io/HuntPack/hunts/ScatteredSpider-Hunt.html

# Pull the 2 most recently added hunts and run ALL their queries:
python run_hunt.py --latest 2

# Run specific hunts by their --list-remote number (single, list, or range):
python run_hunt.py --pick 9
python run_hunt.py --pick 9-10
python run_hunt.py --pick 1,3,5-7
```

`--list-remote` numbers every hunt (newest = 1), and `--pick` runs those
numbers. The numbering is stable, so a number always maps to the same hunt as
the list shows it.

Each run prints the **time per query** and a **total**, and (when multiple packs
run at once) saves results in one folder per pack so identically-named queries
(`Q1`, `Q1`) never overwrite each other:

```
output/20260708-153010/
  ColdFusion-CVE-2026-48282-Hunt/  Q1_cql1.json ...
  TeamPCP-SupplyChain-Hunt/        Q1_cql1.json ...
```

Results land in `output/<timestamp>/Q1_cql1.json`, etc. — each file holds the
query text, the event count, and the raw events.

### Flags

| Flag | Meaning |
|------|---------|
| `-f, --huntpack` | A `.html` HuntPack **or** `.yml` CQL-Hub file, a directory, or a URL (auto-detected) |
| `--source`       | Library for `--list-remote`/`--latest`/`--pick`: `huntpack` (default) or `cqlhub` |
| `--list-remote`  | List every entry in the selected `--source` library and exit |
| `--latest N`     | Pull the N most recently added hunts and run them |
| `--pick SPEC`    | Run library hunts by list number: `9`, `9-10`, `1,3,5-7` |
| `-q, --query`    | Run only these queries — by list number (`7`), range (`5-8`), or label (`Q1`); repeatable & comma-ok |
| `-l, --list`     | List queries and exit |
| `--dry-run`      | Print the CQL without calling the API |
| `-i, --interactive` | Review each query and confirm before it runs (`[Y]es / [n]o / [a]ll / [q]uit`) |
| `--verbose`      | Show full API error responses (default: concise) |
| `--limit N`      | Rows returned per query (default 200, max 20000) — raise LogScale's cap to see true volume |
| `--start`        | Lookback (`60m`, `24h`, `7d`, `30d`) — overrides config |
| `--end`          | Window end (default `now`) |
| `--region`       | Falcon region override |
| `--repository`   | NG-SIEM repository override (default `search-all`) |

---

## Notes on these queries

The FortiBleed pack has two kinds of query:

- **Q1–Q4** hunt **FortiGate event logs** that must already be ingested into
  Next-Gen SIEM. If you don't forward FortiGate logs to Falcon, these return
  nothing — that's a data-availability gap, not a bug. Field prefixes
  (`logid`, `cfgpath`, `srcip`, …) depend on your FortiGate parser; adjust if
  your tenant names them differently.
- **Q5–Q7** hunt **Falcon EDR telemetry** (`ProcessRollup2`,
  `NetworkConnectIP4`, …) and work out of the box wherever the Falcon sensor
  is deployed.

Several queries carry environment-specific exclusions (service-account names,
management-station source IPs, jump-host `aid`s). Review the `// TUNING:`
comment in each and adjust before trusting the results in production.

## Reviewing results

Every run auto-generates a **`review.html`** in its output folder — a
self-contained dark report showing which queries fired, hit counts, timing, and
an events table for each detection. Just open it in a browser.

You can also (re)build a report for any past run, or get a quick console
summary, with `review.py` (no credentials or venv needed — it only reads local
files):

```powershell
python review.py                          # newest run under output/
python review.py output\20260709-113237   # a specific run
python review.py --open                   # also open the report in a browser
python review.py --no-html                # console summary only
```

The console summary marks queries with hits and flags any that **hit the row
cap** (200 by default) — meaning the result is truncated. To see the true
volume of a noisy hit, re-run with a higher cap:

```powershell
python run_hunt.py -f huntpacks\SomePack.html -q Q2 --limit 20000
```

`--limit N` raises LogScale's row limit (max 20000) by rewriting the query's
trailing `table(...)`. If a query still returns exactly N, it's capped again —
tighten it or narrow the window rather than pulling more noise.

## Query sources

Two interchangeable libraries behind one `--source` flag:

| | `--source huntpack` (default) | `--source cqlhub` |
|---|---|---|
| Where | slapopotamus.github.io/HuntPack | github.com/ByteRay-Labs/Query-Hub |
| Format | HTML, multiple `Q#` queries per pack | YAML, one detection per file |
| Ordering | newest first (dated) | A–Z |

```powershell
# Browse either library (numbered):
python run_hunt.py --list-remote                    # HuntPacks (default)
python run_hunt.py --source cqlhub --list-remote     # CQL-Hub (~150 detections)

# Pull & run by number from the chosen library:
python run_hunt.py --source cqlhub --pick 5-10
python run_hunt.py --source cqlhub --pick 5-10 -i    # review each first

# A -f path or URL is auto-detected by extension (.yml = CQL-Hub, .html = HuntPack):
python run_hunt.py -f https://raw.githubusercontent.com/ByteRay-Labs/Query-Hub/main/queries/<Name>.yml
python run_hunt.py -f cqlhub\<Name>.yml
```

**Lookup dependency:** some CQL-Hub queries correlate against lookup CSVs (Tor exit
nodes, cloud IP ranges, LOLBAS, …) that must be uploaded to your NG-SIEM first.
Those are flagged with a `// NOTE: references a lookup file` line in `--dry-run`
and will error until the lookup exists in your tenant (the error is captured
per-query; the rest of the batch continues).

## Security & trust boundary

- **The hunt library is third-party.** `--list-remote` / `--latest` / `--pick` / `-f <url>`
  pull HuntPack HTML from `slapopotamus.github.io`, and the CQL inside runs against **your**
  Falcon tenant. Review unfamiliar packs first with `--dry-run`, or run with **`-i` /
  `--interactive`** to approve each query before it executes. (A one-time notice reminds you
  of this the first time you run a remote-pulled pack.)
- **Credentials & results are locked down.** `.env` and everything under `output/` are
  written owner-only (POSIX `600` / Windows ACL) and are git-ignored — never committed.
  Treat `output/` as sensitive: it can contain hostnames, users, and IPs from your
  environment.
- **Region is validated** against an allowlist, so a bad `--region`/config can't redirect
  your credentials to an arbitrary host.
- **Reproducible installs:** `requirements.lock` pins every dependency with hashes
  (`pip install --require-hashes -r requirements.lock`); run `pip-audit -r requirements.lock`
  to scan for CVEs.

## Run manifest & audit trail

Every run writes `output/<timestamp>/summary.json` — a machine-readable manifest with the
user, host, region, repository, time window, **SHA256 of each HuntPack**, and per-query
status/counts/durations. A cumulative one-line-per-run audit log is appended to
`output/huntpack.log`. Both make the runner safe to consume from a pipeline or SIEM.

## Scheduling / automation

The runner is headless-friendly: supply credentials via environment variables (no `.env`
needed) and it never prompts. Do **not** pass `-i`/`--interactive` in a scheduled context —
it refuses when there's no terminal.

```bat
:: Windows Task Scheduler action (daily hunt of the newest 3 packs, 24h window)
set FALCON_CLIENT_ID=...
set FALCON_CLIENT_SECRET=...
set FALCON_REGION=us-2
"C:\tools\HuntPack-Runner\.venv\Scripts\python.exe" "C:\tools\HuntPack-Runner\run_hunt.py" --latest 3 --start 24h
```

```bash
# cron (Linux): FALCON_* exported in the environment / a sourced secrets file
0 7 * * *  cd /opt/huntpack-runner && ./.venv/bin/python run_hunt.py --latest 3 --start 24h
```

**Exit codes:** `0` = all selected queries ran · `1` = ran but ≥1 query failed · `2` =
config/usage error or aborted (`q`) — alert on non-zero, inspect `summary.json` for detail.

## How it talks to the API

```
POST   /humio/api/v1/repositories/{repo}/queryjobs        start_search  -> {id}
GET    /humio/api/v1/repositories/{repo}/queryjobs/{id}   get_search_status (poll until done)
DELETE /humio/api/v1/repositories/{repo}/queryjobs/{id}   stop_search (on timeout)
```

---

## Sharing this tool

Clone or download the repo — nothing sensitive is tracked in git:

- **Secrets never ship.** `.env` is git-ignored. Credentials live only in your
  local `.env`, never in the repo.
- **New users** run `setup.bat` (or `copy .env.example .env`) and supply their
  own Client ID / Secret and region — nothing is pre-filled.
- **Results stay local.** `output\` is git-ignored; treat those JSON files as
  sensitive (they can contain hostnames, users, and IPs from your tenant).

## License

MIT — see [LICENSE](LICENSE).
