# Changelog

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
