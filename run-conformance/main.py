"""Run the conformance cases pinned in a language's manifest with its runner, and write the report."""

import json
import os
import pathlib
import subprocess
import sys
import tempfile
from typing import NoReturn

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
    print("Conformance failed:")
    for problem in problems:
        print(f"::error::{problem}")
    sys.exit(1)


def main():
    env = os.environ
    owner = env["REPO"].split("/")[0]
    conformance_repo = env.get("CONFORMANCE_REPO") or f"{owner}/conformance"
    report_dir = pathlib.Path(env["REPORT_DIR"]).resolve()
    manifest_path = env.get("MANIFEST") or "conformance.json"
    language = env.get("LANGUAGE", "")

    found = language_problems(language)
    if found:
        fail(found)
    names = report_names(language)
    # The upload step reads these names, even when this run fails.
    with open(env["GITHUB_OUTPUT"], "a", encoding="utf-8") as output:
        output.write(f"artifact={names.artifact}\ncucumber={names.cucumber}\nexclusions={names.exclusions}\n")

    try:
        text = pathlib.Path(manifest_path).read_text(encoding="utf-8")
    except (OSError, ValueError) as error:
        fail([f"{manifest_path} cannot be read: {error}"])
    manifest, found = load_manifest(manifest_path, text)
    if manifest is None:
        fail(found)

    work = tempfile.mkdtemp(dir=env.get("RUNNER_TEMP"))
    try:
        root = GitHub(env["GH_TOKEN"]).extract_repository(conformance_repo, manifest["cases"], work)
    except GitHubError as error:
        fail([f"The cases at {conformance_repo}@{manifest['cases']} cannot be downloaded: {error}"])
    scenarios = read_scenarios(root)
    print(f"Cases: {conformance_repo}@{manifest['cases']}, {len(scenarios)} scenarios.")

    found = exclusion_problems(scenarios, manifest["impossible"])
    if found:
        fail(found)

    report_dir.mkdir(parents=True, exist_ok=True)
    report = report_dir / names.cucumber
    (report_dir / names.exclusions).write_text(
        json.dumps(exclusions_report(manifest["impossible"]), indent=2) + "\n", encoding="utf-8"
    )

    if not manifest["proposals"]:
        report.write_text("[]\n", encoding="utf-8")
        print(f"No proposals are listed in {manifest_path} yet, so no scenario runs.")
        return

    tags = tag_expression(scenarios, manifest["proposals"], manifest["capabilities"], manifest["impossible"])
    print(f"Tags: {tags}")
    report.unlink(missing_ok=True)
    run_env = {
        **env,
        "ITINERA_CONFORMANCE_CASES": str(root / "cases"),
        "ITINERA_CONFORMANCE_TAGS": tags,
        "ITINERA_CONFORMANCE_REPORT": str(report),
    }
    result = subprocess.run(["bash", "-c", env["COMMAND"]], env=run_env)
    if result.returncode != 0:
        fail([f"The conformance runner failed with exit code {result.returncode}."])
    if not report.is_file():
        fail([f"The conformance runner did not write {report}."])


if __name__ == "__main__":
    main()
