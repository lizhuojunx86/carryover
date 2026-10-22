import contextlib
import hashlib
import io
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from carryover import cli  # noqa: E402
from carryover.safety import is_denied_file, redact  # noqa: E402
import fixtures  # noqa: E402


def tree_digest(root: Path) -> dict:
    out = {}
    for cur, _dirs, files in os.walk(root):
        for fn in files:
            p = Path(cur) / fn
            st = p.stat()
            out[str(p)] = (hashlib.sha256(p.read_bytes()).hexdigest(), st.st_mtime_ns, st.st_size)
    return out


def all_text(root: Path) -> str:
    chunks = []
    for cur, _dirs, files in os.walk(root):
        for fn in files:
            chunks.append((Path(cur) / fn).read_text(encoding='utf-8', errors='replace'))
    return '\n'.join(chunks)


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.fx = fixtures.build(self.root)
        self.src_args = ['--claude-home', str(self.fx['claude']), '--cowork-root', str(self.fx['lams']),
                         '--documents-claude', str(self.fx['docs'])]

    def tearDown(self):
        self.tmp.cleanup()

    def run_cli(self, *args):
        buf_out, buf_err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(buf_out), contextlib.redirect_stderr(buf_err):
            code = cli.main(list(args))
        return code, buf_out.getvalue(), buf_err.getvalue()


class TestRedact(unittest.TestCase):
    def test_known_formats(self):
        c = {}
        s = redact(f'a {fixtures.FAKE_ANTHROPIC} b {fixtures.FAKE_GITHUB} AKIAABCDEFGHIJKLMNOP '
                   'Authorization: Bearer abcdefghijklmnopqrstuvwxyz api_key="0123456789abcdef"', c)
        self.assertNotIn('sk-ant-api03', s)
        self.assertNotIn('ghp_', s)
        self.assertNotIn('AKIA', s)
        self.assertNotIn('abcdefghijklmnopqrstuvwxyz', s)
        self.assertNotIn('0123456789abcdef', s)
        self.assertIn('api_key="[REDACTED]"', s)
        self.assertEqual(c['anthropic-key'], 1)

    def test_leaves_prose_alone(self):
        t = 'The password policy says eight characters. Bearer bonds are old.'
        self.assertEqual(redact(t), t)

    def test_deny_list(self):
        for n in ('.env', '.env.local', 'id_rsa', 'server.PEM', 'Cookies', 'credentials.json'):
            self.assertIsNotNone(is_denied_file(n), n)
        for n in ('report.md', 'environment.md', 'keynote.pdf'):
            self.assertIsNone(is_denied_file(n), n)


class TestScan(Base):
    def test_scan_counts_and_flags(self):
        code, out, _ = self.run_cli('scan', '--json', *self.src_args)
        self.assertEqual(code, 0)
        d = json.loads(out)
        self.assertEqual(d['claude_code']['projects'], 2)
        self.assertEqual(d['claude_code']['sessions'], 2)
        self.assertEqual(d['claude_code']['memory_files'], 2)
        org = d['cowork']['orgs'][0]
        self.assertEqual(org['sessions'], 2)
        self.assertEqual(org['email'], 'old@example.com')
        self.assertEqual(len(org['projects']), 2)
        self.assertEqual(org['scheduled_tasks'], 2)
        self.assertEqual(org['artifacts'], 1)
        self.assertEqual(d['cowork']['unregistered_task_prompts'], 1)
        flags = ' '.join(d['flags'])
        self.assertIn('no longer exist', flags)
        self.assertIn('not found', flags)
        self.assertIn('already moved to the cloud', flags)
        self.assertIn('no prompt file', flags)

    def test_retention_warning(self):
        import time
        old = time.time() - 40 * 86400
        for f in (self.fx['claude'] / 'projects').rglob('*.jsonl'):
            os.utime(f, (old, old))
        _, out, _ = self.run_cli('scan', '--json', *self.src_args)
        d = json.loads(out)
        self.assertEqual(d['claude_code']['retention']['older_than_period'], 2)
        self.assertIn('cleanupPeriodDays is not set', ' '.join(d['flags']))
        (self.fx['claude'] / 'settings.json').write_text('{"cleanupPeriodDays": 3650}')
        _, out, _ = self.run_cli('scan', '--json', *self.src_args)
        d = json.loads(out)
        self.assertEqual(d['claude_code']['retention']['older_than_period'], 0)
        self.assertNotIn('cleanupPeriodDays', ' '.join(d['flags']))

    def test_empty_org_hidden(self):
        (self.fx['lams'] / fixtures.ACCT / 'cccccccc-empty').mkdir()
        (self.fx['lams'] / fixtures.ACCT / 'cccccccc-empty' / 'scheduled-tasks.json').write_text('{"scheduledTasks": []}')
        _, out, _ = self.run_cli('scan', '--json', *self.src_args)
        d = json.loads(out)
        self.assertEqual(len(d['cowork']['orgs']), 1)
        self.assertEqual(d['cowork']['empty_org_folders'], 1)

    def test_scan_text_writes_nothing(self):
        before = tree_digest(self.root)
        code, out, _ = self.run_cli('scan', *self.src_args)
        self.assertEqual(code, 0)
        self.assertIn('Nothing was written', out)
        self.assertEqual(before, tree_digest(self.root))

    def test_missing_sources(self):
        code, out, _ = self.run_cli('scan', '--json', '--claude-home', str(self.root / 'nope'),
                                    '--cowork-root', str(self.root / 'nope2'), '--documents-claude', str(self.root / 'n3'))
        self.assertEqual(code, 0)
        d = json.loads(out)
        self.assertEqual(d['claude_code']['projects'], 0)
        self.assertEqual(d['cowork']['orgs'], [])


class TestExport(Base):
    def export(self, *extra):
        out = self.root / 'archive'
        code, stdout, err = self.run_cli('export', str(out), *self.src_args, *extra)
        self.assertEqual(code, 0, err)
        return out, stdout

    def test_sources_untouched(self):
        before = tree_digest(self.fx['home'])
        self.export()
        self.assertEqual(before, tree_digest(self.fx['home']))

    def test_layout(self):
        out, _ = self.export()
        self.assertTrue((out / 'INDEX.md').is_file())
        self.assertTrue((out / 'manifest.json').is_file())
        self.assertTrue((out / 'claude-code' / 'PROJECTS.md').is_file())
        self.assertTrue((out / 'claude-code' / 'global' / 'CLAUDE.md').is_file())
        self.assertTrue((out / 'claude-code' / 'global' / 'skills' / 'tidy' / 'SKILL.md').is_file())
        org = out / 'cowork' / f'{fixtures.ACCT[:8]}-{fixtures.ORG[:8]}'
        self.assertTrue((org / 'SESSIONS.md').is_file())
        self.assertEqual(len(list((org / 'sessions').glob('*.md'))), 2)
        self.assertTrue((org / 'projects' / 'Reports' / 'RESTORE.md').is_file())
        self.assertTrue((org / 'projects' / 'Reports' / 'memory' / 'MEMORY.md').is_file())
        self.assertTrue((org / 'projects' / 'Empty-project' / 'RESTORE.md').is_file())
        self.assertTrue((org / 'scheduled-tasks' / 'prompts' / 'morning-brief.md').is_file())
        self.assertTrue((org / 'memory' / 'global' / 'user.md').is_file())
        self.assertTrue((org / 'artifacts' / 'status-page' / 'index.html').is_file())
        self.assertTrue((out / 'cowork' / 'unregistered-task-prompts' / 'old-task.md').is_file())

    def test_transcripts_are_condensed(self):
        out, _ = self.export()
        cc = all_text(out / 'claude-code' / 'projects')
        self.assertIn('Add a retry to the fetcher', cc)
        self.assertIn('Added exponential backoff.', cc)
        self.assertIn('Tests pass.', cc)
        self.assertNotIn('/clear', cc)
        self.assertNotIn('subagent chatter', cc)
        self.assertIn('claude --resume 11111111-aaaa-bbbb-cccc-000000000001', cc)
        cw = all_text(out / 'cowork')
        self.assertIn('Make the weekly report', cw)
        self.assertIn('Report saved to outputs/report.md', cw)
        self.assertNotIn('nested agent text', cw)
        self.assertNotIn('replayed', cw)

    def test_no_secrets_or_private_metadata(self):
        out, _ = self.export()
        # everything carryover writes itself; session output files are copied as-is and checked below
        text = '\n'.join(p.read_text(encoding='utf-8', errors='replace') for p in out.rglob('*')
                         if p.is_file() and 'outputs' not in p.relative_to(out).parts)
        for needle in (fixtures.FAKE_ANTHROPIC, fixtures.FAKE_GITHUB, 'z' * 30, 'SECRET SYSTEM PROMPT',
                       'sk-should-never-be-copied', '"token": "never"', 'secret-ish', 'hunter22hunter'):
            self.assertNotIn(needle, text, needle)
        names = {p.name for p in out.rglob('*')}
        self.assertNotIn('.env', names)
        self.assertNotIn('server.pem', names)
        self.assertNotIn('settings.json', names)
        self.assertNotIn('.credentials.json', names)
        man = json.loads((out / 'manifest.json').read_text())
        reasons = {Path(s['source']).name for s in man['skipped']}
        self.assertEqual(reasons, {'.env', 'server.pem'})
        self.assertGreaterEqual(sum(man['redactions'].values()), 2)

    def test_output_files_are_copied_byte_for_byte_except_text_masks(self):
        out, _ = self.export('--no-redact')
        org = out / 'cowork' / f'{fixtures.ACCT[:8]}-{fixtures.ORG[:8]}'
        copied = list((org / 'outputs').rglob('report.md'))
        self.assertEqual(len(copied), 1)
        self.assertIn('hunter22hunter', copied[0].read_text())   # binary/output copies are not rewritten
        self.assertIn(fixtures.FAKE_ANTHROPIC, all_text(out / 'claude-code'))  # --no-redact really is off

    def test_restore_pack(self):
        out, _ = self.export()
        r = (out / 'cowork' / f'{fixtures.ACCT[:8]}-{fixtures.ORG[:8]}' / 'projects' / 'Reports' / 'RESTORE.md').read_text()
        self.assertIn('Write in plain English.', r)
        self.assertIn('not found on this machine', r)
        self.assertIn('First task in the new project', r)
        self.assertIn(str((out / 'cowork').resolve()), r)

    def test_tasks_md(self):
        out, _ = self.export()
        t = (out / 'cowork' / f'{fixtures.ACCT[:8]}-{fixtures.ORG[:8]}' / 'scheduled-tasks' / 'TASKS.md').read_text()
        self.assertIn('`0 7 * * 1-5`', t)
        self.assertIn('trig_test123', t)
        self.assertIn('prompt file missing', t)
        self.assertIn('once at 2026-11-01 12:00', t)

    def test_refuses_output_inside_source(self):
        code, _, err = self.run_cli('export', str(self.fx['claude'] / 'x'), *self.src_args)
        self.assertEqual(code, 2)
        self.assertIn('inside source', err)

    def test_refuses_non_empty_output(self):
        out = self.root / 'busy'
        out.mkdir()
        (out / 'keep.txt').write_text('mine')
        code, _, err = self.run_cli('export', str(out), *self.src_args)
        self.assertEqual(code, 2)
        self.assertEqual((out / 'keep.txt').read_text(), 'mine')

    def test_only_cowork(self):
        out, _ = self.export('--only', 'cowork', '--no-outputs')
        self.assertFalse((out / 'claude-code').exists())
        self.assertFalse(any((out / 'cowork').rglob('outputs')))


if __name__ == '__main__':
    unittest.main()
