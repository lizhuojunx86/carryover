# Changelog

## 0.1.0 · 2026-10-22

First release.

- `scan`: inventory of Claude Code projects and Cowork accounts, sessions, Projects, scheduled tasks,
  artifacts and memory, plus warnings (30-day transcript cleanup, prompts stored under
  `~/Documents/Claude`, missing folders, tasks already moved to the cloud, orphaned prompt folders).
- `export`: condensed transcripts, memory, Cowork outputs, per-Project restore packs, scheduled-task
  checklist with prompts, artifact copies, `INDEX.md` and `manifest.json`.
- Read-only by design; metadata field whitelist; credential-file deny list; secret masking in text output.
