---
description: Start logging this session to a topic note in the learning vault (opens it in Obsidian)
argument-hint: "<topic>[/<subtopic>]"
allowed-tools: Bash(python3:*)
---
!`python3 "${CLAUDE_PLUGIN_ROOT}/scripts/md-log.py" link "$ARGUMENTS"`

Tell the user the result above in one short sentence (which note it is logging to). If it is a usage hint or starts with "md-log error", pass that on. Do nothing else.
