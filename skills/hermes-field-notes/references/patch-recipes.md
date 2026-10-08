# Patch recipes

Local core patches that one production Hermes install has carried through several updates,
written down so another agent can reproduce them. Each recipe says what breaks, where in the core,
what the edit does, how to check it with a `checks.json`, how to tell that upstream fixed it, and
where upstream stands. Verified against Hermes 0.21.5 (rc.33, `8d30c4e`) on 2026-10-07 and
re-checked against 0.21.6 (`818c13b`) on 2026-10-08: the first four bugfixes are still needed,
the fifth is fixed upstream in 0.21.6.

How to use a recipe:

1. Confirm the symptom on your install first (`fieldnotes.py search`, logs). No symptom — no patch.
2. Check the upstream issue/PR: if it is merged in your version, you need nothing.
3. Ask the owner before touching `hermes-agent`. Write the edit as an idempotent script following
   `patch-scripts.md`: exact anchors, fail closed, unique marker, backup, `py_compile`.
4. `fieldnotes.py new <slug> --type patch`, fill `patch_what`, write `<id>.checks.json` from the
   recipe's **Checks** line (format: `note-format.md`) with your own marker, then `patches check` must
   say `OK`. Restart the gateway.
5. Prefer pushing the fix upstream (`upstreaming.md`): a recipe is a stopgap, not a fork.

Anchors move between releases. The recipes name functions and the shape of the change, not line
numbers; read the current code before editing.

## Bugfixes

### Quota and policy errors are reported as an authentication failure
- **Affects:** gateway replies to the chat on provider errors; seen with Codex. Part (a) is upstream
  since 0.21.4; part (b) is not.
- **Symptom:** a valid account hits its quota and the chat says "Provider authentication failed";
  or a request blocked by provider policy (`HTTP 429 … security policy`) is answered with "wait, the
  limit resets" — it never will.
- **Where:** the error-to-reply table in `gateway/run.py` (`_PROVIDER_ERROR_REPLIES` and the
  function that walks it).
- **Edit:** the table is checked top to bottom and several patterns match one message. Order the
  rows POLICY → RATE_LIMIT → AUTH, so the most specific meaning wins. Keep upstream's wording.
- **Checks:** `contains`: your marker in `gateway/run.py`; optionally a regression test name if you
  add one under `tests/gateway/`.
- **Upstream signs:** the POLICY row precedes the RATE_LIMIT row in the table.
- **Upstream:** issue [#60846](https://github.com/NousResearch/hermes-agent/issues/60846), PR
  [#60856](https://github.com/NousResearch/hermes-agent/pull/60856) (open); part (a) in
  [#89401](https://github.com/NousResearch/hermes-agent/issues/89401).

### "Stale systemd unit detected" for a gateway that runs as a system service
- **Affects:** installs where the gateway is a system-level unit and `restart_drain_timeout` or
  `cron_drain_timeout` is raised above the defaults.
- **Symptom:** every gateway start logs `Stale systemd unit detected: … TimeoutStopSec=90s but
  drain_timeout=…`, although the unit file has the right value.
- **Where:** `check_systemd_timing_alignment()` in `gateway/shutdown_forensics.py`.
- **Edit:** the check queries `systemctl --user show`. For a unit the user manager does not know,
  systemd answers exit 0 with defaults (`TimeoutStopUSec=90s`, `LoadState=not-found`). Read
  `LoadState` too and trust the timeout only when it is `loaded` (fail closed: `masked`, `error`,
  `bad-setting` and unknown states are skipped as well).
- **Checks:** `contains`: your marker and `LoadState` in `gateway/shutdown_forensics.py`.
- **Upstream signs:** the function reads `LoadState`.
- **Upstream:** issue [#36755](https://github.com/NousResearch/hermes-agent/issues/36755), PR
  [#37324](https://github.com/NousResearch/hermes-agent/pull/37324) (open).

### Telegram messages made only of invisible characters are sent as empty bubbles
- **Affects:** Telegram, both delivery paths.
- **Symptom:** the chat receives a message that looks empty; logs show text of length > 0.
- **Where:** `send()` in `plugins/platforms/telegram/adapter.py` (live adapter: streaming final,
  cron through the gateway, plugins) and the direct Telegram sender used by the `send_message` tool
  and the standalone cron fallback (`tools/send_message_senders.py` on 0.21.5 and 0.21.6).
- **Edit:** the guard uses `not text.strip()`, and `strip()` keeps zero-width and other invisible
  characters (U+200B, U+200C, U+200D, U+FEFF, U+2060, U+2063, U+00AD, U+180E). Strip whitespace and
  those characters before the emptiness check, skip the send, log a warning with a `repr` preview.
  Patch both paths: one of them bypasses the adapter.
- **Checks:** two targets, your marker in each file.
- **Upstream signs:** an invisible-character set next to the empty-send guard in the adapter.
- **Upstream:** issue [#60848](https://github.com/NousResearch/hermes-agent/issues/60848), PR
  [#60865](https://github.com/NousResearch/hermes-agent/pull/60865) (open).

### Slash commands in observed Telegram groups act on an empty personal session
- **Affects:** Telegram groups without topics, with `observe_unmentioned_group_messages` and
  `group_sessions_per_user: true`. Forum topics are not affected.
- **Symptom:** `/new` answers "Session reset" but the context keeps growing; `/model` changes
  nothing; `/context` shows another session. The state database has empty sessions keyed by user.
- **Where:** `_session_key_for_source` in `gateway/run.py` — the single funnel all slash-command
  handlers use.
- **Edit:** ordinary messages of observed groups are de-personalised (`user_id=None`, one shared
  session per chat), but command events keep `user_id` for access checks, so the session key gets a
  user suffix. Normalise the source the same way the adapter does for ordinary messages before
  building the key; leave the access check untouched.
- **Checks:** your marker in `gateway/run.py`.
- **Upstream signs:** `_session_key_for_source` applies the group-observe normalisation itself.
- **Upstream:** issue [#65085](https://github.com/NousResearch/hermes-agent/issues/65085) (open).

### Reasoning is delivered to the chat as the answer (0.21.3–0.21.5; fixed in 0.21.6)
- **Fixed upstream in 0.21.6** (`71c1669404`, `2f0efe8f66`): the promotion now needs a trusted route
  (`agent/reasoning_promotion.py` `answer_in_reasoning_capability()` — an `answer_in_reasoning`
  opt-in in `custom_providers` or the local Nemotron-3.5-Lightning route); OpenRouter and
  non-chat-completions transports such as Codex Responses never promote. On 0.21.6+ do not apply
  this patch; retire an existing one (set `status: fixed-upstream` in its note).
- **Affects:** 0.21.3 to 0.21.5, any provider that returns reasoning separately (Codex summaries,
  Gemini) and sometimes stops with empty content.
- **Symptom:** the user receives the model's internal reasoning instead of a reply, and it is
  stored in the history as the assistant's answer.
- **Where:** the "reasoning-only clean stop" branch in `agent/turn_final_response.py`
  (`finish_reason == "stop"`, empty `content`, no tool calls → reasoning promoted to the answer).
- **Edit:** put the promotion behind an opt-in flag (for example an environment variable that
  restores upstream behaviour), keep the log line, and let the turn fall through to the normal
  empty-response recovery (prefill retries, then fallback).
- **Checks:** `when: {"min_version": "0.21.3"}`; your marker in `agent/turn_final_response.py`.
  Older cores have no such block: the edition does not apply there (`N/A`). Put an edition for
  0.21.6 first, with the same target and the upstream sign below, so an updated core reports
  `UPSTREAMED` (or `conflict` if the old patch was re-applied on top) instead of `MISSING`.
- **Upstream signs:** `answer_in_reasoning_capability(agent)` in `agent/turn_final_response.py`.
- **Upstream:** issue [#111761](https://github.com/NousResearch/hermes-agent/issues/111761) closed
  with a partial fix (reasoning no longer written into `content`); the promotion itself remained in
  0.21.5 and is gated by route since 0.21.6.

## Customization ideas

Behaviour one owner wanted and upstream may not. No code here — the shape of the change and where it
goes. Set `patch_kind: customization` and write `upstream_none_reason`.

- **Usage in the status footer** — `gateway/runtime_footer.py` (+ `agent/account_usage.py`, the call
  site in `gateway/run_turn.py`): show the provider's 5-hour window and context fill in percent.
  The call signature changes between releases; a stale footer disappears silently, so check it
  after every update.
- **Shorter answers on a paid fallback** — `agent/conversation_loop.py` /
  `agent/turn_api_request.py`: when the active provider is a paid fallback, append a short
  "be brief" note to the request. A rule in the persona is not enough: the system prompt is cached.
- **Delivery target chosen by a cron pre-check** — `cron/scheduler.py`, `cron/scheduler_prompt.py`:
  honour a per-run `deliver` from the pre-check's wake-gate JSON, so a reactive job answers where it
  was called.
- **Telegram custom emoji in ordinary replies** — `plugins/platforms/telegram/adapter.py`: bots whose
  owner has Telegram Premium may send custom emoji entities, but the formatter escapes the leading
  `!` of `![alias](tg://emoji?id=…)`; let that syntax through.
- **Speech inside `video_analyze`** — `tools/vision_tools.py`: since 0.21.1 Codex rejects video input
  with a clear error instead of dropping it silently. To get the speech anyway, extract the audio
  track (ffmpeg), transcribe it with the configured STT provider and add the transcript to the
  prompt and the result; accept plain audio files the same way.
