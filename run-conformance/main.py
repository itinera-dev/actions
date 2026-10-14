"""Run the conformance cases pinned in conformance.json with the language's runner, and write the report."""

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
    manifest_problems,
    read_scenarios,
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

    try:
        manifest = json.loads(pathlib.Path("conformance.json").read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        fail([f"conformance.json cannot be read: {error}"])
    if not isinstance(manifest, dict):
        fail(["conformance.json must hold an object."])
    found = manifest_problems(manifest)
    if found:
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
    report = report_dir / "cucumber.json"
    (report_dir / "exclusions.json").write_text(
        json.dumps(exclusions_report(manifest["impossible"]), indent=2) + "\n", encoding="utf-8"
    )

    if not manifest["proposals"]:
        report.write_text("[]\n", encoding="utf-8")
        print("No proposals are listed in conformance.json yet, so no scenario runs.")
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
