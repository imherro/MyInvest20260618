# Monorepo subsystem rules

- These directories are source snapshots. Original sibling repositories and their runtime data remain untouched; production has NOT been switched here.
- The only Git root is the parent MyInvest20260618 repository. Never create nested repositories or push to an original subsystem remote from here.
- Run tests per application in isolated processes. Do not combine all applications on one PYTHONPATH: core, app, web and scripts names collide.
- Never read production credentials or write original data during tests. Use the sandbox test runner.
- Do not run daily data writers or auto-publish jobs during development verification.
- Commit only reviewed paths from the repository root, with a clean index. Do not automatically commit or push from a subsystem task.
- Keep financial research boundaries unchanged. No trading, cash/share/order writes, or implicit production migration.
- Subsystem instructions below this directory supplement these rules; old per-repository push instructions are superseded by the monorepo workflow.
