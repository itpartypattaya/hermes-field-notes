"""install.py, install_cron.py and fieldnotes-watch.py, run as real subprocesses against a temp home."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import unittest

from _helpers import SCRIPTS, HomeCase

FAKE_CRON = '''
import json, pathlib
_DB = pathlib.Path(__file__).with_name("jobs.json")
def _load():
    return json.loads(_DB.read_text()) if _DB.exists() else []
def list_jobs(include_disabled=False):
    if pathlib.Path(__file__).with_name("BROKEN").exists():
        raise RuntimeError("db locked")
    return _load()
def create_job(**kw):
    jobs = _load(); kw["id"] = "job%d" % (len(jobs) + 1); jobs.append(kw)
    _DB.write_text(json.dumps(jobs)); return kw
'''


class InstallTest(HomeCase):
    def run_py(self, script, *argv, env=None):
        full_env = dict(os.environ, PYTHONDONTWRITEBYTECODE="1", PYTHONIOENCODING="utf-8", **(env or {}))
        return subprocess.run([sys.executable, str(script), *argv], capture_output=True, text=True,
                              encoding="utf-8", env=full_env, timeout=120)

    def test_install_seeds_and_check_catches_drift(self):
        import shutil
        shutil.rmtree(self.store)
        self.make_core(files={"a.py": "x"})
        (self.home / "config.yaml").write_text("x: 1\n", encoding="utf-8")
        proc = self.run_py(SCRIPTS / "install.py")
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.assertTrue((self.home / "field-notes.json").is_file())
        self.assertTrue((self.home / "scripts" / "fieldnotes-watch.py").is_file())
        self.assertTrue((self.store / "INDEX.md").is_file())
        proc = self.run_py(SCRIPTS / "install.py", "--check")
        self.assertEqual(proc.returncode, 0, proc.stdout)
        (self.home / "scripts" / "fieldnotes-watch.py").write_text("# stale copy\n", encoding="utf-8")
        proc = self.run_py(SCRIPTS / "install.py", "--check")
        self.assertEqual(proc.returncode, 1)
        self.assertIn("differs from the skill", proc.stdout)
        proc = self.run_py(SCRIPTS / "install.py")                      # re-run refreshes the copy
        self.assertEqual(proc.returncode, 0, proc.stdout)
        self.assertIn("copied fieldnotes-watch.py", proc.stdout)

    def test_install_keeps_existing_config(self):
        (self.home / "field-notes.json").write_text('{"language": "ru"}', encoding="utf-8")
        self.run_py(SCRIPTS / "install.py")
        self.assertEqual(json.loads((self.home / "field-notes.json").read_text(encoding="utf-8")), {"language": "ru"})

    def test_check_flags_enabled_dashboard_without_token(self):
        self.run_py(SCRIPTS / "install.py")
        (self.home / "field-notes.json").write_text('{"dashboard": {"enabled": true, "chat_id": "-1001"}}',
                                                    encoding="utf-8")
        proc = self.run_py(SCRIPTS / "install.py", "--check")
        self.assertEqual(proc.returncode, 1)
        self.assertIn("no TELEGRAM_BOT_TOKEN", proc.stdout)

    def test_install_cron_dry_run_idempotent_and_safe(self):
        cron = self.make_core() / "cron"
        cron.mkdir()
        (cron / "__init__.py").write_text("", encoding="utf-8")
        (cron / "jobs.py").write_text(FAKE_CRON, encoding="utf-8")
        proc = self.run_py(SCRIPTS / "install_cron.py", "--dry-run")
        self.assertEqual(proc.returncode, 1)
        self.assertIn("run scripts/install.py first", proc.stderr)
        self.run_py(SCRIPTS / "install.py")
        (self.home / "field-notes.json").write_text(
            '{"dashboard": {"chat_id": "-1001234567890", "thread_id": "42"}}', encoding="utf-8")
        proc = self.run_py(SCRIPTS / "install_cron.py", "--dry-run")
        plan = json.loads(proc.stdout)
        self.assertEqual((plan["no_agent"], plan["deliver"]), (True, "telegram:-1001234567890:42"))
        proc = self.run_py(SCRIPTS / "install_cron.py")
        self.assertIn("created job job1", proc.stdout)
        proc = self.run_py(SCRIPTS / "install_cron.py")
        self.assertIn("already runs as job job1", proc.stdout)
        jobs = json.loads((cron / "jobs.json").read_text())
        self.assertEqual(len(jobs), 1)
        self.assertEqual(jobs[0]["script"], "fieldnotes-watch.py")
        (cron / "BROKEN").write_text("", encoding="utf-8")
        proc = self.run_py(SCRIPTS / "install_cron.py", "--force")
        self.assertEqual(proc.returncode, 1)
        self.assertIn("not creating anything", proc.stderr)


class WatchTest(HomeCase):
    def run_watch(self, env=None):
        full_env = dict(os.environ, PYTHONDONTWRITEBYTECODE="1", PYTHONIOENCODING="utf-8", **(env or {}))
        return subprocess.run([sys.executable, str(SCRIPTS / "fieldnotes-watch.py")], capture_output=True,
                              text=True, encoding="utf-8", env=full_env, timeout=120)

    def test_silent_then_reports_change(self):
        self.make_core(files={"a.py": "MARK"})
        self.write_patch("2026-01-01-a", "a.py", ["MARK"], patch_short="Patch A")
        env = {"FIELDNOTES_SCRIPT": str(SCRIPTS / "fieldnotes.py")}
        proc = self.run_watch(env)
        self.assertEqual((proc.returncode, proc.stdout), (0, ""), proc.stderr)
        (self.core / "a.py").write_text("gone", encoding="utf-8")
        proc = self.run_watch(env)
        self.assertEqual(proc.returncode, 0)
        self.assertIn("Patch «Patch A» is missing", proc.stdout)

    def test_skill_not_found_and_failure_are_throttled(self):
        proc = self.run_watch({"FIELDNOTES_SCRIPT": ""})
        self.assertEqual(proc.returncode, 0)
        self.assertIn("not found", proc.stdout)
        self.assertEqual(self.run_watch({"FIELDNOTES_SCRIPT": ""}).stdout, "")
        broken = self.tmp / "broken.py"
        broken.write_text("import sys; sys.exit(5)\n", encoding="utf-8")
        (self.home / "cache" / "field-notes-watch.json").unlink()
        proc = self.run_watch({"FIELDNOTES_SCRIPT": str(broken)})
        self.assertEqual(proc.returncode, 0)
        self.assertIn("check failed (exit 5)", proc.stdout)
        self.assertEqual(self.run_watch({"FIELDNOTES_SCRIPT": str(broken)}).stdout, "")

    def test_finds_regular_skill_install(self):
        skill = self.home / "skills" / "devops" / "hermes-field-notes" / "scripts"
        skill.mkdir(parents=True)
        (skill / "fieldnotes.py").write_text("print('found me')\n", encoding="utf-8")
        proc = self.run_watch()
        self.assertEqual(proc.stdout.strip(), "found me")


if __name__ == "__main__":
    unittest.main()
