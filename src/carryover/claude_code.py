"""Claude Code: ~/.claude/projects/<encoded-path>/*.jsonl, per-project memory, global CLAUDE.md, skills.

Claude Code data is not tied to a login. A new account on the same machine can
`claude --resume` old sessions as-is; the export here is for reading, search and
moving to another machine without dragging along settings or credentials.
"""
from __future__ import annotations

import collections
import os
from dataclasses import dataclass, field
from pathlib import Path

from .util import iter_jsonl, one_line, read_json, text_of, clip, iso, slug, Writer, md_cell

NOISE_PREFIXES = ('<command-', '<local-command', '<system-reminder', 'Caveat:', '<task-notification',
                  '<user-prompt-submit-hook', '<bash-input', '<bash-stdout', '<bash-stderr')


def _is_noise(t: str) -> bool:
    t = (t or '').lstrip()
    return (not t) or t.startswith(NOISE_PREFIXES)


@dataclass
class CCSession:
    path: Path
    id: str
    cwd: str = ''
    branch: str = ''
    title: str = ''
    first_prompt: str = ''
    first_ts: str = ''
    last_ts: str = ''
    bytes: int = 0


@dataclass
class CCProject:
    dir_name: str
    path: Path
    cwd: str = ''
    sessions: list = field(default_factory=list)
    memory: list = field(default_factory=list)

    @property
    def last_activity(self) -> str:
        return max([s.last_ts for s in self.sessions] + [''])


def _head_tail(p: Path, head_n: int = 300, tail_bytes: int = 1_500_000):
    head = []
    with open(p, 'rb') as f:
        for i, line in enumerate(f):
            if i >= head_n:
                break
            head.append(line)
        size = os.fstat(f.fileno()).st_size
        f.seek(max(0, size - tail_bytes))
        tail = f.read().splitlines()
        if size > tail_bytes:
            tail = tail[1:]
    import json
    out = []
    for chunk in (head, tail):
        rows = []
        for line in chunk:
            try:
                rows.append(json.loads(line))
            except ValueError:
                pass
        out.append(rows)
    return out


def scan_session(p: Path) -> CCSession:
    s = CCSession(path=p, id=p.stem, bytes=p.stat().st_size)
    head, tail = _head_tail(p)
    for d in head:
        s.cwd = s.cwd or d.get('cwd') or ''
        s.branch = s.branch or d.get('gitBranch') or ''
        s.first_ts = s.first_ts or d.get('timestamp') or ''
        if not s.first_prompt and d.get('type') == 'user' and not d.get('isMeta') and not d.get('isSidechain'):
            t = text_of((d.get('message') or {}).get('content'))
            if not _is_noise(t):
                s.first_prompt = one_line(t, 200)
    title = summary = ''
    for d in tail:
        ty = d.get('type')
        s.last_ts = d.get('timestamp') or s.last_ts
        if ty == 'custom-title':
            title = d.get('customTitle') or title
        elif ty == 'ai-title' and not title:
            title = d.get('aiTitle') or d.get('title') or title
        elif ty == 'summary':
            summary = d.get('summary') or summary
        s.cwd = s.cwd or d.get('cwd') or ''
    s.title = one_line(title or summary or s.first_prompt or '(untitled)', 120)
    s.first_ts, s.last_ts = iso(s.first_ts), iso(s.last_ts)
    return s


def scan(claude_home: Path) -> list[CCProject]:
    pdir = claude_home / 'projects'
    if not pdir.is_dir():
        return []
    projects = []
    for d in sorted(pdir.iterdir()):
        if not d.is_dir():
            continue
        proj = CCProject(dir_name=d.name, path=d)
        for f in sorted(d.glob('*.jsonl')):
            try:
                proj.sessions.append(scan_session(f))
            except OSError:
                continue
        proj.sessions.sort(key=lambda s: s.last_ts, reverse=True)
        proj.memory = sorted((d / 'memory').glob('*.md')) if (d / 'memory').is_dir() else []
        cwds = [s.cwd for s in proj.sessions if s.cwd]
        proj.cwd = collections.Counter(cwds).most_common(1)[0][0] if cwds else ''
        if proj.sessions or proj.memory:
            projects.append(proj)
    return projects


DEFAULT_CLEANUP_DAYS = 30


def retention(claude_home: Path, projects: list[CCProject], now: float | None = None) -> dict:
    """Claude Code deletes local transcripts older than cleanupPeriodDays (default 30) when it starts.

    Sessions started or last continued from Claude Desktop / Cowork are exempt by default; we cannot
    tell those apart from disk, so counts here are an upper bound.
    """
    import time
    now = now or time.time()
    settings = read_json(claude_home / 'settings.json', {}) or {}
    raw = settings.get('cleanupPeriodDays') if isinstance(settings, dict) else None
    period = raw if isinstance(raw, (int, float)) and raw > 0 else DEFAULT_CLEANUP_DAYS
    over = soon = 0
    for p in projects:
        for s in p.sessions:
            try:
                age = (now - s.path.stat().st_mtime) / 86400
            except OSError:
                continue
            if age > period:
                over += 1
            elif age > period - 7:
                soon += 1
    return {'cleanupPeriodDays': raw, 'effective_days': period, 'older_than_period': over, 'due_within_7_days': soon}


def render_session(s: CCSession, max_chars: int) -> tuple[str, int]:
    lines = [f'# {s.title}', '',
             f'- Session: `{s.id}`',
             f'- Folder: `{s.cwd or "?"}`' + (f' (branch `{s.branch}`)' if s.branch else ''),
             f'- First / last activity: {s.first_ts} / {s.last_ts}',
             f'- Resume on the original machine: `cd "{s.cwd}" && claude --resume {s.id}`' if s.cwd else '',
             '', '---', '']
    n = 0
    last_role = None
    for d in iter_jsonl(s.path):
        ty = d.get('type')
        if ty not in ('user', 'assistant') or d.get('isSidechain') or d.get('isMeta'):
            continue
        t = text_of((d.get('message') or {}).get('content')).strip()
        if not t or (ty == 'user' and _is_noise(t)):
            continue
        role = 'User' if ty == 'user' else 'Claude'
        if role == last_role == 'Claude':
            lines += [clip(t, max_chars), '']
        else:
            lines += [f'## {role} · {iso(d.get("timestamp"))}', '', clip(t, max_chars), '']
            n += 1
        last_role = role
    return '\n'.join(lines), n


def _project_dirname(p: CCProject) -> str:
    if not p.cwd:
        return slug(p.dir_name, 80)
    home = str(Path.home())
    rel = p.cwd[len(home):] if p.cwd == home or p.cwd.startswith(home + os.sep) else p.cwd
    return slug(rel.strip('/\\').replace('/', '_').replace('\\', '_') or 'home', 80)


def export(claude_home: Path, w: Writer, projects: list[CCProject], max_chars: int) -> dict:
    stats = {'projects': 0, 'sessions': 0, 'memory': 0}
    rows = []
    for p in projects:
        base = f'claude-code/projects/{_project_dirname(p)}'
        for s in p.sessions:
            md, _ = render_session(s, max_chars)
            w.text(f'{base}/sessions/{(s.first_ts or "0000-00-00")[:10]}_{slug(s.title)}__{s.id[:8]}.md', md,
                   source=str(s.path))
            stats['sessions'] += 1
        for m in p.memory:
            if w.copy_text(f'{base}/memory/{m.name}', m):
                stats['memory'] += 1
        stats['projects'] += 1
        rows.append((p, base))
    # global instructions and personal skills (settings.json is deliberately not copied)
    g = claude_home / 'CLAUDE.md'
    if g.is_file():
        w.copy_text('claude-code/global/CLAUDE.md', g)
    skills = claude_home / 'skills'
    n_sk = 0
    if skills.is_dir():
        for f in sorted(skills.rglob('*')):
            if f.is_file() and not any(part.startswith('.') for part in f.relative_to(skills).parts):
                if f.suffix.lower() in ('.md', '.txt', '.py', '.sh', '.js', '.ts', '.json', '.yaml', '.yml'):
                    if w.copy_text(f'claude-code/global/skills/{f.relative_to(skills).as_posix()}', f):
                        n_sk += 1
    stats['skill_files'] = n_sk
    settings = read_json(claude_home / 'settings.json', {}) or {}
    stats['settings_keys'] = sorted(settings.keys()) if isinstance(settings, dict) else []

    idx = ['# Claude Code projects', '',
           'Sessions are condensed: your prompts and Claude\'s replies, no tool calls. '
           'The originals stay in `~/.claude/projects/` and still work with `claude --resume`.', '',
           '| Project folder | Sessions | Memory | Last activity | Export |', '|---|---|---|---|---|']
    for p, base in sorted(rows, key=lambda r: r[0].last_activity, reverse=True):
        exists = '' if (not p.cwd or Path(p.cwd).exists()) else ' ⚠ missing'
        idx.append(f'| `{md_cell(p.cwd or p.dir_name)}`{exists} | {len(p.sessions)} | {len(p.memory)} | '
                   f'{p.last_activity} | [{base.split("/")[-1]}]({base.split("/", 1)[1]}/) |')
    if stats['settings_keys']:
        idx += ['', f'`settings.json` was not copied (it can hold env vars with keys). Top-level keys found: '
                    f'{", ".join(stats["settings_keys"])}. Re-apply what you need by hand.']
    w.text('claude-code/PROJECTS.md', '\n'.join(idx) + '\n')
    return stats
