import unittest

from starter.src.chunking import by_paragraph, fixed_size
from starter.src.models import DocumentPage


class ChunkingTests(unittest.TestCase):
    def page(self, text):
        return DocumentPage("doc", "source.pdf", 17, text, {"chapter": 1})

    def test_fixed_windows_preserve_overlap_and_source_offsets(self):
        page = self.page("abcdefghijklmno")
        chunks = fixed_size(page, 6, 2)
        self.assertEqual([c.text for c in chunks], ["abcdef", "efghij", "ijklmn", "mno"])
        for chunk in chunks:
            self.assertEqual(chunk.text, page.text[chunk.metadata["char_start"]:chunk.metadata["char_end"]])
            self.assertEqual((chunk.source, chunk.page, chunk.metadata["chapter"]), ("source.pdf", 17, 1))
        self.assertEqual(chunks, fixed_size(page, 6, 2))

    def test_fixed_full_last_window_is_not_followed_by_a_duplicate_tail(self):
        self.assertEqual(len(fixed_size(self.page("abcdefghij"), 6, 2)), 2)

    def test_structure_splits_at_headings_without_blank_lines(self):
        page = self.page("1.1 First topic\nA complete first paragraph.\n1.2 Second topic\nAnother paragraph.")
        chunks = by_paragraph(page, 100)
        self.assertEqual(len(chunks), 2)
        self.assertTrue(chunks[1].text.startswith("1.2 Second topic"))
        self.assertEqual("".join(c.text for c in chunks), page.text)

    def test_oversized_paragraph_preserves_all_characters(self):
        page = self.page("abc def ghi\n" * 30 + "x" * 120)
        chunks = by_paragraph(page, 35)
        self.assertTrue(all(len(c.text) <= 35 for c in chunks))
        self.assertEqual("".join(c.text for c in chunks), page.text)

    def test_consecutive_headings_stay_with_their_body(self):
        page = self.page("1.1 Topic\nLearning objectives\nA sentence that explains the topic.")
        chunks = by_paragraph(page, 200)
        self.assertEqual(len(chunks), 1)
        self.assertEqual(chunks[0].text, page.text)

    def test_blank_pages_have_no_chunks(self):
        self.assertEqual(fixed_size(self.page(" \n"), 10, 0), [])
        self.assertEqual(by_paragraph(self.page(" \n"), 10), [])

    def test_invalid_parameters(self):
        for size, overlap in [(0, 0), (5, 5), (5, -1), (5.5, 1)]:
            with self.subTest(size=size, overlap=overlap), self.assertRaises(ValueError):
                fixed_size(self.page("example"), size, overlap)
        with self.assertRaises(ValueError):
            by_paragraph(self.page("example"), 0)


if __name__ == "__main__":
    unittest.main()
