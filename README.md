# The Last Backup — Vercel edition

A separate, deployable Flask application for the six-stage Northstar investigation. It includes registration, sign-in, sequential challenges, case-sensitive flag checks, paid hints, a scoreboard, the archive, evidence review, cipher downloads, a forensic image, a browser evidence explorer and organizer controls.

This edition replaces the Docker/CTFd stack with a small custom scoring application. Online state lives in PostgreSQL. Stage 6 is a browser-based investigation of preserved Linux files, **not an SSH server or a live terminal**. The original Docker project remains the version for a real Linux/SSH demonstration. See [design differences](docs/DESIGN-DIFFERENCES.md) before using this edition for assessment.

## Upload through GitHub's website

Use a **new private repository**, for example `the-last-backup-vercel`. Upload the contents of the provided `Upload-to-GitHub` folder into the repository root. Do not upload its enclosing folder and do not combine this edition with the old four-part Docker upload.

The root must contain `app.py`, `build.py`, `pyproject.toml`, `requirements.txt`, `vercel.json`, `templates/`, `public/`, `ctf/` and `storage.py`. Include the dotfiles. No ZIP is needed. The upload copy contains fewer than 100 files, each below 25 MiB.

Keep this repository private while people play: organizer source includes static flags and reference solutions. Never upload `Local-Only`, real environment variables, passwords or user databases.

## Deploy from the Vercel website

1. Import the new GitHub repository into a **new Vercel project**.
2. Framework preset: **Flask**. Root Directory: leave blank, or `.` if the interface requires a value, when `app.py` is at the repository root. Build Command: **`python build.py`**. Leave Output Directory and Install Command at their framework defaults.
3. Connect a PostgreSQL provider such as Neon through Vercel's Storage/Marketplace flow. Choose a database region close to the function region. Use a dedicated database for this CTF. Add its pooled PostgreSQL connection string as **`DATABASE_URL`** if the integration did not create that exact variable. Do not use a frontend/public-prefixed environment variable. PostgreSQL connections enforce TLS.
4. Add **`SECRET_KEY`** (at least 32 random characters) and **`ADMIN_PASSWORD`** (at least 12 characters). Run `python tools/new_secrets.py` locally to generate strong values, then copy them directly into Vercel's Environment Variables settings. Do not put the values into GitHub.
5. Apply all three variables to the deployment environment you use. Keep Preview deployments on a different database and different secrets from Production if you enable both.
6. Deploy. The build produces immutable challenge evidence. The app creates its own `ns_*` database tables on first use under a database lock. The connected database role therefore needs schema/table creation permission in its dedicated database.
7. Open `/health`: it should return `status: ok`, `stages: 6`, `storage: postgresql`. Open `/admin` and sign in with `ADMIN_PASSWORD`. Register a normal player and verify the full journey from another device.

If the app displays **Almost ready**, it explains the missing environment setting or build step. After changing environment variables, redeploy. If it reports database unavailable, check that the provider is active, `DATABASE_URL` is correct, the PostgreSQL role has the needed permissions and the project can reach the provider.

The explicit entrypoint is already correct:

```toml
[tool.vercel]
entrypoint = "app:app"

[tool.vercel.scripts]
build = "python build.py"
```

Do not use `local.bootstrap.activate_theme:app`, do not select a folder under `local/`, and do not set an output folder such as `dist`. Those belong to other application structures. This repository has one root `app.py` that exports its Flask app.

## Environment settings

| Name | Required | Purpose |
|---|---|---|
| `SECRET_KEY` | Yes | Signs login/session cookies. Use a strong random value. |
| `ADMIN_PASSWORD` | Yes | Organizer sign-in password. |
| `DATABASE_URL` | Yes | Dedicated PostgreSQL connection string. Use the provider's pooled endpoint. |
| `REGISTRATION_OPEN` | No | Defaults to `true`; set `false` and redeploy to stop new registrations. |

Vercel supplies `VERCEL` automatically. When present, the app requires PostgreSQL and uses secure cookies. It never falls back to SQLite or temporary-file storage online. Never override `VERCEL` to bypass this check.

## Routes

| Address | What it does |
|---|---|
| `/` | Public introduction |
| `/register`, `/login` | Player access |
| `/challenges` | Saved progress and six-stage pathway |
| `/scoreboard` | Investigator names, completed stages and scores |
| `/archive/` | Stage 1 source comparison |
| `/portal` | Stage 3 policy, transactions, audit and evidence review |
| `/evidence` | Stage 6 file explorer and final verification |
| `/admin` | Organizer panel, individual reset/disable and progress export |
| `/health` | Database readiness and application health |

Stage files are protected by account and prerequisite checks. CSS belongs in `public/assets` and is served by Vercel's CDN. Flags, private configuration and gated evidence do **not** belong in `public/`.

## Separate local environment

The prepared workspace has these sibling folders:

```text
Vercel-Workspace/
  Project/             working source
  Upload-to-GitHub/     clean source copy for website upload
  Local-Only/           Python environment, credentials, database and test output
```

To set up a new downloaded copy on Windows, open PowerShell in its project root:

```powershell
py -3.12 -m venv ../Local-Only/.venv
& ../Local-Only/.venv/Scripts/python.exe -m pip install -r requirements-dev.txt
& ../Local-Only/.venv/Scripts/python.exe build.py
& ../Local-Only/.venv/Scripts/python.exe tools/run_local.py
```

Open **http://localhost:8002**. `tools/run_local.py` creates fresh local credentials and a SQLite database in the sibling `Local-Only` folder. Organizer credentials are in `Local-Only/LOCAL-ACCESS.txt`; the organizer URL is `/admin`. This is independent of the original project on port 8001. After setup, `Start Local.cmd` starts the preview. Stop it with Ctrl+C in its terminal.

For Vercel CLI integration testing, use `vercel dev` after installing the project's dependencies and linking the intended test project. That requires your Vercel account and environment configuration. The provided local preview uses Waitress and is not proof of a deployed Vercel runtime test.

## Tests and evidence

Run `python build.py` before testing, then:

```powershell
& ../Local-Only/.venv/Scripts/python.exe -m pytest -q
```

The build creates a reproducible 64 MiB FAT16 evidence image and distributes it as a gzip file of about 65 KiB. Extract it before using Sleuth Kit/Autopsy or the reference solver. Its **decompressed** checksum is embedded in the encrypted warning. Compression avoids Vercel's 4.5 MB function response limit. All links use the same website origin; there are no hard-coded localhost links in player pages or the PNG clue.

Organizer reference tools:

```sh
python tools/solve.py png private_data/stage1/event-original.png
python tools/solve.py cipher private_data/portal/elias.enc.txt
# After extracting the downloaded image:
python tools/solve.py fat northstar_evidence.img
```

See docs/TEST-RESULTS.md for executed checks and limitations. The supplied tests use temporary local databases and never use the deployed DATABASE_URL. A local test pass does not replace a live PostgreSQL/Vercel validation.

## Reset, export and recovery

The organizer panel lets you reset one player's progress or disable/enable their account after typing the exact player name. Reset clears solves, hints, portal review and final verification; it preserves the account and password and invalidates existing sessions. It does not clear rate-limit records; wait for their normal expiry.

The progress export contains names and progress, not password hashes. It is an assessment/reporting export, **not a restorable database backup**. Use the PostgreSQL provider's backup/restore tools for full recovery. Restore into a separate test database and check accounts/progress before relying on that backup. Immutable challenge files are recreated by the build; players cannot write to them. Start a new event with a new dedicated database rather than deleting tables in a running event.

Password recovery/email delivery, teams, CTFd plugins, VM snapshots and live SSH are not implemented in this edition. If a player loses their password, an organizer can disable the old account and the player can register a new unique name; scores are not automatically transferred.

## References and acknowledgment

Implementation follows Vercel documentation checked on 10 October 2026:

- [Flask entrypoints, build commands and public assets](https://vercel.com/docs/frameworks/backend/flask)
- [Python runtime and supported versions](https://vercel.com/docs/functions/runtimes/python)
- [Function response limits](https://vercel.com/docs/functions/limitations)
- [PostgreSQL through Marketplace](https://vercel.com/docs/postgres)

This project uses Flask/Werkzeug/Jinja, SQLAlchemy, Psycopg, Pillow, python-dotenv, Waitress and pytest, under their upstream licenses. PostgreSQL is hosted separately. The story, evidence generator, cipher and FAT writer are adapted from the existing Last Backup project; this edition has new templates and CSS and does not bundle the CTFd theme. See docs/AI-ASSISTANCE.md. Keep credentials and solutions out of player materials.
