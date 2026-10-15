import unittest

from lib.commits import is_merge, parse, parse_log, problems

FEATURE = """\
feat(step)!: give an attempt a type of its own

An attempt's number was a bare NonZeroU32.

Added: `step::Attempt`, an attempt's number, counted from 1.
Changed: An attempt's number is a `step::Attempt` instead of a `NonZeroU32`.
Refs #7

Co-Authored-By: Someone <noreply@example.invalid>
"""

# Each message with the trailers git-cliff 2.14.2 reads in it, taken from `git cliff --context`.
AS_GIT_CLIFF_READS = [
    ("a trailer starts the paragraphs of trailers",
     "feat: x\n\nNote: prose about something.\n\nAdded: y.\nRefs #7\n",
     [("Note", "prose about something."), ("Added", "y."), ("Refs", "7")]),
    ("an indented line continues the entry",
     "feat: x\n\nAdded: a long entry\n  wrapped onto a second line.\nRefs #7\n",
     [("Added", "a long entry\n  wrapped onto a second line."), ("Refs", "7")]),
    ("a wrapped line naming a path is a trailer of its own",
     "feat: x\n\nAdded: `step::Attempt`, counted from 1, with\n`Attempt::FIRST` and `is_first()`.\nRefs #7\n",
     [("Added", "`step::Attempt`, counted from 1, with"), ("`Attempt", ":FIRST` and `is_first()`."), ("Refs", "7")]),
    ("prose after the trailers continues the last one",
     "feat: x\n\nAdded: y.\n\nA closing paragraph of prose.\n",
     [("Added", "y.\n\nA closing paragraph of prose.")]),
    ("no space is needed after the colon",
     "fix: x\n\nFixed:y.\nRefs #7\n",
     [("Fixed", "y."), ("Refs", "7")]),
    ("an empty trailer takes the next line",
     "feat: x\n\nAdded: y.\nSee:\nAdded: z.\nRefs #7\n",
     [("Added", "y."), ("See", "Added: z."), ("Refs", "7")]),
    ("trailers may span several paragraphs",
     "feat: x\n\nBody.\n\nAdded: y.\n\nRefs #7\n\nCo-Authored-By: A <a@example.invalid>\n"
     "Claude-Session: https://example.invalid/s\n",
     [("Added", "y."), ("Refs", "7"), ("Co-Authored-By", "A <a@example.invalid>"),
      ("Claude-Session", "https://example.invalid/s")]),
    ("a hash after a space separates a trailer",
     "feat: x\n\nAdded: the type\nis #1 now.\nRefs #7\n",
     [("Added", "the type"), ("is", "1 now."), ("Refs", "7")]),
    ("a colon inside the value belongs to it",
     "fix: x\n\nFixed: `a::b` now returns: the value.\nRefs #7\n",
     [("Fixed", "`a::b` now returns: the value."), ("Refs", "7")]),
    ("a breaking change trailer has a space in its token",
     "feat!: x\n\nBREAKING CHANGE: the old thing is gone.\nRemoved: `a::B`.\nRefs #7\n",
     [("BREAKING CHANGE", "the old thing is gone."), ("Removed", "`a::B`."), ("Refs", "7")]),
    ("a paragraph that opens with prose holds no trailers",
     "feat: x\n\nSome prose\nAdded: not a trailer.\nRefs #7\n",
     []),
]


def trailers(text):
    return [(trailer.token, trailer.value) for trailer in parse(text).trailers]


class Parsing(unittest.TestCase):
    def test_trailers_are_found_as_git_cliff_finds_them(self):
        for name, text, expected in AS_GIT_CLIFF_READS:
            with self.subTest(name):
                self.assertEqual(trailers(text), expected)

    def test_the_subject_gives_the_type_and_whether_the_change_breaks(self):
        message = parse(FEATURE)
        self.assertEqual((message.type, message.breaking), ("feat", True))

    def test_entries_are_the_trailers_named_after_a_changelog_section(self):
        self.assertEqual([entry.token for entry in parse(FEATURE).entries()], ["Added", "Changed"])

    def test_a_subject_that_breaks_the_form_has_no_type(self):
        self.assertIsNone(parse("Give an attempt a type of its own").type)

    def test_git_logs_output_becomes_commits_as_github_lists_them(self):
        output = "a1\x00p1\x00feat: x\n\nAdded: y.\n\x1e\nb2\x00p1 p2\x00Merge branch\n\x1e\n"
        self.assertEqual(
            parse_log(output),
            [
                {"sha": "a1", "parents": [{"sha": "p1"}], "commit": {"message": "feat: x\n\nAdded: y."}},
                {"sha": "b2", "parents": [{"sha": "p1"}, {"sha": "p2"}], "commit": {"message": "Merge branch"}},
            ],
        )


class Problems(unittest.TestCase):
    def test_a_feature_with_entries_keeps_the_convention(self):
        self.assertEqual(problems(FEATURE), [])

    def test_a_change_an_application_does_not_meet_needs_no_entry(self):
        for subject in ("test: bless the proofs", "ci(release): build without debug information", "docs: fix a link"):
            with self.subTest(subject=subject):
                self.assertEqual(problems(f"{subject}\n\nRefs #7\n"), [])

    def test_a_subject_without_a_type_is_refused(self):
        self.assertEqual(len(problems("Give an attempt a type of its own\n")), 1)

    def test_an_unknown_type_is_refused(self):
        self.assertIn('The type "feature"', problems("feature: x\n\nChangelog: none\n")[0])

    def test_a_capitalised_type_is_refused(self):
        self.assertEqual(len(problems("Feat: x\n")), 1)

    def test_the_line_after_the_subject_must_be_blank(self):
        self.assertEqual(problems("docs: x\nbody right away\n"), ["The line after the subject must be blank."])

    def test_a_feature_a_fix_or_a_breaking_change_needs_an_entry(self):
        for subject in ("feat: x", "fix(step): x", "refactor!: x"):
            with self.subTest(subject=subject):
                self.assertEqual(len(problems(f"{subject}\n\nRefs #7\n")), 1)

    def test_changelog_none_stands_in_for_an_entry(self):
        self.assertEqual(problems("fix: x\n\nChangelog: none\nRefs #7\n"), [])

    def test_changelog_takes_only_none(self):
        self.assertIn('"Changelog:" takes only "none".', problems("fix: x\n\nChangelog: skip\n"))

    def test_entries_and_changelog_none_contradict_each_other(self):
        self.assertEqual(len(problems("fix: x\n\nFixed: y.\nChangelog: none\n")), 1)

    def test_an_entry_in_the_body_is_refused_since_no_tool_reads_it(self):
        found = problems("feat: x\n\nSome prose\nAdded: y.\n\nRefs #7\n")
        self.assertTrue(any("reads like a changelog entry" in problem for problem in found))

    def test_an_entry_must_use_its_sections_spelling(self):
        self.assertIn('The trailer "added" must be spelled "Added".', problems("feat: x\n\nadded: y.\n"))

    def test_a_section_the_changelog_does_not_have_is_refused(self):
        for token in ("Deprecated", "Security", "Fix", "Change", "Add", "Remove"):
            with self.subTest(token=token):
                found = problems(f"fix: x\n\nFixed: y.\n{token}: z.\n")
                expected = f'No changelog section is called "{token}"; use Added, Changed, Fixed, Removed.'
                self.assertEqual(found, [expected])

    def test_fixes_as_a_closing_keyword_is_not_a_section(self):
        self.assertEqual(problems("fix: x\n\nFixed: y.\nFixes #12\n"), [])

    def test_an_entry_on_several_lines_is_refused(self):
        found = problems("feat: x\n\nAdded: a long entry\n  wrapped onto a second line.\n")
        self.assertTrue(any("spans several lines" in problem for problem in found))

    def test_an_entry_that_runs_into_prose_is_refused(self):
        found = problems("feat: x\n\nAdded: y.\n\nA closing paragraph of prose.\n")
        self.assertTrue(any("spans several lines" in problem for problem in found))

    def test_a_wrapped_line_that_git_cliff_reads_as_a_trailer_is_refused(self):
        for text in (
            "feat: x\n\nAdded: `step::Attempt`, with\n`Attempt::FIRST`.\nRefs #7\n",
            "feat: x\n\nAdded: the type\nis #1 now.\nRefs #7\n",
        ):
            with self.subTest(text=text):
                self.assertTrue(any("cuts the entry before it short" in problem for problem in problems(text)))

    def test_a_body_paragraph_that_git_cliff_reads_as_trailers_is_refused(self):
        found = problems("refactor: x\n\n`a::b()` lists the steps.\n\nRefs #7\n")
        self.assertTrue(any("open the paragraph with other words" in problem for problem in found))

    def test_an_empty_trailer_is_refused_since_git_cliff_takes_the_next_line(self):
        for text in ("feat: x\n\nAdded: y.\nSee:\nAdded: z.\n", "feat: x\n\nAdded: y.\nAcked:\n"):
            with self.subTest(text=text):
                self.assertTrue(any("has nothing after its colon" in problem for problem in problems(text)))

    def test_a_breaking_change_trailer_is_refused_for_the_subjects_mark(self):
        found = problems("refactor: x\n\nBREAKING CHANGE: gone.\nRefs #7\n")
        self.assertTrue(any('Mark a breaking change with "!"' in problem for problem in found))


class Merges(unittest.TestCase):
    def test_a_commit_with_two_parents_is_a_merge(self):
        self.assertTrue(is_merge({"parents": [{"sha": "a"}, {"sha": "b"}]}))
        self.assertFalse(is_merge({"parents": [{"sha": "a"}]}))
