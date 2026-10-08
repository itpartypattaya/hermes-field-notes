# Writing a patch that survives `hermes update`

`hermes update` moves the core tree to new code. It stashes uncommitted local edits and tries to
re-apply them, but a conflict, a failed syntax or import check or a declined prompt leaves them
parked in `git stash` (`known-pitfalls.md`), so treat every local edit as gone unless your own
script re-applies it.
Ready recipes for known problems: `patch-recipes.md`. Keep each edit as a small, idempotent script outside the core (for example in a folder you version
yourself), and register it with a patch note so the skill can tell when it is missing.

## Rules that proved themselves

1. **One script per patch, idempotent.** Running it twice changes nothing the second time and says
   so ("already applied").
2. **Anchor on exact text, fail closed.** Replace an exact block of the original code. If the anchor
   is not found, stop with an error instead of guessing — the core changed and a human must look.
3. **Leave a unique marker** in the patched code (a comment like `# MYPATCH_QUOTA_BEFORE_AUTH`) and
   use it, plus one line of the new code, in `contains`. Put a line of the original code into
   `not_contains`: a marker that survived while the code under it was replaced is then caught.
4. **Back up before writing** (`file.py.pre-<patch-name>`), write atomically, then run
   `python3 -m py_compile file.py`; on a compile error restore the backup.
5. **Know the version.** Read `version` from `pyproject.toml`. Development builds say `0.0.0` —
   do not treat that as "newer than everything"; use the git tag or the SHA. Give the script one
   branch per range of versions where the anchors differ, and mirror those ranges as `editions`
   in the checks file.
6. **Detect the upstream fix.** If the core already contains the fix, print "fixed upstream" and
   exit 0 without editing; describe the same signs in the checks file's `upstream` list. The next
   `patches check` then reports `UPSTREAMED`, and the patch can retire.
7. **Restart what loaded the code.** The gateway keeps the old code in memory until restarted.

## Lifecycle

`new <slug> --type patch` → edit + script + checks → `patches check` says `OK` → after every update
`doctor` → `MISSING`: re-run the script (with the owner's consent) → `UPSTREAMED`: confirm, set
`status: fixed-upstream`, keep the script only as long as you may roll back.

Bugfixes should go upstream: `fieldnotes.py issue-draft <id>` drafts the report. Customizations
(behaviour you want and upstream does not) stay local for good; write why in
`upstream_none_reason`.
