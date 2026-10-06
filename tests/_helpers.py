"""Shared fixtures: load the skill's scripts as modules and build fake Hermes homes."""

from __future__ import annotations

import contextlib
import importlib.util
import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.dont_write_bytecode = True

REPO = Path(__file__).resolve().parents[1]
SKILL = REPO / "skills" / "hermes-field-notes"
SCRIPTS = SKILL / "scripts"


def load(name, filename):
    spec = importlib.util.spec_from_file_location(name, SCRIPTS / filename)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


fn = load("fieldnotes", "fieldnotes.py")

ENV_KEYS = ("HERMES_HOME", "FIELDNOTES_STORE_DIR", "FIELD_NOTES_DIR", "FIELDNOTES_CONFIG", "FIELDNOTES_HERMES_ROOT",
            "FIELDNOTES_TIMEZONE", "FIELDNOTES_LANGUAGE", "FIELDNOTES_NOW", "TELEGRAM_BOT_TOKEN",
            "TELEGRAM_HOME_CHANNEL", "TELEGRAM_HOME_CHANNEL_THREAD_ID", "FIELDNOTES_SCRIPT")

PYPROJECT = '[project]\nname = "hermes-agent"\nversion = "{v}"\n'


def note_text(note_id, **meta):
    base = {"schema_version": 1, "id": note_id, "title": "A claim about something", "date": note_id[:10],
            "updated": note_id[:10], "type": "pitfall", "area": "cron", "status": "active",
            "summary": "dense summary line"}
    base.update(meta)
    return fn.dump_frontmatter(base) + "\n# Title\n\n## Symptom\nError: boom\n"


class HomeCase(unittest.TestCase):
    """A temporary Hermes home with a store and an optional core tree."""

    def setUp(self):
        self._env = {k: os.environ.get(k) for k in ENV_KEYS}
        for k in ENV_KEYS:
            os.environ.pop(k, None)
        self.tmp = Path(tempfile.mkdtemp(prefix="fn-test-"))
        self.home = self.tmp / "hermes"
        self.home.mkdir()
        os.environ["HERMES_HOME"] = str(self.home)
        self.store = self.home / "field-notes"
        (self.store / "notes").mkdir(parents=True)
        self.core = self.home / "hermes-agent"

    def tearDown(self):
        for k, v in self._env.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
        shutil.rmtree(self.tmp, ignore_errors=True)

    # -- builders ---------------------------------------------------------
    def make_core(self, version="0.21.5", files=None, git=False):
        self.core.mkdir(exist_ok=True)
        (self.core / "pyproject.toml").write_text(PYPROJECT.format(v=version), encoding="utf-8")
        for rel, text in (files or {}).items():
            path = self.core / rel
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text, encoding="utf-8")
        if git:
            self.git("init", "-q")
            self.git("add", "-A")
            self.git("-c", "user.email=t@example.com", "-c", "user.name=t", "commit", "-q", "-m", "base")
            self.git("tag", "v" + version)
        return self.core

    def git(self, *argv):
        subprocess.run(["git", "-C", str(self.core), *argv], check=True, capture_output=True)

    def write_note(self, note_id, checks=None, **meta):
        path = self.store / "notes" / f"{note_id}.md"
        path.write_text(note_text(note_id, **meta), encoding="utf-8")
        if checks is not None:
            (self.store / "notes" / f"{note_id}.checks.json").write_text(json.dumps(checks), encoding="utf-8")
        return path

    def write_patch(self, note_id, file, contains, upstream_rules=None, not_contains=None, editions=None, **meta):
        checks = {"schema_version": 1, "editions": editions or [{
            "targets": [{"file": file, "contains": contains, "not_contains": not_contains or []}],
            "upstream": upstream_rules or []}]}
        meta.setdefault("type", "patch")
        meta.setdefault("patch_kind", "bugfix")
        meta.setdefault("patch_short", note_id[11:])
        return self.write_note(note_id, checks=checks, **meta)

    # -- runners ----------------------------------------------------------
    def run_cli(self, *argv):
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = fn.main(list(argv))
        return code, out.getvalue(), err.getvalue()

    def ctx(self, **kw):
        ns = type("A", (), {"hermes_home": None, "config": None, "root": None, "hermes_root": None,
                            "read_only": False, **kw})()
        return fn.Context(ns)

    def files_snapshot(self):
        return sorted(str(p.relative_to(self.tmp)) for p in self.tmp.rglob("*")
                      if ".git" not in p.parts)
