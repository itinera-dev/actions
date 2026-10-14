"""A minimal GitHub REST and GraphQL client over urllib."""

import io
import json
import os
import pathlib
import re
import tarfile
import urllib.error
import urllib.request

API_URL = os.environ.get("GITHUB_API_URL", "https://api.github.com")


class GitHubError(Exception):
    pass


def next_page_url(link_header):
    """The URL marked rel="next" in a Link header, or None."""
    for part in link_header.split(","):
        match = re.search(r'<([^>]+)>\s*;\s*rel="next"', part)
        if match:
            return match.group(1)
    return None


class GitHub:
    def __init__(self, token, api_url=API_URL):
        self._token = token
        self._api_url = api_url

    def _request(self, method, url, body=None, data=None, content_type="application/json"):
        """Send `body` as JSON, or the raw bytes `data` of `content_type`, returning the JSON answer and Link header."""
        if body is not None:
            data = json.dumps(body).encode()
        request = urllib.request.Request(
            url,
            data=data,
            method=method,
            headers={
                "Authorization": f"Bearer {self._token}",
                "Accept": "application/vnd.github+json",
                "Content-Type": content_type,
                "X-GitHub-Api-Version": "2022-11-28",
            },
        )
        try:
            with urllib.request.urlopen(request) as response:
                text = response.read().decode()
                return (json.loads(text) if text else None), response.headers.get("Link", "")
        except urllib.error.HTTPError as error:
            raise GitHubError(f"{method} {url} failed with {error.code}: {error.read().decode()}") from error

    def get(self, path):
        return self._request("GET", self._api_url + path)[0]

    def get_all(self, path):
        separator = "&" if "?" in path else "?"
        url = f"{self._api_url}{path}{separator}per_page=100"
        items = []
        while url:
            page, link = self._request("GET", url)
            items.extend(page or [])
            url = next_page_url(link)
        return items

    def download(self, path):
        """The raw bytes at `path`, following redirects, such as a repository tarball."""
        request = urllib.request.Request(
            self._api_url + path,
            headers={"Authorization": f"Bearer {self._token}", "X-GitHub-Api-Version": "2022-11-28"},
        )
        try:
            with urllib.request.urlopen(request) as response:
                return response.read()
        except urllib.error.HTTPError as error:
            raise GitHubError(f"GET {path} failed with {error.code}: {error.read().decode()}") from error

    def extract_repository(self, repo, ref, into):
        """Extract the repository `repo` at `ref`, a tag, branch or commit, into `into`, returning its root."""
        archive = self.download(f"/repos/{repo}/tarball/{ref}")
        with tarfile.open(fileobj=io.BytesIO(archive), mode="r:gz") as tar:
            if hasattr(tarfile, "data_filter"):
                tar.extractall(into, filter="data")
            else:
                tar.extractall(into)
        (root,) = pathlib.Path(into).iterdir()
        return root

    def upload(self, url, data, content_type):
        """Send raw bytes to an absolute `url`, such as a release's asset upload URL."""
        return self._request("POST", url, data=data, content_type=content_type)[0]

    def post(self, path, body):
        return self._request("POST", self._api_url + path, body)[0]

    def patch(self, path, body):
        return self._request("PATCH", self._api_url + path, body)[0]

    def put(self, path, body):
        return self._request("PUT", self._api_url + path, body)[0]

    def delete(self, path):
        return self._request("DELETE", self._api_url + path)[0]

    def graphql(self, query, variables):
        result = self.post("/graphql", {"query": query, "variables": variables}) or {}
        if result.get("errors") or "data" not in result:
            raise GitHubError(f"GraphQL query failed: {result['errors']}")
        return result["data"]
