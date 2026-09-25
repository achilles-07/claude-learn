---
description: Learn the next topic of a subject (or a named one, e.g. HLD/Caching) using its plan
argument-hint: "[Subject/Topic]"
allowed-tools: Bash(python3:*)
---
Subjects with plans:
!`python3 "${CLAUDE_PLUGIN_ROOT}/scripts/md-log.py" subjects`

Load the `learn:teach` skill and run its **Topic mode — `/teach-topic`**. The user asked for: "$ARGUMENTS" (empty means: the next topic that isn't Done, in this session's subject — or the only subject above; if several could apply, ask which with `AskUserQuestion`).
