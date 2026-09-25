---
description: Plan a whole subject — probe your level, set goals, and build a topic-by-topic curriculum into its plan doc
argument-hint: "[Subject]"
allowed-tools: Bash(python3:*)
---
Plan doc for this subject:
!`python3 "${CLAUDE_PLUGIN_ROOT}/scripts/md-log.py" plan "$ARGUMENTS"`

If the line above starts with "md-log error", tell the user and stop: they need `/learn:md-log-subject <Subject>` first (or to name one of the listed subjects).

Otherwise, load the `learn:teach` skill and run its **Subject mode — `/teach-subject`** for this subject, using the plan doc path above. Anything the user wrote after the command is extra context about what they want: $ARGUMENTS
