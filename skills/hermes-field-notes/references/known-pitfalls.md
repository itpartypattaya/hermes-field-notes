# Known Hermes pitfalls

A curated list of Hermes Agent behaviours that cost real debugging time: silent misconfigurations,
misleading messages and core mechanisms that surprise operators. Every entry was collected on a
production installation, generalized, and then re-verified by reading the upstream source of
Hermes 0.21.6 (commit `818c13b`) on 2026-10-08 (first pass: a build from `main` after the 0.21.5
tag, `8d30c4e`, on 2026-10-06; the tagged 0.21.5 is `v2026.9.24`); file paths are relative to the
`hermes-agent` checkout (`<hermes-agent>/…`), and `$HERMES_HOME` is the agent home (`~/.hermes` by
default). Entries that could not be traced to code were left out. Fixed behaviours are kept at the
end for installations still on older versions. To propose a new pitfall or a correction, open a pull
request against `itpartypattaya/hermes-field-notes` using the same entry format and include the
file and function where the mechanism lives.

## Skills and plugin packaging

### Only the first 57 characters of a skill description reach the model
- **Affects:** skills from `$HERMES_HOME/skills/` and bundled skills, all current versions (limit constant since 0.19.1). Since 0.21.6, skills registered by an enabled plugin (a portable `plugin.json` package or `ctx.register_skill`) are listed with their full description (portable: up to 1024 characters); before 0.21.6 they were missing from the index.
- **Symptom:** the skill exists and is enabled, but the agent never picks it; the skills index shows `<first 57 chars>...`.
- **Mechanism:** `agent/skill_utils.py` `extract_skill_description()` cuts at `SKILL_PROMPT_DESC_LIMIT = 60` (57 + `...`); `agent/prompt_builder.py` builds the system-prompt skills index from that cut. The full text is seen only after `skill_view`.
- **Workaround:** put the trigger words in the first ~55 characters of `description:`; check with `python3 -c "import re,sys;d=re.search(r'^description:\s*(.*)',open(sys.argv[1]).read(),re.M).group(1);print(d[:57])" SKILL.md`.
- **Verified:** 0.21.6 (818c13b), 2026-10-08
- **Upstream:** not reported (by design)

### An unquoted colon in SKILL.md frontmatter silently degrades the skill's metadata
- **Affects:** skills loaded from `$HERMES_HOME/skills/`, any version; typical trigger is `description: Do X: then Y` without quotes.
- **Symptom:** no error and the skill still works, but `allowed-tools` arrives as a string (or disappears when written as a `- item` list), `metadata` is empty and nested keys show up at top level.
- **Mechanism:** `agent/skill_utils.py` `parse_frontmatter()` catches the YAML error and falls back to `line.split(":", 1)` per line, which keeps flat keys and destroys nesting.
- **Workaround:** quote the description (`description: "Do X: then Y"`) and parse every frontmatter with a strict YAML loader in CI. Restart the gateway or start a new session to see the corrected header.
- **Verified:** 0.21.6 (818c13b), 2026-10-08
- **Upstream:** not reported

### A portable plugin (plugin.json) drops a skill whose frontmatter is invalid, and validation still passes
- **Affects:** Agent Plugins v1 packages installed with `hermes plugins install`.
- **Symptom:** `hermes plugins validate` reports the manifest as OK with one warning such as `skill:<name>: invalid SKILL.md: invalid YAML frontmatter: …`; after install the skill is simply missing.
- **Mechanism:** `hermes_cli/agent_plugins.py` `_discover_skills()` skips the skill with a diagnostic when YAML fails, `metadata` is not a string-to-string map, `allowed-tools` is not a string, `name` differs from the folder, or the description is longer than 1024 characters; `hermes_cli/plugin_validate.py` turns those diagnostics into warnings only.
- **Workaround:** quote descriptions, keep `metadata` flat (string values only), write `allowed-tools` as one string, and treat every validate warning as a failure.
- **Verified:** 0.21.6 (818c13b), 2026-10-08
- **Upstream:** not reported

### Any high-severity scanner finding blocks a community skill, including a plain environment copy
- **Affects:** skills installed from a community source via `hermes skills install`.
- **Symptom:** install refused with verdict `caution`; the finding id is `python_os_environ`, described as a potential environment dump.
- **Mechanism:** `tools/skills_guard.py` `INSTALL_POLICY["community"]` blocks `caution`, and any `high` finding yields `caution`. The rule fires on any reference to the Python environment mapping that is not a `.get(` call — copying it into a dict, subscripting it, unpacking it — and on the Node equivalent. It scans every file of the skill folder, Markdown included, so even documentation that quotes such code is flagged.
- **Workaround:** read variables with `os.environ.get("NAME")` / `os.getenv`, build child environments from an explicit allowlist, and keep tests and example payloads under `tests/`. The skill linter also warns about `README.md`, `CHANGELOG.md`, `install.sh`, `.env*` and `.gitignore` inside a skill folder (`tools/skill_linter.py` `_FORBIDDEN_FILES`); keep installers in `scripts/`.
- **Verified:** 0.21.6 (818c13b), 2026-10-08
- **Upstream:** not reported (by design)

### Edits to skills, persona or memory do not reach conversations that already exist
- **Affects:** gateway platforms with long-lived sessions (Telegram groups, forum topics).
- **Symptom:** a new or fixed skill shows as enabled in `hermes skills list`, a gateway restart is done, and the agent in the same chat still says the skill does not exist.
- **Mechanism:** `agent/conversation_loop.py` reuses the system prompt stored for a continuing session ("Continuing session — reuse the exact system prompt") to keep the provider cache prefix stable; the stored prompt lives in `state.db`, so a restart does not rebuild it.
- **Workaround:** send `/new` (or wait for context compression) in each affected chat after changing skills, persona files or the skills index.
- **Verified:** 0.21.6 (818c13b), 2026-10-08
- **Upstream:** not reported (by design)

## Configuration

### Unquoted `N:M` values in config.yaml are parsed as base-60 numbers
- **Affects:** every YAML file Hermes reads (config, frontmatter, manifests); YAML 1.1 rules in all versions.
- **Symptom:** `telegram.free_response_topics: -1001234567890:2` never matches; after a config rewrite or migration the file shows `-60074074073402`.
- **Mechanism:** the shared loader resolves YAML 1.1 (`hermes_yaml.py` on current builds, PyYAML before), where `a:b` is sexagesimal; `plugins/platforms/telegram/adapter.py` `_extra_str_set()` then stringifies the integer. Same family: `0755` becomes 493, `no`/`off` become `false`, and on current builds bare `y`/`n` become booleans.
- **Workaround:** quote every identifier-like value (`'-1001234567890:2'`, `'08:30'`), and test the parsed value rather than the file text: `python3 -c "import yaml;print(repr(yaml.safe_load(open('config.yaml'))['telegram']['free_response_topics']))"`.
- **Verified:** 0.21.6 (818c13b), 2026-10-08
- **Upstream:** not reported

### Timed `session_reset` (idle/daily) silently stopped working in 0.21.1
- **Affects:** 0.21.1 and later with `session_reset.mode: idle|daily|both`; since 0.21.6 gateway startup and `hermes doctor` print a notice.
- **Symptom:** conversations never rotate on their own; context and cost grow until someone types `/new`. No warning before 0.21.6.
- **Mechanism:** commit `1d5d059410` ("stop time-triggered conversation rotation", first released in 0.21.1) removed the timers; core reads nothing under `session_reset`. Since 0.21.6 (`0d5aae5e24`) `hermes_cli/session_reset_retirement.py` reports it at gateway startup and in `hermes doctor`; nothing restores the timers.
- **Workaround:** `hermes plugins install hermes-session-reset-policy` and enable it; it reads the existing top-level `session_reset` block. Its clock is the process local time (see the timezone entry below).
- **Verified:** 0.21.6 (818c13b), 2026-10-08
- **Upstream:** removal intentional; notice since 0.21.6

### The `timezone` setting does not change the process clock seen by plugins
- **Affects:** plugins, hooks and scripts that call `datetime.now()` / `time.localtime()` inside the gateway.
- **Symptom:** a plugin scheduled for "04:00" fires at 04:00 of the host or unit timezone (often UTC), not the configured one.
- **Mechanism:** `hermes_time.py` applies `timezone` / `HERMES_TIMEZONE` only through `hermes_time.now()`; core never sets `TZ` for its own process (only for code-execution children, `tools/code_execution_env.py`).
- **Workaround:** in plugin code use `hermes_time.now()` or an explicit `ZoneInfo("Europe/Berlin")`; or set `Environment=TZ=Europe/Berlin` in the gateway unit. Convert any hour-based plugin setting accordingly.
- **Verified:** 0.21.6 (818c13b), 2026-10-08
- **Upstream:** not reported

## Telegram and gateway

### With observed group context, /new and other slash commands act on the wrong session
- **Affects:** Telegram groups listed in `telegram.group_allowed_chats` with `telegram.observe_unmentioned_group_messages: true`, default `group_sessions_per_user: true`; forum topics are not affected.
- **Symptom:** `/new` answers as if it reset, but the bot keeps the old context; `/model` seems to have no effect; `/context` shows a different session.
- **Mechanism:** `plugins/platforms/telegram/adapter.py` `_apply_telegram_group_observe_attribution()` strips `user_id` from normal messages (one shared room session) but keeps it on COMMAND events; `gateway/session.py` `build_session_key()` then adds the participant id, so `gateway/run.py` `_session_key_for_source()` resolves a per-user key nobody talks in.
- **Workaround:** set top-level `group_sessions_per_user: false` (commands and messages then share one key), or use a forum topic for that group.
- **Verified:** 0.21.6 (818c13b), 2026-10-08
- **Upstream:** https://github.com/NousResearch/hermes-agent/issues/65085

### In observed groups, plugins cannot tell who is asking
- **Affects:** plugins and tool gates that read the sender (`HERMES_SESSION_USER_ID`) in groups configured as in the previous entry.
- **Symptom:** a per-user tool allowlist refuses the owner's own request in that group while the same request works in a private chat.
- **Mechanism:** the shared source has `user_id=None`, so `gateway/session_context.py` exports an empty `HERMES_SESSION_USER_ID`; the `[name|id]` prefix in the message text is written into user-controlled text and is not proof of identity.
- **Workaround:** fail closed, but narrow by action instead of by person (for example allow read-only tools scoped to the same chat id), and explain the refusal so the model does not invent a cause.
- **Verified:** 0.21.6 (818c13b), 2026-10-08
- **Upstream:** not reported (by design)

### A reply made only of invisible characters is sent as an empty-looking Telegram message
- **Affects:** Telegram delivery, all current versions.
- **Symptom:** blank message bubbles from the bot.
- **Mechanism:** `plugins/platforms/telegram/adapter.py` `send()` and `tools/send_message_senders.py` skip only `.strip()`-empty text; `str.strip()` keeps U+200B/200C/200D/2060/FEFF/00AD.
- **Workaround:** strip zero-width characters before the emptiness check in a `transform_llm_output` hook or local patch; log a `repr()` preview to find the source.
- **Verified:** 0.21.6 (818c13b), 2026-10-08
- **Upstream:** https://github.com/NousResearch/hermes-agent/issues/60848

### A `/model` pin belongs to one session key, not to the chat
- **Affects:** gateway `/model` overrides.
- **Symptom:** a new forum topic, or a new per-user session in the same group, answers with `model.default` despite the earlier pin.
- **Mechanism:** `gateway/session.py` `set_model_override(session_key, …)` stores the override on the session entry; there is no per-chat model setting in config.
- **Workaround:** set `/model` again in each new topic or session, or change `model.default`.
- **Verified:** 0.21.6 (818c13b), 2026-10-08
- **Upstream:** not reported

## Cron

### Cron on a system-level gateway service needs lingering enabled for the service user
- **Affects:** 0.21.1 and later, Linux, gateway installed as a system unit with `User=`; most visible on hosts where that user logs in only over SSH.
- **Symptom:** after the last SSH session closes, runs fail with `restart-safe systemd scope could not be created: the user D-Bus session … disappeared` (0.21.4+) or `cron external worker exited before ownership acknowledgement (exit 1)` (0.21.1–0.21.3, every job, no incident).
- **Mechanism:** `cron/scheduler.py` dispatches each run through `systemd-run --user --scope` (`tools/process_registry.py` `restart_safe_gateway_child_argv()`); without linger the user manager and its bus exist only during a login session. 0.21.4 re-probes every 60 s and degrades to an unscoped run (which dies with the gateway).
- **Workaround:** run `loginctl enable-linger <service-user>` with root privileges and restart the gateway; confirm with `loginctl show-user <service-user> -p Linger`.
- **Verified:** 0.21.6 (818c13b), 2026-10-08
- **Upstream:** https://github.com/NousResearch/hermes-agent/issues/110803, https://github.com/NousResearch/hermes-agent/issues/104893 (fixed in 0.21.4); dispatch failures raise a cron incident since 0.21.6 (`ecc5c263ec`, #123401)

### `last_status: ok` hides intermittent cron failures, and history is short
- **Affects:** anyone judging cron health from `jobs.json` or `hermes cron list`.
- **Symptom:** jobs failed for hours, yet every job shows `last_status: ok` and `failure_streak: 0`. Since 0.21.6 `hermes cron list` adds "Last failure at … — recovered since", but only for the most recent failure.
- **Mechanism:** `cron/jobs.py` `_record_run_outcome()` resets `failure_streak` to 0 on the first success; since 0.21.6 (`e70801e736`, #118354) it also keeps a sticky `last_failure: {at, detail}` that a later success does not clear, yet it holds one failure only. `cron/executions.py` keeps only `MAX_TERMINAL_EXECUTIONS = 1000` finished runs across all jobs.
- **Workaround:** on 0.21.6+ read `last_failure` first; for history, grep the gateway logs by time window or keep an external watchdog (system crontab, no LLM) that records failures; treat one identical error across many jobs as one scheduler or host fault.
- **Verified:** 0.21.6 (818c13b), 2026-10-08
- **Upstream:** not reported

### `cron/jobs.json` mixes job definitions with runtime state
- **Affects:** installations that keep `$HERMES_HOME/cron/jobs.json` under version control or diff it.
- **Symptom:** constant diffs in `next_run_at`, `last_run_at`, `last_status`, `last_failure` (0.21.6+), `repeat.completed`; a fired one-shot job flips to `enabled: false`, `state: completed`.
- **Mechanism:** `cron/jobs.py` writes run outcomes and the next schedule back into the same records (`_record_run_outcome()`, `_complete_job_record()`).
- **Workaround:** version a normalized snapshot without runtime keys, or restore `jobs.json` before committing; never apply a stored copy over the live file blindly.
- **Verified:** 0.21.6 (818c13b), 2026-10-08
- **Upstream:** not reported

### Cron `script:` paths must resolve inside `$HERMES_HOME/scripts/`, symlinks included
- **Affects:** pre-run and no-agent scripts shipped inside a skill or plugin folder.
- **Symptom:** `Blocked: script path resolves outside the scripts directory (…)`.
- **Mechanism:** `cron/scheduler_script.py` resolves the path (following symlinks) and requires it to stay under `$HERMES_HOME/scripts`; `tools/cronjob_job_args.py` enforces a relative path at creation.
- **Workaround:** copy the script into `$HERMES_HOME/scripts/` and keep a test that the copy matches the source in the skill.
- **Verified:** 0.21.6 (818c13b), 2026-10-08
- **Upstream:** not reported (by design)

### Every LLM cron job carries the persona and persistent memory in its prompt
- **Affects:** 0.20.5 and later (earlier versions used `skip_memory=True` for cron).
- **Symptom:** higher token use per job; job output may quote personal memory into whatever target the job delivers to.
- **Mechanism:** `cron/scheduler.py` builds the job agent with `skip_memory=False` and `load_soul_identity=True`; there is no per-job switch.
- **Workaround:** use script-only (`no_agent`) jobs or a pre-run gate for routine work, and deliver jobs with memory access only to private targets.
- **Verified:** 0.21.6 (818c13b), 2026-10-08
- **Upstream:** not reported (behaviour change)

## systemd and processes

### The generated gateway unit freezes PATH at install time
- **Affects:** gateways installed with `hermes gateway install` as systemd units.
- **Symptom:** an MCP server or tool works from your shell but fails from the gateway with "No such file or directory" (ENOENT) for its command.
- **Mechanism:** `hermes_cli/gateway.py` writes `Environment="PATH=…"` from user-local bin dirs that existed at generation time (`_build_user_local_paths()`) plus system dirs; `tools/mcp_tool_config.py` `_resolve_stdio_command()` looks commands up only on the child PATH (bare `npx`/`node`/`uv`/`uvx` are redirected to Hermes-managed copies instead of yours).
- **Workaround:** use absolute paths in `mcp_servers.<name>.command` (also to pin your own Node or uv), or regenerate the unit with `hermes gateway install --force` after installing new toolchains.
- **Verified:** 0.21.6 (818c13b), 2026-10-08
- **Upstream:** not reported

### Background processes started from the terminal tool die on every gateway restart
- **Affects:** systemd-managed gateways (`KillMode=mixed` in the generated unit).
- **Symptom:** a tunnel, server or long job the agent started with `nohup … &` or `setsid` disappears after a deploy or restart, without an error.
- **Mechanism:** systemd kills by cgroup. `nohup`/`setsid` children of foreground terminal commands stay in the gateway cgroup; processes started with the terminal tool's `background=true` get their own `hermes-worker-*.scope` but are killed by `process_registry.kill_all()` on gateway shutdown (`gateway/run_shutdown.py`). Only cron and kanban workers (`tools/process_registry.py` `restart_safe_gateway_child_argv()`) survive.
- **Workaround:** start long-lived work as its own user unit: `systemd-run --user --collect --unit=<name> --property=RuntimeMaxSec=86400 <command>` (needs linger, and `XDG_RUNTIME_DIR=/run/user/$(id -u)` in the environment).
- **Verified:** 0.21.6 (818c13b), 2026-10-08
- **Upstream:** not reported

### "Stale systemd unit detected" is a false alarm on system-level installs
- **Affects:** gateway installed as a system unit while the service user's own systemd manager is running (for example with linger enabled), and `agent.restart_drain_timeout` / `agent.cron_drain_timeout` raised so the required stop budget exceeds 90 s.
- **Symptom:** `Stale systemd unit detected: hermes-gateway.service has TimeoutStopSec=90s but drain_timeout=… Run hermes gateway install --force …` although the unit is correct.
- **Mechanism:** `gateway/shutdown_forensics.py` `_systemd_timeout_stop_us()` asks `systemctl --user show` first; for a unit that does not exist there it returns exit 0 with the default `1min 30s` (`LoadState=not-found`), which is accepted.
- **Workaround:** check the real value with `systemctl show hermes-gateway -p TimeoutStopUSec` (no `--user`) and ignore the warning if it covers the drain budget; do not regenerate the unit because of it.
- **Verified:** 0.21.6 (818c13b), 2026-10-08
- **Upstream:** https://github.com/NousResearch/hermes-agent/issues/36755

## Providers and credentials

### A probe with a non-existent model name can disable a Codex credential for all auxiliary tasks
- **Affects:** pooled `openai-codex` credentials (ChatGPT login) used by both the main model and `auxiliary.*`.
- **Symptom:** the main model keeps working, but compression, titles and vision fail with `openai-codex requested but no Codex OAuth token found (run: hermes model)` and fall back to other providers.
- **Mechanism:** a model-entitlement 400 benches the (credential, model) pair for a year (`agent/credential_pool_model_cooldowns.py`, `MODEL_ENTITLEMENT_BENCH_SECONDS`); `model_cooldown_until()` blocks callers that pass no model on any active cooldown, and `agent/auxiliary_client.py` calls `pool.select()` without a model.
- **Workaround:** `hermes auth reset openai-codex`; test models only with names the plan actually offers.
- **Verified:** 0.21.6 (818c13b), 2026-10-08
- **Upstream:** not reported

## Speech-to-text

### The default STT language is English for every provider
- **Affects:** all STT providers unless `stt.language` is set; per-provider `language: ""` does not override it.
- **Symptom:** non-English voice messages come back as another language or as phonetic nonsense; names are mangled.
- **Mechanism:** `hermes_cli/config_defaults.py` sets `stt.language: "en"`; `tools/transcription_tools.py` `_resolve_stt_language()` takes the first non-empty of `stt.<provider>.language` → `stt.language` → env, and only the active provider's section is read.
- **Workaround:** set `stt.language` to your language code (or `stt.<active provider>.language`); `""` at top level restores auto-detect. Config changes apply without restart.
- **Verified:** 0.21.6 (818c13b), 2026-10-08
- **Upstream:** not reported (default is deliberate)

## Dashboard and MCP

### Opening the dashboard web chat starts a second set of stdio MCP servers that never stops
- **Affects:** standalone `hermes dashboard` (systemd or manual), 0.21.4 and later; before 0.21.4 the set started at dashboard boot.
- **Symptom:** memory use of the dashboard process grows by the size of all MCP servers after someone uses the web chat once, and stays until the dashboard restarts.
- **Mechanism:** `hermes_cli/main.py` arms MCP discovery for the first `/api/ws` client (`defer_background_mcp_discovery(…, delay=None)`); discovery is process-wide and nothing shuts it down when the last client leaves (`hermes_cli/web_server_idle_exit.py` covers only SSH-isolated backends).
- **Workaround:** restart the dashboard service when no client is connected (for example a periodic check of open connections on the dashboard port), or avoid the web chat on small hosts.
- **Verified:** 0.21.6 (818c13b), 2026-10-08
- **Upstream:** not reported (lazy start fixed in https://github.com/NousResearch/hermes-agent/issues/58733)

### MCP `tools.include` must use the server's raw tool names
- **Affects:** `mcp_servers.<name>.tools.include` / `exclude`.
- **Symptom:** `MCP server '<name>' (…): registered 0 tool(s)` after adding an allowlist.
- **Mechanism:** `tools/mcp_tool_registration.py` `_tool_candidates()` applies the filter to `t.name` as the server reports it (for example `list-calendars`) before the name is sanitized into the registered `mcp_<server>_list_calendars`.
- **Workaround:** copy names from the server's own tool list (hyphens included) or use globs such as `list-*`.
- **Verified:** 0.21.6 (818c13b), 2026-10-08
- **Upstream:** not reported

## Sessions and memory

### Session search can silently stop indexing after FTS corruption
- **Affects:** `state.db` with a damaged FTS5 index, any recent version.
- **Symptom:** `session_search` answers, but recent conversations are missing from results; nothing in the chat.
- **Mechanism:** `hermes_state_fts.py` `_enter_fts_fail_open()` drops the FTS triggers so message writes keep working and marks the index stale; `hermes_state_schema.py` keeps it detached on every start "until a full rebuild".
- **Workaround:** run `hermes doctor` after every update; repair with `hermes sessions repair` (makes a backup first; `--check-only` only probes) while the gateway is stopped.
- **Verified:** 0.21.6 (818c13b), 2026-10-08
- **Upstream:** https://github.com/NousResearch/hermes-agent/issues/50502 (detection)

### The holographic fact store barely grows for non-English users
- **Affects:** memory provider `holographic` (`hermes-memory-store`).
- **Symptom:** the fact store stays small for weeks and `retrieval_count` is 0 for every fact.
- **Mechanism:** `plugins/memory/holographic/__init__.py`: `auto_extract` defaults to `false`, and when enabled it matches only English patterns ("I prefer…", "we decided…"); nothing in the plugin increments `retrieval_count`.
- **Workaround:** feed facts explicitly (the `fact_store` tool or a scheduled extraction job) and do not use `retrieval_count` as a usefulness signal.
- **Verified:** 0.21.6 (818c13b), 2026-10-08
- **Upstream:** not reported

## Updates and installation

### `hermes update` on a git install moves to the tip of `main`, not to the latest release
- **Affects:** source (git) installs with the default update channel.
- **Symptom:** after an update the version reads `0.0.0` or a long `+N.g<sha>` suffix, and local patches written for the release fail to apply.
- **Mechanism:** `hermes_cli/update_channel.py` `default_channel()` returns `main` for self-updating source installs.
- **Workaround:** on 0.21.6 (and builds from `main` after the 0.21.5 tag): `hermes update --channel stable` for one run, or `--set-channel stable` to persist it for this install (`update.installs` in config.yaml); a source install then checks out the published release commit. On the tagged 0.21.5 (`v2026.9.24`) and older: check out the release tag after the update, then re-sync the venv and rebuild the web UI. Rehearse local patches on `git archive <tag>` before touching the live tree.
- **Verified:** 0.21.6 (818c13b), 2026-10-08
- **Upstream:** not reported (by design)

### `hermes update` restarts gateways and dashboards before you re-apply local patches
- **Affects:** installations that carry local patches of core files.
- **Symptom:** services come up on unpatched code right after the update (for example a dashboard spawning unwanted MCP servers), before your patch step runs.
- **Mechanism:** the update fleet (`hermes_cli/update_cmd_fleet.py`, units `hermes-gateway*`, `hermes-serve*`, `hermes-dashboard*`) restarts services as part of the update. Since 0.21.6, on Linux and macOS running gateways are also drained and stopped before the checkout moves and restarted right after the dependency sync (`hermes_cli/update_cmd_posix_pause.py`), so the unpatched window starts even earlier; dashboards still restart at the end.
- **Workaround:** inspect with `hermes update --plan`; use `hermes update --no-gateway-restart` (it skips both the early pause and the final restart; gateways keep running old code while the tree changes) or stop the services first, apply patches, then restart.
- **Verified:** 0.21.6 (818c13b), 2026-10-08
- **Upstream:** not reported (by design)

### `hermes update` removes Python packages you added to the venv by hand
- **Affects:** 0.20 and later; anything installed into `<hermes-agent>/venv` outside the lockfile.
- **Symptom:** after an update a plugin silently fails to register or a skill script fails with `ModuleNotFoundError`.
- **Mechanism:** `pm/install.py` `sync_venv()` makes the venv match `uv.lock` plus enabled extras and plugin declarations.
- **Workaround:** declare dependencies in the plugin manifest (`pip_dependencies`, read by `hermes_cli/plugins_manifest.py`) so the sync installs them; snapshot the package list before each update and compare after.
- **Verified:** 0.21.6 (818c13b), 2026-10-08
- **Upstream:** not reported (by design)

### `hermes update` parks local core edits in `git stash` when it cannot restore them
- **Affects:** source installs with uncommitted edits of core files (local patches).
- **Symptom:** after an update a patch is gone from the tree, yet nobody deleted it; `git stash list` in `<hermes-agent>` shows an entry from the update.
- **Mechanism:** `hermes_cli/update_cmd_stash.py` stashes local changes before the checkout and re-applies them afterwards. The restore is refused and the stash is kept ("parked") when it conflicts, when restored Python files fail a syntax or import check, when it would overwrite files the update added, or when the prompt is declined; `--keep-stash` parks on purpose, and `updates.non_interactive_local_changes: discard` drops the stash in non-interactive runs.
- **Workaround:** after every update check `git status` and `git stash list`; prefer idempotent re-apply scripts over relying on the stash, and drop a parked stash only after the scripts have re-applied every patch.
- **Verified:** 0.21.6 (818c13b), 2026-10-08
- **Upstream:** not reported (by design)

## Fixed upstream

### Reasoning was delivered to the chat as the answer
- **Affects:** 0.21.3 to 0.21.5 (and builds from `main` before 2026-10-06); providers that return reasoning or a reasoning summary with empty content and `finish_reason: stop`.
- **Symptom:** users received the model's internal reasoning as a normal reply; log line `Reasoning-only clean stop (N chars) — returning the reasoning as the final response`.
- **Mechanism:** `agent/turn_final_response.py` promoted the reasoning to the answer on every route; the #111761 fix only stopped storing it as content.
- **Fixed in:** 0.21.6 (`71c1669404`, `2f0efe8f66`): promotion needs a trusted route (`agent/reasoning_promotion.py` `answer_in_reasoning_capability()`): an `answer_in_reasoning` opt-in in `custom_providers` (per model or provider `capabilities:`) or the local Nemotron-3.5-Lightning parser route. OpenRouter and non-chat-completions transports (Codex Responses) never promote, and signed Anthropic thinking is excluded. A local patch that gated the promotion is no longer needed.
- **Verified:** 0.21.6 (818c13b), 2026-10-08
- **Upstream:** https://github.com/NousResearch/hermes-agent/issues/111761

### A temporary HERMES_HOME could rewrite the shared CLI launcher
- **Affects:** source installs before 0.21.6; `HERMES_HOME` set to a directory outside `~/.hermes` for test runs of `hermes plugins install` / `hermes skills install`.
- **Symptom:** after the temporary directory was deleted, the `hermes` command failed because its interpreter path pointed inside that directory; the gateway kept running.
- **Mechanism:** `pm/environments.py` fell back to `HERMES_HOME/tools` as the store, and `hermes_cli/venv_sync.py` `publish_launchers()` rewrote `<hermes-agent>/.hermes/bin/hermes` and `hermes-acp` for that interpreter.
- **Fixed in:** 0.21.6 (`d2d45b549b`, #123238; `2c79189699`, #131745): a borrowed `HERMES_HOME` resolves the owning home (`owning_home_root()`) and never publishes launchers. The guard needs the owner's `installs/<key>/facts.json`; on older versions test in a profile under `~/.hermes/profiles/` and compare `sha256sum <hermes-agent>/.hermes/bin/hermes` before and after.
- **Verified:** 0.21.6 (818c13b), 2026-10-08
- **Upstream:** not reported

### Codex quota exhaustion was reported to the chat as an authentication failure
- **Affects:** gateway users of `openai-codex` before 0.21.4.
- **Symptom:** "Provider authentication failed" while credentials were valid and only the quota was used up.
- **Mechanism:** `gateway/run.py` matched the auth pattern before the rate-limit pattern.
- **Fixed in:** 0.21.4 (`4b0dd7e9a7`, #89401): rate limit is checked first and the reply names the reset window.
- **Verified:** 0.21.6 (818c13b), 2026-10-08
- **Upstream:** https://github.com/NousResearch/hermes-agent/issues/60846

### A stale local 429 deadline kept Codex on the paid fallback after the quota reset
- **Affects:** pooled `openai-codex` credentials before 0.21.4.
- **Symptom:** `Codex provider quota exhausted (429); retry after N s. Credentials are still valid.` with N counting down locally, no request ever sent.
- **Mechanism:** the resolver raised from the stored `last_error_reset_at` without contacting the provider.
- **Fixed in:** 0.21.4: `hermes_cli/auth_codex.py` probes the usage endpoint and clears the cooldown when the quota is back. On older versions use `hermes auth reset openai-codex`.
- **Verified:** 0.21.6 (818c13b), 2026-10-08
- **Upstream:** not reported

### Attachments in queued follow-up replies were lost
- **Affects:** gateway before 0.20.1.
- **Symptom:** a reply produced while another turn was queued arrived without its file or image.
- **Mechanism:** the queued branch bypassed media extraction.
- **Fixed in:** 0.20.1 (`808c8570a6`, via `_strip_response_attachments_for_direct_send`).
- **Verified:** 0.21.6 (818c13b), 2026-10-08
- **Upstream:** https://github.com/NousResearch/hermes-agent/issues/60845

### A half-paused cron job could still fire
- **Affects:** cron before 0.20.1.
- **Symptom:** a paused job ran after some tool set `enabled: true` without clearing `state: paused` / `paused_at`.
- **Mechanism:** the due-job scan checked only `enabled`.
- **Fixed in:** 0.20.1 (`c7a5de7d6e`, `_has_pause_marker()` and self-heal in `cron/jobs.py`).
- **Verified:** 0.21.6 (818c13b), 2026-10-08
- **Upstream:** not reported

### Cloud STT providers never received the vocabulary prompt
- **Affects:** OpenAI/Groq STT before 0.20.1.
- **Symptom:** names and domain words mangled; only local faster-whisper used `initial_prompt`.
- **Mechanism:** `prompt` was not passed to cloud transcription calls.
- **Fixed in:** 0.20.1 (`52eb8eb533`): `stt.prompt` goes to openai and groq, trimmed to 224 tokens. In field tests a short list of nouns worked better than a sentence, which tended to leak into transcripts.
- **Verified:** 0.21.6 (818c13b), 2026-10-08
- **Upstream:** not reported

### Cron fallback switched provider but kept the primary model name
- **Affects:** cron jobs with a fallback provider before 0.19.0.
- **Symptom:** fallback requests failed with 404 for an unknown model.
- **Mechanism:** the fallback loop replaced only the provider.
- **Fixed in:** 0.19.0 (`f68fd80f4`, "preserve fallback routes and OAuth state").
- **Verified:** 0.21.6 (818c13b), 2026-10-08
- **Upstream:** https://github.com/NousResearch/hermes-agent/issues/60847

### `video_analyze` on Codex silently analysed nothing
- **Affects:** `auxiliary.vision` on `openai-codex` before 0.21.1.
- **Symptom:** the tool returned success while the model said it saw no file.
- **Mechanism:** the Responses adapter dropped `video_url` parts.
- **Fixed in:** 0.21.1 (`2b7b940046`): `agent/codex_responses_adapter.py` rejects video input with "use a video-capable provider".
- **Verified:** 0.21.6 (818c13b), 2026-10-08
- **Upstream:** not reported

### The dashboard "restart gateway" button failed for system-level units
- **Affects:** dashboard running as a normal user with the gateway installed as a system unit, before 0.21.4.
- **Symptom:** a generic action error; nothing restarted.
- **Mechanism:** the CLI refused system-scope lifecycle actions below root.
- **Fixed in:** 0.21.4 (`eaf700c67e`): the dashboard elevates when passwordless elevation for that exact command is configured, otherwise it says so.
- **Verified:** 0.21.6 (818c13b), 2026-10-08
- **Upstream:** https://github.com/NousResearch/hermes-agent/issues/110820

### An idle dashboard started every stdio MCP server at boot
- **Affects:** standalone dashboard before 0.21.4.
- **Symptom:** a full second set of MCP processes next to the gateway's, even if nobody opened the dashboard.
- **Mechanism:** dashboard startup called MCP discovery eagerly.
- **Fixed in:** 0.21.4 (`b47abc36f9`): discovery waits for the first web-chat client. The open-chat case is still listed above.
- **Verified:** 0.21.6 (818c13b), 2026-10-08
- **Upstream:** https://github.com/NousResearch/hermes-agent/issues/58733

### Duplicate keys in YAML were silently merged
- **Affects:** the tagged 0.21.5 (`v2026.9.24`) and earlier (PyYAML keeps the last duplicate).
- **Symptom:** a whole config section disappears without a warning when its key appears twice.
- **Mechanism:** PyYAML accepts duplicate mapping keys.
- **Fixed in:** 0.21.6 (`284dbaf537`): `hermes_yaml.py` uses ruamel, which raises `DuplicateKeyError`.
- **Verified:** 0.21.6 (818c13b), 2026-10-08
- **Upstream:** not reported
