"""The compatibility table: what every release of every language claims, and what its conformance report shows."""

import json
import re
from dataclasses import dataclass, field

from lib.conformance import load_manifest, report_names
from lib.release import tier, tier_problems

CASES_PATH = re.compile(r"(?:^|.*/)(cases/tier-\d+/.+\.feature)$")
PLACEHOLDER = re.compile(r"<[^<>]+>")
UNSAFE = re.compile(r"[^A-Za-z0-9._-]+")
NAMED_REPORT = re.compile(r"(cucumber|exclusions)-([a-z][a-z0-9-]*)\.json")
REPOSITORY = re.compile(r"[\w.-]+/[\w.-]+")

PASSED = "passed"
EXCLUDED = "excluded"
NOT_RUN = "not-run"
FAILED = "failed"
STATUSES = (PASSED, EXCLUDED, NOT_RUN, FAILED)


class TableError(Exception):
    """A release, or a list of repositories, that the table cannot read, with the reason a reader is shown."""


def load_repositories(text):
    """The repositories listed in the conformance repository's list of implementations."""
    try:
        listed = json.loads(text)
    except ValueError as error:
        raise TableError(f"The list of repositories cannot be read: {error}") from error
    repositories = listed.get("repositories") if isinstance(listed, dict) else None
    if (
        not isinstance(repositories, list)
        or not repositories
        or not all(isinstance(r, str) and REPOSITORY.fullmatch(r) for r in repositories)
    ):
        raise TableError('The list of repositories must hold "repositories", a list such as ["owner/name"].')
    names = [r.split("/")[1] for r in repositories]
    if len(set(names)) != len(names):
        raise TableError("The list of repositories names two repositories of the same name.")
    return repositories


def report_languages(asset_names):
    """The languages whose reports a release carries: [""] for a repository holding one, the names its files carry
    for one holding several, and [] for a release without reports."""
    names = set(asset_names)
    plain = report_names("")
    has_plain = plain.cucumber in names or plain.exclusions in names
    named = {m.group(2) for n in names if (m := NAMED_REPORT.fullmatch(n))}
    if has_plain and named:
        raise TableError(
            "The release carries both a plain report and reports named for their languages, so its rows cannot be told"
            " apart."
        )
    languages = [""] if has_plain else sorted(named)
    for language in languages:
        files = report_names(language)
        missing = [f for f in (files.cucumber, files.exclusions) if f not in names]
        if missing:
            raise TableError(f"The release carries no {' or '.join(missing)}.")
    return languages


def manifest_name(language, files):
    """The manifest a row reads its claim from, among the `files` of the repository at the release's tag."""
    if language and f"conformance-{language}.json" in files:
        return f"conformance-{language}.json"
    if "conformance.json" in files:
        return "conformance.json"
    wanted = f"conformance-{language}.json or conformance.json" if language else "conformance.json"
    raise TableError(f"The repository has no {wanted} at the release's tag.")


def read_manifest(name, text):
    manifest, problems = load_manifest(name, text)
    if manifest is None:
        raise TableError(" ".join(problems))
    return manifest


def feature_path(uri):
    """The path of a feature from the folder `cases/tier-N/` of the conformance repository, from a report's uri, which
    each runner writes in its own form."""
    match = CASES_PATH.search(uri.replace("\\", "/"))
    return match.group(1) if match else None


def listed(value):
    """`value` when it is a list, else nothing."""
    return value if isinstance(value, list) else []


def element_passed(element):
    statuses = [
        s["result"].get("status") if isinstance(s, dict) and isinstance(s.get("result"), dict) else None
        for key in ("before", "steps", "after")
        for s in listed(element.get(key))
    ]
    return all(status == "passed" for status in statuses)


def report_results(text):
    """Whether each scenario of a Cucumber JSON report passed, by its feature and name.

    A scenario outline counts once, and it passes only when every one of its examples passed, in every run of it.
    """
    try:
        features = json.loads(text)
    except ValueError as error:
        raise TableError(f"The Cucumber report cannot be read: {error}") from error
    if not isinstance(features, list):
        raise TableError("The Cucumber report must hold a list of features.")
    results = {}
    for feature in features:
        uri = feature.get("uri") if isinstance(feature, dict) else None
        path = feature_path(uri) if isinstance(uri, str) else None
        if path is None:
            continue
        for element in listed(feature.get("elements")):
            if not isinstance(element, dict) or element.get("type") == "background":
                continue
            if not isinstance(element.get("name"), str):
                continue
            key = (path, element["name"])
            results[key] = results.get(key, True) and element_passed(element)
    return results


def report_exclusions(text):
    """The scenarios a report's exclusions file excludes, by feature and name, each with its tag and proof."""
    try:
        entries = json.loads(text)
    except ValueError as error:
        raise TableError(f"The exclusions file cannot be read: {error}") from error
    if not isinstance(entries, list) or not all(
        isinstance(e, dict) and isinstance(e.get("feature"), str) and isinstance(e.get("scenario"), str)
        for e in entries
    ):
        raise TableError('The exclusions file must hold a list of entries with "feature" and "scenario".')
    return {(e["feature"], e["scenario"]): {**e, "proof": proof_of(e)} for e in entries}


def proof_of(entry):
    """An exclusion's proof, its test and file, when both are text, else nothing."""
    proof = entry.get("proof")
    if isinstance(proof, dict) and isinstance(proof.get("test"), str) and isinstance(proof.get("file"), str):
        return {"test": proof["test"], "file": proof["file"]}
    return {}


def scenario_result(scenario, results):
    """Whether a scenario passed, as `results` show it, or None when it is not in them.

    A report names each example of an outline with its placeholders filled in, so an outline whose name holds them
    matches every name it could take.
    """
    key = (scenario.feature, scenario.name)
    if key in results or not PLACEHOLDER.search(scenario.name):
        return results.get(key)
    parts = PLACEHOLDER.split(scenario.name)
    pattern = re.compile(".*?".join(re.escape(part) for part in parts), re.DOTALL)
    found = [passed for (feature, name), passed in results.items() if feature == key[0] and pattern.fullmatch(name)]
    return all(found) if found else None


@dataclass
class Outcome:
    """What a row's report shows for one scenario of the cases: its status, and why, when it did not pass."""

    feature: str
    name: str
    proposals: set
    status: str
    reason: str = ""
    proof: dict = field(default_factory=dict)


def outcome(scenario, manifest, results, exclusions):
    key = (scenario.feature, scenario.name)
    if key in exclusions:
        entry = exclusions[key]
        tag = entry.get("tag") if isinstance(entry.get("tag"), str) else ""
        return Outcome(*key, scenario.proposals(), EXCLUDED, f"@{tag}", entry["proof"])
    passed = scenario_result(scenario, results)
    if passed is not None:
        return Outcome(*key, scenario.proposals(), PASSED if passed else FAILED, "" if passed else "It failed.")
    unclaimed = sorted(
        t.removeprefix("@capability-")
        for t in scenario.tags
        if t.startswith("@capability-") and t.removeprefix("@capability-") not in manifest["capabilities"]
    )
    unlisted = sorted(scenario.proposals() - set(manifest["proposals"]))
    if unclaimed:
        return Outcome(*key, scenario.proposals(), NOT_RUN, f"It needs {', '.join(unclaimed)}, which is not claimed.")
    if unlisted:
        listed = ", ".join(f"{n:04d}" for n in unlisted)
        return Outcome(*key, scenario.proposals(), NOT_RUN, f"Proposal {listed} is not listed in the manifest.")
    return Outcome(*key, scenario.proposals(), FAILED, "It is missing from the report.")


def tiers_claimed(scenarios, manifest):
    """The highest tier whose proposals, and those of every tier before it, the manifest lists, or 0."""
    tiers = sorted({t for s in scenarios if (t := tier(s)) is not None})
    claimed = 0
    for n in tiers:
        if tier_problems(scenarios, manifest["proposals"], manifest["capabilities"], n, "the manifest"):
            break
        claimed = n
    return claimed


def counts(outcomes):
    tally = {status: 0 for status in STATUSES}
    for o in outcomes:
        tally[o.status] += 1
    tally["scenarios"] = len(outcomes)
    return tally


def by_proposal(outcomes):
    """The counts of each proposal, a scenario counting under every proposal it carries."""
    numbers = sorted(set().union(*(o.proposals for o in outcomes)))
    return {n: counts([o for o in outcomes if n in o.proposals]) for n in numbers}


def row_results(scenarios, manifest, cucumber, exclusions):
    """What a row shows: its tiers, its counts overall and by proposal, and every scenario that did not pass."""
    results = report_results(cucumber)
    excluded = report_exclusions(exclusions)
    outcomes = [outcome(s, manifest, results, excluded) for s in scenarios]
    return {
        "cases": manifest["cases"],
        "tiers": tiers_claimed(scenarios, manifest),
        "capabilities": sorted(manifest["capabilities"]),
        "totals": counts(outcomes),
        "proposals": {f"{n:04d}": c for n, c in by_proposal(outcomes).items()},
        "not_passed": [
            {
                "feature": o.feature,
                "scenario": o.name,
                "proposals": [f"{n:04d}" for n in sorted(o.proposals)],
                "status": o.status,
                "reason": o.reason,
                **({"proof": o.proof} if o.proof else {}),
            }
            for o in outcomes
            if o.status != PASSED
        ],
    }


def proposal_title(text):
    """The title a proposal file's first heading gives, such as "Foundations" for "# 0002: Foundations"."""
    for line in text.splitlines():
        if line.startswith("# "):
            return line[2:].split(":", 1)[-1].strip()
    return ""


def row_slug(repository, tag, language):
    """The file name of a row's page, with every character a file name or an address could misread replaced."""
    name = repository.split("/")[-1]
    return UNSAFE.sub("-", "-".join(part for part in (name, tag, language) if part)) + ".html"


def implementation(repository, language):
    """How a row's implementation is named: its repository, and its language when the repository holds several."""
    name = repository.split("/")[-1]
    return f"{name} {language}" if language else name


def release_rows(source, repository, release, conformance):
    """The rows of one release: one for each language whose report it carries, or one holding the error that keeps
    the release from being read."""
    tag = release["tag_name"]
    base = {
        "repository": repository,
        "tag": tag,
        "prerelease": bool(release.get("prerelease")),
        "published": (release.get("published_at") or "")[:10],
        "conformance": conformance,
    }
    try:
        assets = {a["name"]: a for a in release.get("assets", [])}
        languages = report_languages(assets)
        if not languages:
            raise TableError("The release carries no conformance report.")
        files = source.files(repository, tag)
    except TableError as error:
        return [{**base, "language": "", "implementation": implementation(repository, ""), "error": str(error)}]
    rows = []
    for language in languages:
        row = {**base, "language": language, "implementation": implementation(repository, language)}
        try:
            name = manifest_name(language, files)
            manifest = read_manifest(name, source.text(repository, name, tag))
            reports = report_names(language)
            results = row_results(
                source.scenarios(manifest["cases"]),
                manifest,
                source.asset(repository, assets[reports.cucumber]),
                source.asset(repository, assets[reports.exclusions]),
            )
            rows.append({**row, "manifest": name, "page": row_slug(repository, tag, language), **results})
        except TableError as error:
            rows.append({**row, "error": str(error)})
    return rows


def table_rows(source, repositories, conformance):
    """Every row of the table: the repositories in their listed order, each one's releases newest first, drafts
    left out."""
    rows = []
    for repository in repositories:
        releases = [r for r in source.releases(repository) if not r.get("draft")]
        releases.sort(key=lambda r: r.get("published_at") or "", reverse=True)
        found = [row for release in releases for row in release_rows(source, repository, release, conformance)]
        rows += for_each_language(found)
    return rows


def for_each_language(rows):
    """The rows of one repository, with the error of a release whose languages could not be told shown under every
    language its other releases have, so that no language's latest row hides it."""
    languages = sorted({row["language"] for row in rows if row["language"]})
    if not languages:
        return rows
    spread = []
    for row in rows:
        if row["language"] or "error" not in row:
            spread.append(row)
            continue
        spread += [
            {**row, "language": language, "implementation": implementation(row["repository"], language)}
            for language in languages
        ]
    return spread
