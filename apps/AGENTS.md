# Monorepo subsystem rules

- These directories are modules of the unified application. Production uses the root server on port 8888; module workers use private IPC, never individual TCP listeners. Original repositories remain for history/rollback.
- The only Git root is the parent MyInvest20260618 repository. Never create nested repositories or push to an original subsystem remote from here.
- Run tests per application in isolated processes. Do not combine all applications on one PYTHONPATH: core, app, web and scripts names collide.
- Never read production credentials or write original data during tests. Use the sandbox test runner.
- Runtime directories in apps may be junctions to original data. Never recursively copy, delete, reset or clean these directories. Copy tracked source only with scripts/source_copy.py. Do not launch app-local tests or development servers against mounted production data.
- Do not run daily data writers or auto-publish jobs during development verification.
- Commit only reviewed paths from the repository root, with a clean index. Do not automatically commit or push from a subsystem task.
- Keep financial research boundaries unchanged. No trading, cash/share/order writes, or implicit production migration.
- Subsystem instructions below this directory supplement these rules; old per-repository push instructions are superseded by the monorepo workflow.
