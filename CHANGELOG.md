# Changelog

## 1.2.6 — 2026-10-15

Fixes from a full review of 1.2.5 in the Antigravity CLI. 10 of its 12 findings were confirmed against
the code and fixed. One was not a bug: `core_returned` on a git checkout. Moving forward to a revision seen
before is an update, and the tests pin that. The review also led to one more fix: the documented cron
setup command used a stale interpreter.

- **`doctor` and `patches check`:** a `MISSING` patch now wins over an `UNKNOWN` neighbour (exit 2, not 3).
  The verdict line names every status that needs a look: `MISSING`, `UNKNOWN` and `UPSTREAMED`.
  It no longer says "signs in place" when a patch looks fixed upstream or none applies (`N/A`).
- **Multi-target patch:** one target is gone, another still carries the local edit, and the upstream
  signs are present. This is now `UNKNOWN (conflict)`, not `UPSTREAMED`.
- **Release check with a local commit:** GitHub does not know a commit that was never pushed, so it
  answered 404, and the dashboard showed an error for 12 hours. The check now falls back to the version
  number.
- **`dashboard` without `--publish`** keeps the GitHub answer it fetched, so repeated views do not call
  the API each time.
- **Usage errors** exit with 1. Exit code 2 still means "a patch is MISSING".
- **`fieldnotes-watch.py`:**
  - it writes UTF-8 whatever the locale, so a latin-1 locale or a Windows pipe no longer crashes it on an emoji;
  - each kind of failure is throttled apart, so an hourly timeout no longer hides a broken install for 24 hours.
- **`install.py --check`** reads `.env` the way `fieldnotes.py` does: `export NAME=…`, spaces around `=`,
  quotes.
- **`install_cron.py`:**
  - it re-runs itself with the interpreter Hermes runs on: the active package-manager environment from
    `installs/<key>/facts.json`, else the legacy `<hermes-agent>/venv`. Since 0.22 the documented
    `hermes-agent/venv/bin/python` can be a stale environment left behind. The docs now say `python3`;
  - without `--deliver` and without a dashboard `chat_id`, alerts go to the Telegram home channel when
    `TELEGRAM_HOME_CHANNEL` is set, not to `local`.
- Tests: 95 → 109.

## 1.2.5 — 2026-10-14

Checked against Hermes 0.22.0 (`e06df9c`, Python 3.14):
- `hermes plugins install`, `plugins validate` and the skills scanner all pass and report safe;
- the plugin skill loads (`skill_view`, `skills_list`);
- `install.py`, `doctor` (the new SemVer release tags are read correctly), `lint` and `drift` work, and `--read-only` is accepted in both positions;
- the unit tests pass on 3.14;
- the no_agent job runs through the 0.22.0 scheduler, on both the silent and the alert path.

The catalog rules of 0.22.0 (rule 9, "no runtime overrides of Hermes core") do not touch this skill: its scripts only read the core. No code change was needed; the content was updated.

- **Known pitfalls** re-verified against 0.22.0 (42 entries):
  - Moved to "fixed upstream":
    - `hermes update` following `main` — since 0.21.7 it follows tagged releases;
    - the holographic fact store — it left core in 0.22.0 for a catalog plugin.
  - Partly fixed: skills added mid-chat now reach existing conversations, but changed descriptions, persona and memory edits still do not.
  - Updated:
    - package-manager environment generations instead of `<hermes-agent>/venv`;
    - cron re-runs after an unreachable model;
    - new runtime keys in `jobs.json`;
    - the `session_reset` startup notice;
    - the autostash left after a killed update.
- **Patch recipes:** anchors unchanged in 0.22.0; the four bugfixes are still needed (upstream issues open).
- Version only, no code change; 95 tests.

## 1.2.4 — 2026-10-11

- **Common options before the command.** `fieldnotes.py --read-only doctor` failed with
  "unrecognized arguments: --read-only" (exit 2): `--read-only`, `--json`, `--root`, `--hermes-home`,
  `--hermes-root` and `--config` were accepted only after the subcommand, while agents naturally put
  them first. Both positions work now. The subcommand copies use `argparse.SUPPRESS`, so a flag given
  first is not reset by the subcommand's default. `tick` still refuses `--read-only` in either position.
  Found by the agent itself on Hermes 0.21.6.
- Tests: 94 → 95.

## 1.2.3 — 2026-10-08

Checked against Hermes 0.21.6 (`818c13b`):
- the plugin installs with `hermes plugins install`, and `plugins validate` and the skills scanner both say safe;
- the plugin skill loads;
- `install.py`, `doctor`, `lint`, `drift` and `install_cron.py` work;
- the no_agent job runs through the 0.21.6 scheduler, on both the silent and the alert path.

No code change was needed; the content was updated.

- **Known pitfalls** re-verified against 0.21.6 (42 entries).
  - Moved to "fixed upstream":
    - reasoning delivered as the answer — promotion is now gated by route;
    - a temporary `HERMES_HOME` rewriting the launcher;
    - duplicate YAML keys.
  - Updated:
    - plugin skills reach the index with their full description;
    - `session_reset` notice;
    - cron `last_failure`;
    - `hermes update --channel stable`;
    - gateways paused before the checkout;
    - background processes on gateway shutdown.
  - New: `hermes update` parks local core edits in `git stash` when it cannot restore them.
- **Patch recipes:** the reasoning recipe is marked fixed in 0.21.6, with the upstream sign for its
  checks. The other four bugfixes are still needed.
- **After an update:** for `MISSING`, look at `git stash list` first.
- Tests cover the 0.21.6 tag scheme (`v0.21.6`, `rc.N-v…`, `abandoned-rc.N-v…`, `+canary`): 93 → 94.

## 1.2.2 — 2026-10-09

Fixes ported from [field-notes 2.0.1](https://github.com/itpartypattaya/field-notes/releases/tag/v2.0.1),
found by a Codex CLI review of the sibling skill that shares this code.

- **Locks** (the store lock and the cron/doctor state lock) are OS file locks (`fcntl.flock` /
  `msvcrt.locking`): the OS releases them when the owner exits, and a live owner's lock is never broken
  by age. A long `tick` (slow Telegram calls) can no longer be overtaken by a second run.
- **`migrate`** reads the legacy `**Date:** · **Area:** · **Status:**` line only right after the first
  `# Title`; the same line in a code block is no longer taken as the note's metadata. A file whose first
  line is `---` followed by spaces is treated as frontmatter and, if damaged, skipped.
- **Frontmatter parser** reports unclosed quotes and lists instead of accepting them; a backslash before
  a closing quote is handled (`"C:\\" # comment`).
- **Masking** in `issue-draft`: user names with spaces, Git Bash `/c/Users/…` paths, `C:/Users/…` with
  forward slashes and Claude project slugs (`C--Users-<name>-…`).
- **Secret patterns** (shared by `issue-draft` and `lint`): Telegram bot tokens ending in `-`, all
  `gh*_` tokens, GitLab `glpat-` and friends, lower-case `bearer`, Google API keys, Stripe keys, JWTs.
- **`lint`**: dates must be exactly `YYYY-MM-DD` (Python 3.11+ also parses `20260101` and week dates);
  an unsupported `schema_version` is an error.
- **`search`**: short and technical terms (`r`, `go`, `C++`, `C#`) are matched as whole words, so `go`
  no longer matches `google` and `r` no longer matches everything.
- **`root --json`** prints JSON.
- Tests: 84 → 93.

## 1.2.1 — 2026-10-07

Fixes from a Codex CLI review: secret masking of whole PEM blocks, `tick` refuses `--read-only`, no false
OK/UPSTREAMED, pending alerts survive an interrupted run, no automatic resend after an uncertain send,
lock ownership, a store lock, drift counts untracked files and local commits, rollback by ancestry,
prerelease ordering, migration status mapping.

## 1.2.0 — 2026-10-07

Patch recipes: five core bugfixes and five customization ideas with checks and upstream status.

## 1.1.0 — 2026-10-06

Readable dashboard, core vs the latest release and `main`, banners.

## 1.0.0 — 2026-10-06

First release: pitfalls with root cause, a registry of local core patches checked after every
`hermes update`, an optional pinned Telegram dashboard.
