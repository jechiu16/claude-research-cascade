from __future__ import annotations

import unittest

from research_harness._canon import canonical_question


class CanonicalQuestionTests(unittest.TestCase):
    def test_nfc_line_endings_trim_only_outer_whitespace_and_preserve_code(self) -> None:
        question = (
            "\t\n  Cafe\u0301  \r\n"
            "  ```python\r"
            "\tdef f():\r\n"
            "\t\treturn  1\r\n"
            "  ```\n\t  "
        )
        self.assertEqual(
            canonical_question(question),
            "Caf\u00e9  \n  ```python\n\tdef f():\n\t\treturn  1\n  ```",
        )
        self.assertEqual(canonical_question("e\u0301"), "\u00e9")

    def test_internal_spaces_newlines_and_tabs_are_not_collapsed(self) -> None:
        self.assertEqual(canonical_question("  A  B\n\tC\t\tD  "), "A  B\n\tC\t\tD")

    def test_empty_visual_only_and_forbidden_characters_are_rejected(self) -> None:
        invalid = (
            "",
            " \t\n\r",
            "\u0301",
            "Q\u200b",
            "Q\ufeff",
            "Q\u2060",
            *(f"Q{chr(codepoint)}" for codepoint in range(32) if codepoint not in {9, 10, 13}),
            *(f"Q{chr(codepoint)}" for codepoint in range(0x202A, 0x202F)),
            *(f"Q{chr(codepoint)}" for codepoint in range(0x2066, 0x206A)),
        )
        for value in invalid:
            with self.subTest(value=repr(value)), self.assertRaises(ValueError):
                canonical_question(value)


if __name__ == "__main__":
    unittest.main()
