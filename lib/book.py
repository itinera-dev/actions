"""Book checks: the book commit a language repository pins, and the patch that builds the book's examples against
the repository's own packages."""

import json
import pathlib
import re
import tomllib

COMMIT = re.compile(r"[0-9a-f]{40}")
DEPENDENCY_TABLES = ("dependencies", "dev-dependencies", "build-dependencies")


def pinned_commit(pin):
    """The book commit that `pin`, the parsed pin file, names.

    Raises ValueError when the pin file is not an object whose "commit" is a full commit SHA.
    """
    commit = pin.get("commit") if isinstance(pin, dict) else None
    if not isinstance(commit, str) or not COMMIT.fullmatch(commit):
        raise ValueError('The pin file must hold an object whose "commit" is a full 40-character commit SHA.')
    return commit


def publishable_packages(metadata):
    """The packages of a Cargo workspace that may be published, by name, with the directory of each, from the
    output of `cargo metadata --no-deps --format-version 1`."""
    members = set(metadata["workspace_members"])
    return {
        package["name"]: str(pathlib.PurePath(package["manifest_path"]).parent)
        for package in metadata["packages"]
        if package["id"] in members and package.get("publish") != []
    }


def dependency_sources(manifest, names):
    """Where the Cargo manifest `manifest`, parsed, takes each package of `names` from: a git URL, or "crates-io".

    Raises ValueError for a source a patch cannot replace, such as a path or another registry.
    """
    sources = set()
    for table in DEPENDENCY_TABLES:
        for key, spec in manifest.get(table, {}).items():
            name = spec.get("package", key) if isinstance(spec, dict) else key
            if name not in names:
                continue
            if isinstance(spec, dict) and spec.get("workspace"):
                raise ValueError(
                    f"The book inherits {name} from a workspace; the check patches only the book's own manifest."
                )
            if isinstance(spec, str) or ("version" in spec and not {"git", "path", "registry"} & spec.keys()):
                sources.add("crates-io")
            elif "git" in spec:
                sources.add(spec["git"])
            else:
                raise ValueError(f"The book takes {name} from a source the check cannot replace: {spec}.")
    return sources


def patch_section(sources, packages):
    """The `[patch]` tables that replace every package of `packages` with its local directory, for each source."""
    entries = "".join(
        f"{name} = {{ path = {json.dumps(path, ensure_ascii=False)} }}\n" for name, path in sorted(packages.items())
    )
    return "".join(f"\n[patch.{table_key(source)}]\n{entries}" for source in sorted(sources))


def table_key(source):
    """The key of the `[patch]` table for `source`: crates-io as is, a git URL quoted."""
    return source if source == "crates-io" else json.dumps(source, ensure_ascii=False)


def patched_manifest(text, packages):
    """The book's Cargo manifest `text` with the patch that builds it against `packages`.

    Raises ValueError when the book uses none of the packages, or already patches a source the check would patch.
    """
    manifest = tomllib.loads(text)
    sources = dependency_sources(manifest, packages)
    if not sources:
        raise ValueError(f"The book depends on none of {', '.join(sorted(packages))}.")
    clash = sources & manifest.get("patch", {}).keys()
    if clash:
        raise ValueError(f"The book already patches {', '.join(sorted(clash))}.")
    return text.rstrip("\n") + "\n" + patch_section(sources, packages)


def locked_packages(lock, packages):
    """The packages of `packages` that the book's Cargo.lock, parsed, holds, from any source."""
    return sorted({entry["name"] for entry in lock.get("package", [])} & packages.keys())


def unpatched_packages(lock, packages):
    """The packages of `packages` that the book's Cargo.lock, parsed, still takes from elsewhere than a local path."""
    return sorted({entry["name"] for entry in lock.get("package", []) if "source" in entry} & packages.keys())
