---
description: Start a bigger subject (e.g. HLD) — creates its folder and an empty plan doc, then plan it with /learn:teach-subject
argument-hint: "<Subject>"
allowed-tools: Bash(python3:*)
---
!`python3 "${CLAUDE_PLUGIN_ROOT}/scripts/md-log.py" subject "$ARGUMENTS"`

Tell the user in one or two short sentences what was created (the subject folder and its plan doc), and that the next step is `/learn:teach-subject` to set goals and build the plan. If the line above is a usage hint or starts with "md-log error", pass that on instead. Do nothing else.
