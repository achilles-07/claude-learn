#!/usr/bin/env python3
"""md-log — mirror a Claude Code session into a plain Markdown lesson note.

Port of the pi md-log extension. Captures only reading-relevant content:
user prompts, assistant text, and AskUserQuestion Q&A. Other tools are omitted.

  md-log.py link <topic>[/<subtopic>]  link this session ($CLAUDE_CODE_SESSION_ID) to
                           <learn dir>/<topic>/<topic>.md (or <learn dir>/<topic>/<subtopic>.md),
                           backfill, and open it in your default Markdown app. A *.md, /… or ~… argument
                           is used as a plain file path instead.
  md-log.py link --from-now <topic>  same, but log only from now on (no backfill)
  md-log.py unlink         stop logging this session
  md-log.py subject <Subject>   create <learn dir>/<Subject>/ and "<Subject> — Plan.md"
                           (a skeleton, never overwritten); remembers it as this
                           session's subject; the planning chat itself is not logged
  md-log.py plan [<Subject>]    print the plan path (this session's subject by default)
  md-log.py subjects       list every subject that has a plan: "<name>\t<plan path>"
  md-log.py topics <Subject> <Topic>...  create empty numbered notes "01 <Topic>.md", …
                           (keeps notes that already exist for a topic)
  md-log.py vizdir         where diagrams for this session go (viz/ next to the note)
  md-log.py hook           Stop/SessionEnd/PreToolUse hook: append what's new (silent)
"""
import json
import os
import re
import subprocess
import sys

try:
    import fcntl  # macOS / Linux
except ImportError:  # Windows
    fcntl = None
    import msvcrt
import time
import traceback
from pathlib import Path

STATE_DIR = Path(os.environ.get("MD_LOG_STATE_DIR") or Path.home() / ".claude" / "md-log")
PROJECTS_DIR = Path(os.environ.get("MD_LOG_PROJECTS_DIR") or Path.home() / ".claude" / "projects")
# Where lesson notes live: set LEARN_DIR (e.g. in ~/.claude/settings.json "env") to move it.
VAULT = Path(os.environ.get("LEARN_DIR") or os.environ.get("LEARN_VAULT") or os.environ.get("MD_LOG_VAULT")
             or Path.home() / "learn").expanduser()
LINKS = STATE_DIR / "links.json"
BACKFILLED = STATE_DIR / "backfilled.json"
SUBJECTS = STATE_DIR / "subjects.json"  # {session id: plan path}
PLAN_SUFFIX = " — Plan.md"
PLAN_SKELETON = "# {name} — Plan\n\n## Goals\n\n## Where you are\n\n## Topic map\n\n## Topics\n"
NUMBERED_RE = re.compile(r"^\d+\s+(.+)\.md$", re.IGNORECASE)  # {file: [session ids already backfilled into it]}
ERRORS = STATE_DIR / "errors.log"

SYSTEM_RE = re.compile(r"<system-reminder>.*?</system-reminder>", re.S)
CMD_NAME_RE = re.compile(r"<command-name>(.*?)</command-name>", re.S)
CMD_ARGS_RE = re.compile(r"<command-args>(.*?)</command-args>", re.S)
SKIP_PREFIXES = ("<local-command-caveat>", "<local-command-stdout>", "<local-command-stderr>",
                 "[Request interrupted", "<task-notification>", "<bash-input>", "<bash-stdout>",
                 "<bash-stderr>")
# Hooks fire before the content they follow reaches the transcript: ~50ms in
# headless runs, but >2s in interactive sessions. The waiting happens in a
# detached worker so a hook never delays Claude (or the quiz popup).
FLUSH_WAIT_S = {"PreToolUse": 60.0, "Stop": 30.0}
HIDDEN_COMMANDS = {"md-log", "md-unlog"}


# --- state ---------------------------------------------------------------

def load_json(path):
    try:
        return json.loads(path.read_text())
    except (OSError, ValueError):
        return {}


def save_json(path, data):
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, indent=2))
    tmp.replace(path)


def load_links():
    return load_json(LINKS)


def save_links(links):
    save_json(LINKS, links)


class locked:
    """Serialize concurrent hook runs (Stop and SessionEnd can overlap)."""

    def __enter__(self):
        STATE_DIR.mkdir(parents=True, exist_ok=True)
        self.f = open(STATE_DIR / ".lock", "a+")
        if fcntl:
            fcntl.flock(self.f, fcntl.LOCK_EX)
        else:
            self.f.seek(0)
            while True:
                try:
                    msvcrt.locking(self.f.fileno(), msvcrt.LK_LOCK, 1)
                    break
                except OSError:  # LK_LOCK gives up after ~10s; keep waiting
                    pass

    def __exit__(self, *exc):
        if fcntl:
            fcntl.flock(self.f, fcntl.LOCK_UN)
        else:
            self.f.seek(0)
            msvcrt.locking(self.f.fileno(), msvcrt.LK_UNLCK, 1)
        self.f.close()


# --- transcript ------------------------------------------------------------

def read_new(transcript, offset):
    """Return (entries after `offset` complete lines, total complete lines).
    A trailing line without a newline is still being written: leave it for next time."""
    data = Path(transcript).read_bytes()
    complete = data.split(b"\n")[:-1]
    entries = []
    for line in complete[offset:]:
        try:
            entries.append(json.loads(line.decode("utf-8", errors="replace")))
        except ValueError:
            pass
    return entries, len(complete)


def text_needles(text):
    """How a snippet of `text` can appear inside the JSONL (raw UTF-8 or \\u-escaped)."""
    tail = text.strip()[-40:]
    return [json.dumps(tail, ensure_ascii=False)[1:-1], json.dumps(tail)[1:-1]]


def wait_for_flush(transcript, needles, timeout):
    deadline = time.time() + timeout
    needles = [n.encode() for n in needles if n]
    while time.time() < deadline:
        try:
            data = Path(transcript).read_bytes()
            if any(n in data for n in needles):
                return
        except OSError:
            pass
        time.sleep(0.05)


def find_transcript(session_id):
    hits = sorted(PROJECTS_DIR.glob(f"*/{session_id}.jsonl"), key=lambda p: p.stat().st_mtime)
    return hits[-1] if hits else None


# --- rendering -------------------------------------------------------------

def quote(lines):
    return "\n".join(">" if not line else f"> {line}" for line in lines)


NOTIFICATION_MARKERS = ("<task-notification>", "Another Claude session sent a message", "<agent-message")


def classify_user(text, meta=False):
    """User-side input -> (text to log or None, turn mode).

    Mode "human" starts a turn the learner asked for; "quiet" starts one they
    didn't (a background task finished, a subagent reported, /md-log's own
    confirmation) whose assistant text is plumbing, not lesson; None: no change."""
    text = SYSTEM_RE.sub("", text).strip()
    if not text:
        return None, None
    if text.startswith(NOTIFICATION_MARKERS[0]) or any(m in text[:200] for m in NOTIFICATION_MARKERS[1:]):
        return None, "quiet"
    if meta or text.startswith(SKIP_PREFIXES):
        return None, None  # skill bodies, command expansions, caveats, bash-mode echoes
    name = CMD_NAME_RE.search(text)
    if name:
        if name.group(1).strip().split(":")[-1].lstrip("/") in HIDDEN_COMMANDS:  # also /learn:md-log
            return None, "quiet"
        args = CMD_ARGS_RE.search(text)
        args = args.group(1).strip() if args else ""
        return (args or None), "human"  # "/teach Teach me X" logs as "Teach me X"
    return text, "human"


def question_block(q):
    lines = q.get("question", "").split("\n") + [""]
    lines += [f"{i}. {o.get('label', '')}" for i, o in enumerate(q.get("options") or [], 1)]
    return f"> **Question — {q.get('header') or 'Quiz'}**\n" + quote(lines)


def answer_block(qs, answers):
    lines = [f"**Your answer — {q.get('header') or 'Quiz'}:** {answers.get(q.get('question')) or '*(no answer)*'}"
             for q in qs]
    return quote(lines)


def render(entries, pending=None, quiet=False):
    """Transcript entries -> (markdown blocks, pending asks, quiet).

    `pending` maps AskUserQuestion tool_use_id -> questions whose answer hasn't
    been seen yet; the question is written as soon as it appears (live, before
    the user answers) and the answer in whichever later batch carries the result."""
    blocks = []  # [kind, text]; kind "assistant" merges with a following assistant block
    pending = dict(pending or {})
    state = {"quiet": quiet}  # carried across batches: a turn can span hook runs

    def add(kind, body):
        if kind == "assistant" and blocks and blocks[-1][0] == "assistant":
            blocks[-1][1] += "\n\n" + body
        else:
            blocks.append([kind, body])

    def add_user(raw, meta, starts_turn=True):
        shown, mode = classify_user(raw, meta)
        if mode and starts_turn:
            state["quiet"] = mode == "quiet"
        if shown:
            add("user", quote(f"**You:** {shown}".split("\n")))

    def one(d):
        if not isinstance(d, dict) or d.get("isSidechain") \
                or d.get("isCompactSummary") or d.get("isVisibleInTranscriptOnly"):
            return
        kind = d.get("type")
        if kind == "attachment":
            a = d.get("attachment") or {}
            origin = (a.get("origin") or {}).get("kind", "human")
            if a.get("type") == "queued_command" and a.get("commandMode") == "prompt" \
                    and origin == "human" and isinstance(a.get("prompt"), str):
                add_user(a["prompt"], False, starts_turn=False)  # typed mid-turn
            return
        msg = d.get("message")
        if not isinstance(msg, dict):
            return
        content = msg.get("content")
        if kind == "user":
            if isinstance(content, str):
                add_user(content, d.get("isMeta"))
                return
            for c in content or []:
                if not isinstance(c, dict):
                    continue
                if c.get("type") == "text":
                    add_user(c.get("text", ""), d.get("isMeta"))
                elif c.get("type") == "tool_result" and c.get("tool_use_id") in pending:
                    qs = pending.pop(c["tool_use_id"])
                    state["quiet"] = False  # the learner answered: this is a real lesson turn now
                    tur = d.get("toolUseResult")
                    answers = tur.get("answers") if isinstance(tur, dict) else None
                    add("answer", answer_block(qs, answers if isinstance(answers, dict) else {}))
        elif kind == "assistant":
            if msg.get("model") == "<synthetic>":
                return  # Claude Code placeholders: "No response requested.", API errors
            for c in content or []:
                if not isinstance(c, dict):
                    continue
                # A quiet turn is plumbing, except a reply that embeds a finished diagram
                if c.get("type") == "text" and c.get("text", "").strip() \
                        and (not state["quiet"] or "![" in c["text"]):
                    add("assistant", c["text"].strip())
                elif c.get("type") == "tool_use" and c.get("name") == "AskUserQuestion":
                    qs = (c.get("input") or {}).get("questions") or []
                    add("question", "\n\n".join(question_block(q) for q in qs))
                    pending[c.get("id")] = qs

    for d in entries:
        try:
            one(d)
        except Exception:  # one malformed entry must not stall the log forever
            pass

    out = [body for _, body in blocks]  # the lesson itself is plain prose
    return out, pending, state["quiet"]


def append(file, blocks):
    if not blocks:
        return
    p = Path(file)
    p.parent.mkdir(parents=True, exist_ok=True)
    existing = p.read_text(encoding="utf-8") if p.exists() else ""
    sep = "" if not existing.strip() else ("\n" if existing.endswith("\n") else "\n\n")
    with open(p, "a", encoding="utf-8") as f:
        f.write(sep + "\n\n".join(blocks) + "\n")


# --- commands --------------------------------------------------------------

UNSAFE_NAME_RE = re.compile(r'[\\:*?"<>|#^\[\]]')  # unsafe in file names or Markdown links


def clean_segment(seg):
    return re.sub(r"\s+", " ", UNSAFE_NAME_RE.sub("", seg)).strip(" .")


def resolve_path(arg):
    """Topic -> note in the learn folder; explicit *.md / absolute / ~ paths are used as-is."""
    arg = (arg or "").strip().strip('"').strip("'")
    if not arg:
        return None
    if arg.lower().endswith(".md") or arg.startswith(("/", "~")):
        p = Path(arg).expanduser()
        return p if p.is_absolute() else Path.cwd() / p
    parts = [c for c in (clean_segment(seg) for seg in arg.split("/")) if c]
    if not parts:
        return None
    folder = VAULT.joinpath(*(parts if len(parts) == 1 else parts[:-1]))
    exact = folder / f"{parts[-1]}.md"
    return exact if exact.exists() else (find_topic_note(folder, parts[-1]) or exact)


def find_topic_note(folder, topic):
    """A subject's topic note, "NN <Topic>.md", matched case-insensitively."""
    if not folder.is_dir():
        return None
    for f in sorted(folder.glob("*.md")):
        m = NUMBERED_RE.match(f.name)
        if m and m.group(1).strip().lower() == topic.strip().lower():
            return f
    return None


def subject_folder(arg):
    parts = [c for c in (clean_segment(seg) for seg in (arg or "").strip().strip('"').split("/")) if c]
    return VAULT.joinpath(*parts) if parts else None


def plan_of(folder):
    return folder / f"{folder.name}{PLAN_SUFFIX}"


def open_note(path):
    """Open the note in the system's default app for .md files."""
    if os.environ.get("MD_LOG_NO_OPEN"):
        return
    try:
        if sys.platform == "win32":
            os.startfile(str(path))
        else:
            opener = "open" if sys.platform == "darwin" else "xdg-open"
            subprocess.Popen([opener, str(path)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except OSError:
        pass  # no opener available: logging still works


def cmd_link(arg, from_now=False):
    # Always exit 0: a failing `!` command aborts the slash command's turn.
    sid = os.environ.get("CLAUDE_CODE_SESSION_ID")
    if not sid:
        print("md-log error: CLAUDE_CODE_SESSION_ID is not set — run this from inside Claude Code.")
        return 0
    # On a session's first prompt the transcript doesn't exist yet; the hook
    # supplies transcript_path later and backfills from offset 0.
    transcript = find_transcript(sid)
    path = resolve_path(arg)
    if path is None:
        print("md-log usage: /md-log <topic>  (e.g. /md-log Design Patterns, /md-log LLD/SOLID)")
        return 0
    with locked():
        links = load_links()
        if links.get(sid, {}).get("file") == str(path):
            print(f"md-log: already linked to {path}")
            return 0
        entries, n = read_new(transcript, 0) if transcript else ([], 0)
        # Re-linking a file that already holds this session (e.g. /md-unlog then
        # /md-log) must not duplicate it: backfill each session into a file once.
        backfilled = load_json(BACKFILLED)
        fresh = sid not in backfilled.get(str(path), [])
        if from_now:  # e.g. /teach-topic after planning in the same session
            fresh = False
            if sid not in backfilled.get(str(path), []):
                backfilled.setdefault(str(path), []).append(sid)
        blocks, pending, _ = render(entries) if fresh else ([], {}, True)
        backfilled.setdefault(str(path), [])
        if fresh:
            backfilled[str(path)].append(sid)
        save_json(BACKFILLED, backfilled)
        append(path, blocks)
        if not path.exists():
            path.parent.mkdir(parents=True, exist_ok=True)
            path.touch()
        links[sid] = {"file": str(path), "transcript": str(transcript) if transcript else None,
                      "offset": n, "pending": pending,
                      # after /md-log the rest of the turn is its own confirmation; after a
                      # mid-turn --from-now link (/teach-topic) it is the lesson itself
                      "quiet": not from_now}
        save_links(links)
    how = (f"{len(blocks)} blocks backfilled" if fresh
           else "logging from now on" if from_now else "already has this session: appending from now on")
    open_note(path)
    print(f"md-log: linked {path} ({how})")
    return 0


def cmd_subject(arg):
    sid = os.environ.get("CLAUDE_CODE_SESSION_ID", "")
    folder = subject_folder(arg)
    if folder is None:
        print("md-log usage: /md-log-subject <Subject>  (e.g. /md-log-subject HLD)")
        return 0
    folder.mkdir(parents=True, exist_ok=True)
    plan = plan_of(folder)
    if not plan.exists():
        plan.write_text(PLAN_SKELETON.format(name=folder.name), encoding="utf-8")
    with locked():
        links = load_links()
        if links.pop(sid, None):  # planning is summarized in the plan, not mirrored anywhere
            save_links(links)
        subjects = load_json(SUBJECTS)
        subjects[sid] = str(plan)
        save_json(SUBJECTS, subjects)
    open_note(plan)
    print(f"md-log: subject {folder.name} — plan {plan}")
    return 0


def list_subjects():
    if not VAULT.is_dir():
        return []
    return [(str(p.parent.relative_to(VAULT)), p) for p in sorted(VAULT.glob(f"**/*{PLAN_SUFFIX}"))
            if p.name == f"{p.parent.name}{PLAN_SUFFIX}"]


def cmd_plan(arg):
    # The argument may name a subject, or just be extra context the learner typed
    # after /teach-subject: use it as a subject only if one by that name exists.
    candidates = []
    if (arg or "").strip():
        folder = subject_folder(arg)
        if folder is not None:
            candidates.append(plan_of(folder))
    session_plan = load_json(SUBJECTS).get(os.environ.get("CLAUDE_CODE_SESSION_ID", ""))
    if session_plan:
        candidates.append(Path(session_plan))
    for plan in candidates:
        try:
            if plan.exists():
                print(plan)
                return 0
        except OSError:  # e.g. a paragraph of context is not a valid file name
            continue
    known = ", ".join(name for name, _ in list_subjects()) or "none yet"
    print(f"md-log error: no subject plan found. Subjects: {known}. Start one with /md-log-subject <Subject>.")
    return 0


def cmd_subjects():
    rows = list_subjects()
    print("\n".join(f"{name}\t{plan}" for name, plan in rows) if rows else "md-log: no subjects yet")
    return 0


def cmd_topics(subject, names):
    folder = subject_folder(subject)
    if folder is None or not names:
        print('md-log usage: md-log.py topics <Subject> "<Topic 1>" "<Topic 2>" ...')
        return 0
    folder.mkdir(parents=True, exist_ok=True)
    for i, raw in enumerate(names, 1):
        name = clean_segment(raw)
        if not name:
            continue
        existing = find_topic_note(folder, name)
        if existing:
            print(f"kept {existing}")
            continue
        note = folder / f"{i:02d} {name}.md"
        note.touch()
        print(f"created {note}")
    return 0


def cmd_vizdir():
    link = load_links().get(os.environ.get("CLAUDE_CODE_SESSION_ID", ""))
    print(Path(link["file"]).parent / "viz" if link else Path.cwd() / "viz")
    return 0


def cmd_unlink():
    sid = os.environ.get("CLAUDE_CODE_SESSION_ID", "")
    with locked():
        links = load_links()
        link = links.pop(sid, None)
        save_links(links)
    print(f"md-log: unlinked {link['file']}" if link else "md-log: not linked")
    return 0


def log_error():
    try:
        STATE_DIR.mkdir(parents=True, exist_ok=True)
        with open(ERRORS, "a") as f:
            f.write(time.strftime("%Y-%m-%dT%H:%M:%S ") + traceback.format_exc() + "\n")
    except OSError:
        pass


def sync_log(data):
    """Wait (unlocked) for the triggering content to be flushed, then append what's new."""
    sid = data.get("session_id")
    link = load_links().get(sid)
    transcript = data.get("transcript_path") or (link or {}).get("transcript")
    if not link or not transcript or not Path(transcript).exists():
        return
    event = data.get("hook_event_name")
    if event == "PreToolUse" and data.get("tool_use_id"):
        wait_for_flush(transcript, [data["tool_use_id"]], FLUSH_WAIT_S["PreToolUse"])
    elif event == "Stop" and data.get("last_assistant_message"):
        wait_for_flush(transcript, text_needles(data["last_assistant_message"]), FLUSH_WAIT_S["Stop"])
    with locked():
        links = load_links()  # re-read: another run may have advanced it meanwhile
        link = links.get(sid)
        if not link:
            return
        link["transcript"] = transcript
        entries, n = read_new(transcript, link["offset"])
        blocks, link["pending"], link["quiet"] = render(entries, link.get("pending"), link.get("quiet", False))
        append(link["file"], blocks)
        link["offset"] = n
        save_links(links)


def spawn_worker(data):
    """Re-run this script as a detached worker that outlives the hook, so waiting
    for the transcript never delays Claude. Works on macOS, Linux and Windows."""
    kwargs = {"stdin": subprocess.PIPE, "stdout": subprocess.DEVNULL, "stderr": subprocess.DEVNULL,
              "env": {**os.environ, "MD_LOG_SYNC": "1"}}
    if sys.platform == "win32":
        kwargs["creationflags"] = subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP
    else:
        kwargs["start_new_session"] = True  # own session: not reaped with the hook's group
    proc = subprocess.Popen([sys.executable, os.path.abspath(__file__), "hook"], **kwargs)
    proc.stdin.write(json.dumps(data).encode())
    proc.stdin.close()


def cmd_hook():
    try:
        data = json.loads(sys.stdin.read() or "{}")
        if data.get("session_id") not in load_links():
            return 0  # the common case: unlinked session, stay out of the way
        if data.get("hook_event_name") in FLUSH_WAIT_S and not os.environ.get("MD_LOG_SYNC"):
            spawn_worker(data)
            return 0
        sync_log(data)
    except Exception:
        log_error()
    return 0


def main(argv):
    try:
        return dispatch(argv)
    except Exception as e:  # a failing `!` command would abort the slash command's turn
        log_error()
        print(f"md-log error: {e}")
        return 0


def dispatch(argv):
    cmd = argv[1] if len(argv) > 1 else ""
    args = argv[2:]
    if cmd == "link":
        from_now = bool(args) and args[0] == "--from-now"
        return cmd_link(" ".join(args[1:] if from_now else args), from_now)
    if cmd == "subject":
        return cmd_subject(" ".join(args))
    if cmd == "plan":
        return cmd_plan(" ".join(args))
    if cmd == "subjects":
        return cmd_subjects()
    if cmd == "topics":
        return cmd_topics(args[0] if args else "", args[1:])
    if cmd == "unlink":
        return cmd_unlink()
    if cmd == "vizdir":
        return cmd_vizdir()
    if cmd == "hook":
        return cmd_hook()
    print(__doc__)
    return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
