"""Run the examples of the book at the commit this repository pins, against this repository's own packages."""

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

    work = tempfile.mkdtemp(dir=env.get("RUNNER_TEMP"))
    try:
        root = GitHub(env["GH_TOKEN"]).extract_repository(book_repo, commit, work)
    except GitHubError as error:
        fail(f"The book at {book_repo}@{commit} cannot be downloaded: {error}")
    book = root / env["BOOK_DIR"]
    run_env = {name: value for name, value in env.items() if name != "GH_TOKEN"}
    if (book / "Cargo.toml").is_file():
        command = shlex.split(env["COMMAND"] or "cargo test")
        run_cargo_book(book, env["BOOK_DIR"], f"{book_repo}@{commit}", command, run_env)
    elif (book / "package.json").is_file():
        command = shlex.split(env["COMMAND"] or "npm test")
        run_npm_book(book, env["BOOK_DIR"], f"{book_repo}@{commit}", command, run_env)
    else:
        fail(f"The book at {book_repo}@{commit} has neither a Cargo.toml nor a package.json in {env['BOOK_DIR']}.")


def run_cargo_book(book, book_dir, pinned, command, cargo_env):
    """Run `command` in the Rust book at `book`, built against this Cargo workspace's own crates through a patch."""
    metadata = subprocess.run(
        ["cargo", "metadata", "--no-deps", "--format-version", "1"], stdout=subprocess.PIPE, text=True
    )
    if metadata.returncode != 0:
        fail("cargo metadata failed in this repository; its output is above.")
    packages = publishable_packages(json.loads(metadata.stdout))

    manifest = book / "Cargo.toml"
    try:
        manifest.write_text(patched_manifest(manifest.read_text(encoding="utf-8"), packages), encoding="utf-8")
    except (OSError, ValueError) as error:
        fail(f"The book's {book_dir}/Cargo.toml cannot be patched: {error}")

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

    print(f"Running the book {pinned} against {', '.join(sorted(packages))}.", flush=True)
    sys.exit(subprocess.run(command, cwd=book, env=cargo_env).returncode)


def run_npm_book(book, book_dir, pinned, command, npm_env):
    """Run `command` in the TypeScript book at `book`, against this repository's itinera as it stands.

    The book's `npm run itinera` packs the checkout ITINERA_TS names instead of the commit the book pins, and
    `npm install`, rather than `npm ci`, accepts this repository's dependencies where they differ from the book's
    lockfile.
    """
    print(f"Running the book {pinned} against {os.getcwd()} as it stands.", flush=True)
    npm_env = npm_env | {"ITINERA_TS": os.getcwd()}
    for step in (["npm", "run", "itinera"], ["npm", "install", "--no-audit", "--no-fund"], command):
        try:
            returncode = subprocess.run(step, cwd=book, env=npm_env).returncode
        except OSError as error:
            fail(f"{shlex.join(step)} cannot be run in the book's {book_dir}: {error}")
        if returncode != 0:
            fail(f"{shlex.join(step)} failed in the book's {book_dir}; its output is above.")


if __name__ == "__main__":
    main()
