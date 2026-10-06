"""Conformance runs: the manifest, the scenarios of the cases, the tag expression and the exclusions report."""

import re
from dataclasses import dataclass, field

PROPOSAL_TAG = re.compile(r"@proposal-(\d+)")
CAPABILITY_TAG = re.compile(r"@capability-[\w-]+")
SCENARIO_KEYWORDS = ("Scenario Outline:", "Scenario Template:", "Scenario:", "Example:")


@dataclass
class Scenario:
    feature: str
    name: str
    tags: set = field(default_factory=set)

    def proposals(self):
        return {int(m.group(1)) for tag in self.tags if (m := PROPOSAL_TAG.fullmatch(tag))}


def parse_tags(line):
    return set(line.split("#", 1)[0].split())


def parse_feature(path, text):
    """The scenarios of a feature file, each with the tags it inherits from its feature and rule.

    A scenario outline counts once, under its own name, with the tags of all its examples.
    """
    scenarios = []
    feature_tags, rule_tags, pending = set(), set(), set()
    current = None
    in_doc_string = None
    for raw in text.splitlines():
        line = raw.strip()
        if in_doc_string:
            if line.startswith(in_doc_string):
                in_doc_string = None
            continue
        if line.startswith('"""') or line.startswith("```"):
            in_doc_string = line[:3]
            continue
        if line.startswith("@"):
            pending |= parse_tags(line)
            continue
        if line.startswith("Feature:"):
            feature_tags, rule_tags, current = pending, set(), None
        elif line.startswith("Rule:"):
            rule_tags, current = pending, None
        elif line.startswith(SCENARIO_KEYWORDS):
            name = line.split(":", 1)[1].strip()
            current = Scenario(path, name, feature_tags | rule_tags | pending)
            scenarios.append(current)
        elif line.startswith(("Examples:", "Scenarios:")) and current is not None:
            current.tags |= pending
        elif line.startswith("Background:"):
            current = None
        else:
            continue
        pending = set()
    return scenarios


def manifest_problems(manifest):
    """What is wrong with the shape of a conformance.json manifest."""
    found = []
    if not isinstance(manifest.get("cases"), str) or not manifest.get("cases"):
        found.append('"cases" must be the tag of the conformance cases, for example "v0.1.0".')
    proposals = manifest.get("proposals")
    if not isinstance(proposals, list) or not all(isinstance(n, int) and not isinstance(n, bool) for n in proposals):
        found.append('"proposals" must be a list of proposal numbers.')
    capabilities = manifest.get("capabilities")
    if not isinstance(capabilities, list) or not all(isinstance(c, str) for c in capabilities):
        found.append('"capabilities" must be a list of capability names.')
    impossible = manifest.get("impossible")
    if not isinstance(impossible, dict):
        found.append('"impossible" must map each excluded tag to its scenarios.')
        return found
    for tag, entries in impossible.items():
        if not isinstance(entries, list):
            found.append(f'"impossible.{tag}" must be a list of scenarios.')
            continue
        for entry in entries:
            proof = entry.get("proof") if isinstance(entry, dict) else None
            if (
                not isinstance(entry, dict)
                or not isinstance(entry.get("feature"), str)
                or not isinstance(entry.get("scenario"), str)
                or not isinstance(proof, dict)
                or not isinstance(proof.get("test"), str)
                or not isinstance(proof.get("file"), str)
            ):
                found.append(
                    f'Each entry of "impossible.{tag}" needs "feature", "scenario" and "proof" with "test" and "file".'
                )
    return found


def exclusion_problems(scenarios, impossible):
    """Excluded scenarios without an entry, and entries that name no scenario carrying their tag."""
    found = []
    for tag, entries in impossible.items():
        declared = {(e["feature"], e["scenario"]) for e in entries}
        for s in scenarios:
            if f"@{tag}" in s.tags and (s.feature, s.name) not in declared:
                found.append(f'"{s.name}" in {s.feature} carries @{tag} but has no entry in "impossible.{tag}".')
        for feature, name in sorted(declared):
            matching = [s for s in scenarios if s.feature == feature and s.name == name]
            if not matching:
                found.append(f'"impossible.{tag}" names "{name}" in {feature}, which does not exist in the cases.')
            elif not any(f"@{tag}" in s.tags for s in matching):
                found.append(f'"impossible.{tag}" names "{name}" in {feature}, which does not carry @{tag}.')
    return found


def tag_expression(scenarios, proposals, capabilities, impossible):
    """The Cucumber tag expression selecting the scenarios whose proposals are all listed.

    It leaves out the capabilities not claimed and the tags excluded as impossible. Only called with proposals listed.
    """
    listed = sorted(set(proposals))
    present_proposals = set().union(*(s.proposals() for s in scenarios))
    present_capabilities = {t for s in scenarios for t in s.tags if CAPABILITY_TAG.fullmatch(t)}
    claimed = {f"@capability-{c}" for c in capabilities}
    parts = ["(" + " or ".join(f"@proposal-{n:04d}" for n in listed) + ")"]
    parts += [f"not @proposal-{n:04d}" for n in sorted(present_proposals - set(listed))]
    parts += [f"not {t}" for t in sorted(present_capabilities - claimed)]
    parts += [f"not @{t}" for t in sorted(impossible)]
    return " and ".join(parts)


def exclusions_report(impossible):
    """The exclusions file: every excluded scenario, its tag and its proof."""
    return [
        {"feature": e["feature"], "scenario": e["scenario"], "tag": tag, "proof": e["proof"]}
        for tag in sorted(impossible)
        for e in impossible[tag]
    ]
