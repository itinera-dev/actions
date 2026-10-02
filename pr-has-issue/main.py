"""Fail unless the pull request is linked to an open issue with the labels its profile requires."""

import base64
import json
import os
import sys
import urllib.parse

from lib.github_api import GitHub, GitHubError
from lib.linking import Context, Issue, problems, referenced_numbers, spec_number
from lib.proposals import proposal_numbers

CLOSING_ISSUES = """
query($owner: String!, $name: String!, $number: Int!) {
  repository(owner: $owner, name: $name) {
    pullRequest(number: $number) {
      closingIssuesReferences(first: 50) {
        nodes { number title state repository { nameWithOwner } labels(first: 50) { nodes { name } } }
      }
    }
  }
}
"""


def issue_from_rest(data):
    return Issue(data["number"], data["state"] == "open", {label["name"] for label in data["labels"]}, data["title"])


def manifest_proposals(github, repo, ref):
    """The proposal numbers listed in conformance.json at `ref`; empty when there is no manifest."""
    try:
        content = github.get(f"/repos/{repo}/contents/conformance.json?ref={ref}")
    except GitHubError:
        return set()
    return set(json.loads(base64.b64decode(content["content"])).get("proposals", []))


def cases_merged(github, conformance_repo, proposal):
    """Whether the conformance issue "Cases for spec#N" is closed; None when there is none."""
    query = urllib.parse.urlencode({"q": f'repo:{conformance_repo} is:issue in:title "Cases for spec#{proposal}"'})
    for item in github.get(f"/search/issues?{query}")["items"]:
        if spec_number(item["title"]) == proposal:
            return item["state"] == "closed"
    return None


def spec_ready(github, spec_repo, proposal):
    """Whether spec proposal N is ready for its cases: labelled "status: ready", or already accepted."""
    try:
        issue = issue_from_rest(github.get(f"/repos/{spec_repo}/issues/{proposal}"))
    except GitHubError:
        return False
    return "status: ready" in issue.labels or (not issue.open and "proposal" in issue.labels)


def main():
    env = os.environ
    repo, pr, profile = env["REPO"], int(env["PR"]), env["PROFILE"]
    owner, name = repo.split("/")
    github = GitHub(env["GH_TOKEN"])

    data = github.graphql(CLOSING_ISSUES, {"owner": owner, "name": name, "number": pr})
    closing = [
        Issue(node["number"], node["state"] == "OPEN", {label["name"] for label in node["labels"]["nodes"]}, node["title"])
        for node in data["repository"]["pullRequest"]["closingIssuesReferences"]["nodes"]
        if node["repository"]["nameWithOwner"].lower() == repo.lower()
    ]
    referenced = []
    for n in referenced_numbers(env.get("PR_BODY", "")):
        try:
            referenced.append(issue_from_rest(github.get(f"/repos/{repo}/issues/{n}")))
        except GitHubError:
            print(f"::warning::Refs #{n}: no such issue in {repo}.")
    added = [f["filename"] for f in github.get_all(f"/repos/{repo}/pulls/{pr}/files") if f["status"] == "added"]

    context = Context()
    if profile == "spec":
        conformance_repo = env.get("CONFORMANCE_REPO") or f"{owner}/conformance"
        context.cases_merged = {n: cases_merged(github, conformance_repo, n) for n in proposal_numbers(added)}
    if profile == "conformance":
        spec_repo = env.get("SPEC_REPO") or f"{owner}/spec"
        waiting = {spec_number(i.title) for i in [*closing, *referenced] if "waiting for spec" in i.labels}
        context.spec_ready = {n: spec_ready(github, spec_repo, n) for n in waiting if n is not None}
    if profile == "implementation":
        context.manifest_before = manifest_proposals(github, repo, env["BASE_SHA"])
        context.manifest_after = manifest_proposals(github, repo, env["HEAD_SHA"])

    found = problems(profile, closing, referenced, added, context)
    if found:
        print("This pull request cannot be merged yet:")
        for problem in found:
            print(f"::error::{problem}")
        sys.exit(1)
    linked = sorted({i.number for i in [*closing, *referenced]})
    print("Linked to: " + ", ".join(f"#{n}" for n in linked))


if __name__ == "__main__":
    main()
