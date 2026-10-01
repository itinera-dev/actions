"""Fail unless the pull request is linked to an open issue with the labels its profile requires."""

import os
import sys

from lib.github_api import GitHub
from lib.linking import Issue, problems

LINKED_ISSUES = """
query($owner: String!, $name: String!, $number: Int!) {
  repository(owner: $owner, name: $name) {
    pullRequest(number: $number) {
      closingIssuesReferences(first: 50) {
        nodes { number state repository { nameWithOwner } labels(first: 50) { nodes { name } } }
      }
    }
  }
}
"""


def main():
    repo, pr, profile = os.environ["REPO"], int(os.environ["PR"]), os.environ["PROFILE"]
    owner, name = repo.split("/")
    github = GitHub(os.environ["GH_TOKEN"])

    data = github.graphql(LINKED_ISSUES, {"owner": owner, "name": name, "number": pr})
    issues = [
        Issue(node["number"], node["state"] == "OPEN", {label["name"] for label in node["labels"]["nodes"]})
        for node in data["repository"]["pullRequest"]["closingIssuesReferences"]["nodes"]
        if node["repository"]["nameWithOwner"].lower() == repo.lower()
    ]
    added = [f["filename"] for f in github.get_all(f"/repos/{repo}/pulls/{pr}/files") if f["status"] == "added"]

    found = problems(profile, issues, added)
    if found:
        print("This pull request cannot be merged yet:")
        for problem in found:
            print(f"::error::{problem}")
        sys.exit(1)
    print("Linked to: " + ", ".join(f"#{i.number}" for i in issues))


if __name__ == "__main__":
    main()
