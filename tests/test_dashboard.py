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
                         patch_what="Codex <429> & auth shown right",
                         upstream="https://github.com/NousResearch/hermes-agent/issues/42")
        self.write_patch("2026-01-02-miss", "b.py", ["MARK"], patch_short="Missing one")
        self.write_note("2026-01-03-pit", title="Pitfall title", area="platform")

    def report(self, upstream=None, **cfg):
        if cfg:
            (self.home / "field-notes.json").write_text(json.dumps(cfg), encoding="utf-8")
        ctx = self.ctx()
        state = fn.load_state(ctx)
        notes, core, results, drift, items = fn.collect(ctx)
        fn.record_core(state, core, fn.now_utc())
        return ctx, fn.build_report(ctx, state, notes, core, results, drift, items, upstream)

    def test_verdict_line_groups_and_escaping(self):
        ctx, report = self.report()
        text, _ = fn.render(ctx, report, "telegram")
        first = text.split("\n", 1)[0]
        self.assertEqual(first, "🩺 Hermes 0.21.5 — ❌ 1 patch(es) lost — re-apply needed")
        self.assertIn("❌ Lost after an update — 1, re-apply:", text)
        self.assertIn("✅ Working — 1:", text)
        self.assertIn("• Codex &lt;429&gt; &amp; auth shown right", text)     # patch_what wins over patch_short
        self.assertIn('<a href="https://github.com/NousResearch/hermes-agent/issues/42">#42</a>', text)
        self.assertLess(text.index("Missing one"), text.index("Codex"))     # problems first
        self.assertIn("✅ works · ❌ lost after an update", text)            # the legend
        self.assertEqual(len(re.findall("<b>", text)), len(re.findall("</b>", text)))

    def test_ok_verdict_and_attention(self):
        (self.core / "b.py").write_text("MARK", encoding="utf-8")
        ctx, report = self.report()
        self.assertTrue(fn.render(ctx, report)[0].startswith("🩺 Hermes 0.21.5 — all good ✅"))
        (self.core / "new.py").write_text("x", encoding="utf-8")
        self.git("add", "new.py")
        ctx, report = self.report()
        text = fn.render(ctx, report)[0]
        self.assertIn("needs a look: 1 core edit(s) without a patch note", text.split("\n")[0])
        self.assertIn("vanish on the next update", text)

    def test_upstream_lines(self):
        up = {"enabled": True, "relation": "older", "behind_main": 3285,
              "latest": {"tag": "v2026.10.5", "version": "0.22.0", "date": "2026-10-05"}}
        ctx, report = self.report(upstream=up)
        text = fn.render(ctx, report)[0]
        self.assertIn("🆕 Hermes 0.22.0 is out", text.split("\n")[0])
        self.assertIn("<b>🆕 New release: 0.22.0 (05.10.2026) — you are on 0.21.5</b>", text)
        self.assertIn("main has moved on by 3 285 commits", text)
        up = {"enabled": True, "relation": "newer", "behind_main": 10,
              "latest": {"tag": "v2026.9.24", "version": "0.21.5", "date": "2026-09-24"}}
        ctx, report = self.report(upstream=up)
        text = fn.render(ctx, report)[0]
        self.assertIn("build from main of", text)
        self.assertIn("Newer than the latest release 0.21.5 (24.09.2026)", text)
        up = {"enabled": True, "relation": "same", "behind_main": 0,
              "latest": {"tag": "v1", "version": "0.21.5", "date": "2026-09-24"}}
        ctx, report = self.report(upstream=up)
        text = fn.render(ctx, report)[0]
        self.assertIn("Latest release: you have it ✅", text)
        self.assertIn("release of", text)

    def test_russian_plural(self):
        forms = ("коммит", "коммита", "коммитов")
        self.assertEqual([fn._plural(n, forms) for n in (1, 3, 5, 11, 21, 22, 112, 3293)],
                         ["коммит", "коммита", "коммитов", "коммитов", "коммит", "коммита", "коммитов", "коммита"])

    def test_hash_ignores_footer(self):
        ctx, report = self.report()
        _, h1 = fn.render(ctx, report, "telegram")
        report["generated_at"] = "2030-01-01T00:00:00Z"
        _, h2 = fn.render(ctx, report, "telegram")
        self.assertEqual(h1, h2)

    def test_russian_and_text_formats(self):
        ctx, report = self.report(language="ru")
        text, _ = fn.render(ctx, report, "telegram")
        self.assertIn("Мои патчи: 2", text)
        self.assertIn("Слетели после обновления — 1", text)
        self.assertIn("работает · ❌ слетел после обновления", text)
        plain, _ = fn.render(ctx, report, "text")
        self.assertNotIn("<b>", plain)
        md, _ = fn.render(ctx, report, "md")
        self.assertIn("**⚙️ Ядро Hermes**", md)

    def test_long_ok_list_folds_and_stays_under_limit(self):
        ctx, report = self.report()
        self.assertNotIn("<blockquote", fn.render(ctx, report)[0])     # short lists stay open
        for i in range(200):
            self.write_patch(f"2026-02-{(i % 27) + 1:02d}-p{i}", "a.py", ["MARK"], patch_short="x" * 38 + str(i))
        ctx, report = self.report()
        text, _ = fn.render(ctx, report, "telegram")
        self.assertLessEqual(len(text), 4096)
        self.assertEqual(text.count("<blockquote expandable>"), text.count("</blockquote>"))
        self.assertIn("<blockquote expandable>", text)


class UpstreamTest(HomeCase):
    def setUp(self):
        super().setUp()
        os.environ.pop("FIELDNOTES_OFFLINE")
        self.make_core(files={"a.py": "x"}, git=True)
        self.calls = []
        self._orig = fn.GITHUB_GET
        self.releases = [{"tag_name": "v2026.9.30", "name": "Hermes Agent v0.22.0-rc (v2026.9.30)",
                          "prerelease": True, "published_at": "2026-09-30T00:00:00Z"},
                         {"tag_name": "v2026.9.24", "name": "Hermes Agent v0.21.5 (v2026.9.24)",
                          "prerelease": False, "published_at": "2026-09-24T10:00:00Z"}]

        def fake(path, timeout=15):
            self.calls.append(path)
            if "releases" in path:
                return self.releases
            if path.split("compare/")[1].startswith("v"):
                return {"status": "ahead", "ahead_by": 4853, "behind_by": 0}
            return {"status": "ahead", "ahead_by": 3285, "behind_by": 0}
        fn.GITHUB_GET = fake

    def tearDown(self):
        fn.GITHUB_GET = self._orig
        super().tearDown()

    def test_fetch_cache_and_new_release_event(self):
        ctx = self.ctx()
        state = fn.load_state(ctx)
        core = fn.core_info(ctx)
        info, events = fn.upstream_info(ctx, state, core)
        self.assertEqual(info["latest"]["version"], "0.21.5")         # prerelease skipped
        self.assertEqual((info["relation"], info["behind_main"]), ("newer", 3285))
        self.assertEqual(events, [])
        n = len(self.calls)
        fn.upstream_info(ctx, state, core)
        self.assertEqual(len(self.calls), n)                          # cached within check_hours
        state["upstream"]["fetched_at"] = "2000-01-01T00:00:00Z"
        self.releases.insert(0, {"tag_name": "v2026.10.6", "name": "Hermes Agent v0.22.0 (v2026.10.6)",
                                 "prerelease": False, "published_at": "2026-10-06T00:00:00Z"})
        info, events = fn.upstream_info(ctx, state, core)
        self.assertEqual([e["kind"] for e in events], ["new_release"])
        self.assertTrue(fn.format_events(ctx, state, events)[0].startswith("🆕 Hermes 0.22.0 released"))

    def test_error_keeps_last_answer_and_read_only_skips_network(self):
        ctx = self.ctx()
        state = fn.load_state(ctx)
        core = fn.core_info(ctx)
        fn.upstream_info(ctx, state, core)
        state["upstream"]["fetched_at"] = "2000-01-01T00:00:00Z"

        def boom(path, timeout=15):
            raise OSError("no route")
        fn.GITHUB_GET = boom
        info, _ = fn.upstream_info(ctx, state, core)
        self.assertEqual(info["latest"]["version"], "0.21.5")
        self.assertIn("no route", info["error"])
        ro = self.ctx(read_only=True)
        fresh_state = fn.load_state(ro)
        self.calls.clear()
        info, _ = fn.upstream_info(ro, fresh_state, core)
        self.assertEqual(self.calls, [])
        self.assertIsNone(info.get("latest"))

    def test_check_disabled(self):
        (self.home / "field-notes.json").write_text('{"upstream": {"check": false}}', encoding="utf-8")
        ctx = self.ctx()
        info, _ = fn.upstream_info(ctx, fn.load_state(ctx), fn.core_info(ctx))
        self.assertEqual(info, {"enabled": False})
        self.assertEqual(self.calls, [])


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
        self.at("2026-10-07T17:00:00+00:00")
        self.publish(api2)
        self.assertEqual(api2.calls, [])                 # never resent on its own, even much later
        self.publish(api2, force=True)                   # the owner checked the chat
        self.assertEqual(api2.methods(), ["sendMessage", "pinChatMessage"])

    def test_5xx_on_send_is_uncertain_not_retried(self):
        api = FakeApi({"sendMessage": [fn.TelegramError("Bad Gateway", 502)]})
        events = self.publish(api)
        self.assertEqual(api.methods(), ["sendMessage"])
        self.assertEqual([e["kind"] for e in events], ["send_uncertain"])

    def test_cannot_edit_keeps_the_message(self):
        self.publish(FakeApi())
        api = FakeApi({"editMessageText": [fn.TelegramError("Bad Request: message can't be edited", 400)]})
        events = self.publish(api, digest="h2")
        self.assertEqual(api.methods(), ["editMessageText"])
        self.assertEqual(self.entry()["message_id"], 101)
        self.assertEqual([e["kind"] for e in events], ["bot_failing"])

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
        self.assertIn("Patch «Patch A» is lost", out)
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
