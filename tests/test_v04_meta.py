"""
v0.4 A1 — SKILL.md metadata must satisfy the Agent Skills frontmatter rules.

The slash command is the skill's `name`. A name may use only lowercase letters,
digits and hyphens (at most 64 characters) and may not contain the reserved
words "claude" or "anthropic" — which is why the v0.33 trigger
`/claude_skill_Financial_research` could never resolve (F15). The description is
capped at 1,024 characters (v0.33's was 1,209) and may not contain `<` or `>`.

    python -m unittest tests.test_v04_meta -v
"""

from __future__ import annotations

import re
import unittest
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent
_SKILL_MD = _REPO_ROOT / "SKILL.md"
_RESERVED = ("claude", "anthropic")


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
