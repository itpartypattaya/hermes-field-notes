#!/usr/bin/env python3
"""install_cron.py — create the hermes-field-notes cron job in Hermes.

The job is `no_agent`: the scheduler runs `fieldnotes-watch.py` and delivers its
stdout verbatim; empty stdout means a silent run. No model, no tokens. Why a
script instead of a documented `hermes cron add` line: `cron/jobs.json` is live
scheduler state, so the supported path is the Python API `cron.jobs.create_job()`
— this script is that path, written down and idempotent.

Run it with the interpreter Hermes itself uses, so the import works:

    ~/.hermes/hermes-agent/venv/bin/python \\
        <skill dir>/scripts/install_cron.py --deliver telegram:<chat_id>:<thread_id>

Flags:
    --deliver local|origin|telegram:<chat_id>[:<thread_id>]   where alert lines go
              (default: the dashboard chat from field-notes.json, else local)
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
from pathlib import Path  # noqa: E402

HOME = Path(os.environ.get("HERMES_HOME") or os.path.expanduser("~/.hermes"))
SCRIPT = "fieldnotes-watch.py"
NAME = "Field notes: core, patches and dashboard"


def _import_jobs():
    sys.path.insert(0, str(HOME / "hermes-agent"))
    try:
        from cron import jobs  # noqa: E402
    except ImportError as exc:  # pragma: no cover — environment problem, not logic
        raise SystemExit(
            f"cannot import Hermes cron API from {HOME / 'hermes-agent'}: {exc}\n"
            "Run this with the Hermes interpreter, e.g.\n"
            f"  {HOME}/hermes-agent/venv/bin/python {Path(__file__).name} --help")
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


def default_deliver():
    try:
        cfg = json.loads((HOME / "field-notes.json").read_text(encoding="utf-8-sig"))
    except (OSError, ValueError):
        return "local"
    dash = (cfg or {}).get("dashboard") or {}
    chat = str(dash.get("chat_id") or "").strip()
    if not chat:
        return "local"
    thread = str(dash.get("thread_id") or "").strip()
    return f"telegram:{chat}:{thread}" if thread else f"telegram:{chat}"


def main(argv=None):
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
