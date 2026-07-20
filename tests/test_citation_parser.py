"""Unit tests for CitationStreamParser (chat.md's ChatService section) - synthetic
delta sequences, no live API. The tricky property is a sentinel split across delta
boundaries: the parser must buffer a partial "{{cite:..." tail rather than flush it as
plain text, then emit the citation once the closing "}}" arrives in a later chunk.
"""

from app.services.chat_service import CitationStreamParser

_UUID = "12345678-1234-1234-1234-123456789abc"


def _collect(
    parser: CitationStreamParser, chunks: list[str]
) -> list[tuple[str, tuple[int, str] | None]]:
    events: list[tuple[str, tuple[int, str] | None]] = []
    for chunk in chunks:
        events.extend(parser.feed(chunk))
    events.extend(parser.flush())
    return events


def test_plain_text_no_citation() -> None:
    parser = CitationStreamParser()
    events = _collect(parser, ["Hello ", "world."])
    assert events == [("Hello ", None), ("world.", None)]


def test_single_citation_in_one_chunk() -> None:
    parser = CitationStreamParser()
    events = _collect(parser, [f"See ticket {{{{cite:1:{_UUID}}}}} now"])
    assert events == [
        ("See ticket ", None),
        ("", (1, _UUID)),
        (" now", None),
    ]


def test_citation_split_across_delta_boundaries() -> None:
    parser = CitationStreamParser()
    # The sentinel is dribbled out one fragment at a time - the parser must not flush
    # the partial "{{cite:..." as plain text before it completes.
    events = _collect(
        parser,
        ["Look: ", "{{cite:", "1:", _UUID, "}}", " done"],
    )
    assert events == [
        ("Look: ", None),
        ("", (1, _UUID)),
        (" done", None),
    ]


def test_citation_split_right_after_double_brace() -> None:
    # Regression: OpenRouter really splits a delta right after "{{" (confirmed live) -
    # e.g. "... PR #1 {{" then "cite:1:5bdc6" then more. An earlier partial-sentinel
    # regex required "{{c" to hold a tail back, so a lone "{{" flushed as plain text
    # and the citation leaked through as raw text instead of a CiteEvent. These are the
    # actual fragment boundaries captured from a live OpenRouter stream.
    parser = CitationStreamParser()
    uuid = "5bdc6c25-2622-475e-89f7-a1a512e915e5"
    events = _collect(
        parser,
        [
            "Sarah",
            " opened PR #1 {{",
            "cite:1:5bdc6",
            "c25-2622-475e",
            "-89f7-a1a",
            "512e915e5}} today.",
        ],
    )
    assert events == [
        ("Sarah", None),
        (" opened PR #1 ", None),
        ("", (1, uuid)),
        (" today.", None),
    ]


def test_citation_split_before_final_closing_brace() -> None:
    # Regression: OpenRouter also splits a delta right before the second "}" of the
    # closing "}}" - e.g. "...a43a}" then "}.next" (confirmed live via the manual
    # POST /conversations/{id}/chat exercise). The buffer then holds a complete
    # "{{cite:N:UUID}" (one brace) that the full-sentinel regex can't match yet; the
    # partial regex must hold that single-trailing-"}" tail back rather than flush it.
    parser = CitationStreamParser()
    uuid = "a195f634-b110-4e96-9653-f00ebc07a43a"
    events = _collect(
        parser,
        ["PR #1 ", "{{cite:1:a195f634-b110-4e96-9653-f00ebc07a43a}", "}.next"],
    )
    assert events == [
        ("PR #1 ", None),
        ("", (1, uuid)),
        (".next", None),
    ]


def test_prose_ending_in_single_brace_is_not_held_back() -> None:
    # The single-trailing-"}" hold-back above must NOT trigger on ordinary prose that
    # merely ends in "}" (e.g. code snippets) - only when a full "{{cite:N:UUID"
    # precedes it. Otherwise normal text ending in "}" would stall mid-stream.
    parser = CitationStreamParser()
    events = _collect(parser, ["const x = {a: 1}", " done"])
    assert events == [("const x = {a: 1}", None), (" done", None)]


def test_citation_split_mid_uuid() -> None:
    parser = CitationStreamParser()
    head, tail = _UUID[:10], _UUID[10:]
    events = _collect(parser, [f"x {{{{cite:2:{head}", f"{tail}}}}} y"])
    assert events == [
        ("x ", None),
        ("", (2, _UUID)),
        (" y", None),
    ]


def test_multiple_citations_in_one_message() -> None:
    parser = CitationStreamParser()
    uuid2 = "abcdef01-2345-6789-abcd-ef0123456789"
    events = _collect(
        parser,
        [f"A {{{{cite:1:{_UUID}}}}} and B {{{{cite:2:{uuid2}}}}}."],
    )
    assert events == [
        ("A ", None),
        ("", (1, _UUID)),
        (" and B ", None),
        ("", (2, uuid2)),
        (".", None),
    ]


def test_invalid_uuid_length_is_not_matched() -> None:
    parser = CitationStreamParser()
    # A too-short "uuid" never matches the 36-char pattern, so the whole thing stays
    # plain text (validation of a real-but-unknown uuid happens later in ChatService;
    # here it simply isn't recognized as a sentinel at all).
    events = _collect(parser, ["{{cite:1:not-a-uuid}} rest"])
    assert events == [("{{cite:1:not-a-uuid}} rest", None)]


def test_literal_double_brace_that_never_completes_is_plain_text() -> None:
    parser = CitationStreamParser()
    events = _collect(parser, ["math: {{x}} and ", "more"])
    # "{{x}}" isn't a cite prefix (the char after "{{" isn't "c"), so it flushes as
    # plain text immediately rather than being held back.
    assert events == [("math: {{x}} and ", None), ("more", None)]


def test_trailing_partial_sentinel_flushed_as_plain_text_on_flush() -> None:
    parser = CitationStreamParser()
    # Stream ends mid-sentinel (model got cut off) - flush() must surface the buffered
    # partial as plain text rather than swallowing it.
    events = _collect(parser, ["end {{cite:1:"])
    assert events == [("end ", None), ("{{cite:1:", None)]
