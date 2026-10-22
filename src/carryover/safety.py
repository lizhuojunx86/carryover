"""Credential hygiene: what never gets copied, and what gets masked in text.

Two layers:
  * file-level deny list (credential files are skipped, never opened for copy)
  * text-level redaction for common secret formats in transcripts, memory,
    project instructions and task prompts

Redaction is a safety net, not a guarantee. The README says so too.
"""
from __future__ import annotations

import os
import re
from pathlib import Path

DENY_NAMES = {
    '.env', '.netrc', '.npmrc', '.pypirc', '.git-credentials', '.credentials.json',
    'credentials', 'credentials.json', 'id_rsa', 'id_dsa', 'id_ecdsa', 'id_ed25519',
    'cookies', 'cookies.sqlite', 'login data', 'web data', 'keychain',
}
DENY_SUFFIXES = (
    '.pem', '.key', '.p12', '.pfx', '.keychain', '.keychain-db', '.kdbx', '.ovpn',
    '.mobileprovision', '.jks', '.keystore',
)
DENY_PREFIXES = ('.env.',)


def is_denied_file(name: str) -> str | None:
    """Return a reason string when a file must not be copied, else None."""
    low = name.lower()
    if low in DENY_NAMES:
        return 'credential file name'
    if low.startswith(DENY_PREFIXES):
        return 'env file'
    if low.endswith(DENY_SUFFIXES):
        return 'key/certificate file'
    return None


# Order matters: specific prefixes before generic ones.
_PATTERNS = [
    ('anthropic-key', re.compile(r'sk-ant-[A-Za-z0-9_\-]{20,}')),
    ('openai-key', re.compile(r'\bsk-(?:proj-|svcacct-)?[A-Za-z0-9_\-]{32,}')),
    ('github-token', re.compile(r'\b(?:gh[pousr]_[A-Za-z0-9]{30,}|github_pat_[A-Za-z0-9_]{40,})')),
    ('aws-access-key', re.compile(r'\b(?:AKIA|ASIA)[0-9A-Z]{16}\b')),
    ('slack-token', re.compile(r'\bxox[abprs]-[A-Za-z0-9\-]{10,}')),
    ('google-api-key', re.compile(r'\bAIza[0-9A-Za-z_\-]{35}')),
    ('stripe-key', re.compile(r'\b[rsp]k_(?:live|test)_[0-9A-Za-z]{20,}')),
    ('jwt', re.compile(r'\beyJ[A-Za-z0-9_\-]{10,}\.eyJ[A-Za-z0-9_\-]{10,}\.[A-Za-z0-9_\-]{10,}')),
    ('private-key', re.compile(r'-----BEGIN [A-Z ]*PRIVATE KEY-----[\s\S]+?-----END [A-Z ]*PRIVATE KEY-----')),
    ('bearer', re.compile(r'(?i)\bbearer\s+[A-Za-z0-9._\-~+/]{16,}=*')),
]
_ASSIGN = re.compile(
    r'(?i)\b(password|passwd|pwd|secret|client[_-]?secret|api[_-]?key|access[_-]?token|'
    r'auth[_-]?token|refresh[_-]?token)\b(\s*[:=]\s*)(["\']?)([^\s"\'`,;]{8,})\3'
)


def redact(text: str, counter: dict | None = None) -> str:
    """Mask common secret formats. Optionally tally hits per kind in `counter`."""
    if not text:
        return text

    def sub(kind):
        def _r(m):
            if counter is not None:
                counter[kind] = counter.get(kind, 0) + 1
            return f'[REDACTED:{kind}]'
        return _r

    for kind, pat in _PATTERNS:
        text = pat.sub(sub(kind), text)

    def _assign(m):
        if m.group(4).startswith('[REDACTED'):
            return m.group(0)
        if counter is not None:
            counter['assignment'] = counter.get('assignment', 0) + 1
        return f'{m.group(1)}{m.group(2)}{m.group(3)}[REDACTED]{m.group(3)}'

    return _ASSIGN.sub(_assign, text)


class UnsafeOutput(Exception):
    pass


def check_output_dir(out: Path, sources: list[Path]) -> Path:
    """Refuse an output directory that sits inside (or equals) any source root."""
    out_r = Path(os.path.realpath(out))
    for src in sources:
        if not src:
            continue
        src_r = Path(os.path.realpath(src))
        if out_r == src_r or src_r in out_r.parents:
            raise UnsafeOutput(f'output directory {out} is inside source {src}; pick a folder outside it')
    return out_r
