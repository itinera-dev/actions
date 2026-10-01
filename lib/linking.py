"""Whether a pull request's linked issues allow it to be merged."""

from dataclasses import dataclass, field

from .proposals import proposal_numbers

PROFILES = ("default", "spec", "implementation")
SPEC_ISSUE_LABELS = {"process", "spec defect", "proposal"}


@dataclass
class Issue:
    number: int
    open: bool
    labels: set = field(default_factory=set)


def problems(profile, issues, added_files):
    """Why the pull request cannot be merged; empty when it can.

    `issues` are the issues linked to the pull request in its own repository,
    `added_files` the paths it adds.
    """
    if profile not in PROFILES:
        return [f'Unknown profile "{profile}"; expected one of {", ".join(PROFILES)}.']

    found = []
    by_number = {i.number: i for i in issues}
    if not by_number:
        found.append('Not linked to any issue in this repository. Add "Closes #N" to the description.')
    found += [f"Issue #{n} is closed; link an open issue." for n, i in sorted(by_number.items()) if not i.open]

    if profile == "spec":
        proposals = proposal_numbers(added_files)
        for n in proposals:
            if n not in by_number:
                found.append(f'Adds the file of proposal {n:04d} but is not linked to #{n}. Add "Closes #{n}".')
            elif not {"proposal", "status: ready"} <= by_number[n].labels:
                found.append(f'Issue #{n} must be labelled "proposal" and "status: ready" before its proposal file is merged.')
        if by_number and not proposals and not any(i.labels & SPEC_ISSUE_LABELS for i in by_number.values()):
            found.append('Link an issue labelled "process", "spec defect" or "proposal".')

    if profile == "implementation":
        found += [
            f'Issue #{n} is still "waiting for spec": its proposal is not accepted yet.'
            for n, i in sorted(by_number.items())
            if {"implements-proposal", "waiting for spec"} <= i.labels
        ]

    return found
