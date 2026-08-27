# Setup Guide — HuntPack-Runner

Get the tool running against your CrowdStrike Falcon tenant in about 10 minutes.
Follow the steps in order. Commands are shown for **Windows** (cmd.exe primary,
PowerShell noted where it differs).

---

## Prerequisites

| Need | Details |
|------|---------|
| **Python 3.10+** | Check with `python --version`. Get it from <https://python.org> (tick "Add python.exe to PATH" during install). |
| **A CrowdStrike Falcon tenant** | With Next-Gen SIEM / LogScale enabled. |
| **Permission to create an API client** | Or ask an admin to make one for you (Step 4). |
| **Outbound HTTPS** | To your Falcon API host, and (only if you pull hunts from the library) to `slapopotamus.github.io`. See below. |

### Network access & allowlisting

| Host | Why | Required? |
|------|-----|-----------|
| Your Falcon API host — e.g. `api.us-2.crowdstrike.com` (see Step 6 for the full list) | Authenticate and run every CQL search | **Yes** — the tool does nothing without it |
| `slapopotamus.github.io` | `--list-remote`, `--latest`, `--pick`, and `-f <url>` fetch the hunt index, `feed.xml`, and `hunts/*.html` from here | Only if you pull hunts from the online library |
| `github.com/slapopotamus/HuntPack/tree/main/hunts` | The same hunts, browsable in the source repo — for manual/offline download or review | Optional (manual browsing only) |

The tool itself contacts only **`slapopotamus.github.io`** (a GitHub Pages site)
— it does **not** call `github.com` directly. If your environment blocks it, use
the **offline path**: on any machine with access, open
`github.com/slapopotamus/HuntPack/tree/main/hunts`, download the hunt `.html`
file(s) you want, copy them into this tool's `huntpacks\` folder, and run them
locally with `-f`:

```cmd
python run_hunt.py -f huntpacks\SomePack.html
```

In a fully air-gapped setup only the Falcon API host is strictly required; the
library is a convenience, not a dependency.

---

## Step 1 — Get the files

Unzip the release (or clone the repo) to a working folder, e.g.
`C:\tools\HuntPack-Runner`, then open a terminal **in that folder**:

```cmd
cd C:\tools\HuntPack-Runner
```

You should see `run_hunt.py`, `requirements.txt`, `config.yaml`, and a `src\`
folder.

---

## Step 2 — Create a virtual environment

This keeps the tool's dependencies isolated from the rest of your system.

**cmd.exe:**
```cmd
python -m venv .venv
.venv\Scripts\activate.bat
```

**PowerShell:**
```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

Your prompt should now start with `(.venv)`. That means it's active.

> **You must run the activate step in every new terminal window** before using
> the tool. If you ever see `ModuleNotFoundError: No module named 'falconpy'`,
> the venv isn't active — just run the activate command again.

---

## Step 3 — Install dependencies

```cmd
pip install -r requirements.txt
```

Installs FalconPy (the official CrowdStrike SDK) plus a few small helpers.

---

## Step 4 — Create Falcon API credentials

1. Log into the Falcon console.
2. Go to **Support and resources → API clients and keys → Create API client**.
3. Give it a name (e.g. `huntpack-runner`).
4. Grant this scope:

   | Scope | Access |
   |-------|--------|
   | **NGSIEM search** | Read **and** Write |

5. Click **Create**.
6. **Copy the Client Secret immediately** — Falcon shows it only once. Also copy
   the **Client ID**. Note the **Base URL / cloud** shown (e.g.
   `api.us-2.crowdstrike.com`) — you need it in Step 6.

> If you close the dialog without copying the secret, you'll have to reset it.

---

## Step 5 — Add your credentials

Copy the template and open it:

**cmd.exe:**
```cmd
copy .env.example .env
notepad .env
```

Fill in the two values and save:

```
FALCON_CLIENT_ID=<your client id>
FALCON_CLIENT_SECRET=<your client secret>
```

`.env` stays on your machine only — it is never committed or shared.

---

## Step 6 — Set your region

Open `config.yaml` and set `region` to match the Base URL from Step 4:

| Your Falcon API host | `region:` value |
|----------------------|-----------------|
| `api.crowdstrike.com` | `us-1` |
| `api.us-2.crowdstrike.com` | `us-2` |
| `api.eu-1.crowdstrike.com` | `eu-1` |
| `api.laggar.gcw.crowdstrike.com` | `us-gov-1` |
| `api.us-gov-2.crowdstrike.mil` | `us-gov-2` |

```yaml
region: us-2      # <- set this to your cloud
```

(You can also override per-run with `--region us-2`, or set `FALCON_REGION` in
`.env`.)

---

## Step 7 — Verify (no credentials needed)

Confirm the tool runs and can reach the hunt library:

```cmd
python run_hunt.py --list-remote
```

You should see a numbered list of hunts, newest first. If that works, the
install is good.

---

## Step 8 — First live run

This makes a real API call to confirm auth and search work end to end. Pull the
newest hunt and run it over the last 24 hours:

```cmd
python run_hunt.py --latest 1 --start 24h
```

Expected output:

```
[*] Authenticated to CrowdStrike Falcon.
[*] Region=us-2  Repository=search-all  Window=24h..now
[>] ... Q1 — ...
    OK — 0 event(s) in 1.3s
...
  N queries · 0 with hits · total 12.0s
```

**`OK — 0 event(s)` is success, not an error** — it means the query ran and
nothing matched in that window. You're now operational.

---

## Step 9 — Where results go

Each run writes JSON to `output\<timestamp>\`, one file per query (or one
subfolder per pack when you run several). Each file holds the query text, the
event count, how long it took, and the raw matching events.

> Treat `output\` as sensitive — event data can contain hostnames, usernames,
> and IPs from your environment. It is git-ignored and never included in a
> shared build.

---

## Everyday commands

```cmd
:: Browse the online library (numbered, newest first)
python run_hunt.py --list-remote

:: Pull library hunts by number — single, range, or list
python run_hunt.py --pick 9
python run_hunt.py --pick 9-10
python run_hunt.py --pick 1,3,5

:: Pull the N newest hunts and run them
python run_hunt.py --latest 3

:: Run a local pack you already have
python run_hunt.py -f huntpacks\SomePack.html

:: Preview first — list the queries, or print the CQL without running
python run_hunt.py -f huntpacks\SomePack.html --list
python run_hunt.py -f huntpacks\SomePack.html --dry-run

:: Run only some queries — by number, range, or label
python run_hunt.py -f huntpacks\SomePack.html -q 1-4
python run_hunt.py -f huntpacks\SomePack.html -q Q5

:: Widen or tighten the time window
python run_hunt.py -f huntpacks\SomePack.html --start 30d
python run_hunt.py -f huntpacks\SomePack.html --start 90m
```

Full flag reference is in `README.md`.

---

## Troubleshooting

| Symptom | Cause & fix |
|---------|-------------|
| `ModuleNotFoundError: No module named 'falconpy'` | venv not active. Run `.venv\Scripts\activate.bat` (look for `(.venv)` in the prompt). |
| `Refusing to create a venv ... contains the PATH separator ;` | You pasted a PowerShell one-liner into cmd.exe. Run each command on its own line, or switch to PowerShell. |
| `Auth failed (HTTP 401/403)` | Wrong Client ID/Secret, wrong `region`, or the API client is missing the **NGSIEM search** scope. Re-check Steps 4–6. |
| `Missing FALCON_CLIENT_ID / FALCON_CLIENT_SECRET` | No `.env`, or values not filled in. Redo Step 5. |
| Every query returns `0 events` | Often normal (nothing matched). But FortiGate-log style queries return nothing unless those logs are ingested into NG-SIEM — that's a data-source gap, not a tool bug. |
| `argument --latest: invalid int value: '9-10'` | `--latest` takes a count (`--latest 2`). For specific numbers/ranges use `--pick 9-10`. |
| `--pick ...: index N is out of range` | Run `--list-remote` to see valid numbers. |
| Command hangs a long time | A very wide `--start` (e.g. `90d`) on a big tenant. Narrow the window, or raise `timeout_seconds` in `config.yaml`. |

---

## Security reminders

- **Never commit or share `.env`** — it holds live API keys.
- **Never share `output\`** — it can contain real telemetry from your tenant.
- To hand the tool to someone else, point them at the repo — `.env` and
  `output\` are git-ignored, so neither is ever tracked or shared.
