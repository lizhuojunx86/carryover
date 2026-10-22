from __future__ import annotations

import datetime as _dt
import hashlib
import json
import os
import re
import shutil
from pathlib import Path

from .safety import is_denied_file, redact


def iso(x) -> str:
    """Epoch seconds/ms or ISO string -> 'YYYY-MM-DD HH:MM' (local time for epochs)."""
    if x is None or x == '':
        return ''
    try:
        if isinstance(x, (int, float)):
            if x > 1e11:
                x = x / 1000
            return _dt.datetime.fromtimestamp(x).strftime('%Y-%m-%d %H:%M')
        return str(x)[:16].replace('T', ' ')
    except (OverflowError, OSError, ValueError):
        return str(x)


def slug(s: str, n: int = 50) -> str:
    s = re.sub(r'[\\/:*?"<>|\x00-\x1f]+', ' ', s or '').strip()
    s = re.sub(r'\s+', '-', s)
    return s[:n].strip('-.') or 'untitled'


def one_line(s: str, n: int) -> str:
    s = re.sub(r'\s+', ' ', s or '').strip()
    return s if len(s) <= n else s[:n] + '…'


def clip(t: str, n: int) -> str:
    if n and len(t) > n:
        return t[:n] + f'\n\n…[truncated, {len(t)} chars total]'
    return t


def read_json(p: Path, default=None):
    try:
        with open(p, 'r', encoding='utf-8') as f:
            return json.load(f)
    except (OSError, ValueError):
        return default


def iter_jsonl(p: Path):
    """Stream a JSONL file; bad lines are skipped."""
    try:
        f = open(p, 'r', encoding='utf-8', errors='replace')
    except OSError:
        return
    with f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                yield json.loads(line)
            except ValueError:
                continue


def text_of(content) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return '\n'.join(c.get('text', '') for c in content
                         if isinstance(c, dict) and c.get('type') == 'text')
    return ''


def read_text(p: Path, limit: int | None = None) -> str:
    with open(p, 'r', encoding='utf-8', errors='replace') as f:
        return f.read(limit) if limit else f.read()


def md_cell(s) -> str:
    return str(s if s is not None else '').replace('|', '\\|').replace('\n', ' ')


class Writer:
    """All writes go through here: under one output root, with a manifest."""

    def __init__(self, out: Path, do_redact: bool = True, max_copy_mb: float | None = None):
        self.out = Path(out)
        self.do_redact = do_redact
        self.max_copy = int(max_copy_mb * 1024 * 1024) if max_copy_mb else None
        self.files: list[dict] = []
        self.skipped: list[dict] = []
        self.redactions: dict = {}

    def _target(self, rel: str) -> Path:
        t = (self.out / rel).resolve()
        if self.out.resolve() not in t.parents:
            raise ValueError(f'refusing to write outside output dir: {rel}')
        t.parent.mkdir(parents=True, exist_ok=True)
        return t

    def text(self, rel: str, content: str, source: str | None = None) -> str:
        if self.do_redact:
            content = redact(content, self.redactions)
        t = self._target(rel)
        data = content.encode('utf-8')
        with open(t, 'wb') as f:
            f.write(data)
        self.files.append({'path': rel, 'bytes': len(data), 'sha256': hashlib.sha256(data).hexdigest(),
                           'source': source})
        return rel

    def copy_text(self, rel: str, src: Path) -> str | None:
        reason = is_denied_file(src.name)
        if reason:
            self.skipped.append({'source': str(src), 'reason': reason})
            return None
        return self.text(rel, read_text(src), source=str(src))

    def copy(self, rel: str, src: Path) -> str | None:
        reason = is_denied_file(src.name)
        if reason:
            self.skipped.append({'source': str(src), 'reason': reason})
            return None
        try:
            size = src.stat().st_size
        except OSError as e:
            self.skipped.append({'source': str(src), 'reason': f'unreadable: {e}'})
            return None
        if self.max_copy and size > self.max_copy:
            self.skipped.append({'source': str(src), 'reason': f'larger than limit ({size} bytes)'})
            return None
        t = self._target(rel)
        try:
            shutil.copyfile(src, t)
        except OSError as e:
            self.skipped.append({'source': str(src), 'reason': f'copy failed: {e}'})
            return None
        self.files.append({'path': rel, 'bytes': size, 'sha256': None, 'source': str(src)})
        return rel

    def copy_tree(self, rel_root: str, src_root: Path) -> int:
        n = 0
        for cur, dirs, files in os.walk(src_root):
            dirs[:] = sorted(d for d in dirs if not d.startswith('.'))
            for fn in sorted(files):
                if fn.startswith('.') and fn.lower() not in ('.env',):
                    continue
                src = Path(cur) / fn
                rel = Path(rel_root) / src.relative_to(src_root)
                if self.copy(rel.as_posix(), src):
                    n += 1
        return n

    def manifest(self) -> dict:
        return {'files': self.files, 'skipped': self.skipped, 'redactions': self.redactions}
