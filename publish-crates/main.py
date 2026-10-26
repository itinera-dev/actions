"""Publish every crate of the workspace whose version is not on crates.io yet."""

import json
import subprocess
import sys

from lib.crates_io import crate_versions, publishable_versions, unpublished
from lib.registry import RegistryError


def main():
    metadata = subprocess.run(
        ["cargo", "metadata", "--no-deps", "--format-version", "1"], stdout=subprocess.PIPE, text=True
    )
    if metadata.returncode != 0:
        print("::error::cargo metadata failed in this repository; its output is above.")
        sys.exit(1)
    versions = publishable_versions(json.loads(metadata.stdout))
    try:
        published = {name: crate_versions(name) for name in versions}
    except RegistryError as error:
        print(f"::error::crates.io cannot be read: {error}")
        sys.exit(1)
    names = unpublished(versions, published)
    for name in sorted(set(versions) - set(names)):
        print(f"::notice::{name} {versions[name]} is on crates.io already; it is not published again.")
    if not names:
        return
    command = ["cargo", "publish", "--locked", *(f"--package={name}" for name in names)]
    sys.exit(subprocess.run(command, check=False).returncode)


if __name__ == "__main__":
    main()
