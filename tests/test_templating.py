"""Unit tests for resolve_citations (app/templating.py) - pure Python logic, no live
API needed. Covers the two things this filter has to get right together: markdown
rendering (matching chat.html's client-side marked.js rendering of the same live
content) and citation-sentinel-to-pill substitution, without either one corrupting
the other.
"""

from types import SimpleNamespace
from uuid import uuid4

from app.templating import resolve_citations


def test_plain_markdown_renders_without_citations() -> None:
    result = resolve_citations("**Mike** has been productive.", [])
    assert "<strong>Mike</strong>" in result
    assert "**Mike**" not in result


def test_markdown_list_renders() -> None:
    content = "Work items:\n\n- one\n- two\n"
    result = resolve_citations(content, [])
    assert "<ul>" in result
    assert "<li>one</li>" in result
    assert "<li>two</li>" in result


def test_valid_citation_renders_as_pill_not_literal_sentinel() -> None:
    item_id = uuid4()
    item = SimpleNamespace(
        id=item_id, kind="github_pr", label="PR #1", url="https://example.com/pr/1"
    )
    content = f"Sarah opened PR #1 {{{{cite:1:{item_id}}}}} yesterday."
    result = resolve_citations(content, [item])
    assert "{{cite" not in result
    assert 'class="activity-pill activity-pill--github"' in result
    assert "https://example.com/pr/1" in result


def test_citation_and_markdown_compose_correctly() -> None:
    item_id = uuid4()
    item = SimpleNamespace(
        id=item_id, kind="github_user", label="autonomized3", url="https://github.com/autonomized3"
    )
    content = f"**Mike** {{{{cite:1:{item_id}}}}} has been the most productive."
    result = resolve_citations(content, [item])
    assert "<strong>Mike</strong>" in result
    assert 'class="activity-pill activity-pill--github"' in result
    assert "{{cite" not in result


def test_unknown_uuid_renders_cite_error_not_pill() -> None:
    item_id = uuid4()
    item = SimpleNamespace(
        id=item_id, kind="jira_ticket", label="KAN-1", url="https://example.com/KAN-1"
    )
    wrong_uuid = uuid4()
    content = f"See {{{{cite:1:{wrong_uuid}}}}}."
    result = resolve_citations(content, [item])
    assert "cite-error" in result
    assert "activity-pill" not in result


def test_out_of_range_ordinal_renders_cite_error() -> None:
    content = "See {{cite:1:12345678-1234-1234-1234-123456789abc}}."
    result = resolve_citations(content, [])
    assert "cite-error" in result


def test_literal_html_in_model_text_is_escaped_not_executed() -> None:
    """The model's own text must never become live HTML - Python-Markdown (like
    marked.js client-side) passes raw HTML through unless pre-escaped, so this is
    the actual XSS-safety guarantee, not just a formatting nicety."""
    content = "<script>alert(1)</script> and **bold**"
    result = resolve_citations(content, [])
    assert "<script>" not in result
    assert "&lt;script&gt;" in result
    assert "<strong>bold</strong>" in result


def test_dict_shaped_citations_also_work() -> None:
    """resolve_citations duck-types citations as either objects or dicts (history
    replay may pass either shape) - confirm the dict path still resolves correctly
    now that markdown rendering sits in between sentinel detection and pill output.
    """
    item_id = uuid4()
    item = {
        "id": item_id,
        "kind": "jira_ticket",
        "label": "KAN-1",
        "url": "https://example.com/KAN-1",
    }
    content = f"Ticket {{{{cite:1:{item_id}}}}} is done."
    result = resolve_citations(content, [item])
    assert 'class="activity-pill activity-pill--jira"' in result
