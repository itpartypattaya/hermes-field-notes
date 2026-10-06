# The pinned dashboard

One Telegram message in a chat or forum topic, pinned and edited in place — never a stream of new
messages. It is written by the agent's own bot: the core `send_message` tool can send and react but
cannot edit or pin a message, so the script calls the Bot API directly with the same token.

## Setup

In `$HERMES_HOME/field-notes.json`:

```json
"dashboard": {"enabled": true, "chat_id": "-1001234567890", "thread_id": "42", "pin": true}
```

- `chat_id` empty → `TELEGRAM_HOME_CHANNEL` and `TELEGRAM_HOME_CHANNEL_THREAD_ID`. An explicit
  `chat_id` never inherits the home thread; set `thread_id` for a forum topic.
- The token is read from `bot_token_env` (default `TELEGRAM_BOT_TOKEN`): the environment first,
  then `$HERMES_HOME/.env`. It is never printed.
- The bot must be an admin with the right to pin messages; otherwise the message is sent and a
  one-line alert says the pin failed.
- `language`: `en` or `ru`; dates use `timezone` (IANA name).

Publish by hand with `fieldnotes.py dashboard --publish`; the hourly watch (see
`after-update.md`) refreshes it automatically. Without Telegram, `dashboard --format md` gives the
same report as text for any chat.

## What it shows and why

Written for the owner, not for the engineer: a verdict in words, plain descriptions, a legend.

```
🩺 Hermes 0.21.5 — all good ✅                      ← the pinned bar shows only this line

⚙️ Hermes core
Version 0.21.5 · build from main of 29.09.2026
Installed 30.09.2026 — 7 d ago
Newer than the latest release 0.21.5 (24.09.2026)
main has moved on by 3 293 commits since your build

🩹 My patches: 10
✅ Working — 10:
• Codex quota is not reported as a login failure #89401
• …

📒 Notes: 41 · +5 this month · unconfirmed: 1

✅ works · ❌ lost after an update · ⬆️ fixed in Hermes itself · ❔ check undecided
Checked 07.10 00:31 · refreshed hourly
```

| Part | Source | Why it matters |
|---|---|---|
| Verdict line: all good / patches lost / needs a look (what exactly) / new release out | everything below | the pinned bar is all most people read |
| Version; release or build from main, and its date | `pyproject.toml`, git, GitHub releases | what the agent actually runs on |
| Installed (date, days ago) | Hermes' bootstrap record, else first seen by the skill | tie "it broke" to an update |
| Latest release: you have it / newer / 🆕 out | GitHub API, `upstream.repo` | whether there is something to update to |
| How far main has moved since your build | GitHub compare API | how stale a main build is |
| Core files edited without a patch note | `drift` | those edits vanish on the next update |
| My patches, grouped: lost, undecided, fixed in Hermes, working | `patches check` + `patch_what` | the main signal after an update, in plain words |
| Notes: total, new this month, to re-check after the update, unconfirmed | frontmatter | which knowledge may be stale |
| Legend and "checked at" | — | how to read it and how fresh it is |

The patch list stays open up to 15 working patches; longer lists fold into an expandable quote.
Lines with nothing to say (no drift, nothing stale) are left out.

## Version check

Every `upstream.check_hours` (default 12) the skill asks the GitHub API, without credentials, for
the latest stable release of `upstream.repo` (default `NousResearch/hermes-agent`) and compares the
installed commit with it and with `upstream.branch` (default `main`): three requests. The answer is
cached in the state; on errors the last good answer stays and the line says so. A new release
triggers one alert. `upstream.check: false` stops the GitHub calls (the dashboard still talks to
Telegram while it is enabled); `--read-only` never calls the network.

## Behaviour

- Sent once, then pinned; the message id is stored at once, so a later failure never causes a
  second message. A failed pin is retried on the next run without resending.
- Unchanged content → no request at all; the "checked at" line is refreshed every
  `freshness_hours` (default 6).
- Deleted message → sent and pinned again, with a one-line alert.
- Rate limits are honoured (`retry_after`). A send that got no answer (timeout, 5xx) may have
  reached the chat, so it is never repeated automatically: one alert, then the owner checks the chat
  and runs `dashboard --publish --force`. A message that can no longer be edited keeps its id and
  reports the error; only a deleted message is sent again.
- State lives in `$HERMES_HOME/cache/field-notes-state.json`, keyed by profile, bot, chat and
  thread: moving the dashboard to another chat starts a new message there.
