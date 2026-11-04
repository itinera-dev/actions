"""Whether a deployed site is live: a file of it, as readers get it, holds what the build that was deployed wrote."""

import urllib.parse

from lib.live import PageError


def file_url(url):
    """`url`, checked to be the plain address of a file.

    Raises ValueError when `url` is not an http or https address, ends in "/", or holds a query or a fragment.
    """
    parts = urllib.parse.urlsplit(url)
    if parts.scheme not in ("http", "https") or not parts.netloc or parts.query or parts.fragment:
        raise ValueError(f"The url input must be an http or https address without a query or a fragment, not {url!r}.")
    if url.endswith("/"):
        raise ValueError(f"The url input must name a file, not a directory: {url!r}.")
    return url


def not_live(url, expected, fetch, nonce):
    """Why the file at `url` is not live yet, as `fetch` reads it with `nonce` in its query, so that no cache answers
    with a copy it kept: it cannot be read, or what it holds, leading and trailing white space aside, is not
    `expected`."""
    try:
        body = fetch(f"{url}?live-check={nonce}")
    except PageError as error:
        return [f"{url} {error}."]
    if body.strip() != expected.strip():
        return [f"{url} does not hold what the deployed build wrote."]
    return []
