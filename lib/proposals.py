"""Proposal files: proposals/NNNN-short-name.md, numbered by their issue."""

import re

PROPOSAL_FILE = re.compile(r"proposals/(\d{4})-[^/]+\.md")


def proposal_numbers(filenames):
    """The sorted issue numbers of the proposal files among `filenames`."""
    return sorted({int(m.group(1)) for f in filenames if (m := PROPOSAL_FILE.fullmatch(f))})
