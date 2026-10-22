"""Scan summary (terminal / JSON) and the top-level INDEX.md."""
from __future__ import annotations

import datetime as _dt
from pathlib import Path

from . import __version__
from .cowork import space_dirname
from .util import md_cell


def _home(p) -> str:
    s = str(p)
    h = str(Path.home())
    return '~' + s[len(h):] if s.startswith(h) else s


def flags(cc_projects, orgs, orphans, documents_claude: Path, ret: dict | None = None) -> list[str]:
    out = []
    if ret and (ret['older_than_period'] or ret['due_within_7_days']):
        how = ('is not set, so the 30-day default applies' if ret['cleanupPeriodDays'] is None
               else f'is {ret["cleanupPeriodDays"]}')
        out.append(f'Claude Code deletes local transcripts older than {ret["effective_days"]} days each time it starts '
                   f'(cleanupPeriodDays {how}). {ret["older_than_period"]} session(s) are already past that and '
                   f'{ret["due_within_7_days"]} more will be within a week. Run `export` now, and raise '
                   'cleanupPeriodDays in ~/.claude/settings.json if you want to keep them resumable. '
                   '(Sessions from Claude Desktop/Cowork are exempt by default, so this may overcount.)')
    miss = [p.cwd for p in cc_projects if p.cwd and not Path(p.cwd).exists()]
    if miss:
        out.append(f'{len(miss)} Claude Code project folder(s) no longer exist: ' + ', '.join(_home(m) for m in miss[:5])
                   + (' …' if len(miss) > 5 else ''))
    for o in orgs:
        sp_miss = sorted({f for sp in o.spaces for f in sp['folders'] if f and not Path(f).exists()})
        if sp_miss:
            out.append(f'[{o.label}] {len(sp_miss)} project folder(s) not found: '
                       + ', '.join(_home(m) for m in sp_miss[:5]) + (' …' if len(sp_miss) > 5 else ''))
        in_docs = [t for t in o.tasks if str(t['prompt_path']).startswith(str(documents_claude))]
        if in_docs:
            out.append(f'[{o.label}] {len(in_docs)} scheduled-task prompt(s) live under {_home(documents_claude)}. '
                       'Cowork treats that folder as its own, so tasks you rebuild cannot read prompts from there. '
                       '`export` copies them out.')
        mig = [t for t in o.tasks if t.get('migrated_trigger')]
        if mig:
            out.append(f'[{o.label}] {len(mig)} task(s) were already moved to the cloud by the app; '
                       'those cloud copies stay with the old account.')
        missing = [t for t in o.tasks if not t['prompt_path'].is_file()]
        if missing:
            out.append(f'[{o.label}] {len(missing)} task(s) have no prompt file on disk.')
    if orphans:
        out.append(f'{len(orphans)} prompt folder(s) under {_home(documents_claude / "Scheduled")} are not in any '
                   'task registry (deleted or from another install).')
    return out


def summary_dict(src, cc_projects, orgs, orphans, ret: dict | None = None) -> dict:
    empty = [o for o in orgs if not (o.sessions or o.spaces or o.tasks or o.artifacts or o.global_memory)]
    orgs = [o for o in orgs if o not in empty]
    return {
        'version': __version__,
        'claude_code': {
            'root': str(src.claude_home),
            'projects': len(cc_projects),
            'sessions': sum(len(p.sessions) for p in cc_projects),
            'memory_files': sum(len(p.memory) for p in cc_projects),
            'retention': ret,
        },
        'cowork': {
            'root': str(src.cowork_root),
            'orgs': [{
                'account_id': o.account_id, 'org_id': o.org_id, 'email': o.email,
                'sessions': len(o.sessions), 'last_activity': o.last_activity,
                'projects': [{'name': sp['name'], 'folders': sp['folders'], 'memory_files': len(sp['memory']),
                              'has_instructions': bool(sp['instructions'].strip()), 'sessions': sp['n_sessions']}
                             for sp in o.spaces],
                'scheduled_tasks': len(o.tasks),
                'scheduled_tasks_enabled': sum(1 for t in o.tasks if t.get('enabled')),
                'artifacts': len(o.artifacts),
                'global_memory_files': len(o.global_memory),
            } for o in orgs],
            'unregistered_task_prompts': len(orphans),
            'empty_org_folders': len(empty),
        },
        'flags': flags(cc_projects, orgs, orphans, src.documents_claude, ret),
    }


def summary_text(d: dict) -> str:
    cc = d['claude_code']
    lines = [f'carryover {d["version"]} · read-only scan', '',
             f'Claude Code  {_home(cc["root"])}',
             f'  {cc["projects"]} projects · {cc["sessions"]} sessions · {cc["memory_files"]} memory files', '',
             f'Cowork  {_home(d["cowork"]["root"])}']
    if not d['cowork']['orgs']:
        lines.append('  (no local Cowork data found)')
    if d['cowork'].get('empty_org_folders'):
        lines.append(f'  ({d["cowork"]["empty_org_folders"]} empty account/org folder(s) not shown)')
    for o in d['cowork']['orgs']:
        lines.append(f'  account {o["account_id"][:8]} / org {o["org_id"][:8]}' + (f'  ({o["email"]})' if o['email'] else ''))
        lines.append(f'    {o["sessions"]} sessions (last {o["last_activity"] or "—"}) · {len(o["projects"])} projects · '
                     f'{o["scheduled_tasks"]} scheduled tasks ({o["scheduled_tasks_enabled"]} enabled) · '
                     f'{o["artifacts"]} artifacts · {o["global_memory_files"]} global memory files')
        for p in o['projects']:
            lines.append(f'      - {p["name"]}: {len(p["folders"])} folder(s), {p["memory_files"]} memory, '
                         f'{"instructions" if p["has_instructions"] else "no instructions"}, {p["sessions"]} tasks')
    if d['flags']:
        lines += ['', 'Check before you switch:'] + [f'  ! {f}' for f in d['flags']]
    lines += ['', 'Nothing was written. Run `carryover export <folder>` to build the archive.']
    return '\n'.join(lines)


NOT_CARRIED = """## What this archive does not carry

- Logins: connector sign-ins (Gmail, Drive, Slack…), API keys, cookies. Reconnect them in the new account.
- `~/.claude.json` and `~/.claude/settings.json`. They can hold tokens and env vars, so they are left alone.
- Anything that lived only in the cloud: claude.ai Project documents, chat history, cloud tasks and their
  run logs. Use the old account's data export for those (Settings → Privacy → Export data), if you still
  can sign in.
- Plugins and connectors. Reinstall them; the session files show which ones you used.
"""


def index_md(src, d: dict, cc_stats, cw_stats, orgs, manifest: dict, out: Path) -> str:
    now = _dt.datetime.now().strftime('%Y-%m-%d %H:%M')
    L = [f'# carryover archive', '',
         f'Built {now} by carryover {d["version"]}. Sources were only read.', '',
         '| Source | Path |', '|---|---|',
         f'| Claude Code | `{_home(src.claude_home)}` |',
         f'| Cowork (local) | `{_home(src.cowork_root)}` |',
         f'| Cowork prompts & artifacts | `{_home(src.documents_claude)}` |', '']
    if cc_stats is not None:
        L += ['## Claude Code', '',
              f'{cc_stats["projects"]} projects, {cc_stats["sessions"]} sessions, {cc_stats["memory"]} memory files, '
              f'{cc_stats.get("skill_files", 0)} skill files. → [claude-code/PROJECTS.md](claude-code/PROJECTS.md)', '',
              'Claude Code history is not tied to your login: on the same machine a new account can '
              '`claude --resume` old sessions directly.', '']
    if cw_stats is not None:
        L += ['## Cowork', '']
        if not orgs:
            L.append('No local Cowork data found.')
        for o in orgs:
            base = f'cowork/{o.label}'
            L += [f'### {o.email or o.label}', '',
                  f'- Sessions: {len(o.sessions)} (last {o.last_activity or "—"}) → [{base}/SESSIONS.md]({base}/SESSIONS.md)']
            if o.tasks:
                L.append(f'- Scheduled tasks: {len(o.tasks)} → [{base}/scheduled-tasks/TASKS.md]({base}/scheduled-tasks/TASKS.md)')
            if o.artifacts:
                L.append(f'- Artifacts: {len(o.artifacts)} → [{base}/artifacts/ARTIFACTS.md]({base}/artifacts/ARTIFACTS.md)')
            if o.global_memory:
                L.append(f'- Global memory: {len(o.global_memory)} files in `{base}/memory/global/`')
            if o.spaces:
                L += ['', '| Project | Tasks | Last | Memory | Restore pack |', '|---|---|---|---|---|']
                for sp in sorted(o.spaces, key=lambda s: s['last'], reverse=True):
                    pd = f'{base}/projects/{space_dirname(o, sp)}'
                    L.append(f'| {md_cell(sp["name"])} | {sp["n_sessions"]} | {sp["last"] or "—"} | {len(sp["memory"])} | '
                             f'[RESTORE.md]({pd}/RESTORE.md) |')
            L.append('')
    if d['flags']:
        L += ['## Check before you switch', ''] + [f'- {f}' for f in d['flags']] + ['']
    L += [NOT_CARRIED, '## Before you share this folder', '',
          f'Transcripts can contain personal data. carryover masked {sum(manifest["redactions"].values())} '
          f'secret-looking strings and skipped {len(manifest["skipped"])} credential-like files '
          '(see `manifest.json`). Masking catches common key formats only; read before you share.', '']
    return '\n'.join(L)
