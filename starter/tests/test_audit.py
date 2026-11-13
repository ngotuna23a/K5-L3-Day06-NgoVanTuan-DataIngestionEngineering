import unittest

from starter.src.audit import summarize_rows


class AuditTests(unittest.TestCase):
    def row(self, score="", reason="", reviewer=""):
        return {"sample_id": "sample", "score": score, "metadata_ok": score,
                "reason": reason, "reviewer": reviewer, "proposed_score": "2"}

    def test_proposals_do_not_count_as_manual_scores(self):
        result = summarize_rows([self.row()], "score", {"0", "1", "2"})
        self.assertEqual(result["reviewed"], 0)
        self.assertFalse(result["complete"])
        self.assertIsNone(result["mean"])

    def test_confirmed_scores_include_zero(self):
        rows = [self.row("0", "Missing context", "Reviewer"), self.row("2", "Complete", "Reviewer")]
        result = summarize_rows(rows, "score", {"0", "1", "2"})
        self.assertTrue(result["complete"])
        self.assertEqual(result["mean"], 1.0)
        self.assertEqual(result["counts"], {0: 1, 2: 1})

    def test_partial_reviews_have_no_final_average(self):
        rows = [self.row("2", "Complete", "Reviewer"), self.row()]
        result = summarize_rows(rows, "score", {"0", "1", "2"})
        self.assertEqual(result["reviewed"], 1)
        self.assertIsNone(result["mean"])

    def test_reason_and_reviewer_are_required(self):
        for row in [self.row("1", "", "Reviewer"), self.row("1", "Partial", "")]:
            with self.subTest(row=row), self.assertRaises(ValueError):
                summarize_rows([row], "score", {"0", "1", "2"})

    def test_out_of_range_scores_are_rejected(self):
        with self.assertRaises(ValueError):
            summarize_rows([self.row("3", "Invalid", "Reviewer")], "score", {"0", "1", "2"})

    def test_metadata_accepts_only_zero_or_one(self):
        with self.assertRaises(ValueError):
            summarize_rows([self.row("2", "Invalid", "Reviewer")], "metadata_ok", {"0", "1"})


if __name__ == "__main__":
    unittest.main()
