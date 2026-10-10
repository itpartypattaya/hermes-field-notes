"""Patches: static checks, editions, safety, drift, core identity, doctor events, read-only."""

from __future__ import annotations

import json
import os
import unittest

from _helpers import HomeCase, fn

PATCHED = "x = 1  # MYPATCH_A\nnew_code()\n"
PRISTINE = "x = 1\nold_code()\n"


class CheckTest(HomeCase):
    def status(self, note_id):
        ctx = self.ctx()
        notes = fn.load_notes(ctx)
        core = fn.core_info(ctx)
        return {r["id"]: r for r in fn.check_patches(ctx, notes, core)}[note_id]

    def test_ok_missing_partial(self):
        self.make_core(files={"gw/run.py": PATCHED})
        self.write_patch("2026-01-01-a", "gw/run.py", ["MYPATCH_A", "new_code()"], not_contains=["old_code()"])
        self.assertEqual(self.status("2026-01-01-a")["status"], "OK")
        (self.core / "gw/run.py").write_text(PRISTINE, encoding="utf-8")
        self.assertEqual(self.status("2026-01-01-a")["status"], "MISSING")
        # marker survived, the code under it did not: not a false green
        (self.core / "gw/run.py").write_text("x = 1  # MYPATCH_A\nold_code()\n", encoding="utf-8")
        r = self.status("2026-01-01-a")
        self.assertEqual((r["status"], r["reason"]), ("UNKNOWN", "partial"))

    def test_upstreamed_conflict_target_gone(self):
        self.make_core(files={"gw/run.py": "def upstream_fix(): pass\n"})
        up = [{"file": "gw/run.py", "contains": ["def upstream_fix("]}]
        self.write_patch("2026-01-01-a", "gw/run.py", ["MYPATCH_A"], upstream_rules=up)
        self.assertEqual(self.status("2026-01-01-a")["status"], "UPSTREAMED")
        (self.core / "gw/run.py").write_text("def upstream_fix(): pass  # MYPATCH_A\n", encoding="utf-8")
        r = self.status("2026-01-01-a")
        self.assertEqual((r["status"], r["reason"]), ("UNKNOWN", "conflict"))
        self.write_patch("2026-01-02-b", "gw/gone.py", ["MYPATCH_B"])
        r = self.status("2026-01-02-b")
        self.assertEqual((r["status"], r["reason"]), ("UNKNOWN", "target_gone"))

    def test_multi_target_mixed_is_partial(self):
        self.make_core(files={"a.py": "MARK", "b.py": "nothing"})
        self.write_patch("2026-01-01-a", None, None, editions=[{"targets": [
            {"file": "a.py", "contains": ["MARK"]}, {"file": "b.py", "contains": ["MARK"]}]}])
        r = self.status("2026-01-01-a")
        self.assertEqual((r["status"], r["reason"]), ("UNKNOWN", "partial"))

    def test_editions_by_version_and_na(self):
        editions = [{"when": {"min_version": "0.21.3"}, "targets": [{"file": "a.py", "contains": ["NEW"]}]},
                    {"when": {"max_version": "0.20.9"}, "targets": [{"file": "a.py", "contains": ["OLD"]}]}]
        self.make_core(version="0.21.5", files={"a.py": "NEW"})
        self.write_patch("2026-01-01-a", None, None, editions=editions)
        self.assertEqual(self.status("2026-01-01-a")["status"], "OK")
        (self.core / "pyproject.toml").write_text('version = "0.20.1"\n', encoding="utf-8")
        self.assertEqual(self.status("2026-01-01-a")["status"], "MISSING")   # OLD edition, OLD sign absent
        (self.core / "pyproject.toml").write_text('version = "0.21.1"\n', encoding="utf-8")
        self.assertEqual(self.status("2026-01-01-a")["status"], "N/A")

    def test_dev_build_version_unknown(self):
        editions = [{"when": {"min_version": "0.21.3"}, "targets": [{"file": "a.py", "contains": ["NEW"]}]}]
        self.make_core(version="0.0.0", files={"a.py": "NEW"})
        self.write_patch("2026-01-01-a", None, None, editions=editions)
        r = self.status("2026-01-01-a")
        self.assertEqual((r["status"], r["reason"]), ("UNKNOWN", "version_unknown"))

    def test_dev_build_named_by_tag(self):
        editions = [{"when": {"min_version": "0.21.3"}, "targets": [{"file": "a.py", "contains": ["NEW"]}]}]
        self.make_core(version="0.0.0", files={"a.py": "NEW"}, git=True)
        self.git("tag", "rc.33-v0.21.5")
        self.write_patch("2026-01-01-a", None, None, editions=editions)
        self.assertEqual(self.status("2026-01-01-a")["status"], "OK")

    def test_tags_of_the_0216_release_pipeline(self):
        # 0.21.6 tags: v0.21.6 and rc.N-v0.21.6, abandoned-rc.N-v…, v0.21.5+canary.…
        self.make_core(version="0.0.0", files={"a.py": "x"}, git=True)
        for tag, want in (("abandoned-rc.33-v0.21.5", "0.21.5"), ("v0.21.5+canary.20261008T070449Z", "0.21.5"),
                          ("rc.4-v0.21.6", "0.21.6"), ("v0.21.6", "0.21.6")):
            with self.subTest(tag=tag):
                self.git("-c", "user.email=t@example.com", "-c", "user.name=t",
                         "commit", "-q", "--allow-empty", "-m", tag)
                self.git("tag", tag)
                self.assertEqual(fn.core_info(self.ctx()).get("version_from_tag"), want)
        self.assertEqual(fn._release_version({"name": "Hermes Agent v0.21.6", "tag_name": "v0.21.6"}), "0.21.6")

    def test_path_escape_rejected(self):
        self.make_core(files={"a.py": "x"})
        outside = self.tmp / "secret.py"
        outside.write_text("MARK", encoding="utf-8")
        self.assertIsNone(fn.safe_target(self.core, "../secret.py"))
        self.assertIsNone(fn.safe_target(self.core, "/etc/passwd"))
        self.assertIsNone(fn.safe_target(self.core, "C:/x"))
        try:
            (self.core / "link.py").symlink_to(outside)
        except (OSError, NotImplementedError):
            return  # no symlink privilege (Windows)
        self.assertIsNone(fn.safe_target(self.core, "link.py"))

    def test_retired_notes_are_not_checked_and_exit_codes(self):
        self.make_core(files={"a.py": ""})
        self.write_patch("2026-01-01-gone", "a.py", ["M"], status="fixed-upstream")
        code, out, _ = self.run_cli("patches", "check")
        self.assertEqual(code, 0)
        self.assertIn("0 live patches", out)
        self.write_patch("2026-01-02-miss", "a.py", ["M"])
        code, _, _ = self.run_cli("patches", "check")
        self.assertEqual(code, 2)
        self.write_patch("2026-01-03-unk", "nope.py", ["M"])
        code, out, _ = self.run_cli("patches", "check")
        self.assertEqual(code, 3)
        self.assertIn("file not found", out)
        code, out, _ = self.run_cli("patches", "check", "--json")
        data = json.loads(out)
        self.assertEqual(len(data["patches"]), 2)

    def test_core_missing(self):
        self.write_patch("2026-01-01-a", "a.py", ["M"])
        code, _, err = self.run_cli("patches", "check")
        self.assertEqual(code, 4)
        self.assertIn("core not found", err)


class DriftTest(HomeCase):
    def test_not_git(self):
        self.make_core(files={"a.py": "x"})
        code, out, _ = self.run_cli("drift")
        self.assertIn("not a git checkout", out)

    def test_staged_unstaged_untracked_registered(self):
        self.make_core(files={"a.py": "x\n", "b.py": "y\n", "c.py": "z\n"}, git=True)
        self.write_patch("2026-01-01-a", "a.py", ["MARK"])
        (self.core / "a.py").write_text("x\nMARK\n", encoding="utf-8")          # registered file
        (self.core / "b.py").write_text("y changed\n", encoding="utf-8")        # unstaged, unregistered
        (self.core / "c.py").write_text("z changed\n", encoding="utf-8")
        self.git("add", "c.py")                                                 # staged, unregistered
        (self.core / "new.py").write_text("n\n", encoding="utf-8")              # untracked
        (self.core / "a.py.pre-mypatch").write_text("backup\n", encoding="utf-8")  # ignored by default globs
        code, out, _ = self.run_cli("drift", "--json")
        d = json.loads(out)
        self.assertTrue(d["available"])
        self.assertEqual(d["registered"], ["a.py"])
        self.assertEqual(sorted(d["unregistered"]), ["b.py", "c.py", "new.py"])   # new files count
        self.assertEqual(d["untracked"], ["new.py"])

    def test_local_commits_ahead_of_tag(self):
        self.make_core(files={"a.py": "x\n"}, git=True)
        (self.core / "a.py").write_text("x2\n", encoding="utf-8")
        self.git("-c", "user.email=t@example.com", "-c", "user.name=t", "commit", "-qam", "local")
        ctx = self.ctx()
        core = fn.core_info(ctx)
        self.assertEqual(core["ahead"], 1)
        self.assertEqual(core["tag"], "v0.21.5")


class DoctorTest(HomeCase):
    def test_events_on_change_and_recovery(self):
        self.make_core(files={"a.py": "MARK"}, git=True)
        self.write_patch("2026-01-01-a", "a.py", ["MARK"], patch_short="Patch A")
        ctx = self.ctx()
        state = fn.load_state(ctx)

        def tick():
            notes, core, results, drift, _ = fn.collect(ctx)
            ev = fn.record_core(state, core, fn.now_utc())
            events = ([ev] if ev else []) + fn.diff_events(state, core, results, drift, notes)
            return [e["kind"] for e in events]

        self.assertEqual(tick(), [])                         # first run, all fine: silence
        self.assertEqual(tick(), [])                         # nothing changed: silence
        (self.core / "a.py").write_text("plain", encoding="utf-8")
        self.git("-c", "user.email=t@example.com", "-c", "user.name=t", "commit", "-qam", "update")
        self.assertEqual(tick(), ["core_changed", "patch_MISSING"])
        self.assertEqual(tick(), [])                         # still missing: no repeat
        (self.core / "b.py").write_text("x", encoding="utf-8")
        self.git("add", "b.py")
        self.assertEqual(tick(), ["drift_new"])
        self.git("rm", "-q", "--cached", "b.py")
        (self.core / "b.py").unlink()
        (self.core / "a.py").write_text("MARK", encoding="utf-8")
        kinds = tick()
        self.assertIn("patch_back", kinds)
        self.assertIn("drift_clear", kinds)

    def test_rollback_detected(self):
        self.make_core(files={"a.py": "1"}, git=True)
        ctx = self.ctx()
        state = fn.load_state(ctx)
        root = ctx.hermes_root
        fn.record_core(state, fn.core_info(ctx), fn.now_utc(), root)
        first = fn.core_info(ctx)["identity"]
        (self.core / "a.py").write_text("2", encoding="utf-8")
        self.git("-c", "user.email=t@example.com", "-c", "user.name=t", "commit", "-qam", "u")
        second = fn.core_info(ctx)["identity"]
        self.assertEqual(fn.record_core(state, fn.core_info(ctx), fn.now_utc(), root)["kind"], "core_changed")
        self.git("checkout", "-q", first)
        self.assertEqual(fn.record_core(state, fn.core_info(ctx), fn.now_utc(), root)["kind"], "core_rollback")
        self.git("checkout", "-q", second)   # A -> B -> A -> B: the last step goes forward
        self.assertEqual(fn.record_core(state, fn.core_info(ctx), fn.now_utc(), root)["kind"], "core_changed")

    def test_bootstrap_record_is_used(self):
        self.make_core(files={"a.py": "1"}, git=True)
        ident = fn.core_info(self.ctx())["identity"]
        rec = self.home / "installs" / "abc" / "bootstrap"
        rec.mkdir(parents=True)
        (rec / "default.json").write_text(json.dumps({"identity": ident, "bootstrappedAt": "2026-09-30T19:45:10+0700"}),
                                          encoding="utf-8")
        self.assertEqual(fn.core_info(self.ctx())["bootstrapped_at"], "2026-09-30T12:45:10Z")

    def test_doctor_read_only_writes_nothing(self):
        self.make_core(files={"a.py": "MARK"}, git=True)
        self.write_patch("2026-01-01-a", "a.py", ["MARK"])
        before = self.files_snapshot()
        for argv in (["doctor", "--read-only"], ["patches", "check", "--read-only"], ["drift", "--read-only"],
                     ["dashboard", "--format", "text", "--read-only"], ["lint", "--read-only"],
                     ["search", "x", "--read-only"]):
            self.run_cli(*argv)
        self.assertEqual(before, self.files_snapshot())

    def test_common_flags_before_the_subcommand(self):
        # 1.2.3: `fieldnotes.py --read-only doctor` failed with "unrecognized arguments" (exit 2).
        self.make_core(files={"a.py": "MARK"}, git=True)
        self.write_patch("2026-01-01-a", "a.py", ["MARK"])
        before = self.files_snapshot()
        for argv in (["--read-only", "doctor"], ["--read-only", "search", "x"], ["--read-only", "patches", "check"]):
            with self.subTest(argv=argv):
                code, _, err = self.run_cli(*argv)
                self.assertEqual(code, 0, err)
        self.assertEqual(before, self.files_snapshot())
        args = fn.build_parser().parse_args(["--read-only", "--json", "doctor"])
        self.assertEqual((args.read_only, args.json), (True, True))          # not reset by the subcommand
        args = fn.build_parser().parse_args(["doctor", "--read-only", "--json"])
        self.assertEqual((args.read_only, args.json), (True, True))
        args = fn.build_parser().parse_args(["doctor"])
        self.assertEqual((args.read_only, args.json, args.root), (False, False, None))
        code, out, _ = self.run_cli("--json", "patches", "check")
        self.assertEqual(json.loads(out)["patches"][0]["status"], "OK")
        for argv in (["--read-only", "tick"], ["tick", "--read-only"]):
            with self.subTest(argv=argv):
                code, _, err = self.run_cli(*argv)
                self.assertNotEqual(code, 0)
                self.assertIn("--read-only", err)

    def test_doctor_writes_state_and_text(self):
        self.make_core(files={"a.py": "MARK"}, git=True)
        self.write_patch("2026-01-01-a", "a.py", ["MARK"], patch_short="Patch A")
        code, out, _ = self.run_cli("doctor")
        self.assertEqual(code, 0, out)
        self.assertIn("all live patches have their signs in place", out)
        state = json.loads((self.home / "cache" / "field-notes-state.json").read_text(encoding="utf-8"))
        self.assertEqual(state["last_check"]["patches"], {"2026-01-01-a": "OK"})
        with fn.Lock(self.home / "cache" / "field-notes.lock", wait=0):   # released, not just closed
            pass

    def test_corrupt_state_recovers(self):
        self.make_core(files={"a.py": "MARK"})
        (self.home / "cache").mkdir()
        (self.home / "cache" / "field-notes-state.json").write_text("{broken", encoding="utf-8")
        code, out, _ = self.run_cli("doctor")
        self.assertIn("state file was unreadable", out)
        self.assertTrue((self.home / "cache" / "field-notes-state.json.corrupt").is_file())

    def test_explicit_paths_fail_loudly(self):
        code, _, err = self.run_cli("doctor", "--hermes-home", str(self.tmp / "nope"))
        self.assertEqual(code, 4)
        code, _, err = self.run_cli("doctor", "--config", str(self.tmp / "nope.json"))
        self.assertEqual(code, 4)

    def test_precedence_cli_env_file(self):
        (self.home / "field-notes.json").write_text(json.dumps({"store_dir": str(self.tmp / "from-file"),
                                                                "language": "ru"}), encoding="utf-8")
        self.assertEqual(self.ctx().store, self.tmp / "from-file")
        self.assertEqual(self.ctx().lang, "ru")
        os.environ["FIELDNOTES_STORE_DIR"] = str(self.tmp / "from-env")
        self.assertEqual(self.ctx().store, self.tmp / "from-env")
        self.assertEqual(self.ctx(root=str(self.tmp / "from-cli")).store, self.tmp / "from-cli")



class ReviewFixesTest(HomeCase):
    """Findings of the code review 07.10.2026."""

    def test_upstream_rule_needs_signs_and_honours_not_contains(self):
        self.make_core(files={"a.py": "old_code()"})
        self.assertTrue(any("contains must name" in p for p in fn.validate_checks(
            {"editions": [{"targets": [{"file": "a.py", "contains": ["M"]}], "upstream": [{"file": "a.py"}]}]})))
        self.assertTrue(any("upstream must be a list" in p for p in fn.validate_checks(
            {"editions": [{"targets": [{"file": "a.py", "contains": ["M"]}], "upstream": 42}]})))
        self.write_patch("2026-01-01-a", "a.py", ["M"],
                         upstream_rules=[{"file": "a.py", "contains": ["old_code()"], "not_contains": ["old_code()"]}])
        ctx = self.ctx()
        r = fn.check_patches(ctx, fn.load_notes(ctx), fn.core_info(ctx))[0]
        self.assertEqual(r["status"], "MISSING")          # not a false UPSTREAMED

    def test_damaged_patch_note_is_unknown(self):
        self.make_core(files={"a.py": "M"})
        path = self.write_patch("2026-01-01-a", "a.py", ["M"])
        path.write_text("no frontmatter at all", encoding="utf-8")
        ctx = self.ctx()
        r = fn.check_patches(ctx, fn.load_notes(ctx), fn.core_info(ctx))
        self.assertEqual((r[0]["status"], r[0]["reason"]), ("UNKNOWN", "bad_note"))

    def test_doctor_exit_codes_core_missing_and_lint_errors(self):
        self.write_note("2026-01-01-a")
        code, out, _ = self.run_cli("doctor", "--read-only")
        self.assertEqual(code, 4)
        self.make_core(files={"a.py": "M"})
        self.write_note("2026-01-02-bad", status="done")
        code, out, _ = self.run_cli("doctor", "--read-only")
        self.assertEqual(code, 1)
        self.assertIn("registry unreliable", out)

    def test_prerelease_is_before_release(self):
        self.assertLess(fn.version_tuple("0.22.0-rc1"), fn.version_tuple("0.22.0"))
        editions = [{"when": {"min_version": "0.22.0"}, "targets": [{"file": "a.py", "contains": ["M"]}]}]
        self.assertEqual(fn._edition_for(editions, "0.22.0rc1"), (None, "n/a"))

    def test_tick_refuses_read_only(self):
        self.make_core(files={"a.py": "M"})
        code, _, err = self.run_cli("tick", "--read-only")
        self.assertEqual(code, 1)
        self.assertFalse((self.home / "cache").exists())

    def test_pending_alert_survives_an_interrupted_tick(self):
        self.make_core(files={"a.py": "M"})
        self.write_patch("2026-01-01-a", "a.py", ["M"], patch_short="Patch A")
        self.run_cli("tick")
        (self.core / "a.py").write_text("x", encoding="utf-8")
        orig = fn.upstream_info

        def crash_after_baseline(ctx, state, core, allow_network=True):
            raise KeyboardInterrupt  # killed after diff_events moved the baseline
        ctx = self.ctx()
        state = fn.load_state(ctx)
        notes, core, results, drift, _ = fn.collect(ctx)
        events = fn.diff_events(state, core, results, drift, notes)
        state["pending"] = fn.format_events(ctx, state, events)
        fn.save_state(ctx, state)                          # the run dies before printing
        code, out, _ = self.run_cli("tick")
        self.assertIn("Patch «Patch A» is lost", out)       # repeated, not lost
        code, out, _ = self.run_cli("tick")
        self.assertEqual(out, "")
        fn.upstream_info = orig

if __name__ == "__main__":
    unittest.main()
