# ~/Developer/Study/learn/tests/test_md_log.py
import json, os, subprocess, tempfile, time, unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "md-log.py"
SID = "11111111-2222-3333-4444-555555555555"


def user(text, meta=False):
    d = {"type": "user", "isSidechain": False, "message": {"role": "user", "content": text}}
    if meta:
        d["isMeta"] = True
    return d


def assistant(*content):
    return {"type": "assistant", "isSidechain": False, "message": {"role": "assistant", "content": list(content)}}


def text(t):
    return {"type": "text", "text": t}


def ask_use(tid, questions):
    return {"type": "tool_use", "id": tid, "name": "AskUserQuestion", "input": {"questions": questions}}


def tool_result(tid, content, tur=None):
    d = {"type": "user", "isSidechain": False,
         "message": {"role": "user", "content": [{"type": "tool_result", "tool_use_id": tid, "content": content}]}}
    if tur is not None:
        d["toolUseResult"] = tur
    return d


Q = {"question": "What is $2+2$?", "header": "Arithmetic", "multiSelect": False,
     "options": [{"label": "3", "description": ""}, {"label": "4", "description": ""}]}


class MdLogTest(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.state = self.tmp / "state"
        self.projects = self.tmp / "projects"
        (self.projects / "-proj").mkdir(parents=True)
        self.transcript = self.projects / "-proj" / f"{SID}.jsonl"
        self.transcript.write_text("")
        self.cwd = self.tmp / "vault"
        self.cwd.mkdir()
        self.env = {**os.environ, "MD_LOG_STATE_DIR": str(self.state),
                    "MD_LOG_PROJECTS_DIR": str(self.projects), "CLAUDE_CODE_SESSION_ID": SID,
                    "MD_LOG_SYNC": "1",  # run hooks inline so assertions don't race the detached worker
                    "MD_LOG_VAULT": str(self.tmp / "vaultroot"), "MD_LOG_NO_OPEN": "1"}
        self.vault = self.tmp / "vaultroot"

    def write(self, *entries, partial=None):
        with open(self.transcript, "a") as f:
            for e in entries:
                f.write(json.dumps(e) + "\n")
            if partial is not None:
                f.write(partial)

    def run_cli(self, *args, stdin=None):
        return subprocess.run(["python3", str(SCRIPT), *args], cwd=self.cwd, env=self.env,
                              input=stdin, capture_output=True, text=True)

    def hook(self, sid=SID, event="Stop", tool_use_id=None):
        data = {"session_id": sid, "transcript_path": str(self.transcript), "hook_event_name": event}
        if tool_use_id:
            data["tool_use_id"] = tool_use_id
        return self.run_cli("hook", stdin=json.dumps(data))

    def log(self):
        return (self.cwd / "lesson.md").read_text()

    def test_link_backfills_user_and_assistant(self):
        self.write(user("teach me TCP"), assistant(text("First, packets.")))
        r = self.run_cli("link", "lesson.md")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("linked", r.stdout)
        self.assertEqual(self.log(), "> **You:** teach me TCP\n\nFirst, packets.\n")

    def test_hook_appends_only_new_entries(self):
        self.write(user("one"))
        self.run_cli("link", "lesson.md")
        self.write(user("go"), assistant(text("two")))
        self.hook()
        self.hook()  # second run must not duplicate
        self.assertEqual(self.log().count("two"), 1)
        self.assertEqual(self.log().count("one"), 1)

    def test_consecutive_assistant_text_merged(self):
        self.write(assistant(text("a")), assistant(text("b")))
        self.run_cli("link", "lesson.md")
        self.assertEqual(self.log(), "a\n\nb\n")
        self.assertIn("a\n\nb", self.log())

    def test_question_and_answer(self):
        self.write(assistant(text("Quick check."), ask_use("t1", [Q])),
                   tool_result("t1", 'The user answered: "What is $2+2$?"="4"',
                               {"questions": [Q], "answers": {"What is $2+2$?": "4"}}),
                   assistant(text("> **✓ Correct**")))
        self.run_cli("link", "lesson.md")
        log = self.log()
        self.assertIn("> **Question — Arithmetic**\n> What is $2+2$?\n>\n> 1. 3\n> 2. 4", log)
        self.assertIn("> **Your answer — Arithmetic:** 4", log)
        self.assertLess(log.index("**Question —"), log.index("**Your answer"))
        self.assertLess(log.index("**Your answer"), log.index("✓ Correct"))

    def test_question_live_then_answer_in_later_batch(self):
        # PreToolUse run: question is in the transcript, answer isn't yet
        self.run_cli("link", "lesson.md")
        self.write(user("go"), assistant(text("Node 1 explained."), ask_use("t1", [Q])))
        self.hook(event="PreToolUse", tool_use_id="t1")
        log = self.log()
        self.assertIn("Node 1 explained.", log)
        self.assertIn("**Question — Arithmetic**", log)
        self.assertNotIn("Your answer", log)
        # Stop run: answer arrives in a later batch
        self.write(tool_result("t1", "...", {"questions": [Q], "answers": {"What is $2+2$?": "4"}}),
                   assistant(text("graded")))
        self.hook()
        log = self.log()
        self.assertEqual(log.count("**Question —"), 1)
        self.assertIn("> **Your answer — Arithmetic:** 4", log)

    def test_pretooluse_waits_for_transcript_flush(self):
        self.run_cli("link", "lesson.md")
        p = subprocess.Popen(["python3", str(SCRIPT), "hook"], cwd=self.cwd, env=self.env,
                             stdin=subprocess.PIPE, text=True)
        p.stdin.write(json.dumps({"session_id": SID, "transcript_path": str(self.transcript),
                                  "hook_event_name": "PreToolUse", "tool_use_id": "t9"}))
        p.stdin.close()
        time.sleep(0.3)
        self.write(user("go"), assistant(text("late flush"), ask_use("t9", [Q])))
        p.wait(timeout=5)
        self.assertIn("late flush", self.log())
        self.assertIn("**Question —", self.log())

    def test_unanswered_question(self):
        self.write(assistant(ask_use("t1", [Q])),
                   tool_result("t1", "The user doesn't want to proceed with this tool use."))
        self.run_cli("link", "lesson.md")
        self.assertIn("> **Your answer — Arithmetic:** *(no answer)*", self.log())

    def test_multiline_prompt_stays_in_quote(self):
        self.write(user("line one\nline two\n\nline four"))
        self.run_cli("link", "lesson.md")
        self.assertEqual(self.log(), "> **You:** line one\n> line two\n>\n> line four\n")

    def test_no_obsidian_only_syntax(self):
        self.write(user("q"), assistant(text("t"), ask_use("t1", [Q])),
                   tool_result("t1", "", {"answers": {"What is $2+2$?": "4"}}))
        self.run_cli("link", "lesson.md")
        self.assertNotIn("[!", self.log())

    def test_noise_filtered(self):
        self.write(
            user("<local-command-caveat>Caveat...</local-command-caveat>", meta=True),
            user("<command-name>/model</command-name>\n<command-message>model</command-message>\n<command-args></command-args>"),
            user("<command-name>/md-log</command-name>\n<command-args>lesson.md</command-args>"),
            user([{"type": "text", "text": "Base directory for this skill: /x/skills/teach\n\n# Teaching"}], meta=True),
            user("hi<system-reminder>secret</system-reminder>"),
            assistant({"type": "thinking", "thinking": "hmm"},
                      {"type": "tool_use", "id": "b1", "name": "Bash", "input": {"command": "ls"}}),
            tool_result("b1", "file.txt"),
            {"type": "attachment", "isSidechain": False,
             "attachment": {"type": "queued_command", "prompt": "mid-turn msg", "commandMode": "prompt"}},
            {**user("subagent prompt"), "isSidechain": True},
        )
        self.run_cli("link", "lesson.md")
        log = self.log()
        self.assertNotIn("/model", log)
        self.assertNotIn("/md-log", log)
        self.assertNotIn("SKILL loaded", log)
        self.assertIn("> **You:** hi\n", log)
        for bad in ("secret", "Caveat", "hmm", "file.txt", "subagent prompt", "# Teaching"):
            self.assertNotIn(bad, log)
        self.assertIn("mid-turn msg", log)

    def test_stop_waits_for_final_message_flush(self):
        # Stop can fire before the turn's last assistant text reaches the transcript
        self.run_cli("link", "lesson.md")
        p = subprocess.Popen(["python3", str(SCRIPT), "hook"], cwd=self.cwd, env=self.env,
                             stdin=subprocess.PIPE, text=True)
        p.stdin.write(json.dumps({"session_id": SID, "transcript_path": str(self.transcript),
                                  "hook_event_name": "Stop",
                                  "last_assistant_message": 'Final "quoted" ünïcode line'}))
        p.stdin.close()
        time.sleep(0.3)
        self.write(user("go"), assistant(text('Final "quoted" ünïcode line')))
        p.wait(timeout=5)
        self.assertIn('Final "quoted" ünïcode line', self.log())

    def test_pretooluse_detaches_and_catches_up_slow_flush(self):
        # Interactive Claude Code can write the lesson text + tool_use >2s after
        # PreToolUse fires. The hook must return at once (never delay the popup)
        # and still log them once they land.
        self.run_cli("link", "lesson.md")
        env = {k: v for k, v in self.env.items() if k != "MD_LOG_SYNC"}
        t0 = time.time()
        r = subprocess.run(["python3", str(SCRIPT), "hook"], cwd=self.cwd, env=env, text=True,
                           capture_output=True, timeout=5,
                           input=json.dumps({"session_id": SID, "transcript_path": str(self.transcript),
                                             "hook_event_name": "PreToolUse", "tool_use_id": "slow1"}))
        self.assertLess(time.time() - t0, 1.5)
        self.assertEqual((r.returncode, r.stdout), (0, ""))
        time.sleep(3)
        self.write(user("go"), assistant(text("Slow lesson text."), ask_use("slow1", [Q])))
        for _ in range(60):
            if "Slow lesson text." in self.log():
                break
            time.sleep(0.1)
        self.assertIn("Slow lesson text.", self.log())
        self.assertIn("**Question — Arithmetic**", self.log())

    def test_peer_message_not_logged_as_user(self):
        self.write(
            {"type": "attachment", "isSidechain": False,
             "attachment": {"type": "queued_command", "commandMode": "prompt",
                            "prompt": "<agent-message from=\"x\">REPORT</agent-message>",
                            "origin": {"kind": "peer", "from": "x"}}},
            {"type": "attachment", "isSidechain": False,
             "attachment": {"type": "queued_command", "commandMode": "prompt", "prompt": "typed mid-turn",
                            "origin": {"kind": "human"}}},
        )
        self.run_cli("link", "lesson.md")
        self.assertNotIn("REPORT", self.log())
        self.assertIn("typed mid-turn", self.log())

    def test_plumbing_not_logged(self):
        cmd = lambda name, args="": user(f"<command-name>{name}</command-name>\n"
                                         f"<command-message>{name[1:]}</command-message>\n<command-args>{args}</command-args>")
        self.write(
            cmd("/md-log", "lesson.md"),
            user("md-log expansion prompt", meta=True),
            assistant(text("Now logging this session to lesson.md.")),
            cmd("/teach"),
            user([{"type": "text", "text": "Base directory for this skill: /x/skills/teach\n\n# T"}], meta=True),
            cmd("/teach", "Teach me design patterns"),
            assistant(text("Lesson starts.")),
        )
        self.run_cli("link", "lesson.md")
        log = self.log()
        for bad in ("Now logging", "/teach", "SKILL loaded", "expansion"):
            self.assertNotIn(bad, log)
        self.assertIn("> **You:** Teach me design patterns", log)
        self.assertIn("Lesson starts.", log)

    def test_namespaced_plugin_command_is_plumbing(self):
        self.write(user("<command-name>/learn:md-log</command-name>\n<command-args>X</command-args>"),
                   assistant(text("Now logging to X.")),
                   user("<command-name>/learn:teach</command-name>\n<command-args>Teach me TCP</command-args>"),
                   assistant(text("Lesson.")))
        self.run_cli("link", "lesson.md")
        self.assertNotIn("Now logging", self.log())
        self.assertIn("Teach me TCP", self.log())
        self.assertIn("Lesson.", self.log())

    def test_confirmation_after_first_prompt_link_not_logged(self):
        # /md-log as the first prompt: its confirmation arrives in a later batch
        self.transcript.unlink()
        self.run_cli("link", "lesson.md")
        self.write(user("<command-name>/md-log</command-name>\n<command-args>lesson.md</command-args>"),
                   assistant(text("Now logging this session.")))
        self.hook()
        self.assertNotIn("Now logging", self.log())

    def test_background_notification_turns_not_logged(self):
        self.write(
            user("teach me"), assistant(text("Plan above.")),
            user("<task-notification>\n<task-id>a</task-id>\n</task-notification>"),
            assistant(text("No response requested.")),
            user("Another Claude session sent a message:\n<agent-message from=\"a\">R</agent-message>", meta=True),
            assistant(text("I'm still waiting on you."), ask_use("tq", [Q])),
            user("yes"), assistant(text("Node 1.")),
        )
        self.run_cli("link", "lesson.md")
        log = self.log()
        self.assertNotIn("No response requested", log)
        self.assertNotIn("still waiting", log)
        self.assertIn("**Question — Arithmetic**", log)  # questions always reach the learner
        self.assertIn("Plan above.", log)
        self.assertIn("Node 1.", log)

    def test_embed_in_notification_turn_is_kept(self):
        self.write(user("go"), assistant(text("Node 1.")),
                   user("<task-notification>\n<task-id>m</task-id>\n</task-notification>"),
                   assistant(text("Here is the structure:\n\n![Observer structure](viz/viz-observer-1.png)")),
                   user("<task-notification>\n<task-id>n</task-id>\n</task-notification>"),
                   assistant(text("Noted.")))
        self.run_cli("link", "lesson.md")
        self.assertIn("![Observer structure](viz/viz-observer-1.png)", self.log())
        self.assertNotIn("Noted.", self.log())

    def test_answering_a_quiz_ends_quiet_mode(self):
        # a quiz asked in a background-woken turn: the learner's answer makes it a real turn again
        self.write(user("go"), assistant(text("Node 1.")),
                   user("<task-notification>\n<task-id>m</task-id>\n</task-notification>"),
                   assistant(text("(diagram ready)"), ask_use("t5", [Q])),
                   tool_result("t5", "", {"answers": {"What is $2+2$?": "4"}}),
                   assistant(text("Right. Node 2 builds on that.")))
        self.run_cli("link", "lesson.md")
        self.assertNotIn("diagram ready", self.log())
        self.assertIn("Node 2 builds on that", self.log())

    def test_synthetic_assistant_messages_not_logged(self):
        syn = assistant(text("No response requested."))
        syn["message"]["model"] = "<synthetic>"
        err = assistant(text("API Error: Your computer went to sleep"))
        err["message"]["model"] = "<synthetic>"
        self.write(user("go"), assistant(text("real")), syn, err)
        self.run_cli("link", "lesson.md")
        self.assertNotIn("No response requested", self.log())
        self.assertNotIn("API Error", self.log())
        self.assertIn("real", self.log())

    def test_relink_same_file_does_not_duplicate(self):
        self.write(user("hello"))
        self.run_cli("link", "lesson.md")
        r = self.run_cli("link", "lesson.md")
        self.assertIn("already", r.stdout)
        self.run_cli("unlink")
        self.run_cli("link", "lesson.md")
        self.assertEqual(self.log().count("hello"), 1)
        self.write(user("later"))
        self.hook()
        self.assertEqual(self.log().count("later"), 1)

    def test_compact_summary_and_notifications_skipped(self):
        self.write(
            {**user("This session is being continued from a previous conversation... SUMMARY"),
             "isCompactSummary": True, "isVisibleInTranscriptOnly": True},
            user("<task-notification>\n<task-id>x</task-id>\n</task-notification>"),
            user("<bash-input>ls</bash-input>"),
            user("<bash-stdout>file</bash-stdout><bash-stderr></bash-stderr>"),
            user("real prompt"),
        )
        self.run_cli("link", "lesson.md")
        log = self.log()
        for bad in ("SUMMARY", "task-notification", "bash-input", "bash-stdout"):
            self.assertNotIn(bad, log)
        self.assertEqual(log.count("**You:**"), 1)

    def test_bad_entry_does_not_block_logging(self):
        self.write(user("one"))
        self.run_cli("link", "lesson.md")
        with open(self.transcript, "ab") as f:
            f.write(json.dumps({"type": "assistant", "message": {"content": ["not-a-dict", 5]}}).encode() + b"\n")
            f.write(b'{"type":"user","message":{"content":"caf\xff broken utf8"}}\n')
        self.write(assistant(text("two")))
        self.hook()
        self.assertIn("two", self.log())
        self.write(assistant(text("three")))
        self.hook()
        self.assertEqual(self.log().count("two"), 1)
        self.assertIn("three", self.log())

    def test_hook_unlinked_is_silent(self):
        self.write(user("x"))
        r = self.hook(sid="other-session")
        self.assertEqual((r.returncode, r.stdout, r.stderr), (0, "", ""))
        self.assertFalse((self.cwd / "lesson.md").exists())

    def test_hook_bad_stdin_is_silent(self):
        r = self.run_cli("hook", stdin="not json")
        self.assertEqual((r.returncode, r.stdout), (0, ""))

    def test_partial_last_line_deferred(self):
        self.write(user("one"))
        self.run_cli("link", "lesson.md")
        self.write(user("go"))
        full = json.dumps(assistant(text("two")))
        self.write(partial=full[:20])
        self.hook()
        self.assertNotIn("two", self.log())
        with open(self.transcript, "a") as f:
            f.write(full[20:] + "\n")
        self.hook()
        self.assertEqual(self.log().count("two"), 1)

    def test_link_path_resolution(self):
        # explicit .md paths keep working relative to cwd
        r = self.run_cli("link", "notes/tcp.md")
        self.assertIn(str(self.cwd / "notes" / "tcp.md"), r.stdout)
        self.assertTrue((self.cwd / "notes" / "tcp.md").exists())

    def test_topic_creates_folder_in_vault(self):
        r = self.run_cli("link", "Design Patterns")
        note = self.vault / "Design Patterns" / "Design Patterns.md"
        self.assertIn(str(note), r.stdout)
        self.assertTrue(note.exists())

    def test_subtopic_goes_in_topic_folder(self):
        r = self.run_cli("link", "LLD/SOLID")
        self.assertIn(str(self.vault / "LLD" / "SOLID.md"), r.stdout)
        self.assertTrue((self.vault / "LLD" / "SOLID.md").exists())

    def test_topic_is_sanitized_and_cannot_escape_vault(self):
        r = self.run_cli("link", 'What is "TCP"? #1')
        self.assertIn(str(self.vault / "What is TCP 1" / "What is TCP 1.md"), r.stdout)
        r = self.run_cli("link", "../../etc/evil")
        self.assertIn(str(self.vault / "etc" / "evil.md"), r.stdout)

    def test_empty_topic_prints_usage(self):
        r = self.run_cli("link")
        self.assertEqual(r.returncode, 0)
        self.assertIn("usage", r.stdout.lower())
        self.assertFalse(self.vault.exists())

    def test_vizdir_is_next_to_linked_note(self):
        self.assertEqual(self.run_cli("vizdir").stdout.strip(), str(self.cwd.resolve() / "viz"))  # unlinked: cwd
        self.run_cli("link", "LLD/SOLID")
        self.assertEqual(self.run_cli("vizdir").stdout.strip(), str(self.vault / "LLD" / "viz"))

    def test_link_without_session_env(self):
        env = {k: v for k, v in self.env.items() if k != "CLAUDE_CODE_SESSION_ID"}
        r = subprocess.run(["python3", str(SCRIPT), "link", "x.md"], cwd=self.cwd, env=env,
                           capture_output=True, text=True)
        self.assertEqual(r.returncode, 0)  # non-zero would abort the slash command's turn
        self.assertIn("md-log error", r.stdout)

    def test_link_before_transcript_exists(self):
        # /md-log as a session's first prompt: Claude Code hasn't created the JSONL yet
        self.transcript.unlink()
        r = self.run_cli("link", "lesson.md")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("linked", r.stdout)
        self.write(user("first"), assistant(text("reply")))
        self.hook()
        self.assertIn("first", self.log())
        self.assertIn("reply", self.log())

    def test_unlink_stops_logging(self):
        self.write(user("one"))
        self.run_cli("link", "lesson.md")
        self.assertIn("unlinked", self.run_cli("unlink").stdout)
        self.write(assistant(text("two")))
        self.hook()
        self.assertNotIn("two", self.log())
        self.assertIn("not linked", self.run_cli("unlink").stdout)

    def test_relink_new_file_backfills_whole_session(self):
        self.write(user("one"))
        self.run_cli("link", "lesson.md")
        self.run_cli("link", "other.md")
        self.assertIn("one", (self.cwd / "other.md").read_text())

    def test_appends_to_existing_file_with_blank_line(self):
        (self.cwd / "lesson.md").write_text("# My notes\n")
        self.write(user("one"))
        self.run_cli("link", "lesson.md")
        self.assertTrue(self.log().startswith("# My notes\n\n> **You:**"))


if __name__ == "__main__":
    unittest.main()
