"""Whether a reference laid out in editions is live: its root and the newest release's own pages, as readers get
them, name the newest release in their title."""

import html
import http.client
import re
import urllib.error
import urllib.parse
import urllib.request

from lib.registry import TIMEOUT_SECONDS, USER_AGENT

INTERVAL_SECONDS = 20
TITLE = re.compile(r"<title[^>]*>(.*?)</title>", re.IGNORECASE | re.DOTALL)


class PageError(Exception):
    pass


def names_version(page, version):
    """Whether the title of `page`, an HTML document, names "v" followed by `version`, and not a longer version that
    starts with it, such as 0.1.0-beta.60 for 0.1.0-beta.6."""
    title = TITLE.search(page)
    named = rf"(?<![0-9A-Za-z.-])v{re.escape(version)}(?![0-9A-Za-z+-]|\.[0-9A-Za-z])"
    return title is not None and re.search(named, html.unescape(title.group(1))) is not None


def root_of(url):
    """The address of the reference's root at `url`, ending in "/".

    Raises ValueError when `url` is not an http or https address, or holds a query or a fragment.
    """
    parts = urllib.parse.urlsplit(url)
    if parts.scheme not in ("http", "https") or not parts.netloc or parts.query or parts.fragment:
        raise ValueError(f"The url input must be an http or https address without a query or a fragment, not {url!r}.")
    return url if url.endswith("/") else f"{url}/"


def live_pages(root, version):
    """The pages that name `version` once the editions are live at `root`: the root and the release's front page."""
    return [root, f"{root}{version}/"]


def fetch_page(url):
    """The page at `url`, asking every cache on the way for a fresh copy.

    Raises PageError when it cannot be read.
    """
    request = urllib.request.Request(url, headers={"Cache-Control": "no-cache", "User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(request, timeout=TIMEOUT_SECONDS) as response:
            return response.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as error:
        raise PageError(f"answered {error.code}") from error
    except urllib.error.URLError as error:
        raise PageError(f"cannot be reached: {error.reason}") from error
    except (OSError, http.client.HTTPException) as error:
        raise PageError(f"cannot be read: {error!r}") from error


def not_live(pages, version, fetch, nonce):
    """Why each of `pages` is not live yet, as `fetch` reads it with `nonce` in its query, so that no cache answers
    with a copy it kept: it cannot be read, or its title does not name `version`."""
    problems = []
    for page in pages:
        try:
            body = fetch(f"{page}?live-check={nonce}")
        except PageError as error:
            problems.append(f"{page} {error}.")
            continue
        if not names_version(body, version):
            problems.append(f"{page} does not name v{version} in its title.")
    return problems


def wait_until_live(pages, version, fetch, sleep, clock, timeout, nonce):
    """Reads `pages` every INTERVAL_SECONDS until they are live or `timeout` seconds have passed, as `clock` counts
    them, and returns why they are not live at the last reading, or an empty list once they are."""
    deadline = clock() + timeout
    attempt = 1
    while True:
        problems = not_live(pages, version, fetch, f"{nonce}-{attempt}")
        if not problems or clock() + INTERVAL_SECONDS > deadline:
            return problems
        sleep(INTERVAL_SECONDS)
        attempt += 1
