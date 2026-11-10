import json
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import import_subsystems
import subsystems
import offline_tests


class MonorepoTests(unittest.TestCase):
    def test_offline_guard_allows_only_socketpair_internal_reserved_ports(self):
        with self.assertRaises(RuntimeError):
            offline_tests.check(("127.0.0.1", 8014))
        with patch.object(offline_tests, "_socketpair", side_effect=lambda: offline_tests.check(("127.0.0.1", 8014))):
            offline_tests.socketpair()
        with self.assertRaises(RuntimeError):
            offline_tests.check(("127.0.0.1", 8014))
        with self.assertRaises(RuntimeError):
            offline_tests.check(("example.com", 443))

    def test_registry_is_complete_and_independent(self):
        systems = subsystems.systems()
        self.assertEqual(len(systems), 15)
        self.assertEqual(len({s["port"] for s in systems}), len(systems))
        self.assertEqual({s["id"]: s["directory"] for s in systems}, import_subsystems.PROJECTS)
        for system in systems:
            root = ROOT / "apps" / system["directory"]
            self.assertTrue(root.is_dir())
            self.assertFalse((root / ".git").exists())
            self.assertFalse((root / ".env").exists())
            self.assertIn("127.0.0.1", subsystems.development_command(system, 19000))

    def test_production_ports_are_never_used_for_development(self):
        system = subsystems.systems()[0]
        for port in [8888, 8009, 8011, 8025, 0, 65536]:
            with self.assertRaises(ValueError):
                subsystems.development_command(system, port)

    def test_snapshot_includes_uncommitted_intraday(self):
        snapshot = json.loads((ROOT / "docs/migration/source-snapshot.json").read_text(encoding="utf-8"))
        intraday = next(p for p in snapshot["projects"] if p["id"] == "intraday")
        self.assertIsNone(intraday["source_head"])
        self.assertIn("server.py", [f["path"] for f in intraday["files"]])
        self.assertFalse(snapshot["services_switched"])

    def test_import_filters_data_not_code(self):
        for path in [".env", "config/private.key", "data/scores.json", "book/a.epub", "research/report.md"]:
            self.assertIsNotNone(import_subsystems.exclusion(path))
        for path in ["data/cache_manager.py", "tests/fixtures/sample.json", ".env.example", "config/themes.json"]:
            self.assertIsNone(import_subsystems.exclusion(path))

    def test_daily_jobs_have_no_git_publish_commands(self):
        # The imported jobs must not be able to publish the shared index.
        import ast
        for relative in ["MyInvestMarket/scripts/run_post_close_update.py", "MyInvestTheme/scripts/daily_mainline_update.py"]:
            tree = ast.parse((ROOT / "apps" / relative).read_text(encoding="utf-8"))
            function = next(node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == "commit_and_push")
            calls = [node for node in ast.walk(function) if isinstance(node, ast.Call)]
            self.assertFalse(any(isinstance(node.func, ast.Name) and node.func.id in {"run_command", "git_output"} for node in calls))
