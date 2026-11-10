"""The scenario pages of the conformance repository: every feature file of every version as a plain HTML page,
with an anchor per scenario, and indexes by tier, proposal and tag (conformance FORMAT.md, "The scenario pages")."""

import html
import pathlib
import re
from dataclasses import dataclass, field

from lib import gherkin

SITE_TITLE = "Itinera conformance cases"
BUILD_FILE = "cases/build.txt"
REF = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]*")
RESERVED = {"index.html", "style.css", "build.txt"}
VERSION = re.compile(r"v(?P<major>\d+)\.(?P<minor>\d+)\.(?P<patch>\d+)(?:-(?P<pre>[0-9A-Za-z.-]+))?")
STYLE = """\
:root { color-scheme: light dark; --text: #1a1a1a; --muted: #555; --background: #ffffff; --line: #c8c8c8;
  --header: #f0f0f0; --link: #0b57d0; --note: #fff4ce; }
@media (prefers-color-scheme: dark) {
  :root { --text: #e8e8e8; --muted: #b0b0b0; --background: #161616; --line: #4a4a4a; --header: #262626;
    --link: #8ab4f8; --note: #3d3415; }
}
body { margin: 0 auto; max-width: 60rem; padding: 1rem; font: 1rem/1.5 system-ui, sans-serif;
  color: var(--text); background: var(--background); }
a { color: var(--link); }
nav ol { list-style: none; padding: 0; margin: 0 0 1rem; }
nav.breadcrumb li { display: inline; }
nav.breadcrumb li + li::before { content: " / "; color: var(--muted); }
.note { background: var(--note); padding: 0.5rem 1rem; border-radius: 0.25rem; }
.meta { color: var(--muted); }
ol.steps { list-style: none; padding-left: 0; }
ol.steps > li { margin: 0.25rem 0; }
.keyword { font-weight: bold; }
.table { overflow-x: auto; margin: 0.25rem 0 0.75rem; }
table { border-collapse: collapse; }
th, td { border: 1px solid var(--line); padding: 0.2rem 0.5rem; text-align: left; vertical-align: top; }
th { background: var(--header); }
pre { background: var(--header); padding: 0.5rem; overflow-x: auto; }
"""


def anchor(name):
    """A scenario's or rule's name as an anchor: in lower case, without apostrophes, with each run of characters
    other than a to z and 0 to 9 written as one "-", and no "-" at either end."""
    text = re.sub(r"['’]", "", name.lower())
    return re.sub(r"[^a-z0-9]+", "-", text).strip("-") or "scenario"


class Anchors:
    """The anchors of one page, each unique: a name whose anchor is taken gets "-2", then "-3"."""

    def __init__(self):
        self.used = set()

    def take(self, base):
        candidate, n = base, 1
        while candidate in self.used:
            n += 1
            candidate = f"{base}-{n}"
        self.used.add(candidate)
        return candidate


def version_key(name):
    """A sort key putting newer versions first: three-part versions by their numbers, a pre-release before its
    release, the numeric parts of a pre-release compared as numbers."""
    match = VERSION.fullmatch(name)
    if not match:
        return (1, name)
    numbers = tuple(-int(match.group(k)) for k in ("major", "minor", "patch"))
    pre = match.group("pre")
    if pre is None:
        return (0, numbers, 0, ())
    parts = tuple((0, -int(p), "") if p.isdigit() else (1, 0, p) for p in pre.split("."))
    return (0, numbers, 1, parts)


def usable_ref(name):
    """Why the tag or branch `name` cannot be a directory of the site, or None when it can."""
    if not REF.fullmatch(name) or name in RESERVED:
        return f'"{name}" is left out: a version must be a single path segment of letters, digits, ".", "_" and "-".'
    return None


def is_release(name):
    match = VERSION.fullmatch(name)
    return bool(match) and match.group("pre") is None


@dataclass
class FeatureFile:
    path: str
    """Its path in the repository, such as "cases/tier-1/0008-steps/outcomes.feature"."""
    feature: gherkin.Feature
    anchors: dict = field(default_factory=dict)
    """For each (rule, scenario) of the feature, by identity, its anchor."""

    @property
    def page(self):
        """Its page, relative to its version's directory."""
        relative = self.path[len("cases/") :] if self.path.startswith("cases/") else self.path
        return relative[: -len(".feature")] + ".html"

    @property
    def group(self):
        """(tier, proposal) as its folders name them, such as ("tier-1", "0008-steps"); empty where missing."""
        parts = self.page.split("/")[:-1]
        return (parts[0] if parts else "", parts[1] if len(parts) > 1 else "")


def read_features(root):
    """Every feature file under `root`/cases, parsed, in path order; files without a feature are left out."""
    files = []
    for path in sorted(pathlib.Path(root).joinpath("cases").rglob("*.feature")):
        feature = gherkin.parse(path.read_text(encoding="utf-8"))
        if feature is not None:
            files.append(assign_anchors(FeatureFile(path.relative_to(root).as_posix(), feature)))
    return files


def assign_anchors(file):
    anchors = Anchors()
    anchors.take("background")
    for child in file.feature.children:
        if isinstance(child, gherkin.Rule):
            file.anchors[id(child)] = anchors.take("rule-" + anchor(child.name))
    for _, scenario in file.feature.scenarios():
        file.anchors[id(scenario)] = anchors.take(anchor(scenario.name))
    return file


# Rendering.


def e(text):
    return html.escape(text, quote=True)


def tag_file(tag):
    return tag.lstrip("@") + ".html"


def page(title, depth, crumbs, body):
    """A whole page. `depth` is how many directories below the site's root it lies; `crumbs` are (label, href)
    from the root down, the last one being this page; an href of None shows the label without a link."""
    up = "../" * depth
    items = "".join(
        ('<li aria-current="page">' if i == len(crumbs) - 1 else "<li>")
        + (f'<a href="{e(href)}">{e(label)}</a>' if href else e(label))
        + "</li>"
        for i, (label, href) in enumerate(crumbs)
    )
    return (
        "<!doctype html>\n"
        '<html lang="en">\n<head>\n<meta charset="utf-8">\n'
        '<meta name="viewport" content="width=device-width, initial-scale=1">\n'
        f"<title>{e(title)}</title>\n"
        f'<link rel="stylesheet" href="{up}cases/style.css">\n'
        "</head>\n<body>\n"
        f'<nav class="breadcrumb" aria-label="Breadcrumb"><ol>{items}</ol></nav>\n'
        f"<main>\n{body}</main>\n</body>\n</html>\n"
    )


def paragraphs(text):
    """A description as paragraphs: blank lines separate them, and the lines of one are joined."""
    blocks = [" ".join(line.strip() for line in block.splitlines()) for block in re.split(r"\n\s*\n", text.strip())]
    return "".join(f"<p>{e(b)}</p>\n" for b in blocks if b)


def tags_line(tags, to_tags):
    if not tags:
        return ""
    links = ", ".join(f'<a href="{to_tags}{e(tag_file(t))}">{e(t)}</a>' for t in tags)
    return f'<p class="meta">Tags: {links}</p>\n'


def table(rows, label):
    if not rows:
        return ""
    width = max(len(r) for r in rows)
    head = "".join(f'<th scope="col">{cell(c)}</th>' for c in rows[0] + [""] * (width - len(rows[0])))
    body = "".join(
        "<tr>" + "".join(f"<td>{cell(c)}</td>" for c in r + [""] * (width - len(r))) + "</tr>\n" for r in rows[1:]
    )
    return (
        f'<div class="table" role="region" aria-label="{e(label)}" tabindex="0"><table>\n'
        f"<thead><tr>{head}</tr></thead>\n<tbody>\n{body}</tbody>\n</table></div>\n"
    )


def cell(text):
    return "<br>".join(e(line) for line in text.split("\n"))


def steps(items):
    if not items:
        return ""
    out = []
    for number, step in enumerate(items, start=1):
        extra = ""
        if step.table is not None:
            extra += table(step.table, f"Table of step {number}")
        if step.doc_string is not None:
            extra += f"<pre>{e(step.doc_string.content)}</pre>\n"
        out.append(f'<li><span class="keyword">{e(step.keyword)}</span> {e(step.text)}\n{extra}</li>\n')
    return '<ol class="steps" role="list">\n' + "".join(out) + "</ol>\n"


def heading(level, text, anchor_id=None):
    attribute = f' id="{e(anchor_id)}"' if anchor_id else ""
    return f"<h{level}{attribute}>{e(text)}</h{level}>\n"


def titled(keyword, name):
    return f"{keyword}: {name}" if name else keyword


def render_background(background, level, anchor_id):
    if background is None:
        return ""
    return (
        heading(level, titled(background.keyword, background.name), anchor_id)
        + paragraphs(background.description)
        + steps(background.steps)
    )


def render_scenario(file, scenario, level, to_tags):
    out = heading(level, titled(scenario.keyword, scenario.name), file.anchors[id(scenario)])
    out += tags_line(scenario.tags, to_tags) + paragraphs(scenario.description) + steps(scenario.steps)
    for examples in scenario.examples:
        out += heading(level + 1, titled(examples.keyword, examples.name))
        out += tags_line(examples.tags, to_tags) + paragraphs(examples.description)
        out += table(examples.table, titled(examples.keyword, examples.name))
    return out


def contents(file):
    """The page's own list of rules and scenarios, linked to their anchors."""
    items = []
    for child in file.feature.children:
        if isinstance(child, gherkin.Rule):
            inner = "".join(
                f'<li><a href="#{e(file.anchors[id(s)])}">{e(s.name)}</a></li>' for s in child.scenarios
            )
            items.append(
                f'<li><a href="#{e(file.anchors[id(child)])}">{e(titled(child.keyword, child.name))}</a>'
                f"<ul>{inner}</ul></li>"
            )
        else:
            items.append(f'<li><a href="#{e(file.anchors[id(child)])}">{e(child.name)}</a></li>')
    return f'<nav aria-label="Scenarios of this feature"><h2>Contents</h2>\n<ul>\n{"".join(items)}\n</ul></nav>\n'


@dataclass
class Version:
    name: str
    """The tag, or the default branch, such as "main"."""
    files: list
    branch: bool = False
    """Whether it is the default branch rather than a tag."""


def version_note(version):
    if version.branch:
        return (
            f'<p class="note">These are the cases on the {e(version.name)} branch, not a released version: '
            "they change as the branch does.</p>\n"
        )
    return ""


def render_feature(repo, version, file):
    depth = 2 + file.page.count("/")
    to_version = "../" * file.page.count("/")
    to_tags = to_version + "tags/"
    feature = file.feature
    source = f"https://github.com/{repo}/blob/{version.name}/{file.path}"
    body = heading(1, titled(feature.keyword, feature.name))
    body += version_note(version)
    body += (
        f'<p class="meta">Cases version {e(version.name)}. '
        f'Source: <a href="{e(source)}">{e(file.path)} on GitHub</a>.</p>\n'
    )
    body += tags_line(feature.tags, to_tags) + paragraphs(feature.description)
    body += contents(file)
    body += render_background(feature.background, 2, "background")
    for child in feature.children:
        if isinstance(child, gherkin.Rule):
            body += heading(2, titled(child.keyword, child.name), file.anchors[id(child)])
            body += tags_line(child.tags, to_tags) + paragraphs(child.description)
            body += render_background(child.background, 3, None)
            for scenario in child.scenarios:
                body += render_scenario(file, scenario, 3, to_tags)
        else:
            body += render_scenario(file, child, 2, to_tags)
    crumbs = [
        (SITE_TITLE, "../" * depth + "cases/index.html"),
        (version.name, to_version + "index.html"),
        *[(part, None) for part in file.page.split("/")[:-1]],
        (feature.name, None),
    ]
    return page(f"{feature.name} ({version.name}) - {SITE_TITLE}", depth, crumbs, body)


def scenario_link(file, scenario, prefix):
    return f'<a href="{e(prefix + file.page)}#{e(file.anchors[id(scenario)])}">{e(scenario.name)}</a>'


def render_version_index(version):
    body = heading(1, f"Cases {version.name}") + version_note(version)
    count = sum(1 for f in version.files for _ in f.feature.scenarios())
    body += f'<p>{len(version.files)} features, {count} scenarios. <a href="tags/index.html">Every tag</a>.</p>\n'
    groups = {}
    for file in version.files:
        groups.setdefault(file.group[0], {}).setdefault(file.group[1], []).append(file)
    for tier in sorted(groups, key=natural):
        body += heading(2, folder_title(tier))
        for proposal in sorted(groups[tier], key=natural):
            if proposal:
                body += heading(3, proposal)
            body += "<ul>\n"
            for file in groups[tier][proposal]:
                inner = "".join(f"<li>{scenario_link(file, s, '')}</li>" for _, s in file.feature.scenarios())
                body += f'<li><a href="{e(file.page)}">{e(file.feature.name)}</a>\n<ul>{inner}</ul></li>\n'
            body += "</ul>\n"
    crumbs = [(SITE_TITLE, "../index.html"), (version.name, None)]
    return page(f"Cases {version.name} - {SITE_TITLE}", 2, crumbs, body)


def folder_title(name):
    match = re.fullmatch(r"tier-(\d+)", name)
    return f"Tier {match.group(1)}" if match else (name or "Other features")


def natural(text):
    return [int(p) if p.isdigit() else p for p in re.split(r"(\d+)", text)]


def tag_index(version):
    """For each tag, in natural order, the (file, scenario) pairs that carry it, in path order."""
    found = {}
    for file in version.files:
        for rule, scenario in file.feature.scenarios():
            for tag in file.feature.tags_of(rule, scenario):
                found.setdefault(tag, []).append((file, scenario))
    return {tag: found[tag] for tag in sorted(found, key=natural)}


def render_tags_index(version, tags):
    rows = "".join(
        f'<tr><td><a href="{e(tag_file(t))}">{e(t)}</a></td><td>{len(found)}</td></tr>\n' for t, found in tags.items()
    )
    body = heading(1, f"Tags of cases {version.name}") + version_note(version)
    body += (
        '<div class="table" role="region" aria-label="Tags" tabindex="0"><table>\n'
        '<thead><tr><th scope="col">Tag</th><th scope="col">Scenarios</th></tr></thead>\n'
        f"<tbody>\n{rows}</tbody>\n</table></div>\n"
    )
    crumbs = [(SITE_TITLE, "../../index.html"), (version.name, "../index.html"), ("Tags", None)]
    return page(f"Tags of cases {version.name} - {SITE_TITLE}", 3, crumbs, body)


def render_tag(version, tag, found):
    body = heading(1, f"{tag} in cases {version.name}") + version_note(version)
    body += f"<p>{len(found)} {'scenario carries' if len(found) == 1 else 'scenarios carry'} this tag.</p>\n"
    by_file = {}
    for file, scenario in found:
        by_file.setdefault(file.path, (file, []))[1].append(scenario)
    for file, scenarios in by_file.values():
        body += f'<h2><a href="../{e(file.page)}">{e(file.feature.name)}</a></h2>\n'
        body += f'<p class="meta">{e(file.path)}</p>\n<ul>\n'
        body += "".join(f"<li>{scenario_link(file, s, '../')}</li>\n" for s in scenarios)
        body += "</ul>\n"
    crumbs = [
        (SITE_TITLE, "../../index.html"),
        (version.name, "../index.html"),
        ("Tags", "index.html"),
        (tag, None),
    ]
    return page(f"{tag} in cases {version.name} - {SITE_TITLE}", 3, crumbs, body)


def version_item(version):
    note = " (the branch, not a released version)" if version.branch else ""
    return f'<li><a href="{e(version.name)}/index.html">{e(version.name)}</a>{note}</li>\n'


def render_versions(versions):
    branches = [v for v in versions if v.branch]
    tags = sorted((v for v in versions if not v.branch), key=lambda v: version_key(v.name))
    releases = [v for v in tags if is_release(v.name)]
    others = [v for v in tags if not is_release(v.name)]
    body = heading(1, SITE_TITLE)
    body += (
        "<p>Every feature file of the Itinera conformance suite, for every version, with a link for each scenario "
        "and an index for each tag.</p>\n"
    )
    if branches:
        body += heading(2, "Current") + "<ul>\n" + "".join(version_item(v) for v in branches) + "</ul>\n"
    if releases:
        body += heading(2, "Releases") + "<ul>\n" + "".join(version_item(v) for v in releases) + "</ul>\n"
    if others:
        body += (
            f"<details><summary>Release candidates and other tags ({len(others)})</summary>\n<ul>\n"
            + "".join(version_item(v) for v in others)
            + "</ul></details>\n"
        )
    return page(SITE_TITLE, 1, [(SITE_TITLE, None)], body)


def render_home():
    body = heading(1, "Itinera conformance") + '<ul>\n<li><a href="cases/index.html">The cases</a></li>\n</ul>\n'
    return page("Itinera conformance", 0, [("Itinera conformance", None)], body)


def write_site(repo, versions, out, build=""):
    """Writes the pages of `versions` under `out`/cases, `out`/index.html unless one is there, and BUILD_FILE,
    holding `build`, which names this build. Returns the number of files written."""
    out = pathlib.Path(out)
    written = []

    def write(relative, text):
        path = out / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        written.append(relative)

    write("cases/style.css", STYLE)
    write(BUILD_FILE, build + "\n")
    write("cases/index.html", render_versions(versions))
    for version in versions:
        base = f"cases/{version.name}/"
        write(base + "index.html", render_version_index(version))
        for file in version.files:
            write(base + file.page, render_feature(repo, version, file))
        tags = tag_index(version)
        write(base + "tags/index.html", render_tags_index(version, tags))
        for tag, found in tags.items():
            write(base + "tags/" + tag_file(tag), render_tag(version, tag, found))
    if not (out / "index.html").exists():
        write("index.html", render_home())
    return len(written)
