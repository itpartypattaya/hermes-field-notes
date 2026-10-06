# After `hermes update`, and the hourly watch

## By hand, right after an update

1. `python3 "${HERMES_SKILL_DIR}/scripts/fieldnotes.py" doctor` — core version and SHA, patch
   statuses, core changes outside the registry, notes to re-verify, one verdict line.
2. `MISSING` → show the user the re-apply command from the note; run it only after their "yes";
   restart the gateway; `patches check` again.
3. `UPSTREAMED` → read the evidence; when the user agrees, set `status: fixed-upstream` in the note.
4. `UNKNOWN` → read the evidence (`patches check -v`): `partial` and `conflict` need a human look at
   the file; `target_gone` means the core moved code — update the checks file.
5. `lint` → `stale` lines are notes last verified on another core. Re-check the important ones
   and set `verified_identity` / `verified_at`.
6. `dashboard --publish` if the dashboard is on.

## The hourly watch (optional)

```bash
python3 "${HERMES_SKILL_DIR}/scripts/install.py"     # copies fieldnotes-watch.py to $HERMES_HOME/scripts
"$HERMES_HOME/hermes-agent/venv/bin/python" "${HERMES_SKILL_DIR}/scripts/install_cron.py" --dry-run
"$HERMES_HOME/hermes-agent/venv/bin/python" "${HERMES_SKILL_DIR}/scripts/install_cron.py" \
    --deliver telegram:<chat_id>:<thread_id>
```

The job is `no_agent`: the scheduler runs the script and delivers its stdout as is; empty stdout is
a silent run. No model is called. The script prints a line only when something changed:

- the core identity changed (update) or went back to an earlier one (rollback);
- a patch became `MISSING`, `UNKNOWN` or `UPSTREAMED` — and again when it is back to `OK`;
- core files changed outside the patch registry appeared, or disappeared;
- a new stable Hermes release came out (once per release);
- the dashboard could not be updated or pinned (at most once per `alerts.repeat_hours`).

Hermes runs cron scripts only from `$HERMES_HOME/scripts/`, so the script is a copy. After
updating the skill, run `install.py` again; `install.py --check` reports a stale copy.
