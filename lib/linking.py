"""Whether a pull request's linked issues allow it to be merged."""

import re
from dataclasses import dataclass, field

from .proposals import proposal_numbers

PROFILES = ("default", "spec", "implementation", "conformance")
SPEC_ISSUE_LABELS = {"process", "spec defect", "proposal"}

_REFS = re.compile(r"\brefs?:?\s+#(\d+)\b", re.IGNORECASE)
_SPEC_NUMBER = re.compile(r"\bspec#(\d+)\b", re.IGNORECASE)


@dataclass
class Issue:
    number: int
    open: bool
    labels: set = field(default_factory=set)
    title: str = ""


def referenced_numbers(body):
    """Issue numbers in this repository that `body` refers to with "Refs #N"."""
    return sorted({int(n) for n in _REFS.findall(body or "")})


def spec_number(title):
    """The spec proposal number an issue title names, as in "Implement spec#8 (Steps)", or None."""
    match = _SPEC_NUMBER.search(title or "")
    return int(match.group(1)) if match else None


@dataclass
class Context:
    """Facts from outside the pull request's own issues that some profiles need."""

    # spec: for each proposal number, whether its conformance issue "Cases for spec#N" is closed (None: not found).
    cases_merged: dict = field(default_factory=dict)
    # conformance: for each spec proposal number, whether it is ready or already accepted.
    spec_ready: dict = field(default_factory=dict)
    # implementation: the proposal numbers listed in conformance.json before and after the pull request.
    manifest_before: set = field(default_factory=set)
    manifest_after: set = field(default_factory=set)


def problems(profile, closing, referenced, added_files, context=None):
    """Why the pull request cannot be merged; empty when it can.

    `closing` are the issues the pull request closes in its own repository, `referenced`
    the ones it refers to with "Refs #N", and `added_files` the paths it adds.
    """
    if profile not in PROFILES:
        return [f'Unknown profile "{profile}"; expected one of {", ".join(PROFILES)}.']
    context = context or Context()

    found = []
    linked = {i.number: i for i in [*referenced, *closing]}
    closing_by_number = {i.number: i for i in closing}
    if not linked:
        found.append('Not linked to any issue in this repository. Add "Closes #N" or "Refs #N" to the description.')
    found += [f"Issue #{n} is closed; link an open issue." for n, i in sorted(linked.items()) if not i.open]

    if profile == "spec":
        proposals = proposal_numbers(added_files)
        for n in proposals:
            if n not in closing_by_number:
                found.append(f'Adds the file of proposal {n:04d} but does not close #{n}. Add "Closes #{n}".')
            elif not {"proposal", "status: ready"} <= closing_by_number[n].labels:
                found.append(f'Issue #{n} must be labelled "proposal" and "status: ready" before its proposal file is merged.')
            merged = context.cases_merged.get(n)
            if merged is None:
                found.append(f'No conformance issue "Cases for spec#{n}" was found; its cases must be merged first.')
            elif not merged:
                found.append(f'The conformance cases for proposal {n:04d} are not merged yet ("Cases for spec#{n}" is open).')
        if linked and not proposals and not any(i.labels & SPEC_ISSUE_LABELS for i in linked.values()):
            found.append('Link an issue labelled "process", "spec defect" or "proposal".')

    if profile == "implementation":
        found += [
            f'Issue #{n} is still "waiting for spec": its proposal is not accepted yet.'
            for n, i in sorted(linked.items())
            if {"implements-proposal", "waiting for spec"} <= i.labels
        ]
        switched_on = context.manifest_after - context.manifest_before
        closed_proposals = {
            spec_number(i.title): n
            for n, i in closing_by_number.items()
            if "implements-proposal" in i.labels and spec_number(i.title) is not None
        }
        for proposal, n in sorted(closed_proposals.items()):
            if proposal not in switched_on:
                found.append(f"Closes #{n}, which implements spec#{proposal}, but does not add {proposal} to the proposals in conformance.json.")
        for proposal in sorted(switched_on - set(closed_proposals)):
            found.append(f"Adds {proposal} to the proposals in conformance.json but does not close its implementation issue.")

    if profile == "conformance":
        for n, i in sorted(linked.items()):
            if "waiting for spec" in i.labels:
                proposal = spec_number(i.title)
                if proposal is None or not context.spec_ready.get(proposal, False):
                    found.append(f'Issue #{n} is "waiting for spec" and spec#{proposal} is not ready yet.')

    return found
