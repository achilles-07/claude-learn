#!/usr/bin/env python3
"""render — the diagram makers' only tool for rendering and publishing (macOS, Linux, Windows).

  render.py stage                  create ./.viz-staging/<random> for sources/previews; prints it
  render.py mermaid <in.mmd> <out.png>
  render.py svg <in.svg> <out.png>
  render.py publish <preview.png> <slug>
                                   copy into the lesson's viz/ folder (next to the note this
                                   session logs to, else ./viz) as viz-<slug>-<ms>.png; prints path

Mermaid renders with `mmdc` (npm i -g @mermaid-js/mermaid-cli), using an installed
Chrome/Chromium/Edge when one is found. SVG renders with rsvg-convert, falling back to
ImageMagick, then headless Chrome.
"""
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
TIMEOUT_S = 120


def fail(msg):
    print(f"render error: {msg}", file=sys.stderr)
    sys.exit(1)


def find_browser():
    env = os.environ.get("PUPPETEER_EXECUTABLE_PATH")
    if env and Path(env).exists():
        return env
    if sys.platform == "darwin":
        candidates = ["/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
                      "/Applications/Chromium.app/Contents/MacOS/Chromium",
                      "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge"]
    elif sys.platform == "win32":
        roots = [os.environ.get(k, "") for k in ("PROGRAMFILES", "PROGRAMFILES(X86)", "LOCALAPPDATA")]
        candidates = [os.path.join(r, *p) for r in roots if r for p in (
            ("Google", "Chrome", "Application", "chrome.exe"),
            ("Microsoft", "Edge", "Application", "msedge.exe"))]
    else:
        candidates = [shutil.which(n) for n in ("google-chrome", "google-chrome-stable",
                                                 "chromium", "chromium-browser", "microsoft-edge")]
    return next((c for c in candidates if c and Path(c).exists()), None)


def run(cmd):
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=TIMEOUT_S)
    except subprocess.TimeoutExpired:
        fail(f"timed out after {TIMEOUT_S}s: {cmd[0]}")
    if r.returncode != 0:
        fail((r.stderr or r.stdout).strip()[-2000:] or f"{cmd[0]} exited {r.returncode}")


def mermaid(src, out):
    mmdc = shutil.which("mmdc")
    if not mmdc:
        fail("mmdc not found — install it: npm i -g @mermaid-js/mermaid-cli")
    cmd = [mmdc, "-i", src, "-o", out, "-b", "white", "-s", "2"]
    browser = find_browser()
    if browser:
        cfg = Path(tempfile.gettempdir()) / "claude-learn-puppeteer.json"
        cfg.write_text(json.dumps({"executablePath": browser, "args": ["--no-sandbox"]}))
        cmd += ["-p", str(cfg)]
    run(cmd)


def svg_size(src):
    text = Path(src).read_text(encoding="utf-8", errors="replace")[:4000]
    num = lambda k: re.search(rf'\b{k}="([\d.]+)', text)
    w, h = num("width"), num("height")
    if w and h:
        return int(float(w.group(1))), int(float(h.group(1)))
    vb = re.search(r'viewBox="[\d.\-]+[ ,]+[\d.\-]+[ ,]+([\d.]+)[ ,]+([\d.]+)"', text)
    return (int(float(vb.group(1))), int(float(vb.group(2)))) if vb else (800, 600)


def svg(src, out):
    if shutil.which("rsvg-convert"):
        return run(["rsvg-convert", "-z", "2", "-b", "white", src, "-o", out])
    if shutil.which("magick"):
        return run(["magick", "-density", "192", "-background", "white", src, "-flatten", out])
    browser = find_browser()
    if not browser:
        fail("no SVG renderer — install librsvg (rsvg-convert), ImageMagick, or Chrome")
    w, h = svg_size(src)
    run([browser, "--headless=new", "--disable-gpu", "--hide-scrollbars", "--default-background-color=ffffffff",
         "--force-device-scale-factor=2", f"--window-size={w},{h}", f"--screenshot={out}",
         Path(src).resolve().as_uri()])


def viz_dir():
    r = subprocess.run([sys.executable, str(HERE / "md-log.py"), "vizdir"], capture_output=True, text=True)
    return Path(r.stdout.strip() or Path.cwd() / "viz")


def publish(png, slug):
    if not Path(png).exists():
        fail(f"no such file: {png}")
    clean = re.sub(r"[^a-z0-9]+", "-", slug.lower()).strip("-") or "viz"
    dest_dir = viz_dir()
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / f"viz-{clean}-{int(time.time() * 1000)}.png"
    shutil.copyfile(png, dest)
    print(dest)


def stage():
    # Under the cwd (hidden): file edits there need no extra permission, and
    # Obsidian never indexes dot-folders.
    root = Path.cwd() / ".viz-staging"
    root.mkdir(parents=True, exist_ok=True)
    print(tempfile.mkdtemp(dir=root))


def main(argv):
    cmd, args = (argv[1] if len(argv) > 1 else ""), argv[2:]
    if cmd == "stage" and not args:
        return stage()
    if cmd in ("mermaid", "svg") and len(args) == 2:
        (mermaid if cmd == "mermaid" else svg)(*args)
        if not Path(args[1]).exists():
            fail("renderer reported success but wrote no PNG")
        return print(args[1])
    if cmd == "publish" and len(args) == 2:
        return publish(*args)
    print(__doc__)
    sys.exit(2)


if __name__ == "__main__":
    main(sys.argv)
