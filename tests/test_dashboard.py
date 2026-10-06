"""Dashboard: report, render (escaping, limits, languages) and the send/pin/edit state machine."""

from __future__ import annotations

import json
import os
import re
import unittest

from _helpers import HomeCase, fn

TOKEN = "123456789:" + "A" * 35


class FakeApi:
    """Records calls; `plan` maps a method to a list of outcomes (dict result or TelegramError)."""

    def __init__(self, plan=None):
        self.calls, self.plan, self.next_id = [], plan or {}, 100

    def call(self, method, payload):
        self.calls.append((method, payload))
        queue = self.plan.get(method)
        if queue:
            outcome = queue.pop(0)
            if isinstance(outcome, Exception):
                raise outcome
            return outcome
        if method == "sendMessage":
            self.next_id += 1
            return {"message_id": self.next_id}
        return True

    def methods(self):
        return [m for m, _ in self.calls]


class RenderTest(HomeCase):
    def setUp(self):
        super().setUp()
        self.make_core(files={"a.py": "MARK", "b.py": ""}, git=True)
        self.write_patch("2026-01-01-ok", "a.py", ["MARK"], patch_short="Codex <429> & auth",
                         upstream="https://github.com/NousResearch/hermes-agent/issues/42")
        self.write_patch("2026-01-02-miss", "b.py", ["MARK"], patch_short="Missing one")
        self.write_note("2026-01-03-pit", title="Pitfall title", area="platform")

    def report(self, **cfg):
        if cfg:
            (self.home / "field-notes.json").write_text(json.dumps(cfg), encoding="utf-8")
        ctx = self.ctx()
        state = fn.load_state(ctx)
        notes, core, results, drift, items = fn.collect(ctx)
        fn.record_core(state, core, fn.now_utc())
        return ctx, fn.build_report(ctx, state, notes, core, results, drift, items)

    def test_first_line_counts_and_escaping(self):
        ctx, report = self.report()
        text, digest = fn.render(ctx, report, "telegram")
        first = text.split("\n", 1)[0]
        self.assertEqual(first, "🩺 Hermes 0.21.5 · 🩹 1 ✅ · 1 ❌ · 🪤 3")
        self.assertIn("Codex &lt;429&gt; &amp; auth", text)
        self.assertIn('<a href="https://github.com/NousResearch/hermes-agent/issues/42">#42</a>', text)
        self.assertIn("<blockquote expandable>", text)
        self.assertLess(text.index("Missing one"), text.index("Codex"))     # problems first
        self.assertEqual(len(re.findall("<b>", text)), len(re.findall("</b>", text)))

    def test_hash_ignores_freshness_line(self):
        ctx, report = self.report()
        _, h1 = fn.render(ctx, report, "telegram")
        report["generated_at"] = "2030-01-01T00:00:00Z"
        _, h2 = fn.render(ctx, report, "telegram")
        self.assertEqual(h1, h2)

    def test_russian_and_text_formats(self):
        ctx, report = self.report(language="ru")
        text, _ = fn.render(ctx, report, "telegram")
        self.assertIn("Патчи — 2", text)
        self.assertIn("слетел", text)
        plain, _ = fn.render(ctx, report, "text")
        self.assertNotIn("<b>", plain)
        md, _ = fn.render(ctx, report, "md")
        self.assertIn("**Ядро**", md)

    def test_truncation_keeps_markup_valid(self):
        for i in range(200):
            self.write_patch(f"2026-02-{(i % 27) + 1:02d}-p{i}", "a.py", ["MARK"], patch_short="x" * 38 + str(i))
        ctx, report = self.report()
        text, _ = fn.render(ctx, report, "telegram")
        self.assertLessEqual(len(text), 4000)
        self.assertEqual(text.count("<blockquote expandable>"), text.count("</blockquote>"))
        self.assertRegex(text, r"\+\d+ more")


class PublishTest(HomeCase):
    def setUp(self):
        super().setUp()
        self.make_core(files={"a.py": "MARK"})
        self.write_patch("2026-01-01-ok", "a.py", ["MARK"])
        os.environ["TELEGRAM_BOT_TOKEN"] = TOKEN
        (self.home / "field-notes.json").write_text(json.dumps(
            {"dashboard": {"enabled": True, "chat_id": "-1001234567890", "thread_id": "42", "freshness_hours": 6}}),
            encoding="utf-8")
        self.ctx_ = self.ctx()
        self.state = fn.load_state(self.ctx_)
        self.saves = 0

    def save(self):
        self.saves += 1
        fn.save_state(self.ctx_, self.state)

    def entry(self):
        return next(iter(self.state["dashboard"].values()))

    def publish(self, api, text="t", digest="h1", force=False):
        return fn.publish(self.ctx_, self.state, text, digest, api, self.save, force=force)

    def at(self, iso_time):
        os.environ["FIELDNOTES_NOW"] = iso_time

    def test_first_run_sends_pins_and_stores_id_at_once(self):
        self.at("2026-10-06T10:00:00+00:00")
        api = FakeApi()
        events = self.publish(api)
        self.assertEqual(api.methods(), ["sendMessage", "pinChatMessage"])
        self.assertEqual(api.calls[0][1]["message_thread_id"], 42)
        self.assertEqual(api.calls[0][1]["chat_id"], -1001234567890)
        self.assertEqual(self.entry()["message_id"], 101)
        self.assertTrue(self.entry()["pinned"])
        self.assertEqual(self.entry()["last_action"], "sent")
        self.assertEqual(events, [])
        key = next(iter(self.state["dashboard"]))
        self.assertEqual(key, "hermes|123456789|-1001234567890|42")

    def test_unchanged_makes_zero_requests_until_stale(self):
        self.at("2026-10-06T10:00:00+00:00")
        self.publish(FakeApi())
        api = FakeApi()
        self.at("2026-10-06T12:00:00+00:00")
        self.publish(api)
        self.assertEqual(api.calls, [])
        self.assertEqual(self.entry()["last_action"], "unchanged")
        self.at("2026-10-06T17:00:00+00:00")          # older than freshness_hours: refresh the "checked" line
        self.publish(api)
        self.assertEqual(api.methods(), ["editMessageText"])

    def test_changed_content_edits_in_place(self):
        self.at("2026-10-06T10:00:00+00:00")
        self.publish(FakeApi())
        api = FakeApi()
        self.publish(api, digest="h2")
        self.assertEqual(api.methods(), ["editMessageText"])
        self.assertEqual(api.calls[0][1]["message_id"], 101)
        self.assertEqual(self.entry()["content_hash"], "h2")
        self.assertEqual(self.entry()["last_action"], "edited")

    def test_not_modified_is_success(self):
        self.publish(FakeApi())
        api = FakeApi({"editMessageText": [fn.TelegramError("Bad Request: message is not modified", 400)]})
        events = self.publish(api, digest="h2")
        self.assertEqual(events, [])
        self.assertEqual(self.entry()["content_hash"], "h2")

    def test_deleted_message_is_recreated_and_repinned(self):
        self.publish(FakeApi())
        api = FakeApi({"editMessageText": [fn.TelegramError("Bad Request: message to edit not found", 400)]})
        events = self.publish(api, digest="h2")
        self.assertEqual(api.methods(), ["editMessageText", "sendMessage", "pinChatMessage"])
        self.assertEqual([e["kind"] for e in events], ["dash_recreated"])
        self.assertEqual(self.entry()["last_action"], "recreated")
        self.assertEqual(self.entry()["message_id"], 101)

    def test_send_ok_pin_fails_then_retries_pin_only(self):
        api = FakeApi({"pinChatMessage": [fn.TelegramError("Bad Request: not enough rights to pin a message", 400)]})
        events = self.publish(api)
        self.assertEqual([e["kind"] for e in events], ["pin_failed"])
        self.assertEqual(self.entry()["message_id"], 101)
        self.assertFalse(self.entry()["pinned"])
        api2 = FakeApi()
        self.publish(api2)                               # same content: only the pin is retried
        self.assertEqual(api2.methods(), ["pinChatMessage"])
        self.assertTrue(self.entry()["pinned"])

    def test_network_after_send_is_uncertain_no_duplicate(self):
        self.at("2026-10-06T10:00:00+00:00")
        api = FakeApi({"sendMessage": [fn.TelegramError("network: TimeoutError", uncertain=True)]})
        events = self.publish(api)
        self.assertEqual([e["kind"] for e in events], ["send_uncertain"])
        api2 = FakeApi()
        self.at("2026-10-06T11:00:00+00:00")
        self.publish(api2)
        self.assertEqual(api2.calls, [])                 # no resend within freshness_hours
        self.at("2026-10-06T17:00:00+00:00")
        self.publish(api2)
        self.assertEqual(api2.methods(), ["sendMessage", "pinChatMessage"])

    def test_rate_limit_waits_and_retries_once(self):
        orig = fn.time.sleep
        fn.time.sleep = lambda s: None
        try:
            api = FakeApi({"sendMessage": [fn.TelegramError("Too Many Requests", 429, retry_after=3)]})
            events = self.publish(api)
        finally:
            fn.time.sleep = orig
        self.assertEqual(api.methods(), ["sendMessage", "sendMessage", "pinChatMessage"])
        self.assertEqual(events, [])

    def test_hard_failure_is_reported_and_throttled(self):
        api = FakeApi({"sendMessage": [fn.TelegramError("Forbidden: bot was kicked", 403)]})
        events = self.publish(api)
        self.assertEqual([e["kind"] for e in events], ["bot_failing"])
        lines = fn.format_events(self.ctx_, self.state, events)
        self.assertEqual(len(lines), 1)
        self.assertNotIn(TOKEN, lines[0])
        self.assertEqual(fn.format_events(self.ctx_, self.state, events), [])   # within repeat_hours

    def test_new_recipient_gets_new_message(self):
        self.publish(FakeApi())
        (self.home / "field-notes.json").write_text(json.dumps(
            {"dashboard": {"enabled": True, "chat_id": "-1009999999999"}}), encoding="utf-8")
        self.ctx_ = self.ctx()
        api = FakeApi()
        self.publish(api)
        self.assertEqual(api.methods(), ["sendMessage", "pinChatMessage"])
        self.assertNotIn("message_thread_id", api.calls[0][1])   # explicit chat does not inherit a thread
        self.assertEqual(len(self.state["dashboard"]), 2)

    def test_home_channel_fallback_and_env_file(self):
        (self.home / "field-notes.json").write_text(json.dumps({"dashboard": {"enabled": True}}), encoding="utf-8")
        os.environ.pop("TELEGRAM_BOT_TOKEN")
        (self.home / ".env").write_text(f'TELEGRAM_BOT_TOKEN="{TOKEN}"\nTELEGRAM_HOME_CHANNEL=-1005555555555\n'
                                        "TELEGRAM_HOME_CHANNEL_THREAD_ID=7  # topic\n", encoding="utf-8")
        token, chat, thread = fn.dashboard_target(self.ctx())
        self.assertEqual((token, chat, thread), (TOKEN, "-1005555555555", "7"))

    def test_bot_api_masks_token(self):
        api = fn.BotApi(TOKEN)
        self.assertEqual(api._mask(f"bad url https://api.telegram.org/bot{TOKEN}/x"),
                         "bad url https://api.telegram.org/bot<token>/x")


class TickTest(HomeCase):
    def test_tick_is_silent_when_nothing_changes_and_reports_change(self):
        self.make_core(files={"a.py": "MARK"}, git=True)
        self.write_patch("2026-01-01-a", "a.py", ["MARK"], patch_short="Patch A")
        code, out, _ = self.run_cli("tick")
        self.assertEqual((code, out), (0, ""))
        code, out, _ = self.run_cli("tick")
        self.assertEqual(out, "")
        (self.core / "a.py").write_text("gone", encoding="utf-8")
        code, out, _ = self.run_cli("tick")
        self.assertIn("Patch «Patch A» is missing", out)
        code, out, _ = self.run_cli("tick")
        self.assertEqual(out, "")

    def test_tick_without_store_is_throttled(self):
        import shutil
        shutil.rmtree(self.store)
        _, out1, _ = self.run_cli("tick")
        _, out2, _ = self.run_cli("tick")
        self.assertIn("no notes store", out1)
        self.assertEqual(out2, "")

    def test_tick_dashboard_without_token_reports_once(self):
        self.make_core(files={"a.py": "MARK"})
        (self.home / "field-notes.json").write_text(json.dumps({"dashboard": {"enabled": True, "chat_id": "-1001"}}),
                                                    encoding="utf-8")
        _, out1, _ = self.run_cli("tick")
        _, out2, _ = self.run_cli("tick")
        self.assertIn("no bot token or chat id", out1)
        self.assertEqual(out2, "")


if __name__ == "__main__":
    unittest.main()
