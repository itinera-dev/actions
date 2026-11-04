"""Check that a deployed site is live: a file of it holds what the deployed build wrote."""

import os
import sys
import time
from typing import NoReturn

from lib.live import fetch_page, wait_until
from lib.site_live import file_url, not_live

STALE_DEPLOYMENT = (
    "GitHub Pages can keep serving its previous deployment while reporting a new one as successful, as when a run"
    " deploys from a tag a commit it already serves; deploying again from the default branch, with"
    " workflow_dispatch, or a deployment of a newer commit makes the site live."
)


def fail(message) -> NoReturn:
    print(f"::error::{message}")
    sys.exit(1)


def main():
    env = os.environ
    try:
        timeout = int(env["TIMEOUT"])
    except ValueError:
        fail(f"The timeout must be a whole number of seconds, not {env['TIMEOUT']!r}.")
    try:
        url = file_url(env["URL"])
    except ValueError as error:
        fail(str(error))
    try:
        with open(env["EXPECTED"], encoding="utf-8") as built:
            expected = built.read()
    except OSError as error:
        fail(f"The file the expected input names cannot be read: {error}.")
    if not expected.strip():
        fail("The file the expected input names is empty, so there is nothing to compare the site with.")
    nonce = f"{env.get('GITHUB_RUN_ID', '0')}-{env.get('GITHUB_RUN_ATTEMPT', '1')}"
    problems = wait_until(
        lambda attempt: not_live(url, expected, fetch_page, attempt), time.sleep, time.monotonic, timeout, nonce
    )
    if problems:
        fail(f"The site is not live after about {timeout} seconds: {' '.join(problems)} {STALE_DEPLOYMENT}")
    print(f"The site is live: {url} holds what the deployed build wrote.")


if __name__ == "__main__":
    main()
