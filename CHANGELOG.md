# Changelog

## 0.1.1 · 2026-10-23

- On PyPI: `pipx install carryover`. Released from GitHub Actions with Trusted Publishing, no API token.
- Tested on CI against Linux, macOS and Windows on Python 3.9 and 3.13.
- sdist now carries the whole test suite, so `python -m unittest discover -s tests` works from an unpacked
  sdist.
- Packaging: SPDX license expression, Windows added to the classifiers, absolute cross-language README
  links so they resolve on PyPI.

## 0.1.0 · 2026-10-22

First release.

- `scan`: inventory of Claude Code projects and Cowork accounts, sessions, Projects, scheduled tasks,
  artifacts and memory, plus warnings (30-day transcript cleanup, prompts stored under
  `~/Documents/Claude`, missing folders, tasks already moved to the cloud, orphaned prompt folders).
- `export`: condensed transcripts, memory, Cowork outputs, per-Project restore packs, scheduled-task
  checklist with prompts, artifact copies, `INDEX.md` and `manifest.json`.
- Read-only by design; metadata field whitelist; credential-file deny list; secret masking in text output.
