"""Commit messages: Conventional Commits subjects, and the changelog entries carried as trailers.

Trailers are found as git-cliff finds them, through the git-conventional crate: they start at the first paragraph
after the subject whose first line is a trailer, a trailer's token is any run of characters other than white space,
colons and parentheses, and a line that is not a trailer continues the trailer before it.
"""

import re
from dataclasses import dataclass, field

TYPES = ("build", "chore", "ci", "docs", "feat", "fix", "perf", "refactor", "revert", "test")
ENTRIES = ("Added", "Changed", "Fixed", "Removed")
NO_ENTRY = "Changelog"
NEAR_ENTRIES = ("add", "adds", "change", "changes", "fix", "remove", "removes", "deprecated", "security")

SUBJECT = re.compile(r"(?P<type>[a-z]+)(?:\((?P<scope>[a-z0-9][a-z0-9-]*)\))?(?P<breaking>!)?: (?P<description>\S.*)")
TRAILER = re.compile(r"(?P<token>BREAKING[ -]CHANGE|[^\s:()]+)(?P<separator>:[ \t]*| #)(?P<value>.*)")
GIT_TOKEN = re.compile(r"BREAKING[ -]CHANGE|[A-Z][A-Za-z0-9-]*")


@dataclass
class Trailer:
    token: str
    separator: str
    """Either ":" or " #"."""
    value: str
    empty: bool = False
    """Whether nothing followed the separator, so that git-cliff takes the next line as the value."""


@dataclass
class Message:
    subject: str
    type: str | None = None
    breaking: bool = False
    body: list[str] = field(default_factory=list)
    trailers: list[Trailer] = field(default_factory=list)

    def entries(self):
        """The trailers that are changelog entries."""
        return [trailer for trailer in self.trailers if trailer.token in ENTRIES]


def parse(text):
    """The subject, body and trailers of a commit message."""
    lines = [line.rstrip() for line in text.strip().splitlines()]
    message = Message(lines[0] if lines else "")
    match = SUBJECT.fullmatch(message.subject)
    if match:
        message.type = match["type"]
        message.breaking = match["breaking"] is not None
    rest = lines[1:]
    start = next((i for i, line in enumerate(rest) if starts_paragraph(rest, i) and TRAILER.fullmatch(line)), len(rest))
    message.body = rest[:start]
    for line in rest[start:]:
        trailer = TRAILER.fullmatch(line)
        last = message.trailers[-1] if message.trailers else None
        if last is not None and last.empty and last.value == "":
            last.value = line
        elif trailer:
            separator = ":" if trailer["separator"].startswith(":") else " #"
            message.trailers.append(Trailer(trailer["token"], separator, trailer["value"], trailer["value"] == ""))
        elif last is not None:
            last.value += f"\n{line}"
    for trailer in message.trailers:
        trailer.value = trailer.value.strip()
    return message


def starts_paragraph(lines, i):
    """Whether `lines[i]` opens a paragraph: it holds text and follows a blank line."""
    return lines[i] != "" and i > 0 and lines[i - 1] == ""


def needs_entry(message):
    """Whether a commit must say what it changes in the changelog: a feature, a fix or a breaking change."""
    return message.type in ("feat", "fix") or message.breaking


def problems(text):
    """Why a commit message breaks the convention, each as a sentence; empty when it keeps it."""
    message = parse(text)
    if message.type is None:
        return [
            f'The subject "{message.subject}" must read "type(scope): description" or "type: description", '
            f'with "!" before the colon for a breaking change.'
        ]
    found = []
    if message.type not in TYPES:
        found.append(f'The type "{message.type}" is not one of {", ".join(TYPES)}.')
    if message.body and message.body[0] != "":
        found.append("The line after the subject must be blank.")
    found += [
        f'"{line}" reads like a changelog entry, but no tool reads it: entries are trailers, in the paragraphs '
        f"that close the message."
        for line in message.body
        if looks_like_entry(line)
    ]
    found += [problem for i, trailer in enumerate(message.trailers) if (problem := trailer_problem(trailer, i == 0))]
    no_entry = [trailer.value for trailer in message.trailers if trailer.token == NO_ENTRY]
    if any(value != "none" for value in no_entry):
        found.append(f'"{NO_ENTRY}:" takes only "none".')
    if no_entry and message.entries():
        found.append(f'A commit with changelog entries cannot also say "{NO_ENTRY}: none".')
    if needs_entry(message) and not message.entries() and not no_entry:
        found.append(
            f"A feature, a fix or a breaking change carries at least one trailer {', '.join(ENTRIES)}, "
            f'or "{NO_ENTRY}: none" when an application meets no change.'
        )
    return found


def trailer_problem(trailer, first):
    """Why git-cliff would read `trailer`, the message's first trailer when `first`, other than as meant, or None."""
    if trailer.empty:
        return (
            f'The trailer "{trailer.token}" has nothing after its colon, so git-cliff takes the next line as its '
            f"value, or drops the commit when no line follows."
        )
    if trailer.token.startswith("BREAKING"):
        return f'Mark a breaking change with "!" in the subject and a Changed or Removed entry, not "{trailer.token}".'
    spelling = entry_spelling(trailer.token)
    if spelling not in (None, trailer.token):
        return f'The trailer "{trailer.token}" must be spelled "{spelling}".'
    if not GIT_TOKEN.fullmatch(trailer.token) and first:
        return (
            f'"{trailer.token}{trailer.separator}{first_line(trailer.value)}" reads as a trailer to git-cliff, '
            f"which takes this paragraph and everything after it as trailers: open the paragraph with other words."
        )
    if not GIT_TOKEN.fullmatch(trailer.token):
        return (
            f'"{trailer.token}{trailer.separator}{first_line(trailer.value)}" reads as a trailer to git-cliff, '
            f"which cuts the entry before it short: keep each entry on one line, and start every line of the closing "
            f'paragraphs with a trailer, such as "Refs #7".'
        )
    if trailer.separator == ":" and trailer.token.lower() in NEAR_ENTRIES:
        return f'No changelog section is called "{trailer.token}"; use {", ".join(ENTRIES)}.'
    if trailer.token in ENTRIES and "\n" in trailer.value:
        return f'The {trailer.token} entry "{first_line(trailer.value)}" spans several lines; keep it on one line.'
    return None


def looks_like_entry(line):
    return any(line.lower().startswith(f"{entry.lower()}:") for entry in ENTRIES)


def entry_spelling(token):
    """The spelling of the entry section `token` names, ignoring case, or None when it names none."""
    return next((entry for entry in ENTRIES if entry.lower() == token.lower()), None)


def first_line(value):
    return value.split("\n", 1)[0]


def parse_log(output):
    """The commits of `git log --format=%H%x00%P%x00%B%x1e`, shaped as GitHub lists a pull request's commits."""
    records = [record.strip("\n").split("\x00") for record in output.split("\x1e") if record.strip()]
    return [
        {"sha": sha, "parents": [{"sha": p} for p in parents.split()], "commit": {"message": message}}
        for sha, parents, message in records
    ]


def is_merge(commit):
    """Whether a commit from GitHub's list of a pull request's commits merges others, and so has its own wording."""
    return len(commit["parents"]) > 1
