"""Small loader for app/prompts/*.md - plain text files, not string literals inline in
ChatService (chat.md's Prompts section). No caching: these are small files read once
per ChatService.run() call, not a hot path worth optimizing at this project's scale.
"""

from pathlib import Path

_PROMPTS_DIR = Path(__file__).resolve().parent


def load_prompt(name: str) -> str:
    return (_PROMPTS_DIR / name).read_text()
