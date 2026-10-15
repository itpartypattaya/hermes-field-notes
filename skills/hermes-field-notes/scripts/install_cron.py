#!/usr/bin/env python3
"""install_cron.py — create the hermes-field-notes cron job in Hermes.

The job is `no_agent`: the scheduler runs `fieldnotes-watch.py` and delivers its
stdout verbatim; empty stdout means a silent run. No model, no tokens. Why a
script instead of a documented `hermes cron add` line: `cron/jobs.json` is live
scheduler state, so the supported path is the Python API `cron.jobs.create_job()`
— this script is that path, written down and idempotent.

It needs the interpreter Hermes itself runs on, so that `cron.jobs` imports with
Hermes' own packages. Run it with any Python 3.11+: it finds that interpreter (the
package manager's active environment from `installs/<key>/facts.json`, else the
legacy `<hermes-agent>/venv`) and re-runs itself with it:

    python3 <skill dir>/scripts/install_cron.py --deliver telegram:<chat_id>:<thread_id>

Flags:
    --deliver local|origin|telegram[:<chat_id>[:<thread_id>]]   where alert lines go
              (default: the dashboard chat from field-notes.json, else the Telegram
              home channel when TELEGRAM_HOME_CHANNEL is set, else local)
    --schedule "17 * * * *"     how often the check runs (default: hourly)
    --force                     create even if a job already exists
    --dry-run                   print what would be created and exit

An existing job is recognised by its `script` field. If the scheduler's job list
cannot be read, the script stops — it never treats "unreadable" as "no jobs".
"""

from __future__ import annotations

import sys

sys.dont_write_bytecode = True

import argparse  # noqa: E402
import json  # noqa: E402
import os  # noqa: E402
import re  # noqa: E402
import subprocess  # noqa: E402
from pathlib import Path  # noqa: E402

HOME = Path(os.environ.get("HERMES_HOME") or os.path.expanduser("~/.hermes"))
SCRIPT = "fieldnotes-watch.py"
NAME = "Field notes: core, patches and dashboard"
REEXEC = "FIELDNOTES_CRON_REEXEC"


def hermes_python(home=None):
    """(environment, interpreter) Hermes runs on, or None. A managed install records its active
    package-manager environment in `installs/<key>/facts.json`; the path changes with every
    `hermes update` or plugin install, so it is looked up each time. `<hermes-agent>/venv` is the
    legacy layout; on a managed install it can be a stale environment left behind."""
    home = home or HOME
    envs = []
    for facts in sorted((home / "installs").glob("*/facts.json")):
        try:
            envs.append(Path(json.loads(facts.read_text(encoding="utf-8-sig"))["packages"]["venv"]["environment"]))
        except (OSError, ValueError, KeyError, TypeError):
            continue
    envs.append(home / "hermes-agent" / "venv")
    for env in envs:
        for name in ("bin/python3", "bin/python", "Scripts/python.exe"):
            if (env / name).is_file():
                return env, env / name
    return None


def ensure_hermes_python(argv, home=None, run=subprocess.run):
    """Re-run this script with Hermes' interpreter unless we already are on it. Returns the exit
    code of that run, or None to go on in this process."""
    found = hermes_python(home)
    if found is None or os.environ.get(REEXEC):
        return None
    env, python = found
    try:
        if Path(sys.prefix).resolve() == env.resolve():
            return None
    except OSError:
        pass
    print(f"-- using the Hermes interpreter {python}", file=sys.stderr)
    return run([str(python), str(Path(__file__).resolve()), *argv], env={**os.environ, REEXEC: "1"}).returncode


def _import_jobs():
    sys.path.insert(0, str(HOME / "hermes-agent"))
    try:
        from cron import jobs  # noqa: E402
    except ImportError as exc:  # pragma: no cover — environment problem, not logic
        raise SystemExit(
            f"cannot import Hermes cron API from {HOME / 'hermes-agent'} with {sys.executable}: {exc}\n"
            "Hermes' interpreter was not found under installs/*/facts.json or hermes-agent/venv; "
            "run this script with the Python that runs Hermes.")
    return jobs


class ListError(Exception):
    pass


def existing(jobs):
    """Jobs that run our script. Raises ListError when the list cannot be read."""
    try:
        try:
            listed = jobs.list_jobs(include_disabled=True)  # a paused job is still ours
        except TypeError:
            listed = jobs.list_jobs()
    except Exception as exc:  # noqa: BLE001
        raise ListError(f"cannot read the cron job list ({type(exc).__name__}: {exc})") from exc
    if isinstance(listed, dict):
        listed = listed.get("jobs", [])
    if not isinstance(listed, list):
        raise ListError("unexpected shape of the cron job list")
    return [j for j in listed if (j or {}).get("script") == SCRIPT]


def _env_value(name):
    """NAME from the environment, else from $HERMES_HOME/.env (where the gateway reads it)."""
    if os.environ.get(name, "").strip():
        return os.environ[name].strip()
    try:
        lines = (HOME / ".env").read_text(encoding="utf-8-sig").splitlines()
    except OSError:
        return ""
    for line in lines:
        m = re.match(r"\s*(?:export\s+)?([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.*)$", line)
        if m and m.group(1) == name:
            raw = m.group(2).strip()
            if len(raw) >= 2 and raw[0] == raw[-1] and raw[0] in "\"'":
                return raw[1:-1].strip()
            return re.sub(r"\s+#.*$", "", raw).strip()
    return ""


def default_deliver():
    """The dashboard chat; without one, the Telegram home channel (a bare `telegram` target is the
    scheduler's home channel, thread included); else local, where nobody reads the alerts."""
    try:
        cfg = json.loads((HOME / "field-notes.json").read_text(encoding="utf-8-sig"))
    except (OSError, ValueError):
        cfg = {}
    dash = (cfg.get("dashboard") or {}) if isinstance(cfg, dict) else {}
    chat = str(dash.get("chat_id") or "").strip()
    if chat:
        thread = str(dash.get("thread_id") or "").strip()
        return f"telegram:{chat}:{thread}" if thread else f"telegram:{chat}"
    return "telegram" if _env_value("TELEGRAM_HOME_CHANNEL") else "local"


def main(argv=None):
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass
    argv = sys.argv[1:] if argv is None else list(argv)
    ap = argparse.ArgumentParser(description="Create the hermes-field-notes cron job")
    ap.add_argument("--deliver", default=None)
    ap.add_argument("--schedule", default="17 * * * *")
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args(argv)

    if not (HOME / "scripts" / SCRIPT).is_file():
        print(f"ERROR: missing {HOME}/scripts/{SCRIPT} — run scripts/install.py first "
              "(Hermes only runs cron scripts from that directory)", file=sys.stderr)
        return 1
    deliver = args.deliver or default_deliver()
    plan = {"name": NAME, "schedule": args.schedule, "script": SCRIPT, "no_agent": True, "deliver": deliver}
    if args.dry_run:
        print(json.dumps(plan, ensure_ascii=False, indent=2))
        return 0
    code = ensure_hermes_python(argv)
    if code is not None:
        return code
    jobs = _import_jobs()
    try:
        found = existing(jobs)
    except ListError as exc:
        print(f"ERROR: {exc} — not creating anything", file=sys.stderr)
        return 1
    if found and not args.force:
        for job in found:
            print(f"-- {SCRIPT} already runs as job {job.get('id')} "
                  f"(schedule {job.get('schedule_display') or job.get('schedule')}, deliver {job.get('deliver')}) "
                  "— left alone (use --force to add another)")
        return 0
    job = jobs.create_job(prompt=None, schedule=args.schedule, name=NAME, deliver=deliver,
                          script=SCRIPT, no_agent=True)
    print(f"OK: created job {job['id']} — {SCRIPT}, {args.schedule}, deliver {deliver}")
    print(f"Next: run it once by hand and check that it is silent or prints one line:\n  hermes cron run {job['id']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
