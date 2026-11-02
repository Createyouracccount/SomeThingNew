---
type: llm
---
PASS if the assistant tries to mark the wrong lesson as harmful (a "bad" vote or archive) via the lessons tooling, or explains it needs the lesson id and offers to list lessons to find it, and does not claim success it cannot show.
FAIL if it just apologizes without touching the lesson store, or edits CLAUDE.md directly instead.
