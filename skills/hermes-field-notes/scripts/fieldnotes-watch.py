#!/usr/bin/env python3
"""fieldnotes-watch.py — Hermes cron job (no_agent) for hermes-field-notes.

Install: `scripts/install.py` copies this file to `$HERMES_HOME/scripts/` (Hermes
runs cron scripts only from there) and `scripts/install_cron.py` creates the job.

Each run calls `fieldnotes.py tick` of the installed skill, which checks the core
and the patches, refreshes the pinned dashboard when it is enabled, and prints a
line only when something changed. Contract with the scheduler (no_agent):
  - nothing changed           → empty stdout → the run is silent;
  - something changed         → one to a few lines → delivered as they are;
  - the skill is broken/slow  → one line, at most once per `alerts.repeat_hours`.
The exit code is always 0: a non-zero code would turn every hourly run into a
raw scheduler alert. No model is called, no tokens are spent.
"""

from __future__ import annotations

import sys

sys.dont_write_bytecode = True

import datetime as dt  # noqa: E402
import json  # noqa: E402
import os  # noqa: E402
import subprocess  # noqa: E402
from pathlib import Path  # noqa: E402

DEFAULT_TIMEOUT = 180
SKILL = "hermes-field-notes"


def hermes_home():
    """$HERMES_HOME, else the home this script was installed into (it lives in
    `<home>/scripts/`), else ~/.hermes."""
    env = os.environ.get("HERMES_HOME")
    if env:
        return Path(env)
    here = Path(__file__).resolve().parent
    if here.name == "scripts" and (here.parent / "config.yaml").is_file():
        return here.parent
    return Path(os.path.expanduser("~/.hermes"))


def find_fieldnotes(home):
    """fieldnotes.py of the installed skill: the plugin copy first, then a regular skill install."""
    explicit = os.environ.get("FIELDNOTES_SCRIPT")
    if explicit:
        return Path(explicit)
    tail = Path(SKILL) / "scripts" / "fieldnotes.py"
    candidates = [home / "plugins" / SKILL / "skills" / tail,
                  home / "skills" / tail,
                  *sorted((home / "skills").glob(f"*/{SKILL}/scripts/fieldnotes.py"))]
    return next((c for c in candidates if c.is_file()), None)


def _config(home):
    try:
        data = json.loads((home / "field-notes.json").read_text(encoding="utf-8-sig"))
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def throttled_error(home, message):
    """Print `message` unless the same kind of failure was reported within repeat_hours."""
    cfg = _config(home)
    try:
        repeat = float((cfg.get("alerts") or {}).get("repeat_hours") or 24)
    except (TypeError, ValueError):
        repeat = 24.0
    path = home / "cache" / "field-notes-watch.json"
    now = dt.datetime.now(dt.timezone.utc)
    try:
        last = dt.datetime.fromisoformat(json.loads(path.read_text(encoding="utf-8")).get("error_at"))
    except (OSError, ValueError, TypeError, AttributeError):
        last = None
    if last and (now - last).total_seconds() < repeat * 3600:
        return
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({"error_at": now.isoformat()}), encoding="utf-8")
    except OSError:
        pass
    print(message)


def clear_error(home):
    try:
        (home / "cache" / "field-notes-watch.json").unlink()
    except OSError:
        pass


def main():
    home = hermes_home()
    script = find_fieldnotes(home)
    if script is None:
        throttled_error(home, f"⚠️ field-notes: skill {SKILL} not found under {home} — reinstall it")
        return 0
    timeout = DEFAULT_TIMEOUT
    try:
        timeout = int((_config(home).get("watch") or {}).get("timeout_sec") or DEFAULT_TIMEOUT)
    except (TypeError, ValueError):
        pass
    try:
        proc = subprocess.run([sys.executable, "-B", str(script), "tick", "--hermes-home", str(home)],
                              capture_output=True, text=True, encoding="utf-8", errors="replace",
                              timeout=timeout)
    except subprocess.TimeoutExpired:
        throttled_error(home, f"⚠️ field-notes: check took longer than {timeout} s and was stopped")
        return 0
    except OSError as exc:
        throttled_error(home, f"⚠️ field-notes: cannot run {script.name}: {exc}")
        return 0
    if proc.returncode != 0:
        tail = (proc.stderr or proc.stdout or "").strip().splitlines()
        throttled_error(home, f"⚠️ field-notes: check failed (exit {proc.returncode}): "
                              f"{tail[-1][:200] if tail else 'no output'}")
        return 0
    clear_error(home)
    out = proc.stdout.strip()
    if out:
        print(out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
