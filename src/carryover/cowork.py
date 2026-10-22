"""Claude desktop Cowork (local mode) data.

Layout, as observed on macOS desktop builds through 2026:

  <app dir>/local-agent-mode-sessions/<accountId>/<orgId>/
      local_<id>.json            session metadata (also under agent/)
      local_<id>/audit.jsonl     the transcript
      local_<id>/outputs/        files the session produced
      spaces.json                Projects: name, folders, instructions
      spaces/<spaceId>/memory/   per-project memory (*.md)
      agent/memory/              global memory (*.md)
      scheduled-tasks.json       scheduled task registry
      artifacts.json             artifact registry
  ~/Documents/Claude/Scheduled/<taskId>/SKILL.md   task prompts
  ~/Documents/Claude/Artifacts/<artifactId>/       artifact files

Session metadata also carries system prompts, connector configs and approval
state. Only the whitelisted fields below are ever read into the export.
"""
from __future__ import annotations

import collections
from dataclasses import dataclass, field
from pathlib import Path

from .util import iso, iter_jsonl, md_cell, one_line, read_json, slug, text_of, clip, Writer

SESSION_FIELDS = ('sessionId', 'title', 'createdAt', 'lastActivityAt', 'sessionType', 'scheduledTaskId',
                  'spaceId', 'userSelectedFolders', 'model', 'isArchived', 'initialMessage')
TASK_FIELDS = ('id', 'displayName', 'cronExpression', 'fireAt', 'enabled', 'userSelectedFolders', 'createdAt',
               'lastRunAt', 'model', 'permissionMode', 'filePath')


@dataclass
class Org:
    account_id: str
    org_id: str
    path: Path
    email: str = ''
    sessions: list = field(default_factory=list)
    spaces: list = field(default_factory=list)
    tasks: list = field(default_factory=list)
    artifacts: list = field(default_factory=list)
    global_memory: list = field(default_factory=list)

    @property
    def label(self) -> str:
        return f'{self.account_id[:8]}-{self.org_id[:8]}'

    @property
    def last_activity(self) -> str:
        return max([s['last'] for s in self.sessions] + [''])


def _is_org_dir(p: Path) -> bool:
    return (p / 'spaces.json').exists() or (p / 'scheduled-tasks.json').exists() or any(p.glob('local_*.json'))


def find_orgs(root: Path) -> list[Path]:
    out = []
    if not root.is_dir():
        return out
    for acct in sorted(root.iterdir()):
        if not acct.is_dir():
            continue
        for org in sorted(acct.iterdir()):
            if org.is_dir() and _is_org_dir(org):
                out.append(org)
    return out


def _meta_files(org: Path) -> list[Path]:
    return sorted(list(org.glob('local_*.json')) + list((org / 'agent').glob('local_*.json')))


def scan_org(org_path: Path, documents_claude: Path) -> Org:
    org = Org(account_id=org_path.parent.name, org_id=org_path.name, path=org_path)
    emails = collections.Counter()
    for mp in _meta_files(org_path):
        raw = read_json(mp, {}) or {}
        if not isinstance(raw, dict):
            continue
        if raw.get('emailAddress'):
            emails[raw['emailAddress']] += 1
        m = {k: raw.get(k) for k in SESSION_FIELDS}
        m['_meta'] = mp
        m['_dir'] = mp.with_suffix('')
        m['created'] = iso(m.get('createdAt'))
        m['last'] = iso(m.get('lastActivityAt') or m.get('createdAt'))
        m['title'] = m.get('title') or one_line(m.get('initialMessage') or '', 60) or '(untitled)'
        org.sessions.append(m)
        del raw
    org.sessions.sort(key=lambda s: s['last'], reverse=True)
    org.email = emails.most_common(1)[0][0] if emails else ''

    spaces = (read_json(org_path / 'spaces.json', {}) or {}).get('spaces') or []
    counts = collections.Counter(s.get('spaceId') for s in org.sessions)
    last = {}
    for s in org.sessions:
        last.setdefault(s.get('spaceId'), s['last'])
    for sp in spaces:
        if not isinstance(sp, dict):
            continue
        mem_dir = org_path / 'spaces' / str(sp.get('id')) / 'memory'
        org.spaces.append({
            'id': sp.get('id'), 'name': sp.get('name') or sp.get('id'),
            'folders': [f.get('path') if isinstance(f, dict) else str(f) for f in (sp.get('folders') or [])],
            'instructions': sp.get('instructions') or '',
            'created': iso(sp.get('createdAt')), 'updated': iso(sp.get('updatedAt')),
            'memory': sorted(mem_dir.glob('*.md')) if mem_dir.is_dir() else [],
            'n_sessions': counts.get(sp.get('id'), 0), 'last': last.get(sp.get('id'), ''),
        })

    gm = org_path / 'agent' / 'memory'
    org.global_memory = sorted(gm.glob('*.md')) if gm.is_dir() else []

    reg = read_json(org_path / 'scheduled-tasks.json', {}) or {}
    for t in reg.get('scheduledTasks') or []:
        if not isinstance(t, dict) or not t.get('id'):
            continue
        task = {k: t.get(k) for k in TASK_FIELDS}
        task['prompt_path'] = Path(t.get('filePath') or documents_claude / 'Scheduled' / t['id'] / 'SKILL.md')
        mig = t.get('migratedToRemote')
        task['migrated_trigger'] = mig.get('triggerId') if isinstance(mig, dict) else None
        task['runs'] = sum(1 for s in org.sessions if s.get('scheduledTaskId') == t['id'])
        org.tasks.append(task)

    arts = read_json(org_path / 'artifacts.json', []) or []
    for a in arts if isinstance(arts, list) else []:
        if isinstance(a, dict) and a.get('id'):
            org.artifacts.append({'id': a['id'], 'name': a.get('name') or a['id'],
                                  'description': a.get('description') or '',
                                  'updated': iso(a.get('updatedAt') or a.get('createdAt')),
                                  'n_versions': len(a.get('versions') or []),
                                  'dir': documents_claude / 'Artifacts' / a['id']})
    return org


def scan(cowork_root: Path, documents_claude: Path) -> list[Org]:
    return [scan_org(p, documents_claude) for p in find_orgs(cowork_root)]


def orphan_prompts(orgs: list[Org], documents_claude: Path) -> list[Path]:
    """Prompt folders under ~/Documents/Claude/Scheduled that no registry points at."""
    base = documents_claude / 'Scheduled'
    if not base.is_dir():
        return []
    known = {t['prompt_path'].parent.resolve() for o in orgs for t in o.tasks}
    return [d / 'SKILL.md' for d in sorted(base.iterdir())
            if (d / 'SKILL.md').is_file() and d.resolve() not in known]


# ---------------------------------------------------------------- rendering
def render_session(s: dict, space_names: dict, max_chars: int) -> tuple[str, int]:
    folders = ', '.join(f'`{f}`' for f in (s.get('userSelectedFolders') or [])) or '—'
    kind = s.get('sessionType') or 'interactive'
    if s.get('scheduledTaskId'):
        kind += f' (scheduled task `{s["scheduledTaskId"]}`)'
    lines = [f'# {s["title"]}', '',
             f'- Session: `{s.get("sessionId")}`',
             f'- Created / last activity: {s["created"]} / {s["last"]}',
             f'- Type: {kind}',
             f'- Project: {space_names.get(s.get("spaceId"), "—")}',
             f'- Folders: {folders}',
             f'- Model: {s.get("model") or "?"}' + ('  · archived' if s.get('isArchived') else ''),
             '', '---', '']
    n, seen = 0, set()
    for e in iter_jsonl(s['_dir'] / 'audit.jsonl'):
        ty = e.get('type')
        if ty not in ('user', 'assistant', 'result') or e.get('isReplay') or e.get('parent_tool_use_id'):
            continue
        ts = iso(e.get('timestamp'))
        if ty == 'user':
            t = text_of((e.get('message') or {}).get('content')).strip()
            if t and t not in seen:
                seen.add(t)
                lines += [f'## User · {ts}', '', clip(t, max_chars), '']
                n += 1
        elif ty == 'assistant':
            t = text_of((e.get('message') or {}).get('content')).strip()
            if t:
                lines += [f'## Claude · {ts}', '', clip(t, max_chars), '']
                n += 1
        else:
            r = (e.get('result') or '').strip() if isinstance(e.get('result'), str) else ''
            if r and r not in seen:
                seen.add(r)
                lines += [f'### Turn result · {ts}', '', clip(r, max_chars), '']
    return '\n'.join(lines), n


SEED_PROMPT = """This project was moved over from another Claude account. Please set it up once:
1. Read the old project memory in: {mem}
   (MEMORY.md, if present, is the index.)
2. Read the CLAUDE.md and any status/handoff files in this project's folders and check the old memory
   against what is true now. Save what still holds to this project's memory. Do not carry over what is
   out of date; list it separately.
3. Do not change any files in the project folders and do not run git write commands.
4. When done, show me a table: what you saved, what you skipped, and why. Then remind me that I can
   remove the old-memory folder from the project."""


def _restore_pack(sp: dict, mem_abs: str | None) -> str:
    fl = []
    for f in sp['folders']:
        ok = Path(f).exists() if f else False
        fl.append(f'- `{f}`' + ('' if ok else '  ⚠ not found on this machine'))
    if mem_abs:
        fl.append(f'- `{mem_abs}`  (temporary: old memory, remove after step 4)')
    out = [f'# Restore: {sp["name"]}', '',
           f'Old project id `{sp["id"]}` · created {sp["created"] or "—"} · updated {sp["updated"] or "—"} · '
           f'{sp["n_sessions"]} tasks, last {sp["last"] or "—"}', '',
           '## 1. Name', '', '```text', sp['name'], '```', '',
           '## 2. Folders', ''] + (fl or ['- (none)']) + ['',
           '## 3. Instructions', '']
    out += (['```text', sp['instructions'], '```'] if sp['instructions'].strip() else ['(none set)'])
    out += ['', f'## 4. Memory ({len(sp["memory"])} files, copied to `memory/`)', '']
    out += [f'- {m.name}' for m in sp['memory']] or ['(none)']
    if mem_abs:
        out += ['', '## 5. First task in the new project', '', 'Paste this as the first message:', '',
                '```text', SEED_PROMPT.format(mem=mem_abs), '```']
    return '\n'.join(out) + '\n'


def space_dirname(org: Org, sp: dict) -> str:
    """Folder name for a project's restore pack; unique within the org."""
    name = slug(sp['name'], 60)
    if sum(1 for o in org.spaces if slug(o['name'], 60) == name) > 1:
        name = f'{name}-{str(sp["id"])[:6]}'
    return name


def _cron_label(t: dict) -> str:
    if t.get('cronExpression'):
        return f'`{t["cronExpression"]}`'
    if t.get('fireAt'):
        return f'once at {iso(t["fireAt"])}'
    return 'manual'


def export(orgs: list[Org], orphans: list[Path], w: Writer, max_chars: int, outputs: bool) -> dict:
    stats = collections.Counter()
    out_abs = w.out.resolve()
    for org in orgs:
        base = f'cowork/{org.label}'
        names = {sp['id']: sp['name'] for sp in org.spaces}
        rows = []
        for s in org.sessions:
            sid = str(s.get('sessionId') or s['_meta'].stem)
            fname = f'{(s["created"] or "0000-00-00")[:10]}_{slug(s["title"])}__{sid.replace("local_", "")[:8]}'
            md, n = render_session(s, names, max_chars)
            n_out = 0
            od = s['_dir'] / 'outputs'
            if outputs and od.is_dir():
                n_out = w.copy_tree(f'{base}/outputs/{fname}', od)
                if n_out:
                    md += f'\n---\n\n{n_out} output file(s) copied to `../outputs/{fname}/`.\n'
            w.text(f'{base}/sessions/{fname}.md', md, source=str(s['_meta']))
            stats['sessions'] += 1
            stats['outputs'] += n_out
            rows.append((s, fname, n, n_out))

        idx = [f'# Cowork sessions · {org.email or org.label}', '',
               '| Last activity | Title | Project | Type | Msgs | Outputs |', '|---|---|---|---|---|---|']
        for s, fname, n, n_out in rows:
            kind = 'scheduled' if s.get('scheduledTaskId') else (s.get('sessionType') or 'interactive')
            idx.append(f'| {s["last"]} | [{md_cell(one_line(s["title"], 70))}](sessions/{fname}.md) | '
                       f'{md_cell(names.get(s.get("spaceId"), ""))} | {kind} | {n} | {n_out or ""} |')
        w.text(f'{base}/SESSIONS.md', '\n'.join(idx) + '\n')

        for sp in org.spaces:
            pdir = f'{base}/projects/{space_dirname(org, sp)}'
            for m in sp['memory']:
                w.copy_text(f'{pdir}/memory/{m.name}', m)
            mem_abs = str(out_abs / pdir / 'memory') if sp['memory'] else None
            w.text(f'{pdir}/RESTORE.md', _restore_pack(sp, mem_abs))
            stats['projects'] += 1
            stats['project_memory'] += len(sp['memory'])

        for m in org.global_memory:
            if w.copy_text(f'{base}/memory/global/{m.name}', m):
                stats['global_memory'] += 1

        if org.tasks:
            t_lines = [f'# Scheduled tasks · {org.email or org.label}', '',
                       'Recreate each one in the new account: same prompt, schedule and folders. '
                       'Schedules are shown as stored; check the time zone when you re-enter them.', '',
                       '| Task | Schedule | Enabled | Runs | Last run | Prompt | Note |',
                       '|---|---|---|---|---|---|---|']
            for t in org.tasks:
                note = []
                pp = t['prompt_path']
                prompt_rel = ''
                if pp.is_file():
                    prompt_rel = w.copy_text(f'{base}/scheduled-tasks/prompts/{slug(t["id"], 80)}.md', pp) or ''
                    stats['task_prompts'] += 1
                else:
                    note.append('prompt file missing')
                if t.get('migrated_trigger'):
                    note.append(f'already moved to cloud as `{t["migrated_trigger"]}`')
                for f in t.get('userSelectedFolders') or []:
                    if not Path(f).exists():
                        note.append(f'folder missing: `{f}`')
                link = f'[prompt](prompts/{Path(prompt_rel).name})' if prompt_rel else '—'
                t_lines.append(f'| {md_cell(t.get("displayName") or t["id"])} | {_cron_label(t)} | '
                               f'{"yes" if t.get("enabled") else "no"} | {t["runs"]} | {iso(t.get("lastRunAt"))} | '
                               f'{link} | {md_cell("; ".join(note))} |')
            t_lines += ['', '## Folders per task', '']
            for t in org.tasks:
                fl = ', '.join(f'`{f}`' for f in (t.get('userSelectedFolders') or [])) or '—'
                t_lines.append(f'- **{md_cell(t.get("displayName") or t["id"])}**: {fl}')
            w.text(f'{base}/scheduled-tasks/TASKS.md', '\n'.join(t_lines) + '\n')
            stats['tasks'] += len(org.tasks)

        if org.artifacts:
            a_lines = [f'# Artifacts · {org.email or org.label}', '', '| Artifact | Updated | Versions | Files |',
                       '|---|---|---|---|']
            for a in org.artifacts:
                n = w.copy_tree(f'{base}/artifacts/{slug(a["id"], 80)}', a['dir']) if a['dir'].is_dir() else 0
                stats['artifact_files'] += n
                a_lines.append(f'| {md_cell(a["name"])} — {md_cell(one_line(a["description"], 80))} | {a["updated"]} | '
                               f'{a["n_versions"]} | {n} |')
            w.text(f'{base}/artifacts/ARTIFACTS.md', '\n'.join(a_lines) + '\n')
            stats['artifacts'] += len(org.artifacts)

    for p in orphans:
        w.copy_text(f'cowork/unregistered-task-prompts/{slug(p.parent.name, 80)}.md', p)
        stats['orphan_prompts'] += 1
    return dict(stats)
