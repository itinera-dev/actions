"""Proposal files: proposals/NNNN-short-name.md, numbered by their issue."""

import re

PROPOSAL_FILE = re.compile(r"proposals/(\d{4})-[^/]+\.md")


def proposal_numbers(filenames):
    """The sorted issue numbers of the proposal files among `filenames`."""
    return sorted({int(m.group(1)) for f in filenames if (m := PROPOSAL_FILE.fullmatch(f))})


def acceptance_comment(pr, merged_at):
    """The comment closing an accepted proposal's issue; `merged_at` is the merge's ISO 8601 timestamp."""
    return f"Accepted on {merged_at[:10]} in #{pr}."
