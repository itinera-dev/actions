"""Closing keywords that point at an issue in another repository."""

import re

_CLOSING = re.compile(
    r"\b(?:close[sd]?|fix(?:e[sd])?|resolve[sd]?):?\s+"
    r"(?:https://github\.com/([\w.-]+/[\w.-]+)/issues/\d+|([\w.-]+/[\w.-]+)#\d+)",
    re.IGNORECASE,
)


def cross_repo_closings(text, repo):
    """Each closing reference in `text` whose target is not `repo` (owner/name)."""
    return [
        m.group(0)
        for m in _CLOSING.finditer(text)
        if (m.group(1) or m.group(2)).lower() != repo.lower()
    ]
