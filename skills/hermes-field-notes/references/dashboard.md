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

| Line | Source | Why it matters |
|---|---|---|
| First line: version · patches OK / missing / unknown · notes | all below | visible in the pinned bar without opening it |
| Version, tag, short SHA | `pyproject.toml`, `git describe` | what the agent runs on |
| Updated (date, days ago), previous version | Hermes' bootstrap record, else first seen by the skill | tie "it broke" to an update |
| Core changes outside the registry; local commits on top of the tag | `drift` | an unregistered edit disappears on the next update |
| Patches: bugfixes / customizations / workarounds | `patch_kind` | what can go upstream and what stays for good |
| In place / missing / unknown | `patches check` | the main signal after an update |
| Fixed upstream (all time); bugfixes without an issue | note statuses and links | debt you keep paying until it is reported |
| Core files under patches; oldest patch | checks files, note dates | surface and age of local changes |
| Patch list (expandable) | per patch: status, age, issue link | problems first |
| Notes: new in 30 days, to re-verify on this core, unconfirmed | frontmatter | which knowledge may be stale |
| Areas (top 3); latest note | `area`, `date` | where things break most |
| Checked at · lint errors / warnings | doctor, lint | how fresh and trustworthy the numbers are |

## Behaviour

- Sent once, then pinned; the message id is stored at once, so a later failure never causes a
  second message. A failed pin is retried on the next run without resending.
- Unchanged content → no request at all; the "checked at" line is refreshed every
  `freshness_hours` (default 6).
- Deleted message → sent and pinned again, with a one-line alert.
- Rate limits are honoured (`retry_after`); a timeout right after sending marks the send as
  uncertain and waits `freshness_hours` before trying again (one duplicate is possible, never a
  stream).
- State lives in `$HERMES_HOME/cache/field-notes-state.json`, keyed by profile, bot, chat and
  thread: moving the dashboard to another chat starts a new message there.
