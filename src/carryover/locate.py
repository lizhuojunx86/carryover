"""Where Claude keeps things on each OS. Every path can be overridden on the CLI."""
from __future__ import annotations

import os
import sys
from dataclasses import dataclass
from pathlib import Path


def default_claude_home() -> Path:
    env = os.environ.get('CLAUDE_CONFIG_DIR')
    return Path(env).expanduser() if env else Path.home() / '.claude'


def default_app_dir() -> Path:
    if sys.platform == 'darwin':
        return Path.home() / 'Library' / 'Application Support' / 'Claude'
    if sys.platform.startswith('win'):
        return Path(os.environ.get('APPDATA') or Path.home() / 'AppData' / 'Roaming') / 'Claude'
    return Path(os.environ.get('XDG_CONFIG_HOME') or Path.home() / '.config') / 'Claude'


def default_cowork_root() -> Path:
    return default_app_dir() / 'local-agent-mode-sessions'


def default_documents_claude() -> Path:
    """Cowork keeps scheduled-task prompts and artifacts under ~/Documents/Claude."""
    return Path.home() / 'Documents' / 'Claude'


@dataclass
class Sources:
    claude_home: Path
    cowork_root: Path
    documents_claude: Path

    @classmethod
    def from_args(cls, claude_home=None, cowork_root=None, documents_claude=None) -> 'Sources':
        return cls(
            Path(claude_home).expanduser() if claude_home else default_claude_home(),
            Path(cowork_root).expanduser() if cowork_root else default_cowork_root(),
            Path(documents_claude).expanduser() if documents_claude else default_documents_claude(),
        )

    def roots(self) -> list[Path]:
        return [self.claude_home, self.cowork_root, self.documents_claude]
