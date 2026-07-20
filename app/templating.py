import re
from html import escape
from pathlib import Path
from typing import Any

from fastapi.templating import Jinja2Templates
from markupsafe import Markup

_CITE_SENTINEL_RE = re.compile(r"\{\{cite:(\d+):([0-9a-fA-F-]{36})\}\}")

_ACTIVITY_KIND_META = {
    "jira_ticket": {"css_class": "jira", "prefix": "JIRA"},
    "jira_comment": {"css_class": "jira", "prefix": "JIRA comment"},
    "github_commit": {"css_class": "github", "prefix": "Commit"},
    "github_pr": {"css_class": "github", "prefix": "PR"},
    "github_comment": {"css_class": "github", "prefix": "GitHub comment"},
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
    per chat.md's MessageOut shape). An ordinal with no matching citations entry,
    or a uuid that doesn't match that entry's id, renders as a cite-error marker
    instead of a pill, mirroring the live cite-error SSE path for history replay.
    """

    def replace(match: re.Match[str]) -> str:
        ordinal = int(match.group(1))
        uuid = match.group(2)
        index = ordinal - 1
        if index < 0 or index >= len(citations):
            return _render_cite_error(ordinal)
        item = citations[index]
        item_id = str(item.id) if hasattr(item, "id") else str(item["id"])
        if item_id.lower() != uuid.lower():
            return _render_cite_error(ordinal)
        kind = item.kind if hasattr(item, "kind") else item["kind"]
        kind_value = kind.value if hasattr(kind, "value") else kind
        label = item.label if hasattr(item, "label") else item["label"]
        url = item.url if hasattr(item, "url") else item["url"]
        return _render_pill(kind_value, label, url)

    escaped = escape(content)
    resolved = _CITE_SENTINEL_RE.sub(replace, escaped)
    return Markup(resolved)  # noqa: S704


templates = Jinja2Templates(directory=Path(__file__).resolve().parent / "templates")
templates.env.filters["resolve_citations"] = resolve_citations
