#!/usr/bin/env python3
"""install.py — set up hermes-field-notes in a Hermes home, and verify the setup.

    python3 install.py            create the store, seed the config, copy the cron script, verify
    python3 install.py --check    verify only, change nothing (exit 1 on any problem)

Hermes runs cron scripts only from $HERMES_HOME/scripts (a symlink does not help),
so `fieldnotes-watch.py` is COPIED there — and a copy can silently drift from
the skill after an update. `--check` catches exactly that. Everything is
idempotent; re-running is safe. Standard library only.
"""

from __future__ import annotations

import sys

sys.dont_write_bytecode = True

import argparse  # noqa: E402
import filecmp  # noqa: E402
import json  # noqa: E402
import os  # noqa: E402
import shutil  # noqa: E402
import subprocess  # noqa: E402
from pathlib import Path  # noqa: E402

SKILL_DIR = Path(__file__).resolve().parents[1]
WATCH = "fieldnotes-watch.py"
EXAMPLE = SKILL_DIR / "examples" / "field-notes.example.json"
KNOWN_KEYS = {"store_dir", "hermes_root", "patch_scripts_base", "timezone", "language", "drift",
              "dashboard", "alerts", "watch"}


class Report:
    def __init__(self):
        self.bad_n = self.warn_n = 0

    def ok(self, msg):
        print(f"  ✓ {msg}")

    def warn(self, msg):
        print(f"  ! {msg}")
        self.warn_n += 1

    def bad(self, msg):
        print(f"  ✗ {msg}")
        self.bad_n += 1


def _home(arg):
    if arg:
        return Path(arg).expanduser()
    env = os.environ.get("HERMES_HOME")
    return Path(env) if env else Path(os.path.expanduser("~/.hermes"))


def _fieldnotes(home, *argv):
    return subprocess.run([sys.executable, "-B", str(SKILL_DIR / "scripts" / "fieldnotes.py"), *argv,
                           "--hermes-home", str(home)],
                          capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=180)


def check(home, rep):
    if not home.is_dir():
        rep.bad(f"Hermes home not found: {home}")
        return
    cfg_path = home / "field-notes.json"
    cfg = {}
    if cfg_path.is_file():
        try:
            cfg = json.loads(cfg_path.read_text(encoding="utf-8-sig"))
            unknown = sorted(k for k in cfg if not k.startswith("_") and k not in KNOWN_KEYS)
            if unknown:
                rep.warn(f"{cfg_path.name}: unknown keys {', '.join(unknown)} (ignored)")
            else:
                rep.ok(f"config {cfg_path}")
        except ValueError as exc:
            rep.bad(f"{cfg_path} is not valid JSON: {exc}")
    else:
        rep.warn(f"no {cfg_path.name} — defaults apply (run install.py without --check to seed it)")
    copy = home / "scripts" / WATCH
    if not copy.is_file():
        rep.bad(f"missing {copy} — run install.py (Hermes only runs cron scripts from that directory)")
    elif not filecmp.cmp(copy, SKILL_DIR / "scripts" / WATCH, shallow=False):
        rep.bad(f"{copy} differs from the skill's copy — re-run install.py to refresh it")
    else:
        rep.ok(f"cron script {copy} matches the skill")
    proc = _fieldnotes(home, "root")
    store = Path(proc.stdout.strip()) if proc.returncode == 0 else None
    if store is None:
        rep.bad(f"fieldnotes.py root failed: {(proc.stderr or '').strip()}")
    elif not (store / "notes").is_dir():
        rep.bad(f"no notes store at {store} — run install.py")
    else:
        rep.ok(f"notes store {store}")
    proc = _fieldnotes(home, "doctor", "--read-only", "--json")
    if proc.returncode in (0, 2, 3):
        try:
            data = json.loads(proc.stdout)
            core = data["report"]["core"]
            rep.ok(f"dry run: core {core['version']} found={core['exists']}, "
                   f"{data['report']['patches']['total']} live patches, {data['report']['notes']['total']} notes")
            if not core["exists"]:
                rep.warn("Hermes core not found — set hermes_root in field-notes.json")
        except (ValueError, KeyError) as exc:
            rep.bad(f"dry run returned unexpected output: {exc}")
    else:
        rep.bad(f"dry run failed: {(proc.stderr or proc.stdout).strip()[:300]}")
    dash = (cfg.get("dashboard") or {}) if isinstance(cfg, dict) else {}
    if dash.get("enabled"):
        token_env = str(dash.get("bot_token_env") or "TELEGRAM_BOT_TOKEN")
        has_token = bool(os.environ.get(token_env)) or _env_file_has(home, token_env)
        has_chat = bool(dash.get("chat_id")) or _env_file_has(home, "TELEGRAM_HOME_CHANNEL") \
            or bool(os.environ.get("TELEGRAM_HOME_CHANNEL"))
        if has_token and has_chat:
            rep.ok("dashboard: bot token and chat are configured")
        else:
            rep.bad(f"dashboard enabled but {'no ' + token_env if not has_token else 'no chat_id'}")


def _env_file_has(home, name):
    try:
        for line in (home / ".env").read_text(encoding="utf-8-sig").splitlines():
            if line.strip().startswith(f"{name}=") and line.split("=", 1)[1].strip():
                return True
    except OSError:
        pass
    return False


def install(home, rep):
    if not home.is_dir():
        rep.bad(f"Hermes home not found: {home}")
        return
    cfg_path = home / "field-notes.json"
    if cfg_path.exists():
        rep.ok(f"{cfg_path.name} exists — left as it is")
    else:
        shutil.copyfile(EXAMPLE, cfg_path)
        rep.ok(f"seeded {cfg_path} from the example — edit it (timezone, language, dashboard)")
    proc = _fieldnotes(home, "init")
    if proc.returncode == 0:
        rep.ok(f"notes store {proc.stdout.strip().splitlines()[-1]}")
    else:
        rep.bad(f"init failed: {(proc.stderr or '').strip()}")
    dest = home / "scripts" / WATCH
    dest.parent.mkdir(parents=True, exist_ok=True)
    src = SKILL_DIR / "scripts" / WATCH
    if dest.is_file() and filecmp.cmp(dest, src, shallow=False):
        rep.ok(f"{dest} is up to date")
    else:
        shutil.copyfile(src, dest)
        rep.ok(f"copied {WATCH} → {dest}")


def main(argv=None):
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8")
        except (AttributeError, ValueError):
            pass
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--hermes-home", help="default: $HERMES_HOME or ~/.hermes")
    ap.add_argument("--check", action="store_true", help="verify only, change nothing")
    args = ap.parse_args(argv)
    home = _home(args.hermes_home)
    rep = Report()
    if not args.check:
        print(f"install into {home}")
        install(home, rep)
    print(f"check {home}")
    check(home, rep)
    print(f"-- {rep.bad_n} problems, {rep.warn_n} warnings")
    if not args.check and not rep.bad_n:
        print("next: create the cron job with scripts/install_cron.py (run it with Hermes' own python)")
    return 1 if rep.bad_n else 0


if __name__ == "__main__":
    raise SystemExit(main())
