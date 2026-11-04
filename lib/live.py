"""Reading a deployed site as readers get it, again and again until it serves what was deployed."""

import http.client
import urllib.error
import urllib.request

from lib.registry import TIMEOUT_SECONDS, USER_AGENT

INTERVAL_SECONDS = 20


class PageError(Exception):
    pass


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


def wait_until(problems_at, sleep, clock, timeout, nonce):
    """Calls `problems_at` with a new nonce, starting with `nonce`, every INTERVAL_SECONDS until it returns no problem
    or `timeout` seconds have passed, as `clock` counts them, and returns the problems of the last call."""
    deadline = clock() + timeout
    attempt = 1
    while True:
        problems = problems_at(f"{nonce}-{attempt}")
        if not problems or clock() + INTERVAL_SECONDS > deadline:
            return problems
        sleep(INTERVAL_SECONDS)
        attempt += 1
