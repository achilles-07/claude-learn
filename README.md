# learn — a teaching system for Claude Code

Turn Claude Code into a tutor that teaches for *understanding*, not memorization:

- **Probe → plan → teach.** Claude first maps what you already know with graded quiz popups, then plans a dependency map of the topic (unconditional truths at the roots), then teaches it node by node. Every step is motivated ("how could I have discovered this?") and quiz-checked.
- **Diagrams that are checked.** Structural ideas get a class, sequence, state or flow diagram, or an SVG figure. They're planned up front and drawn in the background by subagents that render each picture and *look at it* before handing it over.
- **Fact-checking.** A researcher subagent verifies claims on the web before they're taught.
- **A live Markdown lesson note.** `/learn:md-log <topic>` creates a plain `.md` note for the topic, opens it in your default Markdown app, and mirrors the lesson into it as you go: explanations, quiz questions before you answer, your answers, and diagrams. It's standard Markdown (with Mermaid diagrams and `$…$` math), so any capable reader works.

## What's inside

| Piece | What it does |
|---|---|
| `skills/teach` | The teaching method (probe → plan → teach, quiz protocol, voice) |
| `skills/visualize` | When and how to add a diagram; dispatches the makers |
| `agents/researcher` | Web fact-checker (WebSearch + WebFetch) |
| `agents/mermaid-maker`, `agents/svg-maker` | Render → inspect → iterate → publish diagram makers |
| `commands/md-log`, `commands/md-unlog` | Start and stop logging to a topic note |
| `hooks/hooks.json` + `scripts/md-log.py` | Mirror the session into the note (Stop, SessionEnd, and before each quiz popup) |
| `scripts/render.py` | Cross-platform rendering for the makers |

## Requirements

- [Claude Code](https://code.claude.com)
- **Python 3**, runnable as `python3`
- **Node.js**, for the Mermaid renderer: `npm install -g @mermaid-js/mermaid-cli`
- **An SVG renderer**, any one of: `rsvg-convert` (librsvg), ImageMagick, or Google Chrome / Chromium / Edge
- **A Markdown reader that renders Mermaid and math**, set as the default app for `.md` files (see below)

| | macOS | Linux (Debian/Ubuntu) | Windows |
|---|---|---|---|
| Python 3 | `brew install python` | `sudo apt install python3` | Microsoft Store "Python 3.x" (provides `python3`)¹ |
| Node.js | `brew install node` | `sudo apt install nodejs npm` | `winget install OpenJS.NodeJS` |
| Mermaid CLI | `npm i -g @mermaid-js/mermaid-cli` | same | same |
| SVG renderer | `brew install librsvg` | `sudo apt install librsvg2-bin` | Chrome or Edge (already installed) is enough |

¹ The python.org installer on Windows provides `python`/`py` but not `python3`. Either use the Microsoft Store build, or copy `python.exe` to `python3.exe` in the Python install folder.

## Install

### Option A: straight from GitHub (recommended, same on every platform)

Inside Claude Code:

```
/plugin marketplace add achilles-07/claude-learn
/plugin install learn@claude-learn
```

Restart Claude Code. That's it. Use `/plugin` to update, disable or remove it later.

> This repo is **private**. `/plugin marketplace add` clones it with your normal git credentials, so the machine needs GitHub access to `achilles-07/claude-learn`: an SSH key added to your GitHub account, or `gh auth login`. If the add fails with an authentication error, use Option B with a clone you've already made.

### Option B: from a copied or cloned folder

Plugins can't simply be dropped into `~/.claude/plugins/`, because Claude Code doesn't auto-discover them there. Put the folder anywhere you like, then register it as a local marketplace. A tidy place:

| Platform | Put the folder at | Then, inside Claude Code |
|---|---|---|
| macOS | `~/.claude/local-plugins/claude-learn` | `/plugin marketplace add ~/.claude/local-plugins/claude-learn` |
| Linux | `~/.claude/local-plugins/claude-learn` | `/plugin marketplace add ~/.claude/local-plugins/claude-learn` |
| Windows | `%USERPROFILE%\.claude\local-plugins\claude-learn` | `/plugin marketplace add C:\Users\<you>\.claude\local-plugins\claude-learn` |

```bash
# macOS / Linux
git clone https://github.com/achilles-07/claude-learn ~/.claude/local-plugins/claude-learn
```
```powershell
# Windows (PowerShell)
git clone https://github.com/achilles-07/claude-learn "$env:USERPROFILE\.claude\local-plugins\claude-learn"
```

Then `/plugin install learn@claude-learn` and restart Claude Code. After a `git pull`, run `/plugin marketplace update claude-learn` to pick up changes.

**Just trying it out?** `claude --plugin-dir /path/to/claude-learn` loads it for one session without installing.

## Pick a Markdown reader

`/learn:md-log` opens the lesson note in your system's **default app for `.md` files**, so choose one that renders **Mermaid** diagrams (the lesson plan's dependency map) and **LaTeX math** (`$…$`), and ideally refreshes live while the file grows. Good options:

| Reader | Mermaid | Math | Platforms |
|---|---|---|---|
| [Obsidian](https://obsidian.md) | built in | built in | macOS, Linux, Windows |
| [Typora](https://typora.io) | built in | built in | macOS, Linux, Windows |
| [MarkText](https://github.com/marktext/marktext) | built in | built in | macOS, Linux, Windows |
| [VS Code](https://code.visualstudio.com) Markdown preview | with the *Markdown Preview Mermaid Support* extension | built in | macOS, Linux, Windows |

Then make it the default for `.md` files:

- **macOS:** Finder → select any `.md` file → *Get Info* (⌘I) → *Open with* → pick the app → *Change All…*
- **Linux:** `xdg-mime default <app>.desktop text/markdown`, for example `xdg-mime default typora.desktop text/markdown`
- **Windows:** right-click any `.md` file → *Open with* → *Choose another app* → pick it → tick *Always use this app*

Diagram images are plain relative links (`viz/…png` next to the note), so they render in every reader.

## Where notes go

Lessons go into `~/learn` by default (`%USERPROFILE%\learn` on Windows). To use a different folder, set `LEARN_DIR` in `~/.claude/settings.json`:

```json
{
  "env": { "LEARN_DIR": "/Users/you/Documents/learn" }
}
```

On Windows use a path like `"C:\\Users\\you\\Documents\\learn"`.

## Use it

```
cd ~/learn            # or anywhere: notes always go to the learn folder
claude
/learn:md-log LLD/Strategy
/learn:teach Strategy pattern. I know basic OOP; focus on when to use it vs State
```

- `/learn:md-log Design Patterns` → `~/learn/Design Patterns/Design Patterns.md`
- `/learn:md-log LLD/SOLID` → `~/learn/LLD/SOLID.md` (subtopics share a folder)
- Coming back to a topic later appends to the same note, without duplicating anything.
- Diagrams are saved to `viz/` next to the note and embedded inline.
- `/learn:md-unlog` stops logging.

Answer the quiz popups in the terminal and read the lesson in your Markdown reader. Pick **Other → idk** when you don't know an answer; that's a useful signal, not a wrong answer. You don't call `visualize`, the researcher or the diagram makers yourself: the teacher uses them.

When nothing else defines them, the short forms `/md-log` and `/teach` also work, and saying "teach me X" triggers the skill too.

## Troubleshooting

- **Nothing appears in the note**: check `~/.claude/md-log/errors.log`, and that `python3 --version` works in the shell Claude Code uses.
- **Diagrams fail to render**: run `python3 scripts/render.py mermaid in.mmd out.png` yourself to see the error. Usually `mmdc` isn't installed, or it can't find a browser. Set `PUPPETEER_EXECUTABLE_PATH` to your Chrome/Edge binary.
- **The note opens in the wrong app** (or doesn't open): set your reader as the default app for `.md` files (see *Pick a Markdown reader*). On Linux this needs `xdg-open`.
- **Diagrams or math show as raw text**: your reader doesn't render Mermaid or LaTeX. Switch readers, or add the plugin/extension for it.

## Development

```bash
python3 tests/test_md_log.py      # 36 tests for the lesson logger
```

## Credits

The teaching method, skills and agent designs are adapted from Amos Blomqvist's pi configuration, [amosblomqvist/learn](https://github.com/amosblomqvist/learn) (see his video [How I Use AI to Learn Things](https://www.youtube.com/watch?v=kzcI5F4tGiU)). This repo ports them to Claude Code and adds the quiz protocol, planned background visuals, topic folders and a cross-platform lesson logger.
