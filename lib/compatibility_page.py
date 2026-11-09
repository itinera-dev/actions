"""The compatibility table's pages: a summary of every row, and a page for each row with its counts by proposal."""

from html import escape
from urllib.parse import quote

from lib.compatibility import EXCLUDED, FAILED, NOT_RUN

STYLE = """
:root { color-scheme: light dark; --text: #1b1b1f; --muted: #55565e; --background: #ffffff;
  --surface: #f3f3f6; --line: #d4d4dc; --link: #1f4fb8; --error: #a3191f; }
@media (prefers-color-scheme: dark) {
  :root { --text: #e8e8ee; --muted: #a9aab4; --background: #16161a; --surface: #222228; --line: #3a3a44;
    --link: #8fb1ff; --error: #ff8a8f; }
}
* { box-sizing: border-box; }
body { margin: 0; background: var(--background); color: var(--text);
  font: 1rem/1.55 system-ui, -apple-system, "Segoe UI", sans-serif; }
main { max-width: 72rem; margin: 0 auto; padding: 1.5rem 1rem 3rem; }
a { color: var(--link); }
h1 { font-size: 1.75rem; line-height: 1.25; margin: 0 0 0.75rem; }
h2 { font-size: 1.3rem; margin: 2rem 0 0.75rem; }
p, li { max-width: 46rem; }
.scroll { overflow-x: auto; margin: 0 0 1rem; }
table { border-collapse: collapse; width: 100%; font-size: 0.95rem; }
caption { text-align: left; font-weight: 600; padding: 0 0 0.5rem; }
th, td { border-bottom: 1px solid var(--line); padding: 0.45rem 0.6rem; text-align: left; vertical-align: top; }
thead th { background: var(--surface); }
td.number, th.number { text-align: right; font-variant-numeric: tabular-nums; }
.error { color: var(--error); font-weight: 600; }
details { border: 1px solid var(--line); border-radius: 0.4rem; margin: 0 0 0.75rem; padding: 0 0.9rem; }
details[open] { padding-bottom: 0.75rem; }
summary { cursor: pointer; padding: 0.6rem 0; font-weight: 600; }
summary:focus-visible, a:focus-visible { outline: 2px solid var(--link); outline-offset: 2px; }
footer { color: var(--muted); font-size: 0.9rem; margin-top: 2.5rem; }
"""

COLUMNS = (("passed", "Passed"), (EXCLUDED, "Excluded with proof"), (NOT_RUN, "Not run"), (FAILED, "Failed or missing"))


def page(title, body, generated, home: str | None = "index.html"):
    back = "" if home is None else f'<p><a href="{home}">Every release</a></p>\n'
    return (
        "<!doctype html>\n"
        '<html lang="en">\n<head>\n<meta charset="utf-8">\n'
        '<meta name="viewport" content="width=device-width, initial-scale=1">\n'
        '<link rel="icon" href="data:,">\n'
        f"<title>{escape(title)}</title>\n<style>{STYLE}</style>\n</head>\n<body>\n<main>\n{back}{body}"
        f'<footer><p>Rebuilt on {escape(generated)} from every release\'s conformance report. Part of '
        '<a href="https://itinera-dev.org/">Itinera</a>.</p></footer>\n'
        "</main>\n</body>\n</html>\n"
    )


def count_cells(totals):
    return "".join(f'<td class="number">{totals[key]}</td>' for key, _ in COLUMNS)


def count_headers():
    return "".join(f'<th scope="col" class="number">{label}</th>' for _, label in COLUMNS)


def link(url, text):
    return f'<a href="{escape(url, quote=True)}">{escape(text)}</a>'


def release_cell(row):
    marker = " (pre-release)" if row["prerelease"] else ""
    if "error" in row:
        return f"{escape(row['tag'])}{marker}"
    return f"{link(row['page'], row['tag'])}{marker}"


def summary_rows(rows):
    lines = []
    for row in rows:
        head = (
            f'<tr><th scope="row">{escape(row["implementation"])}</th><td>{release_cell(row)}</td>'
            f"<td>{escape(row['published'])}</td>"
        )
        if "error" in row:
            lines.append(f'{head}<td colspan="7" class="error">Error: {escape(row["error"])}</td></tr>')
            continue
        tiers = str(row["tiers"]) if row["tiers"] else "none"
        lines.append(
            f"{head}<td>{escape(row['cases'])}</td><td>{tiers}</td>"
            f"<td>{escape(', '.join(row['capabilities']) or 'none')}</td>{count_cells(row['totals'])}</tr>"
        )
    return "\n".join(lines)


def summary_table(caption, rows):
    return (
        f'<div class="scroll"><table>\n<caption>{escape(caption)}</caption>\n<thead><tr>'
        '<th scope="col">Implementation</th><th scope="col">Release</th><th scope="col">Published</th>'
        '<th scope="col">Cases</th><th scope="col">Tier</th><th scope="col">Capabilities</th>'
        f"{count_headers()}</tr></thead>\n<tbody>\n{summary_rows(rows)}\n</tbody>\n</table></div>\n"
    )


def summary_page(rows, generated):
    """The page listing every implementation's latest release, with its earlier releases collapsed under it."""
    implementations = list(dict.fromkeys(row["implementation"] for row in rows))
    latest = [next(row for row in rows if row["implementation"] == name) for name in implementations]
    body = [
        "<h1>Compatibility table</h1>\n",
        "<p>What every release of every Itinera implementation claims, and what the conformance report it carries "
        "shows. Each row counts the scenarios of the conformance cases the release ran against: passed, excluded "
        "with a proof that the language makes them impossible to express, not run because they need a capability "
        "or a proposal the release does not claim, and failed or missing from its report. A row's release links to "
        "its counts by proposal.</p>\n",
        "<p>The table is rebuilt every day. It is also available as "
        '<a href="table.json">table.json</a>.</p>\n',
        "<h2>Latest releases</h2>\n",
        summary_table("The latest release of each implementation", latest),
    ]
    earlier = [(name, [row for row in rows if row["implementation"] == name][1:]) for name in implementations]
    if any(older for _, older in earlier):
        body.append("<h2>Earlier releases</h2>\n")
    for name, older in earlier:
        if older:
            body.append(
                f"<details>\n<summary>Earlier releases of {escape(name)} ({len(older)})</summary>\n"
                f"{summary_table(f'Earlier releases of {name}, newest first', older)}</details>\n"
            )
    return page("Compatibility table · Itinera", "".join(body), generated, home=None)


def proposal_cell(number, titles, spec):
    title = titles.get(number, {})
    text = f"{number}: {title['title']}" if title.get("title") else number
    return link(f"{spec}/blob/main/{title['path']}", text) if title.get("path") else escape(text)


def scenario_item(entry, repository_url, tag):
    text = f"{escape(entry['scenario'])}, in {escape(entry['feature'].removeprefix('cases/'))}"
    tag = quote(tag, safe="")
    if entry["status"] == EXCLUDED:
        proof = entry.get("proof", {})
        proved = ""
        if proof.get("test") and proof.get("file"):
            proof_url = f"{repository_url}/blob/{tag}/{proof['file']}"
            proved = f", proved by the test “{escape(proof['test'])}” in {link(proof_url, proof['file'])}"
        return f"<li>{text}: excluded by {escape(entry['reason'])}{proved}.</li>"
    label = "Not run" if entry["status"] == NOT_RUN else "Failed or missing"
    return f"<li>{text}: {label}. {escape(entry['reason'])}</li>"


def describe(counts):
    parts = [f"{counts[key]} {label.lower()}" for key, label in COLUMNS[1:] if counts[key]]
    return ", ".join(parts)


def row_page(row, titles, spec, generated):
    """A row's page: what the release claims, its counts by proposal, and the scenarios that did not pass."""
    repository_url = f"https://github.com/{row['repository']}"
    tag = row["tag"]
    at = quote(tag, safe="")
    cases_url = f"https://github.com/{row['conformance']}/tree/{quote(row['cases'], safe='')}"
    manifest_url = f"{repository_url}/blob/{at}/{row['manifest']}"
    release_url = f"{repository_url}/releases/tag/{at}"
    marker = ", a pre-release" if row["prerelease"] else ""
    body = [
        f"<h1>{escape(row['implementation'])} {escape(tag)}</h1>\n",
        "<ul>\n",
        f"<li>Release: {link(release_url, tag)}, published {escape(row['published'])}"
        f"{marker}.</li>\n",
        f"<li>Cases: {link(cases_url, row['cases'])}, read from {link(manifest_url, row['manifest'])}.</li>\n",
        f"<li>Tier: {row['tiers'] or 'none'}.</li>\n",
        f"<li>Capabilities: {escape(', '.join(row['capabilities']) or 'none')}.</li>\n",
        "</ul>\n<h2>Scenarios by proposal</h2>\n",
        "<p>A scenario counts under every proposal it carries, so a scenario an amendment changed counts under both. "
        "The last row counts each scenario once.</p>\n",
        '<div class="scroll"><table>\n<caption>Scenarios of each proposal</caption>\n<thead><tr>'
        f'<th scope="col">Proposal</th><th scope="col" class="number">Scenarios</th>{count_headers()}</tr></thead>\n'
        "<tbody>\n",
    ]
    for number, counts in row["proposals"].items():
        body.append(
            f'<tr><th scope="row">{proposal_cell(number, titles, spec)}</th>'
            f'<td class="number">{counts["scenarios"]}</td>{count_cells(counts)}</tr>\n'
        )
    totals = row["totals"]
    body.append(
        f'</tbody>\n<tfoot><tr><th scope="row">Every scenario</th><td class="number">{totals["scenarios"]}</td>'
        f"{count_cells(totals)}</tr></tfoot>\n</table></div>\n"
    )
    body.append("<h2>Scenarios that did not pass</h2>\n")
    pending = [(n, c) for n, c in row["proposals"].items() if c["scenarios"] != c["passed"]]
    if totals["scenarios"] == totals["passed"]:
        body.append("<p>Every scenario passed.</p>\n")
    for number, counts in pending:
        title = titles.get(number, {}).get("title")
        name = f"{number}: {title}" if title else number
        items = "\n".join(
            scenario_item(e, repository_url, tag) for e in row["not_passed"] if number in e["proposals"]
        )
        body.append(
            f"<details>\n<summary>{escape(name)}: {describe(counts)}</summary>\n<ul>\n{items}\n</ul>\n</details>\n"
        )
    unproposed = [e for e in row["not_passed"] if not e["proposals"]]
    if unproposed:
        items = "\n".join(scenario_item(e, repository_url, tag) for e in unproposed)
        body.append(
            f"<details>\n<summary>Scenarios without a proposal: {len(unproposed)}</summary>\n<ul>\n{items}\n</ul>\n"
            "</details>\n"
        )
    return page(f"{row['implementation']} {tag} · Compatibility table", "".join(body), generated)
