"""Publish a workspace package's version to npm, unless that version is there already."""

import json
import os
import pathlib
import subprocess
import sys

from lib.npm import npm_versions, package_of
from lib.registry import RegistryError


def main():
    directory = os.environ["PACKAGE"].rstrip("/")
    path = f"{directory}/package.json"
    try:
        name, version = package_of(json.loads(pathlib.Path(path).read_text(encoding="utf-8")))
    except (OSError, ValueError) as error:
        print(f"::error::{path} cannot be read: {error}")
        sys.exit(1)
    try:
        published = version in npm_versions(name)
    except RegistryError as error:
        print(f"::error::npm cannot be read: {error}")
        sys.exit(1)
    if published:
        print(f"::notice::{name} {version} is on npm already; nothing is published.")
        return
    sys.exit(subprocess.run(["npm", "publish", "--workspace", directory], check=False).returncode)


if __name__ == "__main__":
    main()
