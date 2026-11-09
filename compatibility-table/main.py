"""Build the compatibility table from the releases, reports and manifests of the repositories listed."""

import datetime
import json
import os
import pathlib
import sys
import tempfile
from typing import NoReturn

from lib.compatibility import TableError, load_repositories, table_rows
from lib.compatibility_page import row_page, summary_page
from lib.compatibility_source import Source
from lib.github_api import GitHub, GitHubError


def fail(message) -> NoReturn:
    print(f"::error::{message}")
    sys.exit(1)


def main():
    env = os.environ
    owner = env["GITHUB_REPOSITORY"].split("/")[0]
    conformance = env.get("CONFORMANCE_REPO") or f"{owner}/conformance"
    spec = env.get("SPEC_REPO") or f"{owner}/spec"
    try:
        repositories = load_repositories(pathlib.Path(env["REPOSITORIES"]).read_text(encoding="utf-8"))
    except OSError as error:
        fail(f"{env['REPOSITORIES']} cannot be read: {error}")
    except TableError as error:
        fail(str(error))

    work = tempfile.mkdtemp(dir=env.get("RUNNER_TEMP"))
    source = Source(GitHub(env["GH_TOKEN"]), conformance, work)
    try:
        titles = source.titles(spec)
        rows = table_rows(source, repositories, conformance)
    except GitHubError as error:
        fail(f"The table cannot be built: {error}")

    generated = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    output = pathlib.Path(env["OUTPUT"])
    output.mkdir(parents=True, exist_ok=True)
    (output / "index.html").write_text(summary_page(rows, generated), encoding="utf-8")
    spec_url = f"https://github.com/{spec}"
    for row in rows:
        if "error" not in row:
            (output / row["page"]).write_text(row_page(row, titles, spec_url, generated), encoding="utf-8")
    table = {"generated": generated, "proposals": titles, "rows": rows}
    (output / "table.json").write_text(json.dumps(table, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    errors = [row for row in rows if "error" in row]
    for row in errors:
        print(f"::warning::{row['implementation']} {row['tag']}: {row['error']}")
    print(f"The table holds {len(rows)} rows from {len(repositories)} repositories, {len(errors)} of them errors.")


if __name__ == "__main__":
    main()
