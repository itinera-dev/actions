"""Stand-ins for urllib's answers, for the tests of what reads a package registry."""

import email.message
import io
import json
import urllib.error
from unittest import mock


class Answer(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()


def answering(body):
    """Patches urllib so that every request is answered with `body`, as JSON, and returns the patch."""
    return mock.patch("urllib.request.urlopen", return_value=Answer(json.dumps(body).encode()))


def failing(code):
    """Patches urllib so that every request fails with the HTTP status `code`."""
    error = urllib.error.HTTPError("https://example.org", code, "failed", email.message.Message(), io.BytesIO(b"why"))
    return mock.patch("urllib.request.urlopen", side_effect=error)
