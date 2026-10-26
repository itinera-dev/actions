"""Reading a package registry's public JSON API, such as npm's or crates.io's, over urllib."""

import http.client
import json
import urllib.error
import urllib.request

# crates.io refuses requests without a User-Agent that says who is asking; this names the project, never a person.
USER_AGENT = "itinera-dev/actions (https://github.com/itinera-dev/actions)"
TIMEOUT_SECONDS = 30


class RegistryError(Exception):
    pass


def get_json(url, accept="application/json"):
    """The JSON answer at `url`, or None when the registry has nothing there (404)."""
    request = urllib.request.Request(url, headers={"Accept": accept, "User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(request, timeout=TIMEOUT_SECONDS) as response:
            return json.loads(response.read())
    except urllib.error.HTTPError as error:
        if error.code == 404:
            return None
        raise RegistryError(f"GET {url} failed with {error.code}: {error.read().decode(errors='replace')}") from error
    except urllib.error.URLError as error:
        raise RegistryError(f"GET {url} failed: {error.reason}") from error
    except (OSError, http.client.HTTPException) as error:
        raise RegistryError(f"GET {url} failed: {error}") from error
    except ValueError as error:
        raise RegistryError(f"GET {url} did not answer with JSON: {error}") from error
