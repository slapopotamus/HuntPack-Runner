# Examples — from first steps to advanced

A hands-on progression. Each block builds on the last. Commands use the **`hunt`
launcher** (no venv activation needed); `python run_hunt.py ...` works
identically if you prefer.

> On PowerShell, write `.\hunt.ps1 ...` instead of `hunt ...`.

Legend for the little notes: 🟢 = no credentials needed · 🔑 = calls the Falcon
API (needs your `.env`).

---

## Level 0 — Look around (no credentials)

**0.1 Browse the online library**, newest first, numbered: 🟢
```cmd
hunt --list-remote
```
The numbers on the left are what `--pick` uses.

**0.2 See the queries inside a pack** without running them: 🟢
```cmd
hunt -f huntpacks\FortiBleed-CVE-2026-24858-Hunt.html --list
```

**0.3 Print the actual CQL** a pack would run: 🟢
```cmd
hunt -f huntpacks\FortiBleed-CVE-2026-24858-Hunt.html --dry-run
```

---

## Level 1 — Your first live runs

**1.1 Run a single query** over the last 24 hours: 🔑
```cmd
hunt -f huntpacks\FortiBleed-CVE-2026-24858-Hunt.html -q Q5 --start 24h
```
> `OK — 0 events` is a clean result — the query ran and nothing matched.

**1.2 Run the whole pack:** 🔑
```cmd
hunt -f huntpacks\FortiBleed-CVE-2026-24858-Hunt.html
```
Uses the default window (7 days). When it finishes, open the `review.html` it
prints a path to.

**1.3 Review each query before it runs** (approve one at a time): 🔑
```cmd
hunt -f huntpacks\FortiBleed-CVE-2026-24858-Hunt.html -i --start 24h
```
> `-i` shows each query and asks `[Y]es / [n]o skip / [a]ll / [q]uit`. Great for
> vetting an unfamiliar pack pulled from the library before it touches your SIEM.

---

## Level 2 — Pick queries and scope the window

**2.1 A few specific queries** by label: 🔑
```cmd
hunt -f huntpacks\FortiBleed-CVE-2026-24858-Hunt.html -q Q1 -q Q5
```

**2.2 By number and range** (numbers come from `--list`): 🔑
```cmd
hunt -f huntpacks\FortiBleed-CVE-2026-24858-Hunt.html -q 1-4
hunt -f huntpacks\FortiBleed-CVE-2026-24858-Hunt.html -q 1,3,5
```

**2.3 Tighten or widen the time window:** 🔑
```cmd
hunt -f huntpacks\FortiBleed-CVE-2026-24858-Hunt.html --start 90m     :: last 90 minutes
hunt -f huntpacks\FortiBleed-CVE-2026-24858-Hunt.html --start 30d     :: last 30 days
```

**2.4 A bounded window** — between 7 and 1 days ago (skip the last day): 🔑
```cmd
hunt -f huntpacks\FortiBleed-CVE-2026-24858-Hunt.html --start 7d --end 1d
```

---

## Level 3 — Pull hunts from the library

**3.1 Pull one hunt by URL** (downloads into `huntpacks\`, then runs): 🔑
```cmd
hunt -f https://slapopotamus.github.io/HuntPack/hunts/ScatteredSpider-Hunt.html
```

**3.2 Pull the newest hunt** and run it: 🔑
```cmd
hunt --latest 1 --start 24h
```

**3.3 Pull specific library numbers** (from `--list-remote`): 🔑
```cmd
hunt --pick 9          :: just #9
hunt --pick 9-10       :: #9 and #10
hunt --pick 1,3,5      :: a mix
```

---

## Level 4 — Multiple packs and reviewing results

**4.1 Run two packs at once** — all their queries: 🔑
```cmd
hunt --pick 9-10
```
Results are split into one folder per pack, and the summary tags each query with
its pack so the repeated `Q1`s don't collide.

**4.2 Select across packs by global number.** After `--pick 9-10`, `--list`
numbers every query 1..N across both — run just the 7th: 🔑
```cmd
hunt --pick 9-10 -q 7
```

**4.3 Review a past run** (no credentials — reads local files): 🟢
```cmd
python review.py                          :: newest run
python review.py output\20260709-113237   :: a specific run
python review.py --open                   :: open the HTML report in a browser
```

---

## Level 5 — Measuring noise and advanced scoping

**5.1 A query came back "capped" (200).** See its true volume: 🔑
```cmd
hunt -f huntpacks\SomePack.html -q Q2 --start 24h --limit 20000
```
> If it still returns exactly your limit, the query is genuinely noisy — tighten
> it or narrow the window instead of pulling more.

**5.2 Run every local pack** you've collected: 🔑
```cmd
hunt -f huntpacks
```

**5.3 Everything combined** — pick two packs, first four queries each region
of interest, tight window, raised cap: 🔑
```cmd
hunt --pick 9-10 -q 1-4 --start 24h --limit 5000
```

**5.4 Override region / repository** for one run (else `config.yaml` decides): 🔑
```cmd
hunt -f huntpacks\SomePack.html --region us-2 --repository search-all
```

---

## Quick reference

| I want to… | Command |
|------------|---------|
| Browse the library | `hunt --list-remote` |
| Preview a pack's queries | `hunt -f <pack> --list` |
| See the CQL without running | `hunt -f <pack> --dry-run` |
| Run one query, last 24h | `hunt -f <pack> -q Q5 --start 24h` |
| Run queries 1–4 | `hunt -f <pack> -q 1-4` |
| Pull & run library #9–10 | `hunt --pick 9-10` |
| Run the 3 newest hunts | `hunt --latest 3` |
| See a noisy query's true count | `hunt -f <pack> -q Q2 --limit 20000` |
| Review a past run | `python review.py output\<timestamp>` |

Full flag reference is in [README.md](README.md); first-time setup is in
[SETUP.md](SETUP.md).
