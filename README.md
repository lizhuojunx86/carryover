# carryover

Move a Claude workspace to a new account or a new machine: Claude Code sessions, Cowork tasks, Projects,
scheduled tasks and memory. It only reads your data and never copies credentials.

[中文说明](https://github.com/lizhuojunx86/carryover/blob/main/README.zh-CN.md)

```
$ carryover scan
Claude Code  ~/.claude
  19 projects · 28 sessions · 323 memory files

Cowork  ~/Library/Application Support/Claude/local-agent-mode-sessions
  account a1b2c3d4 / org e5f6a7b8  (old@example.com)
    432 sessions · 10 projects · 39 scheduled tasks · 12 artifacts · 26 global memory files

Check before you switch:
  ! Claude Code deletes local transcripts older than 30 days each time it starts ...
  ! 39 scheduled-task prompt(s) live under ~/Documents/Claude ...
  ! 23 prompt folder(s) under ~/Documents/Claude/Scheduled are not in any task registry ...
```

## Why

I retired one Claude account in October 2026 and moved everything to another one on the same Mac.
I found no export in the app for Cowork's local Projects, project memory or scheduled tasks, so I read
the files on disk and rebuilt from there. Three things surprised me:

- Project instructions, per-project memory and 62 scheduled-task prompts were all sitting in local files,
  but nothing in the app pointed at them.
- Rebuilt tasks could not read their old prompts, because Cowork treats `~/Documents/Claude` as its own
  folder and keeps sessions out of it.
- Halfway through, Claude Code started once and removed 13 of my transcripts. It deletes local transcripts
  older than 30 days by default (`cleanupPeriodDays`), and I had never changed that.

carryover is the cleaned-up version of the scripts I wrote that day. The longer story is on
[dev.to](https://dev.to/lizhuojunx86/i-moved-432-cowork-tasks-to-a-new-claude-account-claude-code-deleted-13-of-my-transcripts-on-the-1d0i).

## What you get

`carryover export ~/carryover-archive` writes a folder you can browse in any editor:

```
INDEX.md                        start here: counts, warnings, links
manifest.json                   every file written (with source path), every file skipped and why
claude-code/
  PROJECTS.md                   one row per project folder, with `claude --resume` commands
  projects/<folder>/sessions/   condensed transcripts: your prompts and Claude's replies
  projects/<folder>/memory/     per-project memory
  global/                       ~/.claude/CLAUDE.md and your personal skills
cowork/<account>-<org>/
  SESSIONS.md                   every Cowork task, newest first
  sessions/                     condensed transcripts
  outputs/                      files each task produced, copied as-is
  projects/<name>/RESTORE.md    name, folders, instructions, memory, and a first-task prompt
  scheduled-tasks/TASKS.md      schedule, folders, last run, notes; prompts/ has every prompt
  memory/global/                Cowork's global memory
  artifacts/                    artifact registry and files
```

A `RESTORE.md` is built so that recreating a Project in the new account is four pastes: name, folders,
instructions, and a first message that tells Claude to read the old memory, check it against the current
state of the folders, and save only what still holds.

## Install

Python 3.9 or newer, standard library only.

```
pipx install carryover
# or, for the unreleased main branch
pipx install git+https://github.com/lizhuojunx86/carryover
# or from a clone
git clone https://github.com/lizhuojunx86/carryover && cd carryover && python3 -m pip install .
```

Without installing: `PYTHONPATH=src python3 -m carryover scan`.

## Use

```
carryover scan                       # inventory and warnings; writes nothing
carryover scan --json                # same, machine-readable
carryover export ~/carryover-archive # build the archive
```

| Option | Meaning |
|---|---|
| `--only claude-code` / `--only cowork` | limit to one product |
| `--no-outputs` | skip Cowork output files (they can be large) |
| `--max-file-mb N` | skip single output files larger than N MB |
| `--max-chars N` | truncate single messages longer than N characters (default 20000, 0 = never) |
| `--no-redact` | keep secret-looking strings in transcripts |
| `--claude-home`, `--cowork-root`, `--documents-claude` | read from somewhere other than the defaults |
| `--force` | write into a folder that is not empty |

Defaults: `$CLAUDE_CONFIG_DIR` or `~/.claude`; the Claude app folder (`~/Library/Application Support/Claude`
on macOS, `%APPDATA%\Claude` on Windows, `~/.config/Claude` on Linux); `~/Documents/Claude`.

## After the export

- **Claude Code, same machine**: nothing to move. History is not tied to the login, so the new account can
  `claude --resume` old sessions. Do set `"cleanupPeriodDays"` in `~/.claude/settings.json` to something
  long, or the 30-day cleanup keeps eating them.
- **Claude Code, new machine**: carryover gives you readable copies, not a working `~/.claude`.
  [claude-code-migrate](https://github.com/emreonal11/claude-code-migrate) moves the real thing.
- **Cowork Projects**: open each `RESTORE.md` and follow the four steps.
- **Scheduled tasks**: `TASKS.md` lists each task with its schedule and folders; copy the prompt from
  `prompts/` into the new task. If the new task needs to read the prompt from disk, keep it outside
  `~/Documents/Claude`.
- **Memory**: global memory is plain Markdown in `memory/global/`. Hand it to the new account in a first
  message, or import it with whatever memory tool you use.

## Safety

- Read-only. Source files are opened for reading only. The output folder must sit outside every source
  folder, and a non-empty output folder is refused unless you pass `--force`.
- Session metadata files also hold system prompts, connector configs with server URLs, and approval
  state. carryover reads 12 named fields from them (title, dates, folders, project id, account email and the like) and
  ignores everything else.
- Files named like credentials are never copied: `.env*`, `*.pem`, `*.key`, `id_rsa`, `credentials.json`,
  cookie stores and similar. `~/.claude.json` is never opened. `~/.claude/settings.json` is read only for
  `cleanupPeriodDays` and its top-level key names, and is never copied.
- Text that carryover writes (transcripts, memory, instructions, prompts) is masked for common secret
  formats: Anthropic, OpenAI, GitHub, AWS, Slack, Google and Stripe keys, JWTs, private key blocks,
  bearer tokens and `password=`-style assignments. Masking is a safety net. Read the archive before you
  share it with anyone.
- Output files are copied byte for byte and are not masked.

## What it does not carry

Logins and connector sign-ins, plugins, and anything that lived only in the cloud: claude.ai Project
documents, chat history, and cloud tasks with their run logs. For those, use the old account's data export
while you can still sign in.

## Status

v0.1.0. Tested on macOS with Python 3.9 and 3.13, and on Linux. Windows paths are in place but untested.
The Cowork layout is what desktop builds wrote through October 2026; it is not a documented format and
may change. Issues with a `carryover scan --json` output (remove anything private first) help a lot.

Related: [claude-cowork-export](https://github.com/PeriChu/claude-cowork-export) exports and re-imports single
Cowork tasks; [sessionport](https://github.com/Reality-Shifting-Tech/sessionport) hands a coding session from
one agent CLI to another.

Not affiliated with Anthropic. MIT licensed.
