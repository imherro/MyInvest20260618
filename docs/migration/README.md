# 13-system source consolidation

> This document records the completed source-only phase. The subsequent deployment
> and runtime architecture supersede its original deployment boundary; see
> [Unified MyInvest Application](unified-application.md).

## Scope and deployment boundary

The existing MyInvest20260618 repository owns the source under `apps/`.
This is a reviewed working-tree snapshot, not a merge of the original Git histories.
`source-snapshot.json` records each upstream URL, original HEAD (null for Intraday),
working-tree status, imported file SHA-256, and excluded runtime paths.
Local uncommitted source changes are included, notably Intraday and ShortTerm.
Original repositories, credentials, databases, reports, and processes were not moved.
TAA and Test are outside this migration's 13-system scope.

Production still runs from the original sibling directories. No Cloudflare route,
scheduled automation, original Git remote, or production listener is switched.
The existing `scripts/ensure_web_services.ps1` continues using legacy directories;
its pre-existing local changes are not part of this migration commit.
Future production cutover is a separate, explicit operation, one subsystem at a time.
New source changes in this repository do not automatically update legacy services.
"Unchanged deployment" describes the migration actions, not a claim that every
legacy service was healthy: the existing deployment must be checked separately.

## Development

```powershell
python scripts/subsystems.py list
python scripts/subsystems.py check
python scripts/subsystems.py dev --system intraday --port 19022
```

`check` only sends health requests and never starts/stops services. `dev` runs in the
foreground on loopback and refuses production ports or occupied ports. Stop it with
Ctrl+C. It does not reuse original private data or keys. Each application retains its
own working directory, dependency manifest, test suite and Python module namespace.
Use an application-specific virtual environment if installing dependencies; do not
combine all `core`, `web`, `app`, or `scripts` packages into one Python import path.
The existing dependency manifests have not been globally upgraded or locked here.

## Runtime data and secrets

Source snapshots exclude `data`, `reports`, `research`, logs, output, caches and books,
except executable source such as Picking's `data/*.py`. Config/rules and test fixtures
outside runtime directories remain source-controlled. No `.env` or private key is
imported; `.env.example` templates can remain. Old runtime data is retained in place.
An empty source checkout is not a populated research deployment. Restore/provision
approved data and credentials explicitly before a future deployment; never silently
point development writers at production files. Do not symlink runtime directories to
old live repositories for testing.

StrategyIndex and Cycle remain siblings under `apps/`, preserving the default
cross-project relative path. `MYINVEST_CYCLE_BACKTEST_DIR` can explicitly override it.
ETF/Stock generated research prompts now resolve their current application root,
instead of instructing agents to edit the old absolute Documents path.

## Verification

```powershell
python -m unittest discover -s tests -q
python scripts/test_subsystems.py --data-root C:\Users\kunpeng\Documents --timeout 1200
python scripts/audit_subsystems.py --originals C:\Users\kunpeng\Documents
python scripts/smoke_subsystems.py
```

The subsystem runner copies source into a fresh sandbox under ignored `temp/`, runs
each suite in a separate process, strips credential environment variables and blocks
external/production-port socket connections in pytest. It never executes tests in an
original repository. Production report validation tests in Market, Theme and Cycle
need historical inputs: `--data-root` copies only inventoried data/research/report
files into the sandbox, plus Cycle's explicit `data/cache/fund_daily_*.csv` and
`index_daily_*.csv` price-series fixtures; no databases, `.env`, books, account data
or arbitrary ignored files. Fixture paths and SHA-256 are logged per suite.
Without these inputs, report-dependent tests fail as missing data, not skipped success.
Results/logs are written per suite. This is local isolated acceptance, not hosted CI,
live upstream-data acceptance or production deployment acceptance.
The smoke runner starts each imported web entry point on an OS-selected temporary
loopback port in its own copy, verifies its catalog/health response, and stops only
the child process it created. Production ports and data are never used.
The final compact acceptance evidence is in `validation.json`; per-run detailed
logs and copied fixtures remain local under ignored `temp/`.

One Market parameter unit test previously assumed that mutable live history never
contains an active contrarian overlay. The imported test now supplies a deterministic
inactive-history fixture and adds the opposite active-history rejection case. The
research algorithm and its live-history audit gate remain unchanged. A passing unit
suite does not assert that the current production history passes that audit.

## Git workflow

Do not create `.git` directories inside `apps/`. Publish only from the repository root.
Market and Theme imported daily jobs generate artifacts but no longer stage, commit,
or push Git changes. Original daily jobs were not modified. Separate automation
worktrees/branches are required when migrating existing jobs to the monorepo.
Do not share one working tree/index among concurrent publishing jobs.
Review the staged diff and use exact paths; never `git add .` around runtime data.
Original Git repositories remain the historical record and rollback source, not a
second automatic destination for new development commits. They were not archived,
deleted, reset or force-pushed as part of this task.

## Reproduction and rollback

`scripts/import_subsystems.py` inventories originals by default. `--apply` is a
one-time import that refuses existing app destinations; do not rerun over adapted
sources. `audit_subsystems.py` compares current original sources to the recorded
snapshot, reports adaptations, and checks imports against known local credential
values without printing secrets. It is not a complete historical-secret scan.
Runtime data was intentionally not imported into Git, so rollback of this source-only
migration requires no service or data restoration. Do not delete the old directories.

## Legacy service observations during this migration

The initial listener inventory contained hub 8888 (PID 27020), Market 8011
(PID 34640), and Theme 8012 (PID 47188). A later inventory, taken before the first
temporary web smoke-test cleanup, contained only hub 8888 with the same PID.
This task did not stop/restart the legacy processes, and the reason for those two
listeners disappearing has not been established. Do not interpret source acceptance
as proof that all legacy services are currently available. Existing startup scripts
and scheduled jobs were deliberately left unchanged.
