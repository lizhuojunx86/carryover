"""Build a small, fully synthetic Claude workspace in a temp dir."""
from __future__ import annotations

import json
from pathlib import Path

ACCT = 'aaaaaaaa-1111-2222-3333-444444444444'
ORG = 'bbbbbbbb-5555-6666-7777-888888888888'
FAKE_ANTHROPIC = 'sk-ant-api03-' + 'A' * 40
FAKE_GITHUB = 'ghp_' + 'b' * 36


def _jsonl(p: Path, rows) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    with open(p, 'w', encoding='utf-8') as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + '\n')


def _json(p: Path, obj) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(obj, ensure_ascii=False, indent=1), encoding='utf-8')


def build(root: Path) -> dict:
    home = root / 'home'
    repo = home / 'dev' / 'demo-repo'
    repo.mkdir(parents=True)
    claude = home / '.claude'
    app = home / 'AppSupport' / 'Claude'
    lams = app / 'local-agent-mode-sessions'
    docs = home / 'Documents' / 'Claude'

    # ---- Claude Code
    proj = claude / 'projects' / '-home-dev-demo-repo'
    _jsonl(proj / '11111111-aaaa-bbbb-cccc-000000000001.jsonl', [
        {'type': 'user', 'cwd': str(repo), 'gitBranch': 'main', 'timestamp': '2026-09-01T10:00:00Z',
         'message': {'role': 'user', 'content': '<command-name>/clear</command-name>'}},
        {'type': 'user', 'cwd': str(repo), 'timestamp': '2026-09-01T10:01:00Z',
         'message': {'role': 'user', 'content': f'Add a retry to the fetcher. My key is {FAKE_ANTHROPIC}'}},
        {'type': 'assistant', 'timestamp': '2026-09-01T10:02:00Z',
         'message': {'content': [{'type': 'text', 'text': 'Added exponential backoff.'},
                                 {'type': 'tool_use', 'name': 'Edit', 'input': {}}]}},
        {'type': 'assistant', 'timestamp': '2026-09-01T10:02:05Z',
         'message': {'content': [{'type': 'text', 'text': 'Tests pass.'}]}},
        {'type': 'user', 'isSidechain': True, 'timestamp': '2026-09-01T10:03:00Z',
         'message': {'content': 'subagent chatter'}},
        {'type': 'ai-title', 'aiTitle': 'Fetcher retry'},
    ])
    (proj / 'memory').mkdir(parents=True)
    (proj / 'memory' / 'MEMORY.md').write_text('- [build](build.md)\n', encoding='utf-8')
    (proj / 'memory' / 'build.md').write_text('---\nname: build\n---\nRun make test.\n', encoding='utf-8')
    gone = claude / 'projects' / '-home-old-gone'
    _jsonl(gone / '22222222-aaaa-bbbb-cccc-000000000002.jsonl', [
        {'type': 'user', 'cwd': str(home / 'old' / 'gone'), 'timestamp': '2026-05-01T08:00:00Z',
         'message': {'content': 'hello'}}])
    (claude / 'CLAUDE.md').write_text('Answer briefly.\n', encoding='utf-8')
    _json(claude / 'settings.json', {'env': {'OPENAI_API_KEY': 'sk-should-never-be-copied'}, 'hooks': {}})
    (claude / '.credentials.json').write_text('{"token": "never"}', encoding='utf-8')
    (claude / 'skills' / 'tidy').mkdir(parents=True)
    (claude / 'skills' / 'tidy' / 'SKILL.md').write_text('---\nname: tidy\n---\nTidy up.\n', encoding='utf-8')

    # ---- Cowork
    org = lams / ACCT / ORG
    sid = 'local_cccccccc-0000-0000-0000-000000000001'
    _json(org / f'{sid}.json', {
        'sessionId': sid, 'title': 'Weekly report', 'createdAt': 1788000000000, 'lastActivityAt': 1788003600000,
        'spaceId': 'space-1', 'userSelectedFolders': [str(repo)], 'model': 'claude-test', 'emailAddress': 'old@example.com',
        'systemPrompt': 'SECRET SYSTEM PROMPT', 'initialMessage': 'Make the weekly report',
        'remoteMcpServersConfig': [{'name': 'crm', 'url': 'https://mcp.example.com', 'headers': {'Authorization': 'Bearer ' + 'z' * 30}}],
    })
    _jsonl(org / sid / 'audit.jsonl', [
        {'type': 'system', 'subtype': 'init'},
        {'type': 'user', 'timestamp': '2026-09-02T09:00:00Z', 'message': {'content': [{'type': 'text', 'text': 'Make the weekly report'}]}},
        {'type': 'assistant', 'timestamp': '2026-09-02T09:00:10Z', 'message': {'content': [{'type': 'text', 'text': f'Done. Token {FAKE_GITHUB} found in config.'}]}},
        {'type': 'assistant', 'parent_tool_use_id': 'x', 'message': {'content': [{'type': 'text', 'text': 'nested agent text'}]}},
        {'type': 'user', 'isReplay': True, 'message': {'content': 'replayed'}},
        {'type': 'result', 'timestamp': '2026-09-02T09:01:00Z', 'result': 'Report saved to outputs/report.md'},
    ])
    (org / sid / 'outputs').mkdir(parents=True)
    (org / sid / 'outputs' / 'report.md').write_text('# Report\npassword = hunter22hunter\n', encoding='utf-8')
    (org / sid / 'outputs' / '.env').write_text('API_KEY=nope\n', encoding='utf-8')
    (org / sid / 'outputs' / 'server.pem').write_text('-----BEGIN PRIVATE KEY-----\nabc\n-----END PRIVATE KEY-----\n')

    sid2 = 'local_cccccccc-0000-0000-0000-000000000002'
    _json(org / 'agent' / f'{sid2}.json', {'sessionId': sid2, 'title': '', 'initialMessage': 'Morning brief run',
                                            'createdAt': 1788100000000, 'sessionType': 'scheduled',
                                            'scheduledTaskId': 'morning-brief'})
    _jsonl(org / 'agent' / sid2 / 'audit.jsonl', [
        {'type': 'assistant', 'timestamp': '2026-09-03T06:00:00Z', 'message': {'content': [{'type': 'text', 'text': 'Brief ready.'}]}}])

    _json(org / 'spaces.json', {'spaces': [
        {'id': 'space-1', 'name': 'Reports', 'folders': [{'path': str(repo)}, {'path': str(home / 'gone-folder')}],
         'instructions': 'Write in plain English.', 'createdAt': 1787000000000, 'updatedAt': 1787500000000},
        {'id': 'space-2', 'name': 'Empty project', 'folders': [], 'instructions': ''},
    ]})
    (org / 'spaces' / 'space-1' / 'memory').mkdir(parents=True)
    (org / 'spaces' / 'space-1' / 'memory' / 'MEMORY.md').write_text('- style: short\n', encoding='utf-8')
    (org / 'agent' / 'memory').mkdir(parents=True)
    (org / 'agent' / 'memory' / 'user.md').write_text('Prefers tables.\n', encoding='utf-8')

    prompt_dir = docs / 'Scheduled' / 'morning-brief'
    prompt_dir.mkdir(parents=True)
    (prompt_dir / 'SKILL.md').write_text('Summarize my calendar.\n', encoding='utf-8')
    (docs / 'Scheduled' / 'old-task').mkdir(parents=True)
    (docs / 'Scheduled' / 'old-task' / 'SKILL.md').write_text('An orphan prompt.\n', encoding='utf-8')
    _json(org / 'scheduled-tasks.json', {'scheduledTasks': [
        {'id': 'morning-brief', 'cronExpression': '0 7 * * 1-5', 'enabled': True,
         'filePath': str(prompt_dir / 'SKILL.md'), 'userSelectedFolders': [str(repo)], 'createdAt': 1787000000000,
         'approvedPermissions': ['secret-ish'], 'migratedToRemote': {'triggerId': 'trig_test123'}},
        {'id': 'no-prompt', 'fireAt': '2026-11-01T12:00:00Z', 'enabled': False,
         'filePath': str(docs / 'Scheduled' / 'no-prompt' / 'SKILL.md')},
    ]})
    _json(org / 'artifacts.json', [{'id': 'status-page', 'name': 'Status', 'description': 'Weekly status',
                                     'updatedAt': 1788000000000, 'versions': [1, 2]}])
    (docs / 'Artifacts' / 'status-page').mkdir(parents=True)
    (docs / 'Artifacts' / 'status-page' / 'index.html').write_text('<h1>Status</h1>', encoding='utf-8')

    return {'home': home, 'claude': claude, 'lams': lams, 'docs': docs, 'repo': repo, 'org': org}
