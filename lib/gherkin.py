"""A Gherkin parser for showing feature files: features, backgrounds, rules, scenarios and outlines with their
examples, tags, descriptions, steps, data tables and doc strings. Comments are left out.

It reads the English keywords only, which every conformance case uses, and is lenient: a line it cannot place is
read as description where a description may stand, and otherwise ignored, since what it builds is shown to readers,
not run.
"""

import re
from dataclasses import dataclass, field

STEP_KEYWORDS = ("Given ", "When ", "Then ", "And ", "But ", "* ")
SCENARIO_KEYWORDS = ("Scenario Outline", "Scenario Template", "Scenario", "Example")
EXAMPLES_KEYWORDS = ("Examples", "Scenarios")
DOC_STRING = re.compile(r'(?P<delimiter>"""|```)(?P<media_type>.*)')


@dataclass
class DocString:
    content: str
    media_type: str = ""


@dataclass
class Step:
    keyword: str
    """The keyword as written, such as "Given" or "*"."""
    text: str
    table: list = None
    """The data table's rows, each a list of cells, or None."""
    doc_string: DocString = None


@dataclass
class Examples:
    keyword: str
    name: str = ""
    tags: list = field(default_factory=list)
    description: str = ""
    table: list = field(default_factory=list)


@dataclass
class Background:
    keyword: str
    name: str = ""
    description: str = ""
    steps: list = field(default_factory=list)


@dataclass
class Scenario:
    keyword: str
    """"Scenario", "Example", "Scenario Outline" or "Scenario Template"."""
    name: str
    tags: list = field(default_factory=list)
    description: str = ""
    steps: list = field(default_factory=list)
    examples: list = field(default_factory=list)

    def all_tags(self):
        """Its own tags and those of its examples, in order, each once."""
        return unique(self.tags + [t for e in self.examples for t in e.tags])


@dataclass
class Rule:
    keyword: str
    name: str
    tags: list = field(default_factory=list)
    description: str = ""
    background: Background = None
    scenarios: list = field(default_factory=list)


@dataclass
class Feature:
    keyword: str
    name: str
    tags: list = field(default_factory=list)
    description: str = ""
    background: Background = None
    children: list = field(default_factory=list)
    """Its scenarios and rules, in the order of the file."""

    def scenarios(self):
        """Every scenario with the rule it belongs to, or None, in the order of the file."""
        for child in self.children:
            if isinstance(child, Rule):
                yield from ((child, s) for s in child.scenarios)
            else:
                yield None, child

    def tags_of(self, rule, scenario):
        """The tags `scenario` carries, itself or through this feature, its rule or its examples, each once."""
        return unique(self.tags + (rule.tags if rule else []) + scenario.all_tags())


def unique(items):
    return list(dict.fromkeys(items))


def parse_tags(line):
    """The tags of a tag line, without a trailing comment."""
    return [t for t in re.split(r"\s+#", " " + line, maxsplit=1)[0].split() if t.startswith("@")]


def parse_row(line):
    """The cells of a table row, unescaping `\\|`, `\\n` and `\\\\`, each stripped of surrounding white space."""
    body = line.strip()
    if body.startswith("|"):
        body = body[1:]
    cells, cell, i = [], [], 0
    while i < len(body):
        char = body[i]
        if char == "\\" and i + 1 < len(body):
            following = body[i + 1]
            cell.append({"|": "|", "n": "\n", "\\": "\\"}.get(following, "\\" + following))
            i += 2
            continue
        if char == "|":
            cells.append("".join(cell).strip())
            cell = []
        else:
            cell.append(char)
        i += 1
    if "".join(cell).strip():
        cells.append("".join(cell).strip())
    return cells


def header(line, keywords):
    """(keyword, name) when `line` opens with one of `keywords` followed by a colon, otherwise None."""
    for keyword in keywords:
        if line.startswith(keyword + ":"):
            return keyword, line[len(keyword) + 1 :].strip()
    return None


class _Parser:
    def __init__(self, text):
        self.lines = text.splitlines()
        self.feature = None
        self.rule = None
        self.element = None
        """The element whose description or steps the next lines continue."""
        self.step = None
        self.examples = None
        self.tags = []
        self.description = None
        """The lines of the description being read, or None when no description can stand here."""

    def parse(self):
        i = 0
        while i < len(self.lines):
            raw = self.lines[i]
            line = raw.strip()
            i += 1
            doc = DOC_STRING.fullmatch(line)
            if doc and self.step is not None:
                i = self.doc_string(i, raw, doc)
                continue
            if line.startswith("#"):
                continue
            if line.startswith("@"):
                self.end_description()
                self.tags += parse_tags(line)
                continue
            if self.structure(line):
                continue
            if line.startswith("|"):
                self.end_description()
                self.row(line)
                continue
            if line.startswith(STEP_KEYWORDS) or line == "*":
                self.end_description()
                self.add_step(line)
                continue
            if self.description is not None:
                self.description.append(line)
        self.end_description()
        return self.feature

    def structure(self, line):
        found = header(line, ("Feature",))
        if found:
            self.end_description()
            self.feature = Feature(*found, tags=self.take_tags())
            self.open(self.feature)
            return True
        if self.feature is None:
            return False
        found = header(line, ("Rule",))
        if found:
            self.end_description()
            self.rule = Rule(*found, tags=self.take_tags())
            self.feature.children.append(self.rule)
            self.open(self.rule)
            return True
        found = header(line, ("Background",))
        if found:
            self.end_description()
            background = Background(*found)
            (self.rule or self.feature).background = background
            self.take_tags()
            self.open(background)
            return True
        found = header(line, SCENARIO_KEYWORDS)
        if found:
            self.end_description()
            scenario = Scenario(*found, tags=self.take_tags())
            (self.rule.scenarios if self.rule else self.feature.children).append(scenario)
            self.open(scenario)
            return True
        found = header(line, EXAMPLES_KEYWORDS)
        if found and isinstance(self.element, (Scenario, Examples)):
            self.end_description()
            examples = Examples(*found, tags=self.take_tags())
            self.scenario_of_examples().examples.append(examples)
            self.open(examples)
            self.examples = examples
            return True
        return False

    def scenario_of_examples(self):
        scenarios = self.rule.scenarios if self.rule else [c for c in self.feature.children if isinstance(c, Scenario)]
        return scenarios[-1]

    def open(self, element):
        self.element, self.step, self.examples = element, None, None
        self.description = []

    def take_tags(self):
        tags, self.tags = self.tags, []
        return tags

    def end_description(self):
        if self.description is not None and self.element is not None:
            self.element.description = "\n".join(self.description).strip()
        self.description = None

    def add_step(self, line):
        if not isinstance(self.element, (Background, Scenario)):
            return
        if line == "*":
            keyword, text = "*", ""
        else:
            keyword, _, text = line.partition(" ")
        self.step = Step(keyword, text.strip())
        self.element.steps.append(self.step)

    def row(self, line):
        if self.examples is not None:
            self.examples.table.append(parse_row(line))
        elif self.step is not None:
            if self.step.table is None:
                self.step.table = []
            self.step.table.append(parse_row(line))

    def doc_string(self, i, raw, doc):
        """Reads the doc string opened on the line before `i`, returning the index of the line after it."""
        delimiter = doc.group("delimiter")
        indent = len(raw) - len(raw.lstrip())
        content = []
        while i < len(self.lines):
            line = self.lines[i]
            i += 1
            if line.strip() == delimiter:
                break
            stripped = line[indent:] if line[:indent].strip() == "" else line.lstrip()
            content.append(stripped.replace('\\"\\"\\"', '"""') if delimiter == '"""' else stripped)
        self.step.doc_string = DocString("\n".join(content), doc.group("media_type").strip())
        return i


def parse(text):
    """The feature of a feature file, or None when it has no `Feature:` line."""
    return _Parser(text).parse()
