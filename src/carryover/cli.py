"""carryover CLI.

  carryover scan                 what is there, what will not survive a switch (writes nothing)
  carryover export <folder>      build a browsable archive + restore packs in <folder>
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from . import __version__, claude_code, cowork, report
from .locate import Sources
from .safety import UnsafeOutput, check_output_dir
from .util import Writer


def _add_sources(p: argparse.ArgumentParser) -> None:
    g = p.add_argument_group('sources (auto-detected if omitted)')
    g.add_argument('--claude-home', help='Claude Code config dir (default: $CLAUDE_CONFIG_DIR or ~/.claude)')
    g.add_argument('--cowork-root', help='Cowork local sessions dir (default: <Claude app dir>/local-agent-mode-sessions)')
    g.add_argument('--documents-claude', help='Cowork prompts/artifacts dir (default: ~/Documents/Claude)')
    g.add_argument('--only', choices=['claude-code', 'cowork'], help='limit to one product')


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(prog='carryover', description='Move a Claude workspace (Claude Code + Cowork) to a '
                                 'new account or machine. Reads only; never copies credentials.')
    ap.add_argument('--version', action='version', version=f'carryover {__version__}')
    sub = ap.add_subparsers(dest='cmd', required=True)

    s = sub.add_parser('scan', help='inventory and warnings; writes nothing')
    _add_sources(s)
    s.add_argument('--json', action='store_true', help='machine-readable output')

    e = sub.add_parser('export', help='write an archive with transcripts, memory and restore packs')
    e.add_argument('out', help='output folder (must not be inside a source folder)')
    _add_sources(e)
    e.add_argument('--no-outputs', action='store_true', help='skip copying Cowork session output files')
    e.add_argument('--max-file-mb', type=float, default=None, help='skip output files larger than this')
    e.add_argument('--max-chars', type=int, default=20000, help='truncate single messages longer than this (0 = never)')
    e.add_argument('--no-redact', action='store_true', help='do not mask secret-looking strings in text')
    e.add_argument('--force', action='store_true', help='allow a non-empty output folder')
    return ap


def _collect(src: Sources, only):
    cc = claude_code.scan(src.claude_home) if only != 'cowork' else []
    orgs = cowork.scan(src.cowork_root, src.documents_claude) if only != 'claude-code' else []
    orphans = cowork.orphan_prompts(orgs, src.documents_claude) if only != 'claude-code' else []
    return cc, orgs, orphans


def cmd_scan(a) -> int:
    src = Sources.from_args(a.claude_home, a.cowork_root, a.documents_claude)
    cc, orgs, orphans = _collect(src, a.only)
    ret = claude_code.retention(src.claude_home, cc) if a.only != 'cowork' else None
    d = report.summary_dict(src, cc, orgs, orphans, ret)
    print(json.dumps(d, ensure_ascii=False, indent=1) if a.json else report.summary_text(d))
    return 0


def cmd_export(a) -> int:
    src = Sources.from_args(a.claude_home, a.cowork_root, a.documents_claude)
    out = Path(a.out).expanduser()
    try:
        out = check_output_dir(out, src.roots())
    except UnsafeOutput as ex:
        print(f'carryover: {ex}', file=sys.stderr)
        return 2
    if out.exists() and any(out.iterdir()) and not a.force:
        print(f'carryover: {out} is not empty (use --force to write into it anyway)', file=sys.stderr)
        return 2
    out.mkdir(parents=True, exist_ok=True)

    cc, orgs, orphans = _collect(src, a.only)
    w = Writer(out, do_redact=not a.no_redact, max_copy_mb=a.max_file_mb)
    cc_stats = claude_code.export(src.claude_home, w, cc, a.max_chars) if a.only != 'cowork' else None
    cw_stats = cowork.export(orgs, orphans, w, a.max_chars, outputs=not a.no_outputs) if a.only != 'claude-code' else None
    ret = claude_code.retention(src.claude_home, cc) if a.only != 'cowork' else None
    d = report.summary_dict(src, cc, orgs, orphans, ret)
    orgs = [o for o in orgs if o.sessions or o.spaces or o.tasks or o.artifacts or o.global_memory]
    man = w.manifest()
    w.text('INDEX.md', report.index_md(src, d, cc_stats, cw_stats, orgs, man, out))
    with open(out / 'manifest.json', 'w', encoding='utf-8') as f:
        json.dump({'version': __version__, 'summary': d, 'claude_code': cc_stats, 'cowork': cw_stats, **w.manifest()},
                  f, ensure_ascii=False, indent=1)
    print(f'Wrote {len(w.files)} files to {out}')
    if cc_stats:
        print(f'  Claude Code: {cc_stats["projects"]} projects, {cc_stats["sessions"]} sessions, {cc_stats["memory"]} memory files')
    if cw_stats:
        print(f'  Cowork: {cw_stats.get("sessions", 0)} sessions, {cw_stats.get("outputs", 0)} output files, '
              f'{cw_stats.get("projects", 0)} restore packs, {cw_stats.get("tasks", 0)} scheduled tasks')
    print(f'  Masked {sum(man["redactions"].values())} secret-looking strings; skipped {len(man["skipped"])} files '
          '(see manifest.json)')
    print(f'Start with {out / "INDEX.md"}')
    return 0


def main(argv=None) -> int:
    a = build_parser().parse_args(argv)
    return {'scan': cmd_scan, 'export': cmd_export}[a.cmd](a)
