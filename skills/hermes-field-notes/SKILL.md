---
name: hermes-field-notes
description: "Hermes pitfalls and core patches: search, record, verify."
version: 1.0.0
author: "Anton Vaskov (itpartypattaya), https://t.me/passone"
license: MIT
compatibility: Hermes Agent >= 0.21 (written against 0.21.5)
allowed-tools: terminal read_file write_file patch
tags: [debugging, pitfalls, patches, hermes-update, knowledge, dashboard]
---

# Hermes Field Notes Skill

Keeps what this Hermes installation taught you: pitfalls with their root cause, local patches of
the Hermes core, and observations worth keeping. Before debugging, it searches those notes and a
bundled list of verified Hermes pitfalls; after `hermes update`, it checks read-only that every
local core patch is still in place and that nobody edited the core outside the registry. An
optional pinned Telegram message shows the state. It never edits the core and never runs patch
scripts — it records, verifies and reminds.

## When to Use

- A Hermes problem appears (gateway error, cron did not fire, a tool returned nothing, "broke after
  update") — search the notes **before** debugging.
- A diagnosis took more than a couple of steps, or the cause was not what the symptom suggested —
  record it.
- You are about to edit a file inside the hermes-agent tree, or you just did — register the patch.
- Hermes was updated, a watch alert arrived, or the user asks whether the patches survived.
- The user asks for the dashboard, an upstream issue draft, or "what do we know about X".

## Prerequisites

- The `terminal` tool and Python 3.11+ (standard library only).
- First run: `python3 "${HERMES_SKILL_DIR}/scripts/install.py"` — creates the store
  (`$HERMES_HOME/field-notes/`), the config `$HERMES_HOME/field-notes.json`, and copies the cron
  script. `--check` verifies an existing setup and changes nothing.
- Optional hourly watch + dashboard: `scripts/install_cron.py` (run it with Hermes' own Python, see
  `references/after-update.md`). The dashboard uses the agent's own Telegram bot.

## How to Run

`FN="${HERMES_SKILL_DIR}/scripts/fieldnotes.py"`, then `python3 "$FN" <command>`:

| Command | What it does |
|---|---|
| `search <words…>` | notes + bundled known pitfalls, ranked; says "0 matches" honestly |
| `new <slug> --type pitfall\|patch\|observation --area <area> --title "<claim>"` | note from the template (patch: also `<id>.checks.json`) |
| `index` · `lint` | regenerate `INDEX.md` · validate notes, checks, links, secrets, staleness |
| `patches` · `patches check` | list patch notes · static check against the core on disk |
| `drift` | core changes (git) and whether patch notes cover them |
| `doctor` | core identity + patches + drift + notes to re-verify, one verdict line |
| `dashboard [--format md\|text]` · `dashboard --publish` | render · send/edit the pinned message |
| `issue-draft <id>` | upstream issue draft from a note (stdout, never posted) |
| `migrate --from <dir> [--apply]` | import older field-notes formats (dry run by default) |

Add `--read-only` to any command to guarantee no writes and no network; `--json` for machine output.

## Quick Reference

| `patches check` status | Meaning | Your move |
|---|---|---|
| `OK` | all signs present in every target | nothing (it is a static check, not proof it works) |
| `MISSING` | target present, signs absent | show the user; re-apply only after their "yes" |
| `UPSTREAMED` | signs absent, upstream signs present | propose `status: fixed-upstream`; the user confirms |
| `N/A` | no edition matches this core version | nothing |
| `UNKNOWN` (`partial`, `conflict`, `target_gone`, `version_unknown`, `bad_checks`, `unreadable`) | the check could not decide | read the evidence, fix the checks or ask |

Exit codes: 0 fine · 1 errors · 2 a patch is MISSING · 3 a patch is UNKNOWN · 4 store or core not found.

## Procedure

1. **Search before fixing.** Query by the error text, tool or flag name, symptom — not by your
   hypothesis. If a note matches, read it whole, especially "What misled us". A negative result
   from a tool (empty grep, clean log) is a reason to search too.
2. **Record after a non-trivial diagnosis**, in the same session while details are alive: the cause
   differed from the symptom; a tool lied silently (exit 0, plausible value, empty result); an
   obvious fix broke something nearby; behaviour depends on version or platform; diagnosis cost
   more than the fix. Not for ordinary bugs in your own code or what the docs say in paragraph one.
   Use `new`, fill every section that applies (delete the rest), write a dense `summary`.
3. **Update, don't duplicate.** The same mechanism again → edit the existing note: bump `updated`,
   add `## Update YYYY-MM-DD: <what is new>`. `new` refuses an existing slug and lists similar notes.
4. **Every core edit is a patch note.** Ask the user before touching hermes-agent. Then `new <slug>
   --type patch`, put a unique marker comment in the code, describe the signs in
   `<id>.checks.json` (`contains`, `not_contains`, `upstream`, per version), keep an idempotent
   re-apply script (`references/patch-scripts.md`). Set `patch_kind`: `bugfix`, `customization`
   or `workaround`; non-bugfixes without an upstream link need `upstream_none_reason`.
5. **After `hermes update` or an alert:** `doctor`. Walk every non-OK patch with the user (table
   above), then `lint` — `stale` lines are notes verified on another core; re-check them and set
   `verified_identity`/`verified_at`. Finish with `dashboard --publish` if the dashboard is on.
6. **Bugfix patches belong upstream.** On request, `issue-draft <id>`; review the masked text with
   the user. Publishing is the user's action, never yours.
7. **After any write:** `index`, then `lint`, then `dashboard --publish` (if enabled).
8. **Promote to a skill** when one class of problem repeats (3+ notes), has a checkable procedure
   and needs activation before anyone knows to search. Set `status: promoted`, keep the note.

## Pitfalls

- The note's date and core identity come from the script (`new`), not from memory.
- Never store secrets, tokens, personal data or internal hosts: mask them (`lint` flags obvious ones).
- `OK` means the signs are present, not that the patch works; keep behavioural checks in the note.
- A marker alone is weak: add a line of the new code to `contains` and the old code to `not_contains`.
- The skill folder is read-only and replaced on update: notes live in the store, never here.
- `drift` reads the tree on disk, not the running gateway — restart after re-applying a patch.

## Verification

- `python3 "$FN" lint` exits 0; `python3 "$FN" index` says "up to date".
- `python3 "$FN" doctor` ends with a verdict line; exit 0 when every live patch is `OK`.
- `python3 "${HERMES_SKILL_DIR}/scripts/install.py" --check` reports 0 problems.
- Dashboard on: the pinned message shows the new state after `dashboard --publish`.

More: `references/note-format.md` (fields, statuses, areas), `references/patch-scripts.md`,
`references/after-update.md` (cron job, update routine), `references/dashboard.md`,
`references/upstreaming.md`, `references/known-pitfalls.md` (verified Hermes pitfalls).
