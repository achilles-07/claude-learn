---
description: Clear a topic's note and start it over (old content is saved; plan status goes back to Not started)
argument-hint: "<Subject/Topic>"
allowed-tools: Bash(python3:*)
---
The user wants to reset this topic: "$ARGUMENTS"

1. If no topic was given, run `python3 "${CLAUDE_PLUGIN_ROOT}/scripts/md-log.py" subjects`, read the plan(s), and ask with `AskUserQuestion` which topic to reset (list the topics that are In progress or Done first).
2. Confirm once with `AskUserQuestion`: "Clear `<Subject/Topic>` and start it over? The old note is saved, not deleted." with options "Reset it" / "Cancel".
3. On "Reset it", run: `python3 "${CLAUDE_PLUGIN_ROOT}/scripts/md-log.py" reset "<Subject/Topic>"` and tell the user the result in one or two sentences, including where the old content was saved. Then say they can start again with `/learn:teach-topic <Subject/Topic>` in a fresh session. Do nothing else.
