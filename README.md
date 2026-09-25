# learn — a teaching system for Claude Code

Turn Claude Code into a tutor that teaches for *understanding*, not memorization:

- **Probe → plan → teach.** Claude first maps what you already know with graded quiz popups, then plans a dependency map of the topic (unconditional truths at the roots), then teaches it node by node. Every step is motivated ("how could I have discovered this?") and quiz-checked.
- **Diagrams that are checked.** Structural ideas get a class, sequence, state or flow diagram, or an SVG figure. They're planned up front and drawn in the background by subagents that render each picture and *look at it* before handing it over.
- **Fact-checking.** A researcher subagent verifies claims on the web before they're taught.
- **A live Obsidian lesson log.** `/learn:md-log <topic>` creates a note for the topic in your vault and mirrors the lesson into it as you go: explanations, quiz questions before you answer, your answers, and diagrams. Math renders as LaTeX.

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
- [**Obsidian**](https://obsidian.md) to read the lessons (optional; the log is plain Markdown)

| | macOS | Linux (Debian/Ubuntu) | Windows |
|---|---|---|---|
| Python 3 | `brew install python` | `sudo apt install python3` | Microsoft Store "Python 3.x" (provides `python3`)¹ |
| Node.js | `brew install node` | `sudo apt install nodejs npm` | `winget install OpenJS.NodeJS` |
| Mermaid CLI | `npm i -g @mermaid-js/mermaid-cli` | same | same |
| SVG renderer | `brew install librsvg` | `sudo apt install librsvg2-bin` | Chrome or Edge (already installed) is enough |
| Obsidian | `brew install --cask obsidian` | `flatpak install flathub md.obsidian.Obsidian` or AppImage | `winget install Obsidian.Obsidian` |

¹ The python.org installer on Windows provides `python`/`py` but not `python3`. Either use the Microsoft Store build, or copy `python.exe` to `python3.exe` in the Python install folder.

## Install

### Option A: straight from GitHub (recommended, same on every platform)

Inside Claude Code:

```
/plugin marketplace add achilles-07/claude-learn
/plugin install learn@claude-learn
```

Restart Claude Code. That's it. Use `/plugin` to update, disable or remove it later.

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

## Set up your learning vault

Lessons go into a vault folder, `~/learn` by default (`%USERPROFILE%\learn` on Windows). To use a different folder, set `LEARN_VAULT` in `~/.claude/settings.json`:

```json
{
  "env": { "LEARN_VAULT": "/Users/you/Documents/learn" }
}
```

On Windows use a path like `"C:\\Users\\you\\Documents\\learn"`.

Open that folder in Obsidian once with **Open folder as vault**, so `/learn:md-log` can open notes in it.

## Use it

```
cd ~/learn            # or anywhere: notes always go to the vault
claude
/learn:md-log LLD/Strategy
/learn:teach Strategy pattern. I know basic OOP; focus on when to use it vs State
```

- `/learn:md-log Design Patterns` → `<vault>/Design Patterns/Design Patterns.md`
- `/learn:md-log LLD/SOLID` → `<vault>/LLD/SOLID.md` (subtopics share a folder)
- Coming back to a topic later appends to the same note, without duplicating anything.
- Diagrams are saved to `viz/` next to the note and embedded inline.
- `/learn:md-unlog` stops logging.

Answer the quiz popups in the terminal and read the lesson in Obsidian. Pick **Other → idk** when you don't know an answer; that's a useful signal, not a wrong answer. You don't call `visualize`, the researcher or the diagram makers yourself: the teacher uses them.

When nothing else defines them, the short forms `/md-log` and `/teach` also work, and saying "teach me X" triggers the skill too.

## Troubleshooting

- **Nothing appears in the note**: check `~/.claude/md-log/errors.log`, and that `python3 --version` works in the shell Claude Code uses.
- **Diagrams fail to render**: run `python3 scripts/render.py mermaid in.mmd out.png` yourself to see the error. Usually `mmdc` isn't installed, or it can't find a browser. Set `PUPPETEER_EXECUTABLE_PATH` to your Chrome/Edge binary.
- **The note doesn't open in Obsidian**: open the vault folder in Obsidian once. On Linux, `xdg-open` must be able to handle `obsidian://` links.

## Development

```bash
python3 tests/test_md_log.py      # 34 tests for the lesson logger
```

## Credits

The teaching method, skills and agent designs are adapted from Amos Blomqvist's pi configuration, [amosblomqvist/learn](https://github.com/amosblomqvist/learn) (see his video [How I Use AI to Learn Things](https://www.youtube.com/watch?v=kzcI5F4tGiU)). This repo ports them to Claude Code and adds the quiz protocol, planned background visuals, topic vaults and a cross-platform lesson logger.
