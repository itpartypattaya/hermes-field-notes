# From a note to an upstream issue

A bugfix patch is a cost you pay on every update until the core fixes it. Reporting it upstream is
how it dies a natural death.

1. `python3 "${HERMES_SKILL_DIR}/scripts/fieldnotes.py" issue-draft <id>` prints a draft: title,
   Hermes version and SHA, symptom, root cause, reproduction, workaround — taken from the note.
2. The draft masks obvious secrets (API keys, bot tokens, whole private-key blocks), home paths,
   IPv4 addresses, e-mail addresses and supergroup chat ids (`-100…`). It does not catch IPv6,
   internal hostnames, positive chat or user ids, or secrets in an unusual format. Masking is a safety net, not a review: read every line
   with the user before anything leaves the machine.
3. Search the upstream tracker for the symptom first; add to an existing issue rather than opening
   a duplicate.
4. Publishing is the user's action. When it exists, put the URL into the note's `upstream` field —
   the dashboard then shows the issue number next to the patch.
5. When the fix lands, the next `patches check` shows `UPSTREAMED` (if the checks file describes the
   upstream signs). Confirm and set `status: fixed-upstream`.
