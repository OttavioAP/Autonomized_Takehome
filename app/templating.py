import re
import secrets
from html import escape
from pathlib import Path
from typing import Any

import markdown as markdown_lib
from fastapi.templating import Jinja2Templates
from markupsafe import Markup

_CITE_SENTINEL_RE = re.compile(r"\{\{cite:(\d+):([0-9a-fA-F-]{36})\}\}")

_ACTIVITY_KIND_META = {
    "jira_ticket": {"css_class": "jira", "prefix": "JIRA"},
    "jira_comment": {"css_class": "jira", "prefix": "JIRA comment"},
    "jira_project": {"css_class": "jira", "prefix": "JIRA project"},
    "jira_person": {"css_class": "jira", "prefix": "JIRA person"},
    "github_commit": {"css_class": "github", "prefix": "Commit"},
    "github_pr": {"css_class": "github", "prefix": "PR"},
    "github_comment": {"css_class": "github", "prefix": "GitHub comment"},
    "github_repo": {"css_class": "github", "prefix": "Repo"},
    "github_user": {"css_class": "github", "prefix": "GitHub user"},
}

_UNRESOLVED_CITATION_DETAIL = "Couldn't resolve a citation the assistant made — this may be a bug."


def _render_pill(kind: str, label: str, url: str) -> str:
    meta = _ACTIVITY_KIND_META.get(kind, {"css_class": "github", "prefix": ""})
    prefix = f"{escape(meta['prefix'])}: " if meta["prefix"] else ""
    text = f"{prefix}{escape(label)}"
    return (
        f'<a class="activity-pill activity-pill--{meta["css_class"]}" '
        f'href="{escape(url)}" target="_blank" rel="noopener noreferrer" '
        f'title="{text}">{text}</a>'
    )


def _render_cite_error(ordinal: int) -> str:
    detail = escape(_UNRESOLVED_CITATION_DETAIL)
    return f'<span class="cite-error" title="{detail}">[{ordinal}: unresolved citation]</span>'


def resolve_citations(content: str, citations: list[Any]) -> Markup:
    """Replace {{cite:ordinal:uuid}} sentinels in `content` with rendered activity
    pills, resolving each ordinal against `citations` (list index + 1 == ordinal,
    per chat.md's MessageOut shape), and render the surrounding text as markdown -
    the model's own output is markdown (unprompted but consistent; matches
    chat.html's client-side marked.js rendering of the same content while it
    streams live, so history replay after a reload looks the same as it did live).
    An ordinal with no matching citations entry, or a uuid that doesn't match that
    entry's id, renders as a cite-error marker instead of a pill, mirroring the
    live cite-error SSE path.

    Safety: `content` is escaped BEFORE markdown parsing (neutralizes any literal
    HTML the model's own text might contain - Python-Markdown, like marked.js
    client-side, passes raw HTML through unless the source is pre-escaped) and
    pill/cite-error HTML is substituted in via a random per-call placeholder token
    AFTER parsing, so it's never itself subject to markdown syntax interpretation
    (a pill's label/url are already escaped in _render_pill/_render_cite_error).
    """
    token_prefix = f" CITE{secrets.token_hex(8)}-"
    placeholders: list[str] = []

    def replace(match: re.Match[str]) -> str:
        ordinal = int(match.group(1))
        uuid = match.group(2)
        index = ordinal - 1
        if index < 0 or index >= len(citations):
            html = _render_cite_error(ordinal)
        else:
            item = citations[index]
            item_id = str(item.id) if hasattr(item, "id") else str(item["id"])
            if item_id.lower() != uuid.lower():
                html = _render_cite_error(ordinal)
            else:
                kind = item.kind if hasattr(item, "kind") else item["kind"]
                kind_value = kind.value if hasattr(kind, "value") else kind
                label = item.label if hasattr(item, "label") else item["label"]
                url = item.url if hasattr(item, "url") else item["url"]
                html = _render_pill(kind_value, label, url)
        token = f"{token_prefix}{len(placeholders)}"
        placeholders.append(html)
        return token

    with_tokens = _CITE_SENTINEL_RE.sub(replace, content)
    escaped = escape(with_tokens)
    rendered = markdown_lib.markdown(escaped)
    token_re = re.compile(re.escape(token_prefix) + r"(\d+)")
    resolved = token_re.sub(lambda m: placeholders[int(m.group(1))], rendered)
    return Markup(resolved)  # noqa: S704


templates = Jinja2Templates(directory=Path(__file__).resolve().parent / "templates")
templates.env.filters["resolve_citations"] = resolve_citations
