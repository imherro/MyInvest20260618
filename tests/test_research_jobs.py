import importlib.util
import ast
import json
import os
from pathlib import Path
import subprocess
import sys

import pytest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("research_jobs", ROOT / "scripts/research_jobs.py")
jobs = importlib.util.module_from_spec(spec)
spec.loader.exec_module(jobs)


def test_session_covers_generation_and_qa(tmp_path):
    claim = jobs.transition(tmp_path, "claim", day="2026-11-10")
    token = claim["token"]
    assert claim["claimed"]
    assert not jobs.transition(tmp_path, "claim", day="2026-11-10")["claimed"]
    calls = []
    jobs.transition(tmp_path, "generate", token, operation=lambda: calls.append("generated"))
    assert not jobs.transition(tmp_path, "claim", day="2026-11-11")["claimed"]
    jobs.transition(tmp_path, "qa", token, operation=lambda: calls.append("qa"))
    jobs.transition(tmp_path, "finish", token, outcome="success")
    assert calls == ["generated", "qa"]
    assert not jobs.transition(tmp_path, "claim", day="2026-11-10")["claimed"]
    assert jobs.transition(tmp_path, "claim", day="2026-11-11")["claimed"]


def test_wrong_token_and_early_finish_rejected(tmp_path):
    token = jobs.transition(tmp_path, "claim")["token"]
    with pytest.raises(RuntimeError, match="token"):
        jobs.transition(tmp_path, "generate", "wrong", operation=lambda: pytest.fail("ran"))
    with pytest.raises(RuntimeError, match="unfinished"):
        jobs.transition(tmp_path, "finish", token, outcome="success")


def test_failed_run_is_not_automatically_retried(tmp_path):
    token = jobs.transition(tmp_path, "claim")["token"]
    def fail():
        raise RuntimeError("upstream unavailable")
    with pytest.raises(RuntimeError, match="upstream"):
        jobs.transition(tmp_path, "generate", token, operation=fail)
    assert not jobs.transition(tmp_path, "claim")["claimed"]
    with pytest.raises(RuntimeError, match="Cannot generate"):
        jobs.transition(tmp_path, "generate", token, operation=lambda: pytest.fail("retry"))


def test_cross_process_lock(tmp_path):
    path = tmp_path / "session.lock"
    code = (f"import sys;sys.path.insert(0,{str(ROOT / 'scripts')!r});"
            f"import research_jobs as j;from pathlib import Path;"
            f"c=j.exclusive(Path({str(path)!r}));c.__enter__()")
    with jobs.exclusive(path):
        result = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True)
        assert result.returncode != 0
        assert "busy" in result.stderr
    assert subprocess.run([sys.executable, "-c", code], capture_output=True).returncode == 0


def test_incomplete_sessions_never_expire_automatically(tmp_path):
    token = jobs.transition(tmp_path, "claim", day="2026-01-01")["token"]
    assert not jobs.transition(tmp_path, "claim", day="2027-01-01")["claimed"]
    jobs.transition(tmp_path, "finish", token, outcome="failed")
    assert jobs.transition(tmp_path, "claim", day="2027-01-01")["claimed"]


def test_only_bound_original_data_is_accepted(tmp_path):
    root = tmp_path / "repo"
    originals = tmp_path / "originals"
    original = originals / "MyInvestMarket"
    app = root / "apps/MyInvestMarket"
    (original / "data").mkdir(parents=True)
    app.mkdir(parents=True)
    (original / ".env").write_text("", encoding="utf-8")
    with pytest.raises(RuntimeError, match="binding"):
        jobs.paths("market", root, originals)
    if os.name == "nt":
        subprocess.run(["cmd", "/c", "mklink", "/J", str(app / "data"), str(original / "data")],
                       check=True, capture_output=True)
    else:
        (app / "data").symlink_to(original / "data", target_is_directory=True)
    try:
        _, resolved, bindings = jobs.paths("market", root, originals)
        assert resolved == original
        assert Path(bindings[0]["resolved"]) == (original / "data").resolve()
    finally:
        # Remove the junction itself only, never recurse into its target.
        if os.name == "nt":
            os.rmdir(app / "data")
        else:
            (app / "data").unlink()


@pytest.mark.parametrize("basis,previous,complete", [
    ("2026-11-09", "2026-11-09", True), ("", "", True),
    ("2026-11-11", "2026-11-09", True), ("2026-11-10", "2026-11-09", False),
])
def test_leader_stale_or_incomplete_gate(basis, previous, complete):
    payload = {"result": {"basis_date": basis, "nominal_today": "2026-11-10", "theme_ranking": [{"theme": "test"}],
                          "completeness": {"daily_rows": 1, "daily_basic_rows": int(complete)}}}
    with pytest.raises(RuntimeError):
        jobs.check_leader_basis(payload, previous, "2026-11-10")


def test_leader_complete_new_basis():
    assert jobs.check_leader_basis({"basis_date": "2026-11-10", "nominal_today": "2026-11-10", "theme_ranking": [{}],
                                   "completeness": {"daily_rows": 5000, "daily_basic_rows": 5000}},
                                  "2026-11-09", "2026-11-10") == "2026-11-10"


def test_leader_historical_fallback_is_not_fresh():
    with pytest.raises(RuntimeError, match="historical"):
        jobs.check_leader_basis({"basis_date": "2026-11-03", "nominal_today": "2026-11-04",
                                 "theme_ranking": [{}], "completeness": {"daily_rows": 5000, "daily_basic_rows": 5000}},
                                "2026-09-07", "2026-11-10")


def test_pipeline_stops_after_first_error(monkeypatch, tmp_path):
    monkeypatch.setattr(jobs, "legacy_writers", lambda: [])
    monkeypatch.setattr(jobs, "prepare", lambda _: tmp_path)
    monkeypatch.setattr(jobs, "leader_gate", lambda _: "2026-11-10")
    calls = []
    def fail(app, step):
        calls.append(step[0])
        raise RuntimeError("502")
    monkeypatch.setattr(jobs, "run_step", fail)
    with pytest.raises(RuntimeError, match="502"):
        jobs.generate("leader")
    assert calls == ["scripts/generate_leader_report.py"]


def test_existing_job_id_time_status_inventory():
    assert {v["automation_id"] for v in jobs.JOBS.values()} == {"myinvestleader", "myinvestmarket", "a-2"}
    assert jobs.JOBS["leader"]["status"] == "ACTIVE"
    assert jobs.JOBS["theme"]["status"] == jobs.JOBS["market"]["status"] == "PAUSED"
    assert "BYHOUR=19;BYMINUTE=5" in jobs.JOBS["leader"]["rrule"]
    assert "BYHOUR=21" in jobs.JOBS["market"]["rrule"]
    assert "BYHOUR=22" in jobs.JOBS["theme"]["rrule"]


def function_from_source(relative, name, namespace):
    tree = ast.parse((ROOT / relative).read_text(encoding="utf-8"))
    function = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == name)
    exec(compile(ast.Module(body=[function], type_ignores=[]), relative, "exec"), namespace)
    return namespace[name]


def test_market_managed_verification_never_starts_legacy_server(monkeypatch):
    monkeypatch.setenv("MYINVEST_UNIFIED_ORIGIN", "http://127.0.0.1:8888")
    calls = []
    def endpoint(path):
        calls.append(path)
        raise RuntimeError("unified server unavailable")
    ensure = function_from_source("apps/MyInvestMarket/scripts/run_post_close_update.py", "ensure_server",
                                  {"os": os, "endpoint_json": endpoint})
    with pytest.raises(RuntimeError, match="unavailable"):
        ensure()
    assert calls == ["/api/index"]


def test_theme_canonical_gate_runs_tests_in_disposable_copy(monkeypatch, tmp_path):
    from types import SimpleNamespace
    monkeypatch.setenv("MYINVEST_RESEARCH_ROOT", str(tmp_path / "repo"))
    calls = []
    def run(args, **kwargs):
        calls.append((args, kwargs))
        return SimpleNamespace(stdout="", stderr="", returncode=0)
    fake_subprocess = SimpleNamespace(run=run, CompletedProcess=subprocess.CompletedProcess)
    run_command = function_from_source("apps/MyInvestTheme/scripts/daily_mainline_update.py", "run_command",
                                      {"os": os, "sys": sys, "Path": Path, "ROOT": tmp_path,
                                       "subprocess": fake_subprocess})
    run_command([sys.executable, "-m", "pytest", "web/tests", "-q"])
    assert calls[0][0] == [sys.executable, str(tmp_path / "repo/scripts/test_subsystems.py"),
                          "--system", "theme", "--data-root", str(tmp_path)]


def test_prepare_uses_only_selected_original_env(monkeypatch, tmp_path):
    import dotenv
    import unified.urls
    app, original = tmp_path / "app", tmp_path / "original"
    app.mkdir()
    monkeypatch.setenv("OTHER_API_KEY", "never-inherit")
    monkeypatch.setattr(jobs, "paths", lambda _: (app, original, []))
    calls = []
    monkeypatch.setattr(dotenv, "load_dotenv", lambda p, **kw: calls.append(p))
    monkeypatch.setattr(unified.urls, "install_internal_http", lambda origin: calls.append(origin))
    before_env, before_cwd, before_path = dict(os.environ), Path.cwd(), list(sys.path)
    try:
        assert jobs.prepare("market") == app
        assert "OTHER_API_KEY" not in os.environ
        assert os.environ["MYINVEST_ENV_FILE"] == str(original / ".env")
        assert os.environ["MYINVEST_MARKET_WEB_DATA"] == str(original / "web/data")
        assert os.environ["MYINVEST_RESEARCH_ORIGINAL"] == str(original)
        assert calls == [original / ".env", "http://127.0.0.1:8888"]
    finally:
        os.chdir(before_cwd)
        sys.path[:] = before_path
        os.environ.clear()
        os.environ.update(before_env)


def test_policy_changes_are_not_lost_behind_ignored_junctions(tmp_path):
    (tmp_path / "data").mkdir()
    path = tmp_path / "data/policy_signals.json"
    path.write_text("{}", encoding="utf-8")
    baseline = jobs.policy_signature(tmp_path)
    state = tmp_path / "sessions"
    token = jobs.transition(state, "claim", day="2026-11-10", policy=baseline)["token"]
    path.write_text('{"changed":true}', encoding="utf-8")
    current = jobs.policy_signature(tmp_path)
    assert current != baseline
    jobs.transition(state, "generate", token, operation=lambda: None, policy=current)
    jobs.transition(state, "finish", token, outcome="success")
    jobs.transition(state, "claim", day="2026-11-11", policy=current)
    record = json.loads((state / "session.json").read_text(encoding="utf-8"))
    assert record["last_generated_policy"] == current
    assert (state / "2026-11-10.json").is_file()


def test_theme_managed_dirty_detection_uses_policy_fingerprint(monkeypatch, tmp_path):
    monkeypatch.setenv("MYINVEST_RESEARCH_ROOT", str(tmp_path))
    monkeypatch.setenv("MYINVEST_RESEARCH_POLICY_CHANGED", json.dumps(["data/policy_signals.json", "unrelated.txt"]))
    func = function_from_source("apps/MyInvestTheme/scripts/daily_mainline_update.py", "policy_dirty_paths",
                                {"os": os, "json": json, "ROOT": tmp_path,
                                 "is_allowed_policy_dirty": lambda p: p == "data/policy_signals.json"})
    assert func() == [tmp_path / "data/policy_signals.json"]


def test_scheduler_audit_preserves_ids_times_status_and_rejects_duplicates(tmp_path):
    audit_spec = importlib.util.spec_from_file_location("audit_jobs", ROOT / "scripts/audit_research_jobs.py")
    module = importlib.util.module_from_spec(audit_spec)
    audit_spec.loader.exec_module(module)
    for key, job in jobs.JOBS.items():
        folder = tmp_path / job["automation_id"]
        folder.mkdir()
        fields = {k: job[k] for k in ("name", "status", "rrule")}
        fields.update(id=job["automation_id"], cwds=[str(ROOT)],
                      prompt=job["runbook"] + " scripts/research_jobs.py")
        (folder / "automation.toml").write_text("\n".join(f"{k} = {json.dumps(v, ensure_ascii=False)}" for k, v in fields.items()), encoding="utf-8")
    assert all(not row["errors"] for row in module.audit(tmp_path))
    duplicate = tmp_path / "duplicate"
    duplicate.mkdir()
    (duplicate / "automation.toml").write_text('id="duplicate"\nstatus="ACTIVE"\ncwds=["C:/old/MyInvestLeader"]', encoding="utf-8")
    assert any(row["errors"] for row in module.audit(tmp_path))


def test_managed_writer_uses_new_code_and_original_data(tmp_path, monkeypatch):
    app, original = tmp_path / "app", tmp_path / "original"
    (app / "scripts").mkdir(parents=True)
    (original / "data").mkdir(parents=True)
    if os.name == "nt":
        subprocess.run(["cmd", "/c", "mklink", "/J", str(app / "data"), str(original / "data")], check=True, capture_output=True)
    else:
        (app / "data").symlink_to(original / "data", target_is_directory=True)
    (app / "scripts/fixture.py").write_text(
        "from pathlib import Path\nroot=Path(__file__).resolve().parents[1]\n"
        "(root/'data/result.txt').write_text(str(root))\n", encoding="utf-8")
    monkeypatch.setattr(jobs, "legacy_writers", lambda: [])
    monkeypatch.setattr(jobs, "prepare", lambda task: app)
    monkeypatch.setitem(jobs.JOBS, "market", {"steps": [["scripts/fixture.py"]]})
    argv = sys.argv[:]
    try:
        jobs.generate("market")
        assert (original / "data/result.txt").read_text() == str(app)
        assert not (original / "scripts").exists()
    finally:
        sys.argv[:] = argv
        if os.name == "nt":
            os.rmdir(app / "data")
        else:
            (app / "data").unlink()
