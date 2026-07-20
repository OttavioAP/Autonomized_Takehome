"""Chat feature error classes (chat.md's Errors section). No silent failures - every
failure class either becomes explicit model-facing context or a dedicated SSE event,
never a swallowed exception or a canned string.
"""


class ToolExecutionError(Exception):
    """Raised when a tool's underlying JIRA/GitHub HTTP call fails. Caught by
    ChatService, turned into an explicit error string appended as the tool result,
    fed back to the model - the model decides how to communicate that to the user.
    """


class UpstreamProviderError(Exception):
    """OpenRouter itself is unreachable/erroring - no model is available to explain
    itself, so this maps directly to the `error` SSE event instead.
    """
