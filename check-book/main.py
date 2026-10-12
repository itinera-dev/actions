"""Run the examples of the book at the commit this repository pins, built against this repository's own packages."""

import json
import os
import pathlib
import shlex
import subprocess
import sys
import tempfile
import tomllib
from typing import NoReturn

from lib.book import locked_packages, patched_manifest, pinned_commit, publishable_packages, unpatched_packages
from lib.github_api import GitHub, GitHubError


def fail(message) -> NoReturn:
    print(f"::error::{message}")
    sys.exit(1)


def main():
    env = os.environ
    owner = env["REPO"].split("/")[0]
    book_repo = env.get("BOOK_REPO") or f"{owner}/book"
    try:
        commit = pinned_commit(json.loads(pathlib.Path(env["PIN"]).read_text(encoding="utf-8")))
    except (OSError, ValueError) as error:
        fail(f"{env['PIN']} cannot be read: {error}")

    metadata = subprocess.run(
        ["cargo", "metadata", "--no-deps", "--format-version", "1"], stdout=subprocess.PIPE, text=True
    )
    if metadata.returncode != 0:
        fail("cargo metadata failed in this repository; its output is above.")
    packages = publishable_packages(json.loads(metadata.stdout))
    cargo_env = {name: value for name, value in env.items() if name != "GH_TOKEN"}

    work = tempfile.mkdtemp(dir=env.get("RUNNER_TEMP"))
    try:
        root = GitHub(env["GH_TOKEN"]).extract_repository(book_repo, commit, work)
    except GitHubError as error:
        fail(f"The book at {book_repo}@{commit} cannot be downloaded: {error}")
    book = root / env["BOOK_DIR"]
    manifest = book / "Cargo.toml"
    try:
        manifest.write_text(patched_manifest(manifest.read_text(encoding="utf-8"), packages), encoding="utf-8")
    except (OSError, ValueError) as error:
        fail(f"The book's {env['BOOK_DIR']}/Cargo.toml cannot be patched: {error}")

    lock = book / "Cargo.lock"
    if not lock.exists():
        subprocess.run(["cargo", "generate-lockfile"], cwd=book, env=cargo_env, check=True)
    names = locked_packages(tomllib.loads(lock.read_text(encoding="utf-8")), packages)
    if names:
        update = ["cargo", "update", *(f"--package={name}" for name in names)]
        subprocess.run(update, cwd=book, env=cargo_env, check=True)
    left = unpatched_packages(tomllib.loads(lock.read_text(encoding="utf-8")), packages)
    if left:
        fail(
            f"The book still takes {', '.join(left)} from elsewhere than this repository: its requirement may not"
            " accept this repository's version, so the book needs a matching change."
        )

    print(f"Running the book {book_repo}@{commit} against {', '.join(sorted(packages))}.", flush=True)
    sys.exit(subprocess.run(shlex.split(env["COMMAND"]), cwd=book, env=cargo_env).returncode)


if __name__ == "__main__":
    main()
