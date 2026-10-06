"""Notes: frontmatter, index, lint, search, new, migrate, issue draft."""

from __future__ import annotations

import json
import os
import unittest

from _helpers import HomeCase, fn, note_text


class FrontmatterTest(unittest.TestCase):
    def test_scalars_lists_quotes_comments(self):
        text = ('---\ntitle: "Colon: inside quotes"\nseen_on: "0.21.5"\ntags: [a, "b, c", \'d\']\n'
                "status: active   # trailing comment\nempty:\nurl: https://x.test/a#frag\n---\nbody\n")
        meta, order, body, errors = fn.split_frontmatter(text)
        self.assertEqual(errors, [])
        self.assertEqual(meta["title"], "Colon: inside quotes")
        self.assertEqual(meta["seen_on"], "0.21.5")
        self.assertEqual(meta["tags"], ["a", "b, c", "d"])
        self.assertEqual(meta["status"], "active")
        self.assertEqual(meta["empty"], "")
        self.assertEqual(meta["url"], "https://x.test/a#frag")
        self.assertEqual(body, "body\n")

    def test_crlf_bom_cyrillic(self):
        text = "﻿---\r\ntitle: Грабля с кириллицей\r\n---\r\nтекст\r\n"
        meta, _, body, errors = fn.split_frontmatter(text)
        self.assertEqual(errors, [])
        self.assertEqual(meta["title"], "Грабля с кириллицей")
        self.assertEqual(body, "текст\n")

    def test_duplicate_and_nested_are_errors(self):
        _, _, _, errors = fn.split_frontmatter("---\na: 1\na: 2\nb:\n  c: 3\n---\n")
        self.assertTrue(any("duplicate key 'a'" in e for e in errors))
        self.assertTrue(any("nested" in e for e in errors))

    def test_missing_frontmatter(self):
        meta, _, _, errors = fn.split_frontmatter("# just markdown\n")
        self.assertEqual(meta, {})
        self.assertTrue(errors)

    def test_roundtrip_is_yaml_safe(self):
        meta = {"title": "yes: no", "seen_on": "0.21.5", "date": "2026-10-06", "status": "active",
                "tags": ["1:30", "plain"], "n": 1, "word": "no"}
        text = fn.dump_frontmatter(meta)
        back, _, _, errors = fn.split_frontmatter(text + "x\n")
        self.assertEqual(errors, [])
        self.assertEqual(back["title"], "yes: no")
        self.assertEqual(back["tags"], ["1:30", "plain"])
        self.assertIn('word: "no"', text)          # YAML 1.1 bool word stays a string
        self.assertIn('"1:30"', text)              # sexagesimal-looking value is quoted
        try:
            import yaml  # optional: the same text through a real YAML parser
        except ImportError:
            return
        parsed = yaml.safe_load(text.split("---\n")[1])
        self.assertEqual(parsed["word"], "no")
        self.assertEqual(parsed["tags"][0], "1:30")


class IndexLintTest(HomeCase):
    def test_index_generated_sorted_and_idempotent(self):
        self.write_note("2026-01-01-old", summary="old | piped")
        self.write_note("2026-02-01-new", updated="2026-02-05")
        code, out, _ = self.run_cli("index")
        self.assertEqual(code, 0)
        text = (self.store / "INDEX.md").read_text(encoding="utf-8")
        self.assertLess(text.index("2026-02-01-new"), text.index("2026-01-01-old"))
        self.assertIn("2026-02-01 · upd. 02-05", text)
        self.assertIn("old \\| piped", text)
        code, out, _ = self.run_cli("index")
        self.assertIn("up to date", out)

    def test_index_keeps_user_header(self):
        self.write_note("2026-01-01-a")
        self.run_cli("index")
        path = self.store / "INDEX.md"
        text = path.read_text(encoding="utf-8").replace("# Field Notes", "# My own notes\n\nHand-written intro.")
        path.write_text(text, encoding="utf-8")
        self.write_note("2026-03-01-b")
        self.run_cli("index")
        text = path.read_text(encoding="utf-8")
        self.assertIn("Hand-written intro.", text)
        self.assertIn("2026-03-01-b", text)

    def test_lint_rules(self):
        self.write_note("2026-01-01-ok")
        self.write_note("2026-01-02-bad", status="done", area="space", id="other")
        self.write_note("2026-01-03-secret", summary="token ghp_" + "a" * 36)
        self.write_note("2026-01-04-placeholder", summary="<one dense line>")
        self.write_note("2026-01-05-ok", title="Same slug twice")
        (self.store / "notes" / "2026-02-05-ok.md").write_text(note_text("2026-02-05-ok"), encoding="utf-8")
        self.write_patch("2026-01-06-patch", "a.py", ["MARK"], patch_kind="customization")
        (self.store / "notes" / "2026-01-07-nochecks.md").write_text(
            note_text("2026-01-07-nochecks", type="patch", patch_kind="bugfix", patch_short="x"), encoding="utf-8")
        ctx = self.ctx()
        items = fn.lint(ctx, fn.load_notes(ctx))
        msgs = [f"{lvl}:{where}:{msg}" for lvl, where, msg in items]
        joined = "\n".join(msgs)
        self.assertIn("status 'done' not one of", joined)
        self.assertIn("area 'space' not one of", joined)
        self.assertIn("differs from the file name", joined)
        self.assertIn("looks like a secret (github token)", joined)
        self.assertIn("still the template placeholder", joined)
        self.assertIn("same slug 'ok'", joined)
        self.assertIn("add upstream_none_reason", joined)
        self.assertIn("the patch cannot be checked", joined)
        self.assertIn("INDEX.md", joined)
        code, _, _ = self.run_cli("lint")
        self.assertEqual(code, 1)

    def test_lint_clean_store_passes(self):
        self.write_note("2026-01-01-ok")
        self.run_cli("index")
        code, out, _ = self.run_cli("lint")
        self.assertEqual(code, 0, out)
        self.assertIn("0 errors", out)

    def test_bad_checks_schema(self):
        self.write_note("2026-01-01-p", type="patch", patch_kind="bugfix", patch_short="p",
                        checks={"editions": [{"when": {"min_version": "x"}, "targets": [{"file": "../etc/x"}]}]})
        ctx = self.ctx()
        joined = "\n".join(m for _, _, m in fn.lint(ctx, fn.load_notes(ctx)))
        self.assertIn("is not a version", joined)
        self.assertIn("without '..'", joined)
        self.assertIn("contains must name", joined)


class NewSearchTest(HomeCase):
    def test_new_from_template_and_duplicates(self):
        os.environ["FIELDNOTES_NOW"] = "2026-10-06T10:00:00+00:00"
        code, out, _ = self.run_cli("new", "cron-linger", "--area", "cron", "--title", "Cron worker needs linger")
        self.assertEqual(code, 0)
        path = self.store / "notes" / "2026-10-06-cron-linger.md"
        meta, _, _, errors = fn.split_frontmatter(path.read_text(encoding="utf-8"))
        self.assertEqual(errors, [])
        self.assertEqual(meta["id"], "2026-10-06-cron-linger")
        self.assertEqual(meta["title"], "Cron worker needs linger")
        code, _, err = self.run_cli("new", "cron-linger", "--title", "again")
        self.assertEqual(code, 3)
        self.assertIn("update it instead", err)
        code, _, err = self.run_cli("new", "worker-linger", "--title", "Cron worker linger again")
        self.assertEqual(code, 3)
        self.assertIn("similar notes exist", err)

    def test_new_patch_writes_checks(self):
        os.environ["FIELDNOTES_NOW"] = "2026-10-06T10:00:00+00:00"
        code, _, _ = self.run_cli("new", "my-fix", "--type", "patch", "--area", "gateway", "--title", "Fix a thing")
        self.assertEqual(code, 0)
        self.assertTrue((self.store / "notes" / "2026-10-06-my-fix.checks.json").is_file())

    def test_new_refuses_in_read_only(self):
        code, _, err = self.run_cli("new", "x-y", "--title", "t", "--read-only")
        self.assertEqual(code, 1)
        self.assertIn("--read-only", err)

    def test_search_ranks_and_reports_zero(self):
        self.write_note("2026-01-01-a", title="Cron job silent", summary="no_agent empty stdout")
        self.write_note("2026-01-02-b", title="Telegram topic", summary="thread id")
        code, out, _ = self.run_cli("search", "stdout")
        self.assertIn("2026-01-01-a", out)
        self.assertNotIn("2026-01-02-b", out)
        code, out, _ = self.run_cli("search", "zzzunlikely")
        self.assertIn("0 matches in 2 notes", out)

    def test_search_without_store_still_searches_known(self):
        import shutil
        shutil.rmtree(self.store)
        code, out, _ = self.run_cli("search", "zzzunlikely")
        self.assertEqual(code, 0)
        self.assertIn("0 matches in 0 notes", out)


class MigrateIssueTest(HomeCase):
    def test_migrate_both_formats_dry_run_then_apply(self):
        src = self.tmp / "old"
        (src / "notes").mkdir(parents=True)
        (src / "notes" / "2025-05-01-legacy.md").write_text(
            "# `TZ` silently resolves to UTC\n- **Date:** 2025-05-01 · **Area:** git bash · **Status:** fixed locally\n\n"
            "## Симптом\nwrong time\n", encoding="utf-8")
        (src / "notes" / "2025-06-01-yaml.md").write_text(
            "---\ntitle: Old yaml note\nslug: 2025-06-01-yaml\ndate: 2025-06-01\nstatus: needs verification\n"
            "area: telegram | gateway\ncandidate_skill: \nsource: chat\n---\n\n# Old yaml note\n", encoding="utf-8")
        (src / "INDEX.md").write_text("| Date | Note | Area | Status | Cand | Summary |\n|---|---|---|---|---|---|\n"
                                      "| 2025-05-01 | [x](notes/2025-05-01-legacy.md) | a | s | — | TZ name ignored, 7 h off |\n",
                                      encoding="utf-8")
        code, out, _ = self.run_cli("migrate", "--from", str(src))
        self.assertEqual(code, 0)
        self.assertIn("dry run", out)
        self.assertFalse((self.store / "notes" / "2025-05-01-legacy.md").exists())
        code, out, _ = self.run_cli("migrate", "--from", str(src), "--apply")
        self.assertEqual(code, 0, out)
        legacy = fn.Note(self.store / "notes" / "2025-05-01-legacy.md")
        self.assertEqual(legacy.errors, [])
        self.assertEqual(legacy.get("summary"), "TZ name ignored, 7 h off")
        self.assertEqual(legacy.status, "workaround")
        self.assertEqual(legacy.get("legacy_area"), "git bash")
        yml = fn.Note(self.store / "notes" / "2025-06-01-yaml.md")
        self.assertEqual(yml.status, "needs-verification")
        self.assertEqual(yml.get("area"), "platform")
        self.assertEqual(yml.get("source"), "chat")       # unknown field kept
        self.assertEqual(yml.get("legacy_area"), "telegram | gateway")
        code, out, _ = self.run_cli("migrate", "--from", str(src), "--apply")
        self.assertIn("already migrated", out)              # repeat run: no duplicates
        self.assertTrue((self.store / "INDEX.md").is_file())

    def test_migrate_conflict_left_alone(self):
        src = self.tmp / "old"
        src.mkdir()
        (src / "2025-05-01-x.md").write_text("# T\n- **Date:** 2025-05-01 · **Area:** a · **Status:** active\n",
                                             encoding="utf-8")
        (self.store / "notes" / "2025-05-01-x.md").write_text("different", encoding="utf-8")
        code, out, _ = self.run_cli("migrate", "--from", str(src), "--apply")
        self.assertEqual(code, 1)
        self.assertIn("CONFLICT", out)
        self.assertEqual((self.store / "notes" / "2025-05-01-x.md").read_text(encoding="utf-8"), "different")

    def test_issue_draft_masks(self):
        path = self.write_note("2026-01-01-leak")
        text = path.read_text(encoding="utf-8").replace(
            "Error: boom", "Error at /home/alice/.hermes from 10.1.2.3 chat -1001234567890 mail a@b.io key sk-"
            + "x" * 30)
        path.write_text(text, encoding="utf-8")
        code, out, _ = self.run_cli("issue-draft", "leak")
        self.assertEqual(code, 0)
        for leaked in ("alice", "10.1.2.3", "-1001234567890", "a@b.io", "sk-xxx"):
            self.assertNotIn(leaked, out)
        self.assertIn("DRAFT", out)
        self.assertIn("### Symptom", out)


if __name__ == "__main__":
    unittest.main()
