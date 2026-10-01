"""
v0.4 A1 — SKILL.md metadata must satisfy the Agent Skills frontmatter rules.

The slash command is the skill's `name`. A name may use only lowercase letters,
digits and hyphens (at most 64 characters) and may not contain the reserved
words "claude" or "anthropic" — which is why the v0.33 trigger
`/claude_skill_Financial_research` could never resolve (F15). The description is
capped at 1,024 characters (v0.33's was 1,209) and may not contain `<` or `>`.

C8 adds the layout rules: a wrapped body of at most 500 lines, the context
budget stated up front, and progressive disclosure — every reference file is
named in the stage table one level down, and every long one opens with a
Contents list whose links resolve.

    python -m unittest tests.test_v04_meta -v
"""

from __future__ import annotations

import re
import unittest
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent
_SKILL_MD = _REPO_ROOT / "SKILL.md"
_REFERENCES = _REPO_ROOT / "references"
_RESERVED = ("claude", "anthropic")
_MAX_BODY_WIDTH = 120       # the frontmatter description is one YAML plain scalar
_TOC_ABOVE_LINES = 100      # a reference longer than this opens with a Contents list


def parse_skill_md(text: str) -> tuple[dict[str, str], str]:
    """Split SKILL.md into ({key: value} frontmatter, body).

    The frontmatter is a flat block of single-line `key: value` pairs between
    two `---` lines; nothing in this skill needs YAML beyond that.
    """
    lines = text.split("\n")
    if not lines or lines[0].strip() != "---":
        raise ValueError("SKILL.md must open with a '---' frontmatter line")
    try:
        end = next(i for i in range(1, len(lines)) if lines[i].strip() == "---")
    except StopIteration:
        raise ValueError("SKILL.md frontmatter is not closed by a '---' line")
    meta: dict[str, str] = {}
    for line in lines[1:end]:
        if not line.strip():
            continue
        key, sep, value = line.partition(":")
        if not sep:
            raise ValueError(f"frontmatter line is not 'key: value': {line!r}")
        meta[key.strip()] = value.strip()
    return meta, "\n".join(lines[end + 1:])


class TestSkillFrontmatter(unittest.TestCase):
    def setUp(self):
        self.meta, self.body = parse_skill_md(_SKILL_MD.read_text(encoding="utf-8"))

    def test_name_is_a_valid_skill_name(self):
        name = self.meta.get("name", "")
        self.assertRegex(name, r"^[a-z0-9-]{1,64}$")
        for word in _RESERVED:
            self.assertNotIn(word, name, f"skill names may not contain {word!r}")

    def test_slash_command_is_the_name(self):
        self.assertEqual(self.meta.get("name"), "financial-research")

    def test_description_length_and_characters(self):
        desc = self.meta.get("description", "")
        self.assertGreaterEqual(len(desc), 1)
        self.assertLessEqual(len(desc), 1024, f"description is {len(desc)} characters")
        self.assertNotRegex(desc, r"[<>]")

    def test_description_is_a_safe_plain_yaml_scalar(self):
        # A plain scalar may not contain ': ' (starts a mapping) or ' #' (starts
        # a comment); either would silently truncate the description.
        desc = self.meta.get("description", "")
        self.assertNotIn(": ", desc)
        self.assertNotIn(" #", desc)

    def test_description_names_the_real_trigger(self):
        desc = self.meta.get("description", "")
        self.assertIn("/financial-research", desc)
        self.assertNotIn("/claude_skill", desc)

    def test_body_is_at_most_500_lines(self):
        n = len(self.body.splitlines())
        self.assertLessEqual(n, 500, f"SKILL.md body is {n} lines")

    def test_body_lines_are_wrapped(self):
        # C8: v0.34's longest line was 1,222 characters.
        wide = [(i, len(line)) for i, line in enumerate(self.body.splitlines(), 1)
                if len(line) > _MAX_BODY_WIDTH]
        self.assertEqual(wide, [], f"body lines wider than {_MAX_BODY_WIDTH} (line, width)")

    def test_title_names_the_running_version(self):
        import sys
        sys.path.insert(0, str(_REPO_ROOT / "scripts"))
        import run_phase
        title = next(line for line in self.body.splitlines() if line.startswith("# "))
        self.assertEqual(title, f"# Financial Research Skill v{run_phase.VERSION}")

    def test_context_budget_comes_first(self):
        sections = [line for line in self.body.splitlines() if line.startswith("## ")]
        self.assertEqual(sections[0], "## Context budget (read first)")
        budget = self.body.split("## Context budget (read first)")[1].split("\n## ")[0]
        for rule in ("Never Read a PDF", "Never `cat` or Read a large JSON file",
                     "Load a reference file only at its stage", "3 batches of 5"):
            self.assertIn(rule, budget)


def _headings(text: str) -> list[tuple[int, str]]:
    """(level, text) of every ## / ### heading outside fenced code blocks."""
    found, fence = [], False
    for line in text.split("\n"):
        if line.startswith(("```", "~~~")):
            fence = not fence
            continue
        m = None if fence else re.match(r"^(#{2,3}) (.+?)\s*$", line)
        if m:
            found.append((len(m.group(1)), m.group(2)))
    return found


def _anchor(heading: str) -> str:
    """GitHub's heading anchor: lowercase, punctuation dropped, spaces to hyphens."""
    return re.sub(r"[^\w\- ]", "", heading.strip().lower()).replace(" ", "-")


class TestProgressiveDisclosure(unittest.TestCase):
    """C8: references one level deep, and long references navigable by Contents."""

    def setUp(self):
        _, body = parse_skill_md(_SKILL_MD.read_text(encoding="utf-8"))
        table = body.split("### Stage → reference file to read now")[1].split("\n## ")[0]
        self.named = set(re.findall(r"`references/([\w.]+\.md)`", table))

    def test_every_reference_is_named_in_the_stage_table(self):
        on_disk = {p.name for p in _REFERENCES.glob("*.md")}
        self.assertEqual(self.named, on_disk)

    def test_long_references_open_with_contents_that_resolve(self):
        for path in sorted(_REFERENCES.glob("*.md")):
            text = path.read_text(encoding="utf-8")
            lines = text.split("\n")
            if len(lines) <= _TOC_ABOVE_LINES:
                continue
            with self.subTest(reference=path.name):
                self.assertIn("## Contents", lines[:30], "Contents must open the file")
                toc = text.split("## Contents", 1)[1].split("\n## ", 1)[0]
                links = re.findall(r"\]\(#([^)]+)\)", toc)
                sections = [t for level, t in _headings(text) if level == 2 and t != "Contents"]
                anchors = {_anchor(t) for _, t in _headings(text)}
                for title in sections:
                    self.assertIn(_anchor(title), links, f"Contents misses '{title}'")
                for link in links:
                    self.assertIn(link, anchors, f"Contents link #{link} resolves to no heading")


class TestNoStaleTrigger(unittest.TestCase):
    def test_old_trigger_is_only_mentioned_as_history(self):
        # README may explain why the old trigger never worked; nothing may
        # still instruct a user to type it.
        readme = (_REPO_ROOT / "README.md").read_text(encoding="utf-8")
        for line in readme.splitlines():
            if "/claude_skill_Financial_research" in line:
                self.assertRegex(line, r"could never|never resolve|v0\.33",
                                 f"stale trigger instruction: {line!r}")
        skill = _SKILL_MD.read_text(encoding="utf-8")
        self.assertNotIn("/claude_skill_Financial_research", skill)


if __name__ == "__main__":
    unittest.main(verbosity=2)
