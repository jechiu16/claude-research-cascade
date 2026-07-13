from __future__ import annotations

import unittest

from research_harness._canon import canonical_source_key, normalize_upstream_key


class SourceIdentityTests(unittest.TestCase):
    def test_http_aliases_share_one_canonical_key(self) -> None:
        self.assertEqual(
            canonical_source_key("HTTP://Example.COM:80/path?x=1#fragment"),
            "http://example.com/path?x=1",
        )
        self.assertEqual(
            canonical_source_key("https://EXAMPLE.com:443/path?x=1#fragment"),
            "https://example.com/path?x=1",
        )
        self.assertEqual(
            canonical_source_key("https://example.com"),
            canonical_source_key("https://example.com/"),
        )

    def test_non_default_port_and_path_query_are_preserved(self) -> None:
        self.assertEqual(
            canonical_source_key("HTTPS://Example.COM:8443/a%2Fb?x=1#ignored"),
            "https://example.com:8443/a%2Fb?x=1",
        )

    def test_non_http_source_url_is_rejected(self) -> None:
        with self.assertRaises(ValueError):
            canonical_source_key("ftp://example.com/source")

    def test_upstream_key_normalization_blocks_alias_casing_and_fragments(self) -> None:
        self.assertEqual(
            normalize_upstream_key(" HTTPS://Example.COM:443/feed#fragment "),
            "https://example.com/feed",
        )
        self.assertEqual(normalize_upstream_key(" Publisher-A "), "publisher-a")


if __name__ == "__main__":
    unittest.main()
