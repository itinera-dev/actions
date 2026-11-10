"""Check the `releases` section of a language's manifest: build each release's library with main's conformance
runner, run the cases at every conformance tag it claims, and write a report for each."""

import json
import os
import pathlib
import subprocess
import sys
import tempfile
from typing import NoReturn

from lib.claims import (
    CORRECTIONS_FILE,
    Entry,
    GitHubSource,
    combine,
    corrections_problems,
    library_path_problems,
    library_paths,
    minor_problems,
    releases_of,
    releases_problems,
    report_dir_of,
    section_changed,
    summary,
    summary_markdown,
)
from lib.conformance import (
    exclusion_problems,
    exclusions_report,
    language_problems,
    load_manifest,
    read_scenarios,
    report_names,
    tag_expression,
)
from lib.github_api import GitHub, GitHubError


def fail(problems) -> NoReturn:
    print("The release claims cannot be checked:")
    for problem in problems:
        print(f"::error::{problem}")
    sys.exit(1)


def event_of(env):
    path = env.get("GITHUB_EVENT_PATH")
    if not path or not pathlib.Path(path).is_file():
        return {}
    return json.loads(pathlib.Path(path).read_text(encoding="utf-8"))


def run_entry(entry, release_manifest, impossible, cases_root, combined, command, report_dir, names, env):
    """Run the cases at one claimed tag with the combined repository, writing the entry's report. Returns whether
    every selected scenario passed."""
    scenarios = read_scenarios(cases_root)
    found = exclusion_problems(scenarios, impossible)
    if found:
        entry.problems += [f"main's \"impossible\" does not fit the cases at {entry.cases}: {p}" for p in found]
        return False
    out = report_dir / report_dir_of(entry)
    out.mkdir(parents=True, exist_ok=True)
    (out / names.exclusions).write_text(json.dumps(exclusions_report(impossible), indent=2) + "\n", encoding="utf-8")
    report = out / names.cucumber
    report.unlink(missing_ok=True)
    tags = tag_expression(scenarios, release_manifest["proposals"], release_manifest["capabilities"], impossible)
    print(f"::group::{entry.release} with the cases at {entry.cases}")
    print(f"Tags: {tags}")
    result = subprocess.run(
        ["bash", "-c", command],
        cwd=combined,
        env={
            **env,
            "ITINERA_CONFORMANCE_CASES": str(cases_root / "cases"),
            "ITINERA_CONFORMANCE_TAGS": tags,
            "ITINERA_CONFORMANCE_REPORT": str(report),
        },
    )
    print("::endgroup::")
    if result.returncode != 0:
        entry.problems.append(f"The conformance runner failed with exit code {result.returncode}.")
        return False
    if not report.is_file():
        entry.problems.append(f"The conformance runner did not write {report}.")
        return False
    return True


def check(env, source):
    repo = env["REPO"]
    owner = repo.split("/")[0]
    conformance_repo = env.get("CONFORMANCE_REPO") or f"{owner}/conformance"
    report_dir = pathlib.Path(env["REPORT_DIR"]).resolve()
    manifest_path = env.get("MANIFEST") or "conformance.json"
    language = env.get("LANGUAGE", "")
    event = event_of(env)
    runner_ref = env.get("RUNNER_REF") or event.get("repository", {}).get("default_branch") or "main"

    found = language_problems(language)
    paths = library_paths(env.get("LIBRARY", ""))
    found += library_path_problems(paths)
    if found:
        fail(found)
    names = report_names(language)
    claims_name = f"claims-{language}.json" if language else "claims.json"

    try:
        text = pathlib.Path(manifest_path).read_text(encoding="utf-8")
    except (OSError, ValueError) as error:
        fail([f"{manifest_path} cannot be read: {error}"])
    manifest, found = load_manifest(manifest_path, text)
    if manifest is None:
        fail(found)
    releases = releases_of(manifest)
    found = [f"{manifest_path}: {p}" for p in releases_problems(releases)]
    if found:
        fail(found)

    pull_request = event.get("pull_request")
    if pull_request:
        before_text = source.file_at(repo, pull_request["base"]["sha"], manifest_path)
        before = json.loads(before_text) if before_text else {}
        if not section_changed(before, manifest):
            print(f"This pull request leaves the releases section of {manifest_path} as it is, so nothing is checked.")
            return
    if not releases:
        print(f"{manifest_path} has no release claims, so nothing is checked.")
        return

    work = pathlib.Path(tempfile.mkdtemp(dir=env.get("RUNNER_TEMP")))
    runner_commit = source.branch_commit(repo, runner_ref)
    runner_root = source.extract(repo, runner_commit, work / "runner")
    print(f"Runner: {repo}@{runner_ref}, at {runner_commit}.")
    main_manifest, found = load_manifest(
        f"{manifest_path} at {runner_ref}", (runner_root / manifest_path).read_text(encoding="utf-8")
    )
    if main_manifest is None:
        fail(found)
    impossible = main_manifest["impossible"]

    # Everything is read and refused before anything runs, so a malformed claim never costs a build.
    found, entries, prepared = [], [], []
    cases_roots = {}
    for release, tags in releases.items():
        release_commit = source.tag_commit(repo, release)
        if release_commit is None:
            found.append(f'"releases.{release}": {repo} has no tag {release}.')
            continue
        release_root = source.extract(repo, release_commit, work / "releases" / release)
        if not (release_root / manifest_path).is_file():
            found.append(f'"releases.{release}": the release has no {manifest_path}.')
            continue
        release_manifest, problems = load_manifest(
            f"{manifest_path} at {release}", (release_root / manifest_path).read_text(encoding="utf-8")
        )
        if release_manifest is None:
            found += problems
            continue
        if not release_manifest["proposals"]:
            found.append(f'"releases.{release}": the release lists no proposals in {manifest_path}; it claims nothing.')
            continue
        found += minor_problems(release, release_manifest["cases"], tags)
        for tag in tags:
            cases_commit = source.tag_commit(conformance_repo, tag)
            if cases_commit is None:
                found.append(f'"releases.{release}" lists "{tag}", which is not a tag of {conformance_repo}.')
                continue
            if tag not in cases_roots:
                cases_roots[tag] = source.extract(conformance_repo, cases_commit, work / "cases" / tag)
            corrections = cases_roots[tag] / CORRECTIONS_FILE
            text = corrections.read_text(encoding="utf-8") if corrections.is_file() else None
            found += corrections_problems(release, release_manifest["cases"], tag, text)
            entries.append(Entry(release, tag, release_commit, cases_commit))
        prepared.append((release, release_root, release_manifest))
    if found:
        fail(found)

    for release, release_root, release_manifest in prepared:
        combined = work / "combined" / release
        problems = combine(runner_root, release_root, paths, combined)
        print(f"{release}: the library at {release} with the runner at {runner_ref}, in {combined}.")
        for entry in (e for e in entries if e.release == release):
            entry.problems += problems
            entry.passed = not problems and run_entry(
                entry, release_manifest, impossible, cases_roots[entry.cases], combined,
                env["COMMAND"], report_dir, names, env,
            )

    report_dir.mkdir(parents=True, exist_ok=True)
    (report_dir / claims_name).write_text(
        json.dumps(summary(language, manifest_path, runner_ref, runner_commit, entries, names), indent=2) + "\n",
        encoding="utf-8",
    )
    if env.get("GITHUB_STEP_SUMMARY"):
        with open(env["GITHUB_STEP_SUMMARY"], "a", encoding="utf-8") as page:
            page.write(summary_markdown(language, runner_ref, runner_commit, entries))
    failed = [e for e in entries if not e.passed]
    if failed:
        print("Release claims that do not hold:")
        for e in failed:
            print(f"::error::{e.release} does not pass the cases at {e.cases}. " + " ".join(e.problems))
        sys.exit(1)
    print("Every release claim holds: " + ", ".join(f"{e.release} passes {e.cases}" for e in entries) + ".")


def main():
    env = os.environ
    names = report_names(env.get("LANGUAGE", ""))
    language = env.get("LANGUAGE", "")
    # The upload step reads these names, even when this run fails.
    with open(env["GITHUB_OUTPUT"], "a", encoding="utf-8") as output:
        suffix = f"-{language}" if language and not language_problems(language) else ""
        output.write(f"artifact=release-claims{suffix}\nclaims=claims{suffix}.json\ncucumber={names.cucumber}\n"
                     f"exclusions={names.exclusions}\n")
    try:
        check(env, GitHubSource(GitHub(env["GH_TOKEN"])))
    except GitHubError as error:
        fail([str(error)])


if __name__ == "__main__":
    main()
